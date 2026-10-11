/**
 * Impulse Buy REST API client.
 *
 * Configure VITE_API_BASE_URL in .env.local, e.g.:
 * VITE_API_BASE_URL=http://localhost:3000/v1
 *
 * The API spec's api.impulsebuy.example URL is a placeholder.
 * Session tokens are stored in sessionStorage and are never put in URLs.
 */

export type PhaseName = "LOBBY" | "AUTHOR" | "GUESS" | "REVEAL" | "VOTE" | "FINAL";

export interface JoinResponse {
  roomId: string;
  roomCode: string;
  playerId: string;
  sessionToken: string;
  isCreator?: boolean;
  rejoined?: boolean;
  phase: PhaseName;
  ttlExpiresAt: string;
  snapshotUrl?: string;
}

export interface RoomPlayer {
  playerId: string;
  name: string;
  isCreator: boolean;
  connected: boolean;
}

export interface RoomState {
  phase: PhaseName;
  players: RoomPlayer[];
  canStart: boolean;
  isCreator: boolean;
  ttlExpiresAt: string;
}

export interface WsTicket {
  ticket: string;
  expiresAt: string;
}

export interface AuthorCard {
  cardId: string;
  imageUrl: string;
  priceBand: 1 | 2 | 3 | 4;
  deadlineAt: string;
  status: string;
  constraints: {
    titleMinChars?: number;
    titleMaxChars?: number;
    bulletMinChars?: number;
    bulletMaxChars?: number;
    bulletSlots?: number;
    starRatingMin?: number;
    starRatingMax?: number;
    starRatingStep?: number;
  };
}

export interface RevealGuess {
  playerName: string;
  valueCents: number;
  lockedAt: string;
  cardSeconds?: number | null;
  timedOut: boolean;
}

export interface RevealSlide {
  slideIndex: number;
  slideCount: number;
  autoAdvanceAt: string;
  canAdvance: boolean;
  card: {
    cardId: string;
    authorName: string;
    authored: {
      title?: string | null;
      bullets?: Array<string | null> | null;
      starRating?: number | null;
      reviewBucket?: string | null;
      category?: string | null;
    };
    original: {
      imageUrl?: string | null;
      title?: string | null;
      description?: string | null;
      priceCents?: number | null;
      snapshotDate?: string | null;
      category?: string | null;
    };
    guesses: RevealGuess[];
    axisMinCents: number;
    axisMaxCents: number;
  };
}

export interface VoteOptions {
  options: Array<{
    cardId: string;
    authorName?: string | null;
    title?: string | null;
    category?: string | null;
    starRating?: number | null;
    reviewBucket?: string | null;
  }>;
  deadlineAt?: string | null;
  myVoteCast?: boolean;
}

export interface ValueEcho {
  valueCents: number;
  formattedValue: string;
  wasClamped: boolean;
  wasRounded: boolean;
}

export interface LockResponse extends ValueEcho {
  cardId: string;
  lockedAt: string;
  cardSeconds: number;
  multiplier: number;
  nextCardId?: string | null;
}

export interface GuessQueue {
  cards: Array<{ cardId: string; status: string }>;
  myPosition: {
    activeCardId: string | null;
    nextCardId?: string | null;
    allDone?: boolean;
  };
  progress: {
    myLocked: number;
    myTimedOut: number;
    myTotal: number;
    allPlayersDone: boolean;
  };
}

export interface GuessCard {
  cardId: string;
  status: string;
  openedAt: string;
  capAt: string;
  lockEligibleAt: string;
  multiplierNow: number;
  draftValueCents: number | null;
  sliderTouched: boolean;
  title?: string | null;
  category?: string | null;
  bullets?: Array<string | null>;
  starRating?: number | null;
  reviewBucket?: string | null;
  reviewCount?: number | null;
}

export interface GameSnapshot {
  roomId: string;
  roomCode: string;
  playerId: string;
  phase: PhaseName;
  seq: number;
  lobby?: { players?: RoomPlayer[] };
  author?: { card?: AuthorCard; submitted?: boolean; progress?: Record<string, number> };
  guess?: { queue?: GuessQueue; activeCard?: GuessCard };
  reveal?: RevealSlide;
  vote?: VoteOptions;
  final?: FinalScoreboard;
  [key: string]: unknown;
}

export interface FinalScoreboard {
  endedReason: "COMPLETED" | "TOO_FEW_PLAYERS";
  winnerPlayerId: string | null;
  rankings: FinalRanking[];
}

export interface FinalRanking {
  rank: number;
  playerId: string;
  name: string;
  totalPoints: number;
  breakdown: {
    guesserPoints: number;
    authorPoints: number;
    funniestBonus: number;
  };
  perCard?: Array<{
    cardId: string;
    role: "GUESSER" | "AUTHOR";
    status: string;
    points?: number | null;
    accuracy?: number | null;
    lockedAt?: string | null;
    funniestVotes?: number | null;
  }> | null;
}

export interface AuthorSubmission {
  title?: string | null;
  bullets?: Array<string | null> | null;
  starRating?: number | null;
  reviewBucket?: "UNDER_10" | "TEN_TO_99" | "HUNDRED_TO_999" | "THOUSAND_TO_9999" | "TEN_THOUSAND_PLUS" | null;
  category?: string | null;
}

export interface ApiErrorPayload {
  error?: string;
  code?: string;
  message?: string;
  details?: unknown;
  fieldErrors?: Array<{ field: string; rule: string; message: string }>;
}

export class ApiError extends Error {
  readonly status: number;
  readonly payload?: ApiErrorPayload;

  constructor(message: string, status: number, payload?: ApiErrorPayload) {
    super(message);
    this.status = status;
    this.payload = payload;
    this.name = "ApiError";
  }
}

const envBase = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env
  ?.VITE_API_BASE_URL;

const BASE_URL = (envBase || "http://localhost:3000/v1").replace(/\/+$/, "");
const SESSION_KEY = "impulsebuy.sessionToken";
const ROOM_KEY = "impulsebuy.roomCode";
const PLAYER_KEY = "impulsebuy.playerId";

export const session = {
  get token(): string | null {
    return sessionStorage.getItem(SESSION_KEY);
  },
  get roomCode(): string | null {
    return sessionStorage.getItem(ROOM_KEY);
  },
  get playerId(): string | null {
    return sessionStorage.getItem(PLAYER_KEY);
  },
  save(join: JoinResponse): void {
    sessionStorage.setItem(SESSION_KEY, join.sessionToken);
    sessionStorage.setItem(ROOM_KEY, join.roomCode);
    sessionStorage.setItem(PLAYER_KEY, join.playerId);
  },
  clear(): void {
    sessionStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(ROOM_KEY);
    sessionStorage.removeItem(PLAYER_KEY);
  },
};

async function request<T>(
  path: string,
  options: RequestInit = {},
  authenticated = true,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (authenticated) {
    const token = session.token;
    if (!token) throw new ApiError("You are not in a room. Create or join one first.", 401);
    headers.set("X-Session-Token", token);
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(`Could not reach the API at ${BASE_URL}. Check the server and VITE_API_BASE_URL.`, 0);
  }

  const text = await response.text();
  let payload: unknown;
  if (text) {
    try { payload = JSON.parse(text); }
    catch { payload = { message: text }; }
  }

  if (!response.ok) {
    const detail = payload && typeof payload === "object" ? payload as ApiErrorPayload : undefined;
    const message = detail?.message || detail?.error || detail?.code ||
      `API request failed (${response.status} ${response.statusText})`;
    throw new ApiError(message, response.status, detail);
  }

  return payload as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  ...(body === undefined ? {} : { body: JSON.stringify(body) }),
});

const codePath = (code: string) => `/rooms/${encodeURIComponent(code.toUpperCase())}`;

export const api = {
  baseUrl: BASE_URL,

  health: () => request<{ status: "ok" }>("/health", {}, false),

  createRoom: async (name: string) => {
    const result = await request<JoinResponse>("/rooms", json("POST", { name }), false);
    session.save(result);
    return result;
  },

  joinRoom: async (roomCode: string, name: string) => {
    const result = await request<JoinResponse>(
      `${codePath(roomCode)}/join`, json("POST", { name }), false,
    );
    session.save(result);
    return result;
  },

  rejoinRoom: async (roomCode: string, sessionToken: string) => {
    const result = await request<JoinResponse>(
      `${codePath(roomCode)}/join`, json("POST", { sessionToken }), false,
    );
    session.save(result);
    return result;
  },

  getRoom: (roomCode = session.roomCode) => {
    if (!roomCode) throw new ApiError("Missing room code.", 400);
    return request<RoomState>(codePath(roomCode));
  },

  startGame: (roomCode = session.roomCode) => {
    if (!roomCode) throw new ApiError("Missing room code.", 400);
    return request<{ phase: PhaseName; authorDeadlineAt: string }>(
      `${codePath(roomCode)}/start`, json("POST"),
    );
  },

  replayRoom: (roomCode = session.roomCode) => {
    if (!roomCode) throw new ApiError("Missing room code.", 400);
    return request<{ newRoomId: string; newRoomCode: string; seatClaimExpiresAt: string }>(
      `${codePath(roomCode)}/replay`, json("POST"),
    );
  },

  mintWebSocketTicket: () => request<WsTicket>("/ws/ticket", json("POST")),

  snapshot: () => request<GameSnapshot>("/games/current/snapshot"),

  getAuthorCard: () => request<AuthorCard>("/games/current/author-card"),

  submitAuthorCard: (body: AuthorSubmission) =>
    request<{ cardId: string; status: string; submittedAt?: string | null }>(
      "/games/current/author-card", json("PUT", body),
    ),

  getGuessQueue: () => request<GuessQueue>("/games/current/guess/queue"),

  openGuessCard: (cardId: string) =>
    request<GuessCard>(`/games/current/guess/cards/${encodeURIComponent(cardId)}/open`, json("POST")),

  getGuessCard: (cardId: string) =>
    request<GuessCard>(`/games/current/guess/cards/${encodeURIComponent(cardId)}`),

  saveGuessDraft: (cardId: string, valueCents: number) =>
    request<ValueEcho>(
      `/games/current/guess/cards/${encodeURIComponent(cardId)}/draft`,
      json("PUT", { valueCents: Math.round(valueCents) }),
    ),

  touchGuessSlider: (cardId: string) =>
    request<void>(`/games/current/guess/cards/${encodeURIComponent(cardId)}/touch`, json("POST")),

  lockGuess: (cardId: string, valueCents: number) =>
    request<LockResponse>(
      `/games/current/guess/cards/${encodeURIComponent(cardId)}/lock`,
      json("POST", { valueCents: Math.round(valueCents) }),
    ),

  getReveal: () => request<RevealSlide>("/games/current/reveal"),

  advanceReveal: () => request<void>("/games/current/reveal/advance", json("POST")),

  getVoteOptions: () => request<VoteOptions>("/games/current/vote/options"),

  vote: (cardId: string) =>
    request<void>("/games/current/vote", json("POST", { cardId })),

  getFinal: () => request<FinalScoreboard>("/games/current/final"),

  report: (body: Record<string, unknown>) => request<Record<string, unknown>>("/reports", json("POST", body)),

  voteKick: (roomCode: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`${codePath(roomCode)}/votekick`, json("POST", body)),
};

/**
 * Ticket-based WebSocket connection. The session token is never placed in
 * the URL; only the short-lived single-use ticket is sent as a query value.
 * Call onReconnect to refetch the authoritative snapshot after reconnect.
 */
export async function connectRealtime(
  websocketBaseUrl: string,
  onMessage: (event: MessageEvent<string>) => void,
  onReconnect?: () => void | Promise<void>,
): Promise<WebSocket> {
  const { ticket } = await api.mintWebSocketTicket();
  const url = new URL(websocketBaseUrl, window.location.href);
  // Tickets are short-lived and single-use. Never send the session token in the URL.
  url.searchParams.set("ticket", ticket);
  const socket = new WebSocket(url);
  socket.addEventListener("message", onMessage);
  socket.addEventListener("open", () => { void onReconnect?.(); });
  return socket;
}
