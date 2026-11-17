<p align="center">
  <img src="frontend/public/kunyao-logo.svg" height="64" />
</p>

<h1 align="center">Kunyao AI Interview</h1>

<p align="center">
  <strong>A self-hosted AI interviewer that runs real-time voice interviews and writes the evaluation report.</strong><br />
  HR defines jobs and question banks, candidates open a one-time link, and a realtime speech model conducts the interview while integrity signals and transcripts are recorded for human review.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black" />
  <img src="https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white" />
  <img src="https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/SQLite%20%7C%20Postgres-SQLAlchemy%202-003B57?logo=sqlite&logoColor=white" />
  <img src="https://img.shields.io/badge/Docker-Caddy%20HTTPS-2496ED?logo=docker&logoColor=white" />
</p>

---

## Features

- **Realtime voice interview** - The browser streams microphone audio and camera frames over one WebSocket; **Qwen-Omni Realtime** answers with speech and live subtitles.
- **Job and question bank management** - Per-job description, language (zh/en), duration, interviewer voice, and questions with key points, reference answers, suggested follow-ups, difficulty and probe flags.
- **AI question drafting** - **DeepSeek** drafts questions from the job description with scoring key points, a reference answer and experience-probing follow-ups; HR reviews them in the bank.
- **Interviewer playbook** - The realtime model is briefed with a technical-interview playbook plus each question's confidential key points and follow-ups (never the reference answer).
- **One-time candidate links** - Each invite carries an unguessable token; a finished interview cannot be replayed.
- **Automatic evaluation report** - When the interview ends, **DeepSeek** scores professional ability, communication and job match from the transcript and writes feedback.
- **Integrity signals** - Live AI-read-answer detection, plus a post-interview analysis of answer-latency patterns, main-question vs follow-up score gaps, and similarity to AI-generated answers; each finding is stored with its evidence and rolled up into a green / yellow / red level.
- **Supervisor links** - Read-only links that follow the live transcript without exposing the candidate token.
- **Camera welcome** - On-device person detection (**MediaPipe**, WASM) plays the greeting clip when someone walks up; no lobby frame leaves the browser.
- **Fail-closed admin boundary** - HTTP Basic auth, wrong-password throttling, same-origin write checks and a Content-Security-Policy on every page.
- **Single-container deploy** - One image serves the API and the built frontend; Caddy adds automatic HTTPS.

---

## Quick Start

```bash
git clone https://github.com/SuperGokou/AI_interview.git
cd AI_interview/deploy
cp .env.example .env          # set DOMAIN, ADMIN_PASSWORD and the model keys
chmod 600 .env
docker compose --env-file .env up -d --build
docker compose ps             # app should report "healthy"
```

## Service URLs

| Service | URL |
|---------|-----|
| Candidate interview | `https://<DOMAIN>/interview?token=<invite-token>` |
| Supervisor view | `https://<DOMAIN>/supervise?token=<supervisor-token>` |
| Admin console | `https://<DOMAIN>/admin` |
| Health check | `https://<DOMAIN>/api/health` |
| API docs (admin only) | `https://<DOMAIN>/docs` |
| Local development | `http://127.0.0.1:8010/interview` |

## Prerequisites

- **Docker** with Compose v2 - for deployment
- **A domain** pointing at the server, ports 80/443 open - camera and microphone require HTTPS
- **DashScope API key** with access to a Qwen-Omni realtime model - the live interview
- **DeepSeek API key** (or any OpenAI-compatible endpoint) - scoring and integrity analysis
- **Embedding endpoint** (optional) - AI-answer similarity; defaults to DashScope with the same key, or point it at a self-hosted model such as bge-m3
- **Python 3.12** and **Node.js 24** - local development only

---

## Deploy

1. Point a DNS record at the server and open ports 80 and 443.
2. Copy `deploy/.env.example` to `deploy/.env`; set `DOMAIN`, `ADMIN_PASSWORD`, `DASHSCOPE_API_KEY`, `DEEPSEEK_API_KEY`.
3. Set `QWEN_OMNI_WS_URL` to the provider's realtime **WebSocket** endpoint for your workspace (not the OpenAI-compatible HTTP URL).
4. From `deploy/`, run `docker compose --env-file .env up -d --build`. Caddy obtains the certificate on first start.
5. Verify: `/api/health` returns 200 with `"database": "up"`, anonymous `/api/sessions` returns 401, and the admin sign-in works.
6. Create a job, add questions, generate a candidate link and run one full test interview before handing over.

Data lives in the `interview_data` volume; never run `down -v` on a server with records. See [deploy/README.md](deploy/README.md) for backup, upgrade and runtime-protection notes.

### Local development

```bash
python -m venv .venv
.venv/bin/pip install -r backend/requirements.txt     # Windows: .venv\Scripts\pip
cp .env.example .env                                  # set ADMIN_PASSWORD and model keys

cd frontend && npm ci && npm test && npm run build && cd ..
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest backend/tests -q
./scripts/start-local.sh                              # serves API + built frontend on :8010
```

For frontend hot reload run `npm run dev` in `frontend/` (port 5173, proxies `/api` and `/ws` to `localhost:8000`).

---

## Architecture

```
AI_interview/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app, static/SPA serving, cache policy
│   │   ├── security.py           # admin boundary, throttle, security headers
│   │   ├── config.py             # settings from environment
│   │   ├── api/
│   │   │   ├── interview_ws.py   # /ws/interview: browser <-> realtime model
│   │   │   ├── sessions.py       # invites, consent, transcripts, reports
│   │   │   ├── jobs.py           # job CRUD
│   │   │   ├── questions.py      # question bank CRUD
│   │   │   ├── supervisors.py    # read-only supervisor links
│   │   │   ├── dashboard.py      # aggregate stats
│   │   │   └── health.py         # liveness (503 when the database is down)
│   │   ├── core/
│   │   │   ├── interview_bridge.py  # Qwen-Omni SDK wrapper -> asyncio queue
│   │   │   ├── scoring.py           # report generation (DeepSeek)
│   │   │   ├── question_generator.py # AI-drafted questions with follow-ups
│   │   │   ├── cheat_detection.py   # AI-read-answer detector
│   │   │   ├── integrity.py         # severity weights -> green/yellow/red
│   │   │   ├── answer_timing.py     # question-end -> speech-onset latency
│   │   │   ├── integrity_signals.py # latency / probe-gap / similarity rules
│   │   │   ├── integrity_analysis.py # post-interview analysis -> cheat events
│   │   │   ├── answer_review.py     # per-answer scoring, AI reference answers
│   │   │   ├── embeddings.py        # OpenAI-compatible embedding client
│   │   │   └── session_summary.py   # list queries without N+1
│   │   ├── db/                   # engine, models
│   │   └── prompts/              # interviewer persona and opener
│   └── tests/                    # pytest suite (API, websocket, security)
├── frontend/
│   ├── src/
│   │   ├── routes/interview/     # candidate room, supervisor room
│   │   ├── routes/admin/         # dashboard, jobs, questions, candidates, reports
│   │   ├── hooks/                # useInterviewSession, useWelcomePresence
│   │   ├── audio/                # PCM conversion, playback, base64
│   │   └── lib/                  # API client, avatar state, presence logic
│   └── public/
│       ├── audio/pcm-worklet.js  # microphone batching worklet
│       └── vendor/presence/      # MediaPipe WASM + person model (self-hosted)
├── deploy/
│   ├── compose.yml               # app + Caddy
│   ├── Caddyfile                 # HTTPS, compression, HSTS
│   └── gpu/                      # optional avatar research tools (not required)
├── Dockerfile                    # multi-stage: build frontend, run backend
└── docker-compose.yml            # local single-container run
```

---

## System Design

### High-Level Architecture

```mermaid
graph TB
    subgraph Clients["Browsers"]
        CAND["Candidate<br/>/interview"]
        SUP["Supervisor<br/>/supervise"]
        HR["HR admin<br/>/admin"]
    end

    subgraph Edge["Edge"]
        CADDY["Caddy<br/>TLS, compression, HSTS"]
    end

    subgraph App["Application container"]
        SEC["Admin boundary<br/>Basic auth, throttle, CSP"]
        REST["REST API"]
        WS["/ws/interview"]
        SPA["Static SPA"]
    end

    subgraph Data["Storage"]
        DB[("SQLite volume<br/>or Postgres")]
    end

    subgraph Models["External model services"]
        QWEN["Qwen-Omni Realtime<br/>speech in / speech out"]
        DS["DeepSeek<br/>scoring, AI-text detection"]
    end

    CAND --> CADDY
    SUP --> CADDY
    HR --> CADDY
    CADDY --> SEC
    SEC --> REST
    SEC --> SPA
    CADDY --> WS
    REST --> DB
    WS --> DB
    WS <--> QWEN
    WS --> DS
    REST --> DS

    style Clients fill:#e0f2fe,stroke:#0284c7,stroke-width:2px
    style Edge fill:#fef9c3,stroke:#ca8a04,stroke-width:2px
    style App fill:#dcfce7,stroke:#16a34a,stroke-width:2px
    style Data fill:#f3e8ff,stroke:#9333ea,stroke-width:2px
    style Models fill:#ffe4e6,stroke:#e11d48,stroke-width:2px
```

### Data Flow Pipeline

```mermaid
sequenceDiagram
    participant C as Candidate browser
    participant A as FastAPI
    participant Q as Qwen-Omni Realtime
    participant D as DeepSeek
    participant DB as Database

    C->>A: GET /api/sessions/{token}
    C->>A: POST /api/sessions/{token}/consent
    C->>A: WS /ws/interview?token=...
    A->>Q: open realtime session (persona + question bank)
    A->>DB: status = active
    loop Every 100 ms / 1.5 fps
        C->>A: audio chunk / camera frame
        A->>Q: append audio / image
    end
    Q-->>A: speech audio + transcript deltas
    A-->>C: audio + subtitles
    Q-->>A: candidate transcript
    A->>DB: store transcript
    A-)D: AI-text check (background)
    D--)A: verdict
    A-->>C: integrity level
    C->>A: disconnect or time limit
    A->>DB: status = done
    A->>D: score each answer, generate AI reference answers
    A->>DB: store integrity findings
    A->>D: score transcript
    D-->>A: scores + feedback
    A->>DB: store report
```

### Component Architecture

```mermaid
graph LR
    subgraph FE["Frontend"]
        ROOM["InterviewRoom"]
        HOOK["useInterviewSession"]
        WORKLET["pcm-worklet"]
        PLAYER["PCM player"]
        PRESENCE["Presence worker"]
    end

    subgraph BE["Backend"]
        WSH["interview_ws"]
        BRIDGE["InterviewBridge"]
        DETECT["AiTextDetector"]
        REPORT["ReportGenerator"]
        STORE["report_store / cheat_store"]
    end

    ROOM --> HOOK
    HOOK --> WORKLET
    HOOK --> PLAYER
    ROOM --> PRESENCE
    HOOK <--> WSH
    WSH <--> BRIDGE
    WSH --> DETECT
    WSH --> REPORT
    DETECT --> STORE
    REPORT --> STORE

    style FE fill:#e0f2fe,stroke:#0284c7,stroke-width:2px
    style BE fill:#dcfce7,stroke:#16a34a,stroke-width:2px
```

### WebSocket Admission

```mermaid
flowchart TD
    START["WS /ws/interview?token=..."] --> T{"Token exists?"}
    T -- no --> E1["error: invalid token"]
    T -- yes --> F{"Session already finished?"}
    F -- yes --> E2["error: link already used"]
    F -- no --> J{"Job still exists?"}
    J -- no --> E3["error: job removed"]
    J -- yes --> M{"Realtime model connects?"}
    M -- no --> E4["error: service unavailable<br/>invite stays usable"]
    M -- yes --> RUN["status = active<br/>stream audio and video"]
    RUN --> END{"Disconnect or<br/>duration + 5 min"}
    END --> DONE["status = done"]
    DONE --> TR{"Any transcript?"}
    TR -- yes --> REP["Generate report"]
    TR -- no --> SKIP["Skip report"]

    style START fill:#e0f2fe,stroke:#0284c7,stroke-width:2px
    style RUN fill:#dcfce7,stroke:#16a34a,stroke-width:2px
    style REP fill:#dcfce7,stroke:#16a34a,stroke-width:2px
    style E1 fill:#ffe4e6,stroke:#e11d48,stroke-width:2px
    style E2 fill:#ffe4e6,stroke:#e11d48,stroke-width:2px
    style E3 fill:#ffe4e6,stroke:#e11d48,stroke-width:2px
    style E4 fill:#ffe4e6,stroke:#e11d48,stroke-width:2px
```

### How It Works

1. HR creates a job with a description, language, duration and voice, then adds questions.
2. HR generates a candidate link (and optional supervisor links) from the admin console.
3. The candidate opens the link, grants camera and microphone access and gives consent.
4. The browser opens one WebSocket; the server opens a realtime model session primed with the interviewer persona and the question bank.
5. Microphone audio (16 kHz PCM, 100 ms chunks) and camera frames (640 px JPEG, 1.5 fps) flow up; interviewer speech (24 kHz PCM) and subtitles flow down.
6. Every candidate answer is stored with its response latency and checked in the background for AI-read patterns; hits raise the integrity level.
7. On disconnect or at the time limit the session is closed and the post-interview integrity analysis runs (latency pattern, follow-up gap, AI-answer similarity).
8. The transcript is scored with those findings in context, and the report appears in the admin console.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Liveness; 503 when the database is unreachable (public) |
| GET | `/api/sessions/{token}` | Session info for the candidate (public, token-scoped) |
| POST | `/api/sessions/{token}/consent` | Record candidate consent (public, token-scoped) |
| WS | `/ws/interview?token=` | Live interview stream (token-scoped) |
| GET | `/api/supervisors/{token}` | Supervisor view of a session (public, token-scoped) |
| GET | `/api/supervisors/{token}/transcripts` | Live transcript feed for a supervisor |
| GET | `/api/sessions` | List interview sessions |
| POST | `/api/sessions` | Create a candidate invite |
| GET | `/api/sessions/{token}/transcripts` | Full transcript |
| GET | `/api/sessions/{token}/cheat` | Integrity level and events |
| GET / POST | `/api/sessions/{token}/report` | Read / regenerate the evaluation report |
| GET / POST | `/api/sessions/{token}/supervisors` | List / create supervisor links |
| GET / POST | `/api/jobs` | List / create jobs |
| GET / PUT / DELETE | `/api/jobs/{id}` | Read / update / delete a job (409 if it has interviews) |
| GET / POST | `/api/jobs/{id}/questions` | List / add questions |
| POST | `/api/jobs/{id}/questions/generate` | Draft questions from the job description and add them to the bank |
| PUT / DELETE | `/api/questions/{id}` | Update / delete a question |
| GET | `/api/dashboard/stats` | Dashboard counters and recent sessions |
| POST | `/api/heygen/token` | Optional streaming-avatar token |
| POST | `/api/dev/demo-session` | Demo session; only when `DEV_ENDPOINTS=true` |

All endpoints not marked public require the admin credentials.

## Supported Models

| Role | Default | Configured by |
|------|---------|---------------|
| Realtime interviewer (speech + vision) | `qwen3.8-omni-flash-realtime` | `QWEN_OMNI_MODEL`, `QWEN_OMNI_WS_URL`, `DASHSCOPE_API_KEY` |
| Interviewer voices | Serena, Sunny, Kiki, Tina, Ethan, Dylan, Peter, Aiden | per job, default `QWEN_OMNI_VOICE` |
| Scoring and AI-text detection | `deepseek-chat` (any OpenAI-compatible endpoint) | `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_API_KEY` |
| AI-answer similarity embeddings | `text-embedding-v3` via DashScope (any OpenAI-compatible endpoint, e.g. self-hosted bge-m3) | `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY` |
| Lobby person detection | EfficientDet Lite0 via MediaPipe (in browser) | bundled |

## Domain Logic

| Rule | Behaviour |
|------|-----------|
| Interviewer identity | Introduces itself as `INTERVIEWER_NAME` from `INTERVIEWER_COMPANY`; does not name other vendors or discuss underlying technology |
| Session lifecycle | `pending` -> `active` on connect -> `done` on disconnect or time limit |
| Invite links | Single use: a `done` session rejects new connections |
| Time limit | Job duration plus 5 minutes grace, enforced by the server |
| Integrity score | Event weights low = 1, medium = 3, high = 6; total >= 3 is yellow, >= 6 is red |
| AI-text event | Recorded as high severity when the detector reports AI-like with confidence >= 0.6 |
| Answer latency | Estimated server-side: first audio chunk time + question audio length -> candidate speech onset; barge-in counts as 0 |
| Latency pattern | Medium when >= 3 long answers have a median pause >= 4 s with spread <= 1.5 s |
| Follow-up gap | Main-question average >= 75 and >= 30 points above the follow-up average; high with 2+ follow-ups, else medium |
| AI-answer similarity | Answer-to-AI-reference similarity divided by reference-to-reference similarity >= 0.97; high with 3+ answers, else medium |
| Long answer | Only answers of 60+ characters enter the latency and similarity checks |
| Report scores | Professional, communication, job match (0-100); demeanor is always empty because only text is scored |
| Overall score | Mean of the scored dimensions |
| High-risk session | Red integrity level, or a report with `ai_risk_level = high` |
| Empty interview | No transcript means no report and no model call |
| Job deletion | Refused while the job has interview records; close it instead |
| Admin sign-in | 10 wrong passwords from one address lock it out for 5 minutes |

---

## Configuration

```env
# --- required ---------------------------------------------------------------
DOMAIN=interview.example.com          # public hostname (deploy/compose.yml only)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=                       # admin API refuses all requests while empty
DASHSCOPE_API_KEY=                    # realtime interviewer
DEEPSEEK_API_KEY=                     # scoring + AI-text detection

# --- realtime model ---------------------------------------------------------
QWEN_OMNI_MODEL=qwen3.8-omni-flash-realtime
QWEN_OMNI_VOICE=Tina
QWEN_OMNI_WS_URL=wss://YOUR_WORKSPACE_ID.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime

# --- scoring model (OpenAI-compatible) --------------------------------------
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# --- optional ---------------------------------------------------------------
DATABASE_URL=                         # default SQLite; postgresql://user:pass@host/db also works
DEV_ENDPOINTS=false                   # true enables the unauthenticated demo session; never in production
CORS_ORIGINS=                         # comma-separated; empty for same-origin deployments
CONTENT_SECURITY_POLICY=              # unset = built-in policy; empty string disables it
HEYGEN_API_KEY=                       # optional streaming avatar
INTERVIEWER_NAME=KY-BOT               # how the interviewer introduces itself (branding only)
INTERVIEWER_COMPANY=江苏坤曜智能科技有限公司

# --- AI-answer similarity (optional) ----------------------------------------
EMBEDDING_API_KEY=                    # default: DASHSCOPE_API_KEY
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v3     # or a self-hosted bge-m3 behind an OpenAI-compatible server
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18, TypeScript 5, Vite 8, Tailwind CSS 3, React Router 7 |
| Browser media | Web Audio API, AudioWorklet, MediaPipe Tasks Vision (WASM) |
| Backend | FastAPI, Uvicorn, SQLAlchemy 2, Pydantic 2 |
| Realtime AI | DashScope Qwen-Omni Realtime SDK |
| Text AI | DeepSeek through the OpenAI SDK |
| Database | SQLite (WAL) by default, PostgreSQL through psycopg 3 |
| Edge | Caddy 2 (automatic HTTPS, zstd/gzip, HSTS) |
| Packaging | Multi-stage Docker image, Docker Compose |
| Testing | pytest, Vitest, Testing Library |
| CI | GitHub Actions: frontend test/build/audit, backend tests, image build |

---

## Limitations

- Single organization with one shared admin credential: no tenants, SSO, roles or admin audit log.
- The digital interviewer uses pre-rendered footage with an audio-driven mouth; it is not frame-accurate lip sync.
- The visual integrity pipeline is in place, but the realtime model does not yet emit structured visual observations, so integrity currently reflects the text, timing and follow-up signals.
- Integrity thresholds are reasoned defaults, not calibrated on labelled interviews; answer latency depends on the realtime provider emitting speech-onset events and has not been validated against a live model.
- Correct answers to textbook questions naturally resemble AI answers, so the similarity signal is most meaningful on open-ended and experience questions.
- Reports are model output and need human review; integrity signals are leads for review, not proof.
- A candidate who disconnects mid-interview cannot rejoin with the same link; a new one must be issued.
- The sign-in throttle is in-process, so it resets on restart and is not shared across replicas.
- No interview recording storage, automatic data retention or deletion policy, and no pagination on the session list.
- Schema changes rely on `create_all` plus automatic addition of new nullable columns; anything else still needs a manual migration.
- The realtime model is a hosted service and cannot be fine-tuned; interviewer quality is driven by the playbook prompt and question-bank context. AI-drafted questions are drafts and need HR review.
- No root LICENSE; third-party models, avatar footage and voice rights must be cleared separately. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [docs/RELEASE_REVIEW.md](docs/RELEASE_REVIEW.md).

---

## Future Development

### Roadmap

```mermaid
timeline
    title Kunyao AI Interview Roadmap
    v0.1 : Realtime voice interview
         : Admin console and reports
         : Single-container deploy with HTTPS
    v0.2 : Per-user admin accounts and roles
         : Session resume after a dropped connection
         : Database migrations
    v0.3 : Structured visual integrity events
         : Interview recording and playback
         : Data retention policies
    v1.0 : Multi-tenant organizations and SSO
         : Admin audit log
         : Horizontal scaling
```

### Near-term

| Feature | Description | Priority |
|---------|-------------|----------|
| Admin accounts | Individual logins with hashed passwords instead of one shared credential | High |
| Session resume | Let a candidate rejoin within a short window after a network drop | High |
| Migrations | Alembic for schema changes on live databases | High |
| List pagination | Page the session and candidate lists | Medium |

### Mid-term

| Feature | Description | Priority |
|---------|-------------|----------|
| Visual integrity | Structured gaze / multi-person / absence events from the vision model | High |
| Recording | Store and replay interview audio and video | Medium |
| Retention | Configurable deletion of transcripts and reports | Medium |
| Link expiry | Expiry and revocation for candidate and supervisor links | Medium |

### Long-term

| Feature | Description | Priority |
|---------|-------------|----------|
| Multi-tenancy | Isolated organizations with SSO | Medium |
| Audit log | Who viewed or changed what in the admin console | Medium |
| Realtime lip sync | GPU-rendered avatar driven by the live audio | Low |
| ATS integration | Push reports to applicant-tracking systems | Low |

### Architecture Evolution

```mermaid
graph LR
    subgraph Now["Current"]
        N1["One container<br/>SQLite volume<br/>shared admin login"]
    end
    subgraph Next["Next"]
        X1["Postgres + migrations<br/>per-user accounts<br/>session resume"]
    end
    subgraph Future["Future"]
        F1["Multiple app replicas<br/>shared session state<br/>object storage for recordings"]
    end
    N1 --> X1 --> F1

    style Now fill:#dcfce7,stroke:#16a34a,stroke-width:2px
    style Next fill:#fef9c3,stroke:#ca8a04,stroke-width:2px
    style Future fill:#f3e8ff,stroke:#9333ea,stroke-width:2px
```

### Contributing

1. Create a branch from the default branch.
2. Write a failing test first, then the change (`pytest backend/tests`, `npm test` in `frontend/`).
3. Make sure `npm run build` passes and no secrets or `.env` files are staged.
4. Open a pull request using conventional commit messages (`feat:`, `fix:`, `docs:` ...).
