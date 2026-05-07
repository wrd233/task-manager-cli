# Human Shell Mental Model

Human Shell is place-first:

- `/today`: today's surface.
- `/dashboard`: global operating picture.
- `/projects`: project space.

The core verbs are intentionally small:

- `tree`: structure.
- `ls`: actionable objects.
- `show`: current content.
- `find`: context search.
- `todo` / `idea` / `resource` / `result` / `note`: capture.
- `clarify`: turn ambiguous items into proposals.
- `proposals` / `preview` / `accept` / `apply` / `rollback`: safe proposal workflow.
- `undo`: direct-write recovery.

Workspace mode adds three nouns:

- `view`: what stays in the Main View pane.
- `focus`: the object or semantic node targetless commands act on.
- `sync status`: whether file, index, buffer, view, and rollback state are trustworthy.

Use:

```text
layout on
view tree
focus 123
insert line
```

The rule of thumb is: `cd` changes where you are, `view` changes what you are looking at, and `focus` changes what the next action targets.

Recommended flow:

```text
cd /today
ls
cd /dashboard
ls quality
cd /projects/<project>
tree
ls tasks
show
clarify unplaced
proposals
preview 1
accept 1
apply 1
rollback 1
```

`show` without a target always means "show where I am". `project create` inside `/projects` means "create and enter".

`insert` means "edit the current focus in place". It never edits project root, dashboard, today, or proposals directly; choose a specific object or node first.
