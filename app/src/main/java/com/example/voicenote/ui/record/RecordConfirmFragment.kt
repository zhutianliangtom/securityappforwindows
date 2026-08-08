package com.example.voicenote.ui.record

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import com.example.voicenote.R
import com.example.voicenote.VoiceNoteApp
import com.example.voicenote.data.Note
import com.example.voicenote.databinding.FragmentRecordConfirmBinding
import com.example.voicenote.nlp.NlpEngine
import com.example.voicenote.nlp.NoteIntent
import com.example.voicenote.reminder.AlarmScheduler
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.launch

class RecordConfirmFragment : Fragment() {

    private var _binding: FragmentRecordConfirmBinding? = null
    private val binding get() = _binding!!

    private val viewModel: RecordConfirmViewModel by viewModels {
        RecordConfirmViewModel.Factory((requireActivity().application as VoiceNoteApp).repository)
    }

    private val text: String by lazy { requireArguments().getString(ARG_TEXT, "") }
    private val audioPath: String? by lazy { requireArguments().getString(ARG_AUDIO) }
    private var reminderMillis: Long? = null

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        _binding = FragmentRecordConfirmBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val result = NlpEngine.analyze(text)

        binding.etContent.setText(text)
        binding.etSummary.setText(result.summary)
        binding.etLocation.setText(result.location)
        binding.etPerson.setText(result.person)
        binding.etTopic.setText(result.topic)
        binding.tvTime.text = result.timeText ?: getString(R.string.event_time)
        binding.rbTodo.isChecked = result.intent == NoteIntent.TODO
        binding.rbDone.isChecked = result.intent == NoteIntent.DONE

        binding.tvTime.setOnClickListener { pickReminder() }
        binding.btnClearReminder.setOnClickListener {
            reminderMillis = null
            binding.tvTime.text = getString(R.string.event_time)
        }
        binding.btnSave.setOnClickListener { save() }
        binding.btnBack.setOnClickListener { parentFragmentManager.popBackStack() }

        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.savedId.collect { id ->
                reminderMillis?.let { AlarmScheduler.schedule(requireContext(), id, it) }
                parentFragmentManager.popBackStack()
            }
        }
    }

    private fun pickReminder() {
        val now = Calendar.getInstance()
        DatePickerDialog(
            requireContext(),
            { _, y, m, d ->
                TimePickerDialog(
                    requireContext(),
                    { _, h, min ->
                        val cal = Calendar.getInstance()
                        cal.set(y, m, d, h, min, 0)
                        cal.set(Calendar.MILLISECOND, 0)
                        reminderMillis = cal.timeInMillis
                        binding.tvTime.text = SimpleDateFormat(
                            "yyyy-MM-dd HH:mm", Locale.CHINA
                        ).format(Date(cal.timeInMillis))
                    },
                    now.get(Calendar.HOUR_OF_DAY), now.get(Calendar.MINUTE), true
                ).show()
            },
            now.get(Calendar.YEAR), now.get(Calendar.MONTH), now.get(Calendar.DAY_OF_MONTH)
        ).show()
    }

    private fun save() {
        val content = binding.etContent.text.toString().trim()
        if (content.isBlank()) {
            Toast.makeText(requireContext(), R.string.content_label, Toast.LENGTH_SHORT).show()
            return
        }
        val category = if (binding.rbDone.isChecked) "DONE" else "TODO"
        val note = Note(
            content = content,
            audioPath = audioPath,
            category = category,
            location = binding.etLocation.text.toString().trim().ifBlank { null },
            person = binding.etPerson.text.toString().trim().ifBlank { null },
            summary = binding.etSummary.text.toString().trim().ifBlank { null },
            topic = binding.etTopic.text.toString().trim().ifBlank { null },
            reminderAt = reminderMillis
        )
        viewModel.save(note)
    }

    override fun onDestroyView() {
        _binding = null
        super.onDestroyView()
    }

    companion object {
        private const val ARG_TEXT = "text"
        private const val ARG_AUDIO = "audio"
        fun newInstance(text: String, audioPath: String?): RecordConfirmFragment =
            RecordConfirmFragment().apply {
                arguments = Bundle().apply {
                    putString(ARG_TEXT, text)
                    putString(ARG_AUDIO, audioPath)
                }
            }
    }
}
