# SparkChain 在线图片翻译 Android SDK集成文档

## 1. 在线图片翻译简介

在线图片翻译支持对图片中的文字进行识别并翻译，支持以下翻译语种组合：

| 源语种 | 目标语种                                         |
| ------ | ------------------------------------------------ |
| 中文   | 英语、德语、俄语、法语、葡萄牙语、日语、西班牙语、意大利语、越南语 |
| 英语   | 中文、俄语、法语、日语、西班牙语                 |
| 日语   | 中文、英语                                       |
| 韩语   | 中文、英语                                       |
| 法语   | 中文                                             |

## 2. 兼容性说明

| 类别     | 兼容范围                                        |
| -------- | ----------------------------------------------- |
| 系统     | 支持armv7和armv8架构，兼容android 5.0及以上版本 |
| 开发环境 | 建议使用Android Studio 进行开发                 |

## 3. SDK集成包目录结构

将SDK zip包解压缩，得到如下文件：

├── Demo  SparkChain的使用DEMO，DEMO中已经集成了SDK，您可以参考DEMO，集成SDK。集成前，请先测通DEMO，了解调用原理。

├── ReleaseNotes.txt  SDK版本日志

├── SDK  SparkChain SDK

│ └── SparkChain.aar

└── SparkChain 在线图片翻译 Android SDK集成文档.pdf     SparkChain集成指南

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

SparkChain SDK 已做过混淆，如果您项目中也使用了混淆，请在 proguard-rules.pro 文件中添加如下配置保持SparkChain SDK 不再被混淆。

```Java
-keep class com.iflytek.sparkchain.** {*;}
-keep class com.iflytek.sparkchain.**
```

## 5. 接口流程调用图

![Android图片翻译流程图](D:\iflytek\aikit\demo\Sparkchain\Andorid\SparkChain_Android_SDK_2.0.1_rc3_260309\集成文档\pic\Android图片翻译流程图.png)

## 6. SDK 初始化

**在使用SDK功能前，需要先开通在线图片翻译授权并获取已开通授权的应用信息（appId、apiKey、apiSecret）。SDK全局只需要初始化一次。** 初始化时，开发者需要构建一个SparkChainConfig实例config，把相关的appid信息以及日志设置等传入config中，然后再通过SparkChain.getInst().init方法把config实例设置到SDK中。具体初始化示例如下：

```Java
SparkChainConfig config = SparkChainConfig.builder()
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

## 7. 图片翻译初始化

在使用图片翻译功能前，需先通过其构造方法创建 `ImageTrans` 实例，然后用该实例调用相应的方法去设置翻译参数。

图片翻译构造方法如下：

```Java
public class ImageTrans {
    // 指定OCR语种、源语种、目标语种
    public ImageTrans(String ocrLanguage, String fromLanguage, String toLanguage) {
        ...
    }

    // 使用默认参数，后续通过setter方法设置
    public ImageTrans() {
        ...
    }
}
```

构造方法参数说明：

| 参数名      | 类型   | 说明                                                     |
| ----------- | ------ | -------------------------------------------------------- |
| ocrLanguage | String | OCR识别语种。具体语种见第11章语种列表。                  |
| fromLanguage | String | 翻译方向源语种。具体语种见第11章语种列表。               |
| toLanguage  | String | 翻译方向目标语种。具体语种见第11章语种列表。             |

具体示例如下：

```Java
ImageTrans imageTrans = new ImageTrans("ch_en", "cn", "en");
```

## 8. 功能参数配置

SDK支持用户根据自身需求，通过构建的 `ImageTrans` 实例访问相关方法配置功能参数。具体方法说明如下：

| 方法名        | 形参名      | 形参类型 | 说明                                                         | 是否必填 | 默认值  |
| ------------- | ----------- | -------- | ------------------------------------------------------------ | -------- | ------- |
| ocrLanguage   | ocrLanguage | String   | OCR识别语种。可选值：ch_en（中英）、ja（日语）、ko（韩语）、fr（法语）。 | 否       | ch_en   |
| fromLanguage  | fromLanguage | String  | 翻译方向源语种。具体语种见第11章语种列表。                   | 否       | cn      |
| toLanguage    | toLanguage  | String   | 翻译方向目标语种。具体语种见第11章语种列表。                 | 否       | en      |
| returnType    | returnType  | int      | 返回数据类型。1：仅返回译后图片；2：仅返回原文和译文文本；3：译后图片+文本同时返回。 | 否       | 1       |

具体配置示例如下：

```Java
imageTrans.ocrLanguage("ch_en");   // 设置OCR识别语种
imageTrans.fromLanguage("cn");     // 设置源语种
imageTrans.toLanguage("en");       // 设置目标语种
imageTrans.returnType(3);          // 设置返回类型：图片+文本
```

## 9. 注册结果监听回调

图片翻译运行结果通过 `ImageTransCallbacks` 异步返回，接口定义如下：

```Java
public interface ImageTransCallbacks {
    void onResult(ImageTrans.ImageTransResult result, Object usrTag);

    void onError(ImageTrans.ImageTransError error, Object usrTag);
}
```

ImageTransCallbacks数据结构说明：

- `onResult` 为图片翻译结果回调方法，参数说明如下：

  | 参数   | 类型                         | 说明           |
  | ------ | ---------------------------- | -------------- |
  | result | ImageTrans.ImageTransResult  | 翻译结果实例   |
  | usrTag | Object                       | 用户自定义标识 |

- `ImageTrans.ImageTransResult` 结构说明：

  | 方法                          | 返回值类型              | 说明                                                         |
  | ----------------------------- | ----------------------- | ------------------------------------------------------------ |
  | getStatus()                   | int                     | 数据状态：3 表示结果已全部返回                               |
  | getSid()                      | String                  | 本次交互的sid                                                |
  | getItsImage()                 | byte[]                  | 译后图片的二进制数据（returnType为1或3时返回）               |
  | getItsOutput()                | String                  | 整体翻译文本结果（returnType为2或3时返回）                   |
  | getBlockText()                | ImageTrans.BlockText[]  | 逐块文字翻译结果数组（returnType为2或3时返回）               |
  | getBlockText()[i].getSrc()    | String                  | 第i块原文文字                                                |
  | getBlockText()[i].getDst()    | String                  | 第i块译文文字                                                |

- `onError` 为图片翻译错误回调，参数说明如下：

  | 参数   | 类型                        | 说明             |
  | ------ | --------------------------- | ---------------- |
  | error  | ImageTrans.ImageTransError  | 错误信息结果实例 |
  | usrTag | Object                      | 用户自定义标识   |

- `ImageTrans.ImageTransError` 结构说明：

  | 方法        | 返回值类型 | 说明         |
  | ----------- | ---------- | ------------ |
  | getCode()   | int        | 错误码       |
  | getErrMsg() | String     | 错误信息     |
  | getSid()    | String     | 本次会话的id |

具体示例如下：

```Java
imageTrans.registerCallbacks(new ImageTransCallbacks() {
    @Override
    public void onResult(ImageTrans.ImageTransResult result, Object usrTag) {
        int status = result.getStatus();       // 数据状态，3表示完成
        String sid = result.getSid();          // 本次交互的sid

        // 获取译后图片（returnType为1或3时有效）
        byte[] imageBytes = result.getItsImage();
        if (imageBytes != null && imageBytes.length > 0) {
            Bitmap resultBitmap = BitmapFactory.decodeByteArray(imageBytes, 0, imageBytes.length);
            // 使用 resultBitmap 显示或保存
        }

        // 获取整体翻译文本（returnType为2或3时有效）
        String itsOutput = result.getItsOutput();

        // 获取逐块文字翻译结果（returnType为2或3时有效）
        ImageTrans.BlockText[] blocks = result.getBlockText();
        for (ImageTrans.BlockText block : blocks) {
            String src = block.getSrc();  // 原文
            String dst = block.getDst();  // 译文
        }

        if (status == 3) {
            // 结果返回完毕，可进行后续处理
        }
    }

    @Override
    public void onError(ImageTrans.ImageTransError error, Object usrTag) {
        int code    = error.getCode();    // 错误码
        String msg  = error.getErrMsg(); // 错误信息
    }
});
```

## 10. 请求调用

开发者注册完监听回调后，可通过 `imageTrans.arun()` 方法发起图片翻译请求。请求调用接口如下：

```Java
public class ImageTrans {
    public int arun(byte[] imageData, String encoding, Object usrTag) {
        ...
    }
}
```

arun方法参数说明：

| 参数      | 类型   | 说明                                                         | 是否必填 |
| --------- | ------ | ------------------------------------------------------------ | -------- |
| imageData | byte[] | 图片的二进制数据，大小不超过10MB                             | 是       |
| encoding  | String | 图片编码格式，支持：jpg、jpeg、png、bmp、webp、tiff          | 是       |
| usrTag    | Object | 用户自定义标识，会在回调中原样返回                           | 否       |

返回值：0 表示请求发起成功，非0 表示失败，请参考错误码章节。

具体示例如下：

```Java
// 读取图片文件为 byte[]
File file = new File(imagePath);
byte[] imageData = new byte[(int) file.length()];
FileInputStream fis = new FileInputStream(file);
fis.read(imageData);
fis.close();

// 发起翻译请求
int ret = imageTrans.arun(imageData, "jpg", "myTag");
if (ret != 0) {
    Log.e(TAG, "arun 调用失败，错误码：" + ret);
}
```

## 11. 支持语种列表

### 11.1 OCR识别语种（ocrLanguage）

| 参数值 | 说明       |
| ------ | ---------- |
| ch_en  | 中英混合   |
| ja     | 日语       |
| ko     | 韩语       |
| fr     | 法语       |

### 11.2 翻译语种组合

| 源语种（fromLanguage） | 目标语种（toLanguage） | OCR语种（ocrLanguage） |
| ---------------------- | ---------------------- | ---------------------- |
| cn（中文）             | en（英语）             | ch_en                  |
| cn（中文）             | de（德语）             | ch_en                  |
| cn（中文）             | ru（俄语）             | ch_en                  |
| cn（中文）             | fr（法语）             | ch_en                  |
| cn（中文）             | ko（韩语）             | ch_en                  |
| cn（中文）             | pt（葡萄牙语）         | ch_en                  |
| cn（中文）             | ja（日语）             | ch_en                  |
| cn（中文）             | es（西班牙语）         | ch_en                  |
| cn（中文）             | it（意大利语）         | ch_en                  |
| cn（中文）             | vi（越南语）           | ch_en                  |
| en（英语）             | cn（中文）             | ch_en                  |
| en（英语）             | ru（俄语）             | ch_en                  |
| en（英语）             | fr（法语）             | ch_en                  |
| en（英语）             | ja（日语）             | ch_en                  |
| en（英语）             | es（西班牙语）         | ch_en                  |
| ja（日语）             | cn（中文）             | ja                     |
| ja（日语）             | en（英语）             | ja                     |
| ko（韩语）             | cn（中文）             | ko                     |
| ko（韩语）             | en（英语）             | ko                     |
| fr（法语）             | cn（中文）             | fr                     |

## 12. 逆初始化

当SDK需要完整退出时，需调用逆初始化方法释放资源，示例代码如下：

```Java
SparkChain.getInst().unInit();  // SDK逆初始化
```

## 13. SDK API介绍

### 13.1 SparkChainConfig API

| **返回值类型**   | **方法说明**                                                 |
| ---------------- | ------------------------------------------------------------ |
| SparkChainConfig | public SparkChainConfig appID(String appID) <br />设置用户的appID |
| SparkChainConfig | public SparkChainConfig apiKey(String apiKey) <br />设置用户的apiKey |
| SparkChainConfig | public SparkChainConfig apiSecret(String apiSecret) <br />设置用户的apiSecret |
| SparkChainConfig | public SparkChainConfig uid(String uid) <br />设置用户自定义标识 |
| SparkChainConfig | public SparkChainConfig workDir(String workDir) <br />设置SDK工作路径 |
| SparkChainConfig | public SparkChainConfig logLevel(int logLevel) <br />设置日志等级 |
| SparkChainConfig | public SparkChainConfig logPath(String logPath) <br />设置日志保存路径 |
| SparkChainConfig | public static SparkChainConfig builder() <br />构建SparkChainConfig实例 |

### 13.2 SparkChain API

| **返回值类型** | **方法说明**                                                 |
| -------------- | ------------------------------------------------------------ |
| SparkChain     | public static SparkChain getInst() <br />获取SparkChain单例  |
| int            | public int init(Context context, SparkChainConfig config) <br />SDK初始化 |
| int            | public int unInit() <br />SDK逆初始化                        |
| int            | public int getInitCode() <br />获取SDK初始化结果码           |

### 13.3 ImageTrans API

| **返回值类型** | **方法说明**                                                 |
| -------------- | ------------------------------------------------------------ |
| —              | public ImageTrans(String ocrLanguage, String fromLanguage, String toLanguage) <br />创建图片翻译实例，并指定OCR语种、源语种、目标语种 |
| void           | public void ocrLanguage(String ocrLanguage) <br />设置OCR识别语种 |
| void           | public void fromLanguage(String fromLanguage) <br />设置翻译源语种 |
| void           | public void toLanguage(String toLanguage) <br />设置翻译目标语种 |
| void           | public void returnType(int returnType) <br />设置返回数据类型：1-译后图片，2-文本结果，3-图片+文本 |
| void           | public void registerCallbacks(ImageTransCallbacks cbs) <br />注册结果监听回调 |
| int            | public int arun(byte[] imageData, String encoding, Object usrTag) <br />发起图片翻译请求 |

### 13.4 ImageTransResult API

| 返回值类型             | 方法说明                                                     |
| ---------------------- | ------------------------------------------------------------ |
| int                    | public int getStatus() <br />获取数据状态，3表示结果全部返回 |
| String                 | public String getSid() <br />获取本次交互sid                 |
| byte[]                 | public byte[] getItsImage() <br />获取译后图片二进制数据     |
| String                 | public String getItsOutput() <br />获取整体翻译文本结果      |
| ImageTrans.BlockText[] | public BlockText[] getBlockText() <br />获取逐块文字翻译结果数组 |

### 13.5 ImageTrans.BlockText API

| 返回值类型 | 方法说明                         |
| ---------- | -------------------------------- |
| String     | public String getSrc() <br />获取原文文字 |
| String     | public String getDst() <br />获取译文文字 |

### 13.6 ImageTransError API

| 返回值类型 | 方法说明                                     |
| ---------- | -------------------------------------------- |
| int        | public int getCode() <br />获取错误码        |
| String     | public String getErrMsg() <br />获取错误信息 |

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

| 错误码        | 错误描述                                     | 说明                                         | 处理策略                                                     |
| ------------- | -------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------ |
| 10009         | input invalid data                           | 输入数据非法                                 | 检查输入数据                                                 |
| 10010         | service license not enough                   | 没有授权许可或授权数已满                     | 提交工单                                                     |
| 10019         | service read buffer timeout, session timeout | session超时                                  | 检查是否数据发送完毕但未关闭连接                             |
| 10043         | Syscall AudioCodingDecode error              | 音频解码失败                                 | 检查aue参数，如果为speex，请确保音频是speex音频并分段压缩且与帧大小一致 |
| 10114         | session timeout                              | session 超时                                 | 会话时间超时，检查是否发送数据时间超过了60s                  |
| 10139         | invalid param                                | 参数错误                                     | 检查参数是否正确                                             |
| 10160         | parse request json error                     | 请求数据格式非法                             | 检查请求数据是否是合法的json                                 |
| 10161         | parse base64 string error                    | base64解码失败                               | 检查发送的数据是否使用base64编码了                           |
| 10163         | param validate error:...                     | 参数校验失败                                 | 具体原因见详细的描述                                         |
| 10200         | read data timeout                            | 读取数据超时                                 | 检查是否累计10s未发送数据并且未关闭连接                      |
| 10222         | context deadline exceeded                    | 1.上传的数据超过了接口上限； 2.SSL证书无效； | 1.检查接口上传的数据（文本、音频、图片等）是否超越了接口的最大限制，可到相应的接口文档查询具体的上限； 2. 请将log导出发到工单：https://console.xfyun.cn/workorder/commit； |
| 10223         | RemoteLB: can't find valued addr             | lb 找不到节点                                | 提交工单                                                     |
| 10313         | invalid appid                                | appid和apikey不匹配                          | 检查appid是否合法                                            |
| 10317         | invalid version                              | 版本非法                                     | 请到控制台提交工单联系技术人员                               |
| 10700         | not authority                                | 引擎异常                                     | 按照报错原因的描述，对照开发文档检查输入输出，如果仍然无法排除问题，请提供sid以及接口返回的错误信息，到控制台提交工单联系技术人员排查。 |
| 11200         | auth no license                              | 功能未授权                                   | 请先检查appid是否正确，并且确保该appid下添加了相关服务。若没问题，则按照如下方法排查。 1. 确认总调用量是否已超越限制，或者总次数授权已到期，若已超限或者已过期请联系商务人员。 2. 查看是否使用了未授权的功能，或者授权已过期。 |
| 11201         | auth no enough license                       | 该APPID的每日交互次数超过限制                | 根据自身情况提交应用审核进行服务量提额，或者联系商务购买企业级正式接口，获得海量服务量权限以便商用。 |
| 11503         | server error :atmos return an error data     | 服务内部响应数据错误                         | 提交工单                                                     |
| 11502         | server error: too many datas in resp         | 服务配置错误                                 | 提交工单                                                     |
| 100001~100010 | WrapperInitErr                               | 调用引擎时出现错误                           | 请根据message中包含的errno前往 5.2引擎错误码 查看对应的说明及处理策略 |
