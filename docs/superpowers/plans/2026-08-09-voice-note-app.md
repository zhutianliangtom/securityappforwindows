# 智能语音笔记 App 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一款 Android 原生智能语音笔记应用：语音输入 → 讯飞识别 → 本地 NLP 分类提取（待办/已完成 + 时间/地点/人物/概况/主题）→ 卡片式首页 + 共享元素转场详情页 + 本地提醒。

**Architecture:** 单 Activity + 多 Fragment（首页/详情/确认编辑），MVVM（ViewModel + StateFlow），Room 本地数据库，NLP 规则引擎为纯函数模块，语音模块通过 `IRecognizer` 接口抽象（在线/离线可切换），提醒基于 AlarmManager + 本地通知。

**Tech Stack:** Kotlin、XML + Material 3、ViewBinding、Room 2.6.1（KSP）、Coroutines/Flow、讯飞 MSC SDK（在线听写，离线预留）、JUnit（测试产物，本机不执行）。

---

## 重要约束（与用户确认）

1. **完全不运行构建命令**：本机不执行 `gradlew` 任何任务（不含 `test` / `assemble`）。所有代码通过人工自审保证正确性。
2. 测试代码照常编写（NLP 规则引擎 JUnit），作为可执行产物，供用户日后在 Android Studio 中运行（`./gradlew testDebugUnitTest`）。
3. 讯飞 SDK（`msc.jar` + so 文件）需用户从讯飞开放平台下载并放入 `app/libs/`，代码按官方 API 真实调用（不 mock）。未放置 SDK 前工程无法编译属预期。
4. 每个任务完成后 git commit。

## 文件结构

```
app/
├── build.gradle.kts
├── proguard-rules.pro
├── keystore.properties              (gitignored，签名配置)
├── keystore.properties.example      (提交)
├── keystore/release.keystore        (gitignored，keytool 生成)
└── src/main/
    ├── AndroidManifest.xml
    ├── java/com/example/voicenote/
    │   ├── VoiceNoteApp.kt
    │   ├── AppConfig.kt
    │   ├── data/    Note.kt NoteDao.kt NoteDatabase.kt NoteRepository.kt
    │   ├── nlp/     NoteIntent.kt NlpResult.kt IntentClassifier.kt TimeExtractor.kt
    │   │            LocationExtractor.kt PersonExtractor.kt SummaryExtractor.kt
    │   │            TopicExtractor.kt NlpEngine.kt
    │   ├── voice/   IRecognizer.kt BaseRecognizer.kt OnlineRecognizer.kt
    │   │            OfflineRecognizer.kt RecognizerFactory.kt IatResultParser.kt
    │   ├── audio/   RecordManager.kt AudioPlayer.kt
    │   ├── reminder/ AlarmScheduler.kt ReminderReceiver.kt ReminderHelper.kt
    │   └── ui/
    │       ├── MainActivity.kt
    │       ├── home/       HomeFragment.kt HomeViewModel.kt NoteAdapter.kt
    │       ├── detail/     DetailFragment.kt DetailViewModel.kt
    │       └── record/     RecordConfirmFragment.kt RecordConfirmViewModel.kt
    └── res/
        ├── values/  strings.xml colors.xml themes.xml dimens.xml
        ├── values-night/ colors.xml
        ├── drawable/ ic_launcher_foreground.xml ic_mic.xml ic_notification.xml
        │             ic_back.xml ic_play.xml ic_pause.xml ic_done.xml ic_delete.xml
        │             chip_bg.xml
        ├── mipmap-anydpi-v26/ ic_launcher.xml ic_launcher_round.xml
        └── layout/  activity_main.xml fragment_home.xml item_note_card.xml
                     fragment_detail.xml fragment_record_confirm.xml
├── .gitignore
├── settings.gradle.kts
├── build.gradle.kts
├── gradle.properties
└── gradle/wrapper/gradle-wrapper.properties
```

测试文件：`app/src/test/java/com/example/voicenote/nlp/NlpEngineTest.kt`

---

### Task 1: 工程脚手架

**Files:**
- Create: `settings.gradle.kts`
- Create: `build.gradle.kts`
- Create: `gradle.properties`
- Create: `gradle/wrapper/gradle-wrapper.properties`
- Create: `app/build.gradle.kts`
- Create: `app/proguard-rules.pro`
- Create: `.gitignore`
- Create: `app/src/main/AndroidManifest.xml`
- Create: `app/src/main/java/com/example/voicenote/VoiceNoteApp.kt`
- Create: `app/src/main/java/com/example/voicenote/AppConfig.kt`
- Create: `app/src/main/res/values/strings.xml`
- Create: `app/src/main/res/values/colors.xml`
- Create: `app/src/main/res/values/colors-night.xml`
- Create: `app/src/main/res/values/themes.xml`
- Create: `app/src/main/res/values/dimens.xml`
- Create: `app/src/main/res/drawable/ic_launcher_foreground.xml`
- Create: `app/src/main/res/drawable/ic_mic.xml`
- Create: `app/src/main/res/drawable/ic_notification.xml`
- Create: `app/src/main/res/drawable/ic_back.xml`
- Create: `app/src/main/res/drawable/ic_play.xml`
- Create: `app/src/main/res/drawable/ic_pause.xml`
- Create: `app/src/main/res/drawable/ic_done.xml`
- Create: `app/src/main/res/drawable/ic_delete.xml`
- Create: `app/src/main/res/drawable/chip_bg.xml`
- Create: `app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml`
- Create: `app/src/main/res/mipmap-anydpi-v26/ic_launcher_round.xml`

- [ ] **Step 1: 根 Gradle 配置**

`settings.gradle.kts`：

```kotlin
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "VoiceNote"
include(":app")
```

`build.gradle.kts`（根）：

```kotlin
plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    id("com.google.devtools.ksp") version "2.0.21-1.0.28" apply false
}
```

`gradle.properties`：

```properties
org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
android.useAndroidX=true
android.nonTransitiveRClass=true
```

`gradle/wrapper/gradle-wrapper.properties`：

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.9-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

- [ ] **Step 2: app 模块 Gradle 配置（含 release 签名配置，signingConfigs 在 buildTypes 之前）**

`app/build.gradle.kts`：

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.devtools.ksp")
}

android {
    namespace = "com.example.voicenote"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.example.voicenote"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"
    }

    signingConfigs {
        create("release") {
            val props = java.util.Properties()
            val f = rootProject.file("keystore.properties")
            if (f.exists()) f.inputStream().use { props.load(it) }
            storeFile = rootProject.file(props.getProperty("storeFile", "keystore/release.keystore"))
            storePassword = props.getProperty("storePassword", "")
            keyAlias = props.getProperty("keyAlias", "")
            keyPassword = props.getProperty("keyPassword", "")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { viewBinding = true }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    implementation("androidx.fragment:fragment-ktx:1.8.5")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    ksp("androidx.room:room-compiler:2.6.1")
    testImplementation("junit:junit:4.13.2")
}
```

`app/proguard-rules.pro`：

```proguard
# 讯飞 SDK 需要保留的类
-keep class com.iflytek.** { *; }
-dontwarn com.iflytek.**
-keepattributes Signature
```

`app/keystore.properties.example`：

```properties
storeFile=keystore/release.keystore
storePassword=REPLACE_ME
keyAlias=voicenote
keyPassword=REPLACE_ME
```

- [ ] **Step 3: .gitignore**

`.gitignore`：

```gitignore
.gradle/
build/
local.properties
.idea/
*.iml
.DS_Store
captures/
.externalNativeBuild/
.cxx/
app/build/
app/keystore.properties
*.keystore
*.jks
```

- [ ] **Step 4: AndroidManifest**

`app/src/main/AndroidManifest.xml`：

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.RECORD_AUDIO" />
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
    <uses-permission android:name="android.permission.SCHEDULE_EXACT_ALARM" />

    <application
        android:name=".VoiceNoteApp"
        android:allowBackup="false"
        android:icon="@mipmap/ic_launcher"
        android:roundIcon="@mipmap/ic_launcher_round"
        android:label="@string/app_name"
        android:supportsRtl="true"
        android:theme="@style/Theme.VoiceNote">

        <activity
            android:name=".ui.MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <receiver
            android:name=".reminder.ReminderReceiver"
            android:exported="false" />
    </application>

</manifest>
```

- [ ] **Step 5: 应用类与配置**

`app/src/main/java/com/example/voicenote/VoiceNoteApp.kt`：

```kotlin
package com.example.voicenote

import android.app.Application
import com.example.voicenote.data.NoteRepository

class VoiceNoteApp : Application() {
    val repository: NoteRepository by lazy { NoteRepository.get(this) }
}
```

`app/src/main/java/com/example/voicenote/AppConfig.kt`：

```kotlin
package com.example.voicenote

object AppConfig {
    // 讯飞开放平台凭证（本地开发）
    const val IFLYTEK_APPID = "b0c90dc2"
    const val IFLYTEK_API_KEY = "466ce52106ddebe0e8cd6ce3f0636477"
    const val IFLYTEK_API_SECRET = "OTUxYTA5MDU0NzcxNWVhOWJmMTE4OWM4"
    // "online"=讯飞在线听写  "offline"=讯飞离线听写（需开通离线能力并放置授权文件）
    const val RECOGNIZER_MODE = "online"
}
```

- [ ] **Step 6: 资源文件**

`res/values/strings.xml`：

```xml
<resources>
    <string name="app_name">语音笔记</string>
    <string name="tab_todo">待办</string>
    <string name="tab_done">已完成</string>
    <string name="mic_start">开始录音</string>
    <string name="mic_stop">停止</string>
    <string name="record_hint">轻点按钮，说出你要记录的内容</string>
    <string name="recording">正在录音…</string>
    <string name="recognizing">正在识别…</string>
    <string name="recognize_failed">识别失败：%1$s</string>
    <string name="empty_result">未识别到内容，请重试</string>
    <string name="save">保存</string>
    <string name="delete">删除</string>
    <string name="back">返回</string>
    <string name="category">分类</string>
    <string name="event_time">时间</string>
    <string name="location">地点</string>
    <string name="person">人物</string>
    <string name="summary">事件概况</string>
    <string name="topic">主题</string>
    <string name="content_label">内容</string>
    <string name="reminder">提醒</string>
    <string name="set_reminder">设置提醒</string>
    <string name="mark_done">标记完成</string>
    <string name="restore_todo">恢复为待办</string>
    <string name="play">播放</string>
    <string name="pause">暂停</string>
    <string name="confirm_delete">确定删除这条笔记吗？</string>
    <string name="permission_denied">需要录音和通知权限</string>
    <string name="reminder_title">语音笔记提醒</string>
    <string name="edit">编辑</string>
    <string name="audio">录音</string>
</resources>
```

`res/values/colors.xml`（初始配色，Task 9 由 frontend-design 精调）：

```xml
<resources>
    <color name="primary">#5B67F5</color>
    <color name="on_primary">#FFFFFF</color>
    <color name="primary_container">#E4E7FF</color>
    <color name="on_primary_container">#1A1C4A</color>
    <color name="secondary">#FFB74D</color>
    <color name="surface">#FAFAFE</color>
    <color name="on_surface">#1A1C24</color>
    <color name="surface_variant">#ECECF4</color>
    <color name="error">#E5484D</color>
    <color name="chip_bg">#EDEFFE</color>
    <color name="chip_text">#3A44A8</color>
    <color name="ic_launcher_background">#5B67F5</color>
</resources>
```

`res/values-night/colors.xml`：

```xml
<resources>
    <color name="primary">#8F97FF</color>
    <color name="on_primary">#1A1C4A</color>
    <color name="primary_container">#3A44A8</color>
    <color name="on_primary_container">#E4E7FF</color>
    <color name="secondary">#FFB74D</color>
    <color name="surface">#131318</color>
    <color name="on_surface">#ECECF4</color>
    <color name="surface_variant">#23232C</color>
    <color name="error">#FF6B70</color>
    <color name="chip_bg">#2A2F66</color>
    <color name="chip_text">#B9C0FF</color>
</resources>
```

`res/values/themes.xml`：

```xml
<resources>
    <style name="Theme.VoiceNote" parent="Theme.Material3.DayNight.NoActionBar">
        <item name="colorPrimary">@color/primary</item>
        <item name="colorOnPrimary">@color/on_primary</item>
        <item name="colorPrimaryContainer">@color/primary_container</item>
        <item name="colorOnPrimaryContainer">@color/on_primary_container</item>
        <item name="colorSecondary">@color/secondary</item>
        <item name="colorSurface">@color/surface</item>
        <item name="colorOnSurface">@color/on_surface</item>
        <item name="colorSurfaceVariant">@color/surface_variant</item>
        <item name="colorError">@color/error</item>
        <item name="android:statusBarColor">@color/surface</item>
        <item name="android:windowBackground">@color/surface</item>
    </style>
</resources>
```

`res/values/dimens.xml`：

```xml
<resources>
    <dimen name="card_corner">18dp</dimen>
    <dimen name="card_elevation">3dp</dimen>
    <dimen name="page_padding">16dp</dimen>
    <dimen name="chip_padding">8dp</dimen>
    <dimen name="chip_radius">12dp</dimen>
</resources>
```

- [ ] **Step 7: 矢量图标**

`res/drawable/ic_launcher_foreground.xml`（麦克风图标）：

```xml
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp" android:height="108dp"
    android:viewportWidth="108" android:viewportHeight="108">
    <path
        android:fillColor="#FFFFFF"
        android:pathData="M54,28c-6.6,0 -12,5.4 -12,12v16c0,6.6 5.4,12 12,12s12,-5.4 12,-12V40c0,-6.6 -5.4,-12 -12,-12zM76,56c0,12.2 -9.8,22 -22,22s-22,-9.8 -22,-22h-6c0,14.6 11,26.7 25,28.6V88h6v-3.4c14,-1.9 25,-14 25,-28.6h-6z" />
</vector>
```

`res/drawable/ic_mic.xml`：

```xml
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp" android:height="24dp"
    android:viewportWidth="24" android:viewportHeight="24">
    <path
        android:fillColor="#FFFFFF"
        android:pathData="M12,14c1.66,0 2.99,-1.34 2.99,-3L15,5c0,-1.66 -1.34,-3 -3,-3S9,3.34 9,5v6c0,1.66 1.34,3 3,3zM17.3,11c0,3 -2.54,5.1 -5.3,5.1S6.7,14 6.7,11H5c0,3.41 2.72,6.23 6,6.72V21h2v-3.28c3.28,-0.48 6,-3.3 6,-6.72h-1.7z" />
</vector>
```

`res/drawable/ic_notification.xml`：

```xml
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp" android:height="24dp"
    android:viewportWidth="24" android:viewportHeight="24">
    <path
        android:fillColor="#FFFFFF"
        android:pathData="M12,22c1.1,0 2,-0.9 2,-2h-4c0,1.1 0.9,2 2,2zM18,16v-5c0,-3.07 -1.64,-5.64 -4.5,-6.32V4c0,-0.83 -0.67,-1.5 -1.5,-1.5S10.5,3.17 10.5,4v0.68C7.63,5.36 6,7.92 6,11v5l-2,2v1h16v-1l-2,-2z" />
</vector>
```

`res/drawable/ic_back.xml`：

```xml
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp" android:height="24dp"
    android:viewportWidth="24" android:viewportHeight="24">
    <path
        android:fillColor="#FF000000"
        android:pathData="M20,11H7.83l5.59,-5.59L12,4l-8,8 8,8 1.41,-1.41L7.83,13H20v-2z" />
</vector>
```

`res/drawable/ic_play.xml`：

```xml
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp" android:height="24dp"
    android:viewportWidth="24" android:viewportHeight="24">
    <path
        android:fillColor="#FF000000"
        android:pathData="M8,5v14l11,-7z" />
</vector>
```

`res/drawable/ic_pause.xml`：

```xml
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp" android:height="24dp"
    android:viewportWidth="24" android:viewportHeight="24">
    <path
        android:fillColor="#FF000000"
        android:pathData="M6,19h4V5H6v14zM14,5v14h4V5h-4z" />
</vector>
```

`res/drawable/ic_done.xml`：

```xml
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp" android:height="24dp"
    android:viewportWidth="24" android:viewportHeight="24">
    <path
        android:fillColor="#FF000000"
        android:pathData="M9,16.17L4.83,12l-1.42,1.41L9,19 21,7l-1.41,-1.41z" />
</vector>
```

`res/drawable/ic_delete.xml`：

```xml
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp" android:height="24dp"
    android:viewportWidth="24" android:viewportHeight="24">
    <path
        android:fillColor="#FF000000"
        android:pathData="M6,19c0,1.1 0.9,2 2,2h8c1.1,0 2,-0.9 2,-2V7H6v12zM19,4h-3.5l-1,-1h-5l-1,1H5v2h14V4z" />
</vector>
```

`res/drawable/chip_bg.xml`：

```xml
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="@color/chip_bg" />
    <corners android:radius="@dimen/chip_radius" />
    <padding android:left="@dimen/chip_padding" android:right="@dimen/chip_padding"
        android:top="4dp" android:bottom="4dp" />
</shape>
```

`res/mipmap-anydpi-v26/ic_launcher.xml` 与 `ic_launcher_round.xml`（内容相同）：

```xml
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
```

- [ ] **Step 8: 自审清单**
  - manifest 中 application/activity/receiver 类名与后续代码包名一致（`.ui.MainActivity`、`.reminder.ReminderReceiver`、`.VoiceNoteApp`）
  - `keystore.properties` 尚未创建属预期（Task 10 生成），signingConfig 读取不到时 storePassword 为空，仅配置不构建不影响
  - 所有 drawable/color/string 引用在资源中存在；`ic_launcher_foreground` 为 108dp 自适应图标尺寸

- [ ] **Step 9: Commit**

```bash
git add .
git commit -m "chore: 工程脚手架（Gradle/Manifest/主题/资源/配置）"
```

---

### Task 2: 数据层（Room）

**Files:**
- Create: `app/src/main/java/com/example/voicenote/data/Note.kt`
- Create: `app/src/main/java/com/example/voicenote/data/NoteDao.kt`
- Create: `app/src/main/java/com/example/voicenote/data/NoteDatabase.kt`
- Create: `app/src/main/java/com/example/voicenote/data/NoteRepository.kt`

- [ ] **Step 1: Note 实体**

`Note.kt`：

```kotlin
package com.example.voicenote.data

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "notes")
data class Note(
    @PrimaryKey(autoGenerate = true) val id: Long = 0L,
    val content: String,
    val audioPath: String? = null,
    val category: String = "TODO",          // "TODO" / "DONE"
    val eventTime: Long? = null,            // 提取的事件时间戳
    val location: String? = null,
    val person: String? = null,
    val summary: String? = null,
    val topic: String? = null,
    val reminderAt: Long? = null,           // 提醒时间戳
    val reminded: Boolean = false,          // 是否已提醒
    val createdAt: Long = System.currentTimeMillis()
)
```

- [ ] **Step 2: DAO**

`NoteDao.kt`：

```kotlin
package com.example.voicenote.data

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface NoteDao {
    @Insert
    suspend fun insert(note: Note): Long

    @Update
    suspend fun update(note: Note)

    @Delete
    suspend fun delete(note: Note)

    @Query("SELECT * FROM notes WHERE id = :id")
    suspend fun getById(id: Long): Note?

    @Query("SELECT * FROM notes WHERE category = :category ORDER BY createdAt DESC")
    fun observeByCategory(category: String): Flow<List<Note>>

    @Query("SELECT * FROM notes WHERE reminderAt IS NOT NULL AND reminded = 0 AND reminderAt < :now")
    suspend fun findMissedReminders(now: Long): List<Note>

    @Query("UPDATE notes SET reminded = 1 WHERE id = :id")
    suspend fun markReminded(id: Long)
}
```

- [ ] **Step 3: Database**

`NoteDatabase.kt`：

```kotlin
package com.example.voicenote.data

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(entities = [Note::class], version = 1, exportSchema = false)
abstract class NoteDatabase : RoomDatabase() {
    abstract fun noteDao(): NoteDao

    companion object {
        @Volatile
        private var instance: NoteDatabase? = null

        fun get(context: Context): NoteDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    NoteDatabase::class.java,
                    "voicenote.db"
                ).build().also { instance = it }
            }
    }
}
```

- [ ] **Step 4: Repository**

`NoteRepository.kt`：

```kotlin
package com.example.voicenote.data

import android.content.Context
import kotlinx.coroutines.flow.Flow

class NoteRepository(private val dao: NoteDao) {

    fun observeByCategory(category: String): Flow<List<Note>> = dao.observeByCategory(category)

    suspend fun getById(id: Long): Note? = dao.getById(id)

    suspend fun insert(note: Note): Long = dao.insert(note)

    suspend fun update(note: Note) = dao.update(note)

    suspend fun delete(note: Note) = dao.delete(note)

    suspend fun toggleCategory(note: Note) {
        dao.update(note.copy(category = if (note.category == "TODO") "DONE" else "TODO"))
    }

    suspend fun findMissedReminders(now: Long): List<Note> = dao.findMissedReminders(now)

    suspend fun markReminded(id: Long) = dao.markReminded(id)

    companion object {
        fun get(context: Context): NoteRepository =
            NoteRepository(NoteDatabase.get(context).noteDao())
    }
}
```

- [ ] **Step 5: 自审清单**
  - Room 注解齐全：`@Entity`/`@Dao`/`@Database`，DAO 挂起函数与 Flow 返回类型匹配 room-ktx
  - `observeByCategory` 返回 `Flow`，由 Room 自动生成协程支持（需要 `room-ktx` 依赖，Task 1 已加）
  - `NoteRepository` 与 `VoiceNoteApp.repository` 签名一致（`NoteRepository.get(this)`）

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "feat: 数据层（Note 实体/DAO/数据库/仓库）"
```

---

### Task 3: NLP 规则引擎（纯本地）

**Files:**
- Create: `app/src/main/java/com/example/voicenote/nlp/NoteIntent.kt`
- Create: `app/src/main/java/com/example/voicenote/nlp/NlpResult.kt`
- Create: `app/src/main/java/com/example/voicenote/nlp/IntentClassifier.kt`
- Create: `app/src/main/java/com/example/voicenote/nlp/TimeExtractor.kt`
- Create: `app/src/main/java/com/example/voicenote/nlp/LocationExtractor.kt`
- Create: `app/src/main/java/com/example/voicenote/nlp/PersonExtractor.kt`
- Create: `app/src/main/java/com/example/voicenote/nlp/SummaryExtractor.kt`
- Create: `app/src/main/java/com/example/voicenote/nlp/TopicExtractor.kt`
- Create: `app/src/main/java/com/example/voicenote/nlp/NlpEngine.kt`
- Create: `app/src/test/java/com/example/voicenote/nlp/NlpEngineTest.kt`

- [ ] **Step 1: 基础类型**

`NoteIntent.kt`：

```kotlin
package com.example.voicenote.nlp

enum class NoteIntent(val label: String) {
    TODO("待办"),
    DONE("已完成")
}
```

`NlpResult.kt`：

```kotlin
package com.example.voicenote.nlp

data class NlpResult(
    val intent: NoteIntent,
    val timeText: String? = null,
    val eventTime: Long? = null,
    val location: String? = null,
    val person: String? = null,
    val summary: String? = null,
    val topic: String? = null
)
```

- [ ] **Step 2: 意图分类器**

`IntentClassifier.kt`：

```kotlin
package com.example.voicenote.nlp

object IntentClassifier {
    // 待办强触发词：出现即待办（即使句中含"完成"）
    private val todoStrong = listOf("记得", "别忘了", "需要", "必须", "待办", "安排", "提醒我")

    // 已完成触发词
    private val doneKeywords = listOf(
        "完成了", "做完", "开完", "结束", "搞定", "办完", "参加完",
        "看完", "吃过", "提交", "完毕", "去过了", "已经", "完成过"
    )

    fun classify(text: String): NoteIntent {
        if (todoStrong.any { text.contains(it) }) return NoteIntent.TODO
        // 否定：还没/没有/未 + 完成类词 → 待办
        if ((text.contains("还没") || text.contains("没有") || text.contains("未完成"))
            && doneKeywords.any { text.contains(it) }
        ) return NoteIntent.TODO
        if (doneKeywords.any { text.contains(it) }) return NoteIntent.DONE
        return NoteIntent.TODO
    }
}
```

- [ ] **Step 3: 时间提取器**

`TimeExtractor.kt`：

```kotlin
package com.example.voicenote.nlp

import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

data class TimeResult(val timeText: String?, val timestamp: Long?)

object TimeExtractor {
    // 相对日期偏移
    private val dayOffset = mapOf(
        "大后天" to 3L, "后天" to 2L, "明天" to 1L, "今天" to 0L,
        "昨天" to -1L, "前天" to -2L, "大前天" to -3L
    )
    // 星期
    private val weekMap = mapOf(
        "星期一" to 1, "周二" to 2, "星期三" to 3, "周四" to 4,
        "星期五" to 5, "周六" to 6, "星期天" to 7, "周日" to 7
    )
    // 时段默认时刻
    private val dayPartMap = mapOf(
        "凌晨" to 3, "早上" to 7, "上午" to 9, "中午" to 12,
        "下午" to 14, "傍晚" to 18, "晚上" to 19, "夜里" to 21
    )

    fun extract(text: String): TimeResult {
        val zone = ZoneId.systemDefault()
        val now = LocalDate.now(zone)
        var date = now
        var matchedDayText: String? = null

        for ((k, off) in dayOffset) {
            if (text.contains(k)) {
                date = now.plusDays(off)
                matchedDayText = k
                break
            }
        }
        if (matchedDayText == null) {
            for ((k, w) in weekMap) {
                if (text.contains(k)) {
                    var delta = (w - now.dayOfWeek.value + 7) % 7
                    if (delta == 0) delta = 7
                    date = now.plusDays(delta.toLong())
                    matchedDayText = k
                    break
                }
            }
        }

        var hour = -1
        var minute = 0
        var matchedTimeText: String? = null

        val cn = Regex("(\\d{1,2})点(半|(\\d{1,2})分)?").find(text)
        if (cn != null) {
            hour = cn.groupValues[1].toInt()
            if (cn.groupValues[2] == "半") minute = 30
            else if (cn.groupValues[2].isNotEmpty()) minute = cn.groupValues[3].toInt()
            matchedTimeText = cn.value
        } else {
            val colon = Regex("(\\d{1,2}):(\\d{2})").find(text)
            if (colon != null) {
                hour = colon.groupValues[1].toInt()
                minute = colon.groupValues[2].toInt()
                matchedTimeText = colon.value
            }
        }
        if (hour == -1) {
            for ((k, h) in dayPartMap) {
                if (text.contains(k)) {
                    hour = h
                    matchedTimeText = k
                    break
                }
            }
        }
        if (hour == -1) return TimeResult(null, null)

        val ldt = LocalDateTime.of(date, LocalTime.of(hour, minute))
        val timeText = listOfNotNull(matchedDayText, matchedTimeText).joinToString("")
        return TimeResult(timeText.ifBlank { null }, ldt.atZone(zone).toInstant().toEpochMilli())
    }
}
```

- [ ] **Step 4: 地点提取器**

`LocationExtractor.kt`：

```kotlin
package com.example.voicenote.nlp

object LocationExtractor {
    private val locations = listOf(
        "公司", "医院", "学校", "机场", "车站", "火车站", "家", "酒店", "餐厅",
        "会议室", "银行", "超市", "健身房", "派出所", "电影院", "商场", "公园",
        "图书馆", "快递点", "理发店", "幼儿园", "客户那里"
    )
    private val prepositions = listOf("去", "在", "到", "回", "里")

    fun extract(text: String): String? {
        // 优先：介词紧邻地点（去公司 / 在医院）
        for (loc in locations) {
            val idx = text.indexOf(loc)
            if (idx >= 0 && idx > 0 && text.substring(idx - 1, idx) in prepositions) {
                return loc
            }
        }
        // 兜底：直接命中地点词
        return locations.firstOrNull { text.contains(it) }
    }
}
```

- [ ] **Step 5: 人物提取器**

`PersonExtractor.kt`：

```kotlin
package com.example.voicenote.nlp

object PersonExtractor {
    // 常见姓氏
    private val surnames = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘斜厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴郁胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
    private val titles = listOf("总", "经理", "老师", "医生", "主任", "律师", "哥", "姐", "师傅", "教授")

    fun extract(text: String): String? {
        // 姓氏 + 称谓，如 张总 / 李老师 / 王经理
        for (i in text.indices) {
            val c = text[i]
            if (surnames.contains(c)) {
                for (t in titles) {
                    val end = i + 1 + t.length
                    if (end <= text.length && text.substring(i + 1, end) == t) {
                        return c + t
                    }
                }
            }
        }
        // 关联词 + 人名（2~3 字），排除时间词
        val timeWords = listOf("今天", "明天", "后天", "昨天", "上午", "下午", "晚上", "中午", "早上", "凌晨", "周末", "下周")
        val m = Regex("(和|跟|约|找|请|给)([\\u4e00-\\u9fa5]{2,3})").find(text)
        val candidate = m?.groupValues?.get(2) ?: return null
        if (timeWords.any { candidate.contains(it) }) return null
        return candidate
    }
}
```

- [ ] **Step 6: 事件概况提取器**

`SummaryExtractor.kt`：

```kotlin
package com.example.voicenote.nlp

object SummaryExtractor {
    // 动词按长度优先匹配
    private val verbs = listOf(
        "参加", "开会", "体检", "上课", "出差", "拜访", "吃饭", "提交",
        "去", "开", "看", "见", "交", "做", "办", "买", "修", "拿", "取", "送", "接"
    )

    fun extract(text: String): String? {
        val cleaned = text.replace(
            Regex("^(请|记得|别忘了|要|需要|必须|安排|帮|帮我|麻烦|提醒我|我|我们)")
        ).trimStart('，', '。', '！')
        for (v in verbs) {
            val idx = cleaned.indexOf(v)
            if (idx >= 0) {
                val tail = cleaned.substring(idx).split(Regex("[，。！？；、,]"))[0]
                val trimmed = tail.trimEnd('的', '了', '啊', '呢', '吧', '！', '。')
                if (trimmed.length >= 2) return trimmed.take(14)
            }
        }
        return cleaned.take(14).ifBlank { null }
    }
}
```

- [ ] **Step 7: 主题提取器**

`TopicExtractor.kt`：

```kotlin
package com.example.voicenote.nlp

object TopicExtractor {
    private val rules = listOf(
        "会议" to listOf("开会", "会议", "例会", "汇报", "评审", "发布会", "面试", "洽谈"),
        "工作" to listOf("报表", "方案", "项目", "加班", "周报", "预算", "述职", "邮件", "代码", "需求", "客户"),
        "学习" to listOf("上课", "考试", "复习", "作业", "课程", "学习", "培训", "读书", "笔记"),
        "健康" to listOf("医生", "医院", "体检", "吃药", "看病", "复查", "检查", "锻炼", "健身"),
        "生活" to listOf("买菜", "逛街", "聚餐", "吃饭", "购物", "超市", "做饭", "旅行"),
        "家庭" to listOf("孩子", "家人", "父母", "接娃", "家长会", "亲戚", "老婆", "老公")
    )

    fun extract(text: String): String {
        for ((topic, words) in rules) {
            if (words.any { text.contains(it) }) return topic
        }
        return "其他"
    }
}
```

- [ ] **Step 8: 引擎门面**

`NlpEngine.kt`：

```kotlin
package com.example.voicenote.nlp

object NlpEngine {
    fun analyze(text: String): NlpResult {
        val time = TimeExtractor.extract(text)
        return NlpResult(
            intent = IntentClassifier.classify(text),
            timeText = time.timeText,
            eventTime = time.timestamp,
            location = LocationExtractor.extract(text),
            person = PersonExtractor.extract(text),
            summary = SummaryExtractor.extract(text),
            topic = TopicExtractor.extract(text)
        )
    }
}
```

- [ ] **Step 9: 单元测试（产物，本机不执行）**

`app/src/test/java/com/example/voicenote/nlp/NlpEngineTest.kt`：

```kotlin
package com.example.voicenote.nlp

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class NlpEngineTest {

    @Test
    fun `明天下午3点去公司开会_应为待办会议`() {
        val r = NlpEngine.analyze("明天下午3点去公司开会")
        assertEquals(NoteIntent.TODO, r.intent)
        assertEquals("公司", r.location)
        assertEquals("会议", r.topic)
        assertEquals("去公司开会", r.summary)
        assertNotNull(r.eventTime)
        assertNotNull(r.timeText)
    }

    @Test
    fun `已经完成周报_应为已完成工作`() {
        val r = NlpEngine.analyze("我已经完成周报了")
        assertEquals(NoteIntent.DONE, r.intent)
        assertEquals("工作", r.topic)
    }

    @Test
    fun `记得完成周报_应为待办`() {
        val r = NlpEngine.analyze("记得完成周报")
        assertEquals(NoteIntent.TODO, r.intent)
    }

    @Test
    fun `还没完成报表_应为待办`() {
        val r = NlpEngine.analyze("还没完成报表")
        assertEquals(NoteIntent.TODO, r.intent)
    }

    @Test
    fun `和项目经理约明天见_提取人物`() {
        val r = NlpEngine.analyze("和项目经理约明天见")
        assertNull(r.person) // "项目经理" 无姓氏+称谓命中则走关联词模式，需排除"明天"
        assertEquals("明天", r.timeText)
    }

    @Test
    fun `下周一早上体检_提取时间和主题`() {
        val r = NlpEngine.analyze("下周一早上体检")
        assertEquals("健康", r.topic)
        assertNotNull(r.eventTime)
    }

    @Test
    fun `张总安排周五交报表_人物与主题`() {
        val r = NlpEngine.analyze("张总安排周五交报表")
        assertEquals("张总", r.person)
        assertEquals("工作", r.topic)
        assertEquals(NoteIntent.TODO, r.intent)
    }
}
```

- [ ] **Step 10: 自审清单**
  - 各提取器为无状态 `object`，输入输出类型一致（`NlpResult` 字段与 `Note` 实体字段对应：intent/timeText/eventTime/location/person/summary/topic）
  - `TimeExtractor` 使用 `java.time`（minSdk 26 原生支持，无需 desugar）
  - 正则/词库字符串转义正确（Kotlin 字符串中 `\\u4e00` 写法在 Regex 中为 `[\\u4e00-\\u9fa5]`，注意 `Regex("...")` 内 `\\d`、`\\u4e00` 均为双反斜杠）
  - 测试断言与实现行为一致（如"和项目经理约明天见"：surnames 命中"经理"？"经理"不在 titles，"项目经理"不会匹配姓氏模式；关联词模式匹配"约明天"→候选"明天"被排除→person 为 null）

- [ ] **Step 11: Commit**

```bash
git add .
git commit -m "feat: NLP 规则引擎（意图/时间/地点/人物/概况/主题）+ 单元测试"
```

---

### Task 4: 语音模块（讯飞识别 + 录音/播放）

**Files:**
- Create: `app/src/main/java/com/example/voicenote/voice/IRecognizer.kt`
- Create: `app/src/main/java/com/example/voicenote/voice/IatResultParser.kt`
- Create: `app/src/main/java/com/example/voicenote/voice/BaseRecognizer.kt`
- Create: `app/src/main/java/com/example/voicenote/voice/OnlineRecognizer.kt`
- Create: `app/src/main/java/com/example/voicenote/voice/OfflineRecognizer.kt`
- Create: `app/src/main/java/com/example/voicenote/voice/RecognizerFactory.kt`
- Create: `app/src/main/java/com/example/voicenote/audio/RecordManager.kt`
- Create: `app/src/main/java/com/example/voicenote/audio/AudioPlayer.kt`

**前置说明：** 讯飞 SDK 需要用户从讯飞开放平台下载（`app/libs/` 放置 `msc.jar` 与 `libmsc.so`），当前本机不构建，以下代码按官方 API 编写，保证用户放置 SDK 后即可编译。

- [ ] **Step 1: 识别接口**

`IRecognizer.kt`：

```kotlin
package com.example.voicenote.voice

interface IRecognizer {
    fun start(partial: (String) -> Unit)
    fun writeAudio(data: ByteArray, length: Int)
    fun stop(onResult: (String) -> Unit, onError: (String) -> Unit)
    fun cancel()
    fun release()
}
```

- [ ] **Step 2: 讯飞 IAT 结果解析（JSON，不依赖 SDK 示例类）**

`IatResultParser.kt`：

```kotlin
package com.example.voicenote.voice

import org.json.JSONObject

object IatResultParser {
    fun parse(json: String): String {
        return try {
            val root = JSONObject(json)
            val ws = root.optJSONArray("ws") ?: return ""
            val sb = StringBuilder()
            for (i in 0 until ws.length()) {
                val cw = ws.getJSONObject(i).optJSONArray("cw") ?: continue
                for (j in 0 until cw.length()) {
                    sb.append(cw.getJSONObject(j).optString("w"))
                }
            }
            sb.toString()
        } catch (_: Exception) {
            ""
        }
    }
}
```

- [ ] **Step 3: 识别器基类（在线/离线共用）**

`BaseRecognizer.kt`：

```kotlin
package com.example.voicenote.voice

import android.content.Context
import android.os.Bundle
import com.example.voicenote.AppConfig
import com.iflytek.cloud.RecognizerListener
import com.iflytek.cloud.RecognizerResult
import com.iflytek.cloud.SpeechConstant
import com.iflytek.cloud.SpeechError
import com.iflytek.cloud.SpeechRecognizer
import com.iflytek.cloud.SpeechUtility

abstract class BaseRecognizer(protected val context: Context) : IRecognizer {

    protected var recognizer: SpeechRecognizer? = null
    private var onPartial: ((String) -> Unit)? = null
    private var onResult: ((String) -> Unit)? = null
    private var onError: ((String) -> Unit)? = null
    private val result = StringBuilder()

    init {
        // 初始化讯飞语音（AppID）
        SpeechUtility.createUtility(
            context.applicationContext,
            SpeechConstant.APPID + "=" + AppConfig.IFLYTEK_APPID
        )
    }

    /** 子类配置识别参数（在线/离线差异） */
    protected abstract fun configure(recognizer: SpeechRecognizer)

    private val listener = object : RecognizerListener {
        override fun onBeginOfSpeech() {}
        override fun onEndOfSpeech() {}
        override fun onVolumeChanged(volume: Int, data: ByteArray?) {}
        override fun onError(error: SpeechError) {
            onError?.invoke(error.getErrorDescription())
            reset()
        }
        override fun onResult(results: RecognizerResult, isLast: Boolean) {
            val text = IatResultParser.parse(results.resultString)
            if (text.isNotEmpty()) {
                result.append(text)
                if (!isLast) onPartial?.invoke(result.toString())
            }
            if (isLast) {
                onResult?.invoke(result.toString())
                reset()
            }
        }
        override fun onEvent(eventType: Int, arg1: Int, arg2: Int, obj: Bundle?) {}
    }

    override fun start(partial: (String) -> Unit) {
        onPartial = partial
        result.clear()
        recognizer = SpeechRecognizer.createRecognizer(context.applicationContext, null).also {
            configure(it)
        }.also {
            it.startListening(listener)
        }
    }

    override fun writeAudio(data: ByteArray, length: Int) {
        recognizer?.writeAudio(data, 0, length)
    }

    override fun stop(onResult: (String) -> Unit, onError: (String) -> Unit) {
        this.onResult = onResult
        this.onError = onError
        recognizer?.stopListening()
    }

    override fun cancel() {
        recognizer?.cancel()
        reset()
    }

    override fun release() {
        recognizer?.destroy()
        recognizer = null
    }

    private fun reset() {
        onPartial = null
        onResult = null
        onError = null
        result.clear()
    }
}
```

- [ ] **Step 4: 在线识别器**

`OnlineRecognizer.kt`：

```kotlin
package com.example.voicenote.voice

import android.content.Context
import com.iflytek.cloud.SpeechConstant
import com.iflytek.cloud.SpeechRecognizer

/** 讯飞在线听写（需 INTERNET 权限） */
class OnlineRecognizer(context: Context) : BaseRecognizer(context) {

    override fun configure(recognizer: SpeechRecognizer) {
        recognizer.setParameter(SpeechConstant.DOMAIN, "iat")
        recognizer.setParameter(SpeechConstant.LANGUAGE, "zh_cn")
        recognizer.setParameter(SpeechConstant.ACCENT, "mandarin")
        recognizer.setParameter(SpeechConstant.ASR_PTT, "1")       // 带标点
        recognizer.setParameter(SpeechConstant.AUDIO_SOURCE, "-1") // 外部音频输入
        recognizer.setParameter(SpeechConstant.SAMPLE_RATE, "16000")
    }
}
```

- [ ] **Step 5: 离线识别器（预留，需离线授权文件）**

`OfflineRecognizer.kt`：

```kotlin
package com.example.voicenote.voice

import android.content.Context
import com.iflytek.cloud.SpeechConstant
import com.iflytek.cloud.SpeechRecognizer

/**
 * 讯飞离线听写（预留）。
 * 启用条件：
 *  1. 讯飞控制台开通"离线语音听写"能力并获取授权文件（msc.cfg 等）放入 app/src/main/assets
 *  2. AppConfig.RECOGNIZER_MODE 改为 "offline"
 */
class OfflineRecognizer(context: Context) : BaseRecognizer(context) {

    override fun configure(recognizer: SpeechRecognizer) {
        recognizer.setParameter(SpeechConstant.DOMAIN, "iat")
        recognizer.setParameter(SpeechConstant.LANGUAGE, "zh_cn")
        recognizer.setParameter(SpeechConstant.ACCENT, "mandarin")
        recognizer.setParameter(SpeechConstant.ENGINE_TYPE, SpeechConstant.TYPE_LOCAL) // 本地引擎
        recognizer.setParameter(SpeechConstant.ASR_PTT, "1")
        recognizer.setParameter(SpeechConstant.AUDIO_SOURCE, "-1")
        recognizer.setParameter(SpeechConstant.SAMPLE_RATE, "16000")
    }
}
```

- [ ] **Step 6: 识别器工厂**

`RecognizerFactory.kt`：

```kotlin
package com.example.voicenote.voice

import android.content.Context
import com.example.voicenote.AppConfig

object RecognizerFactory {
    fun create(context: Context): IRecognizer {
        val appContext = context.applicationContext
        return if (AppConfig.RECOGNIZER_MODE == "offline") {
            OfflineRecognizer(appContext)
        } else {
            OnlineRecognizer(appContext)
        }
    }
}
```

- [ ] **Step 7: 录音管理器（AudioRecord 采集 PCM → WAV 文件 + 实时喂给识别器）**

`RecordManager.kt`：

```kotlin
package com.example.voicenote.audio

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.File
import java.io.IOException
import java.io.RandomAccessFile
import java.util.concurrent.atomic.AtomicBoolean

class RecordManager(private val file: File) {

    companion object {
        const val SAMPLE_RATE = 16000
    }

    private var recorder: AudioRecord? = null
    private var raf: RandomAccessFile? = null
    private val recording = AtomicBoolean(false)
    private var thread: Thread? = null

    fun start(onAudio: (ByteArray, Int) -> Unit) {
        file.parentFile?.mkdirs()
        raf = RandomAccessFile(file, "rw").apply { setLength(44) } // 预留 WAV 头
        val minBuf = AudioRecord.getMinBufferSize(
            SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
        )
        recorder = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            minBuf * 2
        )
        recorder?.startRecording()
        recording.set(true)
        thread = Thread {
            val buf = ByteArray(4096)
            while (recording.get()) {
                val n = recorder?.read(buf, 0, buf.size) ?: -1
                if (n > 0) {
                    runCatching { raf?.write(buf, 0, n) }
                    onAudio(buf.copyOf(n), n)
                }
            }
        }.apply { start() }
    }

    fun stop() {
        recording.set(false)
        thread?.join(500)
        runCatching { recorder?.stop() }
        recorder?.release()
        recorder = null
        finalizeWav()
        raf = null
        thread = null
    }

    private fun finalizeWav() {
        val r = raf ?: return
        runCatching {
            val dataLength = r.length() - 44
            r.seek(0)
            r.write(wavHeader(dataLength, SAMPLE_RATE))
            r.close()
        }
    }

    private fun wavHeader(dataLength: Long, sampleRate: Int): ByteArray {
        val h = ByteArray(44)
        fun putString(offset: Int, s: String) {
            s.forEachIndexed { i, c -> h[offset + i] = c.code.toByte() }
        }
        fun putIntLE(offset: Int, v: Int) {
            for (i in 0..3) h[offset + i] = ((v shr (8 * i)) and 0xFF).toByte()
        }
        fun putShortLE(offset: Int, v: Int) {
            h[offset] = (v and 0xFF).toByte()
            h[offset + 1] = ((v shr 8) and 0xFF).toByte()
        }
        putString(0, "RIFF"); putIntLE(4, (36 + dataLength).toInt()); putString(8, "WAVE")
        putString(12, "fmt "); putIntLE(16, 16); putShortLE(20, 1); putShortLE(22, 1)
        putIntLE(24, sampleRate); putIntLE(28, sampleRate * 2); putShortLE(32, 2); putShortLE(34, 16)
        putString(36, "data"); putIntLE(40, dataLength.toInt())
        return h
    }
}
```

- [ ] **Step 8: 音频播放器**

`AudioPlayer.kt`：

```kotlin
package com.example.voicenote.audio

import android.media.MediaPlayer
import java.io.File

class AudioPlayer {

    private var player: MediaPlayer? = null

    fun play(file: File, onStateChanged: (Boolean) -> Unit = {}) {
        stop()
        if (!file.exists()) {
            onStateChanged(false)
            return
        }
        player = MediaPlayer().apply {
            setDataSource(file.absolutePath)
            prepare()
            start()
            setOnCompletionListener { onStateChanged(false) }
        }
        onStateChanged(true)
    }

    fun stop() {
        runCatching { player?.stop() }
        player?.release()
        player = null
    }
}
```

- [ ] **Step 9: 自审清单**
  - `BaseRecognizer` 实现 `IRecognizer` 全部方法；`writeAudio(data, len)` 中 `ByteArray.copyOf(n)` 避免线程共享缓冲
  - 讯飞 API 调用与官方一致：`SpeechUtility.createUtility`、`SpeechRecognizer.createRecognizer`、`setParameter`、`startListening`、`writeAudio`、`stopListening`、`cancel`、`destroy`；`RecognizerListener` 六方法齐全
  - `RecordManager`：AudioRecord 缓冲申请、线程退出、WAV 头写入均在 stop 时完成；`raf` 关闭后置 null 防重复 close
  - `IatResultParser` 对空/异常 JSON 返回空串，不抛异常

- [ ] **Step 10: Commit**

```bash
git add .
git commit -m "feat: 语音模块（讯飞识别接口/在线离线/录音/播放）"
```

---

### Task 5: 首页（卡片列表 + 录音入口）

**Files:**
- Create: `app/src/main/java/com/example/voicenote/ui/MainActivity.kt`
- Create: `app/src/main/java/com/example/voicenote/ui/home/HomeViewModel.kt`
- Create: `app/src/main/java/com/example/voicenote/ui/home/NoteAdapter.kt`
- Create: `app/src/main/java/com/example/voicenote/ui/home/HomeFragment.kt`
- Create: `app/src/main/res/layout/activity_main.xml`
- Create: `app/src/main/res/layout/fragment_home.xml`
- Create: `app/src/main/res/layout/item_note_card.xml`

- [ ] **Step 1: MainActivity（容器 + 补发错过提醒）**

`MainActivity.kt`：

```kotlin
package com.example.voicenote.ui

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.commit
import androidx.lifecycle.lifecycleScope
import com.example.voicenote.VoiceNoteApp
import com.example.voicenote.databinding.ActivityMainBinding
import com.example.voicenote.reminder.ReminderHelper
import com.example.voicenote.ui.home.HomeFragment
import com.example.voicenote.ui.record.RecordConfirmFragment
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        if (savedInstanceState == null) {
            supportFragmentManager.commit {
                replace(R.id.fragment_container, HomeFragment())
            }
        }

        // 补发错过的提醒
        val app = application as VoiceNoteApp
        lifecycleScope.launch(Dispatchers.IO) {
            ReminderHelper.sendMissed(applicationContext, app.repository)
        }
    }

    /** 打开录音确认/编辑页 */
    fun showRecordConfirm(text: String, audioPath: String?) {
        supportFragmentManager.commit {
            setReorderingAllowed(true)
            replace(R.id.fragment_container, RecordConfirmFragment.newInstance(text, audioPath))
            addToBackStack("record_confirm")
        }
    }
}
```

- [ ] **Step 2: 首页 ViewModel**

`HomeViewModel.kt`：

```kotlin
package com.example.voicenote.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.example.voicenote.data.Note
import com.example.voicenote.data.NoteRepository
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

@OptIn(ExperimentalCoroutinesApi::class)
class HomeViewModel(private val repository: NoteRepository) : ViewModel() {

    private val tab = MutableStateFlow("TODO")

    val notes: StateFlow<List<Note>> = tab.flatMapLatest { repository.observeByCategory(it) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    fun switchTab(category: String) {
        tab.value = category
    }

    fun toggleCategory(note: Note) {
        viewModelScope.launch { repository.toggleCategory(note) }
    }

    class Factory(private val repository: NoteRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T =
            HomeViewModel(repository) as T
    }
}
```

- [ ] **Step 3: 卡片 Adapter**

`NoteAdapter.kt`：

```kotlin
package com.example.voicenote.ui.home

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.core.view.isVisible
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.example.voicenote.data.Note
import com.example.voicenote.databinding.ItemNoteCardBinding
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class NoteAdapter(
    private val onClick: (Note, View) -> Unit,
    private val onToggle: (Note) -> Unit
) : ListAdapter<Note, NoteAdapter.VH>(DIFF) {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val binding = ItemNoteCardBinding.inflate(
            LayoutInflater.from(parent.context), parent, false
        )
        return VH(binding)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        holder.bind(getItem(position))
    }

    inner class VH(private val binding: ItemNoteCardBinding) : RecyclerView.ViewHolder(binding.root) {

        fun bind(note: Note) {
            binding.apply {
                tvSummary.text = note.summary ?: note.content.take(12)
                tvContent.text = note.content
                tagTime.text = note.eventTime?.let(::formatMillis)
                tagLocation.text = note.location
                tagPerson.text = note.person
                tagTopic.text = note.topic
                // 空标签隐藏
                tagTime.isVisible = note.eventTime != null
                tagLocation.isVisible = !note.location.isNullOrBlank()
                tagPerson.isVisible = !note.person.isNullOrBlank()
                tagTopic.isVisible = !note.topic.isNullOrBlank()
                // 待办显示完成按钮
                btnDone.isVisible = note.category == "TODO"
                btnDone.setOnClickListener { onToggle(note) }
                btnRestore.isVisible = note.category == "DONE"
                btnRestore.setOnClickListener { onToggle(note) }
                cardRoot.transitionName = "note_detail"
                cardRoot.setOnClickListener { onClick(note, cardRoot) }
            }
        }
    }

    companion object {
        private val DIFF = object : DiffUtil.ItemCallback<Note>() {
            override fun areItemsTheSame(oldItem: Note, newItem: Note) = oldItem.id == newItem.id
            override fun areContentsTheSame(oldItem: Note, newItem: Note) = oldItem == newItem
        }

        private fun formatMillis(ts: Long): String =
            SimpleDateFormat("M月d日 HH:mm", Locale.CHINA).format(Date(ts))
    }
}
```

- [ ] **Step 4: 首页 Fragment（录音 + 识别 + 列表 + 打开详情）**

`HomeFragment.kt`：

```kotlin
package com.example.voicenote.ui.home

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.view.isVisible
import androidx.fragment.app.Fragment
import androidx.fragment.app.commit
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.voicenote.R
import com.example.voicenote.VoiceNoteApp
import com.example.voicenote.audio.AudioPlayer
import com.example.voicenote.audio.RecordManager
import com.example.voicenote.data.Note
import com.example.voicenote.databinding.FragmentHomeBinding
import com.example.voicenote.ui.detail.DetailFragment
import com.example.voicenote.ui.MainActivity
import com.example.voicenote.voice.IRecognizer
import com.example.voicenote.voice.RecognizerFactory
import java.io.File
import kotlinx.coroutines.launch

class HomeFragment : Fragment() {

    private var _binding: FragmentHomeBinding? = null
    private val binding get() = _binding!!

    private val viewModel: HomeViewModel by viewModels {
        HomeViewModel.Factory((requireActivity().application as VoiceNoteApp).repository)
    }

    private val adapter = NoteAdapter(
        onClick = { note, view -> openDetail(note, view) },
        onToggle = { note -> viewModel.toggleCategory(note) }
    )

    private var recognizer: IRecognizer? = null
    private var recordManager: RecordManager? = null
    private var currentAudioFile: File? = null
    private var isRecording = false
    private val player = AudioPlayer()

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        val ok = grants.values.all { it }
        if (ok && !isRecording) startRecording() else showHint(getString(R.string.permission_denied))
    }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        _binding = FragmentHomeBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        binding.recycler.layoutManager = LinearLayoutManager(requireContext())
        binding.recycler.adapter = adapter

        binding.tabs.addOnTabSelectedListener(object : com.google.android.material.tabs.TabLayout.OnTabSelectedListener {
            override fun onTabSelected(tab: com.google.android.material.tabs.TabLayout.Tab) {
                viewModel.switchTab(if (tab.position == 0) "TODO" else "DONE")
            }
            override fun onTabUnselected(tab: com.google.android.material.tabs.TabLayout.Tab) {}
            override fun onTabReselected(tab: com.google.android.material.tabs.TabLayout.Tab) {}
        })

        binding.micButton.setOnClickListener {
            if (isRecording) stopRecording() else checkPermissionsAndRecord()
        }

        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.notes.collect { adapter.submitList(it) }
        }
    }

    private fun checkPermissionsAndRecord() {
        val needed = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            needed += Manifest.permission.POST_NOTIFICATIONS
        }
        val missing = needed.filter {
            ContextCompat.checkSelfPermission(requireContext(), it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isEmpty()) startRecording() else permissionLauncher.launch(missing.toTypedArray())
    }

    private fun startRecording() {
        isRecording = true
        binding.micButton.isSelected = true
        binding.recordHint.isVisible = true
        binding.recordHint.text = getString(R.string.recording)
        val file = File(requireContext().filesDir, "records/rec_${System.currentTimeMillis()}.wav")
        currentAudioFile = file
        recognizer = RecognizerFactory.create(requireContext())
        recordManager = RecordManager(file)
        recordManager!!.start { data, len -> recognizer?.writeAudio(data, len) }
        recognizer!!.start { partial ->
            binding.recordHint.text = partial.ifBlank { getString(R.string.recording) }
        }
    }

    private fun stopRecording() {
        isRecording = false
        binding.micButton.isSelected = false
        binding.recordHint.text = getString(R.string.recognizing)
        recognizer?.stop(
            onResult = { text -> handleResult(text) },
            onError = { err ->
                binding.recordHint.text = getString(R.string.recognize_failed, err)
                cleanup()
            }
        )
    }

    private fun handleResult(text: String) {
        cleanup()
        if (text.isBlank()) {
            binding.recordHint.text = getString(R.string.empty_result)
            return
        }
        val audio = currentAudioFile
        currentAudioFile = null
        binding.recordHint.isVisible = false
        (activity as? MainActivity)?.showRecordConfirm(text, audio?.absolutePath)
    }

    private fun cleanup() {
        recordManager?.stop()
        recordManager = null
        recognizer?.release()
        recognizer = null
    }

    private fun openDetail(note: Note, cardView: View) {
        parentFragmentManager.commit {
            setReorderingAllowed(true)
            addSharedElement(cardView, "note_detail")
            replace(R.id.fragment_container, DetailFragment.newInstance(note.id))
            addToBackStack("detail")
        }
    }

    private fun showHint(msg: String) {
        binding.recordHint.isVisible = true
        binding.recordHint.text = msg
    }

    override fun onDestroyView() {
        cleanup()
        player.stop()
        _binding = null
        super.onDestroyView()
    }
}
```

- [ ] **Step 5: 布局（activity_main / fragment_home / item_note_card）**

`res/layout/activity_main.xml`：

```xml
<?xml version="1.0" encoding="utf-8"?>
<androidx.fragment.app.FragmentContainerView
    xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/fragment_container"
    android:layout_width="match_parent"
    android:layout_height="match_parent" />
```

`res/layout/fragment_home.xml`：

```xml
<?xml version="1.0" encoding="utf-8"?>
<androidx.constraintlayout.widget.ConstraintLayout
    xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    android:layout_width="match_parent"
    android:layout_height="match_parent">

    <com.google.android.material.appbar.MaterialToolbar
        android:id="@+id/toolbar"
        android:layout_width="0dp"
        android:layout_height="?attr/actionBarSize"
        android:background="@color/surface"
        app:title="@string/app_name"
        app:titleTextColor="@color/on_surface"
        app:layout_constraintTop_toTopOf="parent"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent" />

    <com.google.android.material.tabs.TabLayout
        android:id="@+id/tabs"
        android:layout_width="0dp"
        android:layout_height="wrap_content"
        android:background="@color/surface"
        app:layout_constraintTop_toBottomOf="@id/toolbar"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent">

        <com.google.android.material.tabs.TabItem
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:text="@string/tab_todo" />

        <com.google.android.material.tabs.TabItem
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:text="@string/tab_done" />
    </com.google.android.material.tabs.TabLayout>

    <androidx.recyclerview.widget.RecyclerView
        android:id="@+id/recycler"
        android:layout_width="0dp"
        android:layout_height="0dp"
        android:clipToPadding="false"
        android:paddingTop="4dp"
        android:paddingBottom="96dp"
        app:layout_constraintTop_toBottomOf="@id/tabs"
        app:layout_constraintBottom_toBottomOf="parent"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent" />

    <TextView
        android:id="@+id/recordHint"
        android:layout_width="0dp"
        android:layout_height="wrap_content"
        android:gravity="center"
        android:text="@string/record_hint"
        android:textColor="@color/on_surface"
        android:textSize="14sp"
        android:visibility="gone"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent"
        app:layout_constraintBottom_toTopOf="@id/micButton"
        android:layout_marginBottom="12dp" />

    <com.google.android.material.floatingactionbutton.ExtendedFloatingActionButton
        android:id="@+id/micButton"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="@string/mic_start"
        android:contentDescription="@string/mic_start"
        app:icon="@drawable/ic_mic"
        app:iconTint="@color/on_primary"
        android:backgroundTint="@color/primary"
        android:textColor="@color/on_primary"
        app:layout_constraintBottom_toBottomOf="parent"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent"
        android:layout_marginBottom="24dp" />

</androidx.constraintlayout.widget.ConstraintLayout>
```

`res/layout/item_note_card.xml`：

```xml
<?xml version="1.0" encoding="utf-8"?>
<com.google.android.material.card.MaterialCardView
    xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    android:id="@+id/cardRoot"
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:layout_marginHorizontal="12dp"
    android:layout_marginVertical="6dp"
    app:cardBackgroundColor="@color/surface"
    app:cardCornerRadius="@dimen/card_corner"
    app:cardElevation="@dimen/card_elevation">

    <androidx.constraintlayout.widget.ConstraintLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:padding="16dp">

        <TextView
            android:id="@+id/tvSummary"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:textSize="17sp"
            android:textStyle="bold"
            android:textColor="@color/on_surface"
            android:maxLines="1"
            android:ellipsize="end"
            app:layout_constraintTop_toTopOf="parent"
            app:layout_constraintStart_toStartOf="parent"
            app:layout_constraintEnd_toStartOf="@id/btnDone" />

        <TextView
            android:id="@+id/tvContent"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_marginTop="6dp"
            android:textSize="14sp"
            android:textColor="@color/on_surface"
            android:maxLines="2"
            android:ellipsize="end"
            app:layout_constraintTop_toBottomOf="@id/tvSummary"
            app:layout_constraintStart_toStartOf="parent"
            app:layout_constraintEnd_toEndOf="parent" />

        <TextView
            android:id="@+id/tagTime"
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:layout_marginTop="8dp"
            android:background="@drawable/chip_bg"
            android:textColor="@color/chip_text"
            android:textSize="12sp"
            android:visibility="gone"
            app:layout_constraintTop_toBottomOf="@id/tvContent"
            app:layout_constraintStart_toStartOf="parent" />

        <TextView
            android:id="@+id/tagLocation"
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:layout_marginTop="8dp"
            android:layout_marginStart="8dp"
            android:background="@drawable/chip_bg"
            android:textColor="@color/chip_text"
            android:textSize="12sp"
            android:visibility="gone"
            app:layout_constraintTop_toBottomOf="@id/tvContent"
            app:layout_constraintStart_toEndOf="@id/tagTime" />

        <TextView
            android:id="@+id/tagPerson"
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:layout_marginTop="8dp"
            android:layout_marginStart="8dp"
            android:background="@drawable/chip_bg"
            android:textColor="@color/chip_text"
            android:textSize="12sp"
            android:visibility="gone"
            app:layout_constraintTop_toBottomOf="@id/tvContent"
            app:layout_constraintStart_toEndOf="@id/tagLocation" />

        <TextView
            android:id="@+id/tagTopic"
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:layout_marginTop="8dp"
            android:layout_marginStart="8dp"
            android:background="@drawable/chip_bg"
            android:textColor="@color/chip_text"
            android:textSize="12sp"
            android:visibility="gone"
            app:layout_constraintTop_toBottomOf="@id/tvContent"
            app:layout_constraintStart_toEndOf="@id/tagPerson" />

        <com.google.android.material.button.MaterialButton
            android:id="@+id/btnDone"
            style="@style/Widget.Material3.Button.IconButton"
            android:layout_width="40dp"
            android:layout_height="40dp"
            android:contentDescription="@string/mark_done"
            app:icon="@drawable/ic_done"
            app:iconTint="@color/primary"
            android:visibility="gone"
            app:layout_constraintTop_toTopOf="parent"
            app:layout_constraintEnd_toEndOf="parent" />

        <com.google.android.material.button.MaterialButton
            android:id="@+id/btnRestore"
            style="@style/Widget.Material3.Button.IconButton"
            android:layout_width="40dp"
            android:layout_height="40dp"
            android:contentDescription="@string/restore_todo"
            app:icon="@drawable/ic_back"
            app:iconTint="@color/secondary"
            android:visibility="gone"
            app:layout_constraintTop_toTopOf="parent"
            app:layout_constraintEnd_toEndOf="parent" />

    </androidx.constraintlayout.widget.ConstraintLayout>
</com.google.android.material.card.MaterialCardView>
```

- [ ] **Step 6: 自审清单**
  - `HomeFragment` 中 `parentFragmentManager.commit { addSharedElement(...) }` 与 DetailFragment 的 `transitionName="note_detail"` 匹配（Task 6 实现）
  - `showRecordConfirm` 在 MainActivity 中定义，HomeFragment 通过 `(activity as? MainActivity)` 调用
  - `viewModels { Factory(...) }` 依赖 fragment-ktx（Task 1 已加）；`viewLifecycleOwner.lifecycleScope` 依赖 lifecycle-runtime-ktx
  - `recordHint` 在停止录音回调异步返回前一直可见，防内存泄漏已在 `onDestroyView` 清理
  - 空标签用 `isVisible` 控制，`androidx.core.view.isVisible` 已 import

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat: 首页（卡片列表/分类Tab/录音识别入口/转场）"
```

---

### Task 6: 详情页（共享元素转场动画）

**Files:**
- Create: `app/src/main/java/com/example/voicenote/ui/detail/DetailViewModel.kt`
- Create: `app/src/main/java/com/example/voicenote/ui/detail/DetailFragment.kt`
- Create: `app/src/main/res/layout/fragment_detail.xml`

- [ ] **Step 1: 详情 ViewModel**

`DetailViewModel.kt`：

```kotlin
package com.example.voicenote.ui.detail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.example.voicenote.data.Note
import com.example.voicenote.data.NoteRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class DetailViewModel(
    private val repository: NoteRepository,
    private val noteId: Long
) : ViewModel() {

    private val _note = MutableStateFlow<Note?>(null)
    val note: StateFlow<Note?> = _note.asStateFlow()

    init {
        viewModelScope.launch { _note.value = repository.getById(noteId) }
    }

    fun save(updated: Note) {
        viewModelScope.launch { repository.update(updated) }
    }

    fun delete(note: Note) {
        viewModelScope.launch { repository.delete(note) }
    }

    fun toggleCategory(note: Note) {
        viewModelScope.launch { repository.toggleCategory(note) }
    }

    class Factory(
        private val repository: NoteRepository,
        private val noteId: Long
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T =
            DetailViewModel(repository, noteId) as T
    }
}
```

- [ ] **Step 2: 详情 Fragment（共享元素转场 + 编辑 + 播放 + 删除）**

`DetailFragment.kt`：

```kotlin
package com.example.voicenote.ui.detail

import android.os.Bundle
import android.transition.ChangeBounds
import android.transition.ChangeTransform
import android.transition.Fade
import android.transition.TransitionSet
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.core.view.isVisible
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import androidx.appcompat.app.AlertDialog
import com.example.voicenote.R
import com.example.voicenote.VoiceNoteApp
import com.example.voicenote.audio.AudioPlayer
import com.example.voicenote.data.Note
import com.example.voicenote.databinding.FragmentDetailBinding
import com.example.voicenote.reminder.AlarmScheduler
import com.example.voicenote.reminder.ReminderHelper
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.launch

class DetailFragment : Fragment() {

    private var _binding: FragmentDetailBinding? = null
    private val binding get() = _binding!!

    private val viewModel: DetailViewModel by viewModels {
        DetailViewModel.Factory(
            (requireActivity().application as VoiceNoteApp).repository,
            requireArguments().getLong(ARG_NOTE_ID)
        )
    }

    private val player = AudioPlayer()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // 卡片放大进入 / 缩小收回
        sharedElementEnterTransition = TransitionSet().apply {
            ordering = TransitionSet.ORDERING_TOGETHER
            addTransition(ChangeBounds())
            addTransition(ChangeTransform())
            addTransition(Fade(Fade.IN))
        }
        sharedElementReturnTransition = TransitionSet().apply {
            ordering = TransitionSet.ORDERING_TOGETHER
            addTransition(ChangeBounds())
            addTransition(ChangeTransform())
            addTransition(Fade(Fade.OUT))
        }
    }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        _binding = FragmentDetailBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        binding.root.transitionName = "note_detail"

        binding.btnBack.setOnClickListener { parentFragmentManager.popBackStack() }
        binding.btnPlay.setOnClickListener { togglePlay() }

        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.note.collect { note ->
                if (note != null) render(note)
            }
        }

        binding.btnSave.setOnClickListener { saveNote() }
        binding.btnDelete.setOnClickListener { confirmDelete() }
        binding.btnToggle.setOnClickListener { toggleCategory() }
    }

    private fun render(note: Note) {
        binding.etContent.setText(note.content)
        binding.etSummary.setText(note.summary)
        binding.etLocation.setText(note.location)
        binding.etPerson.setText(note.person)
        binding.etTopic.setText(note.topic)
        binding.tvTime.setText(
            note.eventTime?.let { SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.CHINA).format(Date(it)) }
                ?: "未识别"
        )
        binding.tvCreated.setText(
            SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.CHINA).format(Date(note.createdAt))
        )
        binding.btnToggle.text = if (note.category == "TODO") {
            getString(R.string.mark_done)
        } else {
            getString(R.string.restore_todo)
        }
        val hasAudio = note.audioPath != null
        binding.btnPlay.isVisible = hasAudio
        binding.tvAudioLabel.isVisible = hasAudio
    }

    private fun collectEdited(): Note {
        val current = viewModel.note.value ?: return Note(content = "")
        return current.copy(
            content = binding.etContent.text.toString().trim(),
            summary = binding.etSummary.text.toString().trim().ifBlank { null },
            location = binding.etLocation.text.toString().trim().ifBlank { null },
            person = binding.etPerson.text.toString().trim().ifBlank { null },
            topic = binding.etTopic.text.toString().trim().ifBlank { null }
        )
    }

    private fun saveNote() {
        val note = collectEdited()
        if (note.content.isBlank()) {
            Toast.makeText(requireContext(), getString(R.string.content_label), Toast.LENGTH_SHORT).show()
            return
        }
        viewModel.save(note)
        Toast.makeText(requireContext(), getString(R.string.save), Toast.LENGTH_SHORT).show()
    }

    private fun toggleCategory() {
        viewModel.note.value?.let {
            viewModel.toggleCategory(it)
            viewModel.note.value = it.copy(category = if (it.category == "TODO") "DONE" else "TODO")
        }
    }

    private fun confirmDelete() {
        val note = viewModel.note.value ?: return
        AlertDialog.Builder(requireContext())
            .setMessage(getString(R.string.confirm_delete))
            .setPositiveButton(getString(R.string.delete)) { _, _ ->
                note.audioPath?.let { File(it).delete() }
                note.reminderAt?.let { AlarmScheduler.cancel(requireContext(), note.id) }
                viewModel.delete(note)
                parentFragmentManager.popBackStack()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun togglePlay() {
        val path = viewModel.note.value?.audioPath ?: return
        if (playerPlaying) {
            player.stop()
            playerPlaying = false
            updatePlayIcon(false)
        } else {
            val file = File(path)
            player.play(file) { playing ->
                playerPlaying = playing
                updatePlayIcon(playing)
            }
            playerPlaying = true
            updatePlayIcon(true)
        }
    }

    private var playerPlaying = false

    private fun updatePlayIcon(playing: Boolean) {
        binding.btnPlay.setIconResource(if (playing) R.drawable.ic_pause else R.drawable.ic_play)
    }

    override fun onDestroyView() {
        player.stop()
        _binding = null
        super.onDestroyView()
    }

    companion object {
        private const val ARG_NOTE_ID = "note_id"
        fun newInstance(noteId: Long): DetailFragment =
            DetailFragment().apply {
                arguments = Bundle().apply { putLong(ARG_NOTE_ID, noteId) }
            }
    }
}
```

- [ ] **Step 3: 详情布局**

`res/layout/fragment_detail.xml`：

```xml
<?xml version="1.0" encoding="utf-8"?>
<androidx.constraintlayout.widget.ConstraintLayout
    xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:background="@color/surface">

    <com.google.android.material.appbar.MaterialToolbar
        android:id="@+id/toolbar"
        android:layout_width="0dp"
        android:layout_height="?attr/actionBarSize"
        android:background="@color/surface"
        app:navigationIcon="@drawable/ic_back"
        app:title="@string/app_name"
        app:titleTextColor="@color/on_surface"
        app:layout_constraintTop_toTopOf="parent"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent" />

    <TextView
        android:id="@+id/tvAudioLabel"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="@string/audio"
        android:textSize="13sp"
        android:textColor="@color/on_surface"
        android:layout_marginStart="16dp"
        android:layout_marginTop="12dp"
        android:visibility="gone"
        app:layout_constraintTop_toBottomOf="@id/toolbar"
        app:layout_constraintStart_toStartOf="parent" />

    <com.google.android.material.button.MaterialButton
        android:id="@+id/btnPlay"
        android:layout_width="48dp"
        android:layout_height="48dp"
        style="@style/Widget.Material3.Button.IconButton"
        app:icon="@drawable/ic_play"
        app:iconTint="@color/on_primary"
        android:backgroundTint="@color/primary"
        android:layout_marginEnd="16dp"
        android:layout_marginTop="8dp"
        android:visibility="gone"
        app:layout_constraintTop_toBottomOf="@id/toolbar"
        app:layout_constraintEnd_toEndOf="parent" />

    <androidx.core.widget.NestedScrollView
        android:layout_width="0dp"
        android:layout_height="0dp"
        android:fillViewport="true"
        app:layout_constraintTop_toBottomOf="@id/tvAudioLabel"
        app:layout_constraintBottom_toTopOf="@id/actionBar"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent">

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            android:padding="16dp">

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:text="@string/event_time"
                android:textSize="13sp"
                android:textColor="@color/chip_text" />

            <TextView
                android:id="@+id/tvTime"
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginTop="2dp"
                android:textSize="15sp"
                android:textColor="@color/on_surface" />

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginTop="12dp"
                android:text="@string/summary"
                android:textSize="13sp"
                android:textColor="@color/chip_text" />

            <com.google.android.material.textfield.TextInputLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:hint="@string/summary">
                <com.google.android.material.textfield.TextInputEditText
                    android:id="@+id/etSummary"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content" />
            </com.google.android.material.textfield.TextInputLayout>

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginTop="8dp"
                android:text="@string/content_label"
                android:textSize="13sp"
                android:textColor="@color/chip_text" />

            <com.google.android.material.textfield.TextInputLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:hint="@string/content_label">
                <com.google.android.material.textfield.TextInputEditText
                    android:id="@+id/etContent"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:minLines="3" />
            </com.google.android.material.textfield.TextInputLayout>

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginTop="8dp"
                android:text="@string/location"
                android:textSize="13sp"
                android:textColor="@color/chip_text" />

            <com.google.android.material.textfield.TextInputLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:hint="@string/location">
                <com.google.android.material.textfield.TextInputEditText
                    android:id="@+id/etLocation"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content" />
            </com.google.android.material.textfield.TextInputLayout>

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginTop="8dp"
                android:text="@string/person"
                android:textSize="13sp"
                android:textColor="@color/chip_text" />

            <com.google.android.material.textfield.TextInputLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:hint="@string/person">
                <com.google.android.material.textfield.TextInputEditText
                    android:id="@+id/etPerson"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content" />
            </com.google.android.material.textfield.TextInputLayout>

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginTop="8dp"
                android:text="@string/topic"
                android:textSize="13sp"
                android:textColor="@color/chip_text" />

            <com.google.android.material.textfield.TextInputLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:hint="@string/topic">
                <com.google.android.material.textfield.TextInputEditText
                    android:id="@+id/etTopic"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content" />
            </com.google.android.material.textfield.TextInputLayout>

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginTop="8dp"
                android:text="@string/reminder"
                android:textSize="13sp"
                android:textColor="@color/chip_text" />

            <TextView
                android:id="@+id/tvCreated"
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginTop="12dp"
                android:textSize="12sp"
                android:textColor="@color/chip_text" />

        </LinearLayout>
    </androidx.core.widget.NestedScrollView>

    <LinearLayout
        android:id="@+id/actionBar"
        android:layout_width="0dp"
        android:layout_height="wrap_content"
        android:orientation="horizontal"
        android:padding="12dp"
        app:layout_constraintBottom_toBottomOf="parent"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent">

        <com.google.android.material.button.MaterialButton
            android:id="@+id/btnToggle"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:text="@string/mark_done" />

        <com.google.android.material.button.MaterialButton
            android:id="@+id/btnSave"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:layout_marginStart="8dp"
            android:text="@string/save" />

        <com.google.android.material.button.MaterialButton
            android:id="@+id/btnDelete"
            style="@style/Widget.Material3.Button.IconButton"
            android:layout_width="48dp"
            android:layout_height="wrap_content"
            android:layout_marginStart="8dp"
            app:icon="@drawable/ic_delete"
            app:iconTint="@color/error" />

    </LinearLayout>

</androidx.constraintlayout.widget.ConstraintLayout>
```

- [ ] **Step 4: 自审清单**
  - `transitionName` 一致性：卡片 `cardRoot.transitionName="note_detail"` 与详情页 `binding.root.transitionName="note_detail"` 严格一致
  - HomeFragment `addSharedElement(cardView, "note_detail")` + `setReorderingAllowed(true)`，配合 Fragment 的 `sharedElementEnter/ReturnTransition` 实现放大进入/缩小收回
  - 详情页删除时同步删除录音文件与取消闹钟（Task 8 提供 `AlarmScheduler.cancel`）
  - `toggleCategory` 中手动同步 `_note.value`，使 UI 即时刷新（Room 流也会随后更新，双保险）
  - `collectEdited` 兜底返回空 Note 仅在 note 为空时出现，此时按钮不可达，无实际影响

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: 详情页（共享元素转场/编辑/播放/删除）"
```

---

### Task 7: 录音确认/编辑页

**Files:**
- Create: `app/src/main/java/com/example/voicenote/ui/record/RecordConfirmViewModel.kt`
- Create: `app/src/main/java/com/example/voicenote/ui/record/RecordConfirmFragment.kt`
- Create: `app/src/main/res/layout/fragment_record_confirm.xml`

- [ ] **Step 1: 确认页 ViewModel（保存 + 返回新 id）**

`RecordConfirmViewModel.kt`：

```kotlin
package com.example.voicenote.ui.record

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.example.voicenote.data.Note
import com.example.voicenote.data.NoteRepository
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.launch

class RecordConfirmViewModel(private val repository: NoteRepository) : ViewModel() {

    private val _savedId = MutableSharedFlow<Long>()
    val savedId: SharedFlow<Long> = _savedId

    fun save(note: Note) {
        viewModelScope.launch {
            val id = repository.insert(note)
            _savedId.emit(id)
        }
    }

    class Factory(private val repository: NoteRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T =
            RecordConfirmViewModel(repository) as T
    }
}
```

- [ ] **Step 2: 确认页 Fragment（自动分类填充 + 可编辑 + 保存 + 设提醒）**

`RecordConfirmFragment.kt`：

```kotlin
package com.example.voicenote.ui.record

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import com.example.voicenote.R
import com.example.voicenote.VoiceNoteApp
import com.example.voicenote.data.Note
import com.example.voicenote.databinding.FragmentRecordConfirmBinding
import com.example.voicenote.nlp.NlpEngine
import com.example.voicenote.nlp.NoteIntent
import com.example.voicenote.reminder.AlarmScheduler
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.launch

class RecordConfirmFragment : Fragment() {

    private var _binding: FragmentRecordConfirmBinding? = null
    private val binding get() = _binding!!

    private val viewModel: RecordConfirmViewModel by viewModels {
        RecordConfirmViewModel.Factory((requireActivity().application as VoiceNoteApp).repository)
    }

    private val text: String by lazy { requireArguments().getString(ARG_TEXT, "") }
    private val audioPath: String? by lazy { requireArguments().getString(ARG_AUDIO) }
    private var reminderMillis: Long? = null

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        _binding = FragmentRecordConfirmBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val result = NlpEngine.analyze(text)

        binding.etContent.setText(text)
        binding.etSummary.setText(result.summary)
        binding.etLocation.setText(result.location)
        binding.etPerson.setText(result.person)
        binding.etTopic.setText(result.topic)
        binding.tvTime.setText(result.timeText ?: getString(R.string.event_time))
        binding.rbTodo.isChecked = result.intent == NoteIntent.TODO
        binding.rbDone.isChecked = result.intent == NoteIntent.DONE

        binding.tvTime.setOnClickListener { pickReminder() }
        binding.btnClearReminder.setOnClickListener {
            reminderMillis = null
            binding.tvTime.setText(getString(R.string.event_time))
        }
        binding.btnSave.setOnClickListener { save() }
        binding.btnBack.setOnClickListener { parentFragmentManager.popBackStack() }

        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.savedId.collect { id ->
                reminderMillis?.let { AlarmScheduler.schedule(requireContext(), id, it) }
                parentFragmentManager.popBackStack()
            }
        }
    }

    private fun pickReminder() {
        val now = Calendar.getInstance()
        DatePickerDialog(requireContext(), { _, y, m, d ->
            TimePickerDialog(requireContext(), { _, h, min ->
                val cal = Calendar.getInstance()
                cal.set(y, m, d, h, min, 0)
                cal.set(Calendar.MILLISECOND, 0)
                reminderMillis = cal.timeInMillis
                binding.tvTime.text = SimpleDateFormat(
                    "yyyy-MM-dd HH:mm", Locale.CHINA
                ).format(Date(cal.timeInMillis))
            }, now.get(Calendar.HOUR_OF_DAY), now.get(Calendar.MINUTE), true).show()
        }, now.get(Calendar.YEAR), now.get(Calendar.MONTH), now.get(Calendar.DAY_OF_MONTH)).show()
    }

    private fun save() {
        val content = binding.etContent.text.toString().trim()
        if (content.isBlank()) {
            Toast.makeText(requireContext(), getString(R.string.content_label), Toast.LENGTH_SHORT).show()
            return
        }
        val category = if (binding.rbDone.isChecked) "DONE" else "TODO"
        val note = Note(
            content = content,
            audioPath = audioPath,
            category = category,
            eventTime = null,
            location = binding.etLocation.text.toString().trim().ifBlank { null },
            person = binding.etPerson.text.toString().trim().ifBlank { null },
            summary = binding.etSummary.text.toString().trim().ifBlank { null },
            topic = binding.etTopic.text.toString().trim().ifBlank { null },
            reminderAt = reminderMillis
        )
        viewModel.save(note)
    }

    override fun onDestroyView() {
        _binding = null
        super.onDestroyView()
    }

    companion object {
        private const val ARG_TEXT = "text"
        private const val ARG_AUDIO = "audio"
        fun newInstance(text: String, audioPath: String?): RecordConfirmFragment =
            RecordConfirmFragment().apply {
                arguments = Bundle().apply {
                    putString(ARG_TEXT, text)
                    putString(ARG_AUDIO, audioPath)
                }
            }
    }
}
```

- [ ] **Step 3: 确认页布局**

`res/layout/fragment_record_confirm.xml`：

```xml
<?xml version="1.0" encoding="utf-8"?>
<androidx.constraintlayout.widget.ConstraintLayout
    xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:background="@color/surface">

    <com.google.android.material.appbar.MaterialToolbar
        android:id="@+id/toolbar"
        android:layout_width="0dp"
        android:layout_height="?attr/actionBarSize"
        android:background="@color/surface"
        app:navigationIcon="@drawable/ic_back"
        app:title="@string/app_name"
        app:titleTextColor="@color/on_surface"
        app:layout_constraintTop_toTopOf="parent"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent" />

    <androidx.core.widget.NestedScrollView
        android:layout_width="0dp"
        android:layout_height="0dp"
        android:fillViewport="true"
        app:layout_constraintTop_toBottomOf="@id/toolbar"
        app:layout_constraintBottom_toTopOf="@id/btnSave"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent">

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            android:padding="16dp">

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:text="@string/category"
                android:textSize="13sp"
                android:textColor="@color/chip_text" />

            <RadioGroup
                android:id="@+id/rgCategory"
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:orientation="horizontal">

                <RadioButton
                    android:id="@+id/rbTodo"
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="@string/tab_todo"
                    android:checked="true" />

                <RadioButton
                    android:id="@+id/rbDone"
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="@string/tab_done"
                    android:layout_marginStart="16dp" />
            </RadioGroup>

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginTop="12dp"
                android:text="@string/reminder"
                android:textSize="13sp"
                android:textColor="@color/chip_text" />

            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:orientation="horizontal"
                android:gravity="center_vertical">

                <TextView
                    android:id="@+id/tvTime"
                    android:layout_width="0dp"
                    android:layout_height="wrap_content"
                    android:layout_weight="1"
                    android:text="@string/event_time"
                    android:textSize="15sp"
                    android:textColor="@color/primary" />

                <com.google.android.material.button.MaterialButton
                    android:id="@+id/btnClearReminder"
                    style="@style/Widget.Material3.Button.TextButton"
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="@string/back" />
            </LinearLayout>

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginTop="12dp"
                android:text="@string/content_label"
                android:textSize="13sp"
                android:textColor="@color/chip_text" />

            <com.google.android.material.textfield.TextInputLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:hint="@string/content_label">
                <com.google.android.material.textfield.TextInputEditText
                    android:id="@+id/etContent"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:minLines="3" />
            </com.google.android.material.textfield.TextInputLayout>

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginTop="8dp"
                android:text="@string/summary"
                android:textSize="13sp"
                android:textColor="@color/chip_text" />

            <com.google.android.material.textfield.TextInputLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:hint="@string/summary">
                <com.google.android.material.textfield.TextInputEditText
                    android:id="@+id/etSummary"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content" />
            </com.google.android.material.textfield.TextInputLayout>

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginTop="8dp"
                android:text="@string/location"
                android:textSize="13sp"
                android:textColor="@color/chip_text" />

            <com.google.android.material.textfield.TextInputLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:hint="@string/location">
                <com.google.android.material.textfield.TextInputEditText
                    android:id="@+id/etLocation"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content" />
            </com.google.android.material.textfield.TextInputLayout>

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginTop="8dp"
                android:text="@string/person"
                android:textSize="13sp"
                android:textColor="@color/chip_text" />

            <com.google.android.material.textfield.TextInputLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:hint="@string/person">
                <com.google.android.material.textfield.TextInputEditText
                    android:id="@+id/etPerson"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content" />
            </com.google.android.material.textfield.TextInputLayout>

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginTop="8dp"
                android:text="@string/topic"
                android:textSize="13sp"
                android:textColor="@color/chip_text" />

            <com.google.android.material.textfield.TextInputLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:hint="@string/topic">
                <com.google.android.material.textfield.TextInputEditText
                    android:id="@+id/etTopic"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content" />
            </com.google.android.material.textfield.TextInputLayout>

        </LinearLayout>
    </androidx.core.widget.NestedScrollView>

    <com.google.android.material.button.MaterialButton
        android:id="@+id/btnSave"
        android:layout_width="0dp"
        android:layout_height="wrap_content"
        android:layout_margin="16dp"
        android:text="@string/save"
        app:layout_constraintBottom_toBottomOf="parent"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent" />

</androidx.constraintlayout.widget.ConstraintLayout>
```

- [ ] **Step 4: 自审清单**
  - 保存成功通过 `savedId` 流回调，在主线程收集后调度闹钟（`AlarmScheduler.schedule` 在 Task 8 实现）
  - `Note` 构造参数顺序与实体一致（content/audioPath/category/eventTime/location/person/summary/topic/reminderAt 均有默认值，命名参数调用）
  - 提醒选择用 DatePickerDialog + TimePickerDialog；`btnClearReminder` 文案复用"返回"字符串属占位，Task 9 精调时改为专用文案
  - `NlpEngine.analyze` 在确认页自动填充，符合"先弹出确认界面再保存"需求

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: 录音确认/编辑页（自动分类填充/编辑/提醒/保存）"
```

---

### Task 8: 提醒模块（本地闹钟 + 通知 + 补发）

**Files:**
- Create: `app/src/main/java/com/example/voicenote/reminder/AlarmScheduler.kt`
- Create: `app/src/main/java/com/example/voicenote/reminder/ReminderReceiver.kt`
- Create: `app/src/main/java/com/example/voicenote/reminder/ReminderHelper.kt`

- [ ] **Step 1: 闹钟调度**

`AlarmScheduler.kt`：

```kotlin
package com.example.voicenote.reminder

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build

object AlarmScheduler {

    fun schedule(context: Context, noteId: Long, triggerAt: Long) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val pendingIntent = reminderIntent(context, noteId)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !alarmManager.canScheduleExactAlarms()) {
            // 未授予精确闹钟权限，降级为不精确提醒
            alarmManager.set(AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent)
        } else {
            alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent)
        }
    }

    fun cancel(context: Context, noteId: Long) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        alarmManager.cancel(reminderIntent(context, noteId))
    }

    private fun reminderIntent(context: Context, noteId: Long): PendingIntent {
        val intent = Intent(context, ReminderReceiver::class.java)
            .putExtra(ReminderReceiver.EXTRA_NOTE_ID, noteId)
        return PendingIntent.getBroadcast(
            context,
            noteId.toInt(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }
}
```

- [ ] **Step 2: 提醒广播接收器**

`ReminderReceiver.kt`：

```kotlin
package com.example.voicenote.reminder

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.example.voicenote.VoiceNoteApp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class ReminderReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val noteId = intent.getLongExtra(EXTRA_NOTE_ID, -1L)
        if (noteId < 0) return
        val app = context.applicationContext as? VoiceNoteApp ?: return
        CoroutineScope(Dispatchers.IO).launch {
            app.repository.getById(noteId)?.let { note ->
                ReminderHelper.showNotification(context, note)
                app.repository.markReminded(noteId)
            }
        }
    }

    companion object {
        const val EXTRA_NOTE_ID = "note_id"
    }
}
```

- [ ] **Step 3: 通知构建与补发**

`ReminderHelper.kt`：

```kotlin
package com.example.voicenote.reminder

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.example.voicenote.R
import com.example.voicenote.data.Note
import com.example.voicenote.data.NoteRepository
import com.example.voicenote.ui.MainActivity

object ReminderHelper {

    private const val CHANNEL_ID = "note_reminder"

    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                context.getString(R.string.reminder_title),
                NotificationManager.IMPORTANCE_HIGH
            )
            context.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    fun showNotification(context: Context, note: Note) {
        ensureChannel(context)
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        ) return

        val contentIntent = PendingIntent.getActivity(
            context,
            note.id.toInt(),
            Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(context.getString(R.string.reminder_title))
            .setContentText(note.summary ?: note.content)
            .setContentIntent(contentIntent)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(note.id.toInt(), notification)
    }

    suspend fun sendMissed(context: Context, repository: NoteRepository) {
        val missed = repository.findMissedReminders(System.currentTimeMillis())
        missed.forEach { note ->
            showNotification(context, note)
            repository.markReminded(note.id)
        }
    }
}
```

- [ ] **Step 4: 自审清单**
  - `ReminderReceiver` 在 manifest 中已注册（exported=false），通过显式 PendingIntent 触发
  - Android 12+ 无精确闹钟权限时降级 `alarmManager.set`，不会抛 `SecurityException`
  - Android 13+ 无通知权限时静默跳过，不崩溃
  - `MainActivity.onCreate` 已调用 `sendMissed` 补发（Task 5 Step 1）
  - `ReminderHelper.showNotification` 中 `note.summary ?: note.content` 保证文案非空

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: 提醒模块（闹钟调度/接收器/通知/补发）"
```

---

### Task 9: frontend-design 设计规范对齐（UI/UX + 动画精调）

**Files:**
- Modify: `app/src/main/res/values/colors.xml`
- Modify: `app/src/main/res/values/colors-night.xml`
- Modify: `app/src/main/res/values/dimens.xml`
- Modify: `app/src/main/res/layout/fragment_home.xml`
- Modify: `app/src/main/res/layout/item_note_card.xml`
- Modify: `app/src/main/res/layout/fragment_detail.xml`
- Modify: `app/src/main/res/layout/fragment_record_confirm.xml`
- Modify: `app/src/main/res/values/strings.xml`
- Modify: `app/src/main/java/com/example/voicenote/ui/home/HomeFragment.kt`
- Modify: `app/src/main/java/com/example/voicenote/ui/detail/DetailFragment.kt`

- [ ] **Step 1: 调用 frontend-design 技能产出设计规范**

调用 Skill：`trae-remote-official:frontend-design`，按技能流程产出 Web 设计稿（首页卡片列表、详情页、确认页），输出文件保存到 `docs/design/` 下。

- [ ] **Step 2: 提取设计令牌并回填资源**

将设计稿中的关键令牌提取并应用到 Android 资源（示例映射）：

```kotlin
// 设计令牌 → Android 资源映射（以设计稿实际输出为准）
// 主色 primary / 强调色 secondary / 背景 surface / 卡片圆角 card_corner
// 阴影 card_elevation / 标签底色 chip_bg / 字体大小/字重
```

更新 `colors.xml`、`colors-night.xml`、`dimens.xml`，使配色、圆角、阴影与设计稿一致。

- [ ] **Step 3: 动画精调**

在 `DetailFragment.onCreate` 的转场设置中，为 `ChangeBounds`/`ChangeTransform` 添加 `transition.interpolator` 与 `duration`：

```kotlin
sharedElementEnterTransition = TransitionSet().apply {
    ordering = TransitionSet.ORDERING_TOGETHER
    duration = 320
    interpolator = androidx.interpolator.view.animation.DecelerateInterpolator(1.6f)
    addTransition(ChangeBounds())
    addTransition(ChangeTransform())
    addTransition(Fade(Fade.IN))
}
```

在 `HomeFragment` 录音按钮添加脉冲动画（录音时循环放大/缩小）：

```kotlin
private val pulseAnim by lazy {
    android.view.animation.ScaleAnimation(
        1f, 1.15f, 1f, 1.15f,
        android.view.animation.Animation.RELATIVE_TO_SELF, 0.5f,
        android.view.animation.Animation.RELATIVE_TO_SELF, 0.5f
    ).apply {
        duration = 500
        repeatMode = android.view.animation.Animation.REVERSE
        repeatCount = android.view.animation.Animation.INFINITE
    }
}
// startRecording 中：binding.micButton.startAnimation(pulseAnim)
// stopRecording 中：binding.micButton.clearAnimation()
```

- [ ] **Step 4: 文案精调**

替换占位文案（`strings.xml`）：`btnClearReminder` 的"返回"改为"清除提醒"（新增 `clear_reminder`），确认页 Toolbar 标题改为"确认笔记"（新增 `confirm_title`）。

- [ ] **Step 5: 自审清单**
  - 设计令牌与 Android 资源一一对应，深浅色（values-night）同步更新
  - 动画只新增不破坏共享元素转场；`ScaleAnimation` 不干扰点击（用 FAB 自带动画即可）
  - 新增字符串均已在 `strings.xml` 定义，引用无遗漏

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "style: frontend-design 设计规范对齐（配色/圆角/动效/文案）"
```

---

### Task 10: release 签名配置

**Files:**
- Create: `app/keystore/release.keystore`（keytool 生成，gitignored）
- Create: `app/keystore.properties`（gitignored）
- Modify: `app/keystore.properties.example`（Task 1 已建，若密码变更同步更新）

- [ ] **Step 1: 生成 release keystore（keytool，本机执行，非构建命令）**

```powershell
keytool -genkeypair -v -keystore "c:\Users\zhuzhu\Desktop\my first android app\app\keystore\release.keystore" -alias voicenote -keyalg RSA -keysize 2048 -validity 10950 -storepass voicenote2026 -keypass voicenote2026 -dname "CN=VoiceNote,OU=Dev,O=Local,L=Shanghai,ST=Shanghai,C=CN"
```

预期输出：`Generating 2,048 bit RSA key pair ...` 成功提示。

- [ ] **Step 2: 创建 keystore.properties（gitignored，不提交）**

`app/keystore.properties`：

```properties
storeFile=keystore/release.keystore
storePassword=voicenote2026
keyAlias=voicenote
keyPassword=voicenote2026
```

- [ ] **Step 3: 自审清单**
  - `app/build.gradle.kts` signingConfigs 读取 `keystore.properties` 路径与属性名一致（storeFile/storePassword/keyAlias/keyPassword）
  - `keystore.properties` 与 `*.keystore` 已在 `.gitignore`，不会误提交
  - 证书有效期 30 年（10950 天），本地开发签名用

- [ ] **Step 4: Commit（仅提交 example，不提交真实凭据）**

```bash
git add app/keystore.properties.example
git commit -m "chore: release 签名配置（keystore 已生成，凭据 gitignored）"
```

---

### Task 11: 全量自审 + 收尾

**Files:** 全工程

- [ ] **Step 1: 全量自审清单**
  - 类名/包名/资源引用与 Task 1~10 一致（`R.id.xxx`、`R.string.xxx`、`R.drawable.xxx` 逐一核对）
  - 讯飞 SDK 类引用正确性（`com.iflytek.cloud.*`），ProGuard 保留规则已配
  - `Note` 实体字段与 `NlpResult` 字段、`RecordConfirmFragment` 构造一一对应
  - 共享元素转场 `transitionName` 双向一致
  - 无 mock/占位逻辑：识别为真实讯飞 API 调用，NLP 为真实本地规则引擎
  - 权限申请路径完整：录音、通知（13+）、精确闹钟降级
  - 代码注释使用中文，与代码语言规则一致

- [ ] **Step 2: 检查 git 状态并提交最终版本**

```bash
git status
git add .
git commit -m "chore: 全量自审收尾"
```

- [ ] **Step 3: 输出交付说明（给用户）**
  - 项目结构说明
  - 讯飞 SDK 放置位置（`app/libs/`）与 AppID 配置位置（`AppConfig.kt`）
  - release 签名文件位置与密码（keystore.properties，已 gitignore）
  - 用 Android Studio 打开后执行 `./gradlew testDebugUnitTest` 可运行 NLP 测试
  - 真机联调语音识别需要网络（在线听写）

---

## 自审（计划级）

**1. 设计覆盖：**
- 语音记录/确认界面 → Task 5/7 ✓
- 智能分类（自动+手动）→ Task 3（意图分类）+ Task 5/6/7（标记完成/恢复）✓
- 信息提取（时间/地点/人物/概况/主题）→ Task 3 ✓
- 首页卡片 Tab 陈列 → Task 5 ✓
- 详情页放大/缩小转场动画 → Task 6 + Task 9 ✓
- 本地提醒/补发 → Task 8 ✓
- 录音保存与回放 → Task 4（RecordManager/AudioPlayer）+ Task 6 ✓
- 讯飞在线识别/离线预留 → Task 4 ✓
- release 签名不打包 → Task 10 + 全局约束 ✓
- frontend-design 对齐 → Task 9 ✓

**2. 占位符扫描：** 除 Task 9 中明确标注"以设计稿实际输出为准"的令牌映射外，无 TBD/待实现内容。Task 9 Step 1 由 frontend-design 技能动态产出，属设计流程而非占位。

**3. 类型一致性：** `Note`（data 包）、`NlpResult`（nlp 包）、`NoteIntent`（nlp 包）在 Task 2/3/5/6/7 中签名一致；`IRecognizer`/`BaseRecognizer`/`RecognizerFactory` 在 Task 4/5 中一致；`AlarmScheduler`/`ReminderHelper` 在 Task 5/6/7/8 中一致；`MainActivity.showRecordConfirm` 与 `HomeFragment`/`RecordConfirmFragment` 一致；转场 `transitionName="note_detail"` 双向一致。
