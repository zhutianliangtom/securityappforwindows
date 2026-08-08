package com.example.voicenote

object AppConfig {
    // 讯飞开放平台凭证（本地开发）
    const val IFLYTEK_APPID = "b0c90dc2"
    const val IFLYTEK_API_KEY = "466ce52106ddebe0e8cd6ce3f0636477"
    const val IFLYTEK_API_SECRET = "OTUxYTA5MDU0NzcxNWVhOWJmMTE4OWM4"
    // "online"=讯飞在线听写  "offline"=讯飞离线听写（需开通离线能力并放置授权文件）
    const val RECOGNIZER_MODE = "online"
}
