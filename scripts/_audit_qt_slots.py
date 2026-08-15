# -*- coding: utf-8 -*-
"""审计：Qt 内建信号直连 self.xxx 且槽函数不接收信号参数（Cython 编译后 PyQt
无法内省签名会照传参数 -> TypeError）。输出需补默认参数的槽清单。"""
import ast
import pathlib
import re

SIG_ARGS = {'clicked': 1, 'toggled': 1, 'triggered': 1, 'stateChanged': 1,
            'currentIndexChanged': 1, 'textChanged': 1, 'valueChanged': 1,
            'activated': 1, 'doubleClicked': 1, 'pressed': 0, 'released': 0,
            'returnPressed': 0, 'editingFinished': 0, 'customContextMenuRequested': 1}

ROOT = pathlib.Path(__file__).resolve().parent.parent / "src" / "winapp_migrator" / "ui"
PAT = re.compile(r'\.([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*connect\s*\(\s*'
                 r'self\.([A-Za-z_][A-Za-z0-9_]*)\s*\)', re.S)

total = 0
for f in sorted(ROOT.glob('*.py')):
    src = f.read_text(encoding='utf-8')
    tree = ast.parse(src)
    extra_of = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef):
            a = n.args
            extra = len(a.args) - 1 - len(a.defaults) - (1 if a.vararg else 0)
            extra_of.setdefault(n.name, []).append(extra)
    hits = {}
    for m in PAT.finditer(src):
        sig, name = m.group(1), m.group(2)
        nargs = SIG_ARGS.get(sig)
        if not nargs:
            continue
        if any(e == 0 for e in extra_of.get(name, [None])) and nargs >= 1:
            hits[name] = sig
    if hits:
        print(f'== {f.name} ==')
        for k, v in sorted(hits.items()):
            print(f'    {k}  <- {v}')
        total += len(hits)
print('总计:', total)
