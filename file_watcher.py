#!/usr/bin/env python2
import os
import sys
import json
import magic
import shutil
import inspect
import smtplib
import logging
import traceback
import subprocess
from time import sleep
import inotify.adapters
from email import Encoders
from threading import Thread
from datetime import datetime
from Queue import Queue, Empty
from uuid import uuid4 as gen_uuid
from email.MIMEBase import MIMEBase
from email.MIMEText import MIMEText
from zipfile import ZipFile, is_zipfile
from email.MIMEMultipart import MIMEMultipart
from email.Utils import COMMASPACE, formatdate
from multiprocessing import Process, Pool, TimeoutError

assert sys.version_info >= (2, 7, 4), "zipinfo protections introduced in 2.7.4 are required"

_DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

l = logging.getLogger(__name__)

with open("/etc/zp_bugreport.json", 'r') as f:
    config = json.loads(f.read())

assert(config.get("mail_destination", None))
assert(isinstance(config.get("mail_destination", None),list))
assert(config.get("main_path", None))
assert(config.get("sandbox_path", None))
assert(config.get("final_path", None))

def _configure_logging():
    l.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()

    formatter = logging.Formatter(_DEFAULT_LOG_FORMAT)
    ch.setFormatter(formatter)

    l.addHandler(ch)

def sendMail(to, fro, subject, text, files=[],server="127.0.0.1"):
    assert type(to)==list
    assert type(files)==list


    msg = MIMEMultipart()
    msg['From'] = fro
    msg['To'] = COMMASPACE.join(to)
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject

    msg.attach( MIMEText(text) )

    for file in files:
        part = MIMEBase('application', "octet-stream")
        part.set_payload( open(file,"rb").read() )
        Encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment; filename="%s"'
                       % os.path.basename(file))
        msg.attach(part)

    smtp = smtplib.SMTP()
    smtp.connect(server)
    smtp.sendmail(fro, to, msg.as_string() )
    smtp.close()

def clean_dir(dir):
    logging.info(dir)
    for i in os.listdir(dir):
        if os.path.isdir(i) and not os.path.islink(i):
            shutil.rmtree(i)
        elif os.path.exists(i):
            os.remove(i)

def dump_zipinfos_to_str(zipinfos):
    info_strs = []
    attrs = ["comment",
             "create_system",
             "compress_type",
             "extra",
             "create_version",
             "extract_version",
             "reserved",
             "flag_bits",
             "volume",
             "internal_attr",
             "external_attr",
             "header_offset",
             "CRC",
             "compress_size",
             "file_size"]
    for info in zipinfos:
        # v1 of the format
        str = "v1-{}@{}".format(info.filename, datetime(*info.date_time))
        attr_strs = ["{}:{}".format(attr, getattr(info,attr, None)) for attr in attrs if getattr(info, attr, None)]
        attr_strs = filter(None, attr_strs)
        attr_str = ",".join(attr_strs)
        str = ','.join([str, attr_str]) if attr_str else str
        info_strs.append(str)
    return ';'.join(info_strs)

def process_file(file_path, base_sandbox_path, final_path, id):
    filename = os.path.basename(file_path)
    status = {"error":False, "state":"started", "result":None, "file_to_remove":file_path, \
              "exception":None, "sandbox_id":id, "filename":filename, "file_to_mail":None, \
              "file_list":[], "file_info_str":None, "json_failed":False}
    try:
        filename = os.path.basename(file_path)
        if not filename.endswith(".zip"):
            logging.warning("Random shit received: {}, ignoring!".format(filename))
            status["state"] = "finished"
            status["error"] = True
            status["result"] = "random_nonzip_shit"
            os.remove(file_path)
            status["file_to_remove"] = None
            raise ValueError("Got random shit")
        status["state"] = "processing_magic"
        logging.info( "{}: processing {}".format(id, filename) )
        with open(file_path) as f:
            type = magic.from_buffer(f.read(1024))
        logging.info( "{}: '{}' file".format(id, type) )
        status["state"] = "checking_magic"
        if not type.startswith("Zip archive") or not is_zipfile(file_path):
            logging.warning("Random .zip-imitating shit received: {}, ignoring!".format(filename))
            status["state"] = "finished"
            status["error"] = True
            status["result"] = "random_fakezip_shit"
            os.remove(file_path)
            status["file_to_remove"] = None
            raise ValueError("Got random shit pretending to be ZIP")
        #TODO: check file size
        status["state"] = "moving_into_sandbox_base"
        os.rename(file_path, os.path.join(base_sandbox_path, filename))
        status["file_to_remove"] = os.path.join(base_sandbox_path, filename)
        logging.info( "{}: Moved file to the base sandbox folder".format(id) )
        sandbox_dir = os.path.join(base_sandbox_path, str(id))
        logging.info("Cleaning sandbox dir: {}".format(sandbox_dir))
        status["state"] = "cleaning_sandbox_base"
        clean_dir(sandbox_dir)
        sandbox_base_path = os.path.join(base_sandbox_path, filename)
        sandboxed_file_path = os.path.join(sandbox_dir,  filename)
        status["state"] = "moving_into_sandbox"
        shutil.move(sandbox_base_path, sandboxed_file_path)
        status["file_to_remove"] = sandboxed_file_path
        logging.info( "{}: Moved the file into the sandbox".format(id) )
        status["state"] = "extracting_into_sandbox"
        with ZipFile(sandboxed_file_path, 'r') as zf:
            status["file_list"] = list(zf.namelist())
            status["file_info_to_str"] = dump_zipinfos_to_str(zf.infolist())
            zf.extractall(sandbox_dir)
        status["state"] = "removing_original"
        logging.info( "{}: Removing original file: {}".format(id, sandboxed_file_path) )
        os.remove(sandboxed_file_path)
        status["file_to_remove"] = None
        status["state"] = "generating_dest_filename"
        # filename, maybe extension
        fme = filename.rsplit('.', 1)
        if len(fme) == 1:
            logging.warning("lol wtf {} has no extension?".format(filename))
            result_path = os.path.join(final_path, "{}-{}".format(filename, gen_uuid()))
        elif len(fme) == 2:
            # Expected result
            result_path = os.path.join(final_path, "{}-{}.{}".format(fme[0], gen_uuid(), fme[-1]))
        else:
            logging.warning("lol wtf len({}.rsplit('.', 1)) != 2 ?".format(filename))
            result_path = os.path.join(final_path, "{}-{}".format(filename, gen_uuid()))
        status["state"] = "packing_files"
        with ZipFile(result_path, 'w') as zf:
            for fn in status["file_list"]:
                zf.write(os.path.join(sandbox_dir, fn), fn)
        status["file_to_mail"] = result_path
        status["state"] = "success"
    except Exception as e:
        logging.exception("Failure during archive processing!")
        status["error"] = True
        status["exception"] = [traceback.format_exc(), {k:str(v) for k,v in inspect.trace()[-1][0].f_locals.items()}]
        if status["file_to_remove"]:
            try:
                os.remove(status["file_to_remove"])
            except:
                logging.exception("Failure during file removal!")
                status["exception"].append(traceback.format_exc())
    heading = "ZeroPhone bugreport upload fail" if status.get("error", False) else "ZeroPhone bugreport uploaded"
    files = [status["file_to_mail"]] if status.get("file_to_mail", None) else []
    for key in status.keys():
        if status[key] is None:
            status[key] = "None"
    logging.info(status)
    try:
        text = json.dumps(status)
    except:
        logging.exception("Status-to-JSON conversion failed!")
        status["json_failed"] = True
        text = str(status)
    try:
        sendMail(config["mail_destination"], 'ZeroPhone bugreport <bugs@zerophone.org>', \
                 heading, text, files, server=config.get('mail_server', None))
    except Exception as e:
        status["exception"].append(traceback.format_exc())
        status["exception"].append({k:str(v) for k,v in inspect.trace()[-1][0].f_locals.items()})
        logging.exception(status)
    return id


class FileProcessorManager(object):

    t = None

    def __init__(self, sandbox_path, final_path, limit=10):
        self.sandbox_path = sandbox_path
        self.final_path = final_path
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
        result = self.pool.apply_async(process_file, (path, self.sandbox_path, self.final_path, result_id))
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
                    logging.info("File {} uploaded!".format(filename))
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
    main_path = config["main_path"]
    final_path = config["final_path"]
    sandbox_path = config["sandbox_path"]

    _configure_logging()
    manager = FileProcessorManager(sandbox_path, final_path)
    manager.start()
    main(main_path, manager)
