# Veritabanı — TimescaleDB

## Bu Modül Ne Yapar?

Tüm sensör verilerini ve duruş kayıtlarını depolar. TimescaleDB'nin
zaman serisi optimizasyonları sayesinde yüksek hacimli veride bile
sorgu performansı düşmez.

---

## Neden TimescaleDB (Normal PostgreSQL Değil)?

PostgreSQL'de zaman serisi sorguları yıllar geçtikçe yavaşlar. Veri
büyüdükçe indeks bile yetmez.

| Özellik | PostgreSQL | TimescaleDB |
|---------|-----------|-------------|
| Zaman bazlı sorgu | Full table scan veya büyük index | **Hypertable chunk** — sadece ilgili zaman dilimini tara |
| Veri sıkıştırma | Yok (elle yapılmalı) | **Native compression** — eski veriyi otomatik sıkıştır |
| time_bucket() | Yok (elle DATE_TRUNC) | **Built-in** — saatlik/günlük gruplama native |
| Veri yaşam döngüsü | Elle silme | **Retention policy** — otomatik temizlik |

---

## Hypertable Nasıl Çalışır?

Normal PostgreSQL tablosu:

```
sensor_data (tek bir fiziksel dosya)
┌────────┬────────┬────────┬────────┐
│ 00:01  │ 00:02  │ 00:03  │ ...    │  ← Her sorgu tümünü tarar
└────────┴────────┴────────┴────────┘
```

TimescaleDB Hypertable:

```
sensor_data (mantıksal tablo)
┌──────────────────┐  ← Chunk 1 (saat 00:00-01:00)
├──────────────────┤  ← Chunk 2 (saat 01:00-02:00)
├──────────────────┤  ← Chunk 3 (saat 02:00-03:00)
└──────────────────┘
```

```
Sorgu: WHERE time BETWEEN '01:30' AND '01:45'
→ Sadece Chunk 2 taranır. Chunk 1 ve 3 atlanır.
```

```sql
-- Hypertable oluşturma
CREATE TABLE sensor_data (time TIMESTAMPTZ, ...);
SELECT create_hypertable('sensor_data', 'time');
```

Chunk boyutu `time` kolonuna göre otomatik belirlenir (genelde 1 hafta).
Her chunk ayrı bir PostgreSQL tablosudur. Sorgu planlayıcı sadece
ilgili chunk'ları tarar.

---

## Tablo Detayı: sensor_data

Bu tablo tüm sensör okumalarını ve hesaplanan OEE değerlerini içerir.

| Kolon | Tip | Örnek Değer | Açıklama |
|-------|-----|-------------|----------|
| time | TIMESTAMPTZ | `2026-07-30T14:00:00Z` | UTC zaman damgası (partition key) |
| machine_id | TEXT | `M-01-Torna` | Hangi makine |
| temperature | DOUBLE | `77.5` | Sıcaklık (°C) |
| vibration | DOUBLE | `2.15` | Titreşim (mm/s) |
| pressure | DOUBLE | `6.0` | Basınç (bar) |
| produced_qty | INTEGER | `12` | Bu saniyede üretilen adet |
| defective_qty | INTEGER | `2` | Bu saniyede kusurlu adet |
| cycle_time | DOUBLE | `1.4` | Çevrim süresi (saniye) |
| status_code | TEXT | `RUNNING` | Makine durumu |
| error_code | TEXT | `E03` veya `''` | Hata kodu (boş = hata yok) |
| availability | DOUBLE | `100.0` | Hesaplanan kullanılabilirlik (%) |
| performance | DOUBLE | `80.0` | Hesaplanan performans (%) |
| quality | DOUBLE | `83.3` | Hesaplanan kalite (%) |
| oee | DOUBLE | `66.7` | Hesaplanan OEE (%) |

### Nereden Geliyor?

```
Koloni                      Kaynak
──────────────────────────────────────────────
time                        Backend (NOW())
machine_id                  Simülatör (POST)
temperature...error_code    Simülatör (POST)
availability...oee          Backend (calculate_oee)
```

OEE bileşenleri (`availability`, `performance`, `quality`, `oee`)
backend tarafından hesaplanır ve aynı satıra yazılır. Bu sayede
raporlama sorgularında tekrar hesaplama yapılmaz.

---

## Tablo Detayı: downtime_events

Bu tablo her makine duruşunun başlangıcını, bitişini ve sebebini kaydeder.

| Kolon | Tip | Örnek Değer | Açıklama |
|-------|-----|-------------|----------|
| id | SERIAL | `42` | Otomatik artan birincil anahtar |
| machine_id | TEXT | `M-02-Pres` | Hangi makine durdu |
| start_time | TIMESTAMPTZ | `2026-07-30T14:00:00Z` | Duruş başlangıcı |
| end_time | TIMESTAMPTZ | `2026-07-30T14:00:03Z` | Duruş bitişi (NULL = hala duruyor) |
| reason_code | TEXT | `E03` | Hata kodu |
| duration_seconds | INTEGER | `3` | Süre (backend hesaplar) |

### Nasıl Doldurulur?

Simülatör duruşu algıladığında iki endpoint çağrılır:

```python
# Duruş başladı
POST /api/downtime/start {"machine_id":"M-02-Pres", "reason_code":"E03"}
→ INSERT INTO downtime_events (machine_id, start_time, reason_code)

# Duruş bitti
POST /api/downtime/end {"machine_id":"M-02-Pres"}
→ UPDATE downtime_events SET end_time=NOW(),
    duration_seconds = EXTRACT(EPOCH FROM NOW() - start_time)
```

`duration_seconds` backend tarafından `end_time - start_time` farkı
olarak otomatik hesaplanır. Simülatörün süre hesaplamasına gerek yoktur.

---

## İndeks Stratejisi

```sql
CREATE INDEX idx_machine_time
    ON sensor_data (machine_id, time DESC);
CREATE INDEX idx_downtime_machine
    ON downtime_events (machine_id, start_time DESC);
```

### Neden Bu İndeks?

Tüm raporlama sorguları şu pattern'i kullanır:

```sql
WHERE machine_id = 'XXX' AND time BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'
```

İndeks (`machine_id`, `time DESC`) sayesinde:

1. **İlk filtre**: `machine_id` ile doğrudan eşleşme → makineye özel
2. **İkinci filtre**: `time DESC` ile zaman aralığı → son veriler önce

Bu indeks olmadan PostgreSQL her sorguda tüm tabloyu taramak zorunda
kalır (`Seq Scan`). Bu indeksle `Index Only Scan` yapılır — diske
erişilmez, sadece indeks taranır.

---

## Örnek Sorgular ve Açıklamaları

### Saatlik OEE Ortalaması

```sql
SELECT
    time_bucket('1 hour', time) AS hour,
    ROUND(AVG(oee)::numeric, 2) AS avg_oee
FROM sensor_data
WHERE machine_id = 'M-01-Torna'
    AND time::date = '2026-07-30'
GROUP BY hour
ORDER BY hour;
```

`time_bucket('1 hour', time)`: TimescaleDB fonksiyonu. Her satırı
ait olduğu saat dilimine gruplar. `00:00` → saat 0, `01:00` → saat 1, ...
PostgreSQL'de `DATE_TRUNC('hour', time)` aynı işi yapar ama TIME_BUCKET
daha esnektir (örneğin 5 dakikalık bucket: '5 minutes').

### Makine Uptime Yüzdesi

```sql
SELECT
    machine_id,
    ROUND(
        (COUNT(*) FILTER (WHERE status_code = 'RUNNING')::numeric /
         COUNT(*)::numeric) * 100,
    1) AS uptime_pct
FROM sensor_data
GROUP BY machine_id;
```

`COUNT(*) FILTER (WHERE ...)`: Sadece RUNNING kayıtlarını sayar.
Toplam kayıt sayısına böler, yüzde alır.

### En Sık Duruş Sebepleri (Pareto)

```sql
SELECT
    reason_code,
    COUNT(*) AS event_count,
    COALESCE(SUM(duration_seconds), 0) AS total_seconds
FROM downtime_events
GROUP BY reason_code
ORDER BY event_count DESC
LIMIT 10;
```

Hangi hata kodunun en sık görüldüğünü ve toplam ne kadar süre
kaybettirdiğini gösterir. Frontend bu veriyi pasta grafiğinde gösterir.

### Makine Başına MTBF (Mean Time Between Failures)

```sql
SELECT
    sd.machine_id,
    ROUND(COUNT(*)::numeric / NULLIF(MAX(dt.downtime_count), 0), 1) AS mtbf
FROM sensor_data sd
LEFT JOIN (
    SELECT machine_id, COUNT(*) AS downtime_count
    FROM downtime_events GROUP BY machine_id
) dt ON ...
GROUP BY sd.machine_id;
```

MTBF = Toplam okuma sayısı / Duruş sayısı
Bir makinanın ortalama kaç okumada bir duruş yaşadığını gösterir.
Yüksek MTBF = daha güvenilir makine.

---

## Şema Versiyonlama

`init.sql` ilk kurulumda çalışır. Sonraki şema değişiklikleri
backend'in `migrate_db()` fonksiyonu ile otomatik yapılır:

```python
async def migrate_db(conn):
    # Yeni kolon ekle (mevcutsa hata vermez)
    ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS vibration DOUBLE PRECISION DEFAULT 0;
    ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS pressure DOUBLE PRECISION DEFAULT 0;
    # Yeni tablo ekle (mevcutsa hata vermez)
    CREATE TABLE IF NOT EXISTS downtime_events (...);
```

Bu yaklaşımın avantajı: Docker volume silinse bile yeni konteyner
ilk `init.sql`'i çalıştırır, ardından backend `migrate_db()` ile
V2 şemasına günceller. Elle migration scripti yazmaya gerek kalmaz.
