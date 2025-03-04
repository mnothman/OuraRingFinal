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
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
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

    # fix error 400 redirect uri with possible encoding fix
    encoded_redirect_uri = urllib.parse.quote(REDIRECT_URI, safe='')

    # Build the Oura auth URL
    auth_url = (
        f"{AUTHORIZATION_URL}?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={encoded_redirect_uri}"
        f"&scope={SCOPES.replace(' ', '%20')}"
        f"&state={state}"
    )
    print(f"Oura OAuth URL: {auth_url}")
    return RedirectResponse(url=auth_url)

# need to redirect to react native app here ex. return RedirectResponse(url=f"https://my-app.com/oauth-callback?token={access_token}")
@router.get("/callback")
def callback(code: str, state: str):
    """
    OAuth2 callback endpoint that exchanges the code for an access token
    and redirects the user back to the frontend.
    """
    # Verify the state to prevent CSRF
    if not verify_and_remove_oauth_state(state):
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid or expired state. Please try again."}
        )

    try:
        # Exchange the code for a token
        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        # Log the response for debugging
        print(f"Token exchange response: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error response: {response.text}")
            return JSONResponse(
                status_code=response.status_code,
                content={"error": f"Token exchange failed: {response.text}"}
            )
        
        # Parse the response
        token_data = response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 86400)  # Default to 24 hours
        
        # Fetch user information to get user_id (email)
        user_response = requests.get(
            USER_INFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        print(f"User info response status: {user_response.status_code}")
        
        # Default user_id to a generated value in case we can't get the email
        user_id = None
        
        if user_response.status_code == 200:
            try:
                user_data = user_response.json()
                print(f"User data response: {user_data}")
                
                # Try different paths to find the email in the response
                if "data" in user_data and "email" in user_data["data"]:
                    user_id = user_data["data"]["email"]
                elif "data" in user_data and isinstance(user_data["data"], list) and len(user_data["data"]) > 0:
                    # If data is a list, try the first item
                    item = user_data["data"][0]
                    if "email" in item:
                        user_id = item["email"]
                elif "email" in user_data:
                    # Direct email field
                    user_id = user_data["email"]
                
                print(f"Extracted user_id (email): {user_id}")
            except Exception as e:
                print(f"Error parsing user data: {str(e)}")
        else:
            print(f"Error fetching user info: {user_response.text}")
        
        # If we couldn't get the email, generate a unique ID based on the access token
        if not user_id:
            print("Could not extract email from user data, using a generated ID instead")
            # Use the first 8 characters of the access token as a user ID
            user_id = f"user_{access_token[:8]}"
            print(f"Generated user_id: {user_id}")
        
        # Store tokens in the database
        expires_at = int(datetime.utcnow().timestamp()) + expires_in
        store_token(user_id, access_token, refresh_token, expires_at)
        print(f"Stored tokens for user: {user_id}")
        
        # Create URLs for both Expo and native app
        native_app_url = f"myapp://oauth-callback?token={access_token}&user={user_id}"
        
        # Use the IP address from the Expo development server
        # This should match what you see in your Expo dev server output
        expo_url = f"exp://10.0.0.47:8081/--/oauth-callback?token={access_token}&user={user_id}"
        
        print(f"Redirecting to multiple app URL options")
        
        # Return HTML with buttons/links for different URL schemes
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Login Successful</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    text-align: center;
                }}
                h1 {{
                    color: #4CAF50;
                }}
                .info {{
                    background-color: #f8f8f8;
                    border-radius: 5px;
                    padding: 15px;
                    margin: 20px 0;
                    text-align: left;
                }}
                .token-box {{
                    background-color: #f1f1f1;
                    border: 1px solid #ddd;
                    padding: 10px;
                    border-radius: 5px;
                    font-family: monospace;
                    font-size: 12px;
                    overflow-wrap: break-word;
                    margin: 10px 0;
                    text-align: left;
                    position: relative;
                }}
                button {{
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    padding: 10px 15px;
                    text-align: center;
                    text-decoration: none;
                    display: inline-block;
                    font-size: 16px;
                    margin: 10px 2px;
                    cursor: pointer;
                    border-radius: 5px;
                }}
                .copy-btn {{
                    position: absolute;
                    right: 5px;
                    top: 5px;
                    background-color: #555;
                    color: white;
                    border: none;
                    padding: 3px 8px;
                    font-size: 12px;
                    cursor: pointer;
                    border-radius: 3px;
                }}
                .important {{
                    color: #d32f2f;
                    font-weight: bold;
                }}
                .highlight-box {{
                    background-color: #fffde7;
                    border-left: 4px solid #fbc02d;
                    padding: 15px;
                    margin: 20px 0;
                    text-align: left;
                }}
                .instruction-step {{
                    margin: 10px 0;
                    padding-left: 20px;
                    position: relative;
                }}
                .instruction-step:before {{
                    content: "";
                    position: absolute;
                    left: 0;
                    top: 6px;
                    width: 12px;
                    height: 12px;
                    background-color: #4CAF50;
                    border-radius: 50%;
                }}
                .app-buttons {{
                    display: flex;
                    flex-direction: column;
                    gap: 10px;
                    margin: 20px 0;
                }}
                .app-link {{
                    background-color: #2196F3;
                    color: white;
                    text-decoration: none;
                    padding: 12px;
                    border-radius: 5px;
                    display: block;
                }}
                img {{
                    max-width: 100%;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    margin: 10px 0;
                }}
            </style>
            <script>
                function copyToClipboard(text, elementId) {{
                    navigator.clipboard.writeText(text).then(function() {{
                        document.getElementById(elementId).innerText = "Copied!";
                        setTimeout(function() {{
                            document.getElementById(elementId).innerText = "Copy";
                        }}, 2000);
                    }}).catch(function(err) {{
                        console.error('Could not copy text: ', err);
                    }});
                }}
                
                // We're disabling automatic redirection to prevent app disconnection
                // Instead, we'll instruct users to manually click the "Open with Expo" button
                /*
                setTimeout(function() {{
                    window.location.href = "{native_app_url}";
                    setTimeout(function() {{
                        window.location.href = "{expo_url}";
                    }}, 1000);
                }}, 1500);
                */
            </script>
        </head>
        <body>
            <h1>Login Successful!</h1>
            <p>Your login was successful. You're almost ready to use the app!</p>
            
            <div class="highlight-box">
                <h3>🔹 IMPORTANT: How to Return to the App</h3>
                <p>For the best experience, please <span class="important">do NOT use automatic redirection</span>. Instead:</p>
                
                <div class="instruction-step">
                    When Chrome asks "Open with Expo", click that option. This maintains your app's connection to the development server.
                </div>
                
                <div class="instruction-step">
                    If you don't see that option, click one of the buttons below, then select "Open with Expo" when prompted.
                </div>
                
                <div class="instruction-step">
                    If you still have issues, use the manual token entry option in the app.
                </div>
            </div>
            
            <div class="app-buttons">
                <a href="{expo_url}?token={access_token}&user={user_id}" class="app-link">Open with Expo (Recommended)</a>
                <a href="{native_app_url}?token={access_token}&user={user_id}" class="app-link">Open with Native App</a>
            </div>
            
            <h2>Manual Token Entry</h2>
            <p>If the buttons above don't work, copy these values and enter them manually in the app:</p>
            
            <h3>Access Token</h3>
            <div class="token-box">
                {access_token}
                <button id="token-btn" class="copy-btn" onclick="copyToClipboard('{access_token}', 'token-btn')">Copy</button>
            </div>
            
            <h3>User Email</h3>
            <div class="token-box">
                {user_id}
                <button id="email-btn" class="copy-btn" onclick="copyToClipboard('{user_id}', 'email-btn')">Copy</button>
            </div>
            
            <div class="info">
                <p><strong>Troubleshooting:</strong></p>
                <p>If you're having trouble returning to the app:</p>
                <ol>
                    <li>Make sure your Expo development server is still running</li>
                    <li>Try reopening the Expo Go app manually</li>
                    <li>Use the manual token entry feature on the login screen</li>
                </ol>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
    except Exception as e:
        print(f"Exception in OAuth callback: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to process OAuth callback: {str(e)}"}
        )

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