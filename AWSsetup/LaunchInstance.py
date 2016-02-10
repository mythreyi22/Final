# Copyright (C) 2015 Mahesh Pittala <mahesh@multicorewareinc.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version. See COPYING

import os
import subprocess as sub
import time, datetime
import shutil
import glob
import sys
import platform


try:
    from paths_cfg import my_ftp_url, my_ftp_user, my_ftp_pass, my_ftp_path, my_patchtest, my_ftp_instanceid, my_ftp_requestid

except ImportError, e:
    print 'Copy paths_cfg.py.example to paths_cfg.py and edit the file as necessary'
    sys.exit(1)

class Test:
    def __init__(self):
        self.patches = ''
        self.commands = ''
        self.goldentip = ''
        self.instance = ''
        self.mailid = ''
        self.iter = 1

    def parsearg(self, arg, index):
        try:
            if arg == '--commands':
                self.commands = sys.argv[index+1]
            elif arg == '--goldentip':
                self.goldentip = sys.argv[index+1]
            elif arg == '--instance':
                self.instance = sys.argv[index+1]
            elif arg == '--iter':
                self.iter = int(sys.argv[index+1])
            elif arg == '--mailid':
                self.mailid = sys.argv[index+1]
            elif arg == '--':
                self.patches = sys.argv[index+1:]
            elif arg == '-h' or arg == '--help':
                print sys.argv[0], '[OPTIONS]\n'
                print '\t-h/--help                   show this help'
                print '\t   --commands <string>      locate the file which is having additional commandlines (optional)'
                print '\t   --goldentip <string>     The tip which you want to compare with'
                print "\t   --instance <string>      do you want to 'create' the instance or 'terminate'?"
                print '\t   --iter <N>               N times to run the command line, default 1 (optional)'
                print '\t   -- <string>              locate & pass patches'
                print '\t\n\n for full information please read the readme.md file'
                sys.exit(0)
        except IndexError as e:
            print('Run -h\--help for a list of options')
            sys.exit(1)


def upload_patches(test):
    global hashtable
    if not (my_ftp_url and my_ftp_user and my_ftp_pass and my_ftp_path):
        return

    now  = time.strftime("%Y-%m-%d-%H-%M-%S")

    import ftplib
    counter = 0
    for patch in test.patches:
        # open patches and give appropriate names for them to upload
        # ex: date_requestid_instanceid_goldentip_iterations_mailid_patchcount
        renamepatch = '_'.join([now, hashtable['request_id'], hashtable['instance_id'], test.goldentip, str(test.iter), test.mailid, str(counter)])
        try:
            p = open(patch, 'rb')
        except EnvironmentError, e:
            print("failed to open x265binary or library file", e)
            return

        try:
            ftp = ftplib.FTP(my_ftp_url)
            ftp.login(my_ftp_user, my_ftp_pass.decode('base64'))
            ftp.cwd(my_ftp_path)

            # upload x265 binary and corresponding libraries
            ftp.storbinary('STOR ' + renamepatch +'.patch', p)
            counter += 1
            print("uploaded %s \n" % patch)
        except ftplib.all_errors, e:
            print "ftp failed", e
            return

    try:
        if test.commands:
            c = open(test.commands, 'rb')
            ftp.storbinary('STOR ' + '_'.join([now, hashtable['request_id'], hashtable['instance_id'], test.goldentip, str(test.iter), test.mailid, 'commands.txt']), c)
        else:
            print("Please pass goldentip for comparision\n")
    except ftplib.all_errors, e:
        print "ftp failed", e
        return


def upload_requestid_instanceid():

    if not (my_ftp_url and my_ftp_user and my_ftp_pass and my_ftp_path and my_ftp_instanceid and my_ftp_requestid):
        return
    import ftplib
    try:
        ftp = ftplib.FTP(my_ftp_url)
        ftp.login(my_ftp_user, my_ftp_pass.decode('base64'))

        ftp.cwd(my_ftp_instanceid)
        fp = open('instanceid.txt','rb')
        ftp.storbinary('STOR ' +'instanceid.txt',fp)
        fp.close()
        ftp.cwd('./')
        ftp.cwd(my_ftp_requestid)
        fp = open('requestid.txt','rb')
        ftp.storbinary('STOR ' +'requestid.txt',fp)

    except ftplib.all_errors, e:
        print "ftp failed", e
    finally:
        ftp.quit()


def find2(file, keyword, cli) :
    file_name=file
    ret_value="none"
    time.sleep(240)
    with open(file_name,'r') as f:
        for line in f:
            word = line.split()
            c=0
            for j in range(len(word)) :
                if word[j].startswith(keyword) or keyword in word[j] and not 'ami-' in word[j]:
                    if "EBSvolumeid" in file_name:
                        if c==2:
                            return word[j]
                    else:
                        return word[j]
                    c+=1
    return ret_value


def find(test, file, keyword, cli) :
    global Failures, ws_terminate
    file_name=file

    if 'request_id' in file :
      ret_value=find2(file_name, keyword, cli)
      return ret_value
    else :
        for i in range(10) :
          file2=open(file_name,'w')
          print("re run to get id......",file_name, keyword, cli)
          ret = sub.Popen(cli, shell = True, stdout = file2, stderr = fail)
          if ret.wait()!=0:
              print("Command failed to run:", cli)
              Failures.write("\nThis Command failed to run:"+ cli)
              
          file2.close()
          if i == 9 :
                InstanceTerminate_Commands=UpdateHashTable(test, "terminate")
                RunCommands(test, ws_terminate, InstanceTerminate_Commands, "terminate")
                print("terminated instance.........................", instance)
                exit(0)
          else :
              ret_value=find2(file_name, keyword, cli)
              if not ret_value == "none":
                  return ret_value


def UpdateHashTable(test, status):
    global cur_time
    global hashtable
    global workbook
    global cur_time
    global fail
    global Failures

    #get security credentials
    hashtable['accesskey'] = str(os.environ['AWS_ACCESS_KEY_ID'])
    hashtable['secretkey'] = str(os.environ['AWS_SECRET_ACCESS_KEY'])
    
    ws_os = workbook.sheet_by_name('Linux')
    count = ws_os.nrows
    for i in range(count):
        value = str(ws_os.cell(i, 0).value)
        hashtable[value] = str(ws_os.cell(i, 2).value)

    tag = '--tag "Name=x265PerformanceRegression %s" --aws-access-key=' %test.mailid

    if status.lower() == "create":
        InstanceCreate_Commands = ["ec2-request-spot-instances "  +hashtable["ami"]+" -p "+hashtable["price"]+" --subnet "+hashtable["subnet"]+" --aws-access-key="+hashtable["accesskey"]+" --aws-secret-key="+hashtable["secretkey"]+" -t "+hashtable["instancetype"]+" --key "+hashtable["keypair"]+" --group "+hashtable["securitygroup"]+" --region "+hashtable["region"],
                            "ec2-create-tags "  +hashtable['request_id']+" "+tag+hashtable['accesskey']+" --aws-secret-key="+hashtable['secretkey'],
                            "ec2-describe-spot-instance-requests "  +hashtable['request_id']+'  --aws-access-key='+hashtable['accesskey']+' --aws-secret-key='+hashtable['secretkey']+' --region '+hashtable['region'],
                            "ec2-create-tags "  +hashtable['instance_id']+" "+tag+hashtable['accesskey']+" --aws-secret-key="+hashtable['secretkey']]
        return InstanceCreate_Commands
    else:
         InstanceTerminate_Commands = ["ec2-cancel-spot-instance-requests " +hashtable['request_id']+' --aws-access-key='+hashtable['accesskey']+' --aws-secret-key='+hashtable['secretkey']+' --region '+hashtable['region'],
                             "ec2-terminate-instances " +hashtable['instance_id']+' --aws-access-key='+hashtable['accesskey']+' --aws-secret-key='+hashtable['secretkey']+' --region '+hashtable['region']]
         return InstanceTerminate_Commands


def RunCommands(test, key, commands, status):
    global Failures
    global cur_time
    global CWD
    global hashtable

    count = len(commands)
    for i in range(count):
        cli = commands[i]
        return_value = str(key.cell(i+1, 1).value)
        print("\n\n", cli)

        if return_value == "none":
            ret = sub.Popen(cli, shell = True, stderr = fail)
            if ret.wait()!=0:
                print("Command failed to run:", cli)
                Failures.write("\nThis Command failed to run:"+ cli)
        else:
            keyword = str(key.cell(i+1, 2).value)
            file = open(return_value + ".txt", 'w')
            ret = sub.Popen(cli, shell = True, stdout = file, stderr = fail)
            if ret.wait()!=0:
                  print("Command failed to run:", cli)
                  Failures.write("\nThis Command failed to run:"+ cli)

            return_value = return_value.split(",")
            keyword = keyword.split(",")
            
            for i in range(len(return_value)):
                filename = return_value[i]+".txt"
                ID=find(test, filename , keyword[i], cli)
                print("HASH TABLE store....", str(ID))
                hashtable[return_value[i]]=str(ID)
                print(hashtable[return_value[i]])
                print("\n\n\n\n\n")

                commands = UpdateHashTable(test, status)
                print(hashtable)
            file.close()


def launch_instance(test):
    import logging
    import xlrd
    global hashtable
    global workbook
    global cur_time
    global fail
    global Failures
    global ws_terminate

    logging.basicConfig(filename = "Failures.txt", filemode = "w", format = "%(message)s", level = logging.DEBUG)
    fail = open("Failures_StanderedErrors.txt", "w")
    Failures = open("Failures.txt", "w")
    cur_time = time.strftime("%d-%m-%Y-%H-%M-%S")

    workbook = xlrd.open_workbook("Instance_config.xls")
    ws_create = workbook.sheet_by_name("InstanceCreate_Commands")
    ws_terminate = workbook.sheet_by_name("InstanceTerminate_Commands")

    hashtable = {}
    hashtable['request_id'] = ""
    hashtable['instance_id'] = ""
    hashtable['dns'] = ""
    hashtable['instancestore_volumeid'] = ""
    hashtable['EBSvolumeid'] = ""
    Commands = UpdateHashTable(test, test.instance)
    if test.instance.lower() == 'create':
        RunCommands(test, ws_create, Commands, test.instance)
    else:
        RunCommands(test, ws_terminate, Commands, test.instance)

    f = open('instanceid.txt', 'wb')
    f.write(hashtable['instance_id'])
    f.close()
    
    f = open('requestid.txt', 'wb')
    f.write(hashtable['request_id'])
    f.close()




def main():

    # verify the arguments
    if not '--instance' and not '-h' in sys.argv and not '--help' in sys.argv:
        print('Run -h\--help for a list of options')
        sys.exit(1)

    # create object
    test = Test()
    test.cwd = os.getcwd()

    # parse the arguments
    for i in range(len(sys.argv)):
        test.parsearg(sys.argv[i], i)

    # launch instance
    launch_instance(test)

    # upload required files
    if my_patchtest == True:
        upload_patches(test)
    else:
        upload_requestid_instanceid()


if __name__ == "__main__":
    main()
