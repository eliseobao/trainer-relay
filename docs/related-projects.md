# Related projects and design choices

Reviewed while preparing the initial public repository:

| Project | Approach | What influenced TrainerRelay |
| --- | --- | --- |
| [FortiusANT](https://github.com/WouterJD/FortiusANT) | Adapts older Tacx trainers to modern ANT/BLE training software; extensive device and USB setup documentation | Explicit compatibility and driver troubleshooting; FE-C reference layouts and radio scheduling |
| [SmartTrainer UI](https://github.com/krishardy/smarttrainerui) | Focused BLE desktop controls with background async I/O and UI events | A small connection-first window with distinct transport status and no blocked UI thread |
| [Open Ride](https://github.com/baktakt/open-ride-app) | Browser trainer control, workout UI, and separate BLE/ANT transport choices | Explain transport requirements up front; keep connection and control responsibilities clear |

TrainerRelay remains a bridge rather than a training platform: the cycling computer owns the workout. It does not infer a workout plan or percentage from individual power targets.

These projects are references, not bundled dependencies. Downloaded reference code and personal hardware investigation scripts are excluded from this repository and its release. Dependencies actually redistributed in the executable are listed in `THIRD_PARTY_NOTICES.txt` inside the Windows ZIP.
