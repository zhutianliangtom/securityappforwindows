# SparkChain 声音复刻（VC） Android SDK 集成文档

## 1. 声音复刻（VC）简介

声音复刻（Voice Clone，SDK 类名 `VC`）能力用于基于训练流程完成音色定制，并在训练成功后使用复刻音色进行语音合成（TTS）。典型流程包括：获取访问令牌、获取训练文本与分段信息、创建训练任务、上传/关联训练音频、提交任务、查询任务进度直至获得音库资源 ID，最后通过 `vcTTS` 拉取合成音频数据。

本能力与云端服务协同工作，请在开放平台为应用开通对应能力并完成授权配置。

## 2. 兼容性说明

| 类别     | 兼容范围                                        |
| -------- | ----------------------------------------------- |
| 系统     | 支持 armv7 和 armv8 架构，兼容 Android 5.0 及以上版本 |
| 开发环境 | 建议使用 Android Studio 进行开发                 |

## 3. SDK 集成包目录结构

将SDK zip包解压缩，得到如下文件：

├── Demo SparkChain的使用DEMO，DEMO中已经集成了SDK，您可以参考DEMO，集成SDK。集成前，请先测通DEMO，了解调用原理。

├── ReleaseNotes.txt SDK版本日志

├── SDK SparkChain SDK

│ └── SparkChain.aar

└── SparkChain 语音听写 Android SDK集成文档.pdf     SparkChain集成指南

## 4. SDK 工程配置

### 4.1 导入 SDK 库

将发行包中的 AAR 复制到工程的 `libs` 目录，在主 Module 的 `build.gradle` 中增加依赖，例如：

```java
implementation files('libs/SparkChain.aar')
```

（具体 AAR 文件名以您收到的 SDK 包为准，可能同时依赖 `Codec.aar` 等，请参考 DEMO 工程 `gradle` 配置。）

### 4.2 配置权限

外部使用时需要配置以下权限：

| **权限**                | **使用说明**                                                 |
| ----------------------- | ------------------------------------------------------------ |
| INTERNET                | 必须权限，SDK 需要访问网络。                                 |
| READ_EXTERNAL_STORAGE   | 必须权限，读取日志路径、本地训练/试听音频等场景需存储访问。   |
| WRITE_EXTERNAL_STORAGE  | 必须权限，写本地日志或保存合成 PCM 等。                     |
| MANAGE_EXTERNAL_STORAGE | 可选权限，Android 10 及以上动态授权场景可能需要。             |

如果部分权限不需要，可通过如下配置去除，去除示例如下：

```Java
Android 10.0（API 29）及以上版本需要在application中做如下配置
<application android:requestLegacyExternalStorage="true"/>
```

### 4.3 混淆配置

SparkChain SDK 已做过混淆。若工程开启混淆，请在 `proguard-rules.pro` 中增加：

```java
-keep class com.iflytek.sparkchain.** {*;} 
-keep class com.iflytek.sparkchain.**
```

## 5. 业务调用流程说明

![](D:\iflytek\aikit\demo\Sparkchain\Andorid\SparkChain_Android_SDK_2.0.1_rc3_260309\集成文档\pic\Android一句话复刻流程图.png)

## 6. SDK 初始化

**在使用SDK功能前，需要先开通语音听写授权并获取已开通授权的应用信息（appId、apiKey、apiSecret）。SDK全局只需要初始化一次。**初始化时，开发者需要构建一个SparkChainConfig实例config，把相关的appid信息以及日志设置等传入config中，然后再通过SparkChain.getInst().init方法把config实例设置到SDK中。具体初始化示例如下：

```Java
//配置应用信息 
SparkChainConfig config =  SparkChainConfig.builder()    
    .appID("$appId")       
    .apiKey("$apiKey")    
    .apiSecret("$apiSecret")
    .workDir("$workdir")
int ret = SparkChain.getInst().init(getApplicationContext(), config); 
```

初始化参数说明：

| **接口名称** | **含义**                                                     | **参数类型** | **限制**                                                     | **是否必填** |
| ------------ | ------------------------------------------------------------ | ------------ | ------------------------------------------------------------ | ------------ |
| appID        | 创建应用后，生成的应用ID                                     | String       | 与平台生成的appID完全一致                                    | 是           |
| apiKey       | 创建应用后，生成的唯一应用标识                               | String       | 与平台生成的apiKey完全一致                                   | 是           |
| apiSecret    | 创建应用后，生成的唯一应用秘钥                               | String       | 与平台生成的apiSecret完全一致                                | 是           |
| workDir      | 工作目录                                                     | String       | SDK工作目录，用户可自行指定，但要确保有访问权限              | 是           |
| logLevel     | 日志等级                                                     | int          | 枚举，0：VERBOSE，1：DEBUG，2：INFO，3：WARN，4：ERROR，5：FATAL，100：OFF | 否           |
| logPath      | 日志存储路径(具体指定到文件名，如"/sdcard/iflytek/sparkchain.log")，设置则会把日志存在该路径下，不设置则会把日志打印在终端上。 | String       | 设置的路径需要有读写权限                                     | 否           |
| uid          | 用户自定义标识                                               | String       |                                                              | 否           |

初始化返回值：0：初始化成功，非0：初始化失败，请根据具体返回值参考错误码章节查询原因。

## 7. VC 能力初始化

构造 `VC` 实例并注册回调：

```java
VC mVc = new VC();
mVc.registerCallbacks(mVCCallbacks);
```

## 8. 功能参数配置

SDK支持用户根据自身需求，通过构建的VC实例访问相关方法配置识别参数。具体方法说明如下：

| 方法 | 说明 |
| ---- | ---- |
| void setParams(int mode,String key, String value) | 设置字符串类参数。mode有两个选项，<br />0：声音复刻参数<br />1：tts参数 |
| void setParams(int mode,String key, int value) | 整型参数。mode同上。 |
| void setParams(int mode, String key, boolean value) | 布尔参数。mode同上。 |
| void mosRatio(float ratio)                          | 范围0.0～5.0，单位0.1，默认0.0 大于0，则开启音频检测。该值为对应的检测阈值,音频得分高于该值时将会生成音频特征 |

VC个性化参数如下：

| 参数名称      | 类型   | 是否必传 | 参数说明                                                     |
| ------------- | ------ | -------- | ------------------------------------------------------------ |
| engineVersion | string | 否       | 版本类型，多风格版需传**omni_v1**                            |
| taskName      | string | 否       | 创建任务名称, 默认””                                         |
| sex           | int    | 否       | 性别, 1:男2:女, 默认1                                        |
| ageGroup      | int    | 否       | 1:儿童、2:青年、3:中年、4:中老年, 默认1                      |
| resourceType  | int    | 否       | 12:一句话合成                                                |
| thirdUser     | string | 否       | 用户标识, 默认””                                             |
| denoise       | int    | 否       | 降噪开关, 默认0 0: 关闭降噪 1:开启降噪                       |
| mosRatio      | float  | 否       | 范围0.0～5.0，单位0.1，默认0.0 大于0，则开启音频检测。该值为对应的检测阈值,音频得分高于该值时将会生成音频特征 |
| resourceName  | string | 否       | 音库名称, 默认””                                             |
| callbackUrl   | string | 否       | 任务结果回调地址，训练结束时进行回调                         |

tts参数如下：

| 参数名称     | 功能描述                                                     | 数据类型 | 参数说明                                                     | 必填 | 默认值            |
| ------------ | ------------------------------------------------------------ | -------- | ------------------------------------------------------------ | ---- | ----------------- |
| languageID   | 合成的语种及方言                                             | int      | 中文普通话：0 英语：1 日语：2 韩语：3 俄语：4 法语：5 阿拉伯语：6 西班牙语：7 粤语：8 | 是   | 不传默认为0：中文 |
| volume       | 音量：0是静音，1对应默认音量1/2，100对应默认音量的2倍        | int      | 最小值:0, 最大值:100                                         | 否   | 50                |
| pybuffer     | 输出音素时长信息                                             | int      | 1:打开                                                       | 否   | 1                 |
| speed        | 语速：0对应默认语速的1/2，100对应默认语速的2倍               | int      | 最小值:0, 最大值:100                                         | 否   | 50                |
| pitch        | 语调：0对应默认语调的1/2，100对应默认语调的2倍               | int      | 最小值:0, 最大值:100                                         | 否   | 50                |
| reg          | 英文发音方式                                                 | int      | 0:自动判断处理，如果不确定将按照英文词语拼写处理（缺省）, 1:所有英文按字母发音, 2:自动判断处理，如果不确定将按照字母朗读 | 否   | 0                 |
| rdn          | 合成音频数字发音方式                                         | int      | 0:自动判断, 1:完全数值, 2:完全字符串, 3:字符串优先           | 否   | 0                 |
| style        | 方言及风格，仅在多风格版-中文语言下支持（languageID传0 或者不传languageLD），其他版本不生效 | string   | 见下方列表                                                   | 否   |                   |
| impactFactor | 原声影响因子，0 表示偏向自然流畅度，而 10 表示更偏向原声，值越大，越偏向原声，值越小，越偏向美化的效果 当 style 设置为情感（neutral、happy、excited、glad、comfort、encouraging、apologetic、sad、downhearted、curious、confused、regretful、surprised、cute、lovey-dovey、naughty、fearful、afraid、scornful、angry、disgusted、lyrical、wronged、gentle、weak、serious）原声影响因子自动设置为 3 当 style 设置为交互以及为空时，会自动设置为 10 其他会自动设置为 0 | int      | 取值为 0~10 之间的整数，建议使用默认值-1，会根据 style 的值自动设置。 | 否   | -1                |

style部分：

| 取值         | 含义     |
| ------------ | -------- |
| tianjin      | 天津话   |
| dongbei      | 东北话   |
| sichuan      | 四川话   |
| hefei        | 合肥话   |
| chat         | 交互聊天 |
| news         | 新闻播报 |
| explanation  | 通俗解说 |
| picture_book | 绘本朗读 |
| teach        | 教育辅学 |
| langsong     | 朗诵     |
| novel        | 小说旁白 |
| sunwukong    | 孙悟空   |
| lindaiyu     | 林黛玉   |
| labixiaoxin  | 蜡笔小新 |
| xionger      | 熊二     |
| peiqi        | 小猪佩奇 |
| zhugeliang   | 诸葛亮   |
| neutral      | 平和     |
| happy        | 高兴     |
| excited      | 激动     |
| glad         | 开心     |
| comfort      | 安慰     |
| encouraging  | 鼓励     |
| apologetic   | 抱歉     |
| sad          | 悲伤     |
| downhearted  | 低落     |
| curious      | 好奇     |
| confused     | 困惑     |
| regretful    | 后悔     |
| surprised    | 惊讶     |
| cute         | 可爱     |
| lovey-dovey  | 撒娇     |
| naughty      | 调皮     |
| afraid       | 害怕     |
| scornful     | 轻蔑     |
| angry        | 生气     |
| fearful      | 恐惧     |
| disgusted    | 厌恶     |
| lyrical      | 抒情     |
| wronged      | 委屈     |
| gentle       | 温柔     |
| weak         | 虚弱     |
| serious      | 严肃     |

tts的text部分：

| 字段     | 含义         | 数据类型 | 取值范围          | 必填 |
| -------- | ------------ | -------- | ----------------- | ---- |
| encoding | 文本编码     | string   | utf8, gb2312, gbk | 是   |
| compress | 文本压缩格式 | string   | raw, gzip         | 是   |
| format   | 文本格式     | string   | plain, json, xml  | 是   |

## 9. 注册结果监听回调

声音复刻运行结果通过 `VCCallbacks` 异步返回，接口定义如下：

```java
public interface VCCallbacks {
    void onResult(VC.VCResult result, Object usrTag);
    void onError(VC.VCError error, Object usrTag);
    void onProcess(double dltotal, double dlnow, double ultotal, double ulnow, Object usrTag);
}
```

**VCCallbacks 数据结构说明：**

- **onResult** 为声音复刻结果回调方法，参数说明如下：

  | 参数   | 类型          | 说明                                                         |
  | ------ | ------------- | ------------------------------------------------------------ |
  | result | VC.VCResult   | 声音复刻结果实例，需结合 `getKey()` 判断当前为哪类业务回调。 |
  | usrTag | Object        | 用户自定义标识，与发起 `getToken`、`getTraninText`、`taskAdd` 等接口时传入的 `usrTag` 一致。 |

- **VC.VCResult** 结构说明：

  | 方法           | 返回值类型   | 说明                                                         |
  | -------------- | ------------ | ------------------------------------------------------------ |
  | getKey()       | String       | 业务类型标识。常见取值：`token`（令牌）、`traintext`（训练文本）、`taskadd`（创建任务）、`audioadd`（URL 添音频）、`tasksubmit`（提交任务）、`submitwithaudio`（本地音频提交）、`taskresult`（任务进度/结果）、`tts`（复刻合成音频）等； |
  | getRawResult() | String       | 服务端返回的原始结果字符串（JSON 等），便于排查或与协议对齐。 |
  | getToken()     | String       | Access Token，每次获取到的token有效期为7200秒                |
  | getTaskId()    | String       | 训练任务 ID；在 `key` 为 `taskadd` 等任务相关回调时有效。    |
  | getTextSegs()  | VC.TextSeg[] | 训练文本分段列表；在 `key` 为 `traintext` 时有效，用于取得 `segId` 等与音频对齐。 |
  | getStatus()    | int          | 结果进度或状态。与听写类似可理解为阶段信息：**0** 开始、**1** 中间、**2** 结束（如 TTS 最后一包、任务结果终态等） |
  | getAssetId()   | String       | 音库/资源 ID（训练成功后用于 `vcTTS`）；在 `key` 为 `taskresult` 且训练成功等场景有效。 |
  | getAudio()     | byte[]       | 合成音频二进制数据；在 `key` 为 `tts` 时分片返回，需在应用侧拼接保存。 |
  | getLen()       | int          | 与音频等数据相关的长度字段（依协议填充，具体以 SDK 版本为准）。 |

- **TextSeg** 结构体说明（训练文本分段，嵌套于 `getTextSegs()`）：

  | 方法            | 返回值类型 | 说明                                                         |
  | --------------- | ---------- | ------------------------------------------------------------ |
  | getSegId()      | int        | 文本分段 ID，提交训练音频（URL 或本地）时需与服务端约定字段对齐。 |
  | getSegText()    | String     | 该段训练文本内容。                                           |
  | getSegTextLan() | String     | 该段文本语种等标识。                                         |
  | getSegSize()    | int        | 分段相关尺寸或长度信息（依协议）。                           |

- **onError** 为声音复刻错误回调方法，参数说明如下：

  | 参数   | 类型         | 说明                                                         |
  | ------ | ------------ | ------------------------------------------------------------ |
  | error  | VC.VCError   | 错误信息实例。                                               |
  | usrTag | Object       | 用户自定义标识，与发起请求时的 `usrTag` 一致。               |

- **VC.VCError** 结构说明：

  | 方法         | 返回值类型 | 说明                                        |
  | ------------ | ---------- | ------------------------------------------- |
  | getCode()    | int        | 错误码                                      |
  | getKey()     | String     | 出错时关联的业务 key（若服务端/引擎返回）。 |
  | getMessage() | String     | 错误描述信息。                              |
  | getSid()     | String     | 本次交互的 sid（若存在）。                  |

- **onProcess** 为进度回调方法，参数说明如下：

  | 参数     | 类型   | 说明                                                         |
  | -------- | ------ | ------------------------------------------------------------ |
  | dltotal  | double | 下载总量相关度量（依 SDK 实现，可能为总字节数等）。           |
  | dlnow    | double | 当前已下载量。                                               |
  | ultotal  | double | 上传总量相关度量。                                           |
  | ulnow    | double | 当前已上传量。                                               |
  | usrTag   | Object | 用户自定义标识。                                             |

具体示例如下：

```java
VCCallbacks mVCCallbacks = new VCCallbacks() {
    @Override
    public void onResult(VC.VCResult result, Object usrTag) {
        String key = result.getKey();
        int status = result.getStatus();
        if ("token".equals(key)) {
            String token = result.getToken();
        } else if ("traintext".equals(key)) {
            VC.TextSeg[] segs = result.getTextSegs();
            for (VC.TextSeg seg : segs) {
                int segId = seg.getSegId();
                String text = seg.getSegText();
            }
        } else if ("taskresult".equals(key) && status == 2) {
            String assetId = result.getAssetId();
        } else if ("tts".equals(key)) {
            byte[] pcm = result.getAudio();
            if (status == 2) { /* 合成结束 */ }
        }
    }

    @Override
    public void onError(VC.VCError error, Object usrTag) {
        int code = error.getCode();
        String msg = error.getMessage();
    }

    @Override
    public void onProcess(double dltotal, double dlnow, double ultotal, double ulnow, Object usrTag) {
        // 上传下载进度
    }
};
mVc.registerCallbacks(mVCCallbacks);
```

## 10. 请求调用说明

各接口返回值为 **`int`**：**`0`** 一般表示 SDK 已接受本次调用并进入异步流程；**非 0** 多为参数或状态类同步失败，可结合日志与错误码排查。**最终成功、失败及业务数据以 `VCCallbacks.onResult` / `onError` 为准。**

调用前须已完成 **`SparkChain` 初始化**，并已 **`registerCallbacks`**。部分步骤依赖上一步回调中保存的 `token`、`taskId`、`textSegId`、`assetId` 等，需按第 5 节流程顺序执行。

### 10.1 获取 Token

```java
int getToken(Object usrTag);
```

| **形参名** | **类型** | **必传** | **说明**                                                     |
| ---------- | -------- | -------- | ------------------------------------------------------------ |
| usrTag     | Object   | 建议传入 | 用户自定义标识，在 `onResult` / `onError` / `onProcess` 中原样回调，便于区分请求；判等请用 `equals`。 |

**回调：** 成功时 `onResult` 中 `getKey()` 为 `"token"`，通过 `getToken()` 取访问令牌。

### 10.2 获取训练文本

```java
int getTraninText(String token, long textId, Object usrTag);
```

| **形参名** | **类型** | **必传** | **说明**                             |
| ---------- | -------- | -------- | ------------------------------------ |
| token      | String   | 是       | 由 `getToken` 成功后得到的访问令牌。 |
| textId     | long     | 是       | 可使用通用训练文本(textId=5001)      |
| usrTag     | Object   | 建议传入 | 自定义回传标记。                     |

**回调：** `getKey()` 为 `"traintext"` 时，通过 `getTextSegs()` 取训练文本分段，记录 `TextSeg.getSegId()` 等供后续上传音频使用。

### 10.3 创建训练任务

```java
int taskAdd(String token, Object usrTag);
```

| **形参名** | **类型** | **必传** | **说明**                                                     |
| ---------- | -------- | -------- | ------------------------------------------------------------ |
| token      | String   | 是       | 有效访问令牌。                                               |
| usrTag     | Object   | 建议传入 | 自定义回传标记。                                             |

**说明：** 创建任务前可按第 8 节通过 `setParams(0, ...)` 配置 `engineVersion`（如 `omni_v1`）、任务名等。**回调：** `getKey()` 为 `"taskadd"` 时，`getTaskId()` 为新建任务 ID。

### 10.4 添加远程音频 URL

```java
int addAudioUrl(String token, String url, String taskId, int textSegId, long textId, Object usrTag);
```

| **形参名** | **类型** | **必传** | **说明**                                                     |
| ---------- | -------- | -------- | ------------------------------------------------------------ |
| token      | String   | 是       | 有效访问令牌。                                               |
| url        | String   | 是       | 训练音频的网络地址（需服务端可访问）。                       |
| taskId     | String   | 是       | `taskAdd` 成功后的任务 ID。                                  |
| textSegId  | int      | 是       | 与训练文本分段对应，来自 `getTraninText` 结果中某段的 `getSegId()`。 |
| textId     | long     | 是       | 文本ID, 可使用通用训练文本(textId=5001)                      |
| usrTag     | Object   | 建议传入 | 自定义回传标记。                                             |

**回调：** `getKey()` 为 `"audioadd"` 表示 URL 音频添加流程结束（具体成功以服务端与联调为准）。

### 10.5 使用本地文件提交训练音频

```java
int submitWithAudio(String token, String audioPath, String taskId, int textSegId, long textId, Object usrTag);
```

| **形参名** | **类型** | **必传** | **说明**                                |
| ---------- | -------- | -------- | --------------------------------------- |
| token      | String   | 是       | 有效访问令牌。                          |
| audioPath  | String   | 是       | 本地音频文件路径                        |
| taskId     | String   | 是       | `taskAdd` 返回的任务 ID。               |
| textSegId  | int      | 是       | 与 `getTextSegs()` 中分段 ID 对齐。     |
| textId     | long     | 是       | 文本ID, 可使用通用训练文本(textId=5001) |
| usrTag     | Object   | 建议传入 | 自定义回传标记。                        |

**回调：** `getKey()` 为 `"submitwithaudio"` 表示本地文件提交流程结束。

### 10.6 提交任务

```java
int submitTask(String token, String taskId, Object usrTag);
```

| **形参名** | **类型** | **必传** | **说明**                                                     |
| ---------- | -------- | -------- | ------------------------------------------------------------ |
| token      | String   | 是       | 有效访问令牌。                                               |
| taskId     | String   | 是       | 当前训练任务 ID。                                            |
| usrTag     | Object   | 建议传入 | 自定义回传标记。                                             |

**回调：** `getKey()` 为 `"tasksubmit"` 表示提交任务请求已走完 SDK 侧流程。

### 10.7 查询任务进度 / 结果

```java
int getProcess(String token, String taskId, Object usrTag);
```

| **形参名** | **类型** | **必传** | **说明**                                                     |
| ---------- | -------- | -------- | ------------------------------------------------------------ |
| token      | String   | 是       | 有效访问令牌。                                               |
| taskId     | String   | 是       | 待查询的任务 ID。                                            |
| usrTag     | Object   | 建议传入 | 自定义回传标记。                                             |

**回调：** `getKey()` 为 `"taskresult"` 时结合 `getStatus()` 判断进度；训练成功且结束时可通过 `getAssetId()` 取得音库/资源 ID，供 `vcTTS` 使用。

### 10.8 复刻音色合成（TTS）

```java
int vcTTS(String assetId, String text, String audioEncoding, int status, int seq, Object usrTag);
```

| **形参名**    | **类型** | **必传** | **说明**                                                     |
| ------------- | -------- | -------- | ------------------------------------------------------------ |
| assetId       | String   | 是       | 训练完成后的音库/资源 ID（即 `taskresult` 成功时 `getAssetId()`） |
| text          | String   | 是       | 待合成文本内容。                                             |
| audioEncoding | String   | 是       | 输出音频编码相关标识。支持raw,lame, speex, opus, opus-wb, speex-wb |
| status        | int      | 是       | 请求状态，可选值为：2 一次性传输                             |
| seq           | int      | 是       | 数据序号。最小值:0, 最大值:9999999                           |
| usrTag        | Object   | 建议传入 | 自定义回传标记。                                             |

**说明：** 合成所用**文本侧**参数（如 `encoding`、`compress`、`format`）需在调用前通过 **`setParams(1, key, value)`** 配置。

**回调：** `getKey()` 为 `"tts"` 时，`getAudio()` 分片返回 PCM 数据；`getStatus()` 为 **`2`** 表示合成结束。合成音频的采样率为24000。

## 11. 逆初始化

当SDK需要完整退出时，需调用逆初始化方法释放资源，示例代码如下：

```java
SparkChain.getInst().unInit();  //SDK逆初始化
```

## 12. SDK API 介绍

### 12.1 SparkChainConfig API

| **返回值类型**   | **方法说明**                                                 |
| ---------------- | ------------------------------------------------------------ |
| SparkChainConfig | public SparkChainConfig appID(String appID)   <br />设置用户的appID |
| SparkChainConfig | public SparkChainConfig apiKey(String apiKey)   <br />设置用户的apiKey |
| SparkChainConfig | public SparkChainConfig apiSecret(String apiSecret)   <br />设置用户的apiSecret |
| SparkChainConfig | public uid(String uid)   <br />设置用户自定义标识            |
| SparkChainConfig | public SparkChainConfig workDir(String workDir)   <br />设置SDK工作路径 |
| SparkChainConfig | public SparkChainConfig logLevel(int logLevel)   <br />设置日志等级 |
| SparkChainConfig | public SparkChainConfig logPath(String logPath)   <br />设置日志保存路径 |
| SparkChainConfig | public static SparkChainConfig builder()   <br />构建SparkChain实例 |

### 12.2 SparkChain API

| **返回值类型** | **方法说明**                                                 |
| -------------- | ------------------------------------------------------------ |
| SparkChain     | public static SparkChain getInst()  <br />获取SparkChain实例 |
| int            | public int init(Context context, SparkChainConfig config)  <br />SDK初始化 |
| int            | public int init(Context context)  <br />SDK初始化            |
| int            | public int unInit()  <br />SDK逆初始化                       |
| int            | public int getInitCode()  <br />获取SDK初始化结果码          |

## 12.3 VC API

| **返回值类型** | **方法说明** |
| -------------- | ------------ |
| void           | registerCallbacks(VCCallbacks cbs) <br />注册回调 |
| void           | setParams(int stage, String key, String/int/boolean value) <br />扩展参数 |
| void           | mosRatio(float ratio)<br />设置检测阈值 |
| int            | getToken(Object usrTag)<br />获取Access Token |
| int            | getTraninText(String token, long textId, Object usrTag)<br />获取训练文本 |
| int            | taskAdd(String token, Object usrTag)<br />创建训练任务 |
| int            | addAudioUrl(String token, String audioPath, String taskId, int textSegId, long textId, Object usrTag)<br />通过url向训练任务添加音频 |
| int            | submitWithAudio(String token, String audioUrl, String taskId, int textSegId, long textId, Object usrTag)<br />向训练任务添加音频（本地文件）并提交训练任务 |
| int            | submitTask(String token, String taskId, Object usrTag)<br />提交训练任务 |
| int            | getProcess(String token, String taskId, Object usrTag)<br />查询训练状态 |
| int            | vcTTS(String resourceId, String text, String audioEncoding, int status, int seq, Object usrTag)<br />合成音频 |

### 12.2 VC.VCResult API

| **返回值类型** | **方法说明** |
| -------------- | ------------ |
| String         | getKey() <br />业务类型标识 |
| String         | getRawResult() <br />原始结果 |
| String         | getToken()<br />Access Token |
| String         | getTaskId()<br />唯一任务id |
| VC.TextSeg[]   | getTextSegs() <br />训练文本分段 |
| int            | getStatus() <br />状态/进度 |
| String         | getAssetId() <br />音库/资源 ID |
| byte[]         | getAudio() TTS <br />音频数据 |
| int            | getLen()<br />音频长度 |

### 12.3 VC.TextSeg API

| **返回值类型** | **方法说明** |
| -------------- | ------------ |
| int            | getSegId()<br />段落ID，表示第几条文本 |
| String         | getSegText()<br />段落内容 |
| String         | getSegTextLan()<br />段落长度 |
| int            | getSegSize()<br />内容大小 |

### 12.4 VC.VCError API

| **返回值类型** | **方法说明** |
| -------------- | ------------ |
| int            | getCode()<br />错误码 |
| String         | getKey()<br />功能标识 |
| String         | getMessage()<br />错误信息 |
| String         | getSid()<br />错误订单号 |

## 13. 错误码

错误码包含SDK错误码和云端错误码。

### 13.1 SDK错误码

| 错误码 | 含义                                        | 自查指南                                                     |
| ------ | ------------------------------------------- | ------------------------------------------------------------ |
| 0      | 操作成功                                    |                                                              |
| 18000  | 本地license文件不存在                       | 检查工作目录下是否存在license文件，或者该目录是否有读写权限  |
| 18001  | 授权文件内容非法                            | 授权文件存在问题，请联系技术支持询问                         |
| 18002  | 授权文件解析失败                            | 授权文件可能存在损坏，请联系技术支持询问                     |
| 18003  | payload内容缺失                             | 授权文件存在问题，请联系技术支持询问                         |
| 18004  | signature内容缺失                           | 授权文件存在问题，请联系技术支持询问                         |
| 18005  | 授权已过期                                  | 授权时间过期，请检查系统时间是否是当前时间，并联系技术支持询问 |
| 18006  | 授权时间错误，比正常时间慢30分钟以上        | 请检查系统时间是否正确                                       |
| 18007  | 授权应用不匹配（apiKey、apiSecret）         | apiKey、apiSecret 配置有误，请核对项目中配置的 apiKey、apiSecret 。 |
| 18008  | 授权文件激活过期                            | 授权文件已超过15天未激活，需要联系相关人员重新生成离线授权文件 |
| 18009  | 授权app信息指针为空                         |                                                              |
| 18010  | 离线授权激活文件指定平台与设备平台不匹配    | 授权文件里预置的平台架构与实际运行的设备的平台架构不一致     |
| 18011  | 离线授权激活文件指定架构与设备cpu架构不匹配 | 授权文件里预置的cpu架构与实际运行的设备的cpu架构不一致       |
| 18012  | 离线授权激活文件中包含License个数异常       | 离线授权文件异常，请联系相关人员重新生成离线授权文件         |
| 18013  | 离线授权激活文件中未找到当前设备            | 当前运行的设备的设备指纹不在离线授权文件中，请检查该设备的设备指纹是否在提供的指纹池中 |
| 18014  | 离线授权激活文件中设备指纹安全等级非法      | 请联系技术支持调整该appid的设备指纹等级                      |
| 18015  | 硬件授权验证失败                            | 硬件授权验证失败，请联系相关人员处理                         |
| 18016  | 离线授权激活文件内容非法                    | 离线授权文件被修改，请联系相关人员重新生成离线授权文件       |
| 18017  | 离线授权激活文件中协议头非法                | 离线授权文件被修改，请联系相关人员重新生成离线授权文件       |
| 18018  | 离线授权激活文件中指纹组成项个数为0         | 离线授权文件生成异常，请联系相关人员重新生成离线授权文件     |
| 18019  | 资源已过期                                  | 资源的时间校验已过期，请联系相关人员增加授权时间             |
| 18100  | 资源鉴权失败                                | 资源鉴权失败，请联系相关人员处理                             |
| 18101  | 资源格式解析失败                            | 资源格式解析失败，请联系相关人员处理                         |
| 18102  | 资源(与引擎)不匹配                          | 资源(与引擎)不匹配，请检查资源是否用错，如果未用错，请联系相关人员处理 |
| 18103  | 资源参数不存在（指针为NULL）                | 资源参数不存在，请检查资源是否正确                           |
| 18104  | 资源路径打开失败                            | 资源路径打开失败，请检查工作目录下是否存在该资源，或者该资源是否存在读写权限 |
| 18105  | 资源加载失败，workDir内未找到对应资源       | 请检查workDir中是否存在此资源，或者resDir是否设置正确，或者app是否有改路径的读写权限 |
| 18106  | 资源卸载失败, 卸载的资源未加载过            | 资源卸载失败, 卸载的资源未加载过                             |
| 18200  | 引擎鉴权失败                                | 引擎鉴权失败，引擎存在问题。请联系技术支持询问               |
| 18201  | 引擎动态加载失败                            | 引擎动态加载失败，请联系技术支持询问                         |
| 18202  | 引擎未初始化                                | 引擎在使用前，需要调用engineInit初始化                       |
| 18203  | 引擎不支持该接口调用                        | 引擎不支持该接口调用，请查询对应的能力文档，使用正确的方法调用 |
| 18204  | 引擎craete函数指针为空                      | 引擎存在问题，请联系技术支持询问                             |
| 18300  | SDK不可用                                   | SDK存在异常，请联系技术支持询问                              |
| 18301  | SDK未初始化                                 | 在使用大模型前请先初始化 SDK，如果有调用 uninit 方法，再次使用大模型交互时需要重新初始化。 |
| 18302  | SDK初始化失败                               | 请根据init接口回调中返回的错误码参考此文档做对应检查         |
| 18303  | SDK 已经初始化                              | 重复初始化导致，使用能力时，SDK 只需要初始化一次，请检查 SDK 初始化逻辑是否存在多次初始化。 |
| 18304  | 不合法参数                                  | 请参考demo及集成文档仔细检查所传参数是否正确。               |
| 18305  | SDK会话handle为空                           | 请检查代码逻辑，handle是否被释放                             |
| 18306  | SDK会话未找到                               | SDK会话未找到                                                |
| 18307  | SDK会话重复终止                             | SDK会话重复终止，请检查代码逻辑                              |
| 18308  | 超时错误                                    | 请求超时                                                     |
| 18309  | SDK正在初始化中                             | SDK正在初始化中，请检查代码逻辑                              |
| 18310  | SDK会话重复开启                             | SDK会话重复开启，请检查代码逻辑                              |
| 18311  | sdk同一能力并发路数超出最大限制             | sdk同一能力并发路数超出最大限制                              |
| 18312  | 此实例已处在运行态，禁止单实例并发运行      | SDK同一能力单实例不支持并发                                  |
| 18400  | 工作目录无写权限                            | 在设置 workDir 时，请确保该工作路径有读写权限。若无法设置读写权限，请修改为有读写权限的工作路径。 |
| 18401  | 设备指纹获取失败，设备未知                  | 采集不到设备指纹                                             |
| 18402  | 文件打开失败                                | 请检查 日志中所打印的文件是否存在，以及对应路径下是否有读权限。 |
| 18403  | 内存分配失败                                | 请联系技术支持询问                                           |
| 18404  | 设备指纹比较失败                            | 请联系技术支持询问                                           |
| 18500  | 未找到该参数 key                            | 请参照demo或集成文档仔细检查参数名拼写                       |
| 18501  | 参数范围溢出，不满足约束条件                | 请根据文档检查调用 SDK 方法时所传参数范围，需要确保所传参数符合协议约束要求 |
| 18502  | SDK 初始化参数为空                          | 请根据 SDK 集成文档检查 SDK 初始化代码，确保必填参数有值且合法 |
| 18503  | SDK 初始化参数中 appId 为空                 | appId 为空值，请在 SDK 初始化时传入正确的 appId 值           |
| 18504  | SDK 初始化参数中 apiKey为空                 | apiKey为空值，请在 SDK 初始化时传入正确的 apiKey值           |
| 18505  | SDK 初始化参数中 apiSecret 为空             | apiSecret 为空值，请在 SDK 初始化时传入正确的 apapiSecret 值 |
| 18506  | ability参数为空                             | 请检查代码逻辑，参数是否未传入                               |
| 18507  | input参数为空                               | 请检查代码逻辑，参数是否未传入                               |
| 18508  | 输入数据参数Key不存在                       | 请检查代码逻辑，参数key是否不符合该引擎                      |
| 18509  | 必填参数缺失                                | 请参考demo或者文档检查是否漏传必填参数                       |
| 18510  | output参数缺失                              | 引擎输出参数异常，请联系技术支持询问                         |
| 18520  | 不支持的编解码类型                          | 请检查送入的数据是否符合要求                                 |
| 18521  | 编解码handle指针为空                        | 请检查代码逻辑，handle是否被释放                             |
| 18522  | 编解码模块条件编译未打开                    | 请联系技术支持询问                                           |
| 18523  | 编码错误                                    | 请联系技术支持询问                                           |
| 18524  | 解码错误                                    | 请联系技术支持询问                                           |
| 18600  | 协议中时间戳字段缺失                        | 协议文件异常，请联系技术支持询问                             |
| 18601  | 协议中未找到该能力ID                        | 调用的能力不在该SDK中，请检查SDK是否使用错误，或者调用能力id是否写错 |
| 18602  | 协议中未找到该资源ID                        | appid没有该资源的使用权限                                    |
| 18603  | 协议中未找到该引擎ID                        | 协议存在问题，请联系技术支持询问                             |
| 18604  | 协议中引擎个数为0                           | 协议存在问题，请联系技术支持询问                             |
| 18605  | 协议未被初始化解析                          | 协议存在问题，请联系技术支持询问                             |
| 18606  | 协议能力接口类型不匹配                      | 协议存在问题，请联系技术支持询问                             |
| 18607  | 预置协议解析失败                            | 协议存在问题，请联系技术支持询问                             |
| 18700  | 通用网络错误                                | 请检查网络连接是否正常                                       |
| 18701  | 网络不通                                    | 请检查网络连接是否正常                                       |
| 18702  | 网关检查不过                                | 检查设备时间是否正确； 请检查 SDK 初始化时所传 apiKey、apiScrect 是否正确; |
| 18703  | 云端响应格式不对                            | 请检查网络是否可以正常访问外网                               |
| 18704  | 应用未注册                                  | appid存在问题，请检查 appid 是否正确                         |
| 18705  | 应用 ApiKey & ApiSecret 校验失败            | 请检查 apiKey、apiSecret 是否正确                            |
| 18706  | 引擎不支持的平台架构                        | 请检查运行的设备平台引擎是否支持                             |
| 18707  | 授权已过期                                  | 请检查授权期限                                               |
| 18708  | 无可用授权                                  | 没有授权或者授权已满                                         |
| 18709  | 未找到该app绑定的能力                       | 请检查该appid是否申请该能力                                  |
| 18710  | 未找到该app绑定的能力资源                   | 该appid没有该资源的使用权限，请联系技术支持询问              |
| 18711  | JSON操作失败                                | 请联系技术支持询问                                           |
| 18712  | 网络请求 404 错误                           | 请检查网络是否通畅                                           |
| 18713  | 设备指纹安全等级不匹配                      | 设备指纹安全等级不符合要求                                   |
| 18714  | 应用信息有误                                | 服务端无法查询到api_key，请检查api_key和api_secret信息是否填写正确 |
| 18715  | 未找到该SDK ID                              | SDK异常，请联系技术支持询问                                  |
| 18716  | 未找到该组合能力集合                        | 请检查使用的能力是否是该appid所申请的能力                    |
| 18717  | SDK授权不足                                 | 授权数量已满                                                 |
| 18718  | 无效授权应用签名                            | 应用签名异常，请联系技术支持询问                             |
| 18719  | 应用签名不唯一                              | 应用签名异常，请联系技术支持询问                             |
| 18720  | 能力schema不可用                            | 请联系技术支持询问                                           |
| 18721  | 竞争授权: 未找到能力集模板                  | 请联系技术支持询问                                           |
| 18722  | 竞争授权: 能力不在模板能力集模板中          | 请联系技术支持询问                                           |
| 18801  | 连接建立出错                                | 请检查网络是否通畅                                           |
| 18802  | 结果等待超时                                | 请检查网络是否通畅                                           |
| 18803  | 连接状态异常                                | 请检查网络是否通畅                                           |
| 18902  | 并发超过路数限制                            | 不支持并发                                                   |
| 18903  | 大模型规划步骤为空                          | 请检查请求数据的意图是否明确                                 |
| 18904  | 插件未找到                                  | 请检查是否使用了未存在的插件                                 |
| 18906  | 与大模型交互次数超限制                      |                                                              |
| 18907  | 运行超限制时长                              |                                                              |
| 18908  | 大模型返回结果格式异常                      | 可能是因为大模型结果太多，导致30秒内没有返回完，从而引起SDK内部认为超时，建议使用异步调用。 |
| 18951  | 同一流式大模型会话，禁止并发交互请求        |                                                              |
| 18952  | 输入数据为空或异常                          |                                                              |
| 19001  | 设备级授权: 设备被禁用                      |                                                              |
| 19002  | 设备级授权: 协议解析失败                    |                                                              |
| 19003  | 设备级授权: 本地缓存获取失败                |                                                              |
| 19004  | 设备级授权: 无网络                          |                                                              |
| 19005  | 设备级授权: 授权未找到                      |                                                              |
| 19006  | 设备级授权: 设备授权获取失败                |                                                              |
| 19007  | 设备级授权: 当前设备处于黑名单              |                                                              |
| 19008  | 设备级授权: 当前设备不在白名单              |                                                              |
| 19010  | 设备级授权: 鉴权参数非法                    |                                                              |
| 20011  | 设备级授权: 不匹配的appid                   |                                                              |

### 13.2 部分云端错误码

#### 13.2.1 音色训练接口-常见错误码

| 参数名称 | 参数描述                         | 解决方式                                               |
| -------- | -------------------------------- | ------------------------------------------------------ |
| 10000    | token过期无效                    | 检查token是否过期，刷新token                           |
| 10001    | 缺少请求头参数(X-AppId或X-Token) | 检查头部参数                                           |
| 10015    | 训练任务无权操作                 | 任务不属于该应用，无权限操作                           |
| 10016    | 无效的appid                      | 联系我方分配appid权限                                  |
| 10017    | 未授权该训练类型                 | 联系我方授权该训练类型                                 |
| 10018    | 未分配训练路数                   | 联系我方对合作方appid授权训练路数                      |
| 10021    | 未分配训练次数                   | 联系我方对合作方appid授权训练次数                      |
| 10019    | appid授权已过期                  | 联系我方业务员是否增加授权到期时间                     |
| 10020    | 请求ip地址未授权                 | 服务端开启白名单校验时，需要提供ip给我方配置           |
| 20001    | 该textId无效或训练文本内容为空   | 检查textId和textSegId是否正确(通过/train/text接口确认) |
| 20002    | 该textSegId无效                  | 检查textId和textSegId是否正确(通过/train/text接口确认) |
| 60000    | 训练任务不存在                   | 检测taskId是否正确                                     |
| 90001    | 请求非法                         | 按照接口协议检查请求结构                               |
| 90002    | 请求参数不正确(详细原因)         | 例如：textId must not be blank                         |
| 99999    | 系统内部异常                     | 联系我方排查解决                                       |

#### 13.2.2 音频合成接口-常见错误码

| 错误码        | 错误描述                                                     | 说明                                         | 处理策略                                                     |
| ------------- | ------------------------------------------------------------ | -------------------------------------------- | ------------------------------------------------------------ |
| 10009         | input invalid data                                           | 输入数据非法                                 | 检查输入数据                                                 |
| 10010         | service license not enough                                   | 没有授权许可或授权数已满                     | 提交工单                                                     |
| 10019         | service read buffer timeout, session timeout                 | session超时                                  | 检查是否数据发送完毕但未关闭连接                             |
| 10043         | Syscall AudioCodingDecode error                              | 音频解码失败                                 | 检查aue参数，如果为speex，请确保音频是speex音频并分段压缩且与帧大小一致 |
| 10114         | session timeout                                              | session 超时                                 | 会话时间超时，检查是否发送数据时间超过了60s                  |
| 10139         | invalid param                                                | 参数错误                                     | 检查参数是否正确                                             |
| 10160         | parse request json error                                     | 请求数据格式非法                             | 检查请求数据是否是合法的json                                 |
| 10161         | parse base64 string error                                    | base64解码失败                               | 检查发送的数据是否使用base64编码了                           |
| 10163         | param validate error:...                                     | 参数校验失败                                 | 具体原因见详细的描述                                         |
| 10200         | read data timeout                                            | 读取数据超时                                 | 检查是否累计10s未发送数据并且未关闭连接                      |
| 10222         | context deadline exceeded                                    | 1.上传的数据超过了接口上限； 2.SSL证书无效； | 1.检查接口上传的数据（文本、音频、图片等）是否超越了接口的最大限制，可到相应的接口文档查询具体的上限； 2. 请将log导出发到工单：https://console.xfyun.cn/workorder/commit； |
| 10223         | RemoteLB: can't find valued addr                             | lb 找不到节点                                | 提交工单                                                     |
| 10313         | invalid appid                                                | appid和apikey不匹配                          | 检查appid是否合法                                            |
| 10317         | invalid version                                              | 版本非法                                     | 请到控制台提交工单联系技术人员                               |
| 10700         | not authority                                                | 引擎异常                                     | 按照报错原因的描述，对照开发文档检查输入输出，如果仍然无法排除问题，请提供sid以及接口返回的错误信息，到控制台提交工单联系技术人员排查。 |
| 11200         | auth no license                                              | 功能未授权                                   | 请先检查appid是否正确，并且确保该appid下添加了相关服务。若没问题，则按照如下方法排查。 1. 确认总调用量是否已超越限制，或者总次数授权已到期，若已超限或者已过期请联系商务人员。 2. 查看是否使用了未授权的功能，或者授权已过期。 |
| 11201         | auth no enough license                                       | 该APPID的每日交互次数超过限制                | 根据自身情况提交应用审核进行服务量提额，或者联系商务购买企业级正式接口，获得海量服务量权限以便商用。 |
| 11503         | server error :atmos return an error data                     | 服务内部响应数据错误                         | 提交工单                                                     |
| 11502         | server error: too many datas in resp                         | 服务配置错误                                 | 提交工单                                                     |
| 100001~100010 | WrapperInitErr                                               | 调用引擎时出现错误                           | 请提供sid以及接口返回的错误信息，到控制台提交工单联系技术人员排查。 |
| 26004         | invalid res_id, query res_id error, No data found in response | res_id无效                                   | 已注册检查输入是否正确； 未注册请先注册；注意res_id是和appid绑定 |
| 26005         | No active up data within 14000ms, task failed                | 上行数据超时，超过14s没收到客户端的数据      | 检查客户端代码或网络                                         |
| 26006         | No active down data within 14000 ms, task failed             | 下行数据超时，服务内部下发数据超时           | 请到控制台提交工单联系技术人员                               |
