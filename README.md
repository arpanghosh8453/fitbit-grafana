<p align="center">
<img src="./extra/Fitbit_dashboard.png" width="500" height="160" align="center">
</p>

# Fitbit Fetch script and Influxdb Grafana integration

A script to fetch data from Fitbit servers using their API and store the data in a local influxdb database.

## Dashboard Example

![Dashboard](https://github.com/arpanghosh8453/public-fitbit-projects/blob/main/Grafana_Dashboard/Dashboard.png?raw=true)

## Features

- Automatic data collection from Fitbit API
- Support for both InfluxDB 1.x and 2.x (limited support for 2.x)
- Collects comprehensive health metrics including:
  - Heart Rate Data (including intraday)
  - Hourly steps Heatmap
  - Daily Step Count
  - Sleep Data and patterns
  - Sleep regularity heatmap
  - SpO2 Data
  - Breathing Rate
  - HRV
  - Activity Minutes
  - Device Battery Level
  - And more...
- Automated token refresh
- Historical data backfilling
- Rate limit aware data collection

✅ Available Influxdb database measurements and schema is available [here](extra/influxdb_schema.md)

## Install with Docker (Recommended)

1. Follow this [guide](https://dev.fitbit.com/build/reference/web-api/developer-guide/getting-started/) to create an application. ❗ **The Fitbit `Oauth 2.0 Application Type` selection must be `personal` for intraday data access** ❗- Otherwise you might encounter `KeyError: 'activities-heart-intraday'` when fetching intraday Heart rate or steps data.

![image](https://github.com/user-attachments/assets/323884a6-8154-477b-811b-6e75b90f53f8)

2. `Default Access Type` should be `Read Only`. For the Privacy Policy and TOS URLs, you can enter any valid URL links. Those won't be checked or verified as long as they are valid URLs. The `Redirect URL` could be anything that does not redirect to any existing page/service (as the redirected page url will contain some tokens), I suggest using a dummy `http://localhost:8888` or `http://localhost:8000`. This process will give you a `client ID`, `client secret`, and then you must follow the Oauth 2.0 Tutorial link (marked with `2` above) to receive the required `refresh token` for the setup (see step `5`)

3. Create a folder named `fitbit-fetch-data`, cd into the folder, create a `compose.yml` file with the content of the given compose example below ( Change the enviornment variables accordingly )

4. Create two folders named `logs` and `tokens` inside and make sure to chown them for uid `1000` as the docker container runs the scripts as user uid `1000` ( otherwise you may get read/write permission denied errors )

Note: If you are planning to use Influxdb V3, you need to enter the admin access token in `INFLUXDB_V3_ACCESS_TOKEN`. To generate the admin token you should run `docker exec influxdb influxdb3 create token --admin` command. This will give you the admin token which you must update to `INFLUXDB_V3_ACCESS_TOKEN` ENV variable. You can do this only once and the token can't be viewed or retrieved ever again (influxdb only stores a hash of it in the database for comparison). So please store this token carefully.

5. Initial set up of Access and Refresh tokens with the command : `docker pull thisisarpanghosh/fitbit-fetch-data:latest && docker compose run --rm fitbit-fetch-data` as this will save the initial access and refresh token pair to local storage inside the mapped `tokens` directory. Enter the refresh token you obtained from your fitbit account and hit enter when prompted. Exit out with `ctrl + c` after you see the **successful api requests** in the stdout log. This will automatically remove the orphan running container

6. Finally run : `docker compose up -d` ( to launch the full stack in detached mode ). Thereafter you should check the logs with `docker compose logs --follow` to see any potential error from the containers. This will help you debug the issue, if there is any (specially read/write permission issues)

7. Now you can check out the `localhost:3000` to reach Grafana, do the initial setup, add the influxdb as a datasource (the influxdb address should be `http://influxdb:8086` as they are part of the same network stack, and username should be `fitbit_user` with the password `fitbit_password` for the database name `FitbitHealthStats` if you are using the default settings from the compose file.). Test the connection to make sure the influxdb is up and rechable (you are good to go if it finds the measurements when you test the connection)

8. To use the Grafana dashboard, please use the [JSON files](https://github.com/arpanghosh8453/public-fitbit-projects/tree/main/Grafana_Dashboard) downloaded directly from the Grafana_Dashboard of the project (there are separate versions of the dashboard for influxdb v1 and v2) or use the import code **23088** (for influxdb-v1) or **23090** (for influxdb-v2) to pull them directly from the Grafana dashboard cloud.

9. In the Grafana dashboard, the heatmap panels require an additional plugin you must install. This can be done by using the `GF_PLUGINS_PREINSTALL=marcusolsson-hourly-heatmap-panel` environment variable like in the [compose.yml](./compose.yml) file, or after the creation of the container with docker commands. Just run `docker exec -it grafana grafana cli plugins install marcusolsson-hourly-heatmap-panel` and then run `docker restart grafana` to apply that plugin update. Now, you should be able to see the Heatmap panels on the dashboard loading successfully.

---

This project is tested and optimized for InfluxDB 1.11, and using the same version is strongly recommended. Using InfluxDB 2.x may result in a less detailed dashboard as it's developed by other contributers and due to its sole reliance on Flux queries, which can be problematic to use with Grafana at times. In fact, InfluxQL is being reintroduced in InfluxDB 3.0, reflecting user feedback. Grafana also has better compatibility/stability with InfluxQL from InfluxDB 1.11. 

Since InfluxDB 2.x offers no clear benefits for this project, there are no plans for a full migration. While support for InfluxDB 2.x exists for this project and has been tested by others, same visual experience cannot be guaranteed on Grafana dashboard designed for influxdb 2.x.

Example `compose.yml` file contents for influxdb 1.11 is given here for a quick start. If you prefer using influxdb 2.x and accept the limited Grafana dashboard, please refer to the [`compose.yml `](./compose.yml) file and update the `ENV` vriables accordingly. 

Support of current [Influxdb 3](https://docs.influxdata.com/influxdb3/core/) OSS is also available with this project [ `Exprimental` ]

> [!IMPORTANT]
> Please note that InfluxDB 3.x OSS limits the query time limit to 72 hours. This can be extended more by setting `INFLUXDB3_QUERY_FILE_LIMIT` to a very high value with a potential risk of crashing the container (OOM Error). As we are interested in visualization long term data trends, this limit defeats the purpose. Hence, we strongly recommend using InfluxDB 1.11.x (default settings) to our users as long as it's not discontinued from production. 

```yaml
services:
  fitbit-fetch-data:
    restart: unless-stopped
    image: thisisarpanghosh/fitbit-fetch-data:latest
    container_name: fitbit-fetch-data
    volumes:
      - ./logs:/app/logs
      - ./tokens:/app/tokens
      - /etc/timezone:/etc/timezone:ro
    environment:
      - FITBIT_LOG_FILE_PATH=/app/logs/fitbit.log
      - TOKEN_FILE_PATH=/app/tokens/fitbit.token
      - AUTO_DATE_RANGE=True # Used for bulk update, read Historical Data Update section in README
      - INFLUXDB_VERSION=1
      - INFLUXDB_HOST=influxdb
      - INFLUXDB_PORT=8086
      - INFLUXDB_USERNAME=fitbit_user
      - INFLUXDB_PASSWORD=fitbit_password
      - INFLUXDB_DATABASE=FitbitHealthStats
      - CLIENT_ID=your_application_client_ID # Change this to your client ID
      - CLIENT_SECRET=your_application_client_secret # Change this to your client Secret
      - DEVICENAME=Your_Device_Name # Change this to your device name - e.g. "Charge5" without quotes
      - LOCAL_TIMEZONE=Automatic
    depends_on:
      - influxdb


  influxdb:
    restart: unless-stopped
    container_name: influxdb
    hostname: influxdb
    environment:
      - INFLUXDB_DB=FitbitHealthStats
      - INFLUXDB_USER=fitbit_user
      - INFLUXDB_USER_PASSWORD=fitbit_password
      - INFLUXDB_DATA_INDEX_VERSION=tsi1
      ###############################################################################
      # The following ENV variables are applicable for InfluxDB V3 - No effect for V1
      ###############################################################################
      # - INFLUXDB3_MAX_HTTP_REQUEST_SIZE=10485760
      # - INFLUXDB3_NODE_IDENTIFIER_PREFIX=Influxdb-node1
      # - INFLUXDB3_BUCKET=GarminStats
      # - INFLUXDB3_OBJECT_STORE=file
      # - INFLUXDB3_DB_DIR=/data
      # - INFLUXDB3_QUERY_FILE_LIMIT=5000 # this set to be a very high value if you want to view long term data
    ports:
      - '8086:8086' # Influxdb V3 should map as "8181:8181" (Change INFLUXDB_PORT to 8181 on fitbit-fetch-data appropriately for InfluxDB V3)
    volumes:
      - ./influxdb:/var/lib/influxdb # InfluxDB V3 bind mount should be set like - ./influxdb:/data if you set INFLUXDB3_DB_DIR=/data (instead of /var/lib/influxdb)
    image: 'influxdb:1.11' # You must change this to 'quay.io/influxdb/influxdb3-core:latest' for influxdb V3

  grafana:
    restart: unless-stopped
    container_name: grafana
    hostname: grafana
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_PLUGINS_PREINSTALL=marcusolsson-hourly-heatmap-panel
    volumes:
      - './grafana:/var/lib/grafana'
    ports:
      - '3000:3000'
    image: 'grafana/grafana:latest'
```

✅ The Above compose file creates an open read/write access influxdb database with no authentication. Unless you expose this database to the open internet directly, this poses no threat. You may enable authentication and grant appropriate read/write access to the `fitbit_user` on the `FitbitHealthStats` database manually if you want with `INFLUXDB_ADMIN_ENABLED`, `INFLUXDB_ADMIN_USER`, and `INFLUXDB_ADMIN_PASSWORD` ENV variables, following the [influxdb guide](https://github.com/docker-library/docs/blob/master/influxdb/README.md) but this won't be covered here for the sake of simplicity. 

## Historical Data Update

#### Background

The primary purpose of this script is to visualize long term data and if you have just discovered it, you may need to wait a long time to acheive this by automatic daily data fetch process. But fear not! this script was written with that fact in mind. As you may know, **fitbit rate limits the API calls to their server from their users, so only 150 API calls are allowed per hour** and it resets every hour. Some API endpoints allows fetching long term data for months and years while most **intraday data is limited to 24 hours per API call**. So this means if you need to fetch HR and steps data for 5 days, there is no other way but making 5x2=10 API calls to their servers. Now imagine this at scale, multiple measurements over the years of data. I was faced with this exact problem and it really took me a long time to figure out the most optimal way to fetch bulk historic data is to group them into categories based on their period limits and implement robust handing of `429 Error` ('too many requests within an hour' error).

This script has a feature that in the bulk update mode it will fill up the less limited data first and finally fill up the intraday data so you can see the data filling up in grafana real time as the script progresses. After it exausts it's available 150 calls for the hour, it will go to dormant mode for the remaining duration for that hour, and resume fetching the data as soon as the wait time is up automatically (so you can just leave it and let it work). To give you a timeline, **it took a little more than 24 hours to fetch all the historic data for my 2 years of historic data from their servers**.

#### Procedure

The process is quite simple. you need to add an ENV variable and rerun the container in interactive mode. here is a step-by-step guide

- Stop the running container and remove it with `docker compose down` if running already
- In the docker compose file, add a new ENV variable `AUTO_DATE_RANGE=False` under the `environment` section along with other variables. This variable switches the mode to bulk update instead of regular daily update
- Assuming you are already in the directory where the `compose.yml` file is, run `docker compose run --rm fitbit-fetch-data` - this will run this container in _"remove container automatically after finish"_ mode which is useful for one time running like this. This will also attach the container to the shell as interactive mode, so don't close the shell until the bulk update is complete.
- After initialization, you will be requested to input the start and end dates in YYYY-MM-DD format. the format is very important so please enter the dates like this `2024-03-13`. Start date must be earlier than end date. The script should work for any given range, but if you encounter an error during the bulk update with large date range, please break the date range into one year chunks (maybe a few days less than one year just to be safe), and run it for each one year chunk one after another. I personally did not encounter any issue with longer date ranges, but this is just a heads up.
- You will see the update logs in the attached shell. Please wait until it shpws `Bulk Update Complete` and exits. It might take a long time depending on the given duration and 150 API call limit per hour.
- You are done with the bulk update at this point. Remove the ENV variable from the compose or change it to `AUTO_DATE_RANGE=True`, save the compose file and run `docker compose up` to resume daily update.
  
#### Non-interactive Procedure

You can run the bulk update in non-interactive mode by setting these additoinal environment variables.

- `MANUAL_START_DATE` optional, in YYYY-MM-DD format, if you want to bulk update only from specific date
- `MANUAL_END_DATE` optional, in YYYY-MM-DD format, if you want to bulk update until a specific date

## Backup Database

Whether you are using a bind mount or a docker volume, creating a restorable archival backup of your valuable health data is always advised. Assuming you named your database as `FitbitHealthStats` and influxdb container name is `influxdb`, you can use the following script to create a static archival backup of your data present in the influxdb database at that time point. This restore points can be used to re-create the influxdb database with the archived data without requesting them from Garmin's servers again, which is not only time consuming but also resource intensive. 

```bash
#!/bin/bash
TIMESTAMP=$(date +%F_%H-%M)
BACKUP_DIR="./influxdb_backups/$TIMESTAMP"
mkdir -p "$BACKUP_DIR"
docker exec influxdb influxd backup -portable -db FitbitHealthStats /tmp/influxdb_backup
docker cp influxdb:/tmp/influxdb_backup "$BACKUP_DIR"
docker exec influxdb rm -r /tmp/influxdb_backup"
```

The above bash script would create a folder named `influxdb_backups` inside your current working directory and create a subfolder under it with current date-time. Then it will create the backup for `FitbitHealthStats` database and copy the backup files to that location. 

For restoring the data from a backup, you first need to make the files available inside the new influxdb docker container. You can use `docker cp` or volume bind mount for this. Once the backup data is available to the container internally, you can simply run `docker exec influxdb influxd restore -portable -db FitbitHealthStats /path/to/internal-backup-directory` to restore the backup.

Please read detailed guide on this from the [influxDB documentation for backup and restore](https://docs.influxdata.com/influxdb/v1/administration/backup_and_restore/)

## Direct Install method (For developers)

Set up influxdb 1.8 ( direct install or via [docker](https://github.com/arpanghosh8453/public-docker-config#influxdb) ). Create an user with a password and an empty database.

Set up grafana recent release ( direct install or via [docker](https://github.com/arpanghosh8453/public-docker-config#grafana) )

Use the `requirements.txt` file to install the required packages using pip

Follow this [guide](https://dev.fitbit.com/build/reference/web-api/developer-guide/getting-started/) to create an application. This will give you a client ID, client secret, and a refresh token.

❗ **The Fitbit application must be personal type for the access of intraday data series** ❗ - Otherwise you might encounter `KeyError: 'activities-heart-intraday'` Error.

Update the following variables in the python script ( use the influxdb-v2 specific variables for influxdb-v2 instance )

- FITBIT_LOG_FILE_PATH = "your/expected/log/file/location/path"
- TOKEN_FILE_PATH = "your/expected/token/file/location/path"
- INFLUXDB_USERNAME = 'your_influxdb_username'
- INFLUXDB_PASSWORD = 'your_influxdb_password'
- INFLUXDB_DATABASE = 'your_influxdb_database_name'
- client_id = "your_application_client_ID"
- client_secret = "your_application_client_secret"
- DEVICENAME = "Your_Device_Name" # example - "Charge5"
- LOCAL_TIMEZONE=Automatic # set to "Automatic" for Automatic setup from User profile (if not mentioned here specifically).

Run the script; it will request a refresh token as input for the first run to set up the token file. You can check the logs to see the work in progress. The script, by default, keeps running forever, calling different functions at scheduled intervals.

Finally, add the influxdb database as a Data source in Grafana, please use the [JSON files](https://github.com/arpanghosh8453/public-fitbit-projects/tree/main/Grafana_Dashboard) from the Grafana_Dashboard to replicate the dashboard quickly.

You can use the [Fitbit_Fetch_Autostart.service](https://github.com/arpanghosh8453/public-fitbit-projects/blob/main/extra/Fitbit_Fetch_Autostart.service) template to set up an auto-starting ( and auto-restarting in case of temporary failure ) service in Linux based system ( or WSL )

## Troubleshooting

- If you are getting `KeyError: 'activities-heart-intraday'` please double check if your Fitbit Oauth application is set as `personal` type before you open an issue

- If you are missing GPS data, but you know you have some within the selected time range in grafana, check if the variable GPS Activity variable is properly set or not. You should have a dropdown there. If you do not see any values, please go to the dashboard settings and check if the GPS variable datasource is properly set or not.

- In some cases, for the `grafana` container, you may need to chown the corresponding mounted folders as *472*:*472* if you are having read/write errors inside the grafana container. The logs will inform you if this happens. The `influxdb:1.11` container requires the folder to be owned by `1500:1500`


## Own a Garmin Device?

If you are a **Garmin user**, please check out the [sister project](https://github.com/arpanghosh8453/garmin-grafana) made for Garmin

## Deploy with Homeassistant integration

User [@Jasonthefirst](https://github.com/Jasonthefirst) has developed a plugin (issue [#24](https://github.com/arpanghosh8453/public-fitbit-projects/issues/24) ) based on the python script which can be used to deploy the setup without docker. Please refer to [fitbit-ha-addon](https://gitlab.fristerspace.de/demian/fitbit-ha-addon) for the setup.

## Support me

If you enjoy the script and love how it works with simple setup, please consider supporting me with a coffee ❤. You can view more detailed health statistics with this setup than paying a subscription fee to Fitbit, thanks to their free REST API services.

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/A0A84F3DP)

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=arpanghosh8453/public-fitbit-projects&type=Date)](https://www.star-history.com/#arpanghosh8453/public-fitbit-projects&Date)
