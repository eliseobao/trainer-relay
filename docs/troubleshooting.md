# Setup and troubleshooting

## ANT USB driver

TrainerRelay currently needs **libusb-win32**, including `libusb0.dll`, for the supported ANT stick. Check the device in Windows Device Manager. The tested setup listed **ANT USB Stick 2** under **libusb-win32 devices**.

If you already have that driver, leave it in place. If not, [FortiusANT's Windows setup documentation](https://github.com/WouterJD/FortiusANT) is a useful ANT-driver reference; a tool such as [Zadig](https://zadig.akeo.ie/) can install libusb-win32 for the **ANT dongle**. Record the current driver first so you can restore it. Select only the ANT device: do not replace the laptop's Bluetooth driver. WinUSB is not this app's supported backend, and changing the ANT driver can affect other ANT applications.

## Trainer missing from Scan

Wake the trainer and close Zwift, training apps, and other copies of TrainerRelay. The D100 may stop advertising while connected. If a previous connection ended abruptly, power-cycle the trainer and rescan. The app scans for 10 seconds and shows FTMS advertisements plus recognised D100/Magene names; service support is verified when connecting.

## USB timeout or stick not found

Stop the bridge, close other apps using ANT (including Garmin Express), unplug and reconnect the ANT stick, and retry. Some libusb-win32 failures require a physical reconnection; a software reset may not clear them. The app confines USB work to one thread and releases resources on shutdown, but cannot guarantee recovery from a failed driver.

## Windows “object closed” Bluetooth error

The app requests only the fitness service without the OS service cache and retries this specific discovery error twice. If it persists, close other trainer connections, power-cycle the trainer, and scan again. Other Bluetooth errors are surfaced rather than hidden by endless retries.

## Trainer missing on Edge 530

With the bridge running, use **Menu → Training → Indoor Trainer → Pair ANT+ Bike Trainer**. Look for **53001**, then choose **Add Sensor**. Keep the Garmin near the laptop's USB dongle while searching. A normal power-meter search is a different path. [Garmin's instructions](https://www8.garmin.com/manuals/webhelp/edge530/EN-GB/GUID-4A11E0FF-E539-412E-B959-1E709CFF63A3.html).

## Cadence shows a dash

The trainer may not include cadence in its FTMS messages. A dash means unavailable, not zero. Cadence visible on the Edge can instead come from a crank meter paired directly to it. Measurements older than five seconds disappear from the app and are sent as unavailable over ANT.

## Target rejected / power doesn't match

Use ERG targets in the trainer's supported range, no higher than 600 W. The tested D100 supports 50–600 W; zero sends Stop. Slope and resistance commands are unsupported. The ERG target is a requested value; trainer power is a measurement. A separate crank meter is not used to correct trainer resistance.

## Reporting a problem

Use **Copy error** and **Open logs**. Include the app version, Windows version, trainer model, dongle ID/driver, and reproduction steps. Logs under `%LOCALAPPDATA%\TrainerBridge` rotate at 2 MB with three backups. They include nearby Bluetooth names and addresses; redact those before sharing. An ANT signal indicator records received messages; it does not prove the Garmin remains connected indefinitely.
