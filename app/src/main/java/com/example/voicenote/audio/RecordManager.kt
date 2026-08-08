package com.example.voicenote.audio

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.File
import java.io.RandomAccessFile
import java.util.concurrent.atomic.AtomicBoolean

class RecordManager(private val file: File) {

    companion object {
        const val SAMPLE_RATE = 16000
    }

    private var recorder: AudioRecord? = null
    private var raf: RandomAccessFile? = null
    private val recording = AtomicBoolean(false)
    private var thread: Thread? = null

    fun start(onAudio: (ByteArray, Int) -> Unit) {
        file.parentFile?.mkdirs()
        raf = RandomAccessFile(file, "rw").apply { setLength(44) } // 预留 WAV 头
        val minBuf = AudioRecord.getMinBufferSize(
            SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
        )
        recorder = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            minBuf * 2
        )
        recorder?.startRecording()
        recording.set(true)
        thread = Thread {
            val buf = ByteArray(4096)
            while (recording.get()) {
                val n = recorder?.read(buf, 0, buf.size) ?: -1
                if (n > 0) {
                    runCatching { raf?.write(buf, 0, n) }
                    onAudio(buf.copyOf(n), n)
                }
            }
        }.apply { start() }
    }

    fun stop() {
        recording.set(false)
        thread?.join(500)
        runCatching { recorder?.stop() }
        recorder?.release()
        recorder = null
        finalizeWav()
        raf = null
        thread = null
    }

    private fun finalizeWav() {
        val r = raf ?: return
        runCatching {
            val dataLength = r.length() - 44
            r.seek(0)
            r.write(wavHeader(dataLength, SAMPLE_RATE))
            r.close()
        }
    }

    private fun wavHeader(dataLength: Long, sampleRate: Int): ByteArray {
        val h = ByteArray(44)
        fun putString(offset: Int, s: String) {
            s.forEachIndexed { i, c -> h[offset + i] = c.code.toByte() }
        }
        fun putIntLE(offset: Int, v: Int) {
            for (i in 0..3) h[offset + i] = ((v shr (8 * i)) and 0xFF).toByte()
        }
        fun putShortLE(offset: Int, v: Int) {
            h[offset] = (v and 0xFF).toByte()
            h[offset + 1] = ((v shr 8) and 0xFF).toByte()
        }
        putString(0, "RIFF"); putIntLE(4, (36 + dataLength).toInt()); putString(8, "WAVE")
        putString(12, "fmt "); putIntLE(16, 16); putShortLE(20, 1); putShortLE(22, 1)
        putIntLE(24, sampleRate); putIntLE(28, sampleRate * 2); putShortLE(32, 2); putShortLE(34, 16)
        putString(36, "data"); putIntLE(40, dataLength.toInt())
        return h
    }
}
