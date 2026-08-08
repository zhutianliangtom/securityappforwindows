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
