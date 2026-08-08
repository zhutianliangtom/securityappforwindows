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
