from django import forms
from django.db.models import Max

from . import conf
from .apk import ApkInvalido, ler_apk
from .models import AppVersion
from .services import file_integrity


class AppVersionForm(forms.ModelForm):
    """Publicação de um APK: versão, código e pacote são lidos do próprio arquivo."""

    class Meta:
        model = AppVersion
        fields = ["file", "version_name", "version_code", "notes", "active"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"accept": ".apk,application/vnd.android.package-archive"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.manifest = None
        self.editing = self.instance.pk is not None
        if self.editing:
            # Depois de publicada, só novidades e disponibilidade mudam.
            for campo in ("file", "version_name", "version_code"):
                if campo in self.fields:
                    self.fields[campo].disabled = True
                    self.fields[campo].required = False
            return
        self.fields["version_name"].required = False
        self.fields["version_code"].required = False
        self.fields["version_name"].help_text = "Lido do APK. Informe só se o arquivo não trouxer a versão."
        self.fields["version_code"].help_text = "Lido do APK (versionCode)."
        self.fields["file"].help_text = f"APK assinado para Android, até {conf.get('MAX_SIZE_MB')} MB."

    def clean_file(self):
        arquivo = self.cleaned_data.get("file")
        if self.editing:
            return self.instance.file
        if not arquivo:
            raise forms.ValidationError("Envie o APK.")
        if arquivo.size > conf.get("MAX_SIZE_MB") * 1024 * 1024:
            raise forms.ValidationError(f"O APK deve ter no máximo {conf.get('MAX_SIZE_MB')} MB.")
        try:
            self.manifest = ler_apk(arquivo)
        except ApkInvalido as exc:
            raise forms.ValidationError(str(exc)) from exc
        return arquivo

    def clean(self):
        dados = super().clean()
        manifesto = self.manifest
        if self.editing or manifesto is None:
            return dados
        for campo, valor_apk in (("version_code", manifesto.codigo_versao), ("version_name", manifesto.versao)):
            informado = dados.get(campo)
            if valor_apk is None:
                if informado in (None, ""):
                    self.add_error(campo, "O APK não informa este dado; preencha manualmente.")
            elif informado not in (None, "") and informado != valor_apk:
                self.add_error(campo, f"O APK enviado é da versão {valor_apk}. Corrija o campo ou envie o arquivo correto.")
            else:
                dados[campo] = valor_apk
        ultima = AppVersion.objects.order_by("-version_code").first()
        if ultima and manifesto.pacote != ultima.package:
            self.add_error("file", f"Este APK é do pacote {manifesto.pacote}, mas as versões cadastradas são de {ultima.package}.")
        codigo = dados.get("version_code")
        maior = AppVersion.objects.aggregate(maior=Max("version_code"))["maior"]
        if codigo is not None and maior is not None and codigo <= maior:
            self.add_error(
                "version_code",
                f"O código da versão deve ser maior que {maior}, o último cadastrado. Gere o APK com um versionCode maior.",
            )
        return dados

    def save(self, commit=True):
        instancia = super().save(commit=False)
        if not self.editing:
            instancia.version_name = self.cleaned_data["version_name"]
            instancia.version_code = self.cleaned_data["version_code"]
            instancia.package = self.manifest.pacote
            instancia.sha256, instancia.size = file_integrity(self.cleaned_data["file"])
        if commit:
            instancia.save()
        return instancia
