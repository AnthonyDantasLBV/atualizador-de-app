from django.contrib import admin
from django.urls import include, path
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app_update_guard.permissions import RequireCurrentAppVersion


class RotaDoApp(APIView):
    """Exemplo de rota protegida do aplicativo."""

    permission_classes = [IsAuthenticated, RequireCurrentAppVersion]

    def get(self, request):
        return Response({"ok": True})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("app/", include("app_update_guard.urls")),
    path("api/rota/", RotaDoApp.as_view()),
]
