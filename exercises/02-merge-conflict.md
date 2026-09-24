# 02 — Resolve a merge conflict

**Goal:** make two branches edit the same line, then reconcile them by hand.

## Set up the collision

```sh
git switch main
echo "colour: blue" > sandbox/config.txt
git add -f sandbox/config.txt
git commit -m "Add config"

git switch -c feature/red
echo "colour: red" > sandbox/config.txt
git commit -am "Make it red"

git switch main
echo "colour: green" > sandbox/config.txt
git commit -am "Make it green"
```

## Trigger it

```sh
git merge feature/red
```

Git stops with `CONFLICT (content): Merge conflict in sandbox/config.txt` and
leaves the file marked up:

```
<<<<<<< HEAD
colour: green
=======
colour: red
>>>>>>> feature/red
```

`HEAD` is the branch you are on (`main`); below the `=======` is the branch you
are merging in.

## Resolve

Edit the file so it contains only what you want, and delete all three marker
lines. Then:

```sh
git add sandbox/config.txt
git commit          # the merge message is pre-filled
```

`git status` during a conflict tells you exactly which files are still
unmerged. Trust it over your memory.

## Escape hatch

Back out of a merge you don't want to finish:

```sh
git merge --abort
```

This returns the working tree to where it was before the merge started.
