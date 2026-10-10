import "./style.css";
import { playSound } from "./sounds";

type Phase = 0 | 1 | 2 | 3;

type Player = {
  id: number;
  name: string;
  host: boolean;
};

type Product = {
  title: string;
  description: string;
  price: number;
  rating: number;
  retailer: string;
  features: string[];
};

type Submission = {
  title: string;
  description: string;
  rating: number;
  retailer: string;
  features: string[];
};

const app = document.querySelector<HTMLDivElement>("#app");

if (!app) throw new Error("Missing #app");

const products: Product[] = [
  {
    title: "Wireless Noise Cancelling Headphones",
    description:
      "Over-ear headphones with active noise cancellation, immersive sound and a lightweight design.",
    price: 299,
    rating: 4.6,
    retailer: "Electronics Store",
    features: [
      "Noise cancellation",
      "30-hour battery",
      "Bluetooth",
      "Fast charging",
    ],
  },
  {
    title: "Mechanical Gaming Keyboard",
    description:
      "A compact mechanical keyboard with tactile switches, customizable lighting and a sturdy frame.",
    price: 79,
    rating: 4.4,
    retailer: "Gaming Store",
    features: [
      "RGB lighting",
      "Mechanical switches",
      "USB-C",
      "Compact layout",
    ],
  },
];

type LobbyPage = "home" | "lobby" | "join";
let lobbyPage: LobbyPage = "home";
let phase: Phase = 0;
let productIndex = 0;
let secondsLeft = 60;
let timer: ReturnType<typeof setInterval> | undefined;
let nextPlayerId = 4;
let lobbyCode = "FUN826";
let notice = "";

let players: Player[] = [
  { id: 1, name: "You", host: true },
  { id: 2, name: "Mochi", host: false },
  { id: 3, name: "Pixel", host: false },
];

let currentPlayerId = 1;

let submission: Submission = {
  title: "",
  description: "",
  rating: 0,
  retailer: "",
  features: ["", "", ""],
};

const submissions = new Map<number, Submission>();
const guesses = new Map<number, number>();

// Sample submissions let you preview the entire UI without a backend.
const demoSubmissions: Record<number, Submission> = {
  2: {
    title: "Premium wireless headphones",
    description:
      "Over-ear headphones with great sound quality and active noise cancellation for travel.",
    rating: 4,
    retailer: "Audio Store",
    features: ["Wireless", "Noise cancelling", "Long battery life"],
  },
  3: {
    title: "Wireless music headset",
    description:
      "Comfortable headphones with a modern design, clear audio and a long-lasting battery.",
    rating: 5,
    retailer: "Tech Shop",
    features: ["Bluetooth", "Comfortable fit", "Quick charging"],
  },
};

const demoGuesses: Record<number, number> = {
  2: 279,
  3: 319,
};

const product = () => products[productIndex % products.length];
const me = () => players.find((p) => p.id === currentPlayerId);
const isHost = () => me()?.host ?? false;
const others = () => players.filter((p) => p.id !== currentPlayerId);

const money = (amount: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(amount);

const esc = (value: string) =>
  value.replace(/[&<>"']/g, (char) => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[char];
  });

function stopTimer() {
  if (timer) clearInterval(timer);
  timer = undefined;
}

function formatTime(seconds: number) {
  return `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
}

function startTimer() {
  stopTimer();
  secondsLeft = 60;

  timer = setInterval(() => {
    secondsLeft = Math.max(0, secondsLeft - 1);

    const timerElement = document.querySelector<HTMLElement>("#timer");

    if (timerElement) {
      timerElement.textContent = formatTime(secondsLeft);
      timerElement.classList.toggle("urgent", secondsLeft <= 10);
    }

    if (secondsLeft === 0) {
      stopTimer();

      if (phase === 1) {
        if (!saveSubmission()) {
          submission.title ||= "Untitled product";
          submission.description ||= "No description provided.";
          submissions.set(currentPlayerId, structuredClone(submission));
        }
        seedOtherSubmissions();
        phase = 2;
      } else if (phase === 2) {
        saveGuesses();
        phase = 3;
      }

      notice = "Time is up.";
      render();
    }
  }, 1000);
}

function phaseProgress() {
  return `
    <div class="phase-progress">
      ${[1, 2, 3]
        .map(
          (n) => `
            <span class="${n === phase ? "active" : n < phase ? "done" : ""}"></span>
          `,
        )
        .join("")}
    </div>
  `;
}

function header() {
  return ""
  return `
    <header class="topbar">
      <div class="brand">Bad <span>Retail</span></div>
    </header>
  `;
}

function productIllustration() {
  // Simple SVG illustration instead of emoji or an invented product photo.
  return `
    <svg viewBox="0 0 240 180" role="img" aria-label="Illustration of headphones">
      <g fill="none" stroke="var(--purple)" stroke-width="9" stroke-linecap="square">
        <path d="M53 102V83C53 43 81 20 120 20S187 43 187 83V102"/>
      </g>
      <path d="M43 91Q43 83 51 83H70V137H51Q43 137 43 129Z"
        fill="var(--pink)"/>
      <path d="M197 91Q197 83 189 83H170V137H189Q197 137 197 129Z"
        fill="var(--mint)"/>
      <path d="M58 93V127M182 93V127"
        stroke="var(--text)" stroke-width="2" opacity=".25"/>
      <path d="M78 151H162"
        stroke="var(--purple)" stroke-width="3" opacity=".25"/>
    </svg>
  `;
}

function playerList() {
  return `
    <div class="player-list">
      ${players
        .map(
          (player, index) => `
            <div class="player">
              <span class="player-index">${String(index + 1).padStart(2, "0")}</span>
              <span class="player-name">${esc(player.name)}</span>
              ${
                player.host
                  ? `<span class="host-label">HOST</span>`
                  : isHost()
                    ? `<button class="remove-player" data-action="remove-player" data-id="${player.id}" aria-label="Remove player">×</button>`
                    : ""
              }
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function homeScreen() {
  return `
    <main class="main">
      <section class="lobby-controls" style="max-width:440px;margin:auto;height:100%;justify-content:center">
        <h1 class="screen-title">Bad Retail</h1>
        <p class="screen-subtitle">
          A social guessing game. Create a lobby with your friends
          or join one that's already open.
        </p>

        <div class="field">
          <label for="username">USERNAME</label>
          <input
            id="username"
            maxlength="20"
            placeholder="Enter your name"
            value="${esc(me()?.name ?? "")}"
          />
        </div>

        <div class="button-row">
          <button class="btn-primary" data-action="create">
            Create lobby
          </button>
          <button data-action="go-join">
            Join lobby
          </button>
        </div>

        <p class="notice" role="status">${esc(notice)}</p>
      </section>
    </main>
  `;
}

function joinScreen() {
  return `
    <main class="main">
      <section class="lobby-controls" style="max-width:440px;margin:auto;height:100%;justify-content:center">
        <p class="section-label">Join</p>
        <h1 class="screen-title">Join a lobby</h1>
        <p class="screen-subtitle">
          Enter your username and the six-character code shared by the host.
        </p>

        <div class="field">
          <label for="username">USERNAME</label>
          <input
            id="username"
            maxlength="20"
            placeholder="Enter your name"
            value="${esc(me()?.name ?? "")}"
          />
        </div>

        <div class="field">
          <label for="join-code">LOBBY CODE</label>
          <input
            id="join-code"
            maxlength="6"
            placeholder="e.g. FUN826"
          />
        </div>

        <div class="button-row">
          <button data-action="back-home">Back</button>
          <button class="btn-primary" data-action="join">Join lobby</button>
        </div>

        <p class="notice" role="status">${esc(notice)}</p>
      </section>
    </main>
  `;
}

function lobbyScreen() {
  return `
    <main class="main">
      <div class="lobby-layout">
        <section class="lobby-controls">
          <p class="section-label">Lobby</p>
          <h1 class="screen-title">Waiting for players</h1>
          <p class="screen-subtitle">
            Share the lobby code. The host can start once at least
            two players have joined.
          </p>

          <div class="lobby-code">
            <div>
              <div class="detail-label">LOBBY CODE</div>
              <strong>${lobbyCode}</strong>
            </div>
            <button data-action="copy">Copy code</button>
          </div>

          <p class="notice" role="status">${esc(notice)}</p>

          <div class="button-row">
            <button data-action="back-home">Leave lobby</button>
            ${
              isHost()
                ? `<button class="btn-primary" data-action="start"
                    ${players.length < 2 ? "disabled" : ""}>
                    Start game
                  </button>`
                : ""
            }
          </div>
        </section>

        <section class="lobby-players">
          <p class="section-label">Players</p>
          ${playerList()}
          <p class="player-count">${players.length} / 8 players</p>
        </section>
      </div>
    </main>
  `;
}

function ratingInput() {
  return `
    <div class="rating">
      ${[1, 2, 3, 4, 5]
        .map(
          (n) => `
            <button
              type="button"
              data-action="rating"
              data-value="${n}"
              class="${n <= submission.rating ? "selected" : ""}"
              aria-label="${n} stars"
            >★</button>
          `,
        )
        .join("")}
    </div>
  `;
}

function featureInputs() {
  return `
    <div class="features">
      ${submission.features
        .map(
          (feature, index) => `
            <div class="feature-row">
              <input
                data-feature="${index}"
                maxlength="70"
                aria-label="Feature ${index + 1}"
                placeholder="Feature ${index + 1}"
                value="${esc(feature)}"
              />
              <button
                type="button"
                data-action="remove-feature"
                data-index="${index}"
                aria-label="Remove feature"
              >×</button>
            </div>
          `,
        )
        .join("")}
    </div>
    ${
      submission.features.length < 6
        ? `<button type="button" data-action="add-feature" style="margin-top:7px">Add feature</button>`
        : ""
    }
  `;
}

function describeScreen() {
  return `
    <main class="main">
      ${phaseProgress()}

      <div class="phase-heading">
        <div>
          <p class="section-label">Phase 1</p>
          <h1 class="screen-title">Describe the product</h1>
          <p class="screen-subtitle">
            Write the title, description, rating, retailer and features.
            Keep the actual product name out of your description.
          </p>
        </div>
        <div class="timer" id="timer">${formatTime(secondsLeft)}</div>
      </div>

      <div class="describe-layout">
        <section class="product-panel">
          <div class="product-image">
            ${productIllustration()}
          </div>

          <p class="section-label" style="margin-top:14px">Actual price</p>
          <div class="actual-price">${money(product().price)}</div>
          <p class="product-note">
            This product and its price are visible only during this phase.
          </p>
        </section>

        <form class="description-form" id="description-form">
          <div class="field">
            <label for="title">TITLE</label>
            <input id="title" maxlength="120" required
              placeholder="Product title" value="${esc(submission.title)}" />
          </div>

          <div class="field">
            <label for="description">DESCRIPTION</label>
            <textarea id="description" maxlength="500" required
              placeholder="Describe the product...">${esc(submission.description)}</textarea>
          </div>

          <div class="field-row">
            <div class="field">
              <label>RATING</label>
              ${ratingInput()}
            </div>
            <div class="field">
              <label for="retailer">RETAILER</label>
              <input id="retailer" maxlength="80"
                placeholder="Retailer"
                value="${esc(submission.retailer)}" />
            </div>
          </div>

          <div class="field">
            <label>FEATURES</label>
            ${featureInputs()}
          </div>

          <div class="form-bottom">
            <span class="small muted">Your description will be shown to the other players.</span>
            <button class="btn-primary" type="submit">Continue</button>
          </div>
        </form>
      </div>
    </main>
  `;
}

function saveSubmission(): boolean {
  const title = document.querySelector<HTMLInputElement>("#title");
  const description = document.querySelector<HTMLTextAreaElement>("#description");
  const retailer = document.querySelector<HTMLInputElement>("#retailer");

  if (!title || !description) return false;

  submission.title = title.value.trim();
  submission.description = description.value.trim();
  submission.retailer = retailer?.value.trim() ?? "";

  document.querySelectorAll<HTMLInputElement>("[data-feature]").forEach((input) => {
    submission.features[Number(input.dataset.feature)] = input.value.trim();
  });

  submission.features = submission.features.filter(Boolean);

  if (!submission.title || !submission.description) {
    notice = "Enter both a title and description.";
    return false;
  }

  submissions.set(currentPlayerId, structuredClone(submission));
  seedOtherSubmissions();

  return true;
}

function seedOtherSubmissions() {
  for (const player of others()) {
    const demo = demoSubmissions[player.id];
    if (demo && !submissions.has(player.id)) {
      submissions.set(player.id, structuredClone(demo));
    }
  }
}

function guessCard(player: Player) {
  const data = submissions.get(player.id);

  return `
    <section class="guess-card">
      <div class="guess-card-head">
        <h3>${esc(player.name)}</h3>
        <span class="small muted">
          ${data?.rating ? `${data.rating} / 5 stars` : ""}
        </span>
      </div>

      <div class="detail-label">TITLE</div>
      <p style="font-weight:600;margin:5px 0 10px">
        ${esc(data?.title ?? "No title submitted")}
      </p>

      <p class="guess-description">
        ${esc(data?.description ?? "No description submitted.")}
      </p>

      <div class="guess-features">
        ${(data?.features ?? [])
          .map((feature) => `<span class="feature-tag">${esc(feature)}</span>`)
          .join("")}
      </div>

      <div class="guess-price">
        <label for="guess-${player.id}">GUESS THE PRICE ($)</label>
        <input
          id="guess-${player.id}"
          data-guess="${player.id}"
          type="number"
          min="0"
          step="0.01"
          placeholder="0.00"
          value="${guesses.get(player.id) ?? ""}"
        />
        <button type="button" data-action="save-guess" data-id="${player.id}">Save</button>
      </div>
    </section>
  `;
}

function guessScreen() {
  return `
    <main class="main">
      ${phaseProgress()}

      <div class="phase-heading">
        <div>
          <p class="section-label">Phase 2</p>
          <h1 class="screen-title">Guess the price</h1>
          <p class="screen-subtitle">
            Read the descriptions submitted by the other players and estimate
            the actual product price.
          </p>
        </div>
        <div class="timer" id="timer">${formatTime(secondsLeft)}</div>
      </div>

      <div class="guess-layout">
        ${
          others().length
            ? others().map(guessCard).join("")
            : `<p class="empty">No other players are in this lobby.</p>`
        }
      </div>
    </main>

    <footer class="sticky-footer">
      <span class="footer-note">${guesses.size} guesses saved</span>
      <button class="btn-primary" data-action="results">Show results</button>
    </footer>
  `;
}

function saveGuesses() {
  document.querySelectorAll<HTMLInputElement>("[data-guess]").forEach((input) => {
    const id = Number(input.dataset.guess);
    const value = Number(input.value);

    if (input.value.trim() !== "" && Number.isFinite(value) && value >= 0) {
      guesses.set(id, value);
    }
  });
}

function bellCurve(values: number[], actual: number) {
  const sorted = values.filter(Number.isFinite);
  const mean = sorted.length
    ? sorted.reduce((sum, n) => sum + n, 0) / sorted.length
    : actual;

  const variance = sorted.length
    ? sorted.reduce((sum, n) => sum + (n - mean) ** 2, 0) / sorted.length
    : 1;

  const deviation = Math.max(Math.sqrt(variance), actual * 0.05, 1);
  const min = Math.max(0, Math.min(actual, ...sorted) - deviation * 2);
  const max = Math.max(actual, ...sorted) + deviation * 2;
  const width = 700;
  const height = 150;

  const points = Array.from({ length: 101 }, (_, i) => {
    const value = min + (max - min) * (i / 100);
    const z = (value - mean) / deviation;
    const y = height - Math.exp(-0.5 * z * z) * height * 0.8;
    return `${i === 0 ? "M" : "L"} ${(i / 100) * width} ${y}`;
  }).join(" ");

  const actualX = ((actual - min) / (max - min)) * width;
  const meanX = ((mean - min) / (max - min)) * width;

  const markers = sorted
    .map((value, index) => {
      const x = ((value - min) / (max - min)) * width;
      const z = (value - mean) / deviation;
      const y = height - Math.exp(-0.5 * z * z) * height * 0.8;
      return `<circle cx="${x}" cy="${Math.max(7, y - 9 - (index % 3) * 5)}" r="4" fill="var(--purple)"/>`;
    })
    .join("");

  return `
    <section class="distribution">
      <div class="distribution-heading">
        <div>
          <p class="section-label">All players</p>
          <h2>Price distribution</h2>
        </div>
        <span class="small muted">${sorted.length} guesses</span>
      </div>

      <svg class="chart" viewBox="0 0 ${width} ${height}"
        preserveAspectRatio="none" role="img" aria-label="Distribution of price guesses">
        <path d="${points} L ${width} ${height} L 0 ${height} Z"
          fill="var(--purple)" fill-opacity=".09"/>
        <path d="${points}" fill="none" stroke="var(--purple)" stroke-width="3"/>
        <line x1="${actualX}" y1="0" x2="${actualX}" y2="${height}"
          stroke="var(--pink)" stroke-width="3" stroke-dasharray="6 5"/>
        <line x1="${meanX}" y1="8" x2="${meanX}" y2="${height}"
          stroke="var(--purple)" stroke-width="1.5" stroke-dasharray="3 5"/>
        ${markers}
      </svg>

      <div class="chart-labels">
        <span>${money(min)}</span>
        <span>Average: ${money(mean)}</span>
        <span>${money(max)}</span>
      </div>

      <div class="chart-legend">
        <span class="legend-item"><span class="legend-swatch"></span>Guess distribution</span>
        <span class="legend-item"><span class="legend-swatch actual"></span>Actual price</span>
      </div>
    </section>
  `;
}

function resultScreen() {
  const p = product();

  const values = others()
    .map((player) => guesses.get(player.id) ?? demoGuesses[player.id])
    .filter((value): value is number => Number.isFinite(value));

  const sorted = [...values].sort((a, b) => a - b);
  const median = sorted.length
    ? sorted.length % 2
      ? sorted[Math.floor(sorted.length / 2)]
      : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
    : 0;

  return `
    <main class="main">
      ${phaseProgress()}

      <div class="phase-heading">
        <div>
          <p class="section-label">Phase 3</p>
          <h1 class="screen-title">Results</h1>
          <p class="screen-subtitle">
            Compare the real product information with what everyone submitted.
          </p>
        </div>
      </div>

      <div class="results-layout">
        <section>
          <div class="product-image result-image">
            ${productIllustration()}
          </div>

          <p class="section-label" style="margin-top:12px">Actual product</p>
          <h2>${esc(p.title)}</h2>
          <div class="result-price">${money(p.price)}</div>

          <div class="detail-line">
            <div class="detail-label">DESCRIPTION</div>
            <div class="detail-value">${esc(p.description)}</div>
          </div>

          <div class="detail-line">
            <div class="detail-label">RATING</div>
            <div class="detail-value">${p.rating} / 5</div>
          </div>

          <div class="detail-line">
            <div class="detail-label">RETAILER</div>
            <div class="detail-value">${esc(p.retailer)}</div>
          </div>

          <div class="detail-line">
            <div class="detail-label">FEATURES</div>
            <div class="guess-features">
              ${p.features.map((f) => `<span class="feature-tag">${esc(f)}</span>`).join("")}
            </div>
          </div>
        </section>

        <section>
          <p class="section-label">Guessed information</p>
          <h2>Your submission</h2>

          <div class="detail-line" style="margin-top:13px">
            <div class="detail-label">TITLE</div>
            <div class="detail-value">${esc(submission.title || "Not submitted")}</div>
          </div>

          <div class="detail-line">
            <div class="detail-label">DESCRIPTION</div>
            <div class="detail-value">${esc(submission.description || "Not submitted")}</div>
          </div>

          <div class="detail-line">
            <div class="detail-label">RATING</div>
            <div class="detail-value">${submission.rating || "—"} / 5</div>
          </div>

          <div class="detail-line">
            <div class="detail-label">RETAILER</div>
            <div class="detail-value">${esc(submission.retailer || "—")}</div>
          </div>

          <div class="detail-line">
            <div class="detail-label">FEATURES</div>
            <div class="guess-features">
              ${submission.features.map((f) => `<span class="feature-tag">${esc(f)}</span>`).join("")}
            </div>
          </div>

          <p class="section-label" style="margin-top:22px">Other players' guesses</p>

          ${
            values.length
              ? others()
                  .map((player) => {
                    const value = guesses.get(player.id) ?? demoGuesses[player.id];
                    if (!Number.isFinite(value)) return "";

                    const difference = Math.abs(value - p.price);
                    const accuracy = Math.max(
                      0,
                      Math.round((1 - difference / Math.max(p.price, 1)) * 100),
                    );

                    return `
                      <div class="result-submission">
                        <div class="result-submission-head">
                          <strong>${esc(player.name)}</strong>
                          <span class="accuracy">${accuracy}% accuracy</span>
                        </div>
                        <div class="detail-value">${money(value)}</div>
                        <p class="small muted" style="margin-top:4px">
                          ${difference === 0 ? "Exact guess" : `${money(difference)} away`}
                        </p>
                      </div>
                    `;
                  })
                  .join("")
              : `<p class="empty">No price guesses were submitted.</p>`
          }
        </section>
      </div>

      ${bellCurve(values, p.price)}
    </main>

    <footer class="sticky-footer">
      <span class="footer-note">Median guess: ${money(median)} · Actual: ${money(p.price)}</span>
      <button class="btn-primary" data-action="next-round">Next round</button>
    </footer>
  `;
}

function render() {
  stopTimer();

  const screen =
    phase !== 0
        ? phase === 1
        ? describeScreen()
        : phase === 2
            ? guessScreen()
            : resultScreen()
        : lobbyPage === "home"
        ? homeScreen()
        : lobbyPage === "join"
            ? joinScreen()
            : lobbyScreen();
  app!.innerHTML = `
    <div class="game">
      ${header()}
      ${screen}
    </div>
  `;

  if (phase === 1 || phase === 2) startTimer();
}

function startGame() {
  if (!isHost() || players.length < 2) return;

  productIndex = 0;
  submission = {
    title: "",
    description: "",
    rating: 0,
    retailer: "",
    features: ["", "", ""],
  };

  submissions.clear();
  guesses.clear();
  seedOtherSubmissions();
  phase = 1;
  notice = "";
  render();
}

function createLobby() {
  const input = document.querySelector<HTMLInputElement>("#username");
  const name = input?.value.trim();

  if (!name) {
    notice = "Enter a username first.";
    render();
    return;
  }

  players = [{ id: 1, name, host: true }];
  currentPlayerId = 1;
  nextPlayerId = 2;
  lobbyCode = Math.random().toString(36).slice(2, 8).toUpperCase();
  submissions.clear();
  guesses.clear();
  phase = 0;
  notice = "Lobby created.";
  lobbyPage = "lobby";
  render();
}

function joinLobby() {
  const name = document.querySelector<HTMLInputElement>("#username")?.value.trim();
  const code = document.querySelector<HTMLInputElement>("#join-code")?.value.trim().toUpperCase();

  if (!name) {
    notice = "Enter a username first.";
    render();
    return;
  }

  if (!code || code !== lobbyCode) {
    notice = `Enter the current demo lobby code: ${lobbyCode}`;
    render();
    return;
  }

  if (players.length >= 8) {
    notice = "This lobby is full.";
    render();
    return;
  }

  const player: Player = {
    id: nextPlayerId++,
    name,
    host: false,
  };

  players.push(player);
  currentPlayerId = player.id;
  notice = "";
  lobbyPage = "lobby";
  render();
}

app.addEventListener("submit", (event) => {
  if (!(event.target instanceof HTMLFormElement)) return;
  if (event.target.id !== "description-form") return;

  event.preventDefault();

  if (!saveSubmission()) {
    const message = notice;
    render();
    notice = message;
    return;
  }

  phase = 2;
  notice = "";
  render();
});

app.addEventListener("input", (event) => {
  if (!(event.target instanceof HTMLInputElement)) return;

  playSound("select");
  if (event.target.dataset.feature !== undefined) {
    submission.features[Number(event.target.dataset.feature)] = event.target.value;
  }
});

app.addEventListener("click", async (event) => {
  if (!(event.target instanceof Element)) return;

  playSound("click");

  const button = event.target.closest<HTMLButtonElement>("[data-action]");
  if (!button || button.disabled) return;

  switch (button.dataset.action) {
    case "create":
      createLobby();
      break;

    case "join":
      joinLobby();
      break;

    case "copy":
      try {
        await navigator.clipboard.writeText(lobbyCode);
        notice = "Lobby code copied.";
      } catch {
        notice = `Lobby code: ${lobbyCode}`;
      }
      render();
      break;

    case "start":
      startGame();
      break;

    case "remove-player": {
      if (!isHost()) break;

      const id = Number(button.dataset.id);
      players = players.filter((player) => player.id !== id);
      submissions.delete(id);
      guesses.delete(id);
      render();
      break;
    }

    case "rating":
      submission.rating = Number(button.dataset.value);
      render();
      break;

    case "add-feature":
      if (submission.features.length < 6) {
        submission.features.push("");
        render();
      }
      break;

    case "remove-feature": {
      const index = Number(button.dataset.index);
      submission.features.splice(index, 1);
      render();
      break;
    }

    case "save-guess": {
      const id = Number(button.dataset.id);
      const input = document.querySelector<HTMLInputElement>(`#guess-${id}`);
      const value = Number(input?.value);

      if (input?.value.trim() !== "" && Number.isFinite(value) && value >= 0) {
        guesses.set(id, value);
        notice = "Guess saved.";
      } else {
        notice = "Enter a valid price.";
      }

      render();
      break;
    }

    case "results":
      saveGuesses();
      phase = 3;
      notice = "";
      render();
      break;

    case "next-round":
      productIndex = (productIndex + 1) % products.length;
      submission = {
        title: "",
        description: "",
        rating: 0,
        retailer: "",
        features: ["", "", ""],
      };
      submissions.clear();
      guesses.clear();
      seedOtherSubmissions();
      phase = 1;
      render();
      break;
    case "go-join":
      notice = "";
      lobbyPage = "join";
      render();
      break;

    case "back-home":
      stopTimer();
      phase = 0;
      lobbyPage = "home";
      notice = "";
      render();
      break;
  }
});

render();
