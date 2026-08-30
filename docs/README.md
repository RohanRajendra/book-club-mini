# Documentation

| Document | Purpose |
| --- | --- |
| [overview.md](overview.md) | What the project is, its data domain, the current stack, and where it can grow |
| [installation.md](installation.md) | Getting both installations running, with configuration reference and troubleshooting |
| [notion-setup.md](notion-setup.md) | Creating the Notion workspace, databases and environment files |
| [architecture.md](architecture.md) | A guided tour of the codebase, with diagrams |
| [domain-model.md](domain-model.md) | The domain and architecture, specified independently of any technology |
| [storage-backends.md](storage-backends.md) | Replacing Notion with another database |
| [decisions.md](decisions.md) | One entry per architectural pattern, and what would justify removing it |

## Suggested reading order

**Setting it up.** [overview.md](overview.md) →
[notion-setup.md](notion-setup.md) → [installation.md](installation.md)

**Working on the code.** [overview.md](overview.md) →
[architecture.md](architecture.md) → [decisions.md](decisions.md)

**Replacing the database.** [domain-model.md](domain-model.md) §3–§8 →
[storage-backends.md](storage-backends.md)

**Evaluating the design.** [domain-model.md](domain-model.md) →
[decisions.md](decisions.md)

## Internal

[`internal/`](internal/) holds the original build specification and a record of
where the implementation diverged from it. It documents how the project was
produced rather than how it works, and is not required reading for using or
modifying the application.
