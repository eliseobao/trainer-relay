# Development & releases

[← Back to the README](../README.md)

## Run from source

Use **Python 3.13 x64** on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe bridge.py
```

For a hardware-free look at the window, use `bridge.py --preview`. Other source-only diagnostics are `--version`, `--scan`, and `--ant-test`. The ANT test briefly broadcasts a trainer, then releases the stick; close other bridge instances first.

## Check a change

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m unittest discover -v
```

The tests use fake trainer responses and do not send real brake commands. GUI tests need Tk and a display; they run on Windows CI and skip on headless Linux. Radio changes also need a physical check with the priority **D100 + Edge 530** setup. For control changes, test multiple values, mode transitions, Stop, reconnect, and telemetry on the cycling computer.

## A quick tour

| File | Responsibility |
| --- | --- |
| `protocol.py` | FTMS data parsing, FE-C frames/pages, and decoded control requests |
| `bridge.py` | Bluetooth control, USB ownership, and command routing |
| `interface.py` | The small Tk window and its event queue |
| `app_info.py` | App name, version, trainer ID, and power cap |
| `test_*.py` | Protocol, command, recovery, and interface checks |
| `scripts/` | Packaging, screenshots, icons, and dependency notices |

Radio work runs outside Tk's thread. All libusb-win32 operations share one owning thread. FTMS writes are serialized and wait for their response. The app reports FE-C success only after the trainer accepts the control; timeouts stop the bridge rather than letting later responses be mistaken for new commands.

### Control translation

| FE-C page | Bluetooth control |
| --- | --- |
| 48: basic resistance | FTMS `0x04`; percentage mapped onto `2AD6` native range |
| 49: power | FTMS `0x05`; trainer's range, capped at 600 W |
| 50: wind | Cache wind/drag; apply FTMS `0x11` if already simulating |
| 51: track resistance | FTMS `0x11`; merge grade/rolling resistance |

ANT wind speed is converted from km/h to m/s, and drafting scales the wind coefficient. Missing grade preserves the current grade. Values that cannot fit FTMS are rejected. Active simulation settings are committed after trainer acceptance. Wind-only or grade-less road configuration outside simulation is saved locally for the next valid grade target and acknowledged as configuration, without changing the trainer mode. Page 55 user configuration has no implemented Bluetooth mapping.

FE-C page 54 advertises only the controls available from the connected trainer. Pages 16/25 carry telemetry, 71 reports command status, and 80/81 identify the bridge. The fixed trainer ID is **53001**; avoid two nearby instances with the same identity.

## Build a Windows ZIP

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
```

This checks the code, runs tests, builds `dist/TrainerRelay.exe`, and creates a versioned ZIP plus `SHA256SUMS.txt` under `release/`. The ZIP includes user docs, the app license, and full third-party license notices. Python is bundled; the ANT driver is not. No signing certificate is configured.

To release, update `app_info.VERSION` and `CHANGELOG.md`, check the local build, then push a matching tag such as `v0.2.0-rc.1`. The single Windows workflow checks and packages the tagged commit, then publishes a prerelease with the ZIP and checksum. It never runs a hardware test. Keep preview labels when physical verification is pending.

## References worth reading

[SmartTrainer UI](https://github.com/krishardy/smarttrainerui) keeps trainer controls and async I/O straightforward. [SHIFTR](https://github.com/JuergenLeber/SHIFTR) explains its bridge and tested setups clearly. [FortiusANT](https://github.com/WouterJD/FortiusANT) is a useful FE-C and USB reference. TrainerRelay stays narrower: let the cycling computer run the ride.

Protocol sources: [Bluetooth SIG FTMS test suite](https://files.bluetooth.com/wp-content/uploads/dlm_uploads/2024/10/FTMS.TS_.p6.pdf), [Garmin trainer communication](https://developer.garmin.com/tacx-trainer/), and [Edge 530 pairing](https://www8.garmin.com/manuals/webhelp/edge530/EN-GB/GUID-4A11E0FF-E539-412E-B959-1E709CFF63A3.html).
