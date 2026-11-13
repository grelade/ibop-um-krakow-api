"""``ibop-um-krakow-api`` command line interface. Prints JSON to stdout; files are written to disk.

Credentials come from ``IBOP_USER`` / ``IBOP_PASS`` (environment or a ``.env`` file in the
current directory). Cookies are cached in ``~/.cache/ibop-um-krakow-api/session.json``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .client import IbopClient
from .exceptions import IbopError
from .models import ChargeFilter, DownloadedFile, to_jsonable

DEFAULT_SESSION_FILE = Path("~/.cache/ibop-um-krakow-api/session.json")


def load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE lines, existing environment wins."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _print(data: Any) -> None:
    json.dump(to_jsonable(data), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def _save(file: DownloadedFile, out: str) -> Path:
    dest = Path(out)
    if dest.is_dir() or out.endswith(("/", os.sep)):
        dest.mkdir(parents=True, exist_ok=True)
        dest = dest / (file.filename or "download.bin")
    dest.write_bytes(file.content)
    return dest


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="ibop-um-krakow-api", description="Unofficial iBOP UM Kraków (ibop.mpo.krakow.pl) client"
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--customer", help="customer id to switch to first (logins with several customers)")
    ap.add_argument(
        "--session-file",
        default=os.environ.get("IBOP_SESSION_FILE", str(DEFAULT_SESSION_FILE)),
        help="where to cache session cookies ('' disables)",
    )
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND")
    sub.add_parser("user", help="logged-in user")
    sub.add_parser("customers", help="customers on the login")
    sub.add_parser("customer", help="customer data with properties")
    sub.add_parser("summary", help="balance, bank account and monthly schedule")
    p = sub.add_parser("ledger", help="receivables with amount due / paid / remaining")
    p.add_argument("--filter", choices=[f.value for f in ChargeFilter], default="all")
    p.add_argument("--totals", action="store_true", help="print the totals instead of the entries")
    p = sub.add_parser("charges", help="fee notices (Naliczenia)")
    p.add_argument("--limit", type=int, default=0, help="max rows (0 = all)")
    p = sub.add_parser("charge", help="one fee notice")
    p.add_argument("number", help="e.g. PK/2026/12/527351")
    sub.add_parser("books", help="payment books (Książeczki)")
    sub.add_parser("declarations", help="waste-fee declarations")
    sub.add_parser("requests", help="history of requests sent through the portal")
    sub.add_parser("documents", help="documents published in the portal")
    p = sub.add_parser("document", help="download a document")
    p.add_argument("id", help="document id, name or filename")
    p.add_argument("--out", default=".", help="file or directory (default: current directory)")
    return ap


def run(args: argparse.Namespace, client: IbopClient) -> None:
    if args.customer:
        client.set_active_customer(args.customer)
    cmd = args.cmd
    if cmd == "user":
        _print(client.get_user())
    elif cmd == "customers":
        _print(client.get_customers())
    elif cmd == "customer":
        _print(client.get_customer_info())
    elif cmd == "summary":
        _print(client.get_summary())
    elif cmd == "ledger":
        if args.totals:
            ledger = client.get_ledger()
            _print({k: v for k, v in ledger.to_dict().items() if k != "entries"})
        else:
            _print(client.get_ledger_entries(args.filter))
    elif cmd == "charges":
        charges = client.get_charges()
        _print(charges[: args.limit] if args.limit else charges)
    elif cmd == "charge":
        _print(client.get_charge(args.number))
    elif cmd == "books":
        _print(client.get_payment_books())
    elif cmd == "declarations":
        _print([{k: v for k, v in d.to_dict().items() if k != "raw"} for d in client.get_declarations()])
    elif cmd == "requests":
        _print(client.get_requests_history())
    elif cmd == "documents":
        _print(client.get_documents())
    elif cmd == "document":
        print(_save(client.download_document(args.id), args.out))
    else:  # pragma: no cover - argparse rejects unknown commands
        raise SystemExit(f"unknown command {cmd}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(Path.cwd() / ".env")
    user, password = os.environ.get("IBOP_USER"), os.environ.get("IBOP_PASS")
    session_file = args.session_file or None
    if not (user and password) and not (session_file and Path(session_file).expanduser().exists()):
        print("error: set IBOP_USER and IBOP_PASS (environment or .env)", file=sys.stderr)
        return 2
    try:
        with IbopClient(user, password, session_file=session_file) as client:
            run(args, client)
    except IbopError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
