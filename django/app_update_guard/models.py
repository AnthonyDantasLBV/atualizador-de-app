from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.validators import FileExtensionValidator, RegexValidator
from django.db import models

from . import conf


class PrivateStorage(FileSystemStorage):
    """Arquivos sem URL pública: o APK só sai pelas views que validam o acesso."""

    def url(self, name):
        raise ValueError("Os APKs não têm URL pública; use o link de download do app_update_guard.")


def private_storage():
    """Fora de MEDIA_ROOT; lido das settings a cada uso."""
    return PrivateStorage(location=conf.files_root())


def apk_path(instance, filename):
    """Ignora o nome enviado; grava apk/<pacote>-<versão>-<código>.apk."""
    return f"apk/{instance.package}-{instance.version_name}-{instance.version_code}.apk"


class AppVersion(models.Model):
    version_name = models.CharField(
        "versão",
        max_length=40,
        validators=[RegexValidator(r"^[0-9A-Za-z][0-9A-Za-z.+_-]*$", "Use apenas letras, números, ponto, hífen, + ou _.")],
        help_text="Nome exibido ao usuário (versionName), por exemplo 1.4.0.",
    )
    version_code = models.PositiveIntegerField(
        "código da versão",
        unique=True,
        help_text="versionCode do Android. No Flutter, é o número após o + em version do pubspec.yaml.",
    )
    package = models.CharField("pacote", max_length=255, help_text="applicationId do aplicativo Android.")
    file = models.FileField(
        "arquivo APK",
        upload_to=apk_path,
        storage=private_storage,
        max_length=255,
        validators=[FileExtensionValidator(["apk"])],
    )
    size = models.PositiveBigIntegerField("tamanho (bytes)", default=0, editable=False)
    sha256 = models.CharField("SHA-256", max_length=64, editable=False)
    notes = models.TextField("novidades", blank=True, help_text="Exibido na tela de atualização do app.")
    active = models.BooleanField(
        "disponível",
        default=True,
        help_text="A versão disponível de maior código é a exigida de todos os aparelhos.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="publicado por",
    )
    created_at = models.DateTimeField("publicado em", auto_now_add=True)

    class Meta:
        verbose_name = "versão do aplicativo"
        verbose_name_plural = "versões do aplicativo"
        ordering = ("-version_code",)

    def __str__(self):
        return f"{self.version_name} ({self.version_code})"

    @property
    def download_name(self):
        return f"{self.package}-{self.version_name}.apk"
