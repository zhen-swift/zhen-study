# Study 2 — ledger

Append-only. Format in `BRIEF.md`. Times are `America/Los_Angeles`.

## 2026-11-02 · setup · plan written
What: run contract (`RUN.md`), brief (`BRIEF.md`), mini setup (`mini/SETUP.md`), review-PR layout (`REVIEW-PR.md`),
agent wrapper and permissions (`agent/`). Decided with JC 2026-10-31 and 2026-11-02; every decision is in `RUN.md`.

## 2026-11-06 · setup · the repository starts itself
What: `START.md` replaces `mini/SETUP.md`. One prompt on a fresh mini clones this repository and follows it; the
frozen binary comes from the release `study2-binary` by checksum; no SSH and no copying by hand. The agent and the
collection run as LaunchDaemons under `zhenstudy`, so nobody has to be logged in. Decided with JC; `RUN.md` dated.
