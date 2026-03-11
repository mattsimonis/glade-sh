"""Shared test utilities for Roost API tests."""


def assert_cors(headers):
    """Every JSON response must carry the CORS header — regression guard."""
    value = headers.get("Access-Control-Allow-Origin")
    assert value == "*", f"Missing CORS header. Got: {value!r}"
