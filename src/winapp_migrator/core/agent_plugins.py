"""插件系统：统一管理 MCP 连接与标准技能（SKILL.md）两种扩展。

插件 = 一个目录 ~/.winapp_migrator/plugins/<name>/：
  plugin.json     插件元数据（名称/描述/类型/启用状态/构成）
  SKILL.md        标准技能文件（skill / combined 型插件）
  server.py       本地 stdio MCP server 脚本（mcp / combined 型插件）
  deploy.py       远程 SSE 部署脚本（mcp / combined 型插件，可选）
  requirements.txt  Python 依赖（可选）
  examples/       示例资源文件（可选）

插件类型 kind：
  mcp      仅提供 MCP 工具（本地 stdio 或远程 SSE）
  skill    仅提供标准技能 SKILL.md
  combined 同时提供技能与 MCP 工具

导入插件：zip 包（含 plugin.json）或 已存在目录。连接 MCP 与导入技能统一入口。
"""

import json
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

from winapp_migrator.core import agent_skills

PLUGINS_DIR = Path.home() / ".winapp_migrator" / "plugins"

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,50}$")


def plugins_dir() -> Path:
    """统一插件根目录（不存在则创建）"""
    try:
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return PLUGINS_DIR


def plugin_dir(name: str) -> Path:
    return plugins_dir() / name


def _read_meta(name: str) -> dict:
    d = plugin_dir(name)
    f = d / "plugin.json"
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_meta(name: str, meta: dict) -> bool:
    d = plugin_dir(name)
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / "plugin.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def list_plugins() -> list:
    """扫描插件目录，返回插件元数据列表（含默认字段补齐）"""
    root = plugins_dir()
    out = []
    try:
        names = sorted(p.name for p in root.iterdir() if p.is_dir())
    except OSError:
        names = []
    for n in names:
        meta = _read_meta(n)
        meta.setdefault("name", n)
        meta.setdefault("description", "")
        meta.setdefault("kind", "mcp")
        meta.setdefault("enabled", True)
        meta.setdefault("created_at", "")
        # 推断构成：目录内存在 SKILL.md / server.py
        d = plugin_dir(n)
        has_skill = (d / "SKILL.md").is_file()
        has_mcp = (d / "server.py").is_file() or (d / "deploy.py").is_file()
        meta["has_skill"] = has_skill
        meta["has_mcp"] = has_mcp
        out.append(meta)
    return out


def get_plugin(name: str) -> dict:
    for p in list_plugins():
        if p.get("name") == name:
            return p
    return {}


def _mcp_config_for(meta: dict) -> dict:
    """根据插件元数据重建 MCP 服务器配置（本地 stdio server.py）"""
    name = meta.get("name", "")
    d = plugin_dir(name)
    mcp_name = meta.get("mcp_name") or f"{name}-mcp"
    return {"name": mcp_name, "type": "stdio",
            "command": sys.executable, "args": [str(d / "server.py")]}


def set_plugin_enabled(name: str, enabled: bool) -> tuple:
    """启用/停用插件：停用时不删除文件，仅标记 enabled=False，并从 mcp_servers.json
    移除/恢复对应 MCP 服务器配置（联动生效）。返回 (ok, message)。"""
    meta = _read_meta(name)
    if not meta:
        return False, f"插件「{name}」不存在"
    meta["enabled"] = bool(enabled)
    ok = _write_meta(name, meta)
    if not ok:
        return False, "写入插件配置失败"
    # 联动 MCP：停用移除登记，启用恢复登记
    try:
        servers = agent_skills.load_mcp_servers()
        bound = meta.get("mcp_name")
        if bound:
            if enabled:
                if not any(s.get("name") == bound for s in servers):
                    servers.append(_mcp_config_for(meta))
            else:
                servers = [s for s in servers if s.get("name") != bound]
            agent_skills.save_mcp_servers(servers)
    except Exception:
        pass
    return True, f"已{'启用' if enabled else '停用'}插件「{name}」"


def delete_plugin(name: str) -> tuple:
    """删除插件：移除插件目录；若它登记了 MCP 服务器或技能则一并解绑。"""
    if not _NAME_RE.match(name or ""):
        return False, "插件名不合法"
    d = plugin_dir(name)
    if not d.is_dir():
        return False, f"插件「{name}」不存在"
    meta = _read_meta(name)
    # 1. 解绑已登记的 MCP 服务器（mcp_servers.json）
    try:
        bound = meta.get("mcp_name")
        if bound:
            servers = agent_skills.load_mcp_servers()
            servers = [s for s in servers if s.get("name") != bound]
            agent_skills.save_mcp_servers(servers)
    except Exception:
        pass
    # 2. 解绑已登记的技能（删除技能目录）
    try:
        skill = meta.get("skill_name")
        if skill:
            agent_skills.delete_skill(skill)
    except Exception:
        pass
    # 3. 删除插件目录
    try:
        shutil.rmtree(d)
    except OSError as e:
        return False, f"删除插件目录失败: {e}"
    return True, f"已删除插件「{name}」"


# ---------- 导入 ----------

def import_plugin_zip(zip_path: str) -> tuple:
    """导入插件 zip 包：包内应含 plugin.json（或直接为 <name>/plugin.json 结构）。
    防路径穿越；导入后即成为本地插件。返回 (ok, message)。"""
    p = Path(zip_path or "")
    if not p.is_file():
        return False, "文件不存在"
    root = plugins_dir()
    try:
        with zipfile.ZipFile(p) as z:
            infos = [i for i in z.infolist() if not i.is_dir()]
            metas = [i for i in infos
                     if i.filename.replace("\\", "/").endswith("plugin.json")]
            if not metas:
                return False, "压缩包内未找到 plugin.json"
            # 取第一个 plugin.json 定位插件名；确定需要剥离的顶层前缀
            rel = metas[0].filename.replace("\\", "/")
            parent_dir = "/".join([x for x in rel.split("/") if x][:-1])   # plugin.json 所在目录
            try:
                meta0 = json.loads(z.read(metas[0]))
            except Exception:
                meta0 = {}
            meta_name = str((meta0 or {}).get("name") or "").strip()
            if parent_dir:
                # 插件根 = plugin.json 所在目录的末段；剥离该前缀
                segs = [x for x in parent_dir.split("/") if x]
                name = meta_name or segs[-1]
                strip_prefix = parent_dir + "/"
            else:
                # plugin.json 在包根 → 从元数据读取 name，无需剥离
                name = meta_name
                strip_prefix = ""
            if not _NAME_RE.match(name or ""):
                return False, "插件名仅支持字母/数字/下划线/连字符（≤50 字符）"
            target = root / name
            if target.exists():
                return False, f"插件「{name}」已存在"
            for info in infos:
                relpath = info.filename.replace("\\", "/")
                if relpath.startswith("/") or ".." in relpath.split("/"):
                    return False, "压缩包内含非法路径（拒绝导入）"
                if strip_prefix and relpath.startswith(strip_prefix):
                    relpath = relpath[len(strip_prefix):]
                dest = (target / relpath).resolve()
                if not str(dest).startswith(str(target.resolve())):
                    return False, "压缩包内含越界路径（拒绝导入）"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(info))
        return True, f"已导入插件「{name}」（{target}）"
    except zipfile.BadZipFile:
        return False, "不是有效的 zip 包"
    except OSError as e:
        return False, f"导入失败: {e}"


def import_plugin_skill(skill_path: str) -> tuple:
    """导入标准技能为 skill 型插件：将 SKILL.md（或含 SKILL.md 的 zip）包装为插件。"""
    p = Path(skill_path or "")
    if not p.is_file():
        return False, "文件不存在"
    try:
        # 先借用 agent_skills.import_skill_file 把 SKILL.md（或含 SKILL.md 的 zip）导入技能目录，
        # 技能名取 frontmatter（或文件名）；再把技能目录包装为 skill 型插件
        ok, msg = agent_skills.import_skill_file(str(p))
        if not ok:
            return False, msg
        name = msg.split("「")[-1].split("」")[0] if "「" in msg else p.stem
        skill_src = agent_skills._skills_dir() / name
        return _wrap_skill_dir(name, skill_src)
    except Exception as e:
        return False, f"导入失败: {e}"


def _wrap_skill_dir(name: str, skill_src: Path) -> tuple:
    """把技能目录包装为 skill 型插件：复制到插件目录并登记。"""
    if not _NAME_RE.match(name or ""):
        return False, "插件名仅支持字母/数字/下划线/连字符（≤50 字符）"
    if not skill_src.is_dir():
        return False, f"技能「{name}」不存在"
    if plugin_dir(name).exists():
        return False, f"插件「{name}」已存在"
    try:
        shutil.copytree(skill_src, plugin_dir(name), dirs_exist_ok=True)
    except OSError as e:
        return False, f"复制技能失败: {e}"
    meta = {"name": name, "kind": "skill", "enabled": True,
            "skill_name": name, "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "description": _read_skill_desc(plugin_dir(name) / "SKILL.md")}
    _write_meta(name, meta)
    return True, f"已导入技能插件「{name}」（skill 型）"


def _read_skill_desc(md_path: Path) -> str:
    try:
        txt = md_path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^description:\s*(.+)$", txt, re.M)
        return (m.group(1).strip().strip('"') if m else "") or ""
    except Exception:
        return ""


# ---------- 工具：AI 生成插件 ----------

def create_plugin_from_nl(description: str, kind: str = "combined") -> tuple:
    """用自然语言描述创建插件（真实 AI 生成）：生成 SKILL.md + MCP server 脚本，
    并自动登记到技能目录与 mcp_servers.json。返回 (ok, message)。"""
    from winapp_migrator.core import agent_llm
    desc = (description or "").strip()
    if not desc:
        return False, "请用自然语言描述你想要的插件功能"
    kind = (kind or "combined").strip().lower()
    if kind not in ("mcp", "skill", "combined"):
        kind = "combined"
    try:
        spec = _ai_generate_spec(desc, kind)
    except Exception as e:
        return False, f"AI 生成失败: {e}"
    if not spec:
        return False, "AI 未返回有效插件设计"
    name = str(spec.get("name") or "").strip().lower()
    if not _NAME_RE.match(name or ""):
        return False, "AI 返回的插件名不合法，请换一种描述重试"
    if plugin_dir(name).exists():
        return False, f"插件「{name}」已存在，请换名或删除后重试"
    summary = spec.get("summary") or ""
    skill_md = spec.get("skill_md") or ""
    tools = spec.get("tools") or []
    deps = [str(x).strip() for x in (spec.get("dependencies") or []) if str(x).strip()]
    has_skill = bool(skill_md.strip())
    has_mcp = (kind in ("mcp", "combined")) and bool(tools)
    try:
        d = plugin_dir(name)
        d.mkdir(parents=True, exist_ok=True)
        if has_skill:
            (d / "SKILL.md").write_text(skill_md, encoding="utf-8")
        if has_mcp:
            (d / "server.py").write_text(_assemble_server_py(name, tools), encoding="utf-8")
        if deps:
            (d / "requirements.txt").write_text("\n".join(deps), encoding="utf-8")
        examples = spec.get("examples") or {}
        if isinstance(examples, dict) and examples:
            ex = d / "examples"
            ex.mkdir(parents=True, exist_ok=True)
            for k, v in examples.items():
                (ex / str(k)).write_text(str(v), encoding="utf-8")
        meta = {"name": name, "kind": kind, "enabled": True,
                "description": summary or desc,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        # 登记 MCP：本地 server.py → stdio（本地部署）
        if has_mcp:
            servers = agent_skills.load_mcp_servers()
            mcp_name = f"{name}-mcp"
            meta["mcp_name"] = mcp_name
            servers.append({"name": mcp_name, "type": "stdio",
                            "command": sys.executable,
                            "args": [str(d / "server.py")]})
            agent_skills.save_mcp_servers(servers)
        # 登记技能：SKILL.md 复制到技能目录
        if has_skill:
            ok, msg = agent_skills.create_md_skill(name, summary, skill_md)
            if not ok:
                # 技能已存在或失败时仍保留插件，仅提示
                pass
            else:
                meta["skill_name"] = name
        _write_meta(name, meta)
        lines = [f"已创建插件「{name}」（{kind} 型）",
                 f"描述: {summary or desc}"]
        if has_mcp:
            lines.append(f"MCP: 本地 stdio {d / 'server.py'}")
        if has_skill:
            lines.append(f"技能: /{name} 或对话描述即可调用")
        return True, "\n".join(lines)
    except OSError as e:
        return False, f"创建插件失败: {e}"


def _ai_generate_spec(desc: str, kind: str) -> dict:
    """调用当前配置的 LLM 生成插件设计 JSON（真实 API）。

    AI 只负责设计工具定义与实现逻辑，MCP 协议骨架由 _assemble_server_py 组装，
    保证生成的 server.py 严格符合 agent_mcp 客户端约定的 JSON-RPC 协议。
    """
    from winapp_migrator.core import agent_llm
    cfg = agent_llm.load_model_config()
    client = agent_llm.LLMClient(cfg.get("base_url"), cfg.get("api_key"),
                                 cfg.get("model") or agent_llm.DEFAULT_MODEL)
    sys_p = (
        "你是插件设计专家。根据用户自然语言描述，设计一个可运行的插件，"
        "输出严格 JSON（不要 markdown 代码块包裹），字段如下：\n"
        "{\n"
        '  "name": "插件名（英文，字母数字下划线连字符，≤50字符，小写）",\n'
        '  "summary": "一句话用途简介（中文）",\n'
        '  "skill_md": "（skill/combined 型必填）标准 SKILL.md 正文（含 frontmatter 的完整 markdown，'
        'name/description 字段），描述该插件技能触发条件与执行流程（中文）",\n'
        '  "tools": [（mcp/combined 型必填，1-5 个真实可用工具）{\n'
        '    "name": "工具名（英文小写下划线）",\n'
        '    "description": "工具用途一句话（中文，供 LLM 选择调用）",\n'
        '    "input_schema": {"type":"object","properties":{参数名:{"type":"string|integer|number|boolean",'
        '"description":"参数说明"}},"required":[必填参数名]}（参数为空则 properties:{} 无 required）,\n'
        '    "implementation": "该工具函数体的 Python 代码字符串（用标准库实现真实操作，'
        '函数名 def tool_xxx(args: dict)，从 args 取参，返回 str 文本结果；'
        '不要包含 import 之外的框架代码，异常自行捕获并返回错误说明文本"}\n'
        "  ],\n"
        '  "dependencies": ["（可选）工具实现所需第三方 pip 依赖，如 urllib 等标准库则省略"],\n'
        '  "examples": {"示例文件名": "示例内容"}（可选）\n'
        "}\n"
        f"用户描述: {desc}\n"
        f"插件类型: {kind}（mcp 只需 tools，skill 只需 skill_md，combined 两者都要）")
    try:
        res = client.chat(
            [{"role": "system", "content": sys_p},
             {"role": "user", "content": desc}],
            max_tokens=8192)
        text = (res.get("text") or "").strip()
    except Exception:
        raise
    if not text:
        return {}
    # 提取 JSON（容忍 AI 包裹 ```json ... ```）
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return {}
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


def _split_impl(name: str, impl: str) -> tuple:
    """把 AI 返回的工具实现拆成 (嵌入代码, 调用函数名)。

    AI 可能返回两种形式：
      1. 完整函数定义：`def tool_xxx(args): ...` → 原样嵌入，函数名取 def 名
      2. 仅函数体：`text = args.get(...); return ...` → 包装为 def tool_{name}(args): ...
    保证生成代码语法正确（函数体相对 def 缩进 4 空格）。
    """
    impl = (impl or "").strip()
    if not impl:
        return "", ""
    lines = impl.splitlines()
    # 仅匹配首行 def 签名；body 从后续行完整保留（避免 \s* 吞掉换行导致缩进丢失）
    m = re.match(r"^\s*def\s+([A-Za-z_]\w*)\s*\([^)]*\)\s*(->[^:]*)?:\s*(.*)$", lines[0])
    if m:
        fname = m.group(1)
        inline = m.group(3).strip()
        body_lines = ([inline] if inline else []) + lines[1:]
        if not body_lines:
            return f"def {fname}(args: dict):\n    pass", fname
        nonempty = [ln for ln in body_lines if ln.strip()]
        min_ind = min(len(ln) - len(ln.lstrip()) for ln in nonempty)
        body = "\n".join((ln[min_ind:] if ln.strip() else ln) for ln in body_lines)
        body = "\n".join(("    " + ln) if ln.strip() else ln for ln in body.splitlines())
        return f"def {fname}(args: dict):\n{body}", fname
    # 仅函数体：包装为 def，统一缩进 4 空格
    lines = [ln for ln in impl.splitlines() if ln.strip()]
    if not lines:
        return f"def tool_{name}(args: dict):\n    pass", f"tool_{name}"
    indents = [len(ln) - len(ln.lstrip()) for ln in lines]
    min_ind = min(indents) if indents else 0
    body = "\n".join(("    " + ln[min_ind:]) for ln in lines)
    return f"def tool_{name}(args: dict):\n{body}", f"tool_{name}"


def _assemble_server_py(name: str, tools: list) -> str:
    """把 AI 设计的工具定义与实现，组装成符合 agent_mcp 客户端约定的 MCP stdio server。

    协议：newline-delimited JSON-RPC 2.0（stdin 读请求 / stdout 写响应），
    实现 initialize / notifications/initialized / ping / tools/list / tools/call。
    工具由 AI 提供 implementation（完整 def 或函数体，标准库实现真实操作），
    其余为固定骨架，保证与本地 McpClient 完全兼容。
    """
    tool_entries = []
    impls = []
    handlers = []
    for i, t in enumerate(tools or []):
        if not isinstance(t, dict):
            continue
        tname = str(t.get("name") or f"tool_{i}").strip()
        tdesc = str(t.get("description") or "").strip()
        schema = t.get("input_schema") or {"type": "object", "properties": {}}
        impl = str(t.get("implementation") or "").strip()
        if not tname or not impl:
            continue
        code, fn = _split_impl(tname, impl)
        if not code:
            continue
        tool_entries.append(
            f'    {{"name": {json.dumps(tname, ensure_ascii=False)}, '
            f'"description": {json.dumps(tdesc, ensure_ascii=False)}, '
            f'"inputSchema": {json.dumps(schema, ensure_ascii=False)}}},')
        impls.append(code)
        handlers.append(f'    "{tname}": {fn},')
    if not tool_entries:
        return ""
    tools_txt = "\n".join(tool_entries).rstrip(",")
    impls_txt = "\n\n".join(impls)
    handlers_txt = "\n".join(handlers)
    return f'''"""MCP server（stdio）: {name}

由 AI 设计工具实现 + 固定协议骨架组装，供 WinAppMigrator 的 agent_mcp 客户端连接调用。
协议：newline-delimited JSON-RPC 2.0，stdin 读请求 / stdout 写响应（UTF-8）。
"""

import json
import sys


# ---------- 工具实现（真实 API/系统操作，AI 生成） ----------

{impls_txt}

# ---------- 工具注册表 ----------

TOOLS = [
{tools_txt}
]

_HANDLERS = {{
 {handlers_txt}
 }}


# ---------- JSON-RPC 分发 ----------

def _handle(msg: dict):
    """处理单个请求/通知；通知（无 id）返回 None 不回复"""
    method = msg.get("method", "")
    params = msg.get("params", {{}}) or {{}}
    rid = msg.get("id")

    if method == "initialize":
        return {{"jsonrpc": "2.0", "id": rid, "result": {{
            "protocolVersion": "2024-11-05",
            "capabilities": {{"tools": {{}}}},
            "serverInfo": {{"name": {json.dumps(name)}, "version": "1.0"}},
        }}}}
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {{"jsonrpc": "2.0", "id": rid, "result": {{}}}}
    if method == "tools/list":
        return {{"jsonrpc": "2.0", "id": rid, "result": {{"tools": TOOLS}}}}
    if method == "tools/call":
        tname = params.get("name", "")
        fn = _HANDLERS.get(tname)
        if fn is None:
            return {{"jsonrpc": "2.0", "id": rid,
                    "error": {{"code": -32601, "message": f"未知工具: {{tname}}"}}}}
        try:
            text = fn(params.get("arguments", {{}}) or {{}})
            result = {{"content": [{{"type": "text", "text": text}}], "isError": False}}
        except Exception as e:
            result = {{"content": [{{"type": "text", "text": str(e)}}], "isError": True}}
        return {{"jsonrpc": "2.0", "id": rid, "result": result}}
    return {{"jsonrpc": "2.0", "id": rid,
            "error": {{"code": -32601, "message": f"未知方法: {{method}}"}}}}


def main():
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    for line in stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            continue
        resp = _handle(msg)
        if resp is not None:
            stdout.write(json.dumps(resp, ensure_ascii=False).encode("utf-8") + b"\\n")
            stdout.flush()


if __name__ == "__main__":
    main()
'''


def skill_md_path(name: str) -> str:
    """插件内置 SKILL.md 路径（skill 型插件）"""
    return str(plugin_dir(name) / "SKILL.md")
