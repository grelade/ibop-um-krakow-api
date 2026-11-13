"""Typed records returned by the SDK.

All money is ``Decimal`` (PLN), dates are ``datetime.date``. ``to_dict()`` gives a
JSON-friendly ``dict`` (used by the CLI).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def to_jsonable(value: Any) -> Any:
    """Recursively convert dataclasses/Decimal/date/Enum into JSON-serialisable values."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


class _Record:
    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = to_jsonable(self)
        return result


class ChargeFilter(str, Enum):
    """Filter of the ledger, same as the "Rozrachunki" side menu."""

    ALL = "all"
    PAID = "paid"
    UNPAID = "unpaid"


# ---- account -----------------------------------------------------------------


@dataclass
class User(_Record):
    """The logged-in user (``?module=UserConfig``)."""

    name: str | None
    email: str | None
    phone: str | None
    last_login: datetime | None
    session_timeout_seconds: int | None = None


@dataclass
class Customer(_Record):
    """A customer (payer) available on this login (``?module=CustomerList``)."""

    id: str
    name: str
    active: bool


@dataclass
class Estate(_Record):
    """A property the waste fee is charged for."""

    address: str
    name: str | None
    code: str | None
    lp: int | None = None


@dataclass
class CustomerInfo(_Record):
    """Customer master data (``?module=CustomerInfo_v1``)."""

    customer_id: str
    name: str
    address: str | None
    correspondence_address: str | None
    nip: str | None
    regon: str | None
    pesel: str | None
    phone: str | None
    mobile: str | None
    fax: str | None
    email: str | None
    estates: list[Estate] = field(default_factory=list)


# ---- money -------------------------------------------------------------------


@dataclass
class MonthlyCharge(_Record):
    """One month of the yearly schedule shown on the "Podsumowanie" page."""

    year: int
    month: int
    assessed: Decimal | None  # wymiar: "Kwota do zapłaty"
    booked: Decimal | None  # ksiegowosc: "Kwota zaksięgowana"
    due_date: date | None


@dataclass
class Summary(_Record):
    """Payment summary (``?module=Summary_v1``)."""

    balance: Decimal | None  # "Saldo" exactly as the portal reports it
    bank_account: str | None  # individual account number to pay into
    payment_method: str | None
    next_payment_date: date | None
    months: list[MonthlyCharge] = field(default_factory=list)


@dataclass
class LedgerEntry(_Record):
    """A receivable in the ledger ("Rozrachunki", ``?module=Accountancy_v2``)."""

    number: str
    issue_date: date | None
    due_date: date | None
    amount_due: Decimal  # wn: "Kwota należna do zapłaty"
    paid: Decimal  # ma
    remaining: Decimal  # ro
    title: str | None  # ty, e.g. "RozrG"
    account: str | None  # ko
    customer_id: str | None

    @property
    def is_paid(self) -> bool:
        return self.remaining <= 0


@dataclass
class Ledger(_Record):
    entries: list[LedgerEntry]
    total_due: Decimal | None
    total_paid: Decimal | None
    difference: Decimal | None  # total_due - total_paid


@dataclass
class Party(_Record):
    name: str | None
    address: str | None
    nip: str | None
    regon: str | None
    pesel: str | None = None
    phone: str | None = None
    fax: str | None = None
    email: str | None = None


@dataclass
class ChargeLine(_Record):
    lp: int | None
    description: str
    estate_address: str | None
    amount: Decimal | None


@dataclass
class Charge(_Record):
    """A fee notice ("Naliczenia", ``?module=Invoices_v1``): one monthly instalment."""

    id: str
    number: str
    issue_date: date | None
    sale_date: date | None
    due_date: date | None
    payment_type: str | None
    payment_book: str | None
    amount: Decimal | None
    bank_account: str | None
    customer: Party
    seller: Party
    lines: list[ChargeLine] = field(default_factory=list)
    correction_number: str | None = None
    corrected_id: str | None = None


@dataclass
class PaymentBookEntry(_Record):
    id: str
    number: str
    issue_date: date | None
    due_date: date | None
    amount: Decimal | None


@dataclass
class PaymentBook(_Record):
    """A yearly payment book ("Książeczki", ``?module=InvoiceBook_v1``)."""

    id: str
    number: str
    issue_date: date | None
    entries: list[PaymentBookEntry] = field(default_factory=list)


@dataclass
class Declaration(_Record):
    """A waste-fee declaration (``?module=Declarations_v1``)."""

    id: str
    number: str | None
    created: date | None
    valid_from: date | None
    type: str | None  # "DW", ...
    version: int | None
    description: str | None
    submitter_type: str | None
    submitter_name: str | None
    property_address: str | None
    building_type: str | None
    residents: int | None
    household: str | None
    monthly_fee: Decimal | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class Document(_Record):
    """A downloadable document (regulations etc., ``?module=Documents_v1``)."""

    id: str
    name: str
    description: str | None
    filename: str | None
    path: str  # relative URL, e.g. ``dokumenty/cmVndWxhbWluLnBkZg==``


@dataclass
class DownloadedFile(_Record):
    filename: str | None
    content_type: str | None
    content: bytes = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {"filename": self.filename, "content_type": self.content_type, "size": len(self.content)}
