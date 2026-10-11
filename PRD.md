# PRD: Impulse Buy (Working Title)

Oct 10, 2026 · @Aayush

## Overview

Impulse Buy is a mobile-first multiplayer party game where players describe a product they can only see as an image, then guess the real prices of the products everyone else described. It combines the Gartic Phone pattern (a lossy description chain with a funny reveal) with Skribbl-style asymmetric information (the author holds a secret, guessers decode it under a clock).

- **Audience:** friend groups, in the same room or on Discord voice.
- **Platform:** mobile web. Players join with a 4-character room code, with no install and no account.
- **Session size:** 2 to 8 players. Every player authors exactly one card and guesses on every other card.
- **Session length:** about 4 minutes with 4 players and about 7 minutes with 8.
- **Rooms:** private rooms only in v1. Friends play on an honor system, and the design makes cheating unprofitable instead of trying to police it.

## Goals and non-goals

The game succeeds if the group laughs at the reveal carousel and starts another game.

**Goals**

- The funniest moment is the reveal: the original product next to what a friend made of it, with everyone's guesses plotted on a price axis.
- No dead time. Every phase is parallel, with no waiting for someone else's turn.
- Guessing is a real decision. Waiting buys information, and the clock costs points.
- Cheating is unprofitable by design. Moderation handles trolling only.
- From opening the link to the first card in under 30 seconds.

**Non-goals (v1)**

- Hidden roles, saboteurs, or bluffing mechanics. They were removed after the design review, because opposed interests between author and guesser collapse the description into cheap talk.
- Public lobbies and matchmaking with strangers.
- Accounts, friends lists, persistent leaderboards.
- Voice or video (players use Discord).
- Live guess feeds. Guesses are hidden until the reveal to prevent herding.

## Core design principles

These come from the game-theory review and decide trade-offs later in the document.

1. **Information asymmetry is the engine.** The author knows the product, and guessers decode a lossy description.
2. **Scoring must reward the intended behavior.** For each role, the highest-scoring strategy should be the fun one.
3. **No dominant strategy.** Locking early, locking late, and guessing safely should each be viable.
4. **Cheating is made unprofitable, not just forbidden.** The server never sends secrets to clients that shouldn't have them.
5. **Server authority.** Clients send inputs only. The server owns state, timers, and scoring.

## Game flow

`LOBBY → AUTHOR → GUESS → REVEAL CAROUSEL → VOTE → FINAL`

### Phase 1: Author (parallel, 60 seconds)

Every player simultaneously receives a different product from the curated pool.

**The author sees**

- The product image.
- A coarse price band: band 1 (under 15 USD), band 2 (15 to 60 USD), band 3 (60 to 200 USD), or band 4 (over 200 USD). Never the exact price.

**The author never sees**

- The original title, description, rating, or review count.

**The author fills in a constrained form**

| Field               | Rule                                                                          |
| ------------------- | ----------------------------------------------------------------------------- |
| Title               | 8 to 60 characters                                                            |
| Three bullet points | 15 to 80 characters each                                                      |
| Star rating         | Picker, 1.0 to 5.0 in half steps                                              |
| Review count        | Bucket picker: under 10, 10 to 99, 100 to 999, 1,000 to 9,999, 10,000 or more |
| Category            | Dropdown of about 12 categories                                               |

**Input validation (server-side)**

- Reject digits, number words ("fifty", "hundred"), currency symbols, and a maintained list of price words ("cheap", "expensive", "dollar", "bucks", "cost", "pricey").
- Profanity filter on all text.
- Live inline validation, so players see what was rejected and why.

**Timeout:** an author who submits nothing has their card skipped. An author who submits partially has the filled fields used and the rest left blank.

Why constrain the form: free numeric fields and open text are covert channels for leaking the price band. Constrained pickers cap how much information the author can transmit and keep cards comparable across authors.

### Phase 2: Guess (per-player, pipelined)

Each player works through the other players' cards at their own pace.

- **Card order is shuffled per player,** so "the third card is expensive" spoils nothing on Discord.
- Cards are shown in a generic marketplace layout with a placeholder where the image would be. **The server never sends the image to guessers.** A CSS blur or overlay is not acceptable, because it could be removed with a network inspector.
- **Drip reveal:** the card's information arrives on a server-driven schedule, so waiting buys information.

| Card time | What appears                                        |
| --------- | --------------------------------------------------- |
| 0s        | Title and category                                  |
| 5s        | Three bullet points                                 |
| 10s       | Star rating and review-count bucket                 |
| 20s       | Hard cap. The latest slider position is auto-locked |

- **Slider:** a fixed global log scale from 1 to 1,000 USD with tick marks, the same on every card so its range reveals nothing. Plus and minus nudge buttons (about 5% per tap) and a tap-to-type numeric fallback. Cents are allowed under 20 USD.
- **Lock:** a Lock button commits the guess permanently and advances to the next card. It is disabled for the first 3 seconds of each card (minimum dwell) and until the slider has been touched.
- **Time multiplier:** the earlier you lock, the higher the multiplier, with a gentle continuous decay (see Scoring). The countdown ring shows the live multiplier so the cost of waiting is visible.
- **No guesses are visible to anyone** until the reveal. A "3 of 5 locked" style progress indicator is allowed, but it never exposes values.
- A player finishes when every card is locked. They see a waiting screen until all players finish.

### Phase 3: Reveal carousel (shared, about 12 seconds per card)

All players watch the same carousel, one card per slide, in a shuffled order. The room creator can advance early, and slides auto-advance otherwise.

Each slide shows:

1. The **original image**, original title, and original description from the dataset.
2. The **author's card** side by side with the original. A word-level diff is not used, because the author never saw the original text and a diff would just be noise.
3. The **true price**, shown as a vertical line on a log-scale axis.
4. **Every guess as a labeled dot** on that axis, with its lock time.
5. The author's name, and points earned on this card by each guesser.

A fitted bell curve is not used, because with 3 to 7 guesses it is statistically meaningless. A faint decorative density overlay is optional and must not be labeled as data.

Scores are **not shown** on slides.

### Phase 4: Vote and final

1. **Funniest card vote:** each player casts one hidden vote for the funniest card that isn't their own.
2. **Final scoreboard:** only now are scores revealed, with a ranked list, the winner, and a breakdown of guesser points, author points, and funniest-card bonus.
3. **Replay** returns everyone to the lobby.

## Scoring

All numbers are starting values to tune in playtests.

### Guesser points (per card)

Error is measured in log space, so a 10 USD miss on a 12 USD item is treated very differently from a 10 USD miss on a 400 USD item. It is normalized by a **prior** spread for the item's category, never by the in-game crowd, because 3 to 7 guesses give an unstable crowd spread and a kicked player would force recomputing everything.

```
z        = |ln(guess / price)| / sigma_category
accuracy = max(0, 1 - z / 2)
M(t)     = 1.0 - 0.3 * (t / 20)           # t = seconds on the card at lock
points   = round(1000 * accuracy * M(t))
```

- `sigma_category` defaults to 0.5, which makes the zero point about 2.7 times off in either direction. Tune per category from playtest data.
- A guess that is never locked and never touched scores 0.
- There are no bullseye or closest-guess bonuses. They pay almost entirely for exactness, which favors anyone who looked the item up.

### Author points

```
author_points = round(1000 * mean_accuracy_of_all_guessers_on_the_card)
```

This gives authors a reason to write informative cards. It is weighted at about one card's worth of guesser points, so writing quality matters as much as guessing well on one card.

### Funniest-card bonus

The card with the most funniest-card votes earns its author +300, split on ties. This is the counterweight that keeps cards funny instead of dry.

### Total

`total = sum of guesser points over every card + author points + funniest-card bonus`

The highest total wins.

### Why these numbers need testing

The multiplier only creates a real dilemma if later information improves accuracy by roughly what the decay costs. If the drip barely improves guesses, everyone locks immediately and the clock is decoration. See the playtest checklist.

## Fairness and anti-cheat

The approach is **design first, votekick last**. A votekick cannot observe a phone lookup or a Discord leak, so it rests on suspicion.

| Risk                                | Mitigation                                                                                                                                                                                           |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reverse image search by guessers    | Guessers never receive the image. The redaction happens on the server.                                                                                                                               |
| Author leaks the price              | The author sees only a price band, and the form is constrained (pickers and capped text), which caps the information that can be encoded.                                                            |
| Author looks the item up themselves | Accepted residual risk. The 60-second limit, the constrained form, and the author score being capped at one card's worth of points limit the benefit. Playtests should measure how often it happens. |
| Spoiling cards over Discord         | Card order is shuffled per player. The slider range is global.                                                                                                                                       |
| Herding off other guesses           | All guesses are hidden until the reveal.                                                                                                                                                             |
| Leader-bashing and kingmaking       | Scores and running leaderboards are hidden until the final screen. Funniest-card votes are hidden and cast before scores are shown.                                                                  |
| Constant-guess strategy             | The zero point is set so a constant mid-range guess earns well under half of an engaged player's score. Verify in simulation.                                                                        |
| Latency advantage                   | The server stamps all lock times. The multiplier decay is gentle (0.3 over 20 seconds), so 200 ms costs about 0.3%.                                                                                  |
| Trolling cards                      | Length caps, profanity filter, a report button, and votekick for offensive content or AFK only.                                                                                                      |
| Number parsing abuse                | Server-side parsing with clamping to the slider range. Non-numeric input is rejected.                                                                                                                |

### Votekick rules

- Available only for offensive content or AFK behavior, not for accusing someone of cheating.
- Requires at least two thirds of the other players.
- A kicked player's card and guesses are removed from everyone's totals. Scoring is per card and uses a prior spread, so this needs no recomputation of crowd statistics.
- If fewer than 4 players remain, the game ends early and shows the cards completed so far.

## Data and content

Product content comes from a curated product pool. **The data license is a launch blocker** (see open questions).

**Fields needed per product:** image, original title, original description, price, category, plus star rating and review count if they will appear in the reveal.

**Curation**

- Keep items with a working image, a snapshot price, and a clear single variant.
- Price range of about 2 to 500 USD.
- **Sample log-uniformly by price,** so no single price band dominates and a constant guess earns little.
- Do not use stratified sampling without replacement within a game, since players could infer remaining price bands.
- Prefer lookup-resistant and visually ambiguous items: unbranded goods, multipacks, bundles, and variants.
- Remove adult, weapon, and offensive items, near-duplicates, and items with ambiguous pricing.
- Store images on our own storage or CDN. Re-encode and strip metadata and filenames.
- Frame the reveal price as a "snapshot price" with the date.
- Use a generic marketplace look in the UI. Do not use Amazon branding.

## Screens

Every screen is designed for a phone in portrait while the player is on a voice call.

| Screen               | Shown to | Key elements                                                                                                    |
| -------------------- | -------- | --------------------------------------------------------------------------------------------------------------- |
| Lobby                | All      | Room code, player list, start button for the room creator (2 to 8 players)                                      |
| Author               | All      | Image, price band, form with live validation, countdown                                                         |
| Waiting for authors  | All      | Progress indicator                                                                                              |
| Guess                | All      | Redacted card layout, countdown ring with live multiplier, slider, nudge buttons, numeric fallback, Lock button |
| Waiting for guessers | All      | Progress indicator                                                                                              |
| Reveal carousel      | All      | Original vs author card, true price, guess dot plot                                                             |
| Vote                 | All      | Pick the funniest card                                                                                          |
| Final                | All      | Ranked scoreboard, breakdown, replay                                                                            |

**Feel details**

- Each drip reveal arrives with a short sound and a pulse so it is noticed mid-conversation.
- The Lock button gives a clear haptic and visual confirmation, and the echoed price value is displayed before and after locking so typos are visible.
- Reveal slides animate the dots landing on the price axis one by one, ending on the true price.

## Technical requirements

- **Client:** responsive web app that works on current iOS Safari and Android Chrome.
- **Realtime:** one WebSocket per player.
- **Server-authoritative state machine** that owns phase transitions, timers, drip schedules, scoring, and vote tallies.
- **Secrets stay server-side:** the true price, original title, original description, and image are never sent to guessers before the reveal. Authors receive only the image and the price band.
- **Rooms:** 4-character codes, in-memory state with a short TTL. Players rejoin with a session token and their name.
- **Disconnect handling**
  - A disconnected author before submitting: the card is skipped.
  - A disconnected guesser: the current card auto-locks if the slider was touched, otherwise scores 0, and the remaining cards score 0 unless they rejoin in time.
- **Input handling:** the server clamps values, rate-limits events, and caps field lengths.
- **Content store:** curated product table plus image storage, loaded once per room and sampled without repeats within a game.
- **Moderation:** profanity filter on names and all author text, plus a report button.

## Success metrics

- 70% of started games reach the final scoreboard.
- Median time from link open to first card under 30 seconds.
- At least 50% of games produce a replay.
- **Lock-time spread:** no drip stage holds more than 50% of all locks. If one does, the multiplier or the drip schedule is miscalibrated.
- **Lazy-strategy ratio:** a constant mid-range guess earns under half of an engaged player's average score.
- **Searcher edge:** a player who knows the exact price at 10 seconds beats a good honest guesser by a modest margin, not a landslide.
- **Author quality:** mean guesser accuracy on cards is meaningfully above blind-guess accuracy, and the funniest-card winners are not always the least informative cards.
- Votekick usage stays rare (under 3% of games).

## Playtest and simulation checklist

Run these before building polished UI.

1. **Drip lift:** measure how much accuracy improves at 0, 5, and 10 seconds. Set the multiplier decay so the expected value (accuracy times multiplier) is within about 10% across stages. If the drip adds little accuracy, flatten the decay or reduce time pressure to a minor bonus.
2. **Lazy strategy:** simulate a constant guess and a random guess against the log-uniform price distribution and confirm the ratio target.
3. **Searcher advantage:** simulate a perfect guess at roughly 10 seconds and compare with an honest good guess.
4. **Author balance:** check whether authors under the current weights write informative-but-funny cards, or only dry ones. Adjust the funniest-card bonus and the author weight.
5. **Slider precision:** test whether players on phones can land within about 10% on a three-decade log slider, and whether the nudge buttons and numeric fallback are used.
6. **Adversarial session:** ask testers to collude, troll, and share numbers on voice, and record what actually works.

## Milestones

1. **Prototype:** lobby, author form with validation, guessing flow with drip, 100 curated products, per-card scoring.
2. **Playtest build:** reveal carousel with the dot plot, funniest-card vote, hidden scoring until the end, shuffled card order.
3. **Tuning:** adjust the multiplier, category spreads, author weight, and bonus from playtest data and simulation.
4. **Launch:** moderation tooling, rejoin handling, votekick, replay flow, final content licensing.

## Risks

| Risk                                              | Impact | Response                                                                                                      |
| ------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------- |
| Dataset or image licensing blocks a public launch | High   | Resolve before content work. Use licensed data, an open dataset with commercial terms, or self-created items. |
| Authors write dry, price-informative cards        | Medium | Raise the funniest-card bonus and lower the author accuracy weight.                                           |
| Everyone locks instantly                          | Medium | Recalibrate the multiplier against measured drip lift.                                                        |
| Author searches the item up                       | Medium | Constrained form and capped weight. Measure and adjust.                                                       |
| Slider frustration on phones                      | Medium | Log slider with nudge buttons and a numeric fallback. Test early.                                             |
| Small rooms (4 players) give thin guess data      | Low    | Use a prior spread for scoring, so thin crowds do not matter.                                                 |
