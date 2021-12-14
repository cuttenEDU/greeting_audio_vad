from multiprocessing import Queue,Process

import fast_api
import worker


if __name__ == "__main__":
    fragments_queue = Queue()
    active_badges = {}
    rest_api = Process(target=fast_api.main,args=(fragments_queue,active_badges))
    nn_worker = Process(target=worker.process_badge_fragment,args=(fragments_queue,active_badges))
    rest_api.start()
    nn_worker.start()

