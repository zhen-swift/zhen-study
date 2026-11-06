# Starting study 2 on a fresh Mac mini

This file makes the repository self-starting. On the study Mac mini, in an admin account, JC first adds a temporary passwordless sudo line for that account, so
the setup never needs a password:

```bash
echo "$(whoami) ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/zz-study2-setup >/dev/null && sudo chmod 440 /etc/sudoers.d/zz-study2-setup && sudo visudo -c
```

Then opens Claude and says:

> Clone github.com/zhen-swift/zhen-study and follow v2/START.md.

Everything else is here. The run contract is `RUN.md`; this file only gets the machine to the point where the
unattended agent takes over.

```
 admin account, Claude, JC present                                  zhenstudy, unattended
 ───────────────────────────────────────────────────────────        ─────────────────────
 explore ─► machine ─► account ─► build zhen ─► clone ─► tokens (JC) ─► daemons ─► study runs
```

## How to work

- **Explore first.** For every item below, check whether it is already true before changing anything. Leave what
  is right alone, change only what is missing, and check each change after making it.
- Use `sudo -n` only. The temporary grant `/etc/sudoers.d/zz-study2-setup` makes it work; if it is missing, stop
  and tell JC. No password is ever asked for, typed or stored.
- Anything found that could affect a network measurement and is not covered here (another VPN app, a firewall
  rule, low disk): do not fix it. Report it.
- Never scan a network (`nmap --version` is fine), or sign in to anything for anyone. The one zhen build is
  section 3's; nothing else is built.
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

- A **standard, non-admin** user `zhenstudy`. If it does not exist, create it with `sysadminctl`, with a
  random password you do not keep (`openssl rand -base64 24`, passed straight to `sysadminctl`, never shown or
  stored). Nobody logs in as `zhenstudy`; JC resets it from the admin account if ever needed.
- `/etc/sudoers.d/zhen-study2`, mode 0440, `root:wheel`, exactly:
  ```
  zhenstudy ALL=(root) NOPASSWD: /opt/homebrew/bin/nmap, /usr/sbin/tcpdump, /usr/sbin/arp, /usr/bin/wdutil
  ```
  Checked with `visudo -c -f` before it is installed. zhen's own line is added at the freeze stop, not now.

## 3 · The binary, built from source

Study 2 measures **zhen-core 0.8.1**, built here, once, before the study starts. It is never rebuilt after that.

- Clone `github.com/zhen-swift/zhen-core` into `~zhenstudy/Dev/InfinityCastle/zhen-core`, as `zhenstudy`.
- Check out the tag `0.8.1` and confirm it resolves to commit `b6636fa63d5e906a727139a2547490a30fbf0bda`. **Any other commit is a stop.**
- Confirm the tree is clean (`git status --porcelain` empty), then build with exactly `swift build -c release`.
- Install `.build/release/zhen` as `/usr/local/zhen-study2/zhen`, mode 0755, `root:wheel`.
- Record for the agent, in `~zhenstudy/.zhen-study2/build.json`: tag, commit, build command, `swift --version`,
  `sw_vers`, model, the sha256 of the **installed** file, and `zhen --version`. The agent turns this into the
  freeze record in its first step.

A build that fails is a stop: report the error, change nothing in zhen-core.

## 4 · The clones, as `zhenstudy`

- `~/Dev/InfinityCastle/zhen-study` — this repository, on `main`
- `~/Dev/InfinityCastle/zhen-core` — the source the binary was built from (section 3), left at the tag
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

## 7 · Close the setup

Remove `/etc/sudoers.d/zz-study2-setup`, then confirm `sudo -n true` now **fails** for the admin account. This is
the last thing you do with root. The study's own grant (`zhen-study2`) stays.

## 8 · Report to JC

In plain words: what was already there, what you changed, what you flagged, that the setup grant is gone, and that
the study is running. Commit nothing from the admin
account.
