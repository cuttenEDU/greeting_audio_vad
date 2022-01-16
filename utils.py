import logging
import datetime




def init_logging():
    # Logging init

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    date_strftime_format = "%d-%b-%y %H:%M:%S"
    message_format = "%(asctime)s | %(levelname)s | %(module)s.py: %(message)s"
    formatter = logging.Formatter(message_format,date_strftime_format)

    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(formatter)

    log_filename_format = "%d-%m-%y-%H-%M-%S"
    log_filename = f"/logs/{datetime.datetime.now().strftime(log_filename_format)}.log"
    # log_filename = f"{datetime.datetime.now().strftime(log_filename_format)}.log"

    file_handler = logging.FileHandler(log_filename)
    file_handler.setFormatter(formatter)

    logger.addHandler(stderr_handler)
    logger.addHandler(file_handler)