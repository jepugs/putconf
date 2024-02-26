import argparse
from pathlib import Path
import re
import sys
import os

from putconf.PutconfSource import OverwriteMode, PutconfSource
 
def find_git():
    for d in os.get_exec_path():
        e = os.path.join(d, "git")
        if os.path.exists(e):
            return e
    return None

def decomp_source(source_str):
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

def as_rel_path(p, rel_to):
    real_p = os.path.realpath(p)
    real_rel_to = os.path.realpath(rel_to)
    common = os.path.commonpath([real_p, real_rel_to])
    if common != real_rel_to:
        return None
    return os.path.relpath(real_p, real_rel_to)

_program_usage ="""putconf [options] SOURCE [FILES ...]"""
_program_description = """Install/sync user configuration files from a folder or git repository.

Files/directories in the toplevel of SOURCE are ignored if their names
begin with dots. However, if SOURCE contains a directory named ".dotfiles",
the files and directories within will be treated as if they reside
directly in SOURCE, but will have dots prepended to their names in TARGET.

At this time, installing/synchronizing a folder literally named "dotfiles"
is not supported.

FILES should consists of paths within TARGET. Relative paths are calculated
from the directory in which putconf is run."""

_program_epilog = """Note: --checkout can be used to specify a branch for syncing remote
repositories. Using -S and --checkout together is only supported for
remote repos. For local repos, synced files are written straight into
the worktree."""

def main():
    parser = argparse.ArgumentParser(usage=_program_usage,
                                     description=_program_description,
                                     epilog=_program_epilog,
                                     add_help=False,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)

    arg_group = parser.add_argument_group("Arguments")
    # use nargs="?" so parse_args doesn't error when it's missing
    arg_group.add_argument("SOURCE",
                           help="Where config files are stored. (Path or URL).",
                           nargs="?")
    arg_group.add_argument("FILES",
                           help="Which config files to act on. (Default all).",
                           nargs="*")

    glob_opts = parser.add_argument_group("Global Options")
    glob_opts.add_argument("-t",
                           "--target",
                           help="Where config files go. Defaults to $HOME.")
    glob_opts.add_argument("-h",
                           "--help",
                           action="store_true", help="Show help and exit.")
    glob_opts.add_argument("-v",
                           "--verbose",
                           action="store_true",
                           help="Print extra information.")
    glob_opts.add_argument("--checkout",
                           help="Branch, commit, or tag to check out from source.",
                           metavar="REF")
    glob_opts.add_argument("--pull",
                           action="store_true",
                           help="When SOURCE is a local git repository, attempt to run `git pull` before install/sync.")
    glob_opts.add_argument("--dry-run",
                           action="store_true",
                           help="Do not actually install/sync files. Implies -v. (Git clone and pull operations will still be executed).")
    glob_opts.add_argument("--version",
                           action="store_true",
                           help="Show version and exit.")

    inst_opts = parser.add_argument_group("Installation")
    inst_opts.add_argument("-w",
                           "--overwrite",
                           action="store_true",
                           help="Overwrite existing files without prompting.")
    inst_opts.add_argument("-n",
                           "--no-overwrite",
                           action="store_true",
                           help="Never overwrite existing files.")

    sync_opts = parser.add_argument_group("Synchronization")
    sync_opts.add_argument("-S",
                           "--sync-source",
                           action="store_true",
                           help="Update SOURCE with config files from TARGET.")
    #sync_opts.add_argument("-c",
    #                       "--commit",
    #                       help="Commit changes to SOURCE with the given message.",
    #                       metavar="MSG")
    #sync_opts.add_argument("-P",
    #                       "--push",
    #                       action="store_true",
    #                       help="Push changes. Implied true when SOURCE is a remote repository. Requires -c.")

    # it's ok with me if parse_args errors out on an unrecognized option
    args = parser.parse_intermixed_args()

    # ensure no mutually exclusive options are used together
    if args.overwrite and args.no_overwrite:
        print("Error: --overwrite and --no-overwrite are mutually exclusive.")
        sys.exit(1)
    if args.sync_source:
        if args.overwrite or args.no_overwrite:
            print("Error: --sync-source cannot be used with --overwrite or --no-overwrite.")
            sys.exit(1)
    #else:
    #    if args.commit or args.push:
    #        print("Error: --commit and --push require --sync-source.")
    #        sys.exit(1)

    if args.help:
        parser.print_help()
        sys.exit(1)
    elif args.version:
        print("putconf 0.1")
        sys.exit(0)
    elif not args.SOURCE:
        print("Error: SOURCE is required.")
        sys.exit(1)

    dry_run = args.dry_run
    verbose = args.verbose
    if args.dry_run:
        print("Dry run: No changes will be made to destination.")
        verbose = True

    proto, path = decomp_source(args.SOURCE)
    # check transport
    is_remote = proto in ["http", "https", "ssh", "git"]
    if not (is_remote or proto == "file"):
        print("Error: Unsupported transport %s." % proto)
        sys.exit(1)

    # sync operations only support local directories (for now)
    if args.sync_source and is_remote:
        print("Error: Synchronization is only supported for local directories.")
        sys.exit(1)

    git_exe = find_git()

    target = args.target if args.target else os.environ.get("HOME")

    # convert FILES to paths relative to target
    files = [] # TODO
    for f in args.FILES:
        p = as_rel_path(f, target)
        if not p:
            print("Error: %s is not within %s." % (f, args.target))
            sys.exit(1)
        files.append(p)

    try:
        source = PutconfSource(path, is_remote, files, args.checkout, args.pull, git_exe)
        if args.sync_source:
            source.sync_from_target(target, verbose, dry_run)
        else:
            ow_mode = OverwriteMode.PROMPT
            if args.overwrite:
                ow_mode = OverwriteMode.ALL
            elif args.no_overwrite:
                ow_mode = OverwriteMode.NONE
            source.install_to_target(target, verbose, dry_run, ow_mode)
    except Exception as e:
        print("Error: %s" % e)
        sys.exit(1)

    

if __name__ == "__main__":
    main()
