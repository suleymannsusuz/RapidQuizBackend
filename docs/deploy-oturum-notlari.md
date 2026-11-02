# Deploy hazırlık notları (DigitalOcean App Platform, manuel tarayıcı akışı)

Bu dosya, deploy'u yapacağımız oturum için hazırlanmıştır (2026-11-02). **Kullanıcı deploy'u `doctl` ile değil, DigitalOcean panelinden (tarayıcıdan) elle yapacak.** Oturumun başında kullanıcı büyük olasılıkla şunu isteyecek: *"Sıfırdan DigitalOcean'a bir app ve bir static site nasıl deploy ederim, anlat."* Bu dosya, o anlatımın doğru değerlerle ve doğru sırayla yapılması içindir.

## Nasıl davranmalı

- Anlatımı **Türkçe, adım adım, "şuraya tıkla / şunu yaz"** biçiminde ver. Kullanıcı panelde farklı bir ekran görürse ekran görüntüsü ya da ekrandaki metni göndermesini iste; DigitalOcean arayüzü zamanla değişir, aşağıdaki adım adları **güncel panelde doğrulanmalıdır**.
- Resmî DigitalOcean belgesini (ayar adları, panel adımları) okumadan önce **kullanıcıya sor**. Önceki oturumda belge okuyan bir alt ajan çağrısı kullanıcı tarafından reddedildi; sebebi söylenmedi. İzin verirse Browser panelinde belgeyi gösterebilirsin.
- DigitalOcean hesabında **hiçbir işlem yapma** (ücretli hizmet, kullanıcının hesabı). Sen anlatırsın, kullanıcı tıklar. Gizli değerleri (SECRET_KEY, parolalar) sohbete yazdırma; kullanıcının kendi makinesinde üretmesini söyle.
- Kararlar kullanıcıya aittir; seçenek varsa sor. Kullanıcı kendi alan adını kullanacak, **alan adını henüz bilmiyoruz** (sor).

## Mimari (proje dokümanı bölüm 9, 10 ve 13)

İki ayrı App, ayrı repo, ayrı deploy:

| App | Bileşenler | Repo |
| --- | --- | --- |
| `rapid-quiz-api` | **Web Service** (Dockerfile'dan, gunicorn, port 8080) + **Pre-Deploy Job** (`migrate`) + **Dev Database** (PostgreSQL) | `suleymannsusuz/RapidQuizBackend`, dal `main` |
| `rapid-quiz-web` | **Static Site** (Vite derlemesi) | `suleymannsusuz/RapidQuizFrontend`, dal `main` |

Proje dokümanındaki `doctl` bölümü (bölüm 13, "İlk kurulum") **kullanılmayacak**. `.do/app.yaml` dosyaları iki repoda duruyor ve değerlerin referansıdır; panelde elle form doldurulacaksa aynı değerler girilir (panel bir app spec yapıştırmaya da izin veriyorsa kullanılabilir, doğrulanmalı). Repo adları artık gerçek değerlerle yazılı; `instance_size_slug` ve alan adı yer tutucu kaldı.

## Backend (Web Service) değerleri

| Alan | Değer |
| --- | --- |
| Kaynak | GitHub → `suleymannsusuz/RapidQuizBackend`, dal `main`, "Autodeploy" açık |
| Kaynak dizini | `/` (kök) |
| Tür | Web Service (panel `Dockerfile`'ı algılamalı) |
| Dockerfile yolu | `Dockerfile` |
| HTTP portu | `8080` (Dockerfile `PORT=8080` ve `gunicorn --bind 0.0.0.0:${PORT}`) |
| Sağlık kontrolü | HTTP, yol `/api/v1/health/`, başlangıç gecikmesi ~15 sn (veritabanı da denenir; 503 dönerse deploy ilerlemez) |
| Instance | 1 adet, en küçük paylaşımlı (fiyat sayfasında `apps-s-1vcpu-0.5gb`, 512 MiB, aylık ~$5) |
| Bölge | Frankfurt (`fra`) |
| Pre-Deploy Job | ad `migrate`, komut `python manage.py migrate --noinput` (aynı repo/Dockerfile; başarısız olursa yeni sürüm yayına alınmaz) |
| Veritabanı | **Dev Database**, PostgreSQL, ad `db` (aylık ~$7, yedeksiz, bkz. riskler) |

### Ortam değişkenleri (backend)

`config/settings/prod.py` ve `base.py` bunları okur. "Kim girer" sütunu: **K** = kullanıcı panelden girer.

| Değişken | Değer | Not |
| --- | --- | --- |
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` | |
| `SECRET_KEY` | **Gizli (Encrypt/Secret)**, 50+ karakter rastgele | K. Üretim: `python -c "import secrets; print(secrets.token_urlsafe(60))"` (kendi makinesinde). Repoya ya da sohbete yazılmaz |
| `DATABASE_URL` | `${db.DATABASE_URL}` | Panel veritabanı bileşeninden bağlar; Job ve Service ikisi de görmeli (app seviyesinde tanımla) |
| `ALLOWED_HOSTS` | `${APP_DOMAIN}` ve (varsa) özel alan adı, virgülle: `${APP_DOMAIN},api.rapidquiz.<alan-adı>` | Boş bırakılırsa tüm istekler 400 |
| `CORS_ALLOWED_ORIGINS` | `https://<frontend adresi>` (virgülle birden çok) | **Frontend'in tam adresi, sonunda `/` yok.** Önce frontend oluşturulup adresi öğrenilmeli |
| `CSRF_TRUSTED_ORIGINS` | `https://<api adresi>` | Admin girişi için |
| `ADMIN_URL` | tahmin edilmesi zor yol, sonu `/`: örn. `yonetim-x7q2k9/` | Varsayılan `admin/` bırakılmaz (doküman bölüm 8) |
| `NUM_PROXIES` | `1` (varsayılan prod değeri) | **Yayından sonra doğrulanmalı** (aşağıda). Yanlışsa IP'ye göre sınırlama bozulur |
| `SECURE_HSTS_SECONDS` | başlangıçta `3600` (varsayılan); her şey oturunca `31536000` | Büyük değer geri alınamaz, tarayıcılar hatırlar |
| `SCORE_MIN_AVG_RESPONSE_MS` | `500` (varsayılan; **dokunma**) | Bot önlemi; tüm ortamlarda aynı |
| `SECURE_SSL_REDIRECT` | varsayılan `true` | Sağlık kontrolü yoluna muaf (`/api/v1/health/`) |
| `LOG_LEVEL` | `INFO` | |

`.env` yok; hepsi panelden. `PORT` değerini panel kendisi verir.

## Frontend (Static Site) değerleri

| Alan | Değer |
| --- | --- |
| Kaynak | GitHub → `suleymannsusuz/RapidQuizFrontend`, dal `main`, autodeploy açık |
| Tür | Static Site |
| Build komutu | `npm ci && npm run build` |
| Çıktı dizini | `dist` (açıkça yaz) |
| Index belgesi | `index.html` |
| **Catch-all belgesi** | `index.html` (**zorunlu**: Vue Router history modu; yoksa `/leaderboard` gibi adresleri yenileyince 404). `error_document` ile birlikte kullanılamaz |
| Ortam değişkeni | `VITE_API_BASE_URL` = `https://<api adresi>/api/v1`, **kapsam: Build Time** |
| Node sürümü | Vite 8 modern Node ister (yerelde 26, CI'da `lts/*`). Panelin varsayılan Node'u eskiyse derleme düşer: `package.json` `engines` alanı eklendi (`>=24`); düşerse DigitalOcean'ın Node sürüm ayarını (ör. `NODE_VERSION` ortam değişkeni) belgeden doğrula |

`VITE_` ile başlayan değerler derleme sırasında koda gömülür: backend adresi değişirse frontend yeniden build edilmeli ve bu değişkende gizli bilgi olmamalı.

## Sıra (neden bu sıra?)

Frontend adresi backend'in CORS ayarında, backend adresi de frontend'in build ayarında gerekli; bu döngü ikinci bir tur gerektirir. Kendi alan adı kullanılacaksa adresler baştan bilindiği için tek turda bitirilebilir.

1. **Hazırlık:** DigitalOcean hesabı (var) + GitHub bağlantısı: panelde GitHub'ı bağla, DigitalOcean GitHub uygulamasına **yalnızca bu iki repoya** erişim ver. `SECRET_KEY`'i kullanıcı kendi makinesinde üretir.
2. **Backend app'i oluştur:** Create → Apps → GitHub → `RapidQuizBackend` → Web Service + Dockerfile → değerleri gir → Pre-Deploy Job ekle → Dev Database ekle → ortam değişkenleri (`CORS_ALLOWED_ORIGINS` şimdilik geçici ya da alan adından) → bölge/boyut → oluştur. İlk deploy `https://<ad>.ondigitalocean.app` adresini verir.
3. **Sağlık kontrolünü doğrula:** `…/api/v1/health/` → `{"status":"ok","database":"ok"}`.
4. **Frontend static site'ı oluştur:** `VITE_API_BASE_URL` = backend adresi + `/api/v1` (Build Time). Verilen frontend adresini not al.
5. **Backend env'lerini güncelle:** `CORS_ALLOWED_ORIGINS` ve `CSRF_TRUSTED_ORIGINS` gerçek adreslerle → yeniden deploy.
6. **Konsol (panelde Console sekmesi, backend servisi):** `python manage.py createsuperuser` (admin hesabı; kullanıcı kendi parolasını seçer) ve `python manage.py load_questions` (kategoriler + sorular).
7. **Doğrulama listesi** (aşağıda).
8. **Özel alan adı** (kullanıcının alan adı): panelde Settings → Domains → ekle (`rapidquiz.<alan-adı>` frontend'e, `api.rapidquiz.<alan-adı>` backend'e); panelin gösterdiği DNS kaydını (genelde CNAME) alan adının kayıt şirketinde oluştur; TLS sertifikası otomatik; sonra `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `VITE_API_BASE_URL` yeni adreslerle güncellenir (frontend yeniden build olur).
9. **GitHub'da `main` dal koruması** (iki repo; `deploy_on_push` testten bağımsız yayına alır). Adımlar iki repo `CLAUDE.md`'sinde "CI" bölümünde.

## Yayın sonrası doğrulama listesi

Backend (kendi makinesinden, `<api>` yerine gerçek adres):

- `curl -i https://<api>/api/v1/health/` → 200
- `curl -s https://<api>/api/v1/categories/` → 5 kategori (soru yüklendiyse)
- `curl -i http://<api>/api/v1/categories/` → HTTPS'e yönlendirme (301); `…/health/` ise yönlendirmeden muaf
- CORS: `curl -i -H "Origin: https://<frontend>" https://<api>/api/v1/categories/` → `access-control-allow-origin: https://<frontend>`; başka bir `Origin` ile gelmemeli
- `https://<api>/admin/` → **404** (admin gizli yolda: `https://<api>/<ADMIN_URL>`); giriş çalışıyor mu
- `https://<api>/api/v1/docs/` Swagger açılıyor mu (herkese açık olması istenmiyorsa ileride kapatmayı düşün)
- Frontend: ana sayfada kategoriler, bir tam oyun, isim kaydı, skor tablosu, bir sayfayı yenileyince (`/leaderboard/fizik`) 404 olmaması

**`NUM_PROXIES` doğrulaması (yayından sonra mutlaka):** IP'ye göre sınırlama (dakikada 10 oturum) ve `ip_hash`, istemci IP'sini `X-Forwarded-For`'dan okur ve DigitalOcean'ın önünde kaç vekil olduğu bilinmiyor.
- Belirti, değer **çok küçükse**: herkes tek IP görünür (platformun IP'si) ve gerçek kullanıcılar birbirini sınırlar (ör. dakikada 11. kişi 429 alır).
- Belirti, değer **çok büyükse**: istemci `X-Forwarded-For` başlığını uydurarak sınırı atlar.
- Yöntem: çalışan servisin günlüklerinde gelen `X-Forwarded-For` değerini görmek için geçici olarak gunicorn'a `--access-logformat '%(h)s xff=%({x-forwarded-for}i)s "%(r)s" %(s)s'` ekleyen bir `run_command` kullan, kendi telefonundan (mobil veri) ve bilgisayarından birer istek at ve zincirdeki adres sayısıyla kendi IP'ni karşılaştır; doğru vekil sayısı, kendi IP'ni sondan hangi sırada bulduğundur. İş bitince `run_command`'ı kaldır (günlükte IP kalmasın). Alternatif: iki farklı ağdan art arda 11 oturum açmayı deneyip sınırın IP'ye göre ayrıldığını görmek.

## Dikkat edilecekler (riskler)

- **Dev database yedeksizdir ve uygulama silinirse silinir** (fiyat sayfası). Skor tablosu kalıcı veri; **gerçek oyuncu gelmeden yönetilen (managed) PostgreSQL'e geçilmeli** (fiyatı fiyat sayfasında ayrıca kontrol edilir; bu hazırlıkta bakılmadı). Geçerken `DATABASE_URL` ve veri taşıma planlanmalı.
- Gunicorn 2 işçiyle çalışır; throttle sayaçları işçi başına yerel bellektedir, gerçek sınır yaklaşık iki katına esner (kabul edilmiş).
- Sorular şimdilik **kategori başına 25**; doküman 60+ önerir. Altyapı önce, içerik sonra yayınlanır (kullanıcı kararı). Yeni sorular `data/questions/*.json` ile commit'lenip deploy sonrası konsolda `python manage.py load_questions` çalıştırılarak yüklenir (idempotent), ya da admin panelinden eklenir.
- Herkese duyurmadan önce: soru doğruluk kontrolü (kullanıcı), güvenlik gözden geçirmesi, gerçek telefonda 5 sn / 700 ms ağ toleransı testi (mobil veride).
- `deploy_on_push` her `main` push'unu testlerden bağımsız yayına alır; Dependabot PR'lerini CI geçmeden birleştirme.
- Ham IP veritabanında saklanmaz; ama platform günlüklerinde istemci IP'si görünebilir (özellikle yukarıdaki geçici günlük biçimi).

## Fiyat tahmini (DigitalOcean fiyat sayfaları, "26 Ekim 2026'da doğrulandı" notuyla)

Backend servisi ~$5/ay + Dev database ~$7/ay = **~$12/ay**; Static Site, yalnızca statik bileşen içeren ilk 3 app için ücretsiz (app başına 1 GiB giden trafik, fazlası GiB başına $0.02); migrate işi yalnızca çalıştığı sürece faturalanır. Yeni hesaplara kredi verilip verilmediği sayfada belirtilmiyor. **Kesin tutar yayından önce panelde kullanıcı tarafından kontrol edilmeli.**
