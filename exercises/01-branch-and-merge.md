# 01 — Branch and merge

**Goal:** create a branch, commit on it, and merge it back.

## Steps

```sh
git switch main
git switch -c feature/greeting

echo "hello" > sandbox/greeting.txt
git add -f sandbox/greeting.txt
git commit -m "Add a greeting"

git switch main
git merge feature/greeting
```

## What to notice

Because `main` did not move while you were on the branch, git performs a
**fast-forward**: it just slides `main`'s pointer up to the branch tip, adding
no merge commit. Confirm it:

```sh
git log --oneline --graph --all
```

Force a real merge commit instead:

```sh
git switch main
git reset --hard HEAD~1          # undo the fast-forward
git merge --no-ff feature/greeting
git log --oneline --graph --all  # now there are two parents
```

## Clean up

```sh
git branch -d feature/greeting
```

`-d` refuses to delete a branch whose commits aren't reachable from somewhere
else. That refusal is a safety net, not an obstacle — if you see it, the work
is not merged yet.
