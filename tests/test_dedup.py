"""Dedup unit tests - no DB required for the pure url-hash logic."""
from src.pipeline.dedup import url_hash


def test_url_hash_normalises_trailing_slash():
    assert url_hash("https://example.com/news/") == url_hash("https://example.com/news")


def test_url_hash_strips_query():
    assert url_hash("https://example.com/x?utm=foo") == url_hash("https://example.com/x")


def test_url_hash_case_insensitive():
    assert url_hash("https://EXAMPLE.com/X") == url_hash("https://example.com/x")


def test_different_paths_differ():
    assert url_hash("https://example.com/a") != url_hash("https://example.com/b")
