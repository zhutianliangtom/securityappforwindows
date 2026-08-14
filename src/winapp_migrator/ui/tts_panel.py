"""Qwen-TTS 声音复刻面板（深色控制台风格，与 zhuzhu Copilot 面板一致）

功能：
- 配置：API Key / 目标模型（独立存于 ~/.winapp_migrator/agent/tts.json，不污染 settings.json）
- 音色管理：上传参考音频创建音色、查询音色、删除音色
- 合成：输入文本 → 合成语音 → 本地播放（QMediaPlayer）+ 保存 wav
- 全部走 DashScope 真实 API（winapp_migrator.core.agent_tts）
"""

import threading
import time

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QObject
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWidgets import (
    QDialog, QLabel, QLineEdit, QPushButton, QComboBox, QHBoxLayout, QVBoxLayout,
    QMessageBox, QWidget, QFileDialog, QPlainTextEdit, QFrame,
)

from winapp_migrator.core import agent_tts
from winapp_migrator.ui.widgets import PrimaryButton, SecondaryButton

# ---------- 深色主题（与 agent_panel 一致） ----------
BG = "#000000"
PANEL = "#141414"
CARD = "#1E1E1E"
TEXT = "#F5F5F5"
TEXT_DIM = "#8A8A8A"
ACCENT = "#1E40AF"
ACCENT_HOVER = "#2563EB"
BORDER = "#2A2A2A"
GREEN = "#10B981"
RED = "#EF4444"

_MAX_WIDTH = 760


class _Worker(QObject):
    """后台执行 TTS 任务，通过信号回传结果（避免阻塞 UI）"""
    done = pyqtSignal(str, str)          # tag, message
    ok = pyqtSignal(str, object)         # tag, payload

    def run(self, tag, fn, *args, **kwargs):
        try:
            result = fn(*args, **kwargs)
            self.ok.emit(tag, result)
        except Exception as e:
            self.done.emit(tag, f"失败：{e}")


class TtsPanel(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Qwen-TTS 声音复刻")
        self.setMinimumSize(_MAX_WIDTH, 660)
        self._cfg = agent_tts.load_config()
        self._player = None
        self._worker_thread = None
        self._build_ui()
        self._load_config_to_ui()

    # ------------------------------------------------------------ UI
    def _build_ui(self):
        self.setStyleSheet(f"""
            QDialog {{ background: {BG}; }}
            QLabel {{ color: {TEXT}; font-size: 13px; }}
            QLabel[dim="true"] {{ color: {TEXT_DIM}; font-size: 12px; }}
            QLineEdit, QPlainTextEdit {{
                background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};
                border-radius: 8px; padding: 8px; font-size: 13px;
            }}
            QPlainTextEdit {{ font-family: Consolas, monospace; }}
            QComboBox {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};
                         border-radius: 8px; padding: 6px; }}
            QFrame#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # 标题
        title = QLabel("🔊 Qwen-TTS 声音复刻")
        title.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {TEXT};")
        subtitle = QLabel("DashScope 真实 API · 上传音频创建专属音色 → 文本合成语音")
        subtitle.setProperty("dim", True)
        root.addWidget(title)
        root.addWidget(subtitle)

        # ---------- 配置区 ----------
        cfg_card = self._card("配置")
        cfg_row1 = QHBoxLayout()
        cfg_row1.addWidget(self._label("API Key"))
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("DashScope API Key（环境变量 DASHSCOPE_API_KEY 或此处配置）")
        cfg_row1.addWidget(self.key_edit, 1)
        cfg_card.addLayout(cfg_row1)

        cfg_row2 = QHBoxLayout()
        cfg_row2.addWidget(self._label("目标模型"))
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        for m in ("qwen3-tts-vc-2026-01-22", "qwen2.5-tts-vc-2025-07-16"):
            self.model_combo.addItem(m)
        cfg_row2.addWidget(self.model_combo, 1)
        self.save_cfg_btn = SecondaryButton("保存配置")
        self.save_cfg_btn.clicked.connect(self._on_save_cfg)
        cfg_row2.addWidget(self.save_cfg_btn)
        cfg_card.addLayout(cfg_row2)

        # ---------- 音色管理区 ----------
        voice_card = self._card("音色管理")
        vrow = QHBoxLayout()
        vrow.addWidget(self._label("当前音色 ID"))
        self.voice_edit = QLineEdit()
        self.voice_edit.setPlaceholderText("留空则使用已保存的音色")
        vrow.addWidget(self.voice_edit, 1)
        voice_card.addLayout(vrow)

        vrow2 = QHBoxLayout()
        self.audio_path_edit = QLineEdit()
        self.audio_path_edit.setPlaceholderText("参考音频（推荐 10~20s、≥24kHz 单声道、≤10MB）")
        self.pick_btn = SecondaryButton("选择音频")
        self.pick_btn.clicked.connect(self._on_pick_audio)
        vrow2.addWidget(self.audio_path_edit, 1)
        vrow2.addWidget(self.pick_btn)
        voice_card.addLayout(vrow2)

        vrow3 = QHBoxLayout()
        self.create_btn = PrimaryButton("🎤 创建音色")
        self.create_btn.clicked.connect(self._on_create_voice)
        self.query_btn = SecondaryButton("查询音色")
        self.query_btn.clicked.connect(self._on_query_voice)
        self.delete_btn = SecondaryButton("删除音色")
        self.delete_btn.clicked.connect(self._on_delete_voice)
        for b in (self.create_btn, self.query_btn, self.delete_btn):
            vrow3.addWidget(b)
        voice_card.addLayout(vrow3)

        # ---------- 合成区 ----------
        synth_card = self._card("语音合成")
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("输入要合成的文本（支持中文）…")
        self.text_edit.setFixedHeight(110)
        synth_card.addWidget(self.text_edit)

        srow = QHBoxLayout()
        srow.addWidget(self._label("输出目录"))
        self.outdir_edit = QLineEdit()
        self.outdir_edit.setPlaceholderText("留空保存到工作目录 tts_output/")
        self.outdir_btn = SecondaryButton("浏览")
        self.outdir_btn.clicked.connect(self._on_pick_outdir)
        srow.addWidget(self.outdir_edit, 1)
        srow.addWidget(self.outdir_btn)
        synth_card.addLayout(srow)

        srow2 = QHBoxLayout()
        self.speak_btn = PrimaryButton("▶ 合成并播放")
        self.speak_btn.clicked.connect(self._on_speak)
        self.stop_btn = SecondaryButton("停止")
        self.stop_btn.clicked.connect(self._on_stop)
        srow2.addWidget(self.speak_btn)
        srow2.addWidget(self.stop_btn)
        srow2.addStretch(1)
        synth_card.addLayout(srow2)

        # ---------- 日志区 ----------
        log_card = self._card("运行日志")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(130)
        self.log_view.setPlaceholderText("操作日志将显示在这里…")
        log_card.addWidget(self.log_view)

        self._log("就绪：从 tts.json 加载配置完成")

    def _card(self, title: str) -> QVBoxLayout:
        w = QFrame()
        w.setObjectName("card")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(8)
        t = QLabel(title)
        t.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {TEXT};")
        lay.addWidget(t)
        # 把卡片本身加入根布局，返回内部 layout 供调用方继续 addWidget/addLayout
        self.layout().addWidget(w)
        return lay

    @staticmethod
    def _label(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setProperty("dim", True)
        return lab

    # ------------------------------------------------------------ 配置
    def _load_config_to_ui(self):
        self.key_edit.setText(self._cfg.get("api_key", ""))
        model = self._cfg.get("target_model") or agent_tts.DEFAULT_TARGET_MODEL
        idx = self.model_combo.findText(model)
        self.model_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.voice_edit.setText(self._cfg.get("voice_id", ""))

    def _on_save_cfg(self):
        ok = agent_tts.save_config(
            api_key=self.key_edit.text().strip(),
            target_model=self.model_combo.currentText().strip() or agent_tts.DEFAULT_TARGET_MODEL,
            voice_id=self.voice_edit.text().strip(),
            preferred_name=self._cfg.get("preferred_name", "diede"))
        self._log("配置已保存" if ok else "配置保存失败（无写入权限）")
        if ok:
            self._cfg = agent_tts.load_config()

    # ------------------------------------------------------------ 音色
    def _current_model(self) -> str:
        return self.model_combo.currentText().strip() or agent_tts.DEFAULT_TARGET_MODEL

    def _current_voice(self) -> str:
        return self.voice_edit.text().strip() or self._cfg.get("voice_id", "")

    def _on_pick_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择参考音频", "", "音频文件 (*.wav *.mp3 *.m4a *.flac *.ogg *.aac);;所有文件 (*)")
        if path:
            self.audio_path_edit.setText(path)

    def _on_pick_outdir(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.outdir_edit.setText(path)

    def _on_create_voice(self):
        audio = self.audio_path_edit.text().strip()
        if not audio:
            QMessageBox.warning(self, "提示", "请先选择参考音频文件")
            return
        self._set_busy(True)
        self._log(f"上传音频创建音色：{audio} …")
        self._spawn("create", agent_tts.create_voice, audio,
                    self._current_model(), self._cfg.get("preferred_name", "diede"))

    def _on_query_voice(self):
        vid = self._current_voice()
        if not vid:
            QMessageBox.warning(self, "提示", "请先填写音色 ID")
            return
        self._log(f"查询音色：{vid}")
        self._spawn("query", agent_tts.query_voice, vid, self._current_model())

    def _on_delete_voice(self):
        vid = self._current_voice()
        if not vid:
            QMessageBox.warning(self, "提示", "请先填写音色 ID")
            return
        if QMessageBox.question(self, "确认", f"确定删除音色 {vid}？不可恢复。") != QMessageBox.StandardButton.Yes:
            return
        self._log(f"删除音色：{vid}")
        self._spawn("delete", agent_tts.delete_voice, vid)

    # ------------------------------------------------------------ 合成
    def _on_speak(self):
        text = self.text_edit.toPlainText().strip()
        vid = self._current_voice()
        if not text:
            QMessageBox.warning(self, "提示", "请输入要合成的文本")
            return
        if not vid:
            QMessageBox.warning(self, "提示", "请先填写或创建音色 ID")
            return
        outdir = self.outdir_edit.text().strip()
        out_path = ""
        if outdir:
            out_path = f"{outdir}/tts_{int(time.time())}.wav"
        self._log("开始合成语音 …")
        self._spawn("speak", agent_tts.synthesize, text, vid, self._current_model(), out_path)

    def _on_stop(self):
        self._stop_player()
        self._log("已停止播放")

    def _stop_player(self):
        if self._player is not None:
            try:
                self._player.stop()
            except Exception:
                pass

    def _play(self, path: str):
        self._stop_player()
        self._player = QMediaPlayer(self)
        audio = QAudioOutput(self)
        self._player.setAudioOutput(audio)
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()
        self._log(f"播放：{path}")

    # ------------------------------------------------------------ 后台执行
    def _spawn(self, tag: str, fn, *args):
        """在后台线程执行 fn，完成后回调 _on_worker_result"""
        self._worker = _Worker()
        self._worker.done.connect(lambda t, m: self._on_worker_result(t, m))
        self._worker.ok.connect(lambda t, p: self._on_worker_ok(t, p))
        import threading as _th
        th = _th.Thread(target=self._worker.run, args=(tag, fn, *args), daemon=True)
        th.start()

    def _on_worker_ok(self, tag: str, payload):
        self._set_busy(False)
        if tag == "create":
            vid = payload
            self.voice_edit.setText(vid)
            self._cfg["voice_id"] = vid
            agent_tts.save_config(voice_id=vid)
            self._log(f"音色创建成功：{vid}")
        elif tag == "query":
            self._log("音色信息：" + str(payload))
        elif tag == "delete":
            self._log(f"音色已删除：{payload}")
            self.voice_edit.clear()
        elif tag == "speak":
            self._log(f"合成完成：{payload}")
            self._play(payload)

    def _on_worker_result(self, tag: str, message: str):
        self._set_busy(False)
        self._log(message)

    def _set_busy(self, busy: bool):
        for b in (self.create_btn, self.query_btn, self.delete_btn, self.speak_btn):
            b.setEnabled(not busy)

    def _log(self, msg: str):
        self.log_view.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {msg}")
