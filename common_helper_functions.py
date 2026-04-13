# Standard library module for interacting with the operating system (file paths, directory traversal)
import os

# Standard library module for searching and matching text patterns using regular expressions
import re

# Standard library module for accessing system-specific parameters and interpreter information
import sys

###################################################################################################################################

# GET ABSOULTE PATH FOR FILES
# ---------------------------
def get_absolute_path(filename):

    """
    PURPOSE
    -------
    Returns the absolute path of a file relative to the directory where the script 
    or compiled executable is located. Handles both normal Python execution and 
    PyInstaller compiled executables.

    ARGUMENTS
    ---------
    filename (str): The filename or relative path to resolve.

    RETURNS
    -------
    str: The absolute path of the file.
    """
    
    if getattr(sys, 'frozen', False):
        # Running as a PyInstaller compiled executable
        base_directory = os.path.dirname(sys.executable)
    else:
        # Running as a normal Python script
        base_directory = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_directory, filename)


# NORMALIZE STRINGS
# -----------------
def normalize_ios_version_string(version_str):
    """
    Normalizes a version string by removing leading zeros from each numeric segment.
    e.g. '17.15.04c' -> '17.15.4c'
    """
    return re.sub(r'\b0+(\d)', r'\1', version_str)