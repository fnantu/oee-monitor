# Backend — FastAPI OEE Motoru

## Bu Modül Ne Yapar?

Endüstriyel makinelerden gelen ham veriyi alır, OEE hesaplar, TimescaleDB'ye yazar,
WebSocket üzerinden Frontend'e canlı yayın yapar. Sistemin tüm iş mantığı buradadır.

3 ana sorumluluğu vardır:

| Sorumluluk | Açıklama |
|-----------|----------|
| API Gateway | Simülatörden gelen veriyi doğrular, kabul eder veya reddeder |
| OEE Motoru | Anlık OEE ve bileşenlerini (Kullanılabilirlik × Performans × Kalite) hesaplar |
| Veri Dağıtıcı | Veritabanına yazar ve WebSocket üzerinden Frontend'e iletir |

---

## Neden FastAPI?

| Alternatif | Sorun |
|-----------|-------|
| Flask | Senkron, WebSocket desteği limitli, asyncpg ile uyumsuz |
| Django | Ağır, bu proje için fazla büyük, WebSocket için channels gerek |
| Node.js Express | Dil değişikliği, Python ekosistemi kaybı |
| **FastAPI** | **async/await native, Pydantic validasyon, WebSocket built-in, OpenAPI auto-docs** |

FastAPI, `asyncpg` ile doğrudan uyumludur. async/await yapısı sayesinde tek bir worker
yüzlerce eşzamanlı bağlantıyı bloklamadan yönetebilir.

---

## OEE Nasıl Hesaplanır? (Adım Adım)

### Adım 1 — Kullanılabilirlik (Availability)

```
EĞER status_code == "RUNNING" İSE  Availability = %100
DEĞİLSE                           Availability = %0
```

Mantık: Makine çalışıyorsa kullanılabilirdir. IDLE (bekleme), ERROR (arıza),
DOWN (kapalı) durumlarında kullanılabilirlik sıfırdır. Gerçek bir fabrikada
bu daha karmaşıktır (planlı bakım, setup time vs.) ama simülasyon için bu
kural yeterlidir.

### Adım 2 — Performans (Performance)

```
Performance = (produced_qty / target_rate) × 100
Üst sınır: %100 (hedefin üzerinde üretilemez varsayılır)
```

Her makinenin saniyelik hedef üretim kapasitesi vardır:

| Makine | Hedef (adet/sn) |
|--------|----------------|
| Torna (M-01) | 15 |
| Pres (M-02) | 20 |
| CNC (M-03) | 12 |

Örnek: Torna 5 adet üretirse → (5/15)×100 = %33.3 performans.

### Adım 3 — Kalite (Quality)

```
EĞER produced_qty > 0 İSE  Quality = ((produced_qty - defective_qty) / produced_qty) × 100
DEĞİLSE                   Quality = %0
```

Kalite artık dinamiktir. Simülatör her veride kaç adet kusurlu ürün ürettiğini
belirtir. Önceki versiyonda kalite sabit %98'di, V2.0 ile dinamik hale getirildi.
10 üretim, 2 kusurlu → (8/10)×100 = %80 kalite.

### Adım 4 — Anlık OEE

```
OEE = (Availability × Performance × Quality) / 10000
```

Tam formül: OEE = (A × P × Q) / 10000
Örnek: (100 × 33.3 × 80) / 10000 = %26.6

10000'e bölme sebebi: 3 bileşen de yüzde cinsinden (0-100). Gerçek OEE formülünde
bileşenler 0.0-1.0 arasıdır ama bu projede okunabilirlik için yüzde kullanıldı.

---

## Veri Akışı — POST /api/telemetry (Satır Satır)

```
Simülatör                               Backend
   │                                       │
   │ POST /api/telemetry                   │
   │ { machine_id, temperature, ... }      │
   │──────────────────────────────────────►│
   │                                       │
   │                            1. Pydantic TelemetryPayload ile doğrula
   │                               - machine_id: "M-XX-XXXX" formatı
   │                               - temperature: 0-200°C
   │                               - status_code: RUNNING|IDLE|ERROR|DOWN
   │                                       │
   │                           2. calculate_oee() fonksiyonu
   │                               - Availability → status_code kontrolü
   │                               - Performance → produced_qty / target
   │                               - Quality → (üretim - kusur) / üretim
   │                               - OEE → (A × P × Q) / 10000
   │                                       │
   │                           3. asyncpg ile sensor_data'ya INSERT
   │                               - Tüm sensör verileri + OEE bileşenleri
   │                                       │
   │                           4. manager.broadcast() ile WebSocket
   │                               - Tüm bağlı frontend'ler anlık güncellenir
   │                                       │
   │ 200 OK ←──────────────────────────────┤
```

Kod olarak:

```python
@app.post("/api/telemetry")
async def post_telemetry(payload: TelemetryPayload):
    # 1. OEE hesapla
    oee_result = calculate_oee(payload.status_code, payload.produced_qty,
                               payload.defective_qty, payload.machine_id)

    # 2. DB'ye yaz
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sensor_data (...) VALUES ($1,$2,...)",
            now, payload.machine_id, ...)

    # 3. WebSocket broadcast
    await manager.broadcast(broadcast_data)
    return broadcast_data
```

---

## WebSocket Mimarisi — ConnectionManager

```python
class ConnectionManager:
    active_connections: list[WebSocket]   # Tüm açık bağlantılar

    connect(ws)     → ws.accept() + listeye ekle
    disconnect(ws)  → listeden çıkar
    broadcast(data) → tüm bağlantılara send_json(data)
                       kopan bağlantılar otomatik temizlenir
```

Bağlantı koptuğunda hata fırlatmaz, ölü bağlantıyı listeden sessizce siler.

```
Frontend 1 ──ws──► ConnectionManager
Frontend 2 ──ws──► ConnectionManager    ← Broadcast tümüne aynı anda
Frontend 3 ──ws──► ConnectionManager
```

---

## Otomatik Veritabanı Migrasyonu

```python
async def migrate_db(conn):
    # Eksik kolonları otomatik ekler
    for col in ["vibration", "pressure", "defective_qty", ...]:
        await conn.execute(f"ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS {col}...")

    # Yeni tabloları oluşturur
    await conn.execute("CREATE TABLE IF NOT EXISTS downtime_events (...)")
```

Her backend başlatıldığında çalışır. DB şeması ile kod arasındaki
uyumsuzluğu otomatik giderir. Bu sayede elle SQL migration çalıştırmaya
gerek kalmaz.

---

## Tarih Çözümleme Sistemi

```python
def parse_date(d):
    # Sırasıyla dener, ilk başarılıda durur
    1. "2026-07-30T14:00:00"     → ISO datetime
    2. "2026-07-30T14:00:00Z"    → ISO datetime UTC
    3. "2026-07-30"              → Sadece tarih
    # Her durumda Python datetime objesi döner
```

Asyncpg, Python `datetime` objesini otomatik olarak PostgreSQL `timestamptz`'ye
dönüştürür. Ayrıca dönüştürme koduna gerek yoktur.

---

## Endpoint Haritası ve Kullanımı

### Telemetri (Simülatör → Backend)

| Method | Endpoint | Veri Girişi | Veri Çıkışı |
|--------|----------|------------|------------|
| POST | /api/telemetry | sensör verisi | OEE+hesap sonuçları |
| POST | /api/downtime/start | machine_id+reason | duruş event id |
| POST | /api/downtime/end | machine_id | süre+sebep |

### Raporlama (Frontend API)

| Method | Endpoint | Kullanıcı Seçer | Backend SQL Kullanır |
|--------|----------|-----------------|---------------------|
| GET | /api/reports/timeseries | machine_ids, metrics, granularity, from, to | `time_bucket(granularity, time)`, `AVG(FILTER ...)` |
| GET | /api/reports/stats | machine_ids, from, to | `AVG`, `MAX`, `MIN`, `COUNT(*) FILTER` |
| GET | /api/reports/summary | from, to | `GROUP BY machine_id` |
| GET | /api/reports/oee/hourly | machine_id, date | `time_bucket('1 hour', time)` |
| GET | /api/reports/oee/daily | machine_id, from, to | `time_bucket('1 day', time)` |
| GET | /api/reports/downtime | machine_id, from, to | `downtime_events` tablosu |
| GET | /api/reports/production | machine_id, from, to | `SUM`, `AVG` |
| GET | /api/reports/top-errors | machine_ids, from, to | `GROUP BY reason_code` |
| GET | /api/reports/export | format, machine_id, from, to | CSV veya JSON serialize |

---

## Dinamik SQL — /api/reports/timeseries

Bu endpoint en karmaşık olanıdır. Birden çok makine ve metriği
tek sorguda döndürür.

```python
# Örnek: machine_ids="M-01-Torna,M-02-Pres" metrics="oee,temperature"
# Üretilen SQL:
SELECT
  time_bucket('1 hour', time) AS bucket,
  ROUND(AVG(oee) FILTER (WHERE machine_id = 'M-01-Torna')::numeric, 2)
      AS "M-01-Torna_oee_avg",
  ROUND(AVG(temperature) FILTER (WHERE machine_id = 'M-01-Torna')::numeric, 1)
      AS "M-01-Torna_temperature_avg",
  ROUND(AVG(oee) FILTER (WHERE machine_id = 'M-02-Pres')::numeric, 2)
      AS "M-02-Pres_oee_avg",
  ...
FROM sensor_data
WHERE time::date >= $1 AND time::date <= $2
  AND machine_id = ANY($3::text[])
GROUP BY bucket ORDER BY bucket
```

Her makine-metrik çifti için ayrı bir sütun oluşturulur. Frontend bu
sütunları `parseTimeseriesCol()` ile çözümler:

```
"M-01-Torna_oee_avg" → machine_id: "M-01-Torna"
                        metric: "oee"
                        agg: "avg"
```

---

## Hata Yönetimi

Olası hatalar ve backend'in tepkisi:

| Hata | HTTP Kodu | Açıklama |
|------|-----------|----------|
| Geçersiz JSON | 422 (Pydantic) | Field pattern mismatch (örn. machine_id formatı hatalı) |
| Eksik field | 422 (Pydantic) | Zorunlu alan eksik |
| Veritabanı bağlantı hatası | 500 | asyncpg pool boş veya DB down |
| Açık duruş event'i yok | 404 | downtime/end çağrıldı ama başlangıç yok |
| Geçersiz tarih formatı | 500 | parse_date 3 formatı da deneyip başarısız olursa |
