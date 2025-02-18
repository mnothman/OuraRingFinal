"""
This module defines a Flask app that fetches and monitors real-time heart rate data from Oura.
It calculates baselines, identifies stress alerts, and exposes an endpoint for the latest HR data.
"""

import os
import time
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
import pytz

from flask import Flask, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# Paths & DB Setup
DB_DIR = os.path.join(os.path.dirname(__file__), "..", "databases")
AUTH_DB_FILE = os.path.join(DB_DIR, "auth.db")
DB_FILE = os.path.join(DB_DIR, "heart_rate.db")

os.makedirs(DB_DIR, exist_ok=True)

# Constants
HEART_RATE_SPIKE_THRESHOLD_PERCENT = 20  # Percent above baseline to trigger "stress" alert
FETCH_INTERVAL = 300  # 5 minutes in seconds
BASELINE_HEART_DAYS = 14  # For rolling HR baseline over last 14 days
BASELINE_STRESS_DAYS = 29  # For rolling stress baseline over last 29 days

# School hour definitions (currently unused) -> implement later
SCHOOL_HOURS = [(9, 0, 12, 30), (13, 0, 17, 0)]
LUNCH_BREAK = (12, 30, 13, 0)


def get_dynamic_heartrate_baseline(user_id):
    """
    Calculate the rolling baseline HR from the last 14 days for a given user.
    
    :param user_id: The user's unique identifier (e.g., email).
    :return: Float representing the average BPM, or None if no data yet.
    """
    with sqlite3.connect(DB_FILE) as db_conn:
        db_cursor = db_conn.cursor()
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=BASELINE_HEART_DAYS)).isoformat()
        db_cursor.execute(
            "SELECT bpm FROM heart_rate WHERE user_id = ? AND timestamp >= ?",
            (user_id, cutoff_date),
        )
        heart_rates = [row[0] for row in db_cursor.fetchall()]

    if not heart_rates:
        print(f"No baseline HR data available for {user_id}.")
        return None

    baseline_hr = sum(heart_rates) / len(heart_rates)
    print(f"New Generated Baseline HR for {user_id}: {baseline_hr:.2f}")
    return baseline_hr


def get_dynamic_stress_baseline(user_id):
    """
    Calculates the average 'stress_high' over the last BASELINE_STRESS_DAYS days
    for a given user.
    """
    with sqlite3.connect(DB_FILE) as db_conn:
        db_cursor = db_conn.cursor()

        # Compare the date in 'daily_stress' (YYYY-MM-DD) to cutoff
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=BASELINE_STRESS_DAYS))
        # Convert to YYYY-MM-DD for easier comparison
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")

        db_cursor.execute(
            """
            SELECT stress_high FROM daily_stress
            WHERE user_id = ?
              AND date >= ?
            """,
            (user_id, cutoff_str),
        )
        stress_entries = [row[0] for row in db_cursor.fetchall()]

    if not stress_entries:
        print(f"No baseline stress data available for {user_id}.")
        return None

    average_stress = sum(stress_entries) / len(stress_entries)
    print(f"New Generated Stress Baseline for {user_id}: {average_stress:.2f}")
    return average_stress


def is_school_hour():
    """
    Check if the current time is within SCHOOL_HOURS, excluding lunch.
    (Currently unused in this code, but kept for future logic.)

    :return: True if now is within SCHOOL_HOURS; otherwise False.
    """
    user_timezone = pytz.timezone("America/Los_Angeles")
    now_local = datetime.now(timezone.utc).astimezone(user_timezone)
    current_hour, current_minute = now_local.hour, now_local.minute

    for start_h, start_m, end_h, end_m in SCHOOL_HOURS:
        if (start_h, start_m) <= (current_hour, current_minute) < (end_h, end_m):
            return True
    return False


def poll_oura_heart_rate(user_id):
    """
    Continuously fetch recent Oura heart-rate data for a single user at intervals.
    If the new HR is 20% above the rolling baseline, print a "stress alert."

    :param user_id: The user for whom we are fetching HR data.
    """
    from .oura_apiHeart import fetch_recent_heart_rate  # Late import to avoid circular dependency

    print(f"Starting heart-rate monitoring for user {user_id}...")

    while True:
        print(f"\n⏳ Fetching recent heart-rate data for user: {user_id}")
        heart_rate_data = fetch_recent_heart_rate(user_id)

        # If there's an error, wait and retry
        if isinstance(heart_rate_data, dict) and "error" in heart_rate_data:
            print(f"Error fetching recent HR for {user_id}: {heart_rate_data['error']}")
            time.sleep(FETCH_INTERVAL)
            continue

        print(f"📊 Retrieved {len(heart_rate_data)} new HR records for {user_id}.")

        # Calculate rolling baseline
        baseline_hr = get_dynamic_heartrate_baseline(user_id)
        if not baseline_hr:
            print(f"Skipping stress detection; no baseline HR yet for {user_id}.")
            time.sleep(FETCH_INTERVAL)
            continue

        # Check for stress threshold
        threshold = baseline_hr * (1 + (HEART_RATE_SPIKE_THRESHOLD_PERCENT / 100.0))
        for entry in heart_rate_data:
            recent_bpm = entry["bpm"]
            timestamp = entry["timestamp"]
            if recent_bpm > threshold:
                print(
                    f"Stress Alert! HR {recent_bpm} BPM at {timestamp} exceeds "
                    f"{HEART_RATE_SPIKE_THRESHOLD_PERCENT}% threshold of {baseline_hr:.2f} BPM"
                )

        time.sleep(FETCH_INTERVAL)


def poll_oura_daily_stress(user_id):
    """
    Periodically fetch daily stress data from Oura for a single user.
    This runs, for instance, every 24 hours (or a smaller interval if you prefer).
    """
    from .oura_apiHeart import fetch_daily_stress  # Must come after the daily_stress logic

    print(f"Starting daily-stress monitoring for user {user_id}...")

    STRESS_FETCH_INTERVAL = 12 * 60 * 60  # 12 hours in seconds

    while True:
        print(f"\n Fetching daily-stress data for user: {user_id}")
        stress_data = fetch_daily_stress(user_id)

        if isinstance(stress_data, dict) and "error" in stress_data:
            print(f"Error fetching daily stress for {user_id}: {stress_data['error']}")
        else:
            print(f"Fetched or updated {len(stress_data)} daily stress records for {user_id}.")

        time.sleep(STRESS_FETCH_INTERVAL)  # Wait this time before fetching again -> change to cron later


@app.route("/data/real_time_heart_rate/<user_id>")
def get_real_time_heart_rate(user_id):
    """
    Return the latest heart-rate entry for the given user.
    
    :param user_id: The user to query in the heart_rate table.
    :return: JSON with {bpm, timestamp} or an error if not found.
    """
    with sqlite3.connect(DB_FILE) as db_conn:
        db_cursor = db_conn.cursor()
        db_cursor.execute(
            "SELECT bpm, timestamp FROM heart_rate WHERE user_id = ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (user_id,),
        )

        row = db_cursor.fetchone()

    if row:
        return jsonify({"bpm": row[0], "timestamp": row[1]})
    return jsonify({"error": f"No heart-rate data available for {user_id}"}), 404


@app.route("/data/stress_baseline/<user_id>")
def get_stress_baseline_endpoint(user_id):
    """
    Returns the rolling daily stress baseline for the last BASELINE_STRESS_DAYS days.
    """
    baseline_stress = get_dynamic_stress_baseline(user_id)
    if baseline_stress is None:
        return jsonify({"error": f"No daily stress data for user: {user_id}"}), 404

    return jsonify({
        "user_id": user_id,
        "days_used": BASELINE_STRESS_DAYS,
        "stress_baseline": baseline_stress
    })

@app.route("/data/daily_stress/<user_id>")
def get_daily_stress_records(user_id):
    """
    Returns all daily_stress entries for a user (e.g., last 30 days).
    """
    with sqlite3.connect(DB_FILE) as db_conn:
        db_cursor = db_conn.cursor()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        db_cursor.execute(
            """
            SELECT date, stress_high, recovery_high, day_summary
            FROM daily_stress
            WHERE user_id = ?
              AND date >= ?
            ORDER BY date DESC
            """,
            (user_id, cutoff),
        )
        rows = db_cursor.fetchall()

    if not rows:
        return jsonify({"error": f"No daily stress data found for {user_id}"}), 404

    # Format data into list of dicts
    stress_records = []
    for (date_str, stress_high, recovery_high, day_summary) in rows:
        stress_records.append({
            "date": date_str,
            "stress_high": stress_high,
            "recovery_high": recovery_high,
            "day_summary": day_summary
        })

    return jsonify({
        "user_id": user_id,
        "records": stress_records
    })

if __name__ == "__main__":
    # Only run the pollers once the Flask server is started (and not on debug reload).
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        print("Checking if 14-day HR data already exists...")
        print(f"Checking user tokens in {AUTH_DB_FILE}...")

        with sqlite3.connect(AUTH_DB_FILE) as auth_conn:
            auth_cursor = auth_conn.cursor()
            auth_cursor.execute("SELECT user_id FROM user_tokens")
            active_users = [row[0] for row in auth_cursor.fetchall()]

        if not active_users:
            print("No active users found. Skipping HR data fetch.")
        else:
            # pylint: disable=import-outside-toplevel
            from .oura_apiHeart import fetch_all_heart_rate  # Late import avoid circular dependency

            for uid in active_users:
                with sqlite3.connect(DB_FILE) as hr_conn:
                    hr_cursor = hr_conn.cursor()
                    hr_cursor.execute(
                        "SELECT COUNT(*) FROM heart_rate WHERE user_id = ?",
                        (uid,),
                    )
                    record_count = hr_cursor.fetchone()[0]

                if record_count == 0:
                    print(f"Fetching initial HR data for user {uid}...")
                    fetch_all_heart_rate(uid)
                else:
                    print(f"14 day HR data already exists for user {uid}. Skipping fetch.")

                fetch_thread = threading.Thread(
                    target=poll_oura_heart_rate,
                    args=(uid,),
                    daemon=True
                )
                fetch_thread.start()

                # Spin up thread to fetch daily stress data
                # Fetches daily due to -> poll_oura_daily_stress
                stress_thread = threading.Thread(
                    target=poll_oura_daily_stress,
                    args=(uid,),
                    daemon=True
                )
                stress_thread.start()

    app.run(debug=True, port=5001)
