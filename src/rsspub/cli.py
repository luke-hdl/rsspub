"""rsspub command-line interface.

Entry points
------------
* ``rsspub feed create <name>``        – create a new feed collection
* ``rsspub <name> add <url>``          – add a URL to a collection
* ``rsspub <name> list``               – list URLs in a collection
* ``rsspub <name> remove <url>``       – remove a URL from a collection
* ``rsspub <name> export <path>``      – export the collection to a .feed file
* ``rsspub <name> epub [filter ...]``  – generate an EPUB from the collection
"""

import sys
from datetime import date, datetime

import click

from . import feed as feed_module
from . import epub as epub_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _err(message: str) -> None:
    click.echo(f"Error: {message}", err=True)
    sys.exit(1)


def _parse_date(value: str) -> date:
    """Parse *value* as ``YYYY-MM-DD``, raising ``click.BadParameter`` on failure."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise click.BadParameter(f"'{value}' is not a valid date (expected YYYY-MM-DD).")


# ---------------------------------------------------------------------------
# Dynamic collection group
# ---------------------------------------------------------------------------

def _make_collection_group(collection_name: str) -> click.Group:
    """Return a :class:`click.Group` that exposes collection sub-commands."""

    @click.group(name=collection_name)
    @click.pass_context
    def _group(ctx: click.Context) -> None:
        ctx.ensure_object(dict)
        ctx.obj["collection"] = collection_name

    # ------------------------------------------------------------------ add
    @_group.command()
    @click.argument("url")
    @click.pass_context
    def add(ctx: click.Context, url: str) -> None:
        """Add URL to the feed collection."""
        name: str = ctx.obj["collection"]
        try:
            feed_module.add_url(name, url)
        except FileNotFoundError:
            _err(f"Feed collection '{name}' not found. Create it with: rsspub feed create {name}")
        except ValueError as exc:
            _err(str(exc))
        click.echo(f"Added {url} to '{name}'.")

    # ----------------------------------------------------------------- list
    @_group.command(name="list")
    @click.pass_context
    def list_cmd(ctx: click.Context) -> None:
        """List URLs in the feed collection."""
        name: str = ctx.obj["collection"]
        try:
            urls = feed_module.list_urls(name)
        except FileNotFoundError:
            _err(f"Feed collection '{name}' not found.")
        if urls:
            for url in urls:
                click.echo(url)
        else:
            click.echo(f"No URLs in feed collection '{name}'.")

    # --------------------------------------------------------------- remove
    @_group.command()
    @click.argument("url")
    @click.pass_context
    def remove(ctx: click.Context, url: str) -> None:
        """Remove URL from the feed collection."""
        name: str = ctx.obj["collection"]
        try:
            feed_module.remove_url(name, url)
        except FileNotFoundError:
            _err(f"Feed collection '{name}' not found.")
        except ValueError as exc:
            _err(str(exc))
        click.echo(f"Removed {url} from '{name}'.")

    # --------------------------------------------------------------- export
    @_group.command()
    @click.argument("output_path")
    @click.pass_context
    def export(ctx: click.Context, output_path: str) -> None:
        """Export the feed collection to OUTPUT_PATH."""
        name: str = ctx.obj["collection"]
        try:
            feed_module.export_feed(name, output_path)
        except FileNotFoundError:
            _err(f"Feed collection '{name}' not found.")
        click.echo(f"Exported '{name}' to {output_path}.")

    # ----------------------------------------------------------------- epub
    @_group.command(name="epub")
    @click.argument("filter_arg", required=False, metavar="[unconverted|DATE|DATE:DATE|max]")
    @click.argument("max_count", required=False, type=int, metavar="N")
    @click.option(
        "--output", "-o",
        default=None,
        help="Output file path (default: <name>.epub in current directory).",
    )
    @click.pass_context
    def epub_cmd(ctx: click.Context, filter_arg: str, max_count: int, output: str) -> None:
        """Generate an EPUB from the feed collection.

        \b
        FILTER can be:
          (none)                    all entries
          unconverted               entries not yet converted to EPUB
          YYYY-MM-DD                entries from a specific date
          YYYY-MM-DD:YYYY-MM-DD     entries within a date range (inclusive)
          max N                     up to N most-recent entries per feed

        \b
        Examples:
          rsspub news epub
          rsspub news epub unconverted
          rsspub news epub 2025-06-03
          rsspub news epub 2025-06-01:2025-06-30
          rsspub news epub max 10
        """
        name: str = ctx.obj["collection"]

        try:
            urls = feed_module.list_urls(name)
        except FileNotFoundError:
            _err(f"Feed collection '{name}' not found.")

        if not urls:
            _err(f"Feed collection '{name}' has no URLs.")

        # Determine filter parameters
        filter_mode = "all"
        converted: dict = {}
        start_date: date | None = None
        end_date: date | None = None
        max_per_feed: int | None = None

        if filter_arg:
            if filter_arg == "unconverted":
                filter_mode = "unconverted"
                converted = feed_module.get_converted(name)
            elif filter_arg == "max":
                if max_count is None or max_count < 1:
                    _err("'max' filter requires a positive integer, e.g.: rsspub <name> epub max 10")
                filter_mode = "max"
                max_per_feed = max_count
            elif ":" in filter_arg:
                filter_mode = "date"
                parts = filter_arg.split(":", 1)
                start_date = _parse_date(parts[0])
                end_date = _parse_date(parts[1])
            else:
                filter_mode = "date"
                start_date = end_date = _parse_date(filter_arg)

        click.echo(f"Fetching feeds for '{name}'…")
        feed_groups, newly_converted = epub_module.collect_entries(
            urls,
            filter_mode=filter_mode,
            converted=converted,
            start_date=start_date,
            end_date=end_date,
            max_per_feed=max_per_feed,
        )

        if not feed_groups:
            click.echo("No entries matched the filter – no EPUB generated.")
            return

        total_entries = sum(len(entries) for _, entries in feed_groups)

        # Build output filename
        if output is None:
            if filter_arg and filter_arg != "unconverted":
                if filter_arg == "max" and max_count is not None:
                    output = f"{name}_max{max_count}.epub"
                else:
                    safe = filter_arg.replace(":", "_")
                    output = f"{name}_{safe}.epub"
            else:
                output = f"{name}.epub"

        epub_module.generate_epub(name, feed_groups, output)
        click.echo(f"EPUB written to {output} ({total_entries} entries).")

        # Record newly converted entries so future 'epub unconverted' skips them
        if filter_mode == "unconverted" and newly_converted:
            for url, ids in newly_converted.items():
                feed_module.mark_converted(name, url, ids)

    return _group


# ---------------------------------------------------------------------------
# Top-level CLI
# ---------------------------------------------------------------------------

class _DynamicCLI(click.Group):
    """A :class:`click.Group` that routes unknown sub-commands to collection
    groups so that ``rsspub <name> <action>`` works alongside built-in
    commands like ``rsspub feed create``."""

    def get_command(self, ctx: click.Context, cmd_name: str):
        rv = super().get_command(ctx, cmd_name)
        if rv is not None:
            return rv
        # Fall back to treating cmd_name as a collection name
        return _make_collection_group(cmd_name)

    def list_commands(self, ctx: click.Context) -> list:
        return super().list_commands(ctx)


@click.group(cls=_DynamicCLI)
def cli() -> None:
    """rsspub – manage RSS feed collections and generate EPUBs.

    \b
    Common usage:
      rsspub feed create <name>            Create a new feed collection
      rsspub <name> add <url>              Add a feed URL to a collection
      rsspub <name> list                   List all URLs in a collection
      rsspub <name> remove <url>           Remove a URL from a collection
      rsspub <name> export <path>          Export the collection to a file
      rsspub <name> epub                   Generate EPUB with all entries
      rsspub <name> epub unconverted       Generate EPUB with new entries only
      rsspub <name> epub YYYY-MM-DD        Generate EPUB for a specific date
      rsspub <name> epub DATE:DATE         Generate EPUB for a date range
      rsspub <name> epub max N             Generate EPUB with up to N entries per feed
    """


# ---------------------------------------------------------------------------
# Built-in 'feed' command group
# ---------------------------------------------------------------------------

@cli.group()
def feed() -> None:
    """Manage feed collections."""


@feed.command(name="create")
@click.argument("name")
def feed_create(name: str) -> None:
    """Create a new feed collection called NAME."""
    try:
        feed_module.create_feed(name)
    except ValueError as exc:
        _err(str(exc))
    click.echo(f"Feed collection '{name}' created.")
