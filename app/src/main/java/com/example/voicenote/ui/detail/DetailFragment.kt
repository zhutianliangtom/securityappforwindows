package com.example.voicenote.ui.detail

import android.os.Bundle
import android.transition.ChangeBounds
import android.transition.ChangeTransform
import android.transition.Fade
import android.transition.TransitionSet
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import com.example.voicenote.R
import com.example.voicenote.VoiceNoteApp
import com.example.voicenote.audio.AudioPlayer
import com.example.voicenote.data.Note
import com.example.voicenote.databinding.FragmentDetailBinding
import com.example.voicenote.reminder.AlarmScheduler
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.launch

class DetailFragment : Fragment() {

    private var _binding: FragmentDetailBinding? = null
    private val binding get() = _binding!!

    private val viewModel: DetailViewModel by viewModels {
        DetailViewModel.Factory(
            (requireActivity().application as VoiceNoteApp).repository,
            requireArguments().getLong(ARG_NOTE_ID)
        )
    }

    private val player = AudioPlayer()
    private var playerPlaying = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // 卡片放大进入 / 缩小收回
        sharedElementEnterTransition = TransitionSet().apply {
            ordering = TransitionSet.ORDERING_TOGETHER
            addTransition(ChangeBounds())
            addTransition(ChangeTransform())
            addTransition(Fade(Fade.IN))
        }
        sharedElementReturnTransition = TransitionSet().apply {
            ordering = TransitionSet.ORDERING_TOGETHER
            addTransition(ChangeBounds())
            addTransition(ChangeTransform())
            addTransition(Fade(Fade.OUT))
        }
    }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        _binding = FragmentDetailBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        binding.root.transitionName = "note_detail"

        binding.btnBack.setOnClickListener { parentFragmentManager.popBackStack() }
        binding.btnPlay.setOnClickListener { togglePlay() }
        binding.btnSave.setOnClickListener { saveNote() }
        binding.btnDelete.setOnClickListener { confirmDelete() }
        binding.btnToggle.setOnClickListener { toggleCategory() }

        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.note.collect { note ->
                if (note != null) render(note)
            }
        }
    }

    private fun render(note: Note) {
        binding.etContent.setText(note.content)
        binding.etSummary.setText(note.summary)
        binding.etLocation.setText(note.location)
        binding.etPerson.setText(note.person)
        binding.etTopic.setText(note.topic)
        binding.tvTime.text = note.eventTime?.let {
            SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.CHINA).format(Date(it))
        } ?: getString(R.string.event_time)
        binding.tvCreated.text = getString(
            R.string.created_at,
            SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.CHINA).format(Date(note.createdAt))
        )
        binding.btnToggle.text = if (note.category == "TODO") {
            getString(R.string.mark_done)
        } else {
            getString(R.string.restore_todo)
        }
        val hasAudio = note.audioPath != null
        binding.btnPlay.isVisible = hasAudio
        binding.tvAudioLabel.isVisible = hasAudio
    }

    private fun collectEdited(): Note? {
        val current = viewModel.note.value ?: return null
        return current.copy(
            content = binding.etContent.text.toString().trim(),
            summary = binding.etSummary.text.toString().trim().ifBlank { null },
            location = binding.etLocation.text.toString().trim().ifBlank { null },
            person = binding.etPerson.text.toString().trim().ifBlank { null },
            topic = binding.etTopic.text.toString().trim().ifBlank { null }
        )
    }

    private fun saveNote() {
        val note = collectEdited() ?: return
        if (note.content.isBlank()) {
            Toast.makeText(requireContext(), R.string.content_label, Toast.LENGTH_SHORT).show()
            return
        }
        viewModel.save(note)
        Toast.makeText(requireContext(), R.string.save, Toast.LENGTH_SHORT).show()
    }

    private fun toggleCategory() {
        val current = viewModel.note.value ?: return
        viewModel.toggleCategory(current)
        viewModel.note.value = current.copy(
            category = if (current.category == "TODO") "DONE" else "TODO"
        )
    }

    private fun confirmDelete() {
        val note = viewModel.note.value ?: return
        AlertDialog.Builder(requireContext())
            .setMessage(R.string.confirm_delete)
            .setPositiveButton(R.string.delete) { _, _ ->
                note.audioPath?.let { runCatching { File(it).delete() } }
                note.reminderAt?.let { AlarmScheduler.cancel(requireContext(), note.id) }
                viewModel.delete(note)
                parentFragmentManager.popBackStack()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun togglePlay() {
        val path = viewModel.note.value?.audioPath ?: return
        if (playerPlaying) {
            player.stop()
            playerPlaying = false
            updatePlayIcon(false)
        } else {
            player.play(File(path)) { playing ->
                playerPlaying = playing
                updatePlayIcon(playing)
            }
        }
    }

    private fun updatePlayIcon(playing: Boolean) {
        binding.btnPlay.setIconResource(if (playing) R.drawable.ic_pause else R.drawable.ic_play)
    }

    override fun onDestroyView() {
        player.stop()
        _binding = null
        super.onDestroyView()
    }

    companion object {
        private const val ARG_NOTE_ID = "note_id"
        fun newInstance(noteId: Long): DetailFragment =
            DetailFragment().apply {
                arguments = Bundle().apply { putLong(ARG_NOTE_ID, noteId) }
            }
    }
}
