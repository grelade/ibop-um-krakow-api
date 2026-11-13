from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from ibop_um_krakow_api import ParseError, parsers

from .conftest import CUSTOMER, LOGIN_FAILED, LOGIN_PAGE, SHELL_PAGE, fixture_json


def test_scalars() -> None:
    assert parsers.to_decimal("8 184,00") == Decimal("8184.00")
    assert parsers.to_decimal("-140.00") == Decimal("-140.00")
    assert parsers.to_decimal("1\xa0000,50") == Decimal("1000.50")
    assert parsers.to_decimal(140) == Decimal("140")
    assert parsers.to_decimal("") is None
    assert parsers.to_decimal("abc") is None
    assert parsers.to_date("2026-01-14 23:59:59") == date(2026, 1, 14)
    assert parsers.to_date("nope") is None
    assert parsers.to_date(None) is None
    assert parsers.to_datetime("2026-10-24 12:39:07") == datetime(2026, 10, 24, 12, 39, 7)
    assert parsers.to_datetime("x") is None


def test_login_page_detection() -> None:
    assert parsers.is_login_page(LOGIN_PAGE)
    assert not parsers.is_login_page(SHELL_PAGE)
    assert parsers.login_error(LOGIN_FAILED) == "Niepoprawne dane logowania!"
    assert parsers.login_error(LOGIN_PAGE) is None


def test_user_config() -> None:
    u = parsers.parse_user_config(fixture_json("UserConfig"))
    assert u.name == "WSPÓLNOTA MIESZKANIOWA TESTOWA 1"
    assert u.email == "zarzad@example.com"
    assert u.last_login == datetime(2026, 10, 24, 12, 39, 7)
    assert u.session_timeout_seconds == 420
    with pytest.raises(ParseError):
        parsers.parse_user_config([])
    with pytest.raises(ParseError):
        parsers.parse_user_config({})


def test_customers() -> None:
    (c,) = parsers.parse_customers(fixture_json("CustomerList"))
    assert c.id == CUSTOMER and c.active and c.name.startswith("WSPÓLNOTA")


def test_customer_info() -> None:
    info = parsers.parse_customer_info(fixture_json("CustomerInfo_v1"))
    assert info.customer_id == CUSTOMER
    assert info.nip == "1111111111" and info.regon == "222222222"
    assert info.pesel is None and info.correspondence_address is None
    assert info.address == "TESTOWA 1A/2, 00-001 KRAKÓW"
    (estate,) = info.estates
    assert estate.address == "TESTOWA 1A, 00-001 KRAKÓW"
    assert estate.code == "11111"
    with pytest.raises(ParseError):
        parsers.parse_customer_info({"nazwa": "x"})
    with pytest.raises(ParseError):
        parsers.parse_customer_info([])


def test_summary() -> None:
    s = parsers.parse_summary(fixture_json("Summary_v1"))
    assert s.balance == Decimal("-140.00")
    assert s.bank_account == "00 1020 0000 0000 0000 0001 2345"
    assert s.next_payment_date == date(2026, 11, 14)
    assert len(s.months) == 12
    assert s.months[0].month == 1 and s.months[0].assessed == Decimal("140.00")
    assert s.months[0].due_date == date(2026, 1, 14)


def test_ledger() -> None:
    ledger = parsers.parse_ledger(fixture_json("Accountancy_v2"))
    assert len(ledger.entries) == 6
    first = ledger.entries[0]
    assert first.number == "PK/2026/12/527351"
    assert first.issue_date == date(2026, 1, 2) and first.due_date == date(2026, 12, 14)
    assert first.amount_due == Decimal("140.00")
    assert first.paid == Decimal("100.00") and first.remaining == Decimal("40.00")
    assert not first.is_paid and ledger.entries[1].is_paid
    assert first.title == "RozrG" and first.account == "221012345" and first.customer_id == CUSTOMER
    assert ledger.total_due == Decimal("840.00")
    assert ledger.total_paid == Decimal("800.00")
    assert ledger.difference == Decimal("40.00")
    with pytest.raises(ParseError):
        parsers.parse_ledger({"pozycje": [{"wn": "1,00"}]})
    with pytest.raises(ParseError):
        parsers.parse_ledger({"pozycje": [{"nr": "X", "wn": "?", "ma": "0", "ro": "0"}]})
    with pytest.raises(ParseError):
        parsers.parse_ledger({"pozycje": "x"})


def test_charges() -> None:
    charges = parsers.parse_charges(fixture_json("Invoices_v1"))
    assert len(charges) == 4
    c = charges[0]
    assert c.number == "PK/2026/12/527351" and c.id == "11517605"
    assert c.issue_date == date(2026, 1, 2) and c.due_date == date(2026, 12, 14)
    assert c.amount == Decimal("140.00")
    assert c.payment_book == "PK/2026/1/40001"
    assert c.customer.nip == "1111111111"
    assert c.seller.nip == "675-000-65-47"
    assert c.seller.name is not None and "\n" not in c.seller.name
    assert c.lines[0].description == "Opłata za gospodarowanie odpadami komunalnymi"
    assert c.lines[0].amount == Decimal("140.00")
    assert c.correction_number is None
    with pytest.raises(ParseError):
        parsers.parse_charges([{"id": 1}])


def test_payment_books() -> None:
    books = parsers.parse_payment_books(fixture_json("InvoiceBook_v1"))
    assert len(books) == 2
    assert books[0].issue_date is not None and books[1].issue_date is not None
    assert books[0].issue_date >= books[1].issue_date  # newest first
    assert books[0].number == "PK/2026/1/40001"
    e = books[0].entries[0]
    assert e.number == "PK/2026/12/527351" and e.amount == Decimal("140.00")
    assert e.due_date == date(2026, 12, 14)


def test_declarations() -> None:
    (d,) = parsers.parse_declarations(fixture_json("Declarations_v1"))
    assert d.id == "100001" and d.number == "3333333"
    assert d.valid_from == date(2020, 11, 1) and d.type == "DW" and d.version == 5
    assert d.property_address == "TESTOWA 1A, 00-001 KRAKÓW"
    assert d.residents == 4 and d.monthly_fee == Decimal("92.00")
    assert d.raw["et"] == "Budynek wielorodzinny"


def test_documents() -> None:
    (doc,) = parsers.parse_documents(fixture_json("Documents_v1"))
    assert doc.filename == "regulamin.pdf"
    assert doc.path == "dokumenty/cmVndWxhbWluLnBkZg=="
    assert doc.description is None
