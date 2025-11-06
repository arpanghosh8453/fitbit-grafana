# %%
import base64, requests, schedule, time, json, pytz, logging, os, sys
from requests.exceptions import ConnectionError
from datetime import datetime, timedelta
# for influxdb 1.x
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError
# for influxdb 2.x
from influxdb_client import InfluxDBClient as InfluxDBClient2
# from influxdb_client.client.exceptions import InfluxDBError # possible duplicate
from influxdb_client.client.write_api import SYNCHRONOUS
# for influxdb 3.x
from influxdb_client_3 import InfluxDBClient3, InfluxDBError
# For XML processing
import xml.etree.ElementTree as ET

# %% [markdown]
# ## Variables

# %%
FITBIT_LOG_FILE_PATH = os.environ.get("FITBIT_LOG_FILE_PATH") or "your/expected/log/file/location/path"
TOKEN_FILE_PATH = os.environ.get("TOKEN_FILE_PATH") or "your/expected/token/file/location/path"
OVERWRITE_LOG_FILE = True
FITBIT_LANGUAGE = 'en_US'
INFLUXDB_VERSION = os.environ.get("INFLUXDB_VERSION") or "1" # Version of influxdb in use, supported values are 1 or 2
assert INFLUXDB_VERSION in ['1','2','3'], "Only InfluxDB version 1 or 2 or 3 is allowed - please put either 1 or 2 or 3"
# Update these variables for influxdb 1.x versions
INFLUXDB_HOST = os.environ.get("INFLUXDB_HOST") or 'localhost' # for influxdb 1.x
INFLUXDB_PORT = os.environ.get("INFLUXDB_PORT") or 8086 # for influxdb 1.x 
INFLUXDB_USERNAME = os.environ.get("INFLUXDB_USERNAME") or 'your_influxdb_username' # for influxdb 1.x
INFLUXDB_PASSWORD = os.environ.get("INFLUXDB_PASSWORD") or 'your_influxdb_password' # for influxdb 1.x
INFLUXDB_DATABASE = os.environ.get("INFLUXDB_DATABASE") or 'your_influxdb_database_name' # for influxdb 1.x
# Update these variables for influxdb 2.x versions
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET") or "your_bucket_name_here" # for influxdb 2.x
INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG") or "your_org_here" # for influxdb 2.x
INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN") or "your_token_here" # for influxdb 2.x
INFLUXDB_URL = os.environ.get("INFLUXDB_URL") or "http://your_url_here:8086" # for influxdb 2.x
INFLUXDB_V3_ACCESS_TOKEN = os.getenv("INFLUXDB_V3_ACCESS_TOKEN",'') # InfluxDB V3 Access token, required only for InfluxDB 3.x
# MAKE SURE you set the application type to PERSONAL. Otherwise, you won't have access to intraday data series, resulting in 40X errors.
client_id = os.environ.get("CLIENT_ID") or "your_application_client_ID" # Change this to your client ID
client_secret = os.environ.get("CLIENT_SECRET") or "your_application_client_secret" # Change this to your client Secret
DEVICENAME = os.environ.get("DEVICENAME") or "Your_Device_Name" # e.g. "Charge5"
ACCESS_TOKEN = "" # Empty Global variable initialization, will be replaced with a functional access code later using the refresh code
MANUAL_START_DATE = os.getenv("MANUAL_START_DATE", None) # optional, in YYYY-MM-DD format, if you want to bulk update only from specific date
MANUAL_END_DATE = os.getenv("MANUAL_END_DATE", datetime.today().strftime('%Y-%m-%d')) # optional, in YYYY-MM-DD format, if you want to bulk update until a specific date
AUTO_DATE_RANGE = False if os.environ.get("AUTO_DATE_RANGE") in ['False','false','FALSE','f','F','no','No','NO','0'] else (not bool(MANUAL_START_DATE)) # Automatically selects date range from todays date and update_date_range variable
auto_update_date_range = 1 # Days to go back from today for AUTO_DATE_RANGE *** DO NOT go above 2 - otherwise may break rate limit ***
LOCAL_TIMEZONE = os.environ.get("LOCAL_TIMEZONE") or "Automatic" # set to "Automatic" for Automatic setup from User profile (if not mentioned here specifically).
SCHEDULE_AUTO_UPDATE = True if AUTO_DATE_RANGE else False # Scheduling updates of data when script runs
SERVER_ERROR_MAX_RETRY = 3
EXPIRED_TOKEN_MAX_RETRY = 5
SKIP_REQUEST_ON_SERVER_ERROR = True

# %% [markdown]
# ## Logging setup

# %%
if OVERWRITE_LOG_FILE:
    with open(FITBIT_LOG_FILE_PATH, "w"): pass

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(FITBIT_LOG_FILE_PATH, mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)

# %% [markdown]
# ## Setting up base API Caller function

# %%
# Generic Request caller for all 
def request_data_from_fitbit(url, headers={}, params={}, data={}, request_type="get"):
    global ACCESS_TOKEN
    retry_attempts = 0
    logging.debug("Requesting data from fitbit via Url : " + url)
    while True: # Unlimited Retry attempts
        if request_type == "get" and headers == {}:
            headers = {
                "Authorization": f"Bearer {ACCESS_TOKEN}",
                "Accept": "application/json",
                'Accept-Language': FITBIT_LANGUAGE
            }
        try:        
            if request_type == "get":
                response = requests.get(url, headers=headers, params=params, data=data)
            elif request_type == "post":
                response = requests.post(url, headers=headers, params=params, data=data)
            else:
                raise Exception("Invalid request type " + str(request_type))
        
            if response.status_code == 200: # Success
                if url.endswith(".tcx"): # TCX XML file for GPS data
                    return response
                else:
                    return response.json()
            elif response.status_code == 429: # API Limit reached
                retry_after = int(response.headers["Fitbit-Rate-Limit-Reset"]) + 300 # Fitbit changed their headers.
                logging.warning("Fitbit API limit reached. Error code : " + str(response.status_code) + ", Retrying in " + str(retry_after) + " seconds")
                print("Fitbit API limit reached. Error code : " + str(response.status_code) + ", Retrying in " + str(retry_after) + " seconds")
                time.sleep(retry_after)
            elif response.status_code == 401: # Access token expired ( most likely )
                logging.info("Current Access Token : " + ACCESS_TOKEN)
                logging.warning("Error code : " + str(response.status_code) + ", Details : " + response.text)
                print("Error code : " + str(response.status_code) + ", Details : " + response.text)
                ACCESS_TOKEN = Get_New_Access_Token(client_id, client_secret)
                logging.info("New Access Token : " + ACCESS_TOKEN)
                headers["Authorization"] = f"Bearer {ACCESS_TOKEN}" # Update the renewed ACCESS_TOKEN to the headers dict
                time.sleep(30)
                if retry_attempts > EXPIRED_TOKEN_MAX_RETRY:
                    logging.error("Unable to solve the 401 Error. Please debug - " + response.text)
                    raise Exception("Unable to solve the 401 Error. Please debug - " + response.text)
            elif response.status_code in [500, 502, 503, 504]: # Fitbit server is down or not responding ( most likely ):
                logging.warning("Server Error encountered ( Code 5xx ): Retrying after 120 seconds....")
                time.sleep(120)
                if retry_attempts > SERVER_ERROR_MAX_RETRY:
                    logging.error("Unable to solve the server Error. Retry limit exceed. Please debug - " + response.text)
                    if SKIP_REQUEST_ON_SERVER_ERROR:
                        logging.warning("Retry limit reached for server error : Skipping request -> " + url)
                        return None
            else:
                logging.error("Fitbit API request failed. Status code: " + str(response.status_code) + " " + str(response.text) )
                print(f"Fitbit API request failed. Status code: {response.status_code}", response.text)
                response.raise_for_status()
                return None

        except ConnectionError as e:
            logging.error("Retrying in 5 minutes - Failed to connect to internet : " + str(e))
            print("Retrying in 5 minutes - Failed to connect to internet : " + str(e))
        retry_attempts += 1
        time.sleep(30)

# %% [markdown]
# ## Token Refresh Management

# %%
def refresh_fitbit_tokens(client_id, client_secret, refresh_token):
    logging.info("Attempting to refresh tokens...")
    url = "https://api.fitbit.com/oauth2/token"
    headers = {
        "Authorization": "Basic " + base64.b64encode((client_id + ":" + client_secret).encode()).decode(),
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    json_data = request_data_from_fitbit(url, headers=headers, data=data, request_type="post")
    access_token = json_data["access_token"]
    new_refresh_token = json_data["refresh_token"]
    tokens = {
        "access_token": access_token,
        "refresh_token": new_refresh_token
    }
    with open(TOKEN_FILE_PATH, "w") as file:
        json.dump(tokens, file)
    logging.info("Fitbit token refresh successful!")
    return access_token, new_refresh_token

def load_tokens_from_file():
    with open(TOKEN_FILE_PATH, "r") as file:
        tokens = json.load(file)
        return tokens.get("access_token"), tokens.get("refresh_token")

def Get_New_Access_Token(client_id, client_secret):
    try:
        access_token, refresh_token = load_tokens_from_file()
    except FileNotFoundError:
        refresh_token = input("No token file found. Please enter a valid refresh token : ")
    access_token, refresh_token = refresh_fitbit_tokens(client_id, client_secret, refresh_token)
    return access_token

ACCESS_TOKEN = Get_New_Access_Token(client_id, client_secret)

# %% [markdown]
# ## Influxdb Database Initialization

# %%
if INFLUXDB_VERSION == "2":
    try:
        influxdbclient = InfluxDBClient2(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        influxdb_write_api = influxdbclient.write_api(write_options=SYNCHRONOUS)
    except InfluxDBError as err:
        logging.error("Unable to connect with influxdb 2.x database! Aborted")
        raise InfluxDBError("InfluxDB connection failed:" + str(err))
elif INFLUXDB_VERSION == "1":
    try:
        influxdbclient = InfluxDBClient(host=INFLUXDB_HOST, port=INFLUXDB_PORT, username=INFLUXDB_USERNAME, password=INFLUXDB_PASSWORD)
        influxdbclient.switch_database(INFLUXDB_DATABASE)
    except InfluxDBClientError as err:
        logging.error("Unable to connect with influxdb 1.x database! Aborted")
        raise InfluxDBClientError("InfluxDB connection failed:" + str(err))
elif INFLUXDB_VERSION == "3":
    try:
        influxdbclient = InfluxDBClient3(
                host=f"http://{INFLUXDB_HOST}:{INFLUXDB_PORT}",
                token=INFLUXDB_V3_ACCESS_TOKEN,
                database=INFLUXDB_DATABASE
                )
        demo_point = {
        'measurement': 'DemoPoint',
        'time': '1970-01-01T00:00:00+00:00',
        'tags': {'DemoTag': 'DemoTagValue'},
        'fields': {'DemoField': 0}
        }
        # The following code block tests the connection by writing/overwriting a demo point. raises error and aborts if connection fails. 
        influxdbclient.write(record=[demo_point])
    except InfluxDBError as err:
        logging.error("Unable to connect with influxdb 3.x database! Aborted")
        raise InfluxDBClientError("InfluxDB connection failed:" + str(err))
else:
    logging.error("No matching version found. Supported values are 1 and 2 and 3")
    raise InfluxDBClientError("No matching version found. Supported values are 1 and 2 and 3")

def write_points_to_influxdb(points):
    if INFLUXDB_VERSION == "2":
        try:
            influxdb_write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=points)
            logging.info("Successfully updated influxdb database with new points")
        except InfluxDBError as err:
            logging.error("Unable to connect with influxdb 2.x database! " + str(err))
            print("Influxdb connection failed! ", str(err))
    elif INFLUXDB_VERSION == "1":
        try:
            influxdbclient.write_points(points)
            logging.info("Successfully updated influxdb database with new points")
        except InfluxDBClientError as err:
            logging.error("Unable to connect with influxdb 1.x database! " + str(err))
            print("Influxdb connection failed! ", str(err))
    elif INFLUXDB_VERSION == "3":
        try:
            influxdbclient.write(record=points)
            logging.info("Successfully updated influxdb database with new points")
        except InfluxDBError as err:
            logging.error("Unable to connect with influxdb 3.x database! " + str(err))
            print("Influxdb connection failed! ", str(err))
    else:
        logging.error("No matching version found. Supported values are 1 and 2 and 3")
        raise InfluxDBClientError("No matching version found. Supported values are 1 and 2 and 3")

# %% [markdown]
# ## Set Timezone from profile data

# %%
if LOCAL_TIMEZONE == "Automatic":
    LOCAL_TIMEZONE = pytz.timezone(request_data_from_fitbit("https://api.fitbit.com/1/user/-/profile.json")["user"]["timezone"])
else:
    LOCAL_TIMEZONE = pytz.timezone(LOCAL_TIMEZONE)

# %% [markdown]
# ## Selecting Dates for update

# %%
if AUTO_DATE_RANGE:
    end_date = datetime.now(LOCAL_TIMEZONE)
    start_date = end_date - timedelta(days=auto_update_date_range)
    end_date_str = end_date.strftime("%Y-%m-%d")
    start_date_str = start_date.strftime("%Y-%m-%d")
else:
    start_date_str = MANUAL_START_DATE or input("Enter start date in YYYY-MM-DD format : ")
    end_date_str = MANUAL_END_DATE or input("Enter end date in YYYY-MM-DD format : ")
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

# %% [markdown]
# ## Setting up functions for Requesting data from server

# %%
collected_records = []

def update_working_dates():
    global end_date, start_date, end_date_str, start_date_str
    end_date = datetime.now(LOCAL_TIMEZONE)
    start_date = end_date - timedelta(days=auto_update_date_range)
    end_date_str = end_date.strftime("%Y-%m-%d")
    start_date_str = start_date.strftime("%Y-%m-%d")

# Get last synced battery level of the device
def get_battery_level():
    device = request_data_from_fitbit("https://api.fitbit.com/1/user/-/devices.json")[0]
    if device != None:
        collected_records.append({
            "measurement": "DeviceBatteryLevel",
            "time": LOCAL_TIMEZONE.localize(datetime.fromisoformat(device['lastSyncTime'])).astimezone(pytz.utc).isoformat(),
            "fields": {
                "value": float(device['batteryLevel'])
            }
        })
        logging.info("Recorded battery level for " + DEVICENAME)
    else:
        logging.error("Recording battery level failed : " + DEVICENAME)

# For intraday detailed data, max possible range in one day. 
def get_intraday_data_limit_1d(date_str, measurement_list):
    for measurement in measurement_list:
        data = request_data_from_fitbit('https://api.fitbit.com/1/user/-/activities/' + measurement[0] + '/date/' + date_str + '/1d/' + measurement[2] + '.json')["activities-" + measurement[0] + "-intraday"]['dataset']
        if data != None:
            for value in data:
                log_time = datetime.fromisoformat(date_str + "T" + value['time'])
                utc_time = LOCAL_TIMEZONE.localize(log_time).astimezone(pytz.utc).isoformat()
                collected_records.append({
                        "measurement":  measurement[1],
                        "time": utc_time,
                        "tags": {
                            "Device": DEVICENAME
                        },
                        "fields": {
                            "value": int(value['value'])
                        }
                    })
            logging.info("Recorded " +  measurement[1] + " intraday for date " + date_str)
        else:
            logging.error("Recording failed : " +  measurement[1] + " intraday for date " + date_str)

# Max range is 30 days, records BR, SPO2 Intraday, skin temp and HRV - 4 queries
def get_daily_data_limit_30d(start_date_str, end_date_str):

    hrv_data_list = request_data_from_fitbit('https://api.fitbit.com/1/user/-/hrv/date/' + start_date_str + '/' + end_date_str + '.json').get('hrv')
    if hrv_data_list != None:
        for data in hrv_data_list:
            log_time = datetime.fromisoformat(data["dateTime"] + "T" + "00:00:00")
            utc_time = LOCAL_TIMEZONE.localize(log_time).astimezone(pytz.utc).isoformat()
            collected_records.append({
                    "measurement":  "HRV",
                    "time": utc_time,
                    "tags": {
                        "Device": DEVICENAME
                    },
                    "fields": {
                        "dailyRmssd": float(data["value"]["dailyRmssd"]) if data["value"]["dailyRmssd"] else None,
                        "deepRmssd": float(data["value"]["deepRmssd"]) if data["value"]["deepRmssd"] else None
                    }
                })
        logging.info("Recorded HRV for date " + start_date_str + " to " + end_date_str)
    else:
        logging.error("Recording failed HRV for date " + start_date_str + " to " + end_date_str)

    br_data_list = request_data_from_fitbit('https://api.fitbit.com/1/user/-/br/date/' + start_date_str + '/' + end_date_str + '.json').get("br")
    if br_data_list != None:
        for data in br_data_list:
            log_time = datetime.fromisoformat(data["dateTime"] + "T" + "00:00:00")
            utc_time = LOCAL_TIMEZONE.localize(log_time).astimezone(pytz.utc).isoformat()
            collected_records.append({
                    "measurement":  "BreathingRate",
                    "time": utc_time,
                    "tags": {
                        "Device": DEVICENAME
                    },
                    "fields": {
                        "value": float(data["value"]["breathingRate"])
                    }
                })
        logging.info("Recorded BR for date " + start_date_str + " to " + end_date_str)
    else:
        logging.warning("Records not found : BR for date " + start_date_str + " to " + end_date_str)

    skin_temp_data_list = request_data_from_fitbit('https://api.fitbit.com/1/user/-/temp/skin/date/' + start_date_str + '/' + end_date_str + '.json').get("tempSkin")
    if skin_temp_data_list != None:
        for temp_record in skin_temp_data_list:
            log_time = datetime.fromisoformat(temp_record["dateTime"] + "T" + "00:00:00")
            utc_time = LOCAL_TIMEZONE.localize(log_time).astimezone(pytz.utc).isoformat()
            collected_records.append({
                    "measurement":  "Skin Temperature Variation",
                    "time": utc_time,
                    "tags": {
                        "Device": DEVICENAME
                    },
                    "fields": {
                        "RelativeValue": temp_record["value"]["nightlyRelative"]
                    }
                })
        logging.info("Recorded Skin Temperature Variation for date " + start_date_str + " to " + end_date_str)
    else:
        logging.error("Recording failed : Skin Temperature Variation for date " + start_date_str + " to " + end_date_str)

    try:
        spo2_data_list = request_data_from_fitbit('https://api.fitbit.com/1/user/-/spo2/date/' + start_date_str + '/' + end_date_str + '/all.json')
    except requests.exceptions.HTTPError as e:
        logging.error(f"{e}")
        spo2_data_list = None
    if spo2_data_list != None:
        for days in spo2_data_list:
            data = days["minutes"]
            for record in data: 
                log_time = datetime.fromisoformat(record["minute"])
                utc_time = LOCAL_TIMEZONE.localize(log_time).astimezone(pytz.utc).isoformat()
                collected_records.append({
                        "measurement":  "SPO2_Intraday",
                        "time": utc_time,
                        "tags": {
                            "Device": DEVICENAME
                        },
                        "fields": {
                            "value": float(record["value"]),
                        }
                    })
        logging.info("Recorded SPO2 intraday for date " + start_date_str + " to " + end_date_str)
    else:
        logging.error("Recording failed : SPO2 intraday for date " + start_date_str + " to " + end_date_str)

    weight_data_list = request_data_from_fitbit('https://api.fitbit.com/1/user/-/body/log/weight/date/' + start_date_str + '/' + end_date_str + '.json').get("weight")
    if weight_data_list != None:
        for entry in weight_data_list:
            log_time = datetime.fromisoformat(entry["date"] + "T" + entry["time"])
            utc_time = LOCAL_TIMEZONE.localize(log_time).astimezone(pytz.utc).isoformat()
            collected_records.append({
                "measurement":  "weight",
                "time": utc_time,
                "tags": {
                    "Device": DEVICENAME
                },
                "fields": {
                    "value": float(entry["weight"]),
                }
            })
            collected_records.append({
                "measurement":  "bmi",
                "time": utc_time,
                "tags": {
                    "Device": DEVICENAME
                },
                "fields": {
                    "value": float(entry["bmi"]),
                }
            })
        logging.info("Recorded weight and BMI for date " + start_date_str + " to " + end_date_str)
    else:
        logging.error("Recording failed : weight and BMI for date " + start_date_str + " to " + end_date_str)

# Only for sleep data - limit 100 days - 1 query
def get_daily_data_limit_100d(start_date_str, end_date_str):

    sleep_data = request_data_from_fitbit('https://api.fitbit.com/1.2/user/-/sleep/date/' + start_date_str + '/' + end_date_str + '.json').get("sleep")
    if sleep_data != None:
        for record in sleep_data:
            log_time = datetime.fromisoformat(record["startTime"])
            utc_time = LOCAL_TIMEZONE.localize(log_time).astimezone(pytz.utc).isoformat()
            try:
                minutesLight= record['levels']['summary']['light']['minutes']
                minutesREM = record['levels']['summary']['rem']['minutes']
                minutesDeep = record['levels']['summary']['deep']['minutes']
            except:
                minutesLight= record['levels']['summary']['asleep']['minutes']
                minutesREM = record['levels']['summary']['restless']['minutes']
                minutesDeep = 0

            collected_records.append({
                    "measurement":  "Sleep Summary",
                    "time": utc_time,
                    "tags": {
                        "Device": DEVICENAME,
                        "isMainSleep": record["isMainSleep"],
                    },
                    "fields": {
                        'efficiency': record["efficiency"],
                        'minutesAfterWakeup': record['minutesAfterWakeup'],
                        'minutesAsleep': record['minutesAsleep'],
                        'minutesToFallAsleep': record['minutesToFallAsleep'],
                        'minutesInBed': record['timeInBed'],
                        'minutesAwake': record['minutesAwake'],
                        'minutesLight': minutesLight,
                        'minutesREM': minutesREM,
                        'minutesDeep': minutesDeep
                    }
                })
            
            sleep_level_mapping = {'wake': 3, 'rem': 2, 'light': 1, 'deep': 0, 'asleep': 1, 'restless': 2, 'awake': 3, 'unknown': 4}
            for sleep_stage in record['levels']['data']:
                log_time = datetime.fromisoformat(sleep_stage["dateTime"])
                utc_time = LOCAL_TIMEZONE.localize(log_time).astimezone(pytz.utc).isoformat()
                collected_records.append({
                        "measurement":  "Sleep Levels",
                        "time": utc_time,
                        "tags": {
                            "Device": DEVICENAME,
                            "isMainSleep": record["isMainSleep"],
                        },
                        "fields": {
                            'level': sleep_level_mapping[sleep_stage["level"]],
                            'duration_seconds': sleep_stage["seconds"]
                        }
                    })
            wake_time = datetime.fromisoformat(record["endTime"])
            utc_wake_time = LOCAL_TIMEZONE.localize(wake_time).astimezone(pytz.utc).isoformat()
            collected_records.append({
                        "measurement":  "Sleep Levels",
                        "time": utc_wake_time,
                        "tags": {
                            "Device": DEVICENAME,
                            "isMainSleep": record["isMainSleep"],
                        },
                        "fields": {
                            'level': sleep_level_mapping['wake'],
                            'duration_seconds': None
                        }
                    })
        logging.info("Recorded Sleep data for date " + start_date_str + " to " + end_date_str)
    else:
        logging.error("Recording failed : Sleep data for date " + start_date_str + " to " + end_date_str)

# Max date range 1 year, records HR zones, Activity minutes and Resting HR - 4 + 3 + 1 + 1 = 9 queries
def get_daily_data_limit_365d(start_date_str, end_date_str):
    activity_minutes_list = ["minutesSedentary", "minutesLightlyActive", "minutesFairlyActive", "minutesVeryActive"]
    for activity_type in activity_minutes_list:
        activity_minutes_data_list = request_data_from_fitbit('https://api.fitbit.com/1/user/-/activities/tracker/' + activity_type + '/date/' + start_date_str + '/' + end_date_str + '.json').get("activities-tracker-"+activity_type)
        if activity_minutes_data_list != None:
            for data in activity_minutes_data_list:
                log_time = datetime.fromisoformat(data["dateTime"] + "T" + "00:00:00")
                utc_time = LOCAL_TIMEZONE.localize(log_time).astimezone(pytz.utc).isoformat()
                collected_records.append({
                        "measurement": "Activity Minutes",
                        "time": utc_time,
                        "tags": {
                            "Device": DEVICENAME
                        },
                        "fields": {
                            activity_type : int(data["value"])
                        }
                    })
            logging.info("Recorded " + activity_type + "for date " + start_date_str + " to " + end_date_str)
        else:
            logging.error("Recording failed : " + activity_type + " for date " + start_date_str + " to " + end_date_str)
        

    activity_others_list = ["distance", "calories", "steps"]
    for activity_type in activity_others_list:
        activity_others_data_list = request_data_from_fitbit('https://api.fitbit.com/1/user/-/activities/tracker/' + activity_type + '/date/' + start_date_str + '/' + end_date_str + '.json').get("activities-tracker-"+activity_type)
        if activity_others_data_list != None:
            for data in activity_others_data_list:
                log_time = datetime.fromisoformat(data["dateTime"] + "T" + "00:00:00")
                utc_time = LOCAL_TIMEZONE.localize(log_time).astimezone(pytz.utc).isoformat()
                activity_name = "Total Steps" if activity_type == "steps" else activity_type
                collected_records.append({
                        "measurement": activity_name,
                        "time": utc_time,
                        "tags": {
                            "Device": DEVICENAME
                        },
                        "fields": {
                            "value" : float(data["value"])
                        }
                    })
            logging.info("Recorded " + activity_name + " for date " + start_date_str + " to " + end_date_str)
        else:
            logging.error("Recording failed : " + activity_name + " for date " + start_date_str + " to " + end_date_str)
        

    HR_zones_data_list = request_data_from_fitbit('https://api.fitbit.com/1/user/-/activities/heart/date/' + start_date_str + '/' + end_date_str + '.json').get("activities-heart")
    if HR_zones_data_list != None:
        for data in HR_zones_data_list:
            log_time = datetime.fromisoformat(data["dateTime"] + "T" + "00:00:00")
            utc_time = LOCAL_TIMEZONE.localize(log_time).astimezone(pytz.utc).isoformat()
            collected_records.append({
                    "measurement": "HR zones",
                    "time": utc_time,
                    "tags": {
                        "Device": DEVICENAME
                    },
                    # Using get() method with a default value 0 to prevent keyerror ( see issue #31)
                    "fields": {
                        "Normal" : data["value"]["heartRateZones"][0].get("minutes", 0),
                        "Fat Burn" :  data["value"]["heartRateZones"][1].get("minutes", 0),
                        "Cardio" :  data["value"]["heartRateZones"][2].get("minutes", 0),
                        "Peak" :  data["value"]["heartRateZones"][3].get("minutes", 0)
                    }
                })
            if "restingHeartRate" in data["value"]:
                collected_records.append({
                            "measurement":  "RestingHR",
                            "time": utc_time,
                            "tags": {
                                "Device": DEVICENAME
                            },
                            "fields": {
                                "value": data["value"]["restingHeartRate"]
                            }
                        })
        logging.info("Recorded RHR and HR zones for date " + start_date_str + " to " + end_date_str)
    else:
        logging.error("Recording failed : RHR and HR zones for date " + start_date_str + " to " + end_date_str)

    HR_zone_minutes_list = request_data_from_fitbit('https://api.fitbit.com/1/user/-/activities/active-zone-minutes/date/' + start_date_str + '/' + end_date_str + '.json').get("activities-active-zone-minutes")
    if HR_zone_minutes_list != None:
        for data in HR_zone_minutes_list:
            log_time = datetime.fromisoformat(data["dateTime"] + "T" + "00:00:00")
            utc_time = LOCAL_TIMEZONE.localize(log_time).astimezone(pytz.utc).isoformat()
            if data.get("value"):
                collected_records.append({
                        "measurement": "HR zones",
                        "time": utc_time,
                        "tags": {
                            "Device": DEVICENAME
                        },
                        "fields": data["value"]
                    })
        logging.info("Recorded HR zone minutes for date " + start_date_str + " to " + end_date_str)
    else:
        logging.error("Recording failed : HR zone minutes for date " + start_date_str + " to " + end_date_str)

# records SPO2 single days for the whole given period - 1 query
def get_daily_data_limit_none(start_date_str, end_date_str):
    data_list = request_data_from_fitbit('https://api.fitbit.com/1/user/-/spo2/date/' + start_date_str + '/' + end_date_str + '.json')
    if data_list != None:
        for data in data_list:
            log_time = datetime.fromisoformat(data["dateTime"] + "T" + "00:00:00")
            utc_time = LOCAL_TIMEZONE.localize(log_time).astimezone(pytz.utc).isoformat()
            collected_records.append({
                    "measurement":  "SPO2",
                    "time": utc_time,
                    "tags": {
                        "Device": DEVICENAME
                    },
                    "fields": {
                        "avg": float(data["value"]["avg"]) if data["value"]["avg"] else None,
                        "max": float(data["value"]["max"]) if data["value"]["max"] else None,
                        "min": float(data["value"]["min"]) if data["value"]["min"] else None
                    }
                })
        logging.info("Recorded Avg SPO2 for date " + start_date_str + " to " + end_date_str)
    else:
        logging.error("Recording failed : Avg SPO2 for date " + start_date_str + " to " + end_date_str)

# fetches TCX GPS data
def get_tcx_data(tcx_url, ActivityID):
    tcx_headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Accept": "application/x-www-form-urlencoded"
    }
    tcx_params = {
            'includePartialTCX': 'false'
        }
    response = request_data_from_fitbit(tcx_url, headers=tcx_headers, params=tcx_params)
    if response.status_code != 200:
        logging.error(f"Error fetching TCX file: {response.status_code}, {response.text}")
    else:
        root = ET.fromstring(response.text)
        namespace = {"ns": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}
        trackpoints = root.findall(".//ns:Trackpoint", namespace)
        prev_time = None
        prev_distance = None
        
        for i, trkpt in enumerate(trackpoints):
            time_elem = trkpt.find("ns:Time", namespace)
            lat = trkpt.find(".//ns:LatitudeDegrees", namespace)
            lon = trkpt.find(".//ns:LongitudeDegrees", namespace)
            altitude = trkpt.find("ns:AltitudeMeters", namespace)
            distance = trkpt.find("ns:DistanceMeters", namespace)
            heart_rate = trkpt.find(".//ns:HeartRateBpm/ns:Value", namespace)

            if time_elem is not None and lat is not None:
                current_time = datetime.fromisoformat(time_elem.text.strip("Z"))
                fields = {
                    "lat": float(lat.text),
                    "lon": float(lon.text)
                }
                if altitude is not None:
                    fields["altitude"] = float(altitude.text)
                if distance is not None:
                    fields["distance"] = float(distance.text)
                    current_distance = float(distance.text)
                else:
                    current_distance = None
                if heart_rate is not None:
                    fields["heart_rate"] = int(heart_rate.text)
                if i > 0 and prev_time is not None and prev_distance is not None and current_distance is not None:
                    time_diff = (current_time - prev_time).total_seconds()
                    distance_diff = current_distance - prev_distance
                    if time_diff > 0:
                        speed_mps = distance_diff / time_diff
                        speed_kph = speed_mps * 3.6
                        fields["speed_kph"] = speed_kph
                prev_time = current_time
                prev_distance = current_distance
                
                collected_records.append({
                        "measurement": "GPS",
                        "tags": {
                            "ActivityID": ActivityID
                        },
                        "time": datetime.fromisoformat(time_elem.text.strip("Z")).astimezone(pytz.utc).isoformat(),
                        "fields": fields
                    })

# Fetches latest activities from record ( upto last 50 )
def fetch_latest_activities(end_date_str):
    next_end_date_str = (datetime.strptime(end_date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    recent_activities_data = request_data_from_fitbit('https://api.fitbit.com/1/user/-/activities/list.json', params={'beforeDate': next_end_date_str, 'sort':'desc', 'limit':50, 'offset':0})
    TCX_record_count, TCX_record_limit = 0,10
    if recent_activities_data != None:
        for activity in recent_activities_data['activities']:
            fields = {}
            if 'activeDuration' in activity:
                fields['ActiveDuration'] = int(activity['activeDuration'])
            if 'averageHeartRate' in activity:
                fields['AverageHeartRate'] = int(activity['averageHeartRate'])
            if 'calories' in activity:
                fields['calories'] = int(activity['calories'])
            if 'duration' in activity:
                fields['duration'] = int(activity['duration'])
            if 'distance' in activity:
                fields['distance'] = float(activity['distance'])
            if 'steps' in activity:
                fields['steps'] = int(activity['steps'])
            starttime = datetime.fromisoformat(activity['startTime'].strip("Z"))
            utc_time = starttime.astimezone(pytz.utc).isoformat()
            try:
                extracted_activity_name = activity['activityName']
            except KeyError as MissingKeyError:
                extracted_activity_name = "Unknown-Activity"
            ActivityID = utc_time + "-" + extracted_activity_name
            collected_records.append({
                "measurement": "Activity Records",
                "time": utc_time,
                "tags": {
                    "ActivityName": extracted_activity_name
                },
                "fields": fields
            })
            if activity.get("hasGps", False):
                tcx_link = activity.get("tcxLink", False)
                if tcx_link and TCX_record_count <= TCX_record_limit:
                    TCX_record_count += 1
                    try:
                        get_tcx_data(tcx_link, ActivityID)
                        logging.info("Recorded TCX GPS data for " + tcx_link)
                    except Exception as tcx_exception:
                        logging.error("Failed to get GPS Data for " + tcx_link + " : " + str(tcx_exception))
        logging.info("Fetched 50 recent activities before date " + end_date_str)
    else:
        logging.error("Fetching 50 recent activities failed : before date " + end_date_str)


# %% [markdown]
# ## Call the functions one time as a startup update OR do switch to bulk update mode

# %%
if AUTO_DATE_RANGE:
    date_list = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((end_date - start_date).days + 1)]
    if len(date_list) > 3:
        logging.warn("Auto schedule update is not meant for more than 3 days at a time, please consider lowering the auto_update_date_range variable to aviod rate limit hit!")
    for date_str in date_list:
        get_intraday_data_limit_1d(date_str, [('heart','HeartRate_Intraday','1sec'),('steps','Steps_Intraday','1min')]) # 2 queries x number of dates ( default 2)
    get_daily_data_limit_30d(start_date_str, end_date_str) # 3 queries
    get_daily_data_limit_100d(start_date_str, end_date_str) # 1 query
    get_daily_data_limit_365d(start_date_str, end_date_str) # 8 queries
    get_daily_data_limit_none(start_date_str, end_date_str) # 1 query
    get_battery_level() # 1 query
    fetch_latest_activities(end_date_str) # 1 query
    write_points_to_influxdb(collected_records)
    collected_records = []
else:
    # Do Bulk update----------------------------------------------------------------------------------------------------------------------------

    schedule.every(1).hours.do(lambda : Get_New_Access_Token(client_id,client_secret)) # Auto-refresh tokens every 1 hour
    
    date_list = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((end_date - start_date).days + 1)]

    def yield_dates_with_gap(date_list, gap):
        start_index = -1*gap
        while start_index < len(date_list)-1:
            start_index  = start_index + gap
            end_index = start_index+gap
            if end_index > len(date_list) - 1:
                end_index = len(date_list) - 1
            if start_index > len(date_list) - 1:
                break
            yield (date_list[start_index],date_list[end_index])

    def do_bulk_update(funcname, start_date, end_date):
        global collected_records
        funcname(start_date, end_date)
        schedule.run_pending()
        write_points_to_influxdb(collected_records)
        collected_records = []

    fetch_latest_activities(date_list[-1])
    write_points_to_influxdb(collected_records)
    do_bulk_update(get_daily_data_limit_none, date_list[0], date_list[-1])
    for date_range in yield_dates_with_gap(date_list, 360):
        do_bulk_update(get_daily_data_limit_365d, date_range[0], date_range[1])
    for date_range in yield_dates_with_gap(date_list, 98):
        do_bulk_update(get_daily_data_limit_100d, date_range[0], date_range[1])
    for date_range in yield_dates_with_gap(date_list, 28):
        do_bulk_update(get_daily_data_limit_30d, date_range[0], date_range[1])
    for single_day in date_list:
        do_bulk_update(get_intraday_data_limit_1d, single_day, [('heart','HeartRate_Intraday','1sec'),('steps','Steps_Intraday','1min')])

    logging.info("Success : Bulk update complete for " + start_date_str + " to " + end_date_str)
    print("Bulk update complete!")

# %% [markdown]
# ## Schedule functions at specific intervals (Ongoing continuous update)

# %%
# Ongoing continuous update of data
if SCHEDULE_AUTO_UPDATE:
    
    schedule.every(1).hours.do(lambda : Get_New_Access_Token(client_id,client_secret)) # Auto-refresh tokens every 1 hour
    schedule.every(3).minutes.do( lambda : get_intraday_data_limit_1d(end_date_str, [('heart','HeartRate_Intraday','1sec'),('steps','Steps_Intraday','1min')] )) # Auto-refresh detailed HR and steps
    schedule.every(1).hours.do( lambda : get_intraday_data_limit_1d((datetime.strptime(end_date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d"), [('heart','HeartRate_Intraday','1sec'),('steps','Steps_Intraday','1min')] )) # Refilling any missing data on previous day end of night due to fitbit sync delay ( see issue #10 )
    schedule.every(20).minutes.do(get_battery_level) # Auto-refresh battery level
    schedule.every(3).hours.do(lambda : get_daily_data_limit_30d(start_date_str, end_date_str))
    schedule.every(4).hours.do(lambda : get_daily_data_limit_100d(start_date_str, end_date_str))
    schedule.every(6).hours.do( lambda : get_daily_data_limit_365d(start_date_str, end_date_str))
    schedule.every(6).hours.do(lambda : get_daily_data_limit_none(start_date_str, end_date_str))
    schedule.every(1).hours.do( lambda : fetch_latest_activities(end_date_str))

    while True:
        schedule.run_pending()
        if len(collected_records) != 0:
            write_points_to_influxdb(collected_records)
            collected_records = []
        time.sleep(30)
        update_working_dates()
        



