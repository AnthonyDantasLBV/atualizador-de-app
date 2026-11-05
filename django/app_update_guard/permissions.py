"""Integração com o Django REST Framework."""
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission

from .services import update_required_for


class UpdateRequired(APIException):
    """HTTP 426 com a situação completa da versão (o app lê o mesmo formato de status/)."""

    status_code = status.HTTP_426_UPGRADE_REQUIRED
    default_code = "update_required"
    default_detail = "Há uma nova versão do aplicativo. Atualize para continuar."

    def __init__(self, situacao):
        super().__init__()
        # Mantém booleanos, números e nulos; o DRF converteria tudo em texto.
        self.detail = {"detail": str(self.default_detail), "code": self.default_code, **situacao}


class RequireCurrentAppVersion(BasePermission):
    """Responde 426 enquanto o app não estiver na versão exigida.

    Combine com a permissão de acesso do seu projeto, por exemplo::

        permission_classes = [IsAuthenticated, RequireCurrentAppVersion]

    Coloque-a depois das permissões de autenticação: assim um usuário sem
    acesso recebe 401/403, e não 426.
    """

    def has_permission(self, request, view):
        situacao = update_required_for(request)
        if situacao is not None:
            raise UpdateRequired(situacao)
        return True
