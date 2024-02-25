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

For convenience, the source may contain a toplevel directory named "dotfiles".
Files in this directory are treated as if they reside in the toplevel
themselves, but with a dot character `.` prepended to their names. E.g.
`dotfiles/bashrc` will be installed with the name `.bashrc`.

Example:
```console
# install from git
putconf ssh://git@github.com:jepugs/my-home-folder
# install from a local directory
putconf Documents/config-files
```

Run `putconf -h` to see additional options.


## License

`putconf` is distributed under the terms of the [GPL](https://spdx.org/licenses/GPL-3.0-or-later.html) license.
