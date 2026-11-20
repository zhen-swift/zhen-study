#!/usr/bin/env python3
"""/study-sync's privacy check on copied files. Exit 1 on any hit.

    python3 v2/harness/privacy.py [--rewrite] FILE...

Finds hardware addresses and addresses inside `config.json`'s `home.cidr`. With --rewrite, a lima VM's hardware
address (52:55:55:…) becomes `vm-` + sha256(two-digit colon form)[:12], the scheme of every committed copy, and any
other hardware address `redacted-host-mac`. Home addresses are only reported, never rewritten: phase 3's data must
arrive hashed.
"""
import hashlib, ipaddress, json, re, sys
from pathlib import Path
MAC = re.compile(r'(?<![0-9A-Fa-f:])([0-9A-Fa-f]{1,2}(?::[0-9A-Fa-f]{1,2}){5})(?![0-9A-Fa-f:])')
IP4 = re.compile(r'(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])')
HOME = ipaddress.ip_network(json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text())["home"]["cidr"])
def norm(m): return ":".join(o.zfill(2) for o in m.lower().split(":"))
def sub(m):
    n = norm(m.group(1))
    return "vm-" + hashlib.sha256(n.encode()).hexdigest()[:12] if n.startswith("52:55:55:") else "redacted-host-mac"
rewrite = sys.argv[1:2] == ["--rewrite"]
hits = 0
for f in sys.argv[2 if rewrite else 1:]:
    p = Path(f)
    try: t = p.read_text()
    except UnicodeDecodeError: print(f"BINARY {f}"); hits += 1; continue
    macs = sorted({norm(m) for m in MAC.findall(t)})
    home = sorted({a for a in IP4.findall(t) if all(int(x) < 256 for x in a.split(".")) and ipaddress.ip_address(a) in HOME})
    if home: print(f"HOME {f}: {home}"); hits += 1
    if macs:
        if rewrite: p.write_text(MAC.sub(sub, t)); print(f"rewrote {f}: {len(macs)} macs ({sum(not m.startswith('52:55:55:') for m in macs)} non-VM)")
        else: print(f"MAC {f}: {macs}"); hits += 1
print(f"{hits} files with hits")
sys.exit(1 if hits else 0)
