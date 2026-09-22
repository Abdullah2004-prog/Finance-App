import json
import os
import csv
from abc import ABC, abstractmethod


class Transaction:
    def __init__(self, date, amount, category, payment_type):
        self._date = date
        self._amount = amount
        self._category = category
        self._payment_type = payment_type

    @property
    def date(self):
        return self._date

    @property
    def amount(self):
        return self._amount

    @amount.setter
    def amount(self, value):
        if value < 0:
            raise ValueError("Amount cannot be negative")
        self._amount = value

    @property
    def category(self):
        return self._category

    @property
    def payment_type(self):
        return self._payment_type

    def apply(self, balance):
        raise NotImplementedError("Subclasses must implement apply()")

    def to_dict(self):
        return {
            "type": self.__class__.__name__,
            "date": self._date,
            "amount": self._amount,
            "category": self._category,
            "payment_type": self._payment_type
        }

    def __str__(self):
        return f"{self._date} | {self._category:<12} | {self._payment_type:<10} | {self._amount}"

    def __repr__(self):
        return self.__str__()


class Income(Transaction):
    def apply(self, balance):
        return balance + self.amount

    def __str__(self):
        return f"[INCOME]  {self.date} | {self.category:<12} | {self.payment_type:<10} | +{self.amount}"


class Expense(Transaction):
    def apply(self, balance):
        return balance - self.amount

    def __str__(self):
        return f"[EXPENSE] {self.date} | {self.category:<12} | {self.payment_type:<10} | -{self.amount}"


def transaction_from_dict(data):
    if data.get("type") == "Income":
        return Income(data["date"], float(data["amount"]), data["category"], data["payment_type"])
    elif data.get("type") == "Expense":
        return Expense(data["date"], float(data["amount"]), data["category"], data["payment_type"])
    else:
        return Transaction(data["date"], float(data["amount"]), data["category"], data["payment_type"])


class Category:
    categories = [
        "Food",
        "Transport",
        "Bills",
        "Salary",
        "Shopping",
        "Entertainment"
    ]


class StorageManager(ABC):
    def __init__(self, filepath):
        self.filepath = filepath

    @abstractmethod
    def save(self, transactions):
        pass

    @abstractmethod
    def load(self):
        pass


class JSONStorage(StorageManager):
    def __init__(self, filepath="transactions.json"):
        super().__init__(filepath)

    def save(self, transactions):
        data = [t.to_dict() for t in transactions]
        with open(self.filepath, mode='w') as file:
            json.dump(data, file, indent=4)

    def load(self):
        if not os.path.exists(self.filepath):
            return []
        with open(self.filepath, mode='r') as file:
            data = json.load(file)
        return [transaction_from_dict(item) for item in data]


class CSVStorage(StorageManager):
    def __init__(self, filepath="transactions.csv"):
        super().__init__(filepath)

    def save(self, transactions):
        with open(self.filepath, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["type", "date", "amount", "category", "payment_type"])
            for t in transactions:
                d = t.to_dict()
                writer.writerow([d["type"], d["date"], d["amount"], d["category"], d["payment_type"]])

    def load(self):
        if not os.path.exists(self.filepath):
            return []
        with open(self.filepath, mode='r', newline='') as file:
            reader = csv.DictReader(file)
            return [transaction_from_dict(row) for row in reader]


class Budget:
    def __init__(self):
        self._limits = {}
        self._savings_goal = None

    @property
    def limits(self):
        return self._limits

    def set_limit(self, category, amount):
        if amount < 0:
            raise ValueError("Limit cannot be negative")
        self._limits[category] = amount

    def get_limit(self, category):
        return self._limits.get(category)

    def set_savings_goal(self, amount):
        if amount < 0:
            raise ValueError("Savings goal cannot be negative")
        self._savings_goal = amount

    def get_savings_goal(self):
        return self._savings_goal

    def check_savings_progress(self, current_balance):
        if self._savings_goal is None:
            return None
        if self._savings_goal == 0:
            percent = 0
        else:
            percent = (current_balance / self._savings_goal) * 100
        display_percent = max(0, min(percent, 100))
        return {
            "balance": current_balance,
            "goal": self._savings_goal,
            "percent": round(display_percent),
            "exceeded": percent > 100
        }

    def check_alert(self, category, spent):
        limit = self.get_limit(category)
        if not limit:
            return None
        percent = (spent / limit) * 100
        if percent >= 100:
            return {"level": "alert", "message": f"{category} is at {percent:.0f}% of budget (OVER LIMIT)"}
        elif percent >= 80:
            return {"level": "warning", "message": f"{category} is at {percent:.0f}% of budget"}
        return None

    def monthly_summary(self, transactions, month, year):
        totals = {}
        for t in transactions:
            parts = t.date.split("-")
            if len(parts) != 3:
                continue
            t_year, t_month = int(parts[0]), int(parts[1])
            if t_year == year and t_month == month:
                totals[t.category] = totals.get(t.category, 0) + t.amount

        rows = []
        for category, spent in totals.items():
            limit = self.get_limit(category)
            status = "-"
            if limit is not None:
                status = "OVER" if spent > limit else "OK"
            alert = self.check_alert(category, spent)
            rows.append({
                "category": category,
                "spent": spent,
                "limit": limit if limit is not None else "N/A",
                "status": status,
                "alert": alert
            })
        return rows


def save_budget(filepath, budget):
    data = {
        "limits": budget.limits,
        "savings_goal": budget.get_savings_goal()
    }
    with open(filepath, mode='w') as file:
        json.dump(data, file, indent=4)


def load_budget(filepath):
    budget = Budget()
    if not os.path.exists(filepath):
        return budget

    with open(filepath, mode='r') as file:
        data = json.load(file)

    for category, amount in data.get("limits", {}).items():
        budget.set_limit(category, amount)

    goal = data.get("savings_goal")
    if goal is not None:
        budget.set_savings_goal(goal)

    return budget


def calculate_balance(transactions):
    balance = 0
    for t in transactions:
        balance = t.apply(balance)
    return balance


def filter_by_month(transactions, month, year):
    """Return only the transactions whose date falls in the given month/year.
    month/year may be None, in which case no filtering happens (returns all)."""
    if month is None or year is None:
        return list(transactions)

    filtered = []
    for t in transactions:
        parts = t.date.split("-")
        if len(parts) != 3:
            continue
        t_year, t_month = int(parts[0]), int(parts[1])
        if t_year == year and t_month == month:
            filtered.append(t)
    return filtered


def available_months(transactions):
    """Return a sorted list of unique (year, month) pairs present in the data,
    newest first — used to populate a filter dropdown."""
    seen = set()
    for t in transactions:
        parts = t.date.split("-")
        if len(parts) != 3:
            continue
        seen.add((int(parts[0]), int(parts[1])))
    return sorted(seen, reverse=True)
