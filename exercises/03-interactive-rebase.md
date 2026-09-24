# 03 — Rewrite history with rebase

**Goal:** turn a messy string of commits into the history you wish you had made.

## Build something messy

```sh
git switch main
git switch -c feature/messy

for n in 1 2 3; do
  echo "line $n" >> sandbox/notes.txt
  git add -f sandbox/notes.txt
  git commit -m "wip $n"
done
```

## Squash it

```sh
git rebase -i HEAD~3
```

An editor opens with one line per commit, oldest at the top:

```
pick a1b2c3d wip 1
pick e4f5g6h wip 2
pick i7j8k9l wip 3
```

Change the later `pick`s to `squash` (or `s`) to fold them into the first, save,
and write a single message when prompted. `git log --oneline` now shows one
commit.

Other verbs worth trying on a later run: `reword` (change a message only),
`edit` (stop so you can amend), `drop` (delete the commit), and reordering the
lines (reorders the commits).

> Interactive rebase is not available through this environment's Bash tool,
> which cannot open an editor. Run it in your own terminal.

## Rebase onto a moved base

```sh
git switch main
echo "upstream change" > sandbox/upstream.txt
git add -f sandbox/upstream.txt
git commit -m "Upstream work"

git switch feature/messy
git rebase main
```

Your commits are replayed on top of the new `main`, giving a linear history
rather than the merge commit exercise 01 produced.

## The rule that matters

Rebase creates *new* commits with new hashes. Rewriting history that other
people have already pulled forces them to reconcile two versions of the same
work. Rebase your own unpushed branches freely; leave shared branches alone.

If a rebase goes wrong mid-flight:

```sh
git rebase --abort
```

And if it "succeeded" into something you didn't want, exercise 04 gets it back.
