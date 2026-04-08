"""Tests for EPUB generation helpers in epub.py, including image embedding."""

import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from rsspub import epub as epub_module


# ---------------------------------------------------------------------------
# _embed_images
# ---------------------------------------------------------------------------

class TestEmbedImages:
    """Unit tests for the _embed_images helper."""

    def _make_mock_response(self, data: bytes, content_type: str = "image/jpeg"):
        """Build a mock urllib response."""
        resp = MagicMock()
        resp.read.return_value = data
        resp.headers.get.return_value = content_type
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    def _make_book(self):
        from ebooklib import epub
        book = epub.EpubBook()
        book.set_identifier("test-id")
        book.set_title("Test")
        book.set_language("en")
        return book

    def test_replaces_http_img_src(self):
        book = self._make_book()
        image_cache = {}
        fake_image = b"\xff\xd8\xff"  # JPEG magic bytes
        html = '<img src="http://example.com/image.jpg" alt="test"/>'

        resp = self._make_mock_response(fake_image, "image/jpeg")
        with patch("urllib.request.urlopen", return_value=resp):
            result = epub_module._embed_images(html, book, image_cache)

        assert "http://example.com/image.jpg" not in result
        assert 'src="images/' in result

    def test_replaces_https_img_src(self):
        book = self._make_book()
        image_cache = {}
        fake_image = b"\x89PNG"  # PNG magic bytes
        html = '<img src="https://example.com/photo.png"/>'

        resp = self._make_mock_response(fake_image, "image/png")
        with patch("urllib.request.urlopen", return_value=resp):
            result = epub_module._embed_images(html, book, image_cache)

        assert "https://example.com/photo.png" not in result
        assert 'src="images/' in result
        assert ".png" in result

    def test_embedded_image_added_to_book(self):
        book = self._make_book()
        image_cache = {}
        fake_image = b"\xff\xd8\xff"
        html = '<img src="https://example.com/img.jpg"/>'

        resp = self._make_mock_response(fake_image, "image/jpeg")
        with patch("urllib.request.urlopen", return_value=resp):
            epub_module._embed_images(html, book, image_cache)

        # Book should now contain the image item
        items = list(book.get_items())
        image_items = [it for it in items if it.media_type == "image/jpeg"]
        assert len(image_items) == 1
        assert image_items[0].content == fake_image

    def test_same_url_downloaded_once(self):
        book = self._make_book()
        image_cache = {}
        fake_image = b"\xff\xd8\xff"
        url = "https://example.com/same.jpg"
        html = f'<img src="{url}"/><img src="{url}"/>'

        resp = self._make_mock_response(fake_image, "image/jpeg")
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            result = epub_module._embed_images(html, book, image_cache)

        # urlopen called only once despite two img tags with same URL
        assert mock_open.call_count == 1
        # Both img tags should be updated to same local path
        assert result.count('src="images/') == 2

    def test_failed_download_leaves_src_unchanged(self):
        book = self._make_book()
        image_cache = {}
        original_html = '<img src="https://example.com/broken.jpg"/>'

        with patch("urllib.request.urlopen", side_effect=OSError("network error")):
            result = epub_module._embed_images(original_html, book, image_cache)

        assert result == original_html

    def test_non_http_src_left_unchanged(self):
        book = self._make_book()
        image_cache = {}
        html = '<img src="data:image/png;base64,abc123"/>'

        result = epub_module._embed_images(html, book, image_cache)

        assert result == html

    def test_image_cache_populated(self):
        book = self._make_book()
        image_cache = {}
        fake_image = b"\xff\xd8\xff"
        url = "https://example.com/cached.jpg"
        html = f'<img src="{url}"/>'

        resp = self._make_mock_response(fake_image, "image/jpeg")
        with patch("urllib.request.urlopen", return_value=resp):
            epub_module._embed_images(html, book, image_cache)

        assert url in image_cache
        assert image_cache[url].startswith("images/")
        assert image_cache[url].endswith(".jpg")

    def test_cache_reused_across_calls(self):
        book = self._make_book()
        image_cache = {}
        fake_image = b"\xff\xd8\xff"
        url = "https://example.com/reused.jpg"

        resp = self._make_mock_response(fake_image, "image/jpeg")
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            epub_module._embed_images(f'<img src="{url}"/>', book, image_cache)
            epub_module._embed_images(f'<img src="{url}"/>', book, image_cache)

        # Second call reuses cache; urlopen still called only once
        assert mock_open.call_count == 1

    def test_unknown_media_type_uses_url_extension(self):
        book = self._make_book()
        image_cache = {}
        fake_image = b"GIF89a"
        html = '<img src="https://example.com/anim.gif"/>'

        resp = self._make_mock_response(fake_image, "application/octet-stream")
        with patch("urllib.request.urlopen", return_value=resp):
            result = epub_module._embed_images(html, book, image_cache)

        assert ".gif" in result

    def test_single_quoted_src(self):
        book = self._make_book()
        image_cache = {}
        fake_image = b"\xff\xd8\xff"
        html = "<img src='https://example.com/sq.jpg'/>"

        resp = self._make_mock_response(fake_image, "image/jpeg")
        with patch("urllib.request.urlopen", return_value=resp):
            result = epub_module._embed_images(html, book, image_cache)

        assert "https://example.com/sq.jpg" not in result


# ---------------------------------------------------------------------------
# generate_epub with image content
# ---------------------------------------------------------------------------

class TestGenerateEpubImages:
    """Integration tests verifying images are embedded in the written EPUB."""

    def test_epub_contains_embedded_image(self, tmp_path):
        fake_image = b"\xff\xd8\xff\xe0"
        url = "https://example.com/comic.jpg"
        feed_groups = [("My Comic Feed", [("Strip 1", f'<img src="{url}"/>', None)])]

        resp = MagicMock()
        resp.read.return_value = fake_image
        resp.headers.get.return_value = "image/jpeg"
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        out = tmp_path / "out.epub"
        with patch("urllib.request.urlopen", return_value=resp):
            epub_module.generate_epub("My Comic", feed_groups, str(out))

        assert out.exists()
        with zipfile.ZipFile(str(out)) as zf:
            names = zf.namelist()
            image_files = [n for n in names if "images/" in n]
            assert len(image_files) == 1
            image_data = zf.read(image_files[0])
            assert image_data == fake_image

    def test_epub_chapter_references_local_image(self, tmp_path):
        fake_image = b"\xff\xd8\xff"
        url = "https://example.com/page1.jpg"
        feed_groups = [("Comic Feed", [("Chapter 1", f'<p><img src="{url}" alt="page"/></p>', None)])]

        resp = MagicMock()
        resp.read.return_value = fake_image
        resp.headers.get.return_value = "image/jpeg"
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        out = tmp_path / "comic.epub"
        with patch("urllib.request.urlopen", return_value=resp):
            epub_module.generate_epub("Comic", feed_groups, str(out))

        with zipfile.ZipFile(str(out)) as zf:
            chapter_files = [n for n in zf.namelist() if n.endswith(".xhtml")]
            assert chapter_files
            chapter_content = zf.read(chapter_files[0]).decode()
            # The src should now point to the local images/ path
            assert url not in chapter_content
            assert "images/" in chapter_content


# ---------------------------------------------------------------------------
# generate_epub ToC structure
# ---------------------------------------------------------------------------

class TestGenerateEpubToc:
    """Tests verifying the Table of Contents is grouped by feed with dates."""

    def test_toc_grouped_by_feed(self, tmp_path):
        from datetime import date as date_type
        feed_groups = [
            ("Feed A", [
                ("Entry 1", "<p>Body 1</p>", date_type(2025, 2, 1)),
            ]),
            ("Feed B", [
                ("Entry 2", "<p>Body 2</p>", date_type(2025, 2, 1)),
                ("Entry 3", "<p>Body 3</p>", date_type(2025, 2, 2)),
            ]),
        ]
        out = tmp_path / "toc.epub"
        epub_module.generate_epub("My Book", feed_groups, str(out))

        assert out.exists()
        # Inspect the nav document for ToC structure
        with zipfile.ZipFile(str(out)) as zf:
            nav_files = [n for n in zf.namelist() if "nav" in n and n.endswith(".xhtml")]
            assert nav_files
            nav_content = zf.read(nav_files[0]).decode()

        # Feed names appear as section headings
        assert "Feed A" in nav_content
        assert "Feed B" in nav_content
        # Entries are shown with date prefix
        assert "2025-02-01: Entry 1" in nav_content
        assert "2025-02-01: Entry 2" in nav_content
        assert "2025-02-02: Entry 3" in nav_content

    def test_toc_entry_without_date_shows_title_only(self, tmp_path):
        feed_groups = [
            ("Feed A", [
                ("Undated Entry", "<p>No date here</p>", None),
            ]),
        ]
        out = tmp_path / "nodates.epub"
        epub_module.generate_epub("My Book", feed_groups, str(out))

        with zipfile.ZipFile(str(out)) as zf:
            nav_files = [n for n in zf.namelist() if "nav" in n and n.endswith(".xhtml")]
            nav_content = zf.read(nav_files[0]).decode()

        assert "Undated Entry" in nav_content
        # No "None:" prefix should appear
        assert "None:" not in nav_content


# ---------------------------------------------------------------------------
# generate_epub CSS / image aspect-ratio
# ---------------------------------------------------------------------------

class TestGenerateEpubCss:
    """Tests verifying that image-sizing CSS is embedded in the EPUB."""

    def test_epub_contains_css_file(self, tmp_path):
        feed_groups = [("Feed", [("Entry", "<p>text</p>", None)])]
        out = tmp_path / "css.epub"
        epub_module.generate_epub("Book", feed_groups, str(out))

        with zipfile.ZipFile(str(out)) as zf:
            css_files = [n for n in zf.namelist() if n.endswith(".css")]
            assert css_files, "No CSS file found in EPUB"
            css_content = zf.read(css_files[0]).decode()

        assert "max-width" in css_content
        assert "height" in css_content

    def test_chapter_references_css(self, tmp_path):
        feed_groups = [("Feed", [("Entry", "<p>text</p>", None)])]
        out = tmp_path / "cssref.epub"
        epub_module.generate_epub("Book", feed_groups, str(out))

        with zipfile.ZipFile(str(out)) as zf:
            chapter_files = [n for n in zf.namelist() if n.endswith(".xhtml") and "nav" not in n]
            assert chapter_files
            chapter_content = zf.read(chapter_files[0]).decode()

        assert ".css" in chapter_content
