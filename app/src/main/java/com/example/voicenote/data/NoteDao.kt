package com.example.voicenote.data

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface NoteDao {
    @Insert
    suspend fun insert(note: Note): Long

    @Update
    suspend fun update(note: Note)

    @Delete
    suspend fun delete(note: Note)

    @Query("SELECT * FROM notes WHERE id = :id")
    suspend fun getById(id: Long): Note?

    @Query("SELECT * FROM notes WHERE category = :category ORDER BY createdAt DESC")
    fun observeByCategory(category: String): Flow<List<Note>>

    @Query("SELECT * FROM notes WHERE reminderAt IS NOT NULL AND reminded = 0 AND reminderAt < :now")
    suspend fun findMissedReminders(now: Long): List<Note>

    @Query("UPDATE notes SET reminded = 1 WHERE id = :id")
    suspend fun markReminded(id: Long)
}
