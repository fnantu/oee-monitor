# ENDÜSTRİYEL OEE & TELEMETRİ İZLEME SİSTEMİ - MASTER DOKÜMAN

**KURAL BİLDİRİMİ (AI ASİSTANLARI İÇİN):** 
Bu doküman projenin tek gerçeklik kaynağıdır (Single Source of Truth). Bu dosyadaki hiçbir mimari karar, kural veya geçmiş kayıt silinemez. Proje geliştikçe sadece yeni modüller, güncellemeler ve loglar dosyanın sonuna EKLENEBİLİR (Append-Only).

---

## 1. PROJE VİZYONU VE KAPSAMI
Bu proje, endüstriyel üretim hatlarından (Torna, Pres, CNC vb.) gelen yüksek frekanslı sensör verilerini gerçek zamanlı (real-time) işleyerek, OEE (Genel Ekipman Etkinliği) metriklerini hesaplayan ve görselleştiren izole bir mikroservis mimarisidir. 
Hedef: Sensörlerden arayüze kadar uçtan uca asenkron, ölçeklenebilir ve API-Driven (API odaklı) bir sistem inşa etmektir.

---

## 2. KULLANILAN TEKNOLOJİ YIĞINI (TECH STACK)
*   **Konteyner/Orkestrasyon:** Docker & Docker Compose
*   **Veritabanı Katmanı (TSDB):** TimescaleDB (PostgreSQL 16 tabanlı)
*   **API / Backend Katmanı:** Python 3.10+, FastAPI, Uvicorn, asyncpg
*   **IoT Uç Cihaz Simülasyonu:** Python 3.10+, Requests (Otonom veri üretici)
*   **Ön Yüz (Frontend):** Nginx Alpine, Vanilla JavaScript, TailwindCSS, ECharts (SVG Renderer)

---

## 3. SİSTEM MİMARİSİ VE AĞ (NETWORK) TOPOLOJİSİ
Proje, dış dünyaya kapalı bir Docker ağı içinde birbirine API'ler üzerinden bağlanan 4 temel servisten oluşur:

### 3.1. Servis: `timescaledb` (Port: 5432)
*   **Görev:** Zaman serisi verilerini depolamak.
*   **Yapı:** İlişkisel veri şişmesini önlemek için veriler `sensor_data` tablosunda `TIMESTAMPTZ` baz alınarak fiziksel bloklara (Hypertable) bölünür.
*   **Erişim:** Sadece `backend` servisi tarafından asenkron (`asyncpg`) olarak erişilebilir.

### 3.2. Servis: `backend` (Port: 8000)
*   **Görev:** Sistemin güvenlik duvarı, doğrulayıcısı ve matematiksel (OEE) motorudur.
*   **Yapı:** Gelen HTTP isteklerini karşılar, Pydantic şeması ile doğrular, veritabanına yazar ve eşzamanlı olarak WebSocket üzerinden Frontend'e fırlatır.

### 3.3. Servis: `simulator` (Ağ içi çalışır, dış portu yoktur)
*   **Görev:** Fiziksel makineleri (PLC'leri) taklit eder.
*   **Yapı:** Her saniye rastgele ancak mantıklı üretim verisi ve hata kodları üretip `backend` API'sine HTTP POST atar. Veritabanı ile direkt bağlantısı YASAKTIR.

### 3.4. Servis: `frontend` (Port: 8080)
*   **Görev:** Üretim yöneticisi için canlı izleme ekranı.
*   **Yapı:** Nginx üzerinden sunulan statik HTML/JS dosyaları. Sayfa açılır açılmaz Backend (Port 8000) üzerindeki WebSocket'e bağlanıp, gelen paketlerle (payload) ECharts SVG vektör grafiklerini günceller.

---

## 4. VERİ İLETİŞİM SÖZLEŞMELERİ (API CONTRACTS)

Farklı dillerin veya AI modellerinin uyumsuzluk yaşamaması için veri yapıları (JSON) kesin olarak aşağıdaki gibidir:

### 4.1. Uç Cihazdan Backend'e Giden Ham Veri (POST /api/telemetry)
Simülatör, Backend'e şu JSON formatında veri fırlatmak zorundadır:
```json
{
  "machine_id": "M-01-Torna",
  "temperature": 72.5,
  "vibration": 2.15,
  "pressure": 6.0,
  "produced_qty": 12,
  "defective_qty": 2,
  "cycle_time": 1.4,
  "status_code": "RUNNING",
  "error_code": ""
}
```
### 4.2. OEE Hesaplama Kuralları (Backend İçi)
Backend veriyi aldığında şu matematiği uygular:
- Kullanılabilirlik: Durum "RUNNING" ise %100, değilse %0.
- Performans: (Üretilen Adet / Saniyelik Hedef Üretim) * 100.
- Kalite: ((Üretim - Kusurlu) / Üretim) * 100 (Dinamik).
- Anlık OEE: $OEE = (Kullanılabilirlik \times Performans \times Kalite) / 10000$

### 4.3. Backend'den Frontend'e Canlı Veri Yayını (WebSocket Payload)
Backend, OEE'yi hesapladıktan sonra WebSocket üzerinden şu paketi fırlatır:
```json
{
  "machine_id": "M-01-Torna",
  "temperature": 72.5,
  "vibration": 2.15,
  "pressure": 6.0,
  "cycle_time": 1.4,
  "produced_qty": 12,
  "defective_qty": 2,
  "oee": 68.6,
  "availability": 100.0,
  "performance": 80.0,
  "quality": 83.3,
  "status": "RUNNING",
  "error_code": "",
  "time": "2026-07-30T17:11:43Z"
}
```

---

## 5. KLASÖR HİYERARŞİSİ
```
/
├── docker-compose.yml
├── PROJECT_ARCHITECTURE.md
├── README.md
├── .gitignore
├── database/
│   └── init.sql
├── simulator/
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
└── frontend/
    ├── index.html
    ├── app.js
    └── Dockerfile
```

---

## 6. GELİŞTİRME GÜNLÜĞÜ VE REVİZYONLAR (APPEND-ONLY LEDGER)

(Yeni bir özellik eklendiğinde, veritabanı şeması değiştiğinde veya yeni bir API Endpoint açıldığında, tarihi ve yapılan değişiklikleri kalıcı olarak buraya ekleyin.)

[2026-07-30] [V1.0]: Ana mimari dokümanı oluşturuldu. API ve WebSocket yapıları tanımlandı. TimescaleDB hypertable tasarımı kilitlendi.
[2026-07-30] [V1.1]: Tüm servisler Docker Compose ile ayağa kaldırıldı. Backend (FastAPI + asyncpg), Simülatör (3 makine: Torna/Pres/CNC), Frontend (TailwindCSS + Chart.js) çalışır durumda. TimescaleDB imajı `latest-pg16` olarak güncellendi. Simülatör saniyede 1 veri gönderiyor, Backend OEE hesaplayıp WebSocket'ten broadcast yapıyor, Frontend canlı grafik gösteriyor.
[2026-07-30] [V2.0]: Kapsamlı veri modeli iyileştirmesi ve raporlama altyapısı eklendi. Veritabanı şeması genişletildi (vibration, pressure, defective_qty, cycle_time, error_code, OEE bileşenleri). Yeni `downtime_events` tablosu eklendi. Simülatör stateful hale getirildi (3 makine/saniye, sıcaklık drift'i, dinamik kalite, duruş event'leri). Backend'e 7 yeni raporlama endpoint'i eklendi (history, oee/hourly, oee/daily, downtime, production, summary, export). Frontend 4 sekmeli dashboard'a yükseltildi (Canlı İzleme, Geçmiş Raporlar, Duruş Analizi, İhracat). Tüm raporlar Chart.js grafikleri ve tablolarla görselleştiriliyor. Hata kodları: E01-E06 (teknik arızalar) ve M01 (planlı duruş).
[2026-07-30] [V2.1]: Tamamen yeniden yapılandırılmış raporlama altyapısı. Backend'e 3 yeni esnek sorgu endpoint'i eklendi: `/api/reports/timeseries` (dinamik zaman-bucket sorgulama, çoklu makine + metrik + granülerite), `/api/reports/stats` (makine başına özet istatistikler: avg/max/min OEE, uptime %, MTBF, üretim, duruş analizi), `/api/reports/top-errors` (hata kodu dağılımı). Frontend üst tab bar ile 4 sayfaya yeniden yapılandırıldı: CANLI İZLEME (gerçek zamanlı WS + machine cards + çift grafik), VERİ KEŞFİ (zaman presets, çoklu makine/metrik checkbox, çözünürlük seçimi, dinamik grafik + sıralanabilir tablo), RAPORLAR (özet kartlar, OEE trend çizgisi, hata dağılımı pie chart, üretim bar chart, top error listesi), İHRACAT (format + tarih + makine seçimi). Sistem artık kullanıcıya "normal DB sorgusunu arayüzden yapma" imkanı sunuyor.
[2026-07-30] [V2.2]: Tam SVG vektör grafik dönüşümü. Chart.js kaldırıldı, tüm grafikler ECharts (SVG renderer) ile değiştirildi — tarayıcı zoom'unda pikselleşme yok. Grafik boyutları büyütüldü (380px → 400px, Veri Keşfi chart 55vh). Katlanabilir filtre paneli, tam ekran chart modu ve katlanabilir veri tablosu eklendi. Backend dead code temizliği (MachineData, asyncio, date, timedelta). CORS middleware eklendi. API dokümantasyonu ve README güncellendi. Proje yapılandırması standartlaştırıldı (`.gitignore`, GitHub entegrasyonu).
