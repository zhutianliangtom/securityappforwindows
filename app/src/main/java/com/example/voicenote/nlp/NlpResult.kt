package com.example.voicenote.nlp

data class NlpResult(
    val intent: NoteIntent,
    val timeText: String? = null,
    val eventTime: Long? = null,
    val location: String? = null,
    val person: String? = null,
    val summary: String? = null,
    val topic: String? = null
)
