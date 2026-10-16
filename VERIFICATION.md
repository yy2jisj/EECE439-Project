# Verification record

Verified on October 12, 2026 with Python 3.12.6 and Django 5.2.18 on Windows.

## Automated checks

- All eight `app1` migrations and Django's built-in migrations applied successfully
  to a new SQLite database.
- `manage.py check`: no issues.
- `manage.py makemigrations --check --dry-run`: no missing model changes.
- `manage.py test app1`: **52 tests passed**. These cover registration, password
  validation and hashing, login/logout/profile, expense CRUD, positive/decimal
  amount validation, categories/currencies/dates, combined inclusive filters,
  invalid filters, current-month and monthly summaries, year boundaries, empty
  accounts, recent expenses, separate currencies, two-user isolation, direct
  requests using another owner's ID, safe redirects, enforced CSRF checks,
  fictional demo seeding, and admin owner restrictions.
- The demo command added 15 fictional rows to a temporary QA account; immediately
  rerunning it added zero rows.
- All ten application templates parsed successfully. After the final accessibility
  adjustment, the 31 authentication, expense CRUD, and filter tests passed again.
- The delivered folder also passed fresh migrations, system checks, migration
  consistency, and static-file discovery using a database outside the output
  folder. That fresh database had zero accounts, zero expenses, and no student
  or course tables.

## Browser checks

Used the local development server in the Codex in-app browser. Confirmed:

- Registration creates an account and opens the empty dashboard.
- Navigation opens the main pages; profile displays the current account.
- Login and POST logout work.
- Adding an expense shows it in history with a success message; editing changes
  its amount; deleting first opens a confirmation and then removes the row.
- Category, date and amount filters work together, include boundary values, and
  reset correctly. An inverted amount range displays an understandable error.
- Switching between USD and LBP shows separate records and totals without
  conversion. Demo October totals were USD 60.00 and LBP 1,540,000.00.
- The static CSS loads, with the basic layout, labels, tables, and empty states
  visible.
- Desktop layout and a 390-by-844 phone-sized viewport are usable. Navigation
  wraps, forms remain readable, and expense tables scroll inside their
  own container. The document itself has no horizontal overflow in that viewport.

The preview image accompanying the project shows only fictional demo purchases.
The QA account and QA SQLite database are excluded from both the delivered project
folder and ZIP. The delivered project initializes its own empty database when
the user runs `migrate`.

## Scope

No cloud deployment or Docker/PostgreSQL runtime was tested or provisioned.
Those are later deployment options described in the README. The application was
verified for local SQLite operation and the supported Django version pinned in
requirements.txt.
