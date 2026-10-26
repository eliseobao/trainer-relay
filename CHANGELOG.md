# What's new

## 0.2.0-rc.1 — Slope & resistance preview

Your cycling computer can now send slope, road-load settings, and basic resistance as well as ERG targets. The target card follows the active mode automatically.

- Available modes follow the trainer's Bluetooth features.
- Resistance maps to the trainer's native range and step size, with a limited legacy-format fallback.
- Road settings preserve each other, and wind updates do not interrupt an ERG target.
- Normal command rejections stay visible without closing the bridge.
- The README and help are shorter, and one workflow handles checks and releases.

**Physical slope/resistance verification is still pending.** Protocol and mode-transition tests use a simulated trainer. The D100 + Edge 530 remains the priority setup, and 0.1.0 remains available for the verified ERG-only path.

## 0.1.0 — First rides

Bluetooth-to-ANT+ ERG control, live trainer readings, a simple connection window, and a standalone Windows download. Tested with the D100 and Edge 530, including USB close/reopen and real power targets.
