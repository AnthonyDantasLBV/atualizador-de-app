import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:package_info_plus/package_info_plus.dart';

/// Versão exigida pelo servidor quando o app instalado está desatualizado.
///
/// Lê a resposta de `GET <statusPath>` e o corpo do HTTP 426 do pacote
/// Django `django-app-update-guard` (mesmo formato).
@immutable
class RequiredUpdate {
  const RequiredUpdate({
    this.versionName,
    this.versionCode,
    this.notes,
    this.downloadUrl,
    this.sha256,
  });

  factory RequiredUpdate.fromJson(Map<dynamic, dynamic> data) {
    final current = data['current_version'];
    String? text(Object? value) =>
        value is String && value.trim().isNotEmpty ? value.trim() : null;
    return RequiredUpdate(
      versionName: current is Map ? text(current['version_name']) : null,
      versionCode: current is Map && current['version_code'] is int
          ? current['version_code'] as int
          : null,
      notes: current is Map ? text(current['notes']) : null,
      downloadUrl: text(data['download_url']),
      sha256: current is Map ? _hash(current['sha256']) : null,
    );
  }

  final String? versionName;
  final int? versionCode;
  final String? notes;

  /// Link pessoal e temporário; só vem quando a consulta está autenticada.
  final String? downloadUrl;

  /// SHA-256 do APK publicado, conferido antes de abrir o instalador.
  final String? sha256;

  /// Mantém o link e o hash já conhecidos quando [other] vier sem eles.
  RequiredUpdate merge(RequiredUpdate? other) => other == null
      ? this
      : RequiredUpdate(
          versionName: versionName ?? other.versionName,
          versionCode: versionCode ?? other.versionCode,
          notes: notes ?? other.notes,
          downloadUrl: downloadUrl ?? other.downloadUrl,
          sha256: sha256 ?? other.sha256,
        );

  static String? _hash(Object? value) =>
      value is String && RegExp(r'^[0-9a-fA-F]{64}$').hasMatch(value)
          ? value.toLowerCase()
          : null;
}

/// Estado global "há atualização obrigatória".
///
/// `value == null`: app liberado. Com valor, `AppUpdateGate` troca qualquer
/// tela pela tela de atualização.
class AppUpdateController extends ValueNotifier<RequiredUpdate?> {
  AppUpdateController({
    required this.baseUrl,
    this.token,
    int? versionCode,
    this.statusPath = '/app/status/',
    this.downloadPagePath = '/app/download/',
    this.header = 'X-App-Version',
    Dio? dio,
  })  : _versionCode = versionCode,
        dio = dio ?? Dio(),
        super(null);

  /// Raiz do servidor (ex.: `https://vendas.empresa.com.br`). Uma função,
  /// para acompanhar apps que trocam de servidor em tempo de execução.
  final String Function() baseUrl;

  /// Token de acesso atual (Bearer). Com ele, o servidor envia o link do APK.
  final String? Function()? token;

  /// Caminhos do pacote Django (padrão para `include(...)` em `app/`).
  final String statusPath;
  final String downloadPagePath;

  /// Cabeçalho com o versionCode; o mesmo de `APP_UPDATE_GUARD['HEADER']`.
  final String header;

  /// Cliente usado só na consulta de status (sem interceptors do app).
  final Dio dio;

  int? _versionCode;
  bool _checking = false;

  /// versionCode instalado (número após o + em `version` do pubspec.yaml).
  int? get versionCode => _versionCode;

  /// Lê o versionCode do aparelho (se não foi informado) e consulta o servidor.
  /// Chame uma vez ao iniciar o app.
  Future<void> init() async {
    if (_versionCode == null) {
      try {
        _versionCode = int.tryParse(
          (await PackageInfo.fromPlatform()).buildNumber,
        );
      } catch (_) {
        _versionCode = null;
      }
    }
    await check();
  }

  String get _base {
    final base = baseUrl().trim();
    return base.endsWith('/') ? base.substring(0, base.length - 1) : base;
  }

  /// Página do servidor onde se baixa o app com usuário e senha.
  String? get downloadPageUrl =>
      _base.isEmpty ? null : '$_base$downloadPagePath';

  /// Consulta o servidor. Falha de rede não bloqueia: as rotas protegidas
  /// continuam respondendo 426 se a versão estiver desatualizada.
  Future<void> check() async {
    final base = _base;
    if (_versionCode == null || base.isEmpty || _checking) return;
    _checking = true;
    try {
      final session = token?.call();
      final response = await dio.get<Map<String, dynamic>>(
        '$base$statusPath',
        options: Options(
          headers: {
            header: '$_versionCode',
            if (session != null && session.isNotEmpty)
              'Authorization': 'Bearer $session',
          },
        ),
      );
      final data = response.data;
      if (data == null) return;
      value = data['update_required'] == true
          ? RequiredUpdate.fromJson(data).merge(value)
          : null;
    } on DioException {
      // Servidor fora do ar ou sem a rota: segue sem bloquear.
    } finally {
      _checking = false;
    }
  }

  /// Chamado pelo [AppVersionInterceptor] quando uma rota responde 426.
  void requireUpdate(Object? data) {
    final update =
        data is Map ? RequiredUpdate.fromJson(data) : const RequiredUpdate();
    value = update.merge(value);
  }
}

/// Envia a versão instalada em toda requisição e trata o 426 do servidor.
///
/// Adicione em todos os `Dio` do app:
/// `dio.interceptors.add(AppVersionInterceptor(controller));`
class AppVersionInterceptor extends Interceptor {
  AppVersionInterceptor(this.controller);
  final AppUpdateController controller;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final code = controller.versionCode;
    if (code != null) options.headers[controller.header] = '$code';
    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    if (err.response?.statusCode == 426) {
      controller.requireUpdate(err.response?.data);
    }
    handler.next(err);
  }
}
