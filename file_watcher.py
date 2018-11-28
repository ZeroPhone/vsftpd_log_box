#!/usr/bin/env python2
import os
import magic
import shutil
import zipfile
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

def clean_dir(dir):
    lprint(dir)
    for i in os.listdir(dir):
        if os.path.isdir(i) and not os.path.islink(i):
            shutil.rmtree(i)
        elif os.path.exists(i):
            os.remove(i)

def process_file(file_path, base_sandbox_path, id):
    file_to_remove = file_path
    try:
        filename = os.path.basename(file_path)
        if not filename.endswith(".zip"):
            lprint("Random shit received: {}, ignoring!".format(filename))
            os.remove(file_path)
            return False
        lprint( "{}: processing {}".format(id, filename) )
        with open(file_path) as f:
            type = magic.from_buffer(f.read(1024))
        lprint( "{}: '{}' file".format(id, type) )
        if not type.startswith("Zip archive") or not zipfile.is_zipfile(file_path):
            lprint("Random .zip-imitating shit received: {}, ignoring!".format(filename))
            os.remove(file_path)
            return False
        #TODO: check file size
        os.rename(file_path, os.path.join(base_sandbox_path, filename))
        file_to_remove = os.path.join(base_sandbox_path, filename)
        lprint( "{}: Moved file to the base sandbox folder".format(id) )
        sandbox_dir = os.path.join(base_sandbox_path, str(id))
        lprint("Cleaning sandbox dir: {}".format(sandbox_dir))
        clean_dir(sandbox_dir)
        sandbox_base_path = os.path.join(base_sandbox_path, filename)
        sandboxed_file_path = os.path.join(sandbox_dir,  filename)
        shutil.move(sandbox_base_path, sandboxed_file_path)
        file_to_remove = sandboxed_file_path
        lprint( "{}: Moved the file into the sandbox".format(id) )
        with zipfile.ZipFile(sandboxed_file_path, 'r') as zf:
            zf.extractall(sandbox_dir)
        lprint( "{}: Removing original file: {}".format(id, sandboxed_file_path) )
        os.remove(sandboxed_file_path)
    except:
        import traceback; traceback.print_exc()
        try:
            os.remove(file_to_remove)
        except:
            import traceback; traceback.print_exc()
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
                #The timeout doesn't actually work!
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
    main_path = b'/srv/zerophone-logs/ftp/upload/'
    sandbox_path = b'/srv/zerophone-logs/ftp/sandbox/'

    _configure_logging()
    manager = FileProcessorManager(sandbox_path)
    manager.start()
    main(main_path, manager)
