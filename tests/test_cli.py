from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import responses

from ibop_um_krakow_api import cli

from .conftest import BASE, CUSTOMER, LOGIN_FAILED, LOGIN_PAGE, add_fixture, login_ok


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.chdir(tmp_path)  # no stray .env
    monkeypatch.setenv("IBOP_USER", "login")
    monkeypatch.setenv("IBOP_PASS", "secret")
    return tmp_path


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, object]:
    code = cli.main(["--session-file", "", *argv])
    out = capsys.readouterr().out
    try:
        return code, json.loads(out)
    except ValueError:
        return code, out.strip()


def test_missing_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("IBOP_USER", raising=False)
    monkeypatch.delenv("IBOP_PASS", raising=False)
    assert cli.main(["--session-file", "", "summary"]) == 2


def test_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("IBOP_USER", raising=False)
    (tmp_path / ".env").write_text("# c\nIBOP_USER='abc'\nbad line\n")
    cli.load_dotenv(tmp_path / ".env")
    assert os.environ["IBOP_USER"] == "abc"
    monkeypatch.delenv("IBOP_USER")


def test_commands(env: Path, mocked: responses.RequestsMock, capsys: pytest.CaptureFixture[str]) -> None:
    login_ok(mocked)
    for module in [
        "UserConfig",
        "CustomerList",
        "CustomerInfo_v1",
        "Summary_v1",
        "Accountancy_v2",
        "Invoices_v1",
        "InvoiceBook_v1",
        "Declarations_v1",
        "NotificationsHistory_v1",
        "Documents_v1",
    ]:
        add_fixture(mocked, module)
    expectations = {
        ("user",): lambda o: o["session_timeout_seconds"] == 420,
        ("customers",): lambda o: o[0]["id"] == CUSTOMER,
        ("customer",): lambda o: o["nip"] == "1111111111",
        ("summary",): lambda o: o["balance"] == "-140.00",
        ("ledger",): lambda o: len(o) == 6,
        ("ledger", "--filter", "unpaid"): lambda o: o[0]["remaining"] == "40.00",
        ("ledger", "--totals"): lambda o: (
            o == {"total_due": "840.00", "total_paid": "800.00", "difference": "40.00"}
        ),
        ("charges", "--limit", "2"): lambda o: len(o) == 2,
        ("charge", "PK/2026/12/527351"): lambda o: o["amount"] == "140.00",
        ("books",): lambda o: len(o) == 2,
        ("declarations",): lambda o: "raw" not in o[0] and o[0]["residents"] == 4,
        ("requests",): lambda o: o == [],
        ("documents",): lambda o: o[0]["filename"] == "regulamin.pdf",
    }
    for argv, check in expectations.items():
        code, out = run(capsys, *argv)
        assert code == 0, argv
        assert check(out), argv


def test_document_and_customer_switch(
    env: Path, mocked: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    login_ok(mocked)
    add_fixture(mocked, "CustomerList")
    add_fixture(mocked, "Documents_v1")
    mocked.add("POST", BASE + "/", body="ok")
    mocked.add("GET", BASE + "/dokumenty/cmVndWxhbWluLnBkZg==", body=b"%PDF-1.4")
    code, _ = run(capsys, "--customer", CUSTOMER, "document", "regulamin.pdf", "--out", "docs/")
    assert code == 0
    assert (env / "docs" / "regulamin.pdf").read_bytes() == b"%PDF-1.4"


def test_error_exit_code(
    env: Path, mocked: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mocked.add("GET", BASE + "/", body=LOGIN_PAGE)
    mocked.add("POST", BASE + "/", body=LOGIN_FAILED)
    assert cli.main(["--session-file", "", "summary"]) == 1
    assert "Niepoprawne" in capsys.readouterr().err
