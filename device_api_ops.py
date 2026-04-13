# Third-party library for making asynchronous HTTP requests
import aiohttp

# Standard library module for writing and running asynchronous concurrent code
import asyncio

# Standard library module for searching and matching text patterns using regular expressions
import re

# Local helper module; provides utility functions such as get_absolute_path()
import common_helper_functions

# Standard library module for writing structured log messages (INFO, ERROR, etc.)
import logging

# Logging handler that auto-rotates the log file when it reaches a defined size limit
from logging.handlers import RotatingFileHandler

###################################################################################################################################

# SETUP LOGGING
# -------------
logger = logging.getLogger(__name__) # use the module's name as the name in the logs
logger.setLevel(logging.INFO) # set the logging level
log_file_path = common_helper_functions.get_absolute_path('execution_logs.log') # define the logging file path

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

# RETRIEVE THE CURRENT VERSION
# ----------------------------
async def get_current_version(session, ip, username, password, semaphore):

    """
    PURPOSE
    -------
    Asynchronously retrieves the current IOS version of a device via RESTCONF.

    
    ARGUMENTS
    ---------
    session  (aiohttp.ClientSession): Shared async HTTP session.
    ip       (str):                   Device OOBM IP address.
    username (str):                   Device username.
    password (str):                   Device password.

    
    RETURN VALUE
    ------------
    Version string (e.g. '17.13.1a') on success, None on failure.
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
                    # 200 received but version string not found in the response body
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

    # ssl=False and connector disable built-in SSL verification (equivalent to verify=False)
    connector = aiohttp.TCPConnector(ssl=False)

    # Allow a maximum of 5 concurrent requests at a time
    semaphore = asyncio.Semaphore(10)

    async with aiohttp.ClientSession(connector=connector) as session:

        # Build a coroutine for each device
        tasks = [
            get_current_version(session, row['OOBM IP Address'], username, password, semaphore)
            for _, row in valid_devices_df.iterrows()
        ]

        # Fire all tasks concurrently and wait for all to finish
        results = await asyncio.gather(*tasks)

    # Return the list of (ip, version) tuples to the caller
    return results
 

# GET THE DEVICE'S FLASH MEMORY FREE SPACE
# ----------------------------------------
async def get_flash_free_space(session, ip, username, password, semaphore):

    """
    PURPOSE
    -------
    Retrieves available flash free space on a device via RESTCONF.

    ARGUMENTS
    ---------
    session   (aiohttp.ClientSession): Shared async HTTP session.
    ip        (str):                   Device OOBM IP address.
    username  (str):                   Device username.
    password  (str):                   Device password.
    semaphore (asyncio.Semaphore):     Semaphore to control concurrency.

    RETURN VALUE
    ------------
    Tuple of (ip, free_bytes) on success, (ip, None) on failure.
    """

    url = f"https://{ip}/restconf/data/Cisco-IOS-XE-platform-software-oper:cisco-platform-software/q-filesystem"

    headers = {
        "Accept": "application/yang-data+json"
    }

    async with semaphore:
        try:
            async with session.get(url, auth=aiohttp.BasicAuth(username, password), headers=headers, ssl=False) as response:

                if response.status == 200:
                    data = await response.json(content_type=None)
                    filesystems = data.get("Cisco-IOS-XE-platform-software-oper:q-filesystem", [])
                    # Temporary debug log to inspect the response structure
                    #------------------------------------------------------------
                    #logger.info(f"Filesystems response for {ip}: {filesystems}")
                    #------------------------------------------------------------

                    # Find the flash: filesystem entry
                    for fs in filesystems:
                        for partition in fs.get("partitions", []):
                            # The flash partition is called bootflash
                            if "bootflash" in partition.get("name", "").lower() or "flash" in partition.get("name", "").lower():
                                total = int(partition.get("total-size", 0))
                                used = int(partition.get("used-size", 0))
                                free_bytes = (total - used) * 1024  # values are in KB, so multiply by 1024 to get bytes for the comparison against the image file size.
                                #---------------------------------------------------------------------------
                                logger.info(f"Flash free space for {ip}: {free_bytes / (1024*1024):.0f} MB")
                                #---------------------------------------------------------------------------
                                return ip, free_bytes
                        
                    # No flash filesystem entry found in the response
                    #----------------------------------------------------------------
                    logger.warning(f"No flash filesystem found in response for {ip}")
                    #----------------------------------------------------------------
                    return ip, None
                
                else:
                    #--------------------------------------------------------------------------------------------------------
                    logger.error(f"!!! Failed retrieving flash space for {ip}: {response.status}")
                    #--------------------------------------------------------------------------------------------------------
                    return ip, None

        except Exception as e:
            #--------------------------------------------------------------------------------------------------------
            logger.error(f"!!! Exception retrieving flash space for {ip}: {e}")
            #--------------------------------------------------------------------------------------------------------
            return ip, None
        
# Event Loop
async def get_all_flash_free_space(valid_devices_df, username, password):
    """
    PURPOSE
    -------
    Concurrently retrieves the available flash free space for all devices
    in the DataFrame using async HTTP requests, and stores the results
    in the 'Flash Free Space' column.


    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): DataFrame containing at minimum 'OOBM IP Address' column.
    username         (str):          Device username for RESTCONF authentication.
    password         (str):          Device password for RESTCONF authentication.


    RETURN VALUE
    ------------
    List of (ip, free_bytes) tuples, one per device.
    free_bytes is None for devices that failed or were unreachable.
    """

    # Create a TCP connector with SSL verification disabled
    connector = aiohttp.TCPConnector(ssl=False)

    # Limit concurrent requests to 10 at a time
    semaphore = asyncio.Semaphore(10)

    async with aiohttp.ClientSession(connector=connector) as session:

        # Build one coroutine per device row
        tasks = [
            get_flash_free_space(session, row['OOBM IP Address'], username, password, semaphore)
            for _, row in valid_devices_df.iterrows()
        ]

        # Fire all coroutines concurrently and wait for all to complete
        results = await asyncio.gather(*tasks)

    # Return the list of (ip, free_bytes) tuples to the caller
    return results


# CHECK IF SCP IS ENABLED
# -----------------------
async def get_scp_status(session, ip, username, password, semaphore):
    """
    PURPOSE
    -------
    Checks if SCP server is enabled on a device via RESTCONF.


    ARGUMENTS
    ---------
    session   (aiohttp.ClientSession): Shared async HTTP session.
    ip        (str):                   Device OOBM IP address.
    username  (str):                   Device username.
    password  (str):                   Device password.
    semaphore (asyncio.Semaphore):     Semaphore to control concurrency.


    RETURN VALUE
    ------------
    Tuple of (ip, 'YES') if enabled, (ip, 'NO') if not, (ip, None) on error.
    """

    url = f"https://{ip}/restconf/data/Cisco-IOS-XE-native:native/ip/scp/server/enable"

    headers = {
        "Accept": "application/yang-data+json"
    }

    async with semaphore:
        try:
            async with session.get(url, auth=aiohttp.BasicAuth(username, password), headers=headers, ssl=False) as response:

                if response.status == 200:
                    #--------------------------------------------
                    logger.info(f"SCP server is enabled on {ip}")
                    #--------------------------------------------
                    return ip, 'YES'

                elif response.status == 404:
                    #---------------------------------------------------
                    logger.warning(f"SCP server is not enabled on {ip}")
                    #---------------------------------------------------
                    #-------------------------------------------------------------------
                    # The 404 assumption may not always be correct. On some IOS-XE versions/configurations, a 404 could also mean the RESTCONF path itself is wrong 
                    # or the YANG model isn't supported — not necessarily that SCP is disabled. A device returning 404 for a different reason would be incorrectly
                    #  marked as 'NO'. So we can consider debugging when we see that SCP is enabled on such device but is being marked as NO

                    logger.debug(f"404 response body for {ip}: {await response.text()}")
                    #-------------------------------------------------------------------
                    return ip, 'NO'

                else:
                    #--------------------------------------------------------------------------
                    logger.error(f"!!! Failed checking SCP status for {ip}: {response.status}")
                    #--------------------------------------------------------------------------
                    return ip, "UNKNOWN"

        except Exception as e:
            #---------------------------------------------------------------
            logger.error(f"!!! Exception checking SCP status for {ip}: {e}")
            #---------------------------------------------------------------
            return ip, "UNKNOWN"

# Event Loop
async def get_all_scp_status(valid_devices_df, username, password):
    """
    PURPOSE
    -------
    Concurrently checks SCP server status for all devices in the DataFrame.


    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): DataFrame containing at minimum 'OOBM IP Address' column.
    username         (str):          Device username for RESTCONF authentication.
    password         (str):          Device password for RESTCONF authentication.


    RETURN VALUE
    ------------
    List of (ip, scp_status) tuples, one per device.
    """

    # Create a TCP connector with SSL verification disabled
    connector = aiohttp.TCPConnector(ssl=False)

    # Limit concurrent requests to 10 at a time
    semaphore = asyncio.Semaphore(10)

    async with aiohttp.ClientSession(connector=connector) as session:

        # Build one coroutine per device row
        tasks = [
            get_scp_status(session, row['OOBM IP Address'], username, password, semaphore)
            for _, row in valid_devices_df.iterrows()
        ]

        # Fire all coroutines concurrently and wait for all to complete
        results = await asyncio.gather(*tasks)

    # Return the list of (ip, scp_status) tuples to the caller
    return results