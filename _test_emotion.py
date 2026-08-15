# -*- coding: utf-8 -*-
"""临时验证：情感/语速分析 + 真实合成（验证后删除）"""
import sys
sys.path.insert(0, r"c:\Users\zhuzhu\Desktop\my first android app\src")
from winapp_migrator.core import agent_tts

cases = [
    "太棒了！我们终于成功了！",
    "听到这个消息我很难过，心里特别难受。",
    "真是太可恶了，你怎么能这样过分！",
    "今天天气不错，我们出去走走吧。",
    "哈哈，这也太搞笑了吧。",
    "你能不能告诉我这是为什么？",
    "这个方案涉及很多细节需要仔细权衡考虑，不是简单几句话能说清楚的。",
]
print("== 分析函数 ==")
for t in cases:
    tag, rate = agent_tts._analyze_expression(t)
    deco, eff = agent_tts._decorate_for_synthesis(t)
    print("[%s x%.2f] %s" % (tag or "无", rate, deco[:45]))

print("== 真实合成（确认标签不读出、语速生效） ==")
cfg = agent_tts.load_config()
vid = cfg.get("voice_id") or ""
if vid:
    for name, t in (("悲伤", "听到这个消息我很难过，心里特别难受。"),
                    ("开心", "太棒了！我们终于成功了！"),
                    ("愤怒", "真是太可恶了，你怎么能这样过分！")):
        try:
            p = agent_tts.synthesize_stream(t, vid, output_path="emo_%s.wav" % name)
            import wave
            w = wave.open(p)
            print("[%s] 时长=%.2fs -> %s" % (name, w.getnframes() / w.getframerate(), p))
            w.close()
        except Exception as e:
            print("[%s] 失败: %s" % (name, str(e)[:150]))
else:
    print("无音色，跳过合成测试")
