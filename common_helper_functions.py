# Standard library module for interacting with the operating system (file paths, directory traversal)
import os

# Standard library module for searching and matching text patterns using regular expressions
import re

# Standard library module for accessing system-specific parameters and interpreter information
import sys

###################################################################################################################################

# HELPER FUNCTION: GET THE RIGHT PATH FOR FILES
# ---------------------------------------------
# def alternate_get_absolute_path(file_name):

#     """Returns the absolute path for the file argumented"""

#     if getattr(sys, 'frozen', False):
#         # If the application is run as a bundle (e.g., by PyInstaller)
#         BASE_PATH = os.path.dirname(sys.executable)
#     else:
#         # If running as a normal .py script
#         BASE_PATH = os.path.dirname(os.path.abspath(__file__))
    
#     file_absolute_path = os.path.join(BASE_PATH, file_name)
#     return file_absolute_path


def get_absolute_path(relative_path):
    """
    Get the absolute path to a resource, works for both development and
    for a PyInstaller bundled application.
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
    Normalizes a version string by removing leading zeros from each numeric segment.
    e.g. '17.15.04c' -> '17.15.4c'
    """
    return re.sub(r'\b0+(\d)', r'\1', version_str)