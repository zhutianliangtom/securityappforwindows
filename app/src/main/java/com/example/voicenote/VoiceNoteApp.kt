package com.example.voicenote

import android.app.Application
import com.example.voicenote.data.NoteRepository

class VoiceNoteApp : Application() {
    val repository: NoteRepository by lazy { NoteRepository.get(this) }
}
