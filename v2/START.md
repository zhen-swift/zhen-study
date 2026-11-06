# Starting study 2 on a fresh Mac mini

This file makes the repository self-starting. On the study Mac mini, in an admin account, JC opens Claude and
says:

> Clone github.com/zhen-swift/zhen-study and follow v2/START.md. The sudo password is [PASSWORD].

Everything else is here. The run contract is `RUN.md`; this file only gets the machine to the point where the
unattended agent takes over.

```
 admin account, Claude, JC present                                  zhenstudy, unattended
 ───────────────────────────────────────────────────────────        ─────────────────────
 explore ─► machine ─► account ─► binary ─► clone ─► tokens (JC) ─► daemons ─► study runs
```

## How to work

- **Explore first.** For every item below, check whether it is already true before changing anything. Leave what
  is right alone, change only what is missing, and check each change after making it.
- Use the sudo password only through `sudo -S`, and never write it into a file, script, log or commit.
- Anything found that could affect a network measurement and is not covered here (another VPN app, a firewall
  rule, low disk): do not fix it. Report it.
- Never scan a network (`nmap --version` is fine), build a zhen binary, or sign in to anything for anyone.
- This is the only part of study 2 with a person present. Ask JC only where this file says to.

## 1 · The machine

| Must be true | Check with |
|---|---|
| zone `America/Los_Angeles`, network time on, offset under 1 s | `readlink /etc/localtime`, `sntp time.apple.com` |
| never sleeps; restarts after power loss | `pmset -g`: `sleep 0`, `disksleep 0`, `autorestart 1` |
| no automatic macOS or App Store installs | `com.apple.SoftwareUpdate` `AutomaticallyInstallMacOSUpdates` and `CriticalUpdateInstall` false; `com.apple.commerce` `AutoUpdate` false |
| `en0` is Ethernet and carries the default route | `networksetup -listallhardwareports`, `route -n get default` |
| no VPN, no network filter or system extension | `scutil --nc list`, `systemextensionsctl list` |
| tools: Homebrew, `nmap`, `lima`, `gh`, `jq`, `pdflatex`, `python3`, `swift`, `git` | each runs; Homebrew under `/opt/homebrew`; TeX from the `mactex-no-gui` cask |

## 2 · The study account

- A **standard, non-admin** user `zhenstudy`. If it does not exist, create it with `sysadminctl`, with the same
  password as the admin account for now, and tell JC to change it.
- `/etc/sudoers.d/zhen-study2`, mode 0440, `root:wheel`, exactly:
  ```
  zhenstudy ALL=(root) NOPASSWD: /opt/homebrew/bin/nmap, /usr/sbin/tcpdump, /usr/sbin/arp, /usr/bin/wdutil
  ```
  Checked with `visudo -c -f` before it is installed. zhen's own line is added at the freeze stop, not now.

## 3 · The binary

The frozen zhen 0.8.0 is attached to this repository's release `study2-binary`:

```
https://github.com/zhen-swift/zhen-study/releases/download/study2-binary/zhen-0.8.0
sha256 e1f95ea922a4a8764022a877a712e9c39f00352c9a0b955eee615555934a742c
```

Download it, check the sha256 (**a mismatch is a stop**: do not install it), and install it as
`/usr/local/zhen-study2/zhen-0.8.0`, mode 0755, `root:wheel`. Run `--version` and note it.

## 4 · The clones, as `zhenstudy`

- `~/Dev/InfinityCastle/zhen-study` — this repository, on `main`
- `~/Dev/InfinityCastle/zhen-core` — read-only reference, on `main`
- git identity: the name and email of this repository's latest commit (`git log -1 --format='%an %ae'`)
- folders: `~/.zhen-study2/logs`, `~/zhen-study2-private` (700), `~/.config/zhen` (700)
- Claude Code installed for `zhenstudy` (`curl -fsSL https://claude.ai/install.sh | bash`), not signed in

## 5 · Tokens — the one thing JC does

Tell JC to open a **separate** Terminal on the mini and run:

```bash
sudo -u zhenstudy -H bash ~zhenstudy/Dev/InfinityCastle/zhen-study/v2/agent/tokens.sh
```

It asks for two tokens and stores them without echoing. Wait until JC says it is done. Then check that both files
exist with mode 600, **without reading them**:
`~zhenstudy/.config/zhen/claude-token`, `~zhenstudy/.config/zhen/gh-token`.

## 6 · Hand over

```bash
sudo ~zhenstudy/Dev/InfinityCastle/zhen-study/v2/agent/start.sh install
```

This installs two LaunchDaemons that run as `zhenstudy` with nobody logged in: the hourly agent tick and the
collection runner. The first tick starts at once: it cuts `study2` from `main`, and the agent begins at `BRIEF.md`
step S0.

Check `sudo launchctl print system/dev.zhen.study2.agent` shows the job, and that
`~zhenstudy/.zhen-study2/logs/start.log` has a "starting agent" line.

## 7 · Report to JC

In plain words: what was already there, what you changed, what you flagged, and that the study is running. Remind
JC to change the passwords. Commit nothing from the admin account.
