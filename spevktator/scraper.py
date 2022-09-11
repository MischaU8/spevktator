import click
from bs4 import BeautifulSoup
from dataclasses import dataclass
import dateparser
import datetime
import deepl
import httpx
import re
import sqlite_utils
from sqlite_utils.utils import chunks
from sqlite_utils.utils import sqlite3
import time

import spevktator.dostoevsky_sentiment as dostoevsky_sentiment
import spevktator.natasha_entities as natasha_entities
import spevktator.utils as utils


DEFAULT_HEADERS = {
    "accept-language": "en-US,en;q=0.5",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:103.0) Gecko/20100101 Firefox/103.0",
}

VK_BASE_URL = "https://m.vk.com"
DEFAULT_PAGE_LIMIT = 5
DEFAULT_DELAY = 5
DEFAULT_LOOP_DELAY = 300
ERROR_DELAY = 120


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

        post_date_utc = (
            dateparser.parse(
                post_date_raw,
                settings=dateparser_settings,
            )
            .replace(microsecond=0)
            .isoformat()
        )

        post_text_div = post_div.find(class_="pi_text")
        if post_text_div:
            pi_text_more = post_text_div.find(class_="pi_text_more")
            if pi_text_more:
                # strip "See more" in post
                pi_text_more.decompose()

        post_text = post_text_div.get_text(separator=" ") if post_text_div else ""

        _RE_COMBINE_WHITESPACE = re.compile(r"\s+")
        post_text = _RE_COMBINE_WHITESPACE.sub(" ", post_text).strip()

        post = {
            "id": post_id,
            "domain": domain,
            "date_utc": post_date_utc,
            "text": post_text,
        }

        post_buttons_div = post_div.find(class_="_wi_buttons")

        # <div aria-hidden="true" class="svgIcon svgIcon-like_outline_24">
        # <span class="PostBottomButtonReaction__label" aria-hidden="true">11</span>
        # <span class="visually-hidden">1738 people reacted</span>
        post_buttons_a = post_buttons_div.find_all("a", class_="PostBottomButton")
        likes_text = (
            post_buttons_a[0].parent.find_all("span", class_="visually-hidden")[-1].text
        )
        likes = int(re.sub(r" (person|people) reacted", "", likes_text))

        # <div aria-hidden="true" class="svgIcon svgIcon-share_outline_24">
        # <span class="PostBottomButton__label" aria-hidden="true">2</span>
        shares = int(post_buttons_a[1]["aria-label"].replace(" Share", ""))

        # <div class="PostRowBottomButtons__views">
        # <span class=" wall_item_views" aria-label="262671 views">
        views_div = post_buttons_div.find(class_="wall_item_views")
        if views_div and "aria-label" in views_div.attrs:
            views = int(re.sub(r" views?", "", views_div["aria-label"]))
        else:
            views = 0
        metrics = {
            "id": post_id,
            "likes": likes,
            "shares": shares,
            "views": views,
            "timestamp": relative_timestamp.replace(microsecond=0).isoformat(),
        }
        # post_explain_div = post_div.find(class_="wi_explain")
        # if post_explain_div and "pinned post" in post_explain_div.text:
        #     # only set when pinned, to prevent unsetting it when it gets unpinned
        #     metrics["was_pinned"] = True

        # XXX convert into upsert_all in outside loop
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

            db["posts_metrics"].upsert(
                metrics,
                pk="id",
                column_order=("id", "shares", "likes", "views", "timestamp"),
            )
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
    deepl_auth_key=None,
    proxies=None,
):
    for domain in domains:
        pages_requested = 0

        if not offset:
            url = f"{VK_BASE_URL}/{domain}"
        else:
            url = f"{VK_BASE_URL}/{domain}?offset={offset}&own=1"

        while True:
            timestamp = datetime.datetime.utcnow()
            click.echo(f"Scraping VK domain '{domain}'... {url}")
            try:
                r = httpx.get(url, headers=DEFAULT_HEADERS, proxies=proxies)
            except httpx.HTTPError as exc:
                click.secho(f"HTTP Exception for {exc.request.url} - {exc}", fg="red")
                time.sleep(ERROR_DELAY)
                continue
            if r.status_code != 200:
                with db.conn:
                    db["scrape_log"].insert(
                        {
                            "domain": domain,
                            "timestamp": timestamp.isoformat(),
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
            result = process_page(
                db, domain, r.text, force, relative_timestamp=timestamp
            )

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

            # translate
            if result.posts_added > 0 and deepl_auth_key is not None:
                translate_posts(db, deepl_auth_key, limit=result.posts_added)

            # named entities recognition
            if result.posts_added > 0:
                ner_count = extract_named_entities(db, limit=result.posts_added)
                if ner_count > 0 and deepl_auth_key is not None:
                    translate_entities(db, deepl_auth_key, limit=ner_count)

            if scrape_delay:
                time.sleep(DEFAULT_DELAY)
            url = next_url(domain, r.text, result, pages_requested, force, limit, until)
            if url is None:
                break


def translate_posts(
    db: sqlite_utils.Database, deepl_auth_key: str, limit: int, verbose=False
):
    translator = deepl.Translator(deepl_auth_key)

    output_table = "posts_translation"
    sql = (
        "select id, text from posts where text != '' and length(text) <= 2500"
        f" and id not in (select id from {output_table}) order by date_utc desc"
    )
    if limit:
        sql += f" limit {limit}"
    params = dict()
    rows = db.query(sql, params)

    # Run a count, for the progress bar
    count = utils.get_count(db, sql, params)
    click.echo(f"Translating {count} of max {limit} posts...")
    if count == 0:
        return
    translation_count = 0
    try:
        with click.progressbar(rows, length=count) as bar:
            for chunk in chunks(bar, 10):
                chunk = list(chunk)
                texts_ru = [row["text"] for row in chunk]

                if verbose:
                    click.echo(texts_ru)

                result = translator.translate_text(
                    texts_ru, source_lang="RU", target_lang="EN-US"
                )
                if verbose:
                    click.echo([item.text for item in result])

                to_insert = []
                for i, translation in enumerate(result):
                    to_insert.append(
                        {"id": chunk[i]["id"], "text_en": translation.text}
                    )
                    translation_count += 1

                db[output_table].insert_all(
                    to_insert,
                    pk="id",
                    column_order=("id", "text_en"),
                    foreign_keys=[("id", "posts")],
                )

        click.echo(f"{translation_count} posts translated")

    except deepl.exceptions.DeepLException as e:
        click.secho(
            (f"DeepL API throws error: {e}"),
            fg="red",
        )
        time.sleep(ERROR_DELAY)


def translate_entities(
    db: sqlite_utils.Database, deepl_auth_key: str, limit: int, verbose=False
):
    translator = deepl.Translator(deepl_auth_key)

    sql = (
        "select id, name from entities where name != '' and (name_en = '' or name_en is null)"
        " order by rowid desc"
    )
    if limit:
        sql += f" limit {limit}"

    params = dict()
    rows = db.query(sql, params)

    # Run a count, for the progress bar
    count = utils.get_count(db, sql, params)
    click.echo(f"Translating {count} of max {limit} entities...")
    if count == 0:
        return
    translation_count = 0
    try:
        with click.progressbar(rows, length=count) as bar:
            for chunk in chunks(bar, 50):
                chunk = list(chunk)
                texts_ru = [row["name"] for row in chunk]

                if verbose:
                    click.echo(texts_ru)

                result = translator.translate_text(
                    texts_ru, source_lang="RU", target_lang="EN-US"
                )
                if verbose:
                    click.echo([item.text for item in result])

                for i, translation in enumerate(result):
                    db["entities"].update(chunk[i]["id"], {"name_en": translation.text})
                    translation_count += 1

        click.echo(f"{translation_count} entities translated")

    except deepl.exceptions.DeepLException as e:
        click.secho(
            (f"DeepL API throws error: {e}"),
            fg="red",
        )


def extract_named_entities(db: sqlite_utils.Database, limit: int, verbose=False):

    output_table = "posts_entities"
    done_table = f"{output_table}_done"
    sql = (
        "select id, text from posts where text != ''"
        f" and id not in (select id from {done_table})"
        " order by date_utc desc"
    )
    if limit:
        sql += f" limit {limit}"
    params = dict()
    rows = db.query(sql, params)

    # Run a count, for the progress bar
    count = utils.get_count(db, sql, params)
    post_count = 0
    ner_count = 0
    click.echo(f"Extracting named-entities up to {limit} posts...")
    with click.progressbar(rows, length=count) as bar:
        for row in bar:
            if verbose:
                click.echo(row)
            entities = natasha_entities.named_entity_normalization(row["text"])

            to_insert = []
            for entity in entities:
                if verbose:
                    click.echo(f"-> {entity}")
                to_insert.append(
                    {
                        "id": row["id"],
                        "entity": db["entities"].lookup(
                            {
                                "type": db["entity_types"].lookup(
                                    {"value": entity["type"]}
                                ),
                                "name": entity["normal"],
                            }
                        ),
                        "begin_offset": entity["start"],
                        "end_offset": entity["stop"],
                    }
                )
                ner_count += 1

            db[output_table].insert_all(to_insert)

            db[done_table].insert_all(
                [{"id": row["id"]}], pk="id", foreign_keys=[("id", "posts", "id")]
            )

            post_count += 1

    click.echo(f"{ner_count} extracted out of {post_count} posts")
    return ner_count
