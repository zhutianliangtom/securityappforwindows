package com.example.voicenote.voice

import org.json.JSONObject

object IatResultParser {
    fun parse(json: String): String {
        return try {
            val root = JSONObject(json)
            val ws = root.optJSONArray("ws") ?: return ""
            val sb = StringBuilder()
            for (i in 0 until ws.length()) {
                val cw = ws.getJSONObject(i).optJSONArray("cw") ?: continue
                for (j in 0 until cw.length()) {
                    sb.append(cw.getJSONObject(j).optString("w"))
                }
            }
            sb.toString()
        } catch (_: Exception) {
            ""
        }
    }
}
