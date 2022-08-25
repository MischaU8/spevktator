#!/usr/bin/env python3

from bs4 import BeautifulSoup
import click
import dateparser
import datetime
import httpx
import os
import re
import sqlite_utils
import time


headers = {
    "accept-language": "en-US,en;q=0.5",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:103.0) Gecko/20100101 Firefox/103.0",
}
proxies = "http://localhost:8888"


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
def test():
    r = httpx.get("https://httpbin.org/get", headers=headers, proxies=proxies)
    click.echo(r)
    click.echo(r.status_code)
    click.echo(r.text)


@cli.command()
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
@click.argument("domains", type=VK_DOMAIN, nargs=-1)
def listen(db_path, domains):
    "Retrieve all wall posts from the VK communities specified by their domains"
    db = sqlite_utils.Database(db_path)
    ensure_tables(db)

    # next_id = int(next(db.query("select max(id) + 1 as max_id from posts")).get("max_id") or 1)
    # click.echo("Highest known ID = {}".format(id))

    for domain in domains:
        click.echo("Scraping VK domain '{}'...".format(domain))
        timestamp = datetime.datetime.utcnow().isoformat()

        r = httpx.get(f"https://m.vk.com/{domain}", headers=headers, proxies=proxies)
        assert r.status_code == 200, r.status_code
        assert r.headers["content-type"] == "text/html; charset=utf-8", r.headers[
            "content-type"
        ]

        # open(f"dumps/dump_{domain}_{timestamp}.html", "w").write(r.text)
        soup = BeautifulSoup(r.text, "html.parser")

        for post_div in soup.find_all("div", class_="wall_item"):
            post_id = post_div.find("a", class_="post__anchor")["name"].replace(
                "post", ""
            )
            # post_id = post_div["id"]
            post_date_raw = post_div.find("a", class_="wi_date").text
            # Convert from moscow timezone
            post_date_utc = dateparser.parse(
                post_date_raw,
                settings={"TIMEZONE": "Europe/Moscow", "TO_TIMEZONE": "UTC"},
            ).isoformat()
            post_text = post_div.find(class_="pi_text").text
            post_html = str(post_div)

            post = {
                "id": post_id,
                "domain": domain,
                "timestamp": timestamp,
                "date_raw": post_date_raw,
                "date_utc": post_date_utc,
                "text": post_text,
                "html": post_html,
            }

            click.echo(f"POST: {domain}/{post_id}")

            # TODO strip see more
            # TODO preload_data

            with db.conn:
                db["posts"].upsert(
                    post,
                    column_order=("id", "domain", "timestamp", "date", "text"),
                    pk="id",
                )

        if "PYTEST_CURRENT_TEST" not in os.environ:
            time.sleep(3)

    ensure_fts(db)


def ensure_tables(db):
    # Create tables manually, because if we create them automatically
    # we may create items without 'title' first, which breaks
    # when we later call ensure_fts()
    if "posts" not in db.table_names():
        db["posts"].create(
            {
                "id": str,
                "domain": str,
                "timestamp": str,
                "date_utc": str,
                "date_raw": str,
                "text": str,
                "html": str,
            },
            pk="id",
        )


def ensure_fts(db):
    table_names = set(db.table_names())
    if "posts" in table_names and "posts_fts" not in table_names:
        db["posts"].enable_fts(["text"], create_triggers=True)


if __name__ == "__main__":
    cli()