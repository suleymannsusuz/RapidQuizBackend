"""Quiz testleri için küçük yardımcılar (API üzerinden oyun oynatır)."""

from apps.catalog.models import Choice


class Game:
    """Tek bir oturumu API üzerinden yöneten test yardımcısı."""

    def __init__(self, client, slug="yazilim", platform="web"):
        self.client = client
        response = client.post(
            "/api/v1/sessions/", {"category": slug, "platform": platform}, format="json"
        )
        assert response.status_code == 201, response.content
        body = response.json()
        self.session_id = body["session_id"]
        self.token = body["session_token"]
        self.start_response = body

    @property
    def base(self):
        return f"/api/v1/sessions/{self.session_id}"

    def headers(self, token="__own__"):
        token = self.token if token == "__own__" else token
        return {"HTTP_X_SESSION_TOKEN": token} if token is not None else {}

    def question(self, token="__own__"):
        return self.client.get(f"{self.base}/question/", **self.headers(token))

    def answer(self, question_id, choice_id, token="__own__"):
        return self.client.post(
            f"{self.base}/answer/",
            {"question_id": question_id, "choice_id": choice_id},
            format="json",
            **self.headers(token),
        )

    def result(self, token="__own__"):
        return self.client.get(f"{self.base}/result/", **self.headers(token))

    def correct_choice(self, question_id):
        return Choice.objects.get(question_id=question_id, is_correct=True).id

    def wrong_choice(self, question_id):
        return Choice.objects.filter(question_id=question_id, is_correct=False).first().id

    def play_correct(self, clock=None, delay_ms=0):
        """Mevcut soruyu getirir ve `delay_ms` sonra doğru cevaplar; (soru, cevap) döner."""
        question = self.question().json()
        if clock and delay_ms:
            clock.shift(delay_ms / 1000)
        qid = question["question"]["id"]
        answer = self.answer(qid, self.correct_choice(qid))
        return question, answer
