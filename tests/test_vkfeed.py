import httpx
import pathlib
import pytest
from pytest_httpx import HTTPXMock
from click.testing import CliRunner
from vkfeed import cli


@pytest.fixture
def vk_life_html():
    return open(pathlib.Path(__file__).parent / "vk_life.html").read()


def test_url(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url="https://test_url?a=1&b=2")
    # httpx_mock.add_exception(httpx.TimeoutException("No httpx_mock match found"))

    with httpx.Client() as client:
        response1 = client.delete("https://test_url?a=1&b=2")
        print(response1.status_code)
        response2 = client.get("https://test_url?b=2&a=1")
        print(response2.status_code)


def test_vkfeed_test(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url="https://httpbin.org/get")
    # httpx_mock.add_exception(httpx.TimeoutException("No httpx_mock match found"))

    result = CliRunner().invoke(cli.cli, ["test"], catch_exceptions=False)
    # print(result)
    assert not result.exception, result.exception


def test_vkfeed_listen(tmpdir, vk_life_html, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url="https://m.vk.com/life", html=vk_life_html)
    # httpx_mock.add_exception(httpx.TimeoutException("No httpx_mock match found"))

    db_path = str(tmpdir / "data.db")
    result = CliRunner().invoke(
        cli.cli, ["listen", db_path, "life"], catch_exceptions=False
    )
    assert not result.exception, result.exception
    print(result.output)

    # db = sqlite_utils.Database(db_path)
    # assert {
    #     "posts",
    #     "posts_fts",
    # }.issubset(db.table_names())
