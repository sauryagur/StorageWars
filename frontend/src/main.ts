import "./style.css";
import { playSound } from "./sounds";
import {
  api,
  ApiError,
  connectRealtime,
  session,
  type AuthorCard,
  type GameSnapshot,
  type GuessCard,
  type GuessQueue,
  type RoomState,
} from "./api";

type LobbyPage = "home" | "join" | "lobby";
type UiPhase = 0 | 1 | 2 | 3;
type FeatureForm = {
  title: string;
  description: string;
  rating: number;
  retailer: string;
  features: string[];
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

let lobbyPage: LobbyPage = "home";
let phase: UiPhase = 0;
let roomCode = session.roomCode ?? "";
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

let submission: FeatureForm = {
  title: "",
  description: "",
  rating: 0,
  retailer: "",
  features: ["", "", ""],
};

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
  }, 10000);
}

function websocketUrl(): string | null {
  const configured = (import.meta as ImportMeta & { env?: Record<string, string | undefined> })
    .env?.VITE_WS_URL;
  if (configured) return configured;
  try {
    const base = new URL(api.baseUrl);
    base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
    // The spec defines the ticket endpoint but does not define a WebSocket
    // path. Configure VITE_WS_URL when the backend uses a dedicated path.
    return base.toString().replace(/\/$/, "");
  } catch {
    return null;
  }
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
      if (socket === nextSocket) socket = undefined;
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

function setNotice(message: string) {
  notice = message;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return error.message;
    if (error.status === 401) return "Your session is missing or expired. Return home and rejoin the room.";
    return error.message;
  }
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}

async function runBusy<T>(task: () => Promise<T>, successMessage = ""): Promise<T | undefined> {
  if (busy) return;
  busy = true;
  notice = "";
  render();
  try {
    const result = await task();
    if (successMessage) notice = successMessage;
    return result;
  } catch (error) {
    notice = errorMessage(error);
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
    } else if (state.phase === "GUESS") {
      guessQueue = await api.getGuessQueue();
      const cardId = guessQueue.myPosition?.activeCardId;
      if (cardId && cardId !== activeCardId) {
        activeCardId = cardId;
        activeGuess = await api.openGuessCard(cardId);
        guessCents = activeGuess.draftValueCents ?? 10000;
        sliderTouched = activeGuess.sliderTouched;
      } else if (cardId) {
        activeGuess = await api.getGuessCard(cardId);
        guessCents = activeGuess.draftValueCents ?? guessCents;
        sliderTouched = activeGuess.sliderTouched;
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
    }
    render();
  } catch (error) {
    if (showErrors) {
      notice = errorMessage(error);
      render();
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

function authorScreen() {
  const card = authorCard;
  const constraints = card?.constraints ?? {};
  const maxBullets = Math.min(6, constraints.bulletSlots ?? 4);
  const bullets = Array.from({ length: maxBullets }, (_, i) => submission.features[i] ?? "");
  return `<main class="main">
    ${phaseProgress()}
    <div class="phase-heading"><div>
      <p class="section-label">Phase 1</p>
      <h1 class="screen-title">Describe the product</h1>
      <p class="screen-subtitle">Use the assigned image. Do not reveal the original product name or price.</p>
    </div><div class="timer">${formatTime(card?.deadlineAt)}</div></div>
    <div class="describe-layout">
      <section class="product-panel">
        <div class="product-image">${card?.imageUrl
          ? `<img src="${esc(card.imageUrl)}" alt="Assigned product" style="max-width:100%;max-height:260px;object-fit:contain" />`
          : productIllustration()}</div>
        <p class="section-label" style="margin-top:14px">Price band</p>
        <div class="actual-price">${card ? `Band ${card.priceBand}` : "Loading…"}</div>
        <p class="product-note">The actual price is hidden from other players.</p>
      </section>
      <form class="description-form" id="description-form">
        <div class="field"><label for="title">TITLE</label>
          <input id="title" maxlength="${constraints.titleMaxChars ?? 120}" required value="${esc(submission.title)}" placeholder="Describe the item" /></div>
        <div class="field"><label for="description">DESCRIPTION</label>
          <textarea id="description" maxlength="500" required placeholder="Describe the product without naming it">${esc(submission.description)}</textarea></div>
        <div class="field-row">
          <div class="field"><label>RATING</label><div class="rating">
            ${[1, 2, 3, 4, 5].map((n) => `<button type="button" data-action="rating" data-value="${n}" class="${n <= submission.rating ? "selected" : ""}" aria-label="${n} stars">★</button>`).join("")}
          </div></div>
          <div class="field"><label for="retailer">CATEGORY</label>
            <input id="retailer" maxlength="80" value="${esc(submission.retailer)}" placeholder="Category" /></div>
        </div>
        <div class="field"><label>FEATURES / BULLETS</label><div class="features">
          ${bullets.map((value, index) => `<div class="feature-row"><input data-feature="${index}" maxlength="${constraints.bulletMaxChars ?? 140}" placeholder="Feature ${index + 1}" value="${esc(value)}" /></div>`).join("")}
        </div></div>
        <div class="form-bottom"><span class="small muted">Your description will be shown to other players.</span>
          <button class="btn-primary" type="submit" ${busy ? "disabled" : ""}>Submit description</button></div>
        <p class="notice" role="status">${esc(notice)}</p>
      </form>
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
  return `<main class="main">
    ${phaseProgress()}
    <div class="phase-heading"><div><p class="section-label">Phase 2</p><h1 class="screen-title">Guess the price</h1>
      <p class="screen-subtitle">Product details appear over time. Only lock when your guess is ready.</p>
    </div><div class="timer">${formatTime(card?.capAt)}</div></div>
    <section class="guess-card">
      <div class="guess-card-head"><h3>Product ${activeCardId ? esc(activeCardId.slice(0, 8)) : ""}</h3>
        <span class="small muted">${card ? `Multiplier ${card.multiplierNow}×` : "Waiting for your card"}</span></div>
      ${fields || `<p class="empty">${card ? "More details will appear as the reveal timer advances." : "No active card. Waiting for the server…"}</p>`}
      <div class="guess-price">
        <label for="guess-slider">YOUR PRICE GUESS ($${money(1).slice(1)} – ${money(1000)})</label>
        <input id="guess-slider" type="range" min="100" max="100000" step="1" value="${guessCents}" ${locked || busy ? "disabled" : ""} />
        <div class="detail-value">${money(valueDollars)}</div>
        <button type="button" data-action="lock-guess" ${!card || locked || busy || !sliderTouched ? "disabled" : ""}>Lock guess</button>
      </div>
    </section>
    <p class="small muted">Cards completed: ${guessQueue?.progress.myLocked ?? 0} / ${guessQueue?.progress.myTotal ?? 0}</p>
    <p class="notice" role="status">${esc(notice)}</p>
  </main>`;
}

function genericDataScreen(title: string, data: unknown, actions: string) {
  const serialized = data ? esc(JSON.stringify(data, null, 2)) : "Waiting for server data…";
  return `<main class="main">${phaseProgress()}
    <div class="phase-heading"><div><p class="section-label">${esc(currentPhase())}</p><h1 class="screen-title">${esc(title)}</h1>
    <p class="screen-subtitle">This phase is controlled by the game server.</p></div></div>
    <section class="guess-card"><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${serialized}</pre></section>
    <p class="notice" role="status">${esc(notice)}</p>
    <div class="button-row">${actions}</div>
  </main>`;
}

function revealScreen() {
  return genericDataScreen("Reveal", snapshot?.reveal, `<button class="btn-primary" data-action="advance-reveal" ${busy ? "disabled" : ""}>Continue</button>`);
}

function voteScreen() {
  const data = snapshot?.vote as { options?: Array<{ cardId: string; title?: string }> } | undefined;
  const options = data?.options ?? [];
  const controls = options.map((option) => `<button data-action="vote" data-card-id="${esc(option.cardId)}">${esc(option.title ?? `Vote for ${option.cardId}`)}</button>`).join("");
  return genericDataScreen("Vote for a description", snapshot?.vote, controls || "<span>No vote options available yet.</span>");
}

function finalScreen() {
  return genericDataScreen("Final results", snapshot?.final, `<button class="btn-primary" data-action="replay" ${busy ? "disabled" : ""}>Play again</button>`);
}

function render() {
  const screen = phase === 0
    ? lobbyPage === "home" ? homeScreen() : lobbyPage === "join" ? joinScreen() : lobbyScreen()
    : phase === 1 ? authorScreen()
    : phase === 2 ? guessScreen()
    : currentPhase() === "VOTE" ? voteScreen()
    : currentPhase() === "FINAL" ? finalScreen()
    : revealScreen();

  app!.innerHTML = `<div class="game">${screen}</div>`;
}

function readAuthorForm(): boolean {
  const title = document.querySelector<HTMLInputElement>("#title");
  const description = document.querySelector<HTMLTextAreaElement>("#description");
  const category = document.querySelector<HTMLInputElement>("#retailer");
  if (!title || !description) return false;
  submission.title = title.value.trim();
  submission.description = description.value.trim();
  submission.retailer = category?.value.trim() ?? "";
  document.querySelectorAll<HTMLInputElement>("[data-feature]").forEach((input) => {
    submission.features[Number(input.dataset.feature)] = input.value.trim();
  });
  submission.features = submission.features.filter(Boolean);
  if (!submission.title || !submission.description) {
    notice = "Enter both a title and description.";
    return false;
  }
  return true;
}

async function createRoom() {
  const input = document.querySelector<HTMLInputElement>("#username");
  playerName = input?.value.trim() ?? "";
  if (!playerName) { notice = "Enter a username first."; render(); return; }
  const joined = await runBusy(() => api.createRoom(playerName));
  if (!joined) return;
  roomCode = joined.roomCode;
  lobbyPage = "lobby";
  await refreshState();
  await startRealtime();
  startPolling();
}

async function joinRoom() {
  playerName = document.querySelector<HTMLInputElement>("#username")?.value.trim() ?? "";
  const code = document.querySelector<HTMLInputElement>("#join-code")?.value.trim().toUpperCase() ?? "";
  if (!playerName) { notice = "Enter a username first."; render(); return; }
  if (!code) { notice = "Enter a room code."; render(); return; }
  const joined = await runBusy(() => api.joinRoom(code, playerName));
  if (!joined) return;
  roomCode = joined.roomCode;
  lobbyPage = "lobby";
  await refreshState();
  await startRealtime();
  startPolling();
}

async function startGame() {
  if (!room?.canStart || !room.isCreator) return;
  const started = await runBusy(() => api.startGame(roomCode));
  if (!started) return;
  await refreshState();
}

app.addEventListener("submit", async (event) => {
  if (!(event.target instanceof HTMLFormElement) || event.target.id !== "description-form") return;
  event.preventDefault();
  if (!readAuthorForm()) { render(); return; }
  const body = {
    title: submission.title,
    bullets: submission.features,
    starRating: submission.rating || null,
    category: submission.retailer || null,
  };
  const result = await runBusy(() => api.submitAuthorCard(body), "Description submitted.");
  if (result) await refreshState();
});

app.addEventListener("input", (event) => {
  if (!(event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement)) return;
  if (event.target.id === "username") playerName = event.target.value;
  if (event.target.dataset.feature !== undefined) {
    submission.features[Number(event.target.dataset.feature)] = event.target.value;
  }
  if (event.target.id === "guess-slider") {
    guessCents = Number(event.target.value);
    sliderTouched = true;
    render();
    return;
  }
  playSound("select");
});

app.addEventListener("change", async (event) => {
  if (!(event.target instanceof HTMLInputElement) || event.target.id !== "guess-slider") return;
  if (!activeCardId) return;
  const result = await runBusy(async () => {
    await api.touchGuessSlider(activeCardId!);
    return api.saveGuessDraft(activeCardId!, guessCents);
  });
  if (result) {
    activeGuess = result;
    sliderTouched = true;
    render();
  }
});

app.addEventListener("click", async (event) => {
  if (!(event.target instanceof Element)) return;
  const button = event.target.closest<HTMLButtonElement>("[data-action]");
  if (!button || button.disabled) return;
  playSound("click");

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
      render();
      break;
    case "lock-guess": {
      if (!activeCardId || !sliderTouched) break;
      const locked = await runBusy(() => api.lockGuess(activeCardId!, guessCents));
      if (locked) {
        activeGuess = locked;
        await refreshState();
      }
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
      const result = await runBusy(() => api.replayRoom(roomCode));
      if (result) {
        session.clear();
        roomCode = result.newRoomCode;
        phase = 0;
        lobbyPage = "lobby";
        await refreshState();
      }
      break;
    }
  }
});

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
