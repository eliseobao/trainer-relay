# Development

Use Python 3.13 x64 and Windows for builds and hardware tests:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe bridge.py
```

The GUI tests need a display and Tk. They run on the Windows CI runner. On Linux without a display they skip; protocol tests still run. `bridge.py --preview` opens a labelled sample UI and never uses hardware.

## Layout

- `bridge.py`: FTMS client, ANT driver/session, and orchestration. CLI and GUI entry point.
- `protocol.py`: FTMS parsing and FE-C frame/page encoding, with no radio dependencies.
- `interface.py`: Tk widgets and event queue. Workers never update widgets directly.
- `app_info.py`: app name, release version, broadcast trainer ID, and power cap.
- `test_*.py`: protocol, command, lifecycle, and interface tests.
- `scripts/`: build and dependency-notice generation.
- `.github/workflows/`: checks, Windows artifact build, and prereleases on version tags.

The GUI launches an asyncio worker for scan/bridge operations. `AntSession` owns a dedicated one-thread executor so all libusb-win32 operations happen on one thread. FTMS commands are serialized and require control-point indications. FE-C status reports success only after the trainer accepts the command. Radio reception/transmission and command acknowledgements are distinct from UI status.

## Hardware verification

1. Run `bridge.py --ant-test` with no other bridge instance open. Confirm transmission events and clean exit.
2. Run the app, connect the trainer, and pair 53001 from the cycling computer's trainer-control menu.
3. Send two distinct in-range ERG targets and verify the ANT receive logs, FTMS success responses, changed trainer resistance, and telemetry on the cycling computer.
4. Stop and reconnect; check release/reopen of the dongle and trainer. Exercise unplugging the USB stick and losing Bluetooth.

Mocks and green CI do not replace these checks. Do not send real power commands from automated CI. The first release retains the radio implementation tested with the D100 and Edge; UI changes are verified separately.
