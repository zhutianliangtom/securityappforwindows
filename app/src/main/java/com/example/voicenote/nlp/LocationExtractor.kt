package com.example.voicenote.nlp

object LocationExtractor {
    private val locations = listOf(
        "公司", "医院", "学校", "机场", "车站", "火车站", "家", "酒店", "餐厅",
        "会议室", "银行", "超市", "健身房", "派出所", "电影院", "商场", "公园",
        "图书馆", "快递点", "理发店", "幼儿园", "客户那里"
    )
    private val prepositions = listOf("去", "在", "到", "回", "里")

    fun extract(text: String): String? {
        // 优先：介词紧邻地点（去公司 / 在医院）
        for (loc in locations) {
            val idx = text.indexOf(loc)
            if (idx >= 0 && idx > 0 && text.substring(idx - 1, idx) in prepositions) {
                return loc
            }
        }
        // 兜底：直接命中地点词
        return locations.firstOrNull { text.contains(it) }
    }
}
