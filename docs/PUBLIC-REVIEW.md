# Blacklight release review

Review the full Git history, including disabled design assets under `incubator/` and historical notes under `docs/design-notes/`; inspecting only the latest tree is insufficient because older commits remain visible after publication.

The Git history records sanitized extraction, profile boundaries, bounded target adapters and campaigns, a local reviewer isolation workflow, the synthetic graph profile, MIT/audit preparation, and the Blacklight rename. It does not include the original private project's Git history. Generated workspaces, source study results, approval records and credentials are outside this repository.

A practical review sequence from the repository root:

```sh
git log --oneline --all
git ls-tree -r --name-only HEAD
python3 scripts/audit_export.py
python3 -m unittest discover -s tests -v
```

Review commit author metadata and each commit's file contents as well. The automated export scan checks common private labels, paths, contact patterns and credential shapes, but is heuristic. The independent sweep should inspect meaning and context, especially within preserved design notes. The license is MIT. CI runs the test suite and export scan on pushes and pull requests. Automated checks are not a substitute for the owner's independent review.
