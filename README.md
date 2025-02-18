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

should create database and then continually look for new heart index every FETCH_INTERVAL (5 min oura api updates heart  -> put 1 min for testing)


!!! auth.db fully cleaned -> pytest working and pylint clean except whitespace who cares 


for api calls need to call

user_id = session.get("user_id")
access_token = get_valid_access_token(user_id)



testing:
pip install pytest requests-mock
pytest test_auth.py
pytest test_oura_apiHeart.py

for code coverage: (tests both for auth.py and oura_apiHeart.py)
pip install pytest-cov
pytest --cov=oura_apiHeart --cov=auth --cov-report=term-missing


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