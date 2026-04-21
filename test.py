# Local module: provides data manipulation functions with DataFrames and EXCEL
import excel_and_data_ops

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

#------------------------------
logger.info("STARTING PROGRAM")
#------------------------------

###################################################################################################################################

# PART 1: VALID DEVICES AND EXCEL UPDATE
# --------------------------------------

#---------------------------------------------------------------------------
logger.info("PART 1: Checking Elegible Devices and updating the EXCEL file")
#---------------------------------------------------------------------------

username = "admin"
password = 'Taco23%!ab'

# Get the absolute path of the EXCEL file
excel_file = 'LAN_Network_Devices.xlsx'
excel_sheet_name = 'LAB_NETAUTO001'

# Check that the EXCEL file is closed before continuing — aborts if file is locked
excel_and_data_ops.check_excel_file_not_open(excel_file)

# Read the Excel sheet into a DataFrame with all devices
all_devices_df = excel_and_data_ops.create_devices_dataframe(excel_file, excel_sheet_name)

# Filter out rows with missing critical fields (Hostname, IP Address)
valid_devices_df = excel_and_data_ops.valid_devices_dataframe(all_devices_df)

# Popluate the STATUS column and AUTH STATUS of the DataFrame.
excel_and_data_ops.populate_status_and_auth_status_column(valid_devices_df, username, password)

# Poll each device until RESTCONF becomes operative or times out
excel_and_data_ops.populate_restconf_status_column(valid_devices_df, username, password, 180, 15)

# Popluate the Current Version column of the DataFrame
excel_and_data_ops.populate_current_version_column(valid_devices_df, username, password)

# Compare current vs recommended IOS version and populate the 'Needs Update' column
excel_and_data_ops.populate_needs_update_column(valid_devices_df)

# Locate the IOS image file for each device and store its absolute path in the DataFrame
excel_and_data_ops.valid_devices_df_with_image_path(valid_devices_df)

# Read the file size of each IOS image and store it in the DataFrame
excel_and_data_ops.get_image_files_size(valid_devices_df)

# Query each device via RESTCONF to get available flash space and store it in the DataFrame
excel_and_data_ops.populate_flash_free_space_column(valid_devices_df, username, password)

# Compare flash free space vs image size and populate the 'Enough Flash Space' column
excel_and_data_ops.populate_enough_space_column(valid_devices_df)

print(f"\nValid Devices\n-------------\n{valid_devices_df.to_string()}")

# Write all updated DataFrame values back to the Excel tracker
excel_and_data_ops.update_excel_tracker(excel_file, excel_sheet_name, valid_devices_df)

###################################################################################################################################

# PART 2: ELEGIBLE DEVICES AND USER SELECTION
# -------------------------------------------

#-------------------------------------------------------------------------------
logger.info("PART 2: Determining Elegible Devices and User Selection to update")
#-------------------------------------------------------------------------------

# Determine which of the valid devices are elegible for an update
eligible_devices_df = excel_and_data_ops.get_eligible_devices_df(valid_devices_df)
print(f"\nEligible Devices\n----------------{eligible_devices_df.head()}")

# Let the user choose which devices to update within the elegible ones
selected_elegible_devices_df = excel_and_data_ops.select_devices_for_update(eligible_devices_df)
print(f"\nSelected Eligible Devices\n-------------------------{selected_elegible_devices_df.head()}")

###################################################################################################################################

# PART 3: IOS FILE TRANSFER
# -------------------------

#-----------------------------------------------------------------------------------------
logger.info("PART 3: Transferring IOS files to the selected devices FLASH memory via SCP")
#-----------------------------------------------------------------------------------------

excel_and_data_ops.populate_transfer_status_column(valid_devices_df, selected_elegible_devices_df, username, password)

# Write all updated DataFrame values back to the Excel tracker
excel_and_data_ops.update_excel_tracker(excel_file, excel_sheet_name, valid_devices_df)

###################################################################################################################################

# PART 4: SET THE UPDATE CONFIGS AND TRIGGER RELOAD ON CONFIRMED DEVICES
# ----------------------------------------------------------------------

#-------------------------------------------------------
logger.info("PART 4: Pushing the configs and reloading")
#-------------------------------------------------------

install_elegible_devices_df = excel_and_data_ops.get_install_eligible_devices_df(valid_devices_df)

# Confirm devices to update, push the commands to set the boot variable and activate it, and populate the 'Install Status' column for confirmed, 
# aborted and non-elegible devices.
excel_and_data_ops.populate_install_status_column(valid_devices_df, install_elegible_devices_df, username, password)

# Write all updated DataFrame values back to the Excel tracker
excel_and_data_ops.update_excel_tracker(excel_file, excel_sheet_name, valid_devices_df)

###################################################################################################################################

# PART 5: COMMIT AND CHECK IF THE UPDATE SUCCEDED
# -----------------------------------------------

#-----------------------------------------------------
logger.info("PART 5: Checking if the update succeded")
#-----------------------------------------------------

# Determine if the update succeded or not
excel_and_data_ops.populate_post_install_columns(valid_devices_df, install_elegible_devices_df, username, password)

# Write all updated DataFrame values back to the Excel tracker
excel_and_data_ops.update_excel_tracker(excel_file, excel_sheet_name, valid_devices_df)

###################################################################################################################################

# PART 6: CLEAN INACTIVE FILES
# ----------------------------

#---------------------------------------------
logger.info("PART 6: Cleaning inactive files")
#---------------------------------------------

# Clean the inactive packages from the old version
excel_and_data_ops.populate_cleaned_inactive_column(valid_devices_df, username, password)

# Write all updated DataFrame values back to the Excel tracker
excel_and_data_ops.update_excel_tracker(excel_file, excel_sheet_name, valid_devices_df)
