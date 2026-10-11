from test_rooms_api import run_http_game_and_replay_claim_use_original_tokens


def test_four_player_http_game_replay_and_claim(client, clock):
    run_http_game_and_replay_claim_use_original_tokens(client, clock)
