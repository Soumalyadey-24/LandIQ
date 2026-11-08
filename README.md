<div align="center">

# 🌍 LandIQ

### From Legacy Documents to Trusted Land Intelligence

AI-powered digitization and validation of land records, where **every field carries a confidence score and a link back to the exact pixels it was read from.**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![PostGIS](https://img.shields.io/badge/PostgreSQL-PostGIS-336791?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![Status](https://img.shields.io/badge/status-hackathon%20prototype-orange)

**Smart India Hackathon · Problem Statement SIH26018**
*Intelligent Land Record Digitization and Validation System*

[Quick Start](#-quick-start) · [Features](#-features) · [Demo Walkthrough](#-the-5-minute-demo) · [Architecture](#-architecture) · [API Docs](#-api)

</div>

---

## 📖 Overview

Land records in India are often decades-old scans: faded, skewed, handwritten, and in multiple scripts. Mistakes in them cause ownership disputes and fraud.

**LandIQ** turns a scanned Record of Rights into a structured, verifiable land record. It:

- **Restores** the scan and reads it with OCR / handwriting recognition
- **Scores confidence** for every extracted field, with evidence tied to the source pixels
- **Cross-checks** the recorded area against surveyed parcel geometry (PostGIS)
- **Detects** ownership conflicts and impossible timelines
- **Risk-scores** each record (0–100) with a fully itemised explanation
- **Routes** anything uncertain to a human officer, and audits every correction

> **Honest by design:** handwriting recognition is verified for **Latin/English only** (TrOCR, CER 0.0505 on held-out IAM samples). Unsupported scripts return `UNSUPPORTED` instead of a guess.

## 🎯 The Hero Case

The bundled degraded document records **2.40 acres**, but ink bleed makes the scan read like **8.40**. LandIQ doesn't quietly pick one:

| Signal | Result |
|---|---|
| Area read as | `8.40 acres` at **34% confidence (RED)** |
| Alternate restoration pass | `2.40 acres` |
| Surveyed geometry (PostGIS) | `2.37 acres` |
| GIS verdict | **MISMATCH, 254% difference** |
| Ownership | Competing claim on the same survey number |
| History | 2019 sale recorded *after* a 2021 mutation (impossible) |
| **Risk** | **94 / 100, HIGH** |

The officer accepts the alternate reading, the GIS check flips to **MATCH (1.27%)**, risk drops to 73, and the change is written to the audit trail with the reason and officer ID.

<!-- Add a screenshot or GIF here:
![LandIQ hero record](docs/screenshots/hero-record.png)
-->

## ✨ Features

| Area | Highlights |
|---|---|
| 🖼️ **Preprocessing** | 7 real OpenCV stages (denoise, CLAHE, sharpen, deskew, perspective, threshold), every stage image stored and viewable |
| 🔤 **OCR / HTR** | Tesseract (eng/ben/hin) for print, TrOCR for Latin handwriting, capability-detected and degrades gracefully |
| 🈯 **Script detection** | Tesseract OSD plus Unicode histogram, with agreement reporting and mixed-script detection |
| 🧩 **Extraction** | 17-field common schema; maps RoR / RTC / Jamabandi / Patta; normalises units, names, dates, IDs |
| 📊 **Confidence** | 3-signal fusion: engine confidence + pixel quality + cross-restoration agreement |
| 🔗 **Evidence binding** | Page, bounding box, source text, engine, and model version per field; click a value to highlight it on the scan |
| ✅ **Validation** | 7 checks: completeness, confidence, identifiers, GIS area, duplicates, ownership conflict, ownership timeline |
| 🗺️ **GIS** | Geodesic area on the WGS84 ellipsoid, spatial overlap detection, document-vs-survey reconciliation |
| ⚠️ **Risk scoring** | 0–100, 7 weighted inputs, every point traceable |
| 👮 **Human-in-the-loop** | Split-screen review: accept, accept alternative, edit, or escalate |
| 📜 **Audit trail** | Append-only log with actor, timestamp, old → new value, and reason |
| 🔁 **Continuous learning** | Corrections captured as training examples; retraining is human-gated, never automatic |
| 🔍 **Search & export** | Phonetic/transliterated owner search; CSV, JSON, and one-page PDF export |
| 🔐 **Security** | JWT + bcrypt, role-based access, content-based upload validation, rate limiting |

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────┐
│  FRONTEND  React 19 · TypeScript · Vite · Tailwind          │
│  Dashboard · Upload · Record + Evidence · Review · Audit    │
└──────────────────────────┬─────────────────────────────────┘
                           │ JSON over HTTPS (nginx proxies /api)
┌──────────────────────────▼─────────────────────────────────┐
│  BACKEND  FastAPI · Pydantic v2 · SQLAlchemy 2.0            │
│  routes → services (pipeline, validation, risk, gis) → ORM  │
└───────┬──────────────────┬─────────────────────┬───────────┘
        │                  │                     │
┌───────▼──────┐  ┌────────▼─────────┐  ┌────────▼──────────┐
│ ai/          │  │ PostgreSQL 16    │  │ Celery + Redis    │
│ framework-   │  │ + PostGIS 3.4    │  │ (thread-runner    │
│ free package │  │ (SQLite fallback)│  │  fallback)        │
└──────────────┘  └──────────────────┘  └───────────────────┘
```

**Processing pipeline:**

```
UPLOAD → PREPROCESSING → SCRIPT DETECTION → OCR/HTR → LAYOUT ANALYSIS
      → FIELD EXTRACTION → CONFIDENCE SCORING → VALIDATION → GIS CHECK
      → RISK SCORING → COMPLETED
```

**Two key design decisions**
- **`ai/` imports no web framework**, so it can be tested, benchmarked, or split into its own service independently.
- **The ORM declares no PostGIS types.** Geometry is stored as portable GeoJSON; a real `geometry(Polygon,4326)` column with a GIST index is added when PostGIS is present, otherwise geodesic Shapely takes over. Both engines agree to within 1e-5 acres.

## 🧰 Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query, Recharts, React-Leaflet |
| **Backend** | Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0 |
| **Database** | PostgreSQL 16 + PostGIS 3.4 (SQLite fallback) |
| **Async** | Celery + Redis (in-process fallback) |
| **Documents / AI** | OpenCV, Pillow, PyMuPDF, Tesseract 5, TrOCR (Hugging Face + PyTorch) |
| **GIS** | PostGIS, Shapely, pyproj, GeoJSON, Leaflet |
| **Infra** | Docker, docker-compose, nginx |

## 🚀 Quick Start

### Option A: Docker (recommended)

```bash
git clone https://github.com/FarhanSyed987/LandIQ-Github.git
cd LandIQ-Github/LandIQ-Project/LandIQ
cp .env.example .env
docker compose up --build
```

Open **http://localhost:3000** and sign in with `officer@landiq.gov` / `LandIQ@123`.

| Service | URL / Port | Purpose |
|---|---|---|
| Frontend | http://localhost:3000 | nginx serving the app, proxying `/api` |
| Backend | http://localhost:8000 | FastAPI (`/docs` for Swagger UI) |
| Postgres | localhost:5433 | PostgreSQL 16 + PostGIS |
| Redis | localhost:6380 | Celery broker |

```bash
docker compose logs -f backend   # watch the pipeline
docker compose down -v           # stop and delete all data
```

### Option B: Run locally

**Requirements:** Python 3.11, Node 20+, Tesseract. PostgreSQL is optional (falls back to SQLite).

```bash
# 1. Tesseract
brew install tesseract                                  # macOS
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng \
  tesseract-ocr-ben tesseract-ocr-hin tesseract-ocr-osd libgl1   # Ubuntu

# 2. (Recommended) PostGIS
docker run -d --name landiq-postgres \
  -e POSTGRES_USER=landiq -e POSTGRES_PASSWORD=landiq -e POSTGRES_DB=landiq \
  -p 5433:5432 postgis/postgis:16-3.4

# 3. Backend
cd backend
python3.11 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cd .. && cp .env.example .env     # set TESSERACT_CMD for your OS
cd backend && ./.venv/bin/uvicorn app.main:app --reload --port 8000

# 4. Frontend (new terminal)
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

A `Makefile` wraps this: `make setup`, `make backend`, `make frontend`, `make reset`, `make test`, `make docker`.

## ⚙️ Configuration

Copy `.env.example` to `.env`. Key variables:

| Variable | Default | Meaning |
|---|---|---|
| `DEMO_MODE` | `true` | Serve transcription from the controlled demo dataset |
| `DATABASE_URL` | `postgresql+psycopg://landiq:landiq@localhost:5433/landiq` | Primary database |
| `DATABASE_FALLBACK_URL` | `sqlite:///./landiq_fallback.db` | Used if primary is unreachable |
| `CELERY_ENABLED` | `false` | Use Celery instead of the thread runner |
| `TESSERACT_CMD` | n/a | Path to the tesseract binary |
| `TROCR_ALLOW_DOWNLOAD` | `0` | `1` allows the ~1.3 GB TrOCR weight download |
| `QA_THRESHOLD` | `0.85` | Fields below this go to human review |
| `GIS_AREA_TOLERANCE_PCT` | `5.0` | Area difference counted as a MATCH |
| `RISK_HIGH_THRESHOLD` | `70` | Score at which a record becomes HIGH risk |
| `JWT_SECRET` | dev value | ⚠️ **Change for any real deployment** |

> Thresholds are prototype operating parameters, not legal or universal accuracy standards.

## 🔑 Demo Credentials

| Role | Email | Password |
|---|---|---|
| Officer | `officer@landiq.gov` | `LandIQ@123` |
| Administrator | `admin@landiq.gov` | `LandIQ@123` |
| Reviewer | `reviewer@landiq.gov` | `LandIQ@123` |

A Reviewer cannot upload or verify; an Officer cannot change settings; an Administrator can do both.

## 🎬 The 5-Minute Demo

Reset to a clean state first:

```bash
python backend/scripts/reset_demo.py --yes
```

1. **Sign in** as the officer
2. **Dashboard**: 24 records, 4 high risk, 6 GIS mismatches, parcel map
3. **Digitise a document**: load the hero sample and watch the 11-stage pipeline run live
4. **Open the record**: HIGH RISK banner, scan with colour-coded evidence boxes
5. **Click the Area field** (8.4 acre, 34% RED) to see the cropped source pixels and Tesseract's raw output
6. **Validation / GIS / History / Risk tabs**: ownership conflict, area mismatch, impossible timeline, itemised score
7. **Officer review**: accept the alternate reading `2.4 acre`
8. **Watch** GIS flip to MATCH and risk drop 94 → 73
9. **Verify** the record, check the **Audit Trail**, and **export** the PDF summary

Optional: upload `doc1_ror_clean.png` as the clean control case (LOW risk).

## 🔬 DEMO_MODE: What Is Real

`DEMO_MODE=true` changes **exactly one thing**: the *transcription text* assigned to a recognised region. Everything else runs for real on the uploaded pixels:

| Always computed | Controlled in DEMO_MODE |
|---|---|
| OpenCV restoration, skew, perspective | The text assigned to a value region |
| Region detection and classification | |
| Pixel quality metrics | |
| Tesseract's raw output | |
| Confidence fusion and disagreement | |
| Validation, duplicates, history checks | |
| PostGIS geometry, areas, reconciliation | |
| Risk scoring, audit, export | |

The 34% confidence on the hero field is **computed**, not hard-coded. Upload a cleaner scan and the numbers move. Set `DEMO_MODE=false` for pure engine output.

## 🧠 AI Pipeline

**Confidence fusion** combines three independent signals:

```
confidence = 0.40 · engine confidence
           + 0.25 · pixel quality of the region
           + 0.35 · agreement between two restoration passes
           − legibility penalty
```

A single engine's self-reported confidence is a poor uncertainty estimate on degraded scans. Disagreement between two restoration paths is exactly what an officer needs to see, and the dissenting reading is carried forward as the **alternative prediction** in the review panel.

**Transliteration** is deliberately conservative. LandIQ shows candidate name matches to reduce false conflict alarms, but **never concludes that two differently spelled names are the same person**. That decision stays with the officer.

## 🗺️ GIS

- Areas are computed on the **WGS84 ellipsoid**, never as planar degrees
- Reconciliation tolerances:

| Difference | Status | Effect |
|---|---|---|
| ≤ 5% | `MATCH` | No risk contribution |
| ≤ 15% | `WARNING` | +30% of GIS weight |
| > 15% | `MISMATCH` | Up to full GIS weight (30 points) |

## 📡 API

Interactive docs: **http://localhost:8000/docs** (Swagger) and `/redoc`. 47 endpoints across auth, documents, records, parcels, validation, dashboard, audit, search, feedback, and settings. See [`docs/API.md`](docs/API.md).

Errors are typed and never leak stack traces:

```json
{
  "error": {
    "code": "unsupported_file",
    "message": "That file is not a PDF, PNG or JPEG.",
    "hint": "Re-scan or export the document as PDF or PNG."
  }
}
```

## 🧪 Testing

```bash
# End-to-end: 92 assertions over real HTTP against a running API
python backend/tests/test_hero_flow.py

# Browser: drives the full UI demo and screenshots every step
node frontend/tests/ui_demo_walkthrough.mjs

# Real handwriting inference on a sample
python htr_infer.py sample_documents/handwriting/iam_test/iam_test_0002.jpg

# Regenerate published CER/WER
python scripts/evaluate_htr.py --show-errors
```

## 📁 Project Structure

```
LandIQ/
├── ai/                  # Framework-free AI package
│   ├── preprocessing/   #   OpenCV restoration + quality metrics
│   ├── scripts/         #   Script identification
│   ├── ocr/             #   Regions, engines, confidence fusion
│   ├── extraction/      #   Schema mapping, normalisation, transliteration
│   ├── recognizers/     #   HTR interface, TrOCR, script registry
│   ├── evaluation/      #   CER/WER
│   └── demo/            #   Controlled demo dataset
├── backend/
│   ├── app/             #   api, core, db, models, schemas, services, workers
│   ├── scripts/         #   reset_demo.py
│   └── tests/
├── frontend/            # React app (13 routed screens)
├── database/init/       # PostGIS + pg_trgm bootstrap
├── sample_data/         # Seed dataset + generator
├── sample_documents/    # 3 synthetic scans + generator
├── docs/                # API, DATABASE, HTR, ARCHITECTURE
├── models.yaml          # Model manifest
├── docker-compose.yml
├── .env.example
└── Makefile
```

## ⚠️ Known Limitations

1. **Handwriting is Latin-only**, and TrOCR weights are an opt-in ~1.3 GB download. Digits and slash-delimited IDs are unreliable, so those fields always reach a human.
2. **`DEMO_MODE` controls transcription** (see above).
3. **No government API integration** (Bhoomi, Dharitree, DILRMP).
4. **ULPIN is never issued.** Only clearly marked `DEMO-` placeholders.
5. **Layout extraction is tuned for tabular forms**, not free-form deeds.
6. **Bengali/Hindi OCR is baseline** quality.
7. **Rate limiting is single-node** (move to Redis for multi-instance).
8. **Transliteration uses a curated gazetteer.** Unknown names stay Latin-only.
9. **All data is synthetic.**

## 🔮 Future Scope

- Fine-tuned Indic OCR/HTR on consented, de-identified records
- Layout-aware models (LayoutLMv3 / Donut)
- Integration with state land-record systems and the ULPIN registry
- Cadastral basemap overlays (WMS/WMTS)
- Multi-page deeds, encumbrance certificates, mutation orders
- Bulk ingestion with batch quality dashboards
- Row-level security and per-district partitioning
- Tamper-evident, hash-chained audit log

## 🛡️ Data & Ethics

- **All data is synthetic.** No real citizen's information appears anywhere.
- **Risk score is a triage signal**, not a legal determination of title or fraud.
- **LandIQ does not decide ownership.** It surfaces conflicts and asks an officer.
- **LandIQ does not self-train.** Retraining is human-approved only.
- **No field is shown without provenance** (page, bounding box, engine, model version).

## 🤝 Contributing

Contributions are welcome. Fork the repo, create a branch (`git checkout -b feature/your-feature`), commit, push, and open a Pull Request.

## 📄 License

Add a `LICENSE` file (e.g. MIT) and reference it here.

## 👤 Author

**Farhan Syed** · [@FarhanSyed987](https://github.com/FarhanSyed987)

---

<div align="center">

Built for **Smart India Hackathon** · Problem Statement SIH26018

⭐ If you find this project useful, consider giving it a star!

</div>
