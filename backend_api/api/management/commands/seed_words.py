from django.core.management.base import BaseCommand
from api.models import Word

SEED_WORDS = [
    "apple", "brave", "crane", "delta", "eager", "flame",
    "grape", "hover", "ivory", "jolly", "karma", "lemon",
    "mango", "noble", "ocean", "pride", "quake", "raven",
    "solar", "tiger", "ultra", "vivid", "whale", "xenon",
    "young", "zebra",
]


class Command(BaseCommand):
    help = "Seed a minimal playable word list if the Words table is empty."

    def handle(self, *args, **options):
        # PUBLIC_INTERFACE
        # This command is idempotent and safe to run multiple times.
        count_before = Word.objects.count()
        if count_before > 0:
            self.stdout.write(self.style.WARNING(f"Words already present: {count_before}. No action taken."))
            return

        objs = [Word(text=w, length=len(w), is_active=True) for w in SEED_WORDS]
        Word.objects.bulk_create(objs, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(SEED_WORDS)} words."))
