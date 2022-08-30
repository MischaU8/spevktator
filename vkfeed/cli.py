#!/usr/bin/env python3

import click

import os
import random
import re
import sqlite_utils
from sqlite_utils.utils import chunks
from tabulate import tabulate
import time

import vkfeed.scraper as scraper

import vkfeed.dostoevsky_sentiment as dostoevsky_sentiment


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
def install():
    "Download and install models"

    click.echo("Downloading Dostoevsky sentiment model... ", nl=False)
    dostoevsky_sentiment.download()
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


@cli.command()
@click.option(
    "-l",
    "--limit",
    type=click.IntRange(1, 10, clamp=True),
    show_default=True,
    default=scraper.DEFAULT_PAGE_LIMIT,
    help="Number of pages to be requested",
)
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
@click.argument("domains", type=VK_DOMAIN, nargs=-1, required=True)
def listen(db_path, domains, limit):
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

        scraper.fetch_domains(db, domains, False, limit, 0, scrape_delay)

        click.echo(f"Done with all domains, sleeping {scraper.DEFAULT_LOOP_DELAY}s...")
        if scrape_delay:
            time.sleep(scraper.DEFAULT_LOOP_DELAY)


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

    # Run a count, for the progress bar
    count = next(
        db.query(
            "with t as ({}) select count(*) as c from t".format(sql),
            params=dict(params),
        )
    )["c"]

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
    rows = db.query("""
    select domain, count(*) as nr_posts, min(date_utc) as first, max(date_utc) as last
    from posts group by domain order by domain
    """)
    click.echo(tabulate(list(rows), headers="keys"))


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
    if "posts_sentiment_view" not in db.view_names():
        db.create_view(
            "posts_sentiment_view",
            """
        select posts.id, domain, date_utc, text, (positive - negative) as sentiment
        from posts join posts_sentiment on posts.id = posts_sentiment.id
        order by sentiment
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
