# Security

Please report security problems privately through
[GitHub security advisories](https://github.com/Roxxas96/ha-soundboks-integration/security/advisories/new),
not as public issues. I'll answer as soon as I can.

## How the PIN is handled

- If your speaker has a PIN, the integration stores it in Home Assistant's config entry, like any
  other integration credential, and sends it to the speaker at the start of each connection.
- It is removed from diagnostics downloads. It is never logged.
- The integration can't set, change or remove a PIN, and has no way around one: without the right
  PIN it can read the speaker, but not change anything.
- Bluetooth LE between Home Assistant and the speaker is not encrypted by the speaker. Anyone in
  radio range can see the PIN go by. That's a limit of the speaker, not something this integration
  can fix.
