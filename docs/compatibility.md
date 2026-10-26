# Compatibility

TrainerRelay runs on Windows x64 with Bluetooth LE. The packaged release uses Python 3.13. Development tests may run elsewhere, but the radio implementation is Windows-specific.

## Priority tested setup

The **Van Rysel D100 + Garmin Edge 530** is the priority setup for testing and regressions. The app uses standard FTMS and FE-C protocols, without locking the interface to these device names.

For the Edge 530, use **Menu → Training → Indoor Trainer → Pair ANT+ Bike Trainer**, choose **53001**, then **Add Sensor**. Keep the Edge close to the ANT USB dongle while pairing.

## Bluetooth trainer

Required FTMS service `1826`, Indoor Bike Data `2AD2`, Fitness Machine Feature `2ACC`, and Control Point `2AD9`. The trainer must advertise target-power support and accept Request Control, Set Target Power, and Start. Supported Power Range `2AD8` is read when present; accepted targets are capped at 600 W.

The tested Van Rysel D100 reports 50–600 W in 1 W steps. Cadence was absent from its captured FTMS data. The bridge never invents cadence or substitutes an external meter. Additional trainer models are unverified.

## ANT

Supported dongles are USB IDs `0fcf:1008` and `0fcf:1009`, opened through Windows `libusb0.dll` and the libusb-win32 driver. ANT USB Stick 2 (`1008`) was verified. Other IDs and WinUSB drivers need implementation work, not just a different dropdown selection.

The bridge broadcasts device type 17 (fitness equipment), device ID 53001, period 8192 (4 Hz), RF channel 57 (2457 MHz). Device ID 53001 is the emulated trainer, not the Garmin's serial number. Avoid using two nearby copies with this fixed identity.

Implemented FE-C pages: 16/25 telemetry, 49 target power, 54 capabilities, 71 command status, 80/81 identity, and page-70 requests for these common pages. Recognised but unimplemented control modes return unsupported status. No slope, resistance, calibration, or full-workout transfer.

Garmin Edge 530 is tested. Other ANT+ FE-C cycling computers may work. Basic ANT+ power-sensor support alone is insufficient for trainer control.

## External power meters

A crank or pedal meter connected directly to the Edge is separate from TrainerRelay. Displayed or recorded Edge readings may therefore differ from the trainer readings shown in the app. ERG uses the trainer's own measurement; there is no PowerMatch loop.
