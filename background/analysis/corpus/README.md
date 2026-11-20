# Orchestration harness evaluation corpus

The authoritative user-specified corpus is now `orchestrators.tsv` (35 pinned
repositories). `repos.tsv` is retained only as the earlier supplemental
framework/runtime survey and must not be used to report progress for the
orchestrator evaluation.

Snapshot date: 2026-11-18 UTC.

`repos.tsv` records the canonical GitHub upstream, default branch observed during
discovery, and immutable commit selected for evaluation. Repositories are cloned
under `../repos/OWNER__REPO` and checked out detached at the recorded commit.

The corpus covers three distinct units:

- `general`: embeddable agent, graph, workflow, and multi-agent runtimes.
- `coding`: coding-session and repository-task agent runtimes.
- `outer`: worker-supervision and evaluation-trial harnesses.

The study excludes front ends and GUI quality. Deep Agents was excluded as a
separate runtime because it delegates execution to LangGraph-backed machinery;
mini-SWE-agent was excluded because its core loop is intentionally minimal and
does not support the requested deep core-code comparison as well as Cline's
standalone SDK runtime. Microsoft Agent Framework could not be pinned because
its expected public repository returned 404 during the snapshot.
