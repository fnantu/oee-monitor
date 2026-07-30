# Frontend — ECharts SVG Dashboard

## Bu Modül Ne Yapar?

Nginx üzerinden sunulan tek sayfa uygulaması (SPA). 4 sekme ile canlı veri
izleme, geçmiş sorgulama ve ihracat sağlar. Tüm grafikler SVG vektör
formatında render edilir — tarayıcı zoom'unda pikselleşme olmaz.

---

## Neden ECharts (Chart.js Değil)?

Chart.js v4 ile başlandı, V2.2'de ECharts v5 SVG'e geçildi.

| Özellik | Chart.js (canvas) | ECharts SVG |
|---------|------------------|-------------|
| Render motoru | Canvas (raster/piksel) | **SVG (vektör)** |
| 200% zoom | Bulanık/pikselleşir | **Net, kayıp yok** |
| 4K ekran | Düşük çözünürlük | **Doğal çözünürlük** |
| tooltip | Temel, sade metin | **Zengin etkileşimli** |
| Eklenti | Yok | **dataZoom, markLine, visualMap** |

ECharts seçilme sebebi: Endüstriyel dashboard'larda grafiklerin her ölçekte
net görünmesi kritiktir. Bir üretim müdürü yakınlaştırıp bir veri noktasını
incelerken grafiğin bulanıklaşması kabul edilemez.

---

## Sayfa 1: CANLI İZLEME

### Veri Akışı

```
Simülatör ──POST──► Backend ──WebSocket──► Frontend
  (3/sn)             (OEE hesapla)          (DOM + ECharts)
```

### Nasıl Çalışır?

```javascript
// 1. WebSocket bağlantısı
const ws = new WebSocket("ws://localhost:8000/ws");

// 2. Her mesajda updateLive(data) çağrılır
ws.onmessage = e => updateLive(JSON.parse(e.data));
```

### updateLive() — Adım Adım

```javascript
function updateLive(data) {
    // 1. DOM kartlarını güncelle (HTML elemanlarının textContent'ini değiştir)
    document.getElementById("oee-" + mid).textContent = data.oee + "%";
    document.getElementById("temp-" + mid).textContent = data.temperature + "°C";
    document.getElementById("prod-" + mid).textContent = data.produced_qty;
    document.getElementById("vib-" + mid).textContent = data.vibration;
    document.getElementById("pres-" + mid).textContent = data.pressure;

    // 2. Status badge rengini güncelle (CSS class değiştir)
    se.className = cls[data.status] || cls.DOWN;

    // 3. Kayan pencere verisine ekle (son 60 nokta)
    liveOeeData[mid].push(data.oee);
    if (liveOeeData[mid].length > 60) liveOeeData[mid].shift();

    // 4. ECharts grafiğini güncelle
    liveOeeChart.setOption({
        series: [{ data: [...liveOeeData[mid]] }]
    });
}
```

### ECharts SVG Chart Oluşturma

```javascript
// Helper fonksiyon — tüm grafikler buradan oluşur
function initECharts(id) {
    const el = document.getElementById(id);
    return echarts.init(el, null, { renderer: "svg" });
}

// Kullanımı
const chart = initECharts("oeeChart");
chart.setOption({
    grid: { left: 35, right: 10, top: 5, bottom: 5 },
    xAxis: { type: "category", show: false },
    yAxis: { type: "value", min: 0, max: 100 },
    series: [{ type: "line", data: [], smooth: true }],
    tooltip: { trigger: "axis" },
});
```

`renderer: "svg"` parametresi ECharts'a SVG çıktı üretmesini söyler.
Bu sayede grafik vektör formatında render edilir ve zoom'da pikselleşmez.

---

## Sayfa 2: VERİ KEŞFİ

### Esnek Sorgu Mimarisi

Bu sayfa kullanıcıya "SQL sorgusu yazmadan veri keşfetme" imkanı verir.

```
Kullanıcı Seçer              → URL Parametreleri        → Backend SQL
────────────────────────────────────────────────────────────────────
Makine: ☑Torna ☑Pres         machine_ids=M-01-Torna,..  WHERE machine_id IN (...)
Metrik: ☑OEE ☑Sıcaklık       metrics=oee,temperature   AVG(oee), AVG(temperature)
Çözünürlük: Saat              granularity=1h            time_bucket('1h', time)
Tarih: 2026-07-30             from=..&to=..             WHERE time::date BETWEEN ...
```

### Backend'den Dönen Yanıtın Parse Edilmesi

Backend dinamik sütun adlarıyla yanıt döner:

```json
[
  {
    "bucket": "2026-07-30T14:00:00Z",
    "M-01-Torna_oee_avg": 42.3,
    "M-01-Torna_temperature_avg": 77.5,
    "M-02-Pres_oee_avg": 38.7,
    "M-02-Pres_temperature_avg": 67.2
  }
]
```

Frontend bu sütunları `parseTimeseriesCol()` ile çözümler:

```javascript
function parseTimeseriesCol(key) {
    // "M-01-Torna_oee_avg"
    //   → machine_id: "M-01-Torna"
    //   → metric: "oee"
    //   → agg: "avg"
    for (const mid of Object.keys(MACH_STYLES)) {
        if (key.startsWith(mid + "_")) {
            const suffix = key.slice(mid.length + 1);  // "oee_avg"
            const us = suffix.lastIndexOf("_");
            return {
                machine_id: mid,
                metric: suffix.slice(0, us),    // "oee"
                agg: suffix.slice(us + 1)       // "avg"
            };
        }
    }
}
```

Her sütun bir ECharts serisi olur: "Torna - OEE", "Pres - Sıcaklık" vb.

### Katlanabilir UI Elementleri

```
┌─ [▶ FİLTRELER] [⛶] ──────────────────────────────┐
│  (Filtre paneli varsayılan kapalı)                 │
├────────────────────────────────────────────────────┤
│                                                    │
│            BÜYÜK SVG GRAFİK (flex 1)               │
│            min-height: 55vh                        │
│                                                    │
├────────────────────────────────────────────────────┤
│ [▶ VERİ TABLOSU] (tıkla aç, tıkla kapa)            │
└────────────────────────────────────────────────────┘
```

| Element | Davranış |
|---------|----------|
| ▶ FİLTRELER | Tıkla → panel açılır, ikon ▶ → ▼ |
| ⛶ | Tıkla → grafik tam ekran, ESC → çık |
| ▶ VERİ TABLOSU | Tıkla → tablo aç/kapa |

---

## Sayfa 3: RAPORLAR

Tek bir "YENİLE" butonuyla 3 paralel API çağrısı:

```javascript
const [stats, ts, errors] = await Promise.all([
    fetch(`${API}/api/reports/stats?...`),       // Özet kartlar
    fetch(`${API}/api/reports/timeseries?...`),   // OEE trend
    fetch(`${API}/api/reports/top-errors?...`),   // Hata dağılımı
]);
```

### Stats Yanıtı → Özet Kartlar

```javascript
function renderRptCards(stats) {
    // Her makine için bir kart
    // OEE, max/min, uptime %, üretim, kusur, duruş sayısı, MTBF
    document.getElementById("rptCards").innerHTML = stats.map(s => `
        <div>
            <div>OEE: ${s.avg_oee}%</div>
            <div>Max: ${s.max_oee}%</div>
            <div>Uptime: ${s.uptime_pct}%</div>
            <div>Üretim: ${s.total_production}</div>
            <div>MTBF: ${s.mtbf_seconds}s</div>
        </div>
    `).join("");
}
```

### timeseries Yanıtı → OEE Trend Çizgisi

Her makine için ayrı bir ECharts serisi oluşturulur.
Renkler `MACH_STYLES`'tan alınır:

| Makine | Renk |
|--------|------|
| Torna | `#34d399` (yeşil) |
| Pres | `#60a5fa` (mavi) |
| CNC | `#f472b6` (pembe) |

### top-errors Yanıtı → Hata Dağılımı Pasta Grafiği

ECharts doughnut (halka) tipinde grafik.

```javascript
rptPieChart.setOption({
    series: [{
        type: "pie", radius: ["40%", "70%"],   // doughnut
        data: [
            { name: "E01", value: 30, itemStyle: { color: "#ef4444" } },
            { name: "M01", value: 25, itemStyle: { color: "#f59e0b" } },
        ]
    }]
});
```

`radius: ["40%", "70%"]` — iç yarıçap %40, dış yarıçap %70.
İç boşluk sayesinde halka (doughnut) görünümü elde edilir.

---

## Sayfa 4: İHRACAT

```javascript
function downloadExport() {
    const fmt = CSV / JSON seçimi;
    const url = `${API}/api/reports/export?format=${fmt}&from=${date}&to=${date}`;
    window.open(url, "_blank");
}
```

Backend `Content-Disposition: attachment` header'ı döndüğü için
tarayıcı otomatik indirme başlatır.

---

## API'nin Frontend'deki Konumu

```javascript
const API = "http://" + location.hostname + ":8000";
```

Frontend Nginx'ten (port 8080) sunulur, backend 8000'de olduğu için
tüm `fetch()` çağrıları `API` sabitini kullanır. CORS middleware sayesinde
cross-origin isteklere izin verilir.
