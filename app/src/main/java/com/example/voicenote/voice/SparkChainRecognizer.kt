package com.example.voicenote.voice

import com.iflytek.sparkchain.core.asr.ASR
import com.iflytek.sparkchain.core.asr.AsrCallbacks

/**
 * 讯飞 SparkChain 语音听写（在线 WebSocket 流式识别）。
 * SDK 全局初始化在 VoiceNoteApp 完成；本类仅负责单次会话的启停与结果回调。
 */
class SparkChainRecognizer : IRecognizer {

    private var asr: ASR? = null
    private var onPartial: ((String) -> Unit)? = null
    private var onResult: ((String) -> Unit)? = null
    private var onError: ((String) -> Unit)? = null
    private var pendingError: String? = null
    private var sessionTag = 0

    private val callbacks = object : AsrCallbacks {
        override fun onResult(result: ASR.ASRResult?, usrTag: Any?) {
            val text = result?.bestMatchText ?: return
            when (result.status) {
                // 0=第一块结果 1=中间结果（实时追加显示）
                0, 1 -> onPartial?.invoke(text)
                // 2=最终结果
                2 -> {
                    onResult?.invoke(text)
                    resetCallbacks()
                }
            }
        }

        override fun onError(error: ASR.ASRError?, usrTag: Any?) {
            onError?.invoke(error?.errMsg ?: "语音识别错误")
            resetCallbacks()
        }

        override fun onBeginOfSpeech() {}

        override fun onEndOfSpeech() {}
    }

    override fun start(partial: (String) -> Unit) {
        onPartial = partial
        pendingError = null
        asr = ASR().apply {
            registerCallbacks(callbacks)
            language("zh_cn")
            domain("iat")
            accent("mandarin")
            ptt(true) // 开启标点
        }
        val ret = asr!!.start(sessionTag++)
        if (ret != 0) {
            pendingError = "识别开启失败，错误码:$ret"
        }
    }

    override fun writeAudio(data: ByteArray, length: Int) {
        asr?.write(data.copyOf(length))
    }

    override fun stop(onResult: (String) -> Unit, onError: (String) -> Unit) {
        this.onResult = onResult
        this.onError = onError
        pendingError?.let {
            onError(it)
            pendingError = null
            resetCallbacks()
            return
        }
        // 等云端下发最终结果后再结束会话
        asr?.stop(false)
    }

    override fun cancel() {
        asr?.stop(true) // 立即结束
    }

    override fun release() {
        asr = null
        resetCallbacks()
    }

    private fun resetCallbacks() {
        onPartial = null
        onResult = null
        onError = null
    }
}
