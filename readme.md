x265 test harness
=================

This repository contains the Python scripts which make up the core of
x265's automated regression tests. It has no external dependencies
outside of Python and the tools needed to build x265 itself.  Python
2.7.9 is recommended, but any recent version of Python 2.n should work.

These scripts are designed to work in conjunction with a pair of network
file shares, one called 'sequences' where all of your test video
sequences are found, and another called 'goldens' where the scripts will
keep track of the expected golden outputs for each test case.

Filename                    | Description
---------------------------:| ------------------------------------------------------------------
utils.py                    | core routines for running tests and logging failures
smoke-test.py               | execution script for smoke tests (build, testbench, short encodes)
regression-test.py          | execution script for overnight regression test encodes
long-test.py                | execution script for week long exhaustive testing
conf.py.example             | example configuration file
output-changing-commits.txt | text file with list of x265 commits which changed outputs
readme.md                   | this file

The primary purpose of this test-harness is to catch unintentional
changes in the output of the encoder, including non-deterministic
results.

Setup
-----

The first step to clone the x265 source repository from bitbucket or
videolan; the regression scripts rely on the fact that the source code
lives within a Mercurial repository. It uses the changeset hashes and
revision history to keep track of which output changing commits are
ancestors of the revision you are testing.  This test harness itself
must also be a Mercurial repository for it to function correctly.

The next step is to make sure you have all of the tools for compiling
x265 on your test machine, including cmake and yasm.  The test harness
supports all recent GCC versions and clang, while on Windows it supports
Visual Studio 2008, 2010, 2012, and 2013 and also MinGW (no need for
MSYS or cygwin, you only need the base MinGW compiler). For this step,
ensure you can build x265 correctly with all the compilers you are going
to support in the test harness.  Debugging build issues within the test
harness itself can be tedious.

Next you must create your 'sequences' shared folder and your 'goldens'
shared folder, if they do not yet exist. Both folders are intended to be
shared across all developers at any given geographical location, so they
need to be nfs/smb shared as broadly as possible. 'sequences' can be a
read-only share but 'goldens' must be read/write.

Lastly, copy the conf.py.example file that is provided in the repository
into conf.py and then edit all of the variables within.

Variable         | Description
----------------:| --------------------------------------------------------------------------------------------------------------------------
my_machine_name  | short name describing the test machine, usually a hostname. This name will be used in pass/fail filenames and in test logs
my_machine_desc  | description of CPUs (core count, freq, sockets, SIMD arches, etc). This data will be included in logs
my_x265_source   | the location of the source/ folder within your x265 clone
my_sequences     | the location of your 'sequences' folder
my_goldens       | the location of your 'goldens' folder
my_hm_decoder    | the location of an HM decoder binary, HM-16.3 or later
my_tempfolder    | the location where the testbench can create short-lived tempfolders
my_progress      | Python boolean (True or False) controlling console spew
my_pastebin_key  | Can be left empty unless you are automating the tests
my_make_flags    | Python list of extra arguments to pass to gmake
option_strings   | Python dict mapping short names to cmake options, for convenience
my_builds        | Python dict listing all of the builds of x265 you intend to test

Note:
	conf.py is a Python script and uses Python syntax and white-space
	rules. r'foo' is a Python *raw* string which means you can use
	back-slashes without escaping them, except for the very end of the
	string. r'foo\' is invalid because Python thinks you are escaping
	the close quote.

For Windows deveopers, we recommend that my_builds{} have at least one of
each of:

* A VisualStudio Win64 build - for base coverage
* A VisualStudio Win32 build - for 32bit build/link and testbench problems
* A VisualStudio Win64 16bpp build - for HBD build/link and testbench problems
* A VisualStudio Win64 debug build - for leak detection
* A MinGW 64bit build - for GCC warning coverage

For Linux/Mac developers, we recommend at least gcc, gcc -m32, and gcc
16bpp. Most builds should have the 'check' option enabled, for run-time
validation checking within the encoder (VS debug builds have then
enabled implicitly).

Most of the data fields in my_builds{} are self-explanatory, but the
**build group** requires an explanation. It is used to differentiate
unique golden test outputs per test case and per output changing commit.
Compilers which share the same build group string are expected to build
x265 encoders which match outputs (binary exact) for all test cases.  It
is generally safe for all Visual C compilers to share a single 'vc'
group, except 16bpp builds which obviously need their own group (we use
'vc10').  Different GCC versions seems to cause x265 outputs to diverge,
even between 64bit and 32bit compiles.  If you have multiple versions of
GCC (or mingw or clang) that will be sharing the same golden outputs
folder, you must give each compiler its own build group ('gcc-48',
'gcc-49', 'gcc-48-10', 'gcc-48-32', etc). We do not know why the GCC
compiler version has such an effect on encoder outputs, there are
suspects like the floating point operations in AQ and SAO, but no
difinitive proof or workaround.

Note:

	Our tests need HM-16.3 both because of the range extension features and
	because of a decoder bug (triggered by --repeat-headers) which was
	not fixed until 16.3


Invoking
--------

The three execution scripts support the same set of command line
arguments. If you run a script with *--help* it will print a short
description of those arguments, like this::

	./smoke-test.py [OPTIONS]
		-h/--help            show this help
		-b/--builds <string> space seperated list of build targets
		-t/--tests <fname>   location of text file with test cases
		--skip <string>      skip test cases matching string
		--only <string>      only test cases matching string
        --save-changed       save all bitstreams with changed outputs
		--no-make            do not compile sources
		--no-bench           do not run test benches
		--rebuild            remove old build folders and rebuild

Examples:

* only run regression tests with --no-wpp: `./regression-tests.py --only no-wpp`
* only run regression tests with reasonable speed: `./regression-tests.py --skip slow`
* use a user-defined test list file: `./regression-tests.py --tests my-test-list.txt`
* re-run a smoke-test, focusing on one failure: `./smoke-test.py --no-make --no-bench --only nr-intra`
* if debugging non-determinism: `./regression-tests.py --save-changed`

By default, smoke-tests.py will use the list of tests checked into the
Mercurial x265 repository as source/test/smoke-tests.txt, and the other
two scripts will read regression-tests.txt from the same location. When
you specify a test filename with *--tests* the script will look in
x265/source/test first if your test filename has no path seperators (/);
otherwise it treats the filename as a relative path.

Note that the test case files are meant to be easy to modify and write.
Each line should contain a test seqeunce (found in my_sequences) and a
command-line seperated by a comma.  Multi-pass tests will have multiple
command-lines after the sequence, with an additional comma between each
command-line. Users are recommended to create their own test files when
working on specific features or bugs, and use --tests my-tests.txt to
run them.

Note:

	Y4M test sequences are handled implicitly by the test harness, and
	are recommended over YUV files. For YUV files, the harness requires
	the resolution, fps, color-space and bitdepth to be specified in the
	filename in a particular format and order:
	foo_bar_WxH_FPS[_10bit][_CSP][_crop].yuv

The test harness creates a temporary folder for each encoder run, and
deletes the folder as soon as the encoder outputs have been validated.
This is why multiple-pass tests must be all on one line. This tells the
harness to keep the temp folder and re-use it for each of the command
lines on the same line (so files written by the first encode will still
be available for those on subsequent encodes).


Golden Outputs
--------------

After you run one of the test harness scripts, if you browse the golden
output folder you will see a list of directories that all have
12-character hash names, for example:

	06793ef5c143/ 200b12d8167d/ 22a7fc102fda/
	3022deb305ef/ 39895d0c1bbc/ 4fe4edb21cd5/
	50f49d4ecd31/ 5b82a383cc0f/ 5e5948c09450/
	...

The test-harness is built around the proposition that the outputs of the
encoder are deterministic for any given combination of test sequence and
command-line.  We codify this by generating a 6byte MD5 hash from the
sequence base filename (no path) and the list of command-line arguments
which affect outputs (preset, tune, frame count, etc). This 6byte MD5
hash is turned into a 12-character digest string that makes up the paths
in the first level of the golden outputs folder.  Each folder tracks the
output history of that single test, including different build-group
outputs.

Note that because we are hashing basenames and command lines, the hashes
will be unique between smoke tests (which adds -f50 to command lines)
and regression tests, so it is always safe to use a single golden output
folder for all test types, and it is safe for many users to share a
single golden outputs folder. It is, in fact, preferred that as many as
possible share each one, to maximize the usefulness of the test-case
pass / fail history.

Note:

	Also note that if a test case is changed in any way which affects
	encoder outputs, it will get a new hash and a new history of golden
	outputs.

Each test-case folder will contain three types of data:

	1. a text file named hashed-command-line.txt containing the sequence
	   name and command line which generated the folder name.
	2. folders of the format **YY-MM-DD-group-hash/**. These folders each
	   contain one golden output. The hash is an x265 changeset id
	   corresponding to a commit which changed outputs, and the date is
	   the commit date of that commit. The date is simply a sorting
	   convenience.
	3. files of the format **no-change-group-hash.txt**. These files
	   indicate that a given output changing commit did not change the
	   outputs of this particular test (so if any changes are found they
	   were caused by something else). The file contains the hash of the
	   ancestor commit which did generate the last known good outputs.

The *build group* name that is part of the golden output folder names
and the no-change file names is the mechanism by which the harness
differentiates between different compilers (GCC, Visual Studio, etc)
x265 will often output different deterministic outputs based on the
compiler used to build it. Compilers with the same build group name are
expected to build encoders which match outputs.  All of the users that
share a golden outputs folder must use the same build group names for
the same compilers.

A typical test case folder will look like:

	15-03-18-gcc-69b2f0d9ebbe/
	15-03-18-gcc10-69b2f0d9ebbe/
	15-03-18-gcc32-69b2f0d9ebbe/
	15-03-18-vc-69b2f0d9ebbe/
	15-03-18-vc10-69b2f0d9ebbe/
	no-change-gcc-cbfa66e0b50c.txt
	no-change-gcc10-cbfa66e0b50c.txt
	no-change-gcc32-cbfa66e0b50c.txt
	no-change-vc-cbfa66e0b50c.txt
	no-change-vc10-cbfa66e0b50c.txt
	hashed-comamnd-line.txt

In this simple history, there was one revision which generated all the
golden outputs for all build groups, and then one output changing commit
which did not change the outputs of this particular test (and one may
infer that all of the no-change files must contain '69b2f0d9ebbe' since
that is the only golden output available).

Each of the golden output folders will contain the following items:

	1. bitstream.hevc - the encoder outputs
	2. summary.txt - small text file with bitrate, psnr, and ssim metrics
	3. passed/  - folder describing passed test cases
	4. failed/  - folder describing failed test cases

The **passed/** and **failed/** folders contain text files with the
format **YY-MM-DD-hash-machinename.txt**. The date in this instance is
the date that the test was run, the hash is the revision of x265 which
was tested, and machinename is my_machine_name from conf.py on the
computer which ran the test. The file contents will describe the build
options, hardware description from my_machine_desc, encoder logs, and
output summary. If the file is in the **failed/** folder it will
additionally contain a description of the failure conditions.


Output Changing Commits
-----------------------

In order for the test harness to function correctly, it must be told
which x265 commits are deliberately changing outputs. The test harness
will assume that if there has not been an output changing commit between
the last golden output and the revision under test, that any deviations
between **bitstream.hevc** and the golden outputs are bugs.

The list of output changing commits is kept in the test-harness
repository instead of in the x265 repository for a number of reasons,
and it is very important to the health of your golden outputs folder
that all users have the most recent version of this file, so the test
bench will download the file directly from the bitbucket web interface
each time it runs the testbench, unless it detects that you have locally
modified your copy - in which case it assumes you are adding a new
change commit locally and uses the local copy.

**output-changing-commits.txt** is a simple text file with each
non-comment line containing a 12-character short-hash of an x265
mercurial changeset which changes test outputs, a space seperator, then
an optional list of keyword filters (comma seperated within square
brackets with no white-space), then finally a description of the changes
(or bug fixes) made by that commit.

It is important that new commits be added to the top of the list, each
commit must be above all of its ancestor commits in the file. So long as
you add lines to the top of the list this rule will be enforced
implicitly.

Example contents:

	69b2f0d9ebbe [scaling-list] fix bug in forward-quant with scaling list
	572b8f2dc414 [temporal-layers] fix open-gop bug with temporal layers
	1bed2e325efc [superfast,ultrafast] changes + CRF fixes from previous few commits
	50d3bb223180 adaptive quant cost fixes

Note how 50d3bb223180 changes AQ which is enabled for most presets and
so we could not make a keyword filter for it. Also note that if an
output change occurs on the stable branch, then the merge commit which
integrates that output change to the default branch is also considered
an output change commit if the default branch had output change commits
not on stable (it creates a new encoder with both changes). The merge
commit should generally get the same keyword filter as the stable branch
commit.

Note:

	VBV is unique among x265 features in that it is expected to be
	non-deterministic by design. So any tests which use VBV features are
	validated by comparing the output bitrate with the golden output
	bitrate and the test is considered a PASS if it is within a certain
	percentage. VBV test cases will only allow new golden outputs to be
	generated for an output changing commit which has a **vbv** keyword.


Test Case Validation
--------------------

About half of the logic in utils.py is dedicated to the task of
configuring, building, and running x265. The other half of the logic is
dedicated to validating the encoder outputs, a difficult job.

The primary purpose of this test-harness is to catch unintentional
changes in the output of the encoder, including non-deterministic
results.  The bitstream validation logic is the key to everything, and
essentially defines the format of the golden outputs folders.

The first steps of validation occur at beginning of the test run. The
script identifies the Mercurial revision of x265 that is under test, it
determines if the x265 source repository has any un-committed changes,
and it determines if the commit under test has been published to a
public repository (aka: whether the revision phase is draft or public).
If the revision under test is not public or has un-committed changes,
then the script sets a flag indicating that no new golden outputs will
be created by this test run, and that no pass/fail files will be
recorded. It essentially treats the golden outputs folder as read-only
when testing with non-public source code (with one exception, detailed
below). In utils.py this is *testrev* and *save_results*.

Next the encoder reads **output-changing-commits.txt** (described in the
previous section) and then iterates through each one determining which
commits are ancestors of the revision under test. The output of this
process is a list of commits, in ancestor order (newest to oldest) of
commits which might have changed the test outputs at some point in the
past. For each of these commits it remembers their keyword filters. In
utils.py these are *changers* (ordered list) and *changefilter* (dict).

Now the script is prepared to validate test-case outputs. Most of this
logic is within **checkoutputs()** in utils.py in less than 90 lines of
Python code. The process works like this:

1. Iterate through ancestor output changing commits, newest to oldest:

	a. look in the test-case folder for a no-change-*group*-*hash*.txt for
	   this commit. If found, read the file to learn the commit which
	   is currently held responsible for the outputs of this test case.

	b. else look in the test-case folder for a *YY-MM-DD-group-hash*
	   golden output folder. If present then this commit itself generated
	   the most recent golden outputs.

	c. else add this commit to an **opencommits** ordered list, meaning
	   that no test results have been recorded yet for this commit.

2. If we make it through the list and did not find any golden output
   commit, we consider this a new test case and store new golden
   outputs, giving the most recent output changing commit credit for the
   outputs (we don't know which previous commit might have originated
   these particular outputs, but using the most recent one is a good
   enough approximation). You will see a log message 'no golden outputs
   for this test case'.

3. We have identified the most recent golden outputs for this test case
   (and build group) and now we do a binary compare between the saved
   HEVC bitstream and the one which was just created.  If they match,
   then the test case is a PASS and we are essentially done but there
   are two bits of upkeep to perform. First, we generate
   **no-change-group-hash.txt** files for all open commits. Second, if
   the golden summary file had 'N/A' for PSNR and SSIM we replace the
   summary with this test results' summary (if it does not have 'N/A').
   You might see log outputs 'not changed by *hash*' or 'Correcting
   golden output summary'

4. At this point we have identified golden outputs and discovered they
   do not match the test outputs. If the test case command line includes
   '--vbv' we search the open commits for one with a **vbv** keyword.
   The first one we find takes ownership of the output changes and is
   credited with new golden outputs (if the revision under test is
   public). Otherwise we examine the summaries to determine if the
   bitrate is within an acceptable range of the last known good.
   You will see log outputs 'VBV OUTPUT CHANGED BY N.NN%'

5. For non-vbv output changes, we scan the list of open commits in
   ancestor order looking for keyword matches for the test command line.
   The first open commit with a keyword match is credited with the
   output change and new golden outputs are created (if the revision
   under test is public).  If no keyword matches are found in the open
   commits, then the testbench will accept the first open commit with no
   keyword filters.  You will see log outputs 'commit *hash* takes
   credit for this change' or 'unfiltered commit *hash* takes credit for
   this change'.

6. Finally, if we did not find an open changing commit that could have
   been responsible for the change, we must consider the test to be
   failed. You will see log outputs 'OUTPUT CHANGED *lastgoodsum* to
   *testsum*'

If the test output bitstream did not binary match the last known good
outputs for any reason (even if we are saving new golden outputs) the HM
decoder is used to decode the test output bitstream to ensure it is
valid. All of the test scripts ensure MD5 recon image hashes are enabled
in all test command lines, so this decoder pass verifies the
reconstructed pictures are valid. Any decoder errors cause the test to
fail, you will see output logs 'OUTPUT CHANGE WITH DECODE ERRORS'.

Note:

	If the revision under test matches an output change commit with a
	keyword filter, then new golden outputs are allowed to be saved for
	tests which match the keyword filter even if the commit is not yet
	public.


Suggested Change Process
------------------------

When one is ready to send a change patch to the mailing list, they
should first run the smoke-tests to ensure that:

1. GCC/MinGW and Visual Studio builds are clean with no warnings

2. x64, x86, and 16bpp test benches build and run clean

3. No output changes are found by the short smoke test encodes

4. No leaks or check failures were found

If all these tests pass, then you have a reasonable expectation that the
patch does not break anything and can be sent to the mailing list.


If the patch(es) change outputs, then your testing burden is much
higher. You must run the full regression test and analyze all of the
reported output changes and validate that they are indeed intentional.

If you have write access to the x265 and test-harness repositories, you
will add your commit hash to output-changing-commits.txt (with good
keywords when possible) and then re-run the regression tests to save the
new golden outputs. Then commit and push your test harness repo and your
output changing commit to x265 (no rebasing is allowed at this point on
the output-change commit, its hash cannot change).

If you do not have write access to those repositories, you must send
your changing patch to the ML and mention in the commit message that
this is an output changing commit and suggest keyword filters to use,
should any be applicable.


Note that all these instructions assume that the change your are making
in your patch is otherwise worthwhile and does not make bad changes to
the encoder outputs. That is outside the scope of this test harness, it
is not evaluating whether the new golden outputs are better than the
previous ones.


Profile Guided Optimizations
----------------------------

Once you have configured the test harness to build and test GCC (or
MinGW) builds (detailed above), you can use the test-harness to drive
profile-guided optimizations.

All you have to do is edit fprofile-tests.txt to include the use cases
that you would like to optimize for (including representative video
sequences) and then run: `fprofile.py`

It operates much the same way as the smoke test except it operates in
three stages.

1. compile build targets with PGO instrumentation
2. run test cases with each build target
3. compile build targets with -fprofile-use and -march=native

Disclaimers:

+ the last build will be noisy, if you look through the logs
+ Only GCC/MinGW is supported at this time.
+ Don't expect encoder outputs to exactly match non-PGO builds, since
  different GCC builds of x265 will often generate slightly different
  outputs (reldeb != debug != release != -m32)
