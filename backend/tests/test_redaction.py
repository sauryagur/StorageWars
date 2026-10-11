from test_guess_api import run_pre_reveal_http_responses_without_product_secrets


def test_pre_reveal_response_redaction_sweep(client, clock):
    run_pre_reveal_http_responses_without_product_secrets(client, clock)
