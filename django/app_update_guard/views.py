from django import forms
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.http import FileResponse, Http404
from django.shortcuts import render
from django.views import View
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import conf
from .services import can_download, current_version, download_link, user_from_token, version_status

PAGE_TEMPLATE = "app_update_guard/download.html"


def apk_response(versao):
    """Entrega o APK como anexo, sem cache."""
    try:
        arquivo = versao.file.open("rb")
    except FileNotFoundError as exc:
        raise Http404("Arquivo do aplicativo não encontrado.") from exc
    response = FileResponse(
        arquivo,
        as_attachment=True,
        filename=versao.download_name,
        content_type="application/vnd.android.package-archive",
    )
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class StatusView(APIView):
    """GET status/ — situação da versão instalada (pública).

    O app informa o versionCode no cabeçalho configurado (padrão X-App-Version)
    ou em ?version_code=. Com o usuário autenticado (ex.: token JWT), a
    resposta inclui download_url.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        parametro = request.query_params.get("version_code", "").strip()
        codigo = int(parametro) if parametro.isdigit() else None
        return Response(version_status(request, codigo))


class DownloadForm(forms.Form):
    username = forms.CharField(label="Usuário ou e-mail", widget=forms.TextInput(attrs={"autocomplete": "username"}))
    password = forms.CharField(label="Senha", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


class DownloadPageView(View):
    """Página para baixar o APK com usuário e senha (limite de tentativas por IP)."""

    def _chave(self, request):
        return f"app_update_guard:tentativas:{request.META.get('REMOTE_ADDR', '')}"

    def _render(self, request, form, status=200, **extra):
        contexto = {"form": form, "version": current_version(), "app_name": conf.get("APP_NAME"), **extra}
        return render(request, PAGE_TEMPLATE, contexto, status=status)

    def get(self, request):
        return self._render(request, DownloadForm())

    def post(self, request):
        form = DownloadForm(request.POST)
        chave = self._chave(request)
        if cache.get(chave, 0) >= conf.get("DOWNLOAD_ATTEMPTS"):
            form.add_error(None, "Muitas tentativas. Aguarde alguns minutos e tente novamente.")
            return self._render(request, form, status=429)
        if not form.is_valid():
            return self._render(request, form, status=400)
        user = authenticate(request, username=form.cleaned_data["username"], password=form.cleaned_data["password"])
        if not can_download(user):
            janela = conf.get("DOWNLOAD_WINDOW_SECONDS")
            cache.add(chave, 0, janela)
            try:
                cache.incr(chave)
            except ValueError:
                cache.set(chave, 1, janela)
            form.add_error(None, "Usuário ou senha inválidos, ou sem acesso ao aplicativo.")
            return self._render(request, form, status=400)
        cache.delete(chave)
        return self._render(request, form, download_url=download_link(user, request))


class TokenDownloadView(View):
    """Link pessoal: entrega o APK da versão exigida no momento."""

    def get(self, request, token):
        if user_from_token(token) is None:
            contexto = {"invalid_link": True, "version": current_version(), "app_name": conf.get("APP_NAME")}
            return render(request, PAGE_TEMPLATE, contexto, status=410)
        versao = current_version()
        if versao is None:
            return render(request, PAGE_TEMPLATE, {"no_version": True, "app_name": conf.get("APP_NAME")}, status=404)
        return apk_response(versao)
