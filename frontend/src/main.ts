import "./style.css";
import {
  api,
  ApiError,
  connectRealtime,
  session,
  type AuthorCard,
  type AuthorSubmission,
  type GameSnapshot,
  type GuessCard,
  type GuessQueue,
  type RevealSlide,
  type RoomState,
} from "./api";

type LobbyPage = "home" | "join" | "lobby";
type UiPhase = 0 | 1 | 2 | 3;
/** Mirrors the API's AuthorCardSubmission: there is no free-text "description". */
type FeatureForm = {
  title: string;
  rating: number;
  category: string;
  reviewBucket: string;
  bullets: string[];
};

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) throw new Error("Missing #app");

const money = (amount: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(amount);

const esc = (value: unknown): string =>
  String(value ?? "").replace(/[&<>"']/g, (char) => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[char];
  });

/** Mirrors the server's category seed data; the API rejects unknown slugs. */
const AUTHOR_CATEGORIES: ReadonlyArray<readonly [string, string]> = [
  ["home-kitchen", "Home & Kitchen"],
  ["electronics", "Electronics"],
  ["beauty", "Beauty & Personal Care"],
  ["sports-outdoors", "Sports & Outdoors"],
  ["toys-games", "Toys & Games"],
  ["clothing", "Clothing & Accessories"],
  ["tools", "Tools & Home Improvement"],
  ["office", "Office Products"],
  ["garden", "Garden & Patio"],
  ["pets", "Pet Supplies"],
  ["automotive", "Automotive"],
  ["food", "Grocery & Gourmet Food"],
];

const REVIEW_BUCKETS: ReadonlyArray<readonly [string, string]> = [
  ["UNDER_10", "Under 10"],
  ["TEN_TO_99", "10 to 99"],
  ["HUNDRED_TO_999", "100 to 999"],
  ["THOUSAND_TO_9999", "1,000 to 9,999"],
  ["TEN_THOUSAND_PLUS", "10,000 or more"],
];

/** Submit this many seconds early so a partial card lands before the server closes AUTHOR. */
const AUTO_SUBMIT_LEAD_SECONDS = 2;

let lobbyPage: LobbyPage = "home";
let phase: UiPhase = 0;
let roomCode = session.roomCode ?? "";

let replayRoomCode = "";
let playerName = "";
let room: RoomState | null = null;
let snapshot: GameSnapshot | null = null;
let authorCard: AuthorCard | null = null;
let guessQueue: GuessQueue | null = null;
let activeGuess: GuessCard | null = null;
let activeCardId: string | null = null;
let guessCents = 10000;
let sliderTouched = false;
let notice = "";
let busy = false;
let pollHandle: ReturnType<typeof setInterval> | undefined;
let socket: WebSocket | undefined;
let reconnectHandle: ReturnType<typeof setTimeout> | undefined;
let reconnectAttempts = 0;
let stateVersion = 0;
/** Identity of the screen currently in the DOM, so background sync knows when it must re-render. */
let lastScreenId = "";
/** A background refresh was skipped because a form control was in use. */
let pendingRender = false;

let submission: FeatureForm = {
  title: "",
  rating: 0,
  category: "",
  reviewBucket: "",
  bullets: ["", "", ""],
};

/** Field-keyed messages from the last rejected submission (`bullets.0`, `title`, …). */
let formErrors: Record<string, string> = {};
/** What was sent, so the submitted panel can show it after the form is gone. */
let submittedForm: FeatureForm | null = null;
let autoSubmitArmed = true;
/** Set once the countdown was seen above the auto-submit lead time. */
let authorWindowObserved = false;

function emptySubmission(): FeatureForm {
  return { title: "", rating: 0, category: "", reviewBucket: "", bullets: ["", "", ""] };
}

let loadedDraftKey: string | null | undefined;

function authorDraftKey(card: AuthorCard): string | null {
  const playerId = session.playerId;
  if (!playerId || !roomCode) return null;
  return `impulsebuy.authorDraft:${encodeURIComponent(roomCode)}:${encodeURIComponent(playerId)}:${encodeURIComponent(card.cardId)}`;
}

function loadAuthorDraft(card: AuthorCard) {
  const key = authorDraftKey(card);
  if (key === loadedDraftKey) return;
  loadedDraftKey = key;
  submission = emptySubmission();
  autoSubmitArmed = true;
  authorWindowObserved = false;
  if (!key) return;

  try {
    const raw = localStorage.getItem(key);
    if (!raw) return;
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null) return;
    const draft = value as Partial<FeatureForm>;
    submission = {
      title: typeof draft.title === "string" ? draft.title : "",
      rating: typeof draft.rating === "number" && Number.isInteger(draft.rating)
        && draft.rating >= 0 && draft.rating <= 5 ? draft.rating : 0,
      category: typeof draft.category === "string" ? draft.category : "",
      reviewBucket: typeof draft.reviewBucket === "string" ? draft.reviewBucket : "",
      bullets: Array.isArray(draft.bullets)
        ? draft.bullets.slice(0, 3).map((bullet) => typeof bullet === "string" ? bullet : "")
        : ["", "", ""],
    };
  } catch {
    // Storage can be unavailable or contain malformed data; keep an empty draft.
  }
}

function persistAuthorDraft() {
  if (!loadedDraftKey) return;
  try {
    localStorage.setItem(loadedDraftKey, JSON.stringify(submission));
  } catch {
    // Keep editing even when browser storage is unavailable.
  }
}

function clearAuthorDraft() {
  if (loadedDraftKey) {
    try {
      localStorage.removeItem(loadedDraftKey);
    } catch {
      // Submission remains successful if browser storage is unavailable.
    }
  }
  loadedDraftKey = undefined;
}

function authorSubmitted(): boolean {
  return submittedForm !== null
    || authorCard?.status === "SUBMITTED"
    || snapshot?.author?.submitted === true;
}

function stopPolling() {
  if (pollHandle) clearInterval(pollHandle);
  pollHandle = undefined;
}

function stopRealtime() {
  if (reconnectHandle) clearTimeout(reconnectHandle);
  reconnectHandle = undefined;
  const current = socket;
  socket = undefined;
  if (current && current.readyState < WebSocket.CLOSING) current.close();
}

function startPolling() {
  stopPolling();
  // Fallback synchronization in case the server closes the WebSocket or
  // a deployment has not configured realtime delivery yet.
  pollHandle = setInterval(() => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      void refreshState(false);
    }
  }, 2000);
}

function websocketUrl(): string | null {
  const roomCode = session.roomCode;
  if (!roomCode) return null;
  const configured = (import.meta as ImportMeta & { env?: Record<string, string | undefined> })
    .env?.VITE_WS_URL;
  let base = configured?.trim();
  if (!base) {
    try {
      const derived = new URL(api.baseUrl, window.location.href);
      derived.protocol = derived.protocol === "https:" ? "wss:" : "ws:";
      base = derived.toString();
    } catch {
      return null;
    }
  }
  // VITE_WS_URL is the API base (for example `wss://api.example.com/v1`); the
  // room path is the same one the server registers.
  return `${base.replace(/\/+$/, "")}/ws/${encodeURIComponent(roomCode.toUpperCase())}`;
}

function scheduleRealtimeReconnect() {
  if (reconnectHandle || !session.token || !session.roomCode) return;
  const delay = Math.min(1000 * (2 ** reconnectAttempts), 15000);
  reconnectAttempts = Math.min(reconnectAttempts + 1, 4);
  reconnectHandle = setTimeout(() => {
    reconnectHandle = undefined;
    void startRealtime();
  }, delay);
}

async function startRealtime() {
  const url = websocketUrl();
  if (!url || !session.token || !session.roomCode) return;
  try {
    const nextSocket = await connectRealtime(
      url,
      (event) => {
        // Event names/payload schemas are not defined in the supplied OpenAPI
        // document. Treat any message as a signal to fetch authoritative state.
        try {
          JSON.parse(event.data);
        } catch {
          // Ignore non-JSON frames; snapshot refresh remains the source of truth.
        }
        void refreshState(false);
      },
      async () => {
        reconnectAttempts = 0;
        stopPolling();
        await refreshState(false);
      },
    );
    if (!session.token) {
      nextSocket.close();
      return;
    }
    socket = nextSocket;
    nextSocket.addEventListener("close", () => {
      if (socket !== nextSocket) return;
      socket = undefined;
      startPolling();
      scheduleRealtimeReconnect();
    });
    nextSocket.addEventListener("error", () => {
      // close event will schedule reconnect; keep a polling fallback meanwhile.
      startPolling();
    });
  } catch {
    startPolling();
    scheduleRealtimeReconnect();
  }
}

function currentPhase(): string {
  return snapshot?.phase ?? room?.phase ?? "LOBBY";
}

function toUiPhase(serverPhase: string): UiPhase {
  switch (serverPhase) {
    case "AUTHOR": return 1;
    case "GUESS": return 2;
    case "REVEAL":
    case "VOTE":
    case "FINAL": return 3;
    default: return 0;
  }
}

function formatTime(deadline?: string | null): string {
  if (!deadline) return "--:--";
  const seconds = Math.max(0, Math.ceil((new Date(deadline).getTime() - Date.now()) / 1000));
  return `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(seconds % 60)
    .toString().padStart(2, "0")}`;
}

/** Tick every server-stamped countdown in the current screen. */
function tickClocks() {
  document.querySelectorAll<HTMLElement>(".timer[data-deadline]").forEach((timer) => {
    timer.textContent = formatTime(timer.dataset.deadline);
  });
  patchDynamic();
  const timer = app!.querySelector<HTMLElement>(".timer[data-deadline]");
  const deadline = timer?.dataset.deadline;
  if (phase !== 1 || !deadline || !autoSubmitArmed || authorSubmitted()) return;
  const remaining = Math.ceil((new Date(deadline).getTime() - Date.now()) / 1000);
  if (remaining > AUTO_SUBMIT_LEAD_SECONDS) {
    authorWindowObserved = true;
    return;
  }
  // Only trust the deadline once a live countdown was seen: a mismatched
  // client/server clock must not burn a draft the moment the form renders.
  if (!authorWindowObserved) return;
  autoSubmitArmed = false;
  void submitAuthorCard(true);
}


function phaseProgress() {
  return `<div class="phase-progress">
    ${[1, 2, 3].map((n) =>
      `<span class="${n === phase ? "active" : n < phase ? "done" : ""}"></span>`
    ).join("")}
  </div>`;
}

function productIllustration() {
  return `<svg viewBox="0 0 240 180" role="img" aria-label="Product image placeholder">
    <rect x="35" y="25" width="170" height="130" fill="var(--panel)" />
    <path d="M65 125L100 85L125 108L150 70L180 125Z" fill="var(--mint)" />
    <circle cx="82" cy="60" r="12" fill="var(--pink)" />
  </svg>`;
}


function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return error.message;
    if (error.status === 401) return "Your session is missing or expired. Return home and rejoin the room.";
    return error.message;
  }
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}

async function runBusy<T>(
  task: () => Promise<T>,
  successMessage = "",
  tolerate: string[] = [],
): Promise<T | undefined> {
  if (busy) return;
  busy = true;
  notice = "";
  render();
  try {
    const result = await task();
    if (successMessage) notice = successMessage;
    return result;
  } catch (error) {
    const code = error instanceof ApiError
      ? String(error.payload?.code ?? error.payload?.error ?? "")
      : "";
    if (!tolerate.includes(code)) notice = errorMessage(error);
    return undefined;
  } finally {
    busy = false;
    render();
  }
}

async function refreshState(showErrors = true) {
  const version = ++stateVersion;
  if (!session.token || !session.roomCode) return;
  try {
    const state = await api.snapshot();
    if (version !== stateVersion) return;
    snapshot = state;
    roomCode = state.roomCode || session.roomCode || "";
    phase = toUiPhase(state.phase);
    if (state.phase === "LOBBY") {
      room = await api.getRoom(roomCode);
    }
    if (state.phase === "AUTHOR") {
      authorCard = await api.getAuthorCard();

      loadAuthorDraft(authorCard);
    } else if (state.phase === "GUESS") {
      guessQueue = await api.getGuessQueue();
      // The server hands out one card at a time: it names the next card in the
      // queue and the player claims it with an explicit open, which stamps the
      // drip schedule and the 20s cap.
      const position = guessQueue.myPosition;
      const target = position?.activeCardId
        ?? (position?.allDone ? null : position?.nextCardId ?? null);
      if (target && target !== activeCardId) {
        const opened = await api.openGuessCard(target);
        activeCardId = target;
        activeGuess = opened;
        guessCents = opened.draftValueCents ?? 10000;
        sliderTouched = opened.sliderTouched;
      } else if (target) {
        activeGuess = await api.getGuessCard(target);
        guessCents = activeGuess.draftValueCents ?? guessCents;
        // A poll can land between the drag and the touch call; the server's
        // stale false must not disarm the lock the player already used.
        sliderTouched = activeGuess.sliderTouched || sliderTouched;
      } else {
        activeGuess = null;
        activeCardId = null;
      }
    }
    if (state.phase === "REVEAL") {
      snapshot.reveal = await api.getReveal();
    } else if (state.phase === "VOTE") {
      snapshot.vote = await api.getVoteOptions();
    } else if (state.phase === "FINAL") {
      snapshot.final = await api.getFinal();
      room = await api.getRoom(roomCode);
    }
    renderIfIdle();
  } catch (error) {
    if (showErrors) {
      notice = errorMessage(error);
      renderIfIdle();
    }
  }
}

function homeScreen() {
  return `<main class="main">
    <section class="lobby-controls" style="max-width:440px;margin:auto;height:100%;justify-content:center">
      <h1 class="screen-title">Bad Retail</h1>
      <p class="screen-subtitle">Create a lobby with your friends or join one that's already open.</p>
      <div class="field">
        <label for="username">USERNAME</label>
        <input id="username" maxlength="20" placeholder="Enter your name" value="${esc(playerName)}" />
      </div>
      <div class="button-row">
        <button class="btn-primary" data-action="create" ${busy ? "disabled" : ""}>Create lobby</button>
        <button data-action="go-join">Join lobby</button>
      </div>
      <p class="notice" role="status">${esc(notice)}</p>
    </section>
  </main>`;
}

function joinScreen() {
  return `<main class="main">
    <section class="lobby-controls" style="max-width:440px;margin:auto;height:100%;justify-content:center">
      <p class="section-label">Join</p>
      <h1 class="screen-title">Join a lobby</h1>
      <p class="screen-subtitle">Enter your username and the room code shared by the host.</p>
      <div class="field">
        <label for="username">USERNAME</label>
        <input id="username" maxlength="20" placeholder="Enter your name" value="${esc(playerName)}" />
      </div>
      <div class="field">
        <label for="join-code">LOBBY CODE</label>
        <input id="join-code" maxlength="6" placeholder="e.g. FUN826" value="${esc(roomCode)}" />
      </div>
      <div class="button-row">
        <button data-action="back-home">Back</button>
        <button class="btn-primary" data-action="join" ${busy ? "disabled" : ""}>Join lobby</button>
      </div>
      <p class="notice" role="status">${esc(notice)}</p>
    </section>
  </main>`;
}

function playerList() {
  const players = room?.players ?? [];
  return `<div class="player-list">${players.map((player, index) => `
    <div class="player">
      <span class="player-index">${String(index + 1).padStart(2, "0")}</span>
      <span class="player-name">${esc(player.name)}</span>
      ${player.isCreator ? `<span class="host-label">HOST</span>` : ""}
    </div>`).join("")}</div>`;
}

function lobbyScreen() {
  const players = room?.players ?? [];
  const isCreator = room?.isCreator ?? false;
  const canStart = room?.canStart ?? false;
  return `<main class="main">
    <div class="lobby-layout">
      <section class="lobby-controls">
        <p class="section-label">Lobby</p>
        <h1 class="screen-title">Waiting for players</h1>
        <p class="screen-subtitle">Share the room code. The host can start when the server says the room is ready.</p>
        <div class="lobby-code"><div><div class="detail-label">LOBBY CODE</div><strong>${esc(roomCode)}</strong></div>
          <button data-action="copy">Copy code</button>
        </div>
        <p class="notice" role="status">${esc(notice)}</p>
        <div class="button-row">
          <button data-action="back-home">Leave lobby</button>
          ${isCreator ? `<button class="btn-primary" data-action="start" ${!canStart || busy ? "disabled" : ""}>Start game</button>` : ""}
        </div>
      </section>
      <section class="lobby-players">
        <p class="section-label">Players</p>
        ${playerList()}
        <p class="player-count">${players.length} / 8 players</p>
        ${!canStart && isCreator ? `<p class="small muted">The server will enable starting when enough players have joined.</p>` : ""}
      </section>
    </div>
  </main>`;
}

function fieldError(field: string): string {
  const message = formErrors[field];
  return message ? `<p class="field-error">${esc(message)}</p>` : "";
}

function submittedPanel() {
  const form = submittedForm ?? submission;
  const progress = snapshot?.author?.progress as
    | { submitted?: number; total?: number }
    | undefined;
  const progressText = progress?.total
    ? `${progress.submitted ?? 0} of ${progress.total} cards submitted.`
    : "Waiting for the other players.";
  const category = AUTHOR_CATEGORIES.find(([slug]) => slug === form.category)?.[1] ?? form.category;
  const bucket = REVIEW_BUCKETS.find(([key]) => key === form.reviewBucket)?.[1] ?? form.reviewBucket;
  const rows = [
    form.title ? `<div class="detail-line"><div class="detail-label">TITLE</div><div class="detail-value">${esc(form.title)}</div></div>` : "",
    category ? `<div class="detail-line"><div class="detail-label">CATEGORY</div><div class="detail-value">${esc(category)}</div></div>` : "",
    ...form.bullets.filter(Boolean).map((bullet) => `<div class="detail-line"><div class="detail-value">${esc(bullet)}</div></div>`),
    form.rating ? `<div class="detail-line"><div class="detail-label">RATING</div><div class="detail-value">${esc(form.rating)} / 5</div></div>` : "",
    bucket ? `<div class="detail-line"><div class="detail-label">REVIEWS</div><div class="detail-value">${esc(bucket)}</div></div>` : "",
  ].join("");
  return `<section class="submitted-panel">
    <p class="section-label">Submitted</p>
    <p class="submitted-headline">Your card is in.</p>
    <p class="small muted">${esc(progressText)} The guess phase starts when everyone is done or the timer runs out.</p>
    ${rows}
  </section>`;
}

function authorScreen() {
  const card = authorCard;
  const constraints = card?.constraints ?? {};
  const titleMin = constraints.titleMinChars ?? 8;
  const titleMax = constraints.titleMaxChars ?? 60;
  const bulletMin = constraints.bulletMinChars ?? 15;
  const bulletMax = constraints.bulletMaxChars ?? 80;
  const maxBullets = Math.min(3, constraints.bulletSlots ?? 3);
  const bullets = Array.from({ length: maxBullets }, (_, i) => submission.bullets[i] ?? "");
  const submitted = authorSubmitted();
  const options = (entries: ReadonlyArray<readonly [string, string]>, selected: string, placeholder: string) =>
    [`<option value="">${esc(placeholder)}</option>`]
      .concat(entries.map(([value, label]) =>
        `<option value="${esc(value)}" ${value === selected ? "selected" : ""}>${esc(label)}</option>`))
      .join("");
  return `<main class="main">
    ${phaseProgress()}
    <div class="phase-heading"><div>
      <p class="section-label">Phase 1</p>
      <h1 class="screen-title">Describe the product</h1>
      <p class="screen-subtitle">Use the assigned image. Do not reveal the original product name or price.</p>
    </div><div class="timer" data-deadline="${esc(card?.deadlineAt ?? "")}">${formatTime(card?.deadlineAt)}</div></div>
    <div class="describe-layout">
      <section class="product-panel">
        <div class="product-image">${card?.imageUrl
          ? `<img src="${esc(card.imageUrl)}" alt="Assigned product" style="max-width:100%;max-height:260px;object-fit:contain" />`
          : productIllustration()}</div>
        <p class="section-label" style="margin-top:14px">Price band</p>
        <div class="actual-price">${card ? `Band ${card.priceBand}` : "Loading…"}</div>
        <p class="product-note">The actual price is hidden from other players.</p>
      </section>
      ${submitted ? submittedPanel() : `<form class="description-form" id="description-form">
        ${notice ? `<p class="form-status ${formErrors && Object.keys(formErrors).length ? "error" : "info"}" role="status">${esc(notice)}</p>` : ""}
        <div class="field"><label for="title">TITLE</label>
          <input id="title" minlength="${titleMin}" maxlength="${titleMax}" required value="${esc(submission.title)}" placeholder="${titleMin}–${titleMax} characters" />
          <p class="field-hint">${titleMin}–${titleMax} characters, no digits or price words.</p>
          ${fieldError("title")}</div>
        <div class="field-row">
          <div class="field"><label for="category">CATEGORY</label>
            <select id="category">${options(AUTHOR_CATEGORIES, submission.category, "Choose a category")}</select>
            ${fieldError("category")}</div>
          <div class="field"><label for="reviews">REVIEW COUNT</label>
            <select id="reviews">${options(REVIEW_BUCKETS, submission.reviewBucket, "Choose a range")}</select>
            ${fieldError("reviewBucket")}</div>
        </div>
        <div class="field"><label>STAR RATING</label><div class="rating">
          ${[1, 2, 3, 4, 5].map((n) => `<button type="button" data-action="rating" data-value="${n}" class="${n <= submission.rating ? "selected" : ""}" aria-label="${n} stars">★</button>`).join("")}
        </div>${fieldError("starRating")}</div>
        <div class="field"><label>FEATURE BULLETS</label><div class="features">
          ${bullets.map((value, index) => `<div class="feature-row"><input data-feature="${index}" minlength="${bulletMin}" maxlength="${bulletMax}" placeholder="Feature ${index + 1} (${bulletMin}–${bulletMax} characters)" value="${esc(value)}" />${fieldError(`bullets.${index}`)}</div>`).join("")}
        </div>
        <p class="field-hint">Every field is optional; whatever you fill in is stored.</p></div>
        <div class="form-bottom"><span class="small muted">Your card is shown to other players.</span>
          <button class="btn-primary" type="submit" ${busy ? "disabled" : ""}>Submit description</button></div>
      </form>`}
    </div>
  </main>`;
}

function guessScreen() {
  const card = activeGuess;
  const fields = [
    card?.title ? `<div class="detail-line"><div class="detail-label">TITLE</div><div class="detail-value">${esc(card.title)}</div></div>` : "",
    card?.category ? `<div class="detail-line"><div class="detail-label">CATEGORY</div><div class="detail-value">${esc(card.category)}</div></div>` : "",
    ...(card?.bullets ?? []).filter((v): v is string => Boolean(v)).map((v) => `<div class="detail-line"><div class="detail-value">${esc(v)}</div></div>`),
    card?.starRating != null ? `<div class="detail-line"><div class="detail-label">RATING</div><div class="detail-value">${esc(card.starRating)} / 5</div></div>` : "",
    card?.reviewBucket ? `<div class="detail-line"><div class="detail-label">REVIEWS</div><div class="detail-value">${esc(card.reviewBucket.replaceAll("_", " ").toLowerCase())}</div></div>` : "",
  ].join("");
  const locked = card?.status === "LOCKED" || card?.status === "TIMED_OUT";
  const valueDollars = guessCents / 100;
  const waiting = guessQueue?.myPosition?.allDone
    ? "All your cards are locked. Waiting for the other players to finish."
    : "Securing your next card…";
  return `<main class="main">
    ${phaseProgress()}
    <div class="phase-heading"><div><p class="section-label">Phase 2</p><h1 class="screen-title">Guess the price</h1>
      <p class="screen-subtitle">Product details appear over time. Lock stays disabled until you move the slider and the card's minimum dwell has passed.</p>
    </div><div class="timer" data-deadline="${esc(card?.capAt ?? "")}">${formatTime(card?.capAt)}</div></div>
    <section class="guess-card">
      <div class="guess-card-head"><h3>${activeCardId ? `Product ${esc(activeCardId.slice(0, 8))}` : guessQueue?.myPosition?.allDone ? "All cards locked" : "Loading card…"}</h3>
        <span class="small muted">${card ? `Multiplier ${card.multiplierNow}×` : "Waiting for your card"}</span></div>
      ${fields || `<p class="empty">${card ? "More details will appear as the reveal timer advances." : esc(waiting)}</p>`}
      <div class="guess-price">
        <label for="guess-slider">YOUR PRICE GUESS ($${money(1).slice(1)} – ${money(1000)})</label>
        <input id="guess-slider" type="range" min="100" max="100000" step="1" value="${guessCents}" ${locked || busy ? "disabled" : ""} />
        <div class="detail-value" data-patch="guess-value">${money(valueDollars)}</div>
        <button type="button" data-action="lock-guess" ${!lockReady(card) || busy ? "disabled" : ""}>Lock guess</button>
        <p class="lock-hint" data-patch="lock-hint">${esc(lockHint(card))}</p>
      </div>
    </section>
    <p class="small muted" data-patch="cards-progress">Cards completed: ${guessQueue?.progress.myLocked ?? 0} / ${guessQueue?.progress.myTotal ?? 0}</p>
    <p class="notice" role="status">${esc(notice)}</p>
  </main>`;
}

/** Dot-plot palette; matches the theme's series colours. */
const SERIES_COLORS = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c5)", "var(--c6)"];

/**
 * Log-scaled dot plot of every guess against the real price. Prices are spread
 * over three orders of magnitude, so a linear axis would stack every cheap guess.
 */
function priceAxis(card: RevealSlide["card"]): string {
  const min = Math.max(1, card.axisMinCents || 100);
  const max = Math.max(min * 10, card.axisMaxCents || 100000);
  const price = Math.min(max, Math.max(min, card.original?.priceCents ?? min));
  const width = 760;
  const height = 148;
  const pad = 16;
  const axisY = 104;
  const span = Math.log(max / min);
  const scale = (cents: number) =>
    pad + (Math.log(Math.min(max, Math.max(min, cents)) / min) / span) * (width - 2 * pad);
  const ticks = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000]
    .filter((tick) => tick >= min && tick <= max);
  const tickMarks = ticks
    .map((tick) => {
      const x = scale(tick);
      return `<line x1="${x.toFixed(1)}" y1="${axisY}" x2="${x.toFixed(1)}" y2="${axisY + 5}" stroke="var(--border)" />`
        + `<text x="${x.toFixed(1)}" y="${axisY + 22}" text-anchor="middle" font-size="11" fill="var(--muted)">${money(tick / 100)}</text>`;
    })
    .join("");
  const dots = card.guesses
    .map((guess, index) => {
      const x = scale(guess.valueCents).toFixed(1);
      const y = axisY - 18 - (index % 3) * 18;
      const color = SERIES_COLORS[index % SERIES_COLORS.length];
      const marker = guess.timedOut
        ? `<circle cx="${x}" cy="${y}" r="6" fill="var(--panel)" stroke="${color}" stroke-width="2" stroke-dasharray="3 2" />`
        : `<circle cx="${x}" cy="${y}" r="6" fill="${color}" />`;
      return `<line x1="${x}" y1="${y}" x2="${x}" y2="${axisY}" stroke="${color}" opacity="0.4" />${marker}`;
    })
    .join("");
  const priceX = scale(price).toFixed(1);
  return `<svg class="price-axis" viewBox="0 0 ${width} ${height}" role="img"
    aria-label="Guesses plotted against the real price of ${money(price / 100)}">
    <line x1="${pad}" y1="${axisY}" x2="${width - pad}" y2="${axisY}" stroke="var(--border)" stroke-width="2" />
    ${tickMarks}
    <line x1="${priceX}" y1="26" x2="${priceX}" y2="${axisY + 8}" stroke="var(--success)" stroke-width="2" stroke-dasharray="5 4" />
    <text x="${priceX}" y="18" text-anchor="middle" font-size="12" font-weight="700" fill="var(--success)">Real ${money(price / 100)}</text>
    ${dots}
  </svg>`;
}

function revealScreen(): string {
  const slide = snapshot?.reveal;
  const heading = (subtitle: string) => `${phaseProgress()}
    <div class="phase-heading"><div><p class="section-label">Phase 3</p><h1 class="screen-title">Reveal</h1>
    <p class="screen-subtitle">${esc(subtitle)}</p></div>
    <div class="timer" data-deadline="${esc(slide?.autoAdvanceAt ?? "")}">${formatTime(slide?.autoAdvanceAt)}</div></div>`;

  if (!slide?.card) {
    return `<main class="main">${heading("Loading the first card…")}
      <p class="notice" role="status">${esc(notice)}</p></main>`;
  }

  const card = slide.card;
  const authored = card.authored ?? {};
  const original = card.original ?? {};
  const category = AUTHOR_CATEGORIES.find(([slug]) => slug === authored.category)?.[1] ?? authored.category ?? "";
  const bucket = REVIEW_BUCKETS.find(([key]) => key === authored.reviewBucket)?.[1] ?? "";
  const bullets = (authored.bullets ?? []).filter((bullet): bullet is string => Boolean(bullet));
  const guessRows = card.guesses
    .map((guess, index) => `<div class="reveal-guess">
      <span class="reveal-swatch" style="background:${SERIES_COLORS[index % SERIES_COLORS.length]}"></span>
      <span class="reveal-guess-name">${esc(guess.playerName)}</span>
      <strong>${money(guess.valueCents / 100)}</strong>
      <span class="small muted">${guess.timedOut
        ? "auto-locked at the cap"
        : `${(guess.cardSeconds ?? 0).toFixed(1)}s on the card`}</span>
    </div>`)
    .join("");

  const controls = slide.canAdvance
    ? `<div class="button-row"><button class="btn-primary" data-action="advance-reveal" ${busy ? "disabled" : ""}>
        ${slide.slideIndex + 1 >= slide.slideCount ? "Start the vote" : "Next card"}</button></div>`
    : `<p class="small muted">The host moves the carousel on, or it advances by itself.</p>`;

  return `<main class="main">${heading(`Card ${slide.slideIndex + 1} of ${slide.slideCount}, authored by ${card.authorName}. Guesses are in.`)}
    <div class="reveal-layout">
      <section class="guess-card">
        <div class="guess-card-head"><h3>What ${esc(card.authorName)} wrote</h3>
          <span class="small muted">Category: ${esc(category) || "—"}</span></div>
        ${authored.title ? `<div class="detail-line"><div class="detail-label">TITLE</div><div class="detail-value">${esc(authored.title)}</div></div>` : ""}
        ${bullets.map((bullet) => `<div class="detail-line"><div class="detail-value">${esc(bullet)}</div></div>`).join("")}
        ${authored.starRating ? `<div class="detail-line"><div class="detail-label">RATING</div><div class="detail-value">${esc(authored.starRating)} / 5</div></div>` : ""}
        ${bucket ? `<div class="detail-line"><div class="detail-label">REVIEWS</div><div class="detail-value">${esc(bucket)}</div></div>` : ""}
        <p class="detail-label" style="margin-top:16px">GUESSES</p>
        ${priceAxis(card)}
        ${guessRows || `<p class="empty">Nobody locked a guess in time.</p>`}
      </section>
      <section class="guess-card">
        <p class="detail-label">THE ACTUAL PRODUCT</p>
        ${original.imageUrl
          ? `<img class="reveal-photo" src="${esc(original.imageUrl)}" alt="The real product" />`
          : productIllustration()}
        <div class="reveal-price">${money((original.priceCents ?? 0) / 100)}</div>
        <div class="detail-line"><div class="detail-label">REAL TITLE</div><div class="detail-value">${esc(original.title ?? "—")}</div></div>
        ${original.description ? `<p class="small muted">${esc(original.description)}</p>` : ""}
      </section>
    </div>
    <p class="notice" role="status">${esc(notice)}</p>
    ${controls}
  </main>`;
}

function voteScreen(): string {
  const data = snapshot?.vote;
  const options = data?.options ?? [];
  const voted = data?.myVoteCast === true;
  const controls = options
    .map((option) => `<button class="vote-option" data-action="vote" data-card-id="${esc(option.cardId)}" ${busy || voted ? "disabled" : ""}>
      <strong>${esc(option.title ?? "Untitled card")}</strong>
      <span class="small muted">${esc(option.authorName ?? "Someone")} · ${esc(option.category ?? "")}</span>
    </button>`)
    .join("");
  return `<main class="main">${phaseProgress()}
    <div class="phase-heading"><div><p class="section-label">Phase 3</p><h1 class="screen-title">Vote for the funniest card</h1>
      <p class="screen-subtitle">${data?.myVoteCast
        ? "Your vote is in. The scores open when the vote closes."
        : "Pick the card that made you laugh. You cannot vote for your own."}</p></div>
      <div class="timer" data-deadline="${esc(data?.deadlineAt ?? "")}">${formatTime(data?.deadlineAt)}</div></div>
    <section class="guess-card">${controls || `<p class="empty">No cards to vote on.</p>`}</section>
    <p class="notice" role="status">${esc(notice)}</p>
  </main>`;
}

function finalScreen() {
  const result = snapshot?.final;
  const rankings = Array.isArray(result?.rankings) ? result.rankings : [];
  const winner = result?.winnerPlayerId
    ? rankings.find((ranking) => ranking.playerId === result.winnerPlayerId)
    : undefined;
  const tied = !winner && rankings.length > 1
    && rankings[0].totalPoints === rankings[1].totalPoints;
  const outcome = !result
    ? "Final standings are loading."
    : result.endedReason === "TOO_FEW_PLAYERS"
      ? "The game ended early. Scores include completed cards."
      : winner
        ? `${winner.name} wins the game.`
        : tied
          ? `The game ended in a tie at ${rankings[0].totalPoints.toLocaleString()} points.`
          : rankings.length
            ? "No single winner this round."
            : "No scored cards this game.";
  const controls = room?.isCreator
    ? `<div class="final-actions">
        <button class="btn-primary" data-action="replay" ${busy ? "disabled" : ""}>Play again</button>
        <p class="small muted">Share the new lobby code so players can claim their seats.</p>
        <button class="btn-neutral" data-action="back-home">Leave game</button>
      </div>`
    : `<div class="final-actions">
        <form class="final-replay-form" id="replay-join-form">
          <div class="field"><label for="replay-room-code">ROOM CODE FROM HOST</label>
            <input id="replay-room-code" maxlength="4" minlength="4" pattern="[A-Za-z0-9]{4}" required value="${esc(replayRoomCode)}" placeholder="AB12" /></div>
          <button class="btn-primary" type="submit" ${busy ? "disabled" : ""}>Join replay</button>
        </form>
        <p class="small muted">Enter the new code shared by the host to claim your seat.</p>
        <button class="btn-neutral" data-action="back-home">Leave game</button>
      </div>`;
  const rows = rankings.map((ranking) => `<article class="final-ranking">
    <div class="final-rank">#${esc(ranking.rank)}</div>
    <div class="final-player"><strong>${esc(ranking.name)}</strong>
      ${ranking.playerId === result?.winnerPlayerId ? `<span class="final-winner-badge">WINNER</span>` : ""}
    </div>
    <div class="final-total"><strong>${esc(ranking.totalPoints.toLocaleString())}</strong><span>POINTS</span></div>
    <div class="final-breakdown">
      <span>Guessing <strong>${esc(ranking.breakdown.guesserPoints.toLocaleString())}</strong></span>
      <span>Authoring <strong>${esc(ranking.breakdown.authorPoints.toLocaleString())}</strong></span>
      <span>Funniest <strong>${esc(ranking.breakdown.funniestBonus.toLocaleString())}</strong></span>
    </div>
  </article>`).join("");
  return `<main class="main final-screen">
    ${phaseProgress()}
    <div class="final-heading">
      <div><p class="section-label">Final</p><h1 class="screen-title">Final results</h1>
        <p class="screen-subtitle">${esc(outcome)}</p></div>
      ${controls}
    </div>
    <section class="final-rankings" aria-label="Final standings">
      ${rows || `<p class="empty">${result ? "No final standings are available." : "Loading final standings…"}</p>`}
    </section>
    <p class="notice" role="status">${esc(notice)}</p>
  </main>`;
}

/** Identity of the screen a render would produce; a change always forces a re-render. */
function screenId(): string {
  if (phase === 0) return `lobby:${lobbyPage}`;
  if (phase === 1) return `author:${authorSubmitted() ? "submitted" : "form"}`;
  if (phase === 2) return "guess";
  return `phase:${currentPhase()}`;
}

/** A pointer press is in flight: swapping the tree now would swallow the click. */
let pointerPressed = false;

/**
 * True while the user is using a control whose DOM node must survive a refresh.
 * Replacing the tree would drop focus, close a native dropdown, abandon a
 * half-typed field or swallow a click, so background sync steps aside until the
 * control is released.
 */
function heldControl(): boolean {
  if (pointerPressed) return true;
  const active = document.activeElement;
  if (active instanceof HTMLTextAreaElement || active instanceof HTMLSelectElement) return true;
  return active instanceof HTMLInputElement && active.type !== "range";
}

/** Server-stamped moment the lock button becomes usable for this card. */
function lockEligibleAt(card: GuessCard | null): number {
  const raw = card?.lockEligibleAt ? new Date(card.lockEligibleAt).getTime() : Number.NaN;
  return Number.isFinite(raw) ? raw : 0;
}

/** Lock needs an open card, a touched slider and the minimum dwell to have passed. */
function lockReady(card: GuessCard | null): boolean {
  return Boolean(card && card.status === "IN_PROGRESS" && sliderTouched && Date.now() >= lockEligibleAt(card));
}

/** Spell out why the lock button is unavailable instead of leaving it grey. */
function lockHint(card: GuessCard | null): string {
  if (!card || card.status !== "IN_PROGRESS") return "This card is closed.";
  if (!sliderTouched) return "Move the slider to arm the lock.";
  const remaining = Math.ceil((lockEligibleAt(card) - Date.now()) / 1000);
  if (remaining > 0) return `Lock opens in ${remaining}s — every card has a minimum dwell.`;
  return "Lock commits this price permanently.";
}

/** Update the live values that must keep ticking while a full render is deferred. */
function patchDynamic(): void {
  document.querySelectorAll<HTMLElement>(".timer[data-deadline]").forEach((timer) => {
    timer.textContent = formatTime(timer.dataset.deadline);
  });
  const noticeNode = app!.querySelector<HTMLElement>(".notice[role=status]");
  if (noticeNode) noticeNode.textContent = notice;
  const banner = app!.querySelector<HTMLElement>(".form-status");
  if (banner) {
    banner.textContent = notice;
    banner.className = `form-status ${Object.keys(formErrors).length ? "error" : "info"}`;
  }
  const valueNode = app!.querySelector<HTMLElement>('[data-patch="guess-value"]');
  if (valueNode) valueNode.textContent = money(guessCents / 100);
  const counters = app!.querySelector<HTMLElement>('[data-patch="cards-progress"]');
  if (counters) {
    counters.textContent = `Cards completed: ${guessQueue?.progress.myLocked ?? 0} / ${guessQueue?.progress.myTotal ?? 0}`;
  }
  const lockButton = app!.querySelector<HTMLButtonElement>('[data-action="lock-guess"]');
  if (lockButton) lockButton.disabled = !lockReady(activeGuess) || busy;
  const hint = app!.querySelector<HTMLElement>('[data-patch="lock-hint"]');
  if (hint) hint.textContent = lockHint(activeGuess);
}

function render(): void {
  const screen = phase === 0
    ? lobbyPage === "home" ? homeScreen() : lobbyPage === "join" ? joinScreen() : lobbyScreen()
    : phase === 1 ? authorScreen()
    : phase === 2 ? guessScreen()
    : currentPhase() === "VOTE" ? voteScreen()
    : currentPhase() === "FINAL" ? finalScreen()
    : revealScreen();

  const sliderFocused = document.activeElement instanceof HTMLInputElement
    && document.activeElement.id === "guess-slider";
  const scrollY = window.scrollY;
  lastScreenId = screenId();
  pendingRender = false;
  app!.innerHTML = `<div class="game">${screen}</div>`;
  if (window.scrollY !== scrollY) window.scrollTo({ top: scrollY });
  if (sliderFocused) {
    app!.querySelector<HTMLInputElement>("#guess-slider")?.focus({ preventScroll: true });
  }
}

/**
 * Renderer for server-driven sync: never yanks the DOM out from under the
 * control the player is using, and catches up as soon as they let go.
 */
function renderIfIdle(): void {
  if (screenId() === lastScreenId && heldControl()) {
    pendingRender = true;
    patchDynamic();
    return;
  }
  render();
}

/** Read the rendered author form. Returns null when the form is not shown. */
function authorFormFromDom(): FeatureForm | null {
  const title = document.querySelector<HTMLInputElement>("#title");
  if (!title) return null;
  const category = document.querySelector<HTMLSelectElement>("#category");
  const reviews = document.querySelector<HTMLSelectElement>("#reviews");
  return {
    title: title.value.trim(),
    rating: submission.rating,
    category: category?.value ?? "",
    reviewBucket: reviews?.value ?? "",
    bullets: Array.from(document.querySelectorAll<HTMLInputElement>("[data-feature]"))
      .map((input) => input.value.trim()),
  };
}

/** Client mirror of the server's length rules, so feedback does not need a round trip. */
function authorLengthErrors(form: FeatureForm): Record<string, string> {
  const constraints = authorCard?.constraints ?? {};
  const titleMin = constraints.titleMinChars ?? 8;
  const titleMax = constraints.titleMaxChars ?? 60;
  const bulletMin = constraints.bulletMinChars ?? 15;
  const bulletMax = constraints.bulletMaxChars ?? 80;
  const errors: Record<string, string> = {};
  if (form.title && form.title.length < titleMin) {
    errors.title = `Title must be at least ${titleMin} characters.`;
  } else if (form.title.length > titleMax) {
    errors.title = `Title must be at most ${titleMax} characters.`;
  }
  form.bullets.forEach((bullet, index) => {
    if (bullet && bullet.length < bulletMin) {
      errors[`bullets.${index}`] = `Bullet must be at least ${bulletMin} characters.`;
    } else if (bullet.length > bulletMax) {
      errors[`bullets.${index}`] = `Bullet must be at most ${bulletMax} characters.`;
    }
  });
  return errors;
}

async function submitAuthorCard(auto: boolean): Promise<boolean> {
  if (busy || authorSubmitted()) return false;
  const form = authorFormFromDom();
  if (!form) return false;
  submission = form;
  const localErrors = authorLengthErrors(form);
  if (Object.keys(localErrors).length) {
    formErrors = localErrors;
    notice = auto ? "Time is up, but these fields were not saved." : "Fix the highlighted fields.";
    render();
    return false;
  }
  const hasContent = Boolean(
    form.title || form.rating || form.category || form.reviewBucket
      || form.bullets.some((bullet) => bullet),
  );
  if (!hasContent) {
    if (auto) return false;
    notice = "Fill in at least one field before submitting.";
    render();
    return false;
  }

  const body: AuthorSubmission = {};
  if (form.title) body.title = form.title;
  const bullets = form.bullets.filter(Boolean);
  if (bullets.length) body.bullets = bullets;
  if (form.rating) body.starRating = form.rating;
  if (form.category) body.category = form.category;
  if (form.reviewBucket) body.reviewBucket = form.reviewBucket as AuthorSubmission["reviewBucket"];

  const result = await runBusy(async () => {
    try {
      return await api.submitAuthorCard(body);
    } catch (error) {
      if (error instanceof ApiError && error.payload?.fieldErrors) {
        formErrors = Object.fromEntries(
          error.payload.fieldErrors.map((item) => [item.field, item.message]),
        );
      }
      throw error;
    }
  }, auto ? "Time is up — your card was submitted automatically." : "Description submitted.");
  if (!result) return false;

  submittedForm = form;
  formErrors = {};
  autoSubmitArmed = false;
  clearAuthorDraft();
  await refreshState();
  return true;
}

async function enterLobby(code: string) {
  stopPolling();
  stopRealtime();
  stateVersion++;
  roomCode = code;
  phase = 0;
  room = null;
  snapshot = null;
  replayRoomCode = "";
  lobbyPage = "lobby";
  await refreshState();
  await startRealtime();
  startPolling();
}

async function createRoom() {
  const input = document.querySelector<HTMLInputElement>("#username");
  playerName = input?.value.trim() ?? "";
  if (!playerName) { notice = "Enter a username first."; render(); return; }
  const joined = await runBusy(() => api.createRoom(playerName));
  if (!joined) return;
  await enterLobby(joined.roomCode);
}

async function joinRoom() {
  playerName = document.querySelector<HTMLInputElement>("#username")?.value.trim() ?? "";
  const code = document.querySelector<HTMLInputElement>("#join-code")?.value.trim().toUpperCase() ?? "";
  if (!playerName) { notice = "Enter a username first."; render(); return; }
  if (!code) { notice = "Enter a room code."; render(); return; }
  const joined = await runBusy(() => api.joinRoom(code, playerName));
  if (!joined) return;
  await enterLobby(joined.roomCode);
}

async function startGame() {
  if (!room?.canStart || !room.isCreator) return;
  const started = await runBusy(() => api.startGame(roomCode));
  if (!started) return;
  await refreshState();
}

app.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  if (form.id === "replay-join-form") {
    event.preventDefault();
    const code = document.querySelector<HTMLInputElement>("#replay-room-code")?.value.trim().toUpperCase() ?? "";
    const token = session.token;
    if (!code || !token) {
      notice = !code ? "Enter the room code shared by the host." : "Your session has expired. Return home and rejoin.";
      render();
      return;
    }
    const joined = await runBusy(() => api.rejoinRoom(code, token));
    if (joined) await enterLobby(joined.roomCode);
    return;
  }
  if (form.id !== "description-form") return;
  event.preventDefault();
  formErrors = {};
  await submitAuthorCard(false);
});

app.addEventListener("input", (event) => {
  if (!(event.target instanceof HTMLInputElement
    || event.target instanceof HTMLTextAreaElement
    || event.target instanceof HTMLSelectElement)) return;
  if (event.target.id === "username") playerName = event.target.value;
  if (event.target.id === "replay-room-code") replayRoomCode = event.target.value;
  if (event.target.dataset.feature !== undefined) {
    submission.bullets[Number(event.target.dataset.feature)] = event.target.value;
  }
  if (phase === 1) {
    if (event.target.id === "title") submission.title = event.target.value;
    else if (event.target.id === "category") submission.category = event.target.value;
    else if (event.target.id === "reviews") submission.reviewBucket = event.target.value;
    if (event.target.id === "title" || event.target.id === "category"
      || event.target.id === "reviews" || event.target.dataset.feature !== undefined) {
      persistAuthorDraft();
    }
  }
  if (event.target.id === "guess-slider") {
    guessCents = Number(event.target.value);
    sliderTouched = true;
    // Patch in place: replacing the input mid-drag would end the drag.
    patchDynamic();
    return;
  }
});

app.addEventListener("change", async (event) => {
  if (!(event.target instanceof HTMLInputElement) || event.target.id !== "guess-slider") return;
  if (!activeCardId) return;
  const echo = await runBusy(async () => {
    await api.touchGuessSlider(activeCardId!);
    return api.saveGuessDraft(activeCardId!, guessCents);
  });
  if (echo) {
    // The draft endpoint echoes the clamped value only; the card view stays authoritative.
    sliderTouched = true;
    guessCents = echo.valueCents ?? guessCents;
    patchDynamic();
  }
});

app.addEventListener("click", async (event) => {
  if (!(event.target instanceof Element)) return;
  const button = event.target.closest<HTMLButtonElement>("[data-action]");
  if (!button || button.disabled) return;

  switch (button.dataset.action) {
    case "create":
      await createRoom();
      break;
    case "go-join":
      notice = "";
      lobbyPage = "join";
      render();
      break;
    case "join":
      await joinRoom();
      break;
    case "back-home":
      stopPolling();
      stopRealtime();
      stateVersion++;
      session.clear();
      room = null;
      snapshot = null;
      authorCard = null;
      guessQueue = null;
      activeGuess = null;
      activeCardId = null;
      phase = 0;
      lobbyPage = "home";
      notice = "";
      render();
      break;
    case "copy":
      try {
        await navigator.clipboard.writeText(roomCode);
        notice = "Room code copied.";
      } catch {
        notice = `Room code: ${roomCode}`;
      }
      render();
      break;
    case "start":
      await startGame();
      break;
    case "rating":
      submission.rating = Number(button.dataset.value);
      persistAuthorDraft();
      render();
      break;
    case "lock-guess": {
      if (!activeCardId || !sliderTouched) break;
      // A cap timer can auto-lock the card while the click is in flight; that
      // rejection means the outcome the player wanted is already in place.
      await runBusy(
        () => api.lockGuess(activeCardId!, guessCents),
        "",
        ["ALREADY_LOCKED", "WRONG_PHASE", "NOT_NEXT_CARD"],
      );
      await refreshState();
      break;
    }
    case "advance-reveal": {
      const advanced = await runBusy(() => api.advanceReveal());
      if (advanced) await refreshState();
      break;
    }
    case "vote": {
      const cardId = button.dataset.cardId;
      if (!cardId) break;
      const result = await runBusy(() => api.vote(cardId), "Vote submitted.");
      if (result) await refreshState();
      break;
    }
    case "replay": {
      const token = session.token;
      if (!token) {
        notice = "Your session has expired. Return home and rejoin.";
        render();
        break;
      }
      const result = await runBusy(() => api.replayRoom(roomCode));
      if (result) {
        replayRoomCode = result.newRoomCode;
        const joined = await runBusy(() => api.rejoinRoom(result.newRoomCode, token));
        if (joined) await enterLobby(joined.roomCode);
      }
      break;
    }
  }
});

app.addEventListener("pointerdown", () => {
  pointerPressed = true;
});

// Release can land outside the app (or leave the window entirely); those cases
// must still clear the hold, otherwise background sync would stay paused.
const releasePointer = () => {
  if (!pointerPressed) return;
  pointerPressed = false;
  if (pendingRender) render();
};

window.addEventListener("pointerup", releasePointer);
window.addEventListener("pointercancel", releasePointer);
window.addEventListener("blur", releasePointer);

// A refresh deferred while a field was in use lands as soon as focus moves on.
app.addEventListener("focusout", () => {
  if (!pendingRender) return;
  // Tabbing between fields fires focusout before the next control takes focus;
  // rendering here would rebuild the tree and bounce the caret back to the top.
  window.setTimeout(() => {
    if (pendingRender && !heldControl()) render();
  }, 0);
});

window.setInterval(tickClocks, 1000);

async function bootstrap() {
  render();
  if (!session.token || !session.roomCode) return;
  roomCode = session.roomCode;
  lobbyPage = "lobby";
  await refreshState();
  await startRealtime();
  startPolling();
}

void bootstrap();
