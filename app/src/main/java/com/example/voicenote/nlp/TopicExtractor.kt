package com.example.voicenote.nlp

object TopicExtractor {
    private val rules = listOf(
        "会议" to listOf("开会", "会议", "例会", "汇报", "评审", "发布会", "面试", "洽谈"),
        "工作" to listOf("报表", "方案", "项目", "加班", "周报", "预算", "述职", "邮件", "代码", "需求", "客户"),
        "学习" to listOf("上课", "考试", "复习", "作业", "课程", "学习", "培训", "读书", "笔记"),
        "健康" to listOf("医生", "医院", "体检", "吃药", "看病", "复查", "检查", "锻炼", "健身"),
        "生活" to listOf("买菜", "逛街", "聚餐", "吃饭", "购物", "超市", "做饭", "旅行"),
        "家庭" to listOf("孩子", "家人", "父母", "接娃", "家长会", "亲戚", "老婆", "老公")
    )

    fun extract(text: String): String {
        for ((topic, words) in rules) {
            if (words.any { text.contains(it) }) return topic
        }
        return "其他"
    }
}
