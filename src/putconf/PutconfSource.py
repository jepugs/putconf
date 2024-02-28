from enum import Enum
import itertools
import re
import shutil
import subprocess
import tempfile
import typing
import os

class OverwriteMode(Enum):
    PROMPT = 1
    ALL = 2
    NONE = 3

def _prepend_dot(path):
    return "." + str(path)

def _git_pull(git_exe, repo_dir):
    pull_proc = subprocess.run([git_exe, "-C", repo_dir, "pull"])
    if pull_proc.returncode != 0:
        raise RuntimeError("Git pull failed with code %i.", pull_proc.returncode)

def _do_mkdir(path, verbose=False, dry_run=False):
    if os.path.exists(path):
        if verbose:
            print("Directory already exists: %s" % path)
    else:
        if verbose:
            print("Create directory: %s" % path)
        if not dry_run:
            try: os.mkdir(path)
            except: raise RuntimeError("Failed to create directory: %s" % path)

def _do_copy(src, dest, verbose=False, dry_run=False, overwrite=False):
    if verbose:
        print("%s file: %s" % (("Overwrite" if overwrite else "Create"), dest))
    if not dry_run:
        try: shutil.copy(src, dest)
        except: raise RuntimeError("Failed to overwrite file: %s" % dest)

def _prompt_to_overwrite(src, dest, verbose=False, dry_run=False):
    ow = False
    res = OverwriteMode.PROMPT
    if verbose:
        print("Prompt to overwrite file: %s" % dest)
    if dry_run:
        return res
    while True:
        s = input("Overwrite file %s? (y)es/(n)o/all/none: " % dest)
        if s == "y":
            ow = True
            break
        elif s == "n":
            ow = False
            break
        elif s == "all":
            ow = True
            res = OverwriteMode.ALL
            break
        elif s == "none":
            ow = False
            res = OverwriteMode.NONE
            break
        else:
            print("Please answer y/n/all/none.")
    if ow:
        _do_copy(src, dest, verbose, False)
    elif verbose:
        print("Don't overwrite: %s" % dest)
    return res


def _scan_dir(dir_path, rel_to):
    """Recursively scan a directory, returning two lists of paths: one for all
    files, and one for all subdirectories. The subdirectories are ordered so
    that parent directories always precede their children. Returned paths are
    given relative to rel_to, and dir_path must also be a relative path taken
    relative to rel_to.
    """
    subdirs = []
    files = []
    for x in os.scandir(os.path.join(rel_to, dir_path)):
        if x.is_dir():
            subdirs.append(os.path.join(dir_path, x.name))
        else:
            files.append(os.path.join(dir_path, x.name))

    i = 0
    while i < len(subdirs):
        d = subdirs[i]
        base = os.path.join(rel_to, d)
        i += 1
        for x in os.scandir(base):
            if x.is_dir():
                subdirs.append(os.path.join(d, x.name))
            else:
                files.append(os.path.join(d, x.name))

    return files, subdirs


class PutconfSource:
    tmp : typing.Union[tempfile.TemporaryDirectory, None]
    """Temporary directory, if applicable."""
    work_dir : str
    """Path used to store this directory."""
    is_remote : bool
    """Whether this source was fetched from a remote repository."""
    src_files : list
    """List of tuples (from,to), where from is absolute path to a file in source
    and to is the corresponding relative path in target. Contains all files that
    that should be installed during a put, or overwritten by a sync, except for
    those contained in explicit_subdirs."""
    put_subdirs : list
    """Relative paths of directories that should be created during a put,
    excluding the ones in explicit_subdirs."""
    explicit_subdirs : list
    """List of subdirectories relative to target that are explicitly named in a
    provied file list."""
    sync_new : list
    """Like files, but contains paths from a provided file_list which do not yet
    exist in source. Since these do not exist, they may possibly correspond to
    directories to be installed during sync operations."""
    has_explicit_files : bool
    """Whether a file list was provided. This affects error generation during
    sync operations."""

    def __init__(self,
                 path : str,
                 is_remote : bool,
                 file_list : list[str],
                 gitref : typing.Optional[str] = None,
                 pull : bool = False,
                 git_exe : typing.Optional[str] = None):
        """file_list can only contain paths relative to target, so some processing
        has to be done to the FILES argument before this method gets called.
        """

        self.is_remote = is_remote

        # get source directory ready
        if is_remote or gitref:   # clone repo
            if git_exe is None:
                raise RuntimeError("Git not found.")
            try:
                self.tmp = tempfile.TemporaryDirectory("__putconf-source")
                self.work_dir = self.tmp.name
            except: raise RuntimeError("Couldn't create temporay directory for source.")

            # TODO: decide whether it's worth adding --shared for local repos
            clone_args = [git_exe, "clone", path, self.work_dir]
            clone_proc = subprocess.run(clone_args)
            if clone_proc.returncode != 0:
                raise RuntimeError("Git clone failed with code %i." % clone_proc.returncode)

            # pull is ignored for remote repos
            if pull and not is_remote == "file": _git_pull(git_exe, self.work_dir)

            if gitref:   # perform checkout
                ck_proc = subprocess.run([git_exe, "-C", self.work_dir, "checkout", gitref])
                if ck_proc.returncode != 0:
                    raise RuntimeError("Git checkout failed with code %i." % ck_proc.returncode)

        else:  # proto=="file", no --checkout, don't clone
            if not os.path.exists(path):
                raise RuntimeError("Source path does not exist.")
            elif not os.path.isdir(path):
                raise RuntimeError("Source path does not name a directory.")
            elif not os.access(path, os.R_OK):
                raise RuntimeError("Source path not readable.")
            self.tmp = None
            self.work_dir = path
            if pull:
                if git_exe is None:
                    raise RuntimeError("Git not found.")
                _git_pull(git_exe, self.work_dir)

        # scan files
        try: self._scan_contents(file_list)
        except Exception as e: RuntimeError("Error scanning source: %s" % e)

    def _scan_contents(self, file_list):
        if len(file_list) == 0:
            self.has_explicit_files = False
            self._scan_all()
        else:
            self.has_explicit_files = True
            self._scan_from_list(file_list)

    def _scan_from_list(self, file_list):
        # note that file_list contains relative paths only, which must be
        # assured by the program before instances of this class are constructed
        self.src_files = []
        self.put_subdirs = []
        self.explicit_subdirs = []
        self.sync_new = []

        undot_list = []
        dot_list = []
        subdir_set = set()
        src = self.work_dir
        for x in file_list:
            src_path = ""
            if x.startswith("."):
                dot_list.append(x[1:])
                src_path = os.path.join(src, ".dotfiles", x[1:])
            else:
                undot_list.append(x)
                src_path = os.path.join(src, x)
            # add parent directories to put_subdirs as necessary
            d = os.path.dirname(x)
            parents = []
            while len(d) > 0 and d not in subdir_set:
                subdir_set.add(d)
                parents.append(d)
                d = os.path.dirname(d)
            for p in reversed(parents):
                self.put_subdirs.append(p)

            if os.path.isdir(src_path): # is directory in src
                self.explicit_subdirs.append(x)
            elif os.path.exists(src_path): # is file in src
                self.src_files.append((src_path, x))
            else: # not in src
                # FIXME: in this case it doen't make sense to append parent
                # directories to put_subdirs
                self.sync_new.append((src_path, x))

    def _scan_all(self):
        """Scan work_dir for config files and directories, and compute the
        corresponding relative paths in the putconf target."""

        self.sync_new = []
        self.explicit_subdirs = []

        # scan the top directory,
        self.src_files = []
        src = self.work_dir
        subdirs = []
        dotfile_dir = None
        for x in os.scandir(src):
            if x.is_dir() and x.name == ".dotfiles":
                dotfile_dir = x.path
            elif not x.name.startswith("."):
                if x.is_dir():
                    subdirs.append(x.name)
                else:
                    self.src_files.append((x.path, x.name))

        self.put_subdirs = subdirs.copy()
        for x in subdirs:
            fs, ds = _scan_dir(x, src)
            self.src_files.extend([(os.path.join(src, f), f) for f in fs])
            self.put_subdirs.extend(ds)

        if dotfile_dir:
            fs, ds = _scan_dir("", dotfile_dir)
            self.src_files.extend([(os.path.join(dotfile_dir, f), _prepend_dot(f))
                                   for f in fs])
            self.put_subdirs.extend([_prepend_dot(d) for d in ds])

    def install_to_target(self, target : str, verbose : bool, dry_run : bool,
                          overwrite : OverwriteMode):
        """Copy config files to target."""
        # scan all explicit subdirs first
        extra_dirs = []
        extra_files = []
        for x in self.explicit_subdirs:
            extra_dirs.append(x)
            in_src = self._path_in_src(x)
            fs, ds = _scan_dir("", in_src)
            extra_files.extend([(os.path.join(in_src, f),os.path.join(x,f))
                                for f in fs])
            extra_dirs.extend([os.path.join(x, d) for d in ds])

        # create directories in target
        for d in itertools.chain(self.put_subdirs, extra_dirs):
            abs_path = os.path.join(target, d)
            _do_mkdir(abs_path, verbose, dry_run)

        # copy files to target
        for src_path, rel in itertools.chain(self.src_files, extra_files):
            abs_path = os.path.join(target, rel)
            if os.path.isdir(abs_path):
                raise RuntimeError("%s exists and is a directory." % abs_path)
            elif os.path.exists(abs_path):
                match overwrite:
                    case OverwriteMode.PROMPT:
                        overwrite = _prompt_to_overwrite(src_path, abs_path, verbose, dry_run)
                    case OverwriteMode.ALL:
                        _do_copy(src_path, abs_path, verbose, dry_run, True)
                    case OverwriteMode.NONE:
                        if verbose or dry_run:
                            print("Don't overwrite: %s" % abs_path)
                        # do nothing
                        ...
            else:
                _do_copy(src_path, abs_path, verbose, dry_run)

    def _path_in_src(self, rel_to_target : str):
        if rel_to_target.startswith(""):
            return os.path.join(self.work_dir, ".dotfiles", rel_to_target[1:])
        else:
            return os.path.join(self.work_dir, rel_to_target)

    def sync_from_target(self, target : str, verbose : bool, dry_run : bool):
        extra_files = [] # like self.src_files

        # ensure existence, add extra_files, make directories
        if self.has_explicit_files:
            # Steps:
            # - scan entries of sync_new and explicit_subdirs in target
            #   - raise errors when they don't exist
            #   - make list of directories to create
            # - scan src_files and raise errors on missing files in target
            # - create new directories
            extra_dirs = [] # note: paths relative to target
            extra_files = [] # like self.src_files
            subdir_set = set() # ensure directories are just created once
            # scan sync_new
            for in_src, rel in self.sync_new:
                # append parent directories as necessary
                d = os.path.dirname(rel)
                parents = []
                while len(d) > 0 and d not in subdir_set:
                    subdir_set.add(d)
                    parents.append(d)
                    d = os.path.dirname(d)
                for p in reversed(parents):
                    extra_dirs.append(p)
                # handle the file/directory
                in_target = os.path.join(target, rel)
                if os.path.isdir(in_target):
                    # scan directory
                    if rel not in subdir_set:
                        extra_dirs.append(rel)
                    fs, ds = _scan_dir(rel, target)
                    extra_dirs.extend(ds)
                    extra_files.extend([(self._path_in_src(f), f)
                                        for f in fs])
                elif os.path.exists(in_target):
                    # add file
                    extra_files.append((in_src, rel))
                else:
                    raise RuntimeError("%s does not exist." % in_target)
            for rel in self.explicit_subdirs:
                in_target = os.path.join(target, rel)
                if os.path.isdir(in_target):
                    if rel not in subdir_set:
                        extra_dirs.append(rel)
                    fs, ds = _scan_dir(rel, target)
                    extra_dirs.extend(ds)
                    extra_files.extend([(self._path_in_src(f), f)
                                        for f in fs])
                else:
                    raise RuntimeError("%s is not a directory." % in_target)

            # make directories
            dotfile_dir = os.path.join(self.work_dir, ".dotfiles")
            if not os.path.isdir(dotfile_dir):
                _do_mkdir(dotfile_dir, verbose, dry_run)
            for x in extra_dirs:
                _do_mkdir(self._path_in_src(x), verbose, dry_run)

        # sync files
        for in_src, rel in itertools.chain(extra_files, self.src_files):
            in_target = os.path.join(target, rel)
            if os.path.isdir(in_target):
                raise RuntimeError("%s is a directory." % in_target)
            elif os.path.exists(in_target):
                overwrite = os.path.exists(in_src)
                _do_copy(in_target, in_src, verbose, dry_run, overwrite)
            elif self.has_explicit_files:
                # explicitly named files must exist
                # FIXME: this might be unexpected when using the --all flag
                raise RuntimeError("%s does not exist." % in_target)
            elif verbose:
                print("Don't overwrite: %s (no file in target)" % in_src)
