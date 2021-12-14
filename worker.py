from multiprocessing import Queue
import queue

def process_badge_fragment(fragments_queue: Queue, active_badges: dict):
    while True:
        try:
            badge_id, fragment = fragments_queue.get()
        except queue.Empty:
            continue
        badge_handler = active_badges[badge_id]
        badge_handler.process_audiofragment(fragment)