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
