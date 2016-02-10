# please configure the variables starts with 'my_' as neccessary

# specific name for this test
my_tag = ''

# email the results
my_email_from   = ''
my_smtp_pwd     = ''
my_smtp_host    = 'smtp.gmail.com'
my_smtp_port    = 587
my_email_to     = ''


# files that you wish to upload or download from ftp
# here password should be base64 encoded
my_ftp_url              = 'ftp-multicorewareinc.egnyte.com'
my_ftp_user             = ''
my_ftp_pass             = ''
my_ftp_path             = ''
my_ftp_path_stable      = ''
my_ftp_path_default     = ''
my_ftp_path_stableold   = ''
my_ftp_path_defaultold  = ''
my_ftp_branches         = ''
my_ftp_prevbranch       = ''
my_ftp_requestid        = ''
my_ftp_instanceid       = ''

# are you using this script for running performance regression on patches?
my_patchtest = False

# set AWS credentials and don't make it as public
my_AWS_ACCESS_KEY_ID = ''
my_AWS_SECRET_ACCESS_KEY = ''

my_make_flags   = ['-j', '32'] # example: ['-j', '8'] for 8-core build parallelism

# add one entry here per build target that you would like to build and test
my_builds = {'gcc'  : ('gcc/', 'gcc', 'Unix Makefiles', '',{})
    # Examples:
    #
    #'gcc'   :                   # build label (short name)
    #         ('default/',       # unique build folder
    #          'gcc',            # build group, see below
    #          'Unix Makefiles', # cmake generator
    #          'static checked', # short-hand cmake options (see below)
    #          {}),              # env-vars and other keyword arguments
    #
    #'gcc32' : ('gcc32/', 'gcc32', 'Unix Makefiles', 'static', {'CFLAGS':'-m32'}),
    #'gcc10' : ('gcc10/', 'gcc10', 'Unix Makefiles', '16bpp', {}),
    #'llvm'  : ('llvm/', 'gcc', 'Unix Makefiles', 'checked',
    #           {'CC' : 'clang', 'CXX' : 'clang++'}),
    #'vc11'  : ('vc11/', 'vc', 'Visual Studio 11 Win64', 'checked', {}),
    #'vc11D' : ('vc11D/', 'vc', 'Visual Studio 11 Win64', 'debug crt noasm ppa', {}),
    #'win32' : ('vc11x86/', 'vc', 'Visual Studio 11', 'static ppa', {}),
    #'mingw' : ('mingw/', 'gcc', 'MinGW Makefiles', 'tests',
    #           {'PATH' : r'C:\mingw64\bin'}),
}

# Many builds of x265 will produce the same outputs given the same input
# sequence and command line. The 'build group' string identifies these
# groups of encoder builds which are expected to match outputs

# Supported keyword arguments:
#   CFLAGS - directly assigned to CMAKE CFLAG args (intended for -m32)
#   CC,CXX - are set in the environment for cmake for selecting compilers
#   PATH   - this path is inserted into PATH for cmake, build and encoder runs
#            intended for MinGW/bin folder

# short-hand strings for CMAKE options, feel free to add more
option_strings = {
    'warn'    : '-DWARNINGS_AS_ERRORS=ON',
    'checked' : '-DCHECKED_BUILD=ON',
    'ftrapv'  : '-DENABLE_AGGRESSIVE_CHECKS=ON',
    'main10'  : '-DHIGH_BIT_DEPTH=ON',
    'debug'   : '-DCMAKE_BUILD_TYPE=Debug',
    'reldeb'  : '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
    'tests'   : '-DENABLE_TESTS=ON',
    'ppa'     : '-DENABLE_PPA=ON',
    'stats'   : '-DDETAILED_CU_STATS=ON',
    'static'  : '-DENABLE_SHARED=OFF',
    'noasm'   : '-DENABLE_ASSEMBLY=OFF',
    'nocolor' : '-DCMAKE_COLOR_MAKEFILE=OFF',
    'crt'     : '-DSTATIC_LINK_CRT=ON',
}
