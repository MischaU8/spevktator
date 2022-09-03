import httpx
import pathlib
import pytest
from click.testing import CliRunner
from pytest_httpx import HTTPXMock
import sqlite_utils
from spevktator import cli


@pytest.fixture
def vk_life_html():
    return open(pathlib.Path(__file__).parent / "vk_life.html").read()


def test_spevktator_fetch(tmpdir, vk_life_html, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url="https://m.vk.com/life", html=vk_life_html)
    # httpx_mock.add_exception(httpx.TimeoutException("No httpx_mock match found"))

    db_path = str(tmpdir / "data.db")
    result = CliRunner().invoke(
        cli.cli, ["fetch", db_path, "life", "--limit=1"], catch_exceptions=False
    )
    print(result.output)
    assert not result.exception, result.exception

    db = sqlite_utils.Database(db_path)
    assert {
        "posts",
        "posts_fts",
    }.issubset(db.table_names())

    posts = list(db["posts"].rows)
    assert len(posts) == 5
    assert posts == [
        {
            "id": "-24199209_18932515",
            "domain": "life",
            "date_utc": "2022-08-12T09:00:00",
            "text": 'Самая страшная пыточная современности находилась в Мариуполе, а боевики "Азова"* дали ей необычное название "Библиотека". Людей, которые подвергались там самым изощрённым мучениям и казням, нацисты называли "книгами". После освобождения города мир узнал об одном из самых жутких мест на Украине. Здесь держали пленников под страхом смерти, не зная сострадания и жалости, их истязали, уничтожая способность хоть как-то сопротивляться. О том, как банда неонацистов превратилась в секту "Азов"*, почитающую насилие и культ мёртвых, о том, кто стоит за этими убийцами и о зверствах, которые не должны быть забыты, мы рассказали в новом проекте "Трибунал". В первой серии проекта "Трибунал" "АЗОВ"*: история 4-го рейха" узники самого известного концлагеря современности, члены семей националистов и профессиональные историки рассказывают жёсткую правду о том, что все долгие восемь лет происходило на Юго-Востоке Украины * "Азов" — запрещённая в России террористическая организация.',
        },
        {
            "id": "-24199209_18981678",
            "domain": "life",
            "date_utc": "2022-09-03T12:40:00",
            "text": "Владимир Путин увеличил численность ВС РФ: https://life.ru/p/1518876",
        },
        {
            "id": "-24199209_18981640",
            "domain": "life",
            "date_utc": "2022-09-03T12:30:00",
            "text": "Cуд Москвы вынес окончательное решение в отношении Юрия Дудя*: https://life.ru/p/1518874 * Включены в реестр СМИ-иноагентов.",
        },
        {
            "id": "-24199209_18981607",
            "domain": "life",
            "date_utc": "2022-09-03T12:20:00",
            "text": 'Опубликовано пророческое сообщение умершей звезды "Дома-2": https://life.ru/p/1518819',
        },
        {
            "id": "-24199209_18981564",
            "domain": "life",
            "date_utc": "2022-09-03T12:11:00",
            "text": "Одна из известнейших россиянок уехала из России: https://life.ru/p/1518869",
        }]
    # print(posts)
