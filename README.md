# word-guessing-game-platform-256493-256516

## Backend quick start (migrations and seed)
- Apply migrations:
  - cd backend_api
  - python manage.py migrate
- Seed playable word list (normally auto-seeded via data migration; run if needed):
  - python manage.py seed_words