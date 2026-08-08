package com.example.voicenote.ui.home

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.core.view.isVisible
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.example.voicenote.data.Note
import com.example.voicenote.databinding.ItemNoteCardBinding
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class NoteAdapter(
    private val onClick: (Note, View) -> Unit,
    private val onToggle: (Note) -> Unit
) : ListAdapter<Note, NoteAdapter.VH>(DIFF) {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val binding = ItemNoteCardBinding.inflate(
            LayoutInflater.from(parent.context), parent, false
        )
        return VH(binding)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        holder.bind(getItem(position))
    }

    inner class VH(private val binding: ItemNoteCardBinding) : RecyclerView.ViewHolder(binding.root) {

        fun bind(note: Note) {
            binding.apply {
                tvSummary.text = note.summary ?: note.content.take(12)
                tvContent.text = note.content
                tagTime.text = note.eventTime?.let(::formatMillis)
                tagLocation.text = note.location
                tagPerson.text = note.person
                tagTopic.text = note.topic
                // 空标签隐藏
                tagTime.isVisible = note.eventTime != null
                tagLocation.isVisible = !note.location.isNullOrBlank()
                tagPerson.isVisible = !note.person.isNullOrBlank()
                tagTopic.isVisible = !note.topic.isNullOrBlank()
                // 待办显示完成按钮
                btnDone.isVisible = note.category == "TODO"
                btnDone.setOnClickListener { onToggle(note) }
                btnRestore.isVisible = note.category == "DONE"
                btnRestore.setOnClickListener { onToggle(note) }
                cardRoot.transitionName = "note_detail"
                cardRoot.setOnClickListener { onClick(note, cardRoot) }
            }
        }
    }

    companion object {
        private val DIFF = object : DiffUtil.ItemCallback<Note>() {
            override fun areItemsTheSame(oldItem: Note, newItem: Note) = oldItem.id == newItem.id
            override fun areContentsTheSame(oldItem: Note, newItem: Note) = oldItem == newItem
        }

        private fun formatMillis(ts: Long): String =
            SimpleDateFormat("M月d日 HH:mm", Locale.CHINA).format(Date(ts))
    }
}
