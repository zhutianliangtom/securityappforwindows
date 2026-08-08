package com.example.voicenote.ui.home

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.view.isVisible
import androidx.fragment.app.Fragment
import androidx.fragment.app.commit
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.voicenote.R
import com.example.voicenote.VoiceNoteApp
import com.example.voicenote.audio.AudioPlayer
import com.example.voicenote.audio.RecordManager
import com.example.voicenote.data.Note
import com.example.voicenote.databinding.FragmentHomeBinding
import com.example.voicenote.ui.MainActivity
import com.example.voicenote.ui.detail.DetailFragment
import com.example.voicenote.voice.IRecognizer
import com.example.voicenote.voice.RecognizerFactory
import java.io.File
import kotlinx.coroutines.launch

class HomeFragment : Fragment() {

    private var _binding: FragmentHomeBinding? = null
    private val binding get() = _binding!!

    private val viewModel: HomeViewModel by viewModels {
        HomeViewModel.Factory((requireActivity().application as VoiceNoteApp).repository)
    }

    private val adapter = NoteAdapter(
        onClick = { note, view -> openDetail(note, view) },
        onToggle = { note -> viewModel.toggleCategory(note) }
    )

    private var recognizer: IRecognizer? = null
    private var recordManager: RecordManager? = null
    private var currentAudioFile: File? = null
    private var isRecording = false
    private val player = AudioPlayer()

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        val ok = grants.values.all { it }
        if (ok && !isRecording) startRecording() else showHint(getString(R.string.permission_denied))
    }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        _binding = FragmentHomeBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        binding.recycler.layoutManager = LinearLayoutManager(requireContext())
        binding.recycler.adapter = adapter

        binding.tabs.addOnTabSelectedListener(object : com.google.android.material.tabs.TabLayout.OnTabSelectedListener {
            override fun onTabSelected(tab: com.google.android.material.tabs.TabLayout.Tab) {
                viewModel.switchTab(if (tab.position == 0) "TODO" else "DONE")
            }
            override fun onTabUnselected(tab: com.google.android.material.tabs.TabLayout.Tab) {}
            override fun onTabReselected(tab: com.google.android.material.tabs.TabLayout.Tab) {}
        })

        binding.micButton.setOnClickListener {
            if (isRecording) stopRecording() else checkPermissionsAndRecord()
        }

        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.notes.collect { adapter.submitList(it) }
        }
    }

    private fun checkPermissionsAndRecord() {
        val needed = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            needed += Manifest.permission.POST_NOTIFICATIONS
        }
        val missing = needed.filter {
            ContextCompat.checkSelfPermission(requireContext(), it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isEmpty()) startRecording() else permissionLauncher.launch(missing.toTypedArray())
    }

    private fun startRecording() {
        isRecording = true
        binding.micButton.isSelected = true
        binding.recordHint.isVisible = true
        binding.recordHint.text = getString(R.string.recording)
        val file = File(requireContext().filesDir, "records/rec_${System.currentTimeMillis()}.wav")
        currentAudioFile = file
        recognizer = RecognizerFactory.create(requireContext())
        recordManager = RecordManager(file)
        recordManager!!.start { data, len -> recognizer?.writeAudio(data, len) }
        recognizer!!.start { partial ->
            binding.recordHint.text = partial.ifBlank { getString(R.string.recording) }
        }
    }

    private fun stopRecording() {
        isRecording = false
        binding.micButton.isSelected = false
        binding.recordHint.text = getString(R.string.recognizing)
        recognizer?.stop(
            onResult = { text -> handleResult(text) },
            onError = { err ->
                binding.recordHint.text = getString(R.string.recognize_failed, err)
                cleanup()
            }
        )
    }

    private fun handleResult(text: String) {
        cleanup()
        if (text.isBlank()) {
            binding.recordHint.text = getString(R.string.empty_result)
            return
        }
        val audio = currentAudioFile
        currentAudioFile = null
        binding.recordHint.isVisible = false
        (activity as? MainActivity)?.showRecordConfirm(text, audio?.absolutePath)
    }

    private fun cleanup() {
        recordManager?.stop()
        recordManager = null
        recognizer?.release()
        recognizer = null
    }

    private fun openDetail(note: Note, cardView: View) {
        parentFragmentManager.commit {
            setReorderingAllowed(true)
            addSharedElement(cardView, "note_detail")
            replace(R.id.fragment_container, DetailFragment.newInstance(note.id))
            addToBackStack("detail")
        }
    }

    private fun showHint(msg: String) {
        binding.recordHint.isVisible = true
        binding.recordHint.text = msg
    }

    override fun onDestroyView() {
        cleanup()
        player.stop()
        _binding = null
        super.onDestroyView()
    }
}
