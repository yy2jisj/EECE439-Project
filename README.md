# PocketManager

A small Django expense tracker for general personal spending. It uses plain
server-rendered HTML, minimal CSS, and SQLite. Each account manages its own
expenses. USD and LBP are kept separate; the currency switch changes which records
and totals are displayed. There is no exchange-rate conversion.

## Run on Windows

Use Python 3.12, 3.13, or 3.14; check your version with `py --version`. Install a
supported version if needed. Extract the ZIP, open PowerShell, and change into
the `PocketManager` folder containing
`manage.py`. For example, if you extracted it into Downloads:

```powershell
cd "$env:USERPROFILE\Downloads\PocketManager"
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Open <http://127.0.0.1:8000/>. Create an account using **Register**, then add your
expenses. Stop the server with **Ctrl+C**. To run it again, use the last command.
These commands call the environment's Python directly, so PowerShell activation
and execution-policy changes are unnecessary. If `py` is unavailable, use
`python -m venv .venv` for the first Python command.

The delivered project contains no accounts or expense database. `migrate` creates
a fresh `db.sqlite3`. Registration does not require an administrator account.
For optional Django administration, run:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Then open <http://127.0.0.1:8000/admin/>. This administrator interface is separate
from the normal expense-tracker pages.

## Optional fictional examples

Register an account first. To add the examples to that account, replace
`your_username` with its username and run:

```powershell
.\.venv\Scripts\python.exe manage.py seed_demo --username your_username
```

All example descriptions start with **Demo:**. The purchases, amounts, and dates
are fictional; they do not describe real spending or actual prices. Examples
include mloukhiye, kebbe, fahitta, van 4, van 1, Uber, inDrive, Spinneys groceries,
Netflix, and Claude. The set covers all six categories, both currencies, and
different months. Running the command again in the same calendar month does not duplicate
unchanged examples. It never creates an account or chooses a password. To remove
examples, use the normal expense deletion page.

## Using the app

- **Dashboard:** this month's total and expense count, this month's category
  spending, five recent expenses, and a monthly totals table.
- **Expenses:** history for the selected currency, with category, inclusive date
  ranges, and inclusive amount ranges. Filters work together. **Reset filters**
  returns to the complete history in the selected currency.
- **Add / Edit:** description, amount, one of the six categories, currency, and
  expense date. Amounts must be at least 0.01 and use at most two decimal places.
- **Delete:** review the expense and confirm deletion. Opening the confirmation
  page does not delete anything.
- **Profile:** username, account name, email when supplied, and date joined.
- **Currency switch:** select USD or LBP and press **Switch**. This does not change
  the currency or amount of a saved expense. Adding a record in the other currency
  places it in that currency's history. After saving an expense, the app switches
  the active display to that expense's currency.

The fixed categories are Food, Transport, Bills, Shopping, Entertainment, and
Other. Money is stored as decimal values. Both currencies display two decimal
places. The monthly summary uses the entered expense date and lists months with
recorded expenses, plus the current month even when its total is zero. Valid future
expense dates are allowed and are counted in their entered month. Category totals
appear in a simple table. Invalid filters show validation errors and no results
until corrected or reset.

## Verify locally

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test app1
```

The test runner uses a separate temporary database and does not change your saved
expenses. See [VERIFICATION.md](VERIFICATION.md) for the checks performed before
delivery, [REQUIREMENTS.md](REQUIREMENTS.md) for the assignment feature mapping,
and [PROJECT_GUIDE.md](PROJECT_GUIDE.md) for a beginner-friendly code explanation.

## What changed from the template

The original `website` project, `app1` application, `manage.py`, project-level
templates, and seven historical migrations remain recognizable. The student and
course models, forms, views, and pages were replaced with the expense tracker.
Migration `0008` removes the course/student tables and creates the expense table.
The original ZIP and original database were preserved outside this deliverable;
their old account and student data are not distributed.

The configuration was updated from the old Django 2.0-era settings to
**Django 5.2.18**, a patch in the supported 5.2 LTS series. See the
[official support table](https://www.djangoproject.com/download/) and
[Python compatibility notes](https://docs.djangoproject.com/en/5.2/releases/5.2/).
The requirements pin the tested Django version; pip installs its dependencies.
Authentication, password hashing, validation, CSRF protection, and sessions use
Django's standard tools.

## Configuration and later deployment

No cloud service is provisioned and nothing is deployed. The defaults run locally.
The application timezone is **Asia/Beirut**, matching the timezone provided in this
chat; it determines the dashboard's current month. You can change it before
starting the server:

```powershell
$env:DJANGO_TIME_ZONE = "UTC"
```

Optional environment settings are `DJANGO_SECRET_KEY`, `DJANGO_DEBUG` (`True` or
`False`), `DJANGO_ALLOWED_HOSTS` (comma-separated hostnames), `DJANGO_TIME_ZONE`,
and `SQLITE_DB_PATH` (an alternate SQLite filename). The default secret key is a
local-development value. Setting debug to False requires a supplied secret key.

For a later Docker/PostgreSQL deployment, package this same project, add a
PostgreSQL driver and connection settings to `DATABASES`, configure the production
secret/hosts/debug setting, run migrations and `collectstatic`, and serve the
WSGI or ASGI application with a production server. The ORM model and migration
relationships do not depend on SQLite-specific SQL. Those deployment steps are
future work and are not needed for this local assignment.
