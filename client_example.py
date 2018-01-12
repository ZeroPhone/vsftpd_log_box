from ftplib import FTP_TLS as FTP
from StringIO import StringIO
import zipfile
import ftplib
import ssl

def gf():
  return FTP("ftp.zerophone.org")

ftp = gf()
ftp.set_debuglevel(2)
ftp.ssl_version = ssl.PROTOCOL_TLSv1_2

filename = "zpui_bootlog_test.zip"
zip_contents = StringIO()
zip_contents.name = filename
zip = zipfile.ZipFile(zip_contents, mode="w")
#zip.open()
zip.write("/root/.bashrc")
zip.close()

zip_contents.seek(0)
ftp.login()
ftp.cwd("upload")
ftp.prot_p()
ftp.storbinary("STOR {}".format(filename), zip_contents)
