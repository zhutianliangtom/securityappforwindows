package com.example.voicenote.ui.record

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.example.voicenote.data.Note
import com.example.voicenote.data.NoteRepository
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.launch

class RecordConfirmViewModel(private val repository: NoteRepository) : ViewModel() {

    private val _savedId = MutableSharedFlow<Long>()
    val savedId: SharedFlow<Long> = _savedId

    fun save(note: Note) {
        viewModelScope.launch {
            val id = repository.insert(note)
            _savedId.emit(id)
        }
    }

    class Factory(private val repository: NoteRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T =
            RecordConfirmViewModel(repository) as T
    }
}
