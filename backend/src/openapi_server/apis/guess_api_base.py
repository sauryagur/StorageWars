# coding: utf-8

from typing import ClassVar, Dict, List, Tuple  # noqa: F401

from typing import Any
from uuid import UUID
from openapi_server.models.error import Error
from openapi_server.models.guess_card_view import GuessCardView
from openapi_server.models.guess_queue import GuessQueue
from openapi_server.models.inline_object import InlineObject
from openapi_server.models.lock_response import LockResponse
from openapi_server.models.value_echo import ValueEcho
from openapi_server.models.value_input import ValueInput
from openapi_server.security_api import get_token_sessionToken

class BaseGuessApi:
    subclasses: ClassVar[Tuple] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        BaseGuessApi.subclasses = BaseGuessApi.subclasses + (cls,)
    async def games_current_guess_queue_get(
        self,
    ) -> GuessQueue:
        """Card order is shuffled PER PLAYER, so card positions reveal nothing on voice chat. Only SUBMITTED cards appear; skipped cards are excluded and not counted in totals. Exposes card IDs and statuses only — content access is governed by the server-side one-active-card state machine on the open endpoint, regardless of what IDs a client holds. """
        ...


    async def games_current_guess_cards_card_id_open_post(
        self,
        cardId: UUID,
    ) -> GuessCardView:
        """THE queue state machine, server-enforced:  * Exactly ONE active card per player at any time. * Only the player&#39;s NEXT eligible card may be opened. Opening   a future card, a locked card, an already-open card, or a   card not in this player&#39;s queue is rejected (409/404). * Opening a card starts its drip timers ONCE; retries can   never reset or extend them. * A locked card cannot be reopened or modified. * The server, not the client, determines queue position and   whether a lock advances it.  This is a POST because it changes state; the GET on the card is read-only and always returns the current representation. """
        ...


    async def games_current_guess_cards_card_id_get(
        self,
        cardId: UUID,
    ) -> GuessCardView:
        """Read-only. NEVER starts or resets timers — only &#x60;open&#x60; does. The card&#39;s information is determined by the server clock relative to the server-recorded &#x60;openedAt&#x60;:  * 0s — title, category * 5s — bullet slots * 10s — star rating, review-count bucket * 20s — hard cap; latest draft value auto-locks  ABSENT field &#x3D; drip stage not reached. &#x60;null&#x60; &#x3D; the stage is reached but the author left the field blank. Distinct meanings, never conflated. This schema structurally cannot carry the image, original title, original description, or price. """
        ...


    async def games_current_guess_cards_card_id_draft_put(
        self,
        cardId: UUID,
        value_input: ValueInput,
    ) -> ValueEcho:
        """Keeps the latest slider position in authoritative server state. THIS is what makes the disconnect auto-lock rule implementable: a player who drafts $127.50, touches the slider, and then loses their connection has their draft auto-locked at the card&#39;s 20s cap. A player who never touched the slider scores zero. Drafts are throttled server-side (coalesced; only the latest value matters) and are NOT persisted per-keystroke — the latest value is authoritative and persisted at lock time or cap time. Numeric values are clamped to [100, 100000] cents and rounded per the money rule; the normalized value is echoed. """
        ...


    async def games_current_guess_cards_card_id_touch_post(
        self,
        cardId: UUID,
    ) -> None:
        """Idempotent. Lock is disabled until the slider has been touched AND 3 seconds of minimum dwell have elapsed since open. Touch state also governs disconnect auto-lock (auto-lock fires only if touched). """
        ...


    async def games_current_guess_cards_card_id_lock_post(
        self,
        cardId: UUID,
        value_input: ValueInput,
    ) -> LockResponse:
        """Commits the guess permanently and advances the queue. The lock timestamp is stamped by the SERVER. The live multiplier is M(t) &#x3D; 1.0 - 0.3 * (t / 20), t &#x3D; server-measured seconds on the card, clamped to [0, 20]. Points are computed server-side but NEVER returned before FINAL.  Value handling: numeric input is clamped to [100, 100000] cents and rounded per the money rule ($20+ -&gt; whole dollars); the normalized value is echoed with &#x60;wasClamped&#x60;/&#x60;wasRounded&#x60; flags so typos are visible. Non-numeric input is rejected (422). Locking without a prior draft/touch is rejected (403 SLIDER_UNTOUCHED). """
        ...
