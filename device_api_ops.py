# Third-party library for making asynchronous HTTP requests
import aiohttp

# Standard library module for writing and running asynchronous concurrent code
import asyncio

# Standard library module for searching and matching text patterns using regular expressions
import re

# Standard library module to perform operations with time
import time

# Standard library module for writing structured log messages (INFO, ERROR, etc.)
import logging

# Logging handler that auto-rotates the log file when it reaches a defined size limit
from logging.handlers import RotatingFileHandler

###################################################################################################################################

# SETUP LOGGING
# -------------
logger = logging.getLogger(__name__) # use the module's name as the name in the logs
logger.setLevel(logging.INFO) # set the logging level
log_file_path = 'execution_logs.log' # define the logging file path

# Use RotatingFileHandler
# log_file_path = the absolute path for the log file
# maxBytes: 5 * 1024
# backupCount=0: When the file is full, delete it and start a new one
handler = RotatingFileHandler(
    log_file_path, maxBytes=5*1024*1024, backupCount=0
)

# Set the format of the log messages
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

# Add the formatted HANDLER to the logger
logger.addHandler(handler)

###################################################################################################################################

# CHECK IF RESTCONF HAS BEEN SUCCESSFULLY ENABLED
# -----------------------------------------------
async def wait_for_restconf(session, host, username, password, semaphore, timeout, interval):

    """
    PURPOSE
    -------
    Polls the RESTCONF root endpoint on a device at regular intervals until it
    responds with a valid HTTP status code, indicating the RESTCONF stack is fully
    operative. Returns False if the device does not respond within the timeout window.


    ARGUMENTS
    ---------
    session   (aiohttp.ClientSession):  Shared async HTTP session to use for requests.
    host      (str):                    Device IP address or hostname.
    username  (str):                    Device username for RESTCONF authentication.
    password  (str):                    Device password for RESTCONF authentication.
    semaphore (asyncio.Semaphore):      Shared semaphore that limits concurrent polling sessions.
    timeout   (int):                    Maximum number of seconds to wait before giving up.
    interval  (int):                    Number of seconds to wait between each poll attempt.


    RETURN VALUE
    ------------
    True  if RESTCONF responded within the timeout window.
    False if the timeout was exceeded and RESTCONF never became operative.
    """

    url = f"https://{host}/restconf"
    deadline = time.monotonic() + timeout  # real wall-clock deadline

    while time.monotonic() < deadline:
        try:
            async with semaphore:
                async with session.get(url, auth=aiohttp.BasicAuth(username, password), ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as response:

                    # Any of these status codes confirm the HTTP stack is up and serving requests.
                    # 401/403 are still valid — they mean RESTCONF is running but rejected the credentials,
                    # which is fine here since we are only checking operational readiness, not authenticating
                    if response.status in (200, 401, 403):
                        #--------------------------------------------------------------------------------------
                        logger.info(f"!!! Success checking RESTCONF operational for {host}: {response.status}")
                        #--------------------------------------------------------------------------------------
                        return True

        except Exception:
            # Request failed — RESTCONF is not ready yet. Swallow the exception and retry
            pass

        # Only sleep if there's still time left — avoids one extra interval overshoot
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(interval, remaining))


    # Timeout exceeded — RESTCONF never became operative on this device
    #-------------------------------------------------------
    logger.error(f"!!! RESTCONF NOT operational for {host}")
    #-------------------------------------------------------
    return False

# Event Loop
async def get_all_restconf_status(eligible_devices, username, password, timeout, interval):

    """
    PURPOSE
    -------
    Concurrently polls the RESTCONF root endpoint on all provided devices using
    wait_for_restconf(), and returns the results keyed by IP address.


    ARGUMENTS
    ---------
    eligible_devices (pd.DataFrame): DataFrame slice containing only ONLINE/AUTH_OK devices, with at minimum an 'OOBM IP Address' column.
    username         (str):          Device username for RESTCONF authentication.
    password         (str):          Device password for RESTCONF authentication.
    timeout          (int):          Time range sending API requests to check for status.
    interval         (int):          Number of seconds to wait between each poll attempt.

    RETURN VALUE
    ------------
    Dictionary of {ip: bool} — True if RESTCONF became operative, False if timed out.
    """

    # ssl=False on the connector disables built-in SSL verification (equivalent to verify=False)
    connector = aiohttp.TCPConnector(ssl=False)

    # Allow a maximum of 10 concurrent polling sessions at a time
    semaphore = asyncio.Semaphore(10)

    async with aiohttp.ClientSession(connector=connector) as session:

        # Build one polling task per eligible device, keyed by IP for result mapping
        tasks = {
            row['OOBM IP Address']: asyncio.create_task(
                wait_for_restconf(session, row['OOBM IP Address'], username, password, semaphore, timeout, interval)
            )
            for _, row in eligible_devices.iterrows()
        }

        # Wait for all polling tasks to complete — either RESTCONF came up or timed out
        await asyncio.gather(*tasks.values())

    # Return {ip: True/False} so the caller can map results back to the DataFrame
    return {ip: task.result() for ip, task in tasks.items()}


# RETRIEVE THE CURRENT VERSION
# ----------------------------
async def get_current_version(session, ip, username, password, semaphore):

    """
    PURPOSE
    -------
    Asynchronously retrieves the current IOS version of a device via RESTCONF.

    
    ARGUMENTS
    ---------
    session   (aiohttp.ClientSession): Shared async HTTP session.
    ip        (str):                   Device OOBM IP address.
    username  (str):                   Device username.
    password  (str):                   Device password.
    semaphore (asyncio.Semaphore):     Shared semaphore that limits concurrent requests.

    
    RETURN VALUE
    ------------
    Tuple of (ip, version_string) where version_string is the IOS version as a string
    (e.g. '17.13.1a'), or None if the request failed, returned a non-200 status, or
    the version string could not be parsed from the response body.
    """

    # RESTCONF endpoint for device hardware operational data — contains the IOS version string
    url = f"https://{ip}/restconf/data/Cisco-IOS-XE-device-hardware-oper:device-hardware-data"

    # Request JSON response format
    headers = {
        "Accept": "application/yang-data+json"
    }

    # Acquire the semaphore before making the request — only N tasks can be inside this block at once
    async with semaphore:
        try:
            async with session.get(url, auth=aiohttp.BasicAuth(username, password), headers=headers, ssl=False) as response:

                if response.status == 200:
                    # Read the raw response text and extract the version string using regex
                    # The version appears in the response as: "Version 17.13.1a,"
                    raw = await response.text()
                    match = re.search(r'Version (\S+),', raw)
                    if match:
                        #----------------------------------------------------------------------------------------------------
                        logger.info(f"!!! Success retrieving the IOS version for {ip}: {response.status} - {match.group(1)}")
                        #----------------------------------------------------------------------------------------------------
                        return ip, match.group(1)
                    else:
                        # 200 received but version string not found in the response body
                        #------------------------------------------------------------------------
                        logger.warning(f"Version string not found in RESTCONF response for {ip}")
                        #------------------------------------------------------------------------
                        return ip, None

                else:
                    # Non-200 response — RESTCONF returned an error.
                    #---------------------------------------------------------------------------------
                    logger.error(f"!!! Failed retrieving the IOS version for {ip}: {response.status}")
                    #---------------------------------------------------------------------------------
                    return ip, None

        except Exception as e:
            #----------------------------------------------------------------------
            logger.error(f"!!! Exception retrieving the IOS version for {ip}: {e}")
            #----------------------------------------------------------------------
            return ip, None

# Event Loop
async def get_all_versions(valid_devices_df, username, password):

    """
    PURPOSE
    -------
    Concurrently retrieves the current IOS version for all devices in the
    DataFrame using async HTTP requests.

    
    ARGUMENTS
    ---------
    valid_devices_df    (pd.DataFrame):     DataFrame containing at minimum 'OOBM IP Address' column.
    username            (str):              Device username for RESTCONF authentication.
    password            (str):              Device password for RESTCONF authentication.

    
    RETURN VALUE
    ------------
    List of (ip, version) tuples. version is None for devices that failed or were unreachable.
    """

    # Semaphore limits concurrent connections to avoid overwhelming devices
    semaphore = asyncio.Semaphore(10)
    
    try:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False, limit=10),
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            
            tasks = []
            for _, row in valid_devices_df.iterrows():
                ip = row['OOBM IP Address']
                task = get_current_version(session, ip, username, password, semaphore)
                tasks.append(task)
            
            # Wait for all tasks to complete, return exceptions as results
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter out exceptions and convert to proper format
            processed_results = []
            for result in results:
                if isinstance(result, Exception):
                    # We can't know the IP for an exception without more context, skip it
                    continue
                elif result is not None:
                    processed_results.append(result)
            
            return processed_results
            
    except Exception as e:
        #------------------------------------------------------------
        logger.error(f"Unexpected error from get_all_versions — {e}")
        #------------------------------------------------------------
        return []