"""Unofficial Python SDK for iBOP UM Kraków (ibop.mpo.krakow.pl), the Kraków waste-fee portal."""

from importlib.metadata import PackageNotFoundError, version

from .client import BASE_URL, IbopClient
from .exceptions import ApiError, AuthenticationError, IbopError, NotFoundError, ParseError
from .models import (
    Charge,
    ChargeFilter,
    ChargeLine,
    Customer,
    CustomerInfo,
    Declaration,
    Document,
    DownloadedFile,
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

try:
    __version__ = version("ibop-um-krakow-api")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0"

__all__ = [
    "BASE_URL",
    "ApiError",
    "AuthenticationError",
    "Charge",
    "ChargeFilter",
    "ChargeLine",
    "Customer",
    "CustomerInfo",
    "Declaration",
    "Document",
    "DownloadedFile",
    "Estate",
    "IbopClient",
    "IbopError",
    "Ledger",
    "LedgerEntry",
    "MonthlyCharge",
    "NotFoundError",
    "ParseError",
    "Party",
    "PaymentBook",
    "PaymentBookEntry",
    "Summary",
    "User",
    "__version__",
]
