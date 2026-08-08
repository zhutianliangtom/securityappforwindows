package com.example.voicenote.data

import android.content.Context
import kotlinx.coroutines.flow.Flow

class NoteRepository(private val dao: NoteDao) {

    fun observeByCategory(category: String): Flow<List<Note>> = dao.observeByCategory(category)

    suspend fun getById(id: Long): Note? = dao.getById(id)

    suspend fun insert(note: Note): Long = dao.insert(note)

    suspend fun update(note: Note) = dao.update(note)

    suspend fun delete(note: Note) = dao.delete(note)

    suspend fun toggleCategory(note: Note) {
        dao.update(note.copy(category = if (note.category == "TODO") "DONE" else "TODO"))
    }

    suspend fun findMissedReminders(now: Long): List<Note> = dao.findMissedReminders(now)

    suspend fun markReminded(id: Long) = dao.markReminded(id)

    companion object {
        fun get(context: Context): NoteRepository =
            NoteRepository(NoteDatabase.get(context).noteDao())
    }
}
