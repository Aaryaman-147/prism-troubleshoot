"""
Tests for DeeplinkIndex's handling of edge-case catalog files — empty,
malformed, or structurally invalid. These scenarios are worth covering
explicitly given the real deeplinks.json is expected from Samsung shortly
before submission: a truncated download, bad export, or copy-paste error
should fail loudly and clearly, not with a cryptic crash.

Run with: pytest tests/test_deeplink_catalog_loading.py -v
"""
import json

import numpy as np
import pytest
from unittest.mock import patch


def fake_embed(text):
    return np.array([1.0, 0.0])


def fake_embed_batch(texts):
    return np.array([[1.0, 0.0] for _ in texts])


@pytest.fixture(autouse=True)
def patched_embeddings():
    with patch("app.pipeline.deeplink_retrieval.embed", side_effect=fake_embed), \
         patch("app.pipeline.deeplink_retrieval.embed_batch", side_effect=fake_embed_batch):
        yield


class TestCatalogLoadingEdgeCases:
    def test_empty_catalog_raises_clear_error(self, tmp_path):
        """
        Regression test: an empty catalog previously crashed with a
        cryptic ZeroDivisionError from score normalization dividing by
        the max of an empty array. Must now fail with a clear message
        instead.
        """
        catalog_path = tmp_path / "empty.json"
        catalog_path.write_text("[]")

        from app.pipeline.deeplink_retrieval import DeeplinkIndex

        with pytest.raises(ValueError, match="empty"):
            DeeplinkIndex(str(catalog_path))

    def test_malformed_json_raises_json_error(self, tmp_path):
        catalog_path = tmp_path / "malformed.json"
        catalog_path.write_text("{not valid json")

        from app.pipeline.deeplink_retrieval import DeeplinkIndex

        with pytest.raises(json.JSONDecodeError):
            DeeplinkIndex(str(catalog_path))

    def test_missing_file_raises_file_not_found(self, tmp_path):
        from app.pipeline.deeplink_retrieval import DeeplinkIndex

        with pytest.raises(FileNotFoundError):
            DeeplinkIndex(str(tmp_path / "does_not_exist.json"))

    def test_entry_missing_required_deeplink_key_raises(self, tmp_path):
        catalog_path = tmp_path / "bad_entries.json"
        catalog_path.write_text(json.dumps([{"description": "no deeplink key here"}]))

        from app.pipeline.deeplink_retrieval import DeeplinkIndex

        with pytest.raises(KeyError):
            DeeplinkIndex(str(catalog_path))

    def test_single_entry_catalog_loads_and_searches(self, tmp_path):
        """Sanity check: the smallest VALID catalog (one entry) should
        work fine — the empty-catalog guard shouldn't be overzealous."""
        catalog_path = tmp_path / "single.json"
        catalog_path.write_text(json.dumps([
            {"deeplink": "bixby://masked/act/test", "description": "test entry"}
        ]))

        from app.pipeline.deeplink_retrieval import DeeplinkIndex

        index = DeeplinkIndex(str(catalog_path))
        assert len(index.entries) == 1
        results = index.search("test query", top_k=1)
        assert len(results) == 1
