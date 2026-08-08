# SparkChain 在线语音合成 Android SDK集成文档

## 1. 在线语音合成简介

在线语音合成流式接口将文字信息转化为声音信息，同时提供了众多极具特色的发音人（音库）供您选择。具体发音人参考功能参数配置。

注意：在使用该能力前，需要开通相应的授权。

小语种及少数民族方言：

- 目前新增：韩语、日语、维吾尔语、藏语、法语、俄语、西班牙语、印地语、德语、越南语、巴西葡萄牙语、意大利语、葡萄牙语、泰语、乌尔都语；
- 使用小语种时上传文本编码必须使用unicode编码且设置tte=unicode（unicode即utf16小端的编码方式）或者使用UTF8的编码方式；
- 需先在控制台开启小语种发音人才可合成小语种，否则报错11200。

## 2. 兼容性说明

| **类别** | **兼容范围**                                    |
| -------- | ----------------------------------------------- |
| 系统     | 支持armv7和armv8架构，兼容android 5.0及以上版本 |
| 开发环境 | 建议使用Android Studio 进行开发                 |

## 3. SDK集成包目录结构

将SDK zip包解压缩，得到如下文件：

├── Demo SparkChain的使用DEMO，DEMO中已经集成了SDK，您可以参考DEMO，集成SDK。集成前，请先测通DEMO，了解调用原理。

├── ReleaseNotes.txt SDK版本日志

├── SDK SparkChain SDK

│ └── SparkChain.aar

└── SparkChain 在线语音合成 Android SDK集成文档.pdf     SparkChain集成指南

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

![](.\pic\Android在线语音合成.PNG)

## 6. SDK 初始化

**在使用SDK功能前，需要先开通在线语音合成授权并获取已开通授权的应用信息（appId、apiKey、apiSecret）。SDK全局只需要初始化一次。**初始化时，开发者需要构建一个SparkChainConfig实例config，把相关的appid信息以及日志设置等传入config中，然后再通过SparkChain.getInst().init方法把config实例设置到SDK中。具体初始化示例如下：

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

## 7. 在线语音合成初始化

在使用在线语音合成功能前，需先通过其构造方法OnlineTTS()方法构建其实例，然后用该实例调用相应的方法去设置转写参数。

在线语音合成构造方法如下：

```Java
public class OnlineTTS extends TTS {
    public OnlineTTS(String vcn) {        
        ...
    }
}
```

构造方法参数说明：

| 方法名    | 参数名 | 类型   | 说明                                                         |
| --------- | ------ | ------ | ------------------------------------------------------------ |
| OnlineTTS | vcn    | String | 发音人，可选值：请到控制台添加试用或购买发音人，添加后即显示发音人参数值。默认值:xiaoyan |

具体示例如下：

```Java
OnlineTTS tts = new OnlineTTS("xiaoyan");
```

## 8. 功能参数配置

SDK支持用户根据自身需求，通过构建的OnlineTTS实例访问相关方法配置合成参数。具体方法说明如下：

| 方法名 | 形参名 | 形参类型 | **必传** | **描述**                                                     | **示例**                                                     |
| ------ | ------ | -------- | -------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| aue    | aue    | String   | 是       | 音频编码，可选值： <br />raw：未压缩的pcm <br />lame：mp3 (当aue=lame时需传参sfl=1) <br />speex-org-wb;7： 标准开源speex（for speex_wideband，即16k）数字代表指定压缩等级（默认等级为8） <br />speex-org-nb;7： 标准开源speex（for speex_narrowband，即8k）数字代表指定压缩等级（默认等级为8） <br />speex;7：压缩格式，压缩等级1~10，默认为7（8k讯飞定制speex） <br />speex-wb;7：压缩格式，压缩等级1~10，默认为7（16k讯飞定制speex） | "raw" "speex-org-wb;7" 数字代表指定压缩等级（默认等级为8），数字必传 标准开源speex编码以及讯飞定制speex说明请参考[音频格式说明](https://www.xfyun.cn/doc/asr/voicedictation/Audio.html#speex编码) |
| sfl    | sfl    | int      | 否       | 需要配合aue=lame使用，开启流式返回 mp3格式音频 <br />取值：1 开启 | 1                                                            |
| auf    | auf    | String   | 否       | 音频采样率，可选值： <br />audio/L16;rate=8000：合成8K 的音频 <br />audio/L16;rate=16000：合成16K 的音频 <br />auf不传值：合成16K 的音频 | "audio/L16;rate=16000"                                       |
| vcn    | vcn    | String   | 是       | 发音人，可选值：<br />请到控制台添加试用或购买发音人，添加后即显示发音人参数值 | "xiaoyan"                                                    |
| speed  | speed  | int      | 否       | 语速，可选值：[0-100]，默认为50                              | 50                                                           |
| volume | volume | int      | 否       | 音量，可选值：[0-100]，默认为50                              | 50                                                           |
| pitch  | pitch  | int      | 否       | 音高，可选值：[0-100]，默认为50                              | 50                                                           |
| bgs    | bgs    | int      | 否       | 合成音频的背景音 <br />0:无背景音（默认值） <br />1:有背景音 | 0                                                            |
| tte    | tte    | String   | 否       | 文本编码格式 <br />GB2312 <br />GBK <br />BIG5 <br />UNICODE(小语种必须使用UNICODE编码，合成的文本需使用utf16小端的编码方式，详见[java示例demo](https://www.xfyun.cn/doc/tts/online_tts/API.html#调用示例)) <br />GB18030 UTF8（小语种） | "GBK"                                                        |
| reg    | reg    | int      | 否       | 设置英文发音方式：<br />0：自动判断处理，如果不确定将按照英文词语拼写处理（缺省） <br />1：所有英文按字母发音 <br />2：自动判断处理，如果不确定将按照字母朗读 默认按英文单词发音 | 2                                                            |
| rdn    | rdn    | int      | 否       | 合成音频数字发音方式 <br />0：自动判断（默认值） <br />1：完全数值 <br />2：完全字符串 <br />3：字符串优先 | 0                                                            |

具体配置示例如下：

```Java
mOnlineTTS.aue("raw");
mOnlineTTS.bgs(0);//合成音频的背景音 0:无背景音（默认值） 1:有背景音
...
mOnlineTTS.speed(mTTSParams.speed);//语速
mOnlineTTS.pitch(mTTSParams.pitch);//语调
mOnlineTTS.volume(mTTSParams.volume);//音量
```

## 9. 注册结果监听回调

在线语音合成运行结果通过TTSCallbacks异步返回，接口定义如下：

```Java
public interface TTSCallbacks {
    void onResult(TTS.TTSResult result, Object usrTag);

    void onError(TTS.TTSError error, Object usrTag);
}
```

TTSCallbacks数据结构说明：

- onResult为超拟人合成音频回调方法，参数说明如下：

  | **参数** | **类型**      | **说明**         |
  | -------- | ------------- | ---------------- |
  | result   | TTS.TTSResult | 在线合成结果实例 |
  | usrTag   | Object        | 用户自定义标识   |

- TTSResult结构说明：

  | **方法**    | **返回值类型** | **说明**                                  |
  | ----------- | -------------- | ----------------------------------------- |
  | getData()   | byte[]         | ⾳频数据，最⼩尺⼨:0B, 最⼤尺⼨:10485760B |
  | getLen()    | int            | 音频数据长度                              |
  | getStatus() | int            | 数据状态，0:开始, 1:开始, 2:结束          |
  | getCed()    | String         | 流式音频数据的进度尾端点                  |
  | getSid()    | String         | 本次会话的id                              |

- onError为超拟人合成错误回调，参数说明如下：

  | **参数** | **类型**     | **说明**         |
  | -------- | ------------ | ---------------- |
  | error    | TTS.TTSError | 错误信息结果实例 |
  | usrTag   | Object       | 用户自定义标识   |

- TTSError结果说明：

  | **方法**    | **返回值类型** | **说明**                       |
  | ----------- | -------------- | ------------------------------ |
  | getCode()   | int            | 错误码ID，具体参考错误码章节。 |
  | getErrMsg() | String         | 错误信息                       |
  | getSid()    | String         | 本次会话的id                   |

具体示例如下：

```Java
TTSCallbacks mTTSCallback = new TTSCallbacks() {         
        @Override        
        public void onResult(TTS.TTSResult result, Object usrTag) {            
            //解析获取的交互结果，示例展示所有结果获取，开发者可根据自身需要，选择获取。        
            byte[] audio    = result.getData();//音频数据
            int len        = result.getLen();//音频数据长度
            int status     = result.getStatus();//数据状态
            String ced     = result.getCed();//进度
            String sid     = result.getSid();//sid    
        }        
        @Override        
        public void onError(TTS.TTSError ttsError, Object usrTag) {                 
            int errCode   = ttsError.getCode();//错误码            
            String errMsg = ttsError.getErrMsg();//错误信息            
            String sid    = ttsError.getSid();//sid        
        } 
}; 
mOnlineTTS.registerCallbacks(mTTSCallback);
```

## 10. 请求调用

开发者注册完监听回调后，可通过mOnlineTTS.aRun()方法进行请求调用。请求调用接口如下：

```Java
public class OnlineTTS extends TTS {
    public int aRun(String text) {        
        ...   
    }    
    
    public int aRun(String text, Object usrTag) {        
        ...
    }
}
```

aRun方法结构说明：

| **参数** | **类型** | **说明**       |
| -------- | -------- | -------------- |
| text     | String   | 请求合成文本。 |
| usrTag   | Object   | 用户自定义标识 |

具体示例如下：

```Java
String text = "技术支持跑的快,全靠大佬们带,受着老板们和研发大佬熏陶,技术支持也不会掉队的。"
mOnlineTTS.aRun(text);
 
//带用户自定义标识调用方式示例：
//int usrTag = 1;
//mOnlineTTS.aRun(text,usrTag);
```

## 11. 停止合成

如果开发者不需要此次合成结果，可以通过调用stop()方法结束本次合成，然后重新进行下一次交互。具体调用如下：

```Java
mOnlineTTS.stop();
```

如果不需要继续使用SDK，需要执行逆初始化释放资源。逆初始化执行步骤参考第12节。

## 12. 逆初始化

当SDK需要完整退出时，需调用逆初始化方法释放资源，示例代码如下：

```Java
SparkChain.getInst().unInit();  //SDK逆初始化
```

## 13. SDK API介绍

### 13.1 SparkChainConfig API

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

### 13.2 SparkChain API

| **返回值类型** | **方法说明**                                                 |
| -------------- | ------------------------------------------------------------ |
| SparkChain     | public static SparkChain getInst()  <br />获取SparkChain实例 |
| int            | public int init(Context context, SparkChainConfig config)  <br />SDK初始化 |
| int            | public int init(Context context)  <br />SDK初始化            |
| int            | public int unInit()  <br />SDK逆初始化                       |
| int            | public int getInitCode()  <br />获取SDK初始化结果码          |

### 13.3 OnlineTTS API

| **返回值类型** | **方法说明**                                                 |
| -------------- | ------------------------------------------------------------ |
| void           | public void aue(String aue)  <br />设置音频编码              |
| void           | public void sfl(int sfl) <br />开启流式返回(配合aue=lame使用) |
| void           | public void auf(String auf) <br />设置音频采样率             |
| void           | public void tte(String tte)<br />设置文本编码格式            |
| void           | public void vcn(String vcn) <br />设置发音人                 |
| void           | public void speed(int speed) <br />设置语速                  |
| void           | public void pitch(int pitch) <br />设置音调                  |
| void           | public void volume(int volume) <br />设置音量                |
| void           | public void bgs(int bgs) <br />设置背景音                    |
| void           | public void reg(int reg) <br />设置英文发音方式              |
| void           | public void rdn(int rdn) <br />设置数字发音方式              |
| void           | public void registerCallbacks(TTSCallbacks cbs) <br />注册监听回调 |
| void           | public void stop() <br />停止合成                            |
| int            | public int aRun(String text)<br />请求调用                   |
| int            | public int aRun(String text, Object usrTag) <br />请求调用   |

### 13.4 TTSResult API

| 返回值类型 | 方法说明                                   |
| ---------- | ------------------------------------------ |
| byte[]     | public byte[] getData() <br />获取音频数据 |
| int        | public int getLen() <br />获取音频数据长度 |
| String     | public String getCed() <br />获取音频进度  |
| int        | public int getStatus() <br />获取数据状态  |
| String     | public String getSid() <br />获取交互sid   |

### 13.5 TTSError API

| 返回值类型 | 方法说明                                     |
| ---------- | -------------------------------------------- |
| int        | public int getCode() <br />获取错误码        |
| String     | public String getErrMsg() <br />获取错误信息 |
| String     | public String getSid() <br />获取交互sid     |

## 14. 错误码

错误码包含SDK错误码和云端错误码。

### 14.1 SDK错误码

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

### 14.2 部分云端错误码

备注：如出现下述列表中没有的错误码，可到 [这里](https://www.xfyun.cn/document/error-code) 查询。

| 错误码 | 错误描述                                     | 说明                                               | 处理方式                                                     |
| ------ | -------------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------ |
| 10005  | licc fail                                    | appid授权失败                                      | 确认appid是否正确，是否开通了合成服务                        |
| 10006  | Get audio rate fail                          | 请求缺失必要参数                                   | 检查报错信息中的参数是否正确上传                             |
| 10007  | get invalid rate                             | 请求的参数值无效                                   | 检查报错信息中的参数值是否在取值范围内                       |
| 10010  | AIGES_ERROR_NO_LICENSE                       | 引擎授权不足                                       | 请到控制台提交工单联系技术人员                               |
| 10109  | AIGES_ERROR_INVALID_DATA                     | 请求文本长度非法                                   | 检查是否文本长度超出了限制                                   |
| 10019  | service read buffer timeout, session timeout | session超时                                        | 检查是否数据发送完毕但未关闭连接                             |
| 10101  | engine inavtive                              | 引擎会话已结束                                     | 检查是否引擎已结束会话但客户端还在发送数据，比如音频数据虽然发送完毕但并未关闭websocket连接，还在发送空的音频等 |
| 10313  | appid cannot be empty                        | appid不能为空                                      | 检查common参数是否正确上传，或common中的app_id参数是否正确上传或是否为空 |
| 10317  | invalid version                              | 版本非法                                           | 联系技术人员                                                 |
| 11200  | auth no license                              | 没有权限                                           | 检查是否使用了未授权的发音人，或者总的调用次数已超越上限     |
| 11201  | auth no enough license                       | 日流控超限                                         | 可联系商务提高每日调用次数                                   |
| 10160  | parse request json error                     | 请求数据格式非法                                   | 检查请求数据是否是合法的json                                 |
| 10161  | parse base64 string error                    | base64解码失败                                     | 检查发送的数据是否使用了base64编码                           |
| 10163  | param validate error:...                     | 缺少必传参数，或者参数不合法，具体原因见详细的描述 | 1)检查报错信息中的参数是否正确上传 2)检查上传的文本是不是已超过最大限制 |
| 10200  | read data timeout                            | 读取数据超时                                       | 检查是否累计10s未发送数据并且未关闭连接                      |
| 10222  | context deadline exceeded                    | 网络异常                                           | 1)检查网络是否异常 2)调用超时，如果使用的是mp3格式的话，要传sfl=1来开启流式返回mp3的功能，否则文本长度过长就可能会超时。 |