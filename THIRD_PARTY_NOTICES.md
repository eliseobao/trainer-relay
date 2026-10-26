# Third-party notices

TrainerRelay's own code is MIT licensed. The Windows executable includes Python, Tcl/Tk, Bleak, PyUSB, WinRT bindings and runtime, and their dependencies. PyInstaller supplies the executable bootloader and packaging runtime hooks under its distribution terms and bootloader exception.

The release build generates `THIRD_PARTY_NOTICES.txt` from the installed distributions' license files and metadata, plus the Python and Tcl/Tk licenses. It is included alongside the executable in every release ZIP. This avoids replacing bundled license texts with a bare list of links.

Primary upstreams:

- [Python](https://www.python.org/), PSF license and included notices.
- [Tcl/Tk](https://www.tcl.tk/), licenses included with the runtime.
- [Bleak](https://github.com/hbldh/bleak), MIT.
- [PyUSB](https://github.com/pyusb/pyusb), BSD-3-Clause.
- [PyWinRT](https://github.com/pywinrt/pywinrt), MIT.
- [PyInstaller](https://github.com/pyinstaller/pyinstaller), GPL with its bootloader exception.

The ANT USB driver is an external prerequisite, not distributed with this app. FortiusANT and other related projects were consulted as references; their source files are not bundled here. See [related projects](docs/related-projects.md).
