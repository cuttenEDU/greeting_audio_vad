import logging
from multiprocessing import Queue
import queue
from utils import init_logging
import time

def process_badge_fragment(fragments_queue: Queue, active_badges: dict):
    time.sleep(1)
    logging.debug("Fragments consumer started!")
    logging.debug(f"Active badges: {active_badges.keys()}")
    while True:
        try:
            badge_id, fragment, filename = fragments_queue.get()
        except queue.Empty:
            continue
        try:
            badge_handler = active_badges[badge_id]
            badge_handler.process_audiofragment(fragment,filename)
        except KeyError:
            logging.error(f"No active badge with ID: {badge_id}")
