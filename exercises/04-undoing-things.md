# 04 — Undo things

**Goal:** learn which undo command matches which mistake.

## Pick the right tool

| Mistake                                  | Fix                                      |
| ---------------------------------------- | ---------------------------------------- |
| Bad message on the last commit           | `git commit --amend`                     |
| Forgot a file in the last commit         | `git add <file> && git commit --amend --no-edit` |
| Staged something by accident             | `git restore --staged <file>`            |
| Want to discard uncommitted edits         | `git restore <file>`                     |
| Last commit shouldn't exist, keep changes | `git reset --soft HEAD~1`                |
| Last commit shouldn't exist, drop changes | `git reset --hard HEAD~1`                |
| Undo a commit that others already pulled  | `git revert <sha>`                       |

`reset` rewrites history; `revert` adds a new commit that cancels an old one.
On anything shared, use `revert`.

## Practise a hard reset and recover from it

```sh
git switch main
git switch -c feature/oops

echo "important" > sandbox/important.txt
git add -f sandbox/important.txt
git commit -m "Important work"

git reset --hard HEAD~1     # the commit is now unreachable
git log --oneline           # it's gone
```

Get it back:

```sh
git reflog                  # find the sha of "Important work"
git reset --hard <sha>
cat sandbox/important.txt
```

## What reflog is

`git reflog` records every position `HEAD` has held in this clone — including
positions no branch points at any more. It is local-only, it is not pushed, and
entries expire (90 days by default for reachable ones, 30 for unreachable).

Practically: a *committed* change is very hard to lose permanently. An
*uncommitted* one is trivial to lose, because there is no reflog entry for work
that was never committed. Commit early — you can always tidy the history later
with exercise 03.
