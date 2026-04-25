# Standard library module for interacting with the operating system (file paths, directory traversal)
import os

# Standard library module for searching and matching text patterns using regular expressions
import re

# Standard library module for accessing system-specific parameters and interpreter information
import sys

###################################################################################################################################

# HELPER FUNCTION: GET THE RIGHT PATH FOR FILES
# ---------------------------------------------
def get_absolute_path(relative_path):

    """
    PURPOSE
    -------
    Get the absolute path to a resource, works for both development and
    for a PyInstaller bundled application.
    
    In a PyInstaller bundle, the temporary folder path is stored in
    sys._MEIPASS. If that attribute is not available, the function falls
    back to the directory of the current script.


    ARGUMENTS
    ---------
    relative_path (str): The path relative to the application base directory.


    RETURN VALUE
    ------------
    str: The absolute path formed by joining the base directory with the
    relative path.
    """

    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # This is the base path to where your assets are bundled.
        base_path = sys._MEIPASS
    except Exception:
        # If _MEIPASS is not defined, we are in development mode.
        # The base path is just the directory of the main script.
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)
    

# NORMALIZE STRINGS
# -----------------
def normalize_ios_version_string(version_str):

    """
    PURPOSE
    -------
    Normalize a version string by removing leading zeros from each numeric
    segment, making version comparisons reliable.
    
    e.g. '17.15.04c' -> '17.15.4c'


    ARGUMENTS
    ---------
    version_str (str): The version string to normalize.


    RETURN VALUE
    ------------
    str: The normalized version string with leading zeros stripped from
    all numeric parts.
    """

    return re.sub(r'\b0+(\d)', r'\1', version_str)