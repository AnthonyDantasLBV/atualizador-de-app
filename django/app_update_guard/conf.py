"""Configuração do pacote, lida de ``settings.APP_UPDATE_GUARD``.

Exemplo em ``settings.py``::

    APP_UPDATE_GUARD = {
        "FILES_ROOT": BASE_DIR / "privado",
        "DOWNLOAD_PERMISSION": "usuarios.acessar_app",
        "PUBLIC_URL": "https://vendas.suaempresa.com.br",
    }

Os valores são lidos a cada uso, então ``override_settings`` funciona nos testes.
"""
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

DEFAULTS = {
    # Pasta privada dos APKs (fora de MEDIA_ROOT). Padrão: BASE_DIR / "app_update_files".
    "FILES_ROOT": None,
    # Tamanho máximo do APK aceito na publicação.
    "MAX_SIZE_MB": 200,
    # Validade do link pessoal de download.
    "LINK_HOURS": 168,
    # Com False, nenhuma rota responde 426 (útil em emergências).
    "ENFORCE": True,
    # Cabeçalho com o versionCode instalado, enviado pelo app em toda requisição.
    "HEADER": "X-App-Version",
    # Permissão para baixar o APK (ex.: "usuarios.acessar_app"). None = qualquer usuário ativo.
    "DOWNLOAD_PERMISSION": None,
    # Quem tem esta permissão e NÃO envia o cabeçalho não é bloqueado (integrações, Swagger).
    "SKIP_WITHOUT_HEADER_PERMISSION": None,
    # Raiz pública usada nos links (ex.: "https://vendas.empresa.com.br"). Vazio = endereço da requisição.
    "PUBLIC_URL": "",
    # Nome do aplicativo nas telas e no e-mail.
    "APP_NAME": "Aplicativo",
    # Limite de tentativas da página de download (por IP, dentro da janela).
    "DOWNLOAD_ATTEMPTS": 10,
    "DOWNLOAD_WINDOW_SECONDS": 600,
}


def get(nome):
    if nome not in DEFAULTS:
        raise KeyError(f"Configuração desconhecida do app_update_guard: {nome}")
    return getattr(settings, "APP_UPDATE_GUARD", {}).get(nome, DEFAULTS[nome])


def files_root():
    raiz = get("FILES_ROOT")
    if raiz:
        return Path(raiz)
    base = getattr(settings, "BASE_DIR", None)
    if base is None:
        raise ImproperlyConfigured("Defina APP_UPDATE_GUARD['FILES_ROOT'] (pasta privada dos APKs).")
    return Path(base) / "app_update_files"


def header_meta_key():
    """Nome do cabeçalho em request.META (ex.: HTTP_X_APP_VERSION)."""
    return "HTTP_" + get("HEADER").upper().replace("-", "_")
