# %%
import base64, requests, schedule, time, json, pytz, logging, os, sys
from requests.exceptions import ConnectionError
from datetime import datetime, timedelta, timezone
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
HEALTH_API_PROVIDER = (os.environ.get("HEALTH_API_PROVIDER") or "fitbit").strip().lower()
assert HEALTH_API_PROVIDER in ["fitbit", "google"], "HEALTH_API_PROVIDER must be either 'fitbit' or 'google'"
FITBIT_API_BASE_URL = "https://api.fitbit.com"
GOOGLE_HEALTH_BASE_URL = os.environ.get("GOOGLE_HEALTH_BASE_URL") or "https://health.googleapis.com"
GOOGLE_HEALTH_API_VERSION = os.environ.get("GOOGLE_HEALTH_API_VERSION") or "v4"
GOOGLE_OAUTH_TOKEN_URL = os.environ.get("GOOGLE_OAUTH_TOKEN_URL") or "https://oauth2.googleapis.com/token"
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
google_client_id = os.environ.get("GOOGLE_CLIENT_ID") or client_id
google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET") or client_secret
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
DRY_RUN_MODE = str(os.environ.get("DRY_RUN_MODE", "False")).lower() in ["true", "1", "yes", "y"]
LOG_LEVEL_NAME = (os.environ.get("LOG_LEVEL") or "DEBUG").strip().upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, None)
if not isinstance(LOG_LEVEL, int):
    print(f"Invalid LOG_LEVEL '{LOG_LEVEL_NAME}'. Falling back to DEBUG.")
    LOG_LEVEL = logging.DEBUG
    LOG_LEVEL_NAME = "DEBUG"

# %% [markdown]
# ## Logging setup

# %%
if OVERWRITE_LOG_FILE:
    with open(FITBIT_LOG_FILE_PATH, "w"): pass

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(FITBIT_LOG_FILE_PATH, mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)
logging.info("Logging level set to %s", LOG_LEVEL_NAME)

# %% [markdown]
# ## Setting up base API Caller function

# %%
def get_default_auth_headers():
    if HEALTH_API_PROVIDER == "fitbit":
        return {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Accept": "application/json",
            "Accept-Language": FITBIT_LANGUAGE
        }
    return {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Accept": "application/json"
    }


def get_retry_after_seconds(response):
    # Fitbit and Google use different rate-limit headers; prefer standard Retry-After first.
    retry_after_header = response.headers.get("Retry-After")
    if retry_after_header:
        try:
            return max(0, int(retry_after_header))
        except ValueError:
            pass

    fitbit_reset_header = response.headers.get("Fitbit-Rate-Limit-Reset")
    if fitbit_reset_header:
        try:
            return max(0, int(fitbit_reset_header)) + 300
        except ValueError:
            pass

    return 120


def get_google_health_api_url(path):
    return f"{GOOGLE_HEALTH_BASE_URL}/{GOOGLE_HEALTH_API_VERSION}/{path.lstrip('/')}"


def request_google_data_points_list(data_type, params=None, suppress_http_error_log=False):
    endpoint = get_google_health_api_url(f"users/me/dataTypes/{data_type}/dataPoints")
    return request_data_from_fitbit(endpoint, params=params or {}, suppress_http_error_log=suppress_http_error_log)


def request_google_data_points_daily_rollup(data_type, payload):
    endpoint = get_google_health_api_url(f"users/me/dataTypes/{data_type}/dataPoints:dailyRollUp")
    headers = get_default_auth_headers()
    headers["Content-Type"] = "application/json"
    return request_data_from_fitbit(endpoint, headers=headers, data=json.dumps(payload), request_type="post")


def request_google_data_points_rollup(data_type, payload):
    endpoint = get_google_health_api_url(f"users/me/dataTypes/{data_type}/dataPoints:rollUp")
    headers = get_default_auth_headers()
    headers["Content-Type"] = "application/json"
    return request_data_from_fitbit(endpoint, headers=headers, data=json.dumps(payload), request_type="post")


def extract_first_numeric(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and all(ch in "+-0123456789.eE" for ch in stripped):
            try:
                return float(stripped)
            except ValueError:
                pass
    if isinstance(value, dict):
        for nested in value.values():
            extracted = extract_first_numeric(nested)
            if extracted is not None:
                return extracted
    if isinstance(value, list):
        for nested in value:
            extracted = extract_first_numeric(nested)
            if extracted is not None:
                return extracted
    return None


def extract_numeric_fields(value, key_filter=None):
    fields = {}
    if not isinstance(value, dict):
        return fields
    for key, nested in value.items():
        if key_filter and key_filter not in key.lower():
            continue
        extracted = extract_first_numeric(nested)
        if extracted is not None:
            fields[key] = extracted
    return fields


def get_google_payload_key(data_type):
    parts = data_type.split("-")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def get_google_datapoint_payload(data_point, data_type):
    payload_key = get_google_payload_key(data_type)
    payload = data_point.get(payload_key)
    if isinstance(payload, dict):
        return payload
    return {}


def convert_google_duration_to_seconds(duration_value):
    if duration_value is None:
        return None
    if isinstance(duration_value, (int, float)):
        return float(duration_value)
    if isinstance(duration_value, str) and duration_value.endswith("s"):
        try:
            return float(duration_value[:-1])
        except ValueError:
            return None
    return None


def get_google_datapoint_date_string(data_point, data_type):
    payload = get_google_datapoint_payload(data_point, data_type)

    if isinstance(payload.get("date"), dict):
        date_value = payload["date"]
        try:
            return f"{int(date_value.get('year')):04d}-{int(date_value.get('month')):02d}-{int(date_value.get('day')):02d}"
        except (TypeError, ValueError):
            pass

    interval = payload.get("interval") if isinstance(payload, dict) else None
    if isinstance(interval, dict):
        civil_start = interval.get("civilStartTime")
        if isinstance(civil_start, dict):
            date_value = civil_start.get("date")
            if isinstance(date_value, dict):
                try:
                    return f"{int(date_value.get('year')):04d}-{int(date_value.get('month')):02d}-{int(date_value.get('day')):02d}"
                except (TypeError, ValueError):
                    pass

    return None


def parse_google_datapoint_timestamp(data_point, data_type=None):
    payload = get_google_datapoint_payload(data_point, data_type) if data_type else {}

    time_candidates = [
        data_point.get("sampleTime"),
        data_point.get("sample_time"),
        data_point.get("time"),
    ]

    if isinstance(payload, dict):
        time_candidates.extend([
            payload.get("sampleTime"),
            payload.get("sample_time"),
            payload.get("time"),
        ])

    sample_time = payload.get("sampleTime") if isinstance(payload, dict) else None
    if isinstance(sample_time, dict):
        time_candidates.extend([
            sample_time.get("physicalTime"),
            sample_time.get("physical_time"),
        ])

    interval = data_point.get("interval")
    if isinstance(interval, dict):
        time_candidates.extend([
            interval.get("startTime"),
            interval.get("start_time"),
            interval.get("civilStartTime"),
            interval.get("civil_start_time"),
        ])

    payload_interval = payload.get("interval") if isinstance(payload, dict) else None
    if isinstance(payload_interval, dict):
        time_candidates.extend([
            payload_interval.get("startTime"),
            payload_interval.get("start_time"),
            payload_interval.get("endTime"),
            payload_interval.get("end_time"),
        ])

    for candidate in time_candidates:
        if isinstance(candidate, str):
            normalized = candidate.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(normalized)
                if dt.tzinfo is None:
                    dt = LOCAL_TIMEZONE.localize(dt)
                return dt.astimezone(pytz.utc).isoformat()
            except ValueError:
                continue

    date_str = get_google_datapoint_date_string(data_point, data_type) if data_type else None
    if date_str:
        dt = LOCAL_TIMEZONE.localize(datetime.strptime(date_str + "T00:00:00", "%Y-%m-%dT%H:%M:%S"))
        return dt.astimezone(pytz.utc).isoformat()

    return None


def get_google_datapoints_for_date(data_type, date_str, page_size=10000):
    start_dt_local = LOCAL_TIMEZONE.localize(datetime.strptime(date_str, "%Y-%m-%d"))
    end_dt_local = start_dt_local + timedelta(days=1)
    start_iso = start_dt_local.astimezone(pytz.utc).isoformat().replace("+00:00", "Z")
    end_iso = end_dt_local.astimezone(pytz.utc).isoformat().replace("+00:00", "Z")

    filter_data_type = data_type.replace("-", "_")
    next_date_str = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    # Data types do not expose a uniform set of filter members.
    if data_type in ["steps"]:
        filters_to_try = [
            f'{filter_data_type}.interval.start_time >= "{start_iso}" AND {filter_data_type}.interval.start_time < "{end_iso}"',
            f'{filter_data_type}.interval.civil_start_time >= "{date_str}T00:00:00" AND {filter_data_type}.interval.civil_start_time < "{next_date_str}T00:00:00"',
        ]
    elif data_type in ["heart-rate", "oxygen-saturation", "weight"]:
        filters_to_try = [
            f'{filter_data_type}.sample_time.physical_time >= "{start_iso}" AND {filter_data_type}.sample_time.physical_time < "{end_iso}"',
        ]
    elif data_type in ["exercise", "sleep"]:
        filters_to_try = [
            f'{filter_data_type}.interval.civil_start_time >= "{date_str}T00:00:00" AND {filter_data_type}.interval.civil_start_time < "{next_date_str}T00:00:00"',
            f'{filter_data_type}.interval.civil_end_time >= "{date_str}T00:00:00" AND {filter_data_type}.interval.civil_end_time < "{next_date_str}T00:00:00"',
        ]
    else:
        # Daily and unsupported data types often reject member-based filters.
        filters_to_try = []

    response = None
    used_server_filter = False
    for filter_expr in filters_to_try:
        try:
            response = request_google_data_points_list(
                data_type,
                params={"pageSize": page_size, "filter": filter_expr},
                suppress_http_error_log=True,
            )
            used_server_filter = True
            break
        except requests.exceptions.HTTPError:
            continue

    if response is None:
        response = request_google_data_points_list(data_type, params={"pageSize": page_size})

    points = response.get("dataPoints", []) if isinstance(response, dict) else []
    filtered = []
    for data_point in points:
        ts = parse_google_datapoint_timestamp(data_point, data_type)
        if not ts:
            continue

        data_point_date = get_google_datapoint_date_string(data_point, data_type)
        if used_server_filter:
            filtered.append((data_point, ts))
            continue

        if data_point_date == date_str:
            filtered.append((data_point, ts))
            continue

        if datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(LOCAL_TIMEZONE).strftime("%Y-%m-%d") == date_str:
            filtered.append((data_point, ts))
    return filtered


def get_google_datapoints_for_date_range(data_type, start_date_str, end_date_str, page_size=10000):
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    aggregated = []
    current = start_date
    while current <= end_date:
        aggregated.extend(get_google_datapoints_for_date(data_type, current.strftime("%Y-%m-%d"), page_size=page_size))
        current += timedelta(days=1)
    return aggregated


# Generic Request caller for all 
def request_data_from_fitbit(url, headers=None, params=None, data=None, request_type="get", suppress_http_error_log=False):
    global ACCESS_TOKEN
    headers = headers or {}
    params = params or {}
    data = data or {}
    retry_attempts = 0
    logging.debug("Requesting data from provider '%s' via URL: %s", HEALTH_API_PROVIDER, url)
    if HEALTH_API_PROVIDER == "google" and url.startswith(FITBIT_API_BASE_URL):
        raise NotImplementedError("Google provider is enabled but this endpoint is still Fitbit-only. Migrate the caller to a Google Health endpoint first.")

    while True: # Unlimited Retry attempts
        if request_type == "get" and headers == {}:
            headers = get_default_auth_headers()
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
                retry_after = get_retry_after_seconds(response)
                logging.warning("API limit reached for provider '%s'. Error code: %s, retrying in %s seconds", HEALTH_API_PROVIDER, response.status_code, retry_after)
                print(f"API limit reached for provider '{HEALTH_API_PROVIDER}'. Error code: {response.status_code}, retrying in {retry_after} seconds")
                time.sleep(retry_after)
            elif response.status_code == 401: # Access token expired ( most likely )
                logging.warning("Error code: %s, provider: %s, details: %s", response.status_code, HEALTH_API_PROVIDER, response.text)
                print(f"Error code: {response.status_code}, provider: {HEALTH_API_PROVIDER}, details: {response.text}")
                ACCESS_TOKEN = Get_New_Access_Token(client_id, client_secret)
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
                if not suppress_http_error_log:
                    logging.error("API request failed for provider '%s'. Status code: %s %s", HEALTH_API_PROVIDER, response.status_code, response.text)
                    print(f"API request failed for provider '{HEALTH_API_PROVIDER}'. Status code: {response.status_code}", response.text)
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
def save_tokens_to_file(access_token, refresh_token, provider, expires_in=None):
    tokens = {
        "provider": provider,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "saved_at_utc": datetime.now(timezone.utc).isoformat()
    }
    if expires_in is not None:
        tokens["expires_in"] = int(expires_in)
    with open(TOKEN_FILE_PATH, "w") as file:
        json.dump(tokens, file)


def refresh_fitbit_tokens(client_id, client_secret, refresh_token):
    logging.info("Attempting to refresh tokens...")
    url = f"{FITBIT_API_BASE_URL}/oauth2/token"
    headers = {
        "Authorization": "Basic " + base64.b64encode((client_id + ":" + client_secret).encode()).decode(),
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    response = requests.post(url, headers=headers, data=data)
    if response.status_code != 200:
        logging.error("Fitbit token refresh failed. Status code: %s details: %s", response.status_code, response.text)
        response.raise_for_status()

    json_data = response.json()
    access_token = json_data["access_token"]
    new_refresh_token = json_data["refresh_token"]
    save_tokens_to_file(access_token, new_refresh_token, "fitbit", json_data.get("expires_in"))
    logging.info("Fitbit token refresh successful!")
    return access_token, new_refresh_token


def refresh_google_tokens(client_id, client_secret, refresh_token):
    logging.info("Attempting to refresh Google Health API tokens...")
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    response = requests.post(GOOGLE_OAUTH_TOKEN_URL, data=data)
    if response.status_code != 200:
        logging.error("Google token refresh failed. Status code: %s details: %s", response.status_code, response.text)
        response.raise_for_status()

    json_data = response.json()
    access_token = json_data["access_token"]
    new_refresh_token = json_data.get("refresh_token", refresh_token)
    save_tokens_to_file(access_token, new_refresh_token, "google", json_data.get("expires_in"))
    logging.info("Google token refresh successful!")
    return access_token, new_refresh_token

def load_tokens_from_file():
    with open(TOKEN_FILE_PATH, "r") as file:
        tokens = json.load(file)
        provider = (tokens.get("provider") or "fitbit").lower()
        return tokens.get("access_token"), tokens.get("refresh_token"), provider


def get_active_credentials(client_id, client_secret):
    if HEALTH_API_PROVIDER == "google":
        return google_client_id, google_client_secret
    return client_id, client_secret

def Get_New_Access_Token(client_id, client_secret):
    active_client_id, active_client_secret = get_active_credentials(client_id, client_secret)
    try:
        access_token, refresh_token, provider_in_file = load_tokens_from_file()
        if provider_in_file != HEALTH_API_PROVIDER:
            logging.warning("Token file provider '%s' does not match HEALTH_API_PROVIDER '%s'.", provider_in_file, HEALTH_API_PROVIDER)
    except FileNotFoundError:
        refresh_token = input(f"No token file found. Please enter a valid {HEALTH_API_PROVIDER} refresh token : ")

    if HEALTH_API_PROVIDER == "fitbit":
        access_token, refresh_token = refresh_fitbit_tokens(active_client_id, active_client_secret, refresh_token)
    elif HEALTH_API_PROVIDER == "google":
        access_token, refresh_token = refresh_google_tokens(active_client_id, active_client_secret, refresh_token)
    else:
        raise ValueError(f"Unsupported provider: {HEALTH_API_PROVIDER}")

    return access_token

ACCESS_TOKEN = Get_New_Access_Token(client_id, client_secret)

# %% [markdown]
# ## Influxdb Database Initialization

# %%
if DRY_RUN_MODE:
    influxdbclient = None
    influxdb_write_api = None
    logging.warning("DRY_RUN_MODE is enabled. InfluxDB initialization and writes are skipped.")
elif INFLUXDB_VERSION == "2":
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
    if DRY_RUN_MODE:
        logging.info("DRY_RUN_MODE: Skipping InfluxDB write for %s points", len(points))
        return

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
def get_user_timezone_name():
    if HEALTH_API_PROVIDER == "fitbit":
        profile_data = request_data_from_fitbit(f"{FITBIT_API_BASE_URL}/1/user/-/profile.json")
        return profile_data["user"]["timezone"]

    settings_data = request_data_from_fitbit(f"{GOOGLE_HEALTH_BASE_URL}/{GOOGLE_HEALTH_API_VERSION}/users/me/settings")
    if isinstance(settings_data, dict):
        for key in ["timezone", "timeZone", "time_zone"]:
            if settings_data.get(key):
                return settings_data.get(key)
        nested_settings = settings_data.get("settings")
        if isinstance(nested_settings, dict):
            for key in ["timezone", "timeZone", "time_zone"]:
                if nested_settings.get(key):
                    return nested_settings.get(key)

    logging.warning("Unable to determine timezone from Google settings response. Falling back to UTC")
    return "UTC"


def discover_google_device_name():
    """Inspect a few popular data types and return the first dataSource.device.displayName
    we can find (e.g. "Versa 4"). Google attaches device metadata to every data point even
    though it does not expose battery telemetry. Returns None if nothing usable is found."""
    for data_type in ("heart-rate", "steps", "daily-resting-heart-rate", "weight", "exercise"):
        try:
            resp = request_google_data_points_list(
                data_type, params={"pageSize": 1}, suppress_http_error_log=True
            )
        except requests.exceptions.HTTPError:
            continue
        if not isinstance(resp, dict):
            continue
        for dp in resp.get("dataPoints", []):
            device = (dp.get("dataSource") or {}).get("device") or {}
            name = device.get("displayName")
            if name:
                return name.strip()
    return None


if LOCAL_TIMEZONE == "Automatic":
    LOCAL_TIMEZONE = pytz.timezone(get_user_timezone_name())
else:
    LOCAL_TIMEZONE = pytz.timezone(LOCAL_TIMEZONE)

# Auto-detect the device name from the Google Health API if the user did not set
# DEVICENAME explicitly. Falls back silently to the placeholder if discovery fails.
if HEALTH_API_PROVIDER == "google" and DEVICENAME == "Your_Device_Name":
    discovered_device_name = discover_google_device_name()
    if discovered_device_name:
        logging.info("Auto-detected Google device displayName: %s (override with DEVICENAME env var)", discovered_device_name)
        DEVICENAME = discovered_device_name
    else:
        logging.info("Could not auto-detect device displayName from Google Health API; keeping default '%s'", DEVICENAME)

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
    if HEALTH_API_PROVIDER == "google":
        logging.warning("Battery level endpoint is not mapped for Google Health API yet. Skipping DeviceBatteryLevel update.")
        return

    device = request_data_from_fitbit(f"{FITBIT_API_BASE_URL}/1/user/-/devices.json")[0]
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
    if HEALTH_API_PROVIDER == "google":
        data_type_mapping = {
            "heart": "heart-rate",
            "steps": "steps"
        }
        for measurement in measurement_list:
            inserted_count = 0
            data_type = data_type_mapping.get(measurement[0])
            if not data_type:
                logging.warning("Google mapping not available for intraday type: %s", measurement[0])
                continue

            try:
                points = get_google_datapoints_for_date(data_type, date_str)
            except requests.exceptions.HTTPError as err:
                logging.error("Google intraday fetch failed for %s on %s: %s", data_type, date_str, str(err))
                continue

            for data_point, ts in points:
                payload = get_google_datapoint_payload(data_point, data_type)
                if data_type == "heart-rate":
                    numeric_value = extract_first_numeric(payload.get("beatsPerMinute"))
                elif data_type == "steps":
                    numeric_value = extract_first_numeric(payload.get("count"))
                else:
                    numeric_value = extract_first_numeric(payload)
                if numeric_value is None:
                    continue

                collected_records.append({
                    "measurement": measurement[1],
                    "time": ts,
                    "tags": {
                        "Device": DEVICENAME
                    },
                    "fields": {
                        "value": int(numeric_value)
                    }
                })
                inserted_count += 1
            logging.info("Recorded %s intraday for date %s (Google mode): %s points", measurement[1], date_str, inserted_count)
        return

    for measurement in measurement_list:
        data = request_data_from_fitbit(f"{FITBIT_API_BASE_URL}/1/user/-/activities/{measurement[0]}/date/{date_str}/1d/{measurement[2]}.json")["activities-" + measurement[0] + "-intraday"]['dataset']
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
    if HEALTH_API_PROVIDER == "google":
        logging.warning("Google mapping for 30-day grouped datasets (HRV/BR/SkinTemp/SPO2 intraday/weight) is not finalized yet. Skipping this batch.")
        return

    hrv_data_list = request_data_from_fitbit(f"{FITBIT_API_BASE_URL}/1/user/-/hrv/date/{start_date_str}/{end_date_str}.json").get('hrv')
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

    try:
        br_response = request_data_from_fitbit(f"{FITBIT_API_BASE_URL}/1/user/-/br/date/{start_date_str}/{end_date_str}.json")
        br_data_list = br_response.get("br") if br_response else None
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 403:
            logging.warning("Skipping BR for date " + start_date_str + " to " + end_date_str + " due to missing permission (HTTP 403)")
            br_data_list = None
        else:
            raise
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

    skin_temp_data_list = request_data_from_fitbit(f"{FITBIT_API_BASE_URL}/1/user/-/temp/skin/date/{start_date_str}/{end_date_str}.json").get("tempSkin")
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
                        "RelativeValue": float(temp_record["value"]["nightlyRelative"])
                    }
                })
        logging.info("Recorded Skin Temperature Variation for date " + start_date_str + " to " + end_date_str)
    else:
        logging.error("Recording failed : Skin Temperature Variation for date " + start_date_str + " to " + end_date_str)

    try:
        spo2_data_list = request_data_from_fitbit(f"{FITBIT_API_BASE_URL}/1/user/-/spo2/date/{start_date_str}/{end_date_str}/all.json")
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

    weight_data_list = request_data_from_fitbit(f"{FITBIT_API_BASE_URL}/1/user/-/body/log/weight/date/{start_date_str}/{end_date_str}.json").get("weight")
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
    if HEALTH_API_PROVIDER == "google":
        logging.warning("Google mapping for sleep detail dataset is not finalized yet. Skipping this batch.")
        return

    sleep_data = request_data_from_fitbit(f"{FITBIT_API_BASE_URL}/1.2/user/-/sleep/date/{start_date_str}/{end_date_str}.json").get("sleep")
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
    if HEALTH_API_PROVIDER == "google":
        logging.warning("Google mapping for long-range activity aggregates is not finalized yet. Skipping this batch.")
        return

    activity_minutes_list = ["minutesSedentary", "minutesLightlyActive", "minutesFairlyActive", "minutesVeryActive"]
    for activity_type in activity_minutes_list:
        activity_minutes_data_list = request_data_from_fitbit(f"{FITBIT_API_BASE_URL}/1/user/-/activities/tracker/{activity_type}/date/{start_date_str}/{end_date_str}.json").get("activities-tracker-"+activity_type)
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
        activity_others_data_list = request_data_from_fitbit(f"{FITBIT_API_BASE_URL}/1/user/-/activities/tracker/{activity_type}/date/{start_date_str}/{end_date_str}.json").get("activities-tracker-"+activity_type)
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
        

    HR_zones_data_list = request_data_from_fitbit(f"{FITBIT_API_BASE_URL}/1/user/-/activities/heart/date/{start_date_str}/{end_date_str}.json").get("activities-heart")
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

    HR_zone_minutes_list = request_data_from_fitbit(f"{FITBIT_API_BASE_URL}/1/user/-/activities/active-zone-minutes/date/{start_date_str}/{end_date_str}.json").get("activities-active-zone-minutes")
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
    if HEALTH_API_PROVIDER == "google":
        try:
            points = get_google_datapoints_for_date_range("daily-oxygen-saturation", start_date_str, end_date_str)
        except requests.exceptions.HTTPError as e:
            logging.error("Google daily oxygen saturation fetch failed: %s", str(e))
            points = []

        if points:
            inserted_count = 0
            for data_point, ts in points:
                spo2_fields = data_point.get("dailyOxygenSaturation", {})
                avg_value = extract_first_numeric(spo2_fields.get("averagePercentage"))
                max_value = extract_first_numeric(spo2_fields.get("upperBoundPercentage"))
                min_value = extract_first_numeric(spo2_fields.get("lowerBoundPercentage"))

                if avg_value is None and max_value is None and min_value is None:
                    fallback_value = extract_first_numeric(spo2_fields)
                    avg_value = fallback_value

                collected_records.append({
                    "measurement": "SPO2",
                    "time": ts,
                    "tags": {
                        "Device": DEVICENAME
                    },
                    "fields": {
                        "avg": avg_value,
                        "max": max_value,
                        "min": min_value
                    }
                })
                inserted_count += 1
            logging.info("Recorded Avg SPO2 for date %s to %s (Google mode): %s points", start_date_str, end_date_str, inserted_count)
        else:
            logging.warning("No daily oxygen saturation records found for date %s to %s in Google mode", start_date_str, end_date_str)
        return

    try:
        data_list = request_data_from_fitbit(f"{FITBIT_API_BASE_URL}/1/user/-/spo2/date/{start_date_str}/{end_date_str}.json")
    except requests.exceptions.HTTPError as e:
        logging.error(f"{e}")
        data_list = None
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
    if HEALTH_API_PROVIDER == "google":
        try:
            points = get_google_datapoints_for_date("exercise", end_date_str, page_size=25)
        except requests.exceptions.HTTPError as err:
            logging.error("Google exercise fetch failed for %s: %s", end_date_str, str(err))
            points = []

        inserted_count = 0
        for data_point, ts in points:
            exercise_payload = data_point.get("exercise", {})
            fields = {}
            metrics_summary = exercise_payload.get("metricsSummary", {}) if isinstance(exercise_payload, dict) else {}

            active_duration_seconds = convert_google_duration_to_seconds(exercise_payload.get("activeDuration"))
            if active_duration_seconds is not None:
                fields["ActiveDuration"] = int(active_duration_seconds)
                fields["duration"] = int(active_duration_seconds)

            average_hr = extract_first_numeric(metrics_summary.get("averageHeartRateBeatsPerMinute"))
            if average_hr is not None:
                fields["AverageHeartRate"] = int(average_hr)

            calories_kcal = extract_first_numeric(metrics_summary.get("caloriesKcal"))
            if calories_kcal is not None:
                fields["calories"] = int(calories_kcal)

            steps_count = extract_first_numeric(metrics_summary.get("steps"))
            if steps_count is not None:
                fields["steps"] = int(steps_count)

            distance_value = extract_first_numeric(metrics_summary.get("distanceMeters"))
            if distance_value is not None:
                fields["distance"] = float(distance_value)

            extracted_activity_name = exercise_payload.get("displayName") or exercise_payload.get("exerciseType") or "Unknown-Activity"
            collected_records.append({
                "measurement": "Activity Records",
                "time": ts,
                "tags": {
                    "ActivityName": extracted_activity_name
                },
                "fields": fields
            })
            inserted_count += 1
        logging.info("Fetched recent exercises for date %s (Google mode): %s points", end_date_str, inserted_count)
        return

    next_end_date_str = (datetime.strptime(end_date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    recent_activities_data = request_data_from_fitbit(f"{FITBIT_API_BASE_URL}/1/user/-/activities/list.json", params={'beforeDate': next_end_date_str, 'sort':'desc', 'limit':50, 'offset':0})
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
        



