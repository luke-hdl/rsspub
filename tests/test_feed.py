"""Tests for feed collection management (feed.py)."""

import json
import pytest

from rsspub import feed as feed_module


@pytest.fixture(autouse=True)
def isolated_feed_dir(tmp_path, monkeypatch):
    """Redirect feed storage to a temporary directory for each test."""
    monkeypatch.setattr(feed_module, "get_feed_dir", lambda: tmp_path)


# ---------------------------------------------------------------------------
# create_feed
# ---------------------------------------------------------------------------

class TestCreateFeed:
    def test_creates_feed_file(self, tmp_path):
        feed_module.create_feed("news")
        assert (tmp_path / "news.feed").exists()

    def test_feed_file_has_correct_structure(self, tmp_path):
        feed_module.create_feed("news")
        data = json.loads((tmp_path / "news.feed").read_text())
        assert data["name"] == "news"
        assert data["urls"] == []
        assert data["converted"] == {}

    def test_reserved_name_raises(self):
        with pytest.raises(ValueError, match="reserved"):
            feed_module.create_feed("feed")

    def test_duplicate_name_raises(self):
        feed_module.create_feed("news")
        with pytest.raises(ValueError, match="already exists"):
            feed_module.create_feed("news")


# ---------------------------------------------------------------------------
# load_feed / feed_exists
# ---------------------------------------------------------------------------

class TestLoadFeed:
    def test_load_existing_feed(self):
        feed_module.create_feed("tech")
        data = feed_module.load_feed("tech")
        assert data["name"] == "tech"

    def test_load_missing_feed_raises(self):
        with pytest.raises(FileNotFoundError):
            feed_module.load_feed("nonexistent")

    def test_feed_exists_true(self):
        feed_module.create_feed("tech")
        assert feed_module.feed_exists("tech")

    def test_feed_exists_false(self):
        assert not feed_module.feed_exists("nonexistent")


# ---------------------------------------------------------------------------
# add_url / list_urls / remove_url
# ---------------------------------------------------------------------------

class TestUrlManagement:
    def setup_method(self):
        feed_module.create_feed("myfeed")

    def test_add_and_list(self):
        feed_module.add_url("myfeed", "https://example.com/rss")
        assert feed_module.list_urls("myfeed") == ["https://example.com/rss"]

    def test_add_multiple(self):
        feed_module.add_url("myfeed", "https://a.com/rss")
        feed_module.add_url("myfeed", "https://b.com/rss")
        assert len(feed_module.list_urls("myfeed")) == 2

    def test_add_duplicate_raises(self):
        feed_module.add_url("myfeed", "https://example.com/rss")
        with pytest.raises(ValueError, match="already in"):
            feed_module.add_url("myfeed", "https://example.com/rss")

    def test_remove_existing_url(self):
        feed_module.add_url("myfeed", "https://example.com/rss")
        feed_module.remove_url("myfeed", "https://example.com/rss")
        assert feed_module.list_urls("myfeed") == []

    def test_remove_missing_url_raises(self):
        with pytest.raises(ValueError, match="not in"):
            feed_module.remove_url("myfeed", "https://nothere.com/rss")

    def test_remove_also_clears_converted(self, tmp_path):
        url = "https://example.com/rss"
        feed_module.add_url("myfeed", url)
        feed_module.mark_converted("myfeed", url, ["id1"])
        feed_module.remove_url("myfeed", url)
        assert url not in feed_module.get_converted("myfeed")


# ---------------------------------------------------------------------------
# export_feed
# ---------------------------------------------------------------------------

class TestExportFeed:
    def test_export_creates_file(self, tmp_path):
        feed_module.create_feed("export_test")
        feed_module.add_url("export_test", "https://example.com/rss")
        out = tmp_path / "out.feed"
        feed_module.export_feed("export_test", str(out))
        assert out.exists()
        data = json.loads(out.read_text())
        assert "https://example.com/rss" in data["urls"]


# ---------------------------------------------------------------------------
# mark_converted / get_converted
# ---------------------------------------------------------------------------

class TestConvertedTracking:
    def setup_method(self):
        feed_module.create_feed("convfeed")
        feed_module.add_url("convfeed", "https://example.com/rss")

    def test_mark_and_get(self):
        feed_module.mark_converted("convfeed", "https://example.com/rss", ["id1", "id2"])
        converted = feed_module.get_converted("convfeed")
        assert converted["https://example.com/rss"] == ["id1", "id2"]

    def test_mark_idempotent(self):
        url = "https://example.com/rss"
        feed_module.mark_converted("convfeed", url, ["id1"])
        feed_module.mark_converted("convfeed", url, ["id1", "id2"])
        converted = feed_module.get_converted("convfeed")
        assert converted[url].count("id1") == 1
        assert "id2" in converted[url]
