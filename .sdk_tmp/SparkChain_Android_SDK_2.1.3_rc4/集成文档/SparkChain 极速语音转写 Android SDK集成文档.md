# SparkChain 极速语音转写 Android SDK集成文档

## 1. 极速语音转写简介

录音文件转写极速版（Speed Transcription）基于深度全序列卷积神经网络，将长段音频（5小时以内）数据转换成文本数据，为信息处理和数据挖掘提供基础。**录音文件转写极速版最快可以达到1小时音频转写，完成仅耗时20秒。**

**录音文件转写极速版是已录制音频（非实时）快速转写成文字**，音频文件上传成功后进入等待队列，待转写成功后用户即可获取结果，音频时长与理论返回时间可以参考：音频时长1小时极速语音转写耗时1分钟左右返回。其他时长的，可以等比例替换。如果很短的音频，考虑到系统调度等因素，也要20秒左右。（请注意，实际返回时长受上传的音频时长和任务总量影响，忙时会出现任务排队情况）。**另外，为使转写服务更加通畅，请尽量转写5分钟以上的音频文件。** 

支持的音频格式： **采样率为16K，采样深度为16bit，单声道的wav/pcm/mp3**

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

└── SparkChain 极速语音转写 Android SDK集成文档.pdf     SparkChain集成指南

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

![](.\pic\Android极速语音转写流程图.png)

## 6. SDK 初始化

**在使用SDK功能前，需要先开通极速语音转写授权并获取已开通授权的应用信息（appId、apiKey、apiSecret）。SDK全局只需要初始化一次。**初始化时，开发者需要构建一个SparkChainConfig实例config，把相关的appid信息以及日志设置等传入config中，然后再通过SparkChain.getInst().init方法把config实例设置到SDK中。具体初始化示例如下：

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

## 7. 极速语音转写初始化

在使用极速语音转写功能前，需先通过其构造方法IST()方法构建其实例，然后用该实例调用相应的方法去设置转写参数。

极速语音转写构造方法如下：

```Java
public class IST {
    public IST() {
        ...
    }
}
```

具体示例如下：

```Java
IST mIST = new IST();
```

## 8. 功能参数配置

SDK支持用户根据自身需求，通过构建的IST实例访问相关方法配置转写参数。具体方法说明如下：

| 方法名         | 形参名         | 形参类型 | 说明                                                         | 是否必填 | 默认值     |
| -------------- | -------------- | -------- | ------------------------------------------------------------ | -------- | ---------- |
| language       | language       | String   | 极速语音转写语种，不传默认为中文。若未授权无法使用会报错10110 | 否       | zh_cn      |
| domain         | domain         | String   |                                                              | 否       | pro_ost_ed |
| accent         | accent         | String   |                                                              | 否       | mandarin   |
| callbackUrl    | callbackUrl    | String   | 任务结果回调服务地址，自定义具体值                           | 否       |            |
| vsppOn         | vsppOn         | int      | 是否开启说话人分离，默认为0 0：不开启 1：开启 注：目前mp3不支持角色分离 | 否       | 0          |
| speakerNum     | speakerNum     | int      | 说话人个数，默认0： 0：表示盲分 非0正数：表示指定的说话人个数 | 否       | 0          |
| outputType     | outputType     | int      | 输出结果类型，默认为0，为0时置信度不生效 0：1best 1：cnlbest 2：多候选（传2需要关掉后处理才生效） | 否       | 0          |
| postprocON     | postprocON     | int      | 后处理开关，默认1： 1：开启 0：关闭                          | 否       | 1          |
| pd             | pd             | String   | 领域个性化参数: 法院: court 教育: edu 金融: finance 医疗: medical 科技: tech 体育: sport 政府: gov 游戏: game 电商: ecom 汽车: car | 否       |            |
| duration       | duration       | int      | 音频时长，单位秒                                             | 否       |            |
| enableSubtitle | enableSubtitle | int      | 字幕文稿功能，1: 字幕场景，0: 文稿场景 (默认)                | 否       | 0          |
| smoothproc     | smoothproc     | boolean  | 顺滑开关，true表示开启，false表示关闭，默认值为true          | 否       | true       |
| colloqproc     | colloqproc     | boolean  | 口语规整开关，true表示开启，false表示关闭，默认值为false     | 否       | false      |
| languageType   | languageType   | int      | 语言模式开关: 1：自动，中英文混合模式 (默认) 2：中文模式，可识别出简单英文 3：英文模式，只识别出英文 4：纯中文模式，只识别出中文 | 否       | 1          |
| vto            | vto            | int      | vad强切控制，单位ms                                          | 否       |            |
| dhw            | dhw            | String   | 会话级热词，多个热词用英文 ',' 分隔。只支持UTF8 编码         | 否       |            |

具体配置示例如下：

```Java
mIST.language("zh_cn");
mIST.domain("pro_ost_ed");
mIST.accent("mandarin");
...
mIST.languageType(4);
```

## 9. 注册结果监听回调

极速语音转写运行结果通过ISTCallbacks异步返回，接口定义如下：

```Java
public interface ISTCallbacks {
    void onResult(IST.ISTResult result, Object usrTag);

    void onProcess(String process, Object usrTag);

    void onError(IST.ISTError error, Object usrTag);
}
```

ISTCallbacks数据结构说明：

- onResult为极速语音转写结果回调方法，参数说明如下：

  | 参数   | 类型          | 说明                 |
  | ------ | ------------- | -------------------- |
  | result | IST.ISTResult | 极速语音转写结果实例 |
  | usrTag | Object        | 用户自定义标识       |

- IST.ISTResult结构说明：

  | 方法            | 返回值类型 | 说明                                                         |
  | --------------- | ---------- | ------------------------------------------------------------ |
  | getCode()       | int        | 转写结果标志，0表示正常                                      |
  | getKey()        | String     | 结果标识，表明是哪个功能的结果：<br />completeUpload：上传完成<br />initUpload：分块上传中的初始化<br />uploadChunk：分块上传过程，会返回多次<br />createTask：创建任务<br />queryTask：查询任务 |
  | getSid()        | String     | 本次交互的sid，每个key的sid是独立的                          |
  | getUrl()        | String     | 上传文件结束后获取到的url，根据它来创建任务                  |
  | getTaskId()     | String     | 任务id                                                       |
  | getTaskStatus() | String     | 任务状态，3和4状态表示存在识别结果：<br/>1：待处理<br/>2：处理中<br/>3：处理完成<br/>4：回调完成 |
  | getTaskType()   | String     | 任务类型                                                     |
  | getResult()     | String     | 转写结果，仅文本                                             |
  | getRawResult()  | String     | 原始转写json结果                                             |

  

- onError为极速语音转写错误回调，参数说明如下：

  | 参数   | 类型         | 说明             |
  | ------ | ------------ | ---------------- |
  | error  | IST.ISTError | 错误信息结果实例 |
  | usrTag | Object       | 用户自定义标识   |

- IST.RtAsrError结构说明：

  | 方法        | 返回值类型 | 说明      |
  | ----------- | ---------- | --------- |
  | getCode()   | int        | 错误码    |
  | getKey()    | String     | 结果标识  |
  | getErrMsg() | String     | 错误信息  |
  | getSid()    | String     | 交互的Sid |

- onProcess为极速语音转写分块上传进度回调

具体示例如下：

```Java
mIST.registerCallbacks(new ISTCallbacks() {
            @Override
            public void onResult(IST.ISTResult result, Object usrTag) {
                Log.d(TAG, "Key:" + result.getKey());
                Log.d(TAG, "code:" + result.getCode());
                Log.d(TAG, "TaskId:" + result.getTaskId());
                Log.d(TAG, "Result:" + result.getResult());
                Log.d(TAG, "TaskStatus:" + result.getTaskStatus());
                Log.d(TAG, "Url:" + result.getUrl());
                Log.d(TAG, "tag:" + (String)usrTag);
                url = result.getUrl();
                taskID = result.getTaskId();
                String text = "Key:"+ result.getKey() + "\n"+"Result:"+ result.getResult() + "\n"+"Url:"+result.getUrl()+ "\n"+"TaskId:"+result.getTaskId()+ "\n";
                isrun = false;
            }

            @Override
            public void onProcess(String process, Object usrTag) {
                Log.d(TAG, "onProcess:" + process);
            }

            @Override
            public void onError(IST.ISTError error, Object usrTag) {
                Log.d(TAG, "errorcode:" + error.getCode());
                Log.d(TAG, "sid:" + error.getSid());
                Log.d(TAG, "errortag:" + (String)usrTag);
               
                isrun = false;
            }

});
```

## 10. 请求调用

### 10.1 上传音频

开发者注册完监听回调后，可通过mIST.upload()方法或mIST.mpUpload()上传音频。上传音频接口如下：

```Java
public class IST {
    //小于30M
    public int upload(String audioPath,String requestId,Object usrTag) {
        ...
    }
    
    public int mpUpload(String audioPath,String requestId,int partSize,Object usrTag)
    {
        ...
    }
}
```

- upload方法结构说明：

| 参数      | 类型   | 说明                                                         |
| --------- | ------ | ------------------------------------------------------------ |
| audioPath | String | 音频文件路径，最好携带音频真实的后缀名，避免影响转码         |
| requestId | String | 请求ID，主要给云端使用，用户层暂时不会用到此参数，但是要确保每次请求的时候唯一 |
| usrTag    | Object | 用户自定义标识                                               |

具体示例如下：

```Java
String filePath = "/sdcard/iflytek/asr/cn_test.pcm";
requestId = "第"+count+"次请求";//客户端用于标记任务的唯一id，最大长度64字符，由客户端保证唯一性，服务回调结果时会会包含此参数
mIST.upload(audioPath,requestId,"UPLOAD");
```

- mpUpload方法说明

| 参数      | 类型   | 说明                                                         |
| --------- | ------ | ------------------------------------------------------------ |
| audioPath | String | 音频文件路径，最好携带音频真实的后缀名，避免影响转码         |
| requestId | String | 请求ID，主要给云端使用，用户层暂时不会用到此参数，但是要确保每次请求的时候唯一 |
| partSize  | int    | 分块的大小                                                   |
| usrTag    | Object | 用户自定义标识                                               |

具体示例如下：

```java
String filePath = "/sdcard/iflytek/asr/cn_test.pcm";
requestId = "第"+count+"次请求";//客户端用于标记任务的唯一id，最大长度64字符，由客户端保证唯一性，服务回调结果时会会包含此参数
mIST.mpUpload(audioPath,requestId,5*1024*1024,"MPUPLOAD");
```

### 10.2 创建任务

上传音频后，开发者可通过mIST.createTask()方法创建任务，然后异步从监听回调中获取taskID，用来查询结果。创建任务如下：

```Java
public class IST {
    public int createTask(String requestId,String audioUrl,String format, String encoding,Object usrTag) {
        ...
    }
}
```

createTask方法参数说明：

| 参数      | 类型   | 说明                                                         |
| --------- | ------ | ------------------------------------------------------------ |
| requestId | String | 请求ID，主要给云端使用，用户层暂时不会用到此参数，但是要确保每次请求的时候唯一 |
| audioUrl  | String | 上传文件后返回的url                                          |
| format    | String | 音频的采样率支持16k,audio/L16;rate=16000                     |
| encoding  | String | 音频数据格式：<br/>wav、pcm（传参raw）<br/>mp3（传参lame）   |
| usrTag    | Object | 用户自定义标识                                               |

具体示例如下：

```Java
mIST.createTask("createTask",url,"audio/L16;rate=16000", "raw","tag");
```

### 10.3 查询任务

当开发者创建任务后，需要调用mIST.queryTask()方法进行任务查询。由于极速转写的结果并不能立即得到，因此需要多次调用，直到获取到结果。查询任务如下：

```Java
public class IST {
    public int queryTask(String taskId,Object usrTag) {
        ...
    }

}
```

queryTask方法参数说明：

| 参数   | 类型   | 说明                       |
| ------ | ------ | -------------------------- |
| taskId | String | createTask后获取到的任务id |
| usrTag | Object | 用户自定义标识             |

具体示例如下：

```Java
mIST.queryTask(taskID,"tag");
```

### 10.4 中断上传

当开发者上传音频时，可以通过调用mIST.stop()来中断上传过程。中断接口如下：

```java
public class IST {
    public int stop();
}
```

具体示例如下：

```java
mIST.stop();
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

### 12.3 IST API

| **返回值类型** | **方法说明**                                                 |
| -------------- | ------------------------------------------------------------ |
| int            | public int upload(String audioPath,String requestId,Object usrTag)<br />上传文件（小于30M） |
| int            | public int mpUpload(String audioPath,String requestId,int partSize,Object usrTag)) <br />分块上传文件 |
| int            | public int createTask(String requestId,String audioUrl,String format, String encoding,Object usrTag) <br />创建任务 |
| int            | public int queryTask(String taskId,Object usrTag)  <br />查询任务 |
| int            | public int stop();<br />中断上传                             |
| void           | public void requestId(String requestId);<br />设置requestId  |
| void           | public void language(String language);<br />设置language     |
| void           | public void domain(String domain);<br />设置domain           |
| void           | public void accent(String accent);<br />设置accent           |
| void           | public void callbackUrl(String callbackUrl)  <br />设置任务结果回调服务地址 |
| void           | public void vsppOn(int vsppOn) <br />设置是否开启说话人分离  |
| void           | public void speakerNum(int speakerNum) <br />设置翻译方向的语种 |
| void           | public void outputType(int outputType) <br />标点过滤控制    |
| void           | public void speakerNum(int speakerNum) <br />设置说话人个数  |
| void           | public void outputType(int outputType) <br />设置输出结果类型 |
| void           | public void postprocON(int postprocON) <br />设置后处理开关  |
| void           | public void pd(String pd)  <br />设置领域个性化参数          |
| void           | public void duration(int duration)<br />设置音频时长         |
| void           | public void enableSubtitle(int enableSubtitle)<br />设置字幕文稿功能 |
| void           | public void smoothproc(boolean smoothproc)<br />设置顺滑开关 |
| void           | public void colloqproc(boolean colloqproc)<br />设置口语规整开关 |
| void           | public void languageType(int languageType)<br />设置语言模式 |
| void           | public void vto(int vto)<br />设置vad强切控制                |
| void           | public void dhw(String dhw)<br />设置会话级热词              |

### ISTResult API

| 返回值类型 | 方法说明                                                     |
| ---------- | ------------------------------------------------------------ |
| int        | public int getCode() <br />云端返回的转写结果状态，0表示正常 |
| String     | public String getKey() <br />获取转写结果标志，表明是哪个功能的结果：<br />completeUpload：上传完成<br />initUpload：分块上传中的初始化<br />uploadChunk：分块上传过程，会返回多次<br />createTask：创建任务<br />queryTask：查询任务 |
| String     | public String getSid() <br />获取交互sid                     |
| String     | public String getUrl()<br />获取上传音频的url                |
| String     | public String getTaskId() <br />获取任务id                   |
| String     | public String getTaskStatus()<br />获取任务状态，3和4状态表示存在识别结果：<br/>1：待处理<br/>2：处理中<br/>3：处理完成<br/>4：回调完成 |
| String     | public String getTaskType()<br />获取任务类型                |
| String     | public String getResult()<br />获取转写结果，纯文本          |
| String     | public String getRawResult()<br />获取转写原始结果，json格式 |

### 12.5 ISTError API

| 返回值类型 | 方法说明                                     |
| ---------- | -------------------------------------------- |
| int        | public int getCode() <br />获取错误码        |
| String     | public String getKey()<br />获取结果标志     |
| String     | public String getErrMsg() <br />获取错误信息 |
| String     | public String getSid() <br />获取交互sid     |

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