import os
import magic
import logging

import inotify.adapters

_DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

_LOGGER = logging.getLogger(__name__)

def _configure_logging():
    _LOGGER.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()

    formatter = logging.Formatter(_DEFAULT_LOG_FORMAT)
    ch.setFormatter(formatter)

    _LOGGER.addHandler(ch)

def main():
    i = inotify.adapters.Inotify()

    main_path = b'/srv/zpui-bootlogs/ftp/upload/'

    i.add_watch(main_path)

    try:
        for event in i.event_gen():
            if event is not None:
                (header, type_names, watch_path, filename) = event
                if "IN_CLOSE_WRITE" in type_names:
                    filename = filename.decode('utf-8')
                    print("File {} created!".format(filename))
                    file_path = os.path.join(main_path, filename)
                    with open(file_path) as f:
                        type = magic.from_buffer(f.read(1024))
                    print(type)
                else:
                    pass #_LOGGER.info("WD=(%d) MASK=(%d) COOKIE=(%d) LEN=(%d) MASK->NAMES=%s "
                    #         "WATCH-PATH=[%s] FILENAME=[%s]",
                    #         header.wd, header.mask, header.cookie, header.len, type_names,
                    #         watch_path.decode('utf-8'), filename.decode('utf-8'))
    finally:
        i.remove_watch(b'/tmp')

if __name__ == '__main__':
    _configure_logging()
    main()
