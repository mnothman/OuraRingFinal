import os
import sys
import pytest
import sqlite3
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import oura_apiHeart
    oura_apiHeart = oura_apiHeart
except ModuleNotFoundError as e:
    print("Import Error: Could not find `oura_apiHeart`.")
    print(f"Debug Info: sys.path = {sys.path}")
    raise e

import requests_mock


@pytest.fixture
def fresh_db(tmp_path):
    """
    Points DB_FILE to a temp directory and re-initializes the heart_rate and daily_stress tables.
    """
    test_db_path = tmp_path / "heart_rate_test.db"
    oura_apiHeart.DB_FILE = str(test_db_path)
    oura_apiHeart.init_db()  # This creates both heart_rate and daily_stress tables
    yield

@pytest.fixture
def fresh_auth_db(tmp_path):
    """
    Points AUTH_DB_FILE to a temp directory and creates a minimal user_tokens table
    with a last_fetched_stress_at column.
    """
    test_auth_db_path = tmp_path / "auth_test.db"
    oura_apiHeart.AUTH_DB_FILE = str(test_auth_db_path)

    conn = sqlite3.connect(oura_apiHeart.AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_tokens (
            user_id TEXT PRIMARY KEY,
            access_token TEXT,
            refresh_token TEXT,
            expires_at TEXT,
            last_fetched_at TEXT,
            last_fetched_stress_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    yield

@pytest.fixture
def mock_token(mocker):
    """
    Mocks get_valid_access_token to always return "TEST_TOKEN" unless overridden.
    """
    return mocker.patch("oura_apiHeart.get_valid_access_token", return_value="TEST_TOKEN")


def test_daily_stress_db_structure(fresh_db):
    """
    Verify that the 'daily_stress' table is created properly by init_db().
    """
    conn = sqlite3.connect(oura_apiHeart.DB_FILE)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info('daily_stress')")
    columns = cursor.fetchall()
    conn.close()

    col_names = [col[1] for col in columns]
    # Expect columns: id, user_id, date, stress_high, recovery_high, day_summary
    assert "id" in col_names
    assert "user_id" in col_names
    assert "date" in col_names
    assert "stress_high" in col_names
    assert "recovery_high" in col_names
    assert "day_summary" in col_names


def test_store_daily_stress_duplicates(fresh_db):
    """
    Ensures store_daily_stress uses INSERT OR IGNORE and doesn't duplicate daily entries.
    """
    user_id = "test_dupe@example.com"

    # Insert 1 record
    data1 = [
        {"day": "2025-02-01", "stress_high": 2, "recovery_high": 1, "day_summary": "normal"}
    ]
    oura_apiHeart.store_daily_stress(user_id, data1)

    # Insert a duplicate for the same date
    data2 = [
        {"day": "2025-02-01", "stress_high": 5, "recovery_high": 4, "day_summary": "different"}
    ]
    oura_apiHeart.store_daily_stress(user_id, data2)

    # Only 1 record for that date should exist
    conn = sqlite3.connect(oura_apiHeart.DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT date, stress_high, recovery_high, day_summary "
        "FROM daily_stress WHERE user_id = ?",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    # Should still be exactly 1 row
    assert len(rows) == 1
    # The original "normal" record (INSERT OR IGNORE doesn't overwrite)
    assert rows[0] == ("2025-02-01", 2, 1, "normal")


@pytest.mark.parametrize("mock_status, mock_json_factory, expected_error", [
    # 1) Normal 200, some data returned
    (
        200,
        lambda: {
            "data": [
                {
                    "day": (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d"),
                    "stress_high": 2,
                    "recovery_high": 1,
                    "day_summary": "normal"
                },
                {
                    "day": (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d"),
                    "stress_high": 3,
                    "recovery_high": 2,
                    "day_summary": "somewhat_stressful"
                }
            ]
        },
        None
    ),
    # 2) 200 but empty data
    (200, lambda: {"data": []}, "No stress data returned from Oura API"),
    # 3) Non-200 error
    (500, lambda: {}, "Failed to fetch stress data: 500"),
])
def test_fetch_daily_stress_basic(
    fresh_db, fresh_auth_db, mock_token, requests_mock,
    mock_status, mock_json_factory, expected_error
):
    """
    Tests fetch_daily_stress for normal success, empty data, and non-200 error.
    This DOES NOT test last_fetched_stress_at usage.
    """
    user_id = "test_stress@example.com"

    mock_json = mock_json_factory()
    requests_mock.get(
        f"{oura_apiHeart.API_BASE_URL}/daily_stress",
        json=mock_json,
        status_code=mock_status
    )

    # Insert user with no last_fetched_stress_at -> simulating first fetch
    conn = sqlite3.connect(oura_apiHeart.AUTH_DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_tokens (user_id, access_token, last_fetched_stress_at)
        VALUES (?, ?, ?)
    """, (user_id, "TEST_TOKEN", None))
    conn.commit()
    conn.close()

    result = oura_apiHeart.fetch_daily_stress(user_id)

    if expected_error:
        assert result["error"] == expected_error
    else:
        assert isinstance(result, list)
        # Check DB insertion
        conn = sqlite3.connect(oura_apiHeart.DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT date, stress_high, recovery_high, day_summary FROM daily_stress WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        conn.close()

        expected_data = mock_json["data"]
        assert len(rows) == len(expected_data)


def test_fetch_daily_stress_missing_token(fresh_db, mocker):
    """
    If get_valid_access_token returns None, we expect an error from fetch_daily_stress.
    """
    mocker.patch("oura_apiHeart.get_valid_access_token", return_value=None)
    result = oura_apiHeart.fetch_daily_stress("no_token@example.com")
    assert result["error"] == "Missing authentication token"


def test_fetch_daily_stress_existing_last_fetched(fresh_db, fresh_auth_db, mock_token, requests_mock):
    """
    If last_fetched_stress_at exists, fetch_daily_stress should start from last_fetched_stress_at + 1 day
    and update it to the max day from the newly fetched data.
    """
    user_id = "test_stress2@example.com"

    # Suppose the user last fetched up to '2025-02-20'
    last_fetched_str = "2025-02-20"
    conn = sqlite3.connect(oura_apiHeart.AUTH_DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_tokens (user_id, access_token, last_fetched_stress_at)
        VALUES (?, ?, ?)
    """, (user_id, "TEST_TOKEN", last_fetched_str))
    conn.commit()
    conn.close()

    # We'll pretend the Oura API returns 2 new daily records:
    # '2025-02-21' and '2025-02-22'
    stress_data = {
        "data": [
            {
                "day": "2025-02-21",
                "stress_high": 2,
                "recovery_high": 1,
                "day_summary": "normal"
            },
            {
                "day": "2025-02-22",
                "stress_high": 5,
                "recovery_high": 3,
                "day_summary": "stressful"
            }
        ]
    }

    # Use `requests_mock` fixture to mock API response
    requests_mock.get(
        f"{oura_apiHeart.API_BASE_URL}/daily_stress",
        json=stress_data,
        status_code=200
    )

    # Call the function
    result = oura_apiHeart.fetch_daily_stress(user_id)

    # Should return the raw list from the Oura response
    assert isinstance(result, list)
    assert len(result) == 2

    # Check that daily_stress was updated in the DB
    conn = sqlite3.connect(oura_apiHeart.DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT date, stress_high, recovery_high, day_summary "
        "FROM daily_stress WHERE user_id = ? ORDER BY date ASC",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    # We expect 2 new rows
    assert len(rows) == 2
    assert rows[0] == ("2025-02-21", 2, 1, "normal")
    assert rows[1] == ("2025-02-22", 5, 3, "stressful")

    # Also check we updated last_fetched_stress_at to "2025-02-22" (the max day)
    conn = sqlite3.connect(oura_apiHeart.AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT last_fetched_stress_at
        FROM user_tokens
        WHERE user_id = ?
    """, (user_id,))
    updated_fetch_date = cursor.fetchone()[0]
    conn.close()

    assert updated_fetch_date == "2025-02-22", f"Should update to the max day from new data, got {updated_fetch_date}"
