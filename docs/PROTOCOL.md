# Speaker protocol

What this integration sends to the speaker and why. It covers only what the integration uses, on
the generation it was tested with (hardware `5506_DUAL_SPK`, firmware `4217000100`). Newer
SOUNDBOKS generations use a different layout and are not covered.

The details were worked out for interoperability, by observing the speaker. No code from the
official app is included in this project.

## Connection

- The speaker advertises the service `f5c26570-64ec-4906-b998-6a7302879a2b`, with a local name
  of `#` followed by its serial number (for example `#202047`).
- There is no pairing. Unless a PIN is set, anything that connects can read and write.
- **Only one central can be connected at a time.** While Home Assistant is connected, phones can't
  connect, and the other way round. This is why the integration connects only briefly
  ([README](../README.md#how-the-connection-is-shared)).

## Characteristics

All values are raw bytes.

| Characteristic | UUID | Access | Layout |
|---|---|---|---|
| Volume | `7649b19f-c605-46e2-98f8-6c1808e0cfb4` | read, write, notify | 1 byte, 0–255 |
| Power | `11ad501d-fa86-43cc-8d92-5a27ee672f1a` | read, write | see below |
| Sound profile | `57a394fb-6d89-4105-8f07-bf730338a9b2` | read, write | 7 bytes, see below |
| Stereo role | `7d0d651e-62ae-4ef2-a727-0e8f3e9b4dfb` | read, write, notify | 1 byte: 0 mono, 1 left, 2 right |
| Sound status | `8d36814f-3741-4cb5-a018-ef4a2d8e24f1` | read, notify | byte 1: active inputs bitfield |
| Security level | `93aa965c-98b8-4433-b6bb-41ce61a8db9a` | read, notify | bitfield: 1 PIN set, 2 locked |
| Firmware version | `8980ccc7-e6d4-4f9d-9540-3c62fa0a5a74` | read | ASCII, e.g. `2.4.2` |
| Serial TX | `49535343-8841-43f4-a8d4-ecbe34729bb3` | write | commands, see [PIN](#pin) |
| Serial RX | `49535343-1e4d-4bd9-ba61-23c647249616` | notify | responses |

### Volume

The volume is 0–255, and each click of the physical knob moves it by 7. The speaker notifies every
change, including knob turns. It goes back to `0x2d` (about 18 %) at every power-on.

### Power

- Writing `00` turns the speaker off at once. It must be a write *with* response; a write without
  response is ignored.
- The speaker never answers that write. It drops the connection instead, so a disconnect right
  after the write means it worked.
- Writing `01 01` sets "auto-boot once": the speaker stays on, but the next power-off restarts it.
  Following it with `00` is a remote reboot. This write also drops the connection.
- **The speaker can't be turned on over Bluetooth**: its radio is off along with it.

### Sound profile

Seven bytes: a mode, then six EQ band values. Modes are 0 Power, 1 Bass+, 2 Indoor and 3 custom.
The bands only apply in custom mode. To switch preset, the integration rewrites the mode byte and
sends back the bands unchanged, so the speaker keeps its stored custom EQ.

### Sound status

The second byte is a bitfield of the inputs playing right now: 1 channel 1, 2 channel 2, 4 AUX,
8 Bluetooth, 16 TeamUp.

## PIN

The PIN is optional and has 4 digits; it is set from the SOUNDBOKS app.

1. Read the security level. If bit 1 is clear, there is no PIN: nothing else to do.
2. Subscribe to serial RX. Keep that subscription for the whole connection: unsubscribing drops
   the link and the authentication with it.
3. Write `aup` followed by the PIN's ASCII digits to serial TX, e.g. `aup1234` (write with
   response).
4. The answer arrives on RX: `01 00 00 00 00` accepts the PIN, a packet starting with `02` refuses
   it.

Until a PIN is accepted, reads still work but every write fails with ATT error `0x81` and changes
nothing. Authentication lasts until the connection closes.

## Advertising while connected

Not yet checked. Whether the speaker keeps advertising while another app is connected decides how
long Home Assistant keeps showing it as on after the advertisements stop.
