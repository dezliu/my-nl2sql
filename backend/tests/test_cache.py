import pytest

from backend.cache.llm_cache import LlmCache, _cosine_similarity


def test_hash_key_deterministic():
    k1 = LlmCache._hash_key("sql_generator", "gpt-4o-mini", "hello", {"a": 1})
    k2 = LlmCache._hash_key("sql_generator", "gpt-4o-mini", "hello", {"a": 1})
    k3 = LlmCache._hash_key("sql_generator", "gpt-4o-mini", "hello", {"a": 2})
    assert k1 == k2
    assert k1 != k3


def test_cosine_similarity():
    assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
