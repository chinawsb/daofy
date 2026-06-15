# Sisyphus Session Summary

## Goal
- Fix Delphi parser/formatter bugs (case, try/except/finally) and add file-level write guard to prevent concurrent write corruption

## Constraints & Preferences
- (none)

## Progress
### Done
- **All 3 parse errors fixed** (test28 case, test30 try/finally, test31 try/except/finally) — only 2 expected conditional directive errors remain (test21, test24)
- Added `FormatEpilog` overrides to `AST.Delphi.Nodes.pas`:
  - `TDelphiCaseStmt` — newlines between selectors, `end;` at end
  - `TDelphiTryStmt` — try body formatting, outdent `except`/`finally` to `try` level, `end;` at end
  - `TDelphiExceptBlock` — newlines between exception handlers
  - `TDelphiFinallyBlock` — newlines between finally body statements
  - `TDelphiHandler` — semicolon after handler body statement
- Statement-aware formatting for `TDelphiCallExpr` and `TDelphiIdentifier` — when parent is a statement container, they now add `AppendIndent` + `AppendLine(';')`
- `TDelphiCaseSelector.WriteBody` — outputs `else` for else-branch (was outputting `:` with no values)
- `AFormat.Current := nil` in `TDelphiCallExpr.WriteBody` now runs unconditionally (prevents double-formatting of manually-handled child arguments), not just in statement path
- All 55 tests pass with reasonable formatting output
- **Write corruption analysis**: Root cause is concurrent writes to same file without locking. Lock alone doesn't fix — stale snapshot (read v1, write v2) causes line offset errors
- Added file-level write guard to `src/tools/file_tool.py`:
  - `_file_write_locks` dict + `_acquire_write_lock` / `_release_write_lock` functions
  - `handle_write` now acquires lock before the try block, releases in the finally block
  - `handle_batch_write` now acquires lock before the write try block, releases in the write finally block
  - Rejects concurrent writes to same file with error message asking user to merge edits into one `batch_write`
- Updated `src/config/tool_docs.py`:
  - `TOOL_SHORT_DESC["delphi_file"]` — added `⚠️ 同文件不得并行写`
  - `TOOL_HELP_DOCS["delphi_file"]["constraints"]` — two new constraints: no parallel writes to same file, all edits must be merged into one `batch_write`
  - `TOOL_HELP_DOCS["delphi_file"]["workflow"]` — rewritten to use `read → batch_write` flow
  - `actions.write.description` — added `🚫` not to split into multiple `write` calls
  - `actions.batch_write.description` — marked `⭐ 优先使用`, explains it's for 2+ edits on same file

### In Progress
- (none)

### Blocked
- (none)

## Key Decisions
- **Lock alone doesn't fix stale-snapshot problem**: concurrent writes based on same old snapshot produce wrong results even if serialized. Fix is to prevent parallel writes to same file entirely, not serialize them.
- **Three-layer defense**: (1) tool_docs as soft guidance, (2) orchestrator routing (merge same-file edits), (3) file-tool-level write guard as hard stop
- **batch_write is the canonical path**: all edits on one file must be read once, planned against original line numbers, then written once via `batch_write`

## Next Steps
1. Check remaining formatting quality issues (extra blank lines between statements, handler body same-line formatting)
2. Extend write guard to `format(..., in_place=True)` and `uses` actions if they also modify files
3. Consider orchestrator-level change: detect same-file edits across sub-agents and merge into single agent with `batch_write`

## Critical Context
- Concurrent writes to same file corrupt because: (a) they race, (b) even serialized they use stale line numbers (read v1, write v2 — line offsets shifted)
- `batch_write` solves this: edits are all relative to the original file snapshot, internal offset management handles line shifts
- `TDelphiCallExpr` manually formats children in `WriteBody` — must always set `AFormat.Current := nil` to prevent default `FormatEpilog` from re-processing them
- Parent-child `is` checks in `WriteBody` (for statement detection) use the public `Parent` property, not private `FParent`
- `TDelphiIdentifier` as statement (e.g., `Cleanup;`) needs the same statement-aware treatment as `TDelphiCallExpr`

## Relevant Files
- `AST\Delphi\AST.Delphi.Nodes.pas`: All formatting methods (~1490 lines)
- `AST\Delphi\AST.Delphi.Parser.pas`: Parser logic (~1892 lines)
- `AST\AST.Base.pas`: `TASTNode.Format` engine (line 629)
- `src\tools\file_tool.py`: Write guard added — `_acquire_write_lock`/`_release_write_lock` (line ~30-50), `handle_write` (line ~694-708), `handle_batch_write` (line ~1113-1163)
- `src\config\tool_docs.py`: Updated constraints and workflow for `delphi_file`
