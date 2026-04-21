# Standard library module for thread-safe signaling between threads (used for cancellation)
import threading

# Standard library module for managing concurrent execution across multiple threads
from concurrent.futures import ThreadPoolExecutor, as_completed

# Third-party library for SSH connections to network devices and sending CLI commands
from netmiko import ConnectHandler

# Catch auth failures separately from connectivity failures
from netmiko.exceptions import NetmikoAuthenticationException

# Standard library to perform operations with files and folders
import os

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
    If authentication fails, marks device as ONLINE with AUTH_BAD auth status.

    ARGUMENTS
    ---------
    row      (pd.Series): A single DataFrame row containing device information.
    username (str):       Device SSH username.
    password (str):       Device SSH password.

    RETURN VALUE
    ------------
    Tuple of (index, status, auth_status) where:
        status      : 'ONLINE' or 'OFFLINE'
        auth_status : 'AUTH_OK', 'AUTH_BAD', or None
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

        # If it succeded, it means the device is ONLINE and the authentication succeded
        return index, 'ONLINE', 'AUTH_OK'
    
    except NetmikoAuthenticationException:
        #------------------------------------------------------------------------------------
        logger.warning(f"Authentication failed on '{hostname}' ({ip}) — device is reachable")
        #------------------------------------------------------------------------------------
        # Device responded but rejected credentials — it's ONLINE but AUTH_BAD
        return index, 'ONLINE', 'AUTH_BAD'
    
    except Exception as e:
        #--------------------------------------------------------------------------
        logger.warning(f"Device '{hostname}' ({ip}) is unreachable or failed: {e}")
        #--------------------------------------------------------------------------
        # If it failed, it means that the device is OFFLINE
        return index, 'OFFLINE', 'N/A'

# Thread pool -- Called by 'populate_status_and_auth_status_column' from 'excel_and_data_ops'
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
    List of (index, status, auth_status) tuples — ONLINE/OFFLINE for status, AUTH_OK/AUTH_BAD/N/A for auth_status.
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
                # Unpack the (index, status, auth_status) tuple returned by enable_scp_and_restconf
                index, status, auth_status = future.result()
                results.append((index, status, auth_status))
                #-------------------------------------------------------------------------
                logger.info(f"'{hostname}' status set to: {status} | auth: {auth_status}")
                #-------------------------------------------------------------------------
            except Exception as e:
                #-------------------------------------------------------------
                logger.error(f"Unexpected error processing '{hostname}': {e}")
                #-------------------------------------------------------------

    return results


# GET THE DEVICE'S FLASH MEMORY FREE SPACE
# ----------------------------------------
def get_flash_free_space(row, username, password):

    """
    PURPOSE
    -------
    Connects to a device using Netmiko and retrieves free space (in Bytes)
    from the primary filesystem (bootflash:/flash:) by parsing CLI output.

    Designed to match previous asyncio-style return format.

    
    ARGUMENTS
    ---------
    row      (pd.Series): A single DataFrame row containing device information.
    username (str):       Device SSH username.
    password (str):       Device SSH password.

    
    RETURN VALUE
    ------------
    Tuple of (ip, free_mb) where:
        free_mb : Free space in Bytes (int) or None if unavailable
    """

    ip = row['OOBM IP Address']
    hostname = row['Hostname']

    try:
        connection = ConnectHandler(
            device_type='cisco_ios',
            host=ip,
            username=username,
            password=password
        )

        output = connection.send_command("show file systems")
        connection.disconnect()

        # Intialize the empty list of lines that may contain flash memory information
        flash_candidates = []

        # Find flash/bootflash filesystem lines
        for line in output.splitlines():
            line_clean = line.strip().lower()

            if (
                ("bootflash:" in line_clean or "flash:" in line_clean) and
                any(char.isdigit() for char in line_clean)
            ):
                flash_candidates.append(line)

        if not flash_candidates:
            #-------------------------------------------------------------------
            logger.warning(f"No flash filesystem found for '{hostname}' ({ip})")
            #-------------------------------------------------------------------
            return ip, None

        # Intialize the empty list of lines that actually contain the desired information
        selected_line = None

        # Prefer bootflash if present
        for line in flash_candidates:
            if "bootflash:" in line.lower():
                selected_line = line
                break

        # Otherwise use first flash match
        if not selected_line:
            selected_line = flash_candidates[0]

        # Split and keep only numeric tokens — skips '*', 'rw', 'flash:', etc.
        tokens = [t for t in selected_line.split() if t.isdigit()]

        # Expect at least 3 tokens: total_bytes, free_bytes, and at minimum one more field
        if len(tokens) < 2:
            #--------------------------------------------------------------------------------------------------------------
            logger.warning(f"Invalid filesystem data for '{hostname}' ({ip}): unexpected format '{selected_line.strip()}'")
            #--------------------------------------------------------------------------------------------------------------
            return ip, None

        try:
            # tokens[0] = total size, tokens[1] = free size
            free_bytes = int(tokens[1])
        except ValueError:
            #---------------------------------------------------------------------------------------------
            logger.warning(f"Could not parse free bytes for '{hostname}' ({ip}): token was '{tokens[1]}'")
            #---------------------------------------------------------------------------------------------
            return ip, None

        #-------------------------------------------------------------------------------------------------
        logger.info(f"Flash free space for {ip}: {free_bytes} Bytes -- {free_bytes / (1024*1024):.0f} MB")
        #-------------------------------------------------------------------------------------------------

        return ip, free_bytes

    except Exception as e:
        #------------------------------------------------------------------------
        logger.warning(f"Failed to get flash space for '{hostname}' ({ip}): {e}")
        #------------------------------------------------------------------------
        return ip, None
    
# Thread pool -- Called by 'populate_flash_free_space_column' from 'excel_and_data_ops'
def get_flash_free_space_all(valid_devices_df, username, password, max_workers=10):
    """
    PURPOSE
    -------
    Executes get_flash_free_space() across all devices using multithreading.

    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): Device inventory
    username         (str):          SSH username
    password         (str):          SSH password
    max_workers      (int):          Thread count

    RETURN VALUE
    ------------
    List of tuples:
        (ip, free_bytes)
    """

    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:

        # Keyed by hostname for result logging — mirrors enable_scp_and_restconf_all pattern
        futures = {
            executor.submit(get_flash_free_space, row, username, password): row['Hostname']
            for _, row in valid_devices_df.iterrows()
        }

        for future in as_completed(futures):
            hostname = futures[future]
            try:
                results.append(future.result())
            except Exception as e:
                #--------------------------------------------------------------------------
                logger.error(f"Unexpected error getting flash space for '{hostname}': {e}")
                #--------------------------------------------------------------------------

    return results


# PUSH COMMANDS FOR BOOT VARIABLE AND INSTALL UPGRADE
# ---------------------------------------------------
def install_ios_image(row, username, password):

    """
    PURPOSE
    -------
    Connects to a device via Netmiko and executes the IOS-XE install mode
    upgrade sequence in a single SSH session:

        1. Pushes boot system commands and saves the config.
        2. Runs 'install add file bootflash:<bin>' — stages the image on bootflash.
           Waits for the device prompt (#) to confirm completion, then checks the
           captured output for 'INSTALL_COMPLETED_INFO' or 'SUCCESS'.
        3. Runs 'install activate' via send_multiline — waits for the reload
           confirmation prompt, auto-answers 'y', and waits for '--- Starting
           Activate ---' to confirm the reload sequence has begun.

    User confirmation is handled upstream by confirm_installs() before this
    function is ever called. Version verification and install commit after the
    reboot are handled separately by the caller via the post-install pipeline.


    ARGUMENTS
    ---------
    row      (pd.Series): A single DataFrame row containing device information.
    username (str):       Device SSH username.
    password (str):       Device SSH password.


    RETURN VALUE
    ------------
    Tuple of (index, result) where result is one of:

        'INSTALL_TRIGGERED'  — activate confirmed, device is rebooting.
        'ADD_FAILED'         — install add did not complete successfully.
        'ACTIVATE_FAILED'    — install activate returned a FAILED string.
        'CONNECT_ERROR'      — initial SSH connection or authentication failed.
        'UNEXPECTED_ERROR'   — uncaught exception during any stage.
    """

    index    = row.name
    ip       = row['OOBM IP Address']
    hostname = row['Hostname']
    bin_file = os.path.basename(row['IOS Image Path'])

    try:
        connection = ConnectHandler(
            device_type='cisco_ios',
            host=ip,
            username=username,
            password=password,
            session_timeout=900,
            keepalive=60
        )

        ### <=== PUSH BOOT SYSTEM COMMANDS AND SAVE ===> ###
        # Set the boot variable and save before sending the install commands —
        # this ensures the device boots from the correct image even if the
        # session is interrupted after the reload fires.
        boot_commands = [
            'no boot system',
            'boot system bootflash:packages.conf',
        ]

        #----------------------------------------------------------------
        logger.info(f"'{hostname}' ({ip}): pushing boot system commands")
        #----------------------------------------------------------------

        connection.send_config_set(boot_commands)
        connection.save_config()

        #--------------------------------------------------------------------------------
        logger.info(f"'{hostname}' ({ip}): boot system commands pushed and config saved")
        #--------------------------------------------------------------------------------


        ### <=== INSTALL ADD ===> ###
        # Stages the image on bootflash. This can take several minutes depending
        # on image size — read_timeout is set generously to avoid premature timeout.
        #------------------------------------------------------------------------
        logger.info(f"'{hostname}' ({ip}): running install add for '{bin_file}'")
        #------------------------------------------------------------------------

        add_output = connection.send_command(
            f'install add file bootflash:{bin_file}',
            expect_string=r'SUCCESS|ERROR|FAILED',
            read_timeout=900,
            strip_prompt=False,
            strip_command=False
        )

        if 'SUCCESS' not in add_output:
            #------------------------------------------------------------------------------
            logger.error(f"'{hostname}' ({ip}): install add failed — output: {add_output}")
            #------------------------------------------------------------------------------
            return index, 'ADD_FAILED'
        
        else:
            #------------------------------------------------------------------------
            logger.info(f"'{hostname}' ({ip}): install add succeeded - {add_output}")
            #------------------------------------------------------------------------

            time.sleep(5)

            ### <=== INSTALL ACTIVATE ===> ###
            #------------------------------------------------------------
            logger.info(f"'{hostname}' ({ip}): running install activate")
            #------------------------------------------------------------


            # Wait for the [y/n] confirmation prompt before answering —
            # send_command blocks until the prompt appears
            
            # Command list. This is a list of lists with each element of the inner list being the command to send and the pattern to search for.
            cmd_list = [
                    ['install activate', r"This operation may require a reload"],
                    #  Use a null-string to indicate that we want to automatically search for the trailing prompt as the pattern.
                    ['y', r"Starting Activate"],
                ]
            
            activate_output = connection.send_multiline(
                cmd_list,
                read_timeout=120
            )
            # activate_output = connection.send_command(
            #     'install activate',
            #     expect_string='[y/n]',
            #     read_timeout=120
            # )

            if 'FAILED:' in activate_output:
                #----------------------------------------------------------------------------------------
                logger.error(f"'{hostname}' ({ip}): install activate failed — output: {activate_output}")
                #----------------------------------------------------------------------------------------
                return index,'ACTIVATE_FAILED'

            else:
                #-------------------------------------------------------------------------------------------------
                logger.info(f"'{hostname}' ({ip}): install activate sent — device reloading -- {activate_output}")
                #-------------------------------------------------------------------------------------------------
                connection.disconnect()
                return index, 'INSTALL_TRIGGERED'
                            
    except NetmikoAuthenticationException:
        #---------------------------------------------------------------------------
        logger.error(f"'{hostname}' ({ip}): authentication failed — cannot proceed")
        #---------------------------------------------------------------------------
        return index, 'CONNECT_ERROR'

    except Exception as e:
        #-------------------------------------------------------------------------
        logger.error(f"'{hostname}' ({ip}): failed during install sequence — {e}")
        #-------------------------------------------------------------------------
        return index, 'UNEXPECTED_ERROR'

# Thread pool -- Called by 'populate_install_status_column' from 'excel_and_data_ops'
def install_ios_image_all(confirmed_df, username, password):

    """
    PURPOSE
    -------
    Concurrently executes the IOS install sequence across all confirmed devices
    using a thread pool. User confirmation has already been collected upstream
    by confirm_installs() and all devices are guaranteed to have Transfer Status
    SUCCESS — filtered upstream by get_install_eligible_devices_df().


    ARGUMENTS
    ---------
    confirmed_df (pd.DataFrame): DataFrame containing only devices the user
                                 confirmed for install — subset of install_eligible_devices_df.
    username     (str):          Device SSH username.
    password     (str):          Device SSH password.


    RETURN VALUE
    ------------
    Dict of {index: result} — one entry per device, where index is the original
    DataFrame index and result is the return code from install_ios_image.
    Devices that raised an unexpected thread exception are mapped to 'UNEXPECTED_ERROR'.
    """

    results = {}

    with ThreadPoolExecutor(max_workers=10) as executor:

        # Keyed by dict to avoid tuple unpacking ambiguity on the DataFrame index
        futures = {
            executor.submit(install_ios_image, row, username, password): {'index': idx, 'hostname': row['Hostname']}
            for idx, row in confirmed_df.iterrows()
        }

        # Process results as each thread completes — order is not guaranteed
        for future in as_completed(futures):
            idx      = futures[future]['index']
            hostname = futures[future]['hostname']
            try:
                index, result = future.result()
                #------------------------------------------------------
                logger.info(f"'{hostname}': install result — {result}")
                #------------------------------------------------------
            except Exception as e:
                #-----------------------------------------------------------
                logger.error(f"'{hostname}': unexpected thread error — {e}")
                #-----------------------------------------------------------
                index  = idx
                result = 'UNEXPECTED_ERROR'

            results[index] = result

    return results


# PUSH INSTALL COMMIT
# -------------------
def commit_ios_install(row, username, password):

    """
    PURPOSE
    -------
    Connects to a device via Netmiko and runs 'install commit' to persist
    the activated IOS version as the new default boot image. Called after
    the device has come back up following install activate.


    ARGUMENTS
    ---------
    row      (pd.Series): A single DataFrame row containing device information.
    username (str):       Device SSH username.
    password (str):       Device SSH password.


    RETURN VALUE
    ------------
    Tuple of (index, result) where result is one of:
        'COMMIT_SUCCESS'   — install commit completed successfully.
        'COMMIT_FAILED'    — install commit returned an error or unexpected output.
        'CONNECT_ERROR'    — SSH connection failed.
        'UNEXPECTED_ERROR' — uncaught exception.
    """

    index    = row.name
    ip       = row['OOBM IP Address']
    hostname = row['Hostname']

    try:
        connection = ConnectHandler(
            device_type='cisco_ios',
            host=ip,
            username=username,
            password=password
        )

        #------------------------------------------------------------------
        logger.info(f"'{hostname}' ({ip}): running install commit")
        #------------------------------------------------------------------

        commit_output = connection.send_command(
            'install commit',
            expect_string=r'SUCCESS|ERROR|FAILED',
            read_timeout=300
        )

        if 'SUCCESS' not in commit_output:
            #------------------------------------------------------------------------------------
            logger.error(f"'{hostname}' ({ip}): install commit failed — output: {commit_output}")
            #------------------------------------------------------------------------------------
            return index, 'COMMIT_FAILED'

        #------------------------------------------------------------------
        logger.info(f"'{hostname}' ({ip}): install commit succeeded")
        #------------------------------------------------------------------
        return index, 'COMMIT_SUCCESS'

    except NetmikoAuthenticationException:
        #---------------------------------------------------------------------------
        logger.error(f"'{hostname}' ({ip}): authentication failed during commit")
        #---------------------------------------------------------------------------
        return index, 'CONNECT_ERROR'

    except Exception as e:
        #---------------------------------------------------------------------------
        logger.error(f"'{hostname}' ({ip}): unexpected error during commit — {e}")
        #---------------------------------------------------------------------------
        return index, 'UNEXPECTED_ERROR'

    finally:
        try:
            connection.disconnect()
        except Exception:
            pass

# Thread pool -- Called by 'populate_post_install_status_column' from 'excel_and_data_ops'
def commit_ios_install_all(online_devices_df, username, password):

    """
    PURPOSE
    -------
    Concurrently runs 'install commit' across all devices that came back
    online after the install activate reload, using a thread pool.


    ARGUMENTS
    ---------
    online_devices_df (pd.DataFrame): DataFrame containing only devices that
                                      came back online after the reload.
    username          (str):          Device SSH username.
    password          (str):          Device SSH password.


    RETURN VALUE
    ------------
    Dict of {index: result} — one entry per device, where index is the original
    DataFrame index and result is the return code from commit_ios_install.
    Devices that raised an unexpected thread exception are mapped to 'UNEXPECTED_ERROR'.
    """

    results = {}

    with ThreadPoolExecutor(max_workers=10) as executor:

        # Keyed by dict to avoid tuple unpacking ambiguity on the DataFrame index
        futures = {
            executor.submit(commit_ios_install, row, username, password): {'index': idx, 'hostname': row['Hostname']}
            for idx, row in online_devices_df.iterrows()
        }

        # Process results as each thread completes — order is not guaranteed
        for future in as_completed(futures):
            idx      = futures[future]['index']
            hostname = futures[future]['hostname']
            try:
                index, result = future.result()
                #------------------------------------------------------
                logger.info(f"'{hostname}': commit result — {result}")
                #------------------------------------------------------
            except Exception as e:
                #-----------------------------------------------------------
                logger.error(f"'{hostname}': unexpected thread error — {e}")
                #-----------------------------------------------------------
                index  = idx
                result = 'UNEXPECTED_ERROR'

            results[index] = result

    return results


# REMOVE INACTIVE IOS PACKAGES FROM DEVICES THAT THE INSTALL ADD SUCCEDED
# -----------------------------------------------------------------------
def remove_inactive_ios(row, username, password):

    """
    PURPOSE
    -------
    Connects to a device via Netmiko and runs 'install remove inactive' to
    clean up inactive IOS package files from bootflash, auto-answering the
    confirmation prompt. Only intended to be called on devices whose Install
    Status is INSTALL_TRIGGERED — enforced upstream by the caller.


    ARGUMENTS
    ---------
    row      (pd.Series): A single DataFrame row containing device information.
    username (str):       Device SSH username.
    password (str):       Device SSH password.


    RETURN VALUE
    ------------
    Tuple of (index, result) where result is one of:
        'CLEANED'          — inactive packages removed successfully.
        'CLEAN_FAILED'     — command returned an error or unexpected output.
        'NOTHING_TO_CLEAN' — no inactive packages found, nothing was removed.
        'CONNECT_ERROR'    — SSH connection failed.
        'UNEXPECTED_ERROR' — uncaught exception.
    """

    index    = row.name
    ip       = row['OOBM IP Address']
    hostname = row['Hostname']

    try:
        connection = ConnectHandler(
            device_type='cisco_ios',
            host=ip,
            username=username,
            password=password
        )

        #-------------------------------------------------------------------
        logger.info(f"'{hostname}' ({ip}): running install remove inactive")
        #-------------------------------------------------------------------

        # Command list. This is a list of lists with each element of the inner list being the command to send and the pattern to search for.
        cmd_list = [
                ['install remove inactive', r"Do you want to remove the above files"],
                #  Use a null-string to indicate that we want to automatically search for the trailing prompt as the pattern.
                ['y', r"Deleting file"]
            ]
        
        remove_output = connection.send_multiline(
            cmd_list,
            read_timeout=120
        )

        # If there is nothing to remove the device skips the prompt entirely
        # and returns immediately — detect this before trying to answer
        if 'No inactive' in remove_output or 'Nothing to clean' in remove_output:
            #------------------------------------------------------------------
            logger.info(f"'{hostname}' ({ip}): no inactive packages to remove")
            #------------------------------------------------------------------
            connection.disconnect()
            return index, 'NOTHING_TO_CLEAN'

        if 'SUCCESS' not in remove_output:
            #---------------------------------------------------------------------------------------------
            logger.error(f"'{hostname}' ({ip}): install remove inactive failed — output: {remove_output}")
            #---------------------------------------------------------------------------------------------
            return index, 'CLEAN_FAILED'

        #--------------------------------------------------------------------------
        logger.info(f"'{hostname}' ({ip}): inactive packages removed successfully")
        #--------------------------------------------------------------------------
        return index, 'CLEANED'

    except NetmikoAuthenticationException:
        #-------------------------------------------------------------------------
        logger.error(f"'{hostname}' ({ip}): authentication failed during cleanup")
        #-------------------------------------------------------------------------
        return index, 'CONNECT_ERROR'

    except Exception as e:
        #--------------------------------------------------------------------------
        logger.error(f"'{hostname}' ({ip}): unexpected error during cleanup — {e}")
        #--------------------------------------------------------------------------
        return index, 'UNEXPECTED_ERROR'

    finally:
        try:
            connection.disconnect()
        except Exception:
            pass

def remove_inactive_ios_all(valid_devices_df, username, password):

    """
    PURPOSE
    -------
    Concurrently runs 'install remove inactive' across all devices whose
    Install Status is INSTALL_TRIGGERED, using a thread pool.


    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): Full device DataFrame — filtered internally
                                     to INSTALL_TRIGGERED devices only.
    username         (str):          Device SSH username.
    password         (str):          Device SSH password.


    RETURN VALUE
    ------------
    Dict of {index: result} — one entry per device, where index is the original
    DataFrame index and result is the return code from remove_inactive_ios.
    Devices that raised an unexpected thread exception are mapped to 'UNEXPECTED_ERROR'.
    """

    # Only run cleanup on devices that had the install triggered —
    # all other devices never received a new image so there is nothing to clean
    triggered_devices = valid_devices_df[
        valid_devices_df['Install Status'] == 'INSTALL_TRIGGERED'
    ]

    results = {}

    # Pre-populate N/A for all non-triggered devices upfront —
    # cleanup is not applicable for devices that never received an install
    results = {
        idx: 'N/A'
        for idx in valid_devices_df.index
        if idx not in triggered_devices.index
    }

    if triggered_devices.empty:
        #----------------------------------------------------------------------
        logger.warning("No INSTALL_TRIGGERED devices found — skipping cleanup")
        #----------------------------------------------------------------------
        return {}

    with ThreadPoolExecutor(max_workers=10) as executor:

        # Keyed by dict to avoid tuple unpacking ambiguity on the DataFrame index
        futures = {
            executor.submit(remove_inactive_ios, row, username, password): {'index': idx, 'hostname': row['Hostname']}
            for idx, row in triggered_devices.iterrows()
        }

        # Process results as each thread completes — order is not guaranteed
        for future in as_completed(futures):
            idx      = futures[future]['index']
            hostname = futures[future]['hostname']
            try:
                index, result = future.result()
                #------------------------------------------------------
                logger.info(f"'{hostname}': cleanup result — {result}")
                #------------------------------------------------------
            except Exception as e:
                #-----------------------------------------------------------
                logger.error(f"'{hostname}': unexpected thread error — {e}")
                #-----------------------------------------------------------
                index  = idx
                result = 'UNEXPECTED_ERROR'

            results[index] = result

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

