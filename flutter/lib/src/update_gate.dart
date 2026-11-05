import 'package:flutter/material.dart';

import 'apk_installer.dart';
import 'update_controller.dart';
import 'update_page.dart';
import 'update_texts.dart';

/// Envolve o app e mostra só a tela de atualização enquanto ela for exigida.
///
/// Use no `builder` do MaterialApp para cobrir todas as rotas:
///
/// ```dart
/// MaterialApp(
///   builder: (context, child) => AppUpdateGate(
///     controller: updates,
///     child: child ?? const SizedBox.shrink(),
///   ),
/// )
/// ```
///
/// Com [checkOnResume], consulta o servidor sempre que o app volta para a tela.
class AppUpdateGate extends StatefulWidget {
  const AppUpdateGate({
    required this.controller,
    required this.child,
    this.texts = const AppUpdateTexts(),
    this.checkOnResume = true,
    this.installer,
    this.pageBuilder,
    super.key,
  });

  final AppUpdateController controller;
  final Widget child;
  final AppUpdateTexts texts;
  final bool checkOnResume;
  final ApkInstaller? installer;

  /// Troca a tela padrão por uma sua, mantendo o bloqueio.
  final Widget Function(BuildContext context, RequiredUpdate update)?
      pageBuilder;

  @override
  State<AppUpdateGate> createState() => _AppUpdateGateState();
}

class _AppUpdateGateState extends State<AppUpdateGate>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (widget.checkOnResume && state == AppLifecycleState.resumed) {
      widget.controller.check();
    }
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<RequiredUpdate?>(
      valueListenable: widget.controller,
      builder: (context, update, _) {
        if (update == null) return widget.child;
        return widget.pageBuilder?.call(context, update) ??
            AppUpdatePage(
              update: update,
              controller: widget.controller,
              texts: widget.texts,
              installer: widget.installer,
            );
      },
    );
  }
}
