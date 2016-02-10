# Copyright (C) 2015 Mahesh Pittala <mahesh@multicorewareinc.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version. See COPYING

import os
import socket
import sys
import time
import shutil
from ftplib import FTP
import ftplib

try:
    from paths_cfg import my_FTP_Server, my_FTP_user, my_FTP_pwd, my_FTPServer_usercontent

except ImportError, e:
    print 'Copy paths_cfg.py.example to paths_cfg.py and edit the file as necessary'
    sys.exit(1)


class submit:
    def __init__(self):
        self.commands = ''
        self.goldentip = ''
        self.instancestate = ''
        self.mailid = ''
        self.iter = 1
        self.patches = ''

    def parsearg(self, arg, index):
        try:
            if arg == '--commands':
                self.commands = sys.argv[index+1]
            elif arg == '--goldentip':
                self.goldentip = sys.argv[index+1]
            elif arg == '--instance':
                self.instancestate = sys.argv[index+1]
            elif arg == '--mailid':
                self.mailid = sys.argv[index+1]
            elif arg == '--iter':
                self.iter = int(sys.argv[index+1])
            elif arg == '--':
                self.patches = sys.argv[index+1:]
            elif arg == '-h' or arg == '--help':
                print sys.argv[0], '[OPTIONS]\n'
                print '\t-h/--help                   show this help'
                print '\t   --commands <string>      locate the file which is having additional commandlines (optional)'
                print '\t   --goldentip <string>     The tip which you want to compare with'
                print "\t   --instancestate <string> do you want to 'create' the instance or 'terminate'?"
                print "\t   --mailid <string>        receiver mail id to get results"
                print '\t   --iter <N>               N times to run the command line, default 1 (optional)'
                print '\t   -- <string>              locate the patches with space'
                print '\t\n\n for full information please read the readme.md file'
                sys.exit(0)
        except IndexError as e:
            print('Run -h\--help for a list of options')
            sys.exit(1)


def send_patches(test):
    def transfer(file, rename):
        # transfer files to FTP Server
        f = open(file, 'rb')
        try:
            ftp = FTP(my_FTP_Server)
            ftp.login(my_FTP_user, my_FTP_pwd)
            ftp.cwd(my_FTPServer_usercontent)
            ftp.storbinary('STOR ' + rename, f)
            print('patch %s transfered to the Jenkin server....' %file)
        except ftplib.all_errors, e:
            print "ftp failed", e
            sys.exit(1)
			
        # connect Jenkin Server
        try:
            s.sendall(rename)
            # get acknowledge from Jenkin server
            #reply = s.recv(1024)
            #print(reply)
            #while(reply):
            #    reply = s.recv(1024)
            #    print(reply)
        except socket.error:
            print('failed to transfer files to FTP server...')
            sys.exit(-1)
        return

    try:
        # create a socket object
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # initiates TCP server connection
        s.connect((my_FTP_Server, 10256))
        print('wait until connected to FTP Server...')
        reply = s.recv(1024)
        print(reply)
    except socket.error:
        print('Jenkin server is not running..')
        sys.exit(-1)

    patchcount = 1
    now  = time.strftime("%Y-%m-%d-%H-%M-%S")
    for patch in test.patches:
        # date, request_id, instance_id, goldentip, iter, my_email_to, counter
        rename = '_'.join([now, test.goldentip, str(test.iter), test.mailid, str(patchcount) + '.patch'])
        transfer(patch, rename)
        patchcount += 1

    if test.commands:
        rename = '_'.join([now, test.goldentip, str(test.iter), test.mailid, str(patchcount) + '.txt'])
        transfer(test.commands, rename)

def main():
    # verify the arguments
    if not '--goldentip' in sys.argv and not '--instance' and not '--mailid'and not '-h' in sys.argv and not '--help' in sys.argv:
        print('Run -h\--help for a list of options')
        sys.exit(1)

    # create object
    test = submit()
    test.cwd = os.getcwd()

    # parse the arguments
    for i in range(len(sys.argv)):
        test.parsearg(sys.argv[i], i)
		
    # send patches
    send_patches(test)
	
if __name__ == "__main__":
    main()
