from django.urls import reverse
from rest_framework.test import APITestCase
from api.models import Word, GameSession


class GameFlowTests(APITestCase):
    def setUp(self):
        # Ensure there is at least one 5-letter word available
        Word.objects.create(text="apple", length=5, is_active=True)

    def test_start_game_success(self):
        url = reverse('start-game')
        resp = self.client.post(url, {"word_length": 5, "max_attempts": 6}, format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("session_id", data)
        self.assertEqual(data["word_length"], 5)
        self.assertEqual(data["attempts_used"], 0)
        self.assertEqual(data["status"], "IN_PROGRESS")

    def test_guess_and_win(self):
        # Start session
        start = self.client.post(reverse('start-game'), {"word_length": 5}, format="json").json()
        session_id = start["session_id"]
        # Force target to "apple"
        session = GameSession.objects.get(pk=session_id)
        session.target_word = Word.objects.get(text="apple")
        session.save()

        # Submit correct guess
        resp = self.client.post(reverse('guess'), {"session_id": session_id, "guess": "apple"}, format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["is_correct"])
        self.assertEqual(data["status"], "WON")
        self.assertEqual(len(data["feedback"]), 5)

    def test_session_detail(self):
        start = self.client.post(reverse('start-game'), {"word_length": 5}, format="json").json()
        session_id = start["session_id"]
        resp = self.client.get(reverse('session-detail', kwargs={"session_id": session_id}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["session_id"], session_id)

    def test_leaderboard_empty(self):
        resp = self.client.get(reverse('leaderboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)
