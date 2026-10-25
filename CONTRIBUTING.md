# Contributing

Bug reports, test reports on other speakers and pull requests are all welcome.

## Set up

You need [mise](https://mise.jdx.dev/). Then:

```bash
mise install                         # Python and prek, pinned in mise.toml; creates .venv
pip install -r requirements-dev.txt  # inside the mise-activated .venv
prek install                         # git hooks: ruff, typos, gitleaks, commitizen, actionlint…
```

## Checks

```bash
pytest                   # the test suite; no speaker needed, the BLE stack is faked
prek run --all-files     # every lint hook
```

CI runs both, plus Home Assistant's `hassfest` and the HACS validation.

## Layout

| File | Role |
|---|---|
| `protocol.py` | Byte encoding and decoding. No BLE, no Home Assistant |
| `client.py` | The one BLE connection: connect on demand, PIN, idle timeout |
| `coordinator.py` | Polling, presence from advertisements, commands |
| `config_flow.py` | Discovery and setup |
| `media_player.py`, `select.py`, `sensor.py`, `button.py` | Entities |

`tests/conftest.py` has a `FakeSpeaker` that stands in for the BLE stack: start there when writing
a test.

## Rules

- **Nothing from the official SOUNDBOKS app**: no code, assets, logos or identifiers copied from
  it. Describe protocol facts in your own words and names. This is what keeps the project
  shareable.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`,
  `docs:`…). The commit-msg hook checks it.
- New behaviour comes with a test. Protocol findings go in [docs/PROTOCOL.md](docs/PROTOCOL.md).
- If you changed how the integration talks to the speaker, say in the PR which speaker and
  firmware you tested on.

## Releasing

```bash
cz bump        # bumps the version in manifest.json, updates CHANGELOG.md, tags vX.Y.Z
git push --follow-tags
```

Then create a GitHub release from the tag: that's what HACS offers to users.
