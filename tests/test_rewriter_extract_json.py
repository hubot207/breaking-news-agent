"""Tests for the JSON extraction helper that handles common LLM response shapes."""
import json

from src.pipeline.rewriter import _extract_json


def test_plain_json_passthrough():
    s = '{"x": "hello"}'
    assert json.loads(_extract_json(s)) == {"x": "hello"}


def test_strips_json_code_fence():
    s = '```json\n{"x": "hello"}\n```'
    assert json.loads(_extract_json(s)) == {"x": "hello"}


def test_strips_bare_code_fence():
    s = '```\n{"x": "hello"}\n```'
    assert json.loads(_extract_json(s)) == {"x": "hello"}


def test_strips_surrounding_prose():
    s = 'Here is the JSON output:\n\n{"x": "hello"}\n\nHope this helps!'
    assert json.loads(_extract_json(s)) == {"x": "hello"}


def test_handles_leading_whitespace():
    s = '   \n  {"x": "hello"}  '
    assert json.loads(_extract_json(s)) == {"x": "hello"}


def test_handles_nested_object():
    s = '```json\n{"a": {"b": 1}, "c": 2}\n```'
    assert json.loads(_extract_json(s)) == {"a": {"b": 1}, "c": 2}


def test_empty_input_passthrough():
    assert _extract_json("") == ""
