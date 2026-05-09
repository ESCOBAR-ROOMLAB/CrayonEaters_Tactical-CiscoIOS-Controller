# Standard library module for parsing and validating IP addresses
import ipaddress

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

# VALIDATE AN IP ADDRESS
# ----------------------
def is_valid_ip(ip):

    """
    PURPOSE
    -------
    Validates that a value is a well-formed IPv4 address string (X.X.X.X).
    Handles any input type, accounting for Excel cells being read as floats
    or containing accidental whitespace.

    
    ARGUMENTS
    ---------
    ip (any): The value to validate, regardless of type.

    
    RETURN VALUE
    ------------
    True if the value is a valid IPv4 address, False otherwise.
    """

    try:
        # Ensure it's a string first, then attempt to parse as IPv4
        ipaddress.IPv4Address(str(ip).strip())
        return True
    
    except (ipaddress.AddressValueError, ValueError):
        return False