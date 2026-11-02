# Rapid Quiz — Backend (Django + DRF)

5 kategoride 20'şer soru soran, soru başına 5 saniye süre tanıyan, üyeliksiz bilgi yarışması. Ayrıntılı tasarım: `docs/rapid-quiz-proje-dokumani.md` (kaynak doküman; çelişki olursa o geçerlidir). Frontend ayrı repoda: `C:\Users\Süleyman\PycharmProjects\RapidQuizFrontend` (Vue 3).

## Değişmez kurallar

- **Puan, süre ve doğru cevap kontrolü her zaman sunucuda yapılır.** İstemciden gelen hiçbir süre/puan bilgisine güvenilmez.
- Soru yanıtında doğru şık bilgisi (`is_correct`) **asla** bulunmaz; `correct_choice_id` yalnızca cevap gönderildikten sonra döner.
- Oyun kuralları `apps/quiz/services.py` içindedir; view'lar yalnızca isteği doğrular ve servisi çağırır.
- API çerezsizdir: oturum `X-Session-Token` başlığıyla taşınır. Token'ın yalnızca SHA-256 özeti saklanır; ham IP saklanmaz (`ip_hash`).
- Tüm hatalar tek biçimdedir: `{"error": {"code", "message", "details"}}` (`apps/core/exceptions.py`). Yeni hata için `APIError(code, message, status_code)` kullan.
- Kırıcı API değişikliği `/api/v2/` altında yapılır; `/api/v1/` bozulmaz.
- Sırlar ortam değişkeninde; `.env` repoya girmez, `.env.example` güncel tutulur.
- Kod yorumları ve kullanıcıya dönen mesajlar Türkçe.

## Oyun kuralları

| Kural | Değer |
| --- | --- |
| Soru sayısı | 20 (kategori havuzundan rastgele, tekrarsız) |
| Şık | 4, sırası her oturumda karıştırılır (`choice_order`) |
| Süre | 5000 ms, sunucu saatiyle (`served_at`) |
| Ağ toleransı | +700 ms; bu sürede gelen cevap kabul edilir, bonus 0 |
| 5700 ms sonrası | Süre aşımı, 0 puan |
| Doğru cevap | `100 + round(50 × max(0, 5000 − t) / 5000)`; yarımlar yukarı yuvarlanır (`calculate_points`) |
| Süre aşımının süresi | Toplam süreye her zaman 5000 ms eklenir (soru atlayarak eşitlik bozmada avantaj sağlanamaz) |
| Yanlış / süre aşımı | 0 puan, eksi puan yok |
| Geri dönme / atlama | Yok |
| Zorluk çarpanı | Yok (`difficulty` yalnızca saklanır) |
| Yanlış cevaptan sonra | Doğru şık gösterilir |
| Eşitlik bozma | 1) yüksek puan 2) düşük toplam süre 3) erken bitiren |
| Skor tablosu | Kategori bazlı, tüm zamanların ilk 10'u |
| Oturum ömrü | 10 dk; aşan `active` oturum her istekte `expired` sayılır |
| Soru/şık uzunluğu | en fazla 90 / 40 karakter (DB ve admin'de doğrulanır) |

## API (`/api/v1/`)

| Metot | Uç nokta | Durum |
| --- | --- | --- |
| GET | `/categories/` | ✅ Aşama 1 |
| GET | `/health/` | ✅ Aşama 1 |
| GET | `/schema/`, `/docs/` | ✅ Aşama 1 |
| POST | `/sessions/` `{category, platform}` → `{session_id, session_token, category, total_questions, time_limit_ms}` | ✅ Aşama 2 |
| GET | `/sessions/{id}/question/` (ilk istekte süre başlar; tekrarda kalan süre döner) | ✅ Aşama 2 |
| POST | `/sessions/{id}/answer/` `{question_id, choice_id\|null}` | ✅ Aşama 2 |
| GET | `/sessions/{id}/result/` → `{status, category, total_questions, total_score, correct_count, total_response_ms}` | ✅ Aşama 2 |
| POST | `/sessions/{id}/score/` `{player_name}` → 201 `{rank, in_top_10, score, leaderboard}` | ✅ Aşama 3 |
| GET | `/leaderboard/?category={slug}` → `{category, leaderboard}`; satır: `{rank, player_name, score, correct_count, created_at}` | ✅ Aşama 3 |

### Hata kodları

| code | HTTP | Ne zaman |
| --- | --- | --- |
| `validation_error` | 400 | Eksik/geçersiz alan (ör. isim 2–20 karakter değil) |
| `invalid_token` | 401 | `X-Session-Token` eksik/yanlış |
| `not_found` | 404 | Oturum veya kategori yok |
| `question_mismatch` | 409 | Gönderilen `question_id` sıradaki soru değil |
| `already_answered` | 409 | Soru zaten cevaplanmış |
| `session_not_finished` | 409 | Bitmemiş oturum için skor kaydı |
| `score_already_submitted` | 409 | İsim ikinci kez gönderildi |
| `session_expired` | 410 | Oturum 10 dakikadan eski |
| `rate_limited` | 429 | İstek sınırı aşıldı |

Ek olarak genel durumlar için `method_not_allowed` (405), `forbidden` (403), `server_error` (500) ve oyun motoruna özgü `session_finished` (409, 20. sorudan sonra soru istendi), `category_unavailable` (409, kategoride 20'den az geçerli soru var) ve `score_rejected` (422, cevaplar insan için fazla hızlı; bkz. aşağıda) kullanılır.

Throttle (`apps/quiz/throttles.py`, IP başına): dakikada 10 oturum, 120 cevap, 240 soru/sonuç, 120 skor tablosu; skor kaydı saatte 20. Sayaçlar yerel bellekte: her gunicorn işçisi ayrı sayar, gerçek sınır işçi sayısı kadar esner. IP, `NUM_PROXIES` ayarına göre okunur (dev: 0, prod: 1; **ilk deploy'da App Platform'un gerçek vekil sayısı doğrulanmalı**, yanlış değer ya herkesi tek kovaya ya da sahte `X-Forwarded-For`'u geçerli sayar). Skor yalnızca `finished` oturumdan, bir kez, sunucunun hesapladığı puanla yazılır (istemci yalnızca `player_name` gönderir; fazladan alanlar yok sayılır). Kayıttan sonra oturum `submitted` olur. Son soru terk edilmişse oturum skor kaydı sırasında süre aşımıyla bitmiş sayılır.

İsim (`apps/leaderboard/validators.py`): NFKC normalleştirme, baştaki/sondaki boşluk atılır, art arda boşluklar teke iner; 2–20 karakter; yalnızca harf/rakam/boşluk/`_` (HTML ve görünmez karakterler girmez); en az bir harf/rakam; küfür filtresi (`profanity.py`). Filtre bilerek küçük tutulmuş basit bir listedir: Türkçe karakterleri ASCII'ye indirir, `s1ktir` gibi rakam ikamelerini ve `fuuuck`/`amk123` gibi uzatma/süslemeleri çözer, kısa kelimelerde ("amk", "dick") yalnızca tam sözcük eşleşmesi arar (Scunthorpe sorununu önlemek için). Hata mesajı eşleşen kelimeyi söylemez. Uygunsuz skorlar admin panelinden silinebilir.

**Skor şişirme önlemi:** soru başına ortalama cevap süresi `SCORE_MIN_AVG_RESPONSE_MS`'nin (varsayılan 500 ms, tüm ortamlarda aynı; 0 kapatır) altındaysa `POST /score/` **422 `score_rejected`** döner ve skor yazılmaz (oturum `finished` kalır, tekrar denemek yine reddedilir). Süre sunucu saatiyle, soru sunulduktan cevabın ulaşmasına kadar ölçülür (ağ gecikmesi dahil) ve süre aşımı sorular 5000 ms sayılır; yani gerçek bir oyuncuyu etkilemez, yalnızca soru bankasını toplayıp anında cevaplayan basit botları durdurur (yavaşlatılmış bir bot geçer; ileride gerekirse bot doğrulaması eklenir). Reddedilen denemeler `WARNING` olarak günlüğe yazılır (oturum, ortalama süre, ip özetinin ilk 12 karakteri). Testlerde varsayılan olarak kapalıdır (`tests/conftest.py`, `speed_guard`); `tests/test_speed_guard.py` açıp sınar. **Uçtan uca testler gerçekçi bekleme (≥ ~700 ms/soru) yapmalıdır.**

Sıralama: puan ↓, toplam süre ↑, `created_at` ↑ (skorda `created_at` oynanış **bitiş zamanıdır**, isim girme zamanı değil), son olarak `id`. Sıra (`rank`) aynı kategorideki daha iyi kayıt sayısı + 1'dir.

## Yapı

```text
config/settings/{base,dev,prod}.py   # dev: DEBUG, prod: güvenlik başlıkları + env'den okuma
apps/core/        # hata biçimi (exceptions.py), health, JSON 404/500
apps/catalog/     # Category, Question, Choice, admin, load_questions (loader.py)
apps/quiz/        # QuizSession, SessionQuestion, services.py (oyun motoru), throttles.py, expire_sessions
apps/leaderboard/ # ScoreEntry, services.py (skor kaydı, sıra), validators.py + profanity.py (isim)
data/categories.json, data/questions/<kategori-slug>.json
tests/
```

Tablo adları dokümandaki gibidir (`categories`, `questions`, `choices`, `quiz_sessions`, `session_questions`, `score_entries`). `Choice` için partial unique constraint soru başına en fazla bir doğru şıkkı garanti eder; "tam 4 şık, tam 1 doğru" kuralını admin formset'i ve `load_questions` doğrular.

## Komutlar

```bash
docker compose up                                        # Django + PostgreSQL 16
docker compose exec web python manage.py migrate
docker compose exec web python manage.py load_questions  # kategoriler + sorular (tekrar çalıştırmak güvenli)
docker compose exec web python manage.py expire_sessions # eski skorsuz oturumları temizler (--days 7, --dry-run)
pytest                                                   # testler (PostgreSQL gerekir)
ruff check . && ruff format .
```

Docker olmadan: PostgreSQL 16 taşınabilir sürüm olarak `C:\Users\Süleyman\RapidQuizTools\postgres` altında kuruludur (kullanıcı/şifre/veritabanı `rapidquiz`, `localhost:5432`; compose ile aynı bilgiler, yani `DATABASE_URL` vermeden çalışır). Sunucu bilgisayar yeniden başlayınca kapanır; yolda `ü` olduğu için `initdb`/`pg_ctl` ASCII kısa yolla (`SLEYMA~1`) çalıştırılmalıdır:

```bash
C:/Users/SLEYMA~1/RapidQuizTools/postgres/pgsql/bin/pg_ctl.exe -D C:/Users/SLEYMA~1/RapidQuizTools/postgres/data -l C:/Users/SLEYMA~1/RapidQuizTools/postgres/postgres.log start
```

Docker Compose'un `db` servisi de 5432'yi kullanır; ikisini aynı anda çalıştırma (biri kapalı olmalı). Hızlı deneme için `DATABASE_URL=sqlite:///db.sqlite3` de verilebilir. `SessionQuestion.choice_order` dokümandaki `smallint[]` yerine `JSONField`'dır (şık kimliklerinin listesi; PostgreSQL'de `jsonb`), böylece SQLite ile de çalışır. SQLite `select_for_update`'i yok sayar: oturum satırı kilidiyle sağlanan eşzamanlılık güvenliği (çift cevap, çift tıklama) yalnızca PostgreSQL'e karşı doğrulanabilir (`tests/test_quiz_concurrency.py`, SQLite'ta atlanır). Kilit kaldırıldığında bu testler başarısız olur: 8 eşzamanlı aynı cevabın hepsi 200 döner, puan 8 kez eklenir. CI testleri PostgreSQL ile koşmalıdır.

## Test kuralları

- Zaman testlerinde gerçek bekleme yok: `time-machine` ile saat dondurulur.
- Zorunlu testler: yanıtta doğru şık yok; 5000 ms içinde `100 + bonus`, 5700 ms sonrası 0 puan; aynı soruyu ikinci kez istemek süreyi sıfırlamaz; cevaplanmamış soru varken sıradaki verilmez; ikinci cevap `already_answered`; bitmemiş oturumdan skor kaydı yok, bitmişten bir kez; eşit puanda sıralama; yanlış token 401; throttle aşımı 429.
- Her aşama sonunda `ruff` + `pytest` temiz olmalı; Aşama 2 ve 3 hile önleme açısından ayrıca incelenmeli.

## Yol haritası

1. ✅ **Aşama 1 — Backend temeli** (Django iskeleti, catalog, load_questions, categories/health/OpenAPI, Docker)
2. ✅ **Aşama 2 — Oyun motoru** (QuizSession, SessionQuestion, services.py, sessions uç noktaları, throttling, zorunlu testler)
3. ✅ **Aşama 3 — Skor tablosu** (ScoreEntry, isim doğrulama + küfür filtresi, `POST /score/`, `GET /leaderboard/`, `expire_sessions`)
4. **Aşama 4 — Frontend** (ayrı repo)
5. **Aşama 5 — İçerik ve yayın** (kategori başına 60+ soru, CI, DigitalOcean)

## CI (GitHub Actions)

`.github/workflows/ci.yml` her pull request'te ve `main`'e push'ta çalışır, iki iş: **"Lint ve testler (PostgreSQL)"** (ruff, eksik migration kontrolü, OpenAPI doğrulaması, PostgreSQL 16 servis konteyneri ile tüm testler; eşzamanlılık testleri yalnızca burada anlamlıdır) ve **"Docker imajı derlenir"** (üretim imajı, `collectstatic` dahil). Güvenlik: iş akışı yalnızca `contents: read` izniyle çalışır, kimlik bilgisi saklamaz; üçüncü taraf Action'lar sürüm etiketi yerine **commit SHA'sıyla sabitlenmiştir** (yorumda sürüm yazar). `.github/dependabot.yml` Action, pip ve Docker güncellemeleri için haftalık PR açar; yeni Action eklerken SHA'yı `git ls-remote --tags <repo>` ile bul.

**Dal koruması** (GitHub → Settings → Branches → `main` için kural; `deploy_on_push` testlerden bağımsız yayına aldığı için şart): "Require a pull request before merging", "Require status checks to pass" ve yukarıdaki iki işin adını seç, "Do not allow bypassing". Koruma açılınca `main`'e doğrudan push yapılamaz; değişiklikler dal + PR ile gelir.

## Deploy notları (DigitalOcean App Platform)

- Gunicorn `0.0.0.0:${PORT}` (8080) dinler; migration'lar ayrı `PRE_DEPLOY` job ile çalışır, container açılışında değil.
- `prod.py` `DATABASE_URL` olmadan import edilebilmeli (collectstatic build sırasında DB yok).
- HTTPS yük dengeleyicide sonlanır: `SECURE_PROXY_SSL_HEADER` zorunlu; `/api/v1/health/` SSL yönlendirmesinden muaftır.
- `main` dalı korunmalı: `deploy_on_push` testlerden bağımsız yayına alır.
