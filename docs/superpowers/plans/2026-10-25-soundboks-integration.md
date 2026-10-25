# SOUNDBOKS Home Assistant Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A HACS-installable Home Assistant custom integration (`soundboks`) that discovers a legacy
SOUNDBOKS speaker over Bluetooth and exposes power off, volume, sound profile, stereo role, active
inputs and reboot, without monopolising the speaker's single BLE connection.

**Architecture:** Three layers. `protocol.py` is pure byte encoding/decoding (no BLE, no HA).
`client.py` owns the one BLE connection: connects on demand through `bleak-retry-connector`,
authenticates with the PIN, serialises operations behind a lock, and drops the link after a 30 s
idle window (polls drop it immediately). `coordinator.py` polls every 30 s and tracks presence from
passive advertisements; entities read the coordinator and call it for commands.

**Tech Stack:** Python 3.14, Home Assistant 2026.10, bleak / bleak-retry-connector (shipped with HA),
pytest-homeassistant-custom-component, mise, prek (ruff, typos, gitleaks, commitizen,
editorconfig-checker, actionlint), GitHub Actions (hassfest, HACS validation).

**Spec:** `docs/superpowers/specs/2026-10-25-soundboks-integration-design.md` — read it first.
Protocol source of truth (read-only, private, never copy text or identifiers from it):
`~/Code/soundboks-reversed/PROTOCOL.md` and `~/Code/soundboks-reversed/soundboks.py`.

## Global Constraints

- Work only in `~/Code/ha-soundboks-integration`. Never modify `~/Code/soundboks-reversed`.
- No code, assets, logos or app identifiers from the official app: nothing named `LEGACY_*`,
  `SB*`, `SBLegacy…`; no decompiling instructions; no SOUNDBOKS logo anywhere. Icon: `mdi:speaker`.
- README states: not affiliated with or endorsed by SOUNDBOKS ApS; "SOUNDBOKS" is their trademark,
  used only to say what the integration works with; use at your own risk. License MIT.
- Domain `soundboks`. GitHub `github.com/Roxxas96/ha-soundboks-integration`, codeowner `@Roxxas96`.
- Python pinned `3.14.9` (HA 2026.10 requires ≥ 3.14.2). Test toolkit
  `pytest-homeassistant-custom-component==0.13.374` (pins `homeassistant==2026.10.3`). `hacs.json`
  minimum HA `2026.10.0`.
- Poll interval 30 s. Idle window after a command 30 s. Polls never hold the link afterwards.
- v1 scope only: no custom EQ, XLR, TeamUp, knob limits, boot settings (`uus`/`gu2`), PIN set/clear,
  HomeKit/Siri entity, power on.
- Conventional Commits (commitizen enforces). Default branch `main`. No remote is created.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Every task ends with `prek run --all-files` and `pytest` green.

## Review Focus

1. **Poll + idle window never frees the link** — a poll that reused or opened a connection must not
   leave it open; with a 30 s poll and a 30 s idle timer, a careless implementation holds the
   speaker forever. Expected: after `read_state()` on a fresh connection, the client is
   disconnected. Pinned in Task 4 (`test_read_state_disconnects_when_it_opened_the_link`).
2. **Power off looks like a failure** — the speaker drops the link instead of acking; a `BleakError`
   or disconnect during the power write must count as success, and HA must show `off` at once.
   Pinned in Task 4 (`test_power_off_treats_dropped_link_as_success`) and Task 5
   (`test_power_off_marks_absent_immediately`).
3. **Command while the speaker is off or another app holds it** — must fail fast with a readable
   `HomeAssistantError`, never hang or raise a raw Bleak exception. Pinned in Task 7
   (`test_set_volume_when_unreachable_raises_ha_error`).
4. **Volume edge values** — 0.0 → 0, 1.0 → 255, out-of-range input clamped, raw 255 → 1.0. Pinned in
   Task 3 (`test_level_round_trip_edges`).
5. **Concurrent operations** — a volume burst racing a poll must share one connection and run one
   at a time. Pinned in Task 4 (`test_concurrent_operations_share_one_connection`).

---

## File Structure

```
.editorconfig  .gitignore  .cz.toml  _typos.toml  mise.toml  pyproject.toml
.pre-commit-config.yaml  requirements-dev.txt  hacs.json
LICENSE  README.md  CONTRIBUTING.md  SECURITY.md  CHANGELOG.md
.github/workflows/ci.yml
.github/ISSUE_TEMPLATE/bug_report.yml  .github/ISSUE_TEMPLATE/config.yml
.github/pull_request_template.md
docs/PROTOCOL.md
custom_components/soundboks/
  __init__.py       setup/unload entry, wires client + coordinator + bluetooth callbacks
  manifest.json
  const.py          DOMAIN, CONF_PIN, intervals, PLATFORMS
  protocol.py       UUIDs, enums, SpeakerState, encode/decode, error types (pure)
  client.py         SoundboksClient: the BLE connection
  coordinator.py    SoundboksCoordinator: polling, presence, commands
  entity.py         SoundboksEntity base (device info, availability)
  config_flow.py    bluetooth discovery, user pick, PIN, reauth, reconfigure
  media_player.py  select.py  sensor.py  button.py  diagnostics.py
  translations/en.json
tests/
  conftest.py       FakeBleakClient, fixtures
  test_protocol.py  test_client.py  test_coordinator.py  test_config_flow.py
  test_media_player.py  test_entities.py  test_diagnostics.py
```

Decision: only `translations/en.json` (custom integrations read translations from there; no
`strings.json`).

---

### Task 1: Repository and tooling

**Files:**
- Create: `.editorconfig`, `.gitignore`, `.cz.toml`, `_typos.toml`, `mise.toml`, `pyproject.toml`,
  `.pre-commit-config.yaml`, `requirements-dev.txt`, `LICENSE`, `tests/__init__.py`,
  `tests/test_smoke.py`
- Already present: `docs/superpowers/specs/…`, `docs/superpowers/plans/…` (commit them here)

**Interfaces:**
- Produces: `mise install && pip install -r requirements-dev.txt && prek install` sets up a clone;
  `pytest` and `prek run --all-files` are the two gates every later task uses.

- [ ] **Step 1: `git init -b main`** in `~/Code/ha-soundboks-integration`.
- [ ] **Step 2: Write configs**, mirroring `~/Code/soundboks-reversed` (same files, same hook revs:
  pre-commit-hooks v6.0.0, editorconfig-checker 3.11.1, ruff-pre-commit v0.17.2, typos v1.51.1,
  gitleaks v8.30.1, commitizen v4.19.3) minus the Dart/Flutter hooks and app excludes, plus
  `rhysd/actionlint` (latest tag). `mise.toml`: `python = "3.14.9"`, `prek = "0.5.7"`,
  `.venv` auto-create as in the private repo. `.cz.toml`: conventional commits, `version = "0.1.0"`,
  `tag_format = "v$version"`, `update_changelog_on_bump = true`,
  `version_files = ["custom_components/soundboks/manifest.json:\"version\""]`.
  `pyproject.toml`: `[project]` name `ha-soundboks-integration`, `requires-python = ">=3.14.2"`;
  ruff `line-length = 100`, `target-version = "py314"`, `extend-select = ["I", "B", "UP", "ASYNC"]`;
  pytest `asyncio_mode = "auto"`, `testpaths = ["tests"]`. `requirements-dev.txt`:
  `pytest-homeassistant-custom-component==0.13.374`. `.gitignore`: `.venv/`, `__pycache__/`,
  `.pytest_cache/`, `.ruff_cache/`, `.superpowers/`, `apk/`, `*.apk`, `*.xapk`. `LICENSE`: MIT,
  2026, Alexandre Gomez.
- [ ] **Step 3: `tests/test_smoke.py`** — `def test_toolchain(): assert True` (deleted in Task 3).
- [ ] **Step 4: Verify** — `mise install && pip install -r requirements-dev.txt && prek install &&
  prek run --all-files && pytest` → all hooks pass, `1 passed`.
- [ ] **Step 5: Commit** — `chore: set up repository tooling` (include the spec and plan).

---

### Task 2: Check advertising while another app is connected (needs the owner)

Decides `PRESENCE_GRACE` in Task 5. Cannot be automated: ask the owner to do the physical part.

**Files:** none committed (script lives in the session scratchpad). Result recorded in Task 3's
`docs/PROTOCOL.md`.

- [ ] **Step 1: Write a scratchpad script** using `bleak.BleakScanner` with a detection callback
  filtered on service `f5c26570-64ec-4906-b998-6a7302879a2b`, printing a timestamp per
  advertisement for 60 s.
- [ ] **Step 2: Ask the owner** to turn the speaker on, then connect the official or their Flutter
  app and keep it connected; run the script on the Mac meanwhile.
- [ ] **Step 3: Record the answer.** Advertisements keep arriving while the app is connected →
  `PRESENCE_GRACE = timedelta(0)`. They stop → `PRESENCE_GRACE = timedelta(minutes=5)`.
  Write the value and the evidence into the Task 5 notes (and later `docs/PROTOCOL.md`).

Note (deviation from spec, deliberate): the spec's "try one connect when advertising stops" is
dropped. A speaker that isn't advertising can't be connected to whether it is off or held by
another app, so the attempt can't tell the two apart. The grace window alone covers it.

---

### Task 3: Protocol layer and protocol notes

**Files:**
- Create: `custom_components/soundboks/__init__.py` (empty docstring for now),
  `custom_components/soundboks/protocol.py`, `tests/test_protocol.py`, `docs/PROTOCOL.md`
- Delete: `tests/test_smoke.py`

**Interfaces:**
- Produces (all in `protocol.py`):
  - UUID constants: `ADVERTISED_SERVICE_UUID = "f5c26570-64ec-4906-b998-6a7302879a2b"`,
    `VOLUME_UUID = "7649b19f-c605-46e2-98f8-6c1808e0cfb4"`,
    `POWER_UUID = "11ad501d-fa86-43cc-8d92-5a27ee672f1a"`,
    `PROFILE_UUID = "57a394fb-6d89-4105-8f07-bf730338a9b2"`,
    `STEREO_UUID = "7d0d651e-62ae-4ef2-a727-0e8f3e9b4dfb"`,
    `INPUTS_UUID = "8d36814f-3741-4cb5-a018-ef4a2d8e24f1"`,
    `SECURITY_UUID = "93aa965c-98b8-4433-b6bb-41ce61a8db9a"`,
    `SERIAL_TX_UUID = "49535343-8841-43f4-a8d4-ecbe34729bb3"`,
    `SERIAL_RX_UUID = "49535343-1e4d-4bd9-ba61-23c647249616"`,
    `FIRMWARE_UUID = "8980ccc7-e6d4-4f9d-9540-3c62fa0a5a74"`,
    `REQUIRED_UUIDS = (VOLUME_UUID, POWER_UUID, PROFILE_UUID)`.
  - `POWER_OFF = b"\x00"`, `AUTO_BOOT_ONCE = b"\x01\x01"`.
  - `class SoundProfile(IntEnum)`: `POWER = 0`, `BASS_PLUS = 1`, `INDOOR = 2`, `CUSTOM = 3`.
  - `class StereoRole(IntEnum)`: `MONO = 0`, `LEFT = 1`, `RIGHT = 2`.
  - `class Input(IntFlag)`: `CHANNEL_1 = 1`, `CHANNEL_2 = 2`, `AUX = 4`, `BLUETOOTH = 8`,
    `TEAMUP = 16`.
  - `@dataclass(frozen=True) class SpeakerState`: `volume: int`, `profile: SoundProfile`,
    `stereo: StereoRole`, `inputs: Input`.
  - Errors: `class SoundboksError(Exception)`; subclasses `SpeakerUnreachableError`,
    `PinRequiredError`, `InvalidPinError`, `UnsupportedSpeakerError`, `ProtocolError`.
  - `level_to_raw(level: float) -> int`, `raw_to_level(raw: int) -> float`
  - `decode_volume(data: bytes) -> int`, `decode_profile(data: bytes) -> SoundProfile`,
    `encode_profile(current: bytes, profile: SoundProfile) -> bytes`,
    `decode_stereo(data: bytes) -> StereoRole`, `decode_inputs(data: bytes) -> Input`,
    `pin_required(security: bytes) -> bool`, `validate_pin(pin: str) -> str`,
    `auth_command(pin: str) -> bytes`, `auth_accepted(packet: bytes) -> bool`.

- [ ] **Step 1: Write the failing tests** in `tests/test_protocol.py`:

```python
def test_level_round_trip_edges():
    assert level_to_raw(0.0) == 0
    assert level_to_raw(1.0) == 255
    assert level_to_raw(0.5) == 128
    assert level_to_raw(-0.2) == 0 and level_to_raw(1.7) == 255
    assert raw_to_level(255) == 1.0 and raw_to_level(0) == 0.0


def test_decode_volume():
    assert decode_volume(b"\x2d") == 0x2D
    with pytest.raises(ProtocolError):
        decode_volume(b"")


def test_profile():
    current = bytes([3, 1, 2, 3, 4, 5, 6])
    assert decode_profile(current) is SoundProfile.CUSTOM
    assert encode_profile(current, SoundProfile.BASS_PLUS) == bytes([1, 1, 2, 3, 4, 5, 6])
    with pytest.raises(ValueError):
        encode_profile(current, SoundProfile.CUSTOM)
    with pytest.raises(ProtocolError):
        decode_profile(bytes([9, 0, 0, 0, 0, 0, 0]))
    with pytest.raises(ProtocolError):
        encode_profile(b"\x00", SoundProfile.POWER)  # not 7 bytes


def test_stereo():
    assert decode_stereo(b"\x02") is StereoRole.RIGHT
    with pytest.raises(ProtocolError):
        decode_stereo(b"\x07")


def test_inputs():
    assert decode_inputs(bytes([0, 8 | 4])) == Input.BLUETOOTH | Input.AUX
    assert decode_inputs(bytes([0, 0])) == Input(0)
    assert decode_inputs(bytes([0, 0x80 | 8])) == Input.BLUETOOTH  # unknown bits dropped
    with pytest.raises(ProtocolError):
        decode_inputs(b"\x00")


def test_security_and_pin():
    assert pin_required(b"\x01") and pin_required(b"\x03")
    assert not pin_required(b"\x00") and not pin_required(b"\x02")
    assert validate_pin(" 0042 ") == "0042"
    for bad in ("123", "12345", "12a4", ""):
        with pytest.raises(ValueError):
            validate_pin(bad)
    assert auth_command("1234") == b"aup1234"


def test_auth_accepted():
    assert auth_accepted(b"\x01\x00\x00\x00\x00") is True
    assert auth_accepted(b"\x02\x00") is False
    with pytest.raises(ProtocolError):
        auth_accepted(b"\x00")
```

- [ ] **Step 2: Run** `pytest tests/test_protocol.py -v` → FAIL (import error).
- [ ] **Step 3: Implement `protocol.py`.** `level_to_raw` = `round(clamp(level, 0, 1) * 255)`.
  `decode_*` raise `ProtocolError` on wrong length or unknown enum value; `decode_inputs` reads
  byte 1 and masks with the known bits. `auth_accepted`: `True` for the 5-byte ack, `False` when
  the first byte is `0x02`, `ProtocolError` otherwise. Use original names and docstrings only.
- [ ] **Step 4: Run** `pytest tests/test_protocol.py -v` → PASS.
- [ ] **Step 5: Write `docs/PROTOCOL.md`** in your own words: discovery, single connection, each
  characteristic used above with its byte layout, power-off link drop, auto-boot reboot trick, PIN
  `aup` flow and responses, and the Task 2 advertising finding. Only what the integration uses; no
  app identifiers, no decompiling steps.
- [ ] **Step 6: Commit** — `feat: add speaker protocol encoding`.

---

### Task 4: BLE client

**Files:**
- Create: `custom_components/soundboks/client.py`, `tests/conftest.py`, `tests/test_client.py`

**Interfaces:**
- Consumes: everything in `protocol.py`.
- Produces:

```python
class SoundboksClient:
    def __init__(self, ble_device: BLEDevice | None, pin: str | None, *,
                 idle_timeout: float = 30.0,
                 on_volume: Callable[[int], None] | None = None) -> None
    def set_ble_device(self, ble_device: BLEDevice) -> None
    @property
    def is_connected(self) -> bool
    async def check_supported(self) -> None        # UnsupportedSpeakerError
    async def pin_required(self) -> bool
    async def verify_pin(self, pin: str) -> None    # InvalidPinError
    async def read_firmware(self) -> str
    async def read_state(self) -> SpeakerState
    async def set_volume(self, raw: int) -> None
    async def set_profile(self, profile: SoundProfile) -> None
    async def set_stereo(self, role: StereoRole) -> None
    async def power_off(self) -> None
    async def reboot(self) -> None
    async def disconnect(self) -> None
```

  All public methods may raise `SpeakerUnreachableError` (no BLE device, connect failure,
  `BleakError`/`TimeoutError` mid-operation), `PinRequiredError` (speaker has a PIN, client has
  none) or `InvalidPinError` (PIN refused).
- `tests/conftest.py` produces `FakeBleakClient` and a `fake_speaker` fixture that patches
  `custom_components.soundboks.client.establish_connection` to return it, plus counts connects.

Behaviour to implement:
- One `asyncio.Lock` around every public operation. Connection via
  `bleak_retry_connector.establish_connection(BleakClientWithServiceCache, device, name,
  disconnected_callback=…)`; any `BleakError`/`TimeoutError`/`BleakNotFoundError` →
  `SpeakerUnreachableError("Could not reach the speaker: it may be off, out of range, or another
  app may be connected")`.
- After connecting: start notify on `SERIAL_RX_UUID` (queue packets) and keep it for the whole
  connection; read `SECURITY_UUID`; if `pin_required` → write `auth_command(pin)` to
  `SERIAL_TX_UUID` with `response=True`, wait ≤ 5 s for one packet, `auth_accepted` else
  `InvalidPinError` (disconnect first). Subscribe to `VOLUME_UUID` notifications → `on_volume(raw)`.
- **Idle policy:** commands (`set_*`, `verify_pin`) (re)arm a `loop.call_later(idle_timeout, …)`
  disconnect. `read_state`, `read_firmware`, `check_supported`, `pin_required` disconnect right away
  if they opened the connection themselves, and leave an existing idle timer untouched otherwise.
- `power_off`: write `POWER_OFF` with `response=True`; `BleakError`/disconnect during or after the
  write = success; then clean up connection state (no exception).
- `reboot`: write `AUTO_BOOT_ONCE` (link drop = success), reconnect, write `POWER_OFF` (same rule).
- `set_profile`: read current profile bytes, write `encode_profile(current, profile)`.
- `check_supported`: `UnsupportedSpeakerError` unless every `REQUIRED_UUIDS` characteristic exists
  in `client.services`.

- [ ] **Step 1: Write `FakeBleakClient`** in `tests/conftest.py`: dict of characteristic values
  (defaults: volume `0x2d`, profile `[0,51,51,51,51,51,51]`, stereo `0`, inputs `[0,8]`,
  security `0`, firmware `b"2.4.2"`), `writes: list[tuple[str, bytes]]`, `start_notify` storing
  callbacks, `write_gatt_char` that answers `aup` on RX with ack/refusal based on a `pin`
  attribute, `services.get_characteristic(uuid)`, `is_connected`, `disconnect()`, options
  `drop_on_power_write=True` and `unreachable=False` (fixture raises `BleakError` on connect).
- [ ] **Step 2: Write the failing tests** in `tests/test_client.py`:
  - `test_read_state_disconnects_when_it_opened_the_link` — state equals
    `SpeakerState(0x2d, SoundProfile.POWER, StereoRole.MONO, Input.BLUETOOTH)`; afterwards
    `client.is_connected is False`.
  - `test_command_keeps_link_for_idle_window` — `idle_timeout=0.05`; after `set_volume(100)`:
    connected, write `(VOLUME_UUID, b"\x64")` recorded; after `asyncio.sleep(0.1)`: disconnected.
  - `test_burst_reuses_connection` — three `set_volume` calls → connect count 1.
  - `test_concurrent_operations_share_one_connection` — `asyncio.gather(set_volume(1),
    set_volume(2), read_state())` → connect count 1, writes in call order, no exception.
  - `test_power_off_treats_dropped_link_as_success` — fake raises `BleakError` on the power write;
    `power_off()` returns, write `(POWER_UUID, b"\x00")` recorded, `is_connected is False`.
  - `test_reboot_writes_auto_boot_then_off` — writes contain `(POWER_UUID, b"\x01\x01")` then
    `(POWER_UUID, b"\x00")`, connect count 2.
  - `test_pin_auth_sent_when_required` — security `0x01`, client pin `"1234"` → first TX write is
    `b"aup1234"`; `set_volume` succeeds.
  - `test_wrong_pin_raises` — fake pin `"9999"`, client `"1234"` → `InvalidPinError`, disconnected.
  - `test_missing_pin_raises` — security `0x01`, client pin `None` → `PinRequiredError`.
  - `test_unreachable_raises` — fixture `unreachable=True` → `SpeakerUnreachableError`; also with
    `ble_device=None`.
  - `test_set_profile_keeps_bands` — profile `[3,1,2,3,4,5,6]`, `set_profile(INDOOR)` → write
    `[2,1,2,3,4,5,6]`.
  - `test_check_supported` — fake missing `PROFILE_UUID` → `UnsupportedSpeakerError`.
  - `test_volume_notifications_forwarded` — while connected, fake notifies `b"\x40"` on
    `VOLUME_UUID` → `on_volume` called with `0x40`.
- [ ] **Step 3: Run** `pytest tests/test_client.py -v` → FAIL.
- [ ] **Step 4: Implement `client.py`** per the behaviour above.
- [ ] **Step 5: Run** `pytest -v` → PASS; `prek run --all-files` → pass.
- [ ] **Step 6: Commit** — `feat: add BLE client with on-demand connection`.

---

### Task 5: Integration setup, coordinator and presence

**Files:**
- Create: `custom_components/soundboks/manifest.json`, `const.py`, `coordinator.py`, `entity.py`,
  `tests/test_coordinator.py`
- Modify: `custom_components/soundboks/__init__.py`

**Interfaces:**
- Consumes: `SoundboksClient`, `SpeakerState`, errors.
- Produces:
  - `const.py`: `DOMAIN = "soundboks"`, `CONF_PIN = "pin"`,
    `POLL_INTERVAL = timedelta(seconds=30)`, `IDLE_TIMEOUT = 30.0`,
    `PRESENCE_GRACE = <Task 2 result>`, `MANUFACTURER = "SOUNDBOKS ApS"`,
    `PLATFORMS = [Platform.MEDIA_PLAYER, Platform.SELECT, Platform.SENSOR, Platform.BUTTON]`.
  - `type SoundboksConfigEntry = ConfigEntry[SoundboksCoordinator]` (in `coordinator.py`).
  - `class SoundboksCoordinator(DataUpdateCoordinator[SpeakerState | None])`:
    `__init__(hass, entry, client: SoundboksClient)`; `present: bool`; `firmware: str | None`;
    `async_handle_advertisement(service_info: BluetoothServiceInfoBleak, change: BluetoothChange)
    -> None` (callback); `async_handle_unavailable(service_info) -> None` (callback);
    `async_set_volume(raw: int)`, `async_set_profile(profile)`, `async_set_stereo(role)`,
    `async_power_off()`, `async_reboot()` — all raise `HomeAssistantError` (translation key
    `unreachable`) on `SpeakerUnreachableError`, and update `data` optimistically on success.
  - `class SoundboksEntity(CoordinatorEntity[SoundboksCoordinator])` in `entity.py`:
    `_attr_has_entity_name = True`; `device_info` with identifiers `{(DOMAIN, address)}`,
    connections `{(CONNECTION_BLUETOOTH, address)}`, manufacturer `MANUFACTURER`, model
    `"SOUNDBOKS (BLE)"`, name = entry title, `sw_version = coordinator.firmware`;
    `available` = `coordinator.present and coordinator.data is not None`.
  - Entry data keys: `CONF_ADDRESS` (from `homeassistant.const`), optional `CONF_PIN`.

Behaviour:
- `manifest.json`: `domain`, `name: "SOUNDBOKS"`, `bluetooth: [{"service_uuid":
  ADVERTISED_SERVICE_UUID, "connectable": true}]` (no `local_name`: hassfest rejects too-short
  wildcards), `codeowners`, `config_flow: true`, `dependencies: ["bluetooth_adapters"]`,
  `documentation`/`issue_tracker` (GitHub URLs), `integration_type: "device"`,
  `iot_class: "local_polling"`, `requirements: []`, `version: "0.1.0"`.
- `async_setup_entry`: build client from `async_ble_device_from_address(hass, address,
  connectable=True)` (may be `None`), `pin=entry.data.get(CONF_PIN)`, `on_volume` → coordinator;
  register `async_register_callback(…, BluetoothCallbackMatcher(address=address,
  connectable=True), BluetoothScanningMode.PASSIVE)` and `async_track_unavailable(…, address,
  connectable=True)` with `entry.async_on_unload`; `await coordinator.async_refresh()` (never
  `first_refresh`: an off speaker must not block setup); `entry.runtime_data = coordinator`;
  forward `PLATFORMS`. Unload: unload platforms, `await client.disconnect()`.
- Presence: advertisement → `present = True`, cancel grace timer, `client.set_ble_device`,
  notify listeners; first advertisement after absence triggers `async_request_refresh`.
  Unavailable → if `PRESENCE_GRACE` is zero, `present = False` now; else `async_call_later` it.
  `async_power_off`/`async_reboot` success → `present = False` immediately.
- `_async_update_data`: not present → return `self.data`. `SpeakerUnreachableError` → return
  `self.data` (debug log). `InvalidPinError`/`PinRequiredError` → raise `ConfigEntryAuthFailed`.
  Success → state; read firmware once (store in `firmware`).

- [ ] **Step 1: Write the failing tests** in `tests/test_coordinator.py` (use `enable_bluetooth`,
  `MockConfigEntry`, `fake_speaker`, `async_fire_time_changed`; drive presence by calling the
  coordinator's handlers with a `BluetoothServiceInfoBleak` built in conftest):
  - `test_setup_with_speaker_off_succeeds` — no advertisement, setup → entry `LOADED`,
    `coordinator.data is None`, `present is False`.
  - `test_poll_reads_state_when_present` — advertisement, advance 30 s → `data.volume == 0x2d`.
  - `test_poll_skipped_when_absent` — no advertisement → fake connect count 0 after 30 s.
  - `test_busy_speaker_keeps_last_state` — after one good poll, fake `unreachable=True`, advance
    30 s → `data` unchanged, `last_update_success is True`.
  - `test_wrong_pin_starts_reauth` — fake pin mismatch → a `reauth` flow is in progress for the
    entry.
  - `test_power_off_marks_absent_immediately` — `await coordinator.async_power_off()` →
    `present is False` with no unavailable callback.
  - `test_unavailable_respects_grace` — unavailable callback → `present` is `False` after
    `PRESENCE_GRACE` (immediately when zero), and stays `True` before it when non-zero.
  - `test_unload_disconnects` — unload → client disconnected, entry `NOT_LOADED`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `manifest.json`, `const.py`, `coordinator.py`, `entity.py`,
  `__init__.py`. Add `translations/en.json` with `exceptions.unreachable.message` = "Could not
  reach the speaker. It may be off, out of range, or another app may be connected." (config flow
  strings come in Task 6).
- [ ] **Step 4: Run** `pytest -v` → PASS; `prek run --all-files` → pass.
- [ ] **Step 5: Commit** — `feat: add coordinator with on-demand polling and presence`.

---

### Task 6: Config flow

**Files:**
- Create: `custom_components/soundboks/config_flow.py`, `tests/test_config_flow.py`
- Modify: `custom_components/soundboks/translations/en.json`

**Interfaces:**
- Consumes: `SoundboksClient`, errors, `validate_pin`, `ADVERTISED_SERVICE_UUID`, `DOMAIN`,
  `CONF_PIN`.
- Produces: `class SoundboksConfigFlow(ConfigFlow, domain=DOMAIN)` with steps `bluetooth`,
  `bluetooth_confirm`, `user`, `pin`, `reauth`, `reauth_confirm`, `reconfigure`. Entry
  `unique_id = address`, `title = f"SOUNDBOKS {name}"` where `name` is the advertised local name
  when it starts with `#`, else the address. `data = {CONF_ADDRESS: address}` plus `CONF_PIN` when
  the speaker has one.

Behaviour:
- `bluetooth` → set unique id, abort `already_configured`, → `bluetooth_confirm` (shows the name).
- `user` → `async_discovered_service_info(hass, connectable=True)` filtered on
  `ADVERTISED_SERVICE_UUID` and not yet configured; none → abort `no_devices_found`; else a
  dropdown of addresses labelled with names.
- After a speaker is chosen: probe with a temporary `SoundboksClient(device, None)`:
  `check_supported` (`UnsupportedSpeakerError` → abort `not_supported`), `pin_required`
  (`SpeakerUnreachableError` → form error `cannot_connect`). PIN needed → `pin` step: field
  `pin` (string); `validate_pin` fails → error `invalid_pin_format`; `verify_pin` fails →
  `invalid_pin`; unreachable → `cannot_connect`. Then create entry.
- `reauth_confirm` and `reconfigure`: `pin` form, same validation, then
  `async_update_reload_and_abort` with the new PIN (`reauth_successful` /
  `reconfigure_successful`). Reconfigure with a speaker that has no PIN → removes `CONF_PIN`.
- `translations/en.json`: titles, descriptions, field labels ("PIN — the 4-digit code set in the
  SOUNDBOKS app"), errors and aborts above.

- [ ] **Step 1: Write the failing tests** (patch `async_ble_device_from_address` and
  `async_discovered_service_info` in `config_flow`, use `fake_speaker`):
  - `test_bluetooth_discovery_no_pin` → `CREATE_ENTRY`, title `"SOUNDBOKS #202047"`,
    data `{CONF_ADDRESS: "AA:BB:CC:DD:EE:FF"}`.
  - `test_bluetooth_discovery_with_pin` — security `0x01`, pin `"1234"` → `pin` form; `"12"` →
    error `invalid_pin_format`; `"9999"` → error `invalid_pin`; `"1234"` → entry with `CONF_PIN`.
  - `test_user_step_lists_discovered` / `test_user_step_no_devices` → form / abort
    `no_devices_found`.
  - `test_unreachable_shows_error` → error `cannot_connect`.
  - `test_unsupported_aborts` → abort `not_supported`.
  - `test_already_configured_aborts`.
  - `test_reauth_updates_pin` and `test_reconfigure_updates_pin` → entry data has the new PIN,
    abort reason as above.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `pytest -v` → PASS.
- [ ] **Step 5: Commit** — `feat: add config flow with bluetooth discovery and PIN`.

---

### Task 7: Media player

**Files:**
- Create: `custom_components/soundboks/media_player.py`, `tests/test_media_player.py`

**Interfaces:**
- Consumes: `SoundboksEntity`, coordinator command methods, `raw_to_level`, `level_to_raw`,
  `Input`.
- Produces: `SoundboksMediaPlayer(SoundboksEntity, MediaPlayerEntity)`, `_attr_name = None`
  (entity takes the device name), `device_class = MediaPlayerDeviceClass.SPEAKER`,
  `supported_features = VOLUME_SET | VOLUME_STEP | TURN_OFF`, `volume_step = 0.05`.

Behaviour: `available` is always `True` (an off speaker shows `off`, not unavailable); `state` =
`ON` when `present`, else `OFF`; `volume_level` = `raw_to_level(data.volume)` or `None`; `source`
= active inputs joined, display names `Channel 1`, `Channel 2`, `AUX`, `Bluetooth`, `TeamUp`
(`None` when no input or no data). No `SELECT_SOURCE`. Commands while not present raise
`HomeAssistantError` (translation key `unreachable`) without trying to connect.

- [ ] **Step 1: Write the failing tests:**
  - `test_state_follows_presence` — present → `on`, volume ≈ `0x2d/255`, source `"Bluetooth"`;
    absent → `off`, entity not `unavailable`.
  - `test_set_volume` — `media_player.volume_set` `0.5` → fake write `(VOLUME_UUID, b"\x80")`,
    state attribute updated without waiting for a poll.
  - `test_volume_up` — from raw `0x2d` → write `level_to_raw(0x2d/255 + 0.05)`.
  - `test_turn_off` — write `(POWER_UUID, b"\x00")`, state `off`.
  - `test_set_volume_when_unreachable_raises_ha_error` — fake `unreachable=True` →
    `HomeAssistantError` raised from the service call, not a Bleak exception.
  - `test_command_when_absent_raises_without_connecting` — not present → `HomeAssistantError`,
    connect count 0.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `pytest -v` → PASS.
- [ ] **Step 5: Commit** — `feat: add media player entity`.

---

### Task 8: Extra entities and diagnostics

**Files:**
- Create: `custom_components/soundboks/select.py`, `sensor.py`, `button.py`, `diagnostics.py`,
  `tests/test_entities.py`, `tests/test_diagnostics.py`
- Modify: `custom_components/soundboks/translations/en.json`

**Interfaces:**
- Consumes: `SoundboksEntity`, coordinator commands, enums.
- Produces:
  - `select`: translation keys `sound_profile` (options `power`, `bass_plus`, `indoor`, `custom`;
    names "Power", "Bass+", "Indoor", "Custom") and `stereo_role` (`mono`, `left`, `right`).
    Choosing `custom` raises `ServiceValidationError` (translation key `custom_profile`: "Custom
    EQ can only be set from the SOUNDBOKS app for now").
  - `sensor`: translation key `active_inputs`, state = the same joined names as the media player
    source, `"None"` when no input.
  - `button`: translation key `reboot`, `device_class = ButtonDeviceClass.RESTART`,
    `entity_category = EntityCategory.CONFIG` → `coordinator.async_reboot()`.
  - `diagnostics.async_get_config_entry_diagnostics` → `{"entry": async_redact_data(entry.data,
    {CONF_PIN}), "present": …, "firmware": …, "state": asdict(data) or None}`.
  Unique IDs: `f"{address}_{key}"`; media player uses `address`.

- [ ] **Step 1: Write the failing tests:**
  - `test_profile_select` — current option `power`; select `indoor` → write profile with mode `2`.
  - `test_profile_select_custom_rejected` → `ServiceValidationError`, no write.
  - `test_stereo_select` — select `left` → write `(STEREO_UUID, b"\x01")`.
  - `test_active_inputs_sensor` — inputs `[0, 12]` → `"AUX, Bluetooth"`; `[0, 0]` → `"None"`.
  - `test_reboot_button` — press → writes `b"\x01\x01"` then `b"\x00"`.
  - `test_extras_unavailable_when_absent` — absent → select/sensor/button `unavailable`.
  - `test_diagnostics_redacts_pin` — entry with `CONF_PIN` → output shows `"**REDACTED**"`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `pytest -v` → PASS.
- [ ] **Step 5: Commit** — `feat: add profile, stereo, inputs, reboot and diagnostics`.

---

### Task 9: CI, HACS metadata and public documentation

**Files:**
- Create: `.github/workflows/ci.yml`, `hacs.json`, `.github/ISSUE_TEMPLATE/bug_report.yml`,
  `.github/ISSUE_TEMPLATE/config.yml`, `.github/pull_request_template.md`, `README.md`,
  `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`

**Interfaces:** consumes the finished integration; produces nothing code depends on.

- [ ] **Step 1: `ci.yml`** on push and pull request, `permissions: contents: read`, jobs:
  `lint` (`actions/checkout@v7`, `jdx/mise-action` current major, `prek run --all-files`),
  `tests` (mise, `pip install -r requirements-dev.txt`, `pytest`), `hassfest`
  (`home-assistant/actions/hassfest@master`), `hacs` (`hacs/action@main`,
  `category: integration`, `ignore: brands` until a brand is submitted).
- [ ] **Step 2: `hacs.json`** — `{"name": "SOUNDBOKS", "homeassistant": "2026.10.0",
  "render_readme": true}`.
- [ ] **Step 3: README** — what it does; supported hardware (tested: hardware `5506_DUAL_SPK`,
  firmware `4217000100`; others untested, reports welcome; newer generations unsupported);
  install via HACS custom repository (`https://github.com/Roxxas96/ha-soundboks-integration`,
  category Integration) and manually; setup and PIN; entity table; how the single connection is
  shared (30 s polls, 30 s idle window, close the official app if commands fail); limitations (no
  power on, no Siri volume through HomeKit Bridge yet, v1 scope); troubleshooting (debug logging
  snippet, ESPHome Bluetooth proxies for range); disclaimer and trademark notice from Global
  Constraints; license.
- [ ] **Step 4: CONTRIBUTING** (setup commands from Task 1, running tests, Conventional Commits,
  `cz bump` release flow, protocol doc pointer, "no code or assets from the official app" rule),
  **SECURITY** (report privately via GitHub security advisories; PIN handling note),
  **CHANGELOG** (commitizen header, `## Unreleased`), issue template asking HA version, speaker
  firmware, debug logs, steps; PR template with a checklist (tests, prek, docs).
- [ ] **Step 5: Verify** — `prek run --all-files` (actionlint, check-yaml, typos) and `pytest` →
  pass. Run hassfest locally if Docker is available:
  `docker run --rm -v "$PWD/custom_components:/github/workspace/custom_components" ghcr.io/home-assistant/hassfest`
  → no errors (otherwise note it is unverified until the first push).
- [ ] **Step 6: Commit** — `docs: add README, contributing guide and CI`.

---

### Task 10: Real speaker check (needs the owner)

- [ ] **Step 1:** Ask the owner to install the integration on their HA (copy
  `custom_components/soundboks` or add the repo to HACS once pushed) and restart HA.
- [ ] **Step 2:** With the owner, confirm: discovery shows the speaker; setup (with their PIN if
  any) succeeds; volume from the dashboard changes the speaker; a test automation changes volume;
  turn off powers it off and HA shows `off` at once; turning it back on by hand shows `on` within
  seconds; profile/stereo/reboot work; the official app connects while HA is idle.
- [ ] **Step 3:** Fix anything found (each fix its own `fix:` commit with a test), then report
  results to the owner with any open issues.
