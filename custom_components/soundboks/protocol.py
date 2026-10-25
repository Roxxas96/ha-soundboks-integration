"""The speaker's BLE protocol: characteristic UUIDs and their byte layouts.

Pure encoding and decoding, no BLE and no Home Assistant, so every rule here is unit-tested on its
own. docs/PROTOCOL.md describes the protocol in prose.
"""

from dataclasses import dataclass
from enum import IntEnum, IntFlag

ADVERTISED_SERVICE_UUID = "f5c26570-64ec-4906-b998-6a7302879a2b"
VOLUME_UUID = "7649b19f-c605-46e2-98f8-6c1808e0cfb4"
POWER_UUID = "11ad501d-fa86-43cc-8d92-5a27ee672f1a"
PROFILE_UUID = "57a394fb-6d89-4105-8f07-bf730338a9b2"
STEREO_UUID = "7d0d651e-62ae-4ef2-a727-0e8f3e9b4dfb"
INPUTS_UUID = "8d36814f-3741-4cb5-a018-ef4a2d8e24f1"
SECURITY_UUID = "93aa965c-98b8-4433-b6bb-41ce61a8db9a"
# Serial command channel: commands are written to TX, responses arrive as RX notifications
SERIAL_TX_UUID = "49535343-8841-43f4-a8d4-ecbe34729bb3"
SERIAL_RX_UUID = "49535343-1e4d-4bd9-ba61-23c647249616"
FIRMWARE_UUID = "8980ccc7-e6d4-4f9d-9540-3c62fa0a5a74"
# A speaker without these is another generation, which this integration doesn't speak
REQUIRED_UUIDS = (VOLUME_UUID, POWER_UUID, PROFILE_UUID)

POWER_OFF = b"\x00"
# Power stays on, but the next power-off restarts the speaker once
AUTO_BOOT_ONCE = b"\x01\x01"

MAX_RAW_VOLUME = 255
PROFILE_LENGTH = 7  # mode byte, then six EQ band bytes
PIN_ENABLED = 0x01  # security level bit
PIN_LENGTH = 4
AUTH_ACCEPTED = b"\x01\x00\x00\x00\x00"
ERROR_RESPONSE = 0x02


class SoundProfile(IntEnum):
    """The profile mode byte; band bytes only apply to CUSTOM."""

    POWER = 0
    BASS_PLUS = 1
    INDOOR = 2
    CUSTOM = 3


class StereoRole(IntEnum):
    MONO = 0
    LEFT = 1
    RIGHT = 2


class Input(IntFlag):
    """Audio inputs currently playing."""

    CHANNEL_1 = 1
    CHANNEL_2 = 2
    AUX = 4
    BLUETOOTH = 8
    TEAMUP = 16


@dataclass(frozen=True)
class SpeakerState:
    volume: int  # raw, 0-255
    profile: SoundProfile
    stereo: StereoRole
    inputs: Input


class SoundboksError(Exception):
    """Base for every error talking to the speaker."""


class SpeakerUnreachableError(SoundboksError):
    """No connection: the speaker is off, out of range, or another app holds it."""


class PinRequiredError(SoundboksError):
    """The speaker has a PIN and none was given."""


class InvalidPinError(SoundboksError):
    """The speaker refused the PIN."""


class UnsupportedSpeakerError(SoundboksError):
    """The speaker lacks the characteristics this integration needs."""


class ProtocolError(SoundboksError):
    """The speaker sent bytes that don't match the expected layout."""


def level_to_raw(level: float) -> int:
    """Home Assistant's 0.0-1.0 volume to the speaker's byte, clamped."""
    return round(min(max(level, 0.0), 1.0) * MAX_RAW_VOLUME)


def raw_to_level(raw: int) -> float:
    return raw / MAX_RAW_VOLUME


def _single_byte(data: bytes, what: str) -> int:
    if len(data) != 1:
        raise ProtocolError(f"{what}: expected 1 byte, got {data.hex() or 'nothing'}")
    return data[0]


def decode_volume(data: bytes) -> int:
    return _single_byte(data, "volume")


def _check_profile(data: bytes) -> None:
    if len(data) != PROFILE_LENGTH:
        raise ProtocolError(f"profile: expected {PROFILE_LENGTH} bytes, got {data.hex()}")


def decode_profile(data: bytes) -> SoundProfile:
    _check_profile(data)
    try:
        return SoundProfile(data[0])
    except ValueError:
        raise ProtocolError(f"profile: unknown mode {data[0]}") from None


def encode_profile(current: bytes, profile: SoundProfile) -> bytes:
    """Switch to a preset, keeping the custom EQ bands the speaker already stores."""
    if profile is SoundProfile.CUSTOM:
        raise ValueError("custom EQ bands are not supported")
    _check_profile(current)
    return bytes([profile]) + current[1:]


def decode_stereo(data: bytes) -> StereoRole:
    value = _single_byte(data, "stereo role")
    try:
        return StereoRole(value)
    except ValueError:
        raise ProtocolError(f"stereo role: unknown value {value}") from None


def decode_inputs(data: bytes) -> Input:
    """The second byte of the sound status is the active inputs; unknown bits are ignored."""
    if len(data) < 2:
        raise ProtocolError(f"sound status: expected at least 2 bytes, got {data.hex()}")
    known = 0
    for member in Input:
        known |= member
    return Input(data[1] & known)


def pin_required(security: bytes) -> bool:
    return bool(security[:1] and security[0] & PIN_ENABLED)


def validate_pin(pin: str) -> str:
    """The PIN without surrounding spaces; ValueError unless it is exactly 4 digits."""
    pin = pin.strip()
    if len(pin) != PIN_LENGTH or not pin.isascii() or not pin.isdigit():
        raise ValueError(f"a PIN is {PIN_LENGTH} digits")
    return pin


def auth_command(pin: str) -> bytes:
    return b"aup" + validate_pin(pin).encode()


def auth_accepted(packet: bytes) -> bool:
    """The speaker's answer to auth_command: True accepted, False refused."""
    if packet == AUTH_ACCEPTED:
        return True
    if packet[:1] == bytes([ERROR_RESPONSE]):
        return False
    raise ProtocolError(f"unexpected answer to the PIN: {packet.hex()}")
