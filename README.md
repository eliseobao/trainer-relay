# TrainerRelay

**Use a Bluetooth trainer with an ANT+ cycling computer.**

TrainerRelay is a small Windows bridge for ERG workouts. It connects to a Bluetooth FTMS trainer, broadcasts an ANT+ FE-C trainer through a USB dongle, and relays power targets from your cycling computer. No account, cloud service, or workout library.

![TrainerRelay interface, displaying sample data](docs/interface.png)

```text
Cycling computer  ── ANT+ power target ──▶  TrainerRelay  ── Bluetooth ERG ──▶  Trainer
                 ◀── power and speed ──                 ◀── measurements ──
```

## Get started

Download the Windows x64 ZIP from [Releases](https://github.com/eliseobao/trainer-relay/releases). Extract the entire ZIP and open **TrainerRelay.exe**. Python is bundled; a compatible ANT USB driver must already be installed. The executable is unsigned.

1. Plug in your ANT+ dongle and wake the trainer. Close other apps using either device.
2. Click **Scan**, select your trainer, then **Start bridge**.
3. On your cycling computer, open its indoor-trainer pairing menu and select **53001**. Keep the computer near the USB dongle during pairing. See [device-specific setup](docs/compatibility.md#priority-tested-setup) for the D100 and Edge 530.
4. Start an indoor ERG workout on the cycling computer. TrainerRelay shows each accepted power target and the trainer's live readings.
5. Leave the app running and the laptop awake. Click **Stop** before unplugging the dongle.

The cycling computer should remember trainer **53001** for subsequent sessions. Start TrainerRelay each time you ride.

## What you need

| Component | Requirement | Tested |
| --- | --- | --- |
| Computer | Windows x64 with Bluetooth LE; release built with Python 3.13 | Windows 11 |
| Trainer | Bluetooth FTMS, Indoor Bike Data, target-power control | Van Rysel D100 |
| ANT dongle | USB ID `0fcf:1008` or `0fcf:1009`, libusb-win32 driver | ANT USB Stick 2 (`1008`) |
| Cycling computer | ANT+ FE-C trainer control | Garmin Edge 530 |

Other compatible hardware may work; it has not been verified. macOS, Linux, WinUSB-only dongles, and vendor-specific trainer protocols are outside this release's supported scope. See [compatibility](docs/compatibility.md) and [USB setup and troubleshooting](docs/troubleshooting.md).

## Deliberately a bridge

- Relays ERG targets within the trainer's reported range, capped at **600 W**. Out-of-range requests are rejected. A zero target asks the trainer to stop.
- Returns the trainer's measured power and speed. Cadence is forwarded only when present in FTMS data; the tested D100 did not provide it.
- Shows Bluetooth connection, ANT broadcasting, and received cycling-computer signals separately. Receiving a signal is not a persistent Garmin connection check.
- Does **not** implement slope, resistance, calibration, workout loading, recording, or PowerMatch. An external crank meter connected to the Edge remains independent; the trainer regulates ERG using its own measurement.

**Stop** asks the trainer to stop and releases both connections. If Bluetooth has already disconnected, delivery of the stop command cannot be guaranteed. Hardware errors require restarting the bridge. Do not run two copies against one dongle.

## Run from source

Install Python **3.13 x64** on Windows, then:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe bridge.py
```

[Development and architecture](docs/development.md) · [Build a release](docs/releasing.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

## Diagnostics

Click **Open logs**. Logs are stored under `%LOCALAPPDATA%\TrainerBridge\bridge.log`; the legacy folder name is retained for existing installations. **Copy error** copies the displayed error and app version. Logs can include Bluetooth device names and addresses; redact them before posting an issue.

Source-only commands:

```powershell
.\.venv\Scripts\python.exe bridge.py --version
.\.venv\Scripts\python.exe bridge.py --scan
.\.venv\Scripts\python.exe bridge.py --ant-test
.\.venv\Scripts\python.exe bridge.py --preview
```

`--ant-test` temporarily broadcasts a trainer without connecting Bluetooth, then closes the channel. `--preview` shows explicitly labelled sample UI data and never accesses hardware.

## Project status

Early release, **v0.1.0**. On the tested setup, the Edge paired and sent a 325 W target; the D100 acknowledged the target and start command, and the rider confirmed ERG operation. The USB lifecycle also passed three consecutive 15-second sessions (180 transmissions total) without physical reconnection. Automated tests cover wire formats, FTMS commands, connection recovery, UI states, and USB ownership. These checks do not certify other hardware.

## Related projects and references

[FortiusANT](https://github.com/WouterJD/FortiusANT) bridges older Tacx trainers and documents ANT setup in detail. [SmartTrainer UI](https://github.com/krishardy/smarttrainerui) demonstrates a focused BLE control interface with background I/O. [Open Ride](https://github.com/baktakt/open-ride-app) illustrates clear separation between transport selection and trainer control. TrainerRelay takes the narrower Bluetooth-trainer-to-ANT-computer direction. See [design notes](docs/related-projects.md).

Protocol references: [Bluetooth SIG FTMS](https://www.bluetooth.com/specifications/specs/fitness-machine-service-1-0/), [Garmin trainer communication](https://developer.garmin.com/tacx-trainer/), and [Edge 530 pairing instructions](https://www8.garmin.com/manuals/webhelp/edge530/EN-GB/GUID-4A11E0FF-E539-412E-B959-1E709CFF63A3.html).

MIT licensed. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md). Not affiliated with Garmin, Decathlon, Magene, or the related projects.
