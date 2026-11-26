from datetime import date
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncMonth
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .forms import (
    BudgetForm, ExpenseFilterForm, ExpenseForm, LoginForm, OverallBudgetForm, RegisterForm,
    email_in_use, normalize_email, username_in_use, username_key,
)
from .models import AccountIdentity, Expense, ExpenseSubmission, MonthlyBudget, OverallBudget


def _total(expenses):
    return expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0")


def _category_totals(expenses):
    rows = expenses.values("category").annotate(total=Sum("amount")).order_by()
    return {row["category"]: row["total"] for row in rows}


def _overall_budget_rows(user, currency, today, month_spent, year_spent, all_spent):
    starts = {"month": today.replace(day=1), "year": today.replace(month=1, day=1), "overall": date.min}
    saved = {
        budget.period: budget
        for budget in OverallBudget.objects.filter(
            user=user, currency=currency, period_start__in=starts.values(),
        )
        if budget.period_start == starts[budget.period]
    }
    rows = []
    for period, label, spent in (
        ("month", "This month", month_spent),
        ("year", "This year", year_spent),
        ("overall", "Overall", all_spent),
    ):
        budget = saved.get(period)
        amount = budget.amount if budget else None
        rows.append({
            "id": budget.id if budget else None, "period": period, "label": label,
            "amount": amount, "spent": spent,
            "remaining": amount - spent if amount is not None else None,
            "over_budget": amount is not None and spent > amount,
        })
    return rows


def _currency(value):
    code = str(value).upper()
    if code not in dict(Expense.CURRENCY_CHOICES):
        raise Http404("Wallet not found.")
    return code


def _wallet_context(request, currency):
    today = timezone.localdate()
    request.session["wallet"] = currency.lower()
    return {
        "currency": currency,
        "wallet_slug": currency.lower(),
        "currency_label": dict(Expense.CURRENCY_CHOICES)[currency],
        "today": today,
        "month_label": today.strftime("%B %Y"),
    }


def _attempt_key(request, scope):
    address = request.META.get("REMOTE_ADDR", "local")
    return "attempts:" + sha256(f"{scope}:{address}".encode()).hexdigest()


def _too_many_attempts(request, scope):
    return cache.get(_attempt_key(request, scope), 0) >= getattr(settings, "AUTH_ATTEMPT_LIMIT", 10)


def _failed_attempt(request, scope):
    key = _attempt_key(request, scope)
    if not cache.add(key, 1, timeout=600):
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=600)


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST" and _too_many_attempts(request, "register"):
        initial = {name: request.POST.get(name, "") for name in ["username", "first_name", "last_name", "email"]}
        return render(request, "register.html", {
            "form": RegisterForm(initial=initial),
            "error_message": "Too many registration attempts. Please try again in 10 minutes.",
        }, status=429)
    form = RegisterForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            # Django's User and the unique registration keys must save together.
            with transaction.atomic():
                user = form.save()
                AccountIdentity.objects.create(
                    user=user,
                    username_key=username_key(user.username),
                    email_key=normalize_email(user.email),
                )
        except IntegrityError:
            if username_in_use(form.cleaned_data["username"]):
                form.add_error("username", "A user with that username already exists.")
            elif email_in_use(form.cleaned_data["email"]):
                form.add_error("email", "An account with this email already exists.")
            else:
                form.add_error(None, "These account details were just used. Please check them and try again.")
        else:
            cache.delete(_attempt_key(request, "register"))
            login(request, user)
            messages.success(request, "Your account is ready. Welcome!")
            return redirect("dashboard")
    if request.method == "POST":
        _failed_attempt(request, "register")
    return render(request, "register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_user(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST" and _too_many_attempts(request, "login"):
        return render(request, "login.html", {
            "form": LoginForm(request, initial={"username": request.POST.get("username", "")}),
            "error_message": "Too many login attempts. Please try again in 10 minutes.",
        }, status=429)
    form = LoginForm(request, data=request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        cache.delete(_attempt_key(request, "login"))
        login(request, form.get_user())
        next_page = request.GET.get("next", "")
        if next_page and url_has_allowed_host_and_scheme(
            next_page, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
        ):
            return redirect(next_page)
        return redirect("dashboard")
    if request.method == "POST":
        _failed_attempt(request, "login")
    return render(request, "login.html", {"form": form})


@login_required
@require_POST
def logout_user(request):
    logout(request)
    return redirect("login")


@login_required
def profile(request):
    return render(request, "profile.html")


@login_required
def dashboard(request):
    currency = _currency(request.GET.get("wallet", request.session.get("wallet", "usd")))
    context = _wallet_context(request, currency)
    today = context["today"]
    month = today.replace(day=1)
    expenses = Expense.objects.filter(user=request.user, currency=currency)
    this_month = expenses.filter(date__year=today.year, date__month=today.month)
    this_year = expenses.filter(date__year=today.year)
    spending = _category_totals(this_month)
    month_spent = _total(this_month)
    limits = {budget.category: budget.amount for budget in MonthlyBudget.objects.filter(
        user=request.user, currency=currency, month=month,
    )}
    category_totals = []
    for category, name in Expense.CATEGORY_CHOICES:
        total = spending.get(category, Decimal("0"))
        budget = limits.get(category)
        category_totals.append({
            "name": name, "total": total, "budget": budget,
            "remaining": budget - total if budget is not None else None,
            "over_budget": budget is not None and total > budget,
        })
    wallet_links = [
        {"currency": code, "slug": code.lower(), "label": label}
        for code, label in Expense.CURRENCY_CHOICES
    ]
    top_category = max(category_totals, key=lambda row: row["total"])
    context.update({
        "wallet_links": wallet_links,
        "total_spending": month_spent,
        "overall_budgets": _overall_budget_rows(
            request.user, currency, today, month_spent, _total(this_year), _total(expenses),
        ),
        "spending_by_category": category_totals,
        "recent_expenses": expenses.order_by("-date", "-id")[:5],
        "monthly_summary": expenses.annotate(month=TruncMonth("date")).values("month")
            .annotate(total=Sum("amount"), count=Count("id")).order_by("-month"),
        "top_category": top_category if top_category["total"] else None,
    })
    return render(request, "dashboard.html", context)


def _history_page(request, currency, budget_form=None, overall_budget_form=None):
    context = _wallet_context(request, currency)
    today = context["today"]
    all_expenses = Expense.objects.filter(user=request.user, currency=currency)
    form = ExpenseFilterForm(request.GET)
    expenses = all_expenses
    if form.is_valid():
        filters = form.cleaned_data
        if filters["category"]:
            expenses = expenses.filter(category=filters["category"])
        if filters["start_date"]:
            expenses = expenses.filter(date__gte=filters["start_date"])
        if filters["end_date"]:
            expenses = expenses.filter(date__lte=filters["end_date"])
        if filters["minimum_amount"] is not None:
            expenses = expenses.filter(amount__gte=filters["minimum_amount"])
        if filters["maximum_amount"] is not None:
            expenses = expenses.filter(amount__lte=filters["maximum_amount"])
    else:
        expenses = expenses.none()
    spending = _category_totals(all_expenses.filter(
        date__year=today.year, date__month=today.month,
    ))
    month_spent = sum(spending.values(), Decimal("0"))
    year_spent = _total(all_expenses.filter(date__year=today.year))
    budgets = []
    for budget in MonthlyBudget.objects.filter(
        user=request.user, currency=currency, month=today.replace(day=1),
    ).order_by("category"):
        spent = spending.get(budget.category, Decimal("0"))
        budgets.append({
            "id": budget.id, "category": budget.category, "amount": budget.amount,
            "spent": spent, "remaining": budget.amount - spent,
            "over_budget": spent > budget.amount,
        })
    context.update({
        "form": form, "expenses": expenses.order_by("-date", "-id"),
        "filtered_total": _total(expenses),
        "budget_form": budget_form if budget_form is not None else BudgetForm(auto_id="id_budget_%s"),
        "overall_budget_form": overall_budget_form if overall_budget_form is not None else OverallBudgetForm(auto_id="id_overall_%s"),
        "overall_budgets": _overall_budget_rows(
            request.user, currency, today, month_spent, year_spent, _total(all_expenses),
        ),
        "budgets": budgets,
    })
    return render(request, "expense_history.html", context)


@login_required
def expense_history(request, currency):
    return _history_page(request, _currency(currency))


@login_required
def default_history(request):
    return redirect("expense_history", currency=request.session.get("wallet", "usd"))


@login_required
def default_add(request):
    return redirect("add_expense", currency=request.session.get("wallet", "usd"))


def _submission_token(user, currency):
    return signing.dumps({"user_id": user.id, "currency": currency, "key": str(uuid4())}, salt="expense-add")


@login_required
@require_http_methods(["GET", "POST"])
def add_expense(request, currency):
    currency = _currency(currency)
    context = _wallet_context(request, currency)
    form = ExpenseForm(
        request.POST if request.method == "POST" else None,
        initial={"submission_token": _submission_token(request.user, currency)},
    )
    if request.method == "POST" and form.is_valid():
        try:
            token = signing.loads(form.cleaned_data["submission_token"], salt="expense-add", max_age=86400)
            if not isinstance(token, dict):
                raise ValueError
            if token["user_id"] != request.user.id or token["currency"] != currency:
                raise ValueError
            key = UUID(str(token["key"]))
        except (signing.BadSignature, ValueError, KeyError, TypeError):
            form.add_error(None, "This form has expired or is invalid. Reopen Add Expense and try again.")
        else:
            try:
                # The receipt survives deletion, so an old Save cannot recreate an expense.
                with transaction.atomic():
                    submission = ExpenseSubmission.objects.create(key=key, user=request.user, currency=currency)
                    expense = form.save(commit=False)
                    expense.user = request.user
                    expense.currency = currency
                    expense.submission_key = key
                    expense.save()
                    submission.expense = expense
                    submission.save(update_fields=["expense"])
                created = True
            except IntegrityError:
                submission = ExpenseSubmission.objects.filter(
                    key=key, user=request.user, currency=currency,
                ).first()
                created = False
            if submission is None:
                form.add_error(None, "This expense could not be saved. Please reopen Add Expense and try again.")
            else:
                if not created and submission.expense_id is None:
                    messages.info(request, "This submission was already processed and the expense was deleted. No expense was added.")
                    return redirect("expense_history", currency=currency.lower())
                messages.success(request, "Expense saved." if created else "This expense was already saved; no duplicate was added.")
                target = "add_expense" if request.POST.get("action") == "add_another" else "expense_history"
                return redirect(target, currency=currency.lower())
    context.update({"form": form, "title": "Add Expense", "editing": False})
    return render(request, "expense_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def edit_expense(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id, user=request.user)
    context = _wallet_context(request, expense.currency)
    form = ExpenseForm(
        request.POST if request.method == "POST" else None,
        instance=expense,
    )
    if request.method == "POST" and form.is_valid():
        version = form.cleaned_data.get("version")
        if version is None:
            form.add_error(None, "Please reopen this expense before saving changes.")
        else:
            changed = Expense.objects.filter(id=expense_id, user=request.user, version=version).update(
                description=form.cleaned_data["description"],
                amount=form.cleaned_data["amount"],
                category=form.cleaned_data["category"],
                date=form.cleaned_data["date"],
                version=F("version") + 1,
            )
            if changed:
                messages.success(request, "Expense updated.")
                return redirect("expense_history", currency=expense.currency.lower())
            form.add_error(None, "This expense changed in another tab. Your entries are kept below; reopen the expense to review the latest version.")
    context.update({"form": form, "title": "Edit Expense", "editing": True})
    return render(request, "expense_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def delete_expense(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id, user=request.user)
    context = _wallet_context(request, expense.currency)
    if request.method == "POST":
        expense.delete()
        messages.success(request, "Expense deleted.")
        return redirect("expense_history", currency=expense.currency.lower())
    context["expense"] = expense
    return render(request, "expense_confirm_delete.html", context)


@login_required
@require_POST
def save_budget(request, currency):
    currency = _currency(currency)
    form = BudgetForm(request.POST, auto_id="id_budget_%s")
    if form.is_valid():
        MonthlyBudget.objects.update_or_create(
            user=request.user, currency=currency,
            month=timezone.localdate().replace(day=1), category=form.cleaned_data["category"],
            defaults={"amount": form.cleaned_data["amount"]},
        )
        messages.success(request, "Monthly category budget saved.")
        return redirect("expense_history", currency=currency.lower())
    return _history_page(request, currency, budget_form=form)


@login_required
@require_POST
def save_overall_budget(request, currency):
    currency = _currency(currency)
    form = OverallBudgetForm(request.POST, auto_id="id_overall_%s")
    if form.is_valid():
        today = timezone.localdate()
        period = form.cleaned_data["period"]
        starts = {"month": today.replace(day=1), "year": today.replace(month=1, day=1), "overall": date.min}
        start = starts[period]
        OverallBudget.objects.update_or_create(
            user=request.user, currency=currency, period=period, period_start=start,
            defaults={"amount": form.cleaned_data["amount"]},
        )
        messages.success(request, f"Overall {period} budget saved.")
        return redirect("expense_history", currency=currency.lower())
    return _history_page(request, currency, overall_budget_form=form)


@login_required
@require_POST
def delete_budget(request, budget_id):
    budget = get_object_or_404(MonthlyBudget, id=budget_id, user=request.user)
    currency = budget.currency
    budget.delete()
    messages.success(request, "Budget removed. Your expenses are unchanged.")
    return redirect("expense_history", currency=currency.lower())


@login_required
@require_POST
def delete_overall_budget(request, budget_id):
    budget = get_object_or_404(OverallBudget, id=budget_id, user=request.user)
    currency = budget.currency
    budget.delete()
    messages.success(request, "Overall budget removed. Your expenses are unchanged.")
    return redirect("expense_history", currency=currency.lower())
