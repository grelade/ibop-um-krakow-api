# ibop-um-krakow-api

Unofficial Python SDK and command-line client for **iBOP UM Kraków**
([ibop.mpo.krakow.pl](https://ibop.mpo.krakow.pl)), the online account for the City of Kraków
municipal waste-management fee ("opłata za gospodarowanie odpadami komunalnymi"), run by MPO
Kraków on behalf of Urząd Miasta Krakowa.

It logs in with your iBOP login and password and gives typed access to what the portal shows:

- payment summary: balance, individual bank account to pay into, monthly schedule for the year
- the ledger ("Rozrachunki"): every receivable with amount due, paid and remaining; totals
- fee notices ("Naliczenia") with seller, customer, lines and bank account
- yearly payment books ("Książeczki") with their instalments
- customer data with properties, waste-fee declarations, request history
- documents published in the portal (regulations), with download

> Not affiliated with MPO Kraków or Urząd Miasta Krakowa. The portal has no public API; this
> library calls the same JSON endpoints the web page uses and can break when they change.
> See [API.md](API.md) for the reverse-engineered endpoint reference.

## Install

```bash
pip install ibop-um-krakow-api        # or: uv add ibop-um-krakow-api
```

Latest unreleased code: `pip install git+https://github.com/grelade/ibop-um-krakow-api`.

Requires Python 3.10+.

## Command line

```bash
export IBOP_USER=login IBOP_PASS='…'     # or put them in ./.env
uvx ibop-um-krakow-api summary
```

| Command | Output |
|---|---|
| `user`, `customers`, `customer` | user, customers on the login, customer data with properties |
| `summary` | balance, bank account, payment method, monthly schedule |
| `ledger [--filter all\|paid\|unpaid] [--totals]` | receivables or their totals |
| `charges [--limit N]` / `charge NUMBER` | fee notices |
| `books` | payment books with instalments |
| `declarations`, `requests` | waste-fee declarations, request history |
| `documents` / `document ID [--out DIR_OR_FILE]` | published documents / download one |

Output is JSON (amounts are strings to keep `Decimal` precision). Global options: `--customer ID`
(switch the active customer first, for logins that manage several) and `--session-file PATH`
(default `~/.cache/ibop-um-krakow-api/session.json`; cookies are reused so repeated runs don't log in again).

## Library

```python
from ibop_um_krakow_api import IbopClient

with IbopClient("login", "secret", session_file="~/.cache/ibop-um-krakow-api/session.json") as c:
    summary = c.get_summary()
    print(summary.bank_account, summary.next_payment_date)

    ledger = c.get_ledger()
    print("due", ledger.total_due, "paid", ledger.total_paid)
    for entry in c.iter_unpaid():
        print(entry.number, entry.due_date, entry.remaining)

    for charge in c.get_charges()[:3]:
        print(charge.number, charge.amount, charge.due_date)
```

All methods: `get_user`, `get_customers`, `set_active_customer`, `get_customer_info`,
`get_summary`, `get_ledger`, `get_ledger_entries`, `iter_unpaid`, `get_charges`, `get_charge`,
`get_payment_books`, `get_declarations`, `get_requests_history`, `get_documents`,
`download_document`; session: `login`, `logout`, `save_session`.

Errors derive from `ibop_um_krakow_api.IbopError` (`AuthenticationError`, `ApiError`,
`ParseError`, `NotFoundError`).

## Development

```bash
uv sync                          # creates .venv with dev tools
uv run pytest                    # offline tests (HTTP mocked, anonymised fixtures)
uv run ruff check . && uv run ruff format --check . && uv run mypy
IBOP_LIVE=1 uv run pytest -m live   # read-only smoke tests against the real site (.env credentials)
```

See [AGENTS.md](AGENTS.md) for the project layout and conventions.

## License

MIT
