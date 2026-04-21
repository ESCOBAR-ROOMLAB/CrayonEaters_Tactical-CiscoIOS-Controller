# Data manipulation library; used to read Excel files into DataFrames and perform row/column operations
import pandas as pd

# Standard library module for writing and running asynchronous concurrent code
import asyncio

# Standard library to perform operations with files and folders
import os

# Standard library module for interacting with the Python interpreter (used here for sys.exit())
import sys

# Standard library module to perform operations with time
import time

# Third-party library for retrieving information on running processes and open files
import psutil

# Low-level Excel (.xlsx) reader/writer; used to open and update individual cells in an existing workbook
from openpyxl import load_workbook

# Local helper module; provides IP Addressing operations for validaton, calculation, ...
import ip_addressing_ops

# Local helper module; provides API methods to retrieve and push data of network devices
import device_api_ops

# Local helper module; provides CLI methods to retrieve and push data of network devices
import device_cli_ops

# Local helper module; provides CLI SCP methods to transfer the files for the update
import device_file_transfer_ops

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

# CREATE DEVICES DATAFRAME
# ------------------------
def create_devices_dataframe(excel_file, excel_sheet_name):

    """
    PURPOSE
    -------
    Create a DataFrame from the data in the table of the argumented EXCEL file and sheet

    
    ARGUMENTS
    ---------
    excel_file       (str):            Absolute path to the Excel (.xlsx) file.
    excel_sheet_name (str):            Name of the worksheet to update.

    
    RETURN VALUE
    ------------
    If successful, it returns a DataFrame with all the table data. Otherways, it returns an error code
    """
    
    try:
        # Read the data from the specified sheet
        all_devices_df = pd.read_excel(excel_file, sheet_name=excel_sheet_name)
        #-------------------------------------------
        logger.info("Dataframe creation succedded!")
        #-------------------------------------------
    
    except FileNotFoundError:
        #------------------------------------------------------------------------------
        logger.error(f"Dataframe creation failed: The path {excel_file} was not found")
        #------------------------------------------------------------------------------
        return "FILE_NOT_FOUND_ERROR"
    
    except Exception as e:
        #----------------------------------------------------------------------------------
        logger.error(f"Dataframe creation failed: error while reading the EXCEL file: {e}")
        #----------------------------------------------------------------------------------
        return "UNEXPECTED_ERROR"
    
    if 'OOBM IP Address' not in all_devices_df.columns:
        #------------------------------------------------------------------------------------------------------
        logger.error(f"Dataframe creation failed: a column named 'IP Address' was not found in the EXCEL file")
        #------------------------------------------------------------------------------------------------------
        return "COLUMN_NOT_FOUND_ERROR"
    
    # If successful, return the DataFrame
    return all_devices_df


# VALIDATE DEVICES DATAFRAME
# --------------------------
def valid_devices_dataframe(all_devices_df):

    """
    PURPOSE
    -------
    Remove any rows in the Dataframe that don't have an OOBM IP Address value,
    or a Hostname value, an invalid IP address, or a missing Model. It also sets 
    the current IOS version value for online devices and it points out the offline ones.

    
    ARGUMENTS
    ---------
    all_devices_df (str): the DataFrame with all the table data

    
    RETURN VALUE
    ------------
    Filtered DataFrame with rows that have valid IP Addresses only, both Online and Offline.
    """

    ### <=== REMOVE ROWS WITH MISSING CRITICAL VALUES ===> ###
    # We will only drop rows that don't have a valid value for any of the subset columns
    valid_devices_df = all_devices_df.dropna(subset=['Hostname', 'Model', 'OOBM IP Address'])
    

    ### <=== HANDLE VALUE TYPES FOR BLANK COLUMNS ===> ###
    # When pandas reads an Excel column that has no values in it (all cells empty), it infers the dtype as float64 — since NaN is a 
    # float in numpy, which is what pandas uses to represent empty cells. So when we later try to write a string like '17.13.1a' 
    # into that column with .at[index, ...], pandas refuses because it can't fit a string into a float64 column:
        
    #     TypeError: Invalid value '17.13.1a' for dtype 'float64'
    
    # Initialize all existent columns that will receive mixed string values — blank Excel columns are read as float64
    for col in ['Current IOS Version', 'Needs Update', 'Update IOS File Present', 'Enough Flash Space', 'Status', 'Auth Status', 'Transfer Result', 'Install Status', 'Update Result', 'Cleaned Inactive']:
        valid_devices_df[col] = valid_devices_df[col].astype(object)


    ### <=== REMOVE ROWS WITH INVALID IP ADDRESS ===> ###
    # This line takes the 'OOBM IP Address' column and runs is_valid_ip() on each value individually. Then, it stores on the variable
    # the rows that contain an invalid IP only, so we can log them and handle errors better before removing them
    invalid_ips = valid_devices_df[valid_devices_df['OOBM IP Address'].apply(ip_addressing_ops.is_valid_ip) == False]

    # Log any rows that were dropped due to invalid IPs
    for _, row in invalid_ips.iterrows():
        #---------------------------------------------------------------------------------------------------------------
        logger.warning(f"Skipping device '{row['Hostname']}': invalid OOBM IP Address value '{row['OOBM IP Address']}'")
        #---------------------------------------------------------------------------------------------------------------

    # Filter out any rows with invalid IPs
    valid_devices_df = valid_devices_df[valid_devices_df['OOBM IP Address'].apply(ip_addressing_ops.is_valid_ip) == True]

    ### <=== RETURN FILTERED DATAFRAME ===> ###
    return valid_devices_df
  

# POPULATE THE STATUS AND AUTH STATUS COLUMN
# ------------------------------------------
def populate_status_and_auth_status_column(valid_devices_df, username, password):

    """
    PURPOSE
    -------
    Enables RESTCONF, SCP and HTTPS on all devices and populates the
    'Status' column with ONLINE or OFFLINE, and the 'Auth Status' column
    with AUTH_OK, AUTH_BAD, or None based on the result.

    
    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): DataFrame containing at minimum 'OOBM IP Address' and 'Hostname' columns.
    username         (str):          Device SSH username.
    password         (str):          Device SSH password.

    
    RETURN VALUE
    ------------
    None - modifies valid_devices_df in place via .at[] assignment.
    """

    results = device_cli_ops.enable_scp_and_restconf_all(valid_devices_df, username, password)

    # Write Status and Auth Status back to the dataframe for each device
    for index, status, auth_status in results:
        valid_devices_df.at[index, 'Status']      = status
        valid_devices_df.at[index, 'Auth Status'] = auth_status


# POPULATE THE RESTCONF STATUS COLUMN (going away most likely)
# ------------------------------------
def populate_restconf_status_column(valid_devices_df, username, password, timeout, interval):

    """
    PURPOSE
    -------
    Polls the RESTCONF root endpoint on all ONLINE/AUTH_OK devices and populates
    the 'RESTCONF Status' column with OPERATIVE, NOT_OPERATIVE, or N/A. This column only
    exists in the DataFrame.


    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): DataFrame containing at minimum 'OOBM IP Address', 'Status', and 'Auth Status' columns.
    username         (str):          Device username for RESTCONF authentication.
    password         (str):          Device password for RESTCONF authentication.


    RETURN VALUE
    ------------
    None - modifies valid_devices_df in place via .at[] assignment.
    """

    # Only poll devices that are reachable and authenticated — others can't have RESTCONF operative
    eligible_devices = valid_devices_df[
        (valid_devices_df['Status'] == 'ONLINE') &
        (valid_devices_df['Auth Status'] == 'AUTH_OK')
    ]

    # Returns {ip: True/False} — True if RESTCONF became operative, False if timed out
    restconf_results = asyncio.run(device_api_ops.get_all_restconf_status(eligible_devices, username, password, timeout, interval))

    # Map results back to the DataFrame by IP address
    for index, row in valid_devices_df.iterrows():
        ip = row['OOBM IP Address']

        # Device was not polled — RESTCONF check is irrelevant
        if row['Status'] != 'ONLINE' or row['Auth Status'] != 'AUTH_OK':
            valid_devices_df.at[index, 'RESTCONF Status'] = 'N/A'
            continue

        # True → OPERATIVE, False → NOT_OPERATIVE
        valid_devices_df.at[index, 'RESTCONF Status'] = 'OPERATIVE' if restconf_results[ip] else 'NOT_OPERATIVE'

        
# POPULATE CURRENT VERSION COLUMN (going away most likely, we will use netmiko to retrieve the version)
# -------------------------------
def populate_current_version_column(valid_devices_df, username, password):
    
    """
    PURPOSE
    -------
    Retrieves the current IOS version for all online devices and populates
    the 'Current IOS Version' column.


    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): DataFrame containing at minimum 'OOBM IP Address' column.
    username         (str):          Device username for RESTCONF authentication.
    password         (str):          Device password for RESTCONF authentication.


    RETURN VALUE
    ------------
    None - modifies valid_devices_df in place via .map() assignment.
    """

    # Run all the checks on online devices only
    online_devices = valid_devices_df[valid_devices_df['RESTCONF Status'] == 'OPERATIVE']
    results = asyncio.run(device_api_ops.get_all_versions(online_devices, username, password))

    # Map (ip, version) tuples back to the dataframe by IP address
    version_map = {ip: version for ip, version in results}
    valid_devices_df['Current IOS Version'] = valid_devices_df['OOBM IP Address'].map(version_map)


# DETERMINE IF THE DEVICE NEEDS AN UPDATE
# ---------------------------------------
def populate_needs_update_column(valid_devices_df):

    """
    PURPOSE
    -------
    Compares the current IOS version against the recommended IOS version
    for each device, and stores the result in the 'Needs Update' column.


    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): DataFrame containing 'Current IOS Version' and 'Recommended IOS Version' columns.


    RETURN VALUE
    ------------
    None - modifies valid_devices_df in place via .at[] assignment.
    """

    for index, row in valid_devices_df.iterrows():

        hostname = row['Hostname']
        current_version = row['Current IOS Version']
        recommended_version = row['Recommended IOS Version']

        # Skip rows where either value is missing
        if pd.isna(current_version) or pd.isna(recommended_version):
            valid_devices_df.at[index, 'Needs Update'] = 'UNKNOWN'
            continue
        
        # Normalize the strings so the 0s in front of each digit don't make it look like they are different versions
        current_version = common_helper_functions.normalize_ios_version_string(current_version)
        recommended_version = common_helper_functions.normalize_ios_version_string(recommended_version)
        
        # Write NO if versions match, YES if they differ
        if current_version == recommended_version:
            valid_devices_df.at[index, 'Needs Update'] = 'NO'
            #--------------------------------------------------------------------
            logger.info(f"'{hostname}': up to date (current: {current_version})")
            #--------------------------------------------------------------------
        else:
            valid_devices_df.at[index, 'Needs Update'] = 'YES'
            #-----------------------------------------------------------------------------------------------
            logger.info(f"'{hostname}': needs update (current: {current_version} to {recommended_version})")
            #-----------------------------------------------------------------------------------------------


# GET THE RECOMMENDED IOS IMAGE FILE PATH
# ---------------------------------------
def valid_devices_df_with_image_path(valid_devices_df):

    """
    PURPOSE
    -------
    Locates the IOS image file for each device in the DataFrame by matching
    the recommended IOS version against files in the model-specific subfolder
    of the IOS image repository. Adds the absolute path of the matched image
    as a new 'IOS Image Path' column.


    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): DataFrame containing at minimum 'Model' and 'Recommended IOS Version' columns.


    RETURN VALUE
    ------------
    None - modifies valid_devices_df in place via .at[] assignment.
    """

    # First, lets retrieve the absolute path of the folder that contains all the subfolders of the IOS images
    ios_image_repository_path = common_helper_functions.get_absolute_path('ios_repository')

    # Iterate over each DataFrame row
    for index, row in valid_devices_df.iterrows():

        # Device doesn't need an update (it can also be that it failed to retrieve current version, or missing recommended one) — image path lookup is irrelevant
        if row['Needs Update'] in ('NO', 'UNKNOWN'):
            valid_devices_df.at[index, 'IOS Image Path'] = None # keep things simple, don's use N/A
            valid_devices_df.at[index, 'Update IOS File Present'] = 'N/A' # we want to let the user know in the EXCEL
            continue

        model = row['Model'] # we will use this variable to locate the folder with the IOS images for such model
        recommended_version = row['Recommended IOS Version'] # we will use this variable to locate the exact IOS image within the model folder

        # Build the path to the model-specific subfolder
        model_folder_path = os.path.join(ios_image_repository_path, model)

        # Check the model folder exists
        if not os.path.isdir(model_folder_path):
            #---------------------------------------------------------------------------
            logger.warning(f"Model folder not found for '{model}': {model_folder_path}")
            #---------------------------------------------------------------------------
            # When this continue fires, execution jumps to the next iteration of the for index, row loop. The if ios_image_path / else block at the bottom 
            # never runs for this device — so 'IOS Image Path' and 'Update IOS File Present' are never set for it. Fix:
            valid_devices_df.at[index, 'IOS Image Path'] = None
            valid_devices_df.at[index, 'Update IOS File Present'] = 'NO'
            continue
        
        # Search for the IOS image file whose name contains the recommended version string
        ios_image_path = None
        for file in os.listdir(model_folder_path):
            # The version in the filename (17.15.04c) uses a different format than what RESTCONF returns (17.15.4c) — note the zero-padded 04 vs 4. 
            # So a direct string match won't always work. The safest approach is to normalize both strings before comparing — strip leading zeros 
            # from each numeric segment:
            if common_helper_functions.normalize_ios_version_string(recommended_version) in common_helper_functions.normalize_ios_version_string(file):
                ios_image_path = os.path.join(model_folder_path, file)
                break

        if ios_image_path:
            #----------------------------------------------------------------------------------------
            logger.info(f"IOS image found for '{model}' - '{recommended_version}': {ios_image_path}")
            #----------------------------------------------------------------------------------------
            valid_devices_df.at[index, 'IOS Image Path'] = ios_image_path
            valid_devices_df.at[index, 'Update IOS File Present'] = 'YES' 

        else:
            #------------------------------------------------------------------------------------------------------------------
            logger.warning(f"No IOS image found for '{model}' matching version '{recommended_version}' in {model_folder_path}")
            #------------------------------------------------------------------------------------------------------------------
            valid_devices_df.at[index, 'Update IOS File Present'] = 'NO'
            valid_devices_df.at[index, 'IOS Image Path'] = None


# GET THE SIZE OF THE IOS IMAGE FILE
# ----------------------------------
def get_image_files_size(valid_devices_df):

    """
    PURPOSE
    -------
    Retrieves the file size in bytes of each IOS image file referenced
    in the DataFrame, for rows that have their "Needs Update" value set to YES,
    and stores the result in a new 'IOS Image Size' column. 
    Rows with a None value in 'IOS Image Path' are skipped.


    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): DataFrame containing an 'IOS Image Path' column with absolute paths to the IOS image files.


    RETURN VALUE
    ------------
    None - modifies valid_devices_df in place via .at[] assignment.
    """

    # Only retrieve image size for devices that need an update
    devices_needing_update = valid_devices_df[valid_devices_df['Needs Update'] == 'YES']

    # Note that we are using the original index values from valid_devices_df — iterrows() preserves the original index.
    for index, row in devices_needing_update.iterrows():

        image_path = row['IOS Image Path']

        # We can safely skip rows where the image path was not resolved
        if pd.isna(image_path):
            #---------------------------------------------------------------------------
            logger.warning(f"Skipping '{row['Hostname']}': no IOS image path available")
            #---------------------------------------------------------------------------
            valid_devices_df.at[index, 'IOS Image Size'] = None
            continue

        # Check the file actually exists before attempting to read its size
        if not os.path.isfile(image_path):
            #------------------------------------------------------------------------------
            logger.warning(f"Skipping '{row['Hostname']}': file not found at {image_path}")
            #------------------------------------------------------------------------------
            valid_devices_df.at[index, 'IOS Image Size'] = None
            continue

        # Get the file size in bytes
        image_size = os.path.getsize(image_path)
        #---------------------------------------------------------------------------------------------------
        logger.info(f"Image size for '{row['Hostname']}': {image_size / (1024*1024):.0f} MB - {image_path}")
        #---------------------------------------------------------------------------------------------------

        # Populate the column
        valid_devices_df.at[index, 'IOS Image Size'] = image_size


# GET AND SET THE FLASH FREE SPACE
# --------------------------------
def populate_flash_free_space_column(valid_devices_df, username, password):
    """
    PURPOSE
    -------
    Runs the async flash free space retrieval, then maps the results
    back into the DataFrame as a new 'Flash Free Space' column.


    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): DataFrame containing at minimum 'OOBM IP Address' column.
    username         (str):          Device username for RESTCONF authentication.
    password         (str):          Device password for RESTCONF authentication.


    RETURN VALUE
    ------------
    None - modifies valid_devices_df in place via .at[] assignment. 
    """

    # Only query flash space for devices that need an update
    devices_needing_update = valid_devices_df[valid_devices_df['Needs Update'] == 'YES']
    
    # Use your threaded function instead of asyncio
    results = device_cli_ops.get_flash_free_space_all(
        devices_needing_update,
        username,
        password
    )

    # Map (ip, free_bytes) tuples back to the dataframe. Then .map() looks up each row's OOBM IP Address value in that dictionary. 
    # So even if the async results came back in a completely random order, the correct value would still land on the correct row
    free_space_map = {ip: free_space for ip, free_space in results}
    valid_devices_df['Flash Free Space'] = valid_devices_df['OOBM IP Address'].map(free_space_map)
    
    # NOTE: Devices that need an update get their value from free_space_map, and devices that don't need an update get NaN from .map() (since their IP won't be in the map)


# DETERMINE IF FLASH FREE SPACE IS ENOUGH
# ---------------------------------------
def populate_enough_space_column(valid_devices_df):

    """
    PURPOSE
    -------
    Compares the available flash free space against the IOS image file size
    for each device, and stores the result in an existent 'Enough Flash Space' column.


    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): DataFrame containing 'Flash Free Space' and 'IOS Image Size' columns.


    RETURN VALUE
    ------------
    None - modifies valid_devices_df in place via .at[] assignment.
    """

    # Iterate over each device row
    for index, row in valid_devices_df.iterrows():

        # Device doesn't need an update — flash space check is irrelevant
        if row['Needs Update'] in ('NO', 'UNKNOWN'):
            valid_devices_df.at[index, 'Enough Flash Space'] = 'N/A'
            continue

        # Retrieve the flash free space and image size for this device
        free_space = row['Flash Free Space']
        image_size = row['IOS Image Size']

        # Skip rows where either value is missing — can't compare if data is incomplete
        if pd.isna(free_space) or pd.isna(image_size):
            valid_devices_df.at[index, 'Enough Flash Space'] = "UNKNOWN"
            continue
        
        # Write YES if free space exceeds image size, NO otherwise.
        valid_devices_df.at[index, 'Enough Flash Space'] = 'YES' if free_space > image_size else 'NO'


# # POPULATE THE SCP ENABLED COLUMN (going away most likely)
# # -------------------------------------
# def populate_scp_enabled_column(valid_devices_df, username, password):

#     """
#     PURPOSE
#     -------
#     Checks SCP server status for all online devices and populates the 'SCP Enabled' column.


#     ARGUMENTS
#     ---------
#     valid_devices_df (pd.DataFrame): DataFrame containing at minimum 'OOBM IP Address' column.
#     username         (str):          Device username for RESTCONF authentication.
#     password         (str):          Device password for RESTCONF authentication.


#     RETURN VALUE
#     ------------
#     None - modifies valid_devices_df in place via .map() assignment.
#     """

#     # Only check SCP for devices where RESTCONF is confirmed operative —
#     # the SCP check hits a RESTCONF endpoint, so ONLINE alone is not sufficient
#     operative_devices = valid_devices_df[valid_devices_df['RESTCONF Status'] == 'OPERATIVE']

#     results = asyncio.run(device_api_ops.get_all_scp_status(operative_devices, username, password))

#     # Map results back to the dataframe by IP address
#     scp_map = {ip: scp_status for ip, scp_status in results}
#     valid_devices_df['SCP Enabled'] = valid_devices_df['OOBM IP Address'].map(scp_map)

#     # Offline devices get "UNKNOWN" — SCP check is irrelevant
#     valid_devices_df.loc[valid_devices_df['Status'] == 'OFFLINE', 'SCP Enabled'] = 'UNKNOWN'


# GET ELEGIBLE DEVICES FOR UPDATE
# -------------------------------
def get_eligible_devices_df(valid_devices_df):

    """
    PURPOSE
    -------
    Filters the DataFrame to only include devices that are eligible for
    an IOS update — online, sufficient flash space, valid image path,
    and flagged as needing an update.


    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): DataFrame containing 'Status','Auth Status,
    'Enough Flash Space', 'IOS Image Path', 'SCP Enabled' and 'Needs Update' columns.


    RETURN VALUE
    ------------
    New DataFrame containing only eligible devices.
    """

    # Apply conditions for elegibility
    eligible_mask = (
        (valid_devices_df['Status'] == 'ONLINE')                &   # Device responded to SSH — reachable and alive
        (valid_devices_df['RESTCONF Status'] == 'OPERATIVE')    &   # Device responded to the test API call
        (valid_devices_df['Current IOS Version'].notna())       &   # Current IOS version was successfully retrieved from the device
        (valid_devices_df['Enough Flash Space'] == 'YES')       &   # Sufficient flash space available to store the image
        (valid_devices_df['IOS Image Path'].notna())            &   # A matching IOS image file was found in the local repository
        (valid_devices_df['IOS Image Size'].notna())            &   # Image file size was successfully read from disk
        (valid_devices_df['Needs Update'] == 'YES')                 # Current version differs from the recommended version
    )

    # Define the elegible devices out of the argumented DataFrame
    eligible_devices_df = valid_devices_df[eligible_mask].copy()

    #------------------------------------------------------------------------------------------------------------------------
    logger.info(f"{len(eligible_devices_df)} device(s) eligible for IOS update out of {len(valid_devices_df)} valid devices")
    #------------------------------------------------------------------------------------------------------------------------

    return eligible_devices_df


# USER SELECTION OF ELEGIBLE DEVICES
# ----------------------------------
def select_devices_for_update(eligible_devices_df):
    """
    PURPOSE
    -------
    Prompts the user to select which eligible devices to push the IOS update to,
    by entering their DataFrame index numbers. Returns a new DataFrame containing
    only the selected devices.


    ARGUMENTS
    ---------
    eligible_devices_df (pd.DataFrame): DataFrame containing only eligible devices.


    RETURN VALUE
    ------------
    New DataFrame containing only the user-selected devices.
    """

    # Show the user the eligible devices and their indexes (showing is done in the main_execution_program)
    print("\nEnter the indexes of the devices you want to update, separated by commas (e.g. 0,1,3):")
    raw_input = input("> ").strip()

    try:
        # Parse the input into a list of integers
        selected_indexes = [int(i.strip()) for i in raw_input.split(',')]
    except ValueError:
        #--------------------------------------------------------------------------------
        logger.error(f"Invalid input: '{raw_input}' — expected comma-separated integers")
        #--------------------------------------------------------------------------------
        return None

    # Filter to only the rows whose index matches the user selection
    selected_elegible_devices_df = eligible_devices_df.loc[
        eligible_devices_df.index.isin(selected_indexes)
    ].copy()

    if selected_elegible_devices_df.empty:
        #-------------------------------------------------------------------------
        logger.error(f"No matching devices found for indexes: {selected_indexes}")
        #-------------------------------------------------------------------------
        return None

    #----------------------------------------------------------------------------------------------------
    logger.info(f"{len(selected_elegible_devices_df)} device(s) selected for update: {selected_indexes}")
    #----------------------------------------------------------------------------------------------------

    return selected_elegible_devices_df


# POPULATE THE TRANSFER STATUS COLUMN
# ------------------------------------
def populate_transfer_status_column(valid_devices_df, selected_eligible_devices_df, username, password):

    """
    PURPOSE
    -------
    Calls transfer_ios_image() for each selected eligible device and populates
    the 'Transfer Status' column in valid_devices_df with the return code.
    Prompts the user to choose between sequential and threaded transfer modes
    before starting. Devices not selected for transfer are marked as 'NOT_ATTEMPTED'.


    ARGUMENTS
    ---------
    valid_devices_df              (pd.DataFrame): Full device DataFrame — receives the Transfer Status values.
    selected_eligible_devices_df  (pd.DataFrame): Filtered DataFrame containing only devices selected for update.
    username                      (str):          Device SSH username.
    password                      (str):          Device SSH password.


    RETURN VALUE
    ------------
    None - modifies valid_devices_df in place via .at[] assignment.
    """

    ### <=== MODE SELECTION ===> ###
    # Before starting any transfer, ask the user to choose how transfers will be executed.
    # Sequential is the safe default — one device at a time with a clean progress bar per device.
    # Threaded fires all transfers simultaneously, which is faster at scale but means multiple
    # progress bars will print concurrently and overwrite each other in the terminal.
    print("\nSelect transfer mode:")
    print("  [1] Sequential — one device at a time, live progress bar per device. Slower but safer.")
    print("  [2] Threaded   — all devices concurrently. Faster but progress output will be interleaved.")
    print()

    while True:
        choice = input("Enter 1 or 2: ").strip()
        if choice in ('1', '2'):
            break
        print("Invalid input — please enter 1 or 2.")

    threaded = (choice == '2')

    if threaded:
        print("\n  WARNING: Threaded mode transfers to all devices simultaneously.")
        print("  Progress bars from multiple devices will overlap in the terminal.")
        print("  Check the Transfer Status column in the Excel tracker for individual results.\n")
    else:
        print("\n  Sequential mode selected — devices will be transferred one at a time.\n")


    ### <=== MARK NON-SELECTED DEVICES ===> ###
    # Every device in valid_devices_df that was not part of this transfer run gets
    # NOT_ATTEMPTED — this covers OFFLINE devices, NOT_OPERATIVE devices, devices with
    # insufficient flash space, and eligible devices the user chose not to select.
    # This ensures the Transfer Status column is fully populated for the Excel tracker.
    for index in valid_devices_df.index:
        if index not in selected_eligible_devices_df.index:
            valid_devices_df.at[index, 'Transfer Result'] = 'N/A'


    ### <=== TRANSFER LOGIC ===> ###
    # Nested helper shared by both execution modes. Extracts the parameters needed by
    # transfer_ios_image() from the DataFrame row, calls it, and returns the (index, result)
    # tuple so the caller can write the result back to the correct DataFrame row regardless
    # of execution order — which matters in threaded mode since futures complete out of order.
    def run_transfer(row):
        ip               = row['OOBM IP Address']
        hostname         = row['Hostname']
        local_image_path = row['IOS Image Path']

        # Derive the remote filename from the local path — the file lands on bootflash
        # with the same name it has in the local IOS image repository
        remote_filename  = os.path.basename(local_image_path)

        #-------------------------------------------------------
        logger.info(f"Starting transfer to '{hostname}' ({ip})")
        #-------------------------------------------------------

        result = device_file_transfer_ops.single_transfer_ios_image(
            ip,
            username,
            password,
            local_image_path,
            remote_filename
        )

        #-----------------------------------------------------------------------
        logger.info(f"Transfer Status for '{hostname}' ({ip}) set to: {result}")
        #-----------------------------------------------------------------------

        # Return the original DataFrame index alongside the result so the caller
        # can write back to the correct row in valid_devices_df
        return row.name, result


    ### <=== SEQUENTIAL ===> ###
    # Iterate over selected devices one at a time. Each transfer completes fully
    # before the next one starts — progress bar output is clean and readable.
    if not threaded:
        #----------------------------------------------------
        logger.info("User elected a sequential SCP transfer")
        #----------------------------------------------------
        for _, row in selected_eligible_devices_df.iterrows():
            index, result = run_transfer(row)
            valid_devices_df.at[index, 'Transfer Result'] = result


    ### <=== THREADED ===> ###
    else:
        #--------------------------------------------------
        logger.info("User elected a threaded SCP transfer")
        #--------------------------------------------------
        results = device_file_transfer_ops.threaded_transfer_ios_image_all(
            selected_eligible_devices_df, username, password
        )

        # results is {index: result} — write each back to the correct row
        for index, result in results.items():
            valid_devices_df.at[index, 'Transfer Result'] = result


# GET ELEGIBLE DEVICES FOR INSTALL
# --------------------------------
def get_install_eligible_devices_df(valid_devices_df):

    """
    PURPOSE
    -------
    Filters valid_devices_df to only include devices whose Transfer Result
    is SUCCESS — these are the only devices for which an install is applicable.


    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): Full device DataFrame.
        

    RETURN VALUE
    ------------
    New DataFrame containing only devices with Transfer Status SUCCESS.
    """

    install_eligible_devices_df = valid_devices_df[
        valid_devices_df['Transfer Result'] == 'SUCCESS'
    ].copy()

    #-----------------------------------------------------------------------------------------------------------------------------
    logger.info(f"{len(install_eligible_devices_df)} device(s) eligible for install out of {len(valid_devices_df)} valid devices")
    #-----------------------------------------------------------------------------------------------------------------------------

    return install_eligible_devices_df


# POPULATE THE INSTALL STATUS COLUMN
# ----------------------------------
# Confirm installs before reloading, per device (called by 'populate_install_status_column')
def confirm_installs(install_eligible_devices_df):

    """
    PURPOSE
    -------
    Presents each eligible device to the user one at a time and collects
    explicit YES/NO confirmation before any reload is triggered. Returns
    two separate DataFrames — one for confirmed devices and one for aborted
    ones — so the caller can pass only confirmed devices to install_ios_image_all
    and still record ABORTED in the results for the rest.


    ARGUMENTS
    ---------
    install_eligible_devices_df (pd.DataFrame): Devices eligible for install.


    RETURN VALUE
    ------------
    Tuple of (confirmed_df, aborted_df) — both are subsets of install_eligible_devices_df.
    """

    confirmed_indexes = []
    aborted_indexes   = []

    for idx, row in install_eligible_devices_df.iterrows():

        hostname = row['Hostname']
        ip       = row['OOBM IP Address']
        bin_file = os.path.basename(row['IOS Image Path'])

        print(f"\n  {'='*60}")
        print(f"  WARNING: About to run install on '{hostname}' ({ip})")
        print(f"  Command : install add file bootflash:{bin_file} activate commit")
        print(f"  Effect  : Device will reload. Session will drop.")
        print(f"  {'='*60}")

        while True:
            confirm = input(f"\n  Type 'YES' to proceed with install on '{hostname}', or 'NO' to abort: ").strip().upper()
            if confirm in ('YES', 'NO'):
                break
            print("  Invalid input — please type YES or NO.")

        if confirm == 'YES':
            confirmed_indexes.append(idx)
            #-------------------------------------------------------------
            logger.info(f"'{hostname}' ({ip}): install confirmed by user")
            #-------------------------------------------------------------
        else:
            aborted_indexes.append(idx)
            #--------------------------------------------------------------
            logger.warning(f"'{hostname}' ({ip}): install aborted by user")
            #--------------------------------------------------------------

    confirmed_df = install_eligible_devices_df.loc[confirmed_indexes].copy()
    aborted_df   = install_eligible_devices_df.loc[aborted_indexes].copy()

    #---------------------------------------------------------------------------------------------
    logger.info(f"{len(confirmed_df)} device(s) confirmed for install, {len(aborted_df)} aborted")
    #---------------------------------------------------------------------------------------------

    return confirmed_df, aborted_df

def populate_install_status_column(valid_devices_df, install_eligible_devices_df, username, password):

    """
    PURPOSE
    -------
    Orchestrates the full install sequence for all eligible devices:

        1. Populates the 'Install Status' column in valid_devices_df with the result
           for every device — confirmed, aborted, and not attempted
        1. Collects per-device confirmation from the user before any reload is triggered.
        3. Fires the install command concurrently on all confirmed devices.


    ARGUMENTS
    ---------
    valid_devices_df            (pd.DataFrame): Full device DataFrame — receives Install Status values.
    install_eligible_devices_df (pd.DataFrame): Devices eligible for install — Transfer Status
                                                SUCCESS and all eligibility conditions met.
    username                    (str):          Device SSH username.
    password                    (str):          Device SSH password.


    RETURN VALUE
    ------------
    None - modifies valid_devices_df in place via .at[] assignment.
    """

    ### <=== MARK NON-ELIGIBLE DEVICES ===> ###
    # Every device that was not part of this install run gets NOT_ATTEMPTED —
    # covers OFFLINE, NOT_OPERATIVE, insufficient flash, transfer failures,
    # and devices that never reached the eligibility check.
    for index in valid_devices_df.index:
        if index not in install_eligible_devices_df.index:
            valid_devices_df.at[index, 'Install Status'] = 'NOT_ATTEMPTED'


    ### <=== COLLECT CONFIRMATIONS ===> ###
    # All user confirmations are gathered upfront — before any thread is spawned —
    # so that install prompts never interleave with each other in the terminal.
    confirmed_df, aborted_df = confirm_installs(install_eligible_devices_df)


    ### <=== RECORD ABORTED DEVICES ===> ###
    # Write ABORTED immediately for devices the user declined — these never reach
    # the install function so their status would otherwise remain unpopulated.
    for idx in aborted_df.index:
        valid_devices_df.at[idx, 'Install Status'] = 'ABORTED'
        

    ### <=== FIRE INSTALLS ON CONFIRMED DEVICES ===> ###
    # Pass only confirmed devices to the threaded install function.
    # Returns {index: result} — one entry per device.
    if not confirmed_df.empty:
        install_results = device_cli_ops.install_ios_image_all(confirmed_df, username, password)

        for index, result in install_results.items():
            # Devices skipped due to failed transfer get N/A — install was never applicable
            valid_devices_df.at[index, 'Install Status'] = result
    else:
        #--------------------------------------------------------------------------
        logger.warning("No devices confirmed for install — skipping install phase")
        #--------------------------------------------------------------------------


# POPULATE INSTALLED VERSION AND UPDATE RESULT COLUMNS
# -----------------------------------------------------
def populate_post_install_columns(valid_devices_df, install_eligible_devices_df, username, password):

    """
    PURPOSE
    -------
    Executes the post-reboot sequence for all devices that had an install
    triggered:

        1. Marks devices not part of the install run as N/A immediately.
        2. Waits 5 minutes for devices to complete their reload.
        3. Polls RESTCONF on all INSTALL_TRIGGERED devices for up to 5 minutes
           to determine if they came back online.
        4. Marks timed-out devices as UNKNOWN for both columns.
        5. Runs 'install commit' concurrently on all online devices.
        6. Retrieves the running version via RESTCONF and compares against
           the recommended version, populating both columns accordingly.


    ARGUMENTS
    ---------
    valid_devices_df            (pd.DataFrame): Full device DataFrame — receives column values.
    install_eligible_devices_df (pd.DataFrame): Devices that were part of the install run.
    username                    (str):          Device username.
    password                    (str):          Device password.


    RETURN VALUE
    ------------
    None - modifies valid_devices_df in place via .at[] assignment.
    """

    ### <=== MARK NON-INSTALL DEVICES IMMEDIATELY ===> ###
    # Devices that were never part of the install run get N/A for both columns
    # upfront — no need to wait for them.
    for index in valid_devices_df.index:
        if index not in install_eligible_devices_df.index:
            valid_devices_df.at[index, 'Installed Version'] = 'N/A'
            valid_devices_df.at[index, 'Update Result']     = 'N/A'


    ### <=== FILTER TO INSTALL_TRIGGERED DEVICES ONLY ===> ###
    # Only devices that actually had the install command sent are relevant —
    # aborted devices are in install_eligible_devices_df but never reloaded
    # so they should not be polled.
    triggered_devices = valid_devices_df[
        valid_devices_df['Install Status'] == 'INSTALL_TRIGGERED'
    ]

    if triggered_devices.empty:
        #---------------------------------------------------------------------------
        logger.warning("No INSTALL_TRIGGERED devices found — skipping post-install")
        #---------------------------------------------------------------------------
        return


    ### <=== INITIAL SLEEP — WAIT FOR RELOAD TO COMPLETE ===> ###
    # Give devices 5 minutes to complete the reload before starting to poll.
    # Install mode upgrades can take several minutes to finish booting. This
    # timer starts when the last device is marked with "INSTALL_TRIGGERED"
    #-----------------------------------------------------------------
    logger.info("Waiting 5 minutes for devices to complete reload...")
    #-----------------------------------------------------------------
    time.sleep(360)


    ### <=== POLL RESTCONF TO CHECK IF DEVICES ARE BACK ONLINE ===> ###
    # Use the existing wait_for_restconf() with a 53 minute timeout and 15 second
    # interval — returns {ip: True/False} for each triggered device.
    #-------------------------------------------------------------------------------------------
    logger.info("Polling RESTCONF to check if devices are back online (timeout: 10 minutes)...")
    #-------------------------------------------------------------------------------------------

    restconf_results = asyncio.run(
        device_api_ops.get_all_restconf_status(triggered_devices, username, password, 600, 15)
    )

    # Split triggered devices into those that came back up and those that timed out
    online_indexes  = []
    timeout_indexes = []

    for index, row in triggered_devices.iterrows():
        ip = row['OOBM IP Address']
        if restconf_results.get(ip):
            online_indexes.append(index)
        else:
            timeout_indexes.append(index)
            #------------------------------------------------------------------------------
            logger.error(f"'{row['Hostname']}' ({ip}): did not come back online — timeout")
            #------------------------------------------------------------------------------

    # Devices that timed out get UNKNOWN for both columns
    for index in timeout_indexes:
        valid_devices_df.at[index, 'Installed Version'] = 'UNKNOWN'
        valid_devices_df.at[index, 'Update Result']     = 'UNKNOWN'


    ### <=== RUN INSTALL COMMIT ON ALL ONLINE DEVICES ===> ###
    online_devices_df = triggered_devices.loc[online_indexes]

    if online_devices_df.empty:
        #--------------------------------------------------------------------------------
        logger.warning("No devices came back online — skipping commit and version check")
        #--------------------------------------------------------------------------------
        return

    # Returns {index: result} — one entry per device
    commit_results = device_cli_ops.commit_ios_install_all(online_devices_df, username, password)


    ### <=== RETRIEVE RUNNING VERSION AND POPULATE COLUMNS ===> ###
    version_results = asyncio.run(device_api_ops.get_all_versions(online_devices_df, username, password))
    version_map     = {ip: version for ip, version in version_results}

    for index, row in online_devices_df.iterrows():

        ip                  = row['OOBM IP Address']
        hostname            = row['Hostname']
        installed_version   = version_map.get(ip)
        recommended_version = row['Recommended IOS Version']
        commit_result       = commit_results.get(index, 'UNEXPECTED_ERROR')

        # Version retrieval failed — could not confirm running version
        if not installed_version:
            valid_devices_df.at[index, 'Installed Version'] = 'UNKNOWN'
            valid_devices_df.at[index, 'Update Result']     = 'UNKNOWN'
            #--------------------------------------------------------------------------
            logger.error(f"'{hostname}' ({ip}): version retrieval failed after commit")
            #--------------------------------------------------------------------------
            continue

        valid_devices_df.at[index, 'Installed Version'] = installed_version

        # Normalize both version strings before comparing to handle zero-padded
        # segments — '17.15.04c' and '17.15.4c' must be treated as equal
        installed_normalized   = common_helper_functions.normalize_ios_version_string(installed_version)
        recommended_normalized = common_helper_functions.normalize_ios_version_string(recommended_version)

        if installed_normalized != recommended_normalized:
            #----------------------------------------------------------------------------------------------------------------
            logger.warning(f"'{hostname}': version mismatch — installed {installed_version}, expected {recommended_version}")
            #----------------------------------------------------------------------------------------------------------------
            valid_devices_df.at[index, 'Update Result'] = 'FAILED'

        elif commit_result != 'COMMIT_SUCCESS':
            #-----------------------------------------------------------------------------------
            logger.warning(f"'{hostname}': version matches but commit failed — {commit_result}")
            #-----------------------------------------------------------------------------------
            valid_devices_df.at[index, 'Update Result'] = 'COMMIT_FAILED'

        else:
            #----------------------------------------------------------------------------------------------
            logger.info(f"'{hostname}': update successful — running {installed_version}, commit confirmed")
            #----------------------------------------------------------------------------------------------
            valid_devices_df.at[index, 'Update Result'] = 'SUCCESS'


# POPULATE THE CLEANED INACTIVE COLUMN
# -------------------------------------
def populate_cleaned_inactive_column(valid_devices_df, username, password):

    """
    PURPOSE
    -------
    Runs 'install remove inactive' concurrently on all devices whose Install
    Status is INSTALL_TRIGGERED and populates the 'Cleaned Inactive' column
    in valid_devices_df with the return code. Devices not eligible for cleanup
    are marked as N/A.


    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): Full device DataFrame — receives Cleaned Inactive values.
    username         (str):          Device SSH username.
    password         (str):          Device SSH password.


    RETURN VALUE
    ------------
    None - modifies valid_devices_df in place via .at[] assignment.
    """

    # Returns {index: result} — N/A for non-triggered devices, return code for triggered ones
    results = device_cli_ops.remove_inactive_ios_all(valid_devices_df, username, password)

    for index, result in results.items():
        valid_devices_df.at[index, 'Cleaned Inactive'] = result


# UPDATE THE EXCEL TRACKER
# ------------------------
def update_excel_tracker(excel_file, excel_sheet_name, valid_devices_df):

    """
    PURPOSE
    -------
    Opens an existing Excel workbook and updates the columns that host dynamic data
    for each device whose hostname matches an entry in the provided DataFrame.

    
    ARGUMENTS
    ---------
    excel_file       (str):            Absolute path to the Excel (.xlsx) file.
    excel_sheet_name (str):            Name of the worksheet to update.
    valid_devices_df (pd.DataFrame): DataFrame containing pertinent columns

    
    RETURN VALUE
    ------------
    If successful, it returns a success code. Otherways, it returns an error code

    """

    # Initialize the variable
    workbook = None

    try:
        # Open the existing workbook and select the target worksheet
        workbook = load_workbook(excel_file) 
        worksheet = workbook[excel_sheet_name]

        # Find column indexes for all dynamic columns
        hostname_col_index = -1
        current_ios_col_index = -1
        status_col_index = -1
        auth_status_col_index = -1
        enough_flash_space_col_index = -1
        needs_update_col_index = -1
        update_ios_file_present_col_index = -1
        transfer_status_col_index = -1
        install_status_col_index = -1
        update_result_col_index = -1
        cleaned_inactive_col_index = -1

        # Scan header row (row 1) to locate the relevant column indexes by name
        for column in range(1, worksheet.max_column + 1):
            header = worksheet.cell(row=1, column=column).value
            if header == "Hostname":
                hostname_col_index = column
            if header == "Current IOS Version":
                current_ios_col_index = column
            if header == "Status":
                status_col_index = column
            if header == "Auth Status":
                auth_status_col_index  = column
            if header == "Enough Flash Space":
                enough_flash_space_col_index = column
            if header == "Needs Update":
                needs_update_col_index = column
            if header == "Update IOS File Present":
                update_ios_file_present_col_index = column
            if header == "Transfer Result":
                transfer_status_col_index = column
            if header == "Install Status":
                install_status_col_index = column
            if header == "Update Result":
                 update_result_col_index = column
            if header == "Cleaned Inactive":
                cleaned_inactive_col_index = column

        # Build lookup dicts from the dataframe: {hostname: currrent_version}, ...
        version_lookup = dict(zip(valid_devices_df['Hostname'], valid_devices_df['Current IOS Version']))
        status_lookup = dict(zip(valid_devices_df['Hostname'], valid_devices_df['Status']))
        auth_status_lookup = dict(zip(valid_devices_df['Hostname'], valid_devices_df['Auth Status']))
        enough_flash_space_lookup = dict(zip(valid_devices_df['Hostname'], valid_devices_df['Enough Flash Space']))
        needs_update_lookup = dict(zip(valid_devices_df['Hostname'], valid_devices_df['Needs Update']))
        update_ios_file_present_lookup = dict(zip(valid_devices_df['Hostname'], valid_devices_df['Update IOS File Present']))
        transfer_status_lokup = dict(zip(valid_devices_df['Hostname'], valid_devices_df['Transfer Result']))
        install_status_col_lookup = dict(zip(valid_devices_df['Hostname'], valid_devices_df['Install Status']))
        update_result_lookup = dict(zip(valid_devices_df['Hostname'], valid_devices_df['Update Result']))
        cleaned_inactive_lookup = dict(zip(valid_devices_df['Hostname'], valid_devices_df['Cleaned Inactive']))

        # Iterate over Excel rows and update only matching hostnames
        for row in range(2, worksheet.max_row + 1):
            hostname = worksheet.cell(row=row, column=hostname_col_index).value
            # If the hostname exists in the dataframe, overwrite all dynamic columns
            if hostname in version_lookup:
                worksheet.cell(row=row, column=current_ios_col_index, value=version_lookup[hostname])
                worksheet.cell(row=row, column=status_col_index, value=status_lookup[hostname])
                worksheet.cell(row=row, column=auth_status_col_index, value=auth_status_lookup[hostname])
                worksheet.cell(row=row, column=enough_flash_space_col_index, value=enough_flash_space_lookup[hostname])
                worksheet.cell(row=row, column=needs_update_col_index, value=needs_update_lookup[hostname])
                worksheet.cell(row=row, column=update_ios_file_present_col_index, value=update_ios_file_present_lookup[hostname])
                worksheet.cell(row=row, column=transfer_status_col_index, value=transfer_status_lokup[hostname])
                worksheet.cell(row=row, column=install_status_col_index, value=install_status_col_lookup[hostname])
                worksheet.cell(row=row, column=update_result_col_index, value=update_result_lookup[hostname])
                worksheet.cell(row=row, column=cleaned_inactive_col_index, value=cleaned_inactive_lookup[hostname])

        # Save the workbook back to disk, persisting all cell changes
        workbook.save(excel_file)
        #-------------------------------------------
        logger.info(f"Updating EXCEL file succeded")
        #-------------------------------------------
        return "SUCCESS"
        
    except Exception as e:

        if isinstance(e, PermissionError):
            #-----------------------------------------------------------------------------------------------------
            logger.error(f"Updating EXCEL file failed: Could not save the file, please ensure the file is closed")
            #-----------------------------------------------------------------------------------------------------
            return "PERMISSION_DENIED_ERROR"
        
        else:
            #-----------------------------------------------------------------------------
            logger.error(f"Updating EXCEL file failed: an unexpected error occured - {e}")
            #-----------------------------------------------------------------------------
            return "UNEXPECTED_ERROR"
    
    finally:
        if workbook:
            workbook.close()
            #------------------------------------------------------------
            logger.info(f"The EXCEL file has been closed by the program")
            #------------------------------------------------------------


# CHECK IF EXCEL FILE IS OPEN
# ---------------------------
def check_excel_file_not_open(excel_file):
    """
    PURPOSE
    -------
    Checks if the Excel file is currently open by another process.
    If it is, logs an error and terminates the program.


    ARGUMENTS
    ---------
    excel_file (str): Absolute path to the Excel (.xlsx) file.


    RETURN VALUE
    ------------
    None - terminates the program via sys.exit() if the file is open.
    """

    # Iterate over all running processes, retrieving their PID, name, and open file handles
    for process in psutil.process_iter(['pid', 'name', 'open_files']):

        try:
            # Iterate over the files currently open by this process (default to empty list if None)
            for open_file in process.info['open_files'] or []:
                # Case-insensitive check to see if the Excel file path matches any open file
                if excel_file.lower() in open_file.path.lower():
                    #---------------------------------------------------------------------------------------------------------------------------------------------
                    logger.error(f"EXCEL file is currently open by '{process.info['name']}' (PID {process.info['pid']}) - please close it and re-run the program")
                    #---------------------------------------------------------------------------------------------------------------------------------------------
                    # Stop the program — file must be closed before proceeding
                    sys.exit(1)

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process may have died mid-iteration or denied access to its file list — skip it
            continue