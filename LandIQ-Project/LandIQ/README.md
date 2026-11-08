# LandIQ

**From Legacy Documents to Trusted Land Intelligence**

Smart India Hackathon — Problem Statement **SIH26018**: *Intelligent Land Record
Digitization and Validation System*

LandIQ turns scanned, ageing land documents into structured land records where
**every single field carries a confidence score and a link back to the exact
pixels it was read from**, is reconciled against surveyed parcel geometry, and
is risk-scored for human review.

**Handwriting recognition: verified for Latin/English only.** Printed OCR runs
Tesseract (eng/ben/hin). Handwriting runs a real pretrained TrOCR checkpoint,
inference-tested at **CER 0.0505** on held-out IAM samples. Every other script
returns `UNSUPPORTED` rather than a guess — see [`docs/HTR.md`](docs/HTR.md)
and [`models.yaml`](models.yaml).

---

## Table of contents

- [What it actually does](#what-it-actually-does)
- [Architecture](#architecture)
- [Features](#features)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Running with Docker](#running-with-docker)
- [Running locally](#running-locally)
- [Environment variables](#environment-variables)
- [Demo credentials](#demo-credentials)
- [The 5-minute demo walkthrough](#the-5-minute-demo-walkthrough)
- [DEMO_MODE — what is real and what is not](#demo_mode--what-is-real-and-what-is-not)
- [AI pipeline](#ai-pipeline)
- [GIS pipeline](#gis-pipeline)
- [Database schema](#database-schema)
- [API documentation](#api-documentation)
- [Testing](#testing)
- [Project structure](#project-structure)
- [Known limitations](#known-limitations)
- [Future scope](#future-scope)
- [Data and ethics statement](#data-and-ethics-statement)

---

## What it actually does

Upload a scan of a Record of Rights. LandIQ then, in one pass:

1. **restores** the page — denoise, CLAHE, sharpen, deskew, perspective-correct,
   threshold — and keeps every intermediate image so an officer can inspect it;
2. **identifies the script** (English / Bengali / Hindi / Mixed) from the pixels
   *and* from the recognised text, and reports which detector agreed;
3. **detects text regions** with morphological run-length smearing and classifies
   each one as printed or handwritten using stroke-width variance, baseline
   jitter and contour complexity;
4. **recognises** printed regions with Tesseract and handwritten regions through
   the TrOCR branch;
5. **extracts** the LandIQ common schema (17 fields) by label pairing over the
   detected layout, mapping regional formats (RoR / RTC / Jamabandi / Patta)
   onto one representation, and normalising units, names, dates and identifiers;
6. **scores confidence per field** by fusing three independent signals — the
   engine's own confidence, measured pixel quality of that region, and
   *agreement between two different restoration passes of the same pixels*;
7. **binds evidence** — page, bounding box, source text, engine and model version
   — to every field, so clicking a value highlights it on the original scan;
8. **validates** completeness, confidence, identifiers, GIS area, duplicates,
   ownership conflicts and the ownership timeline;
9. **reconciles the recorded extent against PostGIS geometry** on the WGS84
   ellipsoid;
10. **risk-scores** the record 0–100 with a full, itemised explanation;
11. **routes** anything uncertain to an officer, who corrects it — and every
    correction is audited and captured as a future training example.

### The hero case

The bundled degraded document records **2.40 acres**, but ink bleed has closed
the bowl of the leading digit so the scan genuinely reads like **8.40**.
LandIQ does not quietly pick one:

| | |
|---|---|
| Area read as | `8.40 acres` at **34% confidence (RED)** |
| Tesseract's literal output | `A4o, acres'` |
| Alternate restoration pass reads | `2.40 acres` |
| Surveyed geometry (PostGIS) | `2.37 acres` |
| GIS verdict | **MISMATCH — 254% difference** |
| Ownership | competing claim by *Md. Karim Ali* on the same survey number |
| History | a 2019 sale recorded *after* a 2021 mutation — chronologically impossible |
| **Risk** | **94 / 100 — HIGH** |

The officer accepts the alternative reading. The area becomes 2.40 acres, the
GIS check flips to **MATCH (1.27% difference)**, risk falls to 73, the change is
written to the audit trail with the old value, the reason and the officer's ID,
and the record can be verified.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  BROWSER                                                                     │
│  React 19 + TypeScript + Vite + Tailwind · React Router · React Query        │
│  ┌────────────┬────────────┬─────────────┬──────────────┬─────────────────┐  │
│  │ Dashboard  │ Upload +   │ Hero Record │ Officer      │ Parcels · Audit │  │
│  │ + map      │ pipeline   │ + evidence  │ Review / QA  │ Validation      │  │
│  └────────────┴────────────┴─────────────┴──────────────┴─────────────────┘  │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │  HTTPS / JSON  (nginx proxies /api)
┌───────────────────────────────────▼──────────────────────────────────────────┐
│  FASTAPI BACKEND                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ api/routes   auth · documents · records · parcels · validation ·       │  │
│  │              dashboard · audit · search · feedback · settings · files  │  │
│  ├────────────────────────────────────────────────────────────────────────┤  │
│  │ core         config · JWT + bcrypt · RBAC capability matrix ·          │  │
│  │              rate limiting · typed errors (never a stack trace)        │  │
│  ├────────────────────────────────────────────────────────────────────────┤  │
│  │ services     pipeline · validation · risk · gis · ulpin · export ·     │  │
│  │              search · dashboard · audit · storage · jobs               │  │
│  ├────────────────────────────────────────────────────────────────────────┤  │
│  │ models       18 SQLAlchemy tables (portable: no PostGIS types in ORM)  │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└───────┬───────────────────────────┬──────────────────────────┬───────────────┘
        │                           │                          │
┌───────▼─────────┐   ┌─────────────▼────────────┐   ┌─────────▼──────────────┐
│ ai/  (no web    │   │ PostgreSQL 16 + PostGIS  │   │ Celery + Redis         │
│      framework  │   │  · 18 tables, indexed    │   │  · same task function  │
│      imports)   │   │  · geometry(Polygon,4326)│   │    as the in-process   │
│                 │   │  · GIST spatial index    │   │    thread runner       │
│ preprocessing   │   │  · ST_Area(geography)    │   │  · auto-falls back if  │
│ scripts         │   │                          │   │    no broker is up     │
│ ocr (+conf)     │   │ SQLite fallback if the   │   └────────────────────────┘
│ extraction      │   │ server is unreachable    │
│ demo            │   └──────────────────────────┘   ┌────────────────────────┐
└─────────────────┘                                  │ Storage (S3-shaped     │
                                                     │ interface, local FS)   │
                                                     └────────────────────────┘
```

**Processing pipeline** — each stage persists its own artefacts, so the UI shows
real intermediate output rather than a progress bar over a black box:

```
UPLOAD ─► PREPROCESSING ─► SCRIPT DETECTION ─► OCR / HTR ─► LAYOUT ANALYSIS
   └─► FIELD EXTRACTION ─► CONFIDENCE SCORING ─► VALIDATION ─► GIS CHECK
       └─► RISK SCORING ─► COMPLETED
```

Two design decisions are worth calling out:

- **`ai/` imports no web framework.** It has no FastAPI or SQLAlchemy imports, so
  it can be unit-tested, benchmarked, or lifted into a separate `ai-service`
  container without touching the backend.
- **The ORM declares no PostGIS types.** Geometry is stored as portable GeoJSON;
  a real `geometry(Polygon,4326)` column with a GIST index is added and kept in
  sync at runtime *when PostGIS is present*. Spatial predicates then execute in
  the database, and fall back to geodesic Shapely when it is not. The two engines
  agree to within 1e-5 acres on the demo corpus.

---

## Features

| Area | What is implemented |
|---|---|
| **Auth** | JWT, bcrypt (12 rounds), three roles with a capability matrix, login throttling, per-IP rate limiting |
| **Upload** | Drag-and-drop, PDF/PNG/JPEG validated by *content* (magic bytes) not extension, 25 MB cap, SHA-256 duplicate detection |
| **Preprocessing** | 7 real OpenCV stages, before/after metrics, every stage image stored and viewable |
| **Script detection** | Tesseract OSD (pixels) + Unicode block histogram (text), combined with agreement reporting, MIXED detection |
| **OCR / HTR** | Tesseract (eng/ben/hin) for print; **real TrOCR handwriting recognition, inference-tested on Latin (CER 0.0505)**; deterministic demo engine — one interface, capability-detected |
| **Script coverage** | Enforced in code: `VERIFIED` (latin) / `CANDIDATE` (devanagari, disabled) / `UNSUPPORTED` / `UNKNOWN`. The system never guesses at a script it has not been shown to read |
| **Layout** | Morphological region detection, line grouping, printed/handwritten classification from stroke-width variance, baseline jitter, contour complexity |
| **Extraction** | 17-field common schema, 4 regional formats mapped, label pairing + pattern fallback, unit/name/date/identifier normalisation |
| **Confidence** | 3-signal fusion (engine confidence, pixel quality, cross-restoration agreement) with per-field breakdown |
| **Evidence binding** | Page, bbox, source text, engine, model version and a cropped image per field; click a field to highlight it on the scan |
| **QA** | Automatic routing below threshold, alternative predictions from a second restoration pass, accept / accept-alternative / edit / escalate |
| **Validation** | 7 checks: completeness, confidence, identifiers, GIS area, duplicates, ownership conflict, ownership timeline |
| **GIS** | PostGIS geodesic area/perimeter/centroid, spatial overlap self-join, document-vs-survey reconciliation with configurable tolerance |
| **Risk** | 7 weighted inputs, 0–100, fully itemised — every point is traceable to an observation |
| **Digital twin** | Per-parcel page: geometry, map, ownership timeline, linked records and documents, validation summary, ULPIN readiness |
| **ULPIN** | Readiness assessment against 6 preconditions; **never fabricates an identifier** — demo ids are `DEMO-` prefixed and flagged non-authoritative |
| **Human-in-the-loop** | Split-screen review, inline editing, decisions recorded with outstanding findings |
| **Audit** | Append-only trail of every action with actor, timestamp, old→new values and reason |
| **Continuous learning** | Corrections captured as labelled examples with the image region and model version; retraining is explicitly **human-gated, never automatic** |
| **Search** | Owner (including transliterated and phonetic forms), survey/khata/plot, parcel code, village, district, risk, ULPIN state |
| **Export** | CSV, JSON (full record with fields, findings and risk) and a one-page PDF verification summary |
| **Errors** | Typed errors with plain-language messages and hints; a stack trace never reaches the browser |

---

## Tech stack

**Frontend** — React 19, TypeScript, Vite, Tailwind CSS, shadcn-style components,
Lucide icons, React Router, TanStack Query, Recharts, React-Leaflet

**Backend** — Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic-ready

**Database** — PostgreSQL 16 + PostGIS 3.4 (geodesic area, GIST spatial index)

**Async** — Celery + Redis, with an in-process thread runner as a drop-in fallback

**Documents** — OpenCV, Pillow, PyMuPDF

**AI** — Tesseract 5 (eng/ben/hin/osd), TrOCR via Hugging Face Transformers + PyTorch

**GIS** — PostGIS, Shapely, pyproj, GeoJSON, Leaflet

**Infra** — Docker, docker-compose, nginx

---

## Quick start

The fastest path, with everything containerised:

```bash
git clone <this-repo> landiq && cd landiq
cp .env.example .env
docker compose up --build
```

Then open **http://localhost:3000** and sign in with
`officer@landiq.gov` / `LandIQ@123`.

---

## Running with Docker

```bash
docker compose up --build          # start everything
docker compose logs -f backend     # watch the pipeline
docker compose down                # stop
docker compose down -v             # stop and delete all data
```

| Service | Port | Purpose |
|---|---|---|
| `frontend` | http://localhost:3000 | nginx serving the built app, proxying `/api` |
| `backend` | http://localhost:8000 | FastAPI (`/docs` for Swagger UI) |
| `worker` | — | Celery worker running the same pipeline code |
| `postgres` | localhost:5433 | PostgreSQL 16 + PostGIS 3.4 |
| `redis` | localhost:6380 | Celery broker and result backend |

The backend creates the schema, enables PostGIS, adds the geometry column and
seeds the demonstration dataset on first start. Ports are overridable
(`BACKEND_PORT`, `FRONTEND_PORT`, `POSTGRES_PORT`, `REDIS_PORT`).

---

## Running locally

Local development wants Python 3.11, Node 20+, and Tesseract. PostgreSQL is
recommended but **not required** — the app falls back to SQLite and the geodesic
Shapely GIS engine, and tells you so on the Settings screen.

### 1. System dependencies

```bash
# macOS
brew install tesseract
# optional: Bengali and Hindi language packs
curl -sSL -o "$(brew --prefix)/share/tessdata/ben.traineddata" \
  https://github.com/tesseract-ocr/tessdata_fast/raw/main/ben.traineddata
curl -sSL -o "$(brew --prefix)/share/tessdata/hin.traineddata" \
  https://github.com/tesseract-ocr/tessdata_fast/raw/main/hin.traineddata

# Debian / Ubuntu
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-ben \
                        tesseract-ocr-hin tesseract-ocr-osd libgl1 libglib2.0-0
```

### 2. Database (recommended)

```bash
docker run -d --name landiq-postgres \
  -e POSTGRES_USER=landiq -e POSTGRES_PASSWORD=landiq -e POSTGRES_DB=landiq \
  -p 5433:5432 postgis/postgis:16-3.4
```

### 3. Backend

```bash
cd backend
python3.11 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cd .. && cp .env.example .env          # adjust TESSERACT_CMD for your platform
cd backend && ./.venv/bin/uvicorn app.main:app --reload --port 8000
```

On first start it creates 18 tables, enables PostGIS and seeds 24 records,
10 parcels, 10 ownership chains and 3 officer accounts.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev              # http://localhost:5173, proxies /api to :8000
```

### 5. Regenerate the demo assets (optional)

```bash
python3 sample_documents/generate_documents.py   # the 3 synthetic scans
python3 sample_data/generate_seed.py             # parcels with exact geodesic areas
```

A `Makefile` wraps all of this: `make setup`, `make backend`, `make frontend`,
`make reset`, `make test`, `make docker`.

---

## Environment variables

Every variable is documented in [`.env.example`](.env.example). The ones that
matter most:

| Variable | Default | Meaning |
|---|---|---|
| `DEMO_MODE` | `true` | Serve transcription from the controlled demo dataset (see below) |
| `DATABASE_URL` | `postgresql+psycopg://landiq:landiq@localhost:5433/landiq` | Primary database |
| `DATABASE_FALLBACK_URL` | `sqlite:///./landiq_fallback.db` | Used automatically if the primary is unreachable |
| `CELERY_ENABLED` | `false` | `true` dispatches to Celery; falls back to the thread runner if no broker |
| `TESSERACT_CMD` | — | Path to the tesseract binary |
| `TROCR_ALLOW_DOWNLOAD` | `0` | `1` permits downloading TrOCR weights (~1.3 GB) on first use |
| `QA_THRESHOLD` | `0.85` | Fields below this are routed to human QA |
| `GIS_AREA_TOLERANCE_PCT` | `5.0` | Area difference within this counts as a MATCH |
| `RISK_HIGH_THRESHOLD` | `70` | Risk score at which a record becomes HIGH |
| `JWT_SECRET` | dev value | **Change this for any real deployment** |

> The confidence and risk thresholds are **prototype operating parameters**, not
> legal or universal accuracy standards. They are editable at runtime on the
> Settings screen.

---

## Demo credentials

| Role | Officer ID | Password |
|---|---|---|
| Officer | `officer@landiq.gov` | `LandIQ@123` |
| Administrator | `admin@landiq.gov` | `LandIQ@123` |
| Reviewer | `reviewer@landiq.gov` | `LandIQ@123` |

Roles differ by capability: a Reviewer cannot upload or verify, an Officer cannot
change system settings, an Administrator can do both.

---

## The 5-minute demo walkthrough

Reset to a clean state first so the hero document lands on `LIQ-2026-00127`:

```bash
python backend/scripts/reset_demo.py --yes
```

| # | Time | Action | What the judges see |
|---|---|---|---|
| 1 | 0:00 | Sign in as `officer@landiq.gov` | Government-style login; the sidebar footer shows the live engines — `postgis`, `tesseract`, demo mode |
| 2 | 0:20 | **Dashboard** | 24 records, 4 high risk, 6 GIS mismatches, 10 ownership conflicts, parcel map of Nadia district shaded by area reconciliation |
| 3 | 0:45 | **Digitise a document** → load the hero sample | Drag-and-drop; the 11-stage pipeline executes live with per-stage timings and messages |
| 4 | 1:20 | Open the created record `LIQ-2026-00127` | HIGH RISK banner explaining itself; the scan on the left with 17 colour-coded evidence boxes; fields on the right with confidence badges |
| 5 | 1:45 | Point at **Area — 8.4 acre, 34% RED** | Confidence is genuinely low; other fields are 93–97% |
| 6 | 2:00 | Click the **evidence crosshair** on Area | Modal shows the cropped source pixels, the bbox, the engine, the model version, Tesseract's literal `A4o, acres'`, and the alternative reading |
| 7 | 2:25 | **Validation** tab | Ownership conflict with `LIQ-2023-00127`, 2019-after-2021 timeline impossibility, area mismatch, all with drill-down |
| 8 | 2:50 | **GIS** tab | Document 8.40 ac vs surveyed 2.37 ac → **HIGH RISK — AREA MISMATCH**, 254% difference, with the parcel polygon on a map |
| 9 | 3:10 | **History** tab | Legitimate 2005 settlement → 2011 sale → 2021 mutation, then the flagged out-of-order entry |
| 10 | 3:25 | **Risk** tab | 94/100 with every contributing factor itemised and its points shown |
| 11 | 3:45 | **Officer review** | Split screen; QA panel shows *AI prediction 8.4* beside *alternate pass 2.4* with the evidence crop |
| 12 | 4:05 | Click **Accept "2.4 acre"** | Area becomes 2.40; **GIS flips to MATCH (1.27%)**; risk drops 94 → 73, live |
| 13 | 4:25 | **Verify record** | Blocked until outstanding findings are acknowledged; add a note and verify |
| 14 | 4:40 | **Audit Trail** | Upload → processed → created → area `8.4 → 2.40` with reason and officer → verified |
| 15 | 4:55 | **Export** → PDF | A one-page verification summary downloads |

Optional closers: upload `doc1_ror_clean.png` for the control case (95% average
confidence, area reconciled, LOW risk), or open a parcel for the digital twin
with its ULPIN readiness checklist.

---

## DEMO_MODE — what is real and what is not

This matters, so it is stated plainly.

**`DEMO_MODE=true` changes exactly one thing: the transcription of a recognised
text region.** Everything else in the pipeline executes for real against the
pixels that were actually uploaded:

| Genuinely computed, always | Controlled in DEMO_MODE |
|---|---|
| OpenCV restoration (all 7 stages) | The *text* assigned to a value region |
| Skew angle, perspective homography | |
| Text region detection and geometry | |
| Printed vs handwritten classification | |
| Per-region pixel quality metrics | |
| Tesseract's raw output (stored and displayed alongside) | |
| Confidence fusion, including cross-restoration disagreement | |
| Field normalisation, validation, duplicates, history checks | |
| PostGIS geometry, areas, overlaps, reconciliation | |
| Risk scoring, audit, persistence, export | |

Consequences worth noticing:

- The evidence bounding boxes the officer clicks are **derived from the uploaded
  pixels**, not stored coordinates.
- The 34% confidence on the hero area field is **computed**, not hard-coded —
  it falls out of Tesseract reading `A4o, acres'` while a second restoration pass
  reads something different.
- Upload a **cleaner scan of the same document and the numbers move.**
- An unrelated document that matches no demo profile is processed with **real
  OCR output**; LandIQ never attributes one document's field values to another.

`GET /api/health` reports exactly which engines are live, and the Settings screen
shows the same. Set `DEMO_MODE=false` for pure engine output.

---

## AI pipeline

```
                    ┌──────────────────────────┐
  uploaded scan ───►│ preprocessing (OpenCV)   │─── 7 stages, all stored
                    │ grayscale → denoise →    │    + a 3×3 homography so every
                    │ CLAHE → sharpen →        │    box can be mapped back to
                    │ deskew → perspective →   │    ORIGINAL page coordinates
                    │ threshold                │
                    └────────────┬─────────────┘
                                 ▼
            ┌────────────────────────────────────────┐
            │ script detection                       │
            │  Tesseract OSD (pixels)                │
            │  + Unicode block histogram (text)      │──► english | bengali |
            │  agreement raises confidence,          │    devanagari | mixed
            │  disagreement lowers it                │
            └────────────────────┬───────────────────┘
                                 ▼
            ┌────────────────────────────────────────┐
            │ text region detection                  │
            │  adaptive threshold → strip table      │
            │  rules → horizontal smear → contours   │
            │  → merge → line grouping               │
            └────────────────────┬───────────────────┘
                                 ▼
            ┌────────────────────────────────────────┐
            │ printed / handwritten classification   │
            │  stroke-width variance (distance xf)   │
            │  baseline jitter (detrended bottoms)   │
            │  contour complexity (P²/4πA)           │
            └──────────┬──────────────────┬──────────┘
                       ▼                  ▼
              ┌────────────────┐  ┌────────────────┐
              │ Tesseract OCR  │  │ TrOCR (HTR)    │   engines are capability-
              │ eng/ben/hin    │  │ HuggingFace    │   detected; a missing model
              └────────┬───────┘  └───────┬────────┘   degrades, never raises
                       └────────┬─────────┘
                                ▼
            ┌────────────────────────────────────────┐
            │ confidence fusion                      │
            │   0.40 · engine confidence             │
            │ + 0.25 · pixel quality of the region   │
            │ + 0.35 · agreement between TWO         │
            │          restoration passes            │
            │ − legibility penalty                   │
            └────────────────────┬───────────────────┘
                                 ▼
            ┌────────────────────────────────────────┐
            │ layout-aware field extraction          │
            │  label pairing → pattern fallback      │
            │  format mapping: RoR / RTC / Jamabandi │
            │                  / Patta               │
            │  normalisation: units (9 regional),    │
            │  names, dates, identifiers             │
            └────────────────────┬───────────────────┘
                                 ▼
                    evidence binding: page, bbox,
                    source text, engine, model version
```

The disagreement term is the important one. A single engine's self-reported
confidence is a poor uncertainty estimate on degraded historical scans —
Tesseract will happily report 80% on a smudge. When a glyph is genuinely
ambiguous, two different restoration paths resolve it differently, and *that
disagreement is exactly what an officer needs to see*. The disagreeing reading is
carried forward as the alternative prediction in the QA panel.

**Transliteration** is deliberately conservative. Bengali and Devanagari are
transliterated to Latin with a rule-based ISO-15919-style mapping, and a phonetic
key collapses the aspiration and v/w/b distinctions that clerks routinely lose.
The result is used to *show an officer candidate matches* and to reduce false
"ownership conflict" alarms between spelling variants. **LandIQ never concludes
that two differently-spelled names are the same person** — that has legal
consequences and stays with the officer.

---

## GIS pipeline

- Parcel boundaries are stored as **portable GeoJSON**, always.
- When PostGIS is available, a `geometry(Polygon,4326)` column with a **GIST
  index** is created at runtime and kept in sync; predicates then run in the
  database.
- Areas are computed on the **WGS84 ellipsoid** (`ST_Area(geography)` /
  `pyproj.Geod`), never as planar degrees — a planar area in EPSG:4326 is
  meaningless and would silently produce wrong acreage.
- The two engines agree to within **1e-5 acres** on the demo corpus.

Reconciliation compares the document's extent against the surveyed geometry:

| Difference | Status | Effect |
|---|---|---|
| ≤ 5% | `MATCH` | no risk contribution |
| ≤ 15% | `WARNING` | +30% of the GIS weight |
| > 15% | `MISMATCH` | up to the full GIS weight (30 points) |

Seed parcel polygons are generated to a **target geodesic area** by Newton
correction on the square root of the area ratio, so the demonstration
differences are exact and reproducible (hero parcel: 2.370000 acres).

---

## Database schema

18 tables. Full reference: [`docs/DATABASE.md`](docs/DATABASE.md).

```
users ──────┬── documents ──┬── document_pages ── text_regions
            │               ├── processing_jobs
            │               └── land_records ──┬── extracted_fields ── evidence_bindings
            │                                  ├── validations
            │                                  ├── risk_assessments
            │                                  ├── verification_reviews
            │                                  └── feedback_corrections
            └── audit_logs                              │
                                                        │
parcels ──┬── parcel_geometries  (+ PostGIS geom, GIST) │
          └── ownership_history ── owners               │
                                                  model_versions
```

Indexed for the queries the UI actually makes: `survey_number`, `khata_number`,
`parcel_code`, `owner_name`, `owner_name_normalized`, `owner_phonetic_key`,
`risk_level`, `verification_status`, plus composites on
`(risk_level, verification_status)`, `(survey_number, village)` and
`(owner_name_normalized, survey_number)`.

---

## API documentation

Interactive Swagger UI at **http://localhost:8000/docs**, ReDoc at `/redoc`.
Full reference: [`docs/API.md`](docs/API.md). 47 endpoints.

```
POST   /api/auth/login                     GET    /api/records
GET    /api/auth/me                        GET    /api/records/{id}
POST   /api/auth/logout                    POST   /api/records/{id}/validate
                                           GET    /api/records/{id}/risk
POST   /api/documents/upload               GET    /api/records/{id}/qa
GET    /api/documents                      POST   /api/records/{id}/qa
GET    /api/documents/{id}                 POST   /api/records/{id}/correct
POST   /api/documents/{id}/process         POST   /api/records/{id}/verify
GET    /api/documents/{id}/status          POST   /api/records/{id}/review
GET    /api/documents/{id}/ocr             GET    /api/records/{id}/history
GET    /api/documents/{id}/fields          GET    /api/records/{id}/evidence
GET    /api/documents/{id}/evidence        GET    /api/records/{id}/export
DELETE /api/documents/{id}
                                           GET    /api/parcels
GET    /api/dashboard/stats                GET    /api/parcels/map
GET    /api/dashboard/charts               GET    /api/parcels/{id}
GET    /api/dashboard/recent               GET    /api/parcels/{id}/geometry
GET    /api/dashboard/high-risk            GET    /api/parcels/{id}/history
                                           POST   /api/parcels/{id}/ulpin
GET    /api/audit
GET    /api/audit/record/{id}              POST   /api/feedback
GET    /api/validation                     GET    /api/feedback
GET    /api/search                         GET    /api/feedback/learning-loop
GET    /api/search/facets                  GET    /api/feedback/models
GET    /api/settings                       GET    /api/health
PATCH  /api/settings                       GET    /api/files/{key}
```

Errors are typed and never leak internals:

```json
{
  "error": {
    "code": "unsupported_file",
    "message": "That file is not a PDF, PNG or JPEG. Only scanned land documents in those formats can be processed.",
    "details": { "declared_type": "text/plain" },
    "hint": "Re-scan or export the document as PDF or PNG."
  }
}
```

---

## Testing

```bash
# Real HTR inference on a genuine handwriting sample
python htr_infer.py sample_documents/handwriting/iam_test/iam_test_0002.jpg
python htr_infer.py --list-models        # published script coverage + provenance

# Regenerate the published CER/WER (never hand-copied)
python scripts/evaluate_htr.py --show-errors

# End-to-end: 92 assertions over real HTTP against a running API
python backend/tests/test_hero_flow.py

# Browser: drives the real UI through the whole demo, screenshots every step
node frontend/tests/ui_demo_walkthrough.mjs
```

The backend test (92 assertions, all passing with HTR enabled) asserts the full journey — login, dashboard, upload, all 11
pipeline stages, preprocessing metrics, script detection, OCR regions, field
extraction, confidence bands, the QA queue and its alternative, evidence
geometry inside page bounds, all 7 validation checks, the GIS mismatch, the
ownership timeline, the risk breakdown, correction, the resulting risk drop,
verification gating, the audit trail, all three export formats, and the clean
control document coming out LOW risk. Screenshots from the UI run land in
`frontend/tests/screenshots/`.

---

## Project structure

```
landiq/
├── ai/                       # framework-free AI package
│   ├── recognizers/          #   HTR: base interface, TrOCR, script registry
│   ├── evaluation/           #   CER/WER with an explicit normalisation contract
│   ├── preprocessing/        #   OpenCV restoration + quality metrics
│   ├── scripts/              #   script identification
│   ├── ocr/                  #   regions, engines, confidence fusion
│   ├── extraction/           #   schema mapping, normalisation, transliteration
│   └── demo/                 #   controlled demo dataset + document matching
├── backend/
│   ├── app/
│   │   ├── api/routes/       #   auth, documents, records, parcels, misc
│   │   ├── core/             #   config, security, errors, rate limiting
│   │   ├── db/               #   engine, session, init, seed
│   │   ├── models/           #   18 SQLAlchemy models
│   │   ├── schemas/          #   Pydantic request/response models
│   │   ├── services/         #   pipeline, validation, risk, gis, ulpin, …
│   │   └── workers/          #   Celery app + tasks
│   ├── scripts/reset_demo.py
│   └── tests/test_hero_flow.py
├── frontend/
│   ├── src/
│   │   ├── components/       #   ui primitives + domain components
│   │   ├── pages/            #   13 routed screens
│   │   ├── hooks/            #   auth, toasts
│   │   ├── lib/              #   typed API client, formatting
│   │   └── types/            #   TypeScript mirrors of the API
│   └── tests/ui_demo_walkthrough.mjs
├── database/init/            # PostGIS + pg_trgm bootstrap
├── sample_data/              # seed dataset + generator
├── sample_documents/         # 3 synthetic scans + generator + manifest
├── docs/                     # API, DATABASE, DEMO_SCRIPT, ARCHITECTURE
├── models.yaml               # model manifest incl. rejected candidates + why
├── htr_infer.py              # standalone HTR CLI
├── docker-compose.yml
├── .env.example
└── Makefile
```

---

## Known limitations

These are honest limits of a hackathon prototype, not hidden ones.

1. **Handwriting is Latin-only, and the weights are an opt-in 1.3 GB download.**
   `pip install -r backend/requirements-ai.txt` then
   `python scripts/download_models.py trocr-base-handwritten-en`. Until then the
   branch reports itself unavailable with a reason. Devanagari is registered as
   a CANDIDATE but has **not** been inference-tested here; Bengali and other
   Indic scripts are unsupported. Measured failure modes matter: digits are
   unsafe (`39`→`33` at 0.946 confidence) and slash-delimited identifiers
   (`WB/RS/2011/007742`) are reliably mangled, so those fields always reach a
   human. See [`docs/HTR.md`](docs/HTR.md).
2. **DEMO_MODE controls transcription.** See the section above for exactly what
   that does and does not affect. Judges can set `DEMO_MODE=false` and watch
   pure Tesseract output flow through the identical pipeline.
3. **No government API integration.** There is no live link to Bhoomi, Dharitree,
   DILRMP or any state registry. The schema-mapping layer is the seam where that
   would attach.
4. **ULPIN is never issued.** LandIQ assesses readiness and mints a clearly
   marked `DEMO-` placeholder for demonstration only.
5. **Layout extraction is tuned for tabular forms.** Free-form deeds, multi-column
   registers and rotated stamps are not handled well.
6. **Bengali/Hindi OCR is baseline.** Tesseract's Indic accuracy on degraded
   scans is materially worse than on English; a fine-tuned model is future work.
7. **Single-node rate limiting.** The counter is in-process; a multi-instance
   deployment needs it in Redis.
8. **Transliteration uses a curated gazetteer.** Names outside it are reported
   Latin-only rather than machine-transliterated, because a wrong Indic spelling
   of a citizen's name in a land record is not an acceptable guess.
9. **Everything is synthetic.** No real land record, person or boundary is used.

---

## Future scope

- Fine-tuned Indic OCR/HTR on real (consented, de-identified) revenue records
- Layout-aware document models (LayoutLMv3 / Donut) replacing rule-based pairing
- Integration with state land-record systems and the ULPIN registry
- Cadastral basemap overlays (state WMS/WMTS) instead of OSM tiles
- Multi-page deeds, encumbrance certificates and mutation orders
- Officer-facing bulk ingestion with per-batch quality dashboards
- A formal model-evaluation harness over the accumulated correction dataset
- Row-level security and per-district data partitioning
- Signed, tamper-evident audit log (hash chaining)

---

## Data and ethics statement

- **All data in this repository is synthetic.** Owner names, identifiers, dates,
  villages and boundaries were invented for the prototype. No real citizen's
  information appears anywhere.
- **The risk score is an operational triage signal**, used to order a review
  queue. It is not a legal determination about title, ownership or fraud.
- **LandIQ does not decide ownership.** Where two records conflict, it surfaces
  the conflict, shows the evidence and asks an officer.
- **LandIQ does not self-train.** Corrections are collected as labelled examples
  for a deliberate, human-approved retraining cycle. No model changes itself in
  response to production data.
- **No field is displayed without provenance.** Every value can be traced to a
  page, a bounding box, an engine and a model version.

---

Built for Smart India Hackathon · Problem Statement SIH26018
