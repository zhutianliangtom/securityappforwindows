package com.example.voicenote.nlp

object SummaryExtractor {
    // 动词词库
    private val verbs = listOf(
        "参加", "开会", "体检", "上课", "出差", "拜访", "吃饭", "提交",
        "去", "开", "看", "见", "交", "做", "办", "买", "修", "拿", "取", "送", "接"
    )

    fun extract(text: String): String? {
        val cleaned = text.replace(
            Regex("^(请|记得|别忘了|要|需要|必须|安排|帮|帮我|麻烦|提醒我|我|我们)"), ""
        ).trimStart('，', '。', '！')
        // 取最早出现的动词，保留更完整的动宾结构（如"去公司开会"而非"开会"）
        var bestIdx = -1
        for (v in verbs) {
            val idx = cleaned.indexOf(v)
            if (idx >= 0 && (bestIdx == -1 || idx < bestIdx)) bestIdx = idx
        }
        if (bestIdx >= 0) {
            val tail = cleaned.substring(bestIdx).split(Regex("[，。！？；、,]"))[0]
            val trimmed = tail.trimEnd('的', '了', '啊', '呢', '吧', '！', '。')
            if (trimmed.length >= 2) return trimmed.take(14)
        }
        return cleaned.take(14).ifBlank { null }
    }
}
