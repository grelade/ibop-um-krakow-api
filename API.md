# iBOP UM Kraków (ibop.mpo.krakow.pl): reverse-engineered API reference

Mapped in November 2026 against a live account (one customer, a housing community, one
property) and the page scripts. Unofficial: the portal can change any of this without notice.
Implemented in `src/ibop_um_krakow_api/client.py` (HTTP) and `src/ibop_um_krakow_api/parsers.py`
(parsing). All example values below are fake.

## Architecture

- A PHP app ("iBOK" platform) with an **Adobe Spry + MooTools** front end. The page `/` is a
  shell; each screen is a module whose script comes from `/compress.php?js=<module>` and whose
  data comes from **`/?module=<Name>`**, answering JSON with `Content-Type: text/html`
  (sometimes with a leading newline).
- HTML templates: `/?module=Templates&template=<module>` → `{"html": "…"}` (Spry markup;
  useful to map field names to labels). Labels: `/?module=Dictionary&languageid=0` →
  `[{labelid, text}]`.
- Session: cookie `PHPSESSID`, idle timeout 420 s (`UserConfig.TimeOut`).
  Without a valid session every module answers `200` with an **empty body**.
- Amounts are strings in Polish format (`"8 184,00"`, `"140,00"`); `Summary_v1.saldo` uses a
  dot (`"-140.00"`). Dates are `YYYY-MM-DD` (`paymentDate` has a time part).

## Authentication

1. `GET /` (sets `PHPSESSID`), form `#frmLogin`.
2. `POST /?` form-encoded: `JSTest=ok`, `user=<login>`, `pass=<password>`, `login=Zaloguj`.
3. Success: `302 → ?` and the shell page without `#frmLogin`.
   Failure: `200` with the login form again and the message `Niepoprawne dane logowania!`.

No captcha on this form (`UserConfig.Captcha` hints at one after repeated failures).
There is also a Węzeł Krajowy (login.gov.pl) SSO flow (`?sso=1&start=1`), not used.
Logout: `GET /?logout=true`.

## Modules (all `GET /?module=…`)

| Module | Screen | Response |
|---|---|---|
| `Menu` | menu | `[{nameid, data, type, nameid_dict, …}]`: which modules this login can use |
| `UserConfig` | – | `[{name, value}]`: `lastlogged`, `useremail`, `username`, `customername`, `tel`, `TimeOut` (ms), `roles`, … |
| `CustomerList` | customer selector | `[{id, nazwa, active: "true"}]` |
| `CustomerInfo_v1` | Dane klienta | `{customerid, nazwa, nip, regon, pesel, tel, kom, fax, email, adres, korespondencja, nieruchomosci: [{lp, adres, nazwa, estateCode}]}` |
| `Summary_v1` | Podsumowanie | `{saldo, bankaccountno, paymentmethod, paymentdate, result: [{year, month, wymiar, ksiegowosc, paymentDate, minimumPaymentDate}]}` |
| `Accountancy_v2` | Rozrachunki | `{pozycje: [...], sumawn, sumama, roznica}` |
| `Invoices_v1` | Naliczenia | `[{id, nd, nw, ns, nt, np, ib, nn, na, ni, nr, npe, sn, sa, si, sr, st, sf, se, brutto, cdnr, cid, ba, positions: [{lp, pn, ad, pb}], pw}]` |
| `InvoiceBook_v1` | Książeczki | `[{k_id, k_rn, k_dn, k_isd, invoices: [{i_id, i_isd, i_ipd, i_dn, i_brutto}]}]` |
| `Declarations_v1` | Deklaracje | `[{id, bc, cd, ad, dt, ver, dcr, eot, nn, ni, rr, …, eu/eh/el/ek/ec (property address), et, rn, hhdesc, N1…N5, ra, coowners, containers, …}]` |
| `Documents_v1` | Dokumenty | `[{id, name, description, filename, temp}]`; file at `/dokumenty/<temp>` (`temp` = base64 of the filename) |
| `NotificationsHistory_v1` | Historia Zgłoszeń | `[]` on the test account (row shape not observed) |
| `HomePage_v1` | Strona główna | `null` |

### Field names

- **Ledger** (`Accountancy_v2.pozycje`): `nr` document number, `dw` issue date, `tp` due date,
  `wn` amount due ("Kwota należna do zapłaty"), `ma` paid, `ro` remaining, `ty` title
  (`RozrG` = waste fee), `ko` account, `kontrah` customer id. The page's filters: unpaid = `ro > 0`,
  paid = `wn <= ma`.
- **Fee notice** (`Invoices_v1`): `nd` number, `nw` issue date, `ns` sale date, `nt` due date,
  `np` payment type, `ib` payment book number, `n*` customer (`nn` name, `na` address, `ni` NIP,
  `nr` REGON, `npe` PESEL), `s*` seller (MPO: name, address, NIP, REGON, phone, fax, e-mail),
  `brutto`, `ba` individual bank account, `cdnr`/`cid` correction, `positions[]`
  (`pn` description, `ad` property, `pb` amount).
- **Summary**: `wymiar` "Kwota do zapłaty", `ksiegowosc` "Kwota zaksięgowana",
  `saldo` "Saldo" (reported as-is; on the test account it was `-140.00` while the ledger showed
  everything paid, so its sign convention is unclear), `paymentmethod` dictionary key
  (`przelw_gotwka` = "Przelew/gotówka").

## Not working / not used

- `?module=Accountancy_v2&action=oper|wplaty&…` (payment history per document): this
  deployment ignores the action and returns the full ledger.
- `?module=InvoiceBook_v1&action=pdf&id=…` (bank transfer form): `500` with an empty
  `przelew.pdf`; the page's PDF column is commented out.
- `?module=Declarations_v1&action=json&id=…`: builds a form for the external e-declaration
  service; not needed for reading.
- Write actions, never called: `CustomerList&action=changeActiveCustomer` (POST `customerId`,
  session-level switch; exposed as `set_active_customer`, tested with mocks only),
  `Notifications_v2&action=sendMessage`, `Settings_v1&action=email|password|phone`.
