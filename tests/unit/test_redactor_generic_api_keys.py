"""Generic key=value / key: value secret redaction.

Follow-up to R7.1 (specs/post-audit-stabilization.md): the post-audit
evidence package (v3.9.1) found that `api_key=abcdef0123456789` left the
alphabetic prefix `abcdef` visible and mislabeled it `[REDACTED:phone]`,
because no dedicated rule existed for generic api_key/token/secret
assignments — only the trailing digit run got swallowed by the broad
phone-number matcher. This does not violate R7.1's literal assertion
(the full original substring never leaks), but it is fragile for future
exports/logs. This test locks in the fix: api_key, apikey, apiKey,
API_KEY, token, access_token, secret, and client_secret must have their
entire value masked, with the key name and separator left untouched.
"""

from __future__ import annotations

import re

from core.redactor import redact_for_export

VALUE = "abcdef0123456789"


def _assert_value_fully_masked(raw: str, key_name: str) -> None:
    result = redact_for_export(raw)
    assert VALUE not in result, f"value leaked: {result!r}"
    assert "[REDACTED:token]" in result, f"not redacted: {result!r}"
    assert "phone" not in result, f"mislabeled as phone: {result!r}"
    assert key_name in result, f"key name must be preserved: {result!r}"


def test_api_key_plain():
    _assert_value_fully_masked(f"api_key={VALUE}", "api_key")


def test_api_key_double_quoted():
    result = redact_for_export(f'api_key="{VALUE}"')
    assert result == 'api_key="[REDACTED:token]"'


def test_api_key_single_quoted():
    result = redact_for_export(f"api_key='{VALUE}'")
    assert result == "api_key='[REDACTED:token]'"


def test_apikey_no_separator_in_name():
    _assert_value_fully_masked(f"apikey={VALUE}", "apikey")


def test_apikey_camel_case():
    _assert_value_fully_masked(f"apiKey={VALUE}", "apiKey")


def test_api_key_upper_case():
    _assert_value_fully_masked(f"API_KEY={VALUE}", "API_KEY")


def test_token_plain():
    _assert_value_fully_masked(f"token={VALUE}", "token")


def test_access_token():
    _assert_value_fully_masked(f"access_token={VALUE}", "access_token")


def test_secret_plain():
    _assert_value_fully_masked(f"secret={VALUE}", "secret")


def test_client_secret():
    _assert_value_fully_masked(f"client_secret={VALUE}", "client_secret")


def test_colon_separator():
    result = redact_for_export(f'"token": "{VALUE}"')
    assert VALUE not in result
    assert '"token"' in result


def test_key_name_itself_is_never_masked():
    """Only the value is redacted — never the parameter name."""
    result = redact_for_export(f"api_key={VALUE}")
    assert re.match(r"^api_key=\[REDACTED:token\]$", result), result


def test_does_not_regress_aws_bearer_openai():
    aws_ak = redact_for_export("AKIA1234567890ABCDEF")
    assert "AKIA1234567890ABCDEF" not in aws_ak
    assert "[REDACTED:aws-key]" in aws_ak

    aws_as = redact_for_export("ASIA1234567890ABCDEF")
    assert "ASIA1234567890ABCDEF" not in aws_as

    aws_env = redact_for_export("aws_access_key_id=AKIA1234567890ABCDEF")
    assert aws_env == "aws_access_key_id=[REDACTED:aws-key]"

    aws_secret_env = redact_for_export(
        "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    )
    assert aws_secret_env == "aws_secret_access_key=[REDACTED:aws-key]"

    bearer = redact_for_export(
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig"
    )
    assert "eyJ" not in bearer
    assert "[REDACTED:token]" in bearer

    openai = redact_for_export("sk-proj-abcdefghij1234567890")
    assert "sk-proj-" not in openai
    assert "[REDACTED:token]" in openai
