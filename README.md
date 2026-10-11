# StorageWars

> **Can your friends describe a product well enough for everyone else to guess what it actually costs?**

StorageWars is a fast, social, mobile-first party game for friends on a voice call. Everyone gets a product image, writes a card describing it *without giving away the price*, and then everybody else tries to guess what the thing really costs. The reveal is where it gets good: wildly wrong guesses, suspiciously confident descriptions, and a lot of yelling.

No accounts. No installs. Just a room code and a few friends.

---

## Why I built this

I wanted a game that works the moment someone says "hey, join this link." Most party games either need everyone to download something or take ten minutes of explaining. This one takes about thirty seconds to explain:

1. Write a description of the thing you're shown.
2. Guess the price of everyone else's thing.
3. Laugh at the reveal.

Under the hood it's also a project I used to play with real-time multiplayer: server-authoritative state, WebSockets with a polling fallback, and a content pipeline that keeps product secrets hidden until exactly the right moment. If you're here to poke around the code, welcome. If you're here to play, skip to [Quick start](#-quick-start).

<!-- Add your own story here: who you play with, the funniest round so far, a screenshot or GIF. It'll make this README yours. -->

---

## How a game works

Every game is a single room that moves through six phases:

```mermaid
stateDiagram-v2
    direction LR
    [*] --> LOBBY
    LOBBY --> AUTHOR: host starts game
    AUTHOR --> GUESS: cards written
    GUESS --> REVEAL: guesses locked
    REVEAL --> VOTE: carousel finished
    VOTE --> FINAL: votes counted
    FINAL --> LOBBY: replay
    FINAL --> [*]
```

| Phase | What happens |
| --- | --- |
| **Lobby** | Create or join a room with a short code. |
| **Author** | Everyone writes one product card, in parallel. You see the image and a coarse price band, never the exact price. |
| **Guess** | You guess on everyone else's cards. Clues drip in over time, so waiting is a real decision. |
| **Reveal** | The real item and every guess appear together. This is the comedy moment. |
| **Vote** | Everyone votes for the funniest card. |
| **Final** | Scores for both guessing *and* card-writing, then replay instantly. |

### A round, from the players' point of view

```mermaid
sequenceDiagram
    actor A as Author
    actor G as Guessers
    participant S as Server

    S->>A: Product image + coarse price band
    A->>S: Writes card description
    S->>S: Validates, filters profanity, strips price leaks
    S->>G: Card text only (no image, no exact details)
    Note over G,S: Clues drip in over time.<br/>Guess early, or wait for more info?
    G->>S: Locks price guess (hidden)
    S->>S: Server timestamps every lock
    S-->>A: Reveal: original product + all guesses
    S-->>G: Reveal: original product + all guesses
    G->>S: Vote for funniest card
    S-->>A: Scores
    S-->>G: Scores
```

---

## Features

- **Mobile-first**, runs entirely in the browser
- **Private rooms** with short codes, no account or install
- **Server-authoritative** state, timers, scoring, and phase transitions
- **Real-time** updates over WebSocket, with polling fallback
- **Secrets stay secret** until the reveal
- **Drip-revealed clues**, so waiting is part of the strategy
- **Log-scaled guessing** from `$1` to `$1,000`
- **Hidden guesses** until reveal, so nobody herds
- **Funniest-card voting** and score breakdowns
- **Rejoin and replay** flows
- **Validation, profanity filtering, rate limiting, and moderation**
- **Deterministic offline fixtures** for the product ingestion pipeline

---

## How it's put together

```mermaid
flowchart LR
    subgraph Client["Browser"]
        UI["Vite + TypeScript<br/>Vanilla DOM"]
    end

    subgraph Server["FastAPI backend"]
        REST["REST API<br/>/v1"]
        WS["WebSocket<br/>/v1/ws/roomCode"]
        Engine["Game engine<br/>rooms, phases, timers"]
        Score["Scoring<br/>log-space error"]
        Guard["Validation + moderation"]
    end

    DB[("PostgreSQL")]
    Media[("Local media<br/>metadata-stripped images")]

    UI -- "actions" --> REST
    UI <-- "live events" --> WS
    UI -. "polling fallback" .-> REST
    REST --> Guard --> Engine
    WS --> Engine
    Engine --> Score
    Engine --> DB
    Engine --> Media
```

**Stack:** Vite + TypeScript on the front, FastAPI + Pydantic + SQLModel on the back, PostgreSQL for persistence, and OpenAPI/AsyncAPI for contracts. Tested with pytest and pytest-asyncio, managed with uv and Docker Compose.

### Who sees what, and when

The whole game depends on not leaking the price too early, so the server controls exactly what each role can see:

```mermaid
flowchart TB
    P[("Product record<br/>image, title, description, price, rating")]
    P -->|"image + coarse price band"| Author["Author"]
    P -->|"nothing before reveal"| Guesser["Guessers"]
    P -->|"full details"| Reveal["Reveal phase"]
    Author --> Reveal
    Guesser --> Reveal
```

- Clients submit inputs; the **server owns state**.
- Guessers never get the original image or exact details before reveal.
- Authors get a coarse price band, not the real number.
- Card order is **shuffled per player**.
- Timers and lock timestamps are measured **server-side**.
- Scores use **log-space error**, so being off on a $5 item matters as much as being off on a $500 one.

---

## Quick start

### Prerequisites

- Python 3.10+
- Node.js with npm, or Bun
- PostgreSQL
- Docker (optional, but the easiest way to get a database)

### 1. Start PostgreSQL

```bash
cd backend
docker compose up -d db
```

Default local connection:

```text
postgresql+psycopg://impulsebuy:impulsebuy@localhost:5432/impulsebuy
```

### 2. Install backend dependencies

```bash
cd backend
uv sync
```

Want product ingestion too?

```bash
uv sync --extra ingest
```

### 3. Configure

```bash
export DATABASE_URL='postgresql+psycopg://impulsebuy:impulsebuy@localhost:5432/impulsebuy'
export ADMIN_TOKEN='replace-with-a-secret'
```

<details>
<summary>On Windows PowerShell</summary>

```powershell
$env:DATABASE_URL = "postgresql+psycopg://impulsebuy:impulsebuy@localhost:5432/impulsebuy"
$env:ADMIN_TOKEN = "replace-with-a-secret"
```

</details>

### 4. Run the API

```bash
cd backend
PYTHONPATH=src uv run uvicorn openapi_server.main:app \
  --host 0.0.0.0 \
  --port 3000 \
  --ws-ping-interval 15 \
  --ws-ping-timeout 30
```

| What | Where |
| --- | --- |
| API base | `http://localhost:3000/v1` |
| Health check | `http://localhost:3000/v1/health` |
| Interactive docs | `http://localhost:3000/docs` |
| Product media | `http://localhost:3000/media/products/...` |
| Realtime | `ws://localhost:3000/v1/ws/{roomCode}` |

### 5. Run the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

Open `http://localhost:5173` and grab a friend (or open a second tab to play against yourself).

### Or run everything with Docker

```bash
cd backend
docker compose up --build
```

---

## Configuration

### Environment

```bash
DATABASE_URL=postgresql+psycopg://impulsebuy:impulsebuy@localhost:5432/impulsebuy
ADMIN_TOKEN=your-secret-token
PUBLIC_BASE_URL=http://localhost:3000
IMAGE_URL_SECRET=change-me
CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
TIME_SCALE=1.0
MEDIA_ROOT=media
SEED_FIXTURES=0
```

### Tuning the pace

Don't like how fast rounds go? Change the timers without touching code:

```bash
AUTHOR_SECONDS=60
CARD_CAP_SECONDS=20
MIN_DWELL_SECONDS=3
DRIP_BULLETS_SECONDS=5
DRIP_RATING_SECONDS=10
SLIDE_SECONDS=12
VOTE_SECONDS=30
REJOIN_GRACE_SECONDS=120
ROOM_TTL_SECONDS=1800
```

```mermaid
gantt
    title Default timing per phase (seconds, approximate)
    dateFormat X
    axisFormat %s
    section Author
    Write your card (AUTHOR_SECONDS) :0, 60
    section Guess
    Per-card cap (CARD_CAP_SECONDS) :60, 80
    Bullets drip in (DRIP_BULLETS_SECONDS) :milestone, 65, 0
    Rating drips in (DRIP_RATING_SECONDS) :milestone, 70, 0
    section Reveal
    Per slide (SLIDE_SECONDS) :80, 92
    section Vote
    Funniest card (VOTE_SECONDS) :92, 122
```

> The Gantt chart is a rough illustration of the defaults for a single card. Guess and reveal repeat per card, so a real game runs longer.

Full list and defaults live in [`backend/src/openapi_server/impl/config.py`](backend/src/openapi_server/impl/config.py).

---

## Where the products come from

Each game item is a curated record: image, original title and description, snapshot price, category, star rating, and review-count bucket.

```mermaid
flowchart LR
    A["Source dataset<br/>or fixtures"] --> B["Normalize prices"]
    B --> C{"Supported<br/>product?"}
    C -- "no" --> X["Dropped"]
    C -- "yes" --> D["Download image<br/>if configured"]
    D --> E["Re-encode +<br/>strip metadata"]
    E --> F[("Local media +<br/>PostgreSQL")]
```

### Offline fixture mode

No network, no image dependencies, fully deterministic. Great for development and tests:

```bash
cd backend
PYTHONPATH=src uv run python -m openapi_server.impl.ingest \
  --config ingest.yaml \
  --fixtures
```

### Dataset ingest mode

```bash
cd backend
uv sync --extra ingest
PYTHONPATH=src uv run --extra ingest python -m openapi_server.impl.ingest \
  --config ingest.yaml
```

For the bigger dataset:

```bash
PYTHONPATH=src uv run --extra ingest python -m openapi_server.impl.ingest \
  --config ingest.production.yaml
```

> Before using real product data in a public deployment, double-check the dataset, image, and redistribution licenses.

---

## Testing

```bash
cd backend
PYTHONPATH=src uv run pytest -q
```

The suite covers room lifecycle, authoring, guessing, reveals, voting, moderation, persistence, ingestion, redaction, and full end-to-end game flow.

---

## API overview

| Area | What it does |
| --- | --- |
| **Rooms** | Create rooms, join players, start games, replay |
| **Author** | Assign product cards, accept validated descriptions |
| **Guess** | Drip clues, save drafts, lock guesses |
| **Reveal** | Run the shared reveal carousel, expose product data at the right time |
| **Vote / Final** | Collect funniest-card votes, calculate rankings |
| **Session** | Player identity and rejoin credentials |
| **Moderation** | Reports, content controls, votekick |
| **System** | Health checks |
| **Admin** | Token-protected admin operations |

The source of truth is [`openapi.yaml`](openapi.yaml) for HTTP and [`asyncapi.yaml`](asyncapi.yaml) for realtime events.

### What happens when a connection drops

```mermaid
flowchart TD
    A["WebSocket connected"] --> B{"Connection lost?"}
    B -- "no" --> A
    B -- "yes" --> C["Frontend switches to polling"]
    C --> D{"Back within<br/>REJOIN_GRACE_SECONDS?"}
    D -- "yes" --> E["Rejoin with session credentials<br/>state resyncs"]
    E --> A
    D -- "no" --> F["Player marked away"]
```

Author drafts are also saved locally in your browser, so an accidental refresh doesn't eat your masterpiece.

---

## Repo tour

```mermaid
flowchart LR
    Root["StorageWars/"] --> Docs["PRD.md<br/>TECH_STACK.md<br/>COLOR_SCHEME.md"]
    Root --> Specs["openapi.yaml<br/>asyncapi.yaml"]
    Root --> BE["backend/"]
    Root --> FE["frontend/"]

    BE --> Impl["src/openapi_server/impl/"]
    BE --> Tests["tests/"]
    BE --> Ingest["ingest.yaml<br/>ingest.production.yaml"]

    Impl --> Engine["engine/<br/>rooms, phases, events"]
    Impl --> Scoring["scoring.py"]
    Impl --> RT["realtime.py"]
    Impl --> Val["validation.py"]
    Impl --> Pers["persistence.py"]

    FE --> API["src/api.ts"]
    FE --> Main["src/main.ts"]
    FE --> CSS["src/style.css"]
```

<details>
<summary>Full file tree</summary>

```text
StorageWars/
├── PRD.md # Product requirements and game design
├── TECH_STACK.md # Stack overview
├── COLOR_SCHEME.md # UI color guidance
├── openapi.yaml # HTTP API specification
├── asyncapi.yaml # Realtime API specification
├── openapitools.json # OpenAPI Generator configuration
├── backend/
│ ├── README.md # Backend-specific setup and ingest guide
│ ├── Dockerfile
│ ├── docker-compose.yaml
│ ├── pyproject.toml
│ ├── requirements.txt
│ ├── requirements-ingest.txt
│ ├── ingest.yaml # Small ingest/smoke configuration
│ ├── ingest.production.yaml # Larger ingest configuration
│ ├── src/openapi_server/
│ │ ├── apis/ # Generated API routers and request handling
│ │ ├── impl/ # Game engine and application logic
│ │ │ ├── api/ # Endpoint implementations
│ │ │ ├── engine/ # Room registry, phases, and events
│ │ │ ├── data/ # Categories and moderation data
│ │ │ ├── scoring.py # Guess and author scoring
│ │ │ ├── persistence.py
│ │ │ ├── realtime.py # WebSocket delivery
│ │ │ └── validation.py # Input validation and safeguards
│ │ ├── models/ # Generated OpenAPI models
│ │ └── main.py # FastAPI bootstrap
│ ├── tests/
│ └── local-media/
└── frontend/
    ├── package.json
    ├── index.html
    ├── public/ # Icons and sound assets
    └── src/
        ├── api.ts
        ├── main.ts
        └── style.css
```

</details>

---

## Notes for hackers

- **Generated code:** parts of the backend come from the OpenAPI spec. Change the contract first, then regenerate (or carefully update) the affected models and routers.
- **Realtime:** WebSocket is preferred, polling is the safety net.
- **`TIME_SCALE`:** handy for local testing. Values below `1` slow phases down while keeping server-controlled timestamps intact.

---

## Contributing

Contributions are very welcome, especially around:

- Gameplay balance and scoring
- Room reliability and reconnects
- Mobile usability and accessibility
- Reveal and voting presentation
- Moderation and abuse prevention
- Test coverage
- Product content quality and licensing

Before opening a PR:

1. Read [`PRD.md`](PRD.md) so you know the intended behavior.
2. Keep the server authoritative.
3. Run the backend tests.
4. Don't expose product secrets earlier than the designed phase.
5. Document any API or environment changes.

---

## License and data

This repo doesn't declare a license yet, so please clarify before redistributing or using it commercially. Product data and images may carry their own licenses too, so confirm every dataset and media asset is fine for your deployment.

## Status

StorageWars is an actively developed prototype. The core multiplayer loop, API contracts, persistence, realtime sync, tests, moderation, and ingestion foundations are all in place. Next up: playtesting, scoring calibration, UI polish, production content licensing, and deployment hardening.

---

**Create a room. Write a card. Make your guesses. Watch the reveal. Vote for the funniest one. Play again.**
