# configure all the variables beginning with my_, then you will be able to run the test script

# locate the paths
my_sequences     = r''
my_bitstreams    = r''

# are you created enough RAM disk? if True, then give path
my_RAMDISK       = False
my_RAMDiskpath   = r'/mnt/RAMDISK'

# compare current test performance results with golden (previous) test results
my_compareFPS = False

# email the compared test results
my_email_from   = ''
my_email_to     = ''
my_smtp_pwd     = ''
my_smtp_host    = 'smtp.gmail.com'
my_smtp_port    = 587


# upload csv files on egnyte(This is for automation of tests)
# here password should be base64 encoded
my_csvupload            = False
my_ftp_url              = ''
my_ftp_user             = ''
my_ftp_pass             = ''
my_ftp_path_stable      = ''
my_ftp_path_default     = ''
my_ftp_path_stableold   = ''
my_ftp_path_defaultold  = ''
