"""Regras de versão exigida, links de download e bloqueio de versões antigas."""
import hashlib
import logging

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from . import conf
from .models import AppVersion

logger = logging.getLogger(__name__)

SALT_DOWNLOAD = "app_update_guard.download"


def current_version():
    """A versão disponível de maior código é a exigida de todos."""
    return AppVersion.objects.filter(active=True).order_by("-version_code").first()


def file_integrity(arquivo):
    """(sha256, tamanho) do arquivo enviado, lido em blocos."""
    digest, tamanho = hashlib.sha256(), 0
    arquivo.seek(0)
    for bloco in arquivo.chunks():
        digest.update(bloco)
        tamanho += len(bloco)
    arquivo.seek(0)
    return digest.hexdigest(), tamanho


def can_download(user):
    if not (user and user.is_authenticated and user.is_active):
        return False
    permissao = conf.get("DOWNLOAD_PERMISSION")
    return not permissao or user.has_perm(permissao)


def absolute_url(request, path):
    """URL absoluta usando PUBLIC_URL quando configurada (evita links com 127.0.0.1)."""
    base = conf.get("PUBLIC_URL").rstrip("/")
    return f"{base}{path}" if base else request.build_absolute_uri(path)


def download_link(user, request):
    """Link pessoal e temporário; entrega a versão exigida no momento do download."""
    token = signing.dumps({"u": user.pk}, salt=SALT_DOWNLOAD, compress=True)
    return absolute_url(request, reverse("app_update_guard:download_token", kwargs={"token": token}))


def user_from_token(token):
    """Usuário do link, ou None se inválido, expirado ou sem permissão."""
    User = get_user_model()
    try:
        dados = signing.loads(token, salt=SALT_DOWNLOAD, max_age=conf.get("LINK_HOURS") * 3600)
        user = User.objects.get(pk=dados["u"])
    except (signing.BadSignature, KeyError, TypeError, User.DoesNotExist):
        return None
    return user if can_download(user) else None


def send_download_link(user, request, subject=None):
    """Envia o link por e-mail. Uma falha é registrada e não interrompe o fluxo."""
    versao = current_version()
    if versao is None or not getattr(user, "email", ""):
        return False
    contexto = {
        "user": user,
        "version": versao,
        "app_name": conf.get("APP_NAME"),
        "url": download_link(user, request),
        "page_url": absolute_url(request, reverse("app_update_guard:download_page")),
        "server_url": absolute_url(request, "/"),
        "valid_hours": conf.get("LINK_HOURS"),
    }
    try:
        send_mail(
            subject=subject or f"Baixe o {conf.get('APP_NAME')}",
            message=render_to_string("app_update_guard/emails/download_link.txt", contexto),
            from_email=None,
            recipient_list=[user.email],
        )
    except Exception:  # noqa: BLE001 - o usuário ainda pode baixar pela página de download
        logger.exception("Falha ao enviar o link do aplicativo para o usuário %s.", user.pk)
        return False
    return True


def installed_code(request):
    """versionCode informado no cabeçalho (só dígitos)."""
    valor = (request.META.get(conf.header_meta_key()) or "").strip()
    return int(valor) if valor.isdigit() else None


def version_data(versao):
    if versao is None:
        return None
    return {
        "version_name": versao.version_name,
        "version_code": versao.version_code,
        "package": versao.package,
        "notes": versao.notes,
        "size": versao.size,
        "sha256": versao.sha256,
        "published_at": versao.created_at.isoformat(),
    }


def version_status(request, code=None):
    """Resposta padrão: usada em GET status/ e no corpo do 426."""
    atual = current_version()
    code = installed_code(request) if code is None else code
    user = getattr(request, "user", None)
    return {
        "current_version": version_data(atual),
        "installed_version_code": code,
        "update_required": bool(atual and (code is None or code < atual.version_code)),
        "download_url": download_link(user, request) if atual and can_download(user) else None,
    }


def update_required_for(request):
    """Situação da versão se a requisição deve ser bloqueada; senão None."""
    if not conf.get("ENFORCE"):
        return None
    situacao = version_status(request)
    if not situacao["update_required"]:
        return None
    # Integrações (ERP, Swagger) não enviam o cabeçalho; se enviarem, são validadas.
    liberar = conf.get("SKIP_WITHOUT_HEADER_PERMISSION")
    user = getattr(request, "user", None)
    if (
        liberar
        and request.META.get(conf.header_meta_key()) is None
        and user is not None
        and user.is_authenticated
        and user.has_perm(liberar)
    ):
        return None
    return situacao
