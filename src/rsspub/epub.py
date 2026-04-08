"""RSS fetching and EPUB generation utilities."""

import hashlib
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date
from typing import Optional

import feedparser
from ebooklib import epub


# ---------------------------------------------------------------------------
# Image-embedding helpers
# ---------------------------------------------------------------------------

_IMG_SRC_RE = re.compile(
    r'(<img\b[^>]*?\bsrc=)(["\'])(https?://[^"\'>\s]+)\2',
    re.IGNORECASE | re.DOTALL,
)

_MEDIA_TYPE_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}


def _embed_images(html_content: str, book: epub.EpubBook, image_cache: dict[str, str]) -> str:
    """Download images referenced in *html_content* and embed them in *book*.

    Returns a copy of *html_content* with ``src`` attributes updated to point
    at the embedded images.  Images that cannot be fetched are left unchanged.

    The *image_cache* mapping (``{url: file_name}``) is updated in-place so
    the same image is not downloaded more than once across multiple chapters.
    """

    _MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB safety limit

    def _replace(match: re.Match) -> str:
        prefix = match.group(1)
        quote = match.group(2)
        url = match.group(3)

        if url in image_cache:
            return f"{prefix}{quote}{image_cache[url]}{quote}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "rsspub/0.1"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read(_MAX_IMAGE_BYTES)
                content_type_header = resp.headers.get("Content-Type", "image/jpeg")
        except (urllib.error.URLError, OSError, TimeoutError):
            return match.group(0)

        media_type = content_type_header.split(";")[0].strip().lower()
        ext = _MEDIA_TYPE_TO_EXT.get(media_type, "")
        if not ext:
            _, url_ext = os.path.splitext(urllib.parse.urlparse(url).path)
            ext = url_ext.lower() if url_ext else ".img"

        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        file_name = f"images/{url_hash}{ext}"

        img_item = epub.EpubImage()
        img_item.file_name = file_name
        img_item.media_type = media_type
        img_item.content = data
        book.add_item(img_item)

        image_cache[url] = file_name
        return f"{prefix}{quote}{file_name}{quote}"

    return _IMG_SRC_RE.sub(_replace, html_content)


# ---------------------------------------------------------------------------
# RSS helpers
# ---------------------------------------------------------------------------

def fetch_entries(url: str) -> list:
    """Fetch and return all entries from the RSS/Atom feed at *url*."""
    parsed = feedparser.parse(url)
    return list(parsed.entries)


def fetch_feed_title(url: str) -> str:
    """Return the title of the RSS/Atom feed at *url*, or *url* if unavailable."""
    parsed = feedparser.parse(url)
    return getattr(parsed.feed, "title", None) or url


def get_entry_id(entry) -> str:
    """Return a stable unique identifier for a feed *entry*."""
    for attr in ("id", "link", "title"):
        value = getattr(entry, attr, None)
        if value:
            return value
    return str(uuid.uuid4())


def get_entry_date(entry) -> Optional[date]:
    """Return the publication date of *entry*, or ``None`` if unavailable."""
    for attr in ("published_parsed", "updated_parsed"):
        struct = getattr(entry, attr, None)
        if struct:
            try:
                return date(struct.tm_year, struct.tm_mon, struct.tm_mday)
            except (ValueError, AttributeError):
                continue
    return None


def get_entry_content(entry) -> str:
    """Return the HTML (or plain-text) content of *entry*."""
    content_list = getattr(entry, "content", None)
    if content_list:
        return content_list[0].value
    return getattr(entry, "summary", "") or ""


def get_entry_title(entry) -> str:
    """Return the title of *entry*, falling back to 'Untitled'."""
    return getattr(entry, "title", None) or "Untitled"


# ---------------------------------------------------------------------------
# EPUB helpers
# ---------------------------------------------------------------------------

def _slugify(text: str, index: int) -> str:
    """Return a filesystem-safe slug based on *text* and *index*."""
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    return f"chapter_{index:04d}_{slug[:40]}" if slug else f"chapter_{index:04d}"


def generate_epub(title: str, feed_groups: list, output_path: str) -> None:
    """Write an EPUB file to *output_path*.

    Parameters
    ----------
    title:
        The book title.
    feed_groups:
        A list of ``(feed_title, entries)`` tuples where *entries* is a list
        of ``(entry_title, content_html, entry_date_or_None)`` tuples.
    output_path:
        Destination file path (should end with ``.epub``).
    """
    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(title)
    book.set_language("en")

    css = epub.EpubItem(
        uid="style_default",
        file_name="style/default.css",
        media_type="text/css",
        content="img { max-width: 100%; height: auto; }",
    )
    book.add_item(css)

    image_cache: dict[str, str] = {}
    chapters = []
    toc = []
    chapter_index = 0

    for feed_title, entries in feed_groups:
        feed_links = []
        for entry_title, content, entry_date in entries:
            content = _embed_images(content, book, image_cache)
            chapter = epub.EpubHtml(
                title=entry_title,
                file_name=f"{_slugify(entry_title, chapter_index)}.xhtml",
                lang="en",
            )
            chapter.add_item(css)
            date_str = f"<p><em>{entry_date}</em></p>" if entry_date else ""
            chapter.content = (
                f"<html><body>"
                f"<h1>{entry_title}</h1>"
                f"{date_str}"
                f"{content}"
                f"</body></html>"
            )
            book.add_item(chapter)
            chapters.append(chapter)

            toc_title = f"{entry_date}: {entry_title}" if entry_date else entry_title
            feed_links.append(epub.Link(chapter.file_name, toc_title, chapter.id))
            chapter_index += 1

        toc.append((epub.Section(feed_title), feed_links))

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapters

    epub.write_epub(output_path, book)


# ---------------------------------------------------------------------------
# High-level entry collection
# ---------------------------------------------------------------------------

def collect_entries(
    urls: list,
    *,
    filter_mode: str = "all",
    converted: Optional[dict] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    max_per_feed: Optional[int] = None,
) -> tuple[list, dict]:
    """Fetch entries from all *urls* according to the filter.

    Parameters
    ----------
    urls:
        List of feed URLs.
    filter_mode:
        One of ``"all"``, ``"unconverted"``, ``"date"``, or ``"max"``.
    converted:
        Mapping of ``{url: [entry_id, ...]}`` for already-converted entries.
        Required when *filter_mode* is ``"unconverted"``.
    start_date / end_date:
        Date range (inclusive on both ends).
        Required when *filter_mode* is ``"date"``.
    max_per_feed:
        Maximum number of entries to include per feed, favouring the newest.
        Required when *filter_mode* is ``"max"``.

    Returns
    -------
    feed_groups:
        List of ``(feed_title, entries)`` tuples where *entries* is a list of
        ``(entry_title, content_html, entry_date)`` tuples ready for
        :func:`generate_epub`.
    newly_converted:
        Mapping of ``{url: [entry_id, ...]}`` for entries included in this
        batch (useful for updating the "converted" record).
    """
    converted = converted or {}
    feed_groups: list = []
    newly_converted: dict = {}

    for url in urls:
        feed_title = fetch_feed_title(url)
        raw_entries = fetch_entries(url)
        url_converted = converted.get(url, [])
        url_new_ids: list = []
        url_entries: list = []

        for entry in raw_entries:
            eid = get_entry_id(entry)
            edate = get_entry_date(entry)

            if filter_mode == "unconverted":
                if eid in url_converted:
                    continue
            elif filter_mode == "date":
                if edate is None:
                    continue
                if start_date and edate < start_date:
                    continue
                if end_date and edate > end_date:
                    continue

            url_entries.append((get_entry_title(entry), get_entry_content(entry), edate))
            url_new_ids.append(eid)

        # Apply max-per-feed limit; feedparser returns newest entries first so
        # slicing from the front keeps the most recent ones.
        if max_per_feed is not None and len(url_entries) > max_per_feed:
            url_entries = url_entries[:max_per_feed]
            url_new_ids = url_new_ids[:max_per_feed]

        if url_entries:
            feed_groups.append((feed_title, url_entries))

        if url_new_ids:
            newly_converted[url] = url_new_ids

    return feed_groups, newly_converted
