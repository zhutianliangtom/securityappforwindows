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
