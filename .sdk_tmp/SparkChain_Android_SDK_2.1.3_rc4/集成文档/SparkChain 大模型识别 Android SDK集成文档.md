# SparkChain 大模型识别 Android SDK集成文档

## 1. 大模型识别简介

SparkChain支持开发者通过SDK进行大模型识别。开发者仅需往对应的接口中送入音频数据，则可以从监听回调中获取识别结果。大模型识别对比常规的语音识别，识别效果更好。并且当开发者如果有方言识别的需求，大模型识别可以不用切换方言参数，简化了开发者的代码逻辑。

## 2. 兼容性说明

| 类别     | 兼容范围                                        |
| :------- | :---------------------------------------------- |
| 系统     | 支持armv7和armv8架构，兼容android 5.0及以上版本 |
| 开发环境 | 建议使用Android Studio 进行开发                 |

## 3. SDK集成包目录结构

将SDK zip包解压缩，得到如下文件：

├── Demo SparkChain的使用DEMO，DEMO中已经集成了SDK，您可以参考DEMO，集成SDK。集成前，请先测通DEMO，了解调用原理。

├── ReleaseNotes.txt SDK版本日志

├── SDK SparkChain SDK

│ └── SparkChain.aar

└── SparkChain 大模型识别 Android SDK集成文档.pdf SparkChain集成指南

## 4. SDK工程配置

### 4.1 导入SDK库

复制SparkChain.aar到项目的libs目录下，然后在主Module的build.gradle文件中，增加如下配置：

```java
dependencies { 
    implementation files('libs/SparkChain.aar')    
}
```

### 4.2 配置权限

外部使用时需要配置以下权限：

| 权限                    | 使用说明                                                     |
| :---------------------- | :----------------------------------------------------------- |
| INTERNET                | 必须权限，SDK需要访问网络获取结果。                          |
| READ_EXTERNAL_STORAGE   | 必须权限，SDK需要判断日志路径是否存在。                      |
| WRITE_EXTERNAL_STORAGE  | 必须权限，SDK写本地日志需要用到该权限。                      |
| MANAGE_EXTERNAL_STORAGE | 可选权限，安卓10以上设备用于动态授权弹出授权框需要用到该权限，安卓10以上设备必选。 |

Android 10.0（API 29）及以上版本需要在application中做如下配置

```java
<application android:requestLegacyExternalStorage="true"/>
```

### 4.3 混淆配置

SparkChain SDK 已做过混淆，如果您项目中也使用了混淆，请在 proguard-rules.pro文件中添加如下配置保持SparkChain SDK 不再被混淆。

```java
-keep class com.iflytek.sparkchain.** {*;} 
-keep class com.iflytek.sparkchain.**
```

## 5. 接口流程调用图

![](.\pic\Android大模型识别流程图.png)

## 6. SDK初始化

**在使用SDK功能前，需要先开通星火大模型授权并获取已开通授权的应用信息（appId、apiKey、apiSecret）。SDK全局只需要初始化一次。**初始化时，开发者需要构建一个SparkChainConfig实例config，把相关的appid信息以及日志设置等传入config中，然后再通过SparkChain.getInst().init方法把config实例设置到SDK中。具体初始化示例如下：

```java
//配置应用信息 
SparkChainConfig config =  SparkChainConfig.builder()        
    .appID("$appId")        
    .apiKey("$apiKey")        
    .apiSecret("$apiSecret"); 
int ret = SparkChain.getInst().init(getApplicationContext(), config); 
```

初始化参数说明：

| 接口名称  | 含义                                                         | 参数类型 | 限制                                                         | 是否必填 |
| :-------- | :----------------------------------------------------------- | :------- | :----------------------------------------------------------- | :------- |
| appID     | 创建应用后，生成的应用ID                                     | String   | 与平台生成的appID完全一致                                    | 是       |
| apiKey    | 创建应用后，生成的唯一应用标识                               | String   | 与平台生成的apiKey完全一致                                   | 是       |
| apiSecret | 创建应用后，生成的唯一应用秘钥                               | String   | 与平台生成的apiSecret完全一致                                | 是       |
| logLevel  | 日志等级                                                     | int      | 枚举，0：VERBOSE，1：DEBUG，2：INFO，3：WARN，4：ERROR，5：FATAL，100：OFF | 否       |
| logPath   | 日志存储路径(具体指定到文件名，如"/sdcard/iflytek/sparkchain.log")，设置则会把日志存在该路径下，不设置则会把日志打印在终端上。 | String   | 设置的路径需要有读写权限                                     | 否       |
| uid       | 用户自定义标识                                               | String   |                                                              | 否       |

初始化返回值：0：初始化成功，非0：初始化失败，请根据具体返回值参考错误码章节。

## 7. 大模型识别初始化

在使用大模型识别功能前，需先通过其构造方法ASR()方法构建其实例，然后用该实例调用相应的方法去设置识别参数。

大模型识别构造方法如下：

```java
public class ASR {    
    public ASR() {            
    
    }
    
    public ASR(String language, String domain, String accent) {        
        ...    
    } 
}
```

构造方法参数说明：

| 类型             | 说明                                       |
| ---------------- | ------------------------------------------ |
| 中英识别大模型   | language=zh_cn;domain=slm;accent=mandarin  |
| 多语种识别大模型 | language=mul_cn;domain=slm;accent=mandarin |

具体示例如下：

```java
ASR asr = new ASR("mul_cn","slm","mandarin");
//ASR asr = new ASR();//缺省参数调用方式
```

## 8. 功能参数配置

SDK支持用户根据自身需求，通过构建的asr实例访问相关方法配置识别参数。中文语音大模型和听写多语种大模型所支持的功能不同，具体方法说明如下。

### 8.1 中英识别大模型

| 方法名   | 形参名   | 形参类型 | 说明                                                         | 是否必填                                             | 默认值 |
| -------- | -------- | -------- | ------------------------------------------------------------ | ---------------------------------------------------- | ------ |
| language | language | String   | 识别语种。<br />zh_cn：中文                                  | 如果通过构造方法传入，则这里可不用配置，否则必须设置 |        |
| domain   | domain   | String   | 应用领域。<br/>slm:大模型识别                                | 如果通过构造方法传入，则这里可不用配置，否则必须设置 |        |
| accent   | accent   | String   | 方言。<br/>mandarin：中文普通话、其他语种                    | 如果通过构造方法传入，则这里可不用配置，否则必须设置 |        |
| vadEos   | vadEos   | int      | 尾静音截断：引擎判定结束的时间，连续检测给定时间长度的音频，均为静音，则引擎停止识别，单位是毫秒。最小值:600，最大值:60000 | 否                                                   | 600    |
| ltc      | ltc      | int      | 是否进行中英文筛选，默认：1，不进行筛选 2，只出中文 3，只出英文 | 否                                                   | 1      |
| vinfo    | vinfo    | boolean  | 句子级别帧对齐:给出一次会话中，子句的vad边界信息。<br />false:不返回vad信息<br />true:返回vad信息 | 否                                                   | false  |
| dwa      | dwa      | String   | 流式识别PGS：流式识别功能，打开后，会话过程中实时给出语音识别的结果，而不是子句结束时才给结果。<br />wpgs：开启流式结果返回功能。 | 否                                                   |        |
| dhw      | dhw      | string   | 会话热词，支持utf-8和gb2312； 取值样例：“dhw=gb2312;你好\|大家”（对应gb2312编码）；“dhw=utf-8;你好\|大家”（对应utf-8编码） 最小长度:0, 最大长度:1024 | 否                                                   |        |

### 8.2 多语种识别大模型

| 方法名   | 参数名   | 参数类型 | 说明                                                         | 是否必填                                             | 默认值 |
| -------- | -------- | -------- | ------------------------------------------------------------ | ---------------------------------------------------- | ------ |
| language | language | String   | 识别语种。<br />mul_cn：中文                                 | 如果通过构造方法传入，则这里可不用配置，否则必须设置 |        |
| domain   | domain   | String   | 应用领域。<br/>slm:大模型识别                                | 如果通过构造方法传入，则这里可不用配置，否则必须设置 |        |
| accent   | accent   | String   | 方言。<br/>mandarin：中文普通话、其他语种                    | 如果通过构造方法传入，则这里可不用配置，否则必须设置 |        |
| vadEos   | vadEos   | int      | 尾静音截断：引擎判定结束的时间，连续检测给定时间长度的音频，均为静音，则引擎停止识别，单位是毫秒。最小值:600，最大值:60000 | 否                                                   | 600    |
| vinfo    | vinfo    | boolean  | 句子级别帧对齐:给出一次会话中，子句的vad边界信息。<br />false:不返回vad信息<br />true:返回vad信息 | 否                                                   | false  |
| ln       | ln       | String   | 语种参数：支持两种模式，指定语种模式和免切模式<br/>指定语种，比如当前会话是英文那么传参 ln=en<br/>免切模式，不需要指定语种参数或传参ln=none 引擎将自动识别语种 | 否                                                   | none   |

语种参数详细说明:

引擎支持的语音识别功能语种列表及ln传参说明

**1、指定语种模式**，需要端侧给服务传带识别语音的语种，字段为ln，比如当前会话是英文，那么语种参数是"en"，详细见下面对外ID。

**2、免切模式**，不需要指定语种参数或者ln字段传参数"none"，识别引擎将自动识别语种。

| 对外ID | 语种       |
| :----- | :--------- |
| zh     | 中文       |
| en     | 英文       |
| ja     | 日语       |
| ko     | 韩语       |
| ru     | 俄语       |
| fr     | 法语       |
| es     | 西班牙语   |
| ar     | 阿拉伯语   |
| de     | 德语       |
| th     | 泰语       |
| vi     | 越南语     |
| hi     | 印地语     |
| pt     | 葡萄牙语   |
| it     | 意大利语   |
| ms     | 马来语     |
| id     | 印尼语     |
| fil    | 菲律宾语   |
| tr     | 土耳其语   |
| el     | 希腊语     |
| cs     | 捷克语     |
| ur     | 乌尔都语   |
| bn     | 孟加拉语   |
| ta     | 泰米尔语   |
| uk     | 乌克兰语   |
| kk     | 哈萨克语   |
| uz     | 乌兹别克语 |
| pl     | 波兰语     |
| mn     | 蒙语       |
| sw     | 斯瓦西里语 |
| ha     | 豪撒语     |
| fa     | 波斯语     |
| nl     | 荷兰语     |
| sv     | 瑞典语     |
| ro     | 罗马尼亚语 |
| bg     | 保加利亚语 |
| ug     | 维语       |
| tib    | 藏语       |

配置功能参数具体示例如下：

```java
asr.language("mul_cn");
asr.accent("mandarin");
...
asr.domain("slm");
asr.vinfo(true);
```

## 9. 注册结果监听回调

大模型识别结果通过AsrCallbacks监听回调异步返回，监听回调接口如下：

```java
public interface AsrCallbacks {    
    void onResult(ASR.ASRResult asrResult, Object usrContext);     
    void onError(ASR.ASRError asrError, Object usrContext); 
}
```

AsrCallbacks数据结构说明：

- onResult为识别结果回调方法，参数说明如下：

  | 参数       | 类型          | 说明           |
  | :--------- | :------------ | :------------- |
  | asrResult  | ASR.ASRResult | 识别结果结构体 |
  | usrContext | Object        | 用户自定义标识 |

- ASR.ASRResult结构说明：

  | 方法                | 返回值类型          | 说明                                                         |
  | :------------------ | :------------------ | :----------------------------------------------------------- |
  | getBestMatchText()  | String              | 识别结果返回接口，开发者可通过此方法快速获取识别结果。       |
  | getStatus()         | int                 | 识别结果返回进度，0：开始，1：中间，2：结束                  |
  | getSid()            | String              | 本次交互的sid                                                |
  | getVads()           | List<Vad>           | vad结果结构体，里面包含本次交互的vad信息                     |
  | getTranscriptions() | List<Transcription> | 识别结果结构体，里面包含具体识别结果信息，一般无特殊需求，识别结果从getBestMatchText方法获取。 |

- Vad结构体说明：

  | 方法       | 返回值类型 | 说明                                     |
  | :--------- | :--------- | :--------------------------------------- |
  | getBegin() | int        | 起始的端点帧偏移值，单位：帧（1帧=10ms） |
  | getEnd()   | int        | 结束的端点帧偏移值，单位：帧（1帧=10ms） |

- Transcription结构体说明：

  | 方法          | 返回值类型    | 说明                                                         |
  | :------------ | :------------ | :----------------------------------------------------------- |
  | getIndex()    | int           | 起始的端点帧偏移值，单位：帧（1帧=10ms） <br />注：以下两种情况下bg=0，无参考意义： <br />1)返回结果为标点符号或者为空； <br />2)本次返回结果过长。 |
  | getSegments() | List<Segment> | 中文分词结构体                                               |

- Segment结构体说明：

  | 方法       | 返回值类型 | 说明                                 |
  | :--------- | :--------- | :----------------------------------- |
  | getText()  | String     | 字词                                 |
  | getLg()    | String     | 获得识别语种(仅听写多语种大模型生效) |
  | getScore() | int        | 得分，当前未实现，保留字段           |

- onError为识别错误回调方法，参数说明如下：

  | 参数       | 类型         | 说明           |
  | :--------- | :----------- | :------------- |
  | asrError   | ASR.ASRError | 错误信息结构体 |
  | usrContext | Object       | 用户自定义标识 |

- ASR.ASRError结构说明

  | 方法        | 返回值类型 | 说明          |
  | :---------- | :--------- | :------------ |
  | getErrMsg() | String     | 错误信息      |
  | getCode()   | int        | 错误码        |
  | getSid()    | String     | 本次交互的sid |

具体示例如下：

```java
AsrCallbacks mAsrCallbacks = new AsrCallbacks() { 
    @Override    
    public void onResult(ASR.ASRResult asrResult, Object o) {    	
        int vad_begin  = -1;        
        int vad_end    = -1;        
        String word    = null;    
        String lg      = null;
        String result  = asrResult.getBestMatchText();//解析识别结果        
        int status     = asrResult.getStatus();//解析结果返回状态        
        String sid     = asrResult.getSid();//解析sid        
        //以下信息需要开发者根据自身需求，如无必要，可不需要解析执行。        
        List<Vad> vads = asrResult.getVads();//解析vad结构体                     
        for(Vad vad:vads){        	
            vad_begin = vad.getBegin();//解析vad前端点            
            vad_end   = vad.getEnd();//解析vad后端点            
        }        
        List<Transcription> transcriptions = asrResult.getTranscriptions();//解析具体结果信息           
        for(Transcription transcription : transcriptions){            
            List<Segment> segments = transcription.getSegments();//解析中文分词结构体            
            for(Segment segment:segments){                
                word = segment.getText();//解析词语
                lg   = segment.getLg();  //识别语种，仅听写多语种大模型生效
            }        
        } 
    }    
    @Override    
    public void onError(ASR.ASRError asrError, Object o) {    	
        int errCode   = asrError.getCode();//错误码        
        String errMsg = asrError.getErrMsg();//错误信息        
        String sid    = asrError.getSid();//本次交互的sid    
    } 
}; 
asr.registerCallbacks(mAsrCallbacks);
```

## 10. 启动会话

开发者进行交互前，需通过asr.start()方法先启动会话。调用接口如下：

```java
public class AudioAttributes { 
    public AudioAttributes() {            
    
    }         
    public void setSampleRate(int mSampleRate) {        
        ...    
    }     
    public void setEncoding(String mEncoding) {        
        ...    
    }
    public void setChannels(int channels) {
        ... 
    }
    public void setBitdepth(int bitdepth) {
        ... 
    }
    public void setFrameSize(int frameSize) {
        ...
    }
} 
public class ASR {    
    public int start(Object usrTag) {        
        ...    
    }     
    public int start(AudioAttributes attributes, Object usrTag) {        
        ...    
    } 
}
```

- start方法参数说明：

  | 参数名     | 类型            | 说明               | 是否必填 | 默认值     |
  | :--------- | :-------------- | :----------------- | :------- | :--------- |
  | attributes | AudioAttributes | 输入数据格式结构体 | 否       | attributes |
  | usrTag     | Object          | 用户自定义标识     | 否       | nullptr    |

- AudioAttributes结构说明：

  | 方法名        | 返回值类型 | 参数名      | 参数类型 | 说明                                                         |
  | ------------- | ---------- | ----------- | -------- | ------------------------------------------------------------ |
  | setSampleRate | void       | mSampleRate | int      | 输入音频的采样率，支持8k和16k                                |
  | setEncoding   | void       | mEncoding   | String   | 输入音频的编码格式<br />raw：原生音频（支持单声道的pcm）<br/>speex：speex压缩后的音频（8k）<br/>speex-wb：speex压缩后的音频（16k）<br/>请注意压缩前也必须是采样率16k或8k单声道的pcm。<br/>lame：mp3格式（仅中文普通话和英文支持，方言及小语种暂不支持） |
  | setChannels   | void       | channels    | int      | 输入音频的声道<br />1:单声道(默认)<br />2:双声道             |
  | setBitdepth   | void       | bitdepth    | int      | 位深<br />8:8bit<br />16:16bit(默认)                         |
  | setFrameSize  | void       | frameSize   | int      | 帧大小<br />最小值:0, 最大值:1024                            |

具体示例如下：

```java
asr.start();
//带有数据信息结构体的构建方式示例如下：
//AudioAttributes atr = new AudioAttributes();
//atr.setSampleRate(16000);
//atr.setEncoding("raw");
//atr.setChannels(1);
//asr.start(atr, null);
```

## 11. 送入数据

启动会话后，开发者可通过asr.write()方法送入要识别的音频，然后异步从监听回调中获取识别结果。write方法调用接口如下：

```java
public class ASR {    
    public int write(byte[] data) {        
        ...    
    } 
}
```

write方法参数说明：

| 参数 | 类型   | 说明     |
| :--- | :----- | :------- |
| data | byte[] | 识别数据 |

发送数据时，如果间隔时间太短，可能会导致引擎识别有误。建议每次发送音频间隔40ms，每次发送音频字节数为一帧音频大小的整数倍。

请注意不同音频格式一帧大小的字节数不同，我们建议：

1. 未压缩的PCM格式，每次发送音频间隔40ms，每次发送音频字节数1280B；
2. 讯飞定制speex格式，每次发送音频间隔40ms，假如16k的压缩等级为7，则每次发送61B的整数倍；
3. 标准开源speex格式，每次发送音频间隔40ms，假如16k的压缩等级为7，则每次发送60B的整数倍；

| 讯飞定制speex（压缩等级） | 0    | 1    | 2    | 3    | 4    | 5    | 6    | 7    | 8    | 9    | 10   |
| :------------------------ | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| speex 8k                  | 7    | 11   | 16   | 21   | 21   | 29   | 29   | 39   | 39   | 47   | 63   |
| speex-wb 16k              | 11   | 16   | 21   | 26   | 33   | 43   | 53   | 61   | 71   | 87   | 107  |

| 标准开源speex（压缩等级） | 0    | 1    | 2    | 3    | 4    | 5    | 6    | 7    | 8    | 9    | 10   |
| :------------------------ | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| speex 8k                  | 6    | 10   | 15   | 20   | 20   | 28   | 28   | 38   | 38   | 46   | 62   |
| speex-wb 16k              | 10   | 15   | 20   | 25   | 32   | 42   | 52   | 60   | 70   | 86   | 106  |

整个会话时长最多持续60s，或者超过10s未发送数据，服务端会主动断开连接。

注意：针对用户传参，识别服务如何识别传入的音频是讯飞定制speex格式还是标准开源speex格式音频？

```java
通过是否传入speex_size（speex音频帧长，仅在speex音频时使用）参数来区分 
1、当传入speex_size参数时，会当成标准开源格式进行处理 
2、当未传入speex_size参数时，会当成讯飞定制格式进行处理
```

具体示例如下：

```java
byte[] data = new byte[1280]; 
...//省略获取音频的过程 
asr.write(data);
```

## 12. 停止会话

当开发者送完数据后，需要调用asr.stop()方法通知SDK层数据已传完。之后云端则会下发最终的识别结果，然后结束本轮交互。stop方法调用接口如下：

```java
public class ASR {    
    public int stop(boolean immediate) {        
        ...    
    } 
}
```

stop方法参数说明：

| 参数      | 类型    | 说明                                                         |
| :-------- | :------ | :----------------------------------------------------------- |
| immediate | boolean | true：调用stop后，SDK不管后续云端结果，立即结束。 false：调用stop后，SDK会等云端发送完最终结果后再结束。 |

具体示例如下：

```java
asr.stop(false);
```

如果不需要继续使用SDK，需要执行逆初始化释放资源。具体参考逆初始化章节。

## 13. 逆初始化

当SDK需要完整退出时，需调用逆初始化方法释放资源，示例代码如下：

```java
SparkChain.getInst().unInit();
```

## 14. SDK API介绍

### 14.1 SparkChainConfig API

| 返回值类型       | 方法说明                                                     |
| :--------------- | :----------------------------------------------------------- |
| SparkChainConfig | public SparkChainConfig appID(String appID) <br />设置用户的appID |
| SparkChainConfig | public SparkChainConfig apiKey(String apiKey) <br />设置用户的apiKey |
| SparkChainConfig | public SparkChainConfig apiSecret(String apiSecret) <br />设置用户的apiSecret |
| SparkChainConfig | public uid(String uid) <br />设置用户自定义标识              |
| SparkChainConfig | public SparkChainConfig workDir(String workDir) <br />设置SDK工作路径 |
| SparkChainConfig | public SparkChainConfig logLevel(int logLevel) <br />设置日志等级 |
| SparkChainConfig | public SparkChainConfig logPath(String logPath) <br />设置日志保存路径 |
| SparkChainConfig | public static SparkChainConfig builder() <br />构建SparkChain实例 |

### 14.2 SparkChain API

| 返回值类型 | 方法说明                                                     |
| :--------- | :----------------------------------------------------------- |
| SparkChain | public static SparkChain getInst() <br />获取SparkChain实例  |
| int        | public int init(Context context, SparkChainConfig config) <br />SDK初始化 |
| int        | public int init(Context context) <br />SDK初始化             |
| int        | public int unInit() <br />SDK逆初始化                        |
| int        | public int getInitCode() <br />获取SDK初始化结果码           |

### 14.3 ASR API

| 返回值类型 | 方法说明                                                     |
| :--------- | :----------------------------------------------------------- |
| void       | public void registerCallbacks(AsrCallbacks cbs) <br />注册大模型识别的结果监听回调 |
| void       | public void language(String language) <br />设置大模型识别的语种 |
| void       | public void domain(String domain) <br />设置大模型识别的应用领域 |
| void       | public void accent(String accent) <br />设置大模型识别的方言 |
| void       | public void vadEos(int vadEos)  <br />用于设置端点检测的静默时间，单位是毫秒 |
| void       | public void dwa(String dwa)  <br />（仅中文普通话支持）动态修正 |
| void       | public void pd(String pd) (仅中文支持）<br />领域个性化参数  |
| void       | public void ptt(boolean enable) <br />（仅中文支持）是否开启标点符号添加 |
| void       | public void rlang(String rlang)  <br />（仅中文支持）字体    |
| void       | public void vinfo(boolean vinfo) <br />返回子句结果对应的起始和结束的端点帧偏移值。 |
| void       | public void nunum(boolean enable)  <br />（中文普通话和日语支持）将返回结果的数字格式规则为阿拉伯数字格式，默认开启 |
| void       | public void speexSize(int speexSize)  <br />speex音频帧长，仅在speex音频时使用 |
| void       | public void nbest(int nbest) <br />通过设置此参数，获取在发音相似时的句子多侯选结果。设置多候选会影响性能，响应时间延迟200ms左右。 |
| void       | public void wbest(int wbest) <br />通过设置此参数，获取在发音相似时的词语多侯选结果。设置多候选会影响性能，响应时间延迟200ms左右。 |
| int        | public int start(Object usrTag) <br />启动会话               |
| int        | public int start(AudioAttributes attributes, Object usrTag) <br />带有音频约束条件的启动会话 |
| int        | public int write(byte[] data) <br />输入数据                 |
| int        | public int stop(boolean immediate) <br />停止或者取消接口    |

### 14.4 ASRResult API

| 返回值类型          | 方法说明                                                     |
| :------------------ | :----------------------------------------------------------- |
| String              | public String getBestMatchText() <br />获取识别结果          |
| int                 | public int getStatus() <br />获取识别结果状态                |
| String              | public String getSid() <br />获取本次交互的sid               |
| List<Transcription> | public List<Transcription> getTranscriptions() <br />获取详细信息的识别结果 |
| List<Vad>           | public List<Vad> getVads() <br />获取vad结果                 |

### 14.5 ASRError API

| 返回值类型 | 方法说明                                       |
| :--------- | :--------------------------------------------- |
| String     | public String getErrMsg() <br />获取错误信息   |
| int        | public int getCode() <br />获取错误码          |
| String     | public String getSid() <br />获取本次交互的sid |

### 14.6 ASR AudioAttributes API

| 返回值类型 | 方法说明                                                     |
| :--------- | :----------------------------------------------------------- |
| void       | public void setSampleRate(int mSampleRate)  <br />设置输入音频的采样率 |
| void       | public void setEncoding(String mEncoding) <br />设置输入音频的编码格式 |
| void       | public void setChannels(int channels) <br />设置输入音频的声道 |
| void       | public void setBitdepth(int bitdepth)<br />设置位深          |
| void       | public void setFrameSize(int frameSize)<br />设置帧大小      |

## 15. 错误码

错误码包含SDK错误码和云端错误码。

### 15.1 SDK错误码

| 错误码 | 含义                                        | 自查指南                                                     |
| :----- | :------------------------------------------ | :----------------------------------------------------------- |
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

### 15.2 云端错误码

备注：如出现下述列表中没有的错误码，可到 [这里](https://www.xfyun.cn/document/error-code) 查询。

| 错误码        | 错误描述                                                | 说明                                         | 处理方式                                                     |
| ------------- | ------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------ |
| 10005         | licc fail                                               | appid授权失败                                | 确认appid是否正确，是否开通了听写服务                        |
| 10006         | Get audio rate fail                                     | 获取某个参数失败                             | 检查报错信息中的参数是否正确上传                             |
| 10007         | get invalid rate                                        | 参数值不合法                                 | 检查报错信息中的参数值是否在取值范围内                       |
| 10009         | input invalid data                                      | 输入数据非法                                 | 检查输入数据                                                 |
| 10010         | AIGES_ERROR_NO_LICENSE                                  | 引擎授权不足                                 | 请到控制台提交工单联系技术人员                               |
| 10014         | AIGES_ERROR_TIME_OUT                                    | 会话超时                                     |                                                              |
| 10019         | service read buffer timeout, session timeout            | session超时                                  | 检查是否数据发送完毕但未关闭连接                             |
| 10043         | Syscall AudioCodingDecode error                         | 音频解码失败                                 | 检查aue参数，如果为speex，请确保音频是speex音频并分段压缩且与帧大小一致 |
| 10101         | engine inavtive                                         | 引擎会话已结束                               | 检查是否引擎已结束会话但客户端还在发送数据，比如音频数据虽然发送完毕但并未关闭websocket连接，还在发送空的音频等 |
| 10114         | session timeout                                         | 会话超时                                     | 检查整个会话是否已经超过了60s                                |
| 10139         | invalid param                                           | 参数错误                                     | 引擎编解码错误                                               |
| 10160         | parse request json error                                | 请求数据格式非法                             | 检查请求数据是否是合法的json                                 |
| 10161         | parse base64 string error                               | base64解码失败                               | 检查发送的数据是否使用了base64编码                           |
| 10163         | param validate error:/common 'app_id' param is required | 缺少必传参数，或者参数不合法                 | 检查报错信息中的参数是否正确上传                             |
| 10165         | invalid handle                                          | 无效的句柄                                   | 检查下传入第一帧音频时，是否上传了status=0                   |
| 10200         | read data timeout                                       | 读取数据超时                                 | 检查是否累计10s未发送数据并且未关闭连接                      |
| 10222         | context deadline exceeded                               | 1.上传的数据超过了接口上限； 2.SSL证书无效； | 1.检查接口上传的数据（文本、音频、图片等）是否超越了接口的最大限制，可到相应的接口文档查询具体的上限； 2. 请将log导出发到工单：https://console.xfyun.cn/workorder/commit； |
| 10223         | RemoteLB: can't find valued addr                        | lb 找不到节点                                | 提交工单                                                     |
| 10313         | appid cannot be empty                                   | appid不能为空                                | 检查common参数是否正确上传，或common中的app_id参数是否正确上传或是否为空 |
| 10317         | invalid version                                         | 版本非法                                     | 联系技术人员                                                 |
| 10700         | not authority                                           | 引擎异常                                     | 按照报错原因的描述，对照开发文档检查输入输出，如果仍然无法排除问题，请提供sid以及接口返回的错误信息，到控制台提交工单联系技术人员排查。 |
| 11200         | auth no license                                         | 没有权限                                     | 检查是否使用了未授权的功能，或者总的调用次数已超越上限       |
| 11201         | auth no enough license                                  | 日流控超限                                   | 可联系商务提高每日调用次数                                   |
| 11502         | server error: too many datas in resp                    | 服务配置错误                                 | 提交工单                                                     |
| 11503         | server error :atmos return an error data                | 服务内部响应数据错误                         | 提交工单                                                     |
| 100001~100010 | WrapperInitErr                                          | 调用引擎时出现错误                           | 提交工单                                                     |