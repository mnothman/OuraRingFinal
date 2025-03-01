"""
This module defines a FastAPI app that fetches and monitors real-time heart rate data from Oura.
It calculates baselines, identifies stress alerts, and exposes endpoints for heart rate data.
Production-ready: uses OAuth2 tokens, background tasks, and Uvicorn server.
"""

import os
import sqlite3
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import uvicorn
import pytz
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from flask_cors import CORS

from auth import router as auth_router
from oura_apiHeart import router as heart_router

from dotenv import load_dotenv
from auth import get_user_id_from_token, get_valid_access_token
from oura_apiHeart import (
    fetch_recent_heart_rate,
    fetch_daily_stress_internal,
)

# Load environment variables from .env
load_dotenv()

# Directories & Databases
DB_DIR = os.path.join(os.path.dirname(__file__), "..", "databases")
AUTH_DB_FILE = os.path.join(DB_DIR, "auth.db")
DB_FILE = os.path.join(DB_DIR, "heart_rate.db")
os.makedirs(DB_DIR, exist_ok=True)

# Constants
HEART_RATE_SPIKE_THRESHOLD_PERCENT = 20  # Percent above baseline to trigger "stress" alert
FETCH_INTERVAL = 300  # 5 minutes in seconds
STRESS_FETCH_INTERVAL = 12 * 60 * 60  # 12 hours in seconds
BASELINE_HEART_DAYS = 14
BASELINE_STRESS_DAYS = 29
SCHOOL_HOURS = [(9, 0, 12, 30), (13, 0, 17, 0)]  # Unused, but preserved
LUNCH_BREAK = (12, 30, 13, 0)                  # Unused, but preserved

#  Startup Tasks
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    On startup, check for existing user tokens and start background pollers
    for heart-rate and daily-stress data.
    """
    print("Checking user tokens in", AUTH_DB_FILE)

    if not os.path.exists(AUTH_DB_FILE):
        print("No auth.db found. No tokens => no pollers.")
        yield
        return

    conn = sqlite3.connect(AUTH_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM user_tokens")
    active_users = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not active_users:
        print("No active users found. Skipping pollers.")
        yield
        return

    # If user has no HR data, fetch initial
    from oura_apiHeart import fetch_all_heart_rate_internal

    for uid in active_users:
        # Check if user already has HR data, if not then fetch HR data for user
        with sqlite3.connect(DB_FILE) as hr_conn:
            hr_cursor = hr_conn.cursor()
            hr_cursor.execute("SELECT COUNT(*) FROM heart_rate WHERE user_id = ?", (uid,))
            record_count = hr_cursor.fetchone()[0]

        if record_count == 0:
            print(f"Fetching initial HR data for user {uid}")
            fetch_all_heart_rate_internal(uid)
        else:
            print(f"14-day HR data already exists for user {uid}. Skipping initial fetch.")

        # Spin up background tasks for each user
        asyncio.create_task(poll_oura_heart_rate(uid))
        asyncio.create_task(poll_oura_daily_stress(uid))
        yield

# Create the FastAPI app
app = FastAPI(
    title="Oura Monitoring App",
    description="A production-grade FastAPI app to handle Oura OAuth, heart-rate polling, and daily stress data.",
    version="1.0.0",
    lifespan=lifespan,
)

# origins = [
#     "http://localhost:3000",      # Expo Web (Browser Testing)
#     "exp://127.0.0.1:19000",      # Expo Go on Localhost
#     "http://10.0.2.2:3000",       # Android Emulator (Metro Bundler)
#     "http://192.168.X.X:3000",    # Real device -> not running
#     "yourapp://oauth-callback",   # Custom deep link for OAuth login
# ]

# origins = [
#     "http://localhost:3000",
#     "exp://127.0.0.1:19000",
#     "exp://10.0.0.47:8081",     # Add your Metro URL
#     "http://10.0.0.47:5001",
#     "http://10.0.0.47:8081",    # Add your Metro URL
#     "http://10.0.2.2:3000",
#     "yourapp://oauth-callback"
# ]

origins = [
    "http://localhost:3000",
    "exp://127.0.0.1:19000",
    "http://10.0.2.2:3000",
    "http://10.0.0.47:8081",     # Your FastAPI server URL
    "exp://10.0.0.47:19000",     # Add your Expo development URL
    "http://10.0.0.47:5001",     # Your FastAPI server URL
    "exp://10.0.0.47:19000/--/auth/callback",  # Add your callback URL
    "http://10.0.0.47:5001/auth/callback",     # Add your callback URL
    "https://b33a-2601-207-380-fb60-d023-11f-59af-4505.ngrok-free.app/auth/callback",
    "https://b33a-2601-207-380-fb60-d023-11f-59af-4505.ngrok-free.app",
    "yourapp://oauth-callback",
]

# CORS: allow React Native frontend to call API (modify security later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,   # In production use frontend domain here
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth")
app.include_router(heart_router, prefix="/oura")


def is_school_hour() -> bool:
    """
    Check if now is in SCHOOL_HOURS, excluding lunch. 
    (Unused, but left for future expansions.)
    """
    user_timezone = pytz.timezone("America/Los_Angeles")
    now_local = datetime.now(timezone.utc).astimezone(user_timezone)
    current_hour, current_minute = now_local.hour, now_local.minute

    for start_h, start_m, end_h, end_m in SCHOOL_HOURS:
        if (start_h, start_m) <= (current_hour, current_minute) < (end_h, end_m):
            return True
    return False

# Dynamic Baselines Helper Functions
def get_dynamic_heartrate_baseline(user_id: str) -> Optional[float]:
    """
    Calculate the rolling 14-day baseline HR for a user.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=BASELINE_HEART_DAYS)).isoformat()
    cursor.execute(
        "SELECT bpm FROM heart_rate WHERE user_id = ? AND timestamp >= ?",
        (user_id, cutoff_date),
    )
    heart_rates = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not heart_rates:
        return None

    baseline_hr = sum(heart_rates) / len(heart_rates)
    return baseline_hr


def get_dynamic_stress_baseline(user_id: str) -> Optional[float]:
    """
    Calculates the average 'stress_high' over the last BASELINE_STRESS_DAYS days.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=BASELINE_STRESS_DAYS))
    cutoff_str = cutoff_date.strftime("%Y-%m-%d")

    cursor.execute(
        """
        SELECT stress_high FROM daily_stress
        WHERE user_id = ?
          AND date >= ?
        """,
        (user_id, cutoff_str),
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return None

    stress_values = [r[0] for r in rows]
    print(f"New Generated Stress Baseline for {user_id}: {stress_values:.2f}")
    return sum(stress_values) / len(stress_values)

# Background Tasks
async def poll_oura_heart_rate(user_id: str):
    """
    Continuously fetch new Oura heart-rate data for the user at intervals.
    If new HR is 20% above the rolling baseline, print "stress alert."
    """
    while True:
        print(f"\nPolling heart rate for user {user_id}")
        hr_data = fetch_recent_heart_rate(user_id)
        if isinstance(hr_data, dict) and "error" in hr_data:
            print(f"Error fetching HR for {user_id}: {hr_data['error']}")
            await asyncio.sleep(FETCH_INTERVAL)
            continue

        if not hr_data:
            print(f"No new HR data found for {user_id}.")
            await asyncio.sleep(FETCH_INTERVAL)
            continue

        baseline_hr = get_dynamic_heartrate_baseline(user_id)
        if baseline_hr:
            threshold = baseline_hr * (1 + HEART_RATE_SPIKE_THRESHOLD_PERCENT / 100.0)
            for entry in hr_data:
                if entry["bpm"] > threshold:
                    print(
                        # uncomment this later when fixed. prints too much currently
                        # f"Stress Alert! HR {entry['bpm']} BPM (threshold {threshold:.1f}) "
                        # f"for user {user_id} at {entry['timestamp']}"
                    )
        else:
            print(f"No baseline HR for user {user_id}, skipping stress detection.")

        await asyncio.sleep(FETCH_INTERVAL)


async def poll_oura_daily_stress(user_id: str):
    """
    Periodically fetch daily stress data from Oura for the user.
    Ensures we only fetch new data.
    """
    while True:
        print(f"\nPolling daily stress for {user_id}")

        # Get last_fetched_stress_at from DB
        conn = sqlite3.connect(AUTH_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT last_fetched_stress_at FROM user_tokens WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()

        last_fetched_stress_at = row[0] if row and row[0] else None

        # Determine the start date for fetching
        if last_fetched_stress_at:
            start_date = (datetime.fromisoformat(last_fetched_stress_at) + timedelta(days=1)).strftime("%Y-%m-%d")
            print(f"Using last_fetched_stress_at: {last_fetched_stress_at} (fetching from {start_date} onward)")
        else:
            start_date = (datetime.now(timezone.utc) - timedelta(days=BASELINE_STRESS_DAYS)).strftime("%Y-%m-%d")
            print(f"No last_fetched_stress_at found; fetching last {BASELINE_STRESS_DAYS} days")

        # Fetch new stress data
        new_data = fetch_daily_stress_internal(user_id, start_date=start_date)

        if new_data is None:
            print(f"No new stress data found for {user_id}. Skipping update.")
        else:
            print(f"Retrieved {len(new_data)} new daily stress records for {user_id}")

        await asyncio.sleep(STRESS_FETCH_INTERVAL)  # Wait before fetching again


# Fast API endpoints
@app.get("/data/stress_baseline")
def get_stress_baseline_endpoint(authorization: str):
    """
    Return the rolling daily stress baseline for the last 29 days.
    The user is identified by their Bearer token in 'authorization'.
    """
    user_id = get_user_id_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    baseline_stress = get_dynamic_stress_baseline(user_id)
    if baseline_stress is None:
        raise HTTPException(status_code=404, detail="No daily stress data found")

    return {
        "user_id": user_id,
        "days_used": BASELINE_STRESS_DAYS,
        "stress_baseline": baseline_stress
    }


@app.get("/data/real_time_heart_rate")
def get_real_time_heart_rate(authorization: str):
    """
    Return the latest heart-rate entry for a user identified by 'authorization' Bearer token.
    """
    user_id = get_user_id_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    with sqlite3.connect(DB_FILE) as db_conn:
        db_cursor = db_conn.cursor()
        db_cursor.execute(
            """
            SELECT bpm, timestamp FROM heart_rate
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = db_cursor.fetchone()

    if row:
        return {"bpm": row[0], "timestamp": row[1]}
    raise HTTPException(status_code=404, detail=f"No heart-rate data found for user {user_id}")


@app.get("/")
def root():
    """
    Root endpoint
    """
    return {"message": "Welcome to the Oura Monitoring FastAPI app!"}

