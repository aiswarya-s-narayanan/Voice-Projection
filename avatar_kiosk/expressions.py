"""Small, explicit English text cues and Ditto emotion presets.

Thinking/suggestion are conversational cues, not native Ditto emotion labels.
"""
import re

EMOTIONS = ("neutral", "happy", "sad", "surprise", "thinking", "suggestion", "curious", "concerned")
DITTO_EMOTIONS = {"neutral": 4, "happy": 3, "sad": 5, "surprise": 6,
                  "thinking": 4, "suggestion": [3, 4], "curious": 4, "concerned": 4}


def resolve_emotion(emotion="auto", text=""):
    if emotion != "auto":
        if emotion not in EMOTIONS:
            raise ValueError("Unknown emotion: " + emotion)
        return emotion
    text = text.lower().replace("’", "'")
    # Priority favors apologies over greetings, and explicit cues over punctuation.
    cues = (
        ("sad", r"\b(sorry|sad|unfortunately|apolog\w*|regret|disappointed|unavailable|sold out)\b"),
        ("concerned", r"\b(worried|concerned|worry|pain|hurt|trouble|anxious)\b"),
        ("surprise", r"\b(wow|surpris\w*|amazing|unbelievable|oh my)\b"),
        ("thinking", r"\b(hmm|let me (think|check|see)|wonder|not sure|thinking)\b"),
        ("suggestion", r"\b(recommend\w*|suggest\w*|how about|you could|you might|why not|try our)\b"),
        ("happy", r"\b(happy|glad|great|wonderful|welcome|thank\w*|hello|enjoy|delighted|excellent)\b"),
    )
    for label, pattern in cues:
        if re.search(pattern, text):
            return label
    if "?" in text or re.search(r"\b(curious|tell me more)\b", text):
        return "curious"
    return "neutral"
