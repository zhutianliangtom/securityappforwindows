# -*- coding: utf-8 -*-
"""生成《基于Debian深度定制晨天OS整体方案》极简技术风 PPT
用法: python build_chentianos_ppt.py [封面图片路径]
"""
import sys
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

# ---------------- 主题色 ----------------
BG      = RGBColor(0x0D, 0x11, 0x17)   # 深蓝黑背景
CARD    = RGBColor(0x16, 0x1B, 0x22)   # 卡片底
CARD_LN = RGBColor(0x23, 0x2B, 0x38)   # 分隔线
CYAN    = RGBColor(0x00, 0xD4, 0xFF)   # 主强调青
GREEN   = RGBColor(0x3F, 0xB9, 0x50)   # 辅助绿
AMBER   = RGBColor(0xE3, 0xB3, 0x41)   # 辅助琥珀
TXT     = RGBColor(0xE6, 0xED, 0xF3)   # 主文字
SUB     = RGBColor(0x8B, 0x94, 0x9E)   # 次要文字
WHITE   = RGBColor(0xFF, 0xFF, 0xFF)

SW, SH = Inches(13.333), Inches(7.5)
FONT = "微软雅黑"

prs = Presentation()
prs.slide_width, prs.slide_height = SW, SH
BLANK = prs.slide_layouts[6]

# ---------------- 基础工具 ----------------
def set_font(run, size, color=TXT, bold=False, font=FONT):
    f = run.font
    f.size = Pt(size); f.bold = bold
    f.color.rgb = color; f.name = font
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        e = rPr.find(qn(tag))
        if e is None:
            e = rPr.makeelement(qn(tag), {}); rPr.append(e)
        e.set("typeface", font)

def box(slide, x, y, w, h):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tf

def para(tf, text, size, color=TXT, bold=False, first=False, space=6,
         align=PP_ALIGN.LEFT, segs=None):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align; p.space_after = Pt(space)
    if segs:
        for t, c, b in segs:
            r = p.add_run(); r.text = t
            set_font(r, size, c, b)
    else:
        r = p.add_run(); r.text = text
        set_font(r, size, color, bold)
    return p

def rect(slide, x, y, w, h, fill=CARD, line=None, line_w=0.75, round_=False):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if round_ else MSO_SHAPE.RECTANGLE, x, y, w, h)
    if round_:
        try: shp.adjustments[0] = 0.08
        except Exception: pass
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid(); shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line; shp.line.width = Pt(line_w)
    shp.shadow.inherit = False
    return shp

def set_alpha(shape, opacity):
    srgb = shape.fill.fore_color._xFill.find(qn("a:srgbClr"))
    if srgb is None: return
    a = srgb.makeelement(qn("a:alpha"), {"val": str(int((1 - opacity) * 100000))})
    srgb.append(a)

def new_slide():
    s = prs.slides.add_slide(BLANK)
    rect(s, 0, 0, SW, SH, fill=BG)
    rect(s, 0, 0, SW, Pt(2.5), fill=CYAN)
    c = s.shapes.add_shape(MSO_SHAPE.OVAL, SW - Inches(3.4), SH - Inches(3.4),
                           Inches(3.0), Inches(3.0))
    c.fill.background(); c.line.color.rgb = CARD_LN; c.line.width = Pt(1.2)
    c.shadow.inherit = False
    return s

def header(slide, num, title, en=""):
    t1 = box(slide, Inches(0.62), Inches(0.50), Inches(11.9), Inches(0.4))
    para(t1, num, 13, CYAN, bold=True, first=True, space=0)
    rect(slide, Inches(0.62), Inches(0.80), Inches(0.16), Inches(0.16), fill=CYAN)
    t2 = box(slide, Inches(0.90), Inches(0.70), Inches(11.6), Inches(0.7))
    para(t2, title, 26, WHITE, bold=True, first=True, space=0)
    if en:
        t3 = box(slide, Inches(0.92), Inches(1.42), Inches(11.6), Inches(0.35))
        para(t3, en, 12, SUB, first=True, space=0)
    rect(slide, Inches(0.62), Inches(1.92), Inches(12.09), Pt(1), fill=CARD_LN)

def footer(slide, page):
    rect(slide, Inches(0.62), SH - Inches(0.42), Inches(12.09), Pt(1), fill=CARD_LN)
    t = box(slide, Inches(0.62), SH - Inches(0.38), Inches(9), Inches(0.3))
    para(t, "基于 Debian 深度定制 · 晨天 OS 整体方案", 9, SUB, first=True, space=0)
    t2 = box(slide, Inches(11.6), SH - Inches(0.38), Inches(1.1), Inches(0.3))
    para(t2, "%02d" % page, 9, SUB, first=True, space=0, align=PP_ALIGN.RIGHT)

def card(slide, x, y, w, h, title, lines, accent=CYAN, tcolor=WHITE,
         title_size=15, body_size=12, mark="· "):
    rect(slide, x, y, w, h, fill=CARD, round_=True)
    rect(slide, x, y + Inches(0.26), Pt(3), h - Inches(0.52), fill=accent)
    tf = box(slide, x + Inches(0.32), y + Inches(0.24), w - Inches(0.62), h - Inches(0.46))
    para(tf, title, title_size, tcolor, bold=True, first=True, space=8)
    for ln in lines:
        para(tf, mark + ln, body_size, SUB, space=3)

# ---------------- 封面 ----------------
def cover(img=None):
    s = new_slide()
    if img:
        try:
            s.shapes.add_picture(img, 0, 0, width=SW, height=SH)
            m = rect(s, 0, 0, SW, SH, fill=BG); set_alpha(m, 0.82)
        except Exception:
            pass
    rect(s, Inches(0.9), Inches(1.05), Inches(1.1), Pt(4), fill=CYAN)
    t = box(s, Inches(0.9), Inches(1.35), Inches(11.5), Inches(0.4))
    para(t, "CHENTIAN OS  ·  DEBIAN-BASED  ·  INTERNAL", 13, CYAN, bold=True, first=True, space=0)
    t = box(s, Inches(0.9), Inches(2.15), Inches(11.5), Inches(2.1))
    para(t, "基于 Debian 深度定制", 40, WHITE, bold=True, first=True, space=4)
    para(t, "晨天 OS 整体方案", 40, WHITE, bold=True, space=4,
         segs=[("晨天 OS", WHITE, True)])
    t = box(s, Inches(0.92), Inches(4.35), Inches(11.5), Inches(0.5))
    para(t, "轻 · 快 · 智 —— 新一代桌面操作系统整体设计", 16, SUB, first=True, space=0)
    rect(s, Inches(0.9), Inches(5.05), Inches(2.2), Pt(1), fill=CARD_LN)
    t = box(s, Inches(0.9), Inches(5.25), Inches(11.5), Inches(0.4))
    para(t, "版本 V1.0   ·   2026   ·   内部方案文档", 12, SUB, first=True, space=0)

# ---------------- 目录 ----------------
def toc():
    s = new_slide()
    header(s, "CONTENTS", "方案目录", "Project Roadmap")
    items = [
        ("01", "项目初衷", "WHY · 定位与目标"),
        ("02", "内核裁剪优化", "KERNEL · 瘦身与提速"),
        ("03", "5 秒开机", "BOOT · 全链路手段"),
        ("04", "配套管理面板", "PANEL · 前后端系统"),
        ("05", "自研 MCP 服务", "MCP · AI 能力开放"),
        ("06", "后续迭代规划", "ROADMAP · 演进路径"),
    ]
    for i, (num, zh, en) in enumerate(items):
        col = i // 3; row = i % 3
        x = Inches(0.9) + col * Inches(6.1)
        y = Inches(2.35) + row * Inches(1.42)
        rect(s, x, y, Inches(5.7), Inches(1.12), fill=CARD, round_=True)
        rect(s, x, y, Inches(0.1), Inches(1.12), fill=CYAN)
        t = box(s, x + Inches(0.35), y + Inches(0.2), Inches(1.2), Inches(0.8))
        para(t, num, 26, CYAN, bold=True, first=True, space=0)
        t = box(s, x + Inches(1.7), y + Inches(0.18), Inches(4.0), Inches(0.85))
        para(t, zh, 17, WHITE, bold=True, first=True, space=2)
        para(t, en, 10.5, SUB, space=0)
    footer(s, 2)

# ---------------- 01 项目初衷 ----------------
def p1():
    s = new_slide()
    header(s, "01", "项目初衷", "WHY CHENTIAN OS")
    t = box(s, Inches(0.62), Inches(2.12), Inches(12.09), Inches(0.5))
    para(t, "主流发行版开箱即用的代价：服务冗余、包体臃肿、启动链路漫长——晨天 OS 从内核到用户态全面重做。",
         14, TXT, first=True, space=0)
    data = [
        ("痛点驱动", "系统臃肿", ["默认服务多、软件包冗余", "开机 30s+、内存占用高", "体验卡顿、更新频繁打断"], CYAN),
        ("极致追求", "轻快为先", ["冷启动 ≤ 5 秒", "内存占用降低 40%+", "日常操作秒级响应"], GREEN),
        ("自主可控", "安全可审计", ["内核深度裁剪、攻击面小", "源码级定制、可审计", "构建与升级链路自主"], AMBER),
        ("AI 原生", "系统更懂你", ["内置 AI Agent 与 MCP 服务", "自然语言即可操作系统", "从终端到桌面全面智能"], CYAN),
    ]
    for i, (k, title, lines, ac) in enumerate(data):
        x = Inches(0.62) + (i % 2) * Inches(6.14)
        y = Inches(2.72) + (i // 2) * Inches(2.08)
        card(s, x, y, Inches(5.95), Inches(1.92), title, lines, accent=ac,
             title_size=15, body_size=11.5)
        t = box(s, x + Inches(0.34), y + Inches(0.24), Inches(5.3), Inches(0.5))
        para(t, k, 12, SUB, first=True, space=0)
    footer(s, 3)

# ---------------- 02 内核裁剪优化 ----------------
def p2():
    s = new_slide()
    header(s, "02", "内核裁剪优化", "KERNEL SHRINK & SPEEDUP")
    data = [
        ("配置裁剪", ["按目标硬件平台精简 Kconfig", "仅保留所需驱动与子系统", "内核模块与体积大幅下降"], CYAN),
        ("模块化编译", ["核心功能编入内核 (built-in)", "外设驱动做成可加载模块", "按需加载、减少常驻内存"], GREEN),
        ("initramfs 精简", ["最小化 initramfs 内容", "仅含存储与必要工具", "加速根文件系统挂载"], AMBER),
        ("编译优化", ["O2 + LTO + PGO 回环优化", "去除调试符号与冗余 BTF", "关键路径内联提速"], CYAN),
        ("启动参数优化", ["quiet / loglevel=0", "关闭串口与终端日志输出", "减少启动期 I/O 等待"], GREEN),
        ("systemd 裁剪", ["默认 target 切 multi-user", "禁用无关服务与定时器", "关键服务并行化启动"], AMBER),
    ]
    for i, (title, lines, ac) in enumerate(data):
        x = Inches(0.62) + (i % 3) * Inches(4.15)
        y = Inches(2.25) + (i // 3) * Inches(2.42)
        card(s, x, y, Inches(3.93), Inches(2.26), title, lines, accent=ac,
             title_size=14.5, body_size=11)
    footer(s, 4)

# ---------------- 03 5 秒开机 ----------------
def p3():
    s = new_slide()
    header(s, "03", "5 秒开机：全链路提速手段", "BOOT UNDER 5 SECONDS")
    phases = [
        ("0 ~ 0.8s", "固件层", "UEFI 快启 · 精简 POST", CYAN),
        ("0.8 ~ 2.0s", "内核层", "裁剪内核 · 最小 initramfs", GREEN),
        ("2.0 ~ 3.5s", "并行启动", "systemd 并行 · 驱动延迟加载", AMBER),
        ("3.5 ~ 4.5s", "用户态", "轻量会话 · 直入桌面", CYAN),
        ("4.5 ~ 5.0s", "就绪", "应用预热 · 会话完成", GREEN),
    ]
    for i, (tm, name, desc, ac) in enumerate(phases):
        x = Inches(0.62) + i * Inches(2.44)
        y = Inches(2.30)
        rect(s, x, y, Inches(2.30), Inches(1.55), fill=CARD, round_=True)
        rect(s, x, y, Inches(2.30), Pt(3), fill=ac)
        t = box(s, x + Inches(0.18), y + Inches(0.2), Inches(2.0), Inches(1.3))
        para(t, tm, 15, ac, bold=True, first=True, space=3)
        para(t, name, 14, WHITE, bold=True, space=3)
        para(t, desc, 10, SUB, space=0)
        if i < 4:
            rect(s, x + Inches(2.30), y + Inches(0.62), Inches(0.14), Pt(2), fill=CARD_LN)
    means = [
        ("固件层", "UEFI 快速启动，关闭冗余自检与开机 logo 等待", CYAN),
        ("内核层", "配置裁剪 + 编译优化 + 异步驱动加载，不阻塞启动", GREEN),
        ("文件系统", "EROFS 只读根 + 块层预读缓存，读取更高效", AMBER),
        ("用户态", "systemd 并行化 + 延迟激活 + 轻量桌面会话", CYAN),
        ("电源层", "S2Idle 快速休眠，冷启动与秒级恢复兼顾", GREEN),
    ]
    for i, (name, desc, ac) in enumerate(means):
        x = Inches(0.62) + i * Inches(2.44)
        y = Inches(4.28)
        card(s, x, y, Inches(2.30), Inches(2.20), name, [desc], accent=ac,
             title_size=13.5, body_size=10.5)
    t = box(s, Inches(0.62), Inches(6.62), Inches(12.09), Inches(0.4))
    para(t, "目标：冷启动 ≤ 5 秒（从按下电源键到桌面可交互）—— 全链路流水线化，无一处等待瓶颈",
         12, TXT, first=True, space=0)
    footer(s, 5)

# ---------------- 04 配套管理面板 ----------------
def p4():
    s = new_slide()
    header(s, "04", "配套管理面板", "MANAGEMENT PANEL")
    t = box(s, Inches(0.62), Inches(2.12), Inches(4.8), Inches(0.4))
    para(t, "前后端分离 · 本地 Web 控制台", 14, WHITE, bold=True, first=True, space=0)
    card(s, Inches(0.62), Inches(2.6), Inches(4.75), Inches(1.95), "技术架构",
         ["前端：Vue 3 + TypeScript + Vite", "深色极简 UI · ECharts 实时图表", "后端：Go 本地服务 (127.0.0.1)",
          "RESTful + WebSocket · DBus 对接系统"], accent=CYAN, title_size=14, body_size=11)
    card(s, Inches(0.62), Inches(4.72), Inches(4.75), Inches(1.85), "安全设计",
         ["仅监听本机回环地址", "Token 鉴权 + 会话过期", "可选局域网访问（HTTPS）",
          "操作全量审计日志"], accent=GREEN, title_size=14, body_size=11)
    funcs = [
        ("仪表盘", "CPU/内存/磁盘/温度实时监控"), ("启动分析", "systemd-analyze 耗时可视化"),
        ("服务管理", "启停 / 开机自启 / 依赖图谱"), ("内核调节", "sysctl 参数 · CPU 调频策略"),
        ("软件包", "APT 前端 · 一键更新回滚"), ("系统日志", "journald 检索与导出"),
    ]
    for i, (name, desc) in enumerate(funcs):
        x = Inches(5.72) + (i % 2) * Inches(3.25)
        y = Inches(2.6) + (i // 2) * Inches(1.32)
        rect(s, x, y, Inches(3.05), Inches(1.16), fill=CARD, round_=True)
        rect(s, x, y, Pt(3), Inches(1.16), fill=AMBER if i % 2 else CYAN)
        t = box(s, x + Inches(0.22), y + Inches(0.14), Inches(2.7), Inches(0.95))
        para(t, name, 14, WHITE, bold=True, first=True, space=3)
        para(t, desc, 10.5, SUB, space=0)
    t = box(s, Inches(5.72), Inches(6.72), Inches(7.0), Inches(0.4))
    para(t, "扩展：OTA 在线升级 · 系统健康检查 · 夜间自动优化", 12, TXT, first=True, space=0)
    footer(s, 6)

# ---------------- 05 自研 MCP 服务 ----------------
def p5():
    s = new_slide()
    header(s, "05", "自研 MCP 服务架构", "MODEL CONTEXT PROTOCOL")
    layers = [
        ("AI 会话层", "桌面 AI 助手 · 终端 Agent · 语音入口", CYAN),
        ("MCP Server", "晨天 OS 原生服务 · 统一协议暴露能力", GREEN),
        ("工具注册表", "系统 / 文件 / 服务 / 命令 / 屏幕 标准化工具", AMBER),
        ("能力底座", "DBus · systemd · sysfs · APT · 文件系统", CYAN),
    ]
    y = Inches(2.28)
    for i, (name, desc, ac) in enumerate(layers):
        rect(s, Inches(0.62), y, Inches(5.55), Inches(0.92), fill=CARD, round_=True)
        rect(s, Inches(0.62), y, Pt(3), Inches(0.92), fill=ac)
        t = box(s, Inches(0.92), y + Inches(0.13), Inches(5.1), Inches(0.7))
        para(t, name, 15, WHITE, bold=True, first=True, space=2)
        para(t, desc, 10.5, SUB, space=0)
        if i < 3:
            rect(s, Inches(3.1), y + Inches(0.92), Pt(2), Inches(0.16), fill=CARD_LN)
        y += Inches(1.08)
    t = box(s, Inches(0.62), Inches(6.62), Inches(5.55), Inches(0.4))
    para(t, "统一协议：一次接入，处处可用", 12, TXT, first=True, space=0)
    card(s, Inches(6.5), Inches(2.28), Inches(6.2), Inches(1.62), "为什么自研 MCP",
         ["MCP 让 AI 以标准协议调用系统能力，生态互通", "晨天 OS 原生内置，开箱即用、深度定制",
          "从终端命令到桌面操作的统一 AI 入口"], accent=CYAN, title_size=14, body_size=11)
    card(s, Inches(6.5), Inches(4.06), Inches(6.2), Inches(1.5), "内置工具集",
         ["get_sysinfo · list_files · service_control", "run_cmd(沙盒) · screen_ocr · app_launcher",
          "每个工具可独立鉴权与限流"], accent=GREEN, title_size=14, body_size=11)
    card(s, Inches(6.5), Inches(5.72), Inches(6.2), Inches(1.3), "安全设计",
         ["命令白名单 + 危险操作二次确认", "权限分级 (user/admin) · 全量审计日志"],
         accent=AMBER, title_size=14, body_size=11)
    footer(s, 7)

# ---------------- 06 迭代规划 ----------------
def p6():
    s = new_slide()
    header(s, "06", "后续迭代规划", "ROADMAP")
    miles = [
        ("V1.0", "极简内核", "2026 Q3", ["内核裁剪与编译优化完成", "5 秒开机目标达成", "管理面板 MVP 上线"], CYAN),
        ("V2.0", "智能中枢", "2026 Q4", ["MCP 服务正式开放", "桌面 AI 助手深度集成", "语音控制 / 自主运维"], GREEN),
        ("V3.0", "生态成型", "2027", ["应用商店与分发体系", "x86 / ARM 多硬件适配", "驱动仓库与兼容层"], AMBER),
        ("长期", "自主演进", "持续", ["龙芯 / 飞腾 / 兆芯适配", "社区共建与开源路线图", "滚动发布、月内测季稳定"], CYAN),
    ]
    for i, (ver, name, tm, lines, ac) in enumerate(miles):
        x = Inches(0.62) + i * Inches(3.11)
        rect(s, x, Inches(2.3), Inches(2.95), Inches(3.05), fill=CARD, round_=True)
        rect(s, x, Inches(2.3), Inches(2.95), Pt(3), fill=ac)
        t = box(s, x + Inches(0.26), Inches(2.52), Inches(2.5), Inches(2.7))
        para(t, ver, 24, ac, bold=True, first=True, space=1)
        para(t, name + "  ·  " + tm, 13, WHITE, bold=True, space=6)
        for ln in lines:
            para(t, "· " + ln, 10.5, SUB, space=3)
    rect(s, Inches(0.62), Inches(5.68), Inches(12.09), Inches(0.92), fill=CARD, round_=True)
    rect(s, Inches(0.62), Inches(5.68), Pt(3), Inches(0.92), fill=CYAN)
    t = box(s, Inches(0.95), Inches(5.84), Inches(11.5), Inches(0.66))
    para(t, "迭代节奏：月度内测版 + 季度稳定版，滚动发布", 13, TXT, bold=True, first=True, space=2)
    para(t, "每个版本围绕「更快启动、更低占用、更强智能」三个北极星指标持续演进", 11, SUB, space=0)
    footer(s, 8)

# ---------------- 结束页 ----------------
def p_end():
    s = new_slide()
    t = box(s, Inches(0.9), Inches(2.6), Inches(11.5), Inches(1.6))
    para(t, "让每一台设备，如新生般轻快", 36, WHITE, bold=True, first=True, space=0,
         align=PP_ALIGN.CENTER)
    t = box(s, Inches(0.9), Inches(4.15), Inches(11.5), Inches(0.6))
    para(t, "晨天 OS  ·  轻 快 智", 22, CYAN, bold=True, first=True, space=0,
         align=PP_ALIGN.CENTER)
    rect(s, Inches(5.42), Inches(4.95), Inches(2.5), Pt(1), fill=CARD_LN)
    t = box(s, Inches(0.9), Inches(5.15), Inches(11.5), Inches(0.5))
    para(t, "CHENTIAN OS · 基于 Debian 深度定制 · 感谢聆听", 13, SUB, first=True,
         space=0, align=PP_ALIGN.CENTER)

# ---------------- 组装 ----------------
img = sys.argv[1] if len(sys.argv) > 1 else None
cover(img)
toc()
p1(); p2(); p3(); p4(); p5(); p6()
p_end()

out = r"C:\Users\zhuzhu\Desktop\my first android app\output\chentianos.pptx"
import os
os.makedirs(os.path.dirname(out), exist_ok=True)
prs.save(out)
print("SAVED:", out)
