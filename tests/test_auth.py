import sys
import os
import pytest
import sqlite3
import requests
from flask import session

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Assuming your code is in a file named auth.py
from main.auth import app, init_auth_db, AUTH_DB_FILE

# Ensure the database is stored in /databases/
DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../databases"))
AUTH_DB_FILE = os.path.join(DB_DIR, "auth.db")

# Ensure /databases/ directory exists
os.makedirs(DB_DIR, exist_ok=True)

@pytest.fixture
def client():
    """
    Pytest fixture to create a test client for the Flask app,
    and ensure a fresh test database before each test.
    """
    app.config["TESTING"] = True
    with app.test_client() as client:
        # Initialize/clean DB before each test
        with app.app_context():
            init_auth_db()
            # Optional: clear the DB if needed
            conn = sqlite3.connect(AUTH_DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_tokens")
            conn.commit()
            conn.close()
        yield client

init_auth_db()


def test_login_redirect(client):
    """
    Test that /login redirects to the Oura OAuth Authorization URL.
    """
    response = client.get("/login", follow_redirects=False)
    # We expect a 302 redirect
    assert response.status_code == 302
    # Check that the redirect location includes "cloud.ouraring.com/oauth/authorize"
    assert "cloud.ouraring.com/oauth/authorize" in response.location


def test_callback_missing_code(client):
    """
    Test /callback when no 'code' param is provided (or an error param is present).
    """
    # Simulate Oura returning an error
    response = client.get("/callback?error=access_denied")
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["error"] == "access_denied"


def test_callback_invalid_state(client):
    """
    Test /callback with an invalid state to ensure it rejects mismatched states.
    """
    with client.session_transaction() as sess:
        sess["oauth_state"] = "REAL_STATE"

    # Provide a different 'state' param, so it should fail
    response = client.get("/callback?code=123&state=FAKE_STATE")
    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["error"] == "Invalid OAuth state"


@pytest.mark.parametrize("mock_oura_response_status,mock_oura_response_json", [
    (200, {
        "access_token": "mock_access_token",
        "refresh_token": "mock_refresh_token",
        "expires_in": 3600
    }),
    (400, {"error": "invalid_request"}),
])
def test_callback_exchange_code(
    client,
    requests_mock,
    mock_oura_response_status,
    mock_oura_response_json
):
    """
    Test /callback logic with various responses from Oura's token endpoint.
    We use requests_mock to intercept the POST request.
    """
    # Set a valid state in session
    with client.session_transaction() as sess:
        sess["oauth_state"] = "TEST_STATE"

    # Mock Oura token endpoint
    requests_mock.post(
        "https://api.ouraring.com/oauth/token",
        json=mock_oura_response_json,
        status_code=mock_oura_response_status
    )

    # Mock Oura user info endpoint (used by get_oura_user_email)
    # Only mock if the token response is 200, otherwise the code won't call user info
    if mock_oura_response_status == 200:
        requests_mock.get(
            "https://api.ouraring.com/v2/usercollection/personal_info",
            json={"email": "testuser@example.com"},
            status_code=200
        )

    # Perform callback request
    query = "?code=TEST_CODE&state=TEST_STATE"
    response = client.get("/callback" + query)
    json_data = response.get_json()

    if mock_oura_response_status == 200:
        # Token exchange success
        assert response.status_code == 200
        assert json_data["message"] == "Login successful"
        assert json_data["access_token"] == "mock_access_token"
        assert json_data["user_id"] == "testuser@example.com"

        # Check DB to ensure tokens were stored
        conn = sqlite3.connect(AUTH_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, access_token, refresh_token FROM user_tokens")
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "testuser@example.com"
        assert result[1] == "mock_access_token"
        assert result[2] == "mock_refresh_token"
    else:
        # Token exchange fail
        assert response.status_code == 400
        assert "error" in json_data


def test_get_token_no_user(client):
    """
    Test /token when there's no logged-in user.
    """
    response = client.get("/token")
    assert response.status_code == 401
    assert response.get_json()["error"] == "User not authenticated"


def test_get_token_user_expired_token(client, requests_mock):
    """
    Test /token for a user whose token has expired,
    ensuring the refresh flow is triggered.
    """
    # Insert a user with expired token into DB
    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    user_id = "expireduser@example.com"
    cursor.execute('''
        INSERT INTO user_tokens (user_id, access_token, refresh_token, expires_at, last_fetched_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, "old_access_token", "old_refresh_token", 100, None))    
    conn.commit()
    conn.close()

    # Log this user in
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    # Mock Oura's token refresh endpoint
    requests_mock.post(
        "https://api.ouraring.com/oauth/token",
        json={
            "access_token": "refreshed_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 3600
        },
        status_code=200
    )

    # Hit /token, expecting the refresh flow to kick in
    response = client.get("/token")
    assert response.status_code == 200
    data = response.get_json()
    assert data["user_id"] == user_id
    assert data["access_token"] == "refreshed_access_token"

    # Check DB that tokens got updated
    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT access_token, refresh_token FROM user_tokens WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    assert row[0] == "refreshed_access_token"
    assert row[1] == "new_refresh_token"


def test_get_user_info_no_user(client):
    """
    Test /user when no user is logged in.
    """
    response = client.get("/user")
    assert response.status_code == 401
    assert response.get_json()["error"] == "User not authenticated"


def test_get_user_info_ok(client, requests_mock):
    """
    Test /user for a valid user with a non-expired token.
    """
    # Insert a user with valid token
    expires_at = 9999999999  # far in the future
    user_id = "validuser@example.com"

    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO user_tokens (user_id, access_token, refresh_token, expires_at, last_fetched_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, "valid_access_token", "valid_refresh_token", expires_at, None))
    conn.commit()
    conn.close()

    # Log user in via session
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    # Mock the user info response from Oura
    mock_user_data = {
        "id": "some_id",
        "email": user_id,
        "age": 30,
        "height": 1.75,
        "weight": 75,
        "biological_sex": "male"
    }
    requests_mock.get(
        "https://api.ouraring.com/v2/usercollection/personal_info",
        json=mock_user_data,
        status_code=200
    )

    response = client.get("/user")
    assert response.status_code == 200
    data = response.get_json()
    # Expect the same data we mocked
    assert data["id"] == "some_id"
    assert data["email"] == user_id
    assert data["age"] == 30


def test_logout_no_user(client):
    """
    Test /logout when no user is logged in.
    """
    response = client.get("/logout")
    assert response.status_code == 400
    assert response.get_json()["error"] == "No user logged in"


def test_logout_ok(client):
    """
    Test successful logout, verifying DB row is removed.
    """
    # Insert user in DB
    user_id = "logoutuser@example.com"
    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO user_tokens (user_id, access_token, refresh_token, expires_at, last_fetched_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, "some_token", "some_refresh", 9999999999, None))
    conn.commit()
    conn.close()

    # Log them in
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    # Now logout
    response = client.get("/logout")
    assert response.status_code == 200
    assert "logged out and token deleted" in response.get_json()["message"]

    # Confirm row was removed from DB
    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM user_tokens WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 0
