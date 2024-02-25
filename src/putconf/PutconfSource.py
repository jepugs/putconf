from enum import Enum
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

def _decomp_source(source_str):
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

def _git_pull(git_exe, repo_dir):
    pull_proc = subprocess.run([git_exe, "-C", repo_dir, "pull"])
    if pull_proc.returncode != 0:
        raise RuntimeError("Git pull failed with code %i.", pull_proc.returncode)

def _do_cpdir(path, verbose=False, dry_run=False):
    if verbose:
        print("Create directory: %s" % path)
    if not dry_run:
        try: os.mkdir(path)
        except: raise RuntimeError("Failed to create directory %s." % path)


def _do_mkdir(path, verbose=False, dry_run=False):
    if verbose:
        print("Create directory: %s" % path)
    if not dry_run:
        try: os.mkdir(path)
        except: raise RuntimeError("Failed to create directory %s." % path)

def _do_copy(src, dest, verbose=False, dry_run=False, overwrite=False):
    if verbose:
        print("%s file: %s" % ("Overwrite" if overwrite else "Create", dest))
    if not dry_run:
        try: shutil.copy(src, dest)
        except: raise RuntimeError("Failed to overwrite file: %s" % dest)

def _prompt_to_overwrite(src, dest, dry_run=False, verbose=False):
    ow = False
    res = OverwriteMode.PROMPT
    if verbose:
        print("Prompt to overwrite file: %s" % dest)
    if dry_run:
        return res

    while not dry_run:
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
        _do_copy(src, dest, verbose, dry_run)
    elif verbose:
        print("Don't overwrite: %s" % dest)
    return res



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
    that should be installed during a put, or overwritten by a sync."""
    put_subdirs : list
    """Relative paths of directories that should be created during a put."""
    sync_subdirs : list
    """List of subdirectories that should be updated during a sync, represented
    by their relative paths in target."""
    sync_new : list
    """Like files, but contains paths from a provided file_list which do not yet
    exist in source. Since these do not exist, they may possibly correspond to
    directories to be installed during sync operations."""

    def __init__(self,
                 source_str : str,
                 file_list : list[str],
                 gitref : typing.Optional[str] = None,
                 pull : bool = False,
                 git_exe : typing.Optional[str] = None):
        """file_list can only contain paths relative to target, so some processing
        has to be done to the FILES argument before this method gets called.
        """
        proto, path = _decomp_source(source_str)

        # check transport
        self.is_remote = proto in ["http", "https", "ssh", "git"]
        if not (self.is_remote or proto == "file"):
            raise RuntimeError("Unsupported transport %s." % proto)

        # get source directory ready
        if self.is_remote or gitref:   # clone repo
            if git_exe is None:
                raise RuntimeError("Git not found.")
            try:
                self.tmp = tempfile.TemporaryDirectory("__putconf-source")
                self.work_dir = self.tmp.name
            except: raise RuntimeError("Couldn't create temporay directory for source.")

            # TODO: decide whether it's worth adding --shared for local repos
            clone_args = [git_exe, "clone", source_str, self.work_dir]
            clone_proc = subprocess.run(clone_args)
            if clone_proc.returncode != 0:
                raise RuntimeError("Git clone failed with code %i." % clone_proc.returncode)

            # pull is ignored for remote repos
            if pull and proto == "file": _git_pull(git_exe, self.work_dir)

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
            self._scan_all()
        else:
            self._scan_from_list(file_list)

    def _scan_from_list(self, file_list):
        # note that file_list contains relative paths only, which must be
        # assured by the program before instances of this class are constructed
        self.src_files = []
        self.put_subdirs = []
        self.sync_subdirs = []
        self.new_files = []

        src = self.work_dir
        subdir_set = set() # don't add the same directory twice
        subdirs = []
        dot_subdirs = []
        for x in file_list:
            abs_path = ""
            dot = False
            if x.startswith("."):
                abs_path = os.path.join(src, "dotfiles", x[1:])
                dot = True
            else:
                abs_path = os.path.join(src, x)

            # add parent directories
            d = os.path.dirname(x)
            dirs = []
            while len(d) > 0 and d not in subdir_set:
                dirs.append(d)
                subdir_set.add(d)
                d = os.path.dirname(d)
            for y in reversed(dirs): self.put_subdirs.append(y)

            if os.path.isdir(abs_path):
                # existing directory
                if dot:
                    dot_subdirs.append(x[1:])
                else:
                    subdirs.append(x)
                self.sync_subdirs.append(x)
                # we can add this now that all parent directories are added
                self.put_subdirs.append(x)
            elif os.path.exists(abs_path):
                # existing file
                self.src_files.append((abs_path, x))
            else:
                # file or directory that doesn't exist in source
                self.sync_new.append((abs_path, x))

        # last step is to scan the subdirs within src
        i = 0
        while i < len(subdirs):
            d = subdirs[i]
            i += 1
            for x in os.scandir(os.path.join(src, d)):
                if x.is_dir():
                    subdirs.append(x)
                    self.put_subdirs.append(os.path.join(d, x.name))
                else:
                    self.src_files.append((x.path, os.path.join(d, x.name)))
        i = 0
        while i < len(dot_subdirs):
            d = dot_subdirs[i]
            i += 1
            for x in os.scandir(os.path.join(src, "dotfiles", d)):
                if x.is_dir():
                    dot_subdirs.append(x)
                    self.put_subdirs.append(_prepend_dot(os.path.join(d, x.name)))
                else:
                    self.src_files.append((x.path, _prepend_dot(os.path.join(d, x.name))))
                    

    def _scan_all(self):
        """Scan work_dir for config files and directories, and compute the
        corresponding relative paths in the putconf target."""

        self.sync_subdirs = []
        self.sync_new = []

        # scan the top directory,
        self.src_files = []
        src = self.work_dir
        subdirs = []
        dotfile_dir = None
        for x in os.scandir(src):
            if x.is_dir() and x.name == "dotfiles":
                dotfile_dir = x.path
            elif x.is_dir():
                if x.name != ".git":
                    subdirs.append(x.name)
            elif not x.name.startswith('.'):
                self.src_files.append((x.path, x.name))

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
                    self.src_files.append((os.path.join(src, rel), rel))

        res_subdirs = subdirs

        # scan dotfiles
        if dotfile_dir:
            dot_subdirs = []
            for x in os.scandir(dotfile_dir):
                if x.is_dir():
                    dot_subdirs.append(x.name)
                else:
                    self.src_files.append((x.path, _prepend_dot(x.name)))
            i = 0
            while i < len(dot_subdirs):
                d = dot_subdirs[i]
                i += 1
                for x in os.scandir(os.path.join(dotfile_dir, d)):
                    rel = os.path.join(d, x.name)
                    if x.is_dir():
                        dot_subdirs.append(rel)
                    else:
                        self.src_files.append((x.path, _prepend_dot(rel)))

            for d in dot_subdirs:
                res_subdirs.append(_prepend_dot(d))

        self.put_subdirs = res_subdirs
        self.sync_subdirs = []
        self.sync_new = []

    def install_to_target(self, target : str, verbose : bool, dry_run : bool,
                          overwrite : OverwriteMode):
        """Copy config files to target."""
        for d in self.subdirs:
            abs_path = os.path.join(target, d)
            _do_mkdir(abs_path, verbose, dry_run)
        for src_path, p in self.files:
            abs_path = os.path.join(target, p)
            if os.path.isdir(abs_path):
                raise RuntimeError("%s exists and is a directory." % abs_path)
            elif os.path.exists(abs_path):
                match overwrite:
                    case OverwriteMode.PROMPT:
                        if not dry_run:
                            overwrite = _prompt_to_overwrite(src_path, abs_path, dry_run, verbose)
                    case OverwriteMode.ALL:
                        _do_copy(src_path, abs_path, verbose)
                    case OverwriteMode.NONE:
                        if verbose or dry_run:
                            print("Leave file: %s" % abs_path)
                        # do nothing
                        ...
            else:
                _do_copy(src_path, target)

    def sync_from_target(self, target : str, verbose : bool, dry_run : bool):
        # first, ensure that the non_files all exist
        non_dirs = []
        # unlike non_files, this will contain absolute paths in dest
        true_non_files = []
        for in_src, p in self.non_files:
            abs_path = os.path.join(target, p)
            if os.path.isdir(abs_path):
                non_dirs.append(in_src)
            elif os.path.exists(abs_path):
                true_non_files.append((in_src, abs_path))
            else:
                raise RuntimeError("File %s does not exist." % abs_path)

        # overwrite existing files
        for in_src, p in self.files:
            abs_path = os.path.join(target, p)
            if os.path.isdir(abs_path):
                raise RuntimeError("%s is a directory, but %s is a file." % (abs_path, in_src))
            else:
                _do_copy(abs_path, in_src, verbose, dry_run)

        # create the necessary directories
        for d in non_dirs:
            _do_cpdir(d, verbose, dry_run)

        # copy nonexistent
        for in_src, abs_path in true_non_files:
            _do_copy(abs_path, in_src, verbose, dry_run)


