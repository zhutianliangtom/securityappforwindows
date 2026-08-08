# SparkChain 实时语音转写 Android SDK集成文档

## 1. 实时语音转写简介

实时语音转写（Real-time ASR）基于深度全序列卷积神经网络框架，通过 WebSocket 协议，建立应用与语言转写核心引擎的长连接，开发者可实现将连续的音频流内容，实时识别返回对应的文字流内容。 支持的音频格式： **采样率为16K，采样深度为16bit，单声道的pcm音频**

注意：在使用该能力前，需要开通相应的授权。

## 2. 兼容性说明

| 类别     | 兼容范围                                        |
| -------- | ----------------------------------------------- |
| 系统     | 支持armv7和armv8架构，兼容android 5.0及以上版本 |
| 开发环境 | 建议使用Android Studio 进行开发                 |

## 3. SDK集成包目录结构

将SDK zip包解压缩，得到如下文件：

├── Demo SparkChain的使用DEMO，DEMO中已经集成了SDK，您可以参考DEMO，集成SDK。集成前，请先测通DEMO，了解调用原理。

├── ReleaseNotes.txt SDK版本日志

├── SDK SparkChain SDK

│ └── SparkChain.aar

└── SparkChain 实时语音转写 Android SDK集成文档.pdf     SparkChain集成指南

## 4. SDK工程配置

### 4.1 导入SDK库

复制SparkChain.aar到项目的libs目录下，然后在主Module的build.gradle文件中，增加如下配置：

```Java
implementation files('libs/SparkChain.aar')
```

### 4.2 配置权限

外部使用时需要配置以下权限：

| **权限**                | **使用说明**                                                 |
| ----------------------- | ------------------------------------------------------------ |
| INTERNET                | 必须权限，SDK需要访问网络获取结果。                          |
| READ_EXTERNAL_STORAGE   | 必须权限，SDK需要判断日志路径是否存在。                      |
| WRITE_EXTERNAL_STORAGE  | 必须权限，SDK写本地日志需要用到该权限。                      |
| MANAGE_EXTERNAL_STORAGE | 可选权限，安卓10以上设备用于动态授权弹出授权框需要用到该权限，安卓10以上设备必选。 |

如果部分权限不需要，可通过如下配置去除，去除示例如下：

```Java
Android 10.0（API 29）及以上版本需要在application中做如下配置
<application android:requestLegacyExternalStorage="true"/>
```

### 4.3 混淆配置

SparkChain SDK 已做过混淆，如果您项目中也使用了混淆，请在 proguard-rules.pro文件中添加如下配置保持SparkChain SDK 不再被混淆。

```Java
-keep class com.iflytek.sparkchain.** {*;} 
-keep class com.iflytek.sparkchain.**
```

## 5. 接口流程调用图

![](.\pic\Android实时语音转写流程图.PNG)

## 6. SDK 初始化

**在使用SDK功能前，需要先开通实时语音转写授权并获取已开通授权的应用信息（appId、apiKey、apiSecret）。SDK全局只需要初始化一次。**初始化时，开发者需要构建一个SparkChainConfig实例config，把相关的appid信息以及日志设置等传入config中，然后再通过SparkChain.getInst().init方法把config实例设置到SDK中。具体初始化示例如下：

```Java
//配置应用信息 
SparkChainConfig config =  SparkChainConfig.builder()    
    .appID("$appId")       
    .apiKey("$apiKey")    
    .apiSecret("$apiSecret")
    .workDir("$workdir"); 
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

## 7. 实时语音转写初始化

在使用实时语音转写功能前，需先通过其构造方法RTASR()方法构建其实例，然后用该实例调用相应的方法去设置转写参数。

实时语音转写构造方法如下：

```Java
public class RTASR {
    public RTASR(String apiKey) {
        ...
    }
}
```

构造方法参数说明：

| 方法名 | 参数名 | 类型   | 说明                                                         |
| ------ | ------ | ------ | ------------------------------------------------------------ |
| RTASR  | apikey | String | apikey，用于建立链接时鉴权。可从[开放平台](https://console.xfyun.cn/services/rta)查看。<br />**注意，该值与SDK初始化时传入apiKey不同。** |

具体示例如下：

```Java
RTASR mRTASR = new RTASR(rtAsrApiKey);//rtAsrApiKey参见应用中实时转写栏里的apikey
```

## 8. 功能参数配置

SDK支持用户根据自身需求，通过构建的RTASR实例访问相关方法配置转写参数。具体方法说明如下：

| 方法名        | 形参名        | 形参类型 | 说明                                                         | 是否必填 | 默认值                                         |
| ------------- | ------------- | -------- | ------------------------------------------------------------ | -------- | ---------------------------------------------- |
| lang          | lang          | String   | 实时语音转写语种，不传默认为中文。若未授权无法使用会报错10110 | 否       | cn                                             |
| transType     | transType     | String   | normal表示普通翻译。注意：需控制台开通翻译功能               | 否       | normal                                         |
| transStrategy | transStrategy | int      | 策略1，转写的vad结果直接送去翻译； <br />策略2，返回中间过程中的结果； <br />策略3，按照结束性标点拆分转写结果请求翻译； 建议使用策略2。<br />注意：需控制台开通翻译功能 | 否       | 2                                              |
| targetLang    | targetLang    | String   | 目标翻译语种：控制把源语言转换成什么类型的语言； 请注意类似英文转成法语必须以中文为过渡语言，即英-中-法，暂不支持不含中文语种之间的直接转换；<br />中文：cn <br />英文：en <br />日语：ja <br />韩语：ko <br />俄语：ru <br />法语：fr <br />西班牙语：es <br />越南语：vi <br />广东话：cn_cantonese | 否       | 如果不传，则默认不使用翻译，即没有翻译结果返回 |
| punc          | punc          | String   | 标点过滤控制，默认返回标点，punc=0会过滤结果中的标点         | 否       | 不传则默认返回标点                             |
| pd            | pd            | String   | 垂直领域个性化参数: <br />法院: court <br />教育: edu <br />金融: finance <br />医疗: medical <br />科技: tech <br />运营商: isp <br />政府: gov <br />电商: ecom <br />军事: mil <br />企业: com <br />生活: life <br />汽车: car | 否       | 不设置参数默认为通用                           |
| vadMdn        | vadMdn        | int      | 远近场切换，不传此参数或传1代表远场，传2代表近场             | 否       | 不传默认为远场                                 |
| roleType      | roleType      | int      | 是否开角色分离，默认不开启，传2开启 (效果持续优化中)         | 否       | 不开启                                         |
| engLangType   | engLangType   | int      | 语言识别模式，默认为模式1中英文模式： <br />1：自动中英文模式 <br />2：中文模式，可能包含少量英文 <br />4：纯中文模式，不包含英文 | 否       | 1                                              |

具体配置示例如下：

```Java
mRTASR.transType("normal");
mRTASR.transStrategy(2);
...
mRTASR.lang("cn");
mRTASR.targetLang("en");
```

## 9. 注册结果监听回调

实时语音转写运行结果通过RTASRCallbacks异步返回，接口定义如下：

```Java
public interface RTASRCallbacks {
    void onResult(RTASR.RtAsrResult result, Object usrTag);

    void onError(RTASR.RtAsrError error, Object usrTag);
}
```

RTASRCallbacks数据结构说明：

- onResult为实时语音转写结果回调方法，参数说明如下：

  | 参数   | 类型              | 说明                 |
  | ------ | ----------------- | -------------------- |
  | result | RTASR.RtAsrResult | 实时语音转写结果实例 |
  | usrTag | Object            | 用户自定义标识       |

- RTASR.RtAsrResult结构说明：

  | 方法                         | 返回值类型 | 说明                                                         |
  | ---------------------------- | ---------- | ------------------------------------------------------------ |
  | getData()                    | String     | 转写结果                                                     |
  | getRawResult()               | String     | 云端下发的原始json结果                                       |
  | getStatus()                  | int        | 数据状态： <br />0：此次返回翻译结果。(此时仅翻译有结果，data无结果) <br />1：流式识别结果 <br />2：子句plain结果 <br />3：end |
  | getSid()                     | String     | 本次交互的sid                                                |
  | getTransResult().getSrc()    | String     | 翻译的源文本                                                 |
  | getTransResult().getDst()    | String     | 翻译结果                                                     |
  | getTransResult().getStatus() | int        | 翻译状态：<br />2：翻译的plain结果                           |

- onError为实时语音转写错误回调，参数说明如下：

  | 参数   | 类型             | 说明             |
  | ------ | ---------------- | ---------------- |
  | error  | RTASR.RtAsrError | 错误信息结果实例 |
  | usrTag | Object           | 用户自定义标识   |

- RTASR.RtAsrError结构说明：

  | 方法        | 返回值类型 | 说明      |
  | ----------- | ---------- | --------- |
  | getCode()   | int        | 错误码    |
  | getErrMsg() | String     | 错误信息  |
  | getSid()    | String     | 交互的Sid |

具体示例如下：

```Java
RTASRCallbacks mRtAsrCallbacks = new RTASRCallbacks() {
    @Override
    public void onResult(RTASR.RtAsrResult result, Object usrTag) {
        String data      = result.getData();                     //识别结果
        String rawResult = result.getRawResult();                //云端识别的原始结果
        int status       = result.getStatus();                   //数据状态
        String sid       = result.getSid();                      //交互sid
        String src       = result.getTransResult().getSrc();     //翻译源文本
        String dst       = result.getTransResult().getDst();     //翻译结果
        int transStatus  = result.getTransResult().getStatus();  //翻译状态
    }

    @Override
    public void onError(RTASR.RtAsrError error, Object usrTag) {
        int code   = error.getCode();    //错误码
        String msg = error.getErrMsg();  //错误信息
        String sid = error.getSid();     //交互sid
    }
};
mRTASR.registerCallbacks(mRtAsrCallbacks);
```

## 10. 请求调用

### 10.1 开启会话

开发者注册完监听回调后，可通过mRTASR.start()方法开启会话。请求调用接口如下：

```Java
public class RTASR {
    public int start(Object usrTag) {
        ...
    }
}
```

start方法结构说明：

| 参数   | 类型   | 说明           |
| ------ | ------ | -------------- |
| usrTag | Object | 用户自定义标识 |

具体示例如下：

```Java
int ret = mRTASR.start("12345");
```

### 10.2 送入数据

启动会话后，开发者可通过mRTASR.write()方法送入要识别的音频，然后异步从监听回调中获取识别结果。write方法调用接口如下：

```Java
public class RTASR {
    public int write(byte[] data) {
        ...
    }
}
```

write方法参数说明：

| 参数 | 类型   | 说明                                                         |
| ---- | ------ | ------------------------------------------------------------ |
| data | byte[] | 识别音频<br />**注意：<br />1.建议音频流每40ms发送1280字节，发送过快可能导致引擎出错； <br />2.音频发送间隔超时时间为15秒，超时服务端报错并主动断开连接。** |

具体示例如下：

```Java
byte[] data = new byte[1280]; 
...//省略获取音频的过程 
mRTASR.write(data);
```

### 10.3 结束会话

当开发者送完数据后，需要调用mRTASR.stop()方法通知SDK层以及云端数据已传完。之后云端则会下发最终的识别结果，然后结束本轮交互。stop方法调用接口如下：

```Java
public class RTASR {
    public int stop() {
        ...
    }

}
```

具体示例如下：

```Java
mRTASR.stop();      //停止
```

## 11. 逆初始化

当SDK需要完整退出时，需调用逆初始化方法释放资源，示例代码如下：

```Java
SparkChain.getInst().unInit();  //SDK逆初始化
```

## 12. SDK API介绍

### 12.1 SparkChainConfig API

| **返回值类型**   | **方法说明**                                                 |
| ---------------- | ------------------------------------------------------------ |
| SparkChainConfig | public SparkChainConfig appID(String appID)  <br />设置用户的appID |
| SparkChainConfig | public SparkChainConfig apiKey(String apiKey)  <br />设置用户的apiKey |
| SparkChainConfig | public SparkChainConfig apiSecret(String apiSecret)  <br />设置用户的apiSecret |
| SparkChainConfig | public uid(String uid)  <br />设置用户自定义标识             |
| SparkChainConfig | public SparkChainConfig workDir(String workDir)  <br />设置SDK工作路径 |
| SparkChainConfig | public SparkChainConfig logLevel(int logLevel)  <br />设置日志等级 |
| SparkChainConfig | public SparkChainConfig logPath(String logPath)  <br />设置日志保存路径 |
| SparkChainConfig | public static SparkChainConfig builder()  <br />构建SparkChain实例 |

### 12.2 SparkChain API

| **返回值类型** | **方法说明**                                                 |
| -------------- | ------------------------------------------------------------ |
| SparkChain     | public static SparkChain getInst()  <br />获取SparkChain实例 |
| int            | public int init(Context context, SparkChainConfig config)  <br />SDK初始化 |
| int            | public int init(Context context)  <br />SDK初始化            |
| int            | public int unInit()  <br />SDK逆初始化                       |
| int            | public int getInitCode()  <br />获取SDK初始化结果码          |

### 12.3 RTASR API

| **返回值类型** | **方法说明**                                                 |
| -------------- | ------------------------------------------------------------ |
| int            | public int start(Object usrTag) <br />启动会话               |
| int            | public int write(byte[] data) <br />输入数据                 |
| int            | public int stop() <br />结束会话                             |
| void           | public void lang(String lang)  <br />设置识别的语种          |
| void           | public void transType(String transType)  <br />设置翻译类型  |
| void           | public void transStrategy(int transStrategy) <br />设置翻译策略 |
| void           | public void targetLang(String targetLang) <br />设置翻译方向的语种 |
| void           | public void punc(String punc) <br />标点过滤控制             |
| void           | public void pd(String pd) <br />垂直领域个性化参数           |
| void           | public void vadMdn(int vadMdn) <br />远近场切换              |
| void           | public void roleType(int roleType) <br />是否开角色分离      |
| void           | public void engLangType(int engLangType)  <br />语言识别模式 |
| void           | public void registerCallbacks(RTASRCallbacks cbs)<br />注册实时语音转写的结果监听回调 |

### 12.4 RTASRResult API

| 返回值类型    | 方法说明                                                     |
| ------------- | ------------------------------------------------------------ |
| String        | public String getRawResult() <br />云端返回的原始结果        |
| RtTransResult | public RtTransResult getTransResult() <br />获取翻译结果实例 |
| String        | public String getData() <br />获取识别结果                   |
| int           | public int getStatus() <br />获取数据状态                    |
| String        | public String getSid() <br />获取交互sid                     |

### 12.5 RTASRError API

| 返回值类型 | 方法说明                                     |
| ---------- | -------------------------------------------- |
| int        | public int getCode() <br />获取错误码        |
| String     | public String getErrMsg() <br />获取错误信息 |
| String     | public String getSid() <br />获取交互sid     |

### 12.6 RTASRTransResult API

| 返回值类型 | 方法说明                                      |
| ---------- | --------------------------------------------- |
| int        | public int getStatus() <br />获取翻译数据状态 |
| String     | public String getSrc() <br />获取翻译源文本   |
| String     | public String getDst() <br />获取翻译结果     |

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

备注：如出现下述列表中没有的错误码，可到 [这里](https://www.xfyun.cn/document/error-code) 查询。

| 错误码 | 描述                    | 说明                  | 处理方式                              |
| ------ | ----------------------- | --------------------- | ------------------------------------- |
| 0      | success                 | 成功                  |                                       |
| 10105  | illegal access          | 没有权限              | 检查apiKey，ip，ts等授权参数是否正确  |
| 10106  | invalid parameter       | 无效参数              | 上传必要的参数， 检查参数格式以及编码 |
| 10107  | illegal parameter       | 非法参数值            | 检查参数值是否超过范围或不符合要求    |
| 10110  | no license              | 无授权许可            | 检查参数值是否超过范围或不符合要求    |
| 10700  | engine error            | 引擎错误              | 提供接口返回值，向服务提供商反馈      |
| 10202  | websocket connect error | websocket连接错误     | 检查网络是否正常                      |
| 10204  | websocket write error   | 服务端websocket写错误 | 检查网络是否正常，向服务提供商反馈    |
| 10205  | websocket read error    | 服务端websocket读错误 | 检查网络是否正常，向服务提供商反馈    |
| 16003  | basic component error   | 基础组件异常          | 重试或向服务提供商反馈                |
| 10800  | over max connect limit  | 超过授权的连接数      | 确认连接数是否超过授权的连接数        |