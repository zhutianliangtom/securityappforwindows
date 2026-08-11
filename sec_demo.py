# -*- coding: utf-8 -*-
"""WinAppMigrator 安全模块测试样本（完全无害，仅供检测功能验证）

模拟两类可被「静默防护」检测并清理的恶意行为：
  1. 恶意挖矿进程：复制系统 timeout.exe 为 xmrig.exe 并运行 60 秒
     （timeout.exe 仅执行延时，不做任何危险操作）
  2. 恶意启动项：向 HKCU\\...\\Run 写入 XmrigUpdater（指向上述假进程）

运行本脚本后，打开 WinAppMigrator -> 点击「开启静默防护」，
约 45 秒后右下角应弹出通知：已结束恶意进程、已删除恶意启动项。
"""

import os
import shutil
import subprocess
import winreg

STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_NAME = "XmrigUpdater"


def main():
    tmp = os.path.join(os.environ["TEMP"], "sec_demo")
    os.makedirs(tmp, exist_ok=True)
    fake = os.path.join(tmp, "xmrig.exe")

    # 1) 制造模拟恶意进程（进程名命中特征库 xmrig；运行 300 秒保证检测窗口充足）
    if not os.path.exists(fake):
        shutil.copy2(os.path.join(os.environ["WINDIR"], "System32", "timeout.exe"), fake)
    proc = subprocess.Popen([fake, "300"], creationflags=subprocess.CREATE_NO_WINDOW)
    print(f"[OK] 模拟恶意进程已启动: PID {proc.pid}, 路径 {fake}")

    # 2) 制造恶意启动项（命令含 xmrig 特征，命中启动项特征库）
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY)
    winreg.SetValueEx(key, STARTUP_NAME, 0, winreg.REG_SZ, f'"{fake}" 300')
    winreg.CloseKey(key)
    print(f"[OK] 恶意启动项已写入: HKCU\\{STARTUP_KEY} -> {STARTUP_NAME}")

    print()
    print("请打开 WinAppMigrator，点击「🛡 开启静默防护」。")
    print("开启后立即扫描，右下角应弹出清理通知（结束 xmrig 进程 + 删除启动项）。")
    input("测试结束后按回车，本脚本将还原上述测试样本...")

    # 还原：结束进程、删除启动项、删除临时文件
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, STARTUP_NAME)
        winreg.CloseKey(key)
    except OSError:
        print("  启动项已被防护模块删除（符合预期）")
    for p in (fake,):
        try:
            os.unlink(p)
        except OSError:
            pass
    try:
        os.rmdir(tmp)
    except OSError:
        pass
    print("测试样本已还原，验证完成。")


if __name__ == "__main__":
    main()
