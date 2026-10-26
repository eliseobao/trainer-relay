# Riding with TrainerRelay

[← Back to the README](../README.md)

## Before the first ride

TrainerRelay is made for Windows x64 with Bluetooth LE. It connects to Bluetooth **FTMS** trainers and broadcasts an **ANT+ FE-C** trainer through a USB stick. Both protocols need trainer-control support; power-sensor support alone is not enough.

The priority setup is a **Van Rysel D100**, **Garmin Edge 530**, and **ANT USB Stick 2**. ERG has been tested on this setup. Slope and resistance in the 0.2 preview still need a physical test. Other standards-compatible devices may work, but have not been verified.

### The ANT stick

The supported USB IDs are `0fcf:1008` and `0fcf:1009`, using **libusb-win32** (`libusb0.dll`). WinUSB-only dongles are not supported by this backend.

Check Device Manager first. If the ANT stick is already listed under **libusb-win32 devices**, leave the driver alone. Otherwise, [Zadig](https://zadig.akeo.ie/) can install libusb-win32 for the ANT stick. Save the current driver's details so you can restore it. Select the **ANT stick**, not the laptop's Bluetooth adapter; changing its driver can affect other ANT apps.

The app uses Windows' normal Bluetooth connection. Do not replace your Bluetooth driver.

### Pair an Edge 530

With TrainerRelay running:

**Menu → Training → Indoor Trainer → Pair ANT+ Bike Trainer → 53001 → Add Sensor**

Keep the Edge close to the laptop's USB stick, not just the trainer. It should remember this pairing next time. Other cycling computers have their own trainer-pairing menus.

## Control modes

Your cycling computer chooses the mode; the app follows it. The target card shows the last accepted mode and value, separately from measured trainer power.

**ERG** holds a power target. The bridge respects the trainer's reported range and caps requests at 600 W. The tested D100 reports 50–600 W in 1 W steps. A zero target sends Stop. Requests outside the range are rejected rather than quietly clamped.

**Slope** forwards grade and road-load settings through FTMS indoor-bike simulation. Wind and rolling-resistance updates preserve the other simulation settings. Wind settings received during ERG or basic resistance are saved for the next slope target, so a background road-settings update does not change the active mode. The trainer's physical limits still apply: requested grade is not a guarantee of a particular load. This bridge does not forward rider/bike mass to the trainer, and a downhill request cannot make a non-motorized trainer drive the pedals.

**Resistance** maps the computer's 0–100% request across the trainer's native minimum and maximum levels, rounded to a supported step. It is not a power target or a calibrated braking-force percentage. The bridge uses the current FTMS packet format; for older firmware it retries the legacy format only after a parameter rejection and only when the value fits it.

Modes are advertised over ANT only if the trainer reports the matching Bluetooth feature. Resistance additionally needs a valid range. Calibration and user-mass configuration are not supported.

### Trying the 0.2 preview

With the D100 and Edge available, check two modest slope settings, two resistance settings, and the return to ERG. The app should show the accepted mode, the brake should respond while pedalling, and Stop/reconnect should work. Software tests cannot confirm the physical response. If the preview misbehaves, the 0.1.0 ERG-only download is still on the releases page.

## Reading the window

- **Bluetooth trainer:** whether the trainer connection has opened.
- **ANT+ dongle:** whether the emulated trainer is broadcasting.
- **Cycling computer:** whether an ANT message has been received. This is not a continuous connection monitor.
- **Target:** the last command the trainer accepted. A rejected target leaves the previous accepted target visible and shows an error.
- **Trainer readings:** data received from the trainer. Missing or stale data is shown as a dash.

The D100 did not provide cadence in the captured FTMS data. Cadence on the Edge may instead come from a crank meter paired directly to it. TrainerRelay does not use that meter to adjust resistance.

## When something gets stuck

| Problem | What usually helps |
| --- | --- |
| Trainer missing from Scan | Wake or power-cycle it, close other connected training apps, and scan again. A connected D100 may stop advertising. |
| ANT stick missing or USB timeout | Stop the app, close other ANT apps, physically reconnect the stick, and retry. A software reset may not clear a driver failure. |
| Trainer missing on the cycling computer | Use its **indoor-trainer** pairing menu, look for **53001**, and move it closer to the USB stick. |
| Windows Bluetooth “object closed” error | The app retries this discovery error twice. If it persists, close other connections and power-cycle the trainer. |
| Slope/resistance unavailable | Check the enabled modes after connecting. The trainer may not advertise that control, or may omit its resistance range. |
| Target rejected | Check its range and mode. Use **Copy error** for the exact rejection. The bridge stays open after a normal command rejection. |

**Open logs** opens `%LOCALAPPDATA%\TrainerBridge`. The old folder name is kept so earlier logs stay together. Logs rotate at 2 MB with three backups and can contain nearby Bluetooth names and addresses—redact them before sharing.
