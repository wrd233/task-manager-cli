# Human Shell Inline Edit

Inline edit lets the current `show` target become an editable buffer inside `tm shell`.

```text
insert
insert line
insert subtree
insert <id>
insert <id> line
insert <id> subtree
```

The first implementation is deliberately conservative. It is a Layout Lite editor, not Vim: it supports buffer editing, multiline paste, preview, conflict detection, save, cancel, and rollback, while avoiding mouse support, visual mode, registers, cross-file edits, and background refresh.

## Targets

Default scope:

- task / idea / resource / result: `line`
- mini project / project semantic node: `subtree`
- project root, `/today`, `/dashboard`, `/proposals`: rejected until a specific focus is selected

Use one of these before `insert`:

```text
focus <id>
show <id>
cd <id>
cd <project-node>
```

If no editable target is available, the shell prints:

```text
No editable focus. Use focus <id>, cd <id>, or show <id> first.
```

## Editing

The fallback line-mode editor supports:

- text input
- multiline paste
- `:left`, `:right`, `:up`, `:down`, `:home`, `:end`
- `:backspace`, `:delete`
- `:show`
- `:save`
- `:cancel`

Terminals that pass `Ctrl-S`, `Ctrl-C`, or `Ctrl-G` can use those keys; `:save` and `:cancel` are the reliable fallback because some terminals intercept `Ctrl-S` for flow control.

## Save Flow

Saving does this:

1. Compare buffer and original lines.
2. If unchanged, report `No changes`.
3. Check the file hash from edit start.
4. If the file changed externally, enter conflict mode and refuse overwrite.
5. Generate a preview with target, scope, file, line range, line count change, diff, and rollback note.
6. Ask for confirmation.
7. Write the file with backup.
8. Refresh the changed file in the index.
9. Refresh the current view and sync status.
10. Record an operation for `undo`.

If the replacement has far fewer non-empty lines than the original subtree, preview includes a content-loss warning.

## Cancel And Conflict

`:cancel` discards the buffer only after confirmation when it is dirty. No file changes are made.

If a file changed while editing, save refuses to overwrite it:

```text
Conflict detected: file changed since edit started.
```

The safe recovery path is to cancel, refresh the view, and start a new `insert`.
