import click
from bs4 import BeautifulSoup
from dataclasses import dataclass
import dateparser
import datetime
import httpx
import sqlite_utils
from sqlite_utils.utils import sqlite3
import time

import vkfeed.dostoevsky_sentiment as dostoevsky_sentiment


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
    earliest_post_date: str = None


def process_page(
    db: sqlite_utils.Database,
    domain: str,
    html: str,
    force=False,
    verbose=True,
    relative_timestamp=None,
) -> ProcessResult:
    soup = BeautifulSoup(html, "html.parser")
    result = ProcessResult()

    # Convert from moscow timezone
    dateparser_settings = {"TIMEZONE": "Europe/Moscow", "TO_TIMEZONE": "UTC"}
    if relative_timestamp is not None:
        dateparser_settings["RELATIVE_BASE"] = relative_timestamp

    for post_div in soup.find_all("div", class_="wall_item"):
        post_id = post_div.find("a", class_="post__anchor")["name"].replace("post", "")
        post_date_raw = post_div.find("a", class_="wi_date").text

        post_date_utc = dateparser.parse(
            post_date_raw,
            settings=dateparser_settings,
        ).isoformat()

        post_text_div = post_div.find(class_="pi_text")
        # TODO strip See more in post
        post_text = (
            post_text_div.get_text(separator=" ").strip() if post_text_div else None
        )

        post = {
            "id": post_id,
            "domain": domain,
            "date_utc": post_date_utc,
            "text": post_text,
        }

        with db.conn:
            try:
                db["posts"].insert(post, pk="id", replace=force)
                if verbose:
                    click.echo(f"POST {domain}/{post_id} {post_date_utc} added")
                result.posts_added += 1
                result.last_post_added = True
                if (
                    result.earliest_post_date is None
                    or post_date_utc < result.earliest_post_date
                ):
                    result.earliest_post_date = post_date_utc

                if post_text and dostoevsky_sentiment.model is not None:
                    sentiment_item = {"id": post_id}
                    sentiment_item.update(dostoevsky_sentiment.predict([post_text])[0])
                    db["posts_sentiment"].insert(
                        sentiment_item,
                        pk="id",
                        column_order=(
                            "id",
                            "positive",
                            "negative",
                            "neutral",
                            "skip",
                            "speech",
                        ),
                        replace=force,
                    )
            except sqlite3.IntegrityError:
                if verbose:
                    click.echo(f"POST {domain}/{post_id} already exists, skipping")
                result.last_post_added = False
    return result


def next_url(domain, html, result, pages_requested, force, limit, until) -> str:
    if not force:
        if result.posts_added == 0:
            click.echo(f"Nothing added, done with {domain}")
            return None
        elif not result.last_post_added:
            click.echo(f"Last post not added, done with {domain}")
            return None
    if until and result.earliest_post_date <= until:
        click.echo(f"Until date {until} reached, done with {domain}")
        return None
    if pages_requested < limit:
        soup = BeautifulSoup(html, "html.parser")
        show_more_div = soup.find("div", class_="show_more_wrap")
        if show_more_div:
            show_more_href = show_more_div.a["href"]
            url = f"{VK_BASE_URL}{show_more_href}"
            click.echo(f"next url will be {url}")
            return url
        else:
            click.secho("Show more link not found, aborting", fg="red")
            return None
    else:
        click.echo(f"Page limit {limit} reached, done with {domain}")
        return None


def fetch_domains(
    db: sqlite_utils.Database,
    domains: list,
    force: bool,
    limit: int,
    offset: int,
    scrape_delay=False,
    until=None,
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
            result = process_page(db, domain, r.text, force)

            #  Should we scrape more?
            click.secho(
                (
                    f"{timestamp} posts_added={result.posts_added}"
                    f" last_post_added={result.last_post_added}"
                    f" earliest_post_date={result.earliest_post_date}"
                    f" page: {pages_requested} / {limit}"
                ),
                fg="green",
            )
            if scrape_delay:
                time.sleep(DEFAULT_DELAY)
            url = next_url(domain, r.text, result, pages_requested, force, limit, until)
            if url is None:
                break
