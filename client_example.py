from ftplib import FTP_TLS as FTP
import ftplib
import ssl

def gf():
  return FTP("ftp.zerophone.org")

ftp = gf()
ftp.set_debuglevel(2)
ftp.ssl_version = ssl.PROTOCOL_TLSv1_2

file = open("/root/.bashrc")
ftp.login()
ftp.cwd("upload")
ftp.prot_p()
ftp.storbinary("STOR zpui_bootlog_test.zip", file)
