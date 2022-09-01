#!/usr/bin/env python3

import os
import random
import re
import time

import click
import dateparser
import sqlite_utils
from sqlite_utils.utils import chunks
from tabulate import tabulate

import spevktator.dostoevsky_sentiment as dostoevsky_sentiment
import spevktator.scraper as scraper
import spevktator.utils as utils


class VKDomainParamType(click.ParamType):
    name = "domain"

    def convert(self, value, param, ctx):
        if isinstance(value, int):
            return value

        if re.fullmatch(r"[a-z0-9_]+", value):
            return value
        else:
            self.fail(f"{value!r} is not a valid VK domain", param, ctx)


VK_DOMAIN = VKDomainParamType()


@click.group()
@click.version_option()
def cli():
    "Save wall posts from VK communities to a SQLite database"


@cli.command()
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
def install(db_path):
    "Download and install models, create database"

    click.echo("Downloading Dostoevsky sentiment model... ", nl=False)
    dostoevsky_sentiment.download()
    click.echo("DONE")

    click.echo("Creating database...", nl=False)
    db = sqlite_utils.Database(db_path)
    ensure_tables(db)
    ensure_views(db)
    click.echo("DONE")


@cli.command()
@click.option(
    "-f",
    "--force",
    is_flag=True,
    show_default=True,
    default=False,
    help="Force all pages to be loaded",
)
@click.option(
    "-l",
    "--limit",
    type=click.IntRange(1, 5000, clamp=True),
    show_default=True,
    default=scraper.DEFAULT_PAGE_LIMIT,
    help="Number of pages to be requested",
)
@click.option(
    "-u",
    "--until",
    type=str,
    show_default=True,
    help="Date to go back to",
)
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
@click.argument("domain", type=VK_DOMAIN, required=True)
def backfill(db_path, domain, force, limit, until):
    "Retrieve the backlog of wall posts from the VK communities specified by their domain"

    db = sqlite_utils.Database(db_path)
    ensure_tables(db)
    ensure_views(db)

    if until:
        until = (
            dateparser.parse(
                until,
                settings={"TIMEZONE": "UTC"},
            )
            .replace(microsecond=0)
            .isoformat()
        )

    offset = next(
        db.query(
            "select count(*) as nr_posts from posts where domain = :domain",
            params={"domain": domain},
        )
    )["nr_posts"]

    click.echo(
        f"Scraping max {limit} pages of posts for {domain}, starting at {offset}, until date {until}"
    )

    scrape_delay = "PYTEST_CURRENT_TEST" not in os.environ
    scraper.fetch_domains(db, [domain], force, limit, offset, scrape_delay, until)
    ensure_fts(db)
    db["posts"].optimize()


@cli.command()
@click.option(
    "-f",
    "--force",
    is_flag=True,
    show_default=True,
    default=False,
    help="Force all pages to be loaded",
)
@click.option(
    "-l",
    "--limit",
    type=click.IntRange(1, 5000, clamp=True),
    show_default=True,
    default=scraper.DEFAULT_PAGE_LIMIT,
    help="Number of pages to be requested",
)
@click.option(
    "-o",
    "--offset",
    type=click.IntRange(0, 100, clamp=True),
    show_default=True,
    default=0,
    help="Number of posts to skip",
)
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
@click.argument("domains", type=VK_DOMAIN, nargs=-1, required=True)
def fetch(db_path, domains, force, limit, offset):
    "Retrieve all wall posts from the VK communities specified by their domains"

    db = sqlite_utils.Database(db_path)
    ensure_tables(db)
    ensure_views(db)

    scrape_delay = "PYTEST_CURRENT_TEST" not in os.environ
    scraper.fetch_domains(db, domains, force, limit, offset, scrape_delay)

    ensure_fts(db)
    db["posts"].optimize()


@cli.command()
@click.option(
    "-l",
    "--limit",
    type=click.IntRange(1, 10, clamp=True),
    show_default=True,
    default=scraper.DEFAULT_PAGE_LIMIT,
    help="Number of pages to be requested",
)
@click.option("--deepl-auth-key", envvar="DEEPL_AUTH_KEY")
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
@click.argument("domains", type=VK_DOMAIN, nargs=-1, required=True)
def listen(db_path, domains, limit, deepl_auth_key):
    "Continuously retrieve all wall posts from the VK communities specified by their domains"

    db = sqlite_utils.Database(db_path)
    ensure_tables(db)
    ensure_views(db)

    # build text indexes upfront when running in a loop, otherwise we'll do it afterwards
    ensure_fts(db)

    domains = list(domains)  # so we can shuffle them
    running = True
    scrape_delay = "PYTEST_CURRENT_TEST" not in os.environ
    while running:
        if "PYTEST_CURRENT_TEST" not in os.environ:
            random.shuffle(domains)

        scraper.fetch_domains(
            db,
            domains,
            force=False,
            limit=limit,
            offset=0,
            scrape_delay=scrape_delay,
            deepl_auth_key=deepl_auth_key,
        )

        click.echo(f"Done with all domains, sleeping {scraper.DEFAULT_LOOP_DELAY}s...")
        if scrape_delay:
            time.sleep(scraper.DEFAULT_LOOP_DELAY)


@cli.command()
@click.option(
    "-l",
    "--limit",
    type=int,
    show_default=True,
    default=0,
    help="Number of pages to be processed",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    show_default=True,
    default=False,
    help="Verbose output",
)
@click.option(
    "-r", "--reset", is_flag=True, help="Start from scratch, deleting previous results"
)
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
def rescrape(db_path, limit, verbose, reset):
    "Rescrape HTML pages from the scrape_log"

    db = sqlite_utils.Database(db_path)

    if reset:
        db["posts"].disable_fts()
        db["posts"].drop(True)
        db["posts_metrics"].drop(True)
        db["posts_sentiment"].drop(True)

    ensure_tables(db)
    ensure_views(db)

    sql = "select domain, timestamp, html from scrape_log where status_code = 200 order by timestamp"
    if limit:
        sql += f" limit {limit}"
    params = dict()
    rows = db.query(sql, params)

    # Run a count, for the progress bar
    count = utils.get_count(db, sql, params)
    rescrape_count = 0
    with click.progressbar(rows, length=count) as bar:
        for row in bar:
            timestamp = dateparser.parse(
                row["timestamp"],
                settings={"TIMEZONE": "UTC"},
            )
            result = scraper.process_page(
                db,
                row["domain"],
                row["html"],
                force=True,
                relative_timestamp=timestamp,
                verbose=verbose,
            )
            rescrape_count += result.posts_added

    ensure_fts(db)
    db["posts"].optimize()

    click.echo(f"rescraped {count} pages, {rescrape_count} posts inserted/updated")


@cli.command()
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
@click.argument("table", type=str)
@click.argument("text_column", type=str)
@click.option("-o", "--output", help="Custom output table")
@click.option(
    "-r", "--reset", is_flag=True, help="Start from scratch, deleting previous results"
)
def sentiment(db_path, table, text_column, output, reset):
    "Perform dostoevsky (RU) sentiment analysis on table with column"

    if dostoevsky_sentiment.model is None:
        click.secho(
            "Dostoevsky sentiment model not installed, run `install` first.", fg="red"
        )
        return

    db = sqlite_utils.Database(db_path)
    output_table = output or f"{table}_sentiment"

    if reset:
        db[output_table].drop(True)

    ensure_tables(db)
    ensure_views(db)

    if not db[table].exists():
        raise click.ClickException(f"Table {table} does not exist")

    if text_column not in db[table].columns_dict:
        raise click.ClickException(f"Column {text_column} does not exist")

    if len(db[table].pks) != 1:
        raise click.ClickException(f"Table {table} with multiple PKs not supported")

    pk = db[table].pks[0]
    sql = f"select {pk}, {text_column} from {table} where {text_column} != ''"
    params = dict()

    if reset:
        db[output_table].drop(True)
    else:
        sql += f" and {pk} not in (select id from {output_table})"

    rows = db.query(sql, params=dict(params))
    count = utils.get_count(db, sql, params)

    sentiment_count = 0
    with click.progressbar(rows, length=count) as bar:
        for chunk in chunks(bar, 100):
            chunk = list(chunk)
            to_insert = []
            for row in chunk:
                item = {pk: row[pk]}
                item.update(dostoevsky_sentiment.predict([row[text_column]])[0])
                to_insert.append(item)
                sentiment_count += 1

            db[output_table].insert_all(
                to_insert,
                pk=pk,
                column_order=(
                    "id",
                    "positive",
                    "negative",
                    "neutral",
                    "skip",
                    "speech",
                ),
                foreign_keys=[("id", "posts", pk)],
            )
    click.echo(f"Sentiment for {sentiment_count} rows predicted")


@cli.command()
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
def stats(db_path):
    "Show statistics for the given database"

    db = sqlite_utils.Database(db_path)
    rows = db.query(
        """
    select domain, count(*) as nr_posts, min(date_utc) as first, max(date_utc) as last
    from posts group by domain order by domain
    """
    )
    click.echo(tabulate(list(rows), headers="keys"))


@cli.command()
@click.option(
    "-l",
    "--limit",
    type=int,
    show_default=True,
    default=1,
    help="Number of posts to be translated",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    show_default=True,
    default=False,
    help="Verbose output",
)
@click.option("--deepl-auth-key", type=str, default=None, envvar="DEEPL_AUTH_KEY")
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
def translate(db_path, limit, verbose, deepl_auth_key):
    "Translate posts from RU to EN-US"

    db = sqlite_utils.Database(db_path)
    ensure_tables(db)

    if not deepl_auth_key:
        raise click.ClickException("DEEPL_AUTH_KEY not set")

    scraper.translate(db, deepl_auth_key, limit, verbose)

    ensure_fts(db)
    db["posts_translate"].optimize()


def ensure_tables(db):
    # Create tables manually, because if we create them automatically
    # we may create items without 'title' first, which breaks
    # when we later call ensure_fts()
    if "posts" not in db.table_names():
        db["posts"].create(
            {
                "id": str,
                "domain": str,
                "date_utc": str,
                "text": str,
            },
            pk="id",
            column_order=("id", "domain", "date_utc", "text"),
        )
    if "posts_metrics" not in db.table_names():
        db["posts_metrics"].create(
            {
                "id": str,
                "likes": int,
                "shares": int,
                "views": int,
                "timestamp": str,
            },
            pk="id",
            column_order=("id", "likes", "shares", "views", "timestamp"),
            foreign_keys=[("id", "posts")],
        )
    if "posts_sentiment" not in db.table_names():
        db["posts_sentiment"].create(
            {
                "id": str,
                "positive": float,
                "negative": float,
                "neutral": float,
                "skip": float,
                "speech": float,
            },
            pk="id",
            column_order=(
                "id",
                "positive",
                "negative",
                "neutral",
                "skip",
                "speech",
            ),
            foreign_keys=[("id", "posts")],
        )
    if "posts_translation" not in db.table_names():
        db["posts_translation"].create(
            {
                "id": str,
                "text_en": str,
            },
            pk="id",
            column_order=("id", "text_en"),
            foreign_keys=[("id", "posts")],
        )
    if "scrape_log" not in db.table_names():
        db["scrape_log"].create(
            {
                "domain": str,
                "timestamp": str,
                "url": str,
                "status_code": int,
                "html": str,
            },
        )


def ensure_views(db):
    if "posts_metrics_view" not in db.view_names():
        db.create_view(
            "posts_metrics_view",
            """
        select posts.id, domain, date_utc, text, likes, shares, views
        from posts join posts_metrics on posts.id = posts_metrics.id
        order by likes desc
        """,
        )
    if "posts_sentiment_view" not in db.view_names():
        db.create_view(
            "posts_sentiment_view",
            """
        select posts.id, domain, date_utc, text, (positive - negative) as sentiment
        from posts join posts_sentiment on posts.id = posts_sentiment.id
        order by sentiment
        """,
        )
    if "posts_translation_view" not in db.view_names():
        db.create_view(
            "posts_translation_view",
            """
        select posts.id, domain, date_utc, text, text_en
        from posts left join posts_translation on posts.id = posts_translation.id
        order by date_utc desc
        """,
        )
    if "posts_mega_view" not in db.view_names():
        db.create_view(
            "posts_mega_view",
            """
        select
            p.id, domain, date_utc, text, text_en, likes, shares, views,
            (ps.positive - ps.negative) as sentiment
        from
            posts p
            left join posts_metrics pm on p.id = pm.id
            left join posts_sentiment ps on p.id = ps.id
            left join posts_translation pt on p.id = pt.id
        where text != ''
        order by date_utc desc
        """,
        )
    if "scrape_errors" not in db.view_names():
        db.create_view(
            "scrape_errors",
            """
        select * from scrape_log where status_code != 200
        """,
        )


def ensure_fts(db):
    table_names = set(db.table_names())
    if "posts" in table_names and "posts_fts" not in table_names:
        db["posts"].enable_fts(["text"], create_triggers=True)

    if (
        "posts_translation" in table_names
        and "posts_translation_fts" not in table_names
    ):
        db["posts_translation"].enable_fts(
            ["text_en"], tokenize="porter", create_triggers=True
        )
