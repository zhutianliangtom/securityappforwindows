package com.example.voicenote.reminder

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build

object AlarmScheduler {

    fun schedule(context: Context, noteId: Long, triggerAt: Long) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val pendingIntent = reminderIntent(context, noteId)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !alarmManager.canScheduleExactAlarms()) {
            // 未授予精确闹钟权限，降级为不精确提醒
            alarmManager.set(AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent)
        } else {
            alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent)
        }
    }

    fun cancel(context: Context, noteId: Long) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        alarmManager.cancel(reminderIntent(context, noteId))
    }

    private fun reminderIntent(context: Context, noteId: Long): PendingIntent {
        val intent = Intent(context, ReminderReceiver::class.java)
            .putExtra(ReminderReceiver.EXTRA_NOTE_ID, noteId)
        return PendingIntent.getBroadcast(
            context,
            noteId.toInt(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }
}
