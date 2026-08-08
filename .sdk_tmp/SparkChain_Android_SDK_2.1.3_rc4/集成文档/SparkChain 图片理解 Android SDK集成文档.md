# SparkChain 图片理解 Android SDK集成文档

## 1. 图片理解简介

SparkChain支持用户发送一张图片和文本，向大模型提问图片相关的问题，大模型基于发送的图片来给出相应的答案。

## 2. 兼容性说明

| 类别     | 兼容范围                                        |
| :------- | :---------------------------------------------- |
| 系统     | 支持armv7和armv8架构，兼容android 5.0及以上版本 |
| 开发环境 | 建议使用Android Studio 进行开发                 |

## 3. 授权说明

星火认知大模型授权支持按照tokens授权和设备级授权两种方式。

tokens 授权：授权tokens总量，按照tokens 使用量计费，1 tokens 约等于1.5个中文汉字 或者 0.8个英文单词。

## 4. SDK集成包目录结构

将SDK zip包解压缩，得到如下文件：

├── Demo SparkChain的使用DEMO，DEMO中已经集成了SDK，您可以参考DEMO，集成SDK。集成前，请先测通DEMO，了解调用原理。

├── ReleaseNotes.txt SDK版本日志

├── SDK SparkChain SDK

│ └── SparkChain.aar

└── SparkChain 图片理解 Android SDK集成文档.pdf SparkChain集成指南

## 5. SDK工程配置

### 5.1 导入SDK库

复制SparkChain.aar到项目的libs目录下，然后在主Module的build.gradle文件中，增加如下配置：

```java
implementation files('libs/SparkChain.aar')
```

### 5.2 配置权限

外部使用时需要配置以下权限：

| 权限                    | 使用说明                                                     |
| :---------------------- | :----------------------------------------------------------- |
| 权限                    | 使用说明                                                     |
| INTERNET                | 必须权限，SDK需要访问网络获取结果。                          |
| READ_EXTERNAL_STORAGE   | 必须权限，SDK需要判断日志路径是否存在。                      |
| WRITE_EXTERNAL_STORAGE  | 必须权限，SDK写本地日志需要用到该权限。                      |
| MANAGE_EXTERNAL_STORAGE | 可选权限，安卓10以上设备用于动态授权弹出授权框需要用到该权限，安卓10以上设备必选。 |

Android 10.0（API 29）及以上版本需要在application中做如下配置

```java
<application android:requestLegacyExternalStorage="true"/>
```

### 5.3 混淆配置 

SparkChain SDK 已做过混淆，如果您项目中也使用了混淆，请在 proguard-rules.pro文件中添加如下配置保持SparkChain SDK 不再被混淆。

```java
-keep class com.iflytek.sparkchain.** {*;} 
-keep class com.iflytek.sparkchain.**
```

## 6. 接口流程调用图

![](.\pic\Android图片理解流程图.png)

## 7. SDK 初始化

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

初始化返回值：0：初始化成功，非0：初始化失败，请根据具体返回值参考错误码章节查询原因。

## 8. LLM 初始化

SDK是通过LLM实例和大模型进行交互的，不同的功能需要创建不同类型的LLM实例，SDK通过LLMFactory类向开发者提供相应功能的LLM实例。LLMFactory提供的LLM实例构造方法如下：

| 功能     | 说明                                                         |
| :------- | :----------------------------------------------------------- |
| 图片理解 | 构造方法： <br />public static LLM imageUnderstanding() <br />public static LLM imageUnderstanding(Memory memory) <br />public static LLM imageUnderstanding(LLMConfig config) <br />public static LLM imageUnderstanding(LLMConfig config, Memory memory) <br />参数说明： <br />config:星火大模型配置参数。其中的domain为image，其他domain参数不生效。 <br />memory:Memory，星火可以根据memory进行上下文关联回答 |

- LLMConfig 结构如下：

```java
public class LLMConfig {    
    public LLMConfig uid(String uid) {...}    
    public LLMConfig domain(String domain) {...}    
    public LLMConfig auditing(String auditing) {...}    
    public LLMConfig chatID(String chatID) {...}    
    public LLMConfig temperature(float temperature) {...}    
    public LLMConfig topK(int topK) {...}    
    public LLMConfig maxToken(int maxToken) {...}    
    public LLMConfig url(String url) {...}  }
```

- LLMConfig参数说明：

  | 接口名称    | 含义                                        | 参数类型 | 限制                                                         | 是否必传 |
  | :---------- | :------------------------------------------ | :------- | :----------------------------------------------------------- | :------- |
  | domain      | 需要使用的领域                              | String   | 取值为[image]，默认image<br />image: 图片理解访问的是大模型image服务 <br />domain的取值对应的url不同，需要严格对应。url地址参见下文。 | 否       |
  | url         | 配置chat服务器域名地址                      | String   | image:[wss://spark-api.cn-huabei-1.xf-yun.com/v2.1/image](wss://spark-api.cn-huabei-1.xf-yun.com/v2.1/image) <br />url和domain是配合使用的，SDK里预设了image的url。当使用这几个domain时，SDK会自动设置url，故开发者可不用额外设置其值。SDK同样支持开发者访问其他未预置的服务，此时则需要开发者同时设置domain和url。 | 否       |
  | maxToken    | 回答的tokens的最大长度                      | int      | 取值范围1-4096，默认：2048                                   | 否       |
  | temperature | 配置核采样阈值，改变结果的随机程度          | float    | 最小：0, 最大：1，默认：0.5                                  | 否       |
  | auditing    | 内容审核的场景策略                          | String   | 当前仅支持default                                            | 否       |
  | topK        | 配置从k个候选中随机选择⼀个（⾮等概率)      | int      | 取值范围1-6，默认值：4                                       | 否       |
  | chatID      | 配置关联会话chat_id标识，需要保障用户下唯一 | String   |                                                              | 否       |

- Memory支持windowMemory、tokenMemory两种模式，具体说明如下：

  | 类型         | 说明                                                         | 构造参数类型 | 构造参数限制                                                 | 是否必填 |
  | :----------- | :----------------------------------------------------------- | :----------- | :----------------------------------------------------------- | :------- |
  | windowMemory | 通过会话轮数控制上下文范围，即一次提问和一次回答为一轮会话交互。用户可指定会话关联几轮上下文。 | int          | 最小值：0，最大值：无，实际送入长度受接口Token阈值限制       | 是       |
  | tokenMemory  | 通过Token总长度控制上下文范围，1 token 约等于1.5个中文汉字 或者 0.8个英文单词。用户可指定历史会话Token长度 | int          | 最小值：0，最大值：general：4096 tokens，generalv2：8192 tokens | 是       |

开发者在使用memory中，可以通过调用llm.clearHistory()方法清空其memory。

具体构造示例如下：

```java
Memory window_memory = Memory.windowMemory(5);
//windowMemory Memory tokens_memory = Memory.tokenMemory(8192);//tokenMemory 
/****** *图片理解 *******/ 
LLMConfig image_llmConfig = LLMConfig.builder()    
    .maxToken(2048)    
    ... 
    .topK(4);//config配置可缺省，demo仅供展示如何使用,开发者根据实际情况选择。 
LLM image_llm = LLMFactory.imageUnderstanding(image_llmConfig,tokens_memory);
```

## 9. 同步调用

用户可以通过image_llm.run方法向大模型发送图片理解请求，获取大模型返回结果，不支持单实例并发调用。调用接口如下：

```java
public class LLM { 
    public LLMOutput run(String question, byte[] image) { 	
        ... 
    } 	
    public LLMOutput run(String question, byte[] image, int ttl) { 	
        ... 
    }     
}
```

run方法参数说明：

| 参数名   | 类型   | 说明                       | 限制                                         | 是否必填                                                     |
| :------- | :----- | :------------------------- | :------------------------------------------- | :----------------------------------------------------------- |
| question | String | 输入信息文本，包含历史信息 | general：4096 tokens generalv2：8192 tokens  | 是                                                           |
| image    | byte[] | 输入图片的二进制数据流     | 模型自动判断格式，直接传二进制数据即可       | 是(多轮交互中，除了第一轮交互需要传入图片外，第二轮开始可以不传图片，SDK的memory会自动拼接图片数据流) |
| ttl      | int    | 同步调用超时时间           | 用户根据自身需求设置相应的超时时间，默认30秒 | 否                                                           |

LLMOutput数据结构说明：

| 方法                  | 返回类型 | 说明                                                         |
| :-------------------- | :------- | :----------------------------------------------------------- |
| getContent()          | String   | 交互结果                                                     |
| getRole()             | String   | 星火大模型的角色，assistant:：助手，user：用户               |
| getErrCode()          | int      | 交互结果状态，0：调用成功，非0：调用失败，具体原因请根据返回值参考错误码 |
| getErrMsg()           | String   | 调用失败时的错误信息                                         |
| getSid()              | String   | 获取本次交互的sid                                            |
| getCompletionTokens() | int      | 回答的Token大小                                              |
| getPromptTokens()     | int      | 包含历史问题的总Tokens大小                                   |
| getTotalTokens()      | int      | promptTokens和completionTokens的和，也是本次交互计费的Tokens大小 |

具体调用示例如下(已省略把图片转换成二进制数据流代码，具体参考Demo，这里只展示接口如何使用):

```java
byte[] imageData = null; 
...//省略把图片转换成二进制数据流代码 
LLMOutput syncOutput = image_llm.run("图片的内容是什么？",imageData); 
//解析获取的结果，示例展示所有结果获取，开发者可根据自身需要，选择获取。 
String content       = syncOutput.getContent();//获取调用结果 
int errCode          = syncOutput.getErrCode();//获取结果ID,0:调用成功，非0:调用失败 
String errMsg        = syncOutput.getErrMsg();//获取错误信息 
String role          = syncOutput.getRole();//获取角色信息 
String sid           = syncOutput.getSid();//获取本次交互的sid 
int completionTokens = syncOutput.getCompletionTokens();//获取回答的Token大小 
int promptTokens     = syncOutput.getPromptTokens();//包含历史问题的总Tokens大小 
int totalTokens      = syncOutput.getTotalTokens();//promptTokens和completionTokens的和，也是本次交互计费的Tokens大小
```

## 10. 异步调用

用户可以通过image_llm.arun方法向大模型发送图片理解请求，获取大模型返回结果，不支持单实例并发调用。

### 10.1 注册结果监听回调

图片理解的异步请求结果通过LLMCallbacks监听回调返回，LLMCallbacks监听回调接口如下：

```java
LLMCallbacks llmCallbacks = new LLMCallbacks() {    
    @Override 
    public void onLLMResult(LLMResult llmResult, Object usrContext) {    	 
    
    }      
    @Override    
    public void onLLMEvent(LLMEvent event, Object usrContext) {  		    
    
    }      
    @Override    
    public void onLLMError(LLMError error, Object usrContext) {            
    
    } 
};
```

LLMCallbacks数据结构说明：

- onLLMResult为星火请求结果回调，参数说明如下：

  | 参数       | 类型      | 说明               |
  | :--------- | :-------- | :----------------- |
  | result     | LLMResult | 星火大模型结果实例 |
  | usrContext | Object    | 用户自定义标识     |

- LLMResult结构说明：

  | 方法                  | 返回类型 | 说明                                                         |
  | :-------------------- | :------- | :----------------------------------------------------------- |
  | getContent()          | String   | 交互结果                                                     |
  | getStatus()           | int      | 返回结果状态，0：start，1：continue，2：end                  |
  | getRole()             | String   | 星火大模型角色，assistant:：助手，user：用户                 |
  | getSid()              | String   | 本次交互的sid                                                |
  | getCompletionTokens() | int      | 回答的Token大小                                              |
  | getPromptTokens()     | int      | 包含历史问题的总Tokens大小                                   |
  | getTotalTokens()      | int      | promptTokens和completionTokens的和，也是本次交互计费的Tokens大小 |

- onLLMEvent为星火请求事件回调，参数说明如下：

  | 参数       | 类型     | 说明             |
  | :--------- | :------- | :--------------- |
  | event      | LLMEvent | 调用事件结果实例 |
  | usrContext | Object   | 用户自定义标识   |

- LLMEvent结构说明：

  | 方法          | 返回类型 | 说明                               |
  | :------------ | :------- | :--------------------------------- |
  | getEventID()  | int      | 事件ID，15：建立连接，19：连接断开 |
  | getEventMsg() | String   | 事件信息                           |
  | getSid()      | String   | 本次交互的sid                      |

- onLLMError为星火请求错误回调，参数说明如下：

  | 参数       | 类型     | 说明             |
  | :--------- | :------- | :--------------- |
  | error      | LLMError | 错误信息结果实例 |
  | usrContext | Object   | 用户自定义标识   |

- LLMError结构说明：

  | 方法         | 返回类型 | 说明          |
  | :----------- | :------- | :------------ |
  | getErrCode() | int      | 错误码ID      |
  | getErrMsg()  | String   | 错误信息      |
  | getSid()     | String   | 本次交互的sid |

具体调用示例如下：

```java
LLMCallbacks llmCallbacks = new LLMCallbacks() {    
    @Override 
    public void onLLMResult(LLMResult llmResult, Object usrContext) {    	
        //解析获取的交互结果，示例展示所有结果获取，开发者可根据自身需要，选择获取。        
        String content       = llmResult.getContent();//获取交互结果    	
        int status           = llmResult.getStatus();//返回结果状态        
        String role          = llmResult.getRole();//获取角色信息        
        String sid           = llmResult.getSid();//本次交互的sid        
        int completionTokens = llmResult.getCompletionTokens();//获取回答的Token大小        
        int promptTokens     = llmResult.getPromptTokens();//包含历史问题的总Tokens大小        
        int totalTokens      = llmResult.getTotalTokens();//promptTokens和completionTokens的和，也是本次交互计费的Tokens大小 
    }      
    @Override    
    public void onLLMEvent(LLMEvent event, Object usrContext) {        
        int eventId     = event.getEventID();//获取事件ID        
        String eventMsg = event.getEventMsg();//获取事件信息        
        String sid      = event.getSid();//本次交互的sid    
    }      
    @Override    
    public void onLLMError(LLMError error, Object usrContext) {        
        int errCode   = error.getErrCode();//返回错误码        
        String errMsg = error.getErrMsg();//获取错误信息        
        String sid    = error.getSid();//本次交互的sid    
    } 
}; 
image_llm.registerLLMCallbacks(llmCallbacks);
```

### 10.2 请求调用

异步请求调用接口如下：

```java
public class LLM { 
    public int arun(String question, byte[] image) { 	
        ... 
    } 	
    public int arun(String question, byte[] image, Object usrTag) { 	
        ... 
    }     
}
```

arun方法参数说明：

| 参数     | 类型   | 说明                   | 限制                                        | 是否必填                                                     |
| :------- | :----- | :--------------------- | :------------------------------------------ | :----------------------------------------------------------- |
| question | String | 输入信息文本           | general：4096 tokens generalv2：8192 tokens | 是                                                           |
| image    | byet[] | 输入图片的二进制数据流 | 模型自动判断格式，直接传二进制数据即可      | 是(多轮交互中，除了第一轮交互需要传入图片外，第二轮开始可以不传图片，SDK的memory会自动拼接图片数据流) |
| usrTag   | Object | 用户自定义标识         |                                             | 否                                                           |

具体调用示例如下(已省略把图片转换成二进制数据流代码，具体参考Demo，这里只展示接口如何使用):

```java
byte[] imageData = null; 
...//省略把图片转换成二进制数据流代码 
image_llm.arun("图片的内容是什么？",imageData);
```

## 11. 停止调用

如果开发者不需要此次交互结果，可以通过调用stop()方法抛弃此结果，然后重新进行下一次交互。注意，虽然调用此方法可以让SDK抛弃此次交互结果，但由于本次交互已经产生，因此还是会扣取相应的token量。具体调用如下：

```java
image_llm.stop();
```

如果不需要继续使用SDK，需要执行逆初始化释放资源。逆初始化执行步骤参考第12节。

## 12. 逆初始化

当SDK需要完整退出时，需调用逆初始化方法释放资源，示例代码如下：

```java
SparkChain.getInst().unInit()
```

## 13. SDK API介绍

### 13.1 SparkChainConfig API

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

### 13.2 SparkChain API

| 返回值类型 | 方法说明                                                     |
| :--------- | :----------------------------------------------------------- |
| SparkChain | public static SparkChain getInst() <br />获取SparkChain实例  |
| int        | public int init(Context context, SparkChainConfig config) <br />SDK初始化 |
| int        | public int init(Context context) <br />SDK初始化             |
| int        | public int unInit() <br />SDK逆初始化                        |
| int        | public int getInitCode() <br />获取SDK初始化结果码           |

### 13.3 LLMConfig API

| 返回值类型 | 方法说明                                                     |
| :--------- | :----------------------------------------------------------- |
| LLMConfig  | public LLMConfig uid(String uid)  <br />用户自定义标识       |
| LLMConfig  | public LLMConfig domain(String domain) <br />设置需要使用的领域 |
| LLMConfig  | public LLMConfig auditing(String auditing) <br />内容审核的场景策略 |
| LLMConfig  | public LLMConfig chatID(String chatID) <br />配置关联会话chat_id标识，需要保障用户下唯一 |
| LLMConfig  | public LLMConfig temperature(float temperature)  <br />配置核采样阈值，改变结果的随机程度 |
| LLMConfig  | public LLMConfig topK(int topK) <br />配置从k个候选中随机选择⼀个（⾮等概率) |
| LLMConfig  | public LLMConfig maxToken(int maxToken) <br />回答的tokens的最大长度 |
| LLMConfig  | public LLMConfig url(String url) <br />配置chat服务器域名地址 |
| LLMConfig  | public LLMConfig param(String key, int value) <br />扩展接口，用于扩展当前SDK不支持的参数 |
| LLMConfig  | public LLMConfig param(String key, double value)  <br />扩展接口，用于扩展当前SDK不支持的参数 |
| LLMConfig  | public LLMConfig param(String key, boolean value) <br />扩展接口，用于扩展当前SDK不支持的参数 |
| LLMConfig  | public LLMConfig param(String key, String value) <br />扩展接口，用于扩展当前SDK不支持的参数 |
| LLMConfig  | public static LLMConfig builder() <br />构建LLMConfig实例    |

### 13.4 Memory API

| 返回值类型 | 方法说明                                                     |
| :--------- | :----------------------------------------------------------- |
| Memory     | public static Memory windowMemory(int windowsSize) <br />构建windowMemory |
| Memory     | public static Memory tokenMemory(int maxTokens) <br />构建tokenMemory |
| String     | public String getType() <br />获取memory类型                 |

### 13.5 LLMFactory API

| 返回值类型 | 方法说明                                                     |
| :--------- | :----------------------------------------------------------- |
| LLM        | public static LLM textGeneration(LLMConfig config, Memory memory) <br />构建文本交互LLM |
| LLM        | public static LLM textGeneration(LLMConfig config) <br />构建文本交互LLM |
| LLM        | public static LLM textGeneration(Memory memory) <br />构建文本交互LLM |
| LLM        | public static LLM textGeneration() <br />构建文本交互LLM     |
| LLM        | public static LLM imageUnderstanding(LLMConfig config, Memory memory) <br />构建图片理解LLM |
| LLM        | public static LLM imageUnderstanding(LLMConfig config) <br />构建图片理解LLM |
| LLM        | public static LLM imageUnderstanding(Memory memory) <br />构建图片理解LLM |
| LLM        | public static LLM imageUnderstanding() <br />构建图片理解LLM |
| LLM        | public static LLM imageGeneration(int width, int height, LLMConfig config) <br />构建图片生成LLM |
| LLM        | public static LLM imageGeneration(int width, int height) <br />构建图片生成LLM |
| LLM        | public static LLM imageGeneration(LLMConfig config) <br />构建图片生成LLM |
| LLM        | public static LLM imageGeneration() <br />构建图片生成LLM    |

### 13.6 LLM API

| 返回值类型 | 方法说明                                                     |
| :--------- | :----------------------------------------------------------- |
| int        | public int addSystemPrompt(String prompt) <br />添加prompt   |
| void       | public void registerLLMCallbacks(LLMCallbacks cbs) <br />注册SparkChain结果监听回调 |
| LLMOutput  | public LLMOutput run(String question) <br />文本同步调用     |
| LLMOutput  | public LLMOutput run(String question, int ttl) <br />文本同步调用 |
| LLMOutput  | public LLMOutput run(String question, byte[] image) <br />图片理解同步调用 |
| LLMOutput  | public LLMOutput run(String question, byte[] image, int ttl) <br />图片理解同步调用 |
| int        | public int arun(String question) <br />文本异步调用          |
| int        | public int arun(String question, Object usrTag) <br />文本异步调用 |
| int        | public int arun(String question, byte[] image) <br />图片理解异步调用 |
| int        | public int arun(String question, byte[] image, Object usrTag) <br />图片理解异步调用 |
| int        | public int stop() <br />停止请求调用                         |
| void       | public void clearHistory() <br />清空memory记录              |
| LLMConfig  | public LLMConfig getParams() <br />获取创建的LLMConfig实例   |

### 13.7 LLMOutput API

| 返回值类型 | 方法说明                                                     |
| :--------- | :----------------------------------------------------------- |
| String     | public String getSid() <br />获取返回结果的sid字段           |
| int        | public int getErrCode() <br />获取错误码                     |
| String     | public String getErrMsg() <br />获取错误信息                 |
| String     | public String getRole() <br />获取角色                       |
| String     | public String getContent() <br />获取大模型交互的文本结果    |
| byte[]     | public byte[] getImage() <br />获取图片生成的图片结果        |
| int        | public int getStatus() <br />获取结果状态                    |
| int        | public int getCompletionTokens() <br />获取回答的Token大小   |
| int        | public int getPromptTokens() <br />获取包含历史问题的总Tokens大小 |
| int        | public int getTotalTokens() <br />promptTokens和completionTokens的和，也是本次交互计费的Tokens大小 |
| void       | clear() <br />重置LLMOutput实例                              |

### 13.8 LLMError API

| 返回值类型 | 方法说明                                           |
| :--------- | :------------------------------------------------- |
| String     | public String getSid() <br />获取返回结果的sid字段 |
| int        | public int getErrCode() <br />获取错误码           |
| String     | public String getErrMsg() <br />获取错误信息       |
| void       | clear() <br />重置LLMError实例                     |

### 13.9 LLMEvent API

| 返回值类型 | 方法说明                                           |
| :--------- | :------------------------------------------------- |
| int        | public int getEventID() <br />获取事件id           |
| String     | public String getEventMsg() <br />获取事件信息     |
| String     | public String getSid() <br />获取返回结果的sid字段 |
| void       | clear() <br />重置LLMEvent实例                     |

### 13.10 LLMResult API

| 返回值类型 | 方法说明                                                     |
| :--------- | :----------------------------------------------------------- |
| String     | public String getRole() <br />获取角色                       |
| String     | public String getContent() <br />获取大模型交互的文本结果    |
| byte[]     | public byte[] getImage() <br />获取图片生成的图片结果        |
| int        | public int getStatus() <br />获取结果状态                    |
| int        | public int getCompletionTokens() <br />获取回答的Token大小   |
| int        | public int getPromptTokens() <br />获取包含历史问题的总Tokens大小 |
| int        | public int getTotalTokens() <br />promptTokens和completionTokens的和，也是本次交互计费的Tokens大小 |
| String     | public String getSid() <br />获取返回结果的sid字段           |
| void       | clear() <br />重置LLMResult实例                              |

## 14. 错误码

错误码包含SDK错误码和云端错误码。

### 14.1 SDK错误码

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

### 14.2 云端错误码

| 错误码 | 错误信息                                                     |
| :----- | :----------------------------------------------------------- |
| 错误码 | 错误信息                                                     |
| 0      | 成功                                                         |
| 10000  | 升级为ws出现错误                                             |
| 10001  | 通过ws读取用户的消息出错                                     |
| 10002  | 通过ws向用户发送消息 错                                      |
| 10003  | 用户的消息格式有错误                                         |
| 10004  | 用户数据的schema错误                                         |
| 10005  | 用户参数值有错误                                             |
| 10006  | 用户并发错误：当前用户已连接，同一用户不能多处同时连接。     |
| 10007  | 用户流量受限：服务正在处理用户当前的问题，需等待处理完成后再发送新的请求。（必须要等大模型完全回复之后，才能发送下一个问题） |
| 10008  | 服务容量不足，联系工作人员                                   |
| 10009  | 和引擎建立连接失败                                           |
| 10010  | 接收引擎数据的错误                                           |
| 10011  | 发送数据给引擎的错误                                         |
| 10012  | 引擎内部错误                                                 |
| 10013  | 输入内容审核不通过，涉嫌违规，请重新调整输入内容             |
| 10014  | 输出内容涉及敏感信息，审核不通过，后续结果无法展示给用户     |
| 10015  | appid在黑名单中                                              |
| 10016  | appid授权类的错误。比如：未开通此功能，未开通对应版本，token不足，并发超过授权 等等 |
| 10017  | 清除历史失败                                                 |
| 10019  | 表示本次会话内容有涉及违规信息的倾向；建议开发者收到此错误码后给用户一个输入涉及违规的提示 |
| 10021  | 输入审核不通过                                               |
| 10022  | 模型生产的图片涉及敏感信息，审核不通过                       |
| 10110  | 服务忙，请稍后再试                                           |
| 10163  | 请求引擎的参数异常 引擎的schema 检查不通过                   |
| 10222  | 引擎网络异常                                                 |
| 10907  | token数量超过上限。对话历史+问题的字数太多，需要精简输入     |
| 11200  | 授权错误：该appId没有相关功能的授权 或者 业务量超过限制      |
| 11201  | 授权错误：日流控超限。超过当日最大访问量的限制               |
| 11202  | 授权错误：秒级流控超限。秒级并发超过授权路数限制             |
| 11203  | 授权错误：并发流控超限。并发路数超过授权路数限制             |