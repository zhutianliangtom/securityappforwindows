package com.example.voicenote.ui

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.commit
import androidx.lifecycle.lifecycleScope
import com.example.voicenote.R
import com.example.voicenote.VoiceNoteApp
import com.example.voicenote.databinding.ActivityMainBinding
import com.example.voicenote.reminder.ReminderHelper
import com.example.voicenote.ui.home.HomeFragment
import com.example.voicenote.ui.record.RecordConfirmFragment
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        if (savedInstanceState == null) {
            supportFragmentManager.commit {
                replace(R.id.fragment_container, HomeFragment())
            }
        }

        // 补发错过的提醒
        val app = application as VoiceNoteApp
        lifecycleScope.launch(Dispatchers.IO) {
            ReminderHelper.sendMissed(applicationContext, app.repository)
        }
    }

    /** 打开录音确认/编辑页 */
    fun showRecordConfirm(text: String, audioPath: String?) {
        supportFragmentManager.commit {
            setReorderingAllowed(true)
            replace(R.id.fragment_container, RecordConfirmFragment.newInstance(text, audioPath))
            addToBackStack("record_confirm")
        }
    }
}
