# Superharness architecture, orchestration, and reliability evaluation

## 1. Snapshot, scope, and elapsed-time evidence

- Repository `repos/artificemachine__superharness`, Git HEAD `e77627733cf38b0eed9b05679c0238d1435f2205`, package version 1.86.6 and SQLite schema version 39. At 2026-11-19 16:36:16 UTC, `git rev-parse HEAD` returned the requested commit and `git status --porcelain=v1 --untracked-files=all` returned no output. Source citations below are relative to this repository. `pyproject.toml:5–11`, `src/superharness/engine/db.py:1839–1883`.
- Scope covers the CLI, task and attempt state, routing and planning, watcher and worker execution, provider/tool adapters, local persistence, scheduling, recovery, and operational telemetry. Dashboard layout and GUI quality are excluded. The broad suite includes local HTTP and dashboard regressions as shipped.
- The prior attempt supplied no investigation time or findings. This review reused only local wheel files as installation inputs. It used a fresh, independently cloned copy of the verified HEAD for test execution and a separate process, mount, and network namespace for every run. The evidence contains synthetic tasks, subprocesses, and state. See sections 6–7 for dependency and platform qualifications.
- The evaluation README enumerates nine sections. This report preserves those headings and uses section 10 for the requested tenth section and final integrity receipt. The end time and active span are recorded there.

**Assessment.** The project is a useful local coordination and handoff layer, with a real transactional queue claim, versioned task writes, and substantial compatibility testing. Its unattended reliability is considerably weaker than its individual components suggest. A task phase can advance successfully while the launcher marks its attempt failed. Different paths create different notions of ownership and cancellation, and temporary checkout cleanup can discard the work that recovery needs. The most valuable change is to make dispatch attempts a durable unit with one owner, one completion contract, and a checked finalization protocol shared by all entry points.

## 2. Core architecture and end-to-end control/data flow

**Entrypoints and state.** Both installed executable names reach the same Click command group. Domain groups reuse registered callbacks. CLI commands commonly delegate to argparse modules through a compatibility layer. The project combines a task contract, an inbox of targeted executions, handoff history, decision/failure/usage records, discussions, and heartbeats. SQLite is authoritative for task/inbox records. Selected state still legitimately lives in files, including profiles, schedule metadata, launcher logs, operator process metadata, and discussion submission artifacts. Files such as `inbox.yaml` can remain in command signatures and lock names even when the operation opens SQLite. Verify the callee before attributing a call to legacy persistence. `pyproject.toml:51–53`, `src/superharness/commands/domain_groups.py:15–51`, `src/superharness/engine/state_reader.py:126–160,205–241`, `src/superharness/engine/inbox.py:258–268,385–441,464–551`.

**Operator and watcher.** The optional operator starts a one-shot watcher, supervises its exit, and normally respawns it on a 15-second start-to-start cadence subject to monitor polling. Foreground watch runs the same cycle repeatedly. Installation has further launchd, systemd, and Windows Task Scheduler paths. A tick acquires a project filesystem lock and attempts a SQLite singleton lease, writes heartbeats, processes operator commands, runs configured module hooks, then applies retry, owner fallback, review/close, enqueue, deadline, transcript, and garbage-collection policies. Dispatch is after those phases and the spend/loop checks. The default target expansion intersects the manifest list with executable harnesses. The watcher starts a detached dispatcher per target, discards its handle, and proceeds to discussion dispatch. The operator supervises the watcher process. The detached dispatchers own separate sessions. `src/superharness/engine/operator.py:71–94,313–334,381–539`, `src/superharness/commands/inbox_watch.py:544–627,2837–3266,5397–5508`, `src/superharness/engine/service_installer.py:51–64,162–179,216–300,360–386`.

**Claim and execution.** Public inbox enqueue validates project path, owner, workflow and status for an existing task and writes the inbox row and an enqueue ledger record together. Each dispatcher canonicalizes the project path, takes a short `mkdir` lock, and claims the next pending row for one target using `BEGIN IMMEDIATE` and `UPDATE … RETURNING`. The claim commits `launched`, PID, and timestamps before any provider process starts. A shared-state worker may refresh its copy after claim. The dispatcher decides working directory, worktree isolation and timeout, then releases the claim lock ahead of launching. A Python delegate subprocess, optionally wrapped in a PTY, builds the prompt and invokes the selected CLI or SDK. Completion re-enters reconciliation against contract state or a discussion submission. Nonzero exits feed the failure classifier, ledger, retry metadata and, for eligible failures, the next watcher cycle. Neither a committed claim nor a process exit alone is a durable record of the intended work outcome. `src/superharness/commands/inbox_enqueue.py:30–67,88–184,206–289`, `src/superharness/engine/inbox_dao.py:153–189`, `src/superharness/commands/inbox_dispatch.py:746–854,884–942,1058–1106,1162–1472,1563–1955,2050–2196`.

**Planning and review.** The workflow table distinguishes implementation, quick, note, discussion, review and approval work. Implementation typically moves from `todo` through a plan handoff, approval, execution, a report, verification/review, and close. The delegate checks date and dependencies, task existence and content, and workflow-specific statuses before dispatch. Plan-only prompts ask the agent to do no implementation and submit a TDD plan. Explicit approval and configured AI-driven approval are separate paths. The latter requires a plan in SQLite and a passing validator, then records the approval and its audit entry in one task-status transaction. Automatic reviewer selection, review escalation, and close run in watcher phases. Review and verification are separate concepts. The `close` command checks verification and optional subtask resolution before the task write. `src/superharness/engine/next_action.py:53–158,225–288,379–400`, `src/superharness/commands/delegate.py:278–352,843–986,1196–1229`, `src/superharness/commands/task.py:586–786`, `src/superharness/commands/close.py:143–273`, `src/superharness/commands/inbox_watch.py:102–112,2961–2975,3022–3040,3101–3119`.

**Routing and decomposition.** For direct delegation, role, CLI flags, task fields, classifier and defaults produce model/effort. An additional default orchestrator call can suggest a tier, effort and decomposition, with the requested agent preserved at the actual launch. The orchestrator samples its candidate order using in-memory runtime/model success counters, uses per-runtime argv and a per-call timeout, normalizes the response and estimates cost. The separate `auto-dispatch --orchestrate` branch asks for a split above an effort threshold, inserts child rows with `parent_id`, advances the parent and then enqueues children. Subtask aggregation, bounded review fan-out and the SDK/Git worktree fan-out helpers are distinct mechanisms. The standalone parallel and swarm engines are library surfaces in this snapshot. Their presence does not imply that the regular watcher dispatches a subtask graph or that the CLI preflight hint has a matching `--fanout` flag. `src/superharness/commands/delegate.py:988–1187,1520–1646`, `src/superharness/engine/orchestrator.py:38–114,205–249,455–590,617–780`, `src/superharness/commands/auto_dispatch.py:189–265,268–370`, `src/superharness/engine/review_fanout.py:43–54,110–117`, `src/superharness/engine/parallel_dispatch.py:173–252`, `src/superharness/engine/swarm.py:106–290`.

**Discussions.** The public start command opens discussion state and schedules one inbox job per participant for the shared round task. A participant may submit over the CLI, or write a YAML response for the harness to reconcile into SQLite. Explicit submission validates the participant and verdict, ingests the round, acknowledges matching inbox work, and conditionally commits consensus within the same transaction. Round advancement consumes persisted markers and imported submissions. Discussion close stops further claims and makes a best-effort process-tree termination pass, then recovers leftover submissions. This is a more explicit cancellation path than the ordinary task-status command. `src/superharness/commands/discuss.py:185–258,390–506,1006–1026`, `src/superharness/engine/discussion.py:127–230,249–320,559–675,860–1009`, `src/superharness/engine/discussions_dao.py:146–232`, `src/superharness/commands/discussion_dispatch.py:384–651`.

**Workspaces and sessions.** A source checkout can use a clean worker copy with project state shared through a `.superharness` symlink. Git and mutable build artifacts are excluded. An ephemeral worktree uses the original DB through `SUPERHARNESS_STATE_PROJECT`. Non-interactive Pi requires a committed HEAD for a fresh isolated worktree. Other agents generally get a worktree only when the execution root is dirty and the task is outside discussion mode. Claude session hooks distinguish per-turn snapshots from end-of-session cleanup. The SDK can choose a warm-start session from the latest project JSONL and fork it, then save a local usage/context snapshot. Hand-off recovery in the protocol spans agent sessions independently of SDK resumption. `src/superharness/commands/watcher_worker.py:61–123`, `src/superharness/engine/platform_runtime.py:194–262`, `src/superharness/commands/inbox_dispatch.py:945–968,2165–2177,2201–2303`, `src/superharness/adapters/claude-code/hooks/session-turn-end.sh:2–14,69–93`, `src/superharness/adapters/claude-code/hooks/session-exit.sh:96–158`, `src/superharness/engine/sdk_runner.py:19–43,251–268`, `src/superharness/commands/delegate.py:184–238,1452–1465`.

## 3. Why the design works and its governing invariants

- **Local coordination without a separate broker.** SQLite holds work intent across watcher and agent restarts. ACID writes, foreign keys, a partial unique inbox index and explicit claim ordering serve a useful single-host workload. `claim_next` provides one winner **for a pending row**. Control C1 verified one winner out of eight OS processes. The scope of that invariant leaves space for different agents to work on the same discussion round. It also leaves per-agent execution capacity to a separate policy. `src/superharness/engine/db.py:664–699`, `src/superharness/engine/inbox_dao.py:153–221`.
- **Task states and attempts represent different facts.** The task is the protocol-level plan, implementation, human wait and review history. Inbox phases record delivery and execution. When writers preserve the separation, a plan or report can release the worker and wait for a different actor or phase. `tasks_dao.update` catches stale edits with a version predicate, and the task-state schema constrains the vocabulary. These mechanisms prevent lost updates and invisible misspelled task statuses on the paths that use them. They cannot prove every route obeys the transition table or that the process associated with an inbox record is still its owner. `src/superharness/engine/next_action.py:53–158`, `src/superharness/engine/tasks_dao.py:259–348`, `src/superharness/engine/db.py:1576–1666`.
- **Explicit authority and auditable handoffs.** The resolver uses a real canonical project path and a stable 12-character hash. Precedence is explicit state root with conflict refusal, an existing XDG DB, existing legacy DB, legacy directory, then a new project path. A new temporary project with neither state override keeps state in its disposable harness directory. This protects existing projects while allowing worktrees to reuse one DB. It does not imply that every worker/service propagates the identity or that an ambient XDG change detects every older DB. Typed DAO handoff writes validate phase/status and keep append history. Optional exports support inspection, interop, and repair. `src/superharness/utils/paths.py:48–59,76–118,136–202`, `src/superharness/engine/handoffs_dao.py:14–50,76–128`.
- **Recovery can make progress despite missing processes and observations.** A persistent queue and UTC stage timestamps enable reconciliation. Idle/absolute watchdog telemetry is deliberately optional. The legacy deadline path uses `in_progress_at` when available, so long queue residence does not consume the same execution budget. The operator counts abnormal component exits, and its breaker pauses after the sixth failure in a ten-minute window. Signals, liveness checks, recovery classes and bounded retries make common failures observable or recoverable. Their scope varies by path and stage. `src/superharness/engine/lifecycle_rules.py:33–164,394–568`, `src/superharness/engine/operator.py:400–539`, `src/superharness/commands/inbox_watch.py:1462–1545,3689–3879`.
- **Deliberation has meaningful transaction guards.** One submission per discussion, round and agent is enforced by a unique partial index, including migrations of earlier DBs. The submitter rechecks active status under the write lock and conditionally sets consensus once. A small quorum tolerates one missing agent only in groups of three or more, and an observed dissent blocks consensus. The independent controls verified duplicate rejection and normal acknowledgements. Round identity still needs validation against the current round. `src/superharness/engine/db.py:844–868,1724–1769`, `src/superharness/engine/discussion.py:179–230,249–320`.
- **Extensions can preserve a common task model without forcing a single agent runtime.** A harness exposes an invocation and discovery method. Manifests carry declarative launch, model-tier, auth compatibility and capability metadata. Modules use a separate named action registry with typed-enough lifecycle descriptors and explicit blocking opt-in. The platform seam translates Windows and POSIX liveness/signaling. These are good isolation points for adding an integration, as long as each integration can express the same dispatch outcome and resource ownership. `src/superharness/harnesses/base.py:16–60,93–136`, `src/superharness/engine/adapter_registry.py:104–190,230–283`, `src/superharness/modules/runner.py:13–54,57–154`, `src/superharness/engine/process.py:44–80,112–183`.

## 4. What it does well and poorly, with source evidence

**Strengths.** Atomic queue claims and optimistic task updates address real races with simple SQL and independent tests. Backups taken through SQLite's backup API can include committed WAL pages. Migration savepoints, scoped foreign-key checks and the additive drift healer are evidence of careful operational learning. The explicit root-conflict guard, preflight gate, project overlap guard and Pi fail-closed branch make routine input errors much easier to diagnose. Discussion acknowledgements and duplicate constraints eliminate multiple useful classes of restart error. Existing chaos, E2E, transition, dependency, cross-platform and process tests form a substantial regression net. `src/superharness/engine/db.py:346–389,433–523`, `src/superharness/commands/watcher_worker.py:61–123`, `src/superharness/commands/inbox_dispatch.py:2240–2297`, `tests/chaos/test_concurrent_writers.py:37–110`, `tests/stress/test_operator_process_lifecycle.py:100–152,221–276`.

| Finding | Impact and root cause |
| --- | --- |
| F1 · Successful phase ends are treated as failed attempts | **High, reproduced.** A local agent wrote a real plan or report into SQLite, made the expected task transition, and exited zero. The dispatch returned 1, set the inbox to `failed` with no reason and made it eligible for ordinary auto-retry. A verified and closed task returned 0 with inbox `done`. Postprocessing maps only `done`, `failed` and `pending_user_approval` explicitly. The plan-only and report delivery outcomes are absent from the attempt completion contract. `src/superharness/commands/delegate.py:1204–1229`, `src/superharness/commands/inbox_dispatch.py:1219–1380,1399–1472`, `src/superharness/commands/inbox_watch.py:1489–1539`. C6. |
| F2 · Dirty checkout isolation can fail open, and cleanup discards work | **High, reproduced.** For ordinary Codex dispatch, a dirty Git repo without HEAD makes worktree creation fail. The fallback only attempts `pending → paused` after claim already set `launched`, so execution continues in the original dirty checkout. Pi refuses the same fixture before launch. In a separate genuine dirty-worktree run, force-removal discarded a synthetic tracked edit and subsequent benchmarking recreated a directory at the recorded path with only a benchmark file. The implemented work-preservation policy in `close` is absent from the dispatcher cleanup. `src/superharness/commands/inbox_dispatch.py:205–278,594–603,884–942,1095–1106,1416–1468,2226–2303`, `src/superharness/commands/close.py:44–95`. C5, C14. |
| F3 · Deadline result and process ownership do not agree | **High, reproduced.** The POSIX launcher alarm sends TERM and then waits without escalation. A child ignoring TERM runs past its one-second deadline and returns 124 only after naturally exiting. The operator's group cleanup works while the group leader exists. After `poll()` reaps the leader it cannot obtain its group from the PID, even with a surviving member. Clean/crash watcher handling invokes cleanup after polling. Separately, normal watcher dispatch starts a new session on purpose. Think of these as separate populations of children. `src/superharness/commands/inbox_dispatch.py:454–559`, `src/superharness/engine/operator.py:425–456,505–518,543–600`, `src/superharness/commands/inbox_watch.py:603–613`. C3, C9. |
| F4 · Stopping an ordinary task does not stop its execution | **High, reproduced.** Two separate ticks launched two jobs for the same agent and the single agent heartbeat named only the second job. `task status stopped` set the first task to `stopped` and its inbox to `failed`. The first stub was still executing, with no signal sent by the status path. An auto-retry can reuse the same row ID, while launch finalization, PID clearing and some reconciliation updates accept the row by status/ID without a dispatch generation. This is a plausible stale-writer race even where claim itself is atomic. `src/superharness/commands/task.py:644–655,696–712,1479–1521,1542–1558`, `src/superharness/commands/inbox_dispatch.py:471–523,640–683,2087–2099`, `src/superharness/commands/inbox_watch.py:544–627,1489–1539`, `src/superharness/engine/heartbeat_dao.py:35–104`. C1, C9. |
| F5 · Planner output is not a durable executable graph | **High, reproduced.** Real `delegate --orchestrate` printed two children and launched the parent without inserting children or queue rows. `auto-dispatch --orchestrate` did insert children and moved the parent to `in_progress`; it dropped the dependency, persisted no actionable content, and queued both plan-only. Both then hit the real empty-content gate and exhausted their retry budget before launch. Children and parent are committed before separate enqueue calls, adding partial-registration risk. `src/superharness/commands/delegate.py:374–468,861–887,1130–1181,1471–1486`, `src/superharness/commands/auto_dispatch.py:200–265,304–337`, `docs/GUIDE.md:275–276`. C7. |
| F6 · Persistent handoff command can report either side of the commit incorrectly | **High, reproduced.** Locking a healthy WAL DB for writing elicited an authoritative write failure and a successful export/exit 0. A second real call collided with the same export filename after appending another DB row and returned 1. The engine deliberately returns false on storage trouble for legacy compatibility. The CLI ignores that return, writes SQLite before testing export file existence, and lacks a request identity for safe retries. `src/superharness/engine/state_writer.py:367–388,411–462`, `src/superharness/engine/handoffs_dao.py:76–116`, `src/superharness/commands/handoff_write.py:274–308`. C8. |
| F7 · Recurring schedules can wedge on the first due job | **High, reproduced.** Two valid due schedules with explicit targets produced only one inbox row. The first successful enqueue exited the entire schedule call and left schedule metadata unchanged. A repeat failed on duplicate; an omitted optional target failed on required `--to` before touching any row. The scheduler calls the CLI-only `main()` and catches `Exception`, while both success and parser failure use `SystemExit`. The watcher module for `scheduled_after` separately scans task rows and has no dependency on `scheduled.yaml` or `cmd_run`. `src/superharness/commands/schedule.py:39–56,272–365,387–425`, `src/superharness/commands/inbox_enqueue.py:308–313,413–429`, `src/superharness/modules/actions/auto_schedule.py:76–175`, `src/superharness/commands/inbox_watch.py:2878–2886`. C2. |
| F8 · Switching away from WAL can discard healthy committed data | **High, reproduced on local Btrfs.** With a valid committed WAL frame in a closed-process snapshot, WAL reopening recovered both tasks. PERSIST and DELETE reopening unlinked the sidecars and recovered only the checkpointed row, with `quick_check=ok`. The mitigation for a known network-filesystem incident is applied to every non-WAL mode without proving the sidecars corrupt or closing writers. This is a migration/data policy choice, not rollback-journal behavior by itself. `src/superharness/engine/db.py:89–107,182–228,433–455`. C4. |
| F9 · The lease and OS service boundaries can diverge from recorded ownership | **High, reproduced for local lock and generated Linux configuration.** An explicit shared-DB conflict logs a singleton rejection but the losing watcher still writes a heartbeat. An old watcher's atexit callback can remove a successor's filesystem lock. Linux worker setup writes the requested options into YAML but the service installer passes only the worker path to the generator. The generated service omits the canonical state identity, and an actual worker tick under that environment created a second DB beside the source's XDG DB. `src/superharness/commands/inbox_watch.py:463–536,2396–2459,5432–5508`, `src/superharness/engine/service_installer.py:162–179`, `src/superharness/scripts/install-systemd-inbox-watcher.sh:153–204`, `src/superharness/utils/paths.py:142–185`. C11, C16. |
| F10 · Operational telemetry drops progress at its only normal producer | **High for the optional watchdog.** An ordinary transcript-tail tick consumed 20 bytes and committed its cursor while writing zero typed events. Explicitly configuring the emitter recorded the next complete line. No production code configures it. The idle/absolute watchdog uses the legacy deadline branch until an event exists, so flags alone cannot enforce the advertised event-based watchdog. The runtime enqueue and dispatch routes also omit typed `DispatchStarted/Finished` emissions. `src/superharness/engine/events.py:133–218`, `src/superharness/engine/transcript_tail.py:162–217`, `src/superharness/commands/inbox_watch.py:3639–3686`, `src/superharness/engine/lifecycle_rules.py:394–439,479–542`. C10. |
| F11 · Core policy differs by writer | **High when operators rely on the gate.** With strict subtask resolution enabled, `close` refused an open child and kept a task at `review_passed`; `task status done` committed `done` with verification false. Its subtask gate runs after commit and supplies raw `extras_json` where the evaluator reads a `subtasks` list. `close` reads the embedded representation, which is also distinct from the registered child rows. MCP similarly implements its own state update with the common graph but without the version predicate. `src/superharness/commands/task.py:696–712,788–835`, `src/superharness/engine/subtask_gate.py:45–68`, `src/superharness/commands/close.py:188–273`, `src/superharness/mcp/tools/contract.py:69–136`. C8. |
| F12 · CLI transport and queue arguments lose control information | **Medium–high, reproduced.** GNU `script` without `-e` masked a synthetic provider exit 2, changing permanent-block classification and retry exhaustion. The queue printed explicit model and effort overrides but the stored record and final invocation omitted them. For discussions the code adds a resolved model after it builds the wrapper, leaving the execution argv unchanged. Priority help says 1 is highest while the queue selects 3 first. The inbox partial index also includes `stale` and `stopped`, while the DAO's active set excludes them. `src/superharness/commands/inbox_dispatch.py:2050–2068,2179–2196,2355–2442`, `src/superharness/commands/inbox_enqueue.py:265–288,321–323,349–354`, `src/superharness/engine/inbox_dao.py:34–105,153–189`, `src/superharness/engine/db.py:694–699`. C1, C5, C19. |
| F13 · Restart and round edges still admit inconsistent state | **Medium–high, reproduced.** On concurrent cold open SQLite journal setup can report busy, or multiple callers starting migrations from the same version can hit the migration version uniqueness constraint. The winner's database remained sound and reopens succeeded. In a separate discussion, agreeing on round 3 of a two-round discussion reached consensus with its round 1 jobs still pending. The submit path verifies participant and active state but uses the supplied round directly. `src/superharness/engine/db.py:208–233,271–288,392–408,486–520`, `src/superharness/engine/discussion.py:127–230,293–309`. C13, C15. |
| F14 · MCP starts with incompatible dependencies and loses data across the thread boundary | **High for MCP clients, reproduced.** The declared FastMCP floor allows 0.4.1, which raises a TypeError on `host`; the CLI removes its PID file and exits 0 without listening. With FastMCP 3.2.4 the documented HTTP path starts and exposes 14 tools, but seeded task reads returned empty or null. The sync handler runs in a different thread from the captured SQLite connection. The tool catches the ProgrammingError and returns an empty result. A same-DB, instrumented read with the affinity check disabled restored the row, demonstrating cause. A shared connection still requires serialized operations or request-local ownership. `pyproject.toml:23–40`, `src/superharness/mcp/server.py:35–73,228–255`, `src/superharness/mcp/tools/contract.py:24–43`, `src/superharness/mcp/session.py:56–96`. C12. |
| F15 · Retry batches and late finalizers can invalidate unrelated or newer work | **High, reproduced.** One historical failed row with an active replacement collided with the DB uniqueness rule. The error rolled back an unrelated retry that had already been reported as requeued. An independent lock control showed a nonempty queue returning rc 0 when the claim timed out. Reclaiming the same ID as a new attempt and applying the earlier finalizer then changed the new row to failed while keeping its new PID. These are three distinct symptoms of using mutable rows and best-effort status without an attempt identity. `src/superharness/commands/inbox_watch.py:1489–1545`, `src/superharness/engine/inbox_dao.py:192–221,254–269`, `src/superharness/commands/inbox_dispatch.py:640–693,746–780,1061–1075`. C18. |
| F16 · Budget rejection happens after work and can trigger a second execution route | **High for metered SDK dispatch, boundary simulation.** In a fake SDK run the real runner allowed the query to complete with a local effect, calculated $0.45 against a $0.01 limit, then raised. The real delegate handler proceeded to its CLI launch seam after the effect. The SDK receives permission mode and setting sources but no configured budget in its options, and the same fallback catches cost and transport exceptions. No real provider usage was measured. `src/superharness/engine/sdk_runner.py:251–268,287–328`, `src/superharness/commands/delegate.py:1407–1486`. C17. |
| F17 · Shared worker refresh can overwrite active work | **High, reproduced.** With a correct canonical state mapping and a real copied worker, while the first native dispatcher was still running a local agent in that worker, the second claim refreshed the copy and replaced the first process's uncommitted tracked edit. The same replacement occurs with the Python copy implementation. Refresh is protected by a short claim lock but execution takes place in the same worker after the lock is released. `src/superharness/commands/inbox_dispatch.py:884–925,945–968,1095–1106,2201–2219`, `src/superharness/engine/platform_runtime.py:126–191,194–276`. C20. |
| F18 · Human-wait reason is lost across the inbox DAO | **Medium–high, reproduced.** A worker entered `pending_user_approval` and its attempt paused with rc 0. The pause reason appeared in output but the persisted `reason` field was empty. With just `paused_at` aged to 31 minutes, lifecycle expired the attempt while the task was still waiting for approval. Persisting the reason correctly made the same aged attempt survive. Dispatch writes unrecognized `pause_reason` through `set_field`, while paused lifecycle suppression checks `reason`. This permits normal retries to interfere with a human-wait phase. `src/superharness/commands/inbox_dispatch.py:1264–1286,1387–1398`, `src/superharness/engine/inbox.py:464–487`, `src/superharness/engine/inbox_dao.py:376–409`, `src/superharness/engine/lifecycle_rules.py:47–55,264–306`. C21. |

## 5. Core-code quality: decomposition, state, concurrency, errors, types, tests, observability, extensibility, and maintainability

- **Decomposition and layering.** Small, mostly pure helpers for status transitions, planning validation, model tier resolution, failure classification, telemetry validation and worktree selection make individual decisions easy to test. The watcher is 5,610 lines and orchestrates policy, I/O, retry, liveness, discussion reconciliation, learning, and service behavior inside a command module. The dispatcher is 2,512 lines and uses a mutable phase context. `_do_dispatch` provides readable stage names, but cleanup in its ordinary path does not surround every stage with a `finally`, and lower layers still reach back into command helpers (for example the discussion inbox shim imports the watcher to seed FK state). Code ownership boundaries are weaker than the module names imply. `src/superharness/commands/inbox_dispatch.py:44–76,858–942`, `src/superharness/commands/inbox_watch.py:2837–3266`, `src/superharness/engine/inbox.py:221–255`.
- **State and types.** Frozen DAO records, Pydantic schemas, centralized status sets, exception types and typed telemetry are strong seams. YAML-shaped dicts, raw SQL, embedded `extras_json` and parallel child rows persist across migration boundaries and can represent the same logical fact in different ways. DAO CAS is strong where used. Several commands instead read state through one connection, act on it with side effects, and update via a separate transaction. The pass/fail distinction often comes through a bool, an exit code or an empty list with broad exception handling, which is too little information across layers. `src/superharness/engine/tasks_dao.py:18–84,259–348`, `src/superharness/engine/state_reader.py:139–160,244–291`, `src/superharness/engine/state_writer.py:172–235`, `src/superharness/mcp/tools/contract.py:24–66,100–126`.
- **Concurrency and capacity.** Short DB transactions keep queue claim contention tractable. Watcher tick cooldowns, log rotation, one dispatch opportunity per target per tick, per-target spend checks, loop heuristics and review worker bounds help with resource use. The standard inbox has no project-wide or per-agent running-attempt cap in its selection query or launch loop. Capacity scales with time and backlog. The daily budget is historical `benchmark.jsonl` spend, not reserved capacity, and CLI/self-reported cost can be in separate tables. The SDK checks its cost only after the query finishes, and generic SDK failures fall back to the CLI, including a potential post-work budget exception. Spawning before ownership is persisted or replacing a PID at each layer makes accurate teardown difficult. `src/superharness/engine/inbox_dao.py:153–182`, `src/superharness/commands/inbox_watch.py:2813–2834,3178–3260,4019–4060`, `src/superharness/engine/model_budget.py:42–105,138–177`, `src/superharness/engine/sdk_runner.py:251–328`, `src/superharness/commands/delegate.py:1452–1486`.
- **Errors and process recovery.** Permanent failure classification, comparison against prior failures, zone-specific timeouts, a durable recovery counter and owner fallback are ambitious and valuable. Unsuccessful updates often get absorbed so the watcher survives, but that can erase the difference between empty, busy, illegal and successful. `_sqlite_claim_next` catches a real DB exception and returns the same sentinel as an empty queue. `_sqlite_mirror_dispatch` can write a ledger line and then find no active row, including after its sibling subprocess already updated the row. The ordinary PID is a number since process birth, identity and host are absent from the attempt. Recovery and cancellation should use owned process handles or generation-fenced leases. `src/superharness/commands/inbox_dispatch.py:640–693,746–780,1061–1075,1634–1909`, `src/superharness/engine/inbox_dao.py:254–268,342–359`, `src/superharness/commands/inbox_watch.py:1489–1545,1858–2133,3689–3879`.
- **Observability.** SQLite ledger and failure records answer why an orchestration decision was made. Handoffs, summaries, per-task launcher files, separate audit logs, agent/progress snapshots, and the content-addressed dispatch component store add valuable evidence. The prompt component recorder is currently on the SDK route. Distinct JSONL event streams, DB events, transcript offsets, heartbeats and benchmark records have different freshness and durability contracts. The CLI launcher captures output fully and forwards on return, so the parent PTY cannot reliably show live CLI activity. That also makes log-idle heuristics dependent on which launch path runs. Logging is a useful diagnostic layer. It needs a single durable attempt identifier to explain what actually happened. `src/superharness/engine/context_dao.py:35–112`, `src/superharness/commands/delegate.py:1430–1457`, `src/superharness/engine/platform_runtime.py:337–391`, `src/superharness/engine/event_stream.py:17–61`, `src/superharness/engine/events.py:133–218`.
- **Extension and provider contracts.** The harness Protocol and manifest conventions isolate provider flags, model-name differences and capability probes. The current CLI launch consumes only `Invocation.argv`; declared `env` and `cwd` do not travel through that entry point. Discovery has persistence by project/agent/auth/tier and provider bindings, while classifier and orchestrator launch some provider binaries directly through separate argv builders. Provider failures on one surface can therefore differ from worker failures on another. Pi's bounded capture and explicit isolation are useful patterns. MCP binds contract/inbox/handoff/ledger/events tools to a project; its app builds a shared connection and constructs an unused SessionManager object. The wired enqueue approval is process-local, keyed by connection/tool, and no approve tool is registered. YAML modules and Python callbacks use distinct hook registries and event names. These choices make plugin examples easy to add but category-wide guarantees require entry point parity tests. `src/superharness/harnesses/base.py:16–60`, `src/superharness/commands/delegate.py:674–735`, `src/superharness/engine/orchestrator.py:54–114,617–713`, `src/superharness/engine/model_router.py:935–1043`, `src/superharness/mcp/server.py:35–57,101–121,165–207`, `src/superharness/mcp/approval.py:62–121`, `src/superharness/modules/runner.py:13–154`.
- **Tests and maintenance.** The suite covers large parts of the protocol using deterministic offline defaults and temporary state, and includes real Git, SQLite, child processes and locally bound network tests. Both state tables and source-level invariants have targeted tests. Important unit tests assert stubs or source shapes rather than the wiring between components, for example a schedule stub that returns 0 while the actual enqueue entry point exits, and transcript unit tests that configure the emitter manually. Production-state readers use a different path under pytest to hydrate legacy fixtures. The conftest Git fingerprint is valuable and the review also used an independent clone and unmounted the target. The suite total and API/package compatibility claims should point to a measured revision and environment. `tests/conftest.py:17–74,148–212,372–452`, `tests/unit/test_schedule.py:265–285`, `tests/unit/test_transcript_tail.py:295–309`, `src/superharness/engine/state_reader.py:168–241`.

## 6. Executed tests/experiments and their limitations

**Local execution environment.** Linux x86-64 on local Btrfs, kernel 7.2.15-1-omarchy. Python 3.12.16 used SQLite 3.53.1, pytest 9.2.0, FastMCP 0.4.1 and MCP 1.30.0. Python 3.14.8 used SQLite 3.54.0, pytest 9.2.0, FastMCP 3.2.4, MCP 1.30.0, coverage 7.17.3 and pytest-cov 7.1.0. The successful environments used the source checkout as an editable installation inside isolated venvs, local wheels selected against manifest requirements, and `uv pip check` passed. These are explicitly recorded dependency resolutions separate from the repository's locked resolution.

| Run | UTC and result |
| --- | --- |
| Initial dependency and collection probes | 16:36–16:38. Initial Python inventory lacked runtime and test dependencies. Locked offline install could not resolve from the local wheel files. The first full collection attempt produced seven collection errors covering missing CLI shims and xdist ordering. See T1–T2 below. |
| Full Python 3.12, long basetemp | Started 16:38:58. 6,350 passed, 2 failed, 22 skipped, 2 xfailed, 13 warnings in 223.28 s. Both failures came from a test-local plist extraction slice of fixed length. |
| Full Python 3.12, short basetemp | 16:42:53–16:46:39 including the two-test control. The targeted pair passed in 0.36 s, then **6,352 passed, 22 skipped, 2 xfailed, 13 warnings in 225.06 s**, rc 0. |
| Full Python 3.14, coverage | 16:47:17–16:51:18. **6,352 passed, 22 skipped, 2 xfailed, 397 warnings in 238.98 s**, rc 0. Measured 67.01% statement coverage, 33,073 statements, with the configured 56% threshold reached. Key modules rounded to 60% watcher, 69% dispatcher, 62% delegate, 73% operator, 84% auto dispatch, 80% schedule, 85% inbox DAO, 91% tasks DAO, 95% DB, 96% typed events and 0% MCP server. Controls separately exercised the MCP server. |
| Process stress and targeted regressions | Both isolated runtimes passed the five process stress tests with a 35-second test timeout, in 0.79 s on 3.12 and 0.78 s on 3.14. This includes actual child processes, leader/group cleanup and breaker/PID case tests. A separate 3.14 run of the process seam, watcher lock, cross-project overlap and state-dir isolation modules yielded **42 passed in 7.13 s**. |
| Expected-failure check | `--runxfail` on the two dispatch guard tests reproduced both assertions in 0.21 s. Each observed one enqueue where zero was expected. |
| Shell and doctrine checks | Shell entrypoint guard passed for 55 files. Doctrine changelog, paths, spec placeholder, invariant bindings and binary resolution passed; forbidden-pattern and tag gates were unverified; traceability date gate was confounded by shallow history. Remote visibility stayed outside the offline scope. |
| Additional local controls | C1–C21 below include OS process groups, two Python/FastMCP versions, temporary Git worktrees, database restart and lock controls, an isolated loopback MCP connection and synthetic providers. |

**Cross-runtime check.** The two passing full-suite JUnit reports matched on all 6,376 test identities and reported outcomes. JUnit represents expected failures as skips.

**Boundaries.** Collection under `-m "not network and not stress"` found 6,375 selected test items and five deselected stress items, plus one module-level SDK collection skip. Separate collection under `-m network` selected zero. The 22 reported skips also cover six opt-in live provider cases, agent capability cases, removed help commands, absent project rule fixtures, a macOS-only LaunchAgents case and a no-contract fixture. The namespace had only loopback and no external routes. No real provider, credential, installed user's config, remote Git, account, OS user service manager, NFS mount or Windows/macOS runtime was exercised. Generated OS configuration, local Git and SQLite state, synthetic tokens/costs and isolated POSIX process behavior are the measurement surface. Full-suite coverage is statement coverage, with its ordinary instrumentation and test mocks, and cannot establish production path parity.

| Control | Exercised surface and observed result |
| --- | --- |
| C1 | Four held claims returned priority 3 in FIFO order, then 2 then 1. Eight concurrent processes obtained one copy of the fifth item. Persisted schema v39/WAL and SQLite index were inspected. Marking the row stale blocked reenqueuing that task/agent until removal. |
| C2 | Public schedule CLI with two forced-due entries. Preview returned 0 for both with no changes. With explicit agent the run returned 0 after only the first enqueue and kept the schedule bytes unchanged; the repeat returned 1 (duplicate). Omitting the first agent returned 2 (required `--to`) and queued zero. |
| C3 | POSIX launcher with timeout 1. Immediate child rc 0 in 0.008 s. Default TERM child rc 124 in 1.001 s. TERM-ignoring child rc 124 in 3.012 s. Operator group cleanup removed a same-group descendant of a live leader; a separately reaped leader left its group member live. |
| C4 | Real WAL writer checkpointed the first row and committed the second into valid WAL, then exited without clean close. The main/WAL/SHM files were 339,968/20,632/32,768 bytes. Identical snapshot copies opened with the real DB factory. WAL preserved both rows; PERSIST and DELETE preserved one, and every `quick_check` returned ok. |
| C5 | Public enqueue and native dispatch with inert Codex and Pi/other agent binaries. Dirty committed project executed in a detached checkout with canonical state; dirty unborn non-Pi project executed at the original root; unborn Pi failed closed with no agent run. Default Linux PTY changed a stub's exit-2 classification and retry count from 3 to 0. The enqueue printed an inert model/effort override absent from the actual agent argv and inbox schema. |
| C6 | Synthetic Codex called the public handoff and status commands, then explicitly exited 0. Plan and report each persisted correct task phase/handoff with failed inbox, rc 1 and no reason. Ordinary retry produced pending attempt 1/3. Positive control verified and closed the task, giving inbox done and dispatch rc 0. |
| C7 | A fixed valid local planning response described two children and a dependency. Direct orchestration printed both and launched parent only. Auto-dispatch stored two todo children and moved parent to in_progress, stored no dependency, then both plan-only claims failed empty-content validation at retry 3/3. |
| C8 | Held a real write transaction during handoff CLI. After 5.25 s the CLI returned 0 and wrote YAML with zero DB rows. An unlocked call wrote both. Same-date export collision returned 1 with a second DB row. Close refused an unresolved child, then `task status done` returned 0 with verification still false. |
| C9 | Two public one-shot watcher invocations amid a blocking synthetic agent produced two live same-target attempts, with one agent heartbeat pointing to the second. Public stop returned 0, task stopped, inbox failed and prior process still executing. |
| C10 | Normal watcher tick with a synthetic complete line followed by partial line advanced offset to 20 but produced zero DB events. Positive control configured and flushed the emitter after the newline, advanced to 66 and produced one `transcript_progress` event. |
| C11 | Real shared-DB watcher lease conflict with a different filesystem lock path logged a rejection yet committed a heartbeat. A barrier at the tick seam made earlier watcher cleanup remove a newer watcher's PID-stamped lock while the newer process was still alive. |
| C12 | Public MCP start at the declared lower-bound generation (0.4.1) exited 0 without a listener. The 3.2.4 tested combination initialized and listed 14 tools in an isolated loopback namespace. It returned empty/null data for a known task. Instrumentation showed differing connection/request thread IDs and SQLite ProgrammingError. The same-DB instrumented read with thread guard disabled returned the task. |
| C13 | Public discussion start/submit produced correct consensus and two acknowledged round-1 jobs. Two concurrent same-agent replies returned 0 and 1, with one durable reply. Two valid replies to future round 3 produced consensus in a discussion capped at round 2, with both original round-1 jobs still pending. |
| C14 | Direct removal discarded an uncommitted change in a synthetic worktree. A full native dispatch also discarded a stub agent's tracked edit, kept source HEAD/source file intact and left a stale worktree pointer. The path was recreated by benchmark output even though Git no longer listed the worktree. |
| C15 | Three cold SQLite starts with eight competing processes. Two trials saw 7 busy opens and one success. The third saw 1 busy open, 4 version-uniqueness errors and 3 successes. All recovered/reopened at schema 39 with 39 migration rows and `quick_check=ok`. Forcing two readers to share version 0 after WAL setup gave one migration winner and one duplicate-version failure, while two warm opens succeeded. |
| C16 | Fake systemctl permitted Linux service generation with requested interval 47 s, target Codex, recover after 8 min with stale action and timeout 77 s. Generated timer used 15 s and command used both/20/retry, no timeout or canonical state env. Local worker tick without the env created a separate legacy DB. Mapping back to the source project recovered its existing XDG task. |
| C17 | Mocked only the external SDK and CLI launch seams. Synthetic SDK produced a local side effect and token usage; actual budget accounting calculated $0.45 against $0.01 and did a CLI fallback with the effect still present. |
| C18 | Actual retry sweep logged one early requeue, then an active-row duplicate rolled it back along with its ledger entry. Removing the duplicate restored both. A write lock caused a real native dispatcher rc 0 after 5.07 s with pending work and a logged busy claim. Finally, a late completion overwrote a replacement claim of the same inbox ID. |
| C19 | GNU `script` direct child exit-2 control yielded 0 with the shipped flag style and 2 with `-e`. Preparing a discussion launch appended the synthetic model flag to display argv but not to either PTY or plain execution argv; low-effort timeout resolved to 600 s. |
| C20 | Used two native dispatchers with a shared worker and correctly shared SQLite. The second claim refreshed source files and overwrote the first running synthetic agent's edit. The Python copy fallback independently overwrote another synthetic edit. |
| C21 | Real approval-wait task transition paused its attempt with rc 0 and an empty DB reason. Aging only the attempt's pause timestamp failed the attempt at 31 minutes with the task still waiting. With the same timestamp and `reason='awaiting_user_approval'` the inbox stayed paused. |

## 7. Measurement audit for every negative or surprising result, including alternate commands or code-path checks used to rule out setup mistakes

**Test harness audit.**

| Observation | Isolation and verdict |
| --- | --- |
| T1 · Tooling and dependencies | Initial host interpreter had pytest and Pydantic but lacked Click, ruamel.yaml, FastMCP, Build, MCP and coverage tooling. `bwrap --unshare-net` and `unshare -Urn` worked, so a weaker offline approximation was unnecessary. `uv sync --locked --offline --no-index --find-links /wheelhouse` could not resolve the optional Langfuse version across lock targets. `--frozen` avoided that re-resolution and hit an absent exact cryptography 50.0.0 artifact. Installing manifest deps plus dev requirements against cached wheels failed when CPython 3.12 lacked a compatible cached coverage build, then succeeded omitting only pytest-cov and installing the editable clone without dependency resolution. A Bash `time -p` replaced an unavailable external time binary. With the CPython 3.14 wheel set the coverage toolchain and FastMCP 3.2.4 resolved successfully. A temporary two-directory `UV_FIND_LINKS` value was read as one path, so explicit repeated `-f` options supplied both directories. The tests show two locally resolvable environments and leave exact-lock execution unverified. |
| T2 · Collection | `tests/smoke/test_basic.py:25–61` calls `shux` from PATH at collection, and the initial deps-only environment had no console scripts. Editable install gave `shux --version` = 1.86.6 and imports resolved to the clone. The worker diff showed the same illegal-transition cases in different orders. `tests/state_machine/test_transitions.py:53–57,77–84` builds cases from a set; `PYTHONHASHSEED=0` restored identical order. The separate zero-network-marked collection returned pytest rc 5 because the selection contained no tests. Tests with unmarked live-provider opt-in still needed the namespace fence and ordinary skip. |
| T3 · Two failing launchd tests | Both assertions read `plist_text[idx:idx + 200].splitlines()[1]` in `tests/unit/test_install_scripts.py:330–337,394–408`. Parsing the original failing plists with `plistlib.load` returned the intact 167-character canonical paths, including literal `&` after XML decoding. Both referred to existing correct projects. The same interpreter, dependencies, source and test IDs passed with a short basetemp and the entire shortened suite passed twice. The fixed-length fixture reader caused the failures. Launchd execution itself stayed unverified. |
| T4 · Skips and expected failures | The two expected failures were run alone with `--runxfail`. Both hit their documented assertions after one enqueue, and `auto_enqueue_approved` checks active count, dependencies and deadlines while omitting the content and task-path guards under test. The skip distribution is in section 6. An opt-in live provider run and a real SDK client would measure different behavior. The fake SDK tested only its invocation, accounting and fallback boundary. `tests/unit/test_dispatch_safety_guards.py:92–155`, `src/superharness/commands/inbox_watch.py:2720–2777`. |
| T5 · Warnings | The CPython 3.14 warning report predominantly signaled unclosed SQLite objects at collection sites, with minor Click and datetime deprecations also present on 3.12. Inside the same 3.14 namespace, a first small 10-case rerun did not reproduce warnings. A broader targeted `test_dual_watchdog.py` rerun with `PYTHONTRACEMALLOC=4` and `-W always::ResourceWarning` passed six tests and independently attributed repeated resources to test-owned handles from `_setup`, including call sites at lines 70, 93, 147, 175 without closes. The frames at `src/superharness/engine/db.py:122` in the full run indicate where GC ran, so neither the whole warning count nor that line identifies a production connection leak. Other allocations were sampled rather than attributed individually. |
| T6 · Source gate | The repository and clone are both shallow. `git rev-list --count HEAD` = 1, `git cat-file -t HEAD^` fails and the tag list is empty. `git log -1 --format='%h %cs' -- <path>` returns `e776277 2026-11-13` for unrelated files as well as the listed spec paths. The doctrine date gate compares those dates straight against spec metadata at `tests/doctrine/doctrine-guard.sh:817–831`. Its ten date reports are unverified freshness in this snapshot, with no complete history to assign path-change times. The no-pattern warning matched the checked-in commented-only `.doctrine-forbidden` file. Fifteen focused spec-fixture, SQLite journal and concurrency tests passed after these checks. |

**Finding controls.**

- **C1, C15, C18.** C1 starts after schema creation and C15 starts before it to separate steady-state atomic claims from cold-open contention. The independent Btrfs/WAL integrity check after each trial rules out schema loss in those runs. C15b pre-created the WAL-mode header and used a barrier only at the migration entry to prove that two version-0 snapshots independently trigger a duplicate migration even when journal-mode setup succeeds. The same two callers opened schema 39 cleanly. The unique partial index SQL was read from `sqlite_master` rather than inferred from a duplicate message. C18 changed only one active replacement row and demonstrated restored retry processing; counts and ledger rows were checked after handles closed to rule out reading uncommitted state. Its lock control held a real `BEGIN IMMEDIATE`, then read the still-pending row after rollback. The stale-finalizer experiment serializes the relevant interleaving and uses synthetic PIDs without signaling them. It establishes a missing generation predicate independently of timing.
- **C2.** Both schedules were written with the public add command before forcing only their due time. The manual, explicit-agent path confirmed that date comparison and the DB update worked. Long/short path and package choice did not enter the diagnosis. The two entries and unchanged YAML bytes show the exception escaped between the first enqueue and schedule save. The mocked `main.return_value = 0` path in the unit suite bypasses the exit. Repository-wide references show the auto-schedule module and the explicit cron runner use separate data and execution paths.
- **C3, C9, C11.** PID namespace and locally owned processes make the signal controls safe. C3 varies only TERM disposition and then purposefully reaps the leader before cleanup while keeping a descendant in its group. Raw group liveness and `/proc` distinguish a runnable descendant from a zombie. The shipped stress suite covers a live leader and passed. C9 first expected that ordinary stop would leave the attempt launched. It instead changed it to failed. The actual CLI wrapper invokes `_sync_inbox_after_status` after the task update and writes failed without a process signal. The corrected rerun checked the real process state was live and the stub had not emitted its exit marker. A later invocation of the watcher is sufficient to get overlap because dispatch is detached. C11 uses two separate physical lock directories for the DB-lease conflict, then a shared actual lock path with a deterministic test tick barrier to isolate atexit behavior. Its second phase tests the ownership edge between the return of `watch()` and process exit; it does not estimate the frequency of that interleaving.
- **C4.** Disabled automatic checkpoint only for the second insert and confirmed both rows in the writer after commit. The immediate process exit deliberately left ordinary sidecars. SQLite immutable-mode read gave the single main-file row, and the identical WAL control recovered the other row, ruling out an uncommitted transaction or physically missing frame. SQLite accepted each requested mode, and `quick_check=ok` shows a valid database can nevertheless be stale. NFS detection and override tests passed with mocked mount paths; the measured deletion was on local storage and only when using the non-WAL code path.
- **C5, C14, C19, C20.** C5 compares dirty committed and unborn roots directly with Git; a Pi no-HEAD negative is an intended safety check. The fake Codex marks actual invocation by the worker-only argv fragment, so planner probes cannot be mistaken for worker launches. C19 tests the standalone PTY exit contract and checks both wrapper and plain launch argv using the same prepared state. C14 initially treated directory existence as proof no removal happened. `git worktree list --porcelain`, the absent tracked file, and the residual file listing separated Git worktree removal from subsequent benchmark directory creation. Root HEAD and tracked file matched the baseline. C20 keeps the first process waiting on a local marker, verifies its edit before the second claim, then proves the shared worker value at both agents and with the alternate copy backend. It holds canonical state constant; the separate service path test does not explain the overwrite.
- **C6–C8.** C6 writes handoff data and state via the same commands a worker is prompted to use, observes explicit zero exit, and checks two DB authorities separately. The verified-and-closed positive case and no-PTY execution rule out wrapper codes or missing handoffs as the explanation. C7 holds the planning response constant between direct and automatic dispatch, uses valid agent names, and checks normalized `task_dependencies`, task rows and inbox rows. The early failure is the implementation's empty-content gate; no worker or live provider fails. C8's write lock leaves reads working and is released before the positive control. Identical project and date demonstrate the inverse export-path case. Direct DAO reads, filesystem evidence and actual rc distinguish durable success, export success and a reported failure.
- **C10.** Both event arms have the same transcript and project resolver, with a fully controlled file offset. Tested production watcher with no pytest configuration and then an explicitly configured emitter. The first input line was valid, proven by compact JSON content and the persisted 20-byte cursor. The second complete line was persisted by the same tailer once the emitter was present. Grep for initialization and typed dispatch kinds found tests and definitions only. The watchdog's original deadline fallback is legitimate with absent events. The finding is that current runtime wiring systematically makes that case more common, including advancing the cursor.
- **C12.** On 0.4.1, calling the app's `run` directly exposed the TypeError concealed by `run_server` cleanup. On 3.2.4, initial empty text content prompted reading `structuredContent`; both results stayed empty/null. A same-project independent CLI and SQL read found the task, ruling out namespace, JSON decoding and seed mistakes. The traced server read showed different thread IDs and a real SQLite thread-affinity error. Changing only the test connection's affinity behavior restored the known task. This is a diagnostic control for one read, not a recommendation to share an unlocked connection. Connection-close log noise originally included `anyio.ClosedResourceError` after session deletion and a repeated PID-file cleanup after SIGTERM. They are separate from the empty result obtained before teardown.
- **C13, C16, C17.** C13 directly compares valid round 1, concurrent duplicate, and future round 3 in independent projects with the same max round limit. The DB uniqueness error is the expected duplicate loser. In C16, an initial Linux installer attempt failed its documented confirmation check before calling fake systemctl. Setting its expected local confirmation let metadata generation finish. The result describes generated units and an actual worker CLI tick. It leaves systemd execution, cgroup cleanup semantics and timer cadence unmeasured. In C17 the amount is computed from the pinned project's pricing and injected tokens. The observable side effect preceded the fallback. The fake CLI launch seam only records whether the second route was entered.

- **C21.** Both phases retained the same recent task transition and 31-minute pause timestamp. The first stored the ordinary command result and the second supplied the exact skip field. The outcome therefore follows the lost reason, independently of dispatch status, timezone, stale PID handling or a slow test. The watcher also parses and forwards `recover_timeout_minutes` and `recover_action` into `_run_scripts` without reading either parameter there. Zombie recovery uses its own, separate timing and policy. `src/superharness/commands/inbox_watch.py:2837–2847,3049–3054,3689–3699,5533–5601`.

The controls used declared and measured environment differences instead of pushing failures into a single package-level pass rate. In particular, SQLite data loss, task completion divergence, destructive workspace cleanup, shared-state worker refresh and scheduling failures remained reproducible without network, live quota, provider latency, missing executables or dashboard behavior.

## 8. Post-mortem: design pressures, accumulated tradeoffs, likely failure modes, and the highest-leverage improvements

**Design pressures and tradeoffs.** Superharness combines three plausible product directions. The original goal is resumable collaboration across agent products. The small local DB, handoff artifacts, adapter manifests and simple CLI serve that well. Unattended execution added the inbox, watcher phases, retries, budget, Git isolation, and multiple supervisors. Compatibility and operational incidents added preservation rules, legacy shims, YAML ingestion/export, process ID checks, and best-effort telemetry. Moving state to SQLite solved disagreement about task data, while retaining several command surfaces that independently decide when a task is ready, an attempt is complete, or a process is owned. The resulting contracts are less coherent than the storage layer. A broad test suite can pass while the seam between scheduler and CLI exits, or between transcript and emitter, is missing.

**Likely production sequences.** A planning job successfully delivers a plan, the reconciler marks its inbox attempt failed, and the retry path attempts further work while the expected human approval may already be in progress. A worker configured for repeat ticks can run two attempts in one directory; a refresh or unconditional removal can erase precisely the edit an operator expects to review. Timeout or stop can mark state terminal and leave a process able to write. A subsequent claim may inherit the same ID and be finalized by the prior process. Successful durable writes and successful file exports can disagree, causing repeated handoffs or hiding recoverable work. These are progressive outcomes of missing attempt ownership, atomic effect publication and phase-aware finalization. They do not require a remote service outage.

| Order | Improvement | Verification criterion |
| --- | --- | --- |
| P0 · Make worker state and effects attributable | Put project and agent capacity, attempt UUID/generation, machine/process birth identity, start protocol, heartbeat, phase, cancellation intent, versioned finalization and retry schedule in one attempt record. Keep an owner process alive for every launched attempt. Release a slot only after its process group or platform job is gone and the protected result is finalized. Let the process runner hold the real handle/PGID and enforce TERM, bounded grace and KILL. Use the verified lease for admission and release it exactly once. | Two watcher ticks while work is blocked respect the configured cap. Restart, cancellation and expired-lease interleavings leave one accepted finalizer and no live descendants. A late completion cannot change or clear the new attempt, even after retry. |
| P0 · Preserve work and durable commits | Disallow non-interactive fallback to a dirty root when isolation fails. Use per-attempt checkouts or an exclusively leased worker, and preserve uncommitted edits or reachable commits before removal. Move benchmark recording to canonical state. Add a quiescent journal-mode migration that recovers/checkpoints valid WAL via SQLite and makes a verified backup before any quarantine of suspected corruption. | Dirty/unborn, signal and cleanup controls preserve operator and agent edits and report the location. A valid committed WAL frame survives graceful mode transition or a failed migration with a recoverable original. |
| P1 · Define one task transition and outcome service | Share the policy across CLI, state writer, watcher and MCP. Distinguish plan delivered, report delivered, awaiting operator, verified completion, aborted and retryable/permanent errors. Bind handoff/usage/ledger/phase results atomically or make export an explicit post-commit projection, with idempotent request keys. Unify child rows and their policy view and treat plan/dependency persistence plus release of runnable children as one workflow. | Real CLI/DAL instrumentation shows a phase success releases the attempt, a rejected transition never commits, and retrying the same handoff writes once. Child tasks retain content and dependency order after restart. |
| P1 · Make scheduling and adapters return typed outcomes | Use an application-level enqueue API from schedules and hooks, with transactional due-claim and per-occurrence IDs. Apply explicitly documented priority direction, model/effort overrides, and return codes in the actual invocation. Build/execute one invocation object. Separate budget exhaustion, partial execution, rejected work and transport failure; reserve before launch if strict and disallow automatic replay after effects. | Two due tasks run independently, concurrent schedule runners enqueue once, restart resumes due work, and the chosen model/effort appears in actual argv. Both PTY and plain paths give the same synthetic exit results. |
| P1 · Restore delivery and watchdog visibility | Wire the event emitter into actual startup, or write progress plus cursor in one DB transaction. Bound queues and attach attempt IDs to traces, schedules, log records and DB events. Use one thread-local/request SQLite connection per MCP call, a minimum compatible FastMCP constraint and nonzero startup errors. Persist meaningful approval decisions at the same boundary that enforces them. | Synthetic transcript progress survives an ordinary uninstrumented watcher tick and restart. Default MCP loopback handshake and read/write round-trip a real row on the minimum and locked versions. Failures surface as typed upstream failures rather than empty successes. |
| P2 · Reconcile installed-service and test boundaries | Generate per-platform units from the same canonical project identity and normalized settings. Use idempotent installation, launch environment parity and testable source-root/workspace identity. Decompose watcher policy phases behind narrow services. Keep the breadth of regression coverage and add minimal real-interface tests for the failing seam cases. Correct nondeterministic ordering and fixture XML parsing, close DB fixture handles, and make shallow history checks explicitly unverified. | Generated config, manual invocation and real native service produce equivalent command/state bindings. A short and long path suite pass without hash-order errors or accidental host reads, and CI validates mocked-provider end-to-end semantics. |

## 9. Evidence appendix with local file/line references and commands

**Read map.** Production citations in sections 2–5 refer to the pinned Git tree. A few complementary anchors are `docs/ARCHITECTURE.md:10–19,116–186` (declared design), `docs/specs/SPEC-004-task-lifecycle.md:7–36` (stated phase and deadline invariants), `INVARIANTS.md:25–32` (baseline enforceability), `docs/bugs/BUG-2026-06-04-operator-orphans-pytest-swap-storm.md:17–46,60–85` (source of process recovery pressure), and `docs/audits/2026-09-10-arch-audit.md:17–74` (prior project rationale, treated as historical). Representative shipped tests include `tests/state_machine/test_status_transitions.py`, `tests/integration/test_task_lifecycle.py`, `tests/chaos/test_concurrent_writers.py:36–110`, `tests/stress/test_operator_process_lifecycle.py:100–152,158–276` and `tests/conftest.py:51–74,148–211,372–452`. `src/superharness/engine/benchmark.py:52–97` creates the final residual directory in C14, and `src/superharness/commands/task.py:1479–1521,1542–1558` explains the command-path finalization in C9.

**Environment and full-suite reproduction.** Run from the review workspace. The path of the offline wheelhouse and Python executable is specific to this workspace. The commands below recreate the sandbox and effective invocation, with all writable paths in disposable storage. The existing wheelhouses are read-only inputs. Use the exact stated HEAD. Pass only the `offline312` or `offline314` helpers to controls that create or signal child processes.

```bash
repo="$PWD/repos/artificemachine__superharness"
head=e77627733cf38b0eed9b05679c0238d1435f2205
test "$(git --no-optional-locks -C "$repo" rev-parse HEAD)" = "$head"
test -z "$(git --no-optional-locks -C "$repo" status --porcelain=v1 --untracked-files=all)"

scratch=$(mktemp -d "$PWD/.superharness-review-repro.XXXXXXXX")
mkdir "$scratch"/{home,tmp,cache,state,config}
wheelhouse="$PWD/.superharness-review.Y54aCa8Z/wheelhouse"
wheelhouse314="$PWD/.superharness-review.Y54aCa8Z/env314/wheelhouse"
python312=$HOME/.local/share/mise/installs/python/3.12.16
uvbin=$(command -v uv)

GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
  git -c core.hooksPath=/dev/null clone -q --no-local --no-hardlinks "$repo" "$scratch/checkout"
test "$(git --no-optional-locks -C "$scratch/checkout" rev-parse HEAD)" = "$head"

offline() {
  local major="$1"
  shift
  local venv="$scratch/venv" path_suffix="$python312/bin:/offline-bin:/usr/bin:/bin"
  local uv_links=/wheelhouse pip_links=/wheelhouse
  local mounts=()
  if [[ "$major" = 314 ]]; then
    venv="$scratch/venv314"
    path_suffix=/offline-bin:/usr/bin:/bin
    mounts=(--ro-bind "$wheelhouse314" /wheelhouse314)
    uv_links=/wheelhouse314
    pip_links='/wheelhouse314 /wheelhouse'
  fi
  env -i /usr/bin/bwrap --unshare-all --die-with-parent --new-session \
    --hostname superharness-offline --ro-bind /usr /usr \
    --symlink usr/bin /bin --symlink usr/lib /lib --symlink usr/lib /lib64 \
    --dev /dev --proc /proc --dir /run --dir /var \
    --ro-bind /etc/ld.so.cache /etc/ld.so.cache --ro-bind /etc/os-release /etc/os-release \
    --ro-bind "$python312" "$python312" --ro-bind "$uvbin" /offline-bin/uv \
    --ro-bind "$wheelhouse" /wheelhouse "${mounts[@]}" \
    --bind "$scratch" "$scratch" --bind "$scratch/tmp" /tmp --chdir "$scratch/checkout" \
    --setenv PATH "$venv/bin:$path_suffix" --setenv HOME "$scratch/home" \
    --setenv TMPDIR "$scratch/tmp" --setenv XDG_CACHE_HOME "$scratch/cache" \
    --setenv XDG_STATE_HOME "$scratch/state" --setenv XDG_CONFIG_HOME "$scratch/config" \
    --setenv GIT_CONFIG_NOSYSTEM 1 --setenv GIT_CONFIG_GLOBAL /dev/null \
    --setenv PYTHONDONTWRITEBYTECODE 1 --setenv PYTHONNOUSERSITE 1 \
    --setenv PIP_NO_INDEX 1 --setenv PIP_FIND_LINKS "$pip_links" \
    --setenv UV_OFFLINE 1 --setenv UV_FIND_LINKS "$uv_links" \
    --setenv UV_PROJECT_ENVIRONMENT "$venv" --setenv PYTEST_DISABLE_PLUGIN_AUTOLOAD 1 \
    --setenv SUPERHARNESS_TEST_OFFLINE 1 --setenv SUPERHARNESS_NO_AUTO_INSTALL 1 \
    --setenv SUPERHARNESS_SUMMARIZER noop --setenv LANG C.UTF-8 -- "$@"
}
offline312() { offline 312 "$@"; }
offline314() { offline 314 "$@"; }

offline312 cat /proc/net/route /proc/net/dev
offline312 ps -eo pid,ppid,comm
offline312 uv venv --python 3.12 "$scratch/venv"
offline312 bash -o pipefail -c '
  python -c "import tomllib; d=tomllib.load(open(\"pyproject.toml\",\"rb\")); print(*d[\"project\"][\"dependencies\"], *[x for x in d[\"dependency-groups\"][\"dev\"] if not x.startswith(\"pytest-cov\")], \"setuptools>=68\", \"wheel\", sep=\"\\n\")" |
    uv pip install --python "$UV_PROJECT_ENVIRONMENT/bin/python" --offline --no-index -f /wheelhouse -r /dev/stdin
'
offline312 uv pip install --offline --no-index --no-deps --no-build-isolation -e .
offline312 uv pip check
offline312 python -m ensurepip --default-pip
offline312 shux --version

offline314 uv venv --python /usr/bin/python3.14 "$scratch/venv314"
offline314 bash -o pipefail -c '
  python -c "import tomllib; d=tomllib.load(open(\"pyproject.toml\",\"rb\")); print(*d[\"project\"][\"dependencies\"], *d[\"dependency-groups\"][\"dev\"], \"setuptools>=68\", \"wheel\", \"fastmcp==3.2.4\", sep=\"\\n\")" |
    uv pip install --python "$UV_PROJECT_ENVIRONMENT/bin/python" --offline --no-index -f /wheelhouse -f /wheelhouse314 -r /dev/stdin
'
offline314 uv pip install --offline --no-index --no-deps --no-build-isolation -e .
offline314 uv pip check

offline312 bash -c '
  export TMPDIR=/tmp PYTHONHASHSEED=0
  time -p python -m pytest -p xdist.plugin -p pytest_timeout tests/ -q -ra \
    -m "not network and not stress" --timeout=120 -n 4 --dist loadfile \
    -p no:cacheprovider --basetemp /tmp/sh-full --junitxml /tmp/sh-full.xml --tb=short
'
offline314 bash -c '
  export TMPDIR=/tmp PYTHONHASHSEED=0 COVERAGE_FILE=/tmp/coverage-314
  time -p python -m pytest -p xdist.plugin -p pytest_timeout -p pytest_cov.plugin tests/ -q -ra \
    -m "not network and not stress" --timeout=120 -n 4 --dist loadfile \
    -p no:cacheprovider --basetemp /tmp/sh-314 --junitxml /tmp/sh-314.xml --tb=short \
    --cov=superharness --cov-report=term --cov-fail-under=56
'
offline312 python -m pytest -p pytest_timeout tests/stress/ -q -ra \
  -m 'stress and not network' --timeout=35 -p no:cacheprovider --basetemp /tmp/sh-stress --tb=short
offline314 bash -c '
  export TMPDIR=/tmp PYTHONHASHSEED=0
  python -m pytest -p pytest_timeout tests/stress/ -q -ra -m "stress and not network" \
    --timeout=35 -p no:cacheprovider --basetemp /tmp/sh-stress314-final --tb=short
  python -m pytest -p pytest_timeout -q -ra -p no:cacheprovider \
    --basetemp /tmp/sh-process-controls-final --timeout=45 tests/unit/engine/test_process_seam.py \
    tests/unit/test_inbox_watch_lock.py tests/unit/test_watcher_worker_project_overlap.py \
    tests/unit/test_state_dir_isolation_2026_07_09.py
'
offline312 bash src/superharness/scripts/check-shell-entrypoints.sh
offline312 bash -c '
  for gate in changelog forbidden paths version spec invariants traceability binary; do
    bash tests/doctrine/doctrine-guard.sh --check "$gate"
  done
'
```

**Targeted measurement controls.**

```bash
offline312 bash -c '
  export TMPDIR=/tmp PYTHONHASHSEED=0
  python -m pytest -p pytest_timeout -q --timeout=30 -p no:cacheprovider --basetemp /tmp/sh-target --tb=short \
    tests/unit/test_install_scripts.py::test_install_launchd_state_project_defaults_to_project_dir_without_symlink \
    tests/unit/test_install_scripts.py::test_install_launchd_state_project_resolves_symlink_to_source
  python -m pytest --collect-only -q -m "not network and not stress" -p no:cacheprovider tests/ | tail -8
  python -m pytest --runxfail -q --tb=short -p no:cacheprovider --basetemp /tmp/sh-xfail-audit \
    tests/unit/test_dispatch_safety_guards.py::test_plan_approved_with_no_criteria_is_not_dispatched \
    tests/unit/test_dispatch_safety_guards.py::test_plan_approved_with_no_project_path_is_not_dispatched
  python -m pytest -q -ra -p no:cacheprovider --basetemp /tmp/sh-doctrine-control \
    tests/doctrine/test_spec_affected_paths.py tests/unit/test_nfs_journal_mode.py tests/chaos/test_concurrent_writers.py
'
offline314 bash -c '
  export TMPDIR=/tmp PYTHONTRACEMALLOC=4
  python -m pytest -q -ra -p no:cacheprovider --basetemp /tmp/sh-dual-resource \
    -W always::ResourceWarning tests/unit/test_dual_watchdog.py
'
git --no-optional-locks -C "$repo" rev-parse --is-shallow-repository
git --no-optional-locks -C "$repo" rev-list --count HEAD
git --no-optional-locks -C "$repo" log -1 --format='%h %cs' -- README.md
git --no-optional-locks -C "$repo" log -1 --format='%h %cs' -- src/superharness/engine/next_action.py
git --no-optional-locks -C "$repo" cat-file -t HEAD^
```

**Focused control commands.** Each block runs on its own sandbox invocation. Files, signals, server startup and Git changes are confined to the synthetic projects. Output details such as PIDs, generated task IDs, process timing and the distribution of cold-open winners can vary. The tables above record the observed runs. Re-executing C1, C4, C10 and C19 from these embedded commands reproduced the same invariants and the same measured failure mechanisms.

<details>
<summary>C1 · Atomic claim, order, and stale-row uniqueness</summary>

```bash
offline312 python - <<'PY'
import os
import multiprocessing as mp
import sqlite3
import tempfile
from pathlib import Path
from superharness.engine import db, inbox_dao

now = '2026-11-19T16:40:00Z'
agent = 'codex-cli'
with tempfile.TemporaryDirectory(prefix='queue-control-') as tmp:
    project = str(Path(tmp) / 'project')
    (Path(project) / '.superharness').mkdir(parents=True)
    def insert(conn, name, priority, created_at=now):
        conn.execute("INSERT INTO tasks(id,title,owner,status,project_path,created_at) VALUES(?,?,?,'plan_approved',?,?)",
                     (name,name,agent,project,created_at))
        inbox_dao.enqueue(conn,id=name,task_id=name,target_agent=agent,priority=priority,now=created_at)
    with db.managed_connection(project) as conn:
        for name, priority, when in [('one',1,now), ('three-later',3,now), ('three-first',3,'2026-11-19T16:39:59Z'), ('two',2,now)]:
            insert(conn,name,priority,when)
    with db.managed_connection(project) as conn:
        ordered = [inbox_dao.claim_next(conn,target_agent=agent,pid=os.getpid(),now=now).id for _ in range(4)]
        print('four_held_order',ordered)
        assert ordered == ['three-first','three-later','two','one']
    with db.managed_connection(project) as conn:
        print('already_launched_count',len(inbox_dao.get_all(conn,status='launched')))
        insert(conn,'race',2)
    gate=mp.Barrier(8)
    output=mp.Queue()
    def claim():
        gate.wait(10)
        try:
            with db.managed_connection(project) as conn:
                row=inbox_dao.claim_next(conn,target_agent=agent,pid=os.getpid(),now=now)
            output.put((os.getpid(), row.id if row else None))
        except Exception as exc:
            output.put((os.getpid(),str(exc)))
    workers=[mp.Process(target=claim) for _ in range(8)]
    for proc in workers:
        proc.start()
    results=[output.get(timeout=10) for _ in workers]
    for proc in workers:
        proc.join(5)
        assert proc.exitcode == 0
    winners=[v for _,v in results if v is not None]
    print('eight_competing_processes', sorted(results), 'winners', winners)
    assert winners == ['race']
    with db.managed_connection(project) as conn:
        print('real_db_header',conn.execute('PRAGMA user_version').fetchone()[0],conn.execute('PRAGMA journal_mode').fetchone()[0])
        print('inbox_index',conn.execute("SELECT sql FROM sqlite_master WHERE name='idx_inbox_unique_task_agent'").fetchone()[0].strip())
        inbox_dao.mark_stale(conn,'race',reason='control')
        try:
            inbox_dao.enqueue(conn,id='race-next',task_id='race',target_agent=agent,now=now)
        except Exception as exc:
            print('stale_blocks_requeue',type(exc).__name__,str(exc))
        else:
            raise AssertionError('stale did not block a requeue')
        inbox_dao.remove(conn,'race')
        assert inbox_dao.enqueue(conn,id='race-next',task_id='race',target_agent=agent,now=now).status=='pending'
    print('after_explicit_stale_removal', 'pending')
PY
```

</details>

<details>
<summary>C2 · Public recurring schedule lifecycle</summary>

```bash
offline312 python - <<'PY'
import os, subprocess, tempfile, sys
import yaml
from pathlib import Path
from superharness.engine import db, inbox_dao

agent='codex-cli'
when='2001-01-01T00:00:00Z'
def invoke(args):
    return subprocess.run(['shux',*args],text=True,capture_output=True,timeout=15)
with tempfile.TemporaryDirectory(prefix='schedule-control-') as tmp:
    root=Path(tmp)
    for omit_first_agent in [False,True]:
        p=root/('implicit' if omit_first_agent else 'explicit')
        h=p/'.superharness'
        h.mkdir(parents=True)
        f=h/'scheduled.yaml'
        with db.managed_connection(str(p)) as conn:
            for name in ('first','second'):
                conn.execute("INSERT INTO tasks(id,title,owner,status,project_path,created_at) VALUES(?,?,?,'plan_approved',?,?)",(name,name,agent,str(p),when))
                result=invoke(['schedule','add',name,'--cron','* * * * *','--project',str(p)]
                              + ([] if name=='first' and omit_first_agent else ['--agent',agent]))
                assert result.returncode==0,(result.stdout,result.stderr)
        doc=yaml.safe_load(f.read_text())
        for item in doc['schedules']:
            item['next_run']=when
        f.write_text(yaml.safe_dump(doc))
        baseline=f.read_bytes()
        for label, args in [('preview',['--dry-run']),('real',[]),('repeat',[])]:
            r=invoke(['schedule','run','--project',str(p),*args])
            with db.managed_connection(str(p)) as conn:
                rows=[(x.task_id,x.status) for x in inbox_dao.get_all(conn)]
            print(p.name,label,'rc',r.returncode,'queue',rows,'same_schedule',f.read_bytes()==baseline,
                  'stdout',r.stdout.replace('\n',' | '),'stderr',r.stderr.replace('\n',' | '))
            assert f.read_bytes()==baseline
            if label=='preview':
                assert r.returncode==0 and not rows and 'second' in r.stdout
            elif omit_first_agent:
                assert r.returncode==2 and not rows
            else:
                assert rows==[('first','pending')] and r.returncode==(0 if label=='real' else 1)
PY
```

</details>

<details>
<summary>C3 · Hard-deadline and process-group positive/negative controls</summary>

```bash
offline312 timeout 20 python - <<'PY'
import json, os, signal, subprocess, sys, tempfile, time
from pathlib import Path
from superharness.commands.inbox_dispatch import _run_with_timeout
from superharness.engine.operator import Operator

def check(alarm, source):
    t=time.monotonic()
    code=_run_with_timeout(alarm,[sys.executable,'-c',source])
    return code,round(time.monotonic()-t,3)
samples = {
    'normal': check(1,'pass'),
    'default_term': check(1,'import time; time.sleep(3)'),
    'ignores_term': check(1,'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(3)'),
}
print('timeout_control',samples)
assert samples['normal'][0]==0
assert samples['default_term'][0]==124 and 0.85<samples['default_term'][1]<2.0
assert samples['ignores_term'][0]==124 and samples['ignores_term'][1]>=2.8

with tempfile.TemporaryDirectory(prefix='pgid-control-') as tmp:
    project=Path(tmp)/'project'
    (project/'.superharness').mkdir(parents=True)
    operator=Operator(project)
    parent_code = r"""
import json,os,subprocess,sys,time
proc=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
print(json.dumps([os.getpid(),proc.pid,os.getpgid(proc.pid)]),flush=True)
if sys.argv[1]=='live': time.sleep(30)
"""
    def state(pid):
        try:
            return Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()[0]
        except FileNotFoundError:
            return 'gone'
    for case in ['live','already-reaped']:
        proc=subprocess.Popen([sys.executable,'-c',parent_code,case],start_new_session=True,
                              stdout=subprocess.PIPE,text=True)
        try:
            leader,leaf,group=json.loads(proc.stdout.readline())
            assert leader==group==proc.pid
            if case=='already-reaped':
                assert proc.wait(timeout=5)==0
                try: os.getpgid(leader)
                except ProcessLookupError: pass
                else: raise AssertionError('leader was still visible')
                os.killpg(group,0)
            old=state(leaf)
            operator._kill_process(proc,'watcher-control')
            deadline=time.monotonic()+1
            while case=='live' and state(leaf) not in ('gone','Z') and time.monotonic()<deadline:
                time.sleep(0.01)
            status=state(leaf)
            print('group_control',case,'leader_rc',proc.returncode,'leaf_before',old,'leaf_after',status,
                  'group_exists_after',end=' ')
            try: os.killpg(group,0)
            except ProcessLookupError: print(False)
            else: print(True)
            assert old not in ('gone','Z')
            assert (status in ('gone','Z')) == (case=='live')
        finally:
            try: os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            proc.wait(timeout=5)
PY
```

</details>

<details>
<summary>C4 · Committed WAL preservation across journal modes</summary>

```bash
offline312 python - <<'PY'
import os, shutil, sqlite3, subprocess, sys, tempfile
from pathlib import Path
from superharness.engine import db
from superharness.utils.paths import resolve_active_state_db_path
payload=r"""
import os,sys
from superharness.engine import db
p=sys.argv[1]
c=db.get_connection(p)
db.init_db(c)
c.execute("INSERT INTO tasks(id,title,status,created_at) VALUES('checkpointed','checkpointed','todo','2026-11-19T00:00:00Z')")
c.commit()
print('checkpoint',tuple(c.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()),flush=True)
c.execute('PRAGMA wal_autocheckpoint=0')
c.execute("INSERT INTO tasks(id,title,status,created_at) VALUES('committed-wal','committed-wal','todo','2026-11-19T00:00:01Z')")
c.commit()
print('writer_verified', [r[0] for r in c.execute('SELECT id FROM tasks ORDER BY id')],flush=True)
os._exit(0)
"""
with tempfile.TemporaryDirectory(prefix='sqlite-wal-control-') as tmp:
    root=Path(tmp)
    src=root/'source'
    (src/'.superharness').mkdir(parents=True)
    subprocess.run([sys.executable,'-c',payload,str(src)],check=True,timeout=15)
    dbpath=Path(resolve_active_state_db_path(str(src)))
    print('file_sizes',[Path(f'{dbpath}{s}').stat().st_size for s in ('','-wal','-shm')])
    prove=sqlite3.connect(dbpath.as_uri()+'?immutable=1',uri=True)
    assert [r[0] for r in prove.execute('SELECT id FROM tasks ORDER BY id')]==['checkpointed']
    prove.close()
    for mode in ['WAL','PERSIST','DELETE']:
        p=root/mode.lower()
        (p/'.superharness').mkdir(parents=True)
        snapshot=Path(resolve_active_state_db_path(str(p)))
        snapshot.parent.mkdir(parents=True,exist_ok=True)
        for suffix in ('','-wal','-shm'):
            shutil.copy2(Path(f'{dbpath}{suffix}'),Path(f'{snapshot}{suffix}'))
        os.environ['SUPERHARNESS_JOURNAL_MODE']=mode
        with db.managed_connection(str(p)) as conn:
            print('reopen',mode,'actual',conn.execute('PRAGMA journal_mode').fetchone()[0],
                  'quick_check',conn.execute('PRAGMA quick_check').fetchone()[0],end=' ')
            ids=[r[0] for r in conn.execute('SELECT id FROM tasks ORDER BY id')]
            print(ids)
            assert ids==(['checkpointed','committed-wal'] if mode=='WAL' else ['checkpointed'])
PY
```

</details>

<details>
<summary>C5 · Native CLI dispatch, Git HEAD, launcher argv and PTY comparison</summary>

```bash
offline312 python - <<'PY'
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from superharness.engine import db, inbox_dao

when='2026-11-19T15:00:00Z'
with tempfile.TemporaryDirectory(prefix='dispatch-control-') as tmp:
    root=Path(tmp)
    bindir=root/'bin'; bindir.mkdir()
    for name in ('claude','gemini','opencode','pi','hermes'):
        f=bindir/name
        f.write_text('#!/bin/sh\nexit 127\n')
        f.chmod(0o755)
    codex=bindir/'codex'
    codex.write_text("""#!/usr/bin/env python
import json, os, sys
if '--skip-git-repo-check' not in sys.argv:
    sys.exit(127)
with open(os.environ['LOCAL_AGENT_EVIDENCE'], 'a') as log:
    print(json.dumps([os.getcwd(), os.getenv('SUPERHARNESS_STATE_PROJECT'), sys.argv[1:-1]]),file=log)
print('local stand-in launcher exit 2',file=sys.stderr)
sys.exit(2)
""")
    codex.chmod(0o755)
    def git(project, *args, check=True):
        return subprocess.run(['git','-C',str(project),*args],check=check,text=True,capture_output=True,timeout=10)
    def setup(label, has_head, agent):
        p=root/label
        for sub in ('handoffs','discussions'):
            (p/'.superharness'/sub).mkdir(parents=True,exist_ok=True)
        (p/'.superharness'/'profile.yaml').write_text('require_tdd: false\nautonomy: manual\n')
        git(p,'init','-q')
        if has_head:
            git(p,'-c','user.name=Offline Control','-c','user.email=control@example.invalid','commit','--allow-empty','-qm','fixture')
        (p/'user-dirty.txt').write_text('local synthetic untracked work')
        with db.managed_connection(str(p)) as conn:
            conn.execute("INSERT INTO tasks(id,title,owner,status,project_path,created_at,workflow,acceptance_criteria,effort) VALUES('task','Synthetic task',?,'plan_approved',?,?,'implementation','[\"criterion\"]','low')",(agent,str(p),when))
        return p
    for label, head, agent, no_pty in [
        ('head-ok',True,'codex-cli',True),('no-head',False,'codex-cli',True),
        ('pi-no-head',False,'pi',True),('pty-default',True,'codex-cli',False),
    ]:
        p=setup(label,head,agent)
        evidence=root/(label+'.jsonl')
        env=os.environ | {'PATH':str(bindir)+os.pathsep+os.environ['PATH'],'LOCAL_AGENT_EVIDENCE':str(evidence),
                          'SUPERHARNESS_FORCE_NO_SDK':'1','SUPERHARNESS_NO_PTY_WRAP':'1' if no_pty else '0'}
        enq=subprocess.run([sys.executable,'-m','superharness.commands.inbox_enqueue','--to',agent,'--task','task','--project',str(p),
                            '--id','one','--model','synthetic-override','--effort','xhigh'],
                           capture_output=True,text=True,env=env,timeout=15)
        print(label,'git_head',git(p,'rev-parse','--verify','HEAD',check=False).returncode,
              'dirty',git(p,'status','--porcelain','--','user-dirty.txt').stdout.strip(),
              'enqueue',enq.returncode,enq.stdout.replace('\n',' | '),enq.stderr)
        assert enq.returncode==0
        launch=subprocess.run([sys.executable,'-m','superharness.commands.inbox_dispatch','--project',str(p),'--to',agent,
                               '--non-interactive','--launcher-timeout','10'],capture_output=True,text=True,env=env,timeout=20)
        with db.managed_connection(str(p)) as conn:
            row=inbox_dao.get(conn,'one')
            print(label,'dispatch',launch.returncode,'db',row.status,row.retry_count,repr(row.failed_reason),
                  'override_columns',[r[1] for r in conn.execute('PRAGMA table_info(inbox)') if 'override' in r[1]])
        print('  stdout',launch.stdout.strip().replace('\n',' | '))
        print('  stderr',launch.stderr.strip().replace('\n',' | '))
        record=json.loads(evidence.read_text()) if evidence.exists() else None
        print('  agent',record,'script',shutil.which('script'))
        if label=='head-ok':
            assert record and record[0]!=str(p) and record[1]==str(p) and row.retry_count==3
            assert 'synthetic-override' not in record[2]
        elif label=='no-head':
            assert record and record[0]==str(p) and record[1] is None
        elif label=='pi-no-head':
            assert record is None and row.status=='failed' and row.retry_count==3 and 'committed HEAD' in row.failed_reason
        else:
            assert record and row.retry_count==0
PY
```

</details>

<details>
<summary>C6 · Plan, report and verified-close completion via real CLI</summary>

```bash
offline312 python - <<'PY'
import os, subprocess, sys, tempfile
from pathlib import Path
from superharness.commands.inbox_watch import _auto_retry_failed
from superharness.engine import db, inbox_dao
agent='codex-cli'
with tempfile.TemporaryDirectory(prefix='completion-control-') as tmp:
    root=Path(tmp)
    bindir=root/'bin'; bindir.mkdir()
    for name in ('claude','gemini','opencode','pi','hermes'):
        f=bindir/name; f.write_text('#!/bin/sh\nexit 127\n'); f.chmod(0o755)
    codex=bindir/'codex'
    codex.write_text("""#!/usr/bin/env python
import os, subprocess, sys
if '--skip-git-repo-check' not in sys.argv:
    sys.exit(127)
kind=os.environ['LOCAL_FINISH_CASE']
def shux(*args):
    subprocess.run(['shux',*args],check=True,timeout=5)
def status(value):
    shux('task','status','--id','task','--status',value,'--actor','codex-cli','--summary','synthetic local status')
if kind=='plan':
    shux('handoff','write','--task','task','--phase','plan','--from','codex-cli','--to','owner',
         '--plan','Criterion: put one sentinel in the synthetic output','--tdd-red','test_sentinel',
         '--tdd-green','provide sentinel','--tdd-refactor','none')
    status('plan_proposed')
else:
    status('in_progress')
    shux('handoff','write','--task','task','--phase','report','--from','codex-cli','--to','owner',
         '--outcome','Synthetic report body','--tests-passed')
    status('report_ready')
    if kind=='done':
        shux('verify','--id','task','--method','synthetic local validation','--result','pass')
        shux('close','--id','task','--actor','codex-cli','--summary','synthetic done')
print('fixture explicitly exiting 0')
""")
    codex.chmod(0o755)
    for case,initial in [('plan','todo'),('report','plan_approved'),('done','plan_approved')]:
        p=root/case
        h=p/'.superharness'
        (h/'handoffs').mkdir(parents=True)
        (h/'profile.yaml').write_text('require_tdd: false\nautonomy: manual\nauto_retry: true\n')
        project=str(p)
        with db.managed_connection(project) as c:
            c.execute("INSERT INTO tasks(id,title,owner,status,project_path,created_at,workflow,acceptance_criteria,effort) VALUES('task','Synth task',?,?,?,?, 'implementation','[\"sentinel\"]','low')",(agent,initial,project,db.now_iso()))
            inbox_dao.enqueue(c,id='first',task_id='task',target_agent=agent,project_path=project,
                              plan_only=case=='plan',now=db.now_iso())
        env=os.environ | {'PATH':str(bindir)+os.pathsep+os.environ['PATH'],'LOCAL_FINISH_CASE':case,
                           'SUPERHARNESS_NO_PTY_WRAP':'1','SUPERHARNESS_FORCE_NO_SDK':'1'}
        result=subprocess.run([sys.executable,'-m','superharness.commands.inbox_dispatch','--project',project,
                               '--to',agent,'--non-interactive','--launcher-timeout','20'],env=env,
                              capture_output=True,text=True,timeout=27)
        with db.managed_connection(project) as c:
            snapshot=tuple(c.execute("SELECT status,verified FROM tasks WHERE id='task'").fetchone())
            handoffs=[tuple(r) for r in c.execute('SELECT phase,status FROM handoffs')]
            item=inbox_dao.get(c,'first')
        print(case,'task',snapshot,'handoffs',handoffs,'inbox',item.status,item.retry_count,repr(item.failed_reason),
              'dispatch_rc',result.returncode,'successful_child','fixture explicitly exiting 0' in result.stdout)
        print('tail',result.stdout.splitlines()[-5:],result.stderr.splitlines()[-5:])
        assert 'fixture explicitly exiting 0' in result.stdout
        if case=='done':
            assert (snapshot[0],item.status,result.returncode)==('done','done',0)
        else:
            assert (snapshot[0],item.status,result.returncode)==({'plan':'plan_proposed','report':'report_ready'}[case],'failed',1)
            _auto_retry_failed(project)
            with db.managed_connection(project) as c:
                after=inbox_dao.get(c,'first')
                print('after_original_auto_retry',after.status,after.retry_count)
                assert (after.status,after.retry_count)==('pending',1)
PY
```

</details>

<details>
<summary>C7 · Fixed planning response through two orchestration entry points</summary>

```bash
offline312 python - <<'PY'
import json, os, subprocess, sys, tempfile
from pathlib import Path
from superharness.engine import db
agent='codex-cli'
with tempfile.TemporaryDirectory(prefix='decompose-control-') as tmp:
    root=Path(tmp)
    bindir=root/'bin'; bindir.mkdir()
    for name in ('claude','gemini','opencode','pi','hermes'):
        f=bindir/name; f.write_text('#!/bin/sh\nexit 127\n'); f.chmod(0o755)
    f=bindir/'codex'
    f.write_text("""#!/usr/bin/env python
import json,sys
if '--skip-git-repo-check' in sys.argv:
    print('DIRECT_AGENT_EXECUTION')
else:
    print(json.dumps({'owner':'codex-cli','tier':'max','effort':'high','decompose':True,
        'rationale':'fixed local plan','subtasks':[
           {'id':'child-a','title':'Implement A','owner':'codex-cli','tier':'mini','effort':'low','blocked_by':None,'estimated_tokens':600},
           {'id':'child-b','title':'Implement B','owner':'codex-cli','tier':'mini','effort':'low','blocked_by':'child-a','estimated_tokens':800},
        ]}))
""")
    f.chmod(0o755)
    env=os.environ | {'PATH':str(bindir)+os.pathsep+os.environ['PATH'],
                       'SUPERHARNESS_NO_PTY_WRAP':'1','SUPERHARNESS_FORCE_NO_SDK':'1',
                       'SUPERHARNESS_CONFIRM_NON_INTERACTIVE':'YES'}
    for mode,status in [('direct','plan_approved'),('automatic','todo')]:
        p=root/mode
        h=p/'.superharness'
        (h/'handoffs').mkdir(parents=True)
        (h/'profile.yaml').write_text('autonomy: manual\nrequire_tdd: false\nrequire_subtask_resolution: true\n')
        project=str(p)
        with db.managed_connection(project) as c:
            c.execute("INSERT INTO tasks(id,title,owner,status,project_path,created_at,workflow,acceptance_criteria,effort) VALUES('parent','Synthetic parent',?,?,?,?, 'implementation','[\"Plan A and B\"]','high')",(agent,status,project,db.now_iso()))
        if mode=='direct':
            args=['delegate','parent','--to',agent,'--orchestrate','--non-interactive','--skip-preflight']
        else:
            args=['auto-dispatch','--orchestrate','--agent',agent]
        result=subprocess.run(['shux',*args,'--project',project],env=env,text=True,capture_output=True,timeout=20)
        print(mode,'rc',result.returncode,result.stdout.strip().replace('\n',' | '),result.stderr.strip().replace('\n',' | '))
        with db.managed_connection(project) as c:
            tasks=[tuple(r) for r in c.execute('SELECT id,status,parent_id,acceptance_criteria,context,extras_json FROM tasks ORDER BY id')]
            deps=[tuple(r) for r in c.execute('SELECT * FROM task_dependencies')]
            queued=[tuple(r) for r in c.execute('SELECT task_id,status,plan_only FROM inbox ORDER BY task_id')]
        print(mode,'tasks',tasks,'deps',deps,'queued',queued)
        assert result.returncode==0
        if mode=='direct':
            assert len(tasks)==1 and not queued and 'Decomposed into 2 subtasks' in result.stdout and 'DIRECT_AGENT_EXECUTION' in result.stdout
        else:
            assert tasks[-1][1]=='in_progress' and len(queued)==2 and not deps
            for _ in range(2):
                run=subprocess.run([sys.executable,'-m','superharness.commands.inbox_dispatch','--project',project,
                                    '--to',agent,'--non-interactive','--launcher-timeout','10'],
                                   env=env,text=True,capture_output=True,timeout=20)
                print('child_dispatch',run.returncode,run.stdout.strip().replace('\n',' | '),run.stderr.strip().replace('\n',' | '))
                assert run.returncode==1 and 'has no acceptance criteria' in run.stderr and 'DIRECT_AGENT_EXECUTION' not in run.stdout
            with db.managed_connection(project) as c:
                child_outcomes=[tuple(r) for r in c.execute('SELECT task_id,status,retry_count,max_retries FROM inbox ORDER BY task_id')]
            print('child_outcomes',child_outcomes)
            assert child_outcomes==[('child-a','failed',3,3),('child-b','failed',3,3)]
PY
```

</details>

<details>
<summary>C8 · Handoff persistence under lock/export conflict and close parity</summary>

```bash
offline312 python - <<'PY'
import os, subprocess, tempfile, time
from pathlib import Path
from superharness.engine import db
agent='codex-cli'
with tempfile.TemporaryDirectory(prefix='persistent-boundaries-') as tmp:
    p=Path(tmp)/'project'
    h=p/'.superharness'; h.mkdir(parents=True)
    (h/'profile.yaml').write_text('autonomy: manual\nrequire_subtask_resolution: true\n')
    project=str(p)
    with db.managed_connection(project) as c:
        c.execute("INSERT INTO tasks(id,title,owner,status,project_path,created_at,extras_json) VALUES('task','Synthetic local task',?,'review_passed',?,?,?)",
                  (agent,project,db.now_iso(),'{"subtasks":[{"id":"task.child","status":"pending"}]}'))
    def shux(*args):
        start=time.monotonic()
        r=subprocess.run(['shux',*args,'--project',project],text=True,capture_output=True,timeout=15)
        return r,round(time.monotonic()-start,2)
    def observe():
        with db.managed_connection(project) as c:
            return (tuple(c.execute("SELECT status,verified FROM tasks WHERE id='task'").fetchone()),
                    [r[0] for r in c.execute("SELECT json_extract(metadata,'$.outcome') FROM handoffs ORDER BY id")],
                    sorted(p.name for p in (h/'handoffs').glob('*.yaml')))
    arguments=['handoff','write','--task','task','--phase','report','--from',agent,'--to','owner','--date','2026-11-19T00:00:00Z']
    hold=db.get_connection(project)
    hold.execute('BEGIN IMMEDIATE')
    try:
        r,dt=shux(*arguments,'--outcome','blocked database','--out','locked.yaml')
    finally:
        hold.rollback()
        hold.close()
    print('locked_handoff',r.returncode,dt,observe(),r.stdout.splitlines()[:2],r.stderr.splitlines()[:2])
    assert r.returncode==0 and observe()[1:]==([],['locked.yaml'])
    r,dt=shux(*arguments,'--outcome','first sqlite append')
    print('ordinary_handoff',r.returncode,dt,observe())
    assert r.returncode==0 and observe()[1]==['first sqlite append']
    r,dt=shux(*arguments,'--outcome','second sqlite append despite export conflict')
    print('duplicate_export_path',r.returncode,dt,observe(),r.stderr.strip())
    assert r.returncode==1 and len(observe()[1])==2 and len(observe()[2])==2
    close,_=shux('close','--id','task','--actor',agent,'--summary','unresolved case')
    print('close_gate',close.returncode,observe()[0],close.stderr.splitlines()[:2])
    assert close.returncode==1 and 'still open' in close.stderr and observe()[0]==('review_passed',0)
    status,_=shux('task','status','--id','task','--status','done','--actor',agent,'--summary','same task')
    print('task_status_done',status.returncode,observe()[0],status.stdout.strip(),status.stderr.strip())
    assert status.returncode==0 and observe()[0]==('done',0)
PY
```

</details>

<details>
<summary>C9 · Concurrent watcher ticks and ordinary task stop</summary>

```bash
offline312 python - <<'PY'
import json, os, subprocess, sys, tempfile, time
from pathlib import Path
from superharness.engine import db, inbox_dao
agent='codex-cli'
with tempfile.TemporaryDirectory(prefix='watcher-capacity-') as tmp:
    root=Path(tmp)
    p=root/'project'
    h=p/'.superharness'
    (h/'handoffs').mkdir(parents=True)
    (h/'profile.yaml').write_text('autonomy: manual\nauto_dispatch: false\nauto_retry: false\n')
    bindir=root/'bin'; bindir.mkdir()
    for name in ('claude','gemini','opencode','pi','hermes'):
        f=bindir/name; f.write_text('#!/bin/sh\nexit 127\n'); f.chmod(0o755)
    f=bindir/'codex'
    f.write_text("""#!/usr/bin/env python
import json,os,subprocess,sys,time
from pathlib import Path
if '--skip-git-repo-check' not in sys.argv: sys.exit(127)
name=os.environ['LOCAL_TASK']
sync_dir=Path(os.environ['LOCAL_SYNC'])
subprocess.run(['shux','task','status','--id',name,'--actor','codex-cli',
                '--status','in_progress','--summary','synthetic local runner'],check=True,timeout=5)
(sync_dir/(name+'.json')).write_text(json.dumps([os.getpid(),os.getppid(),os.getpgid(0)]))
try:
    deadline=time.monotonic()+20
    while not (sync_dir/'release').is_file() and time.monotonic()<deadline:
        time.sleep(0.03)
finally:
    (sync_dir/(name+'.exited')).touch()
""")
    f.chmod(0o755)
    env=os.environ | {'PATH':str(bindir)+os.pathsep+os.environ['PATH'],'LOCAL_SYNC':tmp,
                       'SUPERHARNESS_NO_PTY_WRAP':'1','SUPERHARNESS_FORCE_NO_SDK':'1'}
    project=str(p)
    with db.managed_connection(project) as c:
        for name,prio in [('one',3),('two',2)]:
            c.execute("""INSERT INTO tasks
                (id,title,owner,status,project_path,created_at,plan_approved_at,workflow,acceptance_criteria,effort)
                VALUES(?,?,?,'plan_approved',?,?,?,'implementation','["synthetic AC"]','low')""",
                      (name,name,agent,project,db.now_iso(),db.now_iso()))
            inbox_dao.enqueue(c,id=name,task_id=name,target_agent=agent,project_path=project,
                              priority=prio,now=db.now_iso())
    def wait_for(path, seconds=10):
        end=time.monotonic()+seconds
        while not path.exists() and time.monotonic()<end:
            time.sleep(0.025)
        assert path.exists(),path
    try:
        seen={}
        for name in ['one','two']:
            tick=subprocess.run(['shux','watch','--once','--project',project,'--to',agent,
                                 '--launcher-timeout','25'],env=env|{'LOCAL_TASK':name},
                                text=True,capture_output=True,timeout=12)
            print('tick',name,tick.returncode,tick.stdout.splitlines()[-6:],tick.stderr.splitlines()[-6:])
            assert tick.returncode==0
            m=root/(name+'.json')
            wait_for(m)
            seen[name]=json.loads(m.read_text())
            assert not (root/(name+'.exited')).exists()
        with db.managed_connection(project) as c:
            print('simultaneously_claimed',[(r.id,r.status,r.pid) for r in inbox_dao.get_all(c)],
                  'agent_heartbeat',[tuple(r) for r in c.execute("SELECT agent,task_id,pid FROM agent_heartbeats WHERE agent='codex-cli'")],
                  'local_processes',seen)
            assert all(r.status=='launched' for r in inbox_dao.get_all(c))
            assert c.execute("SELECT task_id FROM agent_heartbeats WHERE agent='codex-cli'").fetchone()[0]=='two'
        stopped=subprocess.run(['shux','task','status','--id','one','--status','stopped',
                                '--actor',agent,'--reason','artificial test stop','--project',project],
                                text=True,capture_output=True,timeout=5,env=env)
        print('normal_stop_cli',stopped.returncode,stopped.stdout.strip(),stopped.stderr.strip())
        assert stopped.returncode==0
        with db.managed_connection(project) as c:
            print('after_stop',c.execute("SELECT status FROM tasks WHERE id='one'").fetchone()[0],
                  inbox_dao.get(c,'one').status,'stub_still_alive',Path(f"/proc/{seen['one'][0]}").exists())
            assert inbox_dao.get(c,'one').status=='failed'
            assert not (root/'one.exited').exists()
            with open(f"/proc/{seen['one'][0]}/stat") as live:
                assert live.read().rsplit(') ',1)[1].split()[0] not in ('Z','X')
            assert Path(f"/proc/{seen['one'][0]}").exists()
    finally:
        (root/'release').touch()
        for name in ['one','two']:
            if (root/(name+'.json')).exists(): wait_for(root/(name+'.exited'),5)
        end=time.monotonic()+5
        while time.monotonic()<end:
            with db.managed_connection(project) as c:
                active=inbox_dao.get_all(c,status='launched')
            if not active: break
            time.sleep(0.025)
PY
```

</details>

<details>
<summary>C10 · Ordinary watcher and configured transcript emitter</summary>

```bash
offline312 python - <<'PY'
import os, subprocess, tempfile
from pathlib import Path
from superharness.commands.inbox_watch import _claude_transcript_dir, _run_transcript_tail_if_enabled
from superharness.engine import db, events, inbox_dao

with tempfile.TemporaryDirectory(prefix='transcript-control-') as tmp:
    p=Path(tmp)/'project'
    h=p/'.superharness'; h.mkdir(parents=True)
    (h/'profile.yaml').write_text('transcript_tail: true\nauto_dispatch: false\nautonomy: manual\n')
    project=str(p)
    tdir=Path(_claude_transcript_dir(project)); tdir.mkdir(parents=True)
    transcript=tdir/'synthetic.jsonl'
    now=db.now_iso()
    with db.managed_connection(project) as c:
        c.execute("""INSERT INTO tasks(id,title,owner,status,project_path,created_at,in_progress_at,updated_at)
                     VALUES('task','Synthetic task','claude-code','in_progress',?,?,?,?)""",(project,now,now,now))
        inbox_dao.enqueue(c,id='dispatch-one',task_id='task',target_agent='claude-code',project_path=project,now=now)
        assert inbox_dao.claim_next(c,target_agent='claude-code',pid=os.getpid(),now=now).status=='launched'
    first=b'{"type":"tool_use"}\n'
    second=b'{"message":{"content":[{"type":"tool_use"}]}}'
    transcript.write_bytes(first+second)
    try:
        tick=subprocess.run(['shux','watch','--once','--print-only','--to','claude-code','--project',project],
                            text=True,capture_output=True,timeout=15)
        print('watch_rc',tick.returncode,tick.stdout.splitlines()[-5:],tick.stderr.splitlines()[-5:])
        assert tick.returncode==0
        with db.managed_connection(project) as c:
            off=c.execute("SELECT byte_offset FROM dispatch_cursors WHERE dispatch_id='task'").fetchone()[0]
            n=c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        print('ordinary_tick','cursor',off,'events',n)
        assert (off,n)==(len(first),0)
        with transcript.open('ab') as f: f.write(b'\n')
        events.configure(project)
        _run_transcript_tail_if_enabled(project)
        assert events.flush(timeout=5)
        with db.managed_connection(project) as c:
            rows=[tuple(r) for r in c.execute('SELECT kind,task_id FROM events')]
            offset=c.execute("SELECT byte_offset FROM dispatch_cursors WHERE dispatch_id='task'").fetchone()[0]
        print('configured_emitter','cursor',offset,'events',rows)
        assert rows==[('transcript_progress','task')] and offset==len(first)+len(second)+1
    finally:
        transcript.unlink(missing_ok=True)
        tdir.rmdir()
PY
```

</details>

<details>
<summary>C11 · Two watcher lease and lock ownership controls</summary>

```bash
offline312 python - <<'PY'
import os, subprocess, sys, tempfile, time
from pathlib import Path
from superharness.engine import db, watcher_singleton

with tempfile.TemporaryDirectory(prefix='watcher-lease-') as tmp:
    root=Path(tmp)
    project=root/'project'
    alt=root/'other-surface'
    for p in [project,alt]:
        (p/'.superharness').mkdir(parents=True)
        (p/'.superharness'/'profile.yaml').write_text('auto_dispatch: false\nautonomy: manual\n')
    with db.managed_connection(str(project)) as c:
        watcher_singleton.acquire(c,pid=os.getpid(),now=db.now_iso())
    r=subprocess.run(['shux','watch','--once','--print-only','--to','codex-cli','--project',str(alt)],
                     env=os.environ | {'SUPERHARNESS_STATE_PROJECT':str(project)},
                     capture_output=True,text=True,timeout=10)
    with db.managed_connection(str(project)) as c:
        lease=c.execute("SELECT pid FROM watcher_instance WHERE key='singleton'").fetchone()[0]
        touched=c.execute("SELECT COUNT(*) FROM agent_heartbeats WHERE agent='watcher'").fetchone()[0]
    print('contending_public_tick','rc',r.returncode,'lease_owner',lease,'caller',os.getpid(),
          'wrote_heartbeat',touched,'conflict_logged','Watcher singleton held' in r.stderr)
    assert r.returncode==0 and lease==os.getpid() and touched==1 and 'Watcher singleton held' in r.stderr
    with db.managed_connection(str(project)) as c:
        watcher_singleton.release(c,os.getpid())
    lock_control=r"""
import os, sys, time
from pathlib import Path
from superharness.commands import inbox_watch as w
root=Path(sys.argv[1]); p=str(root/'project'); owner=sys.argv[2]
def wait_for(name):
    end=time.monotonic()+6
    while not (root/name).exists() and time.monotonic()<end:
        time.sleep(0.01)
    assert (root/name).exists(),name
def basic_tick(project_dir,**kwargs):
    if owner=='second':
        pd=Path(w._lock_pid_file(w._lock_dir_path(p)))
        (root/'second_locked').write_text(pd.read_text())
        wait_for('let_second_return')
w._run_scripts=basic_tick
rc=w.watch(p,once=True,print_only=True)
(root/(owner+'_watch_returned')).touch()
if owner=='first': wait_for('let_first_exit')
sys.exit(rc)
"""
    proc, other=None,None
    from superharness.commands.inbox_watch import _lock_dir_path
    lock=Path(_lock_dir_path(str(project)))
    def until(name):
        end=time.monotonic()+7
        while not (root/name).is_file() and time.monotonic()<end:
            time.sleep(0.01)
        assert (root/name).is_file(),name
    try:
        proc=subprocess.Popen([sys.executable,'-c',lock_control,tmp,'first'],
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        until('first_watch_returned')
        assert not lock.is_dir()
        other=subprocess.Popen([sys.executable,'-c',lock_control,tmp,'second'],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        until('second_locked')
        assert lock.is_dir() and int((root/'second_locked').read_text())==other.pid
        (root/'let_first_exit').touch()
        assert proc.wait(timeout=7)==0
        print('first_atexit_after_second_lock','first_pid',proc.pid,'second_pid',other.pid,
              'second_still_running',other.poll() is None,'second_lock_exists',lock.exists())
        assert other.poll() is None and not lock.exists()
    finally:
        (root/'let_first_exit').touch()
        (root/'let_second_return').touch()
        for child in (proc,other):
            if child is not None: child.wait(timeout=8)
PY
```

</details>

<details>
<summary>C12a · Native MCP start and client probe with FastMCP 0.4.1</summary>

```bash
offline312 python - <<'PY'
import asyncio, inspect, json, os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from importlib.metadata import version
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from superharness.engine import db

print('mcp_matrix',sys.version.split()[0],version('fastmcp'),version('mcp'))
with tempfile.TemporaryDirectory(prefix='mcp-transport-control-') as tmp:
    project=Path(tmp)/'project'
    (project/'.superharness').mkdir(parents=True)
    with db.managed_connection(str(project)) as c:
        c.execute("INSERT INTO tasks(id,title,status,created_at) VALUES('known','Synthetic MCP task','todo',?)",(db.now_iso(),))
    state=project/'.superharness'/'mcp.json'
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1',0))
        port=reserve.getsockname()[1]
    command=['shux','mcp','start','--port',str(port),'--project',str(project)]
    proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    ready=False
    try:
        end=time.monotonic()+6
        while proc.poll() is None and time.monotonic()<end:
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=0.2): pass
            except OSError: time.sleep(0.05)
            else:
                ready=True
                break
        print('ready',ready,'pid_file',state.exists(),'poll',proc.poll())
        if ready:
            async def exercise():
                async with streamable_http_client(f'http://127.0.0.1:{port}/mcp') as (r,w,_):
                    async with ClientSession(r,w) as client:
                        init=await client.initialize()
                        tools=await client.list_tools()
                        known=await client.call_tool('list_tasks',{})
                        print('initialize',init.serverInfo.name,'tools',len(tools.tools),
                              'list_tasks_error',known.isError,'list_tasks_content',[getattr(x,'text','?') for x in known.content])
                        healthy=not known.isError and any('known' in getattr(x,'text','') for x in known.content)
                        print('known_task_visible',healthy)
            asyncio.run(asyncio.wait_for(exercise(),timeout=7))
        else:
            from superharness.mcp.server import _make_app
            print('run_signature',str(inspect.signature(_make_app(str(project)).run)))
            try: _make_app(str(project)).run(transport='streamable-http',host='127.0.0.1',port=port)
            except Exception as exc: print('underlying_start_error',type(exc).__name__,str(exc))
    finally:
        if proc.poll() is None: proc.terminate()
        stdout,stderr=proc.communicate(timeout=7)
        print('process_rc',proc.returncode,'state_file_after',state.exists(),
              'server_stdout',stdout.splitlines()[-6:],'server_stderr',stderr.splitlines()[-8:])
PY
```

</details>

<details>
<summary>C12b · Native MCP data check with FastMCP 3.2.4</summary>

```bash
offline314 python - <<'PY'
import asyncio, inspect, json, os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from importlib.metadata import version
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from superharness.engine import db

print('mcp_matrix',sys.version.split()[0],version('fastmcp'),version('mcp'))
with tempfile.TemporaryDirectory(prefix='mcp-transport-control-') as tmp:
    project=Path(tmp)/'project'
    (project/'.superharness').mkdir(parents=True)
    with db.managed_connection(str(project)) as c:
        c.execute("INSERT INTO tasks(id,title,status,created_at) VALUES('known','Synthetic MCP task','todo',?)",(db.now_iso(),))
    state=project/'.superharness'/'mcp.json'
    env=os.environ|{'SUPERHARNESS_LOG_FILE':str(Path(tmp)/'server.log'),'SUPERHARNESS_AUDIT_LOG_FILE':str(Path(tmp)/'audit.log')}
    from superharness.utils.paths import resolve_active_state_db_path
    with db.managed_connection(str(project)) as c:
        print('local_before',resolve_active_state_db_path(str(project)),[tuple(r) for r in c.execute('SELECT id FROM tasks')])
    check=subprocess.run(['shux','contract','--project',str(project)],env=env,capture_output=True,text=True,timeout=10)
    print('independent_contract_cli',check.returncode,'known' in check.stdout,check.stdout.splitlines()[:3],check.stderr.strip())
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1',0))
        port=reserve.getsockname()[1]
    command=['shux','mcp','start','--port',str(port),'--project',str(project)]
    proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    ready=False
    try:
        end=time.monotonic()+6
        while proc.poll() is None and time.monotonic()<end:
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=0.2): pass
            except OSError: time.sleep(0.05)
            else:
                ready=True
                break
        print('ready',ready,'pid_file',state.exists(),'poll',proc.poll())
        if ready:
            async def exercise():
                async with streamable_http_client(f'http://127.0.0.1:{port}/mcp') as (r,w,_):
                    async with ClientSession(r,w) as client:
                        init=await client.initialize()
                        tools=await client.list_tools()
                        known=await client.call_tool('list_tasks',{})
                        print('initialize',init.serverInfo.name,'tools',len(tools.tools),
                              'list_tasks_error',known.isError,'list_tasks_content',[getattr(x,'text','?') for x in known.content])
                        print('list_tasks_structured',known.structuredContent)
                        task=await client.call_tool('get_task',{'task_id':'known'})
                        print('get_task',task.structuredContent,[getattr(x,'text','') for x in task.content])
                        healthy=not known.isError and 'known' in str(known.structuredContent)
                        print('known_task_visible',healthy)
                        return healthy
            healthy=asyncio.run(asyncio.wait_for(exercise(),timeout=7))
        else:
            from superharness.mcp.server import _make_app
            print('run_signature',str(inspect.signature(_make_app(str(project)).run)))
            try: _make_app(str(project)).run(transport='streamable-http',host='127.0.0.1',port=port)
            except Exception as exc: print('underlying_start_error',type(exc).__name__,str(exc))
    finally:
        if proc.poll() is None: proc.terminate()
        stdout,stderr=proc.communicate(timeout=7)
        print('process_rc',proc.returncode,'state_file_after',state.exists(),
              'server_stdout',stdout.splitlines()[-6:],'server_stderr',stderr.splitlines()[-8:])
        for log in ('server.log','audit.log'):
            path=Path(tmp)/log
            print(log,(path.read_text().splitlines()[-25:] if path.exists() else []))
PY
```

</details>

<details>
<summary>C12c · MCP request-thread affinity and corrected read control</summary>

```bash
offline314 python - <<'PY'
import asyncio, os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from superharness.engine import db

instrument=r"""
import sqlite3, sys, threading
from superharness.engine import db
from superharness.utils.paths import resolve_active_state_db_path
from superharness.mcp.tools import contract
original=db.get_connection
def get_connection(path):
    c=original(path) if sys.argv[1]=='trace' else sqlite3.connect(resolve_active_state_db_path(path),check_same_thread=False)
    c.row_factory=sqlite3.Row
    print('connection_thread',threading.get_ident(),'path',resolve_active_state_db_path(path),'count_before_http',
          c.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],file=sys.stderr,flush=True)
    return c
db.get_connection=get_connection
read=contract.get_contract
def get_contract(conn):
    print('request_thread',threading.get_ident(),file=sys.stderr,flush=True)
    try: print('raw_count_in_request',conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],file=sys.stderr,flush=True)
    except Exception as exc: print('raw_read_error',type(exc).__name__,str(exc),file=sys.stderr,flush=True)
    return read(conn)
contract.get_contract=get_contract
from superharness.mcp.server import run_server
run_server(sys.argv[2],port=int(sys.argv[3]))
"""
with tempfile.TemporaryDirectory(prefix='mcp-thread-control-') as tmp:
    p=Path(tmp)/'project'
    (p/'.superharness').mkdir(parents=True)
    with db.managed_connection(str(p)) as c:
        c.execute("INSERT INTO tasks(id,title,status,created_at) VALUES('known','Synthetic MCP task','todo',?)",(db.now_iso(),))
    for mode in ('trace','lifetime-control'):
        with socket.socket() as reserve:
            reserve.bind(('127.0.0.1',0))
            port=reserve.getsockname()[1]
        proc=subprocess.Popen([sys.executable,'-c',instrument,mode,str(p),str(port)],
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            end=time.monotonic()+7
            while proc.poll() is None and time.monotonic()<end:
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=0.2): pass
                except OSError: time.sleep(0.04)
                else: break
            assert proc.poll() is None
            async def exercise():
                async with streamable_http_client(f'http://127.0.0.1:{port}/mcp',terminate_on_close=False) as (r,w,_):
                    async with ClientSession(r,w) as s:
                        await s.initialize()
                        v=await s.call_tool('list_tasks',{})
                        return v.isError,v.structuredContent,v.content
            outcome=asyncio.run(asyncio.wait_for(exercise(),8))
            print(mode,'returned_task','known' in str(outcome),'output',str(outcome)[:190])
        finally:
            proc.terminate()
            stdout,stderr=proc.communicate(timeout=8)
            print([line for line in stderr.splitlines()
                   if any(word in line for word in ('connection_thread','request_thread','raw_read_error','raw_count'))])
        assert ('known' in str(outcome)) == (mode=='lifetime-control')
PY
```

</details>

<details>
<summary>C13 · Normal, duplicate and mismatched-round discussion submissions</summary>

```bash
offline312 python - <<'PY'
import concurrent.futures, re, subprocess, tempfile
from pathlib import Path
from superharness.engine import db
agents=['claude-code','codex-cli']
with tempfile.TemporaryDirectory(prefix='discussion-control-') as tmp:
    for label,round_num in [('in_order',1),('future',3),('duplicate',1)]:
        p=Path(tmp)/label
        (p/'.superharness'/'handoffs').mkdir(parents=True)
        project=str(p)
        def invoke(*args):
            return subprocess.run(['shux','discuss',*args,'--project',project],
                                  text=True,capture_output=True,timeout=12)
        begun=invoke('start','--topic','Synthetic local coordination question','--owners',','.join(agents),
                     '--max-rounds','2','--tier','mini','--effort','low','--force')
        assert begun.returncode==0,(begun.stdout,begun.stderr)
        disc_id=re.search(r'Discussion started: (\S+)',begun.stdout).group(1)
        def say(agent):
            return invoke('submit','--discussion',disc_id,'--agent',agent,'--round',str(round_num),
                          '--verdict','agree','--position','No implementation tasks required')
        submitters=agents if label!='duplicate' else [agents[0],agents[0]]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(say,submitters))
        with db.managed_connection(project) as c:
            outcome=tuple(c.execute('SELECT status,max_rounds,consensus FROM discussions').fetchone())
            rounds=[tuple(r) for r in c.execute("SELECT round_number,agent,verdict FROM discussion_rounds ORDER BY agent")]
            queue=[tuple(r) for r in c.execute("SELECT task_id,target_agent,status FROM inbox ORDER BY target_agent")]
        print(label,'replies',[(r.returncode,r.stdout.strip(),r.stderr.strip()) for r in results],
              'discussion',outcome,'rounds',rounds,'queue',queue)
        if label=='duplicate':
            assert sorted(r.returncode for r in results)==[0,1] and len(rounds)==1 and outcome[0]=='active'
        else:
            assert all(r.returncode==0 for r in results) and outcome[0]=='consensus'
            assert {rd[0] for rd in rounds}=={round_num}
            assert {row[2] for row in queue}==({'done'} if label=='in_order' else {'pending'})
PY
```

</details>

<details>
<summary>C14 · Independent worktree preservation and native cleanup</summary>

```bash
offline312 python - <<'PY'
import os, subprocess, sys, tempfile
from pathlib import Path
from superharness.engine import db, inbox_dao
from superharness.engine.task_commit import has_unsaved_work
from superharness.commands.inbox_dispatch import _git_worktree_add, _git_worktree_remove
agent='codex-cli'
with tempfile.TemporaryDirectory(prefix='worktree-preservation-') as tmp:
    root=Path(tmp)
    p=root/'project'
    (p/'.superharness'/'handoffs').mkdir(parents=True)
    (p/'.superharness'/'profile.yaml').write_text('autonomy: manual\nauto_retry: false\nrequire_tdd: false\n')
    def git(*args,work=None):
        return subprocess.run(['git','-C',str(work or p),*args],text=True,capture_output=True,check=True,timeout=10).stdout
    git('init','-q')
    (p/'tracked.txt').write_text('original\n')
    git('add','tracked.txt')
    git('-c','user.name=Offline Control','-c','user.email=control@example.invalid','commit','-qm','fixture')
    orig=git('rev-parse','HEAD').strip()
    control=Path(_git_worktree_add(str(p),'direct-control'))
    (control/'tracked.txt').write_text('synthetic uncommitted edit\n')
    print('pre_force_cleanup',has_unsaved_work(str(control)),git('status','--porcelain',work=control).strip())
    assert has_unsaved_work(str(control))
    assert _git_worktree_remove(str(p),str(control)) and not control.exists()
    (p/'user-dirty.txt').write_text('operator work')
    bindir=root/'bin'; bindir.mkdir()
    for name in ('claude','gemini','opencode','pi','hermes'):
        f=bindir/name; f.write_text('#!/bin/sh\nexit 127\n'); f.chmod(0o755)
    f=bindir/'codex'
    f.write_text("""#!/usr/bin/env python
from pathlib import Path
import os, subprocess, sys
if '--skip-git-repo-check' not in sys.argv: sys.exit(127)
Path('tracked.txt').write_text('synthetic agent edit')
Path(os.environ['LOCAL_WORKTREE']).write_text(str(Path.cwd()))
print('worktree_dirty_before_cleanup',flush=True)
subprocess.run(['git','status','--porcelain','--','tracked.txt'],check=True,timeout=5)
sys.exit(0)
""")
    f.chmod(0o755)
    env=os.environ|{'PATH':str(bindir)+os.pathsep+os.environ['PATH'],'LOCAL_WORKTREE':str(root/'worker-path'),
                    'SUPERHARNESS_FORCE_NO_SDK':'1','SUPERHARNESS_NO_PTY_WRAP':'1'}
    with db.managed_connection(str(p)) as c:
        c.execute("""INSERT INTO tasks(id,title,owner,status,project_path,created_at,workflow,acceptance_criteria,effort)
                     VALUES('task','Synthetic task',?,'plan_approved',?,?,'implementation','["sentinel"]','low')""",
                  (agent,str(p),db.now_iso()))
        inbox_dao.enqueue(c,id='attempt',task_id='task',target_agent=agent,project_path=str(p),now=db.now_iso())
    r=subprocess.run([sys.executable,'-m','superharness.commands.inbox_dispatch','--project',str(p),'--to',agent,
                      '--non-interactive','--launcher-timeout','15'],env=env,text=True,capture_output=True,timeout=20)
    with db.managed_connection(str(p)) as c:
        wt=c.execute("SELECT worktree_path FROM tasks").fetchone()[0]
        result=inbox_dao.get(c,'attempt').status
    print('agent_fixture_result',r.returncode,'inbox',result,'worktree_path_present_in_db',wt==((root/'worker-path').read_text()),
          'path_on_disk',Path(wt).exists(),'tracked_edit_present',(Path(wt)/'tracked.txt').exists(),'residual_files',[str(q.relative_to(wt)) for q in Path(wt).rglob('*')],'git_worktree_registered',wt in git('worktree','list','--porcelain'),'original_intact',(p/'tracked.txt').read_text().strip(),
          'parent_head_preserved',git('rev-parse','HEAD').strip()==orig)
    print([line for line in r.stdout.splitlines() if 'tracked.txt' in line or 'Worktree removed' in line],r.stderr.splitlines()[-3:])
    assert ' M tracked.txt' in r.stdout and result=='failed' and not (Path(wt)/'tracked.txt').exists() and wt not in git('worktree','list','--porcelain')
    assert (p/'tracked.txt').read_text()=='original\n' and git('rev-parse','HEAD').strip()==orig
PY
```

</details>

<details>
<summary>C15 · Concurrent SQLite cold starts with reopen integrity checks</summary>

```bash
offline312 python - <<'PY'
import collections, multiprocessing as mp, sqlite3, tempfile
from pathlib import Path
from superharness.engine import db
from superharness.utils.paths import resolve_active_state_db_path

with tempfile.TemporaryDirectory(prefix='db-bootstrap-') as tmp:
    for trial in range(3):
        p=Path(tmp)/str(trial)
        (p/'.superharness').mkdir(parents=True)
        n=8
        gate=mp.Barrier(n)
        out=mp.Queue()
        def init():
            c=None
            gate.wait(8)
            try:
                c=db.get_connection(str(p))
                db.init_db(c)
                out.put(('ok',c.execute('PRAGMA user_version').fetchone()[0]))
            except Exception as exc:
                out.put(('error',type(exc).__name__,str(exc)))
            finally:
                if c is not None: c.close()
        workers=[mp.Process(target=init) for _ in range(n)]
        for w in workers: w.start()
        results=[out.get(timeout=10) for _ in workers]
        for w in workers: w.join(5); assert w.exitcode==0
        print('bootstrap_trial',trial,dict(collections.Counter(results)))
        with db.managed_connection(str(p)) as c:
            migrated=c.execute('PRAGMA user_version').fetchone()[0]
            rows=c.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0]
            quick=c.execute('PRAGMA quick_check').fetchone()[0]
            print('post_contention',migrated,rows,quick)
            assert (migrated,rows,quick)==(39,39,'ok')
        settled=sqlite3.connect(resolve_active_state_db_path(str(p)))
        assert settled.execute('PRAGMA user_version').fetchone()[0]==39
        settled.close()
PY
```

</details>

<details>
<summary>C15b · Common migration-version barrier and warm-open control</summary>

```bash
offline312 python - <<'PY'
import multiprocessing as mp
import sqlite3
import tempfile
from pathlib import Path
from superharness.engine import db

with tempfile.TemporaryDirectory(prefix='serialized-init-control-') as tmp:
    p=Path(tmp)/'p'
    (p/'.superharness').mkdir(parents=True)
    project=str(p)
    # Establish the file and WAL mode before either schema initializer joins.
    conn=db.get_connection(project)
    assert conn.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
    conn.execute('CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
    conn.commit(); conn.close()
    def measure(force_shared_version):
        gate=mp.Barrier(2)
        output=mp.Queue()
        def worker():
            c=db.get_connection(project)
            original=db._run_migrations
            def sync(conn, version, project_dir=None):
                gate.wait(6)
                output.put(('read_version',version))
                return original(conn,version,project_dir)
            if force_shared_version:
                db._run_migrations=sync
            try:
                db.init_db(c)
                output.put(('ok',c.execute('PRAGMA user_version').fetchone()[0]))
            except sqlite3.Error as exc:
                output.put(('failure',type(exc).__name__,str(exc)))
            finally:
                c.close()
        workers=[mp.Process(target=worker), mp.Process(target=worker)]
        for proc in workers: proc.start()
        rows=[output.get(timeout=8) for _ in range(4 if force_shared_version else 2)]
        for proc in workers: proc.join(4); assert proc.exitcode==0
        return rows
    forced=measure(True)
    warm=measure(False)
    print('two_migration_readers',forced,'warm_open',warm)
    assert sorted(row[1] for row in forced if row[0]=='read_version')==[0,0]
    assert sum(row[0]=='failure' and 'schema_migrations.version' in row[2] for row in forced)==1
    assert warm==[('ok',39),('ok',39)]
PY
```

</details>

<details>
<summary>C16 · Generated Linux service and shared-state mapping</summary>

```bash
offline312 python - <<'PY'
import os, shlex, subprocess, tempfile
from pathlib import Path
from superharness.engine import db, state_reader
from superharness.utils.paths import resolve_active_state_db_path

with tempfile.TemporaryDirectory(prefix='systemd-generation-') as tmp:
    root=Path(tmp)
    source=root/'source'; source.mkdir()
    worker=root/'worker path'
    bindir=root/'bin'; bindir.mkdir()
    f=bindir/'systemctl'
    f.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$STUB_SYSTEMCTL_LOG"\nexit 0\n'); f.chmod(0o755)
    log=root/'systemctl-calls'
    with db.managed_connection(str(source)) as conn:
        conn.execute("INSERT INTO tasks(id,title,status,created_at) VALUES('source-only','Synthetic','todo',?)",(db.now_iso(),))
    (source/'.superharness'/'handoffs').mkdir(parents=True)
    (source/'.superharness'/'profile.yaml').write_text('auto_dispatch: false\n')
    env=os.environ | {'PATH':str(bindir)+os.pathsep+os.environ['PATH'],'STUB_SYSTEMCTL_LOG':str(log)}
    args=['shux','watcher-worker','--project',str(source),'--worker',str(worker),
          '--to','codex-cli','--interval','47','--recover-timeout-minutes','8',
          '--recover-action','stale','--launcher-timeout','77']
    initial=subprocess.run(args,env=env,capture_output=True,text=True,timeout=10,stdin=subprocess.DEVNULL)
    print('without_linux_confirm',initial.returncode,initial.stderr.splitlines()[-4:],'systemctl_called',log.exists())
    assert initial.returncode==1 and not log.exists()
    setup=subprocess.run(args,env=env|{'CONFIRM_NON_INTERACTIVE':'yes'},capture_output=True,text=True,timeout=10,stdin=subprocess.DEVNULL)
    assert setup.returncode==0,(setup.stdout,setup.stderr)
    directory=Path.home()/'.config/systemd/user'
    unit=directory/'superharness-inbox-worker-path.service'
    timer=unit.with_suffix('.timer')
    try:
        service=unit.read_text(); timer_text=timer.read_text()
        print('unit',service.replace('\n',' | '),'timer',timer_text.replace('\n',' | '))
        cfg=(source/'.superharness'/'watcher.yaml').read_text()
        print('watcher_yaml',cfg.replace('\n',' | '),'systemctl_calls',log.read_text().splitlines())
        assert '--to both' in service and 'OnUnitActiveSec=15' in timer_text
        assert 'target: codex-cli' in cfg and 'interval_seconds: 47' in cfg
        assert 'SUPERHARNESS_STATE_PROJECT' not in service
        assert shlex.split(next(s[10:] for s in service.splitlines() if s.startswith('ExecStart=')))[3]!=str(worker)
        before=Path(resolve_active_state_db_path(str(worker)))
        assert not before.exists()
        tick=subprocess.run(['shux','watch','--once','--print-only','--project',str(worker),'--to','codex-cli'],
                            env=env,capture_output=True,text=True,timeout=10)
        original=Path(resolve_active_state_db_path(str(source)))
        print('manual_worker_tick_without_env',tick.returncode,'source_db',original.name,'worker_db',str(before.relative_to(worker)),
              'work_db_exists',before.exists(),'same_db',original.resolve()==before.resolve(),
              'source_visible_from_worker',state_reader.get_task(str(worker),'source-only') is not None)
        assert tick.returncode==0 and before.exists() and original.resolve()!=before.resolve()
        assert not state_reader.get_task(str(worker),'source-only')
        os.environ['SUPERHARNESS_STATE_PROJECT']=str(source)
        assert state_reader.get_task(str(worker),'source-only')
        print('state_project_override_positive_control','source-only')
    finally:
        unit.unlink(missing_ok=True)
        timer.unlink(missing_ok=True)
PY
```

</details>

<details>
<summary>C17 · SDK budget and fallback boundary simulation</summary>

```bash
offline312 python - <<'PY'
import os, subprocess, sys, tempfile, types
from pathlib import Path
from superharness.engine import db
from superharness.commands import delegate

with tempfile.TemporaryDirectory(prefix='sdk-budget-control-') as tmp:
    root=Path(tmp)
    p=root/'project'
    h=p/'.superharness'
    (h/'handoffs').mkdir(parents=True)
    (h/'profile.yaml').write_text('autonomy: manual\n')
    with db.managed_connection(str(p)) as c:
        c.execute("""INSERT INTO tasks(id,title,owner,status,project_path,created_at,workflow,acceptance_criteria,effort,extras_json)
                     VALUES('sdk','Synthetic SDK task','claude-code','plan_approved',?,?,'implementation','["sentinel"]','low',
                     '{"budget_usd":0.01}')""",(str(p),db.now_iso()))
    fake=types.ModuleType('claude_agent_sdk')
    class ClaudeAgentOptions:
        pass
    class ResultMessage:
        result='SDK completed synthetic work'
        usage={'input_tokens':100000,'output_tokens':10000}
    executions=[]
    async def query(prompt,options):
        executions.append(('sdk', options.cwd, options.permission_mode, hasattr(options,'max_budget_usd')))
        (p/'sdk-work').write_text('a real local side effect from the synthetic SDK')
        yield ResultMessage()
    fake.ClaudeAgentOptions=ClaudeAgentOptions
    fake.ResultMessage=ResultMessage
    fake.query=query
    sys.modules['claude_agent_sdk']=fake
    def simulated_cli(target,prompt,project_dir,*args,**kwargs):
        executions.append(('cli',target,project_dir,(p/'sdk-work').exists()))
    delegate._launch_agent=simulated_cli
    rc=delegate.delegate(
        str(p),'claude-code','sdk',print_only=False,non_interactive=False,codex_bypass=False,
        via_sdk=True,no_orchestrate=True,skip_preflight=True,
        model_override='claude-sonnet-4-6',effort_override='low'
    )
    print('sdk_limit',rc,executions)
    assert rc==0 and executions==[
        ('sdk',str(p),'bypassPermissions',False),('cli','claude-code',str(p),True)
    ]
PY
```

</details>

<details>
<summary>C18 · Retry batch rollback, busy claim, and stale finalizer</summary>

```bash
offline312 python - <<'PY'
import os, subprocess, sys, tempfile, time
from pathlib import Path
from superharness.commands.inbox_watch import _auto_retry_failed
from superharness.commands.inbox_dispatch import _sqlite_mirror_dispatch
from superharness.engine import db, inbox_dao

agent='codex-cli'
with tempfile.TemporaryDirectory(prefix='retry-transaction-control-') as tmp:
    p=Path(tmp)/'project'
    h=p/'.superharness'; h.mkdir(parents=True)
    (h/'profile.yaml').write_text('auto_retry: true\n')
    project=str(p)
    with db.managed_connection(project) as c:
        for name in ('good','poison'):
            c.execute("INSERT INTO tasks(id,title,status,owner,project_path,created_at) VALUES(?,?,'plan_approved',?,?,?)",
                      (name,name,agent,project,db.now_iso()))
            inbox_dao.enqueue(c,id=name+'-old',task_id=name,target_agent=agent,
                              priority=3 if name=='good' else 1,now=db.now_iso())
            inbox_dao.mark_failed(c,name+'-old',reason='synthetic retryable',now=db.now_iso())
        inbox_dao.enqueue(c,id='poison-active',task_id='poison',target_agent=agent,now=db.now_iso())
    def snapshot():
        with db.managed_connection(project) as c:
            return ([(row.id,row.status,row.retry_count) for row in inbox_dao.get_all(c)],
                    c.execute("SELECT COUNT(*) FROM ledger WHERE action='auto_retry'").fetchone()[0])
    _auto_retry_failed(project)
    print('poison_batch',snapshot())
    assert ('good-old','failed',0) in snapshot()[0] and snapshot()[1]==0
    with db.managed_connection(project) as c:
        inbox_dao.remove(c,'poison-active')
    _auto_retry_failed(project)
    print('positive_control',snapshot())
    assert [v[1:] for v in snapshot()[0]]==[('pending',1),('pending',1)] and snapshot()[1]==2
    hold=db.get_connection(project)
    hold.execute('BEGIN IMMEDIATE')
    try:
        start=time.monotonic()
        result=subprocess.run([sys.executable,'-m','superharness.commands.inbox_dispatch','--project',project,
                               '--to',agent,'--non-interactive'],capture_output=True,text=True,timeout=10)
        print('locked_claim','rc',result.returncode,'seconds',round(time.monotonic()-start,2),
              'quiet_stdout',result.stdout=='','busy_logged','database is locked' in result.stderr)
        assert result.returncode==0 and result.stdout=='' and 'database is locked' in result.stderr
    finally:
        hold.rollback();hold.close()
    with db.managed_connection(project) as c:
        first=inbox_dao.claim_next(c,target_agent=agent,pid=91,now=db.now_iso())
        assert first.id=='good-old'
        inbox_dao.set_retry(c,first.id,2,'synthetic obsolete attempt',db.now_iso())
        replacement=inbox_dao.claim_next(c,target_agent=agent,pid=92,now=db.now_iso())
        print('post_lock_replacement',replacement.id,replacement.status,replacement.pid)
        assert replacement.id==first.id and replacement.pid==92
    _sqlite_mirror_dispatch(project,first.id,first.task_id,agent,'failed',db.now_iso(),reason='prior attempt finalizing')
    with db.managed_connection(project) as c:
        clobbered=inbox_dao.get(c,replacement.id)
        print('late_finalizer',clobbered.status,clobbered.pid,clobbered.failed_reason)
        assert (clobbered.status,clobbered.pid,clobbered.failed_reason)==('failed',92,'prior attempt finalizing')
PY
```

</details>

<details>
<summary>C19 · Isolated GNU script exit propagation and discussion argv</summary>

```bash
offline312 python - <<'PY'
import os, shlex, subprocess, tempfile
from pathlib import Path
from superharness.commands.inbox_dispatch import DispatchContext, _prepare_launch_context
from superharness.engine import db

print('script_return_contract', [(opts, subprocess.run(
       ['script','-q',*opts,'-c','sh -c "exit 2"','/dev/null'],
       capture_output=True,text=True,timeout=5).returncode) for opts in ([],['-e'])])
with tempfile.TemporaryDirectory(prefix='discussion-argv-') as tmp:
    p=Path(tmp)/'project'; h=p/'.superharness'; h.mkdir(parents=True)
    now=db.now_iso()
    task='discuss-alpha/round-1'
    with db.managed_connection(str(p)) as c:
        c.execute("""INSERT INTO tasks(id,title,status,owner,project_path,created_at,workflow,effort,model_tier)
        VALUES(?,'Synthetic round','todo','codex-cli',?,?,'discussion','low','max')""",(task,str(p),now))
    os.environ['SUPERHARNESS_CODEX_CLI_MODEL']='synthetic-discussion-override'
    for no_pty in (False,True):
        os.environ['SUPERHARNESS_NO_PTY_WRAP']='1' if no_pty else '0'
        c=DispatchContext(project_dir=str(p),inbox_file=str(h/'inbox.yaml'),contract_file=str(h/'contract.yaml'),
                          target_filter='codex-cli',print_only=False,non_interactive=True,codex_bypass=False,
                          launcher_timeout=0,script_dir='',sqlite_primary=True)
        c.item_task=task
        c.item_to='codex-cli'
        c.exec_project=str(p)
        c.is_discussion=True
        _prepare_launch_context(c)
        actual=c.wrapped_args if no_pty else shlex.split(c.wrapped_args[c.wrapped_args.index('-c')+1])
        print('discussion_model', 'plain' if no_pty else 'pty', 'display_tail',c.launch_args[-2:],
              'argv_model', '--model' in actual,'timeout',c.effective_timeout)
        assert c.launch_args[-2:]==['--model','synthetic-discussion-override'] and '--model' not in actual
PY
```

</details>

<details>
<summary>C20 · Live shared worker refresh and alternate copy implementation</summary>

```bash
offline312 python - <<'PY'
import os, subprocess, sys, tempfile, time
from pathlib import Path
from superharness.engine import db, inbox_dao
from superharness.engine.platform_runtime import sync_worker_copy

with tempfile.TemporaryDirectory(prefix='shared-worker-control-') as tmp:
    root=Path(tmp)
    source=root/'source'
    worker=root/'worker'
    h=source/'.superharness'
    (h/'handoffs').mkdir(parents=True)
    (h/'profile.yaml').write_text('autonomy: manual\nrequire_tdd: false\n')
    def git(*args):
        subprocess.run(['git','-C',str(source),*args],check=True,capture_output=True,timeout=10)
    git('init','-q')
    (source/'tracked.txt').write_text('source file')
    git('add','tracked.txt')
    git('-c','user.name=Offline Control','-c','user.email=control@example.invalid','commit','-qm','fixture')
    assert sync_worker_copy(str(source),str(worker))
    (worker/'.superharness').symlink_to(h,target_is_directory=True)
    with db.managed_connection(str(source)) as c:
        for name,prio in [('one',3),('two',2)]:
            c.execute("""INSERT INTO tasks(id,title,owner,status,project_path,created_at,workflow,acceptance_criteria,effort)
                         VALUES(?,?,'codex-cli','plan_approved',?,?,'implementation','["fixture"]','low')""",
                      (name,name,str(source),db.now_iso()))
            inbox_dao.enqueue(c,id=name,task_id=name,target_agent='codex-cli',project_path=str(source),
                              priority=prio,now=db.now_iso())
    bindir=root/'bin'; bindir.mkdir()
    for name in ('claude','gemini','opencode','pi','hermes'):
        f=bindir/name; f.write_text('#!/bin/sh\nexit 127\n'); f.chmod(0o755)
    f=bindir/'codex'
    f.write_text("""#!/usr/bin/env python
import os,sys,time
from pathlib import Path
if '--skip-git-repo-check' not in sys.argv: sys.exit(127)
root=Path(os.environ['LOCAL_SYNC'])
path=Path('tracked.txt')
if os.environ['LOCAL_SLOT']=='one':
    path.write_text('first attempt uncommitted')
    (root/'first-ready').write_text(str(Path.cwd()))
    end=time.monotonic()+12
    while not (root/'release').is_file() and time.monotonic()<end: time.sleep(0.03)
    (root/'first-after').write_text(path.read_text())
else:
    (root/'second-observed').write_text(path.read_text())
""")
    f.chmod(0o755)
    env=os.environ|{'PATH':str(bindir)+os.pathsep+os.environ['PATH'],'LOCAL_SYNC':tmp,
                    'SUPERHARNESS_STATE_PROJECT':str(source),'SUPERHARNESS_FORCE_NO_SDK':'1','SUPERHARNESS_NO_PTY_WRAP':'1'}
    args=[sys.executable,'-m','superharness.commands.inbox_dispatch','--non-interactive',
          '--project',str(worker),'--to','codex-cli','--launcher-timeout','15']
    first=subprocess.Popen(args,env=env|{'LOCAL_SLOT':'one'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        end=time.monotonic()+7
        while not (root/'first-ready').is_file() and time.monotonic()<end: time.sleep(0.03)
        assert (root/'first-ready').read_text()==str(worker)
        assert (worker/'tracked.txt').read_text()=='first attempt uncommitted'
        second=subprocess.run(args,env=env|{'LOCAL_SLOT':'two'},capture_output=True,text=True,timeout=12)
        print('second_active_refresh','first_still_running',first.poll() is None,'worker_edit_after', (worker/'tracked.txt').read_text(),
              'second_observed',(root/'second-observed').read_text())
        assert first.poll() is None and (root/'second-observed').read_text()=='source file'
    finally:
        (root/'release').touch()
        first.communicate(timeout=10)
    assert (root/'first-after').read_text()=='source file'
    (worker/'tracked.txt').write_text('second synthetic edit')
    assert sync_worker_copy(str(source),str(worker),rsync_disabled=True)
    print('alternate_copy_shows_same_invariant',(worker/'tracked.txt').read_text())
    assert (worker/'tracked.txt').read_text()=='source file'
PY
```

</details>

<details>
<summary>C21 · Approval-wait reason and pause expiration</summary>

```bash
offline312 python - <<'PY'
import os, subprocess, sys, tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from superharness.engine.lifecycle_rules import reconcile_lifecycle
from superharness.engine import db, inbox_dao
agent='codex-cli'
with tempfile.TemporaryDirectory(prefix='completion-control-') as tmp:
    root=Path(tmp)
    bindir=root/'bin'; bindir.mkdir()
    for name in ('claude','gemini','opencode','pi','hermes'):
        f=bindir/name; f.write_text('#!/bin/sh\nexit 127\n'); f.chmod(0o755)
    codex=bindir/'codex'
    codex.write_text("""#!/usr/bin/env python
import os, subprocess, sys
if '--skip-git-repo-check' not in sys.argv:
    sys.exit(127)
kind=os.environ['LOCAL_FINISH_CASE']
def shux(*args):
    subprocess.run(['shux',*args],check=True,timeout=5)
def status(value):
    shux('task','status','--id','task','--status',value,'--actor','codex-cli','--summary','synthetic local status')
if kind=='plan':
    shux('handoff','write','--task','task','--phase','plan','--from','codex-cli','--to','owner',
         '--plan','Criterion: put one sentinel in the synthetic output','--tdd-red','test_sentinel',
         '--tdd-green','provide sentinel','--tdd-refactor','none')
    status('plan_proposed')
elif kind=='approval':
    status('in_progress')
    status('pending_user_approval')
else:
    status('in_progress')
    shux('handoff','write','--task','task','--phase','report','--from','codex-cli','--to','owner',
         '--outcome','Synthetic report body','--tests-passed')
    status('report_ready')
    if kind=='done':
        shux('verify','--id','task','--method','synthetic local validation','--result','pass')
        shux('close','--id','task','--actor','codex-cli','--summary','synthetic done')
print('fixture explicitly exiting 0')
""")
    codex.chmod(0o755)
    for case,initial in [('approval','plan_approved')]:
        p=root/case
        h=p/'.superharness'
        (h/'handoffs').mkdir(parents=True)
        (h/'profile.yaml').write_text('require_tdd: false\nautonomy: manual\nauto_retry: true\n')
        project=str(p)
        with db.managed_connection(project) as c:
            c.execute("INSERT INTO tasks(id,title,owner,status,project_path,created_at,workflow,acceptance_criteria,effort) VALUES('task','Synth task',?,?,?,?, 'implementation','[\"sentinel\"]','low')",(agent,initial,project,db.now_iso()))
            inbox_dao.enqueue(c,id='first',task_id='task',target_agent=agent,project_path=project,
                              plan_only=case=='plan',now=db.now_iso())
        env=os.environ | {'PATH':str(bindir)+os.pathsep+os.environ['PATH'],'LOCAL_FINISH_CASE':case,
                           'SUPERHARNESS_NO_PTY_WRAP':'1','SUPERHARNESS_FORCE_NO_SDK':'1'}
        result=subprocess.run([sys.executable,'-m','superharness.commands.inbox_dispatch','--project',project,
                               '--to',agent,'--non-interactive','--launcher-timeout','20'],env=env,
                              capture_output=True,text=True,timeout=27)
        with db.managed_connection(project) as c:
            snapshot=tuple(c.execute("SELECT status,verified FROM tasks WHERE id='task'").fetchone())
            handoffs=[tuple(r) for r in c.execute('SELECT phase,status FROM handoffs')]
            item=inbox_dao.get(c,'first')
        print(case,'task',snapshot,'handoffs',handoffs,'inbox',item.status,item.retry_count,repr(item.failed_reason),
              'dispatch_rc',result.returncode,'successful_child','fixture explicitly exiting 0' in result.stdout)
        print('tail',result.stdout.splitlines()[-5:],result.stderr.splitlines()[-5:])
        assert 'fixture explicitly exiting 0' in result.stdout
        assert (snapshot[0],item.status,item.reason,result.returncode)==('pending_user_approval','paused',None,0)
        aged=(datetime.now(timezone.utc)-timedelta(minutes=31)).strftime('%Y-%m-%dT%H:%M:%SZ')
        with db.managed_connection(project) as c:
            inbox_dao.set_field(c,'first','paused_at',aged)
        aged_outcome=reconcile_lifecycle(project)
        with db.managed_connection(project) as c:
            expired=inbox_dao.get(c,'first')
            task=c.execute("SELECT status FROM tasks WHERE id='task'").fetchone()[0]
            print('aged_real_pause',aged_outcome,expired.status,expired.reason,expired.failed_reason,task)
            assert aged_outcome==1 and expired.status=='failed' and task=='pending_user_approval'
            inbox_dao.set_fields(c,'first',status='paused',paused_at=aged,reason='awaiting_user_approval')
        assert reconcile_lifecycle(project)==0
        with db.managed_connection(project) as c:
            positive=inbox_dao.get(c,'first')
            print('aged_with_persisted_reason',positive.status,positive.reason)
            assert positive.status=='paused'
PY
```

</details>

## 10. Final integrity and completion receipt

- Fresh review interval **2026-11-19 16:36:16–17:06:51 UTC**, **30.58 minutes**. Checkout verification and environment preparation continued into the first full run. Broad test runs overlapped with source reading, focused experiments and failure diagnosis. Follow-up controls, report drafting, and citation and reproduction checks continued through final verification. The prior attempt contributes zero minutes.
- Final source verification returned HEAD `e77627733cf38b0eed9b05679c0238d1435f2205` and empty `git status --porcelain=v1 --untracked-files=all`. Staged and unstaged `git diff --exit-code` each returned 0. The original repository was inspected read-only.
- The report has ten numbered sections and 21 numbered controls. Markdown structure, local citation paths and line bounds, Bash syntax, and embedded Python syntax were checked. Both dependency setups and controls C1, C4, C10 and C19 were independently rerun from the appendix. The temporary clone, test environments and fixtures were removed. This Markdown report is the sole retained output from the fresh review.
