# coding: utf-8

from typing import ClassVar, Dict, List, Tuple  # noqa: F401

from pydantic import Field, field_validator
from typing import Any
from typing_extensions import Annotated
from openapi_server.models.error import Error
from openapi_server.models.final_scoreboard import FinalScoreboard
from openapi_server.models.games_current_vote_post_request import GamesCurrentVotePostRequest
from openapi_server.models.inline_object import InlineObject
from openapi_server.models.replay_response import ReplayResponse
from openapi_server.models.vote_options import VoteOptions
from openapi_server.security_api import get_token_sessionToken

class BaseVoteFinalApi:
    subclasses: ClassVar[Tuple] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        BaseVoteFinalApi.subclasses = BaseVoteFinalApi.subclasses + (cls,)
    async def rooms_room_code_replay_post(
        self,
        roomCode: Annotated[str, Field(min_length=4, max_length=4, description="4-character room code (convenience ID, not a secret).")],
    ) -> ReplayResponse:
        """REPLAY SEMANTICS (single model): replay always creates a NEW room linked to the old one via replayOfRoomId. The old room, its records, and its scores are immutable history. The creator receives the new room code and a seat-claim window. Every player (including the creator) claims a seat in the new room by calling join with their EXISTING session token inside the window; the server maps old token to new seat, so no new credentials are issued and no player ever receives another player&#39;s token. Unclaimed seats expire with the window. """
        ...


    async def games_current_vote_options_get(
        self,
    ) -> VoteOptions:
        """The canonical vote-phase representation: the SUBMITTED cards excluding the voter&#39;s own, with the minimal presentation needed to choose one. A rejoining client that missed slides recovers its options from here (and from the snapshot). Individual votes and tallies remain hidden until FINAL. Voting ends when all eligible players have voted OR the vote deadline (server-set, ~30s, tunable) expires; non-voters simply record no vote and cost no one anything. """
        ...


    async def games_current_vote_post(
        self,
        games_current_vote_post_request: GamesCurrentVotePostRequest,
    ) -> None:
        """One hidden vote per player, for a card that is not the voter&#39;s own. The vote is FINAL when cast — it cannot be replaced or withdrawn (409 ALREADY_VOTED). Most votes wins +300 for the author, split on ties. Votes cast for a card whose author is later kicked are discarded; the kicked player&#39;s own vote is also discarded. """
        ...


    async def games_current_final_get(
        self,
    ) -> FinalScoreboard:
        """Ranked scoreboard with full breakdown. Also the result for EARLY-ENDED games: &#x60;endedReason&#x60; is TOO_FEW_PLAYERS when a votekick dropped the room under 4 players, and the response includes only the cards completed by that point — the client never has to infer how an interrupted phase resolves. Author points use the mean accuracy over ALL eligible guessers on the card (kicked players excluded; zero-accuracy and timed-out guesses count as 0 in the denominator — never a mean over locked guesses only). """
        ...
