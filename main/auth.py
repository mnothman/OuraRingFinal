"""
Auth module for handling Oura OAuth authentication with FastAPI.
Manages token storage, retrieval, and refresh logic using a Bearer token approach.
"""

import os
import random
import secrets
import string
import sqlite3
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional

import requests
from dotenv import load_dotenv, dotenv_values
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from fastapi.security.utils import get_authorization_scheme_param
from fastapi import Header
from fastapi import APIRouter
# Load env variables from .env file
env_values = dotenv_values(".env")
for key, value in env_values.items():
    os.environ[key] = value

load_dotenv()

# FastAPI app setup
app = FastAPI()

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

router = APIRouter()

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
            last_fetched_at TEXT DEFAULT NULL,
            last_fetched_stress_at TEXT DEFAULT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS oauth_state (
            state TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_auth_db()

def store_oauth_state(state: str):
    """
    Stores a new OAuth `state` in the DB with the current timestamp.
    """
    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO oauth_state (state)
        VALUES (?)
    ''', (state,))
    conn.commit()
    conn.close()

def verify_and_remove_oauth_state(state: str) -> bool:
    """
    Checks if the given `state` exists and is not older than 5 minutes.
    If valid, it removes it from DB to prevent replay. Returns True if valid, else False.
    """
    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT state, created_at
        FROM oauth_state
        WHERE state = ?
    ''', (state,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return False

    # parse created_at as a datetime
    # stored as e.g. "2025-02-28 10:33:00" if using default CURRENT_TIMESTAMP
    state_str, created_str = row
    try:
        created_dt = datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        # fallback in case DB store is different
        created_dt = datetime.strptime(created_str.split(".")[0], "%Y-%m-%d %H:%M:%S")

    # if older than 5 minutes, invalid
    if datetime.utcnow() - created_dt > timedelta(minutes=5):
        conn.close()
        return False

    # remove from DB to prevent reuse
    cursor.execute("DELETE FROM oauth_state WHERE state = ?", (state,))
    conn.commit()
    conn.close()
    return True


def store_token(user_id: str, access_token: str, refresh_token: str, expires_at: int):
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


def refresh_access_token(refresh_token: str) -> Optional[str]:
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


def get_valid_access_token(user_id: str) -> Optional[str]:
    """
    Retrieves a valid access token for a user.
    If expired, attempts to refresh. If refresh fails, deletes token.
    """
    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT access_token, refresh_token, expires_at FROM user_tokens WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    access_token, refresh_token, expires_at = row

    if datetime.now().timestamp() > float(expires_at):
        print("Access token expired! Refreshing...")

        new_access_token = refresh_access_token(refresh_token)
        if new_access_token:
            return new_access_token
        else:
            print(f"Refresh failed. Removing expired token for {user_id}.")
            conn = sqlite3.connect(AUTH_DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_tokens WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            return None  # User must re-authenticate

    return access_token

def get_user_id_from_token(authorization: str = Header(None)) -> Optional[str]:
    """
    Extracts the Bearer token from the `Authorization` header and retrieves the user ID.
    If the token is expired, it attempts to refresh automatically.
    """

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    scheme, token = get_authorization_scheme_param(authorization)
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authentication scheme")

    # Lookup the token in the database
    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, expires_at, refresh_token FROM user_tokens WHERE access_token = ?", (token,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id, expires_at, refresh_token = row

    # Check if token has expired
    if datetime.now().timestamp() > float(expires_at):
        print("Token expired, attempting refresh.")
        new_token = refresh_access_token(refresh_token)
        if not new_token:
            raise HTTPException(status_code=401, detail="Token expired and refresh failed. Please log in again.")

    return user_id

def get_oura_user_email(access_token: str) -> Optional[str]:
    """Fetches the user's email from Oura API."""
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(USER_INFO_URL, headers=headers, timeout=10)
    if response.status_code == 200:
        data = response.json()
        return data.get("email")
    
    return None

def generate_state() -> str:
    """Generates a cryptographically secure OAuth2 state string."""
    return secrets.token_urlsafe(16)

# All endpoints below
# Returns AUTH URL to client for the frontend to redirect to Oura's OAuth page
@router.get("/login")
def login():
    """
    Redirects the user to Oura's OAuth2 authorization page with a secure `state`.
    We store the `state` in DB for CSRF prevention.
    """
    # Generate a random 'state' and store in DB
    state = secrets.token_urlsafe(16)
    store_oauth_state(state)

    # Build the Oura auth URL
    auth_url = (
        f"{AUTHORIZATION_URL}?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={SCOPES.replace(' ', '%20')}"
        f"&state={state}"
    )
    print(f"Oura OAuth URL: {auth_url}")
    return RedirectResponse(url=auth_url)

# need to redirect to react native app here ex. return RedirectResponse(url=f"https://my-app.com/oauth-callback?token={access_token}")
@router.get("/callback")
def callback(code: str, state: Optional[str] = None):
    """
    Oura redirects back with `code` and `state` after user logs in.
    We verify the `state` from DB, then exchange the code for tokens, store them, and return to client.
    """
    if not state or not verify_and_remove_oauth_state(state):
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid or expired state. CSRF check failed."}
        )

    # Exchange authorization code for tokens
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(TOKEN_URL, data=token_data, headers=headers, timeout=10)
    if resp.status_code != 200:
        return JSONResponse(
            status_code=400,
            content={"error": "Failed to obtain access token", "details": resp.text},
        )

    tokens = resp.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    expires_in = tokens["expires_in"]
    expires_at = int(datetime.utcnow().timestamp()) + expires_in

    # (Optional) call Oura user endpoint to get user ID / email
    user_id = fetch_oura_user_email(access_token)
    if not user_id:
        return JSONResponse(status_code=400, content={"error": "Failed to fetch user info from Oura"})

    # Store the tokens in DB
    store_token(user_id, access_token, refresh_token, expires_at)
    print(f"Stored tokens for user: {user_id}")

    # Return tokens to client (or do an additional redirect to your React app)
    # !!!!!!!!!!!!!!!!! INSTEAD OF RETURNING HERE, NEED TO REDIRECT TO REACT NATIVE APP WITH DEEP LINKING
    mobile_app_url = f"myapp://oauth-callback?token={access_token}&user={user_id}"

    return RedirectResponse(url=mobile_app_url)
    # return {
    #     "message": "Login successful",
    #     "user_id": user_id,
    #     "access_token": access_token,
    #     "expires_in": expires_in
    # }

def fetch_oura_user_email(access_token: str) -> Optional[str]:
    """
    Example function that queries Oura's user/personal_info endpoint to get the user's email or ID.
    """
    user_info_url = "https://api.ouraring.com/v2/usercollection/personal_info"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(user_info_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("email")  # or data["data"]["email"] if nested
    except requests.RequestException:
        pass
    return None


@router.get("/user-info")
def get_user_info(user_id: str = Depends(get_user_id_from_token)):
    """
    Example protected endpoint that returns the Oura user info from DB.
    We rely on Bearer token in the Authorization header (token is the Oura access token).
    """
    # The `user_id` is derived from the DB lookup in get_user_id_from_token
    access_token = get_valid_access_token(user_id)
    if not access_token:
        raise HTTPException(status_code=401, detail="No valid access token")

    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(USER_INFO_URL, headers=headers, timeout=10)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Failed to fetch user info")
    return resp.json()

# Triggers Oura refresh flow, updates db with new access token
@router.get("/refresh")
def refresh_oura_token(user_id: str):
    """
    Manually triggers a refresh for a user's Oura tokens if needed.
    Typically, the client would call this if a token is expired.
    """
    # Retrieve old token info
    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT refresh_token FROM user_tokens WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    existing_refresh = row[0]
    token_data = {
        "grant_type": "refresh_token",
        "refresh_token": existing_refresh,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post(TOKEN_URL, data=token_data, headers=headers, timeout=10)

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to refresh token")

    tokens = response.json()
    new_access_token = tokens["access_token"]
    new_refresh_token = tokens.get("refresh_token", existing_refresh)
    new_expires_at = int(datetime.now().timestamp()) + tokens["expires_in"]

    # Update DB
    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE user_tokens SET
            access_token = ?,
            refresh_token = ?,
            expires_at = ?
        WHERE user_id = ?
    ''', (new_access_token, new_refresh_token, new_expires_at, user_id))
    conn.commit()
    conn.close()

    return {
        "message": "Token refreshed successfully",
        "user_id": user_id,
        "access_token": new_access_token,
        "expires_at": tokens["expires_in"]
    }

# removes users row from db, invalidating current tokens
@router.get("/logout")
def logout(user_id: str):
    """
    Logs out user and removes their tokens from the database.
    The client passes user_id in query param or route param. 
    """
    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_tokens WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    return {"message": f"User {user_id} logged out and token deleted"}
