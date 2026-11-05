# app_update_guard

Plugin Flutter (Android) para atualização obrigatória de apps distribuídos fora da Play Store: envia a versão instalada em toda requisição, trata o HTTP 426 do servidor, bloqueia o app com a tela de atualização, baixa o APK, confere o SHA-256 e abre o instalador do Android.

Funciona em conjunto com o pacote Django [`django-app-update-guard`](../django/).

```yaml
dependencies:
  app_update_guard:
    git:
      url: <URL-DO-REPOSITORIO>
      path: flutter
```

```dart
final updates = AppUpdateController(baseUrl: () => servidor, token: () => token);
dio.interceptors.add(AppVersionInterceptor(updates));
await updates.init();

MaterialApp(
  builder: (context, child) => AppUpdateGate(
    controller: updates,
    child: child ?? const SizedBox.shrink(),
  ),
);
```

Guia completo: [README principal](../README.md#parte-2--flutter). Exemplo: [`example/lib/main.dart`](example/lib/main.dart).
