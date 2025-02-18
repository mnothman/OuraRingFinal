"""
Module for handling Oura API heart rate data.
Includes functions to store, clean, and fetch heart rate records.
"""

import os
import sqlite3
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from main.auth import get_valid_access_token

# Load environment variables
load_dotenv()

# Database configurations
DB_DIR = os.path.join(os.path.dirname(__file__), "..", "databases")
DB_FILE = os.path.join(DB_DIR, "heart_rate.db")
AUTH_DB_FILE = os.path.join(DB_DIR, "auth.db")

# Ensure `/databases/` folder exists
os.makedirs(DB_DIR, exist_ok=True)

# API configuration
API_MODE = os.getenv("API_MODE")
API_BASE_URL = os.getenv("REAL_API_BASE")

# Constants
SCHOOL_HOURS = [(9, 0, 12, 30), (13, 0, 17, 0)]
BASELINE_DAYS = 14
STRESS_DAYS = 29

def init_db():
    """
    Initializes the database table for storing heart rate data.
    Ensures the table exists before operations are performed.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS heart_rate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            bpm INTEGER NOT NULL,
            source TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES user_tokens(user_id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_stress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL UNIQUE,
            stress_high INTEGER,
            recovery_high INTEGER,
            day_summary TEXT,
            FOREIGN KEY (user_id) REFERENCES user_tokens(user_id)
        )
        """
    )

    conn.commit()
    conn.close()

# Ensure table is created before running any API operations
init_db()


def fetch_baseline_heart_rate(user_id):
    """
    Retrieves the rolling 14-day baseline heart rate for a given user.

    Args:
        user_id (str): The user identifier (email).
    
    Returns:
        float | None: The average BPM over the past 14 days, or None if no data exists.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=BASELINE_DAYS)).isoformat()
    cursor.execute("SELECT bpm FROM heart_rate WHERE user_id = ? AND timestamp >= ?", (user_id, cutoff_date))

    heart_rates = [row[0] for row in cursor.fetchall()]
    conn.close()

    return sum(heart_rates) / len(heart_rates) if heart_rates else None


def store_heart_rate(user_id, data):
    """
    Stores new heart rate entries for a user, filtering out workout and sleep data.

    Args:
        user_id (str): The user identifier.
        data (list): A list of dictionaries containing heart rate data.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    inserted_count = 0
    for entry in data:
        if entry["source"] not in ["workout", "sleep"]:
            cursor.execute(
                "INSERT INTO heart_rate (user_id, timestamp, bpm, source) VALUES (?, ?, ?, ?)",
                (user_id, entry["timestamp"], entry["bpm"], entry["source"]),
            )
            inserted_count += 1

    conn.commit()
    conn.close()
    cleanup_old_data()

    print(f"{inserted_count} new HR records added to 'heart_rate' for user: {user_id}")


def fetch_daily_stress(user_id):
    """
    Fetches daily stress data from the last known fetch date until 'today'.
    If none is known, fetches the last 29 days.
    """
    access_token = get_valid_access_token(user_id)
    if not access_token:
        return {"error": "Missing authentication token"}

    # Read last_fetched_stress_at from user_tokens
    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT last_fetched_stress_at FROM user_tokens
        WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()

    last_fetched_stress_at = row[0] if row else None

    # Determine date range
    if last_fetched_stress_at:
        # Convert to datetime.date
        last_date = datetime.fromisoformat(last_fetched_stress_at).date()
        # Start from last_date + 1 day (avoid partial overlap)
        start_date = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"Using last_fetched_stress_at: {last_fetched_stress_at} (fetching from {start_date} onward)")
    else:
        # First time: fetch the last 29 days
        earliest_dt = datetime.now(timezone.utc) - timedelta(days=STRESS_DAYS)
        start_date = earliest_dt.strftime("%Y-%m-%d")
        print("No last_fetched_stress_at found; fetching last 29 days")

    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Make Oura API request
    url = f"{API_BASE_URL}/daily_stress"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"start_date": start_date, "end_date": end_date}

    print(f"Fetching stress data from {start_date} to {end_date} for user {user_id}")
    response = requests.get(url, headers=headers, params=params, timeout=10)

    if response.status_code != 200:
        return {"error": f"Failed to fetch stress data: {response.status_code}",
                "details": response.text}

    data = response.json().get("data", [])
    if not data:
        return {"error": "No stress data returned from Oura API"}

    print(f"Retrieved {len(data)} stress records from Oura for {user_id}")
    for entry in data:
        print(f"Stress day: {entry['day']} - High: {entry['stress_high']} "
              f"Recovery: {entry['recovery_high']} - Summary: {entry['day_summary']}")

    # Store in DB
    store_daily_stress(user_id, data)

    # Update last_fetched_stress_at with the max "day" from data
    # The Oura day is a string YYYY-MM-DD, so let's find the max date
    max_day = max(record["day"] for record in data)  # e.g. "2025-02-27"
    print(f"Updating last_fetched_stress_at to {max_day} for user {user_id}")

    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE user_tokens
        SET last_fetched_stress_at = ?
        WHERE user_id = ?
    """, (max_day, user_id))
    conn.commit()
    conn.close()

    print(f"Stored {len(data)} daily stress records for {user_id}")
    return data


def store_daily_stress(user_id, data):
    """
    Stores daily stress data into the database, ignoring duplicates for the same date.

    Args:
        user_id (str): The user identifier.
        data (list): A list of stress records from Oura API.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    inserted_count = 0
    for entry in data:
        try:
            cursor.execute(
                """
                INSERT OR IGNORE INTO daily_stress (user_id, date, stress_high, recovery_high, day_summary)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, entry["day"], entry["stress_high"], entry["recovery_high"], entry["day_summary"]),
            )
            inserted_count += 1
        except sqlite3.IntegrityError:
            print(f"Skipping duplicate entry for {entry['day']}")

    conn.commit()
    conn.close()

    print(f"Stored {inserted_count} new stress records for user {user_id}")


def cleanup_old_data():
    """
    Removes heart rate records older than the defined `BASELINE_DAYS` (14 days).
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=BASELINE_DAYS)).isoformat()
    cursor.execute("DELETE FROM heart_rate WHERE timestamp < ?", (cutoff_date,))
    conn.commit()
    conn.close()

def fetch_all_heart_rate(user_id):
    """
    Fetches and stores the last 14 days of heart rate data from the Oura API.

    Args:
        user_id (str): The user identifier.

    Returns:
        dict | list: Returns a dictionary with an error message if authentication fails.
                     Otherwise, returns a list of heart rate records.
    """
    access_token = get_valid_access_token(user_id)
    if not access_token:
        return {"error": "Missing authentication token"}

    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{API_BASE_URL}/heartrate"

    start_datetime = (datetime.now(timezone.utc) - timedelta(days=BASELINE_DAYS)).isoformat()
    end_datetime = datetime.now(timezone.utc).isoformat()
    params = {"start_datetime": start_datetime, "end_datetime": end_datetime}

    print(f"Fetching heart rate from {start_datetime} to {end_datetime} for user {user_id}")

    response = requests.get(url, headers=headers, params=params, timeout=10)

    # Explicitly handle non-200 responses
    if response.status_code != 200:
        return {
            "error": f"Failed to fetch heart rate: {response.status_code}",
            "details": response.text
        }

    # Ensure the response contains valid JSON before proceeding
    try:
        data = response.json().get("data", [])
    except ValueError:
        return {"error": "Invalid JSON response from Oura API"}

    if not data:
        return {"error": "No heart rate data returned from Oura API"}

    # Filter out unwanted sources (workout, sleep)
    filtered_data = [entry for entry in data if entry["source"] not in ["workout", "sleep"]]
    store_heart_rate(user_id, filtered_data)

    print(f"Retrieved {len(filtered_data)} valid HR records from Oura for {user_id}")

    if filtered_data:
        latest_ts = max(entry["timestamp"] for entry in filtered_data)
        with sqlite3.connect(AUTH_DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE user_tokens
                SET last_fetched_at = ?
                WHERE user_id = ?
            """, (latest_ts, user_id))
            conn.commit()
        print(f"Set last_fetched_at to {latest_ts} for {user_id}.")

    return filtered_data


def fetch_recent_heart_rate(user_id):
    """
    Fetches new heart rate data since the user's last fetched timestamp, with a 1-second overlap.
    Falls back to the last 5 minutes if no last timestamp is found.
    """
    # Get or refresh the user’s access token
    access_token = get_valid_access_token(user_id)
    if not access_token:
        return {"error": "Missing authentication token"}

    # Retrieve last_fetched_at from user_tokens
    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT last_fetched_at FROM user_tokens WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    # If last_fetched_at is NULL, ignore empty strings to prevent errors for timestamp conversion
    last_fetched_at = row[0] if row and row[0] else None

    if last_fetched_at:
        # Overlap by 1 second
        start_time = datetime.fromisoformat(last_fetched_at) - timedelta(seconds=1)
        print(f"Using last_fetched_at: {last_fetched_at} (minus 1s overlap)")
    else:
        # First time: fetch the last 5 minutes
        start_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        print("No last_fetched_at found; fetching last 5 minutes")

    end_time = datetime.now(timezone.utc)

    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{API_BASE_URL}/heartrate"

    params = {
        "start_datetime": start_time.isoformat(),
        "end_datetime": end_time.isoformat()
    }

    print(f"Fetching heart rate from {start_time} to {end_time} for user {user_id}")

    response = requests.get(url, headers=headers, params=params, timeout=10)
    if response.status_code == 200:
        data = response.json().get("data", [])
        if not data:
            print(f"No new heart rate data available for {user_id}. Not updating last_fetched_at.")
            return {"error": "No recent heart rate data returned from Oura API"}

        # Store new HR data
        store_heart_rate(user_id, data)

        # Update last_fetched_at with the max timestamp from the new data
        latest_ts = max(entry["timestamp"] for entry in data)
        print(f"Updating last_fetched_at to {latest_ts} for user {user_id}")

        conn = sqlite3.connect(AUTH_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_tokens
            SET last_fetched_at = ?
            WHERE user_id = ?
        """, (latest_ts, user_id))
        conn.commit()
        conn.close()

        print(f"Stored {len(data)} new HR records for {user_id}")
        return data

    return {"error": f"Failed to fetch heart rate: {response.status_code}", "details": response.text}