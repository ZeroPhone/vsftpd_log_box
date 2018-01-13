import os
import magic
import shutil
import logging
import subprocess
#from fallocate import fallocate

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
    sandbox_path = b'/srv/zpui-bootlogs/ftp/sandbox/'

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
                    #TODO: check file size
                    print(type)
                    sandbox_file_path = os.path.join(sandbox_path, filename)
                    os.rename(file_path, sandbox_file_path)
                    print("Moved file to the sandbox folder")
                    img_file_path = sandbox_file_path+".img"
                    #with open(img_file_path, 'w') as f: #doesn't work, no idea why yet
                    #    fallocate(f, 0, 10*1024*1024)
                    subprocess.check_call(["fallocate", img_file_path, "-l", "10M"])
                    print("Created empty loopback image")
                    subprocess.check_call(["mkfs.ext4", "-F", img_file_path])
                    print("Created filesystem on that image")
                    mount_folder_path = sandbox_file_path+".mnt"
                    os.mkdir(mount_folder_path)
                    subprocess.check_call(["fuse2fs", img_file_path, mount_folder_path, "-o", "rw"])
                    print("Mounted the loopback image")
                    shutil.move(sandbox_file_path, mount_folder_path)
                    print("Moved the file into the mounted image")
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
