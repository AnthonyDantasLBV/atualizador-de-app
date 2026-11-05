import 'package:app_update_guard/app_update_guard.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

/// Endereço do servidor Django. Rode com:
/// flutter run --dart-define=SERVIDOR=http://192.168.0.10:8000
const servidor = String.fromEnvironment(
  'SERVIDOR',
  defaultValue: 'http://10.0.2.2:8000',
);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // 1. Controller: lê o versionCode do aparelho e consulta /app/status/.
  final updates = AppUpdateController(
    baseUrl: () => servidor,
    // token: () => sessao?.accessToken,  // com login, o servidor envia o link do APK
  );

  // 2. Interceptor em todos os Dio do app: envia X-App-Version e trata o 426.
  final api = Dio(BaseOptions(baseUrl: servidor));
  api.interceptors.add(AppVersionInterceptor(updates));

  await updates.init();
  runApp(ExemploApp(updates: updates, api: api));
}

class ExemploApp extends StatelessWidget {
  const ExemploApp({required this.updates, required this.api, super.key});

  final AppUpdateController updates;
  final Dio api;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Exemplo app_update_guard',
      theme: ThemeData(colorSchemeSeed: Colors.blue),
      // 3. Gate no builder: com atualização exigida, nenhuma tela fica acessível.
      builder: (context, child) => AppUpdateGate(
        controller: updates,
        texts: const AppUpdateTexts(appName: 'App de Exemplo'),
        child: child ?? const SizedBox.shrink(),
      ),
      home: InicioPage(updates: updates, api: api),
    );
  }
}

class InicioPage extends StatelessWidget {
  const InicioPage({required this.updates, required this.api, super.key});

  final AppUpdateController updates;
  final Dio api;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('App de exemplo')),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('versionCode instalado: ${updates.versionCode ?? '?'}'),
            Text('Servidor: $servidor'),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: updates.check,
              child: const Text('Verificar versão'),
            ),
          ],
        ),
      ),
    );
  }
}
