import 'package:flutter/foundation.dart';

/// Textos da tela de atualização. Os padrões estão em português; troque o que
/// quiser com [copyWith] ou criando a classe com os seus valores.
@immutable
class AppUpdateTexts {
  const AppUpdateTexts({
    this.appName = 'aplicativo',
    this.title = 'Atualização obrigatória',
    this.notes = 'Novidades',
    this.installNow = 'Atualizar agora',
    this.installHelp =
        'O app baixa a nova versão e abre o instalador do Android. '
            'Toque em Instalar para concluir.',
    this.downloading = 'Baixando a atualização…',
    this.allowInstall = 'Permitir instalação',
    this.allowInstallHelp =
        'Para atualizar, permita que este app instale aplicativos: ative a '
            'opção na tela que abriu e volte para o app.',
    this.installerOpened =
        'Toque em Instalar na tela do Android. Ao terminar, abra o app novamente.',
    this.installAgain = 'Abrir instalador novamente',
    this.viaBrowser = 'Baixar pelo navegador',
    this.browserDownload = 'Baixar atualização',
    this.browserHelp =
        'Depois de baixar, abra o arquivo e toque em Instalar. Se o Android '
            'pedir, permita instalar apps a partir do navegador.',
    this.browserHelpViaPage =
        'Abre a página de download no navegador. Entre com seu usuário e '
            'senha, baixe o arquivo e toque em Instalar.',
    this.checkAgain = 'Já atualizei',
    this.stillRequired =
        'Esta ainda é a versão antiga. Instale a atualização baixada e abra o app novamente.',
    this.linkFailed =
        'Não foi possível abrir o link de download. Verifique a internet e tente novamente.',
    this.downloadFailed =
        'Não foi possível baixar a atualização. Verifique a internet e tente novamente.',
    this.corrupted =
        'O arquivo baixado está incompleto ou corrompido. Toque em Atualizar agora para baixar de novo.',
    this.installFailed =
        'Não foi possível abrir o instalador. Use Baixar pelo navegador.',
  });

  final String appName;
  final String title;
  final String notes;
  final String installNow;
  final String installHelp;
  final String downloading;
  final String allowInstall;
  final String allowInstallHelp;
  final String installerOpened;
  final String installAgain;
  final String viaBrowser;
  final String browserDownload;
  final String browserHelp;
  final String browserHelpViaPage;
  final String checkAgain;
  final String stillRequired;
  final String linkFailed;
  final String downloadFailed;
  final String corrupted;
  final String installFailed;

  /// Frase de abertura da tela, com a versão quando o servidor informar.
  String description(String? version) =>
      'Há uma nova versão do $appName${version == null ? '' : ' ($version)'}. '
      'Atualize para continuar.';

  /// Texto do progresso; [progress] vai de 0 a 1 ou é null sem tamanho conhecido.
  String downloadingProgress(double? progress) => progress == null
      ? downloading
      : '$downloading ${(progress * 100).clamp(0, 100).toStringAsFixed(0)}%';

  AppUpdateTexts copyWith({
    String? appName,
    String? title,
    String? notes,
    String? installNow,
    String? installHelp,
    String? downloading,
    String? allowInstall,
    String? allowInstallHelp,
    String? installerOpened,
    String? installAgain,
    String? viaBrowser,
    String? browserDownload,
    String? browserHelp,
    String? browserHelpViaPage,
    String? checkAgain,
    String? stillRequired,
    String? linkFailed,
    String? downloadFailed,
    String? corrupted,
    String? installFailed,
  }) =>
      AppUpdateTexts(
        appName: appName ?? this.appName,
        title: title ?? this.title,
        notes: notes ?? this.notes,
        installNow: installNow ?? this.installNow,
        installHelp: installHelp ?? this.installHelp,
        downloading: downloading ?? this.downloading,
        allowInstall: allowInstall ?? this.allowInstall,
        allowInstallHelp: allowInstallHelp ?? this.allowInstallHelp,
        installerOpened: installerOpened ?? this.installerOpened,
        installAgain: installAgain ?? this.installAgain,
        viaBrowser: viaBrowser ?? this.viaBrowser,
        browserDownload: browserDownload ?? this.browserDownload,
        browserHelp: browserHelp ?? this.browserHelp,
        browserHelpViaPage: browserHelpViaPage ?? this.browserHelpViaPage,
        checkAgain: checkAgain ?? this.checkAgain,
        stillRequired: stillRequired ?? this.stillRequired,
        linkFailed: linkFailed ?? this.linkFailed,
        downloadFailed: downloadFailed ?? this.downloadFailed,
        corrupted: corrupted ?? this.corrupted,
        installFailed: installFailed ?? this.installFailed,
      );
}
