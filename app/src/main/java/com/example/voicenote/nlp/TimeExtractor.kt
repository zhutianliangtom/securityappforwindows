package com.example.voicenote.nlp

import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

data class TimeResult(val timeText: String?, val timestamp: Long?)

object TimeExtractor {
    // 相对日期偏移
    private val dayOffset = mapOf(
        "大后天" to 3L, "后天" to 2L, "明天" to 1L, "今天" to 0L,
        "昨天" to -1L, "前天" to -2L, "大前天" to -3L
    )
    // 星期数字
    private val weekdayNum = mapOf("一" to 1, "二" to 2, "三" to 3, "四" to 4, "五" to 5, "六" to 6, "日" to 7, "天" to 7)
    // 时段默认时刻
    private val dayPartMap = mapOf(
        "凌晨" to 3, "早上" to 7, "上午" to 9, "中午" to 12,
        "下午" to 14, "傍晚" to 18, "晚上" to 19, "夜里" to 21
    )
    // 需要做 12 小时偏移的时段
    private val pmParts = listOf("下午", "傍晚", "晚上", "夜里")

    fun extract(text: String): TimeResult {
        val zone = ZoneId.systemDefault()
        val now = LocalDate.now(zone)
        var date = now
        var matchedDayText: String? = null

        // 相对日期（今天/明天/后天…）
        for ((k, off) in dayOffset) {
            if (text.contains(k)) {
                date = now.plusDays(off)
                matchedDayText = k
                break
            }
        }
        // 星期（本周/下周）
        if (matchedDayText == null) {
            val week = Regex("(下?周|星期)([一二三四五六日天])").find(text)
            if (week != null) {
                val w = weekdayNum[week.groupValues[2]] ?: -1
                if (w in 1..7) {
                    var delta = (w - now.dayOfWeek.value + 7) % 7
                    if (week.groupValues[1].startsWith("下")) {
                        if (delta == 0) delta = 7 // 下周一且今天是周一 → 7 天后
                    }
                    date = now.plusDays(delta.toLong())
                    matchedDayText = week.value
                }
            }
        }

        // 时段词
        var matchedPart: String? = null
        var partHour = -1
        for ((k, h) in dayPartMap) {
            if (text.contains(k)) {
                matchedPart = k
                partHour = h
                break
            }
        }

        var hour = -1
        var minute = 0
        var matchedTimeText: String? = null

        // "X点" / "X点半" / "X点Y分"
        val cn = Regex("(\\d{1,2})点(半|(\\d{1,2})分)?").find(text)
        if (cn != null) {
            hour = cn.groupValues[1].toInt()
            if (cn.groupValues[2] == "半") minute = 30
            else if (cn.groupValues[2].isNotEmpty()) minute = cn.groupValues[3].toInt()
            matchedTimeText = cn.value
            // 时段偏移：下午3点 → 15 点
            if (matchedPart != null && matchedPart in pmParts && hour < 12) {
                hour += 12
            }
        } else {
            // "HH:mm"
            val colon = Regex("(\\d{1,2}):(\\d{2})").find(text)
            if (colon != null) {
                hour = colon.groupValues[1].toInt()
                minute = colon.groupValues[2].toInt()
                matchedTimeText = colon.value
            }
        }

        // 无具体时刻，用时段默认时刻（如"早上体检"→7点）
        if (hour == -1 && partHour >= 0) {
            hour = partHour
            matchedTimeText = matchedPart
            matchedPart = null
        }
        if (hour == -1) return TimeResult(null, null)

        val ldt = LocalDateTime.of(date, LocalTime.of(hour, minute))
        val timeText = listOfNotNull(matchedDayText, matchedPart, matchedTimeText).joinToString("")
        return TimeResult(timeText.ifBlank { null }, ldt.atZone(zone).toInstant().toEpochMilli())
    }
}
