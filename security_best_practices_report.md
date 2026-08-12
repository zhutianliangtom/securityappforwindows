# WinAppMigrator 安全模块系统性审查报告

> 审查对象：`src/winapp_migrator/core/security.py`（进程/启动项/网络扫描与自动清理）、`core/execution_guard.py`（新进程执行防护）、`core/network_defense.py`（ARP 欺骗/SYN 洪泛/TCP 洪泛防御）及 `ui/main_window.py` 中的 `SecurityMonitorWorker` 集成。
> 审查时间：2026-08-11

## 执行摘要

安全模块整体采用"纯 Win32 API + 特征库"路线，无第三方安全组件依赖，架构清晰、可维护性好。但存在**一个高危级误杀风险**（命令行子串匹配 + 自动终止），以及**多处中危的可靠性/误删风险**（PID 复用竞态、启动项按名称跨键删除、32 位进程 PEB 偏移错误、无隔离/无确认的自动清理）。这些问题的共性根因是：**"检测"到"处置"之间缺少二次校验与人工/隔离环节**，一旦特征命中误判，会直接造成用户进程被终止、注册表启动项被永久删除。

---

## 严重（Critical）

### C1. 命令行子串匹配会误杀无辜进程（自动终止）

- 位置：[execution_guard.py](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/execution_guard.py#L33-L37) `_DESTRUCT_CMDS`、[execution_guard.py#L146](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/execution_guard.py#L146)
- 影响：`any(m in low for m in _DESTRUCT_CMDS)` 对整个命令行做**子串匹配**。例如 `"format "`（带尾空格）会命中任何命令行中包含 `format ` 的进程——包括 `notepad "C:\format folder\readme.txt"`、`7z.exe a "D:\format.tar"` 这类完全正常的操作；`"clean"` 变体、`"systemreset"`、`"dism /remove"`、`"bcdedit /set"` 同样会拦截管理员/用户的合法维护命令。命中即 `level=block` → `_terminate_process` 直接杀进程。
- 影响一句话：一条合法命令行只要"提到"格机关键词即被自动终止，可导致用户工作丢失。

### C2. 自动清理无确认、无隔离、无撤销，误判即永久损失

- 位置：[main_window.py#L240-L265](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/ui/main_window.py#L240-L265) 中 `sweep()` 每 10 秒自动执行；[security.py#L483-L493](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/security.py#L483-L493) 直接 `_terminate_process` 与 `_remove_startup`。
- 影响：进程被 `TerminateProcess` 强杀、注册表 Run 值被 `DeleteValue` 永久删除，均无二次确认、无备份、无恢复路径。叠加 C1/C3/M1/M5 的误判因素，一次误报=用户一个启动项永久丢失（注册表删除不可撤销）。
- 建议方向：删除启动项前先将原值备份（如写入 `Run` 下 `WinAppMigrator_Backup` 或本地 `.quarantine` 文件），进程处置改为"隔离"（如重命名/挂起）并记录可恢复日志。

---

## 高危（High）

### H1. PID 复用竞态（TOCTOU）：扫描与终止之间 PID 可能被其他进程复用

- 位置：[security.py#L483-L487](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/security.py#L483-L487)、[execution_guard.py#L132](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/execution_guard.py#L132)
- 影响：`scan_processes()` 拿到 PID 后，恶意进程可能在 `_terminate_process(pid)` 前退出，PID 被系统回收并分配给**另一个无关进程**，随后该无辜进程被 `TerminateProcess` 强杀。真实安全软件在终止前会重新校验进程映像路径与创建时间。
- 建议：终止前重新调用 `_process_path(pid)` 比对，不一致则放弃；或直接以进程句柄（打开时校验路径）传递。

### H2. 启动项删除按"名称"全局匹配，可能删除合法启动项

- 位置：[security.py#L438-L458](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/security.py#L438-L458) `_remove_startup`
- 影响：扫描时已记录命中项位于哪个 `hive/key_path`（`entry["where"]`），但删除时却**忽略该信息**，遍历全部 4 个启动键、删除**第一个**同名字的值，且**不校验当前值内容是否仍为恶意**。若 HKCU 与 HKLM 的 Run 下存在同名值（一恶一善），会删错。同理启动文件夹只按 `.lnk` 文件名删除。
- 建议：按 `entry["where"]` 精确定位 hive/key 后，先读回值内容再次匹配特征库，命中才删；删除前备份原值。

### H3. 32 位进程 PEB 偏移硬编码 x64 偏移，32 位恶意进程漏检

- 位置：[execution_guard.py#L96-L107](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/execution_guard.py#L96-L107)（CommandLine `0x70`）、[security.py#L243-L254](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/security.py#L243-L254)（ImagePathName `0x60`）
- 影响：`PEB+0x20`（ProcessParameters）、`PP+0x60/0x70` 均为 **x64 布局**偏移。对 32 位（WOW64）进程读取的是错误偏移处的垃圾数据：路径/命令行解码错乱 → `_DESTRUCT_CMDS`、`_LIVELESS_MARKERS`、`_process_path` 全部失效 → **32 位恶意进程（大量木马为 32 位）直接漏检**；更糟的是乱码经 utf-16 解码后可能意外"命中"关键词而误杀（叠加 C1）。
- 建议：用 `NtWow64ReadVirtualMemory64` 读取 64 位 PEB，或按进程位数（PEB->ProcessParameters 在 32 位为 0x10，ImagePathName 0x38 / CommandLine 0x40）选择偏移。

### H4. 特征库存在明显误收与误删面

- 位置：[security.py#L44-L71](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/security.py#L44-L71)
- 影响：
  1. `"srvany"` 是微软 Windows Resource Kit 的**合法服务工具**（真实蠕虫测试还专门伪装成 srvany），列入黑名单会误杀合法服务；`"winrar_setup"`、`"tcpviewer"` 等命名也不严谨。
  2. `_MALICIOUS_STARTUP_MARKERS` 含 `\temp\`、`\tmp\`、`\appdata\local\temp` 路径特征——**大量合法软件的更新器/自升级组件确实从 %TEMP% 运行**，会误删合法启动项。
  3. `"t-rex"`/`"trex"` 同时是合法挖矿基准测试工具名。
- 影响一句话：特征库命中即自动终止/删除，误收条目直接放大 C1/C2 的破坏面。
- 建议：删除非结论性条目；启动项恶意判定要求"恶意文件名 + 非签名"或"命令行含下载执行"等更强条件。

---

## 中危（Medium）

### M1. 名称命中跳过系统目录过滤

- 位置：[security.py#L381](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/security.py#L381) + [#L396-L403](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/security.py#L396-L403)
- 影响：名称命中的条目 `path` 为空，`_not_system(e["path"] or e["name"])` 退化为用**进程名**做路径判断 → `Path("xmrig").parts=("xmrig",)` 恒不在系统目录 → 系统目录内同名进程也会被杀。`_not_system` 对空路径返回 `True` 使过滤形同虚设。
- 建议：名称命中后补查真实路径（`_real_process_path`），路径为空或位于 `C:\Windows` 时不处置。

### M2. ARP 基线的"首样本即真实"假设可被利用

- 位置：[network_defense.py#L290-L303](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/network_defense.py#L290-L303)
- 影响：基线取防护开启时的**第一个** ARP 样本。若开启时攻击已在发生，基线=攻击者 MAC，"修复"反而巩固攻击；且网关 MAC 任何变化（路由器重启/双机热备/多 AP 同网关）都会被判定为 ARP 欺骗，随后主动发送伪造源 MAC 的 ARP 应答包（可能触发网络侧 IDS 告警）。
- 建议：基线取连续 2-3 个稳定样本；对网关 MAC 做 OUI/厂商合理性校验；修复动作降级为"告警 + 建议"，避免主动发包。

### M3. SYN 洪泛封禁规则无限累积且对伪造源 IP 无效

- 位置：[network_defense.py#L189-L204](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/network_defense.py#L189-L204)、[#L323-L328](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/network_defense.py#L323-L328)
- 影响：`block_ip` 以 `WinAppMigrator_Block_{ip}` 永久新增防火墙规则且**从不清理**——SYN 源 IP 多为伪造，封禁无效但规则越积越多，污染用户防火墙（数百条无效入站阻止规则）。
- 建议：规则名打上时间戳/数量上限（如保留最近 50 条），超限自动删除最旧的；或对 SYN 源做多轮确认（连续 N 轮超阈值）再封禁。

### M4. `wpcap.dll` 按名称加载存在 DLL 劫持面

- 位置：[network_defense.py#L210](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/network_defense.py#L210)
- 影响：`ctypes.WinDLL("wpcap.dll")` 按 DLL 搜索顺序（应用目录→PATH）加载，攻击者若能在应用目录投放同名 DLL 可劫持。
- 建议：改用 `LoadLibraryExW` + `LOAD_LIBRARY_SEARCH_SYSTEM32`，或仅当 `C:\Windows\System32\Npcap\wpcap.dll` 存在时加载。

### M5. 检测能力局限：无文件哈希/PE 属性校验，改名即绕过

- 影响：纯文件名/路径名匹配，`xmrig.exe` 改名 `xmr2.exe` 即完全绕过；进程镂空/注入（恶意代码跑在 `svchost.exe` 里）无法检测；无数字签名校验，无法区分"真木马"与"名字撞车的正常程序"。这是签名式检测的固有边界，但叠加自动处置后风险放大。
- 建议：至少对命中进程补充校验（PE 签名缺失/无效 + 文件熵 + 非白名单厂商）再处置；否则维持只提示不处置。

---

## 低危（Low）

- **L1** 无审计日志：[security.py](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/security.py#L472-L500) 的 `sweep` 处置动作（杀进程/删启动项/封禁 IP）未写入 `logger`，安全事件无追溯。
- **L2** 防火墙状态读取受组策略影响：[security.py#L334-L345](file:///c:/Users/zhuzhu/Desktop/my%20first%20android%20app/src/winapp_migrator/core/security.py#L334-L345) 直接读 `EnableFirewall` 注册表值，GPO 托管时显示可能不准。
- **L3** 无自我进程保护：本防护未保护自身 PID（理论上可被其他管理员进程终止），属用户态工具固有边界，建议在代码注释中明示。
- **L4** `sweep` 每次全量枚举 + 8 线程读 PEB，大进程数时每 10 秒一次，资源开销需实测确认。

---

## 修复优先级建议

1. **立即**：C1——将破坏性命令判定从"子串命中"改为"程序名 + 参数严格匹配"（如 `format.com`/`diskpart.exe` 且参数含 `clean/format`），并把 block 降级为先提示。
2. **立即**：C2——清理动作增加"隔离/备份"与可恢复机制，启动项删除前备份原值。
3. **高**：H1/H2——终止前重校验 PID 对应路径；删除按 `entry["where"]` 定位并二次校验值内容。
4. **高**：H3——支持 32 位进程 PEB 布局或使用 WOW64 读取 API。
5. **中**：H4/M1/M2/M3/M4——收敛特征库、路径过滤、ARP 基线校验、防火墙规则上限、wpcap 安全加载。
