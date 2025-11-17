from typing import List

from django.db import transaction

from .models import Word

DEFAULT_SEED: List[str] = [
    "apple", "brave", "crane", "delta", "eager", "flame",
    "grape", "hover", "ivory", "jolly", "karma", "lemon",
    "mango", "noble", "ocean", "pride", "quake", "raven",
    "solar", "tiger", "ultra", "vivid", "whale", "xenon",
    "young", "zebra",
]


# PUBLIC_INTERFACE
def ensure_seed_words(seed_words: List[str] | None = None) -> int:
    """Ensure the Word table has at least a minimal playable list.

    Returns number of words inserted (0 if already present).
    """
    if Word.objects.exists():
        return 0
    words = seed_words or DEFAULT_SEED
    with transaction.atomic():
        Word.objects.bulk_create([Word(text=w, length=len(w), is_active=True) for w in words], ignore_conflicts=True)
    return len(words)
