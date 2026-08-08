package com.example.voicenote.reminder

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.example.voicenote.VoiceNoteApp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class ReminderReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val noteId = intent.getLongExtra(EXTRA_NOTE_ID, -1L)
        if (noteId < 0) return
        val app = context.applicationContext as? VoiceNoteApp ?: return
        CoroutineScope(Dispatchers.IO).launch {
            app.repository.getById(noteId)?.let { note ->
                ReminderHelper.showNotification(context, note)
                app.repository.markReminded(noteId)
            }
        }
    }

    companion object {
        const val EXTRA_NOTE_ID = "note_id"
    }
}
