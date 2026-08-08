package com.example.voicenote.nlp

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class NlpEngineTest {

    @Test
    fun `明天下午3点去公司开会_应为待办会议`() {
        val r = NlpEngine.analyze("明天下午3点去公司开会")
        assertEquals(NoteIntent.TODO, r.intent)
        assertEquals("公司", r.location)
        assertEquals("会议", r.topic)
        assertEquals("去公司开会", r.summary)
        assertEquals("明天下午3点", r.timeText)
        assertNotNull(r.eventTime)
    }

    @Test
    fun `已经完成周报_应为已完成工作`() {
        val r = NlpEngine.analyze("我已经完成周报了")
        assertEquals(NoteIntent.DONE, r.intent)
        assertEquals("工作", r.topic)
    }

    @Test
    fun `记得完成周报_应为待办`() {
        val r = NlpEngine.analyze("记得完成周报")
        assertEquals(NoteIntent.TODO, r.intent)
    }

    @Test
    fun `还没完成报表_应为待办`() {
        val r = NlpEngine.analyze("还没完成报表")
        assertEquals(NoteIntent.TODO, r.intent)
    }

    @Test
    fun `和项目经理约明天见_提取人物`() {
        val r = NlpEngine.analyze("和项目经理约明天见")
        assertEquals("项目经理", r.person)
        // 仅有"明天"无具体时刻 → 不产出时间戳
        assertNull(r.timeText)
        assertNull(r.eventTime)
    }

    @Test
    fun `下周一早上体检_提取时间和主题`() {
        val r = NlpEngine.analyze("下周一早上体检")
        assertEquals("健康", r.topic)
        assertEquals("体检", r.summary)
        assertEquals("下周一早上", r.timeText)
        assertNotNull(r.eventTime)
    }

    @Test
    fun `张总安排周五交报表_人物与主题`() {
        val r = NlpEngine.analyze("张总安排周五交报表")
        assertEquals("张总", r.person)
        assertEquals("工作", r.topic)
        assertEquals(NoteIntent.TODO, r.intent)
        assertEquals("交报表", r.summary)
    }

    @Test
    fun `晚上8点接孩子_时间偏移到20点`() {
        val r = NlpEngine.analyze("晚上8点接孩子")
        assertEquals("家庭", r.topic)
        assertEquals("晚上8点", r.timeText)
        // 晚上8点 → 20:00，当天 20 点
        assertNotNull(r.eventTime)
    }
}
