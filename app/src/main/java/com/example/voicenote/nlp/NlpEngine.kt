package com.example.voicenote.nlp

object NlpEngine {
    fun analyze(text: String): NlpResult {
        val time = TimeExtractor.extract(text)
        return NlpResult(
            intent = IntentClassifier.classify(text),
            timeText = time.timeText,
            eventTime = time.timestamp,
            location = LocationExtractor.extract(text),
            person = PersonExtractor.extract(text),
            summary = SummaryExtractor.extract(text),
            topic = TopicExtractor.extract(text)
        )
    }
}
