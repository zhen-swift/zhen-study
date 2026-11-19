# The Mac mini, as `/study-setup` found and left it

2026-11-18, 20:50–21:00 `-0600` (`America/Mexico_City`), from the MacBook over SSH. The scripts that ran are in the
hub's `Mini/.run/2026-11-18-2050-explore.sh`, `-2053-explore-2.sh`, `-2056-apply.sh` and `-2059-close.sh`.

## Host

| | |
|---|---|
| Model | `Mac18,5`, Apple silicon (arm64) |
| macOS | 27.2.1 (26B131); FileVault on |
| Zone | `America/Mexico_City`; network time on; NTP offset +0.00008 s (limit 1.0 s) |
| Power | `sleep 0`, `disksleep 0`, `autorestart 1` |
| Updates | `AutomaticallyInstallMacOSUpdates` 0, `CriticalUpdateInstall` 0, `com.apple.commerce AutoUpdate` 0 |
| Network | `en0` (Ethernet) `10.10.30.100`, default route via `10.10.30.1` on `en0`; inside `config.json` → `home.cidr` |
| VPN, filters | no `scutil --nc` services; 0 system extensions |
| Tools | Homebrew `/opt/homebrew`; nmap 7.993, lima 2.3.0, python 3.15.2 (Homebrew, a dependency of nmap); jq 1.7.1 (`/usr/bin`), Swift 6.4.2 (`/usr/bin`), git 2.54.0 (`/usr/bin`) |
| Also installed | Homebrew `zhen` 0.9.0 from the `zhen-swift/zhen` tap (installed 2026-11-18 18:53, before the old run). Not named in `SETUP.md`; **kept by JC's decision**. For `zhenstudy` a bare `zhen` resolves to it, so the harness must call `/usr/local/zhen-study2/zhen` by full path |

## The 2026-11-18 leftovers

| Item | Outcome |
|---|---|
| user `zhenstudy` (uid 502, standard, not admin) | kept |
| `/etc/sudoers.d/zhen-study2` (exact, 0440 `root:wheel`) | kept |
| `/usr/local/zhen-study2/zhen` | kept: `build.json` named `b6636fa…` and its `installed_sha256` equalled the file's (`e10ac616…`) |
| `~zhenstudy/.zhen-study2/build.json` | moved to `/Users/Shared/zhen-study2/build.json`, with `source_path` added |
| `~zhenstudy/Dev/InfinityCastle/zhen-core` | kept (HEAD = tag `0.8.1` = `b6636fa…`, clean tree) |
| `~zhenstudy/zhen-study2-private` | kept (700, empty) |
| `~zhenstudy/Dev/InfinityCastle/zhen-study` | removed |
| `~zhenstudy/.local/bin/claude`, `.local/share/claude`, `.claude`, `.claude.json` | removed |
| `~zhenstudy/.config/zhen` | removed; it held **no files**, so no token reached the mini |
| `~zhenstudy/.zhen-study2` (after the move; its `logs/` was empty) | removed |
| `~zhenstudy/.gitconfig` | removed |
| Homebrew `gh` | removed |
| `mactex-no-gui` cask | absent |
| LaunchDaemons `dev.zhen.study2.agent`, `.collect` | absent (not loaded, no plist) |
| `/tmp/zhen-study2-build.log` | removed |

Left under `/Users/zhenstudy`, listed as `SETUP.md` asks: `.local/state/claude` and `.cache/claude/staging`
(Claude Code's state and cache, outside the four removed paths), `.swiftpm/` and `Library/org.swift.swiftpm`
(from the build), the empty `.config/`, `.local/bin/`, `.local/share/`, `.CFUserTextEncoding`, the standard
folders. `zhenstudy` is also in `com.apple.sharepoint.group.1`, `.2` and `_lpoperator`, as macOS adds new users.

## The account and its root

- `zhenstudy`: standard, not admin, created by the old run with `sysadminctl` and an `openssl rand -base64 24`
  password nobody saw (`Mini/.run/2026-11-18-1913-account.sh`).
- `sudo -l -U zhenstudy`: `(root) NOPASSWD: /opt/homebrew/bin/nmap, /usr/sbin/tcpdump, /usr/sbin/arp, /usr/bin/wdutil`.

## The binary

Kept from the old run, so *The binary* section was skipped. Recorded in `../frozen-binary-v2.json`.

## The runner

- `/Users/Shared/zhen-study2/`, `jc-mini:staff`; `repo/` cloned from `github.com/zhen-swift/zhen-study` at
  `6259188`, `jc-mini:staff`.
- `install.sh` made `queue running done failed data logs history` (`zhenstudy:staff`, 2775) and loaded
  `dev.zhen.study2.runner`: state `running`, queue empty, no log lines.
- Found: as `zhenstudy`, git refuses `repo/` (dubious ownership), so `runner.sh` would log `"repo":"none"`. Fixed in
  `runner/runner.sh` on the MacBook (see `LEDGER.md`); the mini gets it when `/study-run` pins the repo.

## Close

`/etc/sudoers.d/zz-study2-setup` removed; `sudo -n true` fails. `/etc/sudoers.d/` holds only `zhen-study2`.
