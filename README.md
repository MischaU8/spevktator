# Spevktator - OSINT tool to collect and analyse public VK community wall posts

[![Python](https://img.shields.io/badge/python-v3.9%20%7C%20v3.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/simonw/datasette/blob/main/LICENSE)

## Team Members
Mischa -  [Github profile](https://github.com/MischaU8)
Morsaki - [Medium blog](https://medium.com/@rosa.noctis532)

## Tool Description
Spevktator provides a combined live feed of 5 popular Russian news channels on VK, along with translations, sentiment analysis and visualisation tools, all of which is accessible online, from anywhere. We currently have an archive of over 65,000 posts, dating back to the beginning of February 2022.

Originally, it was created to help research domestic Russian propaganda narratives, but can also act as a monitoring hub for VK media content, allowing researchers and journalists to stay up to date on disinformation, even as chaotic events unfold. 

## Online Demo

https://spevktator.io/

## Installation

To install and run spevktator, you need at least Python 3.9 and a couple Python libraries which you can install with `pip`.

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

To get you started, download and decompress our VK sqlite database dump (23MB). This includes all public VK wall posts by `life`, `mash`, `nws_ru`, `ria` and `tassagency` between the period of `2022-02-01` and `2022-09-02`. But you can also decide to scrape your own data, see below.

```bash
wget -v -O data/vk.db.xz https://spevktator.io/static/vk_2022-09-02_lite.db.xz
xz -d data/vk.db.xz
```

## Usage

Run the Datasette server to explore the data:

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

### Current limitations

Only passive monitoring is performed, no VK account is needed, so private groups won’t be scraped.
Comments and other personal information isn’t collected due to GDPR reasons.
Sentiment prediction is based on RuSentiment and has moderate quality
Post metrics (shares, likes, views) are only tracked for a limited duration (last 5 posts)
Limited error handling and data loss recovery

### Motivation for design / architecture decisions
The ability to conduct keyword searches with local data is much superior to any online search. I no longer need to worry about revealing details of my investigation to any third party. The online web interface is provided for demo purposes, but not required.

Setting up a data pipeline isn’t trivial, besides getting the raw data a lot of value is added with optional related data such as metrics, sentiment, translation and named-entity extraction.

This tool is modular, the data can be exported in various file formats (CSV, TSV, JSON) through [sqlite-utils](https://sqlite-utils.datasette.io/) while being stored in a very powerful and accessible database format (sqlite).
