# Installation of spevktator

To install and run spevktator, you need at least Python 3.9 and a couple Python libraries which you can install with `pip`.

## Development build (cloning git master branch):

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

## Basic usage

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
