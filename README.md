# rsspub

An RSS reader that converts your feeds to EPUB ebook files. This is a small hobby project I put together for my Xteink x4; given the simplicity of the project, I heavily utilized Copilot to keep things going at a rapid clip. 

The project is finished; I don't expect to do any further development on it unless a new need arises in my personal use case. 

Given the heavy use of Copilot, much of RSSPub is inherently uncopyrightable (due to "machine authorship".) Therefore, please consider the whole project to be in the public domain, if you would like to do anything with it. 

---

## Requirements

- Python 3.9 or newer

## Installation

Navigate to the directory in which you have cloned this repo, then: 

```bash
pip install .
```
---

## Quick Start

```bash
# 1. Create a feed collection
rsspub feed create mynews

# 2. Add one or more RSS/Atom feed URLs
rsspub mynews add https://feeds.example.com/rss

# 3. Generate an EPUB with all current entries
rsspub mynews epub
```

---

## Concepts

rsspub organises RSS/Atom feed URLs into named **collections**.  Each
collection is stored as a small JSON file (`.feed`) in your OS user-data
directory.  You can have as many collections as you like (e.g. one for
"tech news", another for "podcasts").

---

## Commands

### `rsspub feed create <name>`

Create a new, empty feed collection.

```bash
rsspub feed create tech
```

> **Note:** The name `feed` is reserved and cannot be used.

---

### `rsspub <name> add <url>`

Add an RSS or Atom feed URL to the named collection.

```bash
rsspub tech add https://feeds.arstechnica.com/arstechnica/index
rsspub tech add https://www.theverge.com/rss/index.xml
```

---

### `rsspub <name> list`

List all URLs currently in the named collection.

```bash
rsspub tech list
```

---

### `rsspub <name> remove <url>`

Remove a URL from the named collection.

```bash
rsspub tech remove https://www.theverge.com/rss/index.xml
```

---

### `rsspub <name> export <output_path>`

Export the feed collection to a `.feed` JSON file (useful for backup or
sharing your URL list).

```bash
rsspub tech export ~/backups/tech.feed
```

---

### `rsspub <name> epub [filter] [--output <path>]`

Fetch all feeds in the collection and generate an EPUB file.

```bash
rsspub tech epub
```

#### Filter options

| Filter | Description |
|---|---|
| *(none)* | Include **all** entries from every feed |
| `unconverted` | Include only entries that have **not** been included in a previous `epub unconverted` run |
| `YYYY-MM-DD` | Include entries published on a **specific date** |
| `YYYY-MM-DD:YYYY-MM-DD` | Include entries published within a **date range** (both ends inclusive) |

**Examples:**

```bash
# All entries
rsspub tech epub

# Only new (previously unseen) entries, and mark them as converted
rsspub tech epub unconverted

# Entries from a single day
rsspub tech epub 2025-06-03

# Entries within a date range
rsspub tech epub 2025-06-01:2025-06-07
```

#### `--output` / `-o`

By default the EPUB is written to `<name>.epub` (or
`<name>_<filter>.epub` for date-filtered runs) in the current directory.
Use `--output` to specify a different path:

```bash
rsspub tech epub --output ~/ebooks/tech-week.epub
rsspub tech epub 2025-06-01:2025-06-07 -o ~/ebooks/tech-june-week1.epub
```

---

## Tracking Converted Entries

When you run `rsspub <name> epub unconverted`, rsspub records the IDs of
every entry included in the EPUB.  The next time you run the same command
those entries are skipped, so you only ever get fresh content.

Converted state is stored inside the collection's `.feed` file and is
cleared automatically if you remove the corresponding feed URL.

---

## Data Storage

Feed collection files are stored in the platform-appropriate user-data
directory managed by
[platformdirs](https://pypi.org/project/platformdirs/):

| Platform | Example path |
|---|---|
| Linux | `~/.local/share/rsspub/` |
| macOS | `~/Library/Application Support/rsspub/` |
| Windows | `C:\Users\<user>\AppData\Local\rsspub\rsspub\` |

Each collection is a single `<name>.feed` JSON file in that directory.

