"""Read-only smoke tests against the real ibop.mpo.krakow.pl.

Skipped unless IBOP_LIVE=1 and IBOP_USER / IBOP_PASS are set (a .env file in the project
root works too). Run with: ``IBOP_LIVE=1 uv run pytest -m live``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from ibop_um_krakow_api import IbopClient
from ibop_um_krakow_api.cli import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (
            os.environ.get("IBOP_LIVE") == "1" and os.environ.get("IBOP_USER") and os.environ.get("IBOP_PASS")
        ),
        reason="set IBOP_LIVE=1 and IBOP_USER/IBOP_PASS to run live tests",
    ),
]


@pytest.fixture(scope="module")
def live() -> Iterator[IbopClient]:
    with IbopClient(os.environ["IBOP_USER"], os.environ["IBOP_PASS"]) as c:
        yield c


def test_account(live: IbopClient) -> None:
    assert live.get_user().name
    customers = live.get_customers()
    assert any(c.active for c in customers)
    assert live.get_customer_info().customer_id in {c.id for c in customers}


def test_money(live: IbopClient) -> None:
    assert live.get_summary().months
    ledger = live.get_ledger()
    assert ledger.total_due is not None
    assert all(e.amount_due >= 0 for e in ledger.entries)
    charges = live.get_charges()
    assert charges
    assert live.get_charge(charges[0].number).id == charges[0].id
    assert isinstance(live.get_payment_books(), list)


def test_declarations_and_documents(live: IbopClient) -> None:
    assert isinstance(live.get_declarations(), list)
    assert isinstance(live.get_requests_history(), list)
    docs = live.get_documents()
    if docs:
        assert live.download_document(docs[0]).content
