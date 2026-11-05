import 'dart:convert';
import 'dart:io';

import 'package:app_update_guard/app_update_guard.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Responde às requisições do Dio sem rede.
class FakeAdapter implements HttpClientAdapter {
  FakeAdapter(this.handler);
  final ResponseBody Function(RequestOptions options) handler;
  final requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    return handler(options);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody json(Object body, {int status = 200}) => ResponseBody.fromString(
      jsonEncode(body),
      status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );

final sha = 'a' * 64;

Map<String, Object?> situacao({bool required = true, String? link}) => {
      'current_version': {
        'version_name': '1.2.0',
        'version_code': 5,
        'package': 'com.exemplo.app',
        'notes': 'Correções',
        'size': 10,
        'sha256': sha,
        'published_at': '2026-11-05T10:00:00-03:00',
      },
      'installed_version_code': 4,
      'update_required': required,
      'download_url': link,
    };

AppUpdateController controller(FakeAdapter adapter, {String? token}) =>
    AppUpdateController(
      baseUrl: () => 'http://servidor/',
      token: () => token,
      versionCode: 4,
      dio: Dio()..httpClientAdapter = adapter,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('RequiredUpdate', () {
    test('lê o formato do servidor e ignora hash inválido', () {
      final update = RequiredUpdate.fromJson(situacao(link: 'http://x/apk'));
      expect(update.versionName, '1.2.0');
      expect(update.versionCode, 5);
      expect(update.notes, 'Correções');
      expect(update.downloadUrl, 'http://x/apk');
      expect(update.sha256, sha);
      final semHash = RequiredUpdate.fromJson({
        'current_version': {'sha256': 'curto'},
      });
      expect(semHash.sha256, isNull);
    });

    test('merge mantém link e hash conhecidos', () {
      const antigo = RequiredUpdate(downloadUrl: 'http://x/apk', sha256: 'h');
      final novo = const RequiredUpdate(versionName: '2.0').merge(antigo);
      expect((
        novo.versionName,
        novo.downloadUrl,
        novo.sha256
      ), (
        '2.0',
        'http://x/apk',
        'h',
      ));
    });
  });

  group('AppUpdateController', () {
    test('consulta o status com cabeçalho e token', () async {
      final adapter = FakeAdapter((_) => json(situacao(link: 'http://x/apk')));
      final updates = controller(adapter, token: 'abc');
      await updates.check();
      final request = adapter.requests.single;
      expect(request.uri.toString(), 'http://servidor/app/status/');
      expect(request.headers['X-App-Version'], '4');
      expect(request.headers['Authorization'], 'Bearer abc');
      expect(updates.value?.downloadUrl, 'http://x/apk');
      expect(updates.downloadPageUrl, 'http://servidor/app/download/');
    });

    test('versão em dia libera e falha de rede não bloqueia', () async {
      final updates = controller(
        FakeAdapter((_) => json(situacao(required: false))),
      );
      updates.value = const RequiredUpdate();
      await updates.check();
      expect(updates.value, isNull);

      final offline = controller(
        FakeAdapter((o) => throw DioException(requestOptions: o)),
      );
      await offline.check();
      expect(offline.value, isNull);
    });

    test('interceptor envia a versão e trata o 426', () async {
      final updates = controller(FakeAdapter((_) => json({})));
      final api = Dio()
        ..httpClientAdapter = FakeAdapter((_) => json(situacao(), status: 426))
        ..interceptors.add(AppVersionInterceptor(updates));
      await expectLater(
          api.get('http://servidor/api/x'), throwsA(isA<DioException>()));
      final adapter = api.httpClientAdapter as FakeAdapter;
      expect(adapter.requests.single.headers['X-App-Version'], '4');
      expect(updates.value?.versionName, '1.2.0');
    });
  });

  group('ApkInstaller', () {
    const channel = MethodChannel(ApkInstaller.channelName);
    late Directory pasta;
    late List<MethodCall> chamadas;

    setUp(() {
      pasta = Directory.systemTemp.createTempSync('app_update_guard_');
      chamadas = [];
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
        chamadas.add(call);
        return call.method == 'downloadDirectory' ? pasta.path : true;
      });
    });

    tearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null);
      if (pasta.existsSync()) pasta.deleteSync(recursive: true);
    });

    test('baixa para a pasta do app, limpa antigos e informa progresso',
        () async {
      File('${pasta.path}/update-0.9.apk').writeAsBytesSync([9]);
      final progresso = <double?>[];
      final installer = ApkInstaller(
        supported: true,
        channel: channel,
        dio: Dio()
          ..httpClientAdapter = FakeAdapter(
            (_) => ResponseBody.fromBytes(
              [1, 2, 3],
              200,
              headers: {
                Headers.contentLengthHeader: ['3'],
              },
            ),
          ),
      );
      final path = await installer.download(
        'http://servidor/app/download/t/',
        version: '1.2.0 beta/../x',
        onProgress: progresso.add,
      );
      expect(path, '${pasta.path}/update-1.2.0beta..x.apk');
      expect(File(path).readAsBytesSync(), [1, 2, 3]);
      expect(File('$path.part').existsSync(), isFalse);
      expect(File('${pasta.path}/update-0.9.apk').existsSync(), isFalse);
      expect(progresso.last, 1.0);

      await installer.install(path, sha256: sha);
      final instalar = chamadas.last;
      expect(instalar.method, 'install');
      expect(instalar.arguments, {'path': path, 'sha256': sha});
    });

    test('download com erro não deixa arquivo parcial', () async {
      final installer = ApkInstaller(
        supported: true,
        channel: channel,
        dio: Dio()
          ..httpClientAdapter = FakeAdapter(
            (_) => ResponseBody.fromString('erro', 500),
          ),
      );
      await expectLater(
        installer.download('http://servidor/x'),
        throwsA(isA<DioException>()),
      );
      expect(pasta.listSync(), isEmpty);
    });
  });

  group('AppUpdateGate e AppUpdatePage', () {
    Widget app(AppUpdateController updates, {ApkInstaller? installer}) =>
        MaterialApp(
          home: AppUpdateGate(
            controller: updates,
            installer: installer,
            texts: const AppUpdateTexts(appName: 'App Teste'),
            child: const Text('conteúdo do app'),
          ),
        );

    Future<void> tocar(WidgetTester tester, Key key) async {
      await tester.tap(find.byKey(key));
      for (var i = 0; i < 5; i++) {
        await tester.pump();
      }
    }

    testWidgets('mostra o app e troca pela tela quando exigida', (
      tester,
    ) async {
      final updates = controller(FakeAdapter((_) => json({})));
      await tester.pumpWidget(app(updates));
      expect(find.text('conteúdo do app'), findsOneWidget);
      updates.requireUpdate(situacao());
      await tester.pump();
      expect(find.text('conteúdo do app'), findsNothing);
      expect(find.text('Atualização obrigatória'), findsOneWidget);
      expect(find.textContaining('App Teste (1.2.0)'), findsOneWidget);
      expect(find.text('Correções'), findsOneWidget);
    });

    testWidgets('baixa, confere o hash e abre o instalador', (tester) async {
      final installer = FakeInstaller();
      final updates = controller(FakeAdapter((_) => json({})));
      updates.requireUpdate(situacao(link: 'http://servidor/app/download/t/'));
      await tester.pumpWidget(app(updates, installer: installer));
      expect(find.text('Atualizar agora'), findsOneWidget);
      await tocar(tester, const Key('app_update_primary'));
      expect(installer.calls, ['download', 'canInstall', 'install']);
      expect(installer.downloadedUrl, 'http://servidor/app/download/t/');
      expect(installer.installedSha, sha);
      expect(find.text('Abrir instalador novamente'), findsOneWidget);

      // Cancelou no Android: reabre o instalador sem baixar de novo.
      await tocar(tester, const Key('app_update_primary'));
      expect(installer.calls.where((c) => c == 'download'), hasLength(1));
      expect(installer.calls.last, 'install');
    });

    testWidgets('sem permissão, abre a configuração e instala ao voltar', (
      tester,
    ) async {
      final installer = FakeInstaller(canInstallResult: false);
      // Ao voltar para o app, o gate consulta o servidor de novo.
      final link = 'http://servidor/app/download/t/';
      final updates =
          controller(FakeAdapter((_) => json(situacao(link: link))));
      updates.requireUpdate(situacao(link: link));
      await tester.pumpWidget(app(updates, installer: installer));
      await tocar(tester, const Key('app_update_primary'));
      expect(installer.calls, [
        'download',
        'canInstall',
        'openInstallPermission',
      ]);
      expect(find.text('Permitir instalação'), findsOneWidget);

      installer.canInstallResult = true;
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      for (var i = 0; i < 5; i++) {
        await tester.pump(const Duration(milliseconds: 10));
      }
      expect(installer.calls.last, 'install');
      expect(updates.value, isNotNull);
      expect(find.text('Abrir instalador novamente'), findsOneWidget);
    });

    testWidgets('hash divergente pede para baixar de novo', (tester) async {
      final installer = FakeInstaller(
        installError: PlatformException(code: 'integrity'),
      );
      final updates = controller(FakeAdapter((_) => json({})));
      updates.requireUpdate(situacao(link: 'http://servidor/app/download/t/'));
      await tester.pumpWidget(app(updates, installer: installer));
      await tocar(tester, const Key('app_update_primary'));
      expect(find.text(const AppUpdateTexts().corrupted), findsOneWidget);
      expect(find.text('Atualizar agora'), findsOneWidget);
      installer.installError = null;
      await tocar(tester, const Key('app_update_primary'));
      expect(installer.calls.where((c) => c == 'download'), hasLength(2));
    });

    testWidgets('falha no download mostra erro e permite tentar de novo', (
      tester,
    ) async {
      final installer = FakeInstaller(downloadError: true);
      final updates = controller(FakeAdapter((_) => json({})));
      updates.requireUpdate(situacao(link: 'http://servidor/app/download/t/'));
      await tester.pumpWidget(app(updates, installer: installer));
      await tocar(tester, const Key('app_update_primary'));
      expect(find.text(const AppUpdateTexts().downloadFailed), findsOneWidget);
      expect(find.text('Atualizar agora'), findsOneWidget);
    });

    testWidgets('sem link pessoal, abre a página no navegador', (tester) async {
      final updates = controller(FakeAdapter((_) => json({})));
      updates.requireUpdate(situacao());
      Uri? aberto;
      await tester.pumpWidget(
        MaterialApp(
          home: AppUpdatePage(
            update: updates.value!,
            controller: updates,
            installer: FakeInstaller(),
            openLink: (uri) async {
              aberto = uri;
              return true;
            },
          ),
        ),
      );
      expect(find.text('Baixar atualização'), findsOneWidget);
      await tocar(tester, const Key('app_update_primary'));
      expect(aberto.toString(), 'http://servidor/app/download/');
    });

    testWidgets('"Já atualizei" avisa quando ainda é a versão antiga', (
      tester,
    ) async {
      final updates = controller(FakeAdapter((_) => json(situacao())));
      updates.requireUpdate(situacao());
      await tester.pumpWidget(app(updates));
      await tester.runAsync(() async {
        await tester.tap(find.byKey(const Key('app_update_check_again')));
        await Future<void>.delayed(const Duration(milliseconds: 100));
      });
      await tester.pump();
      expect(find.text(const AppUpdateTexts().stillRequired), findsOneWidget);
    });
  });
}

/// Instalador sem disco nem canal nativo, para testar só a tela.
class FakeInstaller extends ApkInstaller {
  FakeInstaller({
    this.canInstallResult = true,
    this.installError,
    this.downloadError = false,
  }) : super(supported: true);

  bool canInstallResult;
  PlatformException? installError;
  final bool downloadError;
  final calls = <String>[];
  String? downloadedUrl;
  String? installedSha;

  @override
  Future<String> download(
    String url, {
    String? version,
    void Function(double? progress)? onProgress,
    CancelToken? cancelToken,
  }) async {
    calls.add('download');
    downloadedUrl = url;
    if (downloadError) {
      throw DioException(requestOptions: RequestOptions(path: url));
    }
    onProgress?.call(0.5);
    return '/cache/app_update_guard/update.apk';
  }

  @override
  Future<bool> canInstall() async {
    calls.add('canInstall');
    return canInstallResult;
  }

  @override
  Future<bool> openInstallPermission() async {
    calls.add('openInstallPermission');
    return true;
  }

  @override
  Future<void> install(String path, {String? sha256}) async {
    calls.add('install');
    installedSha = sha256;
    final erro = installError;
    if (erro != null) throw erro;
  }
}
