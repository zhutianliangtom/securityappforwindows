package com.example.voicenote.voice

interface IRecognizer {
    fun start(partial: (String) -> Unit)
    fun writeAudio(data: ByteArray, length: Int)
    fun stop(onResult: (String) -> Unit, onError: (String) -> Unit)
    fun cancel()
    fun release()
}
