---
title: "Queue Console commands"
description: "Run workers and generate typed job artifacts."
---

Queue registers commands through the existing Titanspan Console. Typer parses
arguments and Rich renders terminal output.

## Worker commands

| Command | Behavior |
| --- | --- |
| `queue:work` | Run a Taskiq worker with configured or explicit concurrency and prefetch. |
| `queue:listen` | Run one concurrent handler through the same worker lifecycle. |

Both commands accept `--connection` and `--queue`. `queue:work` also accepts
`--concurrency` and `--prefetch`. The selected application must register the
same trusted job types as producers.

## Generate job files

```shell
titanspan make:job ProcessDocument
```

```shell
titanspan make:job-middleware RecordAttempt
```

The generators use Foundation's effective application root and the shared
Console artifact generator. Generated jobs require explicit registration
with `QueueServiceProvider`.

## Commands not provided

Queue does not register failed-job administration, worker restart, queue
clearing, monitoring, failed-batch pruning, database migration, or persistent
table-generation commands. Those operations require backend-specific
administrative semantics or Database persistence. Queue does not clear a
shared broker namespace through an unsafe generic command.
