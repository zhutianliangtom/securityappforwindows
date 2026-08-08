# SparkChain 在线翻译 Android SDK集成文档

## 1. 在线翻译简介

在线翻译集成了三种翻译能力，具体如下：

| 翻译类型 | 说明                                                         |
| -------- | ------------------------------------------------------------ |
| 讯飞翻译 | 机器翻译（新），基于讯飞自主研发的机器翻译引擎，已经支持包括英、日、法、西、俄等多种语言，效果更优质，已在讯飞翻译机上应用并取得优异成绩。通过调用该接口，可以将源语种文字转化为目标语种文字，并且支持术语词语的个性化翻译。 |
| 小牛翻译 | 机器翻译2.0，基于小牛翻译自主研发的多语种机器翻译引擎，已经支持包括英、日、韩、法、西、俄等100多种语言。通过调用该接口，将源语种文字转化为目标语种文字。 |

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

└── SparkChain 在线翻译 Android SDK集成文档.pdf     SparkChain集成指南

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

![](.\pic\Android在线翻译流程图.PNG)

## 6. SDK 初始化

**在使用SDK功能前，需要先开通在线翻译授权并获取已开通授权的应用信息（appId、apiKey、apiSecret）。SDK全局只需要初始化一次。**初始化时，开发者需要构建一个SparkChainConfig实例config，把相关的appid信息以及日志设置等传入config中，然后再通过SparkChain.getInst().init方法把config实例设置到SDK中。具体初始化示例如下：

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

## 7. 在线翻译初始化

在使用在线翻译功能前，需先通过其构造方法ITS()方法构建其实例，然后用该实例调用相应的方法去设置翻译参数。

在线翻译构造方法如下：

```Java
public class ITS{
    public ITS(String fromlanguage, String tolanguage,TransType type) {        
        ...   
    }    
    
    public ITS(TransType type) {        
        ...  
    }    
    
    public ITS() {       
        ...
    }
}
```

构造方法参数说明：

| 参数名       | 类型      | 说明                                                         |
| ------------ | --------- | ------------------------------------------------------------ |
| fromlanguage | String    | 翻译方向源语种。具体语种见语种列表。                         |
| tolanguage   | String    | 翻译方向目标语种。具体语种见语种列表。                       |
| type         | TransType | 翻译引擎的类型。 <br />ITRANS：机器翻译 <br />NIUTRANS：小牛翻译 |

具体示例如下：

```Java
ITS its = new ITS("cn", "en", TransType.ITRANS);
```

## 8. 功能参数配置

SDK支持用户根据自身需求，通过构建的ITS实例访问相关方法配置功能参数。具体方法说明如下：

| 方法名       | 形参名       | 形参类型 | 说明                                   | 是否必填 | 默认值                                                       |
| ------------ | ------------ | -------- | -------------------------------------- | -------- | ------------------------------------------------------------ |
| fromlanguage | fromlanguage | String   | 翻译方向源语种。具体语种见语种列表。   | 否       | 无。如果用户的构造方法中没有传入语种方向，则这里必填，否则会报错 |
| tolanguage   | tolanguage   | String   | 翻译方向目标语种。具体语种见语种列表。 | 否       |                                                              |

具体配置示例如下：

```Java
its.fromlanguage("cn");
its.tolanguage("en");
```

## 9. 注册结果监听回调

在线翻译运行结果通过ITSCallbacks异步返回，接口定义如下：

```Java
public interface ITSCallbacks {
    void onResult(ITS.ITSResult result, Object usrTag);

    void onError(ITS.ITSError error, Object usrTag);
}
```

ITSCallbacks数据结构说明：

- onResult为在线翻译结果回调方法，参数说明如下：

  | 参数   | 类型          | 说明           |
  | ------ | ------------- | -------------- |
  | result | ITS.ITSResult | 翻译结果实例   |
  | usrTag | Object        | 用户自定义标识 |

- ITS.ITSResult结构说明：

  | 方法                      | 返回值类型 | 说明                       |
  | ------------------------- | ---------- | -------------------------- |
  | getTransResult().getSrc() | String     | 翻译的源文本               |
  | getTransResult().getDst() | String     | 翻译结果                   |
  | getStatus()               | int        | 数据状态： 3：once(一次性) |
  | getSid()                  | String     | 本次交互的sid              |
  | getFrom()                 | String     | 源语种                     |
  | getTo()                   | String     | 目标语种                   |

- onError为在线翻译错误回调，参数说明如下：

  | 参数   | 类型         | 说明             |
  | ------ | ------------ | ---------------- |
  | error  | ITS.ITSError | 错误信息结果实例 |
  | usrTag | Object       | 用户自定义标识   |

- ITS.ITSError结构说明：

  | 方法        | 返回值类型 | 说明      |
  | ----------- | ---------- | --------- |
  | getCode()   | int        | 错误码    |
  | getErrMsg() | String     | 错误信息  |
  | getSid()    | String     | 交互的Sid |

具体示例如下：

```Java
ITSCallbacks miTransCallback = new ITSCallbacks() {
    @Override
    public void onResult(ITS.ITSResult itsResult, Object o) {
        String srcText = itsResult.getTransResult().getSrc(); //翻译的源文本
        String dstText = itsResult.getTransResult().getDst(); //翻译结果
        int status     = itsResult.getStatus();               //翻译结果状态
        String from    = itsResult.getFrom();                 //源语种
        String to      = itsResult.getTo();                   //目标语种
        String sid     = itsResult.getSid();                  //本次交互的SID
    }

    @Override
    public void onError(ITS.ITSError itsError, Object o) {
        int code   = itsError.getCode();    //错误码
        String msg = itsError.getErrMsg();  //错误信息
        String sid = itsError.getSid();     //交互sid
    }
};
its.registerCallbacks(miTransCallback);
```

## 10. 请求调用

开发者注册完监听回调后，可通过its.arun()方法开启会话。请求调用接口如下：

```Java
public class ITS {
    public int arun(String txt,Object usrTag) {      
        ...
    }
}
```

start方法结构说明：

| 参数   | 类型   | 说明           |
| ------ | ------ | -------------- |
| txt    | String | 翻译的源文本   |
| usrTag | Object | 用户自定义标识 |

具体示例如下：

```Java
int ret = its.arun("今天天气很好","12345");
```

## 11. 语种列表

使用不同类型的翻译，其中包含的翻译语种类型并不相同，具体如下：

**注意：使用其他语种前，需要确保已开通相关语种的授权！**

### 11.1 讯飞翻译语种列表

| **语种**   | **参数** | **语种**   | **参数** | **语种**   | **参数** |
| :--------- | :------- | :--------- | :------- | :--------- | :------- |
| 英语       | en       | 捷克语     | cs       | 豪萨语     | ha       |
| 日语       | ja       | 罗马尼亚语 | ro       | 匈牙利语   | hu       |
| 韩语       | ko       | 瑞典语     | sv       | 斯瓦希里语 | sw       |
| 泰语       | th       | 荷兰语     | nl       | 乌兹别克语 | uz       |
| 俄语       | ru       | 波兰语     | pl       | 祖鲁语     | zu       |
| 保加利亚语 | bg       | 阿拉伯语   | ar       | 希腊语     | el       |
| 乌克兰语   | uk       | 波斯语     | fa       | 希伯来语   | he       |
| 越南语     | vi       | 普什图语   | ps       | 亚美尼亚语 | hy       |
| 马来语     | ms       | 乌尔都语   | ur       | 格鲁吉亚语 | ka       |
| 印尼语     | id       | 印地语     | hi       | 广东话     | yue      |
| 菲律宾语   | tl       | 孟加拉语   | bn       | 彝语       | ii       |
| 德语       | de       | 外蒙语     | nm       | 壮语       | zua      |
| 西班牙语   | es       | 外哈语     | kk       | 内蒙语     | mn       |
| 法语       | fr       | 土耳其语   | tr       | 内哈萨克语 | kka      |

### 11.2 小牛翻译语种列表

| **语种**         | **参数** | **语种**           | **参数** | **语种**     | **参数** |
| :--------------- | :------- | :----------------- | :------- | :----------- | :------- |
| 中文(简体)       | cn       | 海地克里奥尔语     | ht       | 普什图语     | ps       |
| 中文(繁体)       | cht      | 匈牙利语           | hu       | 隆迪语       | rn       |
| 英语             | en       | 亚美尼亚语         | hy       | 罗马尼亚语   | ro       |
| 日语             | ja       | 印尼语             | id       | 卢旺达语     | rw       |
| 韩语             | ko       | 伊博语             | ig       | 信德语       | sd       |
| 俄语             | ru       | 冰岛语             | is       | 桑戈语       | sg       |
| 法语             | fr       | 意大利语           | it       | 僧伽罗语     | si       |
| 西班牙语         | es       | 印尼爪哇语         | jv       | 斯洛伐克语   | sk       |
| 阿拉伯语         | ar       | 格鲁吉亚语         | jy       | 斯洛文尼亚语 | sl       |
| 葡萄牙语         | pt       | 哈萨克语           | ka       | 萨摩亚语     | sm       |
| 南非荷兰语       | af       | 凯克其语           | kek      | 修纳语       | sn       |
| 阿姆哈拉语       | am       | 刚果语             | kg       | 索马里语     | so       |
| 阿塞拜疆语       | az       | 哈萨克语（西里尔） | kk       | 阿尔巴尼亚语 | sq       |
| 巴什基尔语       | ba       | 高棉语             | km       | 塞尔维亚语   | sr       |
| 白俄罗斯语       | be       | 卡纳达语           | kn       | 塞索托语     | st       |
| 别姆巴语         | bem      | 库尔德语           | ku       | 印尼巽他语   | su       |
| 保加利亚语       | bg       | 吉尔吉斯语         | ky       | 瑞典语       | sv       |
| 比斯拉马语       | bi       | 拉丁语             | la       | 斯瓦希里语   | sw       |
| 孟加拉语         | bn       | 卢森堡语           | lb       | 泰米尔语     | ta       |
| 波斯尼亚语       | bs       | 卢干达语           | lg       | 泰卢固语     | te       |
| 加泰罗尼亚语     | ca       | 林加拉语           | ln       | 塔吉克语     | tg       |
| 宿务语           | ceb      | 老挝语             | lo       | 茨瓦纳语     | tn       |
| 科西嘉语         | co       | 立陶宛语           | lt       | 泰语         | th       |
| 塞舌尔克里奥尔语 | crs      | 拉脱维亚语         | lv       | 藏语         | ti       |
| 捷克语           | cs       | 马尔加什语         | mg       | 提格雷语     | tig      |
| 威尔士语         | cy       | 马里语             | mhr      | 土库曼语     | tk       |
| 丹麦语           | da       | 毛利语             | mi       | 汤加语       | to       |
| 德语             | de       | 马其顿语           | mk       | 巴布亚皮钦语 | tpi      |
| 埃维语           | ee       | 马拉雅拉姆语       | ml       | 土耳其语     | tr       |
| 希腊语           | el       | 蒙古语(西里尔)     | mn       | 聪加语       | ts       |
| 世界语           | eo       | 马拉地语           | mr       | 鞑靼语       | tt       |
| 爱沙尼亚语       | et       | 山地马里语         | mrj      | 契维语       | tw       |
| 巴斯克语         | eu       | 马来语             | ms       | 塔希提语     | ty       |
| 波斯语           | fa       | 马耳他语           | mt       | 乌德穆尔特语 | udm      |
| 芬兰语           | fi       | 白苗文             | mww      | 乌克兰语     | uk       |
| 菲律宾语         | fil      | 缅甸语             | my       | 乌尔都语     | ur       |
| 斐济语           | fj       | 博克马尔语         | nb       | 维吾尔语     | uy       |
| 弗里西语         | fy       | 尼泊尔语           | ne       | 乌兹别克语   | uz       |
| 爱尔兰语         | ga       | 荷兰语             | nl       | 越南语       | vi       |
| 苏格兰盖尔语     | gd       | 挪威语             | no       | 瓦瑞语       | war      |
| 加利西亚         | gl       | 齐切瓦语           | ny       | 南非科萨语   | xh       |
| 古吉拉特语       | gu       | 奥罗莫语           | om       | 意第绪语     | yi       |
| 豪萨语           | ha       | 奥赛梯语           | os       | 约鲁巴语     | yo       |
| 夏威夷语         | haw      | 克雷塔罗奥托米语   | otq      | 尤卡坦玛雅语 | yua      |
| 希伯来语         | he       | 旁遮普语           | pa       | 广东话       | yue      |
| 印地语           | hi       | 帕皮阿门托语       | pap      | 南非祖鲁语   | zu       |
| 克罗地亚语       | hr       | 波兰语             | pl       |              |          |

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

### 13.3 ITS API

| **返回值类型** | **方法说明**                                                 |
| -------------- | ------------------------------------------------------------ |
| int            | public int arun(String txt,Object usrTag) <br />翻译请求调用 |
| void           | public void fromlanguage(String fromlanguage) <br />设置源语种 |
| void           | public void tolanguage(String tolanguage) <br />设置目标语种 |
| void           | public void registerCallbacks(ITSCallbacks cbs)<br />注册在线翻译的结果监听回调 |

### 13.4 ITSResult API

| 返回值类型  | 方法说明                                                   |
| ----------- | ---------------------------------------------------------- |
| TransResult | public TransResult getTransResult() <br />获取翻译结果实例 |
| int         | public int getStatus() <br />获取数据状态                  |
| String      | public String getSid() <br />获取交互sid                   |
| String      | public String getFrom()<br />获取源语种                    |
| String      | public String getTo()<br />获取目标语种                    |

### 13.5 ITSError API

| 返回值类型 | 方法说明                                     |
| ---------- | -------------------------------------------- |
| int        | public int getCode() <br />获取错误码        |
| String     | public String getErrMsg() <br />获取错误信息 |
| String     | public String getSid() <br />获取交互sid     |

### 13.6 TransResult API

| 返回值类型 | 方法说明                                    |
| ---------- | ------------------------------------------- |
| String     | public String getSrc() <br />获取翻译源文本 |
| String     | public String getDst() <br />获取翻译结果   |

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