# The two review PRs

JC reviews in the browser, often on a phone. **The PR body is the review**: if a decision needs a file opened,
the PR has failed. Files are there for depth.

## Rules for both

- Figures first. One line under each figure saying what it shows. No paragraphs.
- Plain words in the body: no hypothesis numbers, gate IDs or step codes. They live in the files.
- Images embedded from the branch at the PR's commit (`https://raw.githubusercontent.com/zhen-swift/zhen-study/<sha>/v2/…png`),
  so they render on any device.
- A section never longer than one phone screen.
- Reply to every review comment, revise, push, and say in the reply what changed.

## Freeze PR — `study2` → `main`

**Title:** `Phase 1 results and the study 2 protocol — comment /freeze to lock it`

```
1  THE ANSWER        three numbers, large: wait percentile · first-scan wait · flags phase 2 passes
2  FIGURE            recall against wait, one line per dispersion, chosen point marked
3  FIGURE            scan time against wait, same layout
4  FIGURE            primed history against empty
5  TABLE             each setting: plan → now → why (one line)
6  TABLE             each claim phase 2 tests: claim · what refutes it
7  TABLE             what changed from PLAN.md
8  HEALTH            blocks run / skipped / why · open defects, one line each
9  WHAT /freeze DOES and the one command to run after it
```

Section 9 ends with the command, ready to paste on the mini as `jc-mini`:

```bash
printf 'zhenstudy ALL=(root) NOPASSWD: /usr/local/zhen-study2/zhen-0.8.0\n' > /tmp/zhen-study2-zhen && sudo visudo -c -f /tmp/zhen-study2-zhen && sudo install -m 0440 -o root -g wheel /tmp/zhen-study2-zhen /etc/sudoers.d/zhen-study2-zhen
```

**JC's responses:** review comments → revised. A comment that is exactly `/freeze`, by `JCTec` → the freeze.

## Final PR — `study2-paper` → `paper`

**Title:** `Study 2 results and the combined paper`

```
1  THE ANSWER        one line per claim: held / refuted, with the number
2  FIGURES           the paper's figures, in paper order, one line each
3  TABLE             what the paper says now that it did not
4  HEALTH            phase 2 and 3 blocks run / skipped · defects · deviations from the protocol
5  THE PDF           link to paper.pdf at this commit
6  CLEAN-UP          the two commands below
```

```bash
sudo rm /etc/sudoers.d/zhen-study2-zhen /etc/sudoers.d/zhen-study2
sudo launchctl bootout gui/$(id -u zhenstudy)/dev.zhen.study2.agent
```

**JC's response:** merges. Merging `study2` into `main` for the record is part of the same review.
