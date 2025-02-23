1. In root directory run 

uvicorn main.app:app --host 0.0.0.0 --port 5001 --reload

2. Use curl to get link to login:

in root dir run:

curl -X GET "http://127.0.0.1:5001/auth/login"

3. Check back in terminal that main.app step 1. is running, and open that termporary redirect link 

4. Login with oura link, should try to redirect you to react native frontend (not setup yet)

--> need to fix 1. (last prompt in ch)


curl -X GET "http://127.0.0.1:5001/auth/user-info" -H "Authorization: Bearer <your_access_token>"

can test endpoints in windows to make sure can connect from linux ide and windows emulator android studio:
curl -H "Authorization: Bearer <your_access_token>" "https://api.ouraring.com/v2/usercollection/sleep?start_date=2024-02-15&end_date=2024-02-21"


1.

```bash
python auth.py
```
go to   http://127.0.0.1:5000/login 

login 

dont need to keep this running (stores token)

2.
Start new terminal in root: 
```bash
python -m main.app
```

uvicorn main.app:app --host 0.0.0.0 --port 5001 --reload


should create database and then continually look for new heart index every FETCH_INTERVAL (5 min oura api updates heart  -> put 1 min for testing)


!!! auth.db fully cleaned -> pytest working and pylint clean except whitespace who cares 


for api calls need to call

user_id = session.get("user_id")
access_token = get_valid_access_token(user_id)

!!!!!!!!!!!!!!!
fix last fetched at, not sure if its working



# frontend
npx react-native start

for emulator open android studio:
 ~/android-studio/bin/studio.sh


install for oauth2 handling:
npm install react-native-app-auth react-native-url-polyfill axios




testing:
pip install pytest requests-mock
pytest test_auth.py
pytest test_oura_apiHeart.py

for code coverage: (tests both for auth.py and oura_apiHeart.py)
pip install pytest-cov
pytest --cov=main --cov-report=term-missing

pylint for code qual 
pip install pylint

pylint main.py etc 

.env setup 

sandbox for development, switch to real for prod
API_MODE=development
REAL_API_BASE=https://api.ouraring.com/v2/usercollection
SANDBOX_API_BASE=https://api.ouraring.com/v2/sandbox/usercollection
SANDBOX_ACCESS_TOKEN=your_sandbox_access_token
OPENROUTER_API_KEY=REPLACEHERE
CLIENT_ID=REPLACEHERE
CLIENT_SECRET=REPLACEHERE
REDIRECT_URI=http://127.0.0.1:5000/callback
AUTHORIZATION_URL=https://cloud.ouraring.com/oauth/authorize
TOKEN_URL=https://api.ouraring.com/oauth/token
SECRET_KEY=superduper_ultra_secret_key_derp



Cant use sessions with fastapi like we can in flask, so we need to use bearer tokens with oauth and bearer tokens. our client (react native app) authenticates by sending access tokens un authorization header

TO DO LIST:
-> need to switch from flask to fastapi since its not built for high concurrency, want to switch to fastapi since its asynchronous and flask is not (concurrency issues etc)
-> background task processes -> use celery + redis. Celery for scheduled and real time task execution, and redis as message broker
-> scaling concerns => we should only fetch heart rate data during school hours -> do batch requests outside of school hours / rate limit api calls to avoid Oura rate limit
-> database optimizing: need indexing and partitioning to store large amounts of time series data
-> use worker pools to process heart data instead of looping over users one by one, processes multiple users in parallel -> store last fetch timestamps to avoid redundant calls (do this already -> ensure it works)
-> if user not wearing ring ensure that we do not fetch data for them (not sure how we do this yet)
-> for daily stress data (every 24 hrs) -> scheduled as Celery periodic task running at midnight UTC (ensure that the data gets stored at midnight utc)
-> WE NEED TO MAKE SURE THAT HEART RATE IS EVERY 5 MINUTES !!!!!!!!!!!!!!!! TO GET NOTIFICATIONS AND INFORM THE USER THAT THEY ARE STRESSED AND NEED TO RELAX

-> use gRPC API calls for real time data retrieval 
-> websockets for live updates on heart rate fluctuations 

main.py
 fetch all heart rate, fetch_recent_heart_rate rely on get_valid_access_token from auth.py which is important since every time we fetch we get new or refreshed token if needed (good)
 pull all user ids from user_tokens to poll for all users in system, don't need to rely on users current active session which is good for server side schedule -> read directly from auth.db (improve for scaling though)

 things to improve -> change endpoint /data/real_time_heart_rate/<user_id> since we need user authentication so that only the user can access their own data
  only spawn 1 thread per user, inside each thread this is good if small amount of users, later want to improve since inefficient to spawn a thread for each user and concurrency issues (move away from polling threads and switch to background
job library like celera or rq or maybe possibly even better to use a task queue like redis or rabbitmq)

 make sure to change from 30s to 300s for 5 min from testing, use scheduling to manage intervals gracefully. need to avoid oura rate limits (i think 6000 or smth) and also not overload our server with requests
 add try/except block around entire loop to prevent killing thread in fetch_recent_heart_rate, add logging to see if there are any errors

 the 2 db is an issue -> for now the foreign key does nothing but it works since we call for user_id in both api and auth file, but in future either: combine with attach, make 1 single db file, or switch to postgre sql (best)
 each thread calls fetch_recent_heart_rate which does own db writes, but might lock sqlite since single file and can handle concurrency but will lock if threads write concurrently 

 make HEART_RATE_SPIKE_THRESHOLD_PERCENT = 20 not fixed to 20%, want to make it dynamic for each user (store in db file and update later this value -> implement sleep and stress and other factors)
 if baseline_hr is none we skip detection which isnt good if we want to handle in between states, or seed baseline if user is brand new to oura -> seed with 60 bpm or something

 define school hours but loop doesnt skip or change behavior if not school hours, need to implement that notification is triggered in the loop to check if school hours and then skip if not. now its being unused
 only use while true loop for prod, change to short script, and add logging to see if there are any errors