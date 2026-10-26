# Redragon M908

<img width="565" height="513" alt="image" src="https://github.com/user-attachments/assets/f83b1dc4-136b-4c79-8f17-7b82b7bdf04f" />


A bar widget for the [Omarchy](https://omarchy.org) Quattro shell that maps the 13 remappable buttons on the Redragon M908 gaming mouse and switches between named profiles.

Plugin id: `redragon-m908`

## What it does

- Click the bar icon to open a panel with a visual diagram of the M908's side buttons and top button
- Remap any button to a keyboard key by clicking **Press a key…** and pressing the desired key
- Or click **Find on mouse** and press the physical mouse button you want to assign
- Create, load, and delete named profiles — each profile stores the full 13-button mapping
- Restart the `m908d` daemon from the panel if the connection drops
- Mappings apply system-wide via the daemon, including in full-screen games

## Requirements

- Omarchy with the Quattro shell
- A running `m908d` daemon, **version 1.0.0**, whose full source ships in this
  repository under [`daemon/`](daemon/) — see [daemon/README.md](daemon/README.md)
  for install steps, privileges and trust boundaries
- The Redragon M908 mouse connected

## Install

```bash
omarchy plugin add https://github.com/a77lic7ion/omarchy-redragon-m908.git --enable
```

The panel only renders and edits mappings. The daemon that owns the device has to
be running first; install it from [`daemon/`](daemon/README.md) (about a minute,
no build step, standard library only).

## The backend (m908d)

`m908d` is not downloaded from anywhere. It is in this repository, pinned to the
same commit as the panel, so what a reviewer reads is what runs.

- `daemon/m908d` — entry point, JSON control socket, profile application
- `daemon/backend.py` — grabs the mouse keypad node read-only and re-emits
  remapped keys through a virtual uinput keyboard
- `daemon/buttonmap.py` — the 13 button keycodes, read from the hardware
- `daemon/profiles.py` — profile storage in `~/.config/m908`

It runs as your user in a systemd user unit, needs no root, opens no network
socket, never writes to the mouse, and listens on a 0600 socket in
`$XDG_RUNTIME_DIR`. Full detail in [daemon/README.md](daemon/README.md).

## Usage

| Action | How |
| --- | --- |
| Open the panel | Click the bar icon |
| Close the panel | `Escape`, or click the icon again |
| Remap a button | Click a numbered button in the diagram, then press a key or click **Find on mouse** |
| Switch profile | Click a profile chip at the top of the panel |
| Create profile | Type a name and click **Create** |
| Delete profile | Select a profile and click **Delete** |
| Restart daemon | Click the ↻ button in the header |
| From a keybind | `omarchy-shell shell summon redragon-m908 '{}'` |

## Remove

```bash
omarchy plugin remove redragon-m908
```

Profiles are stored by the `m908d` daemon and are not affected by removing the panel.

## Notes on what it touches

- **Network**: none
- **Files read**: none by the panel; the daemon manages its own config
- **Files written**: none by the panel
- **Commands run**: `systemctl --user restart m908d` (only when you click the restart button)
- **IPC**: talks to `m908d` over `$XDG_RUNTIME_DIR/m908.sock`
- **No privileged commands, no config overwriting, no telemetry**

## License

MIT — see [LICENSE](LICENSE).
