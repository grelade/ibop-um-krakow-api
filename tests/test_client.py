from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs

import pytest
import responses
from responses import matchers

from ibop_um_krakow_api import (
    ApiError,
    AuthenticationError,
    ChargeFilter,
    IbopClient,
    NotFoundError,
)

from .conftest import (
    BASE,
    CUSTOMER,
    LOGIN_FAILED,
    LOGIN_PAGE,
    SHELL_PAGE,
    add_fixture,
    add_module,
    fixture_json,
    login_ok,
)

# ---- auth --------------------------------------------------------------------


def test_login_posts_form_and_saves_cookies(mocked: responses.RequestsMock, tmp_path: Path) -> None:
    mocked.add("GET", BASE + "/", body=LOGIN_PAGE, headers={"Set-Cookie": "PHPSESSID=abc; path=/"})
    mocked.add("POST", BASE + "/", body=SHELL_PAGE)
    sf = tmp_path / "s.json"
    c = IbopClient("login", "pw", session_file=sf)
    c.login()
    body = parse_qs(str(mocked.calls[1].request.body))
    assert body == {"JSTest": ["ok"], "user": ["login"], "pass": ["pw"], "login": ["Zaloguj"]}
    saved = json.loads(sf.read_text())
    assert saved[0]["name"] == "PHPSESSID" and saved[0]["value"] == "abc"
    assert sf.stat().st_mode & 0o777 == 0o600


def test_session_file_reused(mocked: responses.RequestsMock, tmp_path: Path) -> None:
    sf = tmp_path / "s.json"
    sf.write_text(json.dumps([{"name": "PHPSESSID", "value": "cached", "domain": "", "path": "/"}]))
    add_fixture(mocked, "CustomerList")
    c = IbopClient("login", "pw", session_file=sf)
    assert c.get_customers()[0].id == CUSTOMER
    assert len(mocked.calls) == 1
    assert "PHPSESSID=cached" in mocked.calls[0].request.headers["Cookie"]
    sf.write_text("garbage")
    assert not IbopClient("login", "pw", session_file=sf)._logged_in


def test_login_failure(mocked: responses.RequestsMock) -> None:
    mocked.add("GET", BASE + "/", body=LOGIN_PAGE)
    mocked.add("POST", BASE + "/", body=LOGIN_FAILED)
    with pytest.raises(AuthenticationError, match="Niepoprawne dane logowania"):
        IbopClient("login", "bad").login()


def test_login_requires_credentials() -> None:
    with pytest.raises(AuthenticationError):
        IbopClient().login()


def test_relogin_when_module_answers_empty(mocked: responses.RequestsMock) -> None:
    c = IbopClient("login", "pw")
    c._logged_in = True
    mocked.add(
        "GET",
        BASE + "/",
        body="",
        content_type="text/html",
        match=[matchers.query_param_matcher({"module": "Summary_v1"})],
    )
    login_ok(mocked)
    add_fixture(mocked, "Summary_v1")
    assert c.get_summary().next_payment_date is not None
    assert [call.request.method for call in mocked.calls] == ["GET", "GET", "POST", "GET"]


def test_expired_without_credentials(mocked: responses.RequestsMock) -> None:
    c = IbopClient()
    c._logged_in = True
    mocked.add("GET", BASE + "/", body=LOGIN_PAGE, content_type="text/html")
    with pytest.raises(AuthenticationError):
        c.get_summary()


def test_non_json_module(client: IbopClient, mocked: responses.RequestsMock) -> None:
    mocked.add("GET", BASE + "/", body="Fatal error", content_type="text/plain")
    with pytest.raises(ApiError, match="expected JSON"):
        client.get_summary()


def test_logout(client: IbopClient, mocked: responses.RequestsMock, tmp_path: Path) -> None:
    sf = tmp_path / "s.json"
    sf.write_text("[]")
    client.session_file = sf
    mocked.add("GET", BASE + "/", body=LOGIN_PAGE, match=[matchers.query_param_matcher({"logout": "true"})])
    client.logout()
    assert not client._logged_in and not sf.exists()


# ---- data --------------------------------------------------------------------


def test_account_methods(client: IbopClient, mocked: responses.RequestsMock) -> None:
    add_fixture(mocked, "UserConfig")
    add_fixture(mocked, "CustomerList")
    add_fixture(mocked, "CustomerInfo_v1")
    assert client.get_user().email == "zarzad@example.com"
    assert client.get_customers()[0].active
    assert client.get_customer_info().estates


def test_set_active_customer(client: IbopClient, mocked: responses.RequestsMock) -> None:
    add_fixture(mocked, "CustomerList")
    mocked.add(
        "POST",
        BASE + "/",
        body="",
        match=[
            matchers.query_param_matcher({"module": "CustomerList", "action": "changeActiveCustomer"}),
            matchers.urlencoded_params_matcher({"customerId": CUSTOMER}),
        ],
    )
    client.set_active_customer(CUSTOMER)
    with pytest.raises(NotFoundError):
        client.set_active_customer("999")


def test_ledger_filters(client: IbopClient, mocked: responses.RequestsMock) -> None:
    add_fixture(mocked, "Accountancy_v2")
    assert len(client.get_ledger_entries()) == 6
    unpaid = client.get_ledger_entries(ChargeFilter.UNPAID)
    assert [e.number for e in unpaid] == ["PK/2026/12/527351"]
    assert len(client.get_ledger_entries("paid")) == 5
    assert [e.number for e in client.iter_unpaid()] == ["PK/2026/12/527351"]


def test_charges(client: IbopClient, mocked: responses.RequestsMock) -> None:
    add_fixture(mocked, "Invoices_v1")
    assert len(client.get_charges()) == 4
    assert client.get_charge("PK/2026/12/527351").id == "11517605"
    assert client.get_charge("11517605").number == "PK/2026/12/527351"
    with pytest.raises(NotFoundError):
        client.get_charge("nope")


def test_books_declarations_requests(client: IbopClient, mocked: responses.RequestsMock) -> None:
    add_fixture(mocked, "InvoiceBook_v1")
    add_fixture(mocked, "Declarations_v1")
    add_fixture(mocked, "NotificationsHistory_v1")
    assert client.get_payment_books()[0].entries
    assert client.get_declarations()[0].monthly_fee is not None
    assert client.get_requests_history() == []
    mocked.replace(
        "GET",
        BASE + "/",
        body=json.dumps([{"id": 1, "temat": "x"}]),
        match=[matchers.query_param_matcher({"module": "NotificationsHistory_v1"})],
    )
    assert client.get_requests_history() == [{"id": 1, "temat": "x"}]


def test_download_document(client: IbopClient, mocked: responses.RequestsMock) -> None:
    add_fixture(mocked, "Documents_v1")
    mocked.add(
        "GET",
        BASE + "/dokumenty/cmVndWxhbWluLnBkZg==",
        body=b"%PDF-1.4",
        content_type="application/octet-stream",
    )
    f = client.download_document("1")
    assert f.filename == "regulamin.pdf" and f.content == b"%PDF-1.4"
    assert f.to_dict()["size"] == 8
    with pytest.raises(NotFoundError):
        client.download_document("nope")
    doc = client.get_documents()[0]
    mocked.replace("GET", BASE + "/dokumenty/cmVndWxhbWluLnBkZg==", body=b"")
    with pytest.raises(ApiError):
        client.download_document(doc)


def test_module_query(client: IbopClient, mocked: responses.RequestsMock) -> None:
    add_module(mocked, "Summary_v1", fixture_json("Summary_v1"))
    client.get_summary()
    assert mocked.calls[0].request.url == BASE + "/?module=Summary_v1"
