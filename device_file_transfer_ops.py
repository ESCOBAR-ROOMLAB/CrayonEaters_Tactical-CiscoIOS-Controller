# Third-party library for SSH connections and SFTP file transfers over SSH
import paramiko

# Third-party library for error handling of Paramiko
import paramiko.ssh_exception

# Standard library to perform operations with files and folders
import os

# Third-party library for transferring files over SCP via an existing paramiko SSH session
from scp import SCPClient

# Standard library module for managing concurrent execution across multiple threads
from concurrent.futures import ThreadPoolExecutor, as_completed

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

# DEFINE THE FILE TRANSFER METHOD
# -------------------------------
def single_transfer_ios_image(ip, username, password, local_image_path, remote_filename, cancel_event=None):

    """
    PURPOSE
    -------
    Transfers an IOS image file to a device's bootflash via SCP over SSH.
    Displays a live progress bar in the terminal during the transfer.

    If cancel_event is provided and becomes set before the transfer starts,
    the function returns immediately without opening an SCP session. If it
    is set mid-transfer, the progress callback closes the SSH transport which
    causes scp.put() to raise — aborting the transfer from the client side
    without waiting for the router to drop the session.


    ARGUMENTS
    ---------
    ip               (str):             Device OOBM IP address.
    username         (str):             Device SSH username.
    password         (str):             Device SSH password.
    local_image_path (str):             Absolute path to the local IOS image file.
    remote_filename  (str):             Filename to use on the device's bootflash.
    cancel_event     (threading.Event): Optional. When set, aborts the transfer
                                        before or during the SCP session.


    RETURN VALUE
    ------------
    str: 'SUCCESS' on success, 'FAILED' on failure or cancellation.
    """

    # Callback invoked by SCPClient on each chunk sent — updates the terminal progress bar in place.
    # Also acts as the mid-transfer cancellation check point: if cancel_event is set, the SSH
    # transport is closed here which immediately raises an exception inside scp.put(), unwinding
    # the transfer without waiting for the router to time out the session on its own.
    def progress(filename, size, sent):
        if cancel_event is not None and cancel_event.is_set():
            transport = ssh.get_transport()
            if transport and transport.is_active():
                transport.close()   # Force scp.put() to raise — aborts the transfer immediately
            return
        percent    = (sent / size) * 100
        bar_length = 40
        filled     = int(bar_length * sent / size)
        bar        = '█' * filled + '░' * (bar_length - filled)
        # \r returns the cursor to the start of the line so each update overwrites the previous one
        print(f'\r  [{bar}] {percent:.1f}% ({sent / (1024*1024):.1f} MB / {size / (1024*1024):.1f} MB)', end='', flush=True)
        if sent == size:
            print()  # Move to the next line once the transfer is complete

    # Initialize the SSH client
    ssh = paramiko.SSHClient()


    ### <=== ESTABLISH SSH SESSION ===> ###
    try:
        # Disable Pageant/SSH agent and key file lookup — go straight to password authentication
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, port=22, username=username, password=password, allow_agent=False, look_for_keys=False)

    # These errors are rarely going to happen, because the devices have been checked thoroughly beforehand
    except paramiko.AuthenticationException:
        #------------------------------------------------------------------------------------
        logger.error(f"Transfer to {ip} failed: authentication rejected — check credentials")
        #------------------------------------------------------------------------------------
        return 'FAILED'

    except paramiko.ssh_exception.NoValidConnectionsError:
        #--------------------------------------------------------------------------------------------------
        logger.error(f"Transfer to {ip} failed: could not connect — device unreachable or SSH not enabled")
        #--------------------------------------------------------------------------------------------------
        return 'FAILED'

    except Exception as e:
        #--------------------------------------------------------------------------
        logger.error(f"Transfer to {ip} failed: unexpected connection error — {e}")
        #--------------------------------------------------------------------------
        return 'FAILED'


    ### <=== SCP THE FILE ===> ###
    try:
        # Bail out before opening the SCP session if cancellation was already requested —
        # avoids starting a brand-new transfer that would immediately be torn down anyway
        if cancel_event is not None and cancel_event.is_set():
            #---------------------------------------------------------------------
            logger.warning(f"Transfer to {ip} skipped — cancellation already set")
            #---------------------------------------------------------------------
            return 'FAILED'

        print(f'Transferring {os.path.basename(local_image_path)} to {ip}...')

        with SCPClient(ssh.get_transport(), progress=progress) as scp:
            scp.put(local_image_path, f'bootflash:/{remote_filename}')

        #---------------------------------------------------------------------------------
        logger.info(f"Transfer to {ip} succeeded: {remote_filename} written to bootflash")
        #---------------------------------------------------------------------------------
        print(f'Transfer to {ip} complete.')
        return 'SUCCESS'

    except Exception as e:
        #-----------------------------------------------------------------
        logger.error(f"Transfer to {ip} failed: SCP transfer error — {e}")
        #-----------------------------------------------------------------
        return 'FAILED'

    finally:
        ssh.close()

# Thread pool -- Called by 'populate_transfer_status_column' from 'excel_and_data_ops'
def threaded_transfer_ios_image_all(selected_devices_df, username, password, cancel_event=None):

    """
    PURPOSE
    -------
    Concurrently transfers IOS image files to all selected devices using
    a thread pool, one thread per device.

    cancel_event is forwarded to each single_transfer_ios_image call so that
    a cancellation request propagates into every active and pending transfer.


    ARGUMENTS
    ---------
    selected_devices_df (pd.DataFrame):    DataFrame containing only the devices selected for update.
    username            (str):             Device SSH username.
    password            (str):             Device SSH password.
    cancel_event        (threading.Event): Optional. Passed through to each transfer worker. When set, pending transfers are skipped and active ones are aborted at the next progress callback.


    RETURN VALUE
    ------------
    Dict of {index: result} — one entry per device, where index is the original
    DataFrame index and result is the return code from single_transfer_ios_image.
    Devices that raised an unexpected thread exception are mapped to 'FAILED'.
    """

    with ThreadPoolExecutor(max_workers=10) as executor:

        futures = {
            executor.submit(
                single_transfer_ios_image,
                row['OOBM IP Address'],
                username,
                password,
                row['IOS Image Path'],
                os.path.basename(row['IOS Image Path']),
                cancel_event                                # Forward so each worker can self-abort
            ): {'index': idx, 'hostname': row['Hostname']}
            for idx, row in selected_devices_df.iterrows()
        }

        results = {}

        # Process results as each transfer completes — as_completed() returns futures in completion order
        for future in as_completed(futures):
            idx      = futures[future]['index']
            hostname = futures[future]['hostname']
            try:
                result = future.result()
                if result == 'SUCCESS':
                    #-----------------------------------------------------------
                    logger.info(f"{hostname} - transfer completed successfully")
                    #-----------------------------------------------------------
                else:
                    #-----------------------------------------------------------
                    logger.error(f"{hostname} - transfer failed with: {result}")
                    #-----------------------------------------------------------
            except Exception as e:
                #---------------------------------------------------------
                logger.error(f"{hostname} - unexpected thread error: {e}")
                #---------------------------------------------------------
                result = 'FAILED'

            results[idx] = result

    return results