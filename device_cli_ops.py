# Standard library module for thread-safe signaling between threads (used for cancellation)
import threading

# Standard library module for managing concurrent execution across multiple threads
from concurrent.futures import ThreadPoolExecutor, as_completed

# Third-party library for SSH connections to network devices and sending CLI commands
from netmiko import ConnectHandler

# Standard library to perform operations with files and folders
import os

import time

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

# DEFINE A GLOBAL CANCELLATION EVENT
# ----------------------------------
# Set this to signal all threads to stop
cancel_event = threading.Event()


# ENABLE SCP AND RESTCONF ON ALL ONLINE DEVICES
# ---------------------------------------------
def enable_scp_and_restconf(row, username, password):

    """
    PURPOSE
    -------
    Connects to a device via Netmiko and temporarily enables RESTCONF, SCP,
    and HTTPS (ip http secure-server) without saving to the startup config.
    Sets the device Status to ONLINE on success, OFFLINE on failure.


    ARGUMENTS
    ---------
    row      (pd.Series): A single DataFrame row containing device information.
    username (str):       Device SSH username.
    password (str):       Device SSH password.


    RETURN VALUE
    ------------
    Tuple of (index, 'ONLINE') on success, (index, 'OFFLINE') on failure.
    """

    # Define the parameters
    ip = row['OOBM IP Address']
    hostname = row['Hostname']
    index = row.name

    # Open the SSH connection
    try:
        connection = ConnectHandler(
            device_type='cisco_ios',
            host=ip,
            username=username,
            password=password
        )

        # Enable RESTCONF, SCP and HTTPS temporarily — do not save to startup config
        commands = [
            'ip http secure-server',
            'ip scp server enable',
            'restconf'
        ]

        # Push the configs to the devices
        connection.send_config_set(commands)
        connection.disconnect()

        #---------------------------------------------------------------
        logger.info(f"APIs enabled successfully on '{hostname}' ({ip})")
        #---------------------------------------------------------------

        # If it succeded, it means the device is ONLINE
        return index, 'ONLINE'

    except Exception as e:
        #--------------------------------------------------------------------------
        logger.warning(f"Device '{hostname}' ({ip}) is unreachable or failed: {e}")
        #--------------------------------------------------------------------------
        # If it failed, it means that the device is OFFLINE
        return index, 'OFFLINE'

# To be called by main program
def enable_scp_and_restconf_all(valid_devices_df, username, password):

    """
    PURPOSE
    -------
    Concurrently connects to all devices in the DataFrame and temporarily
    enables RESTCONF, SCP, and HTTPS. Waits 60 seconds after all devices
    have been configured to allow RESTCONF to become effective.


    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): DataFrame containing at minimum 'OOBM IP Address' and 'Hostname' columns.
    username         (str):          Device SSH username.
    password         (str):          Device SSH password.


    RETURN VALUE
    ------------
    List of (index, status) tuples — ONLINE if configuration succeeded, OFFLINE if it failed.
    """

    # Submit one configuration task per device — max 10 concurrent connections
    with ThreadPoolExecutor(max_workers=10) as executor:

        # Build a future for each device, keyed by hostname for result logging
        futures = {
            executor.submit(enable_scp_and_restconf, row, username, password): row['Hostname']
            for _, row in valid_devices_df.iterrows()
        }

        # Initialize the list that will collect (index, status) tuples
        results = []

        # Process results as each thread completes — order is not guaranteed
        for future in as_completed(futures):
            hostname = futures[future]
            try:
                # Unpack the (index, status) tuple returned by enable_scp_and_restconf
                index, status = future.result()
                results.append((index, status))
                #---------------------------------------------------
                logger.info(f"'{hostname}' status set to: {status}")
                #---------------------------------------------------
            except Exception as e:
                #-------------------------------------------------------------
                logger.error(f"Unexpected error processing '{hostname}': {e}")
                #-------------------------------------------------------------

    # RESTCONF takes ~30 seconds to become effective after being enabled — wait 60 seconds
    # to ensure all devices are ready before any RESTCONF calls are made
    #-----------------------------------------------------------------------------------
    logger.info("Waiting 60 seconds for RESTCONF to become effective on all devices...")
    #-----------------------------------------------------------------------------------
    time.sleep(60)
    #------------------------------------------------------------------------------------
    logger.info("Wait complete — RESTCONF should now be available on all online devices")
    #------------------------------------------------------------------------------------

    return results


# CANCEL ALL ACTIVE TRANSFERS
# ---------------------------
def cancel_active_transfers(selected_devices_df, username, password):

    """
    PURPOSE
    -------
    Cancels active SCP transfers by sending 'clear line vty X' to each device
    via Netmiko. This terminates the active VTY sessions on the device side,
    causing the SCP transfer to fail and the transfer threads to exit cleanly.
    It also deletes the partially tranferred file from the FLASH memory.


    ARGUMENTS
    ---------
    selected_devices_df (pd.DataFrame): DataFrame containing the devices with active transfers.
    username            (str):          Device SSH username.
    password            (str):          Device SSH password.


    RETURN VALUE
    ------------
    None - logs the result of each cancellation attempt.
    """

    def cancel_single_device(row):

        ip = row['OOBM IP Address']
        hostname = row['Hostname']
        remote_filename = os.path.basename(row['IOS Image Path'])

        try:
            # Connect to the device and send the clear command
            connection = ConnectHandler(
                device_type='cisco_ios',
                host=ip,
                username=username,
                password=password
            )

            #----------------------------------------------------
            logger.warning(f"Sending 'clear line vty *' to {ip}")
            #----------------------------------------------------
            for vty_line in range(0, 16):
                connection.send_command(f'clear line vty {vty_line}', expect_string=r'#|\[confirm\]')
                connection.send_command('\n', expect_string=r'#')
            connection.disconnect()
            #-----------------------------------------------------
            logger.warning(f"Active VTY sessions cleared on {ip}")
            #-----------------------------------------------------

            # Reconnect to delete the partially transferred file from bootflash. This is necessary because clearing VTY lines 
            # kills all active sessions including potentially your own — so the first connection may be dropped after the clear commands.
            connection = ConnectHandler(
                device_type='cisco_ios',
                host=ip,
                username=username,
                password=password
            )

            #---------------------------------------------------------------
            logger.warning(f"Deleting partially transferred file from {ip}")
            #---------------------------------------------------------------
            connection.send_command(f'delete /force bootflash:{remote_filename}')
            connection.disconnect()
            #-------------------------------------------------------------
            logger.warning(f"Partial file deleted from bootflash on {ip}")
            #-------------------------------------------------------------

        except Exception as e:
            #----------------------------------------------------------------------
            logger.error(f"Failed to clear VTY sessions on {hostname} ({ip}): {e}")
            #----------------------------------------------------------------------

    # Set the cancellation flag first — prevents new transfers from starting
    cancel_event.set()
    #---------------------------------------------------------------------------------
    logger.warning("Cancellation requested — clearing VTY sessions on all devices...")
    #---------------------------------------------------------------------------------

    # Fire cancellation commands concurrently to all devices
    with ThreadPoolExecutor(max_workers=len(selected_devices_df)) as executor:
        futures = [
            executor.submit(cancel_single_device, row)
            for _, row in selected_devices_df.iterrows()
        ]

        # Wait for all cancellation commands to complete
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                #---------------------------------------------------------
                logger.error(f"Unexpected error during cancellation: {e}")
                #---------------------------------------------------------

# TEST CANCEL ALL ACTIVE TRANSFERS
# ---------------------------
def test_cancel_active_transfers(device_ips, remote_filename, username, password):

    def cancel_single_device(ip):

        try:
            # Connect to the device and send the clear command
            connection = ConnectHandler(
                device_type='cisco_ios',
                host=ip,
                username=username,
                password=password
            )

            #-----------------------------------------------------------------
            logger.warning(f"Sending 'clear line vty *' to {ip}")
            #-----------------------------------------------------------------
            for vty_line in range(0, 16):
                connection.send_command(f'clear line vty {vty_line}', expect_string=r'#|\[confirm\]')
                connection.send_command('\n', expect_string=r'#')
            connection.disconnect()
            #------------------------------------------------------------------
            logger.warning(f"Active VTY sessions cleared on {ip}")
            #------------------------------------------------------------------

            # Reconnect to delete the partially transferred file from bootflash
            connection = ConnectHandler(
                device_type='cisco_ios',
                host=ip,
                username=username,
                password=password
            )

            #---------------------------------------------------------------
            logger.warning(f"Deleting partially transferred file from {ip}")
            #---------------------------------------------------------------
            connection.send_command(f'delete /force bootflash:{remote_filename}')
            connection.disconnect()
            #-------------------------------------------------------------
            logger.warning(f"Partial file deleted from bootflash on {ip}")
            #-------------------------------------------------------------

        except Exception as e:
            #---------------------------------------------------------
            logger.error(f"Failed to clear VTY sessions on {ip}: {e}")
            #---------------------------------------------------------

    # Set the cancellation flag first — prevents new transfers from starting
    cancel_event.set()
    #---------------------------------------------------------------------------------
    logger.warning("Cancellation requested — clearing VTY sessions on all devices...")
    #---------------------------------------------------------------------------------

    # Fire cancellation commands concurrently to all devices
    with ThreadPoolExecutor(max_workers=len(device_ips)) as executor:
        futures = [
            executor.submit(cancel_single_device, ip)
            for ip in device_ips
        ]

        # Wait for all cancellation commands to complete
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                #---------------------------------------------------------
                logger.error(f"Unexpected error during cancellation: {e}")
                #---------------------------------------------------------

