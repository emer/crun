# this is the grunt git-based run daemon sub-script: https://github.com/emer/grunt
# this is the inner-loop grunt daemon that is spawned by grund.py for each project working directory
# it is passed the arg: ~/grunt/wc/server/username/projname to process

from git import Repo
import os
import sys
import subprocess
from subprocess import Popen, PIPE
import shutil
import glob
from datetime import datetime, timezone
import csv

# turn this on to see more verbose debug messages
grunt_debug = False

# grunt_wc is the working dir for project: ~/grunt/wc/server/username/projname
grunt_wc = ""

# grunt_jobs is the jobs git working dir for project: ~/grunt/wc/server/username/projname/jobs
grunt_jobs = ""

# grunt_jobs_repo is active git repo handle
grunt_jobs_repo = 0

# grunt_results is the jobs git working dir for project: ~/grunt/wc/server/username/projname/results
grunt_results = ""

# grunt_results_repo is active git repo handle
grunt_results_repo = 0

# grunt_jobs_shafn is the sha filename that we use to track what has been processed
grunt_jobs_shafn = ""

# grunt_jobid is the current jobid code
grunt_jobid = ""

# grunt_job is current job file relative to grunt_jobs
# set by master update loop
grunt_job = ""

# grunt_jobdir is current job directory relative to grunt_jobs
# e.g., active/jobid/projname
# set by get_command
grunt_jobdir = ""

# grunt_jobpath is current full job path: grunt_jobs/grunt_jobdir
# set by get_command
grunt_jobpath = ""

# grunt_jobfnm is current job filename -- grcmd.*
# set by get_command
grunt_jobfnm = ""

# grunt_cmd is current command -- part after grcmd.
# set by get_command
grunt_cmd = ""

# get_command gets job file paths based on a job_file which is relative to project 
# returns True if is a valid command file, otherwise False
def get_command(job_file):
    global grunt_jobdir, grunt_jobpath, grunt_jobid, grunt_jobfnm, grunt_cmd
    file_split = os.path.split(job_file)
    fnm = file_split[1]
    prefix = "grcmd."
    if not fnm.startswith(prefix):
        return False
    grunt_jobfnm = fnm
    grunt_cmd = fnm[len(prefix):]
    grunt_jobdir = file_split[0]
    grunt_jobpath = os.path.join(grunt_jobs, grunt_jobdir)
    grunt_jobid = os.path.split(grunt_jobdir)[1]
    return True

def write_csv(fnm, header, data):
    with open(fnm, 'w') as csvfile: 
        csvwriter = csv.writer(csvfile) 
        csvwriter.writerow(header) 
        csvwriter.writerows(data)

def write_string(fnm, stval):
    with open(fnm,"w") as f:
        f.write(stval + "\n")

def read_string(fnm):
    # reads a single string from file and strips any newlines -- returns "" if no file
    if not os.path.isfile(fnm):
        return ""
    with open(fnm, "r") as f:
        val = str(f.readline()).rstrip()
    return val

def read_strings(fnm):
    # reads multiple strings from file, result is list and strings still have \n at end
    if not os.path.isfile(fnm):
        return []
    with open(fnm, "r") as f:
        val = f.readlines()
    return val

def read_strings_strip(fnm):
    # reads multiple strings from file, result is list of strings with no \n at end
    if not os.path.isfile(fnm):
        return []
    with open(fnm, "r") as f:
        val = f.readlines()
        for i, v in enumerate(val):
            val[i] = v.rstrip()
    return val

def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)    

def timestamp_local(dt):
    # returns a string of datetime object in local time -- for printing
    return utc_to_local(dt).strftime("%Y-%m-%d %H:%M:%S %Z")

def timestamp_fmt(dt):
    # returns a string of datetime object formatted in standard timestamp format
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z")

def parse_timestamp(dtstr):
    # returns a datetime object from timestamp-formatted string, None if not properly formatted
    try:
        dt = datetime.strptime(dtstr, "%Y-%m-%d %H:%M:%S %Z")
    except ValueError as ve:
        # print(str(ve))
        return None
    return dt

def timestamp():
    return timestamp_fmt(datetime.now(timezone.utc))

def read_timestamp(fnm):
    # read timestamp from file -- returns None if file does not exist or timestamp format is invalid
    if not os.path.isfile(fnm):
        return None
    return parse_timestamp(read_string(fnm))

def read_timestamp_to_local(fnm):
    # read timestamp from file -- if can be converted to local time, then do that, else return string
    if not os.path.isfile(fnm):
        return ""
    dstr = read_string(fnm)
    dt = parse_timestamp(dstr)
    if dt == None:
        return dstr
    return timestamp_local(dt)
    
file_list_header = ["File", "Size", "Modified"]
    
def list_files(ldir):
    # returns a list of files in directory with fields as in file_list_header
    fls = os.listdir(ldir)
    flist = []
    for f in fls:
        fp = os.path.join(ldir, f)
        if not os.path.isfile(fp):
            continue
        if f[0] == '.' or f.startswith("job.") or f.startswith("grcmd.") or f == "grunter.py":
            continue
        mtime = timestamp_fmt(datetime.fromtimestamp(os.path.getmtime(fp), timezone.utc))
        sz = os.path.getsize(fp)
        flist.append([f, sz, mtime])
    flist.sort()
    return flist

# add job files adds all files named job.* in current dir
def add_job_files(jobid):
    os.chdir(grunt_jobpath)
    flist = list_files("./")
    write_csv("job.list", file_list_header, flist)
    jobfiles = "\n".join(glob.glob("job.*"))
    grunt_jobs_repo.remotes.origin.push()
    for f in jobfiles.splitlines():
        grunt_jobs_repo.git.add(os.path.join(grunt_jobdir, f))

# call the grunter user-script with command
def call_grunter(grcmd):
    print("Calling grunter for job: " + grunt_jobdir + " cmd: " + grcmd)
    os.chdir(grunt_jobpath)
    if (not os.path.isfile("grunter.py")):
        print("Error: grunter.py script not found -- MUST be present and checked into git!")
        return
    try:
        subprocess.run(["python3","grunter.py", grcmd])
    except subprocess.CalledProcessError:
        print("Failed to run grunter.py script")
        return
    add_job_files(grunt_jobid)
        
def update_job():
    os.chdir(grunt_jobpath)
    jfn = os.path.join(grunt_jobpath, grunt_jobfnm)
    ts = read_timestamp(jfn)
    rdir = os.path.join(grunt_results,grunt_jobdir)
    if not os.path.isdir(rdir):
        os.makedirs(rdir)
    if ts == None: # not a timestamp -- must be files!
        fnms = read_strings_strip(jfn)
        for f in fnms:
            if len(f) == 0:  # why is it even doing this?
                continue
            rf = os.path.join(rdir,f)
            shutil.copyfile(f, rf)
            print("added results: " + rf)
            grunt_results_repo.git.add(os.path.join(grunt_jobdir,f))
    else:
        if (not os.path.isfile("grunter.py")):
            print("Error: grunter.py script not found -- MUST be present and checked into git!")
            return
        p = subprocess.check_output(["python3", "grunter.py", "results"], universal_newlines=True)
        for f in p.splitlines():
            if len(f) == 0:  # why is it even doing this?
                continue
            rf = os.path.join(rdir,f)
            shutil.copyfile(f, rf)
            print("added results: " + rf)
            grunt_results_repo.git.add(os.path.join(grunt_jobdir,f))
    add_job_files(grunt_jobid)

def delete_job():
    jdir = os.path.split(grunt_jobdir)[0]
    sli = grunt_jobdir.index("/")
    deldir = "delete" + jdir[sli:]
    os.chdir(grunt_jobs)
    subprocess.run(["git", "mv", jdir, deldir])
    os.chdir(grunt_results)
    subprocess.run(["git", "rm", "-r", "-f", jdir])
    shutil.rmtree(jdir, ignore_errors=True, onerror=None)

def archive_job():
    jdir = os.path.split(grunt_jobdir)[0]
    sli = grunt_jobdir.index("/")
    deldir = "archive" + jdir[sli:]
    os.chdir(grunt_jobs)
    subprocess.run(["git", "mv", jdir, deldir])
    os.chdir(grunt_results)
    subprocess.run(["git", "mv", jdir, deldir])

def nuke_job():
    jdir = os.path.split(grunt_jobdir)[0]
    os.chdir(grunt_jobs)
    subprocess.run(["git", "rm", "-r", "-f", jdir])
    shutil.rmtree(jdir, ignore_errors=True, onerror=None)
    os.chdir(grunt_results)
    subprocess.run(["git", "rm", "-r", "-f", jdir])
    shutil.rmtree(jdir, ignore_errors=True, onerror=None)

def newproj_server():
    jfn = os.path.join(grunt_jobpath, grunt_jobfnm)
    projnm = read_string(jfn)
    if projnm == None:
        print("Error: newproj-server: no valid project name found in: " + grunt_jobfnm)
        return
    print("running grunt.py newproj " + projnm)
    subprocess.run(["python3", "grunt.py", "newproj", projnm])
    
def commit_jobs():
    commit = str(grunt_jobs_repo.heads.master.commit)
    with open(grunt_jobs_shafn, "w") as f:
        f.write(commit)
    grunt_jobs_repo.git.add(grunt_jobs_shafn)
    grunt_jobs_repo.index.commit("GRUND: done up to commit " + commit)
    grunt_jobs_repo.remotes.origin.push()
    
def commit_results():
    commit = str(grunt_results_repo.heads.master.commit)
    with open(grunt_results_shafn, "w") as f:
        f.write(commit)
    grunt_results_repo.git.add(grunt_results_shafn)
    grunt_results_repo.index.commit("GRUND: done up to commit " + commit)
    grunt_results_repo.remotes.origin.push()
    
###################################################################
#  starts running here    
    
if len(sys.argv) != 2:
    print("usage: grund_sub.py ~/grunt/wc/server/username/projname")
    print("  1 argument needed, but " + str(len(sys.argv) - 1) + " given")
    exit(1)
elif os.path.isdir(sys.argv[1]):
    grunt_wc = sys.argv[1]
    grunt_jobs = os.path.join(grunt_wc,"jobs")
    try:
        grunt_jobs_repo = Repo(grunt_jobs)
    except Exception as e:
        print("The directory provided is not a valid grunt jobs git working directory: " + grunt_wc + "! " + str(e))
        exit(3)

    grunt_results = os.path.join(grunt_wc,"results")
    try:
        grunt_results_repo = Repo(grunt_results)
    except Exception as e:
        print("The directory provided is not a valid grunt jobs git working directory: " + grunt_wc + "! " + str(e))
        exit(3)
else:
    print("The path given is not a valid directory")
    exit(2)

grunt_jobs_shafn = os.path.join(grunt_jobs,"last_processed_commit.sha")
grunt_results_shafn = os.path.join(grunt_results,"last_processed_commit.sha")
    
grunt_jobs_repo.remotes.origin.pull()
grunt_results_repo.remotes.origin.pull()

# Check if we have a valid commit sha1 hash as the last processed, so that we can pickup launching from there.

if os.path.isfile(grunt_jobs_shafn):
    with open(grunt_jobs_shafn, "r") as f:
        last_processed_commit_hash = f.readline()
    check_for_updates = True
    com_jobs = False
    com_results = False
    if grunt_debug:
        print("Begin processing commits from hash: " + last_processed_commit_hash, flush=True)
    last_to_head = last_processed_commit_hash + "..HEAD"
    most_recent_head = None
    for cm in grunt_jobs_repo.iter_commits(rev=last_to_head):
        if most_recent_head == None:
            most_recent_head = cm
        if cm.message.startswith("GRUND:"): # skip our own -- key
            continue
        if grunt_debug:
            print("Processing commit " + str(cm), flush=True)
        for f in cm.stats.files:
            if not get_command(f):
                continue
            print("\ngrund command: " + grunt_cmd + " in: " + grunt_jobdir + " at: " + timestamp(), flush=True)
            com_jobs = True
            if grunt_cmd == "update":
                update_job()
                com_results = True
            elif grunt_cmd == "nuke":
                nuke_job()
                com_results = True
            elif grunt_cmd == "archive":
                archive_job()
                com_results = True
            elif grunt_cmd == "delete":
                delete_job()
                com_results = True
            elif grunt_cmd == "newproj-server":
                newproj_server()
            else:
                call_grunter(grunt_cmd)
    if com_jobs:            
        commit_jobs()
    if com_results:
        commit_results()
    exit(0)    
else:
    print(grunt_jobs_repo.heads.master.commit)
    with open(grunt_jobs_shafn, "a") as f:
        f.write(str(grunt_jobs_repo.heads.master.commit))
    grunt_jobs_repo.git.add(grunt_jobs_shafn)
    grunt_jobs_repo.index.commit("GRUND: First commit")
    grunt_jobs_repo.remotes.origin.push()
    print(grunt_jobs_repo.heads.master.commit)

    with open(grunt_results_shafn, "a") as f:
        f.write(str(grunt_results_repo.heads.master.commit))
    grunt_results_repo.git.add(grunt_results_shafn)
    grunt_results_repo.index.commit("GRUND: First commit")
    grunt_results_repo.remotes.origin.push()
    exit(0)


