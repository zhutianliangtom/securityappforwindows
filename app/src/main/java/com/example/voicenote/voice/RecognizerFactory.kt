package com.example.voicenote.voice

import android.content.Context

object RecognizerFactory {
    fun create(context: Context): IRecognizer = SparkChainRecognizer()
}
