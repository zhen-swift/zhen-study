# Setting up the Mac mini

What a ready mini looks like. `/study-setup` (run from the MacBook, in `~/Dev/InfinityCastle`) checks each line
over SSH, changes only what is missing, and checks again after.

**Before it runs,** JC adds a temporary sudo line on the mini. `/study-setup` removes it when it is done:

```bash
ssh -t mini 'echo "$(whoami) ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/zz-study2-setup >/dev/null && sudo chmod 440 /etc/sudoers.d/zz-study2-setup && sudo visudo -c'
```

## First: what the 2026-11-18 run left behind

A `/study-start` run on 2026-11-18 followed the old design (Claude on the mini) part of the way. Its scripts are in
the hub's `Mini/.run/` (`2026-11-18-*.sh`). They are **history**: read them to know what may exist, never run them
again. Each item below has exactly one outcome. Check whether it exists; if it does, do what the row says; if it
does not, there is nothing to do.

| Item the old run may have made | Outcome |
|---|---|
| user `zhenstudy`, standard, not admin | **keep** |
| `/etc/sudoers.d/zhen-study2`, exactly the line below | **keep** (replace it if it differs) |
| `/usr/local/zhen-study2/zhen` | **keep** only if `~zhenstudy/.zhen-study2/build.json` exists, names commit `b6636fa63d5e906a727139a2547490a30fbf0bda`, and its `installed_sha256` equals the installed file's sha256. Then **move** `build.json` to `/Users/Shared/zhen-study2/build.json`. If any of that fails: remove the binary and build again as in *The binary* |
| `~zhenstudy/Dev/InfinityCastle/zhen-core` (the source it was built from) | **keep** if the binary was kept, and add `"source_path"` with this path to `build.json`. Otherwise **remove** |
| `~zhenstudy/zhen-study2-private` | **keep** (mode 700) |
| `~zhenstudy/Dev/InfinityCastle/zhen-study` | **remove**: jobs run from `/Users/Shared/zhen-study2/repo` |
| Claude Code for `zhenstudy`: `~zhenstudy/.local/bin/claude`, `~zhenstudy/.local/share/claude`, `~zhenstudy/.claude`, `~zhenstudy/.claude.json` | **remove** |
| `~zhenstudy/.config/zhen` (token folder) | **remove**. If it holds any file, stop and tell JC: a token reached the mini |
| `~zhenstudy/.zhen-study2` (after `build.json` has moved) | **remove** |
| `~zhenstudy/.gitconfig` | **remove**: the mini never commits |
| Homebrew `gh`, and the `mactex-no-gui` cask | **remove** (`brew uninstall gh`, `brew uninstall --cask mactex-no-gui`): nothing on the mini signs in to GitHub or builds the paper |
| LaunchDaemons `dev.zhen.study2.agent` or `dev.zhen.study2.collect`, in `launchctl` or `/Library/LaunchDaemons/` | **remove** (`bootout`, then delete the plist) |
| `/tmp/zhen-study2-build.log` | **remove** |
| anything else under `/Users/zhenstudy` | leave it, and list it in the report |

Record every outcome (kept, moved, removed, absent) in `mini/MACHINE.md`.

## The machine

| Must be true | Check with |
|---|---|
| network time on, NTP offset within `config.json` | `sntp time.apple.com` (the zone itself is whatever the mini is set to) |
| never sleeps; restarts after power loss | `pmset -g`: `sleep 0`, `disksleep 0`, `autorestart 1` |
| no automatic macOS or App Store installs | `com.apple.SoftwareUpdate` `AutomaticallyInstallMacOSUpdates` and `CriticalUpdateInstall` false; `com.apple.commerce` `AutoUpdate` false |
| `config.json`'s `home.interface` is Ethernet, carries the default route, and has an address in `home.cidr` | `networksetup -listallhardwareports`, `route -n get default`, `ipconfig getifaddr` |
| no VPN, no network filter or system extension | `scutil --nc list`, `systemextensionsctl list` |
| tools: Homebrew, `nmap`, `lima`, `jq`, `python3`, `swift`, `git`, and nothing the study does not use | each runs; Homebrew under `/opt/homebrew` |

## The study account and its root

- `zhenstudy`: a **standard, non-admin** user with a random password nobody keeps (`openssl rand -base64 24`,
  passed straight to `sysadminctl`). Nobody logs in as it.
- `/etc/sudoers.d/zhen-study2`, mode 0440, `root:wheel`, checked with `visudo -c -f` before install, exactly:
  ```
  zhenstudy ALL=(root) NOPASSWD: /opt/homebrew/bin/nmap, /usr/sbin/tcpdump, /usr/sbin/arp, /usr/bin/wdutil
  ```
  zhen's own line comes at the freeze.
- `/Users/zhenstudy/zhen-study2-private`, owned by `zhenstudy`, mode 700.

## The binary, built from source

Skip this section if the binary was kept above.

- `/Users/Shared/zhen-study2/zhen-core`: a clone of `github.com/zhen-swift/zhen-core` at tag `0.8.1`, which must
  resolve to `b6636fa63d5e906a727139a2547490a30fbf0bda` (**anything else is a stop**), with a clean tree.
- Built once with exactly `swift build -c release`, installed as `/usr/local/zhen-study2/zhen`, 0755, `root:wheel`.
- `/Users/Shared/zhen-study2/build.json`: tag, commit, build command, `swift --version`, `sw_vers`, model, the
  sha256 of the **installed** file, `zhen --version`. `STEPS.md` step S0 turns it into the freeze record.

A build that fails is a stop: report it, change nothing in zhen-core.

## The runner

- `/Users/Shared/zhen-study2/`, owned by the admin account, group `staff`.
- `/Users/Shared/zhen-study2/repo`: a clone of `github.com/zhen-swift/zhen-study`, owned by the admin account.
- Then, as root: `bash /Users/Shared/zhen-study2/repo/v2/runner/install.sh`. It creates the job folders and loads
  the LaunchDaemon `dev.zhen.study2.runner`. With the queue empty, it idles.

## Close

Remove `/etc/sudoers.d/zz-study2-setup`, then show `sudo -n true` now **fails**.
