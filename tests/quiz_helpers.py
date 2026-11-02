"""Quiz testleri için küçük yardımcılar (API üzerinden oyun oynatır)."""

import threading

from django.db import connections

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

    def finish(self, correct=True):
        """20 soruyu da anında cevaplar (hepsi doğru ya da hepsi yanlış)."""
        for _ in range(20):
            qid = self.question().json()["question"]["id"]
            choice = self.correct_choice(qid) if correct else self.wrong_choice(qid)
            self.answer(qid, choice)

    def submit_score(self, player_name, token="__own__"):
        return self.client.post(
            f"{self.base}/score/",
            {"player_name": player_name},
            format="json",
            **self.headers(token),
        )


def run_in_parallel(worker, count):
    """`worker(index)` fonksiyonunu aynı anda başlayan iş parçacıklarında çalıştırır."""
    barrier = threading.Barrier(count)
    results = [None] * count
    errors = []

    def target(index):
        try:
            barrier.wait()
            results[index] = worker(index)
        except Exception as exc:  # noqa: BLE001 - test hatası olarak ana iş parçacığına taşınır
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=target, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors, errors
    return results
