# Endüstriyel OEE & Telemetri İzleme Sistemi

Gerçek zamanlı sensör verilerini işleyen, OEE (Genel Ekipman Etkinliği) metriklerini hesaplayan ve ECharts SVG grafiklerle görselleştiren mikroservis tabanlı izleme sistemi.

## Teknoloji Yığını

| Servis | Teknoloji |
|--------|-----------|
| Veritabanı | TimescaleDB (PostgreSQL 16) |
| Backend | FastAPI + asyncpg + WebSocket |
| Simülatör | Python 3.12 + httpx (3 makine: Torna, Pres, CNC) |
| Frontend | Nginx + TailwindCSS + ECharts SVG |

## Başlatma

```bash
cd oee-monitor
docker compose up -d --build
```

## Portlar

| Servis | Port | Arayüz |
|--------|------|--------|
| Frontend Dashboard | 8080 | http://localhost:8080 |
| Backend API | 8000 | http://localhost:8000/health |
| TimescaleDB | 5432 | - |

## API Endpoint'leri

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | /health | Sağlık kontrolü |
| POST | /api/telemetry | Ham sensör verisi girişi |
| POST | /api/downtime/start | Duruş başlangıcı |
| POST | /api/downtime/end | Duruş bitişi |
| GET | /api/telemetry/history | Ham veri geçmişi |
| GET | /api/reports/timeseries | Esnek zaman serisi sorgulama |
| GET | /api/reports/stats | Makine özet istatistikleri |
| GET | /api/reports/summary | Makine karşılaştırma |
| GET | /api/reports/oee/hourly | Saatlik OEE |
| GET | /api/reports/oee/daily | Günlük OEE |
| GET | /api/reports/downtime | Duruş raporu |
| GET | /api/reports/production | Üretim raporu |
| GET | /api/reports/top-errors | Hata kodu dağılımı |
| GET | /api/reports/export | CSV/JSON ihracat |
| WS | /ws | Canlı WebSocket yayını |

## Dashboard

Dört sekmeden oluşur: **Canlı İzleme**, **Veri Keşfi**, **Raporlar**, **İhracat**. Tüm grafikler SVG vektör formatında render edilir — zoom düzeyinden bağımsız net görüntü.

## Lisans

Öğrenme amaçlı açık kaynak proje.
