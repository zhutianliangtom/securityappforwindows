# SparkChain 声纹特征（Feature） Android SDK 集成文档

## 1. 声纹特征（Feature）简介

声纹特征能力（SDK 类名 `Feature`）用于声纹注册、更新与删除等操作。开发者将符合要求的音频数据提交给 SDK，由服务提取声纹并返回 `featureId`；后续可凭 `featureId` 做更新或删除。

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

复制SparkChain.aar到项目的libs目录下，然后在主Module的build.gradle文件中，增加如下配置：

```java
implementation files('libs/SparkChain.aar')
```

若 Demo 中还需 `Codec.aar` 等依赖，请一并按 Sample 工程配置。

### 4.2 配置权限

外部使用时需要配置以下权限：

| **权限**                | **使用说明**                                                 |
| ----------------------- | ------------------------------------------------------------ |
| INTERNET                | 必须权限，SDK 需要访问网络获取结果。                          |
| READ_EXTERNAL_STORAGE   | 必须权限，读取待注册/更新的音频文件、判断日志路径等。          |
| WRITE_EXTERNAL_STORAGE  | 必须权限，SDK 写本地日志等需要用到该权限。                  |
| MANAGE_EXTERNAL_STORAGE | 可选权限，Android 10 及以上设备用于动态授权等场景，按业务需要申请。 |

如果部分权限不需要，可通过如下配置去除，去除示例如下：

```Java
Android 10.0（API 29）及以上版本需要在application中做如下配置
<application android:requestLegacyExternalStorage="true"/>
```

### 4.3 混淆配置

SparkChain SDK 已做过混淆。若项目中开启了混淆，请在 `proguard-rules.pro` 中添加：

```java
-keep class com.iflytek.sparkchain.** {*;} 
-keep class com.iflytek.sparkchain.**
```

## 5. 业务调用流程说明

![](D:\iflytek\aikit\demo\Sparkchain\Andorid\SparkChain_Android_SDK_2.0.1_rc3_260309\集成文档\pic\Android声纹流程图.png)

## 6. SDK 初始化

**在使用SDK功能前，需要先开通语音听写授权并获取已开通授权的应用信息（appId、apiKey、apiSecret）。SDK全局只需要初始化一次。**初始化时，开发者需要构建一个SparkChainConfig实例config，把相关的appid信息以及日志设置等传入config中，然后再通过SparkChain.getInst().init方法把config实例设置到SDK中。具体初始化示例如下：

```java
//配置应用信息 
SparkChainConfig config =  SparkChainConfig.builder()    
    .appID("$appId")       
    .apiKey("$apiKey")    
    .apiSecret("$apiSecret")
    .workDir("$workdir")
int ret = SparkChain.getInst().init(getApplicationContext(), config); 
```

**初始化参数说明：**

| **接口名称** | **含义**                                                     | **参数类型** | **限制**                                                     | **是否必填** |
| ------------ | ------------------------------------------------------------ | ------------ | ------------------------------------------------------------ | ------------ |
| appID        | 创建应用后，生成的应用 ID                                     | String       | 与平台生成的 appID 完全一致                                  | 是           |
| apiKey       | 创建应用后，生成的唯一应用标识                               | String       | 与平台生成的 apiKey 完全一致                                 | 是           |
| apiSecret    | 创建应用后，生成的唯一应用秘钥                               | String       | 与平台生成的 apiSecret 完全一致                              | 是           |
| workDir      | 工作目录                                                     | String       | SDK 工作目录，用户可自行指定，须确保应用具有访问权限           | 是           |
| logLevel     | 日志等级                                                     | int          | 枚举：0：VERBOSE，1：DEBUG，2：INFO，3：WARN，4：ERROR，5：FATAL，100：OFF | 否           |
| logPath      | 日志存储路径（需指定到文件，如 `"/sdcard/iflytek/sparkchain.log"`）；设置后写入该文件，不设置则多在 Logcat 输出 | String       | 路径须具备读写权限                                           | 否           |
| uid          | 用户自定义标识                                               | String       | 按业务需要传入                                               | 否           |

**初始化返回值：** `0` 表示初始化成功；非 `0` 表示失败，请根据返回值查阅本文档 **第 12 章** 错误码。

## 7. Feature 能力初始化

使用声纹特征前，通过无参构造创建实例，并注册回调接口：

```java
Feature mFeature = new Feature();
mFeature.registerCallbacks(mFeatureCallbacks);
```

| 说明项     | 内容                                                         |
| ---------- | ------------------------------------------------------------ |
| 构造方法   | `public Feature()`，创建独立能力实例。                        |
| 回调注册   | 发起 `featureRegister` / `featureUpdate` / `featureDelete` 前必须注册；可替换为新回调对象。 |
| 并发与状态 | 建议在上一笔异步结果（`onResult`/`onError`）返回前，勿发起下一笔同实例请求，避免 `18312` 等单实例运行态错误。 |

## 8. 注册结果监听回调

运行结果通过 `FeatureCallbacks` 异步返回，接口定义如下：

```java
public interface FeatureCallbacks {
    void onResult(Feature.FeatureResult result, Object usrTag);
    void onError(Feature.FeatureError error, Object usrTag);
}
```

### 8.1 onResult

| **参数** | **类型**                  | **说明**                                                     |
| -------- | ------------------------- | ------------------------------------------------------------ |
| result   | `Feature.FeatureResult`   | 成功时的结果对象；注册成功时可通过 `getFeatureId()` 获取服务端分配的声纹 ID。 |
| usrTag   | Object                    | 与调用 `featureRegister` / `featureUpdate` / `featureDelete` 时传入的 `usrTag` 一致，用于关联请求与回调。 |

### 8.2 Feature.FeatureResult 结构说明

| **方法**         | **返回值类型** | **说明**                                                     |
| ---------------- | -------------- | ------------------------------------------------------------ |
| `getFeatureId()` | String         | 声纹特征 ID。注册成功后为新 ID；更新、删除类操作若服务端仍返回 ID，以联调结果与控制台说明为准。 |

### 8.3 onError

| **参数** | **类型**                 | **说明**                                                     |
| -------- | ------------------------ | ------------------------------------------------------------ |
| error    | `Feature.FeatureError`   | 错误信息对象。                                               |
| usrTag   | Object                   | 与发起请求时传入的 `usrTag` 一致。                           |

### 8.4 Feature.FeatureError 结构说明

| **方法**       | **返回值类型** | **说明**                         |
| -------------- | -------------- | -------------------------------- |
| `getCode()`    | int            | 错误码，可对照本文档第 12 章。   |
| `getMessage()` | String         | 错误描述信息。                   |

### 8.5 回调示例

```java
FeatureCallbacks mFeatureCallbacks = new FeatureCallbacks() {
    @Override
    public void onResult(Feature.FeatureResult result, Object usrTag) {
        String fid = result.getFeatureId();
        if ("register".equals(usrTag)) {
            // 保存 fid 供后续更新、删除使用
        }
    }

    @Override
    public void onError(Feature.FeatureError error, Object usrTag) {
        int code = error.getCode();
        String msg = error.getMessage();
        // 日志与提示
    }
};
mFeature.registerCallbacks(mFeatureCallbacks);
```

## 9. 请求调用说明

以下接口的 **int 返回值** 表示「SDK 是否接受本次调用」：`0` 一般为接受并已发起异步流程；**非 0** 多为参数或状态异常，可对照错误码；**最终成功或失败以 `onResult` / `onError` 为准**。

### 9.1 声纹注册 featureRegister

```java
public int featureRegister(byte[] audioData, String format, String userId, Object usrTag);
```

| **形参名** | **类型** | **必传** | **说明**                                                     |
| ---------- | -------- | -------- | ------------------------------------------------------------ |
| audioData  | byte[]   | 是       | 音频二进制数据。长度须大于 0；内容编码须与 `format` 一致。采样率、位深、声道、最大字节数等以平台与联调要求为准。 |
| format     | String   | 是       | 音频格式标识。Demo 中为 `"raw"`，表示与约定一致的裸 PCM（或协议定义的 raw）。其它取值以官方接口说明为准。 |
| userId     | String   | 是       | 业务侧用户标识，用于将声纹与用户账号等关联；字符串内容规则以服务端为准。Demo 示例：`"userid-123456"`。 |
| usrTag     | Object   | 否       | 自定义回传标记；建议传入以便在回调中区分请求（如 `"register"`），判等请用 `equals`，勿用 `==`。 |

### 9.2 声纹更新 featureUpdate

```java
public int featureUpdate(byte[] audioData, String format, String featureId, Object usrTag);
```

| **形参名** | **类型** | **必传** | **说明**                                                     |
| ---------- | -------- | -------- | ------------------------------------------------------------ |
| audioData  | byte[]   | 是       | 新的音频数据，要求同注册。                                   |
| format     | String   | 是       | 同 `featureRegister`。                                       |
| featureId  | String   | 是       | 已通过注册接口获得的声纹 ID，表示待更新的目标特征。          |
| usrTag     | Object   | 否       | 自定义回传标记，如 `"update"`。                              |

### 9.3 声纹删除 featureDelete

```java
public int featureDelete(String featureId, Object usrTag);
```

| **形参名** | **类型** | **必传** | **说明**                                                     |
| ---------- | -------- | -------- | ------------------------------------------------------------ |
| featureId  | String   | 是       | 待删除的声纹特征 ID。                                        |
| usrTag     | Object   | 否       | 自定义回传标记，如 `"delete"`。                              |

### 9.4 从文件读取音频并注册（示例）

```java
byte[] data = null;
try {
    File file = new File("/sdcard/iflytek/test_1.pcm");
    FileInputStream fis = new FileInputStream(file);
    data = new byte[(int) file.length()];
    fis.read(data);
    fis.close();
} catch (Exception e) {
    // 处理异常
}
if (data == null || data.length == 0) {
    return;
}
if (mFeature == null) {
    mFeature = new Feature();
}
mFeature.registerCallbacks(mFeatureCallbacks);
int ret = mFeature.featureRegister(data, "raw", "userid-123456", "register");
if (ret != 0) {
    // 同步失败，结合错误码排查
}
```

## 10. 逆初始化

当 SDK 需要完整退出时，调用逆初始化释放资源：

```java
SparkChain.getInst().unInit();
```

## 11. SDK API 介绍

### 11.1 SparkChainConfig API

| **返回值类型**   | **方法说明**                                                 |
| ---------------- | ------------------------------------------------------------ |
| SparkChainConfig | `public SparkChainConfig appID(String appID)` 设置 appID     |
| SparkChainConfig | `public SparkChainConfig apiKey(String apiKey)` 设置 apiKey |
| SparkChainConfig | `public SparkChainConfig apiSecret(String apiSecret)` 设置 apiSecret |
| SparkChainConfig | `public SparkChainConfig uid(String uid)` 设置用户自定义标识 |
| SparkChainConfig | `public SparkChainConfig workDir(String workDir)` 设置工作目录 |
| SparkChainConfig | `public SparkChainConfig logLevel(int logLevel)` 设置日志等级 |
| SparkChainConfig | `public SparkChainConfig logPath(String logPath)` 设置日志路径 |
| SparkChainConfig | `public static SparkChainConfig builder()` 构建配置对象      |

### 11.2 SparkChain API

| **返回值类型** | **方法说明**                                                 |
| -------------- | ------------------------------------------------------------ |
| SparkChain     | `public static SparkChain getInst()` 获取单例                |
| int            | `public int init(Context context, SparkChainConfig config)` SDK 初始化 |
| int            | `public int init(Context context)` SDK 初始化（重载）        |
| int            | `public int unInit()` SDK 逆初始化                           |
| int            | `public int getInitCode()` 获取初始化结果码                  |

### 11.3 Feature API

| **返回值类型** | **方法说明**                                                 |
| -------------- | ------------------------------------------------------------ |
| void           | `public void registerCallbacks(FeatureCallbacks cbs)` 注册回调 |
| int            | `public int featureRegister(byte[] data, String format, String userId, Object usrTag)` 声纹注册 |
| int            | `public int featureUpdate(byte[] data, String format, String featureId, Object usrTag)` 声纹更新 |
| int            | `public int featureDelete(String featureId, Object usrTag)` 声纹删除 |

### 11.4 FeatureCallbacks API

| **返回值类型** | **方法说明**                                                 |
| -------------- | ------------------------------------------------------------ |
| void           | `void onResult(Feature.FeatureResult result, Object usrTag)` 成功回调 |
| void           | `void onError(Feature.FeatureError error, Object usrTag)` 失败回调 |

### 11.5 Feature.FeatureResult API

| **返回值类型** | **方法说明**                                                 |
| -------------- | ------------------------------------------------------------ |
| String         | `public String getFeatureId()` 获取声纹特征 ID               |

### 11.6 Feature.FeatureError API

| **返回值类型** | **方法说明**                         |
| -------------- | ------------------------------------ |
| int            | `public int getCode()` 错误码        |
| String         | `public String getMessage()` 错误信息 |

## 12. 错误码

错误码包含 SDK 错误码与云端错误码。Feature 与听写等同属 SparkChain 体系，下列与《SparkChain 语音听写 Android SDK集成文档》**第 13 章** 保持一致，便于统一排查。

### 12.1 SDK 错误码

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
| 18007  | 授权应用不匹配（apiKey、apiSecret）         | apiKey、apiSecret 配置有误，请核对项目中配置。                 |
| 18008  | 授权文件激活过期                            | 授权文件已超过15天未激活，需要联系相关人员重新生成离线授权文件 |
| 18009  | 授权app信息指针为空                         |                                                              |
| 18010  | 离线授权激活文件指定平台与设备平台不匹配    | 授权文件里预置的平台架构与实际运行设备不一致                 |
| 18011  | 离线授权激活文件指定架构与设备cpu架构不匹配 | 授权文件里预置的cpu架构与实际运行设备不一致                   |
| 18012  | 离线授权激活文件中包含License个数异常       | 离线授权文件异常，请联系相关人员重新生成                     |
| 18013  | 离线授权激活文件中未找到当前设备            | 设备指纹不在离线授权指纹池中                                  |
| 18014  | 离线授权激活文件中设备指纹安全等级非法      | 请联系技术支持调整该 appid 的设备指纹等级                    |
| 18015  | 硬件授权验证失败                            | 请联系相关人员处理                                           |
| 18016  | 离线授权激活文件内容非法                    | 离线授权文件被修改，请重新生成                               |
| 18017  | 离线授权激活文件中协议头非法                | 离线授权文件被修改，请重新生成                               |
| 18018  | 离线授权激活文件中指纹组成项个数为0         | 离线授权文件生成异常，请重新生成                             |
| 18019  | 资源已过期                                  | 资源时间校验已过期，请联系相关人员增加授权时间               |
| 18100  | 资源鉴权失败                                | 请联系相关人员处理                                           |
| 18101  | 资源格式解析失败                            | 请联系相关人员处理                                           |
| 18102  | 资源(与引擎)不匹配                          | 请检查资源是否用错                                           |
| 18103  | 资源参数不存在（指针为NULL）                | 请检查资源是否正确                                           |
| 18104  | 资源路径打开失败                            | 请检查路径与读写权限                                         |
| 18105  | 资源加载失败，workDir内未找到对应资源       | 请检查 workDir、resDir 与权限                                |
| 18106  | 资源卸载失败, 卸载的资源未加载过            |                                                              |
| 18200  | 引擎鉴权失败                                | 请联系技术支持询问                                           |
| 18201  | 引擎动态加载失败                            | 请联系技术支持询问                                           |
| 18202  | 引擎未初始化                                | 引擎使用前需按文档初始化                                     |
| 18203  | 引擎不支持该接口调用                        | 请使用正确接口                                               |
| 18204  | 引擎craete函数指针为空                      | 请联系技术支持询问                                           |
| 18300  | SDK不可用                                   | SDK 异常，请联系技术支持                                     |
| 18301  | SDK未初始化                                 | 请先 `init`；若已 `unInit`，再次使用前需重新初始化           |
| 18302  | SDK初始化失败                               | 根据错误码检查配置                                           |
| 18303  | SDK 已经初始化                              | 避免重复初始化                                               |
| 18304  | 不合法参数                                  | 对照本文档检查参数                                           |
| 18305  | SDK会话handle为空                           | 检查句柄是否被释放                                           |
| 18306  | SDK会话未找到                               |                                                              |
| 18307  | SDK会话重复终止                             | 检查调用逻辑                                                 |
| 18308  | 超时错误                                    | 检查网络与接口耗时                                           |
| 18309  | SDK正在初始化中                             | 避免并发初始化                                               |
| 18310  | SDK会话重复开启                             | 检查会话逻辑                                                 |
| 18311  | sdk同一能力并发路数超出最大限制             | 降低并发路数                                                 |
| 18312  | 此实例已处在运行态，禁止单实例并发运行      | 等待上一笔回调结束再调用                                     |
| 18400  | 工作目录无写权限                            | 更换有读写权限的 workDir                                     |
| 18401  | 设备指纹获取失败，设备未知                  |                                                              |
| 18402  | 文件打开失败                                | 检查路径与读权限                                             |
| 18403  | 内存分配失败                                | 请联系技术支持                                               |
| 18404  | 设备指纹比较失败                            | 请联系技术支持                                               |
| 18500  | 未找到该参数 key                            | 检查参数名拼写                                               |
| 18501  | 参数范围溢出，不满足约束条件                | 检查取值范围                                                 |
| 18502  | SDK 初始化参数为空                          | 补全初始化必填项                                             |
| 18503  | SDK 初始化参数中 appId 为空                 | 传入 appID                                                   |
| 18504  | SDK 初始化参数中 apiKey为空                 | 传入 apiKey                                                  |
| 18505  | SDK 初始化参数中 apiSecret 为空             | 传入 apiSecret                                               |
| 18506  | ability参数为空                             | 检查入参                                                     |
| 18507  | input参数为空                               | 检查入参                                                     |
| 18508  | 输入数据参数Key不存在                       | 检查 key 与能力是否匹配                                      |
| 18509  | 必填参数缺失                                | 对照文档补参                                                 |
| 18510  | output参数缺失                              | 请联系技术支持                                               |
| 18520  | 不支持的编解码类型                          | 检查音频与 format                                            |
| 18521  | 编解码handle指针为空                        | 检查句柄                                                     |
| 18522  | 编解码模块条件编译未打开                    | 请联系技术支持                                               |
| 18523  | 编码错误                                    | 请联系技术支持                                               |
| 18524  | 解码错误                                    | 请联系技术支持                                               |
| 18600  | 协议中时间戳字段缺失                        | 协议异常，请联系技术支持                                     |
| 18601  | 协议中未找到该能力ID                        | 检查 SDK 与能力是否匹配                                      |
| 18602  | 协议中未找到该资源ID                        | 检查 appid 资源权限                                          |
| 18603  | 协议中未找到该引擎ID                        | 请联系技术支持                                               |
| 18604  | 协议中引擎个数为0                         | 请联系技术支持                                               |
| 18605  | 协议未被初始化解析                          | 请联系技术支持                                               |
| 18606  | 协议能力接口类型不匹配                      | 请联系技术支持                                               |
| 18607  | 预置协议解析失败                            | 请联系技术支持                                               |
| 18700  | 通用网络错误                                | 检查网络                                                     |
| 18701  | 网络不通                                    | 检查网络                                                     |
| 18702  | 网关检查不过                                | 检查设备时间与 apiKey、apiSecret                             |
| 18703  | 云端响应格式不对                            | 检查外网访问                                                 |
| 18704  | 应用未注册                                  | 检查 appid                                                   |
| 18705  | 应用 ApiKey & ApiSecret 校验失败            | 检查密钥                                                     |
| 18706  | 引擎不支持的平台架构                        | 检查设备架构                                                 |
| 18707  | 授权已过期                                  | 检查授权期限                                                 |
| 18708  | 无可用授权                                  | 无授权或已满                                                 |
| 18709  | 未找到该app绑定的能力                       | 在控制台申请对应能力                                         |
| 18710  | 未找到该app绑定的能力资源                   | 联系技术支持                                                 |
| 18711  | JSON操作失败                                | 请联系技术支持                                               |
| 18712  | 网络请求 404 错误                           | 检查网络                                                     |
| 18713  | 设备指纹安全等级不匹配                      |                                                              |
| 18714  | 应用信息有误                                | 检查 api_key / api_secret                                    |
| 18715  | 未找到该SDK ID                              | 请联系技术支持                                               |
| 18716  | 未找到该组合能力集合                        | 检查能力是否属于该 appid                                     |
| 18717  | SDK授权不足                                 | 授权数量已满                                                 |
| 18718  | 无效授权应用签名                            | 联系技术支持                                                 |
| 18719  | 应用签名不唯一                              | 联系技术支持                                                 |
| 18720  | 能力schema不可用                            | 联系技术支持                                                 |
| 18721  | 竞争授权: 未找到能力集模板                  | 联系技术支持                                                 |
| 18722  | 竞争授权: 能力不在模板能力集模板中          | 联系技术支持                                                 |
| 18801  | 连接建立出错                                | 检查网络                                                     |
| 18802  | 结果等待超时                                | 检查网络                                                     |
| 18803  | 连接状态异常                                | 检查网络                                                     |
| 18902  | 并发超过路数限制                            | 降低并发                                                     |
| 18903  | 大模型规划步骤为空                          |                                                              |
| 18904  | 插件未找到                                  |                                                              |
| 18906  | 与大模型交互次数超限制                      |                                                              |
| 18907  | 运行超限制时长                              |                                                              |
| 18908  | 大模型返回结果格式异常                      |                                                              |
| 18951  | 同一流式大模型会话，禁止并发交互请求        |                                                              |
| 18952  | 输入数据为空或异常                          | 检查 audioData 等入参                                        |
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
