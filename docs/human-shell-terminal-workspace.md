# Human Shell Terminal Workspace

`tm shell` can run as either the original REPL or as a persistent terminal workspace.

The workspace is enabled with:

```text
layout on
layout off
layout refresh
layout compact
layout standard
layout full
```

`layout on` keeps a stable screen after each command. It does not change machine-readable CLI output outside `tm shell`, and `layout off` returns to the classic scrolling REPL.

## Panes

The standard layout has four panes:

- `Context`: current path, project, node, focus, view, density, mode, and sync status.
- `Main View`: the persistent current view.
- `Actionable List`: a compact list of objects that can be acted on from the current context.
- `Last Message`: the last command result or actionable error.

Pane boundaries use plain ASCII separators so the layout is readable in narrow terminals, non-color terminals, `NO_COLOR=1`, and test output.

## Views

Views are switched with:

```text
view show
view tree
view tasks
view today
view dashboard
view proposals
view health
view search
view preview
view edit
```

Common commands also update the current view:

- `tree` -> `tree`
- `show` -> `show`
- `ls tasks` -> `tasks`
- `find` -> `search`
- `proposals` -> `proposals`
- `quality project` -> `health`
- `preview` / `where` -> `preview`

Direct writes such as `todo`, `note`, `result`, `done`, and `edit` keep the current view and refresh it. This keeps the user's mental model stable: commands change data, not the screen's topic, unless the command is explicitly a view command.

## Focus

`focus <id>` and `select <id>` set the current target without changing the virtual path:

```text
focus 123
select <node-id>
```

`cd <id>` enters an object context. `show <id>` also makes that item the current focus. Targetless actions and `insert` use the focus when there is no more specific object or project node context.

## Sync Status

The context pane shows:

```text
File: synced ✓ | Index: fresh ✓ | Buffer: none | View: fresh ✓ | Rollback: op #N | Mode: NORMAL
```

Meanings:

- `File`: whether the Logseq file write succeeded, failed, or conflicted.
- `Index`: whether the SQLite index was refreshed after the write.
- `Buffer`: `none`, `clean`, or `dirty *` during inline edit.
- `View`: whether the visible view has been refreshed after the last operation.
- `Rollback`: the latest shell operation that can be undone.
- `Mode`: `NORMAL`, `INSERT`, `PREVIEW`, or `CONFLICT`.

## Density

`layout compact` hides the actionable list. `layout standard` limits it to a readable size. `layout full` shows more context for review or cleanup sessions.
