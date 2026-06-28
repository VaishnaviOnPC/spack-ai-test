import os

def get_extension_path() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))