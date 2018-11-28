#!/bin/sh
ABSPATH=`realpath file_watcher.py`
rm /usr/bin/zp_logfile_watcher.py
cp $ABSPATH /usr/bin/zp_logfile_watcher.py
chmod +x /usr/bin/zp_logfile_watcher.py
chown uploaded:ftp /usr/bin/zp_logfile_watcher.py

ABSPATH=`realpath vsftpd.conf`
ln -sf $ABSPATH /etc/vsftpd.conf

SERVICE=zp_file_watcher.service
cp $SERVICE /etc/systemd/system
systemctl daemon-reload
systemctl enable $SERVICE
systemctl restart $SERVICE
