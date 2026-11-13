"""HTTP client for iBOP UM Kraków (https://ibop.mpo.krakow.pl), the municipal waste-fee portal.

The portal is a PHP app with an Adobe Spry front end: the page is a shell and every screen
loads its data from ``/?module=<Name>``, which answers JSON (served as ``text/html``). Login is
a plain form post that sets ``PHPSESSID``. An expired session makes the modules answer an
empty body. See API.md for the endpoint reference.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests

from . import parsers
from .exceptions import ApiError, AuthenticationError, NotFoundError
from .models import (
    Charge,
    ChargeFilter,
    Customer,
    CustomerInfo,
    Declaration,
    Document,
    DownloadedFile,
    Ledger,
    LedgerEntry,
    PaymentBook,
    Summary,
    User,
)

log = logging.getLogger(__name__)

BASE_URL = "https://ibop.mpo.krakow.pl"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"
)

# module names (``/?module=…``)
MOD_USER_CONFIG = "UserConfig"
MOD_CUSTOMERS = "CustomerList"
MOD_CUSTOMER_INFO = "CustomerInfo_v1"
MOD_SUMMARY = "Summary_v1"
MOD_LEDGER = "Accountancy_v2"
MOD_CHARGES = "Invoices_v1"
MOD_PAYMENT_BOOKS = "InvoiceBook_v1"
MOD_DECLARATIONS = "Declarations_v1"
MOD_DOCUMENTS = "Documents_v1"
MOD_REQUESTS_HISTORY = "NotificationsHistory_v1"


def _filename(r: requests.Response) -> str | None:
    cd = r.headers.get("content-disposition") or ""
    m = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", cd, re.I) or re.search(r'filename="?([^";]+)"?', cd)
    return unquote(m.group(1).strip()) if m else None


class IbopClient:
    """Logged-in session against ibop.mpo.krakow.pl.

    >>> with IbopClient("login", "secret") as c:
    ...     ledger = c.get_ledger()
    ...     print(ledger.difference, [e.number for e in ledger.entries if not e.is_paid])

    All data is for the *active* customer of the login; see :meth:`get_customers` and
    :meth:`set_active_customer` for logins that manage several.
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        *,
        session: requests.Session | None = None,
        session_file: str | Path | None = None,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.session_file = Path(session_file).expanduser() if session_file else None
        self._logged_in = False
        if self.session_file and self.session_file.exists():
            self._load_cookies()

    # ---- context manager -----------------------------------------------------

    def __enter__(self) -> IbopClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.save_session()
        self.session.close()

    # ---- session persistence -------------------------------------------------

    def _load_cookies(self) -> None:
        assert self.session_file is not None
        try:
            cookies = json.loads(self.session_file.read_text())
        except (OSError, ValueError):
            log.warning("ignoring unreadable session file %s", self.session_file)
            return
        if not isinstance(cookies, list):
            return
        for c in cookies:
            self.session.cookies.set(
                c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/")
            )
        self._logged_in = bool(cookies)

    def save_session(self) -> None:
        """Write cookies to ``session_file`` (if set) so the next run can skip logging in."""
        if not self.session_file or not self._logged_in:
            return
        cookies = [
            {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
            for c in self.session.cookies
            if c.value is not None
        ]
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.session_file.write_text(json.dumps(cookies))
        self.session_file.chmod(0o600)

    # ---- auth ----------------------------------------------------------------

    def login(self) -> None:
        """Post the ``frmLogin`` form (``user``, ``pass``)."""
        if not self.username or not self.password:
            raise AuthenticationError("username and password are required to log in")
        self.session.cookies.clear()
        self._logged_in = False
        self.session.get(self.base_url + "/", timeout=self.timeout).raise_for_status()
        r = self.session.post(
            self.base_url + "/?",
            data={"JSTest": "ok", "user": self.username, "pass": self.password, "login": "Zaloguj"},
            timeout=self.timeout,
        )
        r.raise_for_status()
        if parsers.is_login_page(r.text):
            raise AuthenticationError(
                "login failed: " + (parsers.login_error(r.text) or "login form shown again")
            )
        self._logged_in = True
        self.save_session()

    def logout(self) -> None:
        """End the server-side session and forget cookies."""
        try:
            self.session.get(self.base_url + "/?logout=true", timeout=self.timeout)
        finally:
            self.session.cookies.clear()
            self._logged_in = False
            if self.session_file and self.session_file.exists():
                self.session_file.unlink()

    def _ensure_login(self) -> None:
        if not self._logged_in:
            self.login()

    def request(
        self, method: str, params: dict[str, Any], *, check_expired: bool = True, **kwargs: Any
    ) -> requests.Response:
        """Authenticated request to ``/?…``; logs in again once when the session has expired
        (the portal then answers an empty body or the login page)."""
        self._ensure_login()
        kwargs.setdefault("timeout", self.timeout)
        for attempt in (1, 2):
            r = self.session.request(method, self.base_url + "/", params=params, **kwargs)
            r.raise_for_status()
            expired = check_expired and (
                not r.content.strip()
                or ("html" in (r.headers.get("content-type") or "") and parsers.is_login_page(r.text))
            )
            if expired:
                if attempt == 1 and self.username and self.password:
                    log.info("session expired, logging in again")
                    self.login()
                    continue
                raise AuthenticationError("session expired and could not be re-established")
            return r
        raise AuthenticationError("session could not be re-established")  # pragma: no cover

    def _module(self, module: str, **params: Any) -> Any:
        r = self.request("GET", {"module": module, **params})
        try:
            return json.loads(r.text)
        except ValueError as e:
            raise ApiError(f"{module}: expected JSON, got {r.text[:80]!r}", r.text) from e

    # ---- account -------------------------------------------------------------

    def get_user(self) -> User:
        """Logged-in user: name, e-mail, last login."""
        return parsers.parse_user_config(self._module(MOD_USER_CONFIG))

    def get_customers(self) -> list[Customer]:
        """Customers available on this login; one of them is active."""
        return parsers.parse_customers(self._module(MOD_CUSTOMERS))

    def set_active_customer(self, customer_id: str) -> None:
        """Switch the customer the other methods return data for (session-level setting)."""
        if customer_id not in {c.id for c in self.get_customers()}:
            raise NotFoundError(f"customer {customer_id} not available on this login")
        self.request(
            "POST",
            {"module": MOD_CUSTOMERS, "action": "changeActiveCustomer"},
            data={"customerId": customer_id},
            check_expired=False,  # the action may answer an empty body; the page just reloads
        )

    def get_customer_info(self) -> CustomerInfo:
        """Customer master data: name, address, NIP/REGON, contact, properties."""
        return parsers.parse_customer_info(self._module(MOD_CUSTOMER_INFO))

    # ---- money ---------------------------------------------------------------

    def get_summary(self) -> Summary:
        """Balance, bank account to pay into and this year's monthly schedule."""
        return parsers.parse_summary(self._module(MOD_SUMMARY))

    def get_ledger(self) -> Ledger:
        """All receivables with amount due / paid / remaining ("Rozrachunki")."""
        return parsers.parse_ledger(self._module(MOD_LEDGER))

    def get_ledger_entries(self, filter: ChargeFilter | str = ChargeFilter.ALL) -> list[LedgerEntry]:
        entries = self.get_ledger().entries
        f = ChargeFilter(filter)
        if f is ChargeFilter.PAID:
            return [e for e in entries if e.is_paid]
        if f is ChargeFilter.UNPAID:
            return [e for e in entries if not e.is_paid]
        return entries

    def get_charges(self) -> list[Charge]:
        """Fee notices ("Naliczenia") with seller, customer, lines and bank account, newest first."""
        return parsers.parse_charges(self._module(MOD_CHARGES))

    def get_charge(self, number: str) -> Charge:
        for c in self.get_charges():
            if number in (c.number, c.id):
                return c
        raise NotFoundError(f"charge {number} not found")

    def get_payment_books(self) -> list[PaymentBook]:
        """Yearly payment books ("Książeczki") with their instalments, newest first."""
        return parsers.parse_payment_books(self._module(MOD_PAYMENT_BOOKS))

    # ---- declarations & documents --------------------------------------------

    def get_declarations(self) -> list[Declaration]:
        """Waste-fee declarations filed for this customer."""
        return parsers.parse_declarations(self._module(MOD_DECLARATIONS))

    def get_requests_history(self) -> list[dict[str, Any]]:
        """History of requests sent through the portal ("Historia Zgłoszeń"), raw rows."""
        data = self._module(MOD_REQUESTS_HISTORY)
        return [dict(x) for x in data] if isinstance(data, list) else []

    def get_documents(self) -> list[Document]:
        """Documents published in the portal (regulations, ...)."""
        return parsers.parse_documents(self._module(MOD_DOCUMENTS))

    def download_document(self, document: Document | str) -> DownloadedFile:
        """Download a document by object, id or name."""
        if isinstance(document, str):
            found = next((d for d in self.get_documents() if document in (d.id, d.name, d.filename)), None)
            if found is None:
                raise NotFoundError(f"document {document} not found")
            document = found
        self._ensure_login()
        r = self.session.get(f"{self.base_url}/{document.path}", timeout=self.timeout)
        r.raise_for_status()
        if not r.content:
            raise ApiError(f"document {document.name}: empty response")
        ctype = (r.headers.get("content-type") or "").split(";")[0].strip() or None
        return DownloadedFile(
            filename=document.filename or _filename(r), content_type=ctype, content=r.content
        )

    def iter_unpaid(self) -> Iterator[LedgerEntry]:
        """Ledger entries with something left to pay."""
        yield from self.get_ledger_entries(ChargeFilter.UNPAID)
