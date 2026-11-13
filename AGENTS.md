# AGENTS.md

Guidance for coding agents working on this repository.

## What this is

`ibop-um-krakow-api`: an unofficial Python SDK + CLI for iBOP UM Kraków
(https://ibop.mpo.krakow.pl), the Kraków municipal waste-fee portal run by MPO Kraków. The
portal is a PHP app whose screens load JSON from `/?module=<Name>`; the SDK logs in with the
form, keeps the `PHPSESSID` cookie and calls the same modules. **API.md is the endpoint
reference**: read it before touching the client, and update it whenever you learn something
new about the site.

## Layout

```
src/ibop_um_krakow_api/
  client.py      IbopClient: login, session/cookie handling, one method per feature (I/O only)
  parsers.py     pure functions JSON/HTML -> models; all field names of the portal live here
  models.py      dataclasses (Decimal money, date dates), ChargeFilter enum, to_jsonable()
  exceptions.py  IbopError > AuthenticationError | ApiError | ParseError | NotFoundError
  cli.py         `ibop-um-krakow-api` argparse CLI, JSON on stdout
tests/
  fixtures/      ANONYMISED captures of real module responses
  test_parsers.py  parsers against fixtures
  test_client.py   client flows with HTTP mocked by `responses` (asserts request params too)
  test_cli.py      CLI end to end with mocked HTTP
  test_live.py     read-only checks against the real site, skipped unless IBOP_LIVE=1
```

## Commands

```bash
uv sync                                   # install (uses uv.lock)
uv run pytest                             # offline test suite, must stay green
uv run ruff check . && uv run ruff format --check .
uv run mypy                               # strict mode on src/
IBOP_LIVE=1 uv run pytest -m live         # needs IBOP_USER / IBOP_PASS (env or .env)
uv run ibop-um-krakow-api --help          # CLI
```

Add dependencies with `uv add` / `uv add --dev` so `uv.lock` stays in sync. CI runs ruff,
mypy and pytest on Python 3.10–3.13 (`.github/workflows/ci.yml`).

## How a feature works (pattern to follow)

1. Find the screen in `/?module=Menu`, read its script `/compress.php?js=<data>` for the data
   URL (`this.mainDataSetFile = "?module=…"`) and its template
   `/?module=Templates&template=<data>` for the field labels.
2. Call it through `IbopClient._module(name, **params)` (logs in again once when the session
   expired, i.e. the module answered an empty body).
3. Parse with a pure function in `parsers.py` into a dataclass from `models.py`.

Keep I/O in `client.py` and parsing in `parsers.py`. New parsers get a fixture + test in
`test_parsers.py`; new client methods get a `responses` test that also asserts the query sent.

## Site quirks worth knowing

- Modules answer JSON as `text/html`, sometimes with a leading newline; parse `r.text` with `json.loads`.
- An expired or missing session gives `200` with an empty body, not a redirect or 401.
- A failed login returns the login page again (`#frmLogin`) with "Niepoprawne dane logowania!".
- Session idle timeout is 7 minutes; the cached cookie usually needs a fresh login.
- Amounts use Polish formatting with spaces as thousand separators; `Summary_v1.saldo` uses a dot.
- `action=oper` / `action=wplaty` on `Accountancy_v2` and `action=pdf` on `InvoiceBook_v1` do not
  work on this deployment (see API.md); do not build features on them without re-checking.

## Releasing

Releases go to PyPI from GitHub Actions (`.github/workflows/release.yml`) via trusted
publishing; there is no token to manage.

1. Bump the version: `uv version --bump patch` (or `minor` / `major`); this updates `pyproject.toml` and `uv.lock`.
2. Commit, then tag and push: `git tag v$(uv version --short) && git push && git push --tags`.
3. The workflow runs CI, checks the tag matches the version, builds and smoke-tests the wheel,
   publishes to https://pypi.org/project/ibop-um-krakow-api/ and creates a GitHub release with the files attached.

PyPI versions can never be re-uploaded, so a broken release needs a new version number.

## Safety rules

- **Never commit personal data.** `.env` holds real credentials and is gitignored. Fixtures must
  be anonymised: replace names, addresses, customer ids (also inside account numbers like `ko`),
  NIP, REGON, PESEL, phone, e-mails, bank account numbers, declaration and estate ids before
  saving into `tests/fixtures/`. Grep the fixtures for the real values before committing.
- Live exploration is read-only. Do not send requests (`Notifications_v2&action=sendMessage`),
  change settings (`Settings_v1&action=…`), or submit declarations. Write actions the SDK exposes
  (`set_active_customer`) are tested with mocks only.
- Keep request volume low when exploring (one login, reuse the session).
