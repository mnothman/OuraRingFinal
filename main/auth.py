"""
Auth module for handling Oura OAuth authentication.
Manages token storage, retrieval, and refresh logic.
"""

import os
import random
import string
import sqlite3
import urllib.parse
from datetime import datetime

import requests
from flask import Flask, redirect, request, jsonify, session
from dotenv import load_dotenv, dotenv_values

# Load env variables from .env file
env_values = dotenv_values(".env")
for key, value in env_values.items():
    os.environ[key] = value

load_dotenv()

# Flask app setup
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")

# Database configuration
DB_DIR = os.path.join(os.path.dirname(__file__), "..", "databases")
AUTH_DB_FILE = os.path.join(DB_DIR, "auth.db")

# Ensure `/databases/` folder exists
os.makedirs(DB_DIR, exist_ok=True)

# OAuth credentials
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

# Oura API endpoints
AUTHORIZATION_URL = "https://cloud.ouraring.com/oauth/authorize"
TOKEN_URL = "https://api.ouraring.com/oauth/token"
USER_INFO_URL = "https://api.ouraring.com/v2/usercollection/personal_info"

SCOPES = "email personal daily heartrate workout tag session spo2Daily"


def init_auth_db():
    """Initializes the database for storing user authentication tokens."""
    # print("init_auth_db() called!")  # Debug

    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_tokens (
            user_id TEXT PRIMARY KEY,
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            last_fetched_at TEXT DEFAULT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_auth_db()


def store_token(user_id, access_token, refresh_token, expires_at):
    """
    Stores or updates the user's token in the database.
    expires_at is stored as an integer (UNIX timestamp).
    """
    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO user_tokens (user_id, access_token, refresh_token, expires_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            expires_at = excluded.expires_at
    ''', (user_id, access_token, refresh_token, expires_at))
    
    conn.commit()
    conn.close()


def refresh_access_token(refresh_token):
    """Uses the refresh token to get a new access token from Oura."""
    token_data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post(TOKEN_URL, data=token_data, headers=headers, timeout=10)

    if response.status_code == 200:
        tokens = response.json()
        new_access_token = tokens["access_token"]
        new_refresh_token = tokens.get("refresh_token", refresh_token)
        expires_in = tokens["expires_in"]
        new_expires_at = int(datetime.now().timestamp()) + expires_in

        # Update the database with the new tokens
        conn = sqlite3.connect(AUTH_DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE user_tokens SET
                access_token = ?,
                refresh_token = ?,
                expires_at = ?
            WHERE refresh_token = ?
        ''', (new_access_token, new_refresh_token, new_expires_at, refresh_token))
        conn.commit()
        conn.close()

        print("Token refreshed successfully!")
        return new_access_token

    print(f"Token refresh failed! {response.text}")
    return None


def get_valid_access_token(user_id):
    """
    Retrieves the valid access token for a given user, refreshing if necessary.
    """
    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT access_token, refresh_token, expires_at FROM user_tokens WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    access_token, refresh_token, expires_at = row
    expires_at = float(expires_at)

    if datetime.now().timestamp() > expires_at:
        print("Access token expired! Refreshing...")
        return refresh_access_token(refresh_token)

    return access_token


def get_oura_user_email(access_token):
    """Fetches the user's email from Oura API."""
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(USER_INFO_URL, headers=headers, timeout=10)
    if response.status_code == 200:
        data = response.json()
        return data.get("email")
    
    return None


def generate_state():
    """Generates a random state string for OAuth2 security."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=16))


@app.route("/login")
def login():
    """Redirects the user to Oura's OAuth2 authorization page."""
    state = generate_state()
    session['oauth_state'] = state

    auth_url = (
        f"{AUTHORIZATION_URL}?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
        f"&scope={urllib.parse.quote(SCOPES, safe='')}"
        f"&state={state}"
    )
    print(f"Generated OAuth URL: {auth_url}")
    return redirect(auth_url)


@app.route("/callback")
def callback():
    """Handles Oura's OAuth2 callback and exchanges authorization code for an access token."""
    error = request.args.get("error")
    if error:
        return jsonify({"error": error})

    code = request.args.get("code")
    state = request.args.get("state")

    if state != session.get('oauth_state'):
        return jsonify({"error": "Invalid OAuth state"}), 400

    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post(TOKEN_URL, data=token_data, headers=headers, timeout=10)

    if response.status_code == 200:
        tokens = response.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        expires_at = int(datetime.now().timestamp()) + tokens["expires_in"]
        user_email = get_oura_user_email(access_token)
        if not user_email:
            return jsonify({"error": "Failed to fetch user email"}), 400

        store_token(user_email, access_token, refresh_token, expires_at)

        session["user_id"] = user_email
        return jsonify({"message": "Login successful", "user_id": user_email, "access_token": access_token})
          
    return jsonify({"error": "Failed to obtain access token", "details": response.text}), 400

@app.route("/token")
def get_token():
    """
    Returns a valid access token for the currently logged-in user.
    If expired, it will be automatically refreshed.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "User not authenticated"}), 401

    access_token = get_valid_access_token(user_id)
    if not access_token:
        return jsonify({"error": "Token expired or not found"}), 401

    return jsonify({"user_id": user_id, "access_token": access_token})


@app.route("/user")
def get_user_info():
    """
    Fetches user personal info using a valid access token.
    If expired, automatically refreshes before making the request.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "User not authenticated"}), 401

    access_token = get_valid_access_token(user_id)
    if not access_token:
        return jsonify({"error": "Token expired or not found"}), 401

    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(USER_INFO_URL, headers=headers, timeout=10)

    if response.status_code == 200:
        return jsonify(response.json())

    return jsonify({"error": "Failed to fetch user info", "details": response.text}), response.status_code


@app.route("/logout")
def logout():
    """Logs out user and removes their tokens from the database."""
    user_id = session.get("user_id")
    if user_id:
        conn = sqlite3.connect(AUTH_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_tokens WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

        session.clear()
        return jsonify({"message": f"User {user_id} logged out and token deleted"})

    return jsonify({"error": "No user logged in"}), 400

if __name__ == "__main__":
    app.run(debug=True, port=5000)
