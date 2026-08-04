<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi" />
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python" />
  <img src="https://img.shields.io/badge/TimescaleDB-PostgreSQL_16-4169E1?style=for-the-badge&logo=postgresql" />
  <img src="https://img.shields.io/badge/Docker-Supported-2496ED?style=for-the-badge&logo=docker" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
</p>

# Endüstriyel OEE & Telemetri İzleme Sistemi

Gerçek zamanlı sensör verilerini işleyen, **OEE (Overall Equipment Effectiveness / Toplam Ekipman Etkinliği)** metriklerini hesaplayan ve ECharts SVG grafiklerle görselleştiren mikroservis tabanlı izleme platformu.

---

## 🏗️ Mimari & Teknoloji Yığını

| Bileşen | Teknoloji | Açıklama |
| :--- | :--- | :--- |
| **Veritabanı** | TimescaleDB (PostgreSQL 16) | Zaman serisi verileri ve OEE agregasyonları |
| **Backend API** | FastAPI + asyncpg + WebSocket | Yüksek performanslı asenkron veri toplama & canlı yayın |
| **Simülatör** | Python 3.12 + httpx | 3 farklı makine (Torna, Pres, CNC) için sensör veri simülatörü |
| **Frontend UI** | Nginx + TailwindCSS + ECharts SVG | Canlı dashboard ve vektörel grafikler |
| **Konteyner** | Docker & Docker Compose | Tek komutla orkestrasyon |

---

## 🚀 Hızlı Başlangıç

```bash
# Depoyu klonlayın
git clone https://github.com/fnantu/oee-monitor.git
cd oee-monitor

# Tüm servisleri Docker Compose ile başlatın
docker compose up -d --build
```

---

## 🔌 Portlar & Erişim

| Servis | Port | Bağlantı |
| :--- | :--- | :--- |
| **Frontend Dashboard** | `8080` | [http://localhost:8080](http://localhost:8080) |
| **Backend API** | `8000` | [http://localhost:8000/health](http://localhost:8000/health) |
| **TimescaleDB** | `5432` | `localhost:5432` |

---

## 📡 API Endpoint'leri

| Method | Endpoint | Açıklama |
| :--- | :--- | :--- |
| `GET` | `/health` | Sağlık kontrolü |
| `POST` | `/api/telemetry` | Ham sensör verisi girişi |
| `POST` | `/api/downtime/start` | Duruş başlangıcı |
| `POST` | `/api/downtime/end` | Duruş bitişi |
| `GET` | `/api/telemetry/history` | Ham veri geçmişi |
| `GET` | `/api/reports/timeseries` | Esnek zaman serisi sorgulama |
| `GET` | `/api/reports/stats` | Makine özet istatistikleri |
| `GET` | `/api/reports/summary` | Makine karşılaştırma |
| `GET` | `/api/reports/oee/hourly` | Saatlik OEE |
| `GET` | `/api/reports/oee/daily` | Günlük OEE |
| `GET` | `/api/reports/downtime` | Duruş raporu |
| `GET` | `/api/reports/production` | Üretim raporu |
| `GET` | `/api/reports/top-errors` | Hata kodu dağılımı |
| `GET` | `/api/reports/export` | CSV/JSON ihracat |
| `WS` | `/ws` | Canlı WebSocket yayını |

---

## 📊 Dashboard Özellikleri

Dashboard dört temel sekmeden oluşur:
- **Canlı İzleme:** Makine durumları ve WebSocket ile anlık veri akışı
- **Veri Keşfi:** Filtrelenebilir sensör ve zaman serisi analizleri
- **Raporlar:** OEE (Kullanılabilirlik, Performans, Kalite) ve duruş analizleri
- **İhracat:** CSV ve JSON formatlarında veri dışa aktarımı

Tüm grafikler SVG vektör formatında render edilir — zoom düzeyinden bağımsız net görünüm sunar.

---

## ⚖️ Lisans

Bu proje **MIT Lisansı** altında lisanslanmıştır. Detaylar için [LICENSE](./LICENSE) dosyasına bakın.
