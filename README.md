# SOUNDBOKS for Home Assistant

A [Home Assistant](https://www.home-assistant.io/) integration that controls a SOUNDBOKS speaker
over Bluetooth LE: turn it off, set the volume, switch sound profile, all from dashboards and
automations.

> **Not affiliated with SOUNDBOKS.** This is an independent project, not made, endorsed or
> supported by SOUNDBOKS ApS. "SOUNDBOKS" is their trademark, used here only to say which
> speakers this works with. Use it at your own risk.

## What you get

One device per speaker, with:

| Entity | What it does |
|---|---|
| Media player | On/off state, volume (set, up, down), **turn off** (and **turn on** when a turn-on action is set), and the active inputs as its source |
| Sound profile (select) | Power, Bass+ or Indoor. Shows "Custom" when a custom EQ was set from the app |
| Stereo role (select) | Mono, Left or Right |
| Active inputs (sensor) | What is playing right now, e.g. "AUX, Bluetooth" |
| Reboot (button) | Restarts the speaker |

The speaker **can't wake itself remotely**: its Bluetooth radio is off along with it. Turn it on
by hand, and Home Assistant shows it as on within seconds. If you have something that can press its
power button for you, set it as the **turn-on action** (see [Options](#options)).

## Supported speakers

Tested on one speaker: hardware `5506_DUAL_SPK`, firmware `4217000100` (app protocol `2.4.2`).
Other speakers of the same generation probably work too, but are untested: reports are welcome,
working or not.

Newer generations use a different Bluetooth layout and aren't supported yet. Setup tells you so
instead of half-working.

## Requirements

- Home Assistant 2026.10 or newer.
- Bluetooth that reaches the speaker: the host's own adapter, or an
  [ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html) placed near it.

## Installation

### With HACS

1. In HACS, open the ⋮ menu → **Custom repositories**.
2. Add `https://github.com/Roxxas96/ha-soundboks-integration`, type **Integration**.
3. Install **SOUNDBOKS**, then restart Home Assistant.

### By hand

Copy `custom_components/soundboks` into your Home Assistant `config/custom_components/` folder,
then restart Home Assistant.

## Setup

1. **Close the SOUNDBOKS app** on every phone: the speaker accepts one connection at a time.
2. Turn the speaker on. Home Assistant should discover it: go to **Settings → Devices &
   services** and select **Add** on the SOUNDBOKS card. You can also add it by hand: **Add
   integration → SOUNDBOKS**.
3. If the speaker has a PIN (set in the SOUNDBOKS app), enter it.

To change the PIN later, open the integration's ⋮ menu → **Reconfigure**. If you change it from
the app, Home Assistant asks for the new one.

## Options

Open the integration's **Configure** to set optional helpers. They're blank by default, and
nothing changes until you set them.

- **Turn-on action**: any script or button entity that turns your speaker on, for example one that
  triggers a device pressing its power button. The media player's power button then runs it. The
  media player only shows "on" once the speaker is actually up and advertising, usually a few
  seconds later.

## How the connection is shared

The speaker takes **a single Bluetooth connection at a time**. While Home Assistant is connected,
the SOUNDBOKS app can't connect, and the other way round. So Home Assistant never stays connected
for long:

- **Every 30 seconds** it connects, reads the state, and disconnects right away.
- **After a command** (volume, profile…) it stays connected for 30 seconds, so a series of volume
  changes doesn't reconnect each time. Knob turns show up instantly during that window, and at
  the next poll otherwise.
- **Whether the speaker is on** comes from its Bluetooth advertisements, without connecting.

The speaker stops advertising while any app is connected to it, so Home Assistant can't tell "off"
from "busy with the app". It keeps showing the last state for 5 minutes before marking the speaker
off, unless it turned it off itself.

If you open the SOUNDBOKS app while Home Assistant is connected, the app may need a second try.
Commands sent from Home Assistant while the app is connected fail with a clear error.

## Limitations

- No power on (see above).
- No custom EQ, XLR inputs, TeamUp, knob volume limits or boot settings yet.
- No Siri volume control through HomeKit Bridge yet: HomeKit has no speaker volume control for
  media players.

## Troubleshooting

**The speaker isn't discovered, or says it can't connect.** Check that it's on, that no phone has
the SOUNDBOKS app open, and that it's in range. An ESPHome Bluetooth proxy near the speaker fixes
range problems.

**Debug logs.** Enable debug logging from the integration's ⋮ menu, or add this to
`configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.soundboks: debug
```

When reporting a bug, please include the logs and the diagnostics file (device page → ⋮ →
**Download diagnostics**; the PIN is removed from it).

## How it works

[docs/PROTOCOL.md](docs/PROTOCOL.md) describes what the integration sends to the speaker. The
protocol was worked out for interoperability; no code or assets from the official app are included.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE).
