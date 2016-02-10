# Copyright (C) 2015 Mahesh Pittala <mahesh@multicorewareinc.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version. See COPYING

import os
import datetime
import sys
import time
import glob
import subprocess as sub
from subprocess import Popen, PIPE

requestid = ''
instanceid = ''
goldentip = ''
iter = ''
mailid = ''
patches = []
buildObj = {}
binary = ''
orig_repo = 'x265repo'
patches_repo = 'x265patches'
log = open('log.txt', 'wb')


try:
    from paths_cfg import my_builds, my_make_flags, option_strings, my_patchtest, my_tag

except ImportError, e:
    print 'Copy paths_cfg.py.example to paths_cfg.py and edit the file as necessary'
    sys.exit(1)

try:
    from paths_cfg import my_AWS_ACCESS_KEY_ID, my_AWS_SECRET_ACCESS_KEY

except ImportError, e:
    print 'please set AWS credentails and dont make it as public', e
    sys.exit(1)


try:
    from paths_cfg import my_email_from, my_smtp_pwd, my_smtp_host, my_smtp_port, my_email_to
except ImportError, e:
    print '** `my_email_*` not defined, defaulting to None'
    my_email_from, my_email_to, my_smtp_pwd = None, None, None

try:
    from paths_cfg import my_ftp_url, my_ftp_user, my_ftp_pass, my_ftp_path_stable, my_ftp_path_default, my_ftp_path_stableold, my_ftp_path_defaultold, my_ftp_branches, my_ftp_prevbranch, my_ftp_requestid, my_ftp_instanceid
except ImportError, e:
    print '** `my_email_*` not defined, defaulting to None'
    my_ftp_url, my_ftp_user, my_ftp_pass, my_ftp_path_stable, my_ftp_path_default, my_ftp_path_stableold, my_ftp_path_defaultold, my_ftp_branches, my_ftp_prevbranch, my_ftp_requestid, my_ftp_instanceid = None, None, None, None, None, None, None, None, None, None, None




def hgbranches(x265repopath):
    out, err = Popen(['hg', 'branches'], stdout=PIPE, stderr=PIPE, cwd=x265repopath).communicate()
    if err:
        raise Exception('Unable to determine tags: ' + err)
    return out

def hgbranch(x265repopath):
    print('hg')
    out, err = Popen(['hg', 'branch'], stdout=PIPE, stderr=PIPE, cwd=x265repopath).communicate()
    if err:
        raise Exception('Unable to determine tags: ' + err)
    return out

def build(repo):

    global buildfolder, buildobj, rebuild, binary, log
    for key in my_builds:
        buildobj = my_builds[key]

    buildfolder,buildgroup,generator,cmakeopts,opts = buildobj
    buildfolder = os.path.join(os.getcwd(), repo, buildfolder)
    co = cmakeopts.split()
    option = []
    for o in co:
        if o in option_strings:
            option.append(option_strings[o])
        else:
            log.write('\nERROR: unknown cmake option %s' %o)
            cleanup()

    if not os.path.exists(buildfolder):
        os.mkdir(buildfolder)
    if 'Visual Studio' in generator:
        if 'debug' in co:
            target = 'Debug'
        elif 'reldeb' in co:
            target = 'RelWithDebInfo'
        else:
            target = 'Release'
        binary = os.path.abspath(os.path.join(buildfolder, target, 'x265.exe'))
    else:
        binary = os.path.abspath(os.path.join(buildfolder, 'x265'))

    cmakecmd = ['cmake', '-Wno-dev', os.path.abspath(os.path.join(os.getcwd(), repo, 'source'))]
    if generator:
        cmakecmd.append('-G')
        cmakecmd.append(generator)
    cmakecmd.extend(option)

    ret = sub.Popen(cmakecmd, cwd=buildfolder, stdout=log, stderr=log)
    if ret.wait() == 1:
        log.write('\nERROR: cmake command failed to run %s' %cmakecmd)
        cleanup()
    else:
        if os.name == 'nt':
            if os.path.isfile(os.path.join(buildfolder,'x265.sln')):
                cmd = 'MSBuild.exe /clp:disableconsolecolor /p:VisualStudioVersion=12.0 /property:Configuration="Release" x265.sln'
                proc = sub.Popen(cmd, cwd=buildfolder, stdout=log, stderr=log)
                if proc.wait() == 0:
                    if not os.path.isfile(os.path.join(buildfolder, target, 'x265.exe')):
                        print('binary doesnt exist')
                        return 1
                else:
                    print('command failed to run %s %s' %(cmd,buildfolder))
                    return 1
                    
            else:
                print 'x265 solution is not exit'
        else:
            if 'MinGW' in generator:
                cmds = ['mingw32-make']
            else:
                cmds = ['make']
            if my_make_flags:
                cmds.extend(my_make_flags)

            origpath = os.environ['PATH']
            if 'PATH' in opts:
                os.environ['PATH'] += os.pathsep + opts['PATH']
            proc = sub.Popen(cmds,cwd=buildfolder, stdout=log, stderr=log)
            os.environ['PATH'] = origpath
            if proc.wait() == 0:
                if not os.path.isfile(os.path.join(buildfolder, 'x265')):
                    log.write('\nERROR: binary doesnt created - %s' %buildfolder)
                    cleanup()
            else:
                log.write('\nERROR: build failed %s' %cmds)
                cleanup()

def email_results():
    global my_email_to
    if not (my_email_from and my_email_to and my_smtp_pwd):
        return

    import smtplib, platform
    from email.mime.text import MIMEText

    l = open('log.txt', 'rb')
    msg = MIMEText(''.join(l.read()))
    if type(my_email_to) is str:
        msg['To'] = my_email_to
    else:
        msg['To'] = ", ".join(my_email_to)

    msg['From'] = my_email_from
    sub = [platform.system(), ' -', ' Performance Regression Failed']
    msg['Subject'] = ' '.join(sub)

    session = smtplib.SMTP(my_smtp_host, my_smtp_port)
    try:
        session.ehlo()
        session.starttls()
        session.ehlo()
        session.login(my_email_from, my_smtp_pwd.decode('base64'))
        print('log in sussful.....%s' %my_email_to)
        session.sendmail(my_email_from, my_email_to, msg.as_string())
    except smtplib.SMTPException, e:
        print 'Unable to send email', e
    finally:
        session.quit()

def terminate_instance():
    global requestid, instanceid, log
    #get security credentials
    accesskey = my_AWS_ACCESS_KEY_ID
    secretkey = my_AWS_SECRET_ACCESS_KEY
    cmd = "ec2-cancel-spot-instance-requests %s --aws-access-key=%s --aws-secret-key=%s --region us-west-2" %(requestid, accesskey, secretkey)
    ret = sub.Popen(cmd, shell=True, stdout=log, stderr=log)
    if ret.wait() != 0:
        print('failed to cancel spot request')
    cmd = "ec2-terminate-instances %s --aws-access-key=%s --aws-secret-key=%s --region us-west-2" %(instanceid, accesskey, secretkey)
    ret = sub.Popen(cmd, shell=True, stdout=log, stderr=log)
    if ret.wait() != 0:
        print('failed to terminate instance')

def cleanup():
    global log
    log.write('\n..........INSTANCE WILL TERMINATING IN 5 MINUTS..........\n')

    time.sleep(300) # hold 5 minuts before terminating instance
    # clean up spot request and terminate the instance
    print('terminating instance....')
    terminate_instance()

    log.close()
    # email failures to user through email to debug the issues
    email_results()

    time.sleep(30)
    sys.exit(0)


def upload_files():
    global log, cwd

    import ftplib
    try:
        ftp = ftplib.FTP(my_ftp_url)
        ftp.login(my_ftp_user, my_ftp_pass.decode('base64'))

        ftp.cwd(my_ftp_branches)
        fp = open(os.path.join(cwd, 'branches', 'branches.txt'),'rb')
        ftp.storbinary('STOR ' +'branches.txt',fp)

        ftp.cwd(my_ftp_prevbranch)
        fp = open(os.path.join(cwd, 'prevbranch', 'prevbranch.txt'),'rb')
        ftp.storbinary('STOR ' +'prevbranch.txt',fp)

    except ftplib.all_errors, e:
        print "ftp failed", e
        log.write('\nERROR: ftp failed to upload tested branch related information on egnyte\n %s \n' %e)
        cleanup()


def download_patches():
    global log

    if not (my_ftp_url and my_ftp_user and my_ftp_pass and my_ftp_path):
        log.write('\nERROR: ftp failed, please check these variables %s %s %s %s\n' %(my_ftp_url, my_ftp_user, my_ftp_pass, my_ftp_path))
        cleanup()

    import ftplib
    try:
        ftp = ftplib.FTP(my_ftp_url)
        ftp.login(my_ftp_user, my_ftp_pass.decode('base64'))
        ftp.cwd(my_ftp_path)

        dates = []
        list_allfiles = ftp.nlst()
        for file in list_allfiles:
            date = file.split('_')[0]
            dates.append(date)

        ret = sorted(dates, key=lambda x: datetime.datetime.strptime(x, '%Y-%m-%d-%H-%M-%S'), reverse=True)
        for f in list_allfiles:
            if ret[0] in f:
                print 'Downloading ' + f
                file = open(f, 'wb')
                ftp.retrbinary('RETR %s' % f, file.write)
                ftp.delete(f)

    except ftplib.all_errors, e:
        log.write('\nERROR: ftp failed to download patches from egnyte\n %s \n' %e)
        cleanup()

def download_requiredfiles():
    global log, cwd
    if not (my_ftp_url and my_ftp_user and my_ftp_pass and my_ftp_path_stable and my_ftp_path_stableold and my_ftp_path_default and my_ftp_path_defaultold and my_ftp_branches and my_ftp_prevbranch and my_ftp_requestid and my_ftp_instanceid):
        log.write('\nERROR: please check ftp variables\n %s \n' %e)
        cleanup()
        return

    localfolders = [os.path.join(cwd, '..//x265Batch', 'goldencsvstable'), os.path.join(cwd, '..//x265Batch', 'goldencsvdefault'), 'branches', 'prevbranch', 'requestid', 'instanceid']
    ftppath      = [my_ftp_path_stable, my_ftp_path_default, my_ftp_branches, my_ftp_prevbranch, my_ftp_requestid, my_ftp_instanceid]

    import ftplib
    try:
        ftp = ftplib.FTP(my_ftp_url)
        ftp.login(my_ftp_user, my_ftp_pass.decode('base64'))
    except ftplib.all_errors, e:
        print "ftp log in failed", e
        log.write('\nERROR: ftp failed to log in\n %s \n' %e)
        cleanup()

    for i in range(len(localfolders)):
        if not os.path.exists(localfolders[i]):
            print(localfolders[i])
            os.mkdir(localfolders[i])
        try:
            ftp.cwd(ftppath[i])
            files = ftp.dir()
            listing = []
            ftp.retrlines("LIST", listing.append)
            words = listing[0].split(None, 8)
            filename = words[-1].lstrip()
            local_filename = os.path.join(cwd, localfolders[i], filename)
            lf = open(local_filename, "wb")
            ftp.retrbinary("RETR " + filename, lf.write, 8*1024)
            lf.close()
            ftp.cwd('./')
        except ftplib.all_errors, e:
            print "ftp failed", e
            log.write('\nERROR: ftp failed to download patches from egnyte\n %s \n' %e)
            cleanup()

def parse_patch():
    global patches, goldentip, iter, requestid, instanceid, log
    try:
        for file in glob.glob("*.patch"):
            f = file.split('_')
            requestid = f[1]
            instanceid = f[2]
            goldentip = f[3]
            iter =  f[4]
            my_email_to =  f[5].split('.patch')[0]
            patches.append(int(f[6].split('.')[0]))
    except Exception as e:
        log.write('\nERROR: please check the uploaded file name format on egnyte, must be like: date_requestid_instanecid_goldentip_iteration_mailid_patchnumber\n %s \n' %e)
        cleanup()
    patches = sorted(patches)

def parse():
    global requestid, instanceid, cwd
    try:
        f = open(os.path.join(cwd, 'requestid', 'requestid.txt'), 'r')
        requestid = f.read()
        f = open(os.path.join(cwd, 'instanceid', 'instanceid.txt'), 'r')
        instanceid = f.read()
    except Exception as e:
        log.write('\nERROR: failed to get requestid and instanceid to terminate the instance \n %s \n' %e)
        cleanup()

def setup_x265repo_patch():
    global orig_repo, patches_repo, patches, log
    if not os.path.exists(orig_repo):
        os.mkdir(orig_repo)
    sub.Popen('hg init', cwd = orig_repo, shell = True)
    for i in range(10):
        ret=sub.Popen("hg pull https://bitbucket.org/multicoreware/x265", cwd=orig_repo, shell=True)
        if ret.wait()!=0:
            print("pull failed x265 repo")
        else:
            ret=sub.Popen('hg update -r' + goldentip, cwd=orig_repo, stdout=log, stderr=log, shell=True)
            if ret.wait()!=0:
                log.write('\nERROR: update failed at goldentip: %s' %goldentip)
                cleanup()
            else:
                break

    build(orig_repo)

    if not os.path.exists(patches_repo):
        os.mkdir(patches_repo)
    sub.Popen('hg init', cwd = patches_repo, shell = True)
    for i in range(10):
        ret=sub.Popen("hg pull https://bitbucket.org/multicoreware/x265", cwd=patches_repo, shell=True)
        if ret.wait()!=0:
            print("pull failed x265 repo")
        else:
            ret=sub.Popen('hg update tip', cwd=patches_repo, shell=True)
            if ret.wait()!=0:
                print("update failed")
            else:
                break
    for p in patches:
        for file in glob.glob("*.patch"):
            f = file.split('_')
            if int(f[6].split('.')[0]) == int(p):
                print('importing %s' %file)
                ret=sub.Popen("hg import "+ os.path.join(os.getcwd(), file) , cwd=patches_repo, stdout=log, stderr=log, shell=True)
                if ret.wait()!=0:
                    log.write('\nERROR: failed to apply patch: %s' %file)
                    cleanup()
    build(patches_repo)

def setup_regularx265repo():
    global orig_repo, cwd
    if not os.path.exists(orig_repo):
        os.mkdir(orig_repo)

    try:
        f = open(os.path.join(cwd, 'branches', 'branches.txt'),'r')
        f = f.read()
        branches = f.split('\n')
        last_default = branches[0].split(':')[1]
        last_stable = branches[1].split(':')[1].split(' ')[0]
        f = open(os.path.join(cwd, 'prevbranch', 'prevbranch.txt'),'r')
        f = f.read()
        prev_branch = f.strip('\r\n')

        sub.Popen('hg init', cwd = orig_repo, shell = True)
        for i in range(10):
            ret=sub.Popen("hg pull https://bitbucket.org/multicoreware/x265", cwd=orig_repo, shell=True)
            if ret.wait()!=0:
                print("pull failed x265 repo")
            else:
                ret=sub.Popen('hg update tip', cwd=orig_repo, shell=True)
                if ret.wait()!=0:
                    print("update  failed")
    
        out = hgbranches(os.path.join(os.getcwd(), orig_repo))
        branches = out.split('\n')
        present_default = branches[0].split(':')[1]
        present_stable = branches[1].split(':')[1].split(' ')[0]

        if last_stable == present_stable:
            ret=sub.Popen('hg update tip', cwd=orig_repo, shell=True)
            if ret.wait()!=0:
                print("failed to update x265repo at latest tip")

            cur_branch = hgbranch(os.path.join(os.getcwd(), orig_repo))
            if not prev_branch == cur_branch:
                print('testing %s' %cur_branch)
            elif recent_default == latest_default:
                print("This tip %s already tested" %latest_default)
                sys.exit(0)
        else:
            ret=sub.Popen('hg update -r '+ present_stable, cwd=orig_repo, shell=True)
            if ret.wait()!=0:
                print(" failed to updated at present_stable", present_stable)
                sys.exit(0)
            else:
                print("updated  at present_stable tip")

        fp = open(os.path.join(cwd, 'branches', 'branches.txt'),'w')
        out = hgbranches(orig_repo)
        fp.write(out)
        fp.close()

        fp = open(os.path.join(cwd, 'prevbranch', 'prevbranch.txt'),'w')
        out = hgbranch(orig_repo)
        fp.write(out)
        fp.close()

    except Exception as e:
        log.write('\nERROR: failed to setup x265 repo\n %s \n' %e)
    build(orig_repo)

def launch_tests_patch():
    global orig_repo, patches_repo, log
    binary_path = binary.replace('x265patches', 'x265repo')
    os.chdir("..//x265Batch")
    cmd = 'python x265Batch.py --cfg commands.conf.txt --mailid %s --iter %s -- %s --psnr --ssim' %(my_email_to, iter, binary_path)
    ret = sub.Popen(cmd, shell=True, stdout=log, stderr=log)
    if ret.wait() == 0:
        binary_path = binary.replace('x265repox265patches', 'x265patches') 
        cmd = 'python x265Batch.py --cfg commands.conf.txt --mailid %s  --iter %s -- %s --psnr --ssim' %(my_email_to, iter, binary_path)
        ret = sub.Popen(cmd, shell=True, stdout=log, stderr=log)
        if ret.wait() == 0:
            print('tests are successful')
            terminate_instance()

def launch_tests():
    global buildfolder

    branch = hgbranch(os.path.join(os.getcwd(), 'x265repo'))
    binary = os.path.join(buildfolder, 'x265')
    os.chdir("..//x265Batch")
    cmd = 'python x265Batch.py --branch %s --tag %s --cfg commands.conf.txt --iter 3 -- %s --psnr --ssim' % (branch.strip('\r\n'), my_tag, binary)
    ret = sub.Popen(cmd, shell=True, stdout=log, stderr=log)
    if ret.wait() != 0:
        print("\n x265Batch run failed: %s \n" %cmd)
        os.chdir("..//AWSsetup")
        cleanup()
    else:
        print("\n x265Batch run success: %s \n" %cmd)
        upload_files()
        terminate_instance()


def main():
    global log, cwd
    
    cwd = os.getcwd()

    if my_patchtest == True:
        # if part is to run performance regression test on developer patches
        time.sleep(600) # wait until patches uploaded to egnyte from Developer

        # download developer patches from egnyte
        download_patches()

        # parse file names to get request id, instance id, receiver mailid etc...
        parse_patch()

        # create two seperate repos and apply patches on one repo
        setup_x265repo_patch()

        launch_tests_patch()
    else:
        # else part is for running nightly\weekly performance regression tests
        download_requiredfiles()
        parse()
        setup_regularx265repo()
        launch_tests()

if __name__ == "__main__":
    main()
