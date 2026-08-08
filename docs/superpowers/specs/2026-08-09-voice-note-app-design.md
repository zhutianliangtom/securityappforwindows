# 智能语音笔记 App 设计文档

> 日期：2026-08-09
> 状态：已确认

## 1. 项目概述

一款 Android 原生智能语音笔记应用。用户通过语音输入记录事项，应用本地完成语音识别、智能分类（待办/已完成）与结构化信息提取（时间、地点、人物、事件概况、主题），以卡片形式陈列在首页。核心诉求：**纯本地优先**，不开发服务器端，不依赖外部 API 模型调用；语音识别使用讯飞 SDK（当前在线听写，预留离线能力切换）。

## 2. 目标与约束

| 项目 | 说明 |
|---|---|
| 目标系统 | Android 8.0 ~ 16（API 26+） |
| 架构 | Android 原生，单 Activity + 双 Fragment（MVVM） |
| 语言 | Kotlin |
| UI | XML + Material 3 |
| 数据 | Room 本地数据库，录音存 app 私有目录 |
| 语音识别 | 讯飞语音识别 SDK（当前在线听写，后续切换离线听写） |
| 智能分类 | 本地规则引擎 + NLP 词库，不调用任何模型 API |
| 打包 | 不执行打包构建，仅配置 release 签名（生成新 keystore） |
| 美术 | UI/UX 与动画规范由 frontend-design 插件产出，原生 1:1 还原 |

## 3. 功能需求

### 3.1 语音记录
- 首页底部录音按钮，点击开始录音并实时识别，松开/再点结束。
- 录音使用 MediaRecorder 保存 m4a 到 app 私有目录。
- 识别完成后弹出**确认/编辑界面**，展示识别文字与自动提取的分类信息。
- 用户可修改文字、调整分类（待办/已完成）、修改提取的元数据、设置提醒时间，确认后保存。
- 用户确认前自动提取结果实时展示，供其校对。

### 3.2 智能分类（自动 + 手动结合）
- 语音内容自动识别为「待办」或「已完成」。
- 待办卡片提供「标记完成」按钮，点击后移入已完成分类。
- 已完成卡片可「恢复为待办」。

### 3.3 信息提取（元数据）
对识别文字提取以下字段（缺失则留空，用户可在确认界面补充）：
- **时间**：如「明天下午 3 点」
- **地点**：如「公司」「医院」
- **人物**：如「张总」
- **事件概况**：句子主干摘要，如「去开会」
- **主题**：关键词分类（工作/生活/学习/健康/会议/家庭/其他）

### 3.4 首页卡片陈列
- 顶部两个分类 Tab：「待办」「已完成」，Tab 切换展示，默认「待办」。
- 卡片展示：事件概况（标题）、正文摘要、时间/地点/人物标签、主题角标、录音回放入口。
- 未完成待办卡片显示「完成」勾选按钮。

### 3.5 详情页
- 点击卡片 → 共享元素转场**放大弹出**进入详情页；返回 → **缩小收回**回首页。
- 展示完整字段：正文、分类、时间、地点、人物、概况、主题、创建时间。
- 录音播放器（播放/暂停/进度）。
- 支持编辑保存、删除、标记完成、设置提醒。

### 3.6 本地提醒
- 识别到具体时间时自动创建本地闹钟（也可在确认界面/详情页手动设置）。
- 到点通过系统通知提醒（NotificationCompat）。
- 错过的提醒在打开 App 时补发。
- 提醒依赖：`AlarmManager` 一次性闹钟 + `BroadcastReceiver`。

### 3.7 首页/详情动画
- 卡片点击：卡片 View 作为共享元素平滑放大为详情容器。
- 返回：详情容器缩小收回为原卡片。
- 插值器带轻微弹性（decelerate/overshoot 组合）。
- 新卡片入场动画、录音按钮脉冲动效。
- 动效规范由 frontend-design 插件先行产出设计稿（配色、圆角、阴影、动效曲线），原生还原。

## 4. 模块划分

```
app/src/main/java/com/example/voicenote/
├── ui/
│   ├── home/          HomeFragment、NoteAdapter、HomeViewModel
│   ├── detail/        DetailFragment、DetailViewModel
│   └── record/        确认/编辑界面（RecordConfirmFragment）
├── data/
│   ├── Note.kt        Room 实体
│   ├── NoteDao.kt
│   ├── NoteDatabase.kt
│   └── NoteRepository.kt
├── nlp/
│   ├── IntentClassifier.kt    待办/已完成意图
│   ├── TimeExtractor.kt
│   ├── LocationExtractor.kt
│   ├── PersonExtractor.kt
│   ├── SummaryExtractor.kt    事件概况
│   └── TopicExtractor.kt      主题
├── voice/
│   ├── IRecognizer.kt         接口抽象
│   ├── OnlineRecognizer.kt    讯飞在线听写
│   └── OfflineRecognizer.kt   讯飞离线听写（预留）
├── reminder/
│   ├── AlarmScheduler.kt
│   └── ReminderReceiver.kt
└── audio/
    ├── RecordManager.kt
    └── AudioPlayer.kt
```

## 5. 数据模型

### Note（Room 实体）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | Long PK | 自增 |
| content | String | 识别/编辑后的文字 |
| audioPath | String? | 录音文件路径（app 私有目录内相对路径） |
| category | String | `TODO` / `DONE` |
| eventTime | Long? | 提取的事件时间（毫秒时间戳） |
| location | String? | 地点 |
| person | String? | 人物 |
| summary | String? | 事件概况 |
| topic | String? | 主题 |
| reminderAt | Long? | 提醒时间（毫秒时间戳） |
| createdAt | Long | 创建时间 |

## 6. NLP 规则引擎（纯本地）

### 6.1 意图分类（待办/已完成）
- 待办关键词：记得、要、需要、去、参加、安排、提醒、别忘了、必须、待办、约
- 已完成关键词：已经、完成、做完、开完、结束、去过了、搞定了、办完、完成过
- 规则：命中已完成词优先为已完成；命中待办词为待办；均未命中默认待办。
- 否定词处理：「没完成」「还没做」→ 待办。

### 6.2 时间提取
- 相对时间词库：今天、明天、后天、大后天、昨天、下周X、下月、本月、周X/星期X、上午、下午、晚上、凌晨、中午、早上。
- 具体时间正则：`(\d{1,2})[点时](半|\d{1,2}分)?`、`(\d{1,2}):(\d{2})`。
- 组合：相对词 + 时刻，如「明天下午3点」→ 计算为具体时间戳。
- 无年份/日期信息时按最近未来日期推算；解析失败则仅记录原文。

### 6.3 地点提取
- 内置地点词库：公司、医院、学校、机场、车站、家、酒店、餐厅、会议室、银行、超市、健身房、医院、派出所 等。
- 介词模式：「去/在/到/回/约在」+ 地点词。
- 地点词库作为配置文件（assets 或代码常量表），便于扩展。

### 6.4 人物提取
- 称谓词库：X总、X老师、X经理、X医生、X律师、X主任、X哥/姐 等（姓氏+称谓）。
- 关联词模式：「和/跟/约/与/找」+ 人名/称谓。
- 常见姓氏 + 称谓识别：赵钱孙李周吴郑王…+（总/老师/经理/医生）。

### 6.5 事件概况
- 提取动词短语主干：动词 + 宾语，如「去开会」「看医生」「交报表」。
- 常用动词词库：去、开、参加、看、见、交、做、办、买、修、拿、取、送 等。
- 抽取规则：定位意图相关动词，向后截取到句尾或标点。

### 6.6 主题分类
- 主题词库：会议（开会、会议、例会、汇报）、工作（报表、方案、项目、加班）、学习（上课、考试、复习、作业）、健康（医生、医院、体检、吃药）、生活（买菜、逛街、聚餐）、家庭（孩子、家人、父母）。
- 未命中 → 「其他」。

### 6.7 引擎输入输出
- 输入：识别文字（原始整句）。
- 输出：`NlpResult(intent, eventTime, location, person, summary, topic)`。
- 引擎为纯函数模块，无状态，便于单元测试。

## 7. 语音模块设计

### 7.1 IRecognizer 接口
```kotlin
interface IRecognizer {
    fun start()
    fun stop(onResult: (String) -> Unit, onError: (String) -> Unit)
    fun cancel()
    fun release()
}
```
- `OnlineRecognizer`：封装讯飞在线听写 SDK（`SpeechRecognizer`），需 `INTERNET` 权限与 AppID 配置。
- `OfflineRecognizer`：封装讯飞离线听写（预留），需离线授权文件（`msc.cfg` 等）与 `APPID`。
- 通过工厂/配置切换实现，业务层不感知具体实现。

### 7.2 讯飞 SDK 集成要点
- `app/src/main/assets` 放置 SDK 资源；`libs/` 放置 SDK so 与 jar/aar。
- `MscConfig` / `SpeechUtility.createUtility` 初始化 AppID。
- 在线听写参数：`domain=iat`、`language=zh_cn`、`accent=mandarin`、`asr_ptt=1`。
- 录音流由讯飞内部管理或自采 PCM 输入，按官方推荐方案实现。

### 7.3 讯飞凭证配置（本地开发）
用户已提供以下讯飞开放平台凭证，写入本地配置常量（不入库、不提交公共仓库，仅本地开发使用）：

| 项目 | 值 |
|---|---|
| AppID | `b0c90dc2` |
| APISecret | `OTUxYTA5MDU0NzcxNWVhOWJmMTE4OWM4` |
| APIKey | `466ce52106ddebe0e8cd6ce3f0636477` |

- MSC Android SDK 在线听写使用 **AppID** 初始化。
- APIKey / APISecret 备用（如需 WebSocket WebAPI 集成时使用）。
- 在代码中统一收敛为 `AppConfig` 常量，便于后续替换/切换离线。

## 8. 动画与 UI 规范（frontend-design 产出）

### 8.1 设计稿先行
- 由 frontend-design 插件产出 Web 设计稿：首页卡片列表、详情页、确认页、配色、字体、圆角、阴影、动效曲线。
- 设计稿作为视觉规范参考，原生 XML/代码 1:1 还原。

### 8.2 关键动画
- 卡片 → 详情：`FragmentTransaction.addSharedElement` + 共享元素转场（scale + fade，弹性插值器）。
- 返回：`onBackPressed` 触发反向转场（缩小收回）。
- 新卡片：列表新增项入场动画（fade + translate）。
- 录音按钮：录音时呼吸/脉冲动画。

## 9. 权限清单

| 权限 | 级别 | 用途 |
|---|---|---|
| RECORD_AUDIO | 运行时 | 录音 |
| POST_NOTIFICATIONS | 运行时(13+) | 提醒通知 |
| SCHEDULE_EXACT_ALARM | 特殊(12+) | 精确闹钟 |
| INTERNET | 普通 | 讯飞在线听写（切换离线后可移除） |

## 10. 错误处理

- 识别失败：Toast/提示重试，保留录音可重新识别。
- 录音失败（无权限/被占用）：提示并禁用录音按钮。
- 数据库异常：统一捕获，日志记录，避免崩溃。
- 提醒未授权（12+ 精确闹钟被拒）：降级为不精确提醒或提示。
- 错过的提醒：应用启动时扫描 `reminderAt < now` 且未提醒的笔记，补发通知。

## 11. 测试策略

- **单元测试**：NLP 规则引擎 —— 覆盖各类句式：时间/地点/人物/意图/主题的提取与分类（JUnit）。
- **数据库测试**：Room DAO 增删改查（可选，Robolectric）。
- **手动验证**：真机录音、识别、提醒、动画。

## 12. 交付范围

- 完整 Android 工程源码（Kotlin + XML + Room + 讯飞 SDK 集成框架）。
- release keystore 生成 + `build.gradle` 签名配置。
- **不执行打包/构建 APK**。
- 修复开发过程中发现的代码 bug。

## 13. 开发顺序

1. 工程脚手架 + 依赖 + 权限 + 主题/基础 UI
2. 数据层（Room Note 实体/DAO/Repository）
3. NLP 规则引擎 + 单元测试
4. 语音模块（IRecognizer 接口 + 讯飞在线识别 + 录音/播放）
5. UI：首页卡片列表（Tab 分类、卡片、动画）
6. UI：详情页 + 共享元素转场动画
7. 确认/编辑界面
8. 提醒模块（闹钟 + 通知 + 补发）
9. frontend-design 设计规范产出并还原调优
10. release 签名配置 + 自审 + 提交 git
