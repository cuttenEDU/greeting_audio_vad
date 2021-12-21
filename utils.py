import logging

def init_logging():
    # Logging init
    date_strftime_format = "%d-%b-%y %H:%M:%S"
    message_format = "%(asctime)s | %(levelname)s | %(module)s.py: %(message)s"
    logging.basicConfig(format=message_format, datefmt=date_strftime_format, level=logging.DEBUG)