# lab_git

A scratch repository for practising git. Nothing here is precious — break it,
rewrite its history, force-push it, throw it away and start over.

## Layout

| Path         | What it's for                                                        |
| ------------ | -------------------------------------------------------------------- |
| `sandbox/`   | Free-for-all scratch area. Make whatever files an experiment needs.   |
| `exercises/` | Short, self-contained drills. Each one is a single markdown file.     |

## Getting started

```sh
git clone https://github.com/CosminButa/lab_git
cd lab_git
git switch -c my-experiment
```

Work on a branch, not on `main`, so that `main` stays a clean base to branch
off again. When an experiment is done:

```sh
git switch main
git branch -D my-experiment
```

## Resetting the lab

Most experiments are recoverable. If one isn't, reset the working tree to the
last commit and drop untracked files:

```sh
git reset --hard HEAD
git clean -fd
```

To find a commit you thought you destroyed, check the reflog — it keeps a local
record of where `HEAD` has been for 90 days by default:

```sh
git reflog
git switch -c recovered <sha>
```

## Exercises

- [01 — Branch and merge](exercises/01-branch-and-merge.md)
- [02 — Resolve a merge conflict](exercises/02-merge-conflict.md)
- [03 — Rewrite history with rebase](exercises/03-interactive-rebase.md)
- [04 — Undo things](exercises/04-undoing-things.md)
