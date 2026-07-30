# Simülatör — Endüstriyel Makine Taklidi

## Bu Modül Ne Yapar?

Gerçek fabrika ortamındaki 3 makineyi (Torna, Pres, CNC) simüle eder.
Her saniye 3 HTTP POST isteği gönderir, duruş event'lerini yönetir,
sıcaklık/titreşim/basınç gibi fiziksel büyüklükleri gerçekçi pattern'lerle üretir.

Endüstriyel IoT cihazının (PLC veya sensör gateway) davranışını taklit eder.
Gerçek bir fabrikada bu veriler fabrika katından gelir — bu projede simülatör
bu rolü üstlenir.

---

## Neden Ayrı Bir Servis?

| Özellik | Açıklama |
|---------|----------|
| **İzolasyon** | Veritabanına doğrudan erişimi YOKTUR — sadece backend API'si üzerinden iletişim |
| **Gerçekçilik** | Gerçek bir PLC/IoT cihazı gibi davranır, aynı protokolü kullanır |
| **Test** | Backend'i gerçek cihaz olmadan test etmeyi sağlar |
| **Ölçekleme** | İsterseniz 3 yerine 300 makine çalıştırabilirsiniz |

---

## Makine Durum Makinesi (State Machine)

Her saniye her makine için yeni bir durum seçilir.

```
                    ┌──────────┐
         ┌─────────►│ RUNNING  │◄─────────┐
         │          │  (%65)   │          │
         │          └────┬─────┘          │
         │               │                │
         │               ▼                │
         │          ┌──────────┐          │
    ┌────┴──────────┤  IDLE    ├──────────┘
    │    ┌──────────┤  (%10)   │
    │    │          └──────────┘
    ▼    ▼
┌──────────┐    ┌──────────┐
│  ERROR   │    │   DOWN   │
│   (%5)   │    │   (%3)   │
└──────────┘    └──────────┘
```

Durum ağırlıkları gerçekçi bir üretim ortamını yansıtır:
- **%65 RUNNING**: Makine çalışıyor, üretim yapıyor
- **%10 IDLE**: Makine açık ama beklemede (malzeme yok, operatör molası)
- **%5 ERROR**: Teknik arıza (takım aşınması, aşırı ısınma)
- **%3 DOWN**: Makine tamamen kapalı (bakım, planlı duruş)

Her saniye seçim bağımsızdır. Önceki durum sonraki durumu etkilemez
(rassal seçim). **Duruş event yönetimi**, önceki ve yeni durum
arasındaki farkı algılayarak çalışır (aşağıya bakın).

---

## Sıcaklık Drift'i (Random Walk) — Neden?

Gerçek makineler aniden 65°C'den 90°C'ye sıçramaz. Kademeli ısınır/soğur.

```
Sıcaklık (°C)
 90 ┤                                    ╱╲
 85 ┤                               ╱╲
 80 ┤                         ╱╲
 75 ┤                   ╱╲
 70 ┤              ╱╲
 65 ┤         ╱╲    (Random Walk - doğal görünüm)
    └─────────────────────────────────────────► Zaman
```

Kod:

```python
def random_walk(current, target, step=1.5):
    # Hedef: makinenin sıcaklık aralığının ortası
    # Torna: 65-90, hedef = 77.5
    # Pres:  55-80, hedef = 67.5
    # CNC:   70-95, hedef = 82.5

    if current < target:
        return min(current + random(0, step), target)
    return max(current - random(0, step), target)
```

Her saniye en fazla ±1.5°C değişir, keskin sıçrama olmaz.

---

## Duruş Event Akışı (Adım Adım)

Bu akış her 3 makine için saniyede bir tekrarlanır.

```
                               Simülatör                    Backend
                                  │                            │
Saniye 1: Prev=RUNNING            │                            │
          New=RUNNING             │ POST /api/telemetry ──────►│ 200 OK
                                  │                            │
Saniye 2: Prev=RUNNING            │ POST /api/telemetry ──────►│ 200 OK
          New=DOWN                │                            │
          │ start_downtime? EVET  │ POST /api/downtime/start ──►│ INSERT
          │ reason=E03            │                            │
                                  │                            │
Saniye 3: Prev=DOWN               │ POST /api/telemetry ──────►│ 200 OK
          New=DOWN                │                            │
                                  │                            │
Saniye 4: Prev=DOWN               │ POST /api/telemetry ──────►│ 200 OK
          New=RUNNING             │                            │
          │ end_downtime? EVET    │ POST /api/downtime/end ────►│ UPDATE
                                  │    duration=2s             │
```

Kod:

```python
class MachineSim:
    def tick(self):
        self.prev_status = self.status         # önceki durumu kaydet
        self.status = random.choices(STATUS_SET, weights=STATUS_WEIGHTS)[0]
        self.temp = random_walk(self.temp, target, 1.5)   # sıcaklık drift
        self.vib = random_walk(self.vib, target_v, 0.3)
        self.pres = random_walk(self.pres, target_p, 0.5)

    def should_start_downtime(self):
        return self.prev_status in ("RUNNING", "IDLE") \
           and self.status in ("ERROR", "DOWN")

    def should_end_downtime(self):
        return self.prev_status in ("ERROR", "DOWN") \
           and self.status in ("RUNNING", "IDLE")
```

---

## Hata Kodu Sistemi

Her hata kodu belirli bir arıza tipini temsil eder:

| Kod | Anlamı | Senaryo |
|-----|--------|---------|
| E01 | Takım Aşınması | Kesici uç/kalıp ömrü doldu |
| E02 | Aşırı Isınma | Soğutma sistemi arızası, sıcaklık limit aşımı |
| E03 | Titreşim Anomalisi | Rulman arızası, dengesiz mil |
| E04 | Basınç Düşüklüğü | Hidrolik/pnömatik sistem kaçağı |
| E05 | Hammadde Yok | Malzeme besleme hatası |
| E06 | Bakım Zamanı | Periyodik bakım aralığı doldu |
| M01 | Planlı Duruş | Üretim planı gereği kasıtlı duruş |

Makine ERROR veya DOWN durumundayken rastgele bir hata kodu seçilir
ve `POST /api/downtime/start` ile backend'e bildirilir.

---

## Makine Konfigürasyon Detayları

Her makinenin kendine özgü parametreleri vardır:

```
                         Torna (M-01)    Pres (M-02)     CNC (M-03)
                         ───────────    ───────────      ─────────
Hedef üretim/sn:              15             20              12
Sıcaklık aralığı:         65 — 90°C      55 — 80°C       70 — 95°C
Titreşim aralığı:         0.5 — 3.5      1.0 — 5.0       0.3 — 2.0
Basınç aralığı:            4 — 8 bar      6 — 12 bar       3 — 6 bar
Çevrim süresi:           0.8 — 2.5sn     0.5 — 1.5sn     1.2 — 3.0sn
```

Torna yüksek sıcaklık, yüksek çevrim süresi → ağır talaşlı imalat.
Pres düşük sıcaklık, yüksek basınç → metal şekillendirme.
CNC yüksek sıcaklık, düşük titreşim → hassas işleme.

---

## Veri Üretme Mantığı

```python
def get_telemetry(self):
    is_running = self.status == "RUNNING"

    # RUNNING değilse üretim = 0
    produced = random.randint(0, self.cfg["target"]) if is_running else 0

    # Üretim varsa, kusur oranı rastgele (max %25)
    defective = random.randint(0, max(1, produced // 4)) if produced > 0 else 0

    return {
        "machine_id": self.cfg["machine_id"],
        "temperature": round(self.temp, 1),
        "vibration": round(self.vib, 2),
        "pressure": round(self.pres, 2),
        "produced_qty": produced,
        "defective_qty": defective,
        "cycle_time": round(random.uniform(...), 2),
        "status_code": self.status,
        "error_code": random.choice(ERROR_CODES) if self.status in ("ERROR","DOWN") else "",
    }
```

---

## Asenkron Mimari

```python
async def run():
    machines = [MachineSim(cfg) for cfg in MACHINES]

    # httpx.AsyncClient: Tüm HTTP istekleri non-blocking
    async with httpx.AsyncClient(timeout=5) as client:
        while True:
            for sim in machines:           # 3 makine
                sim.tick()                 # Durum + fiziksel değerler
                payload = sim.get_telemetry()

                # Backend'e POST (asenkron, bloklamaz)
                await client.post(f"{BACKEND_URL}/api/telemetry", json=payload)

                # Duruş event kontrolü
                if sim.should_start_downtime():
                    await client.post(f"{BACKEND_URL}/api/downtime/start", ...)
                if sim.should_end_downtime():
                    await client.post(f"{BACKEND_URL}/api/downtime/end", ...)

            await asyncio.sleep(1)  # 1 saniye bekle
```

`httpx.AsyncClient` Python'un standart `requests` kütüphanesinin asenkron
versiyonudur. HTTP POST isteği gönderirken işlemci bloke olmaz, aynı anda
başka işlemler yapılabilir.

---

## Çıktı Örneği (Gerçek Log)

```
[14:44:40] M-02-Pres | OEE: 50.0% RUNNING | T:67.5°C V:3.0 P:9.0 K:12/2
[14:44:40] M-03-CNC | OEE:  0.0%   ERROR | T:82.5°C V:1.15 P:4.5 K:0/0
[DOWN] M-03-CNC başladı: Basınç Düşüklüğü
[14:44:41] M-01-Torna | OEE: 73.3% RUNNING | T:77.5°C V:2.0 P:6.0 K:14/3
[UP]   M-03-CNC bitti (1s) ✅
```

Satır formatı: `[zaman] makine | OEE: değer durum | T:sıcaklık V:titreşim P:basınç K:üretim/kusur`
