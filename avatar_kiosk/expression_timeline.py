"""Sentence boundaries and validated, audio-relative expression cues."""
import math
import re

from .expressions import resolve_emotion


def split_sentences(text):
    # Keep decimals and common titles intact; retain punctuation for Piper.
    protected = re.sub(r'\b(?:Mr|Mrs|Ms|Dr|Prof|St)\.',
                       lambda m: m[0].replace('.', '\x00'), text, flags=re.I)
    return [part.replace('\x00', '.').strip() for part in
            re.split(r'(?<=[.!?])\s+|\n+', protected.strip()) if part.strip()]


def validate_timeline(cues):
    if not isinstance(cues, list) or not 1 <= len(cues) <= 100:
        raise ValueError('Expression timeline must contain 1 to 100 cues')
    result = []
    previous = -1
    for cue in cues:
        if not isinstance(cue, dict):
            raise ValueError('Each expression cue must be an object')
        start = cue.get('start')
        if (isinstance(start, bool) or not isinstance(start, (int, float))
                or not math.isfinite(start) or not 0 <= start < 90
                or start <= previous):
            raise ValueError('Cue starts must increase and be between 0 and 90 seconds')
        if not result and start != 0:
            raise ValueError('The first expression cue must start at zero')
        label = cue.get('emotion')
        if not isinstance(label, str) or label == 'auto':
            raise ValueError('Each cue needs an explicit emotion')
        result.append({'start': float(start), 'emotion': resolve_emotion(label)})
        previous = start
    return result


def cue_at(cues, seconds):
    selected = cues[0]
    for cue in cues[1:]:
        if cue['start'] > seconds:
            break
        selected = cue
    return selected
