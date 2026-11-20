# Evaluation protocol

Each repository receives an independent Sol 6.2 investigation of at least 30
minutes of active work. GUI and front-end quality are out of scope.

Required report sections:

1. Snapshot, scope, and elapsed-time evidence.
2. Core architecture and end-to-end control/data flow.
3. Why the design works and its governing invariants.
4. What it does well and poorly, with source evidence.
5. Core-code quality: decomposition, state, concurrency, errors, types, tests,
   observability, extensibility, and maintainability.
6. Executed tests/experiments and their limitations.
7. Measurement audit for every negative or surprising result, including
   alternate commands or code-path checks used to rule out setup mistakes.
8. Post-mortem: design pressures, accumulated tradeoffs, likely failure modes,
   and the highest-leverage improvements.
9. Evidence appendix with local file/line references and commands.

Investigators must not edit repository sources. Each writes only its assigned
Markdown report under this directory and may use an isolated temporary
directory for experiments.

## Execution policy

An initial 25-way Sol 6.2 fan-out caused provider event streams to close before
substantive work. A single-repository retry remained healthy, so subsequent
evaluations run serially. `retry-queue.tsv` records the deterministic order for
the 24 interrupted repositories; entries advance only after the preceding
evaluation has completed and its report has passed integrity checks.
