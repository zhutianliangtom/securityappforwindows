; ╔══════════════════════════════════════════════════════════╗
; ║        WinAppMigrator Inno Setup 安装脚本              ║
; ║  前置：先运行 build\build.bat 生成 dist\WinAppMigrator  ║
; ║  ⚠ 此安装包含有大量 emoji 和抽象文学，慎入 ⚠         ║
; ╚══════════════════════════════════════════════════════════╝

#define MyAppName "WinAppMigrator"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "WinAppMigrator"
#define MyAppExeName "WinAppMigrator.exe"

[Setup]
AppId={{B4A8C5D2-7E1F-4A3B-9C6D-8E2F5A7B1C3D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=..\dist
OutputBaseFilename=WinAppMigrator_Setup
SetupIconFile=..\assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardSizePercent=130
WizardResizable=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

; ============================================================
; 自定义消息 — 注入灵魂 Pro Max
; ============================================================
[Messages]
; --- 欢迎页 ---
WelcomeLabel2=🫠 听说你的 C 盘又红了？🫠%n%n💡 别担心，这不是你的问题 — 是 Windows 的问题（确信）。%n%n🏠 本工具将把你的应用从 C 盘连根拔起，%n搬到它们该去的广袤天地。%n%n🛸 准备好了吗？让我们开始这场搬家大冒险！%n%n        🚚 💨 💨 💨

; --- 准备安装页 ---
ReadyLabel2=📋 万事俱备，只欠东风%n（东风 = 你点一下「安装」按钮）%n%n按下安装后，我们会把 WinAppMigrator 安置妥当，%n从此你的 C 盘将获得新生 🌱🌱🌱%n%n⚠️ 免责声明：%n本工具不负责安抚被迁移应用的思乡情绪。%n它们在新家过得好不好，取决于新盘符的风水 🧧

; --- 完成页 ---
FinishedLabel=🎉 🎉 🎉  恭喜！安装完成  🎉 🎉 🎉%n%n⚔️ WinAppMigrator 已就位，随时待命。%n%n现在打开它，开始拯救你的 C 盘吧，勇士！%n%n%n📌 记住：%n  🔴 红色的 C 盘 = 病，得治。%n  💊 本工具 = 你的处方药。%n%n      C 盘：谢谢你... 🥹

; --- 卸载确认 ---
ConfirmUninstall=🥺 真的要卸载吗？%n%n你的 C 盘可能会想念这个救星的...%n%n（当然，卸载后应用们不会搬回去，%n它们已经在新家安居乐业了 🏡）

; --- 已存在版本 ---
SetupAppRunningError=🤯 检测到 WinAppMigrator 正在运行！%n%n请先关闭它再安装，我们暂时不支持平行宇宙。

; --- 磁盘空间不足 ---
DiskSpaceMBLabel=至少需要 [mb] MB 的可用空间。%n%n😅 不会吧不会吧，连这点空间都没有？%n（那你的 C 盘确实需要这个工具了 🙃）

; --- 正在卸载 ---
UninstallStatusLabel=正在移除，请稍候...%n%n👋 应用们：谢谢你的照顾，我们过得很好！

[Tasks]
Name: "desktopicon"; Description: "🗺️ 在桌面创建快捷方式（强烈建议，不然你找不到它！）"; GroupDescription: "附加图标："

[Files]
Source: "..\dist\WinAppMigrator\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\WinAppMigrator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "🚀 立即启动 WinAppMigrator（C 盘在哭泣，快去吧！）"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

; ============================================================
; Code 区 — 大字报 + 视觉冲击
; ============================================================
[Code]
procedure InitializeWizard;
begin
  { 欢迎页 — 超大标题 }
  WizardForm.WelcomeLabel1.Caption := '🛟 欢迎使用 WinAppMigrator 🛟';
  WizardForm.WelcomeLabel1.Font.Style := [fsBold];
  WizardForm.WelcomeLabel1.Font.Size := 16;
  WizardForm.WelcomeLabel1.Font.Color := clNavy;

  { 欢迎页正文 — 放大 }
  WizardForm.WelcomeLabel2.Font.Size := 11;

  { 完成页标题 — 超大 }
  WizardForm.FinishedHeadingLabel.Caption := '🎉 安装完成 — C 盘救星已上线！';
  WizardForm.FinishedHeadingLabel.Font.Style := [fsBold];
  WizardForm.FinishedHeadingLabel.Font.Size := 16;
  WizardForm.FinishedHeadingLabel.Font.Color := clGreen;

  { 完成页正文 — 放大 }
  WizardForm.FinishedLabel.Font.Size := 11;

  { 准备安装页正文 — 放大 }
  WizardForm.ReadyLabel2.Font.Size := 11;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  { 选择目录页 }
  if CurPageID = wpSelectDir then
  begin
    WizardForm.PageNameLabel.Caption := '📁 选个新家给应用们';
    WizardForm.PageDescriptionLabel.Caption := '应用们：C 盘太挤了，我们要搬去大房子！🏠';
    WizardForm.PageNameLabel.Font.Size := 12;
    WizardForm.PageDescriptionLabel.Font.Size := 10;
  end;

  { 准备安装页 }
  if CurPageID = wpReady then
  begin
    WizardForm.PageNameLabel.Caption := '✅ 准备就绪，蓄势待发';
    WizardForm.PageDescriptionLabel.Caption := '一切就绪，就差你临门一脚 🦶';
    WizardForm.PageNameLabel.Font.Size := 12;
    WizardForm.PageDescriptionLabel.Font.Size := 10;
  end;

  { 安装页 }
  if CurPageID = wpInstalling then
  begin
    WizardForm.PageNameLabel.Caption := '📦 正在把文件塞进它们的新家...';
    WizardForm.PageDescriptionLabel.Caption := '⏳ 稍安勿躁，好工具值得等待。正在施展搬家魔法... 🪄';
    WizardForm.PageNameLabel.Font.Size := 12;
    WizardForm.PageDescriptionLabel.Font.Size := 10;
  end;

  { 完成页 }
  if CurPageID = wpFinished then
  begin
    WizardForm.PageNameLabel.Caption := '🏆 大功告成！';
    WizardForm.PageDescriptionLabel.Caption := '你已经迈出了拯救 C 盘的第一步，历史会记住这一刻 🫡';
    WizardForm.PageNameLabel.Font.Size := 14;
    WizardForm.PageDescriptionLabel.Font.Size := 10;
  end;
end;