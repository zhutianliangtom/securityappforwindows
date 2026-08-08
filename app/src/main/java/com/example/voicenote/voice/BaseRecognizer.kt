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
