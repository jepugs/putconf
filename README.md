# putconf

putconf is a nice way to install and synchronize config files.

To use putconf, you provide it a directory or git repository containing the
config files you want to install, and it puts them in your home folder (or
somewhere else of your choosing).

[![PyPI - Version](https://img.shields.io/pypi/v/putconf.svg)](https://pypi.org/project/putconf)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/putconf.svg)](https://pypi.org/project/putconf)

-----

**Table of Contents**

- [Installation](#installation)
- [Usage](#usage)
- [License](#license)

## Installation

putconf provides a script, so it is recommended to install it with pipx:

```console
pipx install putconf
```

If installed via pip, you will have to run putconf with `python -m putconf`.

## Usage

To use putconf, you need to provide a source, which may be either a local
directory or a git repository. For the most part, putconf will simply copy the
files in the specified directory into the target directory, which defaults to
the current value of `${HOME}`.

putconf can either install config files from a source or update the source with
config files pulled from another location. The latter is referred to as
synchronization.

Example:
```console
# install from a local directory (to $HOME)
putconf Documents/config-files
# install from git (to $HOME)
putconf ssh://git@github.com:jepugs/my-home-folder

# update all config files in a local source with files (from $HOME)
putconf -S Documents/config-files
# update/add specific config files to a local source (from $HOME)
putconf -S Documents/config-files .bashrc .config/emacs/init.el
```

Run `putconf -h` to see additional options.

### Source Directory Layout

Files in the top level of the source beginning with dots are normally ignored,
but they may contain a toplevel directory named ".dotfiles". Files in this
directory are treated as if they reside in the toplevel themselves, but with a
dot character `.` prepended to their names. E.g. `.dotfiles/bashrc` will be
installed with the name `.bashrc`.

Synchronization operations are aware of how the dotfiles folder should work.

### Known Deficiencies

- putconf does not process .gitignore files
- putconf scans over directories manually in python, so if you accidentally give
  it a ton of files, it may take a long time
  - in particular, if your config directory contains another git repository
    (like with submodules), then the whole .git directory in the subrepository
    will be copied
  - this also goes for synchronization, since specifying a directory in the
    target will cause that whole directory to be scanned
- files are checked for existence before any modifications are made, but the
  program may exit after an incomplete install/sync operation if it encounters a
  permission error
  
### Things It Would Be Nice to Add

This is not a promise, but here are a couple of things I may or may not add in
the future:

- Unix-style globs in the FILES list
- basic facilities to generate config files from scripts in the source
- caching git repositories so we don't have to clone the whole thing each time
- fixes for the above mentioned deficiencies

## License

`putconf` is distributed under the terms of the [GPL](https://spdx.org/licenses/GPL-3.0-or-later.html) license.
