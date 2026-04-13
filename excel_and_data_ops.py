# Data manipulation library; used to read Excel files into DataFrames and perform row/column operations
import pandas as pd

# Standard library module for writing and running asynchronous concurrent code
import asyncio

# Standard library to perform operations with files and folders
import os

# Standard library module for interacting with the Python interpreter (used here for sys.exit())
import sys

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
    for col in ['Current IOS Version', 'Needs Update', 'Update IOS File Present', 'Enough Flash Space', 'Status']:
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
  

# POPULATE THE STATUS COLUMN
# --------------------------
def populate_status_column(valid_devices_df, username, password):
    """
    PURPOSE
    -------
    Enables RESTCONF, SCP and HTTPS on all devices and populates the
    'Status' column with ONLINE or OFFLINE based on the result.


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

    # Write ONLINE or OFFLINE back to the dataframe for each device
    for index, status in results:
        valid_devices_df.at[index, 'Status'] = status

        
# POPULATE CURRENT VERSION COLUMN
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
    online_devices = valid_devices_df[valid_devices_df['Status'] == 'ONLINE']
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
        valid_devices_df.at[index, 'Needs Update'] = 'NO' if current_version == recommended_version else 'YES'


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
    
    results = asyncio.run(device_api_ops.get_all_flash_free_space(devices_needing_update, username, password))

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


# POPULATE THE SCP ENABLED COLUMN
# -------------------------------
def populate_scp_enabled_column(valid_devices_df, username, password):

    """
    PURPOSE
    -------
    Checks SCP server status for all online devices and populates the 'SCP Enabled' column.


    ARGUMENTS
    ---------
    valid_devices_df (pd.DataFrame): DataFrame containing at minimum 'OOBM IP Address' column.
    username         (str):          Device username for RESTCONF authentication.
    password         (str):          Device password for RESTCONF authentication.


    RETURN VALUE
    ------------
    None - modifies valid_devices_df in place via .map() assignment.
    """

    # Only check SCP for online devices
    online_devices = valid_devices_df[valid_devices_df['Status'] == 'ONLINE']

    results = asyncio.run(device_api_ops.get_all_scp_status(online_devices, username, password))

    # Map results back to the dataframe by IP address
    scp_map = {ip: scp_status for ip, scp_status in results}
    valid_devices_df['SCP Enabled'] = valid_devices_df['OOBM IP Address'].map(scp_map)

    # Offline devices get "UNKNOWN" — SCP check is irrelevant
    valid_devices_df.loc[valid_devices_df['Status'] == 'OFFLINE', 'SCP Enabled'] = 'UNKNOWN'


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
    valid_devices_df (pd.DataFrame): DataFrame containing 'Status', 'Enough Flash Space', 
    'IOS Image Path', 'SCP Enabled' and 'Needs Update' columns.


    RETURN VALUE
    ------------
    New DataFrame containing only eligible devices.
    """

    # Apply conditions for elegibility
    eligible_mask = (
        (valid_devices_df['Status'] == 'ONLINE')            &   # Device responded to RESTCONF — reachable and alive
        (valid_devices_df['Enough Flash Space'] == 'YES')   &   # Sufficient flash space available to store the image
        (valid_devices_df['IOS Image Path'].notna())        &   # A matching IOS image file was found in the local repository
        (valid_devices_df['IOS Image Size'].notna())        &   # Image file size was successfully read from disk
        (valid_devices_df['Current IOS Version'].notna())   &   # Current IOS version was successfully retrieved from the device
        (valid_devices_df['SCP Enabled'] == 'YES')          &   # SCP server is enabled on the device
        (valid_devices_df['Needs Update'] == 'YES')             # Current version differs from the recommended version
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
    valid_devices_df (pd.DataFrame): DataFrame containing 'Hostname', 'Current IOS Version', 
    'Status', 'Enough Flash Space', 'Needs Update', and 'Update IOS File Present' columns.

    
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
        enough_flash_space_col_index = -1
        needs_update_col_index = -1
        update_ios_file_present_col_index = -1

        # Scan header row (row 1) to locate the relevant column indexes by name
        for column in range(1, worksheet.max_column + 1):
            header = worksheet.cell(row=1, column=column).value
            if header == "Hostname":
                hostname_col_index = column
            if header == "Current IOS Version":
                current_ios_col_index = column
            if header == "Status":
                status_col_index = column
            if header == "Enough Flash Space":
                enough_flash_space_col_index = column
            if header == "Needs Update":
                needs_update_col_index = column
            if header == "Update IOS File Present":
                update_ios_file_present_col_index = column
        
        # Build lookup dicts from the dataframe: {hostname: currrent_version}, ...
        version_lookup = dict(zip(valid_devices_df['Hostname'], valid_devices_df['Current IOS Version']))
        status_lookup = dict(zip(valid_devices_df['Hostname'], valid_devices_df['Status']))
        enough_flash_space_lookup = dict(zip(valid_devices_df['Hostname'], valid_devices_df['Enough Flash Space']))
        needs_update_lookup = dict(zip(valid_devices_df['Hostname'], valid_devices_df['Needs Update']))
        update_ios_file_present_lookup = dict(zip(valid_devices_df['Hostname'], valid_devices_df['Update IOS File Present']))

        # Iterate over Excel rows and update only matching hostnames
        for row in range(2, worksheet.max_row + 1):
            hostname = worksheet.cell(row=row, column=hostname_col_index).value
            # If the hostname exists in the dataframe, overwrite all dynamic columns
            if hostname in version_lookup:
                worksheet.cell(row=row, column=current_ios_col_index, value=version_lookup[hostname])
                worksheet.cell(row=row, column=status_col_index, value=status_lookup[hostname])
                worksheet.cell(row=row, column=enough_flash_space_col_index, value=enough_flash_space_lookup[hostname])
                worksheet.cell(row=row, column=needs_update_col_index, value=needs_update_lookup[hostname])
                worksheet.cell(row=row, column=update_ios_file_present_col_index, value=update_ios_file_present_lookup[hostname])

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