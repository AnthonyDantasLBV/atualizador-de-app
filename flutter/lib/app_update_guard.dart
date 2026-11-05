/// Atualização obrigatória de apps Android distribuídos fora da Play Store.
///
/// Funciona com o pacote Django `django-app-update-guard`:
/// - [AppUpdateController] consulta a versão exigida e guarda o estado;
/// - [AppVersionInterceptor] envia a versão em toda requisição e trata o 426;
/// - [AppUpdateGate] bloqueia o app com a [AppUpdatePage];
/// - [ApkInstaller] baixa o APK e abre o instalador do Android.
library;

export 'src/apk_installer.dart';
export 'src/update_controller.dart';
export 'src/update_gate.dart';
export 'src/update_page.dart';
export 'src/update_texts.dart';
