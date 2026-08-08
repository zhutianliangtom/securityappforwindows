# SparkChain 录音文件转写大模型 Android SDK集成文档

## 1. 录音文件转写大模型简介

录音文件转写大模型（Long Form ASR）基于深度全序列卷积神经网络，将长段音频（5小时以内）数据转换成文本数据，为信息处理和数据挖掘提供基础。 转写的是已录制音频（非实时），音频文件上传成功后进入等待队列，待转写成功后用户即可获取结果，返回结果时间受音频时长以及排队任务量的影响。 如遇转写耗时比平时延长，大概率表示当前时间段出现转写高峰，请耐心等待即可，我们承诺有效任务耗时最大不超过5小时，详情请参考[SLA协议](https://www.xfyun.cn/doc/policy/SLA.html)。 另外，为使转写服务更加通畅，请尽量转写5分钟以上的音频文件，上传大量的短音频易引起网络和服务器资源紧张，从而导致任务排队积压。 音频时长与理论返回时间可以参考下表（请注意，实际返回时长受上传的音频时长和任务总量影响，忙时会出现任务排队情况）：

| 音频时长X（分钟） | 参考返回时间Y（分钟） |
| ----------------- | --------------------- |
| X<10              | Y<3                   |
| 10<=X<30          | 3<=Y<6                |
| 30<=X<60          | 6<=Y<10               |
| 60<=X             | 10<=Y<20              |

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

└── SparkChain 录音文件转写大模型 Android SDK集成文档.pdf     SparkChain集成指南

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

![](.\pic\Android录音文件转写大模型流程图.PNG)

## 6. SDK 初始化

**在使用SDK功能前，需要先开通录音文件转写大模型授权并获取已开通授权的应用信息（appId、apiKey、apiSecret）。SDK全局只需要初始化一次。**初始化时，开发者需要构建一个SparkChainConfig实例config，把相关的appid信息以及日志设置等传入config中，然后再通过SparkChain.getInst().init方法把config实例设置到SDK中。具体初始化示例如下：

```Java
//配置应用信息 
SparkChainConfig config =  SparkChainConfig.builder()    
    .appID("$appId")       
    .apiKey("$apiKey")    
    .apiSecret("$apiSecret"); 
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

## 7. 录音文件转写大模型初始化

在使用录音文件转写大模型功能前，需先通过其构造方法RAASR()方法构建其实例，然后用该实例调用相应的方法去设置转写参数。

录音文件转写大模型构造方法如下：

```Java
public class RAASR {
    public RAASR(String apiKey,RegionType regionType) {
        ...
    }
}
```

构造方法参数说明：

| 方法名 | 参数名     | 类型       | 说明                                                         |
| ------ | ---------- | ---------- | ------------------------------------------------------------ |
| RAASR  | apikey     | String     | apikey，用于建立链接时鉴权。可从[开放平台](https://console.xfyun.cn/services/lfasr)查看。<br />**注意，该值与SDK初始化时传入apiKey不同。** |
| RTASR  | regionType | RegionType | 实时转写类型，RegionType.CN_LLM_TYPE（实时语音转写大模型）<br/>**注意，设置为大模型转写时，不需要apikey， 设置为""即可** |

具体示例如下：

```Java
RAASR mRAASR = new RAASR("");//RegionType.CN_LLM_TYPE（录音文件转写大模型）
```

## 8. 功能参数配置

SDK支持用户根据自身需求，通过构建的RAASR实例访问相关方法配置转写参数。具体方法说明如下：

| 方法名         | 形参名         | 形参类型 | 必须 | 说明                                                         |
| -------------- | -------------- | -------- | ---- | ------------------------------------------------------------ |
| language       | language       | String   | 是   | 可选范围：<br/>autodialect：支持中英 + 202 种方言免切识别<br/>autominor：支持 37 个语种免切识别 （暂需联系人工对接） |
| duration       | duration       | String   | 是   | 音频时长，需与实际音频时长一致（单位：毫秒）                 |
| candidate      | candidate      | int      | 否   | 多候选开关 <br />0：关闭 (默认) 1：打开                      |
| roleType       | roleType       | int      | 否   | 是否开启角色分离<br/>0：不开启角色分离<br/>1：通用角色分离<br/>3：声纹角色分离（需要传递声纹标识）<br/>注：该字段只有在开通了 角色分离功能 的前提下才会生效。不传默认为0 |
| roleNum        | roleNum        | int      | 否   | 说话人数<br/>取值范围<br/>默认为 0 进行盲分<br/>注：该字段只有在开通了角色分离功能 的前提下才会生效，正确传入该参数后角色分离效果会有所提升 |
| pd             | pd             | String   | 否   | 领域个性化参数 <br />court：法律 <br />edu：教育 <br />finance：金融 <br />medical：医疗 <br />tech： 科技 <br />culture：人文历史 <br />isp：运营商 <br />sport：体育 <br />gov：政府 <br />game：游戏 <br />ecom：电商 <br />mil：军事 <br />com：企业 <br />life：生活 <br />ent：娱乐 <br />car：汽车 |
| callbackUrl    | callbackUrl    | String   | 否   | 订单完成时回调该地址通知完成 支持get请求，我们会在回调地址中拼接参 http://{ip}/{port}?xxx&OrderId=xxxx&status=1 参数： orderId 为订单号 status 为订单状态 1-转写识别成功 -1转写识别失败 长度限制512 |
| featureIds     | featureIds     | String   | 否   | *该字段需要通过[声纹注册接口 ](https://www.xfyun.cn/doc/spark/asr_llm/voice_print.html)先注册声纹*<br/>声纹id集合，只有当roleType传3时该值才有效<br/>多个用逗号分隔，最大支持64个声纹id<br/>"20250918XX...XXq2Eg,20250919XX...XXo00" |
| audioMode      | audioMode      | String   | 否   | fileStream： 文件流<br/>urlLink：音频url外链<br/>默认为fileStream |
| audioUrl       | audioUrl       | String   | 否   | 当audioMode为urlLink时该值必传， 如果url中包含特殊字符，audioUrl需要UrlEncode（不包含签名时需要的UrlEncode） 长度限制512 |
| eng_smoothproc | eng_smoothproc | boolean  | 否   | true：表示开启<br/>false：表示关闭<br/>默认为true            |
| eng_colloqproc | eng_colloqproc | boolean  | 否   | 口语规整是顺滑的升级版本 true：表示开启 false：表示关闭 默认为false 1.当eng_smoothproc为false，eng_colloqproc为false时只返回原始转写结果 2.当eng_smoothproc为true，eng_colloqproc为false时返回包含顺滑词的结果和原始结果 3. 当eng_smoothproc为true，eng_colloqproc为true时返回包含口语规整的结果和原始结果 4. 当eng_smoothproc为false，eng_colloqproc为true时返回包含口语规整的结果和原始结果 |
| eng_vad_mdn    | eng_vad_mdn    | int      | 否   | 1：远场模式 2：近场模式 默认为1                              |

具体配置示例如下：

```Java
mRAASR.setParams("language","autodialect");//autodialect:支持中英 +202 种方言免切识别autominor:支持 37 个语种免切识别(暂需联系人工对接)
mRAASR.setParams("duration","15000");//必须设置duration，要和音频的真实时长一致,单位ms
...
```

## 9. 注册结果监听回调

录音文件转写大模型运行结果通过RAASRCallbacks 异步返回，接口定义如下：

```Java
public interface RAASRCallbacks {    

   void onResult(RAASR.RaAsrResult result, Object usrTag);
   
   void onError(RAASR.RaAsrError error, Object usrTag);
}
```

RAASRCallbacks 数据结构说明：

- onResult为录音文件转写大模型结果回调方法，参数说明如下：

  | 参数   | 类型              | 说明                 |
  | ------ | ----------------- | -------------------- |
  | result | RAASR.RaAsrResult | 录音文件转写大模型结果实例 |
  | usrTag | Object            | 用户自定义标识       |

- RTASR.RtAsrResult结构说明：

  | 方法                  | 返回值类型               | 说明                                                         |
  | --------------------- | ------------------------ | ------------------------------------------------------------ |
  | getStatus()           | int                      | 订单流程状态 <br />0：订单已创建 <br />3：订单处理中 <br />4：订单已完成 <br />-1：订单失败 |
  | getOrderResult()      | String                   | 转写结果                                                     |
  | getTransResult()      | RAASR.RaAsrTransResult[] | 翻译结果实例                                                 |
  | getOrderId()          | String                   | 转写订单ID                                                   |
  | getOriginalDuration() | long                     | 原始音频时长，单位毫秒                                       |
  | getRealDuration()     | long                     | 真实音频时长，单位毫秒                                       |
  | getTaskEstimateTime() | int                      | 订单预估耗时，单位毫秒                                       |
  
- RAASR.RaAsrTransResult结构说明：

  | 方法       | 返回值类型   | 说明     |
  | ---------- | ------------ | -------- |
  | getSegId() | String       | 段落序号 |
  | getDst()   | String       | 翻译结果 |
  | getBg()    | int          | 开始时间 |
  | getEd()    | int          | 结束时间 |
  | getTags()  | List<String> | 标签     |
  | getRoles() | List<String> | 角色     |

- 通过getOrderResult()方法获取到的转写结果为云端下发的原始结果，SDK本身不解析此结果。开发者需自行解析原始结果(可参考demo中的解析步骤)。云端下发的json结果各字段含义如下：

1. orderResult结果字段：

   | 参数名   | 类型   | 描述                                                         |
   | -------- | ------ | ------------------------------------------------------------ |
   | lattice  | List   | 做顺滑功能的识别结果                                         |
   | lattice2 | List   | 未做顺滑功能的识别结果                                       |
   | label    | Object | 转写结果标签信息，用于补充转写结果相关信息，目前开启双通道转写时该对象会返回，标记转写结果角色和声道的对应关系 |

2. Lattice 字段：

   | 参数名     | 类型   | 描述                        |
   | ---------- | ------ | --------------------------- |
   | json_1best | String | 单个 vad 的结果的 json 内容 |

3. json_1best 字段：

   | 参数名 | 类型   | 描述               |
   | ------ | ------ | ------------------ |
   | st     | Object | 单个句子的结果对象 |

4. st 字段：

   | 参数名 | 类型   | 描述                                                         |
   | ------ | ------ | ------------------------------------------------------------ |
   | bg     | String | 单个句子的开始时间，单位毫秒                                 |
   | ed     | String | 单个句子的结束时间，单位毫秒                                 |
   | rl     | String | 分离的角色编号，取值正整数，需开启角色分离的功能才返回对应的分离角色编号 |
   | rt     | List   | 输出词语识别结果集合                                         |

5. ws 字段（词语候选识别结果）：

   | 参数名 | 类型 | 描述                                                         |
   | ------ | ---- | ------------------------------------------------------------ |
   | wb     | Long | 词语开始的帧数（注一帧 10ms），位置是相对 bg，仅支持中、英文语种 |
   | we     | Long | 词语结束的帧数（注一帧 10ms），位置是相对 bg，仅支持中、英文语种 |
   | cw     | List | 词语候选识别结果集合                                         |

6. cw 字段：

   | 参数名 | 类型   | 描述                                                         |
   | ------ | ------ | ------------------------------------------------------------ |
   | w      | String | 识别结果                                                     |
   | wp     | String | 词语的属性 n：正常词 s：顺滑 p：标点 g：分段（按此标识进行分段） |

7. label 字段：

   | 参数名   | 类型 | 描述                                                         |
   | -------- | ---- | ------------------------------------------------------------ |
   | rl_track | List | 双通道模式转写结果中角色和音频轨道对应信息，开启分轨模式该字段会返回 |

8. rl_track 字段：

   | 参数名 | 类型   | 描述                              |
   | ------ | ------ | --------------------------------- |
   | rl     | String | 分离的角色编号，取值正整数        |
   | track  | String | 音频轨道信息 L：左声道，R：右声道 |

- onError为录音文件转写大模型错误回调，参数说明如下：

  | 参数   | 类型             | 说明             |
  | ------ | ---------------- | ---------------- |
  | error  | RAASR.RaAsrError | 错误信息结果实例 |
  | usrTag | Object           | 用户自定义标识   |

- RAASR.RaAsrError结构说明：

  | 方法         | 返回值类型 | 说明       |
  | ------------ | ---------- | ---------- |
  | getCode()    | int        | 错误码     |
  | getErrMsg()  | String     | 错误信息   |
  | getOrderId() | String     | 转写订单ID |

具体示例如下：

```Java
RAASRCallbacks mRAASRCallbacks = new RAASRCallbacks() {
    @Override
    public void onResult(RAASR.RaAsrResult result, Object o) {
        int status                            = result.getStatus();//订单流程状态
        String orderResult                    = result.getOrderResult();//转写结果
        RAASR.RaAsrTransResult[] transResults = result.getTransResult();//翻译结果实例
        String orderId                        = result.getOrderId();//转写订单ID
        long originalDuration                 = result.getOriginalDuration();//原始音频时长，单位毫秒
        long realDuration                     = result.getRealDuration();//真实音频时长，单位毫秒
        int taskEstimateTime                  = result.getTaskEstimateTime();//订单预估耗时，单位毫秒
    }

    @Override
    public void onError(RAASR.RaAsrError raAsrError, Object o) {
        String errMsg  = raAsrError.getErrMsg();//错误信息
        int errCode    = raAsrError.getCode();//错误码
        String orderId = raAsrError.getOrderId();//转写订单ID
    }
};
mRAASR.registerCallbacks(mRAASRCallbacks);
```

## 10. 请求调用

开发者注册完监听回调后，可通过mRAASR.uploadAsync()方法开启会话。请求调用接口如下：

```Java
public class RAASR {
    public int uploadAsync(String fileName, String requestId,Object usrTag) {        
        ...
    }
}
```

uploadAsync方法结构说明：

| 参数      | 类型   | 说明                                                         |
| --------- | ------ | ------------------------------------------------------------ |
| fileName  | String | 音频文件名称，最好携带音频真实的后缀名，避免影响转码         |
| requestId | String | 请求ID，主要给云端使用，用户层暂时不会用到此参数，但是要确保每次请求的时候唯一 |
| usrTag    | Object | 用户自定义标识                                               |

具体示例如下：

```Java
String filePath = "/sdcard/iflytek/asr/cn_test.pcm";
requestId = "第"+count+"次请求";//客户端用于标记任务的唯一id，最大长度64字符，由客户端保证唯一性，服务回调结果时会会包含此参数
mRAASR.uploadAsync(audioPath,requestId,"UPLOAD");
```

## 11. 结果查询

开发者调用uploadAsync方法后，可通过getResultOnceAsync方法查询转写结果。查询方法结构如下：

```Java
public class RAASR {
    public int getResultOnceAsync(String orderId,Object usrTag) {        
        ...
    }
}
```

getResultOnceAsync方法结构说明：

| 参数    | 类型   | 说明           |
| ------- | ------ | -------------- |
| orderId | String | 转写订单ID     |
| usrTag  | Object | 用户自定义标识 |

具体示例如下：

```Java
String resultType = "transfer";
mRAASR.resultType(resultType);
mRAASR.getResultOnceAsync(orderId,"12345");
```

## 12. 转写语种支持

| 语种名称 | 语种编码     |
| -------- | ------------ |
| 中文     | cn           |
| 英文     | en           |
| 日语     | ja           |
| 韩语     | ko           |
| 俄语     | ru           |
| 法语     | fr           |
| 西班牙语 | es           |
| 越南语   | vi           |
| 粤语     | cn_cantonese |
| 维吾尔语 | cn_uyghur    |
| 藏语     | cn_tibetan   |
| 阿拉伯语 | ar           |
| 德语     | de           |
| 意大利语 | it           |

## 13. 停止上传音频

uploadAsync上传音频过程中，可通过该方法进行打断，示例代码如下：

```java
int ret = mRAASR.stop();
```

## 14. 逆初始化

当SDK需要完整退出时，需调用逆初始化方法释放资源，示例代码如下：

```Java
SparkChain.getInst().unInit();  //SDK逆初始化
```

## 15. SDK API介绍

### 15.1 SparkChainConfig API

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

### 15.2 SparkChain API

| **返回值类型** | **方法说明**                                                 |
| -------------- | ------------------------------------------------------------ |
| SparkChain     | public static SparkChain getInst()  <br />获取SparkChain实例 |
| int            | public int init(Context context, SparkChainConfig config)  <br />SDK初始化 |
| int            | public int init(Context context)  <br />SDK初始化            |
| int            | public int unInit()  <br />SDK逆初始化                       |
| int            | public int getInitCode()  <br />获取SDK初始化结果码          |

### 15.3 RAASR API

| **返回值类型** | **方法说明**                                                 |
| -------------- | ------------------------------------------------------------ |
| int            | public int uploadAsync(String fileName,Object usrTag)<br />请求调用 |
| int            | public int getResultOnceAsync(String orderId,String resultType,Object usrTag)<br />结果查询 |
| void           | public void language(String language)<br />设置识别语种      |
| void           | public void hotWord(String hotWord)<br />热词，用以提升专业词汇的识别率格式：热词1\| 热词2\| 热词3 |
| void           | public void candidate(int candidate)<br />多候选开关         |
| void           | public void roleType(int roleType)<br />是否开启角色分离     |
| void           | public void roleNum(int roleNum)<br />说话人数               |
| void           | public void pd(String pd)<br />领域个性化参数                |
| void           | public void audioMode(String audioMode)<br />转写音频上传方式 |
| void           | public void audioUrl(String audioUrl)<br />音频url外链地址 当audioMode为urlLink时该值必传； |
| void           | public void standardWav(int standardWav)<br />是否标准pcm/wav(16k/16bit/单声道) |
| void           | public void languageType(int languageType)<br />语言识别模式选择 |
| void           | public void trackMode(int trackMode)<br />按声道分轨转写模式 |
| void           | public void transLanguage(String transLanguage)<br />需要翻译的语种(转写语种和翻译语种不能相同) |
| void           | public void transMode(int transMode)<br />翻译模式           |
| void           | public void engSegMax(int engSegMax)<br />控制分段的最大字数 |
| void           | public void engSegMin(int engSegMin)<br />控制分段的最小字数 |
| void           | public void engSegWeight(float engSegWeight)<br />控制分段字数的权重 |
| void           | public void engSmoothproc(boolean engSmoothproc)<br />顺滑开关 |
| void           | public void engColloqproc(boolean engColloqproc)<br />口语规整开关 |
| void           | public void engVadMdn(int engVadMdn)<br />远近场模式         |
| void           | public void engVadMargin(int engVadMargin)<br />首尾是否带静音信息 |
| void           | public void engRlang(int engRlang)<br />针对粤语转写后的字体转换 |
| void           | public void registerCallbacks(RAASRCallbacks cbs)<br />注册监听回调 |
| int            | public int stop()<br />中断音频上传                          |
| void           | public void resultType(String resultType) <br />设置结果类型 |

### 15.4 RTASRResult API

| 返回值类型         | 方法说明                                                     |
| ------------------ | ------------------------------------------------------------ |
| int                | public int getStatus() <br />订单流程状态                    |
| String             | public String getOrderResult() <br />转写结果                |
| RaAsrTransResult[] | public RaAsrTransResult[] getTransResult() <br />翻译结果实例 |
| String             | public String getOrderId() <br />获取订单号                  |
| long               | public long getOriginalDuration()<br />原始音频时长          |
| long               | public long getRealDuration()<br />真实音频时长              |
| int                | public int getTaskEstimateTime()<br />订单预估耗时           |

### 15.5 RTASRError API

| 返回值类型 | 方法说明                                        |
| ---------- | ----------------------------------------------- |
| int        | public int getCode() <br />获取错误码           |
| String     | public String getErrMsg() <br />获取错误信息    |
| String     | public String getOrderId() <br />获取转写订单ID |

### 15.6 RAASRTransResult API

| 返回值类型 | 方法说明                                  |
| ---------- | ----------------------------------------- |
| int        | public String getSegId()<br />段落序号    |
| int        | public int getBg() <br />获取开始时间     |
| int        | public int getEd()<br />获取结束时间      |
| String     | public String getDst() <br />获取翻译结果 |
| String[]   | public String[] getTags()<br />获取标签   |
| String[]   | public String[] getRoles()<br />获取角色  |

## 16. 错误码

错误码包含SDK错误码和云端错误码。

### 16.1 SDK错误码

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

### 16.2 部分云端错误码

| 错误码 | 描述                                         |
| ------ | -------------------------------------------- |
| 100001 | 订单不存在或状态异常                         |
| 100002 | 订单音频未上传                               |
| 100003 | 参数错误                                     |
| 100004 | 查询订单错误                                 |
| 100005 | 查询音频为空                                 |
| 100006 | 上传音频异常                                 |
| 100007 | 权限错误                                     |
| 100008 | 签名异常-请求时间超过限制                    |
| 100009 | 签名校验不通过                               |
| 100012 | 请求超过频率限制                             |
| 100013 | 订单未完成                                   |
| 100015 | 热词必须是中文                               |
| 100016 | 热词超出长度限制                             |
| 100017 | 热词超出数量限制                             |
| 100018 | 热词分隔符不能连续出现                       |
| 100019 | 热词验证失败                                 |
| 100020 | 语言验证失败                                 |
| 100021 | 热词上传失败                                 |
| 100022 | 热词不断重复                                 |
| 100023 | 热词保存失败                                 |
| 100024 | 热词为空                                     |
| 100025 | 热词 ID 未知                                 |
| 100026 | 时间格式必须为：yy-MM-dd                     |
| 100027 | patch ID 未知                                |
| 100028 | Patch 验证失败                               |
| 100029 | 文件已存在                                   |
| 100030 | 未知的文件格式                               |
| 100031 | 多候选 ID 未知                               |
| 100032 | 多候选验证失败                               |
| 100033 | 无效的角色分离个数，角色分离个数范围：[0-10] |
| 100034 | 更改 AccesskeySecret 失败                    |
| 100037 | 非法的订单号                                 |
| 100038 | 删除订单验证失败                             |
| 100039 | 订单为空                                     |
| 100040 | 订单个数超出限制                             |
| 100042 | 外链地址无效                                 |
| 100041 | 切换通道失败                                 |
| 100043 | 通道类型验证失败                             |
| 100044 | 通道类型不存在                               |