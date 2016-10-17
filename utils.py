# Copyright (C) 2015 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version. See COPYING

import atexit
import datetime
import filecmp
import md5
import os
import platform
import random
import shutil
import shlex
import sys
import tempfile
import time
import urllib
from subprocess import Popen, PIPE
from distutils.spawn import find_executable
import multiprocessing
import wrapper
run_make  = True     # run cmake and make/msbuild
run_bench = True     # run test benches
rebuild   = False    # delete build folders prior to build
save_results = True  # allow new golden outputs or pass/fail files
save_changed = False # save output bitstreams with valid changes
only_string = None   # filter tests - only those matching this string
skip_string = None   # filter tests - all except those matching this string
test_file = None     # filename or full path of file containing test cases
testrev = None       # revision under test
changers = None      # list of all output changing commits which are ancestors
                     # of the revision under test
changefilter = {}
vbv_tolerance = .05 # fraction of bitrate difference allowed (5%)
abr_tolerance = .10 # fraction of abr difference allowed (10%)
fps_tolerance = .10  # fraction of fps difference allowed (10%)
logger = None
buildObj = {}
spot_checks = []


try:
    from conf import encoder_binary_name
except ImportError, e:
    encoder_binary_name = 'x265'
	
try:
    from conf import feature, feature_value
except ImportError, e:
    feature, feature_value = False, ''
	
try:
    from conf import encoder_library_name
except ImportError, e:
    encoder_library_name = 'libx265'
if not os.path.exists(encoder_binary_name):
    os.mkdir(encoder_binary_name)

try:
    from conf import version_control
except ImportError, e:
    version_control = 'hg'
hg = True if version_control == 'hg' else False

bitstream = 'bitstream.hevc' if hg else 'bitstream.h264'
testhashlist = []

try:
    from conf import my_machine_name, my_machine_desc, my_x265_source 
    from conf import my_sequences, my_goldens, option_strings, my_hm_decoder
    from conf import my_pastebin_key, my_progress, my_tempfolder, my_builds

    # support ~/repos/x265 syntax
    my_x265_source = os.path.expanduser(my_x265_source)
    my_sequences = os.path.expanduser(my_sequences)
    my_goldens = os.path.expanduser(my_goldens)
    my_hm_decoder = os.path.expanduser(my_hm_decoder)
    my_tempfolder = os.path.expanduser(my_tempfolder)

    # backward compatibility check
    for key in my_builds:
        opts = my_builds[key][4]
        if 'mingw' in opts:
            print '** `mingw` keyword for MinGW path is deprecated, use PATH'
            opts['PATH'] = opts['mingw']
except ImportError, e:
    print e
    print 'Copy conf.py.example to conf.py and edit the file as necessary'
    sys.exit(1)

try:
    from conf import check_binary, check_variable, fps_check_variable
except ImportError, e:
    check_binary, check_variable, fps_check_variable = None, None, None

try:
    from conf import my_make_flags
except ImportError, e:
    print '** `my_make_flags` not defined in conf.py, defaulting to []'
    my_make_flags = []

try:
    from conf import my_email_from, my_email_to, my_smtp_pwd, my_smtp_host
    from conf import my_smtp_port
except ImportError, e:
    print '** `my_email_*` not defined in conf.py, defaulting to None'
    my_email_from, my_email_to, my_smtp_pwd = None, None, None

try:
    from conf import my_save_changed
    save_changed = my_save_changed
except ImportError, e:
    pass

try:
    from conf import my_coredumppath
    my_coredumppath = os.path.expanduser(my_coredumppath)
except ImportError, e:
    print '** `my_coredumppath` not defined in conf.py, defaulting to none'
    my_coredumppath = None

try:
    from conf import my_ftp_url, my_ftp_user, my_ftp_pass, my_ftp_folder
    from conf import my_binaries_upload
except ImportError, e:
    my_ftp_url, my_ftp_user, my_ftp_pass, my_ftp_folder = None, None, None, None
    my_binaries_upload = []

try:
    from conf import my_local_changers
except ImportError, e:
    my_local_changers = False

try:
    from conf import my_shellpath
except ImportError, e:
    my_shellpath = ''

try:
    from conf import my_libpairs
except ImportError, e:
    my_libpairs = []

osname = platform.system()
if osname == 'Windows':
    exe_ext         = '.exe'
    if my_shellpath:
        dll_ext         = '.a'
    else:
        dll_ext         = '.dll'
    static_lib      = 'x265-static.lib'
    lib_main        = 'x265-static-main.lib'
    lib_main10      = 'x265-static-main10.lib'
    lib_main12      = 'x265-static-main12.lib'
    extra_link_flag = ''
else:
    exe_ext         = ''
    static_lib      = 'libx265.a'
    lib_main        = 'libx265_main.a'
    lib_main10      = 'libx265_main10.a'
    lib_main12      = 'libx265_main12.a'
    extra_link_flag = r'-DEXTRA_LINK_FLAGS=-L.'
    if osname == 'Darwin':
        dll_ext     = '.dylib'
    elif osname == 'Linux':
        dll_ext     = '.so'

class Build():
    def __init__(self, *args):
        self.folder, self.group, self.gen, self.cmakeopts, self.opts = args
        co = self.cmakeopts.split()
        if 'add-depths' in self.opts:
            self.profile = 'multilib'
        else:
            for p in ('main', 'main10', 'main12'):
                if p in co:
                    self.profile = p
                    break
            else:
                self.profile = 'main'

        if 'Visual Studio' in self.gen:
            if 'debug' in co:
                self.target = 'Debug'
            elif 'reldeb' in co:
                self.target = 'RelWithDebInfo'
            else:
                self.target = 'Release'
            self.exe = os.path.abspath(os.path.join(encoder_binary_name, self.folder, 'default', self.target, encoder_binary_name + exe_ext))
            self.dll = os.path.abspath(os.path.join(encoder_binary_name, self.folder, 'default', self.target, encoder_library_name + dll_ext))
            self.testbench = os.path.abspath(os.path.join(encoder_binary_name, self.folder, 'default', 'test', self.target, 'TestBench' + exe_ext))
        else:
            self.target = ''
            self.exe = os.path.abspath(os.path.join(encoder_binary_name, self.folder, 'default', encoder_binary_name + exe_ext))
            self.dll = os.path.abspath(os.path.join(encoder_binary_name, self.folder, 'default', encoder_library_name + dll_ext))
            self.testbench = os.path.abspath(os.path.join(encoder_binary_name, self.folder, 'default', 'test', 'TestBench' + exe_ext))
    def cmakeoptions(self, cmakeopts, prof):
        for o in self.cmakeopts.split():
            if o in option_strings:
                for tok in option_strings[o].split():
                    cmakeopts.append(tok)
            else:
                logger.write('Unknown cmake option', o)

        if not isancestor('65d004d54895'): # cmake: introduce fprofile options
            pass
        elif 'Makefiles' not in self.gen:
            pass # our cmake script does not support PGO for MSVC yet
        elif prof is 'generate':
            cmakeopts.append('-DFPROFILE_GENERATE=ON')
            cmakeopts.append('-DFPROFILE_USE=OFF')
        elif prof is 'use':
            cmakeopts.append('-DFPROFILE_GENERATE=OFF')
            cmakeopts.append('-DFPROFILE_USE=ON')
        elif hg:
            cmakeopts.append('-DFPROFILE_GENERATE=OFF')
            cmakeopts.append('-DFPROFILE_USE=OFF')

        # force the default of release build if not already specified
        if '-DCMAKE_BUILD_TYPE=' not in ' '.join(cmakeopts) and hg:
            cmakeopts.append('-DCMAKE_BUILD_TYPE=Release')

    def cmake_build(self, key, cmakeopts, buildfolder):
        cout, cerr = cmake(self.gen, buildfolder, cmakeopts, **self.opts)
        empty = True
        if cerr:
            prefix = 'cmake errors reported for %s:: ' % key
            errors = cout + cerr
            _test.failuretype = 'cmake errors'
        elif 'Makefiles' in self.gen:
            errors = gmake(buildfolder, self.gen, **self.opts)
            prefix = 'make warnings or errors reported for %s:: ' % key
            _test.failuretype = 'make warnings or errors'
        elif 'Visual Studio' in self.gen:
            errors = msbuild(key, buildfolder, self.gen, cmakeopts)
            prefix = 'msbuild warnings or errors reported for %s:: ' % key
            _test.failuretype = 'msbuild warnings or errors'
        else:
            raise NotImplemented()

        if errors:
            table(_test.failuretype, empty, empty, logger.build.strip('\n'))		
            logger.writeerr(prefix + '\n' + errors + '\n')

class Logger():
    def __init__(self, testfile):
        testharnesspath = os.path.dirname(os.path.abspath(__file__))
        nowdate = datetime.datetime.now().strftime('log-%y%m%d%H%M')
        self.testname = os.path.splitext(os.path.basename(testfile))[0]
        self.logfname = '%s-%s.txt' % (nowdate, self.testname)
        print 'Logging test results to %s\n' % self.logfname
        self.start_time = datetime.datetime.now()
        self.errors = 0
        self.testcount = 0
        self.totaltests = 0
        self.newoutputs = {}
        self.logfp = open(os.path.join(encoder_binary_name, self.logfname), 'wb')
        self.header  = '\nsystem:      %s\n' % my_machine_name
        self.header += 'hardware:    %s\n' % my_machine_desc
        self.header += 'testharness: %s\n' % hgversion(testharnesspath, True)
        self.header += '%s\n' % hgrevisioninfo(hgversion(my_x265_source))
        htmltable = "style='font-size:15px; font-family: Times New Roman'"
        self.tableheader = r'<tr><th rowspan = "2">{0}</th><th rowspan = "2">{1}</th><th rowspan = "2">{2}</th><th rowspan = "2">{3}</th><th colspan = "3">{4}</th><th rowspan = "2">{5}</th><th colspan = "3">{6}</th></tr>'.format('Failure Type','Failure Commands','Build','Previous Good Revision','Previous Values','Current Revision','Current Values',)
        self.tableheader2 = r'<tr> <th>Bitrate</th><th>SSIM</th><th>PSNR</th> <th>Bitrate</th><th>SSIM</th><th>PSNR</th> </tr>'
        self.table = ['<htm><body ' + htmltable +' ><table border="1">']
        self.table.append(self.tableheader)
        self.table.append(self.tableheader2)
        self.logfp.write(self.header + '\n')
        self.logfp.write('Running %s\n\n' % testfile)
        self.logfp.flush()

    def setbuild(self, key):
        '''configure current build info'''
        b = buildObj[key]
        self.build  = 'cur build: %s group=%s\n' % (key, b.group)
        self.build += 'generator: %s\n' % b.gen
        self.build += 'options  : %s %s\n' % (b.cmakeopts, str(b.opts))
        self.logfp.write(self.build + '\n')
        self.logfp.flush()

    def logrevs(self, lastchange):
        '''configure current revision info'''
        self.write('Revision under test:')
        self.write(hgrevisioninfo(testrev))
        #self.write('Most recent output changing commit:')
        #self.write(hgrevisioninfo(lastchange))

    def read(self):
        return open(self.logfname, 'r').read()

    def write(self, *args):
        '''print text to stdout and maybe write to file'''
        print ' '.join(args)

    def newgolden(self, commit):
        self.write('new golden outputs stored, credited to %s' % commit)
        self.logfp.write(self.test)
        self.logfp.write('new outputs credited to <%s>\n\n' % commit)
        self.logfp.flush()
        if commit in self.newoutputs:
            self.newoutputs[commit] += 1
        else:
            self.newoutputs[commit] = 1
			
    def summaryfile(self, commit):
        self.write('summary.txt file does not exist for <%s> \n\n' % commit)
        self.logfp.write(self.test)
        self.logfp.write('summary.txt file does not exist <%s>\n\n' % commit)
        self.logfp.flush()			

    def writeerr(self, message):
        '''cmake, make, or testbench errors'''
        # TODO: wrapper for pastebin
        if os.linesep == '\r\n':
            message = message.replace(os.linesep, '\n')
        self.logfp.write(message + '\n')
        self.logfp.flush()
        self.errors += 1

    def settest(self, seq, command, extras, hash):
        '''configure current test case'''
        self.test  = 'command: %s %s\n' % (seq, command)
        self.test += '   hash: %s\n' % hash
        self.test += ' extras: ' + ' '.join(extras) + '\n\n'
        self.tablecommand = '%s %s'% (seq, command)
        self.tablecommand += '  '.join(extras)        
        nofn = '[%d/%d]' % (self.testcount, self.totaltests)
        self.settitle(' '.join([nofn, seq, command]))
        print nofn,

    def settestcount(self, count):
        self.totaltests = count

    def settitle(self, str):
        '''set console title'''
        title = '%s: %s' % (platform.node(), str)
        if os.name == 'nt':
            try:
                import ctypes
                ctypes.windll.kernel32.SetConsoleTitleA(title)
                return
            except ImportError:
                pass
            try:
                import win32console
                win32console.SetConsoleTitle(title)
                return
            except ImportError:
                pass
        elif 'xterm' in os.getenv('TERM', ''):
            sys.stdout.write("\x1b]2;%s\x07" % title)

    def testfail(self, prefix, errors, logs):
        '''encoder test failures'''
        if my_pastebin_key:
            url = pastebin('\n'.join([self.header, self.build, self.test,
                                      prefix, errors, logs]))
            self.write(' '.join([prefix, url]))
            self.logfp.write('\n'.join(['**', self.test, prefix, url, '']))
        else:
            message = '\n'.join([prefix, errors, logs])
            if os.linesep == '\r\n':
                message = message.replace(os.linesep, '\n')
            self.write(prefix)
            self.logfp.write('**\n\n' + self.test)
            self.logfp.write(message + '\n')
        self.logfp.flush()
        self.errors += 1

    def close(self, logfp):
        for co, count in self.newoutputs.iteritems():
            msg = '%d test case output changes credited to %s\n' % (count, co)
            print msg
            logfp.write(msg)
        if self.errors:
            print 'Errors written to %s' % self.logfname
        else:
            msg = '\nAll tests passed for %s on %s' % (testrev, my_machine_name)
            print msg
            logfp.write(msg)
        logfp.close()
        self.settitle(os.path.basename(test_file) + ' complete')

    def email_results(self, mailid=None, message='', testedbranch=''):
        if not (my_email_from and my_email_to and my_smtp_pwd):
            return

        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        if mailid and message:
            global my_email_to
            my_email_to = mailid

        msg = MIMEMultipart('alternative')
        duration = str(datetime.datetime.now() - self.start_time).split('.')[0]
        logger.table.append('</table>')
        tableMsg = ''.join(logger.table)
        textMsg = "<br> Test Duration(H:M:S) = " + duration + "<br>" + open(os.path.join(encoder_binary_name, self.logfname), 'r').read()+ "<br><br>"
        if type(my_email_to) is str:
            msg['To'] = my_email_to
        else:
            msg['To'] = ", ".join(my_email_to)
        textStyle = "style='font-size:15px; font-family: Times New Roman'"
        failure_message = MIMEText(tableMsg + '<pre ' + textStyle +' >' + textMsg + '</pre></body></html>', 'html')
        success_message = MIMEText('<pre ' + textStyle +' >' + textMsg + '</pre></body></html>', 'html')
        msg['From'] = my_email_from
        testname = self.testname.split('-')
        status = self.errors and 'failures' or 'successful'
        branch = testedbranch if testedbranch else hggetbranch(testrev)
        if feature:
            data = [feature_value, ': '] + [platform.system(), '-'] + testname + [status, '-', branch] + ['-', str(multiprocessing.cpu_count())] + ['core']
        else:
            data = [encoder_binary_name, ': '] + [platform.system(), '-'] + testname + [status, '-', branch] + ['-', str(multiprocessing.cpu_count())] + ['core'] + ['-', message]
        msg['Subject'] = ' '.join(data)
        if self.errors:
            msg.attach(failure_message)
        else:
            msg.attach(success_message)        
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

def setup(argv, preferredlist):
    if not find_executable(version_control):
        raise Exception('Unable to find Mercurial executable %s' %version_control)
    if not find_executable('cmake'):
        raise Exception('Unable to find cmake executable')
    if not find_executable(my_hm_decoder):
        raise Exception('Unable to find HM decoder')
    if not os.path.exists(os.path.join(my_x265_source, 'CMakeLists.txt')) and not os.path.exists(os.path.join(my_x265_source, 'configure')):
        raise Exception('my_x265_source does not point to x265 source/ folder')

    global run_make, run_bench, rebuild, save_results, test_file, skip_string
    global only_string, save_changed

    if my_tempfolder:
        tempfile.tempdir = my_tempfolder

    test_file = preferredlist

    import getopt
    longopts = ['builds=', 'help', 'no-make', 'no-bench', 'only=', 'rebuild',
                'save-changed', 'skip=', 'tests=']
    optlist, args = getopt.getopt(argv[1:], 'hb:t:', longopts)
    for opt, val in optlist:
        # restrict the list of target builds to just those specified by -b
        # for example: ./smoke-test.py -b "gcc32 gcc10"
        if opt in ('-b', '--builds'):
            userbuilds = val.split()
            delkeys = [key for key in my_builds if not key in userbuilds]
            for key in delkeys:
                del my_builds[key]
        elif opt == '--skip':
            skip_string = val
        elif opt == '--only':
            only_string = val
        elif opt in ('-t', '--tests'):
            test_file = val
        elif opt == '--save-changed':
            save_changed = True
        elif opt == '--no-make':
            run_make = False
        elif opt == '--no-bench':
            run_bench = False
        elif opt == '--rebuild':
            rebuild = True
        elif opt in ('-h', '--help'):
            print sys.argv[0], '[OPTIONS]\n'
            print '\t-h/--help            show this help'
            print '\t-b/--builds <string> space seperated list of build targets'
            print '\t-t/--tests <fname>   location of text file with test cases'
            print '\t   --skip <string>   skip test cases matching string'
            print '\t   --only <string>   only test cases matching string'
            print '\t   --save-changed    save bitstreams with changed outputs'
            print '\t   --no-make         do not compile sources'
            print '\t   --no-bench        do not run test benches'
            print '\t   --rebuild         remove old build folders and rebuild'
            sys.exit(0)

    listInRepo = os.path.join(my_x265_source, 'test', test_file)
    if os.sep not in test_file and os.path.exists(listInRepo):
        test_file = listInRepo
    elif not os.path.exists(test_file):
        raise Exception('Unable to find test list file ' + test_file)

    global buildObj
    for key in my_builds:
        buildObj[key] = Build(*my_builds[key])

    global logger, testrev, changers
    logger = Logger(test_file)

    def closelog(logfp):
        logger.close(logfp)
    atexit.register(closelog, logger.logfp)

    testrev = hgversion(my_x265_source)
    if encoder_binary_name == check_binary:
        save_results = True
    elif testrev.endswith('+'):	
        # we do not store golden outputs if uncommitted changes
        save_results = False
        testrev = testrev[:-1]
    elif hggetphase(testrev) != 'public':
        # we do not store golden outputs until a revision is public (pushed)
        save_results = False
    else:
        save_results = True

    if not save_results:
        logger.write('NOTE: Revision under test is not public or has uncommited changes.')
        logger.write('No new golden outputs will be generated during this run, neither')
        logger.write('will it create pass/fail files.\n')

    changers = findchangeancestors()
    logger.logrevs(changers[0])
    initspotchecks()


ignored_x265_warnings = (
    '--psnr used with psy on: results will be invalid!',
    '--ssim used with AQ off: results will be invalid!',
    '--psnr used with AQ on: results will be invalid!',
    '--tune psnr should be used if attempting to benchmark psnr!',
    '--tune ssim should be used if attempting to benchmark ssim!',
    'Assembly not supported in this binary',
    '!! HEVC Range Extension specifications are not finalized !!',
    '!! This output bitstream may not be compliant with the final spec !!',
    'Max TU size should be less than or equal to max CU size, setting max TU size = 16',
    'QGSize should be less than or equal to maxCUSize, setting QGSize = 16',
    'QGSize should be less than or equal to maxCUSize, setting QGSize = 32',
    'No thread pool allocated, --wpp disabled',
    'No thread pool allocated, --pme disabled',
    'Support for interlaced video is experimental',
    'y4m: down-shifting reconstructed pixels to 8 bits',
    'level 5 detected, but NumPocTotalCurr (total references) is non-compliant',
    'Analysis load/save options incompatible with pmode/pme, Disabling pmode/pme',
    '--rect disabled, requires --rdlevel 2 or higher',
    '--cu-lossless disabled, requires --rdlevel 3 or higher',
    'Source height < 720p; disabling lookahead-slices',
    'Limit reference options 2 and 3 are not supported with pmode. Disabling limit reference',
    'Analysis load/save options works only with cu-tree off, Disabling cu-tree',
    'Rc Grain removes qp fluctuations caused by aq/cutree, Disabling aq,cu-tree',
    '--tskip disabled, requires --rdlevel 3 or higher'	
)


if os.name == 'nt':

    # LOL Windows
    # Use two threads to poll stdout and stderr and write into queues
    # http://stackoverflow.com/questions/375427/non-blocking-read-on-a-subprocess-pipe-in-python

    def enqueue_output(fd, q):
        try: 
            while True:
                line = fd.readline()
                if line:
                    q.put(line)
                else:
                    return
        except:
            fd.close()

    def async_poll_process(proc, fulloutput):
        from Queue import Queue, Empty
        from threading import Thread
        qout = Queue()
        tout = Thread(target=enqueue_output, args=(proc.stdout, qout))
        tout.start()

        qerr = Queue()
        terr = Thread(target=enqueue_output, args=(proc.stderr, qerr))
        terr.start()

        out = []
        errors = ''
        exiting = False
        output = ''
        while True:
            # note that this doesn't guaruntee we get the stdout and stderr
            # lines in the intended order, but they should be close
            try:
                while not qout.empty():
                    line = qout.get()
                    if fulloutput: output += line
                    if my_progress: print line,
                    out.append(line)
            except Empty:
                pass

            if not qerr.empty():
                try:
                    while not qerr.empty():
                        line = qerr.get()
                        if fulloutput: output += line
                        if my_progress: print line,
                        if 'PIE' not in line:
                            errors += ''.join(out[-3:])
                            out = []
                            errors += line
                except Empty:
                    pass

            if proc.poll() != None and not exiting:
                tout.join()
                terr.join()
                exiting = True
            elif exiting and qerr.empty() and qout.empty():
                break

        if proc.returncode and not errors:
            errors = ''.join(out[-10:])
        if proc.returncode == -11:
            errors += 'SIGSEGV\n'
        elif proc.returncode == -10:
            errors += 'SIGBUS\n'
        elif proc.returncode == -6:
            errors += 'SIGABRT\n'
        elif proc.returncode == -4:
            errors += 'SIGILL\n'
        elif proc.returncode:
            errors += 'return code %d\n' % proc.returncode
        if fulloutput:
            return output, errors
        else:
            return errors

else:

    # POSIX systems have select()

    import select

    def async_poll_process(proc, fulloutput):
        out = []
        errors = ''
        output = ''
        exiting = False

        # poll stdout and stderr file handles so we get errors in the context
        # of the stdout compile progress reports
        while True:
            fds = [proc.stdout.fileno(), proc.stderr.fileno()]
            ret = select.select(fds, [], [])

            empty = True
            for fd in ret[0]:
                if fd == proc.stdout.fileno():
                    line = proc.stdout.readline()
                    if line:
                        empty = False
                        if fulloutput: output += line
                        if my_progress: print line,
                        out.append(line)
                if fd == proc.stderr.fileno():
                    line = proc.stderr.readline()
                    if line:
                        empty = False
                        if fulloutput: output += line
                        if my_progress: print line,
                        if 'PIE' not in line:
                            errors += ''.join(out[-3:])
                            out = []
                            errors += line
            if proc.poll() != None and not exiting:
                exiting = True
            elif exiting and empty:
                break

        if proc.returncode and not errors:
            errors = ''.join(out[-10:])
        if proc.returncode == -11:
            errors += 'SIGSEGV\n'
        elif proc.returncode == -10:
            errors += 'SIGBUS\n'
        elif proc.returncode == -6:
            errors += 'SIGABRT\n'
        elif proc.returncode == -4:
            errors += 'SIGILL\n'
        elif proc.returncode:
            errors += 'return code %d\n' % proc.returncode
        if fulloutput:
            return output, errors
        else:
            return errors

# ftp upload x265 binaries
def upload_binaries(ftpfolder=None):
    global my_ftp_folder
    if not (my_ftp_url and my_ftp_user and my_ftp_pass and my_ftp_folder):
        return

    import ftplib
    from collections import defaultdict
    debugopts = set(['reldeb', 'ftrapv', 'noasm', 'ppa', 'debug', 'stats', 'static'])
    date = datetime.datetime.strftime(datetime.datetime.now(),'%Y_%m_%d')
    for key in my_binaries_upload:
        build = buildObj[key]
        buildopts = set(build.cmakeopts.split())
        if buildopts & debugopts:
            print 'debug option(s) %s detected, skipping build %s' % (buildopts & debugopts, key)
            continue
        if not os.path.exists(encoder_binary_name) and not os.path.exists(os.path.join(encoder_binary_name, build.folder)):
            print '%s %s buildfolders does not exist' % encoder_binary_name % build.folder
            continue
        branch = hggetbranch(testrev)
        tagdistance = hggettagdistance(testrev)

        folder = 'Development' # default
        if branch == 'stable':
            if tagdistance.endswith('+0'):
                folder = 'Release'
                tagdistance = tagdistance[:-2]
            else:
                folder = 'Stable'
        if ftpfolder:
            my_ftp_folder = ftpfolder
        ftp_path = '/'.join([my_ftp_folder, osname, folder, build.profile])
        # open x265 binary & library files and give appropriate names for them to upload
        # ex: Darwin - x265-1.5+365-887ac5e457e0, libx265-1.5+365-887ac5e457e0.dylib
        if encoder_binary_name == 'x265':
            exe_name = '-'.join([encoder_binary_name, tagdistance, testrev]) + exe_ext
            dll_name = '-'.join([encoder_library_name, tagdistance, testrev]) + dll_ext
        else:
            if build.profile == 'main':
                exe_name = '_'.join([encoder_binary_name,'8bit', date, testrev]) + exe_ext
                dll_name = '_'.join([encoder_library_name,'8bit', date, testrev]) + dll_ext
            else:
                exe_name = '_'.join([encoder_binary_name,'10bit', date, testrev]) + exe_ext
                dll_name = '_'.join([encoder_library_name,'10bit', date, testrev]) + dll_ext
        try:
            x265 = open(build.exe, 'rb')
            dll = open(build.dll, 'rb')
            if osname == 'Linux':
                compilertype = 'gcc'
                if build.opts.get('CXX') == 'icpc':
                    compilertype = 'intel'
                ftp_path = '/'.join([my_ftp_folder, osname, compilertype, folder, build.profile])
        except EnvironmentError, e:
            logger.writeerr('failed to open x265binary or library file\n' + str(e))
            print("failed to open x265binary or library file", e)
            return

        try:
            ftp = ftplib.FTP(my_ftp_url)
            ftp.login(my_ftp_user, my_ftp_pass)
            ftp.cwd(ftp_path)

            # list the files from ftp location ex:
            # x265-1.5+365-887ac5e457e0, libx265-1.5+365-887ac5e457e0.dylib...
            list_allfiles = ftp.nlst()

            # if files is already exist, delete and re-upload
            for file in (exe_name, dll_name):
                if file in list_allfiles:
                    ftp.delete(file)

            # upload x265 binary and corresponding libraries
            ftp.storbinary('STOR ' + exe_name, x265)
            ftp.storbinary('STOR ' + dll_name, dll)
            list_allfiles = ftp.nlst()
            logger.logfp.write('\nuploaded - %s: %s, %s' %(build.profile, exe_name, dll_name))
            logger.logfp.flush()
        except ftplib.all_errors, e:
            logger.writeerr('\nftp failed to upload binaries\n' + str(e))
            print "ftp failed", e
            return
        
        if not encoder_binary_name == 'x265':
            continue

        if folder == 'Release': # never delete tagged builds
            continue
        tagrevs = defaultdict(set)
        for file in list_allfiles:
            name, tagdist, hash = file.split('-', 2)
            tag, dist = tagdist.split('+', 1)
            tagrevs[tag].add(int(dist)) # { '1.6' : (100, 110, 112) }

        # Keep M last build versions for most recent N tags, and last stable
        # build on each tag. Note that this is relying on string sorting of
        # version numbers - '1.10' would be less than '1.9' - so it is relying
        # on the policy to bump to version '2.0' following '1.9'

        M = 8
        N = folder == 'Stable' and 2 or 1
        keeprevs = []
        for tags_count, tag in enumerate(sorted(tagrevs.keys(), reverse=True)):
            revs = ['+'.join([tag, str(rev)]) for rev in sorted(tagrevs[tag], reverse=True)]
            if tags_count < N:
                keeprevs.extend(revs[:M])
            elif folder == 'Stable':
                keeprevs.append(revs[0])
            else:
                break

        for file in list_allfiles:
            name, tagdist, hash = file.split('-', 2)
            if tagdist not in keeprevs:
                ftp.delete(file)

# save binaries, core dump and required files to debug
def save_coredump(tmpfolder, binary):
    if not my_coredumppath or not os.path.exists(my_coredumppath):
        return 'core dump saving not enabled\n'
    try:
        dest_dir = os.path.join(my_coredumppath, time.strftime("%d-%m-%Y_%H-%M-%S"))
        os.mkdir(dest_dir)
        if binary:
            shutil.copy(binary, dest_dir)
        for filename in os.listdir(my_coredumppath):
            if not os.path.isdir(os.path.join(my_coredumppath, filename)):
                shutil.move(os.path.join(my_coredumppath, filename), dest_dir)
        for filename in os.listdir(tmpfolder):
            if not os.path.isdir(os.path.join(tmpfolder, filename)):
                shutil.copy(os.path.join(tmpfolder,filename), dest_dir)
        return 'core dump file stored in %s\n\n' % dest_dir
    except EnvironmentError, e:
        return 'unable to save coredump, ' + str(e) + '\n'

def parseYuvFilename(fname):
    '''requires the format: foo_bar_WxH_FPS[_10bit][_CSP][_crop].yuv'''

    if not fname.lower().endswith('.yuv'):
        raise Exception('parseYuv only supports YUV files')

    # these steps can raise all manor of index exceptions, callers must
    # catch them in case the YUV filename does not match our scheme
    depth = 8
    csp = '420'
    words = fname[:-4].split('_')

    if words[-1] == 'crop':
        words.pop()

    if words[-1] in ('400','422','444'):
        csp = words.pop()

    if words[-1] == '10bit':
        depth = 10
        words.pop()

    fps = words.pop()
    width, height = words.pop().lower().split('x')

    return (width, height, fps, depth, csp)


def parseY4MHeader(fname):
    '''read important file details from the Y4M header'''
    header = open(fname, "r").readline() # read up to first newline
    if not header.startswith('YUV4MPEG2'):
        raise Exception('parseY4MHeader() did not find YUV4MPEG2 signature')

    # example: C420jpeg W854 H480 F24:1 Ip A1:1
    words = header.split()[1:]
    csp = 420
    depth = 8
    for word in words:
        if word[0] == 'C':
            csp = word[1:4]
            if word.endswith('p10'):
                depth = 10
        elif word[0] == 'W':
            width = word[1:]
        elif word[0] == 'H':
            height = word[1:]
        elif word[0] == 'F':
            fps = word[1:].replace(':', '/')
        elif word[0] in ('A', 'I'):
            pass # ignored, libx265 will parse if needed
        else:
            print 'unknown Y4M header word'

    return (width, height, fps, depth, csp)


def parsetestfile():
    global test_file, vbv_tolerance
    missing = set()
    tests = []
    for line in open(test_file).readlines():
        line = line.strip()
        if line.startswith('# vbv-tolerance ='):
            vbv_tolerance = float(line.split('=')[1])
            print 'using vbv tolerance', vbv_tolerance
        if len(line) < 3 or line[0] == '#':
            continue

        seq, command = line.split(',', 1)
        seq = seq.strip()
        command = command.strip()

        if not os.path.exists(os.path.join(my_sequences, seq)):
            if seq not in missing:
                logger.write('Ignoring missing sequence', seq)
                missing.add(seq)
            continue
        tests.append((seq, command))
    return tests


def testcasehash(sequence, command):
    m = md5.new()
    m.update(sequence)
    m.update(command)
    return m.hexdigest()[:12]


def initspotchecks():
    # these options can be added to any test and should not affect outputs
    sc = [
        '--no-asm',
        '--asm=SSE2',
        '--asm=SSE3',
        '--asm=SSSE3',
        '--asm=SSE4',
        '--asm=AVX',
        '--pme',
        '--recon=recon.yuv',
        '--recon=recon.y4m',
        '--csv=test.csv',
        '--no-progress',
        '--log-level=debug',
        '--log-level=full',
    ]
    if isancestor('63fe043f739c'):
        # these have no effect without --csv=[fname] which is
        # a different spot-check. In order for this to work we need to
        # support multi-option spot checks
        #sc.append('--csv-log-level=1')
        #sc.append('--csv-log-level=2')
        pass
    # stats: introduce X265_LOG_FRAME for file level CSV logging without console logs
    elif isancestor('a5af4cf20660'):
        sc.append('--log-level=frame')

    global spot_checks
    spot_checks = sc


def getspotcheck(cmd):
    '''pick a random spot check, but don't allow some combinations'''
    forbiddens = {
        '--log-level=none': ['vbv'],
        '--no-asm'  : ['veryslow', 'placebo'],
    }
    global spot_checks
    while True:
        sc = random.choice(spot_checks)
        f = forbiddens.get(sc, [])
        if [match for match in f if match in cmd]:
            # pick another spot-check
            continue
        return sc


def pastebin(content):
    sizelimit = 500 * 1024

    if len(content) >= sizelimit:
        content = content[:sizelimit - 30] + '\n\ntruncated to paste limit'

    pastebin_vars = {
        'api_option'     : 'paste',
        'api_dev_key'    : my_pastebin_key,
        'api_paste_code' : content
    }
    conn = urllib.urlopen('http://pastebin.com/api/api_post.php',
                          urllib.urlencode(pastebin_vars))
    url = conn.read()
    if url.startswith('http://pastebin.com/'):
        return url
    else:
        return 'pastebin failed <%s> paste contents:\n%s' % (url, content)


def hgversion(reporoot, ishg=False):
    if hg or ishg:
        out, err = Popen(['hg', 'id', '-i'], stdout=PIPE, stderr=PIPE,
                         cwd=reporoot).communicate()
    else:
        out, err = Popen(['git', 'rev-parse', 'HEAD'], stdout=PIPE, stderr=PIPE,
                        cwd=reporoot).communicate()
    if err:
        raise Exception('Unable to determine source version: ' + err)
    # note, if the ID ends with '+' it means the user's repository has
    # uncommitted changes. We will never want to save golden outputs from these
    # repositories.
    return out[:-1] # strip line feed


def hgsummary():
    if hg:
        out, err = Popen(['hg', 'summary'], stdout=PIPE, stderr=PIPE,
                        cwd=my_x265_source).communicate()
    else:
        out, err = Popen(['git', 'show', '--summary'], stdout=PIPE, stderr=PIPE,
                    cwd=my_x265_source).communicate()
    if err:
            raise Exception('Unable to determine repo summary: ' + err)
    return out


def hgrevisioninfo(rev):
    addstatus = False
    if hg:
        if rev.endswith('+'):
            rev = rev[:-1]
            addstatus = True
        out, err = Popen(['hg', 'log', '-r', rev], stdout=PIPE, stderr=PIPE,
                        cwd=my_x265_source).communicate()
    else:
        out, err = Popen(['git', 'diff-index', '--name-status', '--exit-code', 'HEAD'], stdout=PIPE, stderr=PIPE,
                        cwd=my_x265_source).communicate()
        if out:
            addstatus = True
    if err:
        raise Exception('Unable to determine revision info: ' + err)

    if addstatus:
        if hg:
            out_changes, err = Popen(['hg', 'status'], stdout=PIPE, stderr=PIPE,
                                cwd=my_x265_source).communicate()[0]
        else:
            out_changes, err = Popen(['git' ,'show', '-s', rev], stdout=PIPE, stderr=PIPE,
                                cwd=my_x265_source).communicate()
        out += 'Uncommitted changes in the working directory:\n' + out_changes
    return out


def hggetphase(rev):
    if hg:
        if rev.endswith('+'): rev = rev[:-1]
        out, err = Popen(['hg', 'log', '-r', rev, '--template', '{phase}'],
                     stdout=PIPE, stderr=PIPE, cwd=my_x265_source).communicate()
        if err:
            raise Exception('Unable to determine revision phase: ' + err)
    else:
        out_localchanges, err = Popen(['git', 'log', 'origin..HEAD'], stdout=PIPE, stderr=PIPE,
                        cwd=my_x265_source).communicate()
        out_uncommited, err = Popen(['git', 'diff-index', '--name-status', '--exit-code', 'HEAD'], stdout=PIPE, stderr=PIPE,
                        cwd=my_x265_source).communicate()
        if err:
            raise Exception('Unable to determine revision phase: ' + err)

        if out_localchanges or out_uncommited:
            return 'draft'
        return 'public'
    return out


def hgrevisiondate(rev):
    if hg:
        if rev.endswith('+'): rev = rev[:-1]
        out, err = Popen(['hg', 'log', '-r', rev, '--template', '{isodate(date)}'],
                        stdout=PIPE, stderr=PIPE, cwd=my_x265_source).communicate()
    else:
        out, err = Popen(['git', 'show', '-s', '--format=%ci', rev],
                        stdout=PIPE, stderr=PIPE, cwd=my_x265_source).communicate()
    if err:
        raise Exception('Unable to determine revision phase: ' + err)
    # isodate format is '2015-03-09 12:13 -0500', we want '15-03-09'
    return out[2:10]


def hggetbranch(rev):
    if hg:
        if rev.endswith('+'): rev = rev[:-1]
        out, err = Popen(['hg', 'log', '-r', rev, '--template', '{branch}'],
                        stdout=PIPE, stderr=PIPE, cwd=my_x265_source).communicate()
    else:
        out, err = Popen(['git', 'branch', '--contains', rev],
                        stdout=PIPE, stderr=PIPE, cwd=my_x265_source).communicate()
        out = out.replace('* ','')
    if err:
        raise Exception('Unable to determine revision phase: ' + err)
    return out

def hggettagdistance(rev):
    if rev.endswith('+'): rev = rev[:-1]
    out, err = Popen(['hg', 'log', '-r', rev, '--template', '{latesttag}+{latesttagdistance}'],
                     stdout=PIPE, stderr=PIPE, cwd=my_x265_source).communicate()
    if err:
        raise Exception('Unable to determine tag distance: ' + err)
    return out

def isancestor(ancestor):
    if hg:
        # hg log -r "descendants(1bed2e325efc) and 5ebd5d7c0a76"
        cmds = ['hg', 'log', '-r', 'ancestors(%s) and %s' % (testrev, ancestor),
               '--template', '"{node}"']
        out, err = Popen(cmds, stdout=PIPE, stderr=PIPE, cwd=my_x265_source).communicate()
        if err and 'unknown revision' not in err:
            raise Exception('Unable to determine ancestry: ' + err)
    else:
        out, err = Popen(['git', 'merge-base', '--is-ancestor',  ancestor, testrev],
                        stdout=PIPE, stderr=PIPE, cwd=my_x265_source).communicate()
        if err and 'Not a valid object name' not in err:
            raise Exception('Unable to determine ancestry: ' + err)
        if not out: out = 1
    return bool(out)

def getcommits():
    fname = 'output-changing-commits.txt'
    hashlen = 12 if hg else 40

    def testrev(lines):
        for line in lines[::-1]:
            if len(line) < hashlen or line[0] == '#': continue
            rev = line[:hashlen]
            if hg:
                cmds = ['hg', 'log', '-r', '%s' % (rev)]
                out, err = Popen(cmds, stdout=PIPE, stderr=PIPE, cwd=my_x265_source).communicate()
            else:
                out, err = Popen(['git' ,'show', '-s', rev], stdout=PIPE, stderr=PIPE,
                                cwd=my_x265_source).communicate()
            if not ': unknown revision' in err:
                return lines
            else:
                return open(os.path.abspath(os.path.join(my_x265_source, 'test', fname))).readlines()

    if hg:
        out = Popen(['hg', 'status', fname], stdout=PIPE).communicate()[0]
    else:
        out = Popen(['git', 'diff', fname], stdout=PIPE).communicate()[0]

    if 'M' in out or 'diff' in out:
        if my_local_changers:
            print 'local %s is modified, disabling download' % fname
            l = testrev(open(fname).readlines())
            return l
        else:
            print 'changes in %s ignored, my_local_changers is false' % fname
    try:
        print 'Downloading most recent list of output changing commits...',
        l = urllib.urlopen('https://bitbucket.org/sborho/test-harness/raw/tip/' + \
                          fname).readlines()
        print 'done\n'
        l = testrev(l)
        return l
    except EnvironmentError:
        print 'failed\nWARNING: using local copy of', fname
        print '         it may not be up to date\n'
        l = testrev(open(fname).readlines())
        return l
def findchangeancestors():
    '''
    output-changing-commits.txt must contain the hashes (12-bytes) of
    commits which change outputs. All commits which are ancestors of these
    commits should match outputs (unless they are also listed). New output
    changing commits must be added on top so they are found before any of
    their ancestor commits.

    Lines starting with a hash are considered comments, text after the 12 byte
    hash are ignored and can be used to describe the commit

    Returns a list of all output changing commits which are ancestors of the
    current revision under test.
    '''
    lines = getcommits()

    global changefilter
    ancestors = []
    hashlen = 12 if hg else 40
    for line in lines:
        if len(line) < hashlen or line[0] == '#': continue
        rev = line[:hashlen]
        if isancestor(rev):
            ancestors.append(rev)
            comment = line[hashlen+1:]
            if comment.startswith('[') and ']' in comment:
                contents = comment[1:].split(']', 1)[0]
                changefilter[rev] = contents.split(',')

    return ancestors or [testrev]


def cmake(generator, buildfolder, cmakeopts, **opts):
    # buildfolder is the relative path to build folder
    logger.settitle('cmake ' + buildfolder)

    cmds = ['cmake', '-Wno-dev', os.path.abspath(my_x265_source)]

    if generator:
        cmds.append('-G')
        cmds.append(generator)
        if 'CFLAGS' in opts:
            cmds.append('-DCMAKE_C_COMPILER_ARG1=' + opts['CFLAGS'])
            cmds.append('-DCMAKE_CXX_COMPILER_ARG1=' + opts['CFLAGS'])

    cmds.extend(cmakeopts)

    env = os.environ.copy()
    if generator:
        if 'CC' in opts:
            env['CC'] = opts['CC']
        if 'CXX' in opts:
            env['CXX'] = opts['CXX']

    # note that it is not enough to insert the path into the subprocess
    # environment; it must be in the system PATH in case the compiler
    # spawns subprocesses of its own that take the system PATH (cough, mingw)
    origpath = os.environ['PATH']
    if 'PATH' in opts:
        os.environ['PATH'] += os.pathsep + opts['PATH']
        env['PATH'] += os.pathsep + opts['PATH']

    if not hg:
        cmds = [my_shellpath, './configure']
        cmds.append(' '.join(cmakeopts))
        proc = Popen(' '.join(cmds), cwd=my_x265_source, stdout=PIPE, stderr=PIPE, env=env)
    else:
        proc = Popen(cmds, stdout=PIPE, stderr=PIPE, cwd=buildfolder, env=env)
    out, err = proc.communicate()
    os.environ['PATH'] = origpath
    return out, err


def gmake(buildfolder, generator, **opts):
    logger.settitle('make ' + buildfolder)
    if 'MinGW' in generator and hg:
        cmds = ['mingw32-make']
    else:
        cmds = ['make']
    if my_make_flags:
        cmds.extend(my_make_flags)

    origpath = os.environ['PATH']
    if 'PATH' in opts:
        os.environ['PATH'] += os.pathsep + opts['PATH']
    if not hg:
        out, errors = Popen(cmds, cwd=my_x265_source, stdout=PIPE, stderr=PIPE).communicate()
        import glob
        dll = glob.glob(os.path.join(my_x265_source,'*.dll'))
        if os.path.exists(os.path.join(my_x265_source, 'x264.exe')):
            shutil.copy(os.path.abspath(os.path.join(my_x265_source, 'x264' + exe_ext)), os.path.abspath(os.path.join(buildfolder, 'x264' + exe_ext)))
            for file in  dll:
                shutil.copy(os.path.abspath(os.path.join(my_x265_source, file)), os.path.abspath(os.path.join(buildfolder)))
        return errors
    else:
        p = Popen(cmds, stdout=PIPE, stderr=PIPE, cwd=buildfolder)
    errors = async_poll_process(p, False)
    os.environ['PATH'] = origpath
    return errors


vcvars = ('include', 'lib', 'mssdk', 'path', 'regkeypath', 'sdksetupdir',
          'sdktools', 'targetos', 'vcinstalldir', 'vcroot', 'vsregkeypath')

def get_sdkenv(vcpath, arch):
    '''extract environment vars set by vcvarsall for compiler target'''

    vcvarsall = os.path.abspath(os.path.join(vcpath, 'vcvarsall.bat'))
    if not os.path.exists(vcvarsall):
        raise Exception(vcvarsall + ' not found')

    p = Popen(r'cmd /e:on /v:on /c call "%s" %s && set' % (vcvarsall, arch),
              shell=False, stdout=PIPE, stderr=PIPE)
    out, err = p.communicate()
    newenv = {}
    for line in out.splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            if k.lower() in vcvars:
                newenv[k.upper()] = v
    return newenv


def msbuild(buildkey, buildfolder, generator, cmakeopts):
    '''Build visual studio solution using specified compiler'''
    logger.settitle('msbuild ' + buildfolder)
    if os.name != 'nt':
        raise Exception('Visual Studio builds only supported on Windows')

    # Look for Visual Studio install location within the registry
    key = r'SOFTWARE\Wow6432Node\Microsoft\VisualStudio'
    if '12' in generator:
        key += r'\12.0'
    elif '11' in generator:
        key += r'\11.0'
    elif '10' in generator:
        key += r'\10.0'
    elif '9' in generator:
        key += r'\9.0'
    else:
        raise Exception('Unsupported VC version')

    import _winreg
    vcpath = ''
    win32key = 'SOFTWARE' + key[20:] # trim out Wow6432Node\
    for k in (key, win32key):
        try:
            hkey = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, k)
            pfx = _winreg.QueryValueEx(hkey, 'InstallDir')[0]
            if pfx and os.path.exists(pfx):
                vcpath = os.path.abspath(pfx + r'\..\..\VC')
                break;
        except (WindowsError, EnvironmentError), e:
            pass

    if not vcpath:
        raise Exception(win32key + ' not found or is invalid')

    if 'Win64' in generator:
        arch = 'x86_amd64'
    else:
        arch = 'x86'

    sdkenv = get_sdkenv(vcpath, arch)
    env = os.environ.copy()
    env.update(sdkenv)

    build = buildObj[buildkey]
    target = ''.join(['/p:Configuration=', build.target])

    # use the newest MSBuild installed
    for f in (r'C:\Program Files (x86)\MSBuild\12.0\Bin\MSBuild.exe',
              r'C:\Windows\Microsoft.NET\Framework\v4.0.30319\MSBuild.exe',
              r'C:\Windows\Microsoft.NET\Framework\v3.5\MSBuild.exe'):
        if os.path.exists(f):
            msbuild = f
            break
    else:
        msbuild = find_executable('msbuild')
        if not msbuild:
            raise Exception('Unable to find msbuild.exe')

    p = Popen([msbuild, '/clp:disableconsolecolor', target, encoder_binary_name + '.sln'],
              stdout=PIPE, stderr=PIPE, cwd=buildfolder, env=env)
    out, err = async_poll_process(p, True)
    if not err:
        warnings = []
        for line in out.splitlines(True):
            if 'MSBUILD : warning MSB' in line: # vc9 is a mess
                continue
            if 'warning' in line:
                warnings.append(line.strip())
                logger.write(line.strip())
        if warnings:
            err = '\n'.join(warnings)
    return err


def buildall(prof=None, buildoptions=None):
    global rebuild
    if not run_make:
        return
    if not buildoptions == None:
        rebuild = True
        global buildObj
        buildObj = {}
        for key in buildoptions:
            buildObj[key] = Build(*buildoptions[key])
    for key in buildObj:
        logger.setbuild(key)
        logger.write('building %s...'% key)
        build = buildObj[key]
        if rebuild and os.path.exists(os.path.join(encoder_binary_name, build.folder)):
            shutil.rmtree(os.path.join(encoder_binary_name, build.folder))
        if os.name == 'nt': time.sleep(1)
        if not os.path.exists(os.path.join(encoder_binary_name,build.folder)):
            os.mkdir(os.path.join(encoder_binary_name,build.folder))
        if not os.path.exists(os.path.join(encoder_binary_name, build.folder, 'default')):
            os.mkdir(os.path.join(encoder_binary_name, build.folder, 'default'))
        else:
            generator = None
        defaultco = []
        extra_libs = []
        for bitdepthfolder in build.opts.get('add-depths', []):
            if not os.path.exists(os.path.join(encoder_binary_name, build.folder, bitdepthfolder)):
                os.mkdir(os.path.join(encoder_binary_name, build.folder, bitdepthfolder))
            subco = []
            subco.append('-DENABLE_SHARED=OFF')
            subco.append('-DENABLE_CLI=OFF')
            subco.append('-DEXPORT_C_API=OFF')
            if '12bit' == bitdepthfolder:
                subco.append('-DHIGH_BIT_DEPTH=ON')
                subco.append('-DMAIN12=ON')
                defaultco.append('-DLINKED_12BIT=ON')
                extra_libs.append(lib_main12)
                build.cmakeoptions(subco, prof)
                build.cmake_build(key, subco, os.path.join(encoder_binary_name, build.folder, bitdepthfolder))
                shutil.copy(os.path.join(encoder_binary_name, build.folder, bitdepthfolder, build.target, static_lib),
                            os.path.join(encoder_binary_name, build.folder, 'default', lib_main12))
            elif '10bit' == bitdepthfolder:
                subco.append('-DHIGH_BIT_DEPTH=ON')
                defaultco.append('-DLINKED_10BIT=ON')
                extra_libs.append(lib_main10)
                build.cmakeoptions(subco, prof)
                build.cmake_build(key, subco, os.path.join(encoder_binary_name, build.folder, bitdepthfolder))
                shutil.copy(os.path.join(encoder_binary_name, build.folder, bitdepthfolder, build.target, static_lib),
                            os.path.join(encoder_binary_name, build.folder, 'default', lib_main10))
            else:
                defaultco.append('-DLINKED_8BIT=ON')
                extra_libs.append(lib_main)
                build.cmakeoptions(subco, prof)
                build.cmake_build(key, subco, os.path.join(encoder_binary_name, build.folder, bitdepthfolder))
                shutil.copy(os.path.join(encoder_binary_name, build.folder, bitdepthfolder, build.target, static_lib),
                            os.path.join(encoder_binary_name, build.folder, 'default', lib_main))
        if extra_libs:
            defaultco.append('-DEXTRA_LIB=' + ';'.join(extra_libs))
            if extra_link_flag: defaultco.append(extra_link_flag)
        build.cmakeoptions(defaultco, prof)
        build.cmake_build(key, defaultco, os.path.join(encoder_binary_name, build.folder, 'default'))
    if 'add-depths' in build.opts or not my_libpairs:
        return
    # output depth support: to bind libx265_main, main10, main12 for 8, 10, 12 bit encoders
    for tup in my_libpairs:
        if len(tup) != 3:
            print "`my_libpairs` variable format is wrong", my_libpairs
            return
        if tup[0] not in buildObj or tup[1] not in buildObj or tup[2] not in buildObj:
            # do not warn here, since the build list may be pruned
            return

        build1 = buildObj[tup[0]]
        build2 = buildObj[tup[1]]
        build3 = buildObj[tup[2]]
        if 'static' in build1.cmakeopts.split() or \
           'static' in build2.cmakeopts.split() or \
           'static' in build3.cmakeopts.split():
            print "%s or %s or %s not generating shared libs" % tup
            return

        b12  = (build1.dll).replace('libx265.', 'libx265_' + build2.profile + '.')
        b13  = (build1.dll).replace('libx265.', 'libx265_' + build3.profile + '.')
        b21  = (build2.dll).replace('libx265.', 'libx265_' + build1.profile + '.')
        b23  = (build2.dll).replace('libx265.', 'libx265_' + build3.profile + '.')
        b31  = (build3.dll).replace('libx265.', 'libx265_' + build1.profile + '.')
        b32  = (build3.dll).replace('libx265.', 'libx265_' + build2.profile + '.')
        try:
            if os.path.lexists(b12) and os.path.lexists(b13):
                os.unlink(b12)
                os.unlink(b13)
            if os.path.lexists(b21) and os.path.lexists(b23):
                os.unlink(b21)
                os.unlink(b23)
            if os.path.lexists(b31) and os.path.lexists(b32):
                os.unlink(b31)
                os.unlink(b32)
            if osname == 'Windows':
                shutil.copy(build1.dll, b21)
                shutil.copy(build1.dll, b31)
                shutil.copy(build2.dll, b12)
                shutil.copy(build2.dll, b32)
                shutil.copy(build3.dll, b13)
                shutil.copy(build3.dll, b23)
            else:
                os.symlink(os.path.abspath(build1.dll), b21)
                os.symlink(os.path.abspath(build1.dll), b31)
                os.symlink(os.path.abspath(build2.dll), b12)
                os.symlink(os.path.abspath(build2.dll), b32)
                os.symlink(os.path.abspath(build3.dll), b13)
                os.symlink(os.path.abspath(build3.dll), b23)
        except IOError:
            print("failed to setup library pair", tup)


def testharness():
    if not run_bench:
        return

    empty = True

    for key in buildObj:
        build = buildObj[key]
        bench = build.testbench

        if 'tests' not in build.cmakeopts.split():
            continue
        logger.settitle('testbench ' + key)
        logger.write('Running testbench for %s...'% key)

        if not os.path.isfile(bench):
            err = 'testbench <%s> not built' % bench
        else:
            origpath = os.environ['PATH']
            if 'PATH' in build.opts:
                os.environ['PATH'] += os.pathsep + build.opts['PATH']
            p = Popen([bench], stdout=PIPE, stderr=PIPE)
            err = async_poll_process(p, False)
            os.environ['PATH'] = origpath

        if err:
            prefix = '** testbench failure reported for %s::\n' % key
            _test.failuretype = 'testbench failure'
            table(_test.failuretype, empty, empty, logger.build.strip('\n'))
            logger.writeerr(prefix + err)


def encodeharness(key, tmpfolder, sequence, command, always, inextras):
    '''
    Perform a single test encode within a tempfolder
     * key      is the shortname for the build to use, ex: 'gcc'
     * tmpfolder is a temporary folder in which the test will run
     * sequence is the YUV or Y4M filename with no path
     * command is a string of params which influence outputs (hashed)
     * inextras is a list [] of params which do not influence outputs
    returns tuple of (logs, summary, error)
       logs    - stderr and stdout in paste-friendly format (encode log)
       summary - bitrate, psnr, ssim
       error   - full description of encoder warnings and errors
    '''
    global bitstream
    extras = inextras[:] # make copy so we can append locally
    seq_details         = []
    if sequence.lower().endswith('.yuv'):
        (width, height, fps, depth, csp) = parseYuvFilename(sequence)
        seq_details += ['--input-res=%sx%s' % (width, height),
                   '--fps=%s' % fps,
                   '--input-depth=%s' % depth,
                   '--input-csp=i%s' % csp]
    seqfullpath = os.path.join(my_sequences, sequence)
    build = buildObj[key]
    x265 = build.exe
    cmds = [x265]
    if '[' in command:
        command = wrapper.arrangecli(seqfullpath, command, always, extras, None, None)
        cmds.append(seqfullpath)
        cmds.extend(shlex.split(command))
        cmds.extend(seq_details)
    elif '(' in command:
        command1 = command.split('(')[0]
        command1 += command.split('(')[1].split(')')[0]
        cmds.extend([seqfullpath, bitstream])
        cmds.extend(shlex.split(command1))
        cmds.extend(extras)
        cmds.extend(seq_details)		
    elif '--command-file' in command:
        cmds.append(command)
    elif 'ffmpeg' in command:
        ffmpeg = 'ffmpeg'
        ffmpegfullpath = os.path.join(my_sequences, ffmpeg)
        command = wrapper.arrangecli(seqfullpath, command, always, extras, ffmpegfullpath, x265)
        cmds = []
        cmds.extend(command)
        cmds.extend(seq_details)
        cmds.extend([bitstream])
    else:
        cmds.extend([seqfullpath, '-o', bitstream])
        cmds.extend(shlex.split(command))
        cmds.extend(extras)
        cmds.extend(seq_details)
    if encoder_binary_name == 'x264':
        cmds.extend(['--dump-yuv', 'x264-output.yuv'])
    logs, errors, summary = '', '', ''
    if not os.path.isfile(x265):
        logger.write('x265 executable not found')
        errors = 'x265 <%s> cli not compiled\n\n' % x265
    elif not os.path.isfile(seqfullpath):
        logger.write('Sequence not found')
        errors = 'sequence <%s> not found\n\n' % seqfullpath
    else:
        def prefn():
            import resource # enable core dumps
            resource.setrlimit(resource.RLIMIT_CORE, (-1, -1))

        origpath = os.environ['PATH']
        if 'PATH' in build.opts:
            os.environ['PATH'] += os.pathsep + build.opts['PATH']
        if os.name == 'nt':
            p = Popen(cmds, cwd=tmpfolder, stdout=PIPE, stderr=PIPE, shell = 'TRUE')
        elif 'ffmpeg' in ''.join(command):
            cmds = ' '.join(cmds)
            p = Popen(cmds, cwd=tmpfolder, stdout=PIPE, stderr=PIPE, preexec_fn=prefn, shell = 'TRUE')
        else:
            p = Popen(cmds, cwd=tmpfolder, stdout=PIPE, stderr=PIPE, preexec_fn=prefn)
        stdout, stderr = p.communicate()
        os.environ['PATH'] = origpath

        # prune progress reports
        el = [l for l in stderr.splitlines(True) if not l.endswith('\r')]
        # prune debug and full level log messages
        el = [l for l in el if not l.startswith(('x265 [debug]:', 'x265 [full]:'))]
        logs = 'Full encoder logs without progress reports or debug/full logs:\n'
        logs += ''.join(el) + stdout

        summary, errors, encoder_error_var = parsex265(tmpfolder, stdout, stderr)
        if p.returncode == -11:
            errors += 'x265 encountered SIGSEGV\n\n'
        elif p.returncode == -6:
            errors += 'x265 encountered SIGABRT (usually check failure)\n\n'
        elif p.returncode == -4:
            errors += 'x265 encountered SIGILL (usually -ftrapv)\n\n'
        elif p.returncode == 1:
            errors += 'unable to parse command line (ret 1)\n\n'
        elif p.returncode == 2:
            errors += 'unable open encoder (ret 2)\n\n'
        elif p.returncode == 3:
            errors += 'unable open generate stream headers (ret 3)\n\n'
        elif p.returncode == 4:
            errors += 'encoder abort (ret 4)\n\n'
        elif p.returncode:
            errors += 'x265 return code %d\n\n' % p.returncode

        if p.returncode:
            errors += save_coredump(tmpfolder, x265)

    return (logs, summary, errors, encoder_error_var)


def parsex265(tmpfolder, stdout, stderr):
    '''parse warnings and errors from stderr, summary from stdout, and look
       for leak and check failure files in the temp folder'''
    encoder_error_var = True
    errors = ''
    check = os.path.join(tmpfolder, 'x265_check_failures.txt')
    if os.path.exists(check):
        errors += '** check failures reported:\n' + open(check, 'r').read()

    leaks = os.path.join(tmpfolder, 'x265_leaks.txt')
    if os.path.exists(leaks):
        contents = open(leaks, 'r').read()
        if contents and 'No memory leaks detected' not in contents:
            errors += '** leaks reported:\n' + contents + '\n'

    def scansummary(output):
        ssim, psnr, bitrate = 'N/A', 'N/A', 'N/A'
        for line in output.splitlines():
            if line.startswith('Cumulatively encoded '):
                words = line.split()
                if 'fps),' in words:
                    index = words.index('fps),')
                    bitrate = words[index + 1]
                if 'SSIM' in words:
                    ssim = words[-2]
                    if ssim.startswith('('): ssim = ssim[1:]
                if 'PSNR:' in words:
                    index = words.index('PSNR:')
                    psnr = words[index + 1]
                    if psnr.endswith(','): psnr = psnr[:-1]
                if bitrate:
                    return bitrate, ssim, psnr		
            elif line.startswith('encoded '):
                words = line.split()
                if 'fps),' in words:
                    index = words.index('fps),')
                    bitrate = words[index + 1]
                if 'SSIM' in words:
                    ssim = words[-2]
                    if ssim.startswith('('): ssim = ssim[1:]
                if 'PSNR:' in words:
                    index = words.index('PSNR:')
                    psnr = words[index + 1]
                    if psnr.endswith(','): psnr = psnr[:-1]
                if bitrate:
                    return bitrate, ssim, psnr
            else:
                continue			
        return None

    # parse summary from last line of stdout
    sum = scansummary(stdout)
    if sum is None:
        sum = scansummary(stderr)
    if sum:
        summary = 'bitrate: %s, SSIM: %s, PSNR: %s' % sum
    else:
        summary = 'bitrate: N/A, SSIM: N/A, PSNR: N/A'

    # check for warnings and errors in x265 logs, report together with most
    # recent progress report if there was any
    lastprog = None
    ls = len(os.linesep) # 2 on Windows, 1 on POSIX
    for line in stderr.splitlines(True):
        if line.endswith('\r'):
            lastprog = line
        elif line.startswith(('x265 [debug]:', 'x265 [full]:')):
            lastprog = line
        elif line.startswith('x265 [error]:') or \
             (line.startswith('x265 [warning]:') and \
              line[16:-ls] not in ignored_x265_warnings):		
            if lastprog:
                errors += lastprog.replace('\r', os.linesep)
                lastprog = None
            errors += line
            logger.write(line[:-1])						
	    if line.startswith('x265 [error]:'):
		    encoder_error_var = True
        elif (line.startswith('x265 [warning]:') and \
              line[16:-ls] not in ignored_x265_warnings):
            encoder_error_var = False
	
    return summary, errors, encoder_error_var


def checkoutputs(key, seq, command, sum, tmpdir, logs, testhash):
    global bitstream
    group = my_builds[key][1]
    # Analysis save/load comparison once encoder success.If encoder crash exist it will not compare the output files.
    cwd = os.getcwd()
    if os.path.isfile(os.path.join(tmpdir,bitstream)):
        if 'analysis-mode=save' in command:
            savesummary = sum
            open('savesummary.txt', 'w').write(savesummary)
            shutil.copy(os.path.join(tmpdir,bitstream), cwd)
        if 'analysis-mode=load' in command:
            loadsummary = sum
            savesummary = open('savesummary.txt','r').read()
            save = os.path.join(cwd,bitstream)
            load = os.path.join(tmpdir,bitstream)
            comparingoutput= filecmp.cmp(save,load)
            if comparingoutput == True:
                print 'no difference'
            else:
                logger.writeerr('Analysis save and load output are mismatched')
                res = 'SAVE: %s\n' % savesummary
                res += 'LOAD: %s\n\n' % loadsummary
                table('Outputchange between Analysis save and load', loadsummary, savesummary, logger.build.strip('\n'))
                logger.testfail('Outputchange between Analysis save and load', res, logs)

    opencommits = [] # changing commits without 'no-change' or testfolder
    # walk list of ancestor commits which changed outputs until we find the
    # most recent output bitstream we are expected to match
    for commit in changers:
        nc = 'no-change-%s-%s.txt' % (group, commit)
        nochange = os.path.join(my_goldens, testhash, nc)
        if os.path.exists(nochange):
            # this commit claims to match outputs of a previous commit
            commit = open(nochange, 'r').read()
            revdate = hgrevisiondate(commit)            
            lastfname = '%s-%s-%s' % (revdate, group, commit)
            logger.tableprevrevision = '%s' %commit
            testfolder = os.path.join(my_goldens, testhash, lastfname)
            break
        logger.tableprevrevision = '%s' %commit
        revdate = hgrevisiondate(commit)
        lastfname = '%s-%s-%s' % (revdate, group, commit)
        testfolder = os.path.join(my_goldens, testhash, lastfname)
        if os.path.isdir(testfolder):
            # this commit has known-good outputs
            break

        opencommits.append(commit)
    else:
        # no previously saved known good
        commit = changers[0]
        revdate = hgrevisiondate(commit)
        lastfname = '%s-%s-%s' % (revdate, group, commit)
        # caller will create a new testfolder with this name if the current
        # encode outputs pass validations
        print 'no golden outputs for this test case,',
        return lastfname, None
    golden = os.path.join(testfolder, bitstream)
    test = os.path.join(tmpdir, bitstream)
    if os.path.isfile(os.path.join(my_goldens, testhash, lastfname, 'summary.txt')):
        fname = os.path.join(my_goldens, testhash, lastfname, 'summary.txt')
        lastsum = open(fname, 'r').read()
    else:
        logger.summaryfile(commit)
        return lastfname, None

    if filecmp.cmp(golden, test):
        # outputs matched last-known good, record no-change status for all
        # output changing commits which were not previously accounted for
        for oc in opencommits:
            nc = 'no-change-%s-%s.txt' % (group, oc)
            nochange = os.path.join(my_goldens, testhash, nc)
            open(nochange, 'w').write(commit)
            print 'not changed by %s,' % oc,

        # if the test run which created the golden outputs used a --log-level=none
        # spot-check or something similar, the summary will have some unknowns
        # in it. Replace it with the current summary if it is complete

        if 'N/A' in lastsum and 'N/A' not in sum:
            print 'correcting golden output summary,',
            open(fname, 'w').write(sum)
            return lastfname, False
			
    if '--vbv-bufsize' in command or '--bitrate' in command or (fps_check_variable and (fps_check_variable in command)):
        # outputs did not match but this is a VBV test case.
        # bitrate difference > vbv tolerance will take credit for the change
        # or an open commmit with the 'vbv' keyword may take credit for the change

        if 'N/A' in lastsum and 'N/A' not in sum:
            logger.write('saving new outputs with valid summary:', sum)
            return lastfname, None

        def outputdiff():
            # golden outputs might have used --log-level=none, recover from this
            # VBV encodes are non-deterministic, check that golden output
            # bitrate is within tolerance% of new bitrate. Example summary:
            # 'bitrate: 121.95, SSIM: 20.747, PSNR: 53.359'
            diffmsg , diff_abr, diff_fps, diff_vbv = ' ', 0, 0, 0
            try:
                if '--vbv-bufsize' in command:
                    lastbitrate = float(lastsum.split(',')[0].split(' ')[1])
                    newbitrate = float(sum.split(',')[0].split(' ')[1])
                    diff_vbv = abs(lastbitrate - newbitrate) / lastbitrate
                    if diff_vbv > vbv_tolerance:
                        diffmsg += 'VBV OUTPUT CHANGED BY %.2f%%' % (diff_vbv * 100)
                if '--bitrate' in command:
                    lastbitrate = float(lastsum.split('bitrate: ')[1].split(',')[0])
                    newbitrate = float(sum.split(',')[0].split(' ')[1])
                    diff_abr = abs(lastbitrate - newbitrate) / lastbitrate
                    if diff_abr > abr_tolerance:
                        diffmsg += ' ABR OUTPUT CHANGED BY %.2f%%' % (diff_abr * 100)
                if (fps_check_variable and (fps_check_variable in command)):
                    targetfps_string = command.split(fps_check_variable)[1].split(' ')[0]
                    targetfps = float(targetfps_string)
                    for line in logs.splitlines():
                        if check_variable and line.startswith(check_variable):
                            frame_line = line
                            framelevelfps_string = frame_line.split('frames:')[1].split(' fps')[0]
                            framelevelfps = float(framelevelfps_string)
                            diff_fps = abs(targetfps - framelevelfps) / targetfps
                            frames_count_string = line.split(check_variable)[1].split(' frames:')[0]
                            frame_count = float(frames_count_string)
                            if frame_count > 100:
                                if diff_fps > fps_tolerance:
                                    diffmsg += ' \nFPS TARGET MISSED BY %.2f%% compared to target fps' % (diff_fps * 100)
                                    diffmsg+= ' for FRAME = %s' %frames_count_string
            except (IndexError, ValueError), e:
                diffmsg = 'Unable to parse bitrates for %s:\n<%s>\n<%s>' % \
                           (testhash, lastsum, sum)
                diff_vbv = vbv_tolerance + 1
                diff_abr = abr_tolerance + 1
                diff_fps = fps_tolerance + 1
            return diff_vbv, diff_abr, diff_fps, diffmsg
        for oc in opencommits:
            lastfname = '%s-%s-%s' % (hgrevisiondate(oc), group, oc)
            if 'vbv' in changefilter.get(oc, '') or   'bitrate' in changefilter.get(oc, '') or 'fps' in changefilter.get(oc, ''):
                return lastfname, None
            else:
                diff_vbv, diff_abr, diff_fps, diffmsg = outputdiff()
                if diff_vbv > vbv_tolerance or diff_abr > abr_tolerance or diff_fps > fps_tolerance:
                    logger.logfp.write('\n%s\n' % diffmsg)
                    logger.write(diffmsg)
                    return lastfname, None
        else:
            diff_vbv, diff_abr, diff_fps, diffmsg = outputdiff()
            if diff_vbv > vbv_tolerance or diff_abr > abr_tolerance or diff_fps > fps_tolerance:
                return lastfname, diffmsg
            elif diff_vbv < vbv_tolerance:
                return lastfname, False
    
    if filecmp.cmp(golden, test):
        return lastfname, False
		
    # outputs do not match last good, check for a changing commit that might
    # take credit for this test case being changed
    unfiltered = None
    for oc in opencommits:
        if oc in changefilter:
            if [True for m in changefilter[oc] if m in command]:
                print 'commit %s takes credit for this change' % oc
                revdate = hgrevisiondate(oc)
                lastfname = '%s-%s-%s' % (revdate, group, oc)
                return lastfname, None
        elif not unfiltered:
            unfiltered = oc
    if unfiltered:
        print 'unfiltered commit %s takes credit for this change' % unfiltered
        revdate = hgrevisiondate(unfiltered)
        lastfname = '%s-%s-%s' % (revdate, group, unfiltered)
        return lastfname, None

    # outputs did not match, and were expected to match, considered an error
    if os.path.isfile(os.path.join(testfolder, 'summary.txt')):
        oldsum = open(os.path.join(testfolder, 'summary.txt'), 'r').read()
        res = '%s output does not match last good for group %s\n\n' % (key, group)
        res += 'Previous last known good revision\n'
        res += hgrevisioninfo(commit).replace(os.linesep, '\n') + '\n'
        res += 'PREV: %s\n' % oldsum
        res += ' NEW: %s\n\n' % sum
        return lastfname, res
    else:
        print 'summary.txt file does not exist'
        return lastfname, None
def newgoldenoutputs(seq, command, lastfname, sum, logs, tmpdir, testhash):
    '''
    A test was run and the outputs are good (match the last known good or if
    no last known good is available, these new results are taken
    '''
    global bitstream
    commit = lastfname.split('-')[-1]
    if not save_results:
        # only save results if the testrev is a keyword change commit
        strings = changefilter.get(commit)
        if commit != testrev:
            return
        elif strings and [True for s in strings if s in command]:
            print 'allowing new golden outputs because of change keyword filter'
        else:
            return
    # create golden folder if necessary
    if not os.path.isdir(my_goldens):
        os.mkdir(my_goldens)

    # create a new test folder if necessary
    testfolder = os.path.join(my_goldens, testhash)
    if not os.path.isdir(testfolder):
        os.mkdir(testfolder)
        fp = open(os.path.join(testfolder, 'hashed-command-line.txt'), 'w')
        fp.write('%s %s\n' % (seq, command))
        fp.close()

    # create a new golden output folder if necessary
    lastgoodfolder = os.path.join(testfolder, lastfname)
    if not os.path.isdir(lastgoodfolder):
        os.mkdir(lastgoodfolder)
    shutil.copy(os.path.join(tmpdir, bitstream), lastgoodfolder)
    open(os.path.join(lastgoodfolder, 'summary.txt'), 'w').write(sum)
    addpass(testhash, lastfname, logs)
    logger.newgolden(commit)


def addpass(testhash, lastfname, logs):
    if not save_results:
        return

    folder = os.path.join(my_goldens, testhash, lastfname)
    if not os.path.isdir(folder):
        os.mkdir(folder)
    folder = os.path.join(my_goldens, testhash, lastfname, 'passed')
    if not os.path.isdir(folder):
        os.mkdir(folder)
    nowdate = str(datetime.date.fromtimestamp(time.time()))[2:]
    fname = '%s-%s-%s.txt' % (nowdate, testrev, my_machine_name)
    message = logger.header + logger.build + logger.test + logs
    if os.linesep == '\r\n':
        message = message.replace(os.linesep, '\n')
    open(os.path.join(folder, fname), 'wb').write(message)


def addfail(testhash, lastfname, logs, errors):
    if not save_results:
        return

    folder = os.path.join(my_goldens, testhash, lastfname)
    if not os.path.isdir(folder):
        os.mkdir(folder)
    folder = os.path.join(my_goldens, testhash, lastfname, 'failed')
    if not os.path.isdir(folder):
        os.mkdir(folder)
    nowdate = str(datetime.date.fromtimestamp(time.time()))[2:]
    fname = '%s-%s-%s.txt' % (nowdate, testrev, my_machine_name)
    message = logger.header + logger.build + logger.test + errors + logs
    if os.linesep == '\r\n':
        message = message.replace(os.linesep, '\n')
    open(os.path.join(folder, fname), 'wb').write(message)


def hashbitstream(badfn):
    m = md5.new()
    m.update(open(badfn, 'rb').read())
    return m.hexdigest()

def savebadstream(tmpdir):
    global bitstream
    badbitstreamfolder = os.path.join(my_goldens, 'bad-streams')
    if not os.path.exists(badbitstreamfolder):
        os.mkdir(badbitstreamfolder)
    badfn = os.path.join(tmpdir, bitstream)
    hashname = hashbitstream(badfn)
    hashfname = os.path.join(badbitstreamfolder, hashname + '.hevc')
    shutil.copy(badfn, hashfname)
    return hashfname

def checkdecoder(tmpdir):
    global bitstream
    if encoder_binary_name == 'x264':
        cmds = [my_hm_decoder, '-i', bitstream, '-o', 'jm-output.yuv']
    else:
        cmds = [my_hm_decoder, '-b', bitstream]
    proc = Popen(cmds, stdout=PIPE, stderr=PIPE, cwd=tmpdir)
    stdout, errors = async_poll_process(proc, True)
    hashErrors = [l for l in stdout.splitlines() if '***ERROR***' in l]

    if os.path.exists(os.path.join(tmpdir, 'jm-output.yuv')) and os.path.exists(os.path.join(tmpdir, 'x264-output.yuv')):
        if not filecmp.cmp(os.path.join(tmpdir, 'jm-output.yuv'), os.path.join(tmpdir, 'x264-output.yuv')):
            logger.testfail('yuv mismatch', 'x264 yuv is mismatched with jm yuv', '')
            table('yuv mismatch', True , True, logger.build.strip('\n'))

    if hashErrors or errors:
        return 'Validation failed with %s\n\n' % my_hm_decoder + \
               '\n'.join(hashErrors[:2] + ['', errors])
    else:
        return ''


def table(failuretype, sum , lastsum, build_info):
    var_empty = '-'
    if (sum == True):
        logger.table.append(r'<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td><td>{4}</td><td>{5}</td><td>{6}</td><td>{7}</td><td>{8}</td><td>{9}</td><td>{10}</td></tr>'\
                                .format(failuretype, var_empty, build_info, var_empty, var_empty, var_empty, var_empty, var_empty, var_empty, var_empty, var_empty))

    elif (sum == "encodererror"):
        logger.tableprevvalue = lastsum 
        prevValue = logger.tableprevvalue
        logger.table.append(r'<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td><td>{4}</td><td>{5}</td><td>{6}</td><td>{7}</td><td>{8}</td><td>{9}</td><td>{10}</td></tr>'\
                                .format(failuretype,
                                        logger.tablecommand,
                                        build_info,
                                        logger.tableprevrevision,
                                        prevValue.split(",")[0].split(":")[1],
                                        prevValue.split(",")[1].split(":")[1],
                                        prevValue.split(",")[2].split(":")[1],
                                        var_empty,
                                        var_empty,
                                        var_empty,
                                        var_empty))
        
    else:
        logger.tableprevvalue = lastsum            
        logger.tablecurrentrevision = testrev
        logger.tablecurrentvalue = sum
        prevValue = logger.tableprevvalue
        currValue = logger.tablecurrentvalue            
        logger.table.append(r'<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td><td>{4}</td><td>{5}</td><td>{6}</td><td>{7}</td><td>{8}</td><td>{9}</td><td>{10}</td></tr>'\
                                .format(failuretype,
                                        logger.tablecommand,
                                        build_info,
                                        logger.tableprevrevision,
                                        prevValue.split(",")[0].split(":")[1],
                                        prevValue.split(",")[1].split(":")[1],
                                        prevValue.split(",")[2].split(":")[1],
                                        logger.tablecurrentrevision,
                                        currValue.split(",")[0].split(":")[1],
                                        currValue.split(",")[1].split(":")[1],
                                        currValue.split(",")[2].split(":")[1]))
            

def _test(build, tmpfolder, seq, command,  always, extras):
    '''
    Run a test encode within the specified temp folder
    Check to see if golden outputs exist:
        If they exist, verify bit-exactness or report divergence
        If not, validate new bitstream with decoder then save
    '''
    global bitstream, testhashlist
    empty = True
    testhash = testcasehash(seq, command)
    bitstream = 'bitstream.hevc' if hg else 'bitstream.h264'
    testhashlist = []
    # run the encoder, abort early if any errors encountered
    logs, sum, encoder_errors, encoder_error_var = encodeharness(build, tmpfolder, seq, command,  always, extras)
    if not testhashlist:
        testhashlist.append(testhash)

    for hash in testhashlist:
        if '[' in command:
            bitstream = hash + '.hevc'
      
        if encoder_errors:
            if (encoder_error_var):
                logger.testfail('encoder error reported', encoder_errors, logs)
                table('encoder error', empty , empty, logger.build.strip('\n'))
            else:
                logger.testfail('encoder warning reported', encoder_errors, logs)
                table('encoder warning', empty , empty, logger.build.strip('\n'))
            return

        lastfname, errors = checkoutputs(build, seq, command, sum, tmpfolder, logs, hash)
        fname = os.path.join(my_goldens, hash, lastfname, 'summary.txt')

        # check against last known good outputs - lastfname is the folder
        # containing the last known good outputs (or for the new ones to be
        # created)

        if errors is None or errors is False:
            # no golden outputs for this test yet
            logger.write('validating with decoder')
            decodeerr = checkdecoder(tmpfolder)
            if decodeerr:
                hashfname = savebadstream(tmpfolder)
                decodeerr += '\nThis bitstream was saved to %s' % hashfname
                logger.testfail('Decoder validation failed', decodeerr, logs)
                if os.path.exists(fname):
                    lastsum = open(fname, 'r').read()
                    table('Decoder validation failed', sum , lastsum, logger.build.strip('\n'))
                else:
                    table('Decoder validation failed', empty , empty, logger.build.strip('\n'))
            else:
                logger.write('Decoder validation ok:', sum)
                if errors is False:
                    # outputs matched golden outputs
                    addpass(hash, lastfname, logs)
                    logger.write('PASS')
                else:
                    newgoldenoutputs(seq, command, lastfname, sum, logs, tmpfolder, hash)
        elif errors:
            typeoferror = 'VBV' if '--vbv-bufsize' in command else ('ABR' if '--bitrate' in command else '')
            # outputs did not match golden outputs
            decodeerr = checkdecoder(tmpfolder)
            if decodeerr:
                prefix = '%s OUTPUT CHANGE WITH DECODE ERRORS' % typeoferror
                hashfname = savebadstream(tmpfolder)
                prefix += '\nThis bitstream was saved to %s' % hashfname
                logger.testfail(prefix, errors + decodeerr, logs)
                failuretype = '%s output change with decode errors ' % typeoferror
                if os.path.exists(fname):
                    lastsum = open(fname, 'r').read()
                    table(failuretype, sum , lastsum, logger.build.strip('\n'))
                else:
                    table(failuretype, empty , empty, logger.build.strip('\n'))
            else:
                logger.write('FAIL')
                if 'FPS TARGET MISSED' in errors:
                    if os.path.exists(fname):
                        lastsum = open(fname, 'r').read()
                        prefix = '%s FPS TARGET MISSED: <%s> to <%s>' % (typeoferror, lastsum, sum)
                    else:
                        prefix = '%s FPS TARGET MISSED:' % (typeoferror)
                    failuretype = '%s fps target missed' % typeoferror
                else:
                    if os.path.exists(fname):
                        lastsum = open(fname, 'r').read()
                        prefix = '%s OUTPUT CHANGE: <%s> to <%s>' % (typeoferror, lastsum, sum)
                    else:
                        prefix = '%s OUTPUT CHANGE:' % (typeoferror)
                    failuretype = '%s output change' % typeoferror
                if os.path.exists(fname):
                    lastsum = open(fname, 'r').read()
                    table(failuretype, sum , lastsum, logger.build.strip('\n'))
                else:
                    table(failuretype, empty , empty, logger.build.strip('\n'))
                if save_changed:
                    hashfname = savebadstream(tmpfolder)
                    prefix += '\nThis bitstream was saved to %s' % hashfname
                else:
                    badfn = os.path.join(tmpfolder, bitstream)
                    prefix += '\nbitstream hash was %s' % hashbitstream(badfn)
                addfail(hash, lastfname, logs, errors)
                logger.testfail(prefix, errors, logs)

def runtest(key, seq, commands, always, extras):
    '''
    Execute one complete test case (one line in a testcase file):
       key      - build keyname
       seq      - sequence basename
       commands - comma seperated list of command lines (multipass)
       always   - output-changing arguments which must always be present (hashed)
       extras   - non-output changing arguments

    Creates a temp-folder, runs the test(s), verifies, then removes the temp-
    folder.
    '''

    def skip(*matchers):
        if skip_string:
            if [True for f in matchers if skip_string in f]:
                logger.write('Skipping test', f)
                return True
        if only_string:
            if not [True for f in matchers if only_string in f]:
                return True
        return False
    logger.testcount += 1
    cmds = []
    if ('(' in commands or '[' in commands):
        testhash = testcasehash(seq, commands)
        cmds.append((commands, testhash))	
    else:       	
        for command in commands.split(','):
            command = command.strip()
            if always:
                command = command + ' ' + always
            testhash = testcasehash(seq, command)
            if skip(seq, command, testhash):
                return
            cmds.append((command, testhash))			
    tmpfolder = tempfile.mkdtemp(prefix='x265-temp')
    try:

        for command, testhash in cmds:
            logger.settest(seq, command, extras, testhash)
            logger.write('testing x265-%s %s %s' % (key, seq, command))
            print 'extras: %s ...' % ' '.join(extras),
            sys.stdout.flush()

            build = buildObj[key]
            if '--output-depth' in command and ('add-depths' in build.opts or not my_libpairs):
                continue				
            _test(key, tmpfolder, seq, command, always, extras)
        logger.write('')
    finally:
        shutil.rmtree(tmpfolder)
