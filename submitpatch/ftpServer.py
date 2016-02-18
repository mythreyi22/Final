# Copyright (C) 2015 Mahesh Pittala <mahesh@multicorewareinc.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version. See COPYING

import os
import socket
import sys
from thread import *
import jenkinsapi
from jenkinsapi.jenkins import Jenkins
from jenkinsapi.job import *
from xml.dom import minidom
import shutil
import time
import subprocess as sub
from subprocess import Popen, PIPE

try:
    from paths_cfg import my_FTPServer_usercontent

except ImportError, e:
    print 'Copy paths_cfg.py.example to paths_cfg.py and edit the file as necessary'
    sys.exit(1)



HOST = ''   # Symbolic name meaning all available interfaces
PORT = 10256 # Arbitrary non-privileged port

# Create a socket object
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Bind socket to local host and port
try:
    s.bind((HOST, PORT))
except socket.error , msg:
    print 'Bind failed. Error Code : ' + str(msg[0]) + ' Message ' + msg[1]
    sys.exit()
print 'Socket bind complete'

# Start listening on socket
s.listen(100)
print 'Socket now listening'


# now keep talking with the client
while True:
    # wait to accept a connection - blocking call
    conn, addr = s.accept()
    print('connected to ', addr)
    conn.sendall('connected to FTP server...')
    userfiles = []
    while(1):
        # receive zip file name
        fullname = conn.recv(1024)
        if fullname and '.patch' in fullname or '.txt' in fullname:
            print('filename %s' %fullname)
            userfiles.append(os.path.abspath(os.path.join(my_FTPServer_usercontent, fullname)))
            #conn.sendall('      FTP Server received file')
            continue
        elif not '.patch' in fullname and not '.txt' in fullname:
            break
    print(userfiles)

    try:
        d, g, n, m, c = userfiles[len(userfiles)-1].split('_')

        if '.txt' in userfiles[len(userfiles)-1]:
            p = ' '.join(userfiles[:len(userfiles)-1])
            cmd = 'python LaunchInstance.py --mailid %s --iter %s --goldentip %s --instance create --commands %s -- %s' %(m, n, g, userfiles[len(userfiles)-1], p)
        else:
            p = ' '.join(userfiles[:len(userfiles)])
            cmd = 'python LaunchInstance.py --mailid %s --iter %s --goldentip %s --instance create -- %s' %(m, n, g, p)
        os.chdir("..//AWSsetup")
        ret = sub.Popen(cmd, shell=True)
        if ret.wait() == 0:
            print('tests are successful')
    except Exception as e:
        print('failed to parse file name' %e)

    for f in userfiles:
        try:
            os.remove(f)
        except Exception as e:
            print('let it be %s %s' %f %e)
    conn.close()
    time.sleep(10)
    
s.close()
