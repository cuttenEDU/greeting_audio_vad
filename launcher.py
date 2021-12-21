import threading
import queue
import logging

import fast_api
import worker
from utils import init_logging


from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()

    init_logging()

    fragments_queue = queue.Queue()
    active_badges = {}

    fragments_consumer = threading.Thread(target=worker.process_badge_fragment,args=(fragments_queue,active_badges))

    fragments_consumer.start()

    fast_api.main(fragments_queue,active_badges)

