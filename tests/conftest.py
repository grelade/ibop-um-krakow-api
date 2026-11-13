"""Shared fixtures. All HTTP is mocked with ``responses``; fixtures under tests/fixtures are
anonymised captures of real ibop.mpo.krakow.pl module responses."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import responses
from responses import matchers

from ibop_um_krakow_api import IbopClient

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://ibop.mpo.krakow.pl"
CUSTOMER = "12345"

LOGIN_PAGE = '<html><form id="frmLogin" method="post" action="?"></form></html>'
LOGIN_FAILED = LOGIN_PAGE + '<div class="error">Niepoprawne dane logowania!</div>'
SHELL_PAGE = '<html><div id="tresc"></div></html>'


def fixture_json(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def mocked() -> Iterator[responses.RequestsMock]:
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps


@pytest.fixture
def client(mocked: responses.RequestsMock) -> IbopClient:
    """A client that believes it is logged in (no login round-trip)."""
    c = IbopClient("login", "secret")
    c._logged_in = True
    return c


def add_module(rsps: responses.RequestsMock, module: str, data: Any, **params: str) -> None:
    """Mock ``GET /?module=<module>`` answering JSON as text/html, like the portal."""
    rsps.add(
        "GET",
        BASE + "/",
        body="\n" + json.dumps(data, ensure_ascii=False),
        content_type="text/html; charset=UTF-8",
        match=[matchers.query_param_matcher({"module": module, **params})],
    )


def add_fixture(rsps: responses.RequestsMock, module: str, fixture: str | None = None) -> None:
    add_module(rsps, module, fixture_json(fixture or module))


def login_ok(rsps: responses.RequestsMock) -> None:
    rsps.add(
        "GET",
        BASE + "/",
        body=LOGIN_PAGE,
        content_type="text/html",
        match=[matchers.query_string_matcher("")],
    )
    rsps.add("POST", BASE + "/", body=SHELL_PAGE, content_type="text/html")
