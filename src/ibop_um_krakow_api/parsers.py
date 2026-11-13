"""Pure functions turning iBOP JSON (and the login page HTML) into models. No I/O here.

The portal's ``?module=…`` endpoints answer JSON with short Polish field names
(``wn``/``ma``/``ro``, ``nd``/``nw``/``nt``, …). Amounts are strings in Polish format
(``"8 184,00"``, sometimes ``"-140.00"``); dates are ``YYYY-MM-DD``.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .exceptions import ParseError
from .models import (
    Charge,
    ChargeLine,
    Customer,
    CustomerInfo,
    Declaration,
    Document,
    Estate,
    Ledger,
    LedgerEntry,
    MonthlyCharge,
    Party,
    PaymentBook,
    PaymentBookEntry,
    Summary,
    User,
)

# ---- scalars -----------------------------------------------------------------


def to_decimal(value: Any) -> Decimal | None:
    """``"8 184,00"`` / ``"-140.00"`` / ``140`` -> ``Decimal``."""
    if value is None or value == "":
        return None
    text = str(value).replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _money(value: Any, what: str) -> Decimal:
    d = to_decimal(value)
    if d is None:
        raise ParseError(f"{what}: not an amount: {value!r}")
    return d


def to_date(value: Any) -> date | None:
    """``YYYY-MM-DD`` (optionally followed by a time) -> ``date``."""
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def to_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _id(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _list(data: Any, what: str) -> list[Any]:
    if data is None:
        return []
    if not isinstance(data, list):
        raise ParseError(f"{what}: expected a list, got {type(data).__name__}")
    return data


def _obj(data: Any, what: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ParseError(f"{what}: expected an object, got {type(data).__name__}")
    return data


# ---- login page --------------------------------------------------------------


def is_login_page(text: str) -> bool:
    """The login form is shown when not logged in (also after a failed login)."""
    return 'id="frmLogin"' in text


def login_error(text: str) -> str | None:
    """Error message shown above the login form, e.g. ``Niepoprawne dane logowania!``."""
    m = re.search(r"(Niepoprawne[^<]*|Konto[^<]*zablokowane[^<]*|Błędn[^<]*)", text)
    return html.unescape(m.group(1)).strip() if m else None


# ---- account -----------------------------------------------------------------


def parse_user_config(data: Any) -> User:
    """``UserConfig`` is a list of ``{name, value}`` pairs."""
    pairs = {p.get("name"): p.get("value") for p in _list(data, "UserConfig") if isinstance(p, dict)}
    if not pairs:
        raise ParseError("UserConfig: empty")
    timeout = _int(pairs.get("TimeOut"))
    return User(
        name=_str(pairs.get("customername") or pairs.get("username")),
        email=_str(pairs.get("useremail")),
        phone=_str(pairs.get("tel")),
        last_login=to_datetime(pairs.get("lastlogged")),
        session_timeout_seconds=timeout // 1000 if timeout else None,
    )


def parse_customers(data: Any) -> list[Customer]:
    return [
        Customer(id=_id(c.get("id")), name=str(c.get("nazwa") or ""), active=str(c.get("active")) == "true")
        for c in _list(data, "CustomerList")
    ]


def parse_customer_info(data: Any) -> CustomerInfo:
    d = _obj(data, "CustomerInfo_v1")
    if not d.get("customerid"):
        raise ParseError("CustomerInfo_v1: missing customerid")
    return CustomerInfo(
        customer_id=_id(d["customerid"]),
        name=str(d.get("nazwa") or ""),
        address=_str(d.get("adres")),
        correspondence_address=_str(d.get("korespondencja")),
        nip=_str(d.get("nip")),
        regon=_str(d.get("regon")),
        pesel=_str(d.get("pesel")),
        phone=_str(d.get("tel")),
        mobile=_str(d.get("kom")),
        fax=_str(d.get("fax")),
        email=_str(d.get("email")),
        estates=[
            Estate(
                address=re.sub(r"\s+,", ",", str(e.get("adres") or "")).strip(),
                name=_str(e.get("nazwa")),
                code=_str(e.get("estateCode")),
                lp=_int(e.get("lp")),
            )
            for e in d.get("nieruchomosci") or []
        ],
    )


# ---- money -------------------------------------------------------------------


def parse_summary(data: Any) -> Summary:
    d = _obj(data, "Summary_v1")
    return Summary(
        balance=to_decimal(d.get("saldo")),
        bank_account=_str(d.get("bankaccountno")),
        payment_method=_str(d.get("paymentmethod")),
        next_payment_date=to_date(d.get("paymentdate")),
        months=[
            MonthlyCharge(
                year=int(m["year"]),
                month=int(m["month"]),
                assessed=to_decimal(m.get("wymiar")),
                booked=to_decimal(m.get("ksiegowosc")),
                due_date=to_date(m.get("minimumPaymentDate") or m.get("paymentDate")),
            )
            for m in d.get("result") or []
        ],
    )


def parse_ledger(data: Any) -> Ledger:
    d = _obj(data, "Accountancy_v2")
    entries = []
    for p in _list(d.get("pozycje"), "Accountancy_v2.pozycje"):
        if not p.get("nr"):
            raise ParseError("Accountancy_v2: entry without nr")
        entries.append(
            LedgerEntry(
                number=str(p["nr"]),
                issue_date=to_date(p.get("dw")),
                due_date=to_date(p.get("tp")),
                amount_due=_money(p.get("wn"), "wn"),
                paid=_money(p.get("ma"), "ma"),
                remaining=_money(p.get("ro"), "ro"),
                title=_str(p.get("ty")),
                account=_str(p.get("ko")),
                customer_id=_str(p.get("kontrah")),
            )
        )
    return Ledger(
        entries=entries,
        total_due=to_decimal(d.get("sumawn")),
        total_paid=to_decimal(d.get("sumama")),
        difference=to_decimal(d.get("roznica")),
    )


def parse_charges(data: Any) -> list[Charge]:
    out = []
    for c in _list(data, "Invoices_v1"):
        if not c.get("nd"):
            raise ParseError("Invoices_v1: charge without nd")
        out.append(
            Charge(
                id=_id(c.get("id")),
                number=str(c["nd"]),
                issue_date=to_date(c.get("nw")),
                sale_date=to_date(c.get("ns")),
                due_date=to_date(c.get("nt")),
                payment_type=_str(c.get("np")),
                payment_book=_str(c.get("ib")),
                amount=to_decimal(c.get("brutto")),
                bank_account=_str(c.get("ba")),
                customer=Party(
                    name=_str(c.get("nn")),
                    address=_str(c.get("na")),
                    nip=_str(c.get("ni")),
                    regon=_str(c.get("nr")),
                    pesel=_str(c.get("npe")),
                ),
                seller=Party(
                    name=_str(re.sub(r"\s*\n\s*", " ", str(c.get("sn") or ""))),
                    address=_str(c.get("sa")),
                    nip=_str(c.get("si")),
                    regon=_str(c.get("sr")),
                    phone=_str(c.get("st")),
                    fax=_str(c.get("sf")),
                    email=_str(c.get("se")),
                ),
                lines=[
                    ChargeLine(
                        lp=_int(p.get("lp")),
                        description=str(p.get("pn") or ""),
                        estate_address=_str(p.get("ad")),
                        amount=to_decimal(p.get("pb")),
                    )
                    for p in c.get("positions") or []
                ],
                correction_number=_str(c.get("cdnr")),
                corrected_id=_str(c.get("cid")),
            )
        )
    return out


def parse_payment_books(data: Any) -> list[PaymentBook]:
    books = [
        PaymentBook(
            id=_id(b.get("k_id")),
            number=str(b.get("k_dn") or ""),
            issue_date=to_date(b.get("k_isd")),
            entries=[
                PaymentBookEntry(
                    id=_id(i.get("i_id")),
                    number=str(i.get("i_dn") or ""),
                    issue_date=to_date(i.get("i_isd")),
                    due_date=to_date(i.get("i_ipd")),
                    amount=to_decimal(i.get("i_brutto")),
                )
                for i in b.get("invoices") or []
            ],
        )
        for b in _list(data, "InvoiceBook_v1")
    ]
    return sorted(books, key=lambda b: b.issue_date or date.min, reverse=True)


def _address(street: Any, house: Any, flat: Any, postal: Any, city: Any) -> str | None:
    number = "/".join(p for p in (_str(house), _str(flat)) if p)
    first = " ".join(p for p in (_str(street), number) if p)
    second = " ".join(p for p in (_str(postal), _str(city)) if p)
    return ", ".join(p for p in (first, second) if p) or None


def parse_declarations(data: Any) -> list[Declaration]:
    out = []
    for d in _list(data, "Declarations_v1"):
        out.append(
            Declaration(
                id=_id(d.get("id")),
                number=_str(d.get("bc")),
                created=to_date(d.get("cd")),
                valid_from=to_date(d.get("ad")),
                type=_str(d.get("dt")),
                version=_int(d.get("ver")),
                description=_str(d.get("dcr")),
                submitter_type=_str(d.get("eot")),
                submitter_name=_str(d.get("nn")),
                property_address=_address(d.get("eu"), d.get("eh"), d.get("el"), d.get("ek"), d.get("ec")),
                building_type=_str(d.get("et")),
                residents=_int(d.get("rn")),
                household=_str(d.get("hhdesc")),
                monthly_fee=to_decimal(d.get("ra")),
                raw=dict(d),
            )
        )
    return out


def parse_documents(data: Any) -> list[Document]:
    return [
        Document(
            id=_id(d.get("id")),
            name=str(d.get("name") or ""),
            description=_str(d.get("description")),
            filename=_str(d.get("filename")),
            path="dokumenty/" + str(d.get("temp") or ""),
        )
        for d in _list(data, "Documents_v1")
    ]
