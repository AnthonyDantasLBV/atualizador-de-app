import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import 'apk_installer.dart';
import 'update_controller.dart';
import 'update_texts.dart';

/// Abre um link fora do app (navegador). Substituível nos testes.
typedef ExternalLinkOpener = Future<bool> Function(Uri uri);

Future<bool> openExternalLink(Uri uri) =>
    launchUrl(uri, mode: LaunchMode.externalApplication);

enum _Phase { idle, downloading, needsPermission, installerOpened }

/// Tela única exibida enquanto houver atualização obrigatória.
///
/// No Android, com o link pessoal do APK, baixa a atualização e abre o
/// instalador; sem o link (ou fora do Android), abre o download no navegador.
class AppUpdatePage extends StatefulWidget {
  const AppUpdatePage({
    required this.update,
    required this.controller,
    this.texts = const AppUpdateTexts(),
    this.installer,
    this.openLink = openExternalLink,
    this.icon = Icons.system_update_rounded,
    super.key,
  });

  final RequiredUpdate update;
  final AppUpdateController controller;
  final AppUpdateTexts texts;
  final ApkInstaller? installer;
  final ExternalLinkOpener openLink;
  final IconData icon;

  @override
  State<AppUpdatePage> createState() => _AppUpdatePageState();
}

class _AppUpdatePageState extends State<AppUpdatePage>
    with WidgetsBindingObserver {
  late final ApkInstaller _installer = widget.installer ?? ApkInstaller();
  final _cancel = CancelToken();
  _Phase _phase = _Phase.idle;
  double? _progress;
  String? _apkPath;
  bool _checking = false;
  String? _error;

  AppUpdateTexts get _t => widget.texts;

  bool get _inApp => _installer.supported && widget.update.downloadUrl != null;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _cancel.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Voltou da configuração de permissão: segue direto para o instalador.
    if (state == AppLifecycleState.resumed &&
        _phase == _Phase.needsPermission) {
      _installDownloaded(askPermission: false);
    }
  }

  Future<void> _update() async {
    if (!_inApp) return _openInBrowser();
    if (_apkPath != null) return _installDownloaded();
    setState(() {
      _phase = _Phase.downloading;
      _progress = null;
      _error = null;
    });
    try {
      _apkPath = await _installer.download(
        widget.update.downloadUrl!,
        version: widget.update.versionName,
        cancelToken: _cancel,
        onProgress: (value) {
          if (mounted) setState(() => _progress = value);
        },
      );
    } on DioException catch (error) {
      if (CancelToken.isCancel(error) || !mounted) return;
      return _fail(_t.downloadFailed);
    } catch (_) {
      if (!mounted) return;
      return _fail(_t.downloadFailed);
    }
    if (!mounted) return;
    await _installDownloaded();
  }

  Future<void> _installDownloaded({bool askPermission = true}) async {
    final path = _apkPath;
    if (path == null) return;
    try {
      if (!await _installer.canInstall()) {
        if (!mounted) return;
        setState(() {
          _phase = _Phase.needsPermission;
          if (askPermission) _error = null;
        });
        // Voltou sem permitir: mantém a orientação na tela.
        if (askPermission) await _installer.openInstallPermission();
        return;
      }
      await _installer.install(path, sha256: widget.update.sha256);
      if (!mounted) return;
      setState(() {
        _phase = _Phase.installerOpened;
        _error = null;
      });
    } on PlatformException catch (error) {
      if (!mounted) return;
      if (error.code == 'integrity' || error.code == 'file') {
        _apkPath = null;
        return _fail(_t.corrupted);
      }
      _fail(_t.installFailed);
    }
  }

  void _fail(String message) {
    setState(() {
      _phase = _Phase.idle;
      _progress = null;
      _error = message;
    });
  }

  Future<void> _openInBrowser() async {
    final link = widget.update.downloadUrl ?? widget.controller.downloadPageUrl;
    final uri = link == null ? null : Uri.tryParse(link);
    var opened = false;
    if (uri != null) {
      try {
        opened = await widget.openLink(uri);
      } catch (_) {
        opened = false;
      }
    }
    if (!mounted) return;
    setState(() => _error = opened ? null : _t.linkFailed);
  }

  Future<void> _checkAgain() async {
    setState(() {
      _checking = true;
      _error = null;
    });
    await widget.controller.check();
    if (!mounted) return;
    setState(() {
      _checking = false;
      // Se ainda estiver desatualizado, a tela continua e avisa.
      if (widget.controller.value != null) _error = _t.stillRequired;
    });
  }

  String get _primaryLabel {
    if (!_inApp) return _t.browserDownload;
    return switch (_phase) {
      _Phase.needsPermission => _t.allowInstall,
      _Phase.installerOpened => _t.installAgain,
      _ => _t.installNow,
    };
  }

  String get _help {
    if (!_inApp) {
      return widget.update.downloadUrl == null
          ? _t.browserHelpViaPage
          : _t.browserHelp;
    }
    return switch (_phase) {
      _Phase.downloading => _t.downloadingProgress(_progress),
      _Phase.needsPermission => _t.allowInstallHelp,
      _Phase.installerOpened => _t.installerOpened,
      _Phase.idle => _t.installHelp,
    };
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final update = widget.update;
    final downloading = _phase == _Phase.downloading;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(widget.icon, size: 64, color: theme.colorScheme.primary),
                  const SizedBox(height: 16),
                  Text(
                    _t.title,
                    textAlign: TextAlign.center,
                    style: theme.textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    _t.description(update.versionName),
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodyMedium,
                  ),
                  if (update.notes != null) ...[
                    const SizedBox(height: 16),
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(_t.notes, style: theme.textTheme.titleSmall),
                            const SizedBox(height: 4),
                            Text(update.notes!),
                          ],
                        ),
                      ),
                    ),
                  ],
                  const SizedBox(height: 24),
                  if (downloading)
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: LinearProgressIndicator(
                        value: _progress,
                        minHeight: 8,
                      ),
                    )
                  else
                    FilledButton.icon(
                      key: const Key('app_update_primary'),
                      onPressed: _update,
                      icon: Icon(
                        _phase == _Phase.needsPermission
                            ? Icons.verified_user_rounded
                            : Icons.system_update_alt_rounded,
                      ),
                      label: Text(_primaryLabel),
                    ),
                  const SizedBox(height: 8),
                  Text(
                    _help,
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodySmall,
                  ),
                  const SizedBox(height: 16),
                  OutlinedButton.icon(
                    key: const Key('app_update_check_again'),
                    onPressed: _checking || downloading ? null : _checkAgain,
                    icon: _checking
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.refresh_rounded),
                    label: Text(_t.checkAgain),
                  ),
                  if (_inApp)
                    TextButton(
                      onPressed: downloading ? null : _openInBrowser,
                      child: Text(_t.viaBrowser),
                    ),
                  if (_error != null) ...[
                    const SizedBox(height: 16),
                    Text(
                      _error!,
                      key: const Key('app_update_error'),
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.error,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
