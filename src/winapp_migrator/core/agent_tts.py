# -*- coding: utf-8 -*-
"""Qwen-TTS 声音复刻与语音合成模块（阿里云 DashScope 真实 API 调用）

提供能力：
- create_voice  : 上传参考音频创建自定义音色（声音复刻，qwen-voice-enrollment）
- query_voice   : 查询音色详情（action=query，需 voice 参数）
- delete_voice  : 删除音色（action=delete，不可带 target_model）
- synthesize    : 用指定音色合成语音并下载到本地（multimodal-generation）

API Key 读取顺序（避免硬编码）：
1. 环境变量 DASHSCOPE_API_KEY
2. 独立配置文件 ~/.winapp_migrator/agent/tts.json 的 api_key 字段
   （不放进 settings.json，因其会被设置面板整体覆写）

参考音频要求：10~20s 推荐（最长 60s）、≥24kHz、单声道、≤10MB。
"""
import base64
import json
import os
import pathlib
import urllib.error
import urllib.request
from pathlib import Path

CUSTOMIZATION_URL = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization"
TTS_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
ENROLL_MODEL = "qwen-voice-enrollment"
DEFAULT_TARGET_MODEL = "qwen3-tts-vc-2026-01-22"

CONFIG_FILE = Path.home() / ".winapp_migrator" / "agent" / "tts.json"


# ---------------------------------------------------------------- 配置
def load_api_key() -> str:
    """读取 DashScope API Key：环境变量优先，其次独立配置文件 tts.json"""
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if key:
        return key
    try:
        if CONFIG_FILE.exists():
            return str(json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("api_key", "")).strip()
    except Exception:
        pass
    return ""


def save_config(api_key: str = "", target_model: str = DEFAULT_TARGET_MODEL,
                voice_id: str = "", preferred_name: str = "") -> bool:
    """保存 TTS 配置到独立文件 tts.json（设置面板写入，避免被 settings.json 覆写）"""
    try:
        data = {}
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        data["api_key"] = api_key or data.get("api_key", "")
        data["target_model"] = target_model or data.get("target_model", DEFAULT_TARGET_MODEL)
        data["voice_id"] = voice_id or data.get("voice_id", "")
        data["preferred_name"] = preferred_name or data.get("preferred_name", "")
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def load_config() -> dict:
    """读取 TTS 配置（不含敏感 Key 之外的全部字段）"""
    data = {"target_model": DEFAULT_TARGET_MODEL, "voice_id": "", "preferred_name": ""}
    try:
        if CONFIG_FILE.exists():
            data.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return data


# 朗读意图关键词：命中即自动开启"AI 边输出边朗读 / 回复自动朗读"
READ_INTENT_KEYWORDS = (
    "朗读", "读出来", "读给我听", "读一下", "读一读", "读给", "读给我", "念出来",
    "语音回复", "语音播报", "语音输出", "语音回答", "语音", "播报",
    "边读边", "边输出边读", "边说边读", "读出来给我",
    "voice", "speak", "read aloud",
)


def has_read_intent(text: str) -> bool:
    """判断用户输入是否要求朗读（命中任一关键词返回 True）"""
    t = (text or "").lower()
    return any(k in t for k in READ_INTENT_KEYWORDS)


def _request(url: str, payload: dict, timeout: int = 120) -> dict:
    """发起 DashScope POST 请求，返回解析后的 JSON dict；失败抛 RuntimeError"""
    key = load_api_key()
    if not key:
        raise RuntimeError("未配置 DashScope API Key：请设置环境变量 DASHSCOPE_API_KEY "
                           "或在 TTS 设置中填写")
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"DashScope HTTP {e.code}: {body[:500]}")


def _audio_data_url(path: str) -> str:
    """读取音频文件并转为 data URL（data:audio/wav;base64,...）"""
    p = pathlib.Path(path)
    if not p.exists():
        raise RuntimeError(f"参考音频不存在: {path}")
    size = p.stat().st_size
    if size > 10 * 1024 * 1024:
        raise RuntimeError(f"参考音频过大（{size} bytes > 10MB），请截取 10~20s 片段")
    b64 = base64.b64encode(p.read_bytes()).decode()
    return "data:audio/wav;base64," + b64


# ---------------------------------------------------------------- 音色管理
def create_voice(audio_path: str, target_model: str = DEFAULT_TARGET_MODEL,
                 preferred_name: str = "diede", timeout: int = 120) -> str:
    """上传参考音频创建自定义音色，返回 voice_id"""
    payload = {
        "model": ENROLL_MODEL,
        "input": {
            "action": "create",
            "target_model": target_model,
            "preferred_name": preferred_name,
            "audio": {"data": _audio_data_url(audio_path)},
        },
    }
    d = _request(CUSTOMIZATION_URL, payload, timeout=timeout)
    voice_id = (d.get("output") or {}).get("voice", "")
    if not voice_id:
        raise RuntimeError("创建音色失败：响应中无 voice 字段: " +
                           json.dumps(d, ensure_ascii=False)[:300])
    return voice_id


def query_voice(voice_id: str, target_model: str = DEFAULT_TARGET_MODEL,
                timeout: int = 60) -> dict:
    """查询音色详情（action=query 为单查，必须携带 voice 参数）"""
    payload = {
        "model": ENROLL_MODEL,
        "input": {"action": "query", "target_model": target_model, "voice": voice_id},
    }
    return _request(CUSTOMIZATION_URL, payload, timeout=timeout)


def delete_voice(voice_id: str, timeout: int = 60) -> dict:
    """删除音色（action=delete，注意：不可带 target_model，否则报 VoiceNotFound）"""
    payload = {
        "model": ENROLL_MODEL,
        "input": {"action": "delete", "voice": voice_id},
    }
    return _request(CUSTOMIZATION_URL, payload, timeout=timeout)


def list_voices(timeout: int = 60) -> list:
    """列出已创建的音色（action=list），返回 [{'voice','target_model','language','gmt_create'}, ...]"""
    payload = {"model": ENROLL_MODEL, "input": {"action": "list"}}
    d = _request(CUSTOMIZATION_URL, payload, timeout=timeout)
    return (d.get("output") or {}).get("voice_list") or []


# ---------------------------------------------------------------- 合成
def _strip_wav_header(chunk: bytes) -> bytes:
    """剥离首个音频分片中的 RIFF WAV 头，返回纯 PCM 数据"""
    if chunk[:4] != b"RIFF" or chunk[8:12] != b"WAVE":
        return chunk  # 不是 WAV 头（异常分片），原样返回
    pos = 12
    while pos + 8 <= len(chunk):
        cid = chunk[pos:pos + 4]
        csz = int.from_bytes(chunk[pos + 4:pos + 8], "little")
        if cid == b"data":
            return chunk[pos + 8:]
        pos += 8 + csz + (csz % 2)
    return chunk


def _pcm_to_wav(pcm: bytes, rate: int = 24000, channels: int = 1, bits: int = 16) -> bytes:
    """PCM -> 完整 WAV 内存字节（流式合成落盘用）"""
    import struct
    byte_rate = rate * channels * bits // 8
    block_align = channels * bits // 8
    return struct.pack("<4sI4s4sIHHIIHH4sI",
                       b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16,
                       1, channels, rate, byte_rate, block_align, bits, b"data", len(pcm)) + pcm


def synthesize_stream(text: str, voice_id: str, model: str = DEFAULT_TARGET_MODEL,
                      on_chunk=None, output_path: str = "", timeout: int = 120) -> str:
    """流式合成语音（SSE 分片），边接收边回调，返回完整 wav 文件路径。

    on_chunk(pcm_bytes)：每收到一段 PCM（已剥离 WAV 头，24kHz/16bit/单声道）回调一次，
    可用于边生成边播放；on_chunk 为空时仅保存文件。
    """
    if not text.strip():
        raise RuntimeError("合成文本为空")
    if not voice_id.strip():
        voice_id = str(load_config().get("voice_id", "")).strip()
    if not voice_id.strip():
        raise RuntimeError("未指定音色 voice_id，请先在 AI 设置中选择音色")
    key = load_api_key()
    if not key:
        raise RuntimeError("未配置 DashScope API Key：请设置环境变量 DASHSCOPE_API_KEY "
                           "或在 TTS 设置中填写")
    payload = {
        "model": model,
        "input": {"text": text, "voice": voice_id},
        "parameters": {"stream": True},
    }
    req = urllib.request.Request(
        TTS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "X-DashScope-SSE": "enable", "Accept": "text/event-stream"})
    parts = []
    first = True
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    d = json.loads(line[5:].strip())
                except Exception:
                    continue
                b64 = ((d.get("output") or {}).get("audio") or {}).get("data") or ""
                if not b64:
                    continue
                chunk = base64.b64decode(b64)
                if first:
                    chunk = _strip_wav_header(chunk)
                    first = False
                if chunk:
                    parts.append(chunk)
                    if on_chunk:
                        on_chunk(chunk)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"DashScope HTTP {e.code}: "
                           + e.read().decode("utf-8", "ignore")[:500])
    if not parts:
        raise RuntimeError("合成失败：未收到音频分片")
    if not output_path:
        out_dir = pathlib.Path.cwd() / "tts_output"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / f"tts_{int(__import__('time').time())}.wav")
    pathlib.Path(output_path).write_bytes(_pcm_to_wav(b"".join(parts)))
    return output_path


def synthesize(text: str, voice_id: str, model: str = DEFAULT_TARGET_MODEL,
               output_path: str = "", timeout: int = 120) -> str:
    """用指定音色合成语音，下载到本地，返回音频文件路径。

    output_path 为空时自动生成：工作目录/tts_output_<时间戳>.wav
    """
    if not text.strip():
        raise RuntimeError("合成文本为空")
    if not voice_id.strip():
        # 未显式指定音色时，回退到设置面板选中的音色（tts.json）
        voice_id = str(load_config().get("voice_id", "")).strip()
    if not voice_id.strip():
        raise RuntimeError("未指定音色 voice_id，请先在 AI 设置中选择音色")
    payload = {
        "model": model,
        "input": {"text": text, "voice": voice_id},
    }
    d = _request(TTS_URL, payload, timeout=timeout)
    audio_url = ((d.get("output") or {}).get("audio") or {}).get("url", "")
    if not audio_url:
        raise RuntimeError("合成失败：响应无音频 URL: " +
                           json.dumps(d, ensure_ascii=False)[:300])
    if not output_path:
        out_dir = pathlib.Path.cwd() / "tts_output"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / f"tts_{int(__import__('time').time())}.wav")
    urllib.request.urlretrieve(audio_url, output_path)
    return output_path
