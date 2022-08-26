import click
from bs4 import BeautifulSoup
from dataclasses import dataclass
import dateparser
import datetime
import httpx
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
DEFAULT_DELAY = 5
DEFAULT_LOOP_DELAY = 300


@dataclass
class ProcessResult:
    posts_added: int = 0
    last_post_added: bool = False


def process_page(
    db: sqlite_utils.Database, domain: str, html: str, force=False
) -> ProcessResult:
    soup = BeautifulSoup(html, "html.parser")
    result = ProcessResult()

    for post_div in soup.find_all("div", class_="wall_item"):
        post_id = post_div.find("a", class_="post__anchor")["name"].replace("post", "")
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
                result.posts_added += 1
                result.last_post_added = True
            except sqlite3.IntegrityError:
                click.echo(f"POST {domain}/{post_id} already exists, skipping")
                result.last_post_added = False
    return result


def fetch_domains(
    db: sqlite_utils.Database,
    domains: list,
    force: bool,
    limit: int,
    offset: int,
    scrape_delay=False,
):
    for domain in domains:
        pages_requested = 0

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
            assert r.headers["content-type"] == "text/html; charset=utf-8", r.headers[
                "content-type"
            ]
            pages_requested += 1

            soup = BeautifulSoup(r.text, "html.parser")
            result = process_page(db, domain, r.text, force)

            #  Should we scrape more?
            click.secho(
                (
                    f"{timestamp} posts_added={result.posts_added} last_post_added={result.last_post_added}"
                    f" page: {pages_requested} / {limit}"
                ),
                fg="green",
            )
            if scrape_delay:
                time.sleep(DEFAULT_DELAY)
            if not force:
                if result.posts_added == 0:
                    click.echo(f"Nothing added, done with {domain}")
                    break
                elif not result.last_post_added:
                    click.echo(f"Last post not added, done with {domain}")
                    break
            if pages_requested < limit:
                show_more_div = soup.find("div", class_="show_more_wrap")
                if show_more_div:
                    show_more_href = show_more_div.a["href"]
                    url = f"{VK_BASE_URL}{show_more_href}"
                    click.echo(f"next url will be {url}")
                else:
                    click.secho("Show more link not found, aborting", fg="red")
                    break
            else:
                click.echo(f"Nothing more to scrape for {domain}")
                break
