# Public release review

This is a **local Git repository with no remote**. The intended first public release follows the owner's independent PII review. Review the full four-commit history, including disabled design assets under `incubator/` and historical notes under `docs/design-notes/`; inspecting only the latest tree is insufficient because older commits remain visible after publication.

The local history records four real milestones: sanitized extraction, profile boundary, bounded target adapters, and MIT/audit preparation. It does not include the original private project's Git history. Generated workspaces, source study results, approval records and credentials are outside this repository.

A practical review sequence from the repository root:

```sh
git log --oneline --all
git ls-tree -r --name-only HEAD
python3 scripts/audit_export.py
python3 -m unittest discover -s tests -v
```

Review commit author metadata and each commit's file contents as well. The automated export scan checks common private labels, paths, contact patterns and credential shapes, but is heuristic. The independent sweep should inspect meaning and context, especially within preserved design notes. The license is MIT. Add release CI before creating a public remote or tag. No public repository or release is created by this local work.
