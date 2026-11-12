# app-update-guard

Atualização obrigatória de apps Android distribuídos **fora da Play Store**, em duas partes que trabalham juntas:

| Pasta | Pacote | O que faz |
|---|---|---|
| [`django/`](django/) | `django-app-update-guard` (app `app_update_guard`) | Publicação do APK no Django Admin, versão exigida, bloqueio **HTTP 426** nas rotas do app, links pessoais de download, página de download com usuário e senha e e-mail com o link. |
| [`flutter/`](flutter/) | `app_update_guard` (plugin Android) | Envia a versão instalada em toda requisição, trata o 426, bloqueia o app com a tela de atualização, baixa o APK, confere o SHA-256 e abre o instalador do Android. |

## Como funciona

1. O administrador envia o APK no Django Admin. O servidor lê **do próprio arquivo** o `versionCode`, o `versionName` e o pacote, calcula o SHA-256 e guarda o APK numa pasta privada.
2. A versão **disponível** de **maior código** passa a ser a **exigida**.
3. O app envia o `versionCode` no cabeçalho `X-App-Version` em toda requisição.
4. Se o código for menor que o exigido (ou o cabeçalho faltar), as rotas protegidas respondem **426** com os dados da versão e um link pessoal de download.
5. O app troca todas as telas pela tela de atualização. O botão **Atualizar agora** baixa o APK, confere o hash e abre o instalador; o usuário só toca em **Instalar**.

```text
Django Admin ──publica APK──▶ AppVersion (ativa, maior código)
                                   │
App ── X-App-Version ──▶ RequireCurrentAppVersion ──▶ 426 + current_version + download_url
 │                                                            │
 └── AppVersionInterceptor ◀──────────────────────────────────┘
        │
   AppUpdateGate ──▶ AppUpdatePage ──▶ ApkInstaller.download ──▶ GET app/download/<token>/
                                            │
                                   plugin Android: SHA-256 + instalador do Android
```

---

## Parte 1 — Django

### Instalação

```bash
pip install "git+<URL-DO-REPOSITORIO>#subdirectory=django"
```

Requer Django 4.2+ e Django REST Framework 3.14+.

`settings.py`:

```python
INSTALLED_APPS = [
    # ...
    "rest_framework",
    "app_update_guard",
]

APP_UPDATE_GUARD = {
    "FILES_ROOT": BASE_DIR / "privado",               # pasta privada dos APKs (fora de MEDIA_ROOT)
    "APP_NAME": "Isis Entrega",                       # nome nas telas e no e-mail
    "DOWNLOAD_PERMISSION": "usuarios.acessar_app",    # quem pode baixar (None = qualquer usuário ativo)
    "SKIP_WITHOUT_HEADER_PERMISSION": "usuarios.acessar_api_integracao",  # integrações sem cabeçalho
    "PUBLIC_URL": "https://entrega.empresa.com.br",   # raiz usada nos links (evita 127.0.0.1)
}
```

`urls.py`:

```python
path("app/", include("app_update_guard.urls")),
```

```bash
python manage.py migrate
```

### Proteger as rotas do app

Adicione `RequireCurrentAppVersion` **depois** da permissão de acesso do seu projeto (assim quem não tem acesso recebe 401/403, e não 426):

```python
from rest_framework.permissions import IsAuthenticated
from app_update_guard.permissions import RequireCurrentAppVersion


class PedidosView(APIView):
    permission_classes = [IsAuthenticated, RequireCurrentAppVersion]
```

Ou para todas as rotas, em `REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]`.

### Publicar uma versão

**Django Admin → Atualização do aplicativo → Versões do aplicativo → Adicionar**: envie o APK e escreva as novidades. Versão, código e pacote vêm do arquivo. Para retirar uma versão com problema, desmarque **disponível**: a anterior volta a ser exigida.

### Rotas

| Rota | Acesso | Função |
|---|---|---|
| `GET app/status/` | público | Situação da versão (`X-App-Version` ou `?version_code=`). Com usuário autenticado, inclui `download_url`. |
| `GET/POST app/download/` | público | Página para baixar com usuário e senha (limite de tentativas por IP). |
| `GET app/download/<token>/` | quem tem o link | Entrega o APK da versão exigida no momento. |
| `admin/.../appversion/<id>/apk/` | admin | Baixar o APK de uma versão. |

### Resposta (status e corpo do 426)

```json
{
  "detail": "Há uma nova versão do aplicativo. Atualize para continuar.",
  "code": "update_required",
  "current_version": {
    "version_name": "1.2.0",
    "version_code": 5,
    "package": "br.com.empresa.app",
    "notes": "Correções",
    "size": 64512345,
    "sha256": "9f2c…",
    "published_at": "2026-11-05T10:00:00-03:00"
  },
  "installed_version_code": 4,
  "update_required": true,
  "download_url": "https://servidor/app/download/<token>/"
}
```

`detail` e `code` só vêm no 426.

### Configurações (`APP_UPDATE_GUARD`)

| Chave | Padrão | Uso |
|---|---|---|
| `FILES_ROOT` | `BASE_DIR / "app_update_files"` | Pasta privada dos APKs. |
| `MAX_SIZE_MB` | `200` | Tamanho máximo do APK. |
| `LINK_HOURS` | `168` | Validade do link pessoal. |
| `ENFORCE` | `True` | `False` desliga o 426 (emergências). |
| `HEADER` | `"X-App-Version"` | Cabeçalho com o versionCode (o mesmo no app). |
| `DOWNLOAD_PERMISSION` | `None` | Permissão para baixar; `None` = qualquer usuário ativo. |
| `SKIP_WITHOUT_HEADER_PERMISSION` | `None` | Quem tem esta permissão e não envia o cabeçalho não é bloqueado. |
| `PUBLIC_URL` | `""` | Raiz pública dos links; vazio = endereço da requisição. |
| `APP_NAME` | `"Aplicativo"` | Nome nas telas e no e-mail. |
| `DOWNLOAD_ATTEMPTS` / `DOWNLOAD_WINDOW_SECONDS` | `10` / `600` | Limite da página de download por IP. |

### Enviar o link por e-mail

```python
from app_update_guard.services import send_download_link

send_download_link(usuario, request)  # ex.: ao concluir o cadastro do usuário
```

Para mudar o visual, crie no projeto `templates/app_update_guard/download.html` ou `templates/app_update_guard/emails/download_link.txt`.

---

## Parte 2 — Flutter

### Instalação

`pubspec.yaml` do app:

```yaml
dependencies:
  app_update_guard:
    git:
      url: <URL-DO-REPOSITORIO>
      path: flutter
```

Não é preciso mexer no `AndroidManifest.xml`: o plugin já declara a permissão `REQUEST_INSTALL_PACKAGES` e o `FileProvider`.

### Uso

```dart
import 'package:app_update_guard/app_update_guard.dart';

final updates = AppUpdateController(
  baseUrl: () => servidorAtual,          // função: acompanha troca de servidor
  token: () => sessao?.accessToken,      // com o token, o servidor envia o link do APK
  // statusPath: '/app/status/', downloadPagePath: '/app/download/', header: 'X-App-Version'
);

// Em TODOS os Dio do app:
dio.interceptors.add(AppVersionInterceptor(updates));

await updates.init(); // lê o versionCode do aparelho e consulta o servidor

MaterialApp(
  builder: (context, child) => AppUpdateGate(
    controller: updates,
    texts: const AppUpdateTexts(appName: 'Isis Entrega'),
    child: child ?? const SizedBox.shrink(),
  ),
);
```

Chame `updates.check()` também depois do login, para a consulta já vir com o token e trazer o link pessoal. O `AppUpdateGate` consulta de novo sempre que o app volta para a tela.

### Peças

| Classe | Função |
|---|---|
| `AppUpdateController` | Estado "há atualização obrigatória" (`ValueNotifier<RequiredUpdate?>`), consulta `status/`. |
| `AppVersionInterceptor` | Envia `X-App-Version` e transforma o 426 em atualização exigida. |
| `AppUpdateGate` | Mostra o app ou só a tela de atualização; aceita `pageBuilder` para uma tela própria. |
| `AppUpdatePage` | Tela padrão: baixar, permitir instalação, instalar, "Já atualizei", baixar pelo navegador. |
| `ApkInstaller` | Download com progresso, permissão de instalação e instalador (canal nativo `app_update_guard`). |
| `AppUpdateTexts` | Todos os textos (padrão em português), com `copyWith`. |

---

## Regras e cuidados

- **versionCode** é o número depois do `+` em `version:` do `pubspec.yaml` (`1.4.0+12` → `12`). Cada APK publicado precisa de um número **maior** que o anterior.
- **Mesma chave de assinatura.** O Android só aceita a atualização se o APK novo for assinado com a mesma chave do instalado. Guarde a keystore.
- **O Android sempre pede confirmação.** Fora da Play Store não existe instalação silenciosa; na primeira vez o usuário também libera "Instalar apps desconhecidos".
- **Sem sessão, sem link pessoal.** Sem token, a tela abre a página `app/download/` no navegador (usuário e senha).
- **Falha de rede na consulta não bloqueia o app**; o bloqueio vem do 426 das rotas protegidas.

## Desenvolvimento

```bash
# Django
cd django
python runtests.py

# Flutter
cd flutter
flutter test
flutter analyze
```
"# atualizador-de-app" 
