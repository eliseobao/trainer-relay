# Changelog

## 0.1.0 — initial prerelease

- Bridge Bluetooth FTMS ERG trainers to ANT+ FE-C cycling computers on Windows.
- Display accepted ERG target, trainer power, speed, and optional cadence.
- Show separate Bluetooth, ANT broadcasting, and cycling-computer signal status.
- Provide scan, start, stop, log-folder access, and copyable errors.
- Retry the specific Windows closed-GATT-object discovery error.
- Keep USB operations on one thread and close the ANT channel before releasing it.
- Package a standalone Windows executable, documentation, dependency notices, and SHA-256 checksums.

Known limits: ERG only; 600 W cap; fixed trainer ID 53001; only libusb-win32 ANT drivers supported. The Garmin does not send full workout plans to the bridge.
