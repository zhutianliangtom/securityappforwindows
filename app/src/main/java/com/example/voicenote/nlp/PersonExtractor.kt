package com.example.voicenote.nlp

object PersonExtractor {
    // 常见姓氏
    private val surnames = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘斜厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴郁胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
    private val titles = listOf("总", "经理", "老师", "医生", "主任", "律师", "哥", "姐", "师傅", "教授")

    fun extract(text: String): String? {
        // 姓氏 + 称谓，如 张总 / 李老师 / 王经理
        for (i in text.indices) {
            val c = text[i]
            if (surnames.contains(c)) {
                for (t in titles) {
                    val end = i + 1 + t.length
                    if (end <= text.length && text.substring(i + 1, end) == t) {
                        return c + t
                    }
                }
            }
        }
        // 关联词 + 人名（2~3 字），如 和项目/约明天；若后面紧跟称谓词则拼接（项目经理）
        val timeWords = listOf("今天", "明天", "后天", "昨天", "上午", "下午", "晚上", "中午", "早上", "凌晨", "周末", "下周")
        val m = Regex("(和|跟|约|找|请|给)([\\u4e00-\\u9fa5]{2,3})").find(text) ?: return null
        var candidate = m.groupValues[2]
        val afterIdx = m.range.last + 1
        for (t in titles) {
            if (afterIdx + t.length <= text.length && text.substring(afterIdx, afterIdx + t.length) == t) {
                candidate += t
                break
            }
        }
        if (timeWords.any { candidate.contains(it) }) return null
        return candidate
    }
}
