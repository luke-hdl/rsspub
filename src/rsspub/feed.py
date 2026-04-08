"""Feed collection management: create, load, save, and manipulate .feed files."""

import json
from pathlib import Path

import platformdirs

RESERVED_NAMES = {"feed"}


def get_feed_dir() -> Path:
    """Return the directory where feed collection files are stored."""
    data_dir = Path(platformdirs.user_data_dir("rsspub"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_feed_path(name: str) -> Path:
    """Return the path to the .feed file for *name*."""
    return get_feed_dir() / f"{name}.feed"


def feed_exists(name: str) -> bool:
    """Return True if a feed collection named *name* exists."""
    return get_feed_path(name).exists()


def create_feed(name: str) -> dict:
    """Create a new, empty feed collection.

    Raises ``ValueError`` if the name is reserved or the collection already
    exists.
    """
    if name in RESERVED_NAMES:
        raise ValueError(f"'{name}' is a reserved name and cannot be used for a feed collection.")
    if feed_exists(name):
        raise ValueError(f"Feed collection '{name}' already exists.")
    data: dict = {"name": name, "urls": [], "converted": {}}
    _save(name, data)
    return data


def load_feed(name: str) -> dict:
    """Load and return the feed collection data for *name*.

    Raises ``FileNotFoundError`` if the collection does not exist.
    """
    path = get_feed_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Feed collection '{name}' not found.")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _save(name: str, data: dict) -> None:
    """Persist *data* to the .feed file for *name*."""
    path = get_feed_path(name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def add_url(name: str, url: str) -> None:
    """Add *url* to the feed collection *name*.

    Raises ``ValueError`` if *url* is already present.
    """
    data = load_feed(name)
    if url in data["urls"]:
        raise ValueError(f"'{url}' is already in feed collection '{name}'.")
    data["urls"].append(url)
    _save(name, data)


def list_urls(name: str) -> list:
    """Return the list of URLs in feed collection *name*."""
    return load_feed(name)["urls"]


def remove_url(name: str, url: str) -> None:
    """Remove *url* from feed collection *name*.

    Raises ``ValueError`` if *url* is not present.
    """
    data = load_feed(name)
    if url not in data["urls"]:
        raise ValueError(f"'{url}' is not in feed collection '{name}'.")
    data["urls"].remove(url)
    data.get("converted", {}).pop(url, None)
    _save(name, data)


def export_feed(name: str, output_path: str) -> None:
    """Export feed collection *name* to *output_path* as a .feed JSON file."""
    data = load_feed(name)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def get_converted(name: str) -> dict:
    """Return a mapping of ``{url: [entry_id, ...]}`` for converted entries."""
    return load_feed(name).get("converted", {})


def mark_converted(name: str, url: str, entry_ids: list) -> None:
    """Record that *entry_ids* from *url* have been converted to EPUB."""
    data = load_feed(name)
    converted = data.setdefault("converted", {})
    seen = set(converted.setdefault(url, []))
    for eid in entry_ids:
        if eid not in seen:
            converted[url].append(eid)
            seen.add(eid)
    _save(name, data)
