#!/usr/bin/env python3

from bs4 import BeautifulSoup
import click
import dateparser
import datetime
import httpx
import os
import random
import re
import sqlite_utils
from sqlite_utils.utils import sqlite3
import time


DEFAULT_HEADERS = {
    "accept-language": "en-US,en;q=0.5",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:103.0) Gecko/20100101 Firefox/103.0",
}
PROXIES = "http://localhost:8888"
VK_BASE_URL = "https://m.vk.com"
DEFAULT_PAGE_LIMIT = 5
DEFAULT_DELAY = 3
DEFAULT_LOOP_DELAY = 60


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
    default=DEFAULT_PAGE_LIMIT,
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
@click.option(
    "-x",
    "--loop",
    is_flag=True,
    show_default=True,
    default=False,
    help="Keep looping on domains",
)
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
@click.argument("domains", type=VK_DOMAIN, nargs=-1)
def listen(db_path, domains, force, limit, offset, loop):
    "Retrieve all wall posts from the VK communities specified by their domains"

    # check CLI options for inconsitencies upfront
    if loop and (force or offset):
        click.echo("Can't loop with force or offset enabled")
        return

    db = sqlite_utils.Database(db_path)
    ensure_tables(db)

    if loop:
        # build indexes upfront when running in a loop, otherwise we'll do it afterwards
        ensure_fts(db)

    running = True
    while running:
        for domain in domains:
            pages_requested = 0
            posts_added = 0
            last_post_added = False

            if not offset:
                url = f"{VK_BASE_URL}/{domain}"
            else:
                url = f"{VK_BASE_URL}/{domain}?offset={offset}&own=1"
            while True:
                timestamp = datetime.datetime.utcnow().isoformat()
                click.echo(f"Scraping VK domain '{domain}'... {url}")
                r = httpx.get(url, headers=DEFAULT_HEADERS, proxies=PROXIES)
                with db.conn:
                    db["scrape_log"].insert(
                        {
                            "domain": domain,
                            "timestamp": timestamp,
                            "url": url,
                            "status_code": r.status_code,
                            "html": r.text.strip(),
                        },
                    )

                assert r.status_code == 200, r.status_code
                assert (
                    r.headers["content-type"] == "text/html; charset=utf-8"
                ), r.headers["content-type"]
                pages_requested += 1

                soup = BeautifulSoup(r.text, "html.parser")

                for post_div in soup.find_all("div", class_="wall_item"):
                    post_id = post_div.find("a", class_="post__anchor")["name"].replace(
                        "post", ""
                    )
                    post_date_raw = post_div.find("a", class_="wi_date").text
                    # Convert from moscow timezone
                    post_date_utc = dateparser.parse(
                        post_date_raw,
                        settings={"TIMEZONE": "Europe/Moscow", "TO_TIMEZONE": "UTC"},
                    ).isoformat()

                    post_text_div = post_div.find(class_="pi_text")
                    # TODO strip See more in post
                    post_text = post_text_div.text if post_text_div else None

                    post = {
                        "id": post_id,
                        "domain": domain,
                        # "timestamp": timestamp,
                        "date_utc": post_date_utc,
                        "text": post_text,
                    }

                    with db.conn:
                        try:
                            if force:
                                db["posts"].upsert(
                                    post,
                                    pk="id",  # , ignore=True
                                )
                            else:
                                db["posts"].insert(
                                    post,
                                    pk="id",  # , ignore=True
                                )
                            click.echo(f"POST {domain}/{post_id} added")
                            posts_added += 1
                            last_post_added = True
                        except sqlite3.IntegrityError:
                            click.echo(
                                f"POST {domain}/{post_id} already exists, skipping"
                            )
                            last_post_added = False

                if "PYTEST_CURRENT_TEST" not in os.environ:
                    time.sleep(DEFAULT_DELAY)

                #  Should we scrape more?
                click.echo(
                    f"last_post_added={last_post_added} page: {pages_requested} / {limit}"
                )
                if not force:
                    if posts_added == 0:
                        # XXX unless force
                        click.echo(f"Nothing added, done with {domain}")
                        break
                    elif not last_post_added:
                        # XXX unless force
                        click.echo(f"Last post not added, done with {domain}")
                        break
                if pages_requested < limit:
                    # <div class="show_more_wrap"><a class="show_more" href="/life?offset=5&own=1" rel="noopener">Show more</a></div>
                    show_more_div = soup.find("div", class_="show_more_wrap")
                    if show_more_div:
                        show_more_href = show_more_div.a["href"]
                        url = f"{VK_BASE_URL}{show_more_href}"
                        click.echo(f"next url will be {url}")
                    else:
                        click.echo("Show more link not found, aborting")
                        break
                else:
                    click.echo(f"Nothing more to scrape for {domain}")
                    break

        if not loop:
            ensure_fts(db)
            running = False
        else:
            click.echo(f"Done with all domains, sleeping {DEFAULT_LOOP_DELAY}s...")
            if "PYTEST_CURRENT_TEST" not in os.environ:
                time.sleep(DEFAULT_LOOP_DELAY)
            # shuffle domains
            random.shuffle(domains)


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


if __name__ == "__main__":
    cli()
