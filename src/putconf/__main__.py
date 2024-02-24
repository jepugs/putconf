import argparse
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import os

def proto_and_path(source_str):
    """Break source_string into a protocol and a path and return proto, path. If
    source_str does not begin with <proto>:// then proto will be "file".
    """
    proto = "file"
    path = ""
    # check if source is a path or a url
    match = re.match(r"(?P<proto>\w+)://(?P<path>.*)", source_str)
    if match:
        proto = match.group("proto")
        path = match.group("path")
    else:
        path = source_str
    return proto, path

def find_git():
    for d in os.get_exec_path():
        e = os.path.join(d, "git")
        if os.path.exists(e):
            return e
    return None

def set_up_source(proto, path, gitref):
    """Set up a putconf source and get an absolute path to a directory
    containing the unpacked config files. Also returns a boolean indicating
    whether a temporary directory was created which should be removed later.
    """
    if proto in ["http", "https", "ssh", "git"] or gitref is not None:
        git_exe = find_git()
        if git_exe is None:
            raise RuntimeError("Git not found.")
        res = ""
        try: res = tempfile.mkdtemp("__putconf-source")
        except: raise RuntimeError("Couldn't create temporay directory for source.")

        proc_args = [git_exe, "clone", path, res]
        if proto == "file": proc_args.insert(2, "--shared")
        repo_path = path if proto == "file" else proto + "://" + path
        proc = subprocess.run([git_exe, "clone", path, res])
        if proc.returncode != 0:
            # FIXME: clean up tempfile?
            raise RuntimeError("Git exited with code %i." % proc.returncode)

        if gitref:
            # FIXME: clean up tempfile?
            raise NotImplementedError("--gitref option.")

        return res, True

    elif proto == "file":
        res = None
        res = os.path.realpath(path)
        if not os.access(res, os.R_OK):
            raise RuntimeError("Cannot read source directory.")
        if not os.path.isdir(res):
            raise RuntimeError("Source not a directory.")
        return res, False
    else:
        raise RuntimeError("Unsupported protocol %s" % proto)

def prepend_dot(path):
    return "." + str(path)

def get_putconf_work(src):
    """Returns files, dirs, where each return value is a list of tuples
    consisting of the absolute path to a file followed by the relative path
    where it should be installed in the destination directory.
    """
    res_files = []
    subdirs = []

    # scan the top directory,
    dotfile_dir = None
    for x in os.scandir(src):
        if x.is_dir() and x.name == "dotfiles":
            dotfile_dir = x.path
        elif x.is_dir():
            if x.name != ".git":
                subdirs.append(x.name)
        else:
            res_files.append((x.path, x.name))

    # scan the subdirectories
    i = 0
    while i < len(subdirs):
        d = subdirs[i]
        i += 1
        for x in os.scandir(os.path.join(src, d)):
            rel = os.path.join(d, x.name)
            if x.is_dir():
                subdirs.append(rel)
            else:
                res_files.append((os.path.join(src, rel), rel))

    res_subdirs = subdirs

    # scan dotfiles
    if dotfile_dir:
        dot_subdirs = []
        for x in os.scandir(dotfile_dir):
            if x.is_dir():
                dot_subdirs.append(x.name)
            else:
                res_files.append((x.path, prepend_dot(x.name)))
        i = 0
        while i < len(dot_subdirs):
            d = dot_subdirs[i]
            i += 1
            for x in os.scandir(os.path.join(dotfile_dir, d)):
                rel = os.path.join(d, x.name)
                if x.is_dir():
                    dot_subdirs.append(rel)
                else:
                    res_files.append((x.path, prepend_dot(rel)))

        for d in dot_subdirs:
            res_subdirs.append(prepend_dot(d))

    return res_files, res_subdirs

def do_dir_work(work, dest, dry_run, verbose):
    for rel in work:
        d = os.path.join(dest, rel)
        if os.path.isdir(d):
            if dry_run or verbose:
                print("Directory already exists: %s" % d)
        elif os.path.exists(d):
            raise RuntimeError("%s exists and is not a directory." % d)
        else:
            if dry_run or verbose:
                print("Create directory: %s" % d)
            if not dry_run:
                try: os.mkdir(d)
                except: raise RuntimeError("Couldn't create directory %s" % d)

def overwrite_prompt(dest):
    while True:
        s = input("Overwrite file %s? (y)es/(n)o/(a)ll: " % dest)
        if s == "y":
            return True, False
        elif s == "n":
            return False, False
        elif s == "a":
            return True, True

def do_file_work(work, dest, force, dry_run, verbose):
    # whether the user answered "(a)ll" to the overwrite prompt
    ow_all = False
    for src, rel in work:
        f = os.path.join(dest, rel)
        if os.path.isdir(f):
            raise RuntimeError("%s exists and is a directory." % f)
        if os.path.exists(f):
            if force or ow_all:
                if dry_run or verbose:
                    print("Overwrite file: %s" % f)
                if not dry_run:
                    try: shutil.copy(src, f)
                    except: raise RuntimeError("Couldn't overwrite file %s" % f)
            elif dry_run:
                print("Prompt to overwrite file: %s" % f)
            else:
                ow_one, ow_all = overwrite_prompt(f)
                if ow_one:
                    try: shutil.copy(src, f)
                    except: raise RuntimeError("Couldn't overwrite file %s" % f)
        else:
            if dry_run or verbose:
                print("Create file: %s" % f)
            if not dry_run:
                try: shutil.copy(src, f)
                except: raise RuntimeError("Couldn't create file %s" % f)

_program_usage ="""putconf [options] SOURCE [FILES ...]"""
_program_description = """Install user configuration files from a folder or git repository.

If SOURCE contains a directory named "dotfiles", the files and directories
within will be treated as if they reside directly in SOURCE, but with dots
prepended to their names."""

def main():
    parser = argparse.ArgumentParser(usage=_program_usage, description=_program_description, add_help=False, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-d", "--dest", help="Where to put config files. Defaults to $HOME.")
    parser.add_argument("-f", "--force", action="store_true", help="Overwrite existing files without prompting.")
    parser.add_argument("-g", "--gitref", help="Git reference to check out from source.")
    parser.add_argument("-h", "--help", action="store_true", help="Show help and exit.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print extra information.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write any files. Implies -v.")
    parser.add_argument("--version", action="store_true", help="Show version and exit.")
    # use nargs="?" so parse_args doesn't error when it's missing
    parser.add_argument("SOURCE", help="Where to get config files.", nargs="?")
    parser.add_argument("FILES", help="Files to install. Defaults to all files in SOURCE.", nargs="*")
    # but it's ok with me if parse_args errors out on an unrecognized option
    args = parser.parse_args()

    if args.help:
        parser.print_help()
        sys.exit(1)
    elif args.version:
        print("putconf 0.1")
        sys.exit(0)
    elif not args.SOURCE:
        print("Error: SOURCE is required. Run with -h/--help for usage.")
        sys.exit(1)
    elif args.gitref:
        print("Error (unimplemented behavior): Option --gitref not yet supported.")
        sys.exit(1)

    if args.dry_run:
        print("Dry run: No changes will be made to destination.")

    proto, src_desc = proto_and_path(args.SOURCE)
    dest = Path(args.dest) if args.dest else Path.home()

    # steps:
    # - set up the configuration source
    # - identify which files to copy and where they're going
    # - install files

    src, del_after = None, None
    try:
        src, del_after = set_up_source(proto, src_desc, args.gitref)
        file_work, dir_work = get_putconf_work(src)
        do_dir_work(dir_work, dest, args.dry_run, args.verbose)
        do_file_work(file_work, dest, args.force, args.dry_run, args.verbose)
    except NotImplementedError as err:
        print("Error (unimplemented behavior):", err)
        if dry_run: print("Dry run halted early due to error.")
        sys.exit(1)
    except RuntimeError as err:
        print("Error:", err)
    finally:
        if del_after and src:
            shutil.rmtree(src)

    print("Installed files to: %s" % dest)


if __name__ == "__main__":
    main()
