# SOUNDBOKS Home Assistant integration — design

Date: 2026-10-25. Status: draft, awaiting approval.

## Intent

The owner reverse-engineered the BLE protocol of their SOUNDBOKS speaker (a "legacy" generation,
hardware `5506_DUAL_SPK`, firmware `4217000100`) in a private repo, `~/Code/soundboks-reversed`,
which holds a working Python CLI (`soundboks.py`, bleak) and a Flutter app. They now want the
speaker as a Home Assistant device, and want to share it with other SOUNDBOKS owners through
HACS, from a new public repo: `~/Code/ha-soundboks-integration`. The private repo is never
published.

What they actually do with the speaker: **turn it off and change the volume**, from three places:
the HA dashboard, automations, and eventually **Siri** (through HA's HomeKit Bridge — deferred,
see non-goals). Everything else is secondary.

## Goals

1. A HACS-installable custom integration, domain `soundboks`, that discovers the speaker over
   Bluetooth and sets it up with a config flow.
2. Power off and volume through a `media_player`, reliable enough for automations.
3. The speaker stays usable by other apps: HA never holds the BLE connection for long.
4. A repo that outsiders can read, install, and contribute to: clear README, contributing guide,
   protocol notes, tests, CI, the same dev tooling as the private repo.

## Non-goals (v1)

- Siri / HomeKit Bridge support (owner's call: later). HomeKit Bridge exposes a media player
  without Siri volume; a future version may add a light-style entity for it. Don't design anything
  that blocks adding one.
- Getting into HA core (no separate PyPI library; the protocol code lives inside the integration).
- Powering on (impossible: the radio is off with the speaker).
- Custom EQ bands, XLR inputs, TeamUp, knob limits, phone-volume/autoconnect, writing boot
  settings (`uus`), setting/clearing the PIN. These touch the serial settings protobuf and can
  misconfigure the speaker; they can come later.
- Newer SOUNDBOKS generations (different GATT layout). Nothing is known about how they advertise,
  so they may appear in discovery (my call): setup connects, checks the volume, power and profile
  characteristics exist, and aborts with "unsupported model" otherwise.
- Battery level (not exposed by this generation).

## Anti-goals

- Shipping anything taken from the official app: no decompiled code, no assets, no logos, no app
  identifiers (`LEGACY_*`, `SB*` class names) in code or docs, no decompiling instructions. Write
  original code and original names. Protocol facts (UUIDs, byte layouts, 3-letter serial commands)
  are fine.
- Holding the connection so the official app or the owner's Flutter app can never connect.
- An integration that hangs, spams errors, or flips entities to unavailable every time another app
  briefly holds the speaker.
- Anything that could get around a speaker's PIN. Users enter their own PIN.

## Legal framing (must be visible in the repo)

- README states: not affiliated with or endorsed by SOUNDBOKS ApS; "SOUNDBOKS" is their trademark,
  used only to say what the integration works with; use at your own risk.
- Built for interoperability (EU Directive 2009/24/EC art. 6 is the basis); no SOUNDBOKS code or
  assets included.
- License: MIT (my call).
- No SOUNDBOKS logo in `brands/` or anywhere; use a generic speaker icon (`mdi:speaker`).

## Protocol facts the integration needs

Source of truth: `~/Code/soundboks-reversed/PROTOCOL.md` and `soundboks.py` (read them; do not
copy text or names from them, rewrite in your own words into `docs/PROTOCOL.md` of the new repo,
covering only what this integration uses).

- Discovery: advertises local name `#<serial>` (e.g. `#202047`), service
  `f5c26570-64ec-4906-b998-6a7302879a2b`, manufacturer data company ID `0x0858`. No pairing.
- **One BLE connection at a time.**
- Volume `7649b19f-c605-46e2-98f8-6c1808e0cfb4`: 1 byte 0–255, read/write/notify; resets to `0x2d`
  at power-on. Knob steps by 7.
- Power `11ad501d-fa86-43cc-8d92-5a27ee672f1a`: write `00` (write *with* response) powers off; the
  speaker never acks, it drops the link — treat a disconnect after the write as success. Writing
  `[01, 1]` sets auto-boot "once", so a following `00` reboots it (that's the CLI's `reboot`).
- Sound profile `57a394fb-6d89-4105-8f07-bf730338a9b2`: 7 bytes `[mode, B1..T2]`; mode 0 = Power,
  1 = Bass+, 2 = Indoor, 3 = custom (bands only matter for 3). Writing a preset: keep the current
  band bytes, change only the mode byte.
- Stereo role `7d0d651e-62ae-4ef2-a727-0e8f3e9b4dfb`: 0 mono, 1 left, 2 right.
- Sound status `8d36814f-3741-4cb5-a018-ef4a2d8e24f1`: byte 1 is a bitfield of active inputs:
  ch1 1, ch2 2, aux 4, bluetooth 8, TeamUp 16.
- Security level `93aa965c-98b8-4433-b6bb-41ce61a8db9a`: bitfield, 1 = PIN enabled, 2 = locked.
  Readable without auth.
- PIN auth, only when the PIN bit is set: subscribe to serial RX
  `49535343-1e4d-4bd9-ba61-23c647249616`, write `aup` + the 4 ASCII digits to serial TX
  `49535343-8841-43f4-a8d4-ecbe34729bb3`; `01 00 00 00 00` = accepted, `02 00` = refused. Keep the
  RX subscription for the whole connection (unsubscribing drops the link). Without auth, reads
  work and writes fail with ATT error `0x81`.
- Device info: standard `180a` service; firmware string at `8980ccc7-e6d4-4f9d-9540-3c62fa0a5a74`.

## How it works

### Connection policy (decided with the owner)

- **On demand.** A command connects (via HA's Bluetooth stack and `bleak-retry-connector`),
  authenticates if needed, writes, then keeps the link for a **30 s idle window** so a burst of
  volume changes reuses it; then disconnects.
- **Polling every 30 s** (owner's choice, not 5 min): connect, read volume / profile / stereo /
  status, disconnect (or reuse the link if a command already holds it). Skip the poll while the
  speaker isn't advertising.
- **Presence without connecting.** HA's passive Bluetooth callbacks: advertising = on. Not seen for
  HA's standard unavailable timeout = off. This updates "is it on" within seconds and never uses
  the connection.
- **Busy speaker** (another app connected, connect fails): polls keep the last known state and
  log at debug level, never flip entities to unavailable for that alone. A user command that can't
  get through raises a `HomeAssistantError` with a clear message ("speaker is busy — another app
  may be connected"), so dashboards and automations see the failure.
- **Unknown, verify first (first build task):** whether the speaker keeps advertising while
  another central is connected. Test on the real speaker: connect the official or Flutter app,
  watch advertisements from HA or a Mac. If it keeps advertising, the rule above stands. If it
  stops (my call for the fallback): when HA itself powered it off, show off at once; otherwise,
  when advertising stops, try one connect — "device not found" = off; keep the last state while
  the speaker is in that "gone but not confirmed" window for at most 5 minutes, then off. Document
  the result in `docs/PROTOCOL.md`.
- All BLE access goes through one lock: one connection, one operation at a time.
- While connected (idle window), subscribe to volume notifications so knob changes during that
  window show up immediately (cheap bonus; polling is the guarantee).

### Entities (one device per speaker)

Core (enabled by default):

- `media_player` — state `on` while advertising, `off` otherwise; `volume_set`, `volume_step`
  (raw 0–255 ↔ 0.0–1.0), `turn_off` (power off). No `turn_on`. Source shown read-only as the
  active input(s).

Extras:

- `select` sound profile: Power / Bass+ / Indoor (shows "Custom" read-only when mode is 3; choosing
  it is not offered).
- `select` stereo role: Mono / Left / Right.
- `sensor` active inputs (text, e.g. "Bluetooth, AUX"; "None").
- `button` reboot (auto-boot once + power off).
- Diagnostics: firmware version on the device info; HA diagnostics download with the PIN redacted.

### Config flow

- Bluetooth discovery from `manifest.json` matchers (service UUID + `#*` local name), plus a manual
  "pick a discovered speaker" user step.
- On setup, connect once and read the security level; if a PIN is enabled, ask for it and verify
  with `aup` before creating the entry. Unique ID = BLE address. Title = `SOUNDBOKS #<serial>`.
- Reauth flow when the PIN is later refused; options/reconfigure flow to change the PIN.

### Code layout (builder may adjust)

```
custom_components/soundboks/
  __init__.py  manifest.json  const.py  config_flow.py  coordinator.py
  protocol.py      # pure encode/decode: no BLE, no HA; fully unit-tested
  client.py        # BLE client on bleak + bleak-retry-connector: connect, auth, read, write
  entity.py  media_player.py  select.py  sensor.py  button.py
  diagnostics.py  strings.json  translations/en.json
tests/             # pytest-homeassistant-custom-component; protocol tests need no HA
hacs.json  pyproject.toml  README.md  CONTRIBUTING.md  LICENSE  CHANGELOG.md
docs/PROTOCOL.md
```

## Repo and developer tooling

Mirror the private repo's choices, adapted for HA:

- `mise.toml`: Python pinned to the version current HA requires (check at build time), prek; venv
  in `.venv`.
- `pyproject.toml`: project metadata, dev dependencies (`pytest-homeassistant-custom-component`,
  which pins a matching HA), ruff config (pyflakes/pycodestyle + `I`, `B`, `UP`, plus HA-friendly
  rules), pytest config.
- `.pre-commit-config.yaml` run by prek: pre-commit-hooks basics, editorconfig-checker, ruff
  check/format, typos, gitleaks, commitizen (commit-msg, branch on pre-push). `.editorconfig`,
  `_typos.toml`, `.cz.toml`, `.gitignore`.
- Conventional Commits; CHANGELOG generated by commitizen; releases are git tags + GitHub releases
  (what HACS installs).
- GitHub Actions: lint (prek), tests (pytest), `hassfest`, HACS validation action. Pin actions to
  current majors.
- GitHub extras for outsiders: issue templates (bug report asks for HA version, firmware, logs
  with debug enabled), PR template, a short `SECURITY.md`.
- README: what it does, supported hardware (the tested firmware; others "untested, reports
  welcome"), install via HACS custom repository, setup, entities, the single-connection behaviour,
  limitations (no power on; no Siri volume through HomeKit Bridge yet), troubleshooting (debug
  logging, ESPHome
  Bluetooth proxies for range), disclaimer.
- `git init` with default branch `main`. No remote created; the owner publishes it.
- GitHub location (my call, easy to change): `github.com/Roxxas96/ha-soundboks-integration`,
  codeowner `@Roxxas96`. Used in `manifest.json` (`documentation`, `issue_tracker`,
  `codeowners`), README HACS instructions, issue templates and `SECURITY.md`.

## Testing

- `protocol.py`: unit tests for every encode/decode (volume mapping, profile, stereo, status bits,
  security bits, auth responses).
- Integration tests with mocked client: config flow (discovery, PIN, wrong PIN, reauth), entities,
  busy-speaker handling, idle-disconnect timing.
- Final check on the owner's real speaker (HA runs physically next to it): off, volume, an
  automation, and confirm the official app can still connect between polls.

## Left to the builder

File split, class names, the exact HA coordinator base class, how the idle timer is implemented,
log messages, test structure, versions of tools and actions (latest stable at build time).
