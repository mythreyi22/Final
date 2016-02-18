purpose
-------
The primary purpose of this test is to run a batch of x265 jobs on series of patches in AWS c4.8xlarge Haswell supported instance


Instructions
------------
-> clone test-harness repo
-> goto submitpatch folder and rename 'paths_cfg.example.py' to 'paths_cfg.py'
-> Invoke the script
-> once instance created successfully, it runs tests and will email the results to 'mailid'
-> in case if it fails, you will get the email with failures log


Invoking
--------
The command line arguments for execution of script.

Run ./submit.py --help for a list of options

    ./submit.py [OPTIONS]
        --goldentip <string>  goldentip to compare the results against
        --commands  <string>  locate the file which is having additional commandlines (optional)
        --instance  <string>  create\terminate the instance, only 'create' supports now
        --mailid    <string>  receiver mail id to get results
        --iter      <N>       N times to run the command line, default 1 (optional)
        -- <string>           locate the patches with space
 
Examples:
* Submit.py --goldentip 425b583f25db --instance create --mailid mahesh@multicorewareinc.com -- patch1.patch
* Submit.py --goldentip 425b583f25db --instance create --commands cmds.txt --iter 5 --mailid mahesh@multicorewareinc.com -- patch1.patch patch2.patch patch3.patch

Note1:
-> commands, patch file names should not contain underscore('_').

Output format after invoking,
# Submit.py --goldentip 425b583f25db --instance create --commands cmds.txt --mailid mahesh@multicorewareinc.com -- test1.patch test2.patch test3.patch
wait until connected to FTP Server...
connected to FTP server...
test1.patch transfered to the Jenkin server....
test2.patch transfered to the Jenkin server....
test3.patch transfered to the Jenkin server....
cmds.txt transfered to the Jenkin server....

your patches are transfered to FTP server
FTP server will upload patches on egnyte and launch AWS instance
you can track it on egnyte and AWS dashboard
You will get the results to your mailid


1) cmds.example:
If you want to run performance or quality regression on your new feature then you have to pass this file.
# available sequences on AWS instance - Johnny_1280x720_60.y4m, KristenAndSara_1280x720_60.y4m, BasketballDrive_1920x1080_50.y4m,ParkScene_1920x1080_24.y4m,  Kimono1_1920x1080_24.y4m, Traffic_4096x2048_30p.y4m, tearsofsteel_4k_1000f_s214.y4m,sintel_4k_600f.y4m, Coastguard_4k.y4m
# commandline should be like, 
Kimono1_1920x1080_24.y4m --preset veryfast --bitrate 900


2) default commandlines already set up on instance

commands.conf.txt from x265Batch folder,

BasketballDrive_1920x1080_50.y4m --preset ultrafast --bitrate 4000
BasketballDrive_1920x1080_50.y4m --preset medium --bitrate 7000
BasketballDrive_1920x1080_50.y4m --preset veryslow --bitrate 9000
BasketballDrive_1920x1080_50.y4m --preset ultrafast --qp 35
BasketballDrive_1920x1080_50.y4m --preset medium --qp 25
BasketballDrive_1920x1080_50.y4m --preset veryslow --qp 20
Kimono1_1920x1080_24.y4m --preset veryfast --bitrate 9000
Kimono1_1920x1080_24.y4m --preset fast --bitrate 7000
Kimono1_1920x1080_24.y4m --preset slower --bitrate 4000
Kimono1_1920x1080_24.y4m --preset ultrafast --crf 20
Kimono1_1920x1080_24.y4m --preset medium --crf 28
Kimono1_1920x1080_24.y4m --preset veryslow --crf 32
Traffic_4096x2048_30p.y4m --preset ultrafast --bitrate 7000
Traffic_4096x2048_30p.y4m --preset medium --bitrate 10000
Traffic_4096x2048_30p.y4m --preset veryslow --bitrate 15000
Traffic_4096x2048_30p.y4m --preset veryfast --qp 20
Traffic_4096x2048_30p.y4m --preset fast --qp 25
Traffic_4096x2048_30p.y4m --preset slower --qp 35
Traffic_4096x2048_30p.y4m --preset veryfast --crf 32
Traffic_4096x2048_30p.y4m --preset fast --crf 28
Traffic_4096x2048_30p.y4m --preset slower --crf 20
Coastguard_4k.y4m --preset superfast --bitrate 15000
Coastguard_4k.y4m --preset slow --bitrate 10000
Coastguard_4k.y4m --preset slower --bitrate 7000


Note2:
    Python 2.7.9 is recommended, but any recent version of Python 2.n should work.
