# Storage Wars — Product Requirements Document

## 1. Product Overview

**Storage Wars** is a multiplayer browser party game inspired by storage-unit auctions and games like Skribbl.io and Jackbox.

Players take turns creating visually convincing storage lockers from a random collection of items. The other players then bid on how much they believe the partially revealed locker is worth.

The key twist is that **the host does not control how much of the locker the bidders can see**.

Every round, the server randomly determines how far a physical shutter will open, between **20% and 80%**. The host must therefore arrange their items without knowing exactly how much will ultimately be visible.

The result is a game about:

- Visual deception
- Risk management
- Hidden information
- Spatial optimization
- Bluffing
- Valuation
- Social bidding

### Core design principle

> **The host controls the appearance. The server controls the hidden constraints. The bidders control the price.**

---

# 2. Core Game Loop

A complete game consists of **10 rounds**.

Each round:

1. A player becomes the **host**.
2. The host receives a random collection of items.
3. Each item has:
   - A hidden identity
   - A visual/condition variant
   - A hidden actual value
4. The host arranges the items inside a storage locker.
5. The server determines a random shutter opening percentage between **20% and 80%**.
6. The host does **not know the exact percentage while decorating**.
7. The shutter closes to the randomly selected position.
8. Other players see only the exposed portion of the locker.
9. Players bid on the locker.
10. The host may accept a bid using:
    - Going once
    - Going twice
    - Sold
11. If the timer expires, the highest bidder wins.
12. The shutter opens completely.
13. Items are revealed back-to-front.
14. Each item's actual identity, appearance, and value are revealed.
15. The winning bidder's money is converted into the corresponding item value.
16. The next player becomes host.

After 10 rounds, the player with the highest total net worth wins.

---

# 3. Players

### Supported players

- Minimum: **2**
- Recommended: **4–6**
- Maximum: **8**

No account should be required.

Players can:

- Create a room
- Join using a room code
- Join through a shareable link
- Enter a display name

---

# 4. Game Economy

Each player starts with:

**$10,000**

Players spend money by winning auctions.

Purchased items contribute their **actual revealed value** to the player's final net worth.

### Final score

```text
Final Net Worth =
Remaining Cash
+
Total Actual Value of Purchased Items
```

Example:

```text
Starting cash:        $10,000
Auction spending:      $7,200
Remaining cash:        $2,800
Actual item value:     $8,900

Final net worth:      $11,700
```

This creates an important distinction between:

**What you paid** and **what the locker was actually worth.**

A player can therefore:

- Get a great deal
- Overpay badly
- Make a risky bet
- Intentionally bluff
- Win an apparently cheap locker containing valuable items

---

# 5. Round Structure

Each round has four phases.

## Phase 1 — Setup

The next player becomes host.

The server generates a random locker inventory.

The host receives the items and can arrange them.

## Phase 2 — Decoration

The host places items inside the locker.

They can:

- Drag
- Move
- Scale
- Rotate
- Change layering order

The host is trying to make the locker appear as valuable as possible.

### Hidden constraint

During this phase, the host **does not know the shutter opening percentage**.

The server has already generated it.

For example:

```text
Hidden shutter opening:
37%
```

The host simply sees the full locker while arranging it.

This creates an optimization problem under uncertainty.

The host has to decide:

> "How do I arrange this locker so that it looks valuable regardless of how much of it gets revealed?"

---

# 6. The Shutter Mechanic

The locker has a physical shutter covering its opening.

At the end of the decoration phase, the shutter closes to a randomly selected position.

### Opening range

```text
Minimum: 20%
Maximum: 80%
```

The percentage determines how much of the locker is visible to bidders.

Examples:

```text
80% open
████████████████░░░░

60% open
████████████░░░░░░░░

40% open
████████░░░░░░░░░░░░

20% open
████░░░░░░░░░░░░░░░░
```

The exact presentation should feel physical rather than like a simple UI crop.

### Important rule

**The host does not know the shutter percentage before the auction view is revealed.**

This prevents the host from simply placing the most valuable-looking items exactly where they know the shutter will expose them.

---

# 7. Shutter Behavior

The shutter should reveal a **contiguous region of the locker**.

It should not randomly hide individual objects.

For example, the shutter could roll upward from the bottom:

```text
┌──────────────────────┐
│                      │
│      visible         │
│                      │
├──────────────────────┤
│      SHUTTER         │
│                      │
└──────────────────────┘
```

This preserves the spatial puzzle.

The host therefore has to reason about:

- Vertical placement
- Item size
- Layering
- Visibility
- Partial visibility
- Risk

### Strategic consequence

Suppose a host has:

- $2,000 TV
- $800 guitar
- $50 teddy bear
- $30 lamp

They could place the expensive items together near the front.

But if only 20% is revealed, bidders might see almost none of the valuable items.

Alternatively, they can distribute valuable items throughout the locker.

That produces a more robust locker across different shutter positions.

---

# 8. Item System

Every object in the game is represented by an item instance.

An item has three important concepts:

```text
Item Identity
Appearance Variant
Actual Value
```

These are deliberately not always equivalent.

---

## 8.1 Item Identity

The actual object.

Examples:

- Teddy Bear
- Television
- Guitar
- Sofa
- Laptop
- Watch
- Bicycle
- Microwave
- Camera
- Refrigerator

---

## 8.2 Appearance Variant

The visual state of the object.

Examples:

- New
- Clean
- Dirty
- Damaged
- Old
- Rusty
- Broken
- Luxury
- Generic
- Vintage

The appearance can intentionally mislead the bidder.

### Example

```text
Identity:       Teddy Bear
Appearance:     Dirty
Mean value:     $10
```

A bidder may assume:

> "That looks like an old teddy bear. Probably worth $5."

But the actual item could still be a relatively valuable version.

Conversely:

```text
Identity:       Old Teddy Bear
Appearance:     Old
Mean value:     $5
```

The two objects may look similar while having different underlying values.

---

# 9. Item Value Generation

The game contains a catalogue of items.

Each catalogue entry contains at minimum:

```typescript
{
  id: string
  name: string
  category: string
  meanPrice: number
  volatility: number
  variants: AppearanceVariant[]
  asset: string
}
```

An individual item instance receives a sampled actual value.

For example:

```text
Laptop
Mean price: $800
Volatility: 20%

Sampled instance value:
$947
```

The exact value is determined by the server.

Clients should never receive hidden item values before the reveal.

### Value distribution

The value distribution should avoid producing impossible negative prices.

A positive-valued distribution such as a log-normal distribution or a clamped distribution can be used.

The exact statistical model should be configurable.

---

# 10. Item Catalogue

The game should have a large catalogue of SVG assets.

Target:

- MVP: **200–500 items**
- Long-term: **1,000+ items**

Possible categories:

### Furniture

- Sofa
- Chair
- Table
- Desk
- Bed
- Cabinet
- Bookshelf

### Electronics

- TV
- Laptop
- Monitor
- Camera
- Game console
- Speaker
- Phone

### Toys

- Teddy bear
- Toy car
- Doll
- Board game
- Action figure

### Clothing

- Jacket
- Shoes
- Handbag
- Suit
- Hat

### Kitchen

- Microwave
- Blender
- Toaster
- Coffee machine
- Plates
- Pan

### Tools

- Drill
- Hammer
- Toolbox
- Saw
- Wrench

### Sports

- Bicycle
- Tennis racket
- Football
- Skateboard
- Golf clubs

### Musical Instruments

- Guitar
- Keyboard
- Violin
- Drum

### Books & Collectibles

- Books
- Comic
- Trading cards
- Figurines
- Antique objects

### Jewelry & Luxury

- Watch
- Necklace
- Ring
- Designer bag

### Miscellaneous

- Lamp
- Mirror
- Fan
- Plant
- Clock
- Suitcase

---

# 11. Decoration Interface

The host receives a locker canvas.

The canvas should support:

### Move

Drag items around freely.

### Scale

Resize items.

### Rotate

Rotate objects.

### Layering

Objects can be placed in front of or behind other objects.

Example:

```text
Back
  └── Sofa
      └── Table
          └── Laptop
              └── Lamp
Front
```

Layering should matter during both decoration and reveal.

### Item selection

Selecting an item should provide basic manipulation controls.

The interaction should feel similar to a lightweight design tool rather than a complex editor.

---

# 12. Host Strategy

The host is not simply trying to hide expensive objects.

They are trying to maximize the amount bidders are willing to pay for an incompletely observed locker.

Possible strategies:

### Front-load value

Put expensive objects where they are likely to be visible.

High upside, high risk.

### Distribute value

Spread expensive objects across the locker.

Lower maximum upside but more robust against different shutter positions.

### Mislead

Place visually expensive-looking objects in prominent locations.

### Hide

Put genuinely valuable items behind other objects.

### Create ambiguity

Use appearance variants to make valuable objects look cheap or cheap objects look valuable.

The game should reward different strategies rather than having one obviously optimal arrangement.

---

# 13. Auction Phase

Once the shutter closes, all non-host players enter the bidding phase.

They can see:

- The exposed portion of the locker
- Visible item appearances
- Partial objects
- Item silhouettes naturally created by occlusion
- Current bid
- Remaining auction time

They cannot see:

- Hidden objects
- True item identities
- Actual values
- The shutter percentage as a numerical value
- Any server-side hidden metadata

---

# 14. Bidding

The auction starts at:

**$0**

Players can submit bids.

A bid must be greater than the current bid by a minimum increment.

Example:

```text
Current bid: $1,000
Minimum next bid: $1,100
```

The minimum increment can scale with the current price.

---

# 15. Auction Timer

Recommended auction duration:

**90 seconds**

The timer should create pressure without making the game drag.

Example:

```text
90
89
88
...
10
9
8
...
1
SOLD
```

---

# 16. Host Auction Controls

The host controls the end of the auction.

The host can trigger:

### Going Once

Signals that bidding is nearing its end.

### Going Twice

Signals a final opportunity.

### Sold

Immediately ends the auction and awards the locker to the highest bidder.

The host cannot sell the locker to themselves.

The host also cannot manipulate the auction after seeing hidden information.

---

# 17. Automatic Auction Completion

If the timer reaches zero:

```text
Highest bidder wins.
```

If there are no bids:

```text
Locker remains unsold.
```

The host does not receive the value of the locker.

---

# 18. Reveal Phase

After the auction ends, the shutter opens completely.

The full locker becomes visible.

Then the game reveals the items **back-to-front according to their layer order**.

For each item:

```text
[Visual]
Teddy Bear

Identity:
Teddy Bear

Condition:
Dirty

Actual Value:
$12
```

This is the payoff moment.

The reveal should clearly show the difference between:

```text
What bidders thought
vs.
What was actually there
```

---

# 19. Reveal Animation

The reveal should be one of the most satisfying moments of the game.

Possible sequence:

1. Shutter opens.
2. Full locker becomes visible.
3. Background objects are revealed.
4. Items are revealed in layer order.
5. Each item's value appears.
6. Total locker value is calculated.
7. Auction winner's profit/loss is displayed.

Example:

```text
You paid:

$2,400

Actual locker value:

$4,850

Profit:

+$2,450
```

Or:

```text
You paid:

$5,200

Actual locker value:

$1,900

Loss:

-$3,300
```

---

# 20. Round Results

After the reveal, show:

- Winning bidder
- Winning bid
- Actual locker value
- Profit/loss
- Player cash balances
- Player net worth

Then proceed to the next round.

---

# 21. Host Rotation

The host rotates every round.

For 5 players:

```text
Round 1 → Player A
Round 2 → Player B
Round 3 → Player C
Round 4 → Player D
Round 5 → Player E
Round 6 → Player A
...
```

Every player should receive approximately equal hosting opportunities.

---

# 22. Game End

After **10 rounds**, the game ends.

The final leaderboard displays:

```text
1. Player A     $14,820
2. Player C     $12,410
3. Player B     $10,970
4. Player D      $8,220
```

The winner is the player with the highest **final net worth**.

---

# 23. Multiplayer Rooms

Players can:

### Create a room

The creator receives a short room code.

Example:

```text
K7XP
```

### Join a room

Players enter the code or use a shareable link.

Example:

```text
zimma.game/auction/K7XP
```

No account should be required for the MVP.

---

# 24. Lobby

The lobby displays:

- Room code
- Player list
- Ready status
- Host
- Game settings

The creator can start the game once the minimum player count is reached.

---

# 25. Server Authority

The server must be authoritative over all hidden information.

The client should never know:

- Hidden item identities
- Actual prices
- Randomized item values
- Hidden appearance metadata
- Shutter percentage before it is revealed
- Other hidden game state

The client only receives information necessary to render the current phase.

This prevents cheating through browser devtools or inspecting client state.

---

# 26. State Model

A simplified game state could look like:

```typescript
Game {
  id
  phase
  round
  players[]
  currentHost
  currentLocker
  currentBid
  highestBidder
  auctionEndsAt
}
```

Locker:

```typescript
Locker {
  items[]
  shutterOpening
}
```

Item:

```typescript
ItemInstance {
  instanceId
  catalogueId
  appearanceVariant
  actualValue
  x
  y
  scale
  rotation
  zIndex
}
```

The server should separate:

```text
Public Item State
```

from:

```text
Hidden Item State
```

---

# 27. Recommended Architecture

## Frontend

**Next.js**

Responsibilities:

- Lobby
- Room UI
- Locker editor
- Auction UI
- Bidding
- Reveal animations
- Leaderboard

The locker editor can use standard HTML/canvas/SVG interaction rather than requiring a heavy game engine.

---

## Backend / Realtime State

**SpaceTimeDB**

Use SpaceTimeDB as the authoritative realtime multiplayer state layer.

It should handle:

- Rooms
- Players
- Game state
- Item placement
- Bids
- Timers
- Phase transitions
- Server-side randomness
- Hidden state
- Host rotation

Avoid adding a separate SSE layer if SpaceTimeDB already provides the required realtime synchronization.

---

# 28. Anti-Cheat Requirements

The client must be treated as untrusted.

Important rules:

### Prices

Never send actual values before reveal.

### Shutter

Do not send the exact shutter percentage to the host during decoration.

### Bids

Validate bids server-side.

### Money

Never trust client-provided balances.

### Phase transitions

Only the server can advance phases.

### Auction

Only the server determines the winner.

### Randomness

Item selection, item values, appearance variants, and shutter percentage should be generated server-side.

---

# 29. MVP Scope

The first playable version should contain:

### Required

- Room creation
- Room joining
- Player names
- Lobby
- Host rotation
- 2–8 players
- Random item generation
- Item catalogue
- SVG rendering
- Locker canvas
- Dragging
- Scaling
- Rotation
- Layering
- Hidden item values
- Appearance variants
- Random shutter percentage
- 20–80% shutter range
- Hidden shutter percentage during decoration
- Physical shutter animation
- Live bidding
- Auction timer
- Going once
- Going twice
- Sold
- Automatic timeout
- Full reveal
- Actual value display
- Player economy
- 10-round game
- Final leaderboard

### Explicitly NOT required for MVP

- Accounts
- Matchmaking
- Persistent profiles
- Chat
- Voice chat
- Cosmetics
- Inventory systems
- Complex physics
- Mobile-native apps
- AI-generated items
- User-created item assets
- Advanced monetization

---

# 30. UX Principles

The game should feel:

- Fast
- Funny
- Visual
- Social
- Slightly chaotic
- Easy to understand
- Difficult to perfectly optimize

The player should understand the core loop within one round.

There should be very little reading required during gameplay.

The UI should communicate state visually:

```text
DECORATE
    ↓
SHUTTER
    ↓
BID
    ↓
SOLD
    ↓
REVEAL
    ↓
RESULT
```

---

# 31. Design Philosophy

The most important aspect of the game is **incomplete information**.

There should be multiple layers of uncertainty:

### Host uncertainty

The host doesn't know how much of their locker will be visible.

### Bidder uncertainty

Bidders don't know what is behind the shutter.

### Appearance uncertainty

Visible objects may not be worth what they appear to be worth.

### Price uncertainty

Even knowing the true item does not necessarily reveal its exact value because each instance has a sampled price.

This produces a chain:

```text
Host
  ↓
arranges information
  ↓
Server hides information
  ↓
Bidders form beliefs
  ↓
Bidders assign monetary value
  ↓
Auction determines market price
  ↓
Reveal determines truth
```

---

# 32. The Central Gameplay Tension

A host should constantly be thinking:

> "Do I put my best stuff somewhere it might be hidden, or spread it out so there's always something valuable visible?"

A bidder should constantly be thinking:

> "Am I buying a genuinely valuable locker, or am I paying for what the host wants me to believe?"

The reveal should answer:

> "Who actually understood the locker?"

---

# 33. Example Round

Player A is the host.

They receive:

- Old TV — mean $300
- Guitar — mean $700
- Dirty teddy bear — mean $15
- Laptop — mean $900
- Vintage lamp — mean $250
- Bicycle — mean $500

The server secretly chooses:

```text
Shutter opening: 34%
```

Player A does not know this.

They arrange the locker so valuable objects are distributed throughout the space.

The shutter closes.

Bidders see:

- Part of the laptop
- Most of the lamp
- A small portion of the guitar
- The teddy bear

They cannot see the bicycle or TV.

Bidding begins.

```text
$500
$700
$900
$1,100
$1,300
```

Player C eventually buys the locker for:

**$1,300**

The shutter opens.

The complete locker is revealed.

Actual values:

```text
TV        $281
Guitar    $812
Teddy      $13
Laptop    $1,041
Lamp       $194
Bicycle    $623
----------------
Total    $2,964
```

Player C paid:

```text
$1,300
```

Actual value:

```text
$2,964
```

Profit:

```text
+$1,664
```

Player C made an excellent purchase.

---

# 34. Success Criteria

The MVP is successful if:

1. A room can be created and joined without accounts.
2. 2–8 players can complete a full 10-round game.
3. Players understand the game without external instructions.
4. Host decoration feels expressive rather than tedious.
5. The shutter creates meaningful uncertainty.
6. Bidding produces genuine disagreement about value.
7. Reveals regularly produce surprising outcomes.
8. A complete round takes roughly **2–3 minutes**.
9. A full game takes roughly **20–30 minutes**.
10. The game is fun even when players are losing.

---

# 35. Future Features

Potential post-MVP additions:

### Special item types

- Hidden compartments
- Fake valuables
- Sets/collections
- Items whose value changes based on combinations
- Extremely rare items

### Special shutters

- Vertical shutter
- Horizontal shutter
- Broken shutter
- Windowed shutter
- Multiple shutters

### More auction mechanics

- Secret bids
- Bid multipliers
- Minimum reserve prices
- Host bluff mechanics
- Last-second bidding

### Social features

- Voice chat
- Reactions
- Spectator mode
- Replay reveals
- Shareable highlights

### Content expansion

- Themed locker sets
- Seasonal item pools
- Community-created items
- Procedurally generated item combinations

---

# 36. Product Identity

Storage Wars should feel less like a traditional auction simulator and more like:

> **Skribbl.io meets a storage-unit auction meets a social deduction game.**

The actual value of an object matters, but the central game is about **what other people believe it is worth**.

The host creates the illusion.

The bidders price the illusion.

The server eventually reveals the truth.
