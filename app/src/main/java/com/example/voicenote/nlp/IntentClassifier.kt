package com.example.voicenote.nlp

object IntentClassifier {
    // 待办强触发词：出现即待办（即使句中含"完成"）
    private val todoStrong = listOf("记得", "别忘了", "需要", "必须", "待办", "安排", "提醒我")

    // 已完成触发词
    private val doneKeywords = listOf(
        "完成了", "做完", "开完", "结束", "搞定", "办完", "参加完",
        "看完", "吃过", "提交", "完毕", "去过了", "已经", "完成过"
    )

    fun classify(text: String): NoteIntent {
        if (todoStrong.any { text.contains(it) }) return NoteIntent.TODO
        // 否定：还没/没有/未完成 → 待办
        if ((text.contains("还没") || text.contains("没有") || text.contains("未完成"))
            && doneKeywords.any { text.contains(it) }
        ) return NoteIntent.TODO
        if (doneKeywords.any { text.contains(it) }) return NoteIntent.DONE
        return NoteIntent.TODO
    }
}
