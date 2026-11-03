# Validation record

## Automated checks (executed)

- Python syntax: `ast.parse` on `app.py` — OK
- JavaScript syntax: `node --check` on `investment.js` and other page scripts — OK
- Unit tests: `python3 -m unittest discover -s tests -v` — **7/7 passed**
  - dashboard empty payload
  - transactions + dashboard totals
  - category budgets
  - goals + contributions
  - investments add / buy (avg cost) / sell / oversell guard / history
  - receipt → transaction
  - reports JSON + CSV export

## Manual verification focus

- Add Investment modal opens and form submits (form submit was previously unbound)
- Edit / Buy more / Sell / History buttons on each holding
- Catalog autocomplete for Indian stocks, gold, silver, crypto
- Quote fetch is best-effort (Yahoo delayed); gold/silver remain manual INR
- Theme toggle uses `#themeBtn` via `common.js` on non-dashboard pages
- Bills scan form date field aligned with payload (`due_date`)

## Schema migrations (additive)

- `investments.notes`, `investments.quote_source`, `investments.price_updated_at`
- New table `investment_transactions` for buy/sell history
- Existing holdings are preserved; new columns default safely
