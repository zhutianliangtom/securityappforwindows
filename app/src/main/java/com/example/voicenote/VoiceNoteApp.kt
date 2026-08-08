package com.example.voicenote

import android.app.Application
import com.example.voicenote.data.NoteRepository
import com.iflytek.sparkchain.core.SparkChain
import com.iflytek.sparkchain.core.SparkChainConfig
import java.io.File

class VoiceNoteApp : Application() {
    val repository: NoteRepository by lazy { NoteRepository.get(this) }

    override fun onCreate() {
        super.onCreate()
        initSparkChain()
    }

    /** 全局初始化讯飞 SparkChain SDK（仅一次） */
    private fun initSparkChain() {
        val workDir = File(filesDir, "sparkchain").apply { mkdirs() }.absolutePath
        val config = SparkChainConfig.builder()
            .appID(AppConfig.IFLYTEK_APPID)
            .apiKey(AppConfig.IFLYTEK_API_KEY)
            .apiSecret(AppConfig.IFLYTEK_API_SECRET)
            .workDir(workDir)
            .logLevel(4) // ERROR，避免日志刷屏
        SparkChain.getInst().init(this, config)
    }
}
