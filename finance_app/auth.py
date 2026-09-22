import json
import os
import re
from functools import wraps
from flask import session, redirect, url_for, request, flash
from werkzeug.security import generate_password_hash, check_password_hash

USERS_FILE = "data/users.json"
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,20}$")


def _ensure_data_dir():
    os.makedirs("data", exist_ok=True)


def _load_users():
    _ensure_data_dir()
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def _save_users(users):
    _ensure_data_dir()
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)


def register_user(username, password):
    """Create a new user. Returns (success, error_message)."""
    if not USERNAME_PATTERN.match(username or ""):
        return False, "Username must be 3-20 characters: letters, numbers, underscore only."

    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters."

    users = _load_users()
    if username in users:
        return False, "That username is already taken."

    users[username] = {
        "password_hash": generate_password_hash(password)
    }
    _save_users(users)
    return True, None


def verify_user(username, password):
    """Check username/password against stored hash. Returns True/False."""
    users = _load_users()
    if username not in users:
        return False
    return check_password_hash(users[username]["password_hash"], password)


def user_exists(username):
    users = _load_users()
    return username in users


def login_required(view_func):
    """Decorator: redirect to /login if no user is logged in."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)
    return wrapped


def current_username():
    return session.get("username")
