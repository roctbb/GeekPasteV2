# GitHub similarity

GitHub submissions are compared only after repository files have been saved.
`github_similarity.py` extracts recognised source files from the JSON payload;
repository URLs, branch names, file paths, README files and dependency directories
are not comparison input. No submitted code is executed.

Python files are tokenized with the standard library: comments/formatting are
ignored, but strings (including URLs), operators such as `//`, identifiers and
case are preserved. Invalid Python and other source languages use a conservative
lexical fallback, without stripping `//` comments. Empty projects do not match.
File order and names do not affect the result. The existing size limit applies
to extracted source characters; candidate scope and warning thresholds remain
unchanged. This is a similarity heuristic, not proof of plagiarism.

The legacy bug compared serialized JSON and interpreted the `//` in `https://`
as a comment, leaving the identical prefix `{"repo_url":"https:` for all projects.
There was also a race: similarity used to be queued before GitHub fetching.

## Repair a verified historical pair

Run from the application directory with `PYTHONPATH=.`:

```sh
python scripts/repair_github_similarity.py GGSE98 OS3SRK
python scripts/repair_github_similarity.py GGSE98 OS3SRK --apply --backup /private-backups/github-pair.json
```

The first command is read-only. Applying requires an exclusive backup file and
rechecks the source hashes under row locks. Only this pair and its two similarity
flags are repaired. Other matches are retained when recomputing the flags.
Only `/integrity` is called in CodingProjects: scores, feedback, blocks and
teacher requests are not regraded, and no plagiarism notifications are sent.
Use `--sync-only` to retry an unsuccessful integrity callback without reapplying
the database repair.
