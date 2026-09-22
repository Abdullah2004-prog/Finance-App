import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from models import (
    Income, Expense, Category, DualStorage,
    calculate_balance, filter_by_month, available_months,
    save_budget, load_budget
)
from auth import register_user, verify_user, login_required, current_username

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

app = Flask(__name__)

# --- secret key: generated once, then reused on every restart so logins persist ---
os.makedirs("data", exist_ok=True)
SECRET_KEY_FILE = "data/.secret_key"
if not os.path.exists(SECRET_KEY_FILE):
    with open(SECRET_KEY_FILE, "w") as f:
        f.write(os.urandom(32).hex())
with open(SECRET_KEY_FILE, "r") as f:
    app.secret_key = f.read().strip()


def user_storage():
    """Each logged-in user gets their own transactions file.
    DualStorage keeps a JSON copy (source of truth) and a CSV copy
    (auto-updated mirror) in sync on every save."""
    username = current_username()
    return DualStorage(f"data/{username}_transactions.json")


def user_budget_path():
    username = current_username()
    return f"data/{username}_budget.json"


# ============================================================
# Auth routes
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if "username" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))

        success, error = register_user(username, password)
        if not success:
            flash(error, "error")
            return redirect(url_for("register"))

        flash("Account created. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "username" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        print(f"DEBUG LOGIN ATTEMPT: username={username!r} password_len={len(password)}", flush=True)

        if verify_user(username, password):
            session["username"] = username
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))

        flash("Incorrect username or password.", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("Logged out.", "success")
    return redirect(url_for("login"))


# ============================================================
# App routes (all require login)
# ============================================================

@app.route("/")
@login_required
def dashboard():
    storage = user_storage()
    budget = load_budget(user_budget_path())

    all_transactions = storage.load()

    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)

    scoped = filter_by_month(all_transactions, month, year)
    balance = calculate_balance(scoped)
    savings = budget.check_savings_progress(balance)
    recent = list(reversed(scoped))[:5]

    months = available_months(all_transactions)
    month_options = [
        {"month": m, "year": y, "label": f"{MONTH_NAMES[m]} {y}"}
        for (y, m) in months
    ]

    return render_template(
        "dashboard.html",
        balance=balance,
        savings=savings,
        recent=recent,
        count=len(scoped),
        total_count=len(all_transactions),
        month_options=month_options,
        selected_month=month,
        selected_year=year,
        is_filtered=(month is not None and year is not None),
    )


@app.route("/add", methods=["GET", "POST"])
@login_required
def add_transaction():
    storage = user_storage()
    budget = load_budget(user_budget_path())

    if request.method == "POST":
        t_type = request.form.get("type")
        date = request.form.get("date")
        amount_raw = request.form.get("amount")
        category = request.form.get("category")
        payment_type = request.form.get("payment_type")

        try:
            amount = float(amount_raw)
        except (TypeError, ValueError):
            flash("Amount must be a number.", "error")
            return redirect(url_for("add_transaction"))

        if category not in Category.categories:
            flash("Please choose a valid category.", "error")
            return redirect(url_for("add_transaction"))

        try:
            if t_type == "income":
                new_t = Income(date, amount, category, payment_type)
            else:
                new_t = Expense(date, amount, category, payment_type)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("add_transaction"))

        transactions = storage.load()
        transactions.append(new_t)
        storage.save(transactions)

        alert = budget.check_alert(category, amount)
        if alert:
            flash(alert["message"], alert["level"])
        else:
            flash("Transaction added successfully!", "success")

        return redirect(url_for("dashboard"))

    return render_template("add.html", categories=Category.categories)


@app.route("/transactions")
@login_required
def list_transactions():
    storage = user_storage()
    all_transactions = storage.load()

    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)

    scoped = filter_by_month(all_transactions, month, year)
    transactions = list(reversed(scoped))

    months = available_months(all_transactions)
    month_options = [
        {"month": m, "year": y, "label": f"{MONTH_NAMES[m]} {y}"}
        for (y, m) in months
    ]

    return render_template(
        "transactions.html",
        transactions=transactions,
        month_options=month_options,
        selected_month=month,
        selected_year=year,
        is_filtered=(month is not None and year is not None),
    )


@app.route("/summary", methods=["GET", "POST"])
@login_required
def summary():
    storage = user_storage()
    budget = load_budget(user_budget_path())

    rows = None
    month = year = None
    if request.method == "POST":
        try:
            month = int(request.form.get("month"))
            year = int(request.form.get("year"))
        except (TypeError, ValueError):
            flash("Please enter a valid month and year.", "error")
            return redirect(url_for("summary"))

        transactions = storage.load()
        rows = budget.monthly_summary(transactions, month, year)

    return render_template("summary.html", rows=rows, month=month, year=year)


@app.route("/limits", methods=["GET", "POST"])
@login_required
def limits():
    budget = load_budget(user_budget_path())

    if request.method == "POST":
        category = request.form.get("category")
        amount_raw = request.form.get("amount")
        goal_raw = request.form.get("savings_goal")

        if category and amount_raw:
            try:
                budget.set_limit(category, float(amount_raw))
                flash(f"Limit for {category} set to {amount_raw}.", "success")
            except ValueError as e:
                flash(str(e), "error")

        if goal_raw:
            try:
                budget.set_savings_goal(float(goal_raw))
                flash(f"Savings goal set to {goal_raw}.", "success")
            except ValueError as e:
                flash(str(e), "error")

        save_budget(user_budget_path(), budget)
        return redirect(url_for("limits"))

    return render_template(
        "limits.html",
        categories=Category.categories,
        current_limits=budget.limits,
        current_goal=budget.get_savings_goal()
    )


if __name__ == "__main__":
    # debug=True is only for local testing on your own machine —
    # never leave this on for a publicly hosted app (PythonAnywhere
    # runs this file through WSGI, so this block doesn't even execute there)
    app.run(debug=True)
