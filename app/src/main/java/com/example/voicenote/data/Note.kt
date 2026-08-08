package com.example.voicenote.data

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "notes")
data class Note(
    @PrimaryKey(autoGenerate = true) val id: Long = 0L,
    val content: String,
    val audioPath: String? = null,
    val category: String = "TODO",          // "TODO" / "DONE"
    val eventTime: Long? = null,            // 提取的事件时间戳
    val location: String? = null,
    val person: String? = null,
    val summary: String? = null,
    val topic: String? = null,
    val reminderAt: Long? = null,           // 提醒时间戳
    val reminded: Boolean = false,          // 是否已提醒
    val createdAt: Long = System.currentTimeMillis()
)
