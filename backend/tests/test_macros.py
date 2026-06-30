"""VAST macro substitution tests."""
from app.adserver import macros


def test_cachebusting_and_timestamp_replaced():
    url = "https://x/i?cb=[CACHEBUSTING]&ts=[TIMESTAMP]"
    out, replaced, unresolved = macros.substitute(url, now_ms=1_700_000_000_000)
    assert "[CACHEBUSTING]" not in out and "[TIMESTAMP]" not in out
    assert set(replaced) == {"CACHEBUSTING", "TIMESTAMP"}
    assert unresolved == []


def test_contentplayhead_uses_supplied_value():
    out, replaced, _ = macros.substitute("https://x/q?p=[CONTENTPLAYHEAD]", playhead="00:00:15")
    assert "CONTENTPLAYHEAD" in replaced
    assert "00%3A00%3A15" in out  # url-encoded HH:MM:SS


def test_errorcode_substituted():
    out, replaced, _ = macros.substitute("https://x/e?ec=[ERRORCODE]", errorcode=303)
    assert "ec=303" in out and "ERRORCODE" in replaced


def test_encoded_brackets_handled():
    out, replaced, _ = macros.substitute("https://x/i?cb=%5BCACHEBUSTING%5D")
    assert "%5BCACHEBUSTING%5D" not in out and "CACHEBUSTING" in replaced


def test_unknown_macro_left_in_place():
    out, replaced, unresolved = macros.substitute("https://x/i?z=[SOMETHINGELSE]")
    assert "[SOMETHINGELSE]" in out
    assert unresolved == ["SOMETHINGELSE"] and replaced == []


def test_no_macros_is_noop():
    out, replaced, unresolved = macros.substitute("https://x/i?a=1")
    assert out == "https://x/i?a=1" and not replaced and not unresolved
