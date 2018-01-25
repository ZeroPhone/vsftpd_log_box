import os
import magic
import shutil
import logging
import subprocess
from time import sleep
from threading import Thread
from Queue import Queue, Empty
from multiprocessing import Process, Pool, TimeoutError, Lock

import inotify.adapters

_DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

l = logging.getLogger(__name__)

def _configure_logging():
    l.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()

    formatter = logging.Formatter(_DEFAULT_LOG_FORMAT)
    ch.setFormatter(formatter)

    l.addHandler(ch)

print_lock = Lock()

def lprint(str):
    with print_lock:
       print(str)

def process_file(file_path, sandbox_path, id):
    filename = os.path.basename(file_path)
    lprint( "{}: processing {}".format(id, filename) )
    with open(file_path) as f:
       type = magic.from_buffer(f.read(1024))
    #TODO: check file size
    #TODO: check file type
    lprint( "{}: '{}' file".format(id, type) )
    sandbox_file_path = os.path.join(sandbox_path, filename)
    os.rename(file_path, sandbox_file_path)
    lprint( "{}: Moved file to the base sandbox folder".format(id) )
    img_dir = os.path.join(sandbox_path, str(id))
    img_file_path = os.path.join(img_dir, filename)
    shutil.move(sandbox_file_path, img_file_path)
    lprint( "{}: Moved the file into the sandbox".format(id) )
    return id

class FileProcessorManager(object):

    t = None

    def __init__(self, sandbox_path, limit=10):
        self.sandbox_path = sandbox_path
        self.limit = limit
        self.q = Queue()
        self.pool = Pool(processes=self.limit)
        self.results = {}

    def start(self):
        l.info("Starting FileProcessor manager")
        if self.t is not None: l.error("Already running, wtf"); return
        self.t = Thread(target=self.event_loop)
        self.t.daemon = True
        self.t.start()

    def notify_file(self, path):
        l.info("Notified about {}!".format(path))
        self.q.put(path)

    def event_loop(self):
        while True:
            try:
                self.request_process_file(self.q.get(False, 1))
            except Empty:
                pass
            if not self.check_results():
                sleep(10)

    def check_results(self):
        success = False
        for id, result in self.results.items():
            try:
                result_id = result.get(timeout=1)
            except TimeoutError:
                pass
            else:
                assert( id == result_id )
                l.info("Worker {} finished!".format(result_id))
                self.results.pop(id)
                success = True
        return success

    def request_process_file(self, path):
        l.info("Requesting to process {}".format(path))
        result_id = self.get_runner_id()
        result = self.pool.apply_async(process_file, (path, self.sandbox_path, result_id))
        l.info("Request sent. ({})".format(path))
        self.results[result_id] = result

    def get_runner_id(self):
        l.info("Getting a new process ID")
        if len(self.results.keys()) > self.limit:
            l.warning("Processor count limit reached, waiting...")
            while len(self.result.values()) > self.limit: sleep(5)
        return list( set(range(self.limit)) - set(self.results.keys()) )[0]


def main(main_path, manager):
    i = inotify.adapters.Inotify()

    i.add_watch(main_path)

    try:
        for event in i.event_gen():
            if event is not None:
                (header, type_names, watch_path, filename) = event
                if "IN_CLOSE_WRITE" in type_names:
                    filename = filename.decode('utf-8')
                    print("File {} uploaded!".format(filename))
                    file_path = os.path.join(main_path, filename)
                    manager.notify_file(file_path)
                else:
                    pass #l.info("WD=(%d) MASK=(%d) COOKIE=(%d) LEN=(%d) MASK->NAMES=%s "
                    #         "WATCH-PATH=[%s] FILENAME=[%s]",
                    #         header.wd, header.mask, header.cookie, header.len, type_names,
                    #         watch_path.decode('utf-8'), filename.decode('utf-8'))
    finally:
        i.remove_watch(main_path)

if __name__ == '__main__':
    main_path = b'/srv/zpui-bootlogs/ftp/upload/'
    sandbox_path = b'/srv/zpui-bootlogs/ftp/sandbox/'

    _configure_logging()
    manager = FileProcessorManager(sandbox_path)
    manager.start()
    main(main_path, manager)
