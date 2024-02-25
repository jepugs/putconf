import argparse
from pathlib import Path
import shutil
import sys
import os

from putconf.PutconfSource import OverwriteMode, PutconfSource
 
def find_git():
    for d in os.get_exec_path():
        e = os.path.join(d, "git")
        if os.path.exists(e):
            return e
    return None

def do_install(args):
    try:
        git_exe = find_git()
        src = PutconfSource(args.SOURCE, args.checkout, args.pull, git_exe)
    except NotImplementedError as err:
        print("Error (unimplemented behavior):", err)
        if args.dry_run: print("Dry run halted early due to error.")
        sys.exit(1)
    except RuntimeError as err:
        print("Error:", err)

_program_usage ="""putconf [options] SOURCE [FILES ...]"""
_program_description = """Install/sync user configuration files from a folder or git repository.

Files/directories in the toplevel of SOURCE are ignored if their names
begin with dots. However, if SOURCE contains a directory named "dotfiles",
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
    sync_opts.add_argument("-c",
                           "--commit",
                           help="Commit changes to SOURCE with the given message.",
                           metavar="MSG")
    sync_opts.add_argument("-P",
                           "--push",
                           action="store_true",
                           help="Push changes. Implied true when SOURCE is a remote repository. Requires -c.")
    sync_opts.add_argument("-a",
                           "--all",
                           action="store_true",
                           help="Act on all files in SOURCE in addition to specified FILES. Implied true when no FILES are specified.")

    # it's ok with me if parse_args errors out on an unrecognized option
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

    if args.dry_run:
        print("Dry run: No changes will be made to destination.")

    

if __name__ == "__main__":
    main()
