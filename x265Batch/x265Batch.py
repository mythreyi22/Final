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
import xlrd

header = {}
CWD = os.getcwd()
path = {}
try:
    from paths_cfg import my_sequences, my_bitstreams
    from paths_cfg import my_RAMDISK, my_compareFPS, my_csvupload

    # support ~/repos/x265 syntax
    my_sequences = os.path.expanduser(my_sequences)
    my_bitstreams = os.path.expanduser(my_bitstreams)
except ImportError, e:
    print 'Copy paths_cfg.py.example to paths_cfg.py and edit the file as necessary'
    sys.exit(1)

try:
    from paths_cfg import my_RAMDiskpath
    my_RAMDiskpath = os.path.expanduser(my_RAMDiskpath)
except ImportError, e:
    print 'failed to import variables, if u want to run with ram disk then you must set path, defaulting to None', e
    my_RAMDiskpath = None

try:
    from paths_cfg import my_email_from, my_email_to, my_smtp_pwd, my_smtp_host, my_smtp_port
except ImportError, e:
    print '** `my_email_*` not defined, defaulting to None'
    my_email_from, my_email_to, my_smtp_pwd = None, None, None
try:
    from paths_cfg import Decodebitstream, regeneratecsv
except ImportError, e:
    print '** `Decodebitstream*` not defined, defaulting to None'
    Decodebitstream, regeneratecsv = None, None
try:
    from paths_cfg import my_ftp_url, my_ftp_user, my_ftp_pass, my_ftp_path_stable, my_ftp_path_default, my_ftp_path_stableold, my_ftp_path_defaultold
except ImportError, e:
    print '** `my_email_*` not defined, defaulting to None'
    my_ftp_url, my_ftp_user, my_ftp_pass, my_ftp_path_stable, my_ftp_path_default, my_ftp_path_stableold, my_ftp_path_defaultold = None, None, None, None, None, None, None


class Test:
    def __init__(self):
        self.my_sequences = my_sequences
        self.my_bitstreams = my_bitstreams
        self.my_RAMDISK = my_RAMDISK
        self.my_RAMDiskpath = my_RAMDiskpath

        self.inputsequences_path = ''
        self.outputfile_path = ''
        self.first = True
        self.seq = ''

        self.cwd = ''
        self.finalcsv = 'x265Benchmark_aux.csv'
        self.fullcommandlines = 'fullcommandlines_autogen.txt'
        self.goldendir = ''
        self.resultdir = ''

        self.sequences = set()
        self.commands = open(self.fullcommandlines, 'w')
        self.nowdate = datetime.datetime.now().strftime('log-%y%m%d%H%M%S')
        self.start_time = datetime.datetime.now()
        self.logfname = '%s.txt' % (self.nowdate)
        self.logfp = open(os.path.join(self.resultdir, self.logfname), 'wb')

        self.branch = ''
        self.tag = ''
        self.cfg = ''
        self.cli = ''
        self.iter = 1

        self.video = ''
        self.preset = ''
        self.abr = ''
        self.cqp = ''
        self.crf = ''
        self.vbvbufsize = ''
        self.vbvmaxrate = ''
        self.fps = ''
        self.avg = []
        self.rev = ''
        self.tableheader = r'<tr><th>{0}</th><th>{1}</th><th>{2}</th><th>{3}</th><th>{4}</th><th>{5}</th><th>{6}</th><th>{7}</th><th>{8}</th><th>{9}</th><th>{10}</th><th>{11}</th></tr>'\
                                   .format('Video',
                                   'Preset',
                                   'ABR',
                                   'CQP',
                                   'CRF',
                                   'vbv-bufsize',
                                   'vbv-maxrate',
                                   'golden tip',
                                   'current tip',
                                   'harmonicmean of golden FPS',
                                   'harmonicmean of current FPS', 
                                   '% of increase with current FPS')

        self.table = ['<htm><body><table border="1">']

    def ramdisk(self):
        if self.my_RAMDISK == True:
            self.inputsequences_path = self.my_RAMDiskpath
            self.outputfile_path = self.my_RAMDiskpath
        else:
            self.inputsequences_path = self.my_sequences
            self.outputfile_path = self.my_bitstreams

    def parse(self, arg, index):
        try:
            if arg == '--tag':
                self.tag = sys.argv[index+1]
                self.finalcsv = self.tag + '_aux.csv'
            elif arg == '--cfg':
                self.cfg = sys.argv[index+1]
            elif arg == '--iter':
                self.iter = int(sys.argv[index+1])
            elif arg == '--branch':
                self.branch = sys.argv[index+1]
            elif arg == '--mailid':
                my_email_to = sys.argv[index+1]
            elif arg == '--':
                self.cli = sys.argv[index+1:]
                if not os.name == 'nt':
                    os.system('chmod 555 '+ sys.argv[index+1])
                self.cli = ' '.join(self.cli)
            elif arg == '-h' or arg == '--help':
                print sys.argv[0], '[OPTIONS]\n'
                print '\t-h/--help              show this help'
                print '\t   --cfg <string>      locate the file which is having commandlines'
                print '\t   --tag <string>      specific name for your test, default NULL (optional)'
                print '\t   --iter <N>          N times to run the command line, default 1 (optional)'
                print '\t   --branch <string>   binary built from stable\default branch, default NULL (optional)'
                print '\t   --mailid <string>   receiver mail id to get the results, default NULL (optional)'
                print '\t   -- <string>         binary and additional encoder options'
                print '\t\n\n for full information please read the readme.md file'
                sys.exit(0)
        except IndexError as e:
            print('Run -h\--help for a list of options')
            sys.exit(1)

    def setup_workingdir(self):
        if my_compareFPS == True:
            self.goldendir = 'goldencsv' + self.branch
            if not os.path.exists(os.path.join(self.cwd, self.goldendir)):
                os.mkdir(os.path.join(self.cwd, self.goldendir))

        if not os.path.exists(os.path.join(self.cwd, self.my_bitstreams)):
            os.mkdir(os.path.join(self.cwd, self.my_bitstreams))

        if not os.path.exists(os.path.join(self.cwd, "Results" + self.branch)):
            os.mkdir(os.path.join(self.cwd, "Results" + self.branch))

        self.resultdir = os.path.join(self.cwd, "Results" + self.branch, datetime.datetime.now().strftime('%y-%m-%d-%H%M%S'))
        if not os.path.exists(self.resultdir):
            os.mkdir(self.resultdir)

    def prepare_commands(self):
        with open(self.cfg) as f:
            for cmd in f:
                for i in range(self.iter):
                    self.commands.write(' '.join([self.cli,\
                                                '--input', os.path.join(self.inputsequences_path, cmd.strip('\r\n')), 
                                                '--csv',  os.path.join(self.resultdir, (self.tag if self.tag != '' else 'x265Benchmark') + '.csv'), 
                                                '-o ', os.path.join(self.outputfile_path, ''.join(cmd.strip('\r\n').split(' '))) + self.tag + '.hevc', 
                                                '\n']))
                self.sequences.add(cmd.split(' ')[0])

        for file in glob.glob("..//AWSsetup//*.txt"):
            if '_commands.txt' in file:
                with open(file) as f:
                    for cmd in f:
                        if cmd and not cmd.startswith('#') and not cmd.startswith('\n'):
                            for i in range(self.iter):
                                self.commands.write(' '.join([self.cli,\
                                                            '--input', os.path.join(self.inputsequences_path, cmd.strip('\r\n')), 
                                                            '--csv',  os.path.join(self.resultdir, (self.tag if self.tag != '' else 'x265Benchmark') + '.csv'), 
                                                            '-o ', os.path.join(self.outputfile_path, ''.join(cmd.strip('\r\n').split(' '))) + self.tag + '.hevc', 
                                                            '\n']))
                            self.sequences.add(cmd.split(' ')[0])
        self.commands.close()

    def setup(self, cmd):
        for i in range(len(self.sequences)):
            if list(self.sequences)[i] in cmd:
                if self.my_RAMDISK == True:
                    if not list(self.sequences)[i] == self.seq:
                        if self.first == True:
                            self.first = False
                        else:
                            try:
                                os.remove(os.path.join(self.inputsequences_path, self.seq))
                                shutil.move(os.path.join(self.outputfile_path, '.'), os.path.join(self.my_bitstreams, datetime.datetime.now().strftime('bitstreams-%y%m%d%H%M%S')))
                            except (shutil.Error, OSError), e:
                                pass
                        shutil.copy(os.path.join(self.my_sequences, list(self.sequences)[i]), os.path.join(self.inputsequences_path, list(self.sequences)[i]))
                        self.seq = list(self.sequences)[i]            

    def remove_movefiles(self):
        try:
            os.remove(os.path.join(self.inputsequences_path, self.seq))
            shutil.move(os.path.join(self.outputfile_path, '.'), os.path.join(self.my_bitstreams, datetime.datetime.now().strftime('bitstreams-%y%m%d%H%M%S')))
        except (shutil.Error, OSError), e:
            pass

    def parsecsv(self, tok, index, cmdline):
        if tok == '--input':
            self.video = os.path.basename(cmdline[index + 1])
        elif tok == '-p' or tok == '--preset':
            self.preset = cmdline[index + 1]
        elif tok == '--bitrate':
            self.abr = cmdline[index + 1]
        elif tok == '-q' or tok == '--qp':
            self.cqp = cmdline[index + 1]
        elif tok == '--crf':
            self.crf = cmdline[index + 1]
        elif tok == '--vbv-bufsize':
            self.vbvbufsize = cmdline[index + 1]
        elif tok == '--vbv-maxrate':
            self.vbvmaxrate = cmdline[index + 1]


def harmonic_mean(nums):
    geomean = reduce(lambda x, y: x*y, nums)**(1.0/len(nums))
    arithmean = float(sum(nums)/len(nums))
    return float((geomean**2)/arithmean)

def email_results(test, f1, f2):
    if not (my_email_from and my_email_to and my_smtp_pwd):
        return

    import smtplib
    from email.mime.text import MIMEText
    from email.MIMEMultipart import MIMEMultipart
    from email.encoders import encode_base64
    from email.mime.image import MIMEImage

    duration = str(datetime.datetime.now() - test.start_time).split('.')[0]

    msg = MIMEMultipart()
    body = MIMEText("Test Duration(H:M:S) = {0}".format(duration) + ''.join(test.table), 'html')
    msg.attach(body)
    text0 = MIMEImage(open(f1, 'rb').read(), _subtype="csv")
    text0.add_header('Content-Disposition', 'attachment', filename=os.path.basename(f1))
    msg.attach(text0)
    text1 = MIMEImage(open(f2, 'rb').read(), _subtype="csv")
    text1.add_header('Content-Disposition', 'attachment', filename=os.path.basename(f2))
    msg.attach(text1)
    if type(my_email_to) is str:
        msg['To'] = my_email_to
    else:
        msg['To'] = ", ".join(my_email_to)
    
    msg['From'] = my_email_from
    data = [platform.system(), '-', test.tag, 'Performance Regression']
    msg['Subject'] = ' '.join(data)

    session = smtplib.SMTP(my_smtp_host, my_smtp_port)
    try:
        session.ehlo()
        session.starttls()
        session.ehlo()
        session.login(my_email_from, my_smtp_pwd.decode('base64'))
        session.sendmail(my_email_from, my_email_to, msg.as_string())
    except smtplib.SMTPException, e:
        print 'Unable to send email', e
    finally:
        session.quit()

def encode(test): 
    with open(test.fullcommandlines) as lines:
        for cmd in lines:
            test.setup(cmd)
            print('encoding...', cmd)
            ret = sub.Popen(cmd, shell=True, stderr=test.logfp, stdout=test.logfp)
            if ret.wait() != 0:
                print("\n Encoding failed: %s \n" %cmd)
            # sleep for 10 seconds to release the resource completely....
            time.sleep(10)

def regeneratecsv(test):
    csvheader = True
    csvlist = glob.glob(os.path.join(test.resultdir, '*.csv'))
    final = open(os.path.join(test.resultdir, test.finalcsv), 'w')
    for csv in csvlist:
        with open(csv) as lines:
            for line in lines:
                tokens = line.split(',')
                cmdline = tokens[0].split()
                if cmdline[0] == 'Command':
                    if csvheader == True:
                        final.write('Video,Preset,ABR,CQP,CRF,vbv-bufsize,vbv-maxrate')
                        csvheader = False
                    else:
                        continue
                else:
                    for i in range(len(cmdline)):
                        test.parsecsv(cmdline[i], i, cmdline)
                    if test.preset == '':
                        test.preset = 'medium'
                    if test.abr == '' and test.cqp == '' and test.crf == '':
                        test.crf = '28'
                    final.write(''.join(','.join([test.video, test.preset, test.abr, test.cqp, test.crf, test.vbvbufsize, test.vbvmaxrate])))
                    test.preset = test.abr = test.cqp = test.crf = test.vbvbufsize = test.vbvmaxrate = ''

                for j in range(len(tokens)):
                    final.write(',')
                    final.write(tokens[j])

    final.close()

def compare(test):
    if not os.path.exists(os.path.join(test.resultdir, test.finalcsv)) or not os.path.exists(os.path.join(test.cwd, test.goldendir, test.finalcsv)):
        print('csv file does not exist to compare', os.path.join(test.resultdir, test.finalcsv), os.path.exists(os.path.join(test.cwd, test.goldendir, test.finalcsv)))
        if os.path.exists(os.path.join(test.resultdir, test.finalcsv)):
            shutil.copy(os.path.join(test.resultdir, test.finalcsv), os.path.join(test.cwd, test.goldendir, test.finalcsv))
        return

    import operator
    temp_list = []
    temp_dict = {}
    current = open(os.path.join(test.resultdir, test.finalcsv), 'r')
    golden = open(os.path.join(test.goldendir, test.finalcsv), 'r')
    current_csvlines = current.readlines()
    golden_csvlines = golden.readlines()
    if len(current_csvlines) == len(golden_csvlines):
        test.table.append(test.tableheader)
        for i in range(1, len(golden_csvlines), test.iter):
            tok = golden_csvlines[i].split(',')
            version_len = len(tok)
            test.video, test.preset, test.abr, test.cqp, test.rev, test.crf, test.vbvbufsize, test.vbvmaxrate = tok[0], tok[1], tok[2], tok[3], tok[version_len-1], tok[4], tok[5], tok[6]
            for j in range(test.iter):
                tok = golden_csvlines[i+j].split(',')
                test.avg.append(float(tok[10]))
            test.fps = "%.2f" % harmonic_mean(test.avg)
            test.avg = []

            tok = current_csvlines[i].split(',')
            if tok[0] == test.video and tok[1] == test.preset and tok[2] == test.abr and tok[3] == test.cqp and tok[4] == test.crf and tok[5] == test.vbvbufsize and tok[6] == test.vbvmaxrate:
                for j in range(test.iter):
                    tok = current_csvlines[i+j].split(',')
                    test.avg.append(float(tok[10]))
                fps = "%.2f" % harmonic_mean(test.avg)
                test.avg = []
                perc_increase = float("%.2f" %(100 * ((float(fps) - float(test.fps)) / float(test.fps))))
                temp_dict['fps'] = perc_increase
                temp_dict['cmd'] = r'<tr><th>{0}</th><th>{1}</th><th>{2}</th><th>{3}</th><th>{4}</th><th>{5}</th><th>{6}</th><th>{7}</th><th>{8}</th><th>{9}</th><th>{10}</th><th>{11}</th></tr>'\
                                    .format(test.video, 
                                            test.preset, 
                                            test.abr, 
                                            test.cqp, 
                                            test.crf, 
                                            test.vbvbufsize, 
                                            test.vbvmaxrate, 
                                            test.rev.strip('\r\n'), 
                                            tok[version_len-1].strip('\r\n'), 
                                            str(test.fps), 
                                            str(fps), 
                                            perc_increase)
                temp_list.append(temp_dict)
                temp_dict = {}
                test.preset = test.abr = test.cqp = test.crf = test.vbvbufsize = test.vbvmaxrate = ''

        sorted_table = sorted(temp_list, key=operator.itemgetter('fps'))
        for list in sorted_table:
            test.table.append(list['cmd'])
        test.table.append('</table></body></html>')
        email_results(test, os.path.join(test.resultdir, test.finalcsv), os.path.join(test.cwd, test.goldendir, test.finalcsv))

    current.close()
    golden.close()
    os.remove(os.path.join(test.cwd, test.goldendir, test.finalcsv))
    shutil.copy(os.path.join(test.resultdir, test.finalcsv), os.path.join(test.cwd, test.goldendir, test.finalcsv))

def upload_csv(test):
    if not (my_ftp_url and my_ftp_user and my_ftp_pass and my_ftp_path_stable and my_ftp_path_default and my_ftp_path_defaultold and my_ftp_path_stableold):
        return

    now  = time.strftime("%Y-%m-%d-%H-%M-%S")
    import ftplib
    try:
        ftp = ftplib.FTP(my_ftp_url)
        ftp.login(my_ftp_user, my_ftp_pass.decode('base64'))
        if test.branch == 'default':
            ftp.cwd(my_ftp_path_default)
            fp = open(os.path.join(test.resultdir, test.finalcsv),'rb')
            ftp.storbinary('STOR ' + test.finalcsv,fp)
            ftp.cwd('./')
            ftp.cwd(my_ftp_path_defaultold)            
            ftp.storbinary('STOR ' + '_'.join([now, test.finalcsv]) ,fp)
        else:
            ftp.cwd(my_ftp_path_stable)
            fp = open(os.path.join(test.resultdir, test.finalcsv),'rb')
            ftp.storbinary('STOR ' + test.finalcsv,fp)
            ftp.cwd('./')
            ftp.cwd(my_ftp_path_stableold)            
            ftp.storbinary('STOR ' +'_'.join([now, test.finalcsv]),fp)
    except ftplib.all_errors, e:
        print "ftp failed", e
def Decodebitstreams_runssim(self):
    global headerhandle
    global header_numberofrows
    global header
    global path

    ssim_log=open(os.getcwd()+"//log//ssimlog.txt","w")
    hevcfiles = os.listdir(self.my_bitstreams)
    for bitstream in hevcfiles:
            dirpath = os.path.join(os.getcwd(),"decodedfiles")
            rename=bitstream.replace(".hevc", ".yuv")
            for n in range(header_numberofrows):
                    if headerhandle.cell(n, 0).value in bitstream:
                        header['video']=str(headerhandle.cell(n, 0).value)
                        header['width']=str(headerhandle.cell(n, 1).value)
                        header['height']=str(headerhandle.cell(n, 2).value)
                        header['fps']=str(headerhandle.cell(n, 3).value)
                        header['frames']=str(headerhandle.cell(n, 4).value)
            if 'ultrafast' in rename or 'superfast' in rename:
                command = path['ssim']+" "+ path['UHDcode']+" "+"-b "+os.path.join(self.my_bitstreams,bitstream)+" -o "+os.path.join(os.getcwd(),"decodedfiles","out.yuv")+" --parallel 4 -el "+"--input"+" "+path['input_sequences']+"//"+header['video']+".yuv "+"--frames "+header['frames']+" "+"--maxcusize 64"+" "+"--csv "+dirpath+"/"+rename+"_ssim.csv "+"--width "+header['width']+" "+"--height "+header['height']
            else:
                command = path['ssim']+" "+ path['UHDcode']+" "+"-b "+os.path.join(self.my_bitstreams,bitstream)+" -o "+os.path.join(os.getcwd(),"decodedfiles","out.yuv")+" --parallel 4 -el "+"--input"+" "+path['input_sequences']+"//"+header['video']+".yuv "+"--frames "+header['frames']+" "+"--maxcusize 32"+" "+"--csv "+dirpath+"/"+rename+"_ssim.csv "+"--width "+header['width']+" "+"--height "+header['height']
            print command
            ret=sub.Popen(command, shell=True, stderr=ssim_log, stdout=ssim_log)
            if ret.wait()!=0:
                print("error while running ssim tool")
    ssim_log.close()
    shutil.copy(os.path.join(self.resultdir,'x265Benchmark.csv'),'../plotgraphs')

def main():
    # create object
    test = Test()
    test.cwd = os.getcwd()

    # setup ramdisk path if created
    test.ramdisk()

    # parse the arguments
    for i in range(len(sys.argv)):
        test.parse(sys.argv[i], i)
    if not test.cfg:
        test.cfg = 'commands.conf.txt'

    # set up working directory
    test.setup_workingdir()

    # prepare command lines to run
    test.prepare_commands()

    # run the encoder
    encode(test)

    # remove video and move bitstreams from ramdisk
    test.remove_movefiles()

    # close the encoder log file
    test.logfp.close()
    # add extra columns for video, preset and rate control options in csv
    if regeneratecsv == True:
        regeneratecsv(test)
    # compare current test results with golden(previous) test results
    if my_compareFPS == True:
        compare(test)

    # upload csv file on egnyte
    if my_csvupload == True:
        upload_csv(test)
    # Decoding and comparing the ssim value
    if Decodebitstream == True:
        global headerhandle
        global header_numberofrows
        for folder in ["decodedfiles","log"]:
            if os.path.exists(folder):
                if not os.path.exists(folder+"//older"):
                    os.mkdir(folder+"//older")
            else:
                os.mkdir(folder)
        if not os.path.exists(os.path.join(os.getcwd(),"HeaderInfo.xls")):
            print "HeaderInfo.xls is missing"
            exit(0)
        wb = xlrd.open_workbook(test.cwd+"//HeaderInfo.xls")
        config = wb.sheet_by_name('Configuration')
        config_numberofrows=config.nrows
        headerhandle = wb.sheet_by_name('HeaderInfo')
        header_numberofrows=headerhandle.nrows
        for i in range(config_numberofrows):
            if config.cell(i, 0).value=='input_sequences':
                path['input_sequences']=str(config.cell(i, 1).value)
            elif config.cell(i, 0).value=='ssim':
                path['ssim']=str(config.cell(i, 1).value)
            elif config.cell(i, 0).value=='UHDcode':
                path['UHDcode']=str(config.cell(i, 1).value)
        Decodebitstreams_runssim(test)
        os.chdir('../plotgraphs')
        os.system("python plot.py")

if __name__ == "__main__":
    main()
