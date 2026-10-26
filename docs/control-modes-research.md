# Resistance and slope: feasibility research

**Conclusion: both appear feasible. “Unsupported” in v0.1.0 describes the bridge implementation, not an established limitation of the trainer or cycling computer. Neither mode has been validated end to end through TrainerRelay.**

## Evidence from the priority setup

During the original live Bluetooth inspection, the D100 returned Fitness Machine Feature bytes `014000000ca00000`. The second little-endian word is `0x0000A00C`, advertising these target-setting bits:

| Bit | Advertised capability |
| --- | --- |
| 2 | Resistance target |
| 3 | Power target (already implemented) |
| 13 | Indoor-bike simulation |
| 15 | Spin-down control |

Bluetooth SIG's [FTMS test suite, Table 4.13](https://files.bluetooth.com/wp-content/uploads/dlm_uploads/2024/10/FTMS.TS_.p6.pdf) maps resistance to control-point opcode `0x04` and simulation to `0x11`. Advertisement is evidence of intended support, not proof that this firmware accepts every valid command.

The existing Edge 530 session log also contains FE-C page-51 messages `33ffffffff844eff` and `33ffffffff204eff`: track-resistance commands representing +1% and 0% grade. These were received but rejected as unsupported by the released bridge. The missing work is therefore primarily translation and validation, rather than discovering a way for the Edge to send grade.

A fresh, read-only scan after the release did not find the priority trainer. The feature bitmap above is from the earlier successful inspection, not a newly repeated measurement. No resistance or slope commands were sent during this research.

Decathlon's [D100 product description](https://www.decathlon.com/products/van-rysel-d100-home-trainer-with-zwift-cog-and-click-355194) also describes FTMS connectivity and up to 6% simulated incline. That listing is the Zwift Cog variant; it corroborates the product family's capability but does not replace testing the priority unit's firmware.

## Proposed translation

| Cycling-computer command | Bluetooth control | Work still needed |
| --- | --- | --- |
| FE-C page 48, basic resistance | FTMS `0x04`, target resistance | Read `2AD6` range and increments; map ANT percentage to the trainer's native levels; verify payload width and units on its firmware |
| FE-C page 51, track resistance | FTMS `0x11`, indoor-bike simulation | Convert grade and rolling resistance; preserve the current wind parameters |
| FE-C page 50, wind resistance | Update the same simulation parameters | Convert wind-speed units and define drafting-factor handling |
| FE-C page 49, target power | FTMS `0x05` | Retain existing ERG behaviour and test transitions between modes |

The current Bluetooth test suite specifies a signed 16-bit resistance target and separately covers legacy unsigned-8-bit behaviour. Blindly treating all trainers as 0–100% with an identical packet would be unreliable. The simulation command carries wind speed, grade, rolling coefficient, and wind coefficient together; applying grade alone must not erase the other settings.

## Before enabling either mode

1. Re-read the priority trainer's feature and range characteristics while it is available.
2. Confirm low resistance and modest positive/zero grade commands are acknowledged, and observe the physical response under pedalling.
3. Test two values in each mode, then ERG → simulation → resistance → ERG, plus Stop and reconnect.
4. Advertise the corresponding FE-C capabilities only after that trainer's Bluetooth features and tested mappings support them. Keep ERG-only trainers working and return accurate rejection statuses.

This is a proposed follow-up, not a feature in v0.1.0. It can remain within the same simple bridge interface: show the active control mode and accepted target, without adding workouts or manual training controls.
