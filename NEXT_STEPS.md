# Current File Editing Notes

## Status
- `delphi_file` exposes `write(edits=[...])` as the single write interface.
- The old `batch_write` action has been removed from the MCP schema and handler routing.
- Multiple edits for the same file should be merged into one `write` call.
- `write` accepts per-edit `old_content` to validate stale line ranges without a full reread.
- `old_content` comparison ignores whitespace outside string literals, so formatting-only whitespace drift does not block safe edits.

## Recommended Flow
1. Read only the needed range.
2. Plan all same-file edits against that snapshot.
3. Call `write(edits=[...])` once.
4. For a follow-up write, prefer per-edit `old_content` over `allow_dirty=True`.

## Remaining Follow-Up
- Keep documentation and examples aligned on `write(edits=[...])`.
- Avoid reintroducing `batch_write` in tool schemas, docs, or generated examples.
