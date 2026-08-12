# WinAppMigrator

Windows 应用迁移与安全防护桌面工具，基于 PyQt6 开发。集成了应用迁移、安全防护、内存优化、网络防御、应用卸载与 AI 桌面助手等能力。

## 功能特性

### 应用迁移
- 扫描已安装应用（支持传统 Win32 与 UWP 应用）
- 迁移应用主目录及数据目录到其他盘符
- 自动更新注册表路径、快捷方式、AppData 数据目录
- 冲突目录智能处理（询问替换/重命名）
- 迁移前自动终止占用进程，识别 360 安全卫士自保护

### 安全防护
- 恶意进程 / 恶意启动项扫描
- 可疑文件隔离（quarantine）
- 开启防护后立即扫描，之后每 30 秒自动巡检
- 检测到风险或清理失败时触发通知

### 内存优化
- 清理可安全退出的后台进程（非前台进程树）
- 工作集压缩释放物理内存

### 网络防御
- 网络连接监控与恶意地址拦截

### 应用卸载
- 优先调用应用内置卸载器（读取注册表 `UninstallString`，含 WOW6432Node）
- 卸载后清理残留文件、注册表项与快捷方式

### AI 桌面助手
- LLM 驱动的桌面自动化：`截屏分析 → 调用工具 → 截图验证` 闭环
- 三层混合元素定位：UIA 控件树 → Windows OCR → 视觉准星兜底
- 屏幕操控：截图（整屏/窗口/局部放大）、鼠标点击、键盘输入、窗口枚举
- 内置技能（`/技能名` 或 `/技能名 提示` 手动调用）：头脑风暴、复杂任务拆解、测试驱动开发、系统化调试、代码审查、编写计划等
- MCP（Model Context Protocol）客户端：支持 stdio 与 SSE 传输
- 命令沙盒与路径白名单，禁止修改系统关键目录与危险命令
- 多会话管理，对话上下文持久化，自动上下文压缩
- 拖拽图片作为多模态输入

## 技术栈

- Python 3 + PyQt6（界面）
- pywin32 + ctypes（Windows 系统接口，零额外依赖操控屏幕/注册表/进程）
- PyInstaller 打包 + Inno Setup 安装程序

## 快速开始

```bash
pip install -r requirements.txt
python src/main.py
```

## 目录结构

```
src/
├── main.py                    # 程序入口
└── winapp_migrator/
    ├── core/                  # 核心逻辑
    │   ├── migration.py       # 迁移引擎
    │   ├── security.py        # 安全扫描与隔离
    │   ├── memory_optimizer.py# 内存优化
    │   ├── network_defense.py # 网络防御
    │   ├── uninstaller.py     # 应用卸载
    │   ├── registry.py        # 注册表路径更新
    │   ├── shortcut.py        # 快捷方式更新
    │   ├── uwp.py             # UWP 应用迁移
    │   ├── agent_*.py         # AI 助手（引擎/LLM/工具/定位/沙盒/技能）
    │   └── orchestrator.py    # 迁移编排
    └── ui/                    # PyQt6 界面
        ├── main_window.py     # 主窗口
        ├── agent_panel.py     # AI 助手面板
        └── widgets.py         # 通用控件
installer/                     # Inno Setup 安装脚本
build/                         # PyInstaller 打包配置
```

## 打包

```powershell
# 在项目根目录执行
cmd /c installer\build_setup.bat
```

## 免责声明

本工具包含系统级操作（进程终止、注册表修改、文件删除），请在使用前确认操作目标，迁移与卸载操作不可逆。
