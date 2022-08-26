#!/usr/bin/env python3

import click

import os
import random
import re
import sqlite_utils
import time

import vkfeed.scraper as scraper


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
    type=click.IntRange(1, 10, clamp=True),
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
    help="Number of pages to skip",
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


def ensure_tables(db):
    # Create tables manually, because if we create them automatically
    # we may create items without 'title' first, which breaks
    # when we later call ensure_fts()
    if "posts" not in db.table_names():
        db["posts"].create(
            {
                "id": str,
                "domain": str,
                # "timestamp": str,
                "date_utc": str,
                "text": str,
            },
            pk="id",
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


def ensure_fts(db):
    table_names = set(db.table_names())
    if "posts" in table_names and "posts_fts" not in table_names:
        db["posts"].enable_fts(["text"], create_triggers=True)
