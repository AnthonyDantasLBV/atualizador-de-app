from django.contrib import admin, messages
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html

from .forms import AppVersionForm
from .models import AppVersion
from .services import current_version
from .views import apk_response


@admin.register(AppVersion)
class AppVersionAdmin(admin.ModelAdmin):
    """Publicação de versões pelo Django Admin."""

    form = AppVersionForm
    list_display = ("version_name", "version_code", "situacao", "tamanho", "created_at", "created_by", "baixar")
    list_filter = ("active",)
    search_fields = ("version_name", "notes")
    readonly_fields = ("package", "sha256", "size", "created_by", "created_at")

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("file", "version_name", "version_code", "notes")
        # Sem o campo do arquivo: o APK não tem URL pública (baixe pela lista).
        return ("version_name", "version_code", "package", "notes", "active",
                "size", "sha256", "created_by", "created_at")

    @admin.display(description="situação")
    def situacao(self, obj):
        atual = current_version()
        if atual and atual.pk == obj.pk:
            return "Exigida"
        return "Disponível" if obj.active else "Retirada"

    @admin.display(description="tamanho")
    def tamanho(self, obj):
        from django.template.defaultfilters import filesizeformat

        return filesizeformat(obj.size)

    @admin.display(description="APK")
    def baixar(self, obj):
        url = reverse("admin:app_update_guard_appversion_apk", args=[obj.pk])
        return format_html('<a href="{}">Baixar</a>', url)

    def get_urls(self):
        extra = [
            path(
                "<int:pk>/apk/",
                self.admin_site.admin_view(self.baixar_apk),
                name="app_update_guard_appversion_apk",
            ),
        ]
        return extra + super().get_urls()

    def baixar_apk(self, request, pk):
        if not self.has_view_permission(request):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        return apk_response(get_object_or_404(AppVersion, pk=pk))

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        atual = current_version()
        if not change:
            messages.info(request, f"Versão {obj} publicada. Aparelhos com versão anterior serão bloqueados até atualizar.")
        elif atual:
            messages.info(request, f"A versão exigida agora é {atual}.")
        else:
            messages.info(request, "Nenhuma versão disponível: o aplicativo não é bloqueado.")
