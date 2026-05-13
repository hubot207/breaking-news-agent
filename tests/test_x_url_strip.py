"""Tests for the X adapter's URL stripping.

X charges $0.20 per URL post vs $0.015 for plain text - 13x premium. This
defense-in-depth strips any URL the LLM slipped past the prompt.
"""
from src.adapters.x import _strip_urls


def test_no_url_passthrough():
    text = "Anthropic shipped Claude 4. Big news."
    cleaned, n = _strip_urls(text)
    assert cleaned == text
    assert n == 0


def test_strips_https_url():
    text = "Anthropic shipped Claude 4. Read more: https://anthropic.com/blog/claude-4"
    cleaned, n = _strip_urls(text)
    assert "anthropic.com" not in cleaned
    assert "https" not in cleaned
    assert n == 1
    assert cleaned == "Anthropic shipped Claude 4. Read more"


def test_strips_http_url():
    text = "Visit http://example.com for more"
    cleaned, n = _strip_urls(text)
    assert "example.com" not in cleaned
    assert n == 1


def test_strips_t_co_url():
    text = "More at t.co/abc123 today"
    cleaned, n = _strip_urls(text)
    assert "t.co" not in cleaned
    assert n == 1


def test_strips_multiple_urls():
    text = "See https://a.com and also https://b.com for details"
    cleaned, n = _strip_urls(text)
    assert "a.com" not in cleaned
    assert "b.com" not in cleaned
    assert n == 2


def test_collapses_whitespace_after_strip():
    text = "Apple unveils Vision Pro 2 https://example.com  here"
    cleaned, _ = _strip_urls(text)
    # Should not have double spaces left over
    assert "  " not in cleaned


def test_strips_trailing_punctuation_after_url_removed():
    text = "Apple unveils new product. Read more: https://example.com"
    cleaned, n = _strip_urls(text)
    assert n == 1
    # The trailing ": " should be cleaned up - no dangling colons/dashes
    assert not cleaned.endswith(":")
    assert not cleaned.endswith("-")
    assert not cleaned.endswith(",")


def test_preserves_text_after_url_strip():
    text = "Claude 4 launched (https://anthropic.com/blog) and benchmarks are good"
    cleaned, n = _strip_urls(text)
    assert n == 1
    assert "Claude 4" in cleaned
    assert "benchmarks are good" in cleaned
    assert "anthropic.com" not in cleaned
