# Third-party library for SSH connections and SFTP file transfers over SSH
import paramiko

# Standard library to perform operations with files and folders
import os

# Third-party library for transferring files over SCP via an existing paramiko SSH session
from scp import SCPClient

from concurrent.futures import ThreadPoolExecutor, as_completed

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

# DEFINE THE FILE TRANSFER METHOD
# -------------------------------
def transfer_ios_image(ip, username, password, local_image_path, remote_filename):
    """
    PURPOSE
    -------
    Transfers an IOS image file to a device's bootflash via SCP over SSH.
    Displays a live progress bar in the terminal during the transfer.


    ARGUMENTS
    ---------
    ip               (str): Device OOBM IP address.
    username         (str): Device SSH username.
    password         (str): Device SSH password.
    local_image_path (str): Absolute path to the local IOS image file.
    remote_filename  (str): Filename to use on the device's bootflash.


    RETURN VALUE
    ------------
    str: 'SUCCESS' on success, 'CONNECTION_ERROR', 'TRANSFER_ERROR',
         or 'UNEXPECTED_ERROR' on failure.
    """
    
    # Callback invoked by SCPClient on each chunk sent — updates the terminal progress bar in place
    def progress(filename, size, sent):
        percent = (sent / size) * 100
        bar_length = 40
        filled = int(bar_length * sent / size)
        bar = '█' * filled + '░' * (bar_length - filled)
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

    except paramiko.AuthenticationException:
        #------------------------------------------------------------------------------------
        logger.error(f"Transfer to {ip} failed: authentication rejected — check credentials")
        #------------------------------------------------------------------------------------
        return 'CONNECTION_ERROR'

    except paramiko.NoValidConnectionsError:
        #--------------------------------------------------------------------------------------------------
        logger.error(f"Transfer to {ip} failed: could not connect — device unreachable or SSH not enabled")
        #--------------------------------------------------------------------------------------------------
        return 'CONNECTION_ERROR'

    except Exception as e:
        #--------------------------------------------------------------------------
        logger.error(f"Transfer to {ip} failed: unexpected connection error — {e}")
        #--------------------------------------------------------------------------
        return 'UNEXPECTED_ERROR'


    ### <=== SCP THE FILE ===> ###
    try:
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
        return 'TRANSFER_ERROR'

    finally:
        ssh.close()


# EXECUTE THE FILE TRANSFER TO MULTIPLE DEVICES
# ---------------------------------------------
def transfer_ios_image_all(selected_devices_df, username, password):

    """
    PURPOSE
    -------
    Concurrently transfers IOS image files to all selected devices using
    a thread pool, one thread per device.


    ARGUMENTS
    ---------
    selected_devices_df (pd.DataFrame): DataFrame containing only the devices selected for update.
    username            (str):          Device SSH username.
    password            (str):          Device SSH password.


    RETURN VALUE
    ------------
    None - logs the result of each transfer.
    """

    with ThreadPoolExecutor(max_workers=10) as executor:

        futures = {
            executor.submit(
                transfer_ios_image,
                row['OOBM IP Address'],
                username,
                password,
                row['IOS Image Path'],
                os.path.basename(row['IOS Image Path'])
            ): row['Hostname']
            for _, row in selected_devices_df.iterrows()
        }
        # Process results as each transfer completes — as_completed() returns futures in completion order               
        for future in as_completed(futures):
            hostname = futures[future]
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