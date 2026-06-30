import json

import numpy as np
import pytest

from backend.cache.llm_cache import LlmCache, _cosine_similarity
from backend.rag.retriever import HybridRetriever


def test_hash_key_deterministic():
    k1 = LlmCache._hash_key("sql_generator", "gpt-4o-mini", "hello", {"a": 1})
    k2 = LlmCache._hash_key("sql_generator", "gpt-4o-mini", "hello", {"a": 1})
    k3 = LlmCache._hash_key("sql_generator", "gpt-4o-mini", "hello", {"a": 2})
    assert k1 == k2
    assert k1 != k3


def test_cosine_similarity():
    assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_embed_dense_json_serializable():
    class FakeDenseModel:
        def embed(self, texts):
            yield np.array([0.1, 0.2, 0.3], dtype=np.float32)

    retriever = object.__new__(HybridRetriever)
    retriever.dense_model = FakeDenseModel()
    vec = retriever._embed_dense("test")
    json.dumps(vec)
    assert all(type(x) is float for x in vec)
