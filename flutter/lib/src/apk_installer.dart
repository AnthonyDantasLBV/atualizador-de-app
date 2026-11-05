import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Baixa o APK da atualização e entrega ao instalador do Android.
///
/// O Android sempre pede a confirmação do usuário ("Instalar"); na primeira
/// vez também pede para permitir que o app instale aplicativos.
class ApkInstaller {
  ApkInstaller({Dio? dio, MethodChannel? channel, bool? supported})
      : _dio = dio ??
            Dio(
              BaseOptions(
                connectTimeout: const Duration(seconds: 20),
                // Tempo máximo sem receber dados, não o tempo total do download.
                receiveTimeout: const Duration(minutes: 2),
              ),
            ),
        _channel = channel ?? const MethodChannel(channelName),
        _supported = supported;

  static const channelName = 'app_update_guard';

  final Dio _dio;
  final MethodChannel _channel;
  final bool? _supported;

  /// Só o Android instala pelo app; nas demais plataformas usa o navegador.
  bool get supported => _supported ?? (!kIsWeb && Platform.isAndroid);

  /// Baixa para a pasta privada do app e devolve o caminho do APK.
  /// [onProgress] recebe de 0 a 1, ou null quando o tamanho é desconhecido.
  Future<String> download(
    String url, {
    String? version,
    void Function(double? progress)? onProgress,
    CancelToken? cancelToken,
  }) async {
    final folder = await _channel.invokeMethod<String>('downloadDirectory');
    if (folder == null) throw StateError('Pasta de download indisponível.');
    final target = File('$folder/update-${_safe(version) ?? 'latest'}.apk');
    final partial = File('${target.path}.part');
    await _clean(Directory(folder));
    try {
      // Baixa num arquivo .part: um download interrompido nunca é instalado.
      await _dio.download(
        url,
        partial.path,
        cancelToken: cancelToken,
        onReceiveProgress: (received, total) =>
            onProgress?.call(total > 0 ? received / total : null),
      );
      await partial.rename(target.path);
    } catch (_) {
      if (await partial.exists()) await partial.delete();
      rethrow;
    }
    return target.path;
  }

  Future<bool> canInstall() async =>
      await _channel.invokeMethod<bool>('canInstall') ?? false;

  /// Abre a configuração "Instalar apps desconhecidos" deste app.
  Future<bool> openInstallPermission() async =>
      await _channel.invokeMethod<bool>('openInstallPermission') ?? false;

  /// Confere o SHA-256 (quando informado) e abre o instalador do Android.
  /// Lança [PlatformException] com `code` "integrity", "file" ou "installer".
  Future<void> install(String path, {String? sha256}) =>
      _channel.invokeMethod<bool>('install', {'path': path, 'sha256': sha256});

  /// Remove downloads anteriores para não acumular APKs no aparelho.
  Future<void> _clean(Directory folder) async {
    if (!await folder.exists()) return;
    await for (final item in folder.list()) {
      if (item is File) {
        try {
          await item.delete();
        } on FileSystemException {
          // Arquivo em uso pelo instalador: fica para a próxima limpeza.
        }
      }
    }
  }

  static String? _safe(String? version) {
    final value = version?.replaceAll(RegExp(r'[^0-9A-Za-z._-]'), '');
    return value == null || value.isEmpty ? null : value;
  }
}
