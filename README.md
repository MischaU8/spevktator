# Spevktator:  OSINT analysis tool for VK

[![Python](https://img.shields.io/badge/python-3.8%20%7C%203.9%20%7C%203.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/simonw/datasette/blob/main/LICENSE)
[![Test](https://github.com/MischaU8/spevktator/actions/workflows/test.yml/badge.svg)](https://github.com/MischaU8/spevktator/actions/workflows/test.yml)

## Team Members
Mischa -  [Github profile](https://github.com/MischaU8)
Morsaki - [Medium blog](https://medium.com/@rosa.noctis532)

## Tool Description
Spevktator provides a combined live feed of 5 popular Russian news channels on VK, along with translations, sentiment analysis and visualisation tools, all of which is accessible online, from anywhere (or offline if you prefer so). We currently have an archive of over 67,000 posts, dating back to the beginning of February 2022.

Originally, it was created to help research domestic Russian propaganda narratives, but can also act as a monitoring hub for VK media content, allowing researchers and journalists to stay up to date on disinformation, even as chaotic events unfold.

Sophisticated researchers can run this tool locally, against their own targets of research and even perform their detailed analysis offline through an SQL interface.

## Online Demo

In our public demo, we collect posts from 5 popular Russian news channels on VK (`life`, `mash`, `nws_ru`, `ria` and `tassagency`).

Explore the posts, together with sentiment analysis, metrics and English translation:

https://spevktator.io/vk/posts_mega_view

Some more examples:

- [Mentions of "Ukraine" per week, together with average sentiment and total number of views](
https://spevktator.io/vk?sql=select+strftime%28%27%25Y-%25W%27%2C+date_utc%29+as+week%2C+count%28*%29+as+nr_posts%2C+round%28avg%28sentiment%29%2C+2%29+as+avg_sentiment%2C+sum%28views%29+from+posts_mega_view+where+text_en+like+%27%25Ukraine%25%27+group+by+week+order+by+week#g.mark=circle&g.x_column=week&g.x_type=ordinal&g.y_column=nr_posts&g.y_type=quantitative&g.color_column=avg_sentiment&g.size_column=sum(views)
)
- [Which weapon systems are most often mentioned](
https://spevktator.io/vk?sql=with+himars+as+%28%0D%0A++++select+date%28date_utc%29+as+day%2C+count%28*%29+as+cnt+from+posts+p+join+posts_translation+pt+on+p.id+%3D+pt.id+where+text_en+like+%22%25HIMARS%25%22+group+by+day%0D%0A%29%2C%0D%0Amlrs+as+%28%0D%0A++++select+date%28date_utc%29+as+day%2C+count%28*%29+as+cnt+from+posts+p+join+posts_translation+pt+on+p.id+%3D+pt.id+where+text_en+like+%22%25MLRS%25%22+group+by+day%0D%0A%29%2C%0D%0Asam+as+%28%0D%0A++++select+date%28date_utc%29+as+day%2C+count%28*%29+as+cnt+from+posts+p+join+posts_translation+pt+on+p.id+%3D+pt.id+where+text_en+like+%22%25S-300%25%22+group+by+day%0D%0A%29%2C%0D%0Acombined+as+%28%0D%0A++++select+%22HIMARS%22+as+weapon_type%2C+*+from+himars%0D%0A++++union+select+%22MLRS%22%2C+*+from+mlrs%0D%0A++++union+select+%22SAM%22%2C+*+from+sam%0D%0A%29+select+*+from+combined+order+by+day%0D%0A#g.mark=bar&g.x_column=day&g.x_type=temporal&g.y_column=cnt&g.y_type=quantitative&g.color_column=weapon_type
)
- [When is the Moskva cruiser in the news](
https://spevktator.io/vk?sql=select+date%28date_utc%29+as+day%2C+count%28*%29+from+posts+p+join+posts_translation+t+on+p.id%3Dt.id+where+t.rowid+in+%28select+rowid+from+posts_translation_fts+where+posts_translation_fts+match+escape_fts%28%3Asearch%29%29+group+by+day+order+by+day+limit+101&search=Moskva+cruiser#g.mark=bar&g.x_column=day&g.x_type=ordinal&g.y_column=count(*)&g.y_type=quantitative
)
- [Related entities to ЗАЭС (ZNPP)](https://spevktator.io/vk/related_entities_ru?entity_name=ЗАЭС&_hide_sql=1)
- [Related entities to ZNPP (ЗАЭС)](https://spevktator.io/vk/related_entities_en?entity_name=ZNPP&_hide_sql=1)


## Installation

To install and run Spevktator locally, you need at least Python 3.9 and a couple Python libraries which you can install with `pip`.

### Development build (cloning git master branch):

```
git clone https://github.com/MischaU8/spevktator.git
cd spevktator
```

Recommended: Take a look at [venv](https://docs.python.org/3/tutorial/venv.html). This tool provides isolated Python environments, which are more practical than installing packages systemwide. It also allows installing packages without administrator privileges.

Install the Python dependencies, this will take a while:

```bash
pip3 install .
```

To get you started, download and decompress our VK sqlite database dump (23MB). This includes all public VK wall posts by `life`, `mash`, `nws_ru`, `ria` and `tassagency` between the period of `2022-02-01` and `2022-09-03`. But you can also decide to scrape your own data, see below.

```bash
wget -v -O data/vk.db.xz https://spevktator.io/static/vk_2022-09-03_lite.db.xz
xz -d data/vk.db.xz
```

## Usage

Spevktator uses the open source multi-tool [Datasette](https://datasette.io/) for exploring and publishing the collected data.
Run the Datasette server to explore the collected posts:

```bash
datasette data/
```

Visit the webinterface on http://127.0.0.1:8001

Learn more about Datasette and SQL on https://datasette.io/tutorials

## Scraping your own data

TODO

```bash
spevktator --help
```

## Additional Information
This section includes any additional information that you want to mention about the tool, including:
- Potential next steps for the tool (i.e. what you would implement if you had more time)
- Any limitations of the current implementation of the tool
- Motivation for design/architecture decisions

### Potential next steps

- Expose more VK post data (thumbnail images, videos, comments)
- Expose which channels to monitor through the UI
- Annotation (tags / comments) of posts
- UI notification when data has been updated
- User authentication for non-public information & configuration UI
- More robust installation instructions for various platforms (Windows, Docker)
- Packaging and distribution via pypi.

### Current limitations

- Only passive monitoring is performed, no VK account is needed, so private groups won’t be scraped.
- Comments and other personal information isn’t collected due to GDPR reasons.
- Sentiment prediction is based on RuSentiment and has moderate quality.
- Post metrics (shares, likes, views) are only tracked for a limited duration (last 5 posts).
- Post text longer than 2500 characters are not translated.
- Limited error handling and data loss recovery.

### Motivation for design / architecture decisions

The ability to conduct keyword searches with local data is much superior to any online search. I no longer need to worry about revealing details of my investigation to any third party. The online web interface is provided for demo purposes, but not required.

Setting up a data pipeline isn’t trivial, besides getting the raw data a lot of value is added with optional related data such as metrics, sentiment, translation and named-entity extraction.

This tool is modular, the data can be exported in various file formats (CSV, TSV, JSON) through [sqlite-utils](https://sqlite-utils.datasette.io/) while being stored in a very powerful and accessible database format (sqlite).
