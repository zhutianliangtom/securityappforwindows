# -*- coding: utf-8 -*-
"""验证沙箱放宽逻辑"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from winapp_migrator.core import agent_sandbox as sb

# 路径：应放行
for p in [os.path.expanduser("~/Desktop/a.txt"), "D:/test/b.txt", os.environ["TEMP"] + "/x.log"]:
    print(f"path {p} -> {sb.assess_path(p)}")
# 路径：应拒绝（系统关键目录）
for p in ["C:/Windows/System32/x.dll", "C:/Program Files/App/y.exe", "C:/ProgramData/z.cfg"]:
    print(f"path {p} -> {sb.assess_path(p)}")

# 命令：应放行
for c in ["del D:\\tmp\\a.txt", "mkdir D:\\newdir", "copy a.txt b.txt", "rd D:\\empty"]:
    print(f"cmd  {c} -> {sb.assess_command(c)}")
# 命令：应拒绝（递归/强制/危险）
for c in ["del /s /q C:\\Windows", "rd /s C:\\x", "format d:", "shutdown /s"]:
    print(f"cmd  {c} -> {sb.assess_command(c)}")
print("OK")
