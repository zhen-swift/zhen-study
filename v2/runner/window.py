#!/usr/bin/env python3
"""May a job of this arm start now?  Exit 0 = go, 1 = not now (try later), 2 = refused (the job is wrong).

    python3 v2/runner/window.py <home|testbed> <minutes> [<ntp-offset-seconds>]

Reads v2/config.json. The clock is the mini's own local zone, whatever it is set to. Prints one JSON line with
the decision, the zone and the UTC offset, which the runner appends to its log. Standard library only.
"""
import json, sys, time
from pathlib import Path

CFG = json.loads((Path(__file__).resolve().parent.parent / "config.json").read_text())


def decide(arm, minutes, ntp, ts=None, cfg=CFG):
    ts = time.time() if ts is None else ts
    lt, lt_end = time.localtime(ts), time.localtime(ts + minutes * 60)
    out = {"arm": arm, "now": time.strftime("%Y-%m-%dT%H:%M:%S%z", lt), "zone": lt.tm_zone,
           "utc_offset": time.strftime("%z", lt), "minutes": minutes, "ntp_offset_s": ntp}

    def done(code, why):
        out.update(decision={0: "go", 1: "wait", 2: "refused"}[code], why=why)
        return code, out

    if arm == "testbed":
        return done(0, "testbed runs at any time")
    if arm != "home":
        return done(2, f"unknown arm {arm!r}")
    if minutes <= 0 or minutes > 24 * 60:
        return done(2, f"job length {minutes} min is not plausible")

    limit = cfg["clock"]["max_ntp_offset_seconds"]
    if ntp is None or abs(ntp) > limit:
        return done(1, f"NTP offset {ntp} s is unknown or over {limit} s")
    if lt.tm_gmtoff != lt_end.tm_gmtoff:
        return done(1, "the UTC offset changes during this job (daylight saving); not tonight")

    w = cfg["home"]["window"]
    start = sum(int(x) * m for x, m in zip(w["start"].split(":"), (60, 1)))
    stop = sum(int(x) * m for x, m in zip(w["end"].split(":"), (60, 1)))
    now = lt.tm_hour * 60 + lt.tm_min + lt.tm_sec / 60
    if stop <= start:                       # crosses midnight, e.g. 22:00-04:00
        stop += 24 * 60
        if now < start:
            now += 24 * 60
    if start <= now and now + minutes <= stop:
        return done(0, f"inside {w['start']}-{w['end']} local")
    return done(1, f"outside {w['start']}-{w['end']} local, or would end after it")


if __name__ == "__main__":
    arm, minutes = sys.argv[1], float(sys.argv[2])
    ntp = float(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] not in ("", "nan") else None
    code, out = decide(arm, minutes, ntp)
    print(json.dumps(out))
    sys.exit(code)
