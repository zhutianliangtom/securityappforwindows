; WinAppMigrator Inno Setup 安装脚本
; 前置步骤：先运行 build\build.bat 生成 dist\WinAppMigrator 目录
; 安装页面已注入大量抽象调侃和 emoji，请勿在严肃场合打开此安装包 😎

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
; 让安装向导大一点，更好地展示我们的抽象文学
WizardSizePercent=120,120

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

; ============================================================
; 自定义消息 — 注入灵魂
; ============================================================
[Messages]
; --- 欢迎页 ---
WelcomeLabel2=听说你的 C 盘又红了？🫠%n%n别担心，这不是你的问题，是 Windows 的问题（确信）。%n%n本工具将把你的应用从 C 盘连根拔起，%n搬到它们该去的广袤天地。%n%n准备好了吗？让我们开始这场搬家大冒险 🚚💨

; --- 准备安装页 ---
ReadyLabel2=万事俱备，只欠东风（指你点一下"安装"按钮）。%n%n按下安装后，我们会把 WinAppMigrator 安置到指定目录，%n从此你的 C 盘将获得新生 🌱%n%n⚠ 免责声明：本工具不负责安抚被迁移应用的思乡情绪。

; --- 安装中 ---
; 保持默认即可，Inno Setup 原生就够搞笑了

; --- 完成页 ---
FinishedLabel=恭喜！安装完成 🎉🎉🎉%n%nWinAppMigrator 已就位，随时待命。%n%n现在打开它，开始拯救你的 C 盘吧，勇士！⚔️%n%n记住：%n红色的 C 盘是病，得治。%n本工具就是你的处方药 💊

; --- 管理员权限申请 ---
PrivilegesRequired=本工具需要管理员权限才能施展魔法 🪄%n%n（翻译：搬家需要钥匙，管理员就是那把钥匙）

; --- 卸载确认 ---
ConfirmUninstall=真的要卸载吗？🥺%n%n你的 C 盘可能会想念这个救星的...%n%n（当然，卸载后应用们不会搬回去，它们已经在新家安居乐业了）

; --- 已存在版本 ---
SetupAppRunningError=检测到 WinAppMigrator 正在运行！%n%n请先关闭它再安装，我们暂时不支持平行宇宙 🤯

; --- 磁盘空间不足 ---
DiskSpaceMBLabel=至少需要 [mb] MB 的可用空间。%n%n不会吧不会吧，连这点空间都没有？%n（那你的 C 盘确实需要这个工具了 🙃）

; --- 正在卸载 ---
UninstallStatusLabel=正在移除，请稍候...%n%n应用们：谢谢你的照顾，我们过得很好 👋

; --- 许可协议页（如果有的话） ---
; 保持默认，不搞太抽象

[Tasks]
Name: "desktopicon"; Description: "在桌面创建快捷方式（建议勾上，不然你找不到它 🗺️）"; GroupDescription: "附加图标："

[Files]
Source: "..\dist\WinAppMigrator\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\WinAppMigrator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "🚀 立即启动 WinAppMigrator（C 盘在哭泣，快去吧）"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

; ============================================================
; Code 区 — 更深度的自定义
; ============================================================
[Code]
procedure InitializeWizard;
begin
  { 欢迎页副标题加点料 }
  WizardForm.WelcomeLabel1.Caption := '欢迎使用 WinAppMigrator';
  WizardForm.WelcomeLabel1.Font.Style := [fsBold];

  { 完成页标题 }
  WizardForm.FinishedHeadingLabel.Caption := '✅ 安装完成 — 你的 C 盘救星已上线';
  WizardForm.FinishedHeadingLabel.Font.Style := [fsBold];

  { 准备安装页加个表情 }
  WizardForm.ReadyMemo.Font.Size := 10;

  { 正在安装页标题 }
  WizardForm.InstallingPage.Caption := '正在施展搬家魔法...';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  { 安装确认页，点击"安装"前做最后的调侃 }
  if CurPageID = wpReady then
  begin
    { 直接放行，信息已经在 ReadyLabel2 里了 }
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  { 安装页：显示时改标题为更抽象的表达 }
  if CurPageID = wpInstalling then
  begin
    WizardForm.PageNameLabel.Caption := '正在把文件塞进它们的新家... 📦';
    WizardForm.PageDescriptionLabel.Caption := '稍安勿躁，好工具值得等待 ⏳';
  end;

  { 完成页 }
  if CurPageID = wpFinished then
  begin
    WizardForm.PageNameLabel.Caption := '大功告成！';
    WizardForm.PageDescriptionLabel.Caption := '你已经迈出了拯救 C 盘的第一步 🦶';
  end;
end;