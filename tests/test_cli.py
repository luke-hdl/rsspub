"""Tests for the CLI (cli.py) using Click's CliRunner."""

import json
import pytest
from click.testing import CliRunner

from rsspub import feed as feed_module
from rsspub.cli import cli


@pytest.fixture(autouse=True)
def isolated_feed_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(feed_module, "get_feed_dir", lambda: tmp_path)


@pytest.fixture()
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# rsspub feed create
# ---------------------------------------------------------------------------

class TestFeedCreate:
    def test_create_new_collection(self, runner):
        result = runner.invoke(cli, ["feed", "create", "tech"])
        assert result.exit_code == 0
        assert "tech" in result.output

    def test_create_reserved_name(self, runner):
        result = runner.invoke(cli, ["feed", "create", "feed"])
        assert result.exit_code != 0

    def test_create_duplicate_name(self, runner):
        runner.invoke(cli, ["feed", "create", "tech"])
        result = runner.invoke(cli, ["feed", "create", "tech"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# rsspub <name> add / list / remove
# ---------------------------------------------------------------------------

class TestCollectionCommands:
    def setup_method(self):
        # Pre-create via the module directly so we can test CLI independently
        pass

    def test_add_url(self, runner, tmp_path):
        runner.invoke(cli, ["feed", "create", "news"])
        result = runner.invoke(cli, ["news", "add", "https://example.com/rss"])
        assert result.exit_code == 0
        assert "https://example.com/rss" in feed_module.list_urls("news")

    def test_list_urls(self, runner):
        runner.invoke(cli, ["feed", "create", "news"])
        runner.invoke(cli, ["news", "add", "https://a.com/rss"])
        runner.invoke(cli, ["news", "add", "https://b.com/rss"])
        result = runner.invoke(cli, ["news", "list"])
        assert result.exit_code == 0
        assert "https://a.com/rss" in result.output
        assert "https://b.com/rss" in result.output

    def test_list_empty_collection(self, runner):
        runner.invoke(cli, ["feed", "create", "empty"])
        result = runner.invoke(cli, ["empty", "list"])
        assert result.exit_code == 0
        assert "No URLs" in result.output

    def test_remove_url(self, runner):
        runner.invoke(cli, ["feed", "create", "news"])
        runner.invoke(cli, ["news", "add", "https://example.com/rss"])
        result = runner.invoke(cli, ["news", "remove", "https://example.com/rss"])
        assert result.exit_code == 0
        assert feed_module.list_urls("news") == []

    def test_add_to_nonexistent_collection(self, runner):
        result = runner.invoke(cli, ["ghost", "add", "https://example.com/rss"])
        assert result.exit_code != 0

    def test_remove_missing_url(self, runner):
        runner.invoke(cli, ["feed", "create", "news"])
        result = runner.invoke(cli, ["news", "remove", "https://nothere.com/rss"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# rsspub <name> export
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_command(self, runner, tmp_path):
        runner.invoke(cli, ["feed", "create", "news"])
        runner.invoke(cli, ["news", "add", "https://example.com/rss"])
        out = tmp_path / "exported.feed"
        result = runner.invoke(cli, ["news", "export", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        data = json.loads(out.read_text())
        assert "https://example.com/rss" in data["urls"]


# ---------------------------------------------------------------------------
# rsspub <name> epub (mocked fetch)
# ---------------------------------------------------------------------------

class TestEpubCommand:
    """Test epub generation with a mocked feed fetcher."""

    def _make_entry(self, title, link, date_struct=None, content="<p>Body</p>"):
        """Build a fake feedparser entry dict."""
        class FakeEntry:
            pass

        e = FakeEntry()
        e.title = title
        e.id = link
        e.link = link
        e.published_parsed = date_struct
        e.updated_parsed = None
        e.content = [type("C", (), {"value": content})()]
        e.summary = ""
        return e

    def test_epub_all(self, runner, tmp_path, monkeypatch):
        import time
        runner.invoke(cli, ["feed", "create", "myfeed"])
        runner.invoke(cli, ["myfeed", "add", "https://example.com/rss"])

        entry = self._make_entry(
            "Test Article",
            "https://example.com/1",
            time.strptime("2025-06-03", "%Y-%m-%d"),
        )
        monkeypatch.setattr(epub_module := __import__("rsspub.epub", fromlist=["fetch_entries"]), "fetch_entries", lambda url: [entry])
        monkeypatch.setattr(epub_module, "fetch_feed_title", lambda url: "Test Feed")

        out = tmp_path / "out.epub"
        result = runner.invoke(cli, ["myfeed", "epub", "--output", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()

    def test_epub_unconverted(self, runner, tmp_path, monkeypatch):
        import time
        runner.invoke(cli, ["feed", "create", "myfeed"])
        runner.invoke(cli, ["myfeed", "add", "https://example.com/rss"])

        entry = self._make_entry("Article", "https://example.com/1")
        epub_mod = __import__("rsspub.epub", fromlist=["fetch_entries"])
        monkeypatch.setattr(epub_mod, "fetch_entries", lambda url: [entry])
        monkeypatch.setattr(epub_mod, "fetch_feed_title", lambda url: "Test Feed")

        out = tmp_path / "unconverted.epub"
        result = runner.invoke(cli, ["myfeed", "epub", "unconverted", "--output", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()
        # Entry should now be marked converted
        converted = feed_module.get_converted("myfeed")
        assert "https://example.com/1" in converted.get("https://example.com/rss", [])

    def test_epub_date_filter(self, runner, tmp_path, monkeypatch):
        import time
        runner.invoke(cli, ["feed", "create", "myfeed"])
        runner.invoke(cli, ["myfeed", "add", "https://example.com/rss"])

        entries = [
            self._make_entry("June 3", "https://example.com/1", time.strptime("2025-06-03", "%Y-%m-%d")),
            self._make_entry("June 5", "https://example.com/2", time.strptime("2025-06-05", "%Y-%m-%d")),
        ]
        monkeypatch.setattr(epub_mod := __import__("rsspub.epub", fromlist=["fetch_entries"]), "fetch_entries", lambda url: entries)
        monkeypatch.setattr(epub_mod, "fetch_feed_title", lambda url: "Test Feed")

        out = tmp_path / "date.epub"
        result = runner.invoke(cli, ["myfeed", "epub", "2025-06-03", "--output", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert "1 entries" in result.output

    def test_epub_date_range_filter(self, runner, tmp_path, monkeypatch):
        import time
        runner.invoke(cli, ["feed", "create", "myfeed"])
        runner.invoke(cli, ["myfeed", "add", "https://example.com/rss"])

        entries = [
            self._make_entry("June 3", "https://example.com/1", time.strptime("2025-06-03", "%Y-%m-%d")),
            self._make_entry("June 5", "https://example.com/2", time.strptime("2025-06-05", "%Y-%m-%d")),
            self._make_entry("June 10", "https://example.com/3", time.strptime("2025-06-10", "%Y-%m-%d")),
        ]
        monkeypatch.setattr(epub_mod := __import__("rsspub.epub", fromlist=["fetch_entries"]), "fetch_entries", lambda url: entries)
        monkeypatch.setattr(epub_mod, "fetch_feed_title", lambda url: "Test Feed")

        out = tmp_path / "range.epub"
        result = runner.invoke(cli, ["myfeed", "epub", "2025-06-03:2025-06-06", "--output", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert "2 entries" in result.output

    def test_epub_no_entries_no_file(self, runner, tmp_path, monkeypatch):
        runner.invoke(cli, ["feed", "create", "myfeed"])
        runner.invoke(cli, ["myfeed", "add", "https://example.com/rss"])

        epub_mod = __import__("rsspub.epub", fromlist=["fetch_entries"])
        monkeypatch.setattr(epub_mod, "fetch_entries", lambda url: [])
        monkeypatch.setattr(epub_mod, "fetch_feed_title", lambda url: "Test Feed")

        out = tmp_path / "empty.epub"
        result = runner.invoke(cli, ["myfeed", "epub", "--output", str(out)])
        assert result.exit_code == 0
        assert not out.exists()
        assert "No entries" in result.output

    def test_epub_max_filter(self, runner, tmp_path, monkeypatch):
        """max N should include only the first N (newest) entries per feed."""
        import time
        runner.invoke(cli, ["feed", "create", "myfeed"])
        runner.invoke(cli, ["myfeed", "add", "https://example.com/rss"])

        entries = [
            self._make_entry("Article 1", "https://example.com/1", time.strptime("2025-06-03", "%Y-%m-%d")),
            self._make_entry("Article 2", "https://example.com/2", time.strptime("2025-06-02", "%Y-%m-%d")),
            self._make_entry("Article 3", "https://example.com/3", time.strptime("2025-06-01", "%Y-%m-%d")),
        ]
        epub_mod = __import__("rsspub.epub", fromlist=["fetch_entries"])
        monkeypatch.setattr(epub_mod, "fetch_entries", lambda url: entries)
        monkeypatch.setattr(epub_mod, "fetch_feed_title", lambda url: "Test Feed")

        out = tmp_path / "max.epub"
        result = runner.invoke(cli, ["myfeed", "epub", "max", "2", "--output", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert "2 entries" in result.output

    def test_epub_max_filter_default_filename(self, runner, tmp_path, monkeypatch):
        """max filter should produce a filename like <name>_max<N>.epub."""
        import time
        runner.invoke(cli, ["feed", "create", "myfeed"])
        runner.invoke(cli, ["myfeed", "add", "https://example.com/rss"])

        entry = self._make_entry("Article 1", "https://example.com/1",
                                 time.strptime("2025-06-03", "%Y-%m-%d"))
        epub_mod = __import__("rsspub.epub", fromlist=["fetch_entries"])
        monkeypatch.setattr(epub_mod, "fetch_entries", lambda url: [entry])
        monkeypatch.setattr(epub_mod, "fetch_feed_title", lambda url: "Test Feed")

        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["myfeed", "epub", "max", "5"])
            assert result.exit_code == 0, result.output
            assert "myfeed_max5.epub" in result.output

    def test_epub_max_filter_no_count(self, runner, tmp_path, monkeypatch):
        """max without a count should produce an error."""
        runner.invoke(cli, ["feed", "create", "myfeed"])
        runner.invoke(cli, ["myfeed", "add", "https://example.com/rss"])

        epub_mod = __import__("rsspub.epub", fromlist=["fetch_entries"])
        monkeypatch.setattr(epub_mod, "fetch_entries", lambda url: [])
        monkeypatch.setattr(epub_mod, "fetch_feed_title", lambda url: "Test Feed")

        result = runner.invoke(cli, ["myfeed", "epub", "max"])
        assert result.exit_code != 0

    def test_epub_max_larger_than_available(self, runner, tmp_path, monkeypatch):
        """max N where N > total entries should return all entries."""
        import time
        runner.invoke(cli, ["feed", "create", "myfeed"])
        runner.invoke(cli, ["myfeed", "add", "https://example.com/rss"])

        entries = [
            self._make_entry("Article 1", "https://example.com/1", time.strptime("2025-06-03", "%Y-%m-%d")),
            self._make_entry("Article 2", "https://example.com/2", time.strptime("2025-06-02", "%Y-%m-%d")),
        ]
        epub_mod = __import__("rsspub.epub", fromlist=["fetch_entries"])
        monkeypatch.setattr(epub_mod, "fetch_entries", lambda url: entries)
        monkeypatch.setattr(epub_mod, "fetch_feed_title", lambda url: "Test Feed")

        out = tmp_path / "max_large.epub"
        result = runner.invoke(cli, ["myfeed", "epub", "max", "100", "--output", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert "2 entries" in result.output

