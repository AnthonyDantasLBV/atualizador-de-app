import hashlib
import re
from pathlib import Path

from django.contrib.auth.models import Permission, User
from django.core import mail, signing
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from app_update_guard import conf
from app_update_guard.apk import ApkInvalido, ler_apk, ler_manifesto_binario
from app_update_guard.forms import AppVersionForm
from app_update_guard.models import AppVersion
from app_update_guard.services import (
    SALT_DOWNLOAD,
    current_version,
    download_link,
    send_download_link,
    version_status,
)

from tests.apk_factory import apk_bytes, apk_upload, manifesto_binario

CONFIG = {"FILES_ROOT": Path(__file__).resolve().parent / "_arquivos_teste", "APP_NAME": "App de Teste"}


def publicar(codigo=5, versao="1.2.0", pacote="com.exemplo.app", ativa=True):
    conteudo = apk_bytes(codigo=codigo, versao=versao, pacote=pacote)
    return AppVersion.objects.create(
        version_name=versao, version_code=codigo, package=pacote, active=ativa,
        file=apk_upload(codigo=codigo, versao=versao, pacote=pacote),
        sha256=hashlib.sha256(conteudo).hexdigest(), size=len(conteudo),
    )


class LeituraApkTests(SimpleTestCase):
    def test_le_utf16_utf8_e_atributos_ofuscados(self):
        for kwargs in ({}, {"utf8": True}, {"nomes_ofuscados": True}):
            with self.subTest(**kwargs):
                manifesto = ler_manifesto_binario(manifesto_binario(codigo=7, versao="2.0.1", **kwargs))
                self.assertEqual((manifesto.pacote, manifesto.codigo_versao, manifesto.versao),
                                 ("com.exemplo.app", 7, "2.0.1"))

    def test_recusa_arquivo_que_nao_e_apk(self):
        from io import BytesIO

        with self.assertRaises(ApkInvalido):
            ler_apk(BytesIO(b"nao e zip"))


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user("ana", "ana@example.com", "senha-forte-123")
        cls.admin = User.objects.create_superuser("admin", "admin@example.com", "senha-forte-123")

    def setUp(self):
        cache.clear()


class PublicacaoTests(Base):
    def form(self, arquivo, **dados):
        return AppVersionForm(data=dados, files={"file": arquivo})

    def test_le_versao_do_apk_e_grava_em_pasta_privada(self):
        conteudo = apk_bytes(codigo=12, versao="1.3.0")
        form = self.form(apk_upload(codigo=12, versao="1.3.0"), notes="Novidades")
        self.assertTrue(form.is_valid(), form.errors)
        versao = form.save()
        self.assertEqual((versao.version_name, versao.version_code, versao.package),
                         ("1.3.0", 12, "com.exemplo.app"))
        self.assertEqual((versao.sha256, versao.size), (hashlib.sha256(conteudo).hexdigest(), len(conteudo)))
        self.assertTrue(Path(versao.file.path).resolve().is_relative_to(conf.files_root().resolve()))
        with self.assertRaises(ValueError):
            versao.file.url  # noqa: B018 - o APK nunca tem URL pública

    def test_recusa_codigo_menor_pacote_diferente_e_valor_divergente(self):
        publicar(codigo=10)
        casos = {
            "version_code": (apk_upload(codigo=10), {}),
            "file": (apk_upload(codigo=11, pacote="com.outro.app"), {}),
        }
        for campo, (arquivo, dados) in casos.items():
            with self.subTest(campo=campo):
                form = self.form(arquivo, **dados)
                self.assertFalse(form.is_valid())
                self.assertIn(campo, form.errors)
        form = self.form(apk_upload(codigo=11), version_code=99)
        self.assertFalse(form.is_valid())
        self.assertIn("versão 11", str(form.errors["version_code"]))

    def test_admin_publica_e_baixa_o_apk(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin:app_update_guard_appversion_add"),
                                    {"file": apk_upload(codigo=3, versao="1.0.3"), "notes": ""})
        self.assertEqual(response.status_code, 302)
        versao = AppVersion.objects.get()
        self.assertEqual(versao.created_by, self.admin)
        # Lista e edição abrem; na edição só novidades e disponibilidade mudam.
        self.assertContains(self.client.get(reverse("admin:app_update_guard_appversion_changelist")), "Exigida")
        editar = reverse("admin:app_update_guard_appversion_change", args=[versao.pk])
        self.assertEqual(self.client.get(editar).status_code, 200)
        self.client.post(editar, {"notes": "Correções", "active": ""})
        versao.refresh_from_db()
        self.assertEqual((versao.notes, versao.active, versao.version_code), ("Correções", False, 3))
        arquivo = self.client.get(reverse("admin:app_update_guard_appversion_apk", args=[versao.pk]))
        self.assertEqual(b"".join(arquivo.streaming_content), apk_bytes(codigo=3, versao="1.0.3"))
        arquivo.close()
        self.client.force_login(self.usuario)
        self.assertNotEqual(self.client.get(reverse("admin:app_update_guard_appversion_apk", args=[versao.pk])).status_code, 200)

    def test_retirar_versao_volta_a_exigir_a_anterior(self):
        anterior, nova = publicar(codigo=1, versao="1.0.0"), publicar(codigo=2, versao="1.1.0")
        self.assertEqual(current_version(), nova)
        nova.active = False
        nova.save()
        self.assertEqual(current_version(), anterior)


@override_settings(APP_UPDATE_GUARD={**CONFIG, "DOWNLOAD_PERMISSION": "auth.view_user"})
class StatusEBloqueioTests(Base):
    def setUp(self):
        super().setUp()
        self.usuario.user_permissions.add(Permission.objects.get(codename="view_user"))
        self.api = APIClient()
        self.api.force_authenticate(self.usuario)

    def test_sem_versao_publicada_nao_bloqueia(self):
        self.assertEqual(self.api.get("/api/rota/").status_code, 200)
        dados = self.api.get(reverse("app_update_guard:status")).data
        self.assertEqual((dados["current_version"], dados["update_required"], dados["download_url"]),
                         (None, False, None))

    def test_bloqueia_com_426_desatualizado_ou_sem_cabecalho(self):
        publicar(codigo=5)
        for cabecalho in ({}, {"HTTP_X_APP_VERSION": "4"}):
            with self.subTest(cabecalho=cabecalho):
                response = self.api.get("/api/rota/", **cabecalho)
                self.assertEqual(response.status_code, 426)
                dados = response.json()
                self.assertEqual(dados["code"], "update_required")
                self.assertIs(dados["update_required"], True)
                self.assertEqual(dados["current_version"]["version_code"], 5)
                self.assertIn("/app/download/", dados["download_url"])
        self.assertEqual(self.api.get("/api/rota/", HTTP_X_APP_VERSION="5").status_code, 200)

    def test_status_publico_sem_link_e_parametro_alternativo(self):
        publicar(codigo=5)
        dados = APIClient().get(reverse("app_update_guard:status"), {"version_code": 5}).data
        self.assertEqual((dados["update_required"], dados["download_url"], dados["installed_version_code"]),
                         (False, None, 5))

    def test_usuario_nao_autenticado_recebe_401_e_nao_426(self):
        publicar(codigo=5)
        self.assertIn(APIClient().get("/api/rota/").status_code, {401, 403})

    def test_permissao_de_download_e_obrigatoria_para_o_link(self):
        publicar(codigo=5)
        outro = User.objects.create_user("bia", "bia@example.com", "senha-forte-123")
        api = APIClient()
        api.force_authenticate(outro)
        self.assertIsNone(api.get(reverse("app_update_guard:status")).data["download_url"])

    @override_settings(APP_UPDATE_GUARD={**CONFIG, "SKIP_WITHOUT_HEADER_PERMISSION": "auth.view_user"})
    def test_integracao_sem_cabecalho_continua_e_com_cabecalho_e_validada(self):
        publicar(codigo=5)
        self.assertEqual(self.api.get("/api/rota/").status_code, 200)
        self.assertEqual(self.api.get("/api/rota/", HTTP_X_APP_VERSION="1").status_code, 426)

    @override_settings(APP_UPDATE_GUARD={**CONFIG, "ENFORCE": False})
    def test_bloqueio_pode_ser_desligado(self):
        publicar(codigo=5)
        self.assertEqual(self.api.get("/api/rota/").status_code, 200)

    @override_settings(APP_UPDATE_GUARD={**CONFIG, "HEADER": "X-Versao-App"})
    def test_nome_do_cabecalho_configuravel(self):
        publicar(codigo=5)
        self.assertEqual(self.api.get("/api/rota/", HTTP_X_VERSAO_APP="5").status_code, 200)


class DownloadTests(Base):
    def test_link_pessoal_entrega_versao_atual_e_expira(self):
        publicar(codigo=1, versao="1.0.0")
        link = download_link(self.usuario, RequestFactory().get("/"))
        publicar(codigo=2, versao="1.1.0")
        response = self.client.get(link.split("testserver", 1)[1])
        self.assertEqual(response.status_code, 200)
        self.assertIn("1.1.0", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "no-store")
        response.close()
        token = signing.dumps({"u": self.usuario.pk}, salt=SALT_DOWNLOAD, compress=True)
        with override_settings(APP_UPDATE_GUARD={**CONFIG, "LINK_HOURS": -1}):
            self.assertEqual(self.client.get(reverse("app_update_guard:download_token", args=[token])).status_code, 410)
        self.assertEqual(self.client.get(reverse("app_update_guard:download_token", args=["falso"])).status_code, 410)

    def test_usuario_desativado_perde_o_link(self):
        publicar()
        link = download_link(self.usuario, RequestFactory().get("/"))
        User.objects.filter(pk=self.usuario.pk).update(is_active=False)
        self.assertEqual(self.client.get(link.split("testserver", 1)[1]).status_code, 410)

    def test_pagina_exige_usuario_e_senha_e_limita_tentativas(self):
        publicar()
        url = reverse("app_update_guard:download_page")
        self.assertContains(self.client.get(url), "App de Teste")
        errado = self.client.post(url, {"username": "ana", "password": "errada"})
        self.assertEqual(errado.status_code, 400)
        self.assertNotIn("download_url", errado.context)
        certo = self.client.post(url, {"username": "ana", "password": "senha-forte-123"})
        self.assertIn("/app/download/", certo.context["download_url"])
        for _ in range(10):
            self.client.post(url, {"username": "ana", "password": "errada"})
        self.assertEqual(self.client.post(url, {"username": "ana", "password": "senha-forte-123"}).status_code, 429)

    def test_sem_versao_publicada(self):
        link = download_link(self.usuario, RequestFactory().get("/"))
        self.assertEqual(self.client.get(link.split("testserver", 1)[1]).status_code, 404)

    @override_settings(APP_UPDATE_GUARD={**CONFIG, "PUBLIC_URL": "https://vendas.exemplo.com.br/"})
    def test_url_publica_nos_links_e_no_email(self):
        publicar()
        request = RequestFactory().get("/")
        self.assertTrue(download_link(self.usuario, request).startswith("https://vendas.exemplo.com.br/app/download/"))
        self.assertTrue(send_download_link(self.usuario, request))
        corpo = mail.outbox[-1].body
        self.assertIn("https://vendas.exemplo.com.br/app/download/", corpo)
        self.assertIn("https://vendas.exemplo.com.br/\n", corpo)
        self.assertEqual(mail.outbox[-1].subject, "Baixe o App de Teste")

    def test_email_sem_versao_nao_e_enviado(self):
        self.assertFalse(send_download_link(self.usuario, RequestFactory().get("/")))
        self.assertEqual(len(mail.outbox), 0)

    def test_situacao_sem_requisicao_autenticada(self):
        publicar(codigo=5)
        request = RequestFactory().get("/", HTTP_X_APP_VERSION="5")
        situacao = version_status(request)
        self.assertEqual((situacao["update_required"], situacao["download_url"]), (False, None))
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", situacao["current_version"]["sha256"]))
