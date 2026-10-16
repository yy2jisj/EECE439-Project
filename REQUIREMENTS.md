# Assignment 3 requirement checklist

The supplied one-page assignment is the source for the required features below.
PocketManager runs locally with SQLite. Docker and a cloud PostgreSQL database
are described as later deployment options in the assignment.

| PDF feature | Page or implementation |
| --- | --- |
| Register | `/register/`; Django `UserCreationForm` extension |
| Login / logout | `/login/`; POST form to `/logout/`; Django authentication |
| Profile | `/profile/`; basic information from the logged-in account |
| Add expense | `/expenses/add/`; validated `ExpenseForm` |
| Edit expense | `/expenses/<id>/edit/`; owner-restricted lookup and form |
| Delete expense | `/expenses/<id>/delete/`; GET confirmation, POST deletion |
| View expense history | `/expenses/`; current account and selected currency |
| Food, Transport, Bills, Shopping, Entertainment, Other | Fixed model choices, form selector, history filters, dashboard rows |
| Total spending this month | `/`; database sum within current calendar month |
| Spending by category | `/`; current month totals in a simple table |
| Recent expenses | `/`; latest five by expense date, with ID as tie-breaker |
| Monthly summary | `/`; monthly total and count table |
| Filter by category | `/expenses/`; category selector |
| Filter by date | `/expenses/`; inclusive start/end date fields |
| Filter by amount | `/expenses/`; inclusive minimum/maximum amount fields |
| Local SQLite operation | `website/settings.py`; fresh initialization with `manage.py migrate` |
| Later Docker / PostgreSQL suitability | Standard Django ORM, migrations, WSGI/ASGI, environment settings; README future-deployment notes |

Additional requirements from the user's request are implemented through owner
filters on every expense page and dashboard query, decimal amounts, positive
amount validation, safe redirects, login protection, CSRF tokens, POST mutations,
combined filters, readable function-based views, shared templates, responsive CSS,
success messages, and empty states. USD/LBP are separate records and totals as
confirmed during personalization. Optional demo purchases are clearly fictional.
