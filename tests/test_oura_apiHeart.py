import os
import sys
import pytest
import sqlite3
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import oura_apiHeart
import requests_mock
# try:
#     import main.oura_apiHeart
#     oura_apiHeart = main.oura_apiHeart
# except ModuleNotFoundError as e:
#     print("Import Error: Could not find `main.oura_apiHeart`.")
#     print(f"Debug Info: sys.path = {sys.path}")
#     raise e


@pytest.fixture
def fresh_db(tmp_path):
    """
    Points heart-rate DB_FILE to a temp directory and re-initializes the heart_rate table.
    """
    test_db_path = tmp_path / "heart_rate_test.db"
    oura_apiHeart.DB_FILE = str(test_db_path)
    oura_apiHeart.init_db()
    yield


@pytest.fixture
def fresh_auth_db(tmp_path):
    """
    Points AUTH_DB_FILE to a temp directory and creates a minimal user_tokens table.
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
            last_fetched_at TEXT
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


def test_init_db_structure(fresh_db):
    """
    Verify that the 'heart_rate' table is created properly by init_db().
    """
    conn = sqlite3.connect(oura_apiHeart.DB_FILE)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info('heart_rate')")
    columns = cursor.fetchall()
    conn.close()

    col_names = [col[1] for col in columns]
    # Expect columns: id, user_id, timestamp, bpm, source
    assert "id" in col_names
    assert "user_id" in col_names
    assert "timestamp" in col_names
    assert "bpm" in col_names
    assert "source" in col_names


def test_store_heart_rate_excludes_workout_and_sleep(fresh_db):
    """
    Ensure store_heart_rate excludes entries with source == 'workout' or 'sleep'.
    """
    user_id = "test@example.com"
    now = datetime.now(timezone.utc)

    data = [
        # 1 day old—well within 14 days
        {"timestamp": (now - timedelta(days=1)).isoformat(), "bpm": 60, "source": "rest"},
        {"timestamp": (now - timedelta(days=1, minutes=1)).isoformat(), "bpm": 61, "source": "sleep"},   # excluded
        {"timestamp": (now - timedelta(days=1, minutes=2)).isoformat(), "bpm": 62, "source": "workout"}, # excluded
        {"timestamp": (now - timedelta(days=1, minutes=3)).isoformat(), "bpm": 63, "source": "tag"},
    ]
    oura_apiHeart.store_heart_rate(user_id, data)

    conn = sqlite3.connect(oura_apiHeart.DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, bpm, source FROM heart_rate WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    # Only 'rest' and 'tag' should be stored.
    assert len(rows) == 2


def test_fetch_baseline_heart_rate_no_data(fresh_db):
    """
    fetch_baseline_heart_rate should return None if no data is present.
    """
    baseline = oura_apiHeart.fetch_baseline_heart_rate("newuser@example.com")
    assert baseline is None


def test_fetch_baseline_heart_rate_ok(fresh_db):
    """
    fetch_baseline_heart_rate should return the average BPM in the last 14 days.
    """
    user_id = "test@example.com"
    conn = sqlite3.connect(oura_apiHeart.DB_FILE)
    cursor = conn.cursor()

    now = datetime.now(timezone.utc)
    # Insert some data within the last 14 days
    data_rows = [
        (user_id, (now - timedelta(days=1)).isoformat(), 60, "rest"),
        (user_id, (now - timedelta(days=2)).isoformat(), 80, "tag"),
        # Older than 14 days
        (user_id, (now - timedelta(days=20)).isoformat(), 100, "rest"),
    ]
    cursor.executemany("INSERT INTO heart_rate (user_id, timestamp, bpm, source) VALUES (?, ?, ?, ?)", data_rows)
    conn.commit()
    conn.close()

    baseline = oura_apiHeart.fetch_baseline_heart_rate(user_id)
    # Only 60 and 80 are within 14 days => average 70
    assert baseline == 70.0


def test_cleanup_old_data(fresh_db):
    """
    Confirm cleanup_old_data deletes records older than 14 days.
    """
    user_id = "test@example.com"
    conn = sqlite3.connect(oura_apiHeart.DB_FILE)
    cursor = conn.cursor()

    now = datetime.now(timezone.utc)
    older = (now - timedelta(days=20)).isoformat()
    newer = (now - timedelta(days=1)).isoformat()

    data_rows = [
        (user_id, older, 75, "rest"),  # older
        (user_id, newer, 65, "rest"),  # newer
    ]
    cursor.executemany("INSERT INTO heart_rate (user_id, timestamp, bpm, source) VALUES (?, ?, ?, ?)", data_rows)
    conn.commit()
    conn.close()

    # Call cleanup
    oura_apiHeart.cleanup_old_data()

    conn = sqlite3.connect(oura_apiHeart.DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp FROM heart_rate WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    # Should only keep the record from 1 day ago
    assert len(rows) == 1
    assert rows[0][0] == newer


@pytest.mark.parametrize(
    "mock_status, mock_json_factory, expected_error",
    [
        # 1) Normal 200, some data returned
        (
            200,
            lambda: {
                "data": [
                    {"timestamp": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), "bpm": 65, "source": "rest"},
                    {"timestamp": (datetime.now(timezone.utc) - timedelta(days=1, minutes=10)).isoformat(), "bpm": 70, "source": "workout"},
                    {"timestamp": (datetime.now(timezone.utc) - timedelta(days=1, minutes=20)).isoformat(), "bpm": 68, "source": "sleep"},
                ]
            },
            None
        ),
        # 2) 200 but empty data
        (200, lambda: {"data": []}, "No heart rate data returned from Oura API"),
        # 3) Non-200 error
        (500, lambda: {}, "Failed to fetch heart rate: 500"),
    ]
)
def test_fetch_all_heart_rate(
    fresh_db, mock_token, requests_mock, mock_status, mock_json_factory, expected_error
):
    user_id = "test_all@example.com"
    mock_json = mock_json_factory()

    requests_mock.get(
        f"{oura_apiHeart.API_BASE_URL}/heartrate",
        json=mock_json,
        status_code=mock_status
    )

    result = oura_apiHeart.fetch_all_heart_rate(user_id)

    if expected_error:
        assert result["error"] == expected_error
    else:
        assert isinstance(result, list)
        # Only entries not from workout/sleep are stored/returned
        expected_valid_entries = [
            e for e in mock_json["data"] if e["source"] not in ["workout", "sleep"]
        ]
        assert len(result) == len(expected_valid_entries)

        # Check database
        conn = sqlite3.connect(oura_apiHeart.DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT bpm, source FROM heart_rate WHERE user_id = ?", (user_id,))
        stored_rows = cursor.fetchall()
        conn.close()

        assert len(stored_rows) == len(expected_valid_entries)


def test_fetch_all_heart_rate_missing_token(fresh_db, mocker):
    """
    If get_valid_access_token returns None, we expect an error.
    """
    mocker.patch("oura_apiHeart.get_valid_access_token", return_value=None)
    result = oura_apiHeart.fetch_all_heart_rate("failuser@example.com")
    assert result["error"] == "Missing authentication token"


def test_fetch_recent_heart_rate_missing_token(fresh_db, fresh_auth_db, mocker):
    """
    If get_valid_access_token returns None, we expect an error.
    """
    mocker.patch("oura_apiHeart.get_valid_access_token", return_value=None)
    result = oura_apiHeart.fetch_recent_heart_rate("failuser@example.com")
    assert result["error"] == "Missing authentication token"


def test_fetch_recent_heart_rate_no_last_fetched(
    fresh_db, fresh_auth_db, mock_token, requests_mock
):
    """
    When no last_fetched_at is found, fetch from the last 5 minutes.
    """
    user_id = "test_nolast@example.com"

    # Insert a row for user_tokens, last_fetched_at=None
    conn = sqlite3.connect(oura_apiHeart.AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_tokens (user_id, access_token, last_fetched_at)
        VALUES (?, ?, ?)
    """, (user_id, "TEST_TOKEN", None))
    conn.commit()
    conn.close()

    now_utc = datetime.now(timezone.utc)
    data = [
        {
            "timestamp": (now_utc - timedelta(minutes=3)).isoformat(),
            "bpm": 72,
            "source": "rest"
        },
        {
            "timestamp": (now_utc - timedelta(minutes=4)).isoformat(),
            "bpm": 76,
            "source": "workout"  # excluded
        }
    ]

    requests_mock.get(
        f"{oura_apiHeart.API_BASE_URL}/heartrate",
        json={"data": data},
        status_code=200
    )

    result = oura_apiHeart.fetch_recent_heart_rate(user_id)
    assert isinstance(result, list), "Expected a list of stored data"
    assert len(result) == len(data), "Raw data returned from the function"

    # Only 'rest' is stored in DB
    conn = sqlite3.connect(oura_apiHeart.DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT bpm, source FROM heart_rate WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0] == (72, "rest")

    # Check last_fetched_at got updated in user_tokens
    conn = sqlite3.connect(oura_apiHeart.AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT last_fetched_at FROM user_tokens WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    # Should match the *max* timestamp
    max_ts = max(d["timestamp"] for d in data)
    assert row is not None, "User token row should exist"
    assert row[0] == max_ts


def test_fetch_recent_heart_rate_existing_last_fetched(
    fresh_db, fresh_auth_db, mock_token, requests_mock
):
    """
    If last_fetched_at exists, we fetch from last_fetched_at minus 1s, then update last_fetched_at.
    Using recent timestamps to avoid cleanup_old_data() removing them.
    """
    user_id = "test_last@example.com"

    # Pretend the user last fetched data 2 minutes ago
    last_fetched = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()

    conn = sqlite3.connect(oura_apiHeart.AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_tokens (user_id, access_token, last_fetched_at)
        VALUES (?, ?, ?)
    """, (user_id, "TEST_TOKEN", last_fetched))
    conn.commit()
    conn.close()

    # We'll provide 3 data points: only "rest" should be stored
    now_utc = datetime.now(timezone.utc)
    data = [
        {
            "timestamp": (now_utc - timedelta(minutes=1, seconds=30)).isoformat(),
            "bpm": 65,
            "source": "rest"
        },
        {
            "timestamp": (now_utc - timedelta(minutes=1, seconds=0)).isoformat(),
            "bpm": 70,
            "source": "sleep"
        },
        {
            "timestamp": (now_utc - timedelta(seconds=30)).isoformat(),
            "bpm": 72,
            "source": "workout"
        },
    ]

    requests_mock.get(
        f"{oura_apiHeart.API_BASE_URL}/heartrate",
        json={"data": data},
        status_code=200
    )

    result = oura_apiHeart.fetch_recent_heart_rate(user_id)
    # The function returns ALL raw data from Oura (3 entries)
    assert isinstance(result, list)
    assert len(result) == 3

    # But only 1 (with source 'rest') is actually stored
    conn = sqlite3.connect(oura_apiHeart.DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, bpm, source FROM heart_rate WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 1, f"Expected exactly 1 row, got {len(rows)}"
    # The 'rest' one
    stored_ts, stored_bpm, stored_source = rows[0]
    assert stored_source == "rest"
    assert stored_bpm == 65

    # last_fetched_at updated to the maximum new timestamp
    max_ts = max(entry["timestamp"] for entry in data)
    conn = sqlite3.connect(oura_apiHeart.AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT last_fetched_at FROM user_tokens WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    assert row[0] == max_ts


def test_fetch_recent_heart_rate_no_data_returned(
    fresh_db, fresh_auth_db, mock_token, requests_mock
):
    """
    If the API returns a 200 but with no data, we expect an error dict.
    """
    user_id = "test_nodata@example.com"
    requests_mock.get(
        f"{oura_apiHeart.API_BASE_URL}/heartrate",
        json={"data": []},
        status_code=200
    )

    result = oura_apiHeart.fetch_recent_heart_rate(user_id)
    assert isinstance(result, dict)
    assert "error" in result
    assert result["error"] == "No recent heart rate data returned from Oura API"


def test_fetch_recent_heart_rate_non_200(
    fresh_db, fresh_auth_db, mock_token, requests_mock
):
    """
    If the API returns a non-200, we surface the error code in the result.
    """
    user_id = "test_error@example.com"
    requests_mock.get(
        f"{oura_apiHeart.API_BASE_URL}/heartrate",
        text="Not Found",
        status_code=404
    )

    result = oura_apiHeart.fetch_recent_heart_rate(user_id)
    assert isinstance(result, dict)
    assert result["error"] == "Failed to fetch heart rate: 404"
    assert "details" in result
    assert "Not Found" in result["details"]