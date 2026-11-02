# Setting up the study Mac mini

Done once, by JC. About twenty minutes. After this, the run starts with one command (bottom of this file).

## 1 · As `jc-mini` (admin)

```bash
set -euo pipefail
# clock and power
sudo systemsetup -setusingnetworktime on
sudo pmset -a sleep 0 disksleep 0 autorestart 1 womp 1
# no automatic macOS or app installs during the study
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates -bool false
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate CriticalUpdateInstall -bool false
sudo defaults write /Library/Preferences/com.apple.commerce AutoUpdate -bool false
# tools: Homebrew, the scanner under comparison, the testbed, GitHub, TeX for the paper
NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
eval "$(/opt/homebrew/bin/brew shellenv)"
brew install nmap lima gh jq
brew install --cask mactex-no-gui
# the study user — you type its password at the prompt
sudo sysadminctl -addUser zhenstudy -fullName "Zhen Study" -password -
# root grant, base set (zhen's own line is added at the freeze stop)
printf 'zhenstudy ALL=(root) NOPASSWD: /opt/homebrew/bin/nmap, /usr/sbin/tcpdump, /usr/sbin/arp, /usr/bin/wdutil\n' > /tmp/zhen-study2
sudo visudo -c -f /tmp/zhen-study2 && sudo install -m 0440 -o root -g wheel /tmp/zhen-study2 /etc/sudoers.d/zhen-study2
sudo mkdir -p /usr/local/zhen-study2
```

## 2 · The two frozen binaries

Copy from the MacBook to the mini's `~/Downloads` (AirDrop or your remote tool):

- `~/Dev/zhen-study2-binary/.build/release/zhen`
- `~/Dev/InfinityCastle-collection/Packages/netsanity-cli/.build/release/netsanity`

```bash
sudo install -m 0755 -o root -g wheel ~/Downloads/zhen      /usr/local/zhen-study2/zhen-0.8.0
sudo install -m 0755 -o root -g wheel ~/Downloads/netsanity /usr/local/zhen-study2/netsanity-0.4.0
shasum -a 256 /usr/local/zhen-study2/*
```

Must print `e1f95ea9…742c` for zhen and `b4220600…6eff6e4ed` for netsanity. The agent checks again in its first step.

## 3 · As `zhenstudy`

Log in to `zhenstudy` once through Screen Sharing and leave the session logged in (the testbed VMs are known to
run inside a login session; the agent's first step tests whether they also run without one).

**GitHub token:** fine-grained, created on github.com:
`zhen-swift/zhen-study` — Contents read/write, Pull requests read/write, Issues read ·
`zhen-swift/zhen-core` — Contents read.

```bash
curl -fsSL https://claude.ai/install.sh | bash
~/.local/bin/claude setup-token              # sign in; it prints a long-lived token
mkdir -p ~/.config/zhen && chmod 700 ~/.config/zhen
read -rs T && printf %s "$T" > ~/.config/zhen/claude-token && chmod 600 ~/.config/zhen/claude-token && unset T   # paste the Claude token
read -rs G && printf %s "$G" | /opt/homebrew/bin/gh auth login --with-token && unset G                          # paste the GitHub token
git config --global user.name  "Juan Carlos Estévez Rodríguez"
git config --global user.email "jc_mex_root@proton.me"
```

## 4 · Start — the one command

As `zhenstudy`:

```bash
/opt/homebrew/bin/gh repo clone zhen-swift/zhen-study ~/Dev/zhen-study -- -b study2 && ~/Dev/zhen-study/v2/agent/start.sh install
```

It installs the hourly LaunchAgent and starts the first run. From then on the run is in `v2/LEDGER.md` and
`v2/STATE` on the `study2` branch.
