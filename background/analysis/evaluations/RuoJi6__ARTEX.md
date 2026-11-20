# ARTEX core architecture and reliability evaluation

## 1. Snapshot, scope, and elapsed-time evidence

| Item | Review boundary |
| --- | --- |
| Checkout | `repos/RuoJi6__ARTEX`, `main`, shallow checkout, `6997a4661921395072290becc50380db8dacb04e`, release-note commit for v0.3.30 |
| Start | `2026-11-19T05:58:45Z` UTC. `git rev-parse HEAD` matched the pin and porcelain status, including untracked and ignored items, was empty. |
| Finish | `2026-11-19T06:29:24Z` UTC, `30.65` elapsed minutes. Final exact revision and clean-tree check in §10. |
| Scope | Backend control plane, task and intent lifecycle, execution and process ownership, storage and recovery, provider and tool boundaries, events and extension contracts. All behavior tests used local fixtures. |
| Runtime | Linux amd64, cached Go 1.26.10 and Norma v0.4.3, fresh PostgreSQL 16.16, in-process fakes and private loopback fixtures. All dependency resolution was offline. |

ARTEX is a single-process, database-backed coordinator for model-driven tasks. Its strongest boundary is the task-local, atomically claimed intent. Its weakest boundary is the transition from a durable row to the in-memory owner that carries out the next step. The controls reproduced completion with an interrupted bootstrap, execution before schedule enforcement on restore, two owners after overlapping startup, and several gaps in cancellation and event delivery. These concern orchestration and progress state. The review used inert task text, scripted models, synthetic in-process authentication fixtures, and a private password-free database. It covered neither model quality nor operation against targets.

Fresh activity began with the HEAD and protocol checks. No earlier run contributed evidence or time. The workspace protocol lists nine combined topics. This report uses the established ten-section form, splitting strengths and weaknesses while retaining each listed topic. [Evaluation protocol](./README.md:1)

| UTC interval | Active work and time anchors |
| --- | --- |
| 05:58:45–06:02:01 | Verified revision and clean state, mapped package/test entry points, ran zero-DB baseline, located the exact toolchain and cached database image, started a socket-only cluster. Baseline Go JSON events at 06:00:00–06:00:05. |
| 06:02:01–06:06:12 | Traced admission, timeout, bootstrap, task deletion and activity replay while the full SQL-enabled suite ran. Split failures by cause, made fresh databases, and implemented the first engine controls. Suite JSON at 06:02:03–06:03:07 and first controls at 06:06:00–06:06:07. |
| 06:06:12–06:10:40 | Fixed two fixture assumptions about task status, repeated state and cursor controls, traced scheduler and provider transitions, and tested overlapping startup, timeout trigger order, subprocess ownership, and stream cancellation. Investigated race-test fixture failures and graceful cancellation. |
| 06:10:40–06:14:20 | Ran test-only overlay controls for the original suite negatives, the hardened broad and race suites, and binary and artifact smoke checks. Read the SDK, transcript, archive and extension paths. CLI health and SIGTERM control at 06:13:23. |
| 06:14:20–06:21:30 | Rechecked the original race reports and test fixture ownership, repeated 34 new integration assertions under the race detector across separate runs, checked graph scaling and crash-time accounting, and verified the binary VCS stamp. |
| 06:21:30–2026-11-19T06:29:24Z | Extracted and replayed the report appendix on fresh databases, ran a calibrated whole-suite comparison, verified active shutdown and no-result budget behavior, resolved the remaining fixture mismatches, audited the source links, and checked the clean checkout again. |

## 2. Core architecture and end-to-end control/data flow

### Host and ownership

`cmd/artex` loads config, opens `Manager`, constructs `Server`, and installs a signal-derived context carrying a named shutdown cause. The bootstrap self-update decision runs before DB or HTTP setup. `Manager` owns the PG pool, in-memory task handles, shared asset store, and optional traffic capture. `Server` wires agent resolution, HTTP, schedulers and side services. `Engine` owns per-task routine lifetimes and per-execution cancellation. Norma owns the prompt/tool loop, tool registry, conversation history, budgets, and session-managed subprocesses. ARTEX pins the exact SDK version and also supplies its own provider router, audit and application control. [CLI lifecycle](repos/RuoJi6__ARTEX/cmd/artex/main.go:53) · [Manager startup](repos/RuoJi6__ARTEX/server/manager.go:569) · [Server composition](repos/RuoJi6__ARTEX/server/server.go:173) · [Engine ownership](repos/RuoJi6__ARTEX/server/engine.go:93) · [Module pin](repos/RuoJi6__ARTEX/go.mod:3)

### From a request to admitted work

1. `createTaskFromRequest` normalizes task options and checks source task, profile, worker, category and schedule references. `CreateTaskWithOptions` commits exploration, origin fact, task, sources, company scope, ordered profile chain and optional schedule in one transaction. The HTTP path and host orchestration path reuse launch/admission. A future scheduled task can be born paused with bootstrap mode. [HTTP creation](repos/RuoJi6__ARTEX/server/server.go:1778) · [Task transaction](repos/RuoJi6__ARTEX/db/tasks.go:213) · [Scheduled creation](repos/RuoJi6__ARTEX/db/tasks.go:313) · [Shared launch](repos/RuoJi6__ARTEX/server/goals.go:21)
2. `admitTaskWhenScheduledWithGenerationChecked` serializes local control with `concMu`, re-resolves the handle after locking, checks delete, pause, schedule and reconnect generation, and decides whether to start or queue. Its SQL update compares expected status and commits queue mode, position, pause state and timer changes together. Reconciliation orders ready entries by persisted `queued_at`, falls back to creation time and ID for legacy rows, and skips unavailable providers while limiting admission. Existing running work keeps its slot when the limit decreases. [Admission](repos/RuoJi6__ARTEX/server/goals.go:134) · [DB transition and mirror](repos/RuoJi6__ARTEX/server/manager.go:1493) · [FIFO reconciliation](repos/RuoJi6__ARTEX/server/goals.go:315)
3. Bootstrap asynchronously materializes goal nodes, uses the input goal as a fallback if the model yields no goal, then starts `Engine.Run`. Each task has one planner loop, one loop per configured worker slot and an optional deadline coordinator. Explicit per-task worker count overrides global pool expansion. Global pools can pin a profile to a slot. A distinct pinned worker stays exclusive to its profile. `Run` is idempotent for a task ID within an Engine, using a map and a task-owned wait group. [Bootstrap](repos/RuoJi6__ARTEX/server/goals.go:284) · [Goal materialization](repos/RuoJi6__ARTEX/server/goals.go:433) · [Routine startup](repos/RuoJi6__ARTEX/server/engine.go:798) · [Worker slot rules](repos/RuoJi6__ARTEX/server/engine.go:838) · [Pinned profile](repos/RuoJi6__ARTEX/server/task_llm.go:112)

### Planner, frontier and feedback

The per-task exploration graph is a blackboard for goals, hints, intents, facts and findings. Typed relations and exploration-to-asset anchors preserve lineage. The asset graph is a shared catalog, with task-specific scope and visibility. Workers and planners can read bounded summaries and selected historical traces. Direct source tasks add a read-only view of terminal work and its provenance. Source work stays outside the child task's frontier. [Dual graph rationale](repos/RuoJi6__ARTEX/README.md:566) · [Origin node](repos/RuoJi6__ARTEX/db/tasks.go:234) · [Blackboard projection](repos/RuoJi6__ARTEX/agent/tools.go:358) · [Source store filtering](repos/RuoJi6__ARTEX/db/exploration_sources.go:20) · [Source context caps](repos/RuoJi6__ARTEX/agent/tools.go:564)

The planner's buffered wake signal coalesces bursts, while its trigger slice carries concrete updates. A heartbeat rearms after each wake or round and provides a periodic check. Once ready, the planner snapshots graph summaries and injects the trigger details into a fresh SDK session. Per-exploration `TodoStore` survives across live planning rounds, and the graph is the durable record. The shape is a model-driven blackboard scheduler. Priority and FIFO tie-breaks are SQL properties, while prerequisites and decisions about subsequent work are mostly model/tool contracts. [Wake and trigger ownership](repos/RuoJi6__ARTEX/server/manager.go:2373) · [Planner loop](repos/RuoJi6__ARTEX/server/engine.go:880) · [Planner TodoStore](repos/RuoJi6__ARTEX/agent/planner.go:110) · [Planner request](repos/RuoJi6__ARTEX/agent/planner.go:357) · [Frontier ordering](repos/RuoJi6__ARTEX/db/exploration.go:1136)

Each worker polls for the first 20 candidates and attempts a conditional `open`→`running` update for each until it wins. It builds an intent-specific run inside a task directory, consumes its own transcript and blackboard context, and writes results through typed tool interfaces. Settlement uses the intent state and the named cancellation cause to determine whether work becomes done, blocked, exhausted, stopped, paused, or open again. Worker completion and intermediate durable updates can wake planning. When there are no open goals, the scheduler bypasses model planning and uses frontier exhaustion to decide task completion. [Worker loop](repos/RuoJi6__ARTEX/server/engine.go:1007) · [Claim](repos/RuoJi6__ARTEX/server/engine.go:1377) · [SQL CAS](repos/RuoJi6__ARTEX/db/exploration.go:1172) · [Worker setup](repos/RuoJi6__ARTEX/agent/worker.go:354) · [Settlement](repos/RuoJi6__ARTEX/server/engine.go:1167) · [Goalless path](repos/RuoJi6__ARTEX/server/engine.go:921)

A human turn for a task is owned separately from its planner/worker loops. It can add hints, goals or scoped follow-up intents. An intent pause reserves an in-memory work control slot, sends a named cause, and waits until the worker commits its final state. A message to a paused worker uses a guarded `paused`→`running` transition and starts a detached worker with a server-root context. This is an intentional exception to the ordinary worker pool width. The request marker is deduplicated against the persisted SDK transcript when that text has reached it. [Main Agent tool callbacks](repos/RuoJi6__ARTEX/agent/mainagent.go:114) · [Intent controls](repos/RuoJi6__ARTEX/server/task_control.go:210) · [Per-work control](repos/RuoJi6__ARTEX/server/engine.go:443) · [Detached entry point](repos/RuoJi6__ARTEX/server/intent_intervention.go:78) · [Detached ownership](repos/RuoJi6__ARTEX/server/engine.go:1291) · [Request marker](repos/RuoJi6__ARTEX/agent/worker.go:494)

### Deadlines, calendar and secondary work

Wall time starts on the first real planner/worker run and survives pauses and reloads as an absolute deadline. Active-run time accumulates by persisted segment for the optional one-shot minimum-result check. The failed-check marker and reason survive restart. A coordinator installs a settling gate, waits up to 90 seconds for registered activity, applies hard cancellation if necessary, then asks a final planner and attempts a guarded terminal commit. An explicit timeout revival clears the old clock and process-local coordinator markers. [Clock fields and CAS](repos/RuoJi6__ARTEX/db/tasks.go:548) · [First-run stamp](repos/RuoJi6__ARTEX/db/tasks.go:707) · [No-result coordinator](repos/RuoJi6__ARTEX/server/engine_timeout.go:164) · [Settlement](repos/RuoJi6__ARTEX/server/engine_timeout.go:251) · [Timeout revival](repos/RuoJi6__ARTEX/server/goals.go:247)

A five-second server scheduler reconciles admission, evaluates calendar windows and scans configured custom-agent events. Calendar evaluation uses one-shot/weekly windows and end-exclusive bounds, including overnight ranges. It unions eligible windows before control, persists manual override boundaries, and only auto-resumes schedule-owned pauses. Agent triggers maintain persisted timestamps, ID watermarks or a consumed set, then enqueue in-memory conversations with per-agent serial/parallel and merge policy. Notification delivery and archive jobs have distinct PG job/claim lifecycles. [Scheduler tick and trigger scan](repos/RuoJi6__ARTEX/server/scheduler.go:37) · [Window calculation](repos/RuoJi6__ARTEX/server/calendar_schedule.go:52) · [Calendar control](repos/RuoJi6__ARTEX/server/calendar_schedule.go:232) · [Triggered conversation queue](repos/RuoJi6__ARTEX/server/conversations.go:719) · [Notification leases](repos/RuoJi6__ARTEX/db/notification_delivery.go:211) · [Archive claims](repos/RuoJi6__ARTEX/db/task_archives.go:358)

### Session, process and persistence boundaries

The exploration and activity rows are durable host state. Raw prompt messages are JSONL on disk. Worker keys are deterministic by exploration/intent, main-agent keys by exploration/segment, and custom chat keys by conversation. Workers and both chat forms create a fresh SDK `Session`, resume persisted history and reconstruct deferred-tool unlocks from prior skill invocations. The planner appends a per-exploration transcript for audit but builds a fresh request from current blackboard state. A missing transcript is normal for a new session. A resume error goes unreported by the worker and chat paths. Norma drops trailing tool requests whose result was never saved, preserving a request shape a provider can accept. That cannot certify whether an earlier side effect committed. [Task transcript setup](repos/RuoJi6__ARTEX/server/task_llm.go:575) · [Worker resume](repos/RuoJi6__ARTEX/agent/worker.go:468) · [Main segments](repos/RuoJi6__ARTEX/agent/mainagent.go:170) · [Chat resume](repos/RuoJi6__ARTEX/agent/chat.go:169) · [Planner history](repos/RuoJi6__ARTEX/agent/planner.go:444) · [SDK resume and unpaired tools]($HOME/go/pkg/mod/github.com/!autumn-27/norma@v0.4.3/agentcore/agentcore.go:361)

Sessions own a Norma background-task manager. Deferred `Close` cleans it up, and on Unix its tracked subprocesses run in process groups. ARTEX also has a separate interpreter runner for custom scripts and a separate transport/client lifecycle for MCP. Working directories isolate file organization at the application level. The reviewed code runs the tools under the host process's normal OS authority, with policy checks and configured tool visibility at the application boundary. When optional session compaction is enabled, Norma may use noa with a per-session archive. ARTEX separately compacts the graph: track cold age across rounds, group cold nodes into derived digests, retain original rows and re-check hot membership at rendering and before a new digest commits. [SDK process manager]($HOME/go/pkg/mod/github.com/!autumn-27/norma@v0.4.3/agentcore/agentcore.go:306) · [Unix process group]($HOME/go/pkg/mod/github.com/!autumn-27/norma@v0.4.3/tool/task_unix.go:11) · [Custom Python](repos/RuoJi6__ARTEX/server/customtool.go:380) · [Worker directory and session settings](repos/RuoJi6__ARTEX/agent/worker.go:383) · [Graph digest](repos/RuoJi6__ARTEX/agent/compaction.go:64) · [Digest recheck](repos/RuoJi6__ARTEX/agent/compaction.go:256)

On startup, each new `Manager` drops open accounting segments, loads task rows, and the server reopens stale `running` intents, reapplies pause gates and starts coordinators before running nonqueued, nonterminal tasks. Task deletion installs an in-process no-new-writes barrier and drains active work before durable cleanup. Archive and restore track jobs in PG, use staging journals and a checksummed package, coordinate with schema changes, and run compensating file/traffic operations across store boundaries. Large LLM records stream through the archive as a separate table payload. [Startup clocks](repos/RuoJi6__ARTEX/server/manager.go:591) · [Restore sequence](repos/RuoJi6__ARTEX/server/server.go:334) · [Intent reset](repos/RuoJi6__ARTEX/db/exploration.go:310) · [Task operation gate](repos/RuoJi6__ARTEX/server/engine_timeout.go:47) · [Archive task](repos/RuoJi6__ARTEX/server/task_archives.go:117) · [Archive journal recovery](repos/RuoJi6__ARTEX/server/task_archive_package.go:322) · [Schema lock](repos/RuoJi6__ARTEX/db/db.go:59)

Side questions use a captured request checkpoint for a parent session and a purpose-built, tool-free completion path. Their DB contract includes parent locking, version-ordered snapshot overwrite, per-generation request idempotency, one running answer per session and sequence-guarded state updates. Startup marks old running answers interrupted. This keeps their answer lifecycle independent of the parent agent's execution and transcript. [Side request and snapshot persistence](repos/RuoJi6__ARTEX/db/side_questions.go:19) · [Idempotent admission and update](repos/RuoJi6__ARTEX/db/side_questions.go:162) · [Startup interruption](repos/RuoJi6__ARTEX/db/side_questions.go:287) · [Tool-free service](repos/RuoJi6__ARTEX/sidequestion/service.go:11)

### Model, tools and events

`llm.Provider` isolates the SDK loop from OpenAI-compatible Chat, Responses and Anthropic transports. The per-task runtime reads PG before provider calls and follows role binding, active explicit chain, then the global provider when no explicit chain applies. Profile-pinned worker slots resolve only their pin. Task-chain quota transitions lock the task row and compare the chain revision before recording exhaustion and moving the cursor. The optional global pool uses prioritized members, rotating equal ranks, estimated context fit, and a persisted breaker. An HTTP-level limiter counts each actual attempt in rolling second and minute windows, with context cancellation and a shared identity across provider rebuilds. [Provider construction](repos/RuoJi6__ARTEX/agent/provider.go:266) · [Routing precedence](repos/RuoJi6__ARTEX/server/task_llm.go:112) · [Chain CAS](repos/RuoJi6__ARTEX/db/task_context.go:468) · [Pool ordering and breaker](repos/RuoJi6__ARTEX/llmpool/pool.go:82) · [Health registry](repos/RuoJi6__ARTEX/llmpool/health.go:92) · [Rate limiter](repos/RuoJi6__ARTEX/agent/request_limiter.go:12)

Same-provider retries are distinct from connection or empty-response retries inside the SDK, explicit quota failover, and whole-intent model-error retries. The task streaming router buffers non-committing events, retries transient failures before commitment and refuses to replay a committed quota-failed request. The generic pool uses its first emitted event as the corresponding boundary. Worker intent replay applies after a model error subject to policy and context checks and excludes router-classified failures. [Stream commit boundary](repos/RuoJi6__ARTEX/server/task_llm.go:304) · [Completion retries](repos/RuoJi6__ARTEX/server/task_llm.go:254) · [Global pool stream boundary](repos/RuoJi6__ARTEX/llmpool/pool.go:73) · [Worker replay](repos/RuoJi6__ARTEX/server/engine.go:1147) · [Policy layering](repos/RuoJi6__ARTEX/server/llmretry.go:28)

Run assembly combines role tools with DB bindings and overrides, custom tools, visible skills, and MCP adapters. A skill may reveal deferred tool descriptions and unlock them with a session-local call gate. The final assembly guards individual tool callbacks against panics. MCP clients share `Tools`/`Close` across stdio, Streamable HTTP and legacy SSE. Server-side approval hooks correlate tool-use/result records and synchronize a persisted pending decision with the in-process waiter. These controls have separate failure modes from model retries. [Run assembly](repos/RuoJi6__ARTEX/agent/assembly.go:39) · [Discovery and cleanup](repos/RuoJi6__ARTEX/server/assembly.go:55) · [DB tool decoration](repos/RuoJi6__ARTEX/server/assembly.go:270) · [MCP client contract](repos/RuoJi6__ARTEX/server/mcpdiscover.go:15) · [Approval waiter](repos/RuoJi6__ARTEX/intercept/intercept.go:679)

SDK events become application activities with actor, intent, tool-use ID, results and token usage. Publication follows PG persistence. SSE subscribes before replay and deduplicates its live tail against the replay cursor. Request recordings and aggregate usage have separate retention and storage paths. Notifications use durable event rows and claim/lease-based delivery retries instead of the live stream. [Event conversion](repos/RuoJi6__ARTEX/agent/capture.go:37) · [Durability before fanout](repos/RuoJi6__ARTEX/server/engine.go:657) · [SSE replay and tail](repos/RuoJi6__ARTEX/server/server.go:3340) · [Recording and usage](repos/RuoJi6__ARTEX/llmrec/llmrec.go:1) · [Notification fanout](repos/RuoJi6__ARTEX/db/notification.go:275)

## 3. Why the design works and its governing invariants

| Invariant | Mechanism and boundary |
| --- | --- |
| Local task admission has one decision point. | `concMu` orders competing transitions within one `Server`. The UPDATE compares the previous durable task status and mirrors the values returned by PG. Queue, pause and terminal are separate axes. API `running` may be derived from engine startup/readiness even while PG still holds `created`. [Admission lock](repos/RuoJi6__ARTEX/server/goals.go:148) · [Status projection](repos/RuoJi6__ARTEX/server/server.go:1320) |
| At most one claimant wins a single open intent transition. | Exploration and kind scope the UPDATE and `state='open'` prevents two successes. Sending a user message CASes from `paused` so the ordinary frontier cannot race for it. This invariant holds for an individual transition. Process restart policy can subsequently create a new open transition, as §5 shows. [Intent claim](repos/RuoJi6__ARTEX/db/exploration.go:1172) · [Detached CAS](repos/RuoJi6__ARTEX/server/engine.go:1332) |
| A controller can wait for work settlement. | Task and intent cancellation causes carry different meanings. Ordinary task pause reopens interrupted work. Per-intent pause commits `paused` before unblocking the controller, and a disconnected controller's cause is still usable. [Pause controller](repos/RuoJi6__ARTEX/server/task_control.go:96) · [Intent wait](repos/RuoJi6__ARTEX/server/engine.go:443) · [State settlement](repos/RuoJi6__ARTEX/server/engine.go:1172) |
| A task's normal operations stop entering when deletion begins. | Under `deleteMu`, the operation count is incremented atomically with a check of the barrier. Deletion can await admitted writers, then cancel and join task routines before clearing caches. This promise covers operations that enter that gate. [Operation gate](repos/RuoJi6__ARTEX/server/engine_timeout.go:47) · [Runtime join](repos/RuoJi6__ARTEX/server/engine.go:255) · [File and DB staging](repos/RuoJi6__ARTEX/server/manager.go:2059) |
| Observed partial model output pins that logical attempt. | The task router classifies committing stream events and leaves a committed error visible. Failed profile revisions are fenced in a PG transaction. Whole-intent retry uses the deterministic transcript to recover context. External exactly-once side effects are outside this invariant. [Stream behavior](repos/RuoJi6__ARTEX/server/task_llm.go:304) · [Revision guard](repos/RuoJi6__ARTEX/db/task_context.go:479) · [Transcript resume](repos/RuoJi6__ARTEX/agent/worker.go:494) |
| Durable observation and live delivery have different guarantees. | The row exists before broadcast. The live path is buffered and best effort. Direct history is available from PG with lineage and IDs. The versioned side-answer row and notification leases have their own stronger ownership safeguards. [Activity insert](repos/RuoJi6__ARTEX/db/exploration.go:1204) · [Broadcast buffer](repos/RuoJi6__ARTEX/server/broadcast.go:24) · [Side answer CAS](repos/RuoJi6__ARTEX/db/side_questions.go:203) · [Delivery claim](repos/RuoJi6__ARTEX/db/notification_delivery.go:211) |

The blackboard separation gives a planner an updated durable view without replaying every prior planning turn. Workers keep the intent mandate in the system context so compaction can remove old conversation turns without removing the job definition. The in-memory queue and wait-group model is straightforward for a single process and supports recovery from common exits through PG. It depends on a single owner for the live task set and explicit reconciliation whenever a transitional durable state crosses a restart boundary. [Planner state and context](repos/RuoJi6__ARTEX/agent/planner.go:381) · [Worker mandate rationale](repos/RuoJi6__ARTEX/agent/worker.go:377) · [Restore code](repos/RuoJi6__ARTEX/server/server.go:334)

## 4. Strengths

- **Explicit conditional writes at important boundaries.** The intent claim is a simple PG CAS with deterministic priority and queue ordering. In the focused contention control, 24 simultaneous callers produced one success and a foreign exploration could not acquire the intent. The provider failover cursor also uses a row lock and monotonic revision, so stale quota callbacks cannot advance a replacement chain. [Frontier and claim](repos/RuoJi6__ARTEX/db/exploration.go:1136) · [Profile revision](repos/RuoJi6__ARTEX/db/task_context.go:468)
- **Local ownership and failure explanations are visible in source.** Task routine contexts, per-intent cancellation handles, the deletion barrier and wait groups give distinct owners to loops and execution. Guarded terminal writes reflect committed runtime fields before best-effort hydration. Intent controls surface a conflict rather than claiming success on a lost state transition. [Engine ownership](repos/RuoJi6__ARTEX/server/engine.go:93) · [Intent transition](repos/RuoJi6__ARTEX/server/engine.go:498) · [Terminal mirror](repos/RuoJi6__ARTEX/server/manager.go:1971)
- **Selective reuse of persisted state.** Origin/fact/intent edges support audit and dependency reasoning, source tasks contribute read-only terminal context, workers resume stable transcripts, and phase-specific prompts place durable mandate and mutable situation in sensibly different places. The graph digest is derived and bounded in presentation, with on-demand source recall. [Source history](repos/RuoJi6__ARTEX/db/exploration_sources.go:74) · [Worker context](repos/RuoJi6__ARTEX/agent/worker.go:377) · [Cold member revival](repos/RuoJi6__ARTEX/agent/tools.go:400)
- **Provider reliability at several useful layers.** The router distinguishes quota, transport and deterministic failures, honors cancelable waits before retry, and has tests for pre-output retry and post-output non-replay. Request quotas survive provider cache replacement and are applied to HTTP attempts. [Retry regressions](repos/RuoJi6__ARTEX/server/task_llm_test.go:241) · [Midstream test](repos/RuoJi6__ARTEX/server/task_llm_test.go:375) · [Limiter transport](repos/RuoJi6__ARTEX/agent/request_limiter.go:126) · [Per-profile limiter registry](repos/RuoJi6__ARTEX/server/server.go:727)
- **Recoverable auxiliary jobs.** Archive operations use journals, rollback and startup recovery across PG, SQLite and files. Notification fan-out is transactional and delivery uses leases and backoff. Side-answer updates fence late writes by generation and sequence. These implementations show useful local precedents for durable orchestration elsewhere in the system. [Archive recovery](repos/RuoJi6__ARTEX/server/task_archives.go:36) · [Archive commit](repos/RuoJi6__ARTEX/server/task_archives.go:196) · [Notification fanout](repos/RuoJi6__ARTEX/db/notification.go:275) · [Side generation](repos/RuoJi6__ARTEX/db/side_questions.go:203)
- **Useful evidence and fixture seams.** Model, HTTP and DB interfaces made it possible to test actual claim, settlement, source hydration, control, archive and replay behavior offline. Activity append failure diagnostics include task/entity IDs and FK context, and tool callbacks are individually recoverable from panic. [Activity diagnostics](repos/RuoJi6__ARTEX/server/engine.go:659) · [Provider fixture seams](repos/RuoJi6__ARTEX/server/task_llm.go:100) · [Tool panic containment](repos/RuoJi6__ARTEX/agent/assembly.go:82)

## 5. Weaknesses and evidence status

Priorities reflect state loss, execution boundaries and the difficulty of operator recovery. The observations below are from `TestReview*` controls against the pinned implementation. A passing control means the observed behavior was reproduced and its comparison case behaved as expected.

### High priority

1. **A restart can complete an unfinished bootstrap as if its work were done.** Admitting an unqueued task clears `queue_mode` before spawning asynchronous goal decomposition. After a restart, `restoreTaskRuntimes` calls `Run` directly for the unqueued row. The first planner wake treats zero open goals and zero active intents as completion. In two fresh-manager recoveries the goal text survived, the goal node count stayed zero, and the task became `done`. A second task with a persisted open goal entered the fake planner and stayed nonterminal. The vulnerable interval is between durable admission/queue removal and durable goal materialization. No corruption or model failure was required. [Admission SQL](repos/RuoJi6__ARTEX/server/manager.go:1493) · [Bootstrap dispatch](repos/RuoJi6__ARTEX/server/goals.go:284) · [Startup run loop](repos/RuoJi6__ARTEX/server/server.go:334) · [Goalless decision](repos/RuoJi6__ARTEX/server/engine.go:921)
2. **An explicitly paused intent can become stranded in a completed task.** An intent pause ends in `paused`, but `HasActiveIntent` counts `open` and `running` only. For a goalless task the next planner wake completes the task. Intent resume performs its CAS and reports `open` without reviving the task, whose worker gate ignores the frontier while terminal. The fake worker was invoked once, stopped on pause and never reclaimed the reopened row. With an open goal the same pause and resume did return the intent to `running`. The test supplied a deterministic legitimate `Notify` wake. A normal heartbeat can reach the same branch. [Active intent predicate](repos/RuoJi6__ARTEX/db/exploration.go:1150) · [Pause CAS](repos/RuoJi6__ARTEX/server/engine.go:1188) · [Intent resume](repos/RuoJi6__ARTEX/server/task_control.go:234) · [Worker terminal gate](repos/RuoJi6__ARTEX/server/engine.go:1054)
3. **Restart admits previously active work before checking its calendar.** The restore routine starts task loops immediately, while the scheduler checks windows on its first timed tick. A closed one-shot schedule with a persisted unpaused task allowed the fake worker to start. A direct production calendar tick then canceled it with the schedule cause, persisted `paused`, and returned the intent to `open`. The fixture was an expired real schedule row, and the check observed a worker invocation before explicitly advancing the calendar. This also exposes the scheduling order to review during FIFO reconciliation, which precedes the calendar pass on every scheduler tick. [Restore order](repos/RuoJi6__ARTEX/server/server.go:334) · [Tick order](repos/RuoJi6__ARTEX/server/scheduler.go:41) · [Calendar control](repos/RuoJi6__ARTEX/server/calendar_schedule.go:284)
4. **Startup recovery assumes exclusive process ownership.** The conditional claim is sound for one open row transition, but startup changes every existing `running` intent to `open` without distinguishing stale and live owners. Two distinct Managers and Engines on the same PG fixture, using separate work directories, each held an active fake model call for the same intent after the second restored. The experiment models overlapping application lifetimes, rather than separate OS processes or a supported high-availability deployment. Active accounting segments are also cleared globally on Manager start. In a separate control, an unfinalized 75-second segment was discarded (7 seconds stayed recorded), while a finalized segment kept 82 seconds. This follows the documented choice to avoid charging an unobserved crash interval, and is also how the shown graceful path begins its next run. A single-container deployment is consistent with this assumption. Process exclusivity is an operational invariant the SQL claim alone cannot enforce. [Reset SQL](repos/RuoJi6__ARTEX/db/exploration.go:310) · [Startup invocation](repos/RuoJi6__ARTEX/server/server.go:340) · [Active segment clear](repos/RuoJi6__ARTEX/db/tasks.go:695) · [Single service compose example](repos/RuoJi6__ARTEX/docker-compose.yml:15)
5. **Graceful shutdown can leave an intent blocked instead of recoverable.** The CLI propagates `AbortShutdown`, but that cause is absent from `taskExecutionPaused`. A blocked fake provider that returned its context error gave a durable `blocked` intent on shutdown and `open` on ordinary task pause. `ResetRunningIntents` reopened zero rows after the shutdown case. If the process exits before settlement, the same run may instead remain `running` and be reopened on next startup. `Server.Close` waits for proxy supervision only, so HTTP shutdown and cancellation do not guarantee all task and checkpoint writers have finished before `Manager.Close` closes PG. The binary smoke check demonstrated clean idle exit, and the focused control isolated active-run settlement before store closure. A second race-enabled control let the worker receive the shutdown cause, held its simulated provider cleanup, and observed `Server.Close` return three times with one active call and a persisted `running` intent. [Cause propagation](repos/RuoJi6__ARTEX/cmd/artex/main.go:130) · [Pause-cause classification](repos/RuoJi6__ARTEX/server/engine.go:1354) · [Error state mapping](repos/RuoJi6__ARTEX/server/engine.go:1253) · [Close](repos/RuoJi6__ARTEX/server/server.go:325) · [Manager close](repos/RuoJi6__ARTEX/server/manager.go:1125)

6. **The no-result checkpoint can ignore a first uninterrupted execution segment.** The creation row starts as `created`; ordinary admission preserves that stored status and enables a run segment for either `created` or `running`. The no-result coordinator computes the remaining budget from stored lifecycle state, and `taskRunSeconds` adds a live segment only for `running`. With the real create/admit/start-segment operations and a 75-second live PG segment, a 60-second budget still had all 60 seconds left and the decision marker stayed unset. Changing only the durable status to `running` immediately committed `no_result` against the same segment. Three race-enabled repetitions matched. The DTO can independently report `running`, while the checkpoint uses the stored status. Bootstrap, resume, and time limits therefore need a shared phase or active-segment predicate. [Stored task default](repos/RuoJi6__ARTEX/db/schema.sql:513) · [Admission preserves status](repos/RuoJi6__ARTEX/server/goals.go:237) · [SQL starts either state](repos/RuoJi6__ARTEX/db/tasks.go:548) · [Remaining runtime computation](repos/RuoJi6__ARTEX/server/task_runtime.go:7) · [Checkpoint gate](repos/RuoJi6__ARTEX/server/engine_timeout.go:214) · [Status projection](repos/RuoJi6__ARTEX/server/server.go:1320)

### Medium priority

7. **Task deadline settlement can wait indefinitely for a final planner.** The 90-second constant bounds the initial drain, while `runFinalPlannerRound` polls indefinitely with the task/root context when a planner is unavailable. An already expired task with zero inflight operations stayed durable `running` and runtime `settling` across three readiness checks about four seconds apart from first to third. Canceling the coordinator released the waiter and still committed `timeout`. A ready fake planner produced a terminal status immediately after its single call. The finite observation establishes the polling path. The unbounded claim follows from the cancellation-only loop. The final phase relies on a prompt for the promise of no new intents while assembling ordinary planner domain tools. Ordinary planner completion also uses a less restrictive update than the guarded final path. [Settlement](repos/RuoJi6__ARTEX/server/engine_timeout.go:252) · [Readiness wait](repos/RuoJi6__ARTEX/server/engine_timeout.go:304) · [Final phase tool assembly](repos/RuoJi6__ARTEX/agent/planner.go:375) · [Ordinary planner terminal write](repos/RuoJi6__ARTEX/server/engine.go:970)
8. **Task timeout triggers use task creation order as event order.** The scan filters terminal task IDs above the largest previously seen ID. A newer task timed out first and advanced the watermark. The older task then timed out. Both were present in the full scan, and the incremental scan returned zero. The effect occurs before agent admission or delivery. Separately, the scheduler advances stored progress while triggered work is queued in memory, so a missing chat agent or a process exit before conversation creation can leave a consumed event with no run. The latter follows from source and was not treated as a proven crash-time delivery guarantee. [Timeout scanner](repos/RuoJi6__ARTEX/db/triggers.go:192) · [Persistent watermark write](repos/RuoJi6__ARTEX/server/scheduler.go:223) · [Volatile trigger queue](repos/RuoJi6__ARTEX/server/conversations.go:719) · [Conversation creation](repos/RuoJi6__ARTEX/server/conversations.go:928)
9. **SSE reconnect can skip a persisted event after backpressure.** A subscriber blocked at the initial flush received 256 events once released. The 257th persisted row exceeded the live channel capacity. If the subscriber disconnected at the preceding ID, the actual SSE handler recovered the missing row via `Last-Event-ID`. If a subsequent higher ID arrived before the disconnect, the handler recorded that higher cursor and replay returned zero. PG history from the earlier cursor still returned the dropped row. Nonblocking fan-out protects the engine, but its loss policy and the cursor's meaning disagree. The observed case requires one slow subscriber and a burst, with no DB error. [Broadcast drop](repos/RuoJi6__ARTEX/server/broadcast.go:49) · [Replay query](repos/RuoJi6__ARTEX/server/server.go:3386) · [Live cursor](repos/RuoJi6__ARTEX/server/server.go:3415)
10. **Custom Python timeout does not own descendant lifetime or bound output wait.** Plain interpreter timeout used `CommandContext`, `CombinedOutput` and the interpreter process only. A solo Python fixture returned near 301 ms for a 300 ms deadline. When a short-lived child inherited the output pipes, its post-deadline marker still arrived and the wrapper returned at 567–584 ms in ordinary repetitions and 590–848 ms under race instrumentation. The wrapper returned nil error and encoded the timeout in text. The child was inert and finite in a private PID namespace. The tracked SDK task path demonstrates a different process-group policy, so this result applies to ARTEX's custom-script runner. [Interpreter runner](repos/RuoJi6__ARTEX/server/customtool.go:380) · [Timeout outcome](repos/RuoJi6__ARTEX/server/customtool.go:409) · [SDK process group]($HOME/go/pkg/mod/github.com/!autumn-27/norma@v0.4.3/tool/task_unix.go:11)
11. **Legacy MCP SSE startup disregards the caller's cancellation while waiting for its endpoint.** `NewSSE` starts the GET from a detached background context with an unbounded HTTP client, then reads the first endpoint frame synchronously. On the same loopback fixture, Streamable HTTP returned after cancellation, while legacy SSE remained blocked for the 200 ms observation and unwound only when the server closed the stream. Because the constructor has not returned a closer, session cleanup cannot use it during that wait. This is a startup/cleanup contract mismatch for the legacy transport. [Legacy constructor](repos/RuoJi6__ARTEX/mcphttp/client.go:124) · [Endpoint read](repos/RuoJi6__ARTEX/mcphttp/client.go:182) · [Streamable HTTP request context](repos/RuoJi6__ARTEX/mcphttp/client.go:419) · [Run assembly waits](repos/RuoJi6__ARTEX/server/assembly.go:87)

### Bounded evidence and maintainability risks

Terminal worker loops remain allocated during the process lifetime. Because provider resolution precedes the terminal-state check, four completed fixture tasks still made eight resolver calls before explicit teardown. The test counted calls through a fake resolver. Actual DB pressure varies with role lookup and provider cache hits. Archive/delete's explicit `StopTask` halted further calls in the same fixture. In the opposite direction, graph projections bound serialized summaries but still load full nodes/edges for hot/cold reachability. Section 7 records the graph-size control. [Worker order](repos/RuoJi6__ARTEX/server/engine.go:1007) · [Role readiness](repos/RuoJi6__ARTEX/server/task_llm.go:545) · [Provider cache](repos/RuoJi6__ARTEX/server/server.go:655) · [Whole graph scan](repos/RuoJi6__ARTEX/agent/compaction.go:335)

The broad race run detected three conflicts around process-global hook pointers in the test process. An already-running planner from one fixture read `ToolAugment`, `ToolResolve` and `PromptOverride` while a different fixture restored those hooks. The two attributed chat-mention tests passed when run isolated under the race detector. This supports the scope and teardown critique and matters for multiple embedded server instances. It does not establish steady-state concurrent writes in the ordinary one-server CLI, where these callbacks are installed at startup. Detached graph compaction is another lifetime to account for, since it uses `context.WithoutCancel` and a separate five-minute bound. [Hook reads](repos/RuoJi6__ARTEX/agent/assembly.go:48) · [Prompt callback read](repos/RuoJi6__ARTEX/agent/prompt.go:53) · [Racing test cleanup](repos/RuoJi6__ARTEX/server/finding_retests_test.go:58) · [Startup callback wiring](repos/RuoJi6__ARTEX/server/server.go:218) · [Detached compactor](repos/RuoJi6__ARTEX/agent/compaction.go:85)

## 6. Core-code quality

| Dimension | Assessment |
| --- | --- |
| Decomposition | The `Engine`/`Manager` boundary, `llm.Provider`, PG stores, MCP adapter and separate side-question service give useful test seams. `server.go` (4,576 lines), `manager.go` (2,482), `engine.go` (1,385) and `agent/tools.go` (2,092) concentrate unrelated ownership and feature wiring. Unit-sized functions coexist with admission and startup functions carrying multiple policies and substantial cross-package work. [Server composition](repos/RuoJi6__ARTEX/server/server.go:173) · [Admission](repos/RuoJi6__ARTEX/server/goals.go:134) · [Task lifecycle snapshot](repos/RuoJi6__ARTEX/server/manager.go:100) |
| State and concurrency | SQL predicates, row locks, revision numbers, channels, `sync.Map` and wait groups provide understandable local guards. The hard part is keeping PG status, pause flags, queue flags, timers and per-task execution contexts synchronized. `Task` keeps multiple state axes and callers have to choose the correct snapshot and lock. Most of the reproduced admission and ownership problems sit at this boundary. [Lifecycle fields](repos/RuoJi6__ARTEX/server/manager.go:31) · [Snapshot](repos/RuoJi6__ARTEX/server/manager.go:131) · [Delete lock](repos/RuoJi6__ARTEX/server/engine_timeout.go:47) |
| Types and contracts | Run configuration, activities, graph nodes and provider contracts are typed. PG check constraints reject illegal state/kind combinations. Many transitions still use repeated string literals and graph payloads remain `map[string]any`/JSONB. The protocol admits versioned archive shapes and limits inherited context size, but tests can drift when projections and defaults change without a version or typed consumer contract. [Graph constraints](repos/RuoJi6__ARTEX/db/schema.sql:184) · [Node scan](repos/RuoJi6__ARTEX/db/exploration.go:703) · [Graph summary shape](repos/RuoJi6__ARTEX/agent/tools.go:358) · [Archive version](repos/RuoJi6__ARTEX/db/task_archives.go:19) |
| Errors and observability | Named cancellation causes and typed quota/profile errors make diagnostics actionable. The engine records append retries, SQLSTATE and FK evidence. Some paths still collapse DB errors into idle or empty state, including the frontier fetch/claim, stale-intent reset, fallback goal write and scheduler watermark reads. An accepted/error response can describe a committed SQL transition differently from a later in-memory decision. [Claim error handling](repos/RuoJi6__ARTEX/server/engine.go:1377) · [Goal fallback](repos/RuoJi6__ARTEX/server/goals.go:456) · [Scheduler watermark handling](repos/RuoJi6__ARTEX/server/scheduler.go:347) · [Activity diagnostics](repos/RuoJi6__ARTEX/server/engine.go:659) |
| Extensibility | One tool interface covers built-ins, role tools, extensions and MCP. Defensive concerns include process-wide callback installation, partial assembly on DB or transport failure, different cancellation policies, and replay of skill unlocks based on persisted text history. A role binding controls tool availability. OS process isolation remains an external deployment boundary. [Assembly](repos/RuoJi6__ARTEX/agent/assembly.go:29) · [MCP adapter](repos/RuoJi6__ARTEX/server/mcpdiscover.go:15) · [Run tool policy](repos/RuoJi6__ARTEX/agent/worker.go:426) · [Deferred history](repos/RuoJi6__ARTEX/agent/deferred.go:34) |
| Tests and maintenance | Meaningful package and PG integration coverage includes local provider streams, lease behavior, queue precedence, conditional updates and archive restore. The suite assumes a development DB in several places, and package advisory locks protect only package-level cleanup. Within a package, stale default profiles, live background contexts and global callback replacement still change later results. A narrow test is easier to trust when it owns its DB, root context and teardown. [Shared DB TestMain](repos/RuoJi6__ARTEX/server/testmain_test.go:12) · [Unjoined fixture](repos/RuoJi6__ARTEX/server/chat_llm_resolve_test.go:14) · [Archive test teardown example](repos/RuoJi6__ARTEX/server/task_archives_test.go:39) |

## 7. Executed tests and limitations

Counts use top-level Go `Test` results and exclude subtests unless specified. A package with no tests is listed separately. All database runs used test-owned schemas or databases on the same private cluster. Provider and MCP boundary controls used scripted Go providers or `httptest` servers. No test depended on a live model, a real target, an account or an external endpoint.

| Run | Result |
| --- | --- |
| Exact Go 1.26.10, `test -mod=readonly -count=1 -p=4 -timeout=4m -json ./...`, no database | 646 passed, 43 failed at the missing-DSN prerequisite, 313 skipped. Nineteen successful packages, one failed package, one package without tests. |
| Exact Go and fresh PG 16.16, `test -mod=readonly -count=1 -p=1 -timeout=5m -json ./...` | 992 passed, eight failed, two opt-ins skipped. Seventeen successful packages, three failed (`agent`, `db`, `server`) and one without tests. JSON timestamps 06:02:03–06:03:07 UTC. |
| Hardened, fresh database by package family | `agent` 88 passed/two failed, `db`+`evidence`+`llmrec` 223 passed/two failed, `server` 400 passed/one failed/two skipped. The four persistent `agent`/`db` failures were taken through the controls in §8. |
| Broad PG run with Go `-race`, fresh DB, `-p=1` | 992 passed, eight failed, two opt-ins skipped at its start. Three reports of shared hook-pointer races. JSON 06:11:58–06:14:10 UTC. The two race-attributed tests both passed independently on a fresh DB. |
| Focused package race re-run with fresh DB and the diagnosed marker fixture excluded | 49 top-level tests and 47 subtests passed across `server`, `db`, `agent`, `sidequestion` and `llmpool`; no race reports. The marker fixture received its own 48-run stress test and direct lifecycle control. |
| Added local behavior controls through Go overlay | Initial controls and extended checks reproduced the observations in §5. Hardened race-enabled confirmation passed 30 top-level runs and 20 subtests across two repetitions, with no race reports in that harness. The appendix replay passed 34 top-level runs and 20 subtests in a new DB, plus both graph-size runs. Separate race-enabled checks of process shutdown ownership and the initial active-run budget passed three repetitions each. A final run of the main control set passed 38 top-level tests and 20 subtests across two repetitions. |
| Calibrated broad run with test-only overlays | 998 top-level passes and two failures on a new DB. This run excluded `TestGraphOverviewExpandsAssociatedCompanyScope` and corrected three stale assertions plus the default-profile cleanup. A side-question test had depended on the now-absent leaked default fixture. A remarks subtest observed a concurrent lifecycle change. See §8 for both controls. Final test-only fixture-calibrated run passed 999 top-level tests with 1 failures and 1 live opt-in skips; the isolated remarks check is separate. Package results were 19 passed, 1 failed, and 1 without tests. |
| Package vet and compiled CLI | `go vet -mod=readonly ./...` was silent with exit 0. `go build` produced an amd64 backend. Inside a loopback-only namespace the built binary returned HTTP 200 and `{"ok":true}` on `/api/health`, then exited 0 on SIGTERM. This verifies process startup/shutdown at idle. The active-run behavior was measured separately. |
| Opt-in file-directory smoke | `TestTaskFilesRealDirectory` passed with a generated `.txt` and a valid 2×2 JPEG in a scratch task `313` layout. The opt-in live-review test remained skipped. |

The graph-size control inserted only confirmed synthetic facts with short payloads and no graph edges beyond the origin row. It measured five serial calls per sample in each of two runs on a local Unix socket. Recent prompt facts stayed at 20. `loadColdGraph` still materialized 101, 1,001 and 10,001 nodes, and the `facts` summary capped at 1,000 because it reports the size of a limited fetch. The two call-time medians were 0.89/0.83 ms, 1.94/1.88 ms and 11.20/9.51 ms for the three sizes. These are one-machine fixture timings, with no production latency or throughput implication. `graphOverviewData` and `loadColdGraph` are both checked-in paths. [Projection](repos/RuoJi6__ARTEX/agent/tools.go:405) · [Fact limit](repos/RuoJi6__ARTEX/agent/tools.go:448) · [Graph materialization](repos/RuoJi6__ARTEX/agent/compaction.go:335)

Tests exercised the application and SQL transition semantics on Linux/amd64 and PG 16.16. Coverage limits include multi-node deployments, power loss, live provider model quality and quota policy, host policy coverage, operating-system job lifetime on Windows, and the frontend. The overlapping-manager control used two owners in one test process, isolated Go state and a shared database. Local SQLite/PG integration tests exercised archive persistence and restore; fault coverage was limited to the tested transitions. Source claims about indefinite waiting are grounded in control-flow bounds in addition to short timing measurements.

## 8. Measurement audit

### Fixture and environment checks

- **Dependencies and isolation.** `go list -mod=readonly ./...` resolved all 21 Go packages offline. Native server binaries were absent from the normal PATH and local package cache. `docker image ls` against the local Unix daemon found the cached `postgres:16-alpine` image. It was saved locally and unpacked into scratch. Initially `bwrap` could not create bind targets in a read-only rootfs. Creating the mount point directories in scratch, then using a local passwd mapping, allowed non-root `initdb`. The initialized `C` locale and `UTC` database were sufficient for the fixtures. The checkout's Compose example also uses PostgreSQL 16. [Module manifest](repos/RuoJi6__ARTEX/go.mod:1) · [Compose database](repos/RuoJi6__ARTEX/docker-compose.yml:1)
- **Local DB path ceiling.** Direct `psql -h` with the workspace socket failed before dialing because the Unix socket filename exceeded the 107-byte limit. A mode-700 short directory under `/tmp` with a symlink to the same socket fixed it. A credential-free `SELECT version(),current_user,inet_server_addr() IS NULL` returned PostgreSQL 16.16, the fixture role and `t`. A real fresh database was created for each targeted group. The database listened on Unix sockets only.
- **No-database baseline.** Every one of 43 top-level errors reported the missing DB configuration, while other fixtures explicitly skipped through `db.DSN`/`NewManager`. The successful PostgreSQL integration runs resolved these setup negatives. The initial broad shared-DB run's logs contain failed attempts by fixture code to dial default provider names under a network namespace with loopback and no external routes. Go returned `network is unreachable`. The host resolver path was not masked in that first run. Subsequent runs also masked `/run`, used Go's resolver and an empty environment, and mounted the repository and module cache read-only. The final runtime observations use that hardened wrapper and inert model endpoints. [DSN precedence](repos/RuoJi6__ARTEX/db/db.go:89) · [Fixture gate](repos/RuoJi6__ARTEX/server/engine_no_result_test.go:72)
- **CLI smoke and files.** The first `curl` command used `.2` as its timeout and silently failed option parsing under the readiness loop. `curl --max-time .2 --version` reproduced the parser error without a request. With `--max-time 0.5`, explicit response status and the same private PG fixture, the backend returned 200 and exited 0. A read-only VCS stat cache warning on the initial Go build did not affect the binary or the health check; `-buildvcs=false` provided a separate clean build. The optional file check used ImageMagick after Python reported that PIL was absent. The test then passed on generated text and JPEG artifacts. [Health handler](repos/RuoJi6__ARTEX/server/server.go:1180) · [File fixture requirements](repos/RuoJi6__ARTEX/server/task_files_test.go:317)

### Checked-in suite failures

| Negative or surprise | Attribution and discriminating follow-up |
| --- | --- |
| `TestGraphOverviewExpandsAssociatedCompanyScope` | Stable on a clean DB on both repetitions. The fixture had already verified the associated asset and its company provenance before the failure. It expected a `coverage.scope` payload that the current `graphOverviewData` never emits. The runtime calculates scope-based counters and related-source context through separate paths. A test-only projection control verified the stored company link and all five scope rules through the stores, then passed the unchanged coverage, scoped read and intent-anchor checks. The original failed on the older projection shape. [Fixture assertion](repos/RuoJi6__ARTEX/agent/blackboard_inheritance_test.go:70) · [Current coverage projection](repos/RuoJi6__ARTEX/agent/tools.go:523) · [Scope store](repos/RuoJi6__ARTEX/db/task_scope.go:235) |
| `TestCaptureApprovalLifecycle`, three subcases | Stable twice on a fresh DB. The invalid mock action now goes through the configured default human-review fallback and the fixture reports `timeout` after its one-second configured policy. Two actual manual decisions persist `manual`, while the old assertion requires `model` for every row. Execution outcomes matched the inert probe; a test-only overlay changed the fallback and source expectations and passed all six subcases. [Fixture](repos/RuoJi6__ARTEX/agent/capture_approval_test.go:39) · [Assertion](repos/RuoJi6__ARTEX/agent/capture_approval_test.go:114) · [Failure handling](repos/RuoJi6__ARTEX/intercept/intercept.go:472) · [Manual persistence](repos/RuoJi6__ARTEX/intercept/intercept.go:773) |
| `TestInterceptApprovalFilters` | The fixture sets 2099 timestamps on the first rows, then creates its searched row using the current clock and filters that new row to January 1, 2099. Text, literal-percent and ID subchecks passed. The same test returned the expected day-filter match when only the searched fixture row was assigned an explicit 2099 UTC timestamp in a temporary test overlay. [Original setup](repos/RuoJi6__ARTEX/db/intercept_filter_test.go:62) · [Searched row](repos/RuoJi6__ARTEX/db/intercept_filter_test.go:144) · [Date predicate](repos/RuoJi6__ARTEX/db/intercept.go:353) |
| `TestSideTaskArchiveVersions`, three subcases | The failure printed two side sessions and two side requests, which matched its row expectations. The assertion hard-codes writer version 3, while the current writer emits 4 and the reader accepts versions 1–4. A test-only overlay compared the newly-created archive with `TaskArchiveFormatVersion` and ran the unchanged legacy read cases 1, 2 and 3 to completion. [Assertion](repos/RuoJi6__ARTEX/db/side_questions_test.go:382) · [Version range](repos/RuoJi6__ARTEX/db/task_archives.go:19) · [Snapshot version](repos/RuoJi6__ARTEX/db/task_archives.go:652) |
| `TestCoreTaskLifecyclePG` | Passed alone on a fresh DB, failed after `TestChatUnavailableReasonDistinguishesStates` in a two-test fresh run. The predecessor activated a fake profile. Its deferred Manager close ran before `t.Cleanup` removed the profile, leaving the default installed. The later server started provider-driven decomposition and missed its three-second assertion window. Only changing the predecessor's cleanup registration so DB teardown ran last made the exact pair pass, under the same offline network and PG arrangement. [Leaked fixture](repos/RuoJi6__ARTEX/server/chat_llm_resolve_test.go:14) · [Cleanup and activation](repos/RuoJi6__ARTEX/server/chat_llm_resolve_test.go:37) · [Core wait](repos/RuoJi6__ARTEX/server/core_test.go:75) |
| Three original shared-DB server cleanup failures | `TestInheritedActivityDetailAndRelationDeletion`, `TestTaskMetadataPatchGlobalAssetSharing` and `TestWorkerPoolSettingsRoundTrip` each passed alone on fresh DBs, then passed on the hardened package run. Their original failure was `TempDir RemoveAll cleanup: directory not empty`, and preceding fixture logs showed reloaded tasks and work using already-closed stores. These controls show teardown interference under the shared fixture. The original failure logs lack enough detail to identify each directory-writing goroutine. [Server restoration](repos/RuoJi6__ARTEX/server/server.go:334) · [Server close scope](repos/RuoJi6__ARTEX/server/server.go:325) · [Core fixture context](repos/RuoJi6__ARTEX/server/core_test.go:27) |
| `TestPoolProfilesOrder` under `-count=3` | Passed first, then failed twice at INSERT with SQLSTATE 23505. The fixture uses fixed profile names and defers DB close ahead of a cleanup callback that uses the same handle. Fresh DB, `-count=1` passed. The database had retained the two fixed profile names from the first run. SQL uniqueness enforcement accounts for the repeat-only failure. [Fixture names and cleanup](repos/RuoJi6__ARTEX/db/config_test.go:15) |
| `TestTimedOutTaskRevivalResetsClockAndSettlingAcrossFIFO` | A single fresh focused pass exposed the assertion flake. `-race -count=24 -cpu=1,8` produced 44 passes and four failures, all at the final coordinator marker assertion. The helper uses a pre-canceled root. The coordinator can exit and correctly delete its token before the assertion. A direct control observed the marker under a live root and its removal after cancellation; SQL clock and queue checks in the original fixture passed. [Canceled helper](repos/RuoJi6__ARTEX/server/task_admission_test.go:18) · [Marker assertion](repos/RuoJi6__ARTEX/server/task_admission_test.go:281) · [Coordinator cleanup](repos/RuoJi6__ARTEX/server/engine_timeout.go:152) |
| Race reports attributed to two chat-mention tests | These tests both passed in an isolated fresh DB race run. The broad trace showed an old planner's reads at `agent/assembly.go:48`, `:63` and `agent/prompt.go:55` racing with restoration of shared callbacks at `server/finding_retests_test.go:67`. The old planner originated in `New(context.Background(), …)` from `server/chat_llm_resolve_test.go:21`. The trace attributes the conflicts to process ownership and callback lifetime in tests. [Planner read](repos/RuoJi6__ARTEX/agent/assembly.go:48) · [Prompt read](repos/RuoJi6__ARTEX/agent/prompt.go:55) · [Cleanup write](repos/RuoJi6__ARTEX/server/finding_retests_test.go:64) |
| `TestRemarksRoundTripPreservesExecutionState` under full `-race` | Isolated `-race -count=6` passed six times. The failing full-run row was a disabled schedule changed to `paused`, matching the calendar tick, and it still carried the renamed value. The SQL metadata update touches only name and remark. A direct calendar control demonstrated the rename preserving the existing completed state and the next scheduler pass changing the same row to paused. In the calibrated broad run a task bound to the disabled schedule also changed lifecycle during the task metadata subtest. The scheduler has a separate path to pause attached running tasks outside allowed windows, while the metadata SQL has a separate field list. [Original assertion](repos/RuoJi6__ARTEX/server/remarks_test.go:165) · [Metadata write](repos/RuoJi6__ARTEX/db/schedules.go:419) · [Tick state write](repos/RuoJi6__ARTEX/server/calendar_schedule.go:322) |
| `TestSideTaskContextModelUnavailableIsDistinct` after calibrated profile cleanup | The clean fixture had no active row. The checked-in test queries an active profile before executing either request assertion and returned SQL `ErrNoRows`, both in the calibrated broad run and on a separate fresh DB. A test-only overlay explicitly created and selected a keyless local placeholder profile, then passed the GET and POST model-unavailable assertions. [Fixture lookup](repos/RuoJi6__ARTEX/server/side_questions_test.go:410) · [Default-profile transition](repos/RuoJi6__ARTEX/db/config.go:429) |
| `TestTaskArchiveAPIQueueListAndLimits` in the final calibrated broad comparison | The isolated original test passed six race-enabled repetitions. In the broad run archive returned the explicit queued-state 409 after the test directly set the paused bit. Even a canceled `Server` constructor launches concurrency reconciliation. With the limiter enabled that path can queue an unavailable task. Direct control applied that valid queued state, verified that SQL-only `SetPaused(true)` still failed the archive check, then restored the unpaused fixture state and used the full lifecycle pause to clear queue state and successfully archive. The initial comparison attempted the full pause on an already-paused row, which the pause CAS correctly rejected. [Fixture](repos/RuoJi6__ARTEX/server/task_archives_test.go:33) · [Startup reconciliation launch](repos/RuoJi6__ARTEX/server/server.go:309) · [Queueing path](repos/RuoJi6__ARTEX/server/goals.go:320) · [Pause CAS](repos/RuoJi6__ARTEX/server/manager.go:1630) · [Archive eligibility](repos/RuoJi6__ARTEX/db/task_archives.go:230) |

### New control calibration

- The initial restart fixture assumed a newly created task had stored `running` status. Admission rejected its expected-status CAS when the actual row was `created`. The revised bootstrap test read the actual stored state and used the same transition as normal first admission. The deadline fixture explicitly set the comparison state to `running`. Both revised conditions were re-run on a new database. The state reported by `resolvedTaskStatusFromSnapshot` need not be the stored status. [Schema defaults](repos/RuoJi6__ARTEX/db/schema.sql:505) · [Admission CAS](repos/RuoJi6__ARTEX/server/manager.go:1552) · [Status projection](repos/RuoJi6__ARTEX/server/server.go:1320)
- Calendar restore ran as expected in the first version, but test cleanup used a deferred-close handle. Registering Manager close before the task and schedule cleanup registered the resource lifetime correctly, and the final double race run passed. The first merged overlay used colliding scratch basenames for the `db` and `server` copies of `side_questions_test.go`, and Go rejected the inconsistent package declaration. Keeping package-relative scratch paths and checking unique overlay targets corrected compilation. The graph sizing setup initially inserted facts with `done`, which PG rejected at `ck_node_state` (23514). `confirmed` matches both SQL policy and the production fact writer. The two repeated samples then verified loaded row counts and projection caps. These errors were in the evaluation fixtures. [Graph check](repos/RuoJi6__ARTEX/db/schema.sql:184) · [Fact writer](repos/RuoJi6__ARTEX/agent/tools.go:1340)
- Paused-intent controls checked durable intent and task rows, not just telemetry or a sleep. The fake provider recorded a start before cancellation. The open-goal comparison demonstrated that the same resume transition can produce a new claim. The activity test held SSE at a synchronized flush, waited for exactly 256 live IDs, checked PG for the dropped row, and invoked the real SSE replay path again with `Last-Event-ID`. The later-ID and prior-ID cases used identical stores and channel capacity.
- Deadline polling used three readiness calls at the implementation's two-second interval, consistent with the source. The comparison used a ready no-tool fake and zero inflight work. The overlap fixture separately verified one-winner claim behavior on one open version before exercising startup reset with two owners. The calendar fixture checked the window was closed before calling restore and forced a known calendar tick to validate both the pause transition and reopened intent.
- Python was discovered via PATH and used the same interpreter and body setup in both branches. The child and its parent were local finite fixtures. The late marker distinguishes an inherited pipe and child lifetime from simple launch latency. The MCP comparison used a flushed 200 response that deliberately withheld the endpoint frame. Both code paths received the same cancel signal. A reset test checked the version of the generated archive independently of the version assertions in the repository.

## 9. Post-mortem and prioritized improvements

ARTEX evolved from a graph-centered model loop into a local control plane with persistent queues, schedules, intent intervention, profile failover, archived tasks and operator-visible evidence. The current pin is shallow, so historical conclusions are based on checked-in design notes and release notes. They document the move from SQLite graph state to PG, the effort to reduce duplicate provider calls, and recovery fixes for cross-store archive operations and long-running model sessions. New features preserved short, independent execution scopes. They also accumulated implicit phase markers in row fields and in-memory maps. The bootstrap gap, paused-intent completion, overlapping owner and lost timeout triggers are variations on that split ownership. [DB package history note](repos/RuoJi6__ARTEX/db/db.go:1) · [Retry and settlement notes](repos/RuoJi6__ARTEX/CHANGELOG.md:528) · [Archive incident notes](repos/RuoJi6__ARTEX/CHANGELOG.md:606) · [No-result lifecycle note](repos/RuoJi6__ARTEX/CHANGELOG.md:24)

1. **Make the durable task phase and its owner explicit.** Keep bootstrap pending/complete through admission and restart, and make completion distinguish pending, sleeping, paused and finished intent work. Enforce calendar eligibility before restoring or promoting runnable work. Record and check a run generation or lease when adopting and completing work. For a single-instance product, an exclusive runtime lease with a clear startup error would protect the existing assumption with less surface area. These changes address the highest-impact findings because they remove ambiguity about which row owns the next step. [Current startup and goalless paths](repos/RuoJi6__ARTEX/server/server.go:334) · [Terminal branch](repos/RuoJi6__ARTEX/server/engine.go:921) · [Lease example](repos/RuoJi6__ARTEX/db/notification_delivery.go:211)
2. **Make stop a bounded protocol with durable results.** Give each runtime an explicit stop-and-join owner, stop admitting work before shutdown, and settle or mark intent ownership recoverable before closing PG. Persist counted runtime at a defined graceful boundary. Use a separate deadline for the final planner and a clear durable terminal reason if the model is unavailable. Add a uniform process/call ownership contract for extensions, including descendants, transport open and output drain. The tested independent limits currently cover different portions of a single lifetime. [Coordinator stop](repos/RuoJi6__ARTEX/server/engine_timeout.go:251) · [Current close](repos/RuoJi6__ARTEX/server/server.go:325) · [Process manager contract]($HOME/go/pkg/mod/github.com/!autumn-27/norma@v0.4.3/tool/task.go:513) · [Socket open](repos/RuoJi6__ARTEX/mcphttp/client.go:124)
3. **Give progress delivery a commit point.** Use durable transition events and idempotent consumption for custom-agent triggers, following the notification claim pattern. A task ID should identify the task, while a timeout event has its own ordering. SSE can retain nonblocking wake-ups if it re-reads durable rows after a wake and treats overflow as a reconnect/replay boundary before advancing the cursor. Make queue, settlement, drop and retry counters observable with IDs that correlate state and activity. [Timeout ID scan](repos/RuoJi6__ARTEX/db/triggers.go:192) · [Event fanout](repos/RuoJi6__ARTEX/db/notification.go:275) · [Current SSE watermark](repos/RuoJi6__ARTEX/server/server.go:3423)
4. **Scope configuration and fixtures to the owner.** Inject an instance-owned assembly and prompt resolver into the engine, and make server shutdown join task, archive and checkpoint work. Provision fresh PG state per integration group in CI and test the process lifecycle using controlled fake providers. Prioritize transition-table tests around pending bootstrap, schedule crossing, simultaneous timeout and manual pause, and cancellation-stage durability. Validate archive/version fixtures with current codecs. These changes would make ordinary failures easier to classify and keep shared fixtures from changing later tests. [Global wiring](repos/RuoJi6__ARTEX/server/server.go:218) · [Archive worker teardown example](repos/RuoJi6__ARTEX/server/task_archives_test.go:39) · [Current fixture scope](repos/RuoJi6__ARTEX/server/testmain_test.go:12)

A durable task lifecycle has the highest leverage across the reproduced restart and admission failures. Existing CAS predicates establish one-winner local updates. They need a durable lifecycle phase that startup, admission, cleanup and the operator agree on. The repo already has useful patterns for transactions, versions, job leases and compensating storage operations in its secondary services.

## 10. Evidence appendix

### Source map

| Investigation | Entry points and persistence |
| --- | --- |
| Process and shutdown | [CLI signal and HTTP shutdown](repos/RuoJi6__ARTEX/cmd/artex/main.go:93) · [Shutdown cause](repos/RuoJi6__ARTEX/cmd/artex/main.go:148) · [Server close](repos/RuoJi6__ARTEX/server/server.go:325) · [Manager cleanup](repos/RuoJi6__ARTEX/server/manager.go:1125) |
| Task and graph ownership | [Task transaction](repos/RuoJi6__ARTEX/db/tasks.go:213) · [Graph state checks](repos/RuoJi6__ARTEX/db/schema.sql:184) · [Task row defaults](repos/RuoJi6__ARTEX/db/schema.sql:505) · [Origin/intents](repos/RuoJi6__ARTEX/db/exploration.go:197) · [Priority claim](repos/RuoJi6__ARTEX/db/exploration.go:1136) · [Task runtime](repos/RuoJi6__ARTEX/server/engine.go:235) |
| Coordination and schedule | [Admission/FIFO](repos/RuoJi6__ARTEX/server/goals.go:134) · [Calendar startup rules](repos/RuoJi6__ARTEX/server/calendar_schedule.go:129) · [Calendar tick](repos/RuoJi6__ARTEX/server/calendar_schedule.go:232) · [Settlement coordinator](repos/RuoJi6__ARTEX/server/engine_timeout.go:166) · [Task-clock clamp](repos/RuoJi6__ARTEX/agent/taskclock.go:35) |
| Control and durability | [Cancel and wait](repos/RuoJi6__ARTEX/server/engine.go:446) · [Resume and delete](repos/RuoJi6__ARTEX/server/task_control.go:210) · [Delete staging](repos/RuoJi6__ARTEX/server/manager.go:2064) · [Archive claim](repos/RuoJi6__ARTEX/db/task_archives.go:371) · [Archive recovery](repos/RuoJi6__ARTEX/server/task_archive_package.go:389) · [Side snapshots](repos/RuoJi6__ARTEX/db/side_questions.go:45) |
| Session and model paths | [Agent bundle and transcript](repos/RuoJi6__ARTEX/server/task_llm.go:575) · [Provider cache](repos/RuoJi6__ARTEX/server/server.go:655) · [Provider constructors](repos/RuoJi6__ARTEX/agent/provider.go:283) · [Task-chain stream](repos/RuoJi6__ARTEX/server/task_llm.go:304) · [Intent-keyed session](repos/RuoJi6__ARTEX/agent/worker.go:85) · [Worker replay](repos/RuoJi6__ARTEX/agent/worker.go:491) |
| Event and extension boundary | [SDK capture](repos/RuoJi6__ARTEX/agent/capture.go:37) · [Activity path](repos/RuoJi6__ARTEX/server/engine.go:659) · [SSE](repos/RuoJi6__ARTEX/server/server.go:3340) · [Trigger cursor](repos/RuoJi6__ARTEX/server/scheduler.go:221) · [Extension assembly](repos/RuoJi6__ARTEX/server/assembly.go:26) · [Interpreter boundary](repos/RuoJi6__ARTEX/server/customtool.go:380) · [Legacy SSE client](repos/RuoJi6__ARTEX/mcphttp/client.go:124) |

### Reproduction environment and commands

The original checkout was only read. In the following reconstruction, run from the workspace root. `S` is an isolated temporary directory inside that workspace, so all generated fixtures, Go build/temp caches, test overlays and database data are disposable. The socket directory under `/tmp` exists only to satisfy the Unix socket path limit. This setup needs the exact Go toolchain and modules already cached and the PostgreSQL image already present on the local machine. The sole Docker operation that moves data is a local image export. The fixture is detached from external networking and accepts local trust connections only on a private filesystem socket. A fake test identity is used without a password.

```bash
S=$(mktemp -d "$PWD/.artex-review.XXXXXX")
R="$PWD/repos/RuoJi6__ARTEX"
REPORT="$PWD/evaluations/RuoJi6__ARTEX.md"
GIT_OPTIONAL_LOCKS=0 git -C "$R" rev-parse HEAD
GIT_OPTIONAL_LOCKS=0 git -C "$R" status --porcelain=v1 --untracked-files=all --ignored
mkdir -p "$S"/{home,cache,tmp,pgroot,pgdata,pgsock}
chmod 700 "$S"/{pgdata,pgsock}
env -i PATH=/usr/bin:/bin HOME="$S/home" DOCKER_CONFIG="$S/home" \
  docker -H unix:///run/docker.sock image inspect postgres:16-alpine --format '{{.Id}} {{.Os}}/{{.Architecture}}'
env -i PATH=/usr/bin:/bin HOME="$S/home" DOCKER_CONFIG="$S/home" \
  docker -H unix:///run/docker.sock image save --platform linux/amd64 postgres:16-alpine > "$S/pg16-image.tar"
tar -xOf "$S/pg16-image.tar" manifest.json |
  python -c 'import json,sys; print(*json.load(sys.stdin)[0]["Layers"], sep="\n")' |
  while IFS= read -r layer; do
    tar -xOf "$S/pg16-image.tar" "$layer" | bsdtar -x --no-same-owner --no-same-permissions -C "$S/pgroot"
  done
mkdir -p "$S/pgroot"/{pgdata,pgsock}
cp "$S/pgroot/etc/passwd" "$S/pgpasswd"
printf 'reviewpg:x:%s:%s:Review fixture:/tmp:/bin/sh\n' "$(id -u)" "$(id -g)" >> "$S/pgpasswd"
short=$(mktemp -d /tmp/artex-review-pg.XXXXXX)
ln -s "$S/pgsock" "$short/socket"
printf '%s\n' "$short" > "$S/pgsocket.path"
env -i PATH=/usr/bin:/bin HOME="$S/home" bwrap --unshare-net \
  --ro-bind "$S/pgroot" / --ro-bind "$S/pgpasswd" /etc/passwd \
  --dev /dev --proc /proc --tmpfs /tmp \
  --bind "$S/pgdata" /pgdata --bind "$S/pgsock" /pgsock \
  --setenv PATH /usr/local/bin:/usr/bin:/bin --setenv HOME /tmp --chdir /tmp \
  sh -c 'postgres --version && initdb -D /pgdata -A trust --no-locale -E UTF8 -U artexreview && exec postgres -D /pgdata -k /pgsock -h "" -p 6543'
```

The last command stays in the foreground in its own terminal. The examined image ID was `sha256:81e77a4833487b8132fe4b00bedd39dc3f74b8641e387f19312a48f7de218c2e`. PostgreSQL reported 16.16. An alternative is a local native 16-series `initdb`/`postgres` with the same trust and Unix-only settings. Use the local `psql` control from the scratch wrapper environment:

```bash
short=$(cat "$S/pgsocket.path")
env -i PATH=/usr/bin:/bin HOME="$S/home" PGPASSFILE=/nonexistent unshare -Urn \
  psql -h "$short/socket" -p 6543 -U artexreview -d postgres -Atqc \
    'select version(), current_user, inet_server_addr() is null'
```

The following extractor copies the self-contained test inputs later in this appendix into scratch. It also constructs Go overlays, so the virtual test names never appear on disk within the checkout.

```bash
python - "$REPORT" "$S" "$R" <<'PY'
import json, pathlib, sys
report, scratch, repo = map(pathlib.Path, sys.argv[1:])
content = report.read_text()
for name in ('offline', 'newdb', 'audit-fixtures.py', 'engine_probe_test.go', 'agent_probe_test.go'):
    marker = f'<!-- review-file: {name} -->\n'
    start = content.split(marker, 1)[1].split('\n', 1)[1]
    (scratch / name).write_text(start.split('\n```', 1)[0] + '\n')
for suffix, package, fixture in [('', 'server', 'engine_probe_test.go'), ('-agent', 'agent', 'agent_probe_test.go')]:
    virtual = repo / package / 'zz_architecture_review_probe_test.go'
    (scratch / f'overlay{suffix}.json').write_text(json.dumps({'Replace': {str(virtual): str(scratch / fixture)}}) + '\n')
PY
chmod 700 "$S/offline" "$S/newdb"
python "$S/audit-fixtures.py" "$R" "$S"
"$S/newdb" broad run_race probe graph audit_orig audit_fixed audit_agent audit_db audit_side audit_scope archive_queue clock remarks race_flake
"$S/offline" no-db list -mod=readonly ./...
"$S/offline" no-db test -mod=readonly -count=1 -p=4 -timeout=4m -json ./... > "$S/no-db.json"
"$S/offline" broad test -mod=readonly -count=1 -p=1 -timeout=5m -json ./... > "$S/pg.json"
"$S/offline" run_race test -mod=readonly -race -count=1 -p=1 -timeout=5m -json ./... > "$S/race.json"
"$S/offline" no-db vet -mod=readonly ./...
"$S/offline" no-db build -mod=readonly -o "$S/artex-smoke" ./cmd/artex
"$S/offline" no-db version -m "$S/artex-smoke"
```

The full test commands return nonzero on the pinned original suite for the audited cases. Read the JSON `pass`, `fail`, and `skip` events with `Test` present and no `/` in the name for top-level counts. The broad race run and original no-DB run omitted the opt-in directory environment. The wrapper below supports the same runnable fixture when its directory exists.

```bash
"$S/offline" probe test -mod=readonly -race -overlay "$S/overlay.json" -count=2 -p=1 \
  -timeout=2m -v -run '^TestReview(Paused|Bootstrap|Final|Activity|Atomic|ArchiveFormat|TimeoutTrigger|Overlapping|PythonDeadline|MCPStartup|Shutdown|ServerClose|CoordinatorMarker|Calendar|TerminalWorker|RuntimeSegment|NoResultOn)' ./server
"$S/offline" archive_queue test -mod=readonly -race -overlay "$S/overlay.json" -count=2 -v \
  -run '^TestReviewArchiveQueuePauseControl$' ./server
"$S/offline" graph test -mod=readonly -overlay "$S/overlay-agent.json" -count=2 -p=1 \
  -timeout=90s -v -run '^TestReviewOverviewGraphWork$' ./agent
"$S/offline" audit_orig test -mod=readonly -count=1 -v \
  -run '^(TestChatUnavailableReasonDistinguishesStates|TestCoreTaskLifecyclePG)$' ./server
"$S/offline" audit_fixed test -mod=readonly -overlay "$S/overlay-audit-core.json" -count=1 -v \
  -run '^(TestChatUnavailableReasonDistinguishesStates|TestCoreTaskLifecyclePG)$' ./server
"$S/offline" audit_agent test -mod=readonly -overlay "$S/overlay-audit-approval.json" -count=1 -v \
  -run '^TestCaptureApprovalLifecycle$' ./agent
"$S/offline" audit_db test -mod=readonly -overlay "$S/overlay-audit-db.json" -count=1 -v \
  -run '^Test(InterceptApprovalFilters|SideTaskArchiveVersions)$' ./db
"$S/offline" audit_scope test -mod=readonly -overlay "$S/overlay-audit-scope.json" -count=1 -v \
  -run '^TestGraphOverviewExpandsAssociatedCompanyScope$' ./agent
"$S/offline" audit_side test -mod=readonly -overlay "$S/overlay-audit-side.json" -count=1 -v \
  -run '^TestSideTaskContextModelUnavailableIsDistinct$' ./server
"$S/offline" race_flake test -mod=readonly -race -count=24 -cpu=1,8 -v \
  -run '^TestTimedOutTaskRevivalResetsClockAndSettlingAcrossFIFO$' ./server
"$S/offline" remarks test -mod=readonly -race -count=6 -v \
  -run '^TestRemarksRoundTripPreservesExecutionState$' ./server
mkdir -p "$S/file-fixture/tasks/313/sub"
printf '%s\n' 'test fixture text' > "$S/file-fixture/tasks/313/sub/example.txt"
magick -size 2x2 xc:blue "$S/file-fixture/tasks/313/sub/preview.jpg"
"$S/offline" no-db test -mod=readonly -count=1 -v -run '^TestTaskFilesRealDirectory$' ./server
```

For the CLI lifecycle check, build into scratch, start the executable with `-addr 127.0.0.1:28787 -data "$S/cli-data" -proxy ''` inside the same isolated network and PID namespace with a new empty fixture DSN, poll `/api/health` with `curl -q --noproxy '*' -sS --max-time 0.5`, then send SIGTERM to that process and wait for its exit. The successful run returned `200`, `{"ok":true}` and exit 0. The VCS-stamped binary reported the pinned revision with `vcs.modified=false`.

### Exact control sources and helper scripts

<details>
<summary>Local wrappers, temporary fixture overlays and focused Go controls</summary>

<!-- review-file: offline -->
```sh
#!/bin/sh
set -eu
scratch=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
repo=$(dirname "$scratch")/repos/RuoJi6__ARTEX
goexe=$HOME/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.10.linux-amd64/bin/go
database=$1
shift
case "$database" in
  no-db) dsn='' ;;
  *) short=$(cat "$scratch/pgsocket.path")
     dsn="postgres://artexreview@/$database?host=$short/socket&port=6543&sslmode=disable" ;;
esac
file_fixture=""
[ ! -d "$scratch/file-fixture" ] || file_fixture="$scratch/file-fixture"
exec env -i PATH=/usr/bin:/bin HOME="$scratch/home" XDG_CACHE_HOME="$scratch/home/cache" GOMODCACHE=$HOME/go/pkg/mod GOCACHE="$scratch/cache" GOPATH="$scratch/home/go" GOTMPDIR="$scratch/tmp" TMPDIR="$scratch/tmp" GOTOOLCHAIN=local GOENV=off GOPROXY=off GOSUMDB=off GOVCS='*:off' GODEBUG=netdns=go LC_ALL=C TZ=UTC ARTEX_PG_DSN="$dsn" ARTEX_CONFIG="$scratch/no-config.json" ARTEX_TASK_FILES_TEST_DIR="$file_fixture" PGPASSFILE=/nonexistent unshare -Urn sh -c 'ip link set lo up && exec bwrap --unshare-pid --die-with-parent --ro-bind / / --dev /dev --proc /proc --tmpfs /run --bind "$1" "$1" --chdir "$2" -- "$3" "${@:4}"' bash "$scratch" "$repo" "$goexe" "$@"
```

<!-- review-file: newdb -->
```sh
#!/bin/sh
set -eu
scratch=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
short=$(cat "$scratch/pgsocket.path")
for name do
  case "$name" in *[!a-z0-9_]*|'') exit 2 ;; esac
  env -i PATH=/usr/bin:/bin HOME="$scratch/home" PGPASSFILE=/nonexistent unshare -Urn psql -v ON_ERROR_STOP=1 -h "$short/socket" -p 6543 -U artexreview -d postgres -c "CREATE DATABASE $name"
done
```

<!-- review-file: audit-fixtures.py -->
```python
import json
from pathlib import Path
import sys

root, scratch = (Path(p).resolve() for p in sys.argv[1:])
fix = scratch / 'audit-variants'
fix.mkdir(exist_ok=True)

def amend(path, replacements):
    orig = root / path
    text = orig.read_text()
    for old, new in replacements:
        if old not in text:
            raise RuntimeError(f'missing exact fixture fragment {old!r} in {path}')
        text = text.replace(old, new, 1)
    dst = fix / path
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text)
    return str(orig), str(dst)

def overlay(name, pairs):
    (scratch / f'overlay-audit-{name}.json').write_text(json.dumps({'Replace': dict(pairs)})+'\n')

overlay('db', [
    amend('db/side_questions_test.go', [('archive.FormatVersion != 3 || ', 'archive.FormatVersion != TaskArchiveFormatVersion || ')]),
    amend('db/intercept_filter_test.go', [('rows, total, err = d.ListTaskInterceptsPage(scope, 1, 20, InterceptApprovalFilter{\n\t\tSearch: "example.test", CreatedFrom:', '''if _, err := d.Exec(\x60UPDATE intercept_pending SET created_at=TIMESTAMPTZ '2099-01-01 12:00:00+00' WHERE id=$1\x60, searchID); err != nil { t.Fatal(err) }
	rows, total, err = d.ListTaskInterceptsPage(scope, 1, 20, InterceptApprovalFilter{
		Search: "example.test", CreatedFrom:''')]),
])
overlay('approval', [
    amend('agent/capture_approval_test.go', [
        ('{"model_fallback", "invalid", "allowed",', '{"model_fallback", "invalid", "timeout",'),
        ('initialAction = "allow"', 'initialAction = "ask"'),
        ('if detail.Status != tc.status || detail.DecisionSource != "model"', 'wantSource := "model"\n\t\t\tif tc.manual { wantSource = "manual" }\n\t\t\tif detail.Status != tc.status || detail.DecisionSource != wantSource'),
    ]),
])
overlay('core', [
    amend('server/chat_llm_resolve_test.go', [('defer m.Close()', 't.Cleanup(func() { _ = m.Close() })')]),
])

overlay('side', [
    amend('server/side_questions_test.go', [
        ('\tvar profileID int64\n\tvar originalAPIKey string', '''	fixtureID, err := f.m.pg.SaveProfile(&db.LLMProfile{Name: "keyless availability fixture", Format: "openai", BaseURL: "http://fixture.invalid", Model: "fixture"})
	if err != nil { t.Fatal(err) }
	if err := f.m.pg.SetActiveProfile(fixtureID); err != nil { t.Fatal(err) }
	t.Cleanup(func() {
		_, _ = f.m.pg.Exec(`UPDATE llm_profiles SET is_default=false WHERE id=$1`, fixtureID)
		_ = f.m.pg.DeleteProfile(fixtureID)
	})
	var profileID int64
	var originalAPIKey string'''),
    ]),
])

scope_path = 'agent/blackboard_inheritance_test.go'
scope_original = (root / scope_path).read_text()
scope_start = scope_original.index('\tscopeRows, ok := coverage["scope"]')
scope_end = scope_original.index('\tif hc, _ := coverage["host_count"]', scope_start)
overlay('scope', [
    amend(scope_path, [(scope_original[scope_start:scope_end], '''	scopeRows, err := assets.ListTaskScope(task.ID)
	if err != nil { t.Fatal(err) }
	associated := false
	for _, scope := range scopeRows {
		if scope.CompanyID != nil && *scope.CompanyID == companyID {
			associated = true
		}
	}
	rules, err := companies.GetScope(companyID)
	if err != nil || !associated || len(rules) != len(inputs) {
		t.Fatalf("persisted scope association or rules missing: associated=%t rules=%d err=%v", associated, len(rules), err)
	}
''')]),
])
```

<!-- review-file: engine_probe_test.go -->
```go
package server

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"iter"
	"net/http"
	"net/http/httptest"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Autumn-27/artex/agent"
	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/artex/mcphttp"
	"github.com/Autumn-27/norma/llm"
)

type reviewProvider struct {
	started chan struct{}
	calls   atomic.Int64
	block   bool
}

func (p *reviewProvider) Stream(ctx context.Context, _ llm.CompletionRequest) iter.Seq2[llm.StreamEvent, error] {
	return func(yield func(llm.StreamEvent, error) bool) {
		p.calls.Add(1)
		if p.block {
			select {
			case p.started <- struct{}{}:
			default:
			}
			<-ctx.Done()
			yield(llm.StreamEvent{}, ctx.Err())
			return
		}
		if yield(llm.StreamEvent{Type: llm.SETextDelta, Text: "fixture"}, nil) {
			yield(llm.StreamEvent{Type: llm.SEMessageDelta, StopReason: "end_turn"}, nil)
		}
	}
}

func (p *reviewProvider) Complete(context.Context, llm.CompletionRequest) (llm.Message, string, llm.Usage, error) {
	return llm.Message{}, "", llm.Usage{}, errors.New("unexpected Complete in fixture")
}

func reviewManager(t *testing.T) *Manager {
	t.Helper()
	m, err := NewManager(t.TempDir(), "")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := m.Close(); err != nil {
			t.Error(err)
		}
	})
	return m
}

func reviewTask(t *testing.T, m *Manager, goal string) *Task {
	t.Helper()
	task, err := m.CreateTaskWithOptions("orchestration fixture", goal, db.TaskCreateOptions{WorkerCount: 1})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if _, err := m.DeleteTask(task.ID, DeleteTaskOptions{}); err != nil {
			t.Error(err)
		}
	})
	return task
}

func reviewEngine(t *testing.T, m *Manager, p llm.Provider) (*Engine, context.Context) {
	t.Helper()
	ctx, cancel := context.WithCancel(t.Context())
	t.Cleanup(cancel)
	e := NewEngine(m)
	e.debounce = time.Millisecond
	pl := agent.NewPlanner(p, "fixture", m.dir, nil, 0, 2)
	wk := agent.NewWorker(p, "fixture", m.dir, nil, 0, 2)
	e.SetAuthoritativeAgentResolver(func(*Task) (*agent.Planner, *agent.Worker) { return pl, wk })
	return e, ctx
}

func reviewAddNode(t *testing.T, task *Task, kind, state string) int64 {
	t.Helper()
	id, err := task.Store.AddNode(kind, map[string]any{"summary": "inert fixture", "text": "inert fixture"}, 1, state, "system", nil)
	if err != nil {
		t.Fatal(err)
	}
	return id
}

func reviewWait(t *testing.T, why string, fn func() bool) {
	t.Helper()
	tick := time.NewTicker(time.Millisecond * 10)
	defer tick.Stop()
	timer := time.NewTimer(time.Second * 4)
	defer timer.Stop()
	for !fn() {
		select {
		case <-tick.C:
		case <-timer.C:
			t.Fatal(why)
		}
	}
}

func TestReviewPausedIntentGoalless(t *testing.T) {
	for _, withGoal := range []bool{false, true} {
		t.Run(fmt.Sprint("open_goal=", withGoal), func(t *testing.T) {
			m := reviewManager(t)
			task := reviewTask(t, m, "")
			if withGoal {
				reviewAddNode(t, task, db.KindGoal, "open")
			}
			id := reviewAddNode(t, task, db.KindIntent, "open")
			p := &reviewProvider{started: make(chan struct{}, 8), block: true}
			e, ctx := reviewEngine(t, m, p)
			t.Cleanup(func() { e.StopTask(task.ID) })
			s := &Server{m: m, engine: e, ctx: ctx}
			e.Run(ctx, task)
			select {
			case <-p.started:
			case <-time.After(4 * time.Second):
				t.Fatal("worker failed to start the fake provider")
			}
			active, err := task.Store.HasActiveIntent()
			if err != nil || !active {
				t.Fatalf("running intent should be active: %v %v", active, err)
			}
			if _, err := s.applyIntentControl(ctx, task, id, "pause", "", ""); err != nil {
				t.Fatal(err)
			}
			active, err = task.Store.HasActiveIntent()
			if err != nil || active {
				t.Fatalf("unexpected active predicate after pause: %v %v", active, err)
			}
			task.Notify()
			if withGoal {
				select {
				case <-p.started:
				case <-time.After(4 * time.Second):
					t.Fatal("open goal did not wake planner")
				}
			} else {
				reviewWait(t, "goalless task did not become done", func() bool { return m.TaskStatus(task.ID) == "done" })
			}
			r, err := s.applyIntentControl(ctx, task, id, "resume", "", "")
			if err != nil || r.State != "open" {
				t.Fatalf("resume: %+v %v", r, err)
			}
			if withGoal {
				reviewWait(t, "resumed intent was not reclaimed", func() bool {
					row, err := task.Store.GetNode(id)
					return err == nil && row != nil && row.State == "running"
				})
			} else {
				select {
				case <-p.started:
					t.Fatal("unexpected model invocation after task became done")
				case <-time.After(1100 * time.Millisecond):
				}
				row, err := task.Store.GetNode(id)
				stored, taskErr := m.pg.GetTask(mustReviewID(t, task.ID))
				if err != nil || row == nil || row.State != "open" || taskErr != nil || stored == nil || stored.Status != "done" || p.calls.Load() != 1 {
					t.Fatalf("terminal task did not strand exactly one intent: row=%+v err=%v task=%+v taskErr=%v calls=%d", row, err, stored, taskErr, p.calls.Load())
				}
			}
			t.Logf("with_open_goal=%t task=%s intent_resume=%s actual_model_calls=%d", withGoal, m.TaskStatus(task.ID), r.State, p.calls.Load())
		})
	}
}

func mustReviewID(t *testing.T, id string) int64 {
	t.Helper()
	n, err := strconv.ParseInt(id, 10, 64)
	if err != nil {
		t.Fatal(err)
	}
	return n
}

func TestReviewBootstrapRestart(t *testing.T) {
	m1, err := NewManager(t.TempDir(), "")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = m1.Close() }()
	create := func(goal string) *Task {
		task, err := m1.CreateTaskWithOptions("bootstrap fixture", goal, db.TaskCreateOptions{WorkerCount: 1})
		if err != nil {
			t.Fatal(err)
		}
		return task
	}
	interrupted := create("produce a fixture summary")
	seeded := create("produce a seeded fixture summary")
	reviewAddNode(t, seeded, db.KindGoal, "open")
	createdStatus := interrupted.lifecycleSnapshot().Status
	if err := m1.applyTaskAdmission(interrupted.ID, createdStatus, createdStatus, false, "bootstrap", false, nil); err != nil {
		t.Fatal(err)
	}
	row, err := m1.pg.GetTask(mustReviewID(t, interrupted.ID))
	if err != nil || row == nil || row.Queued || row.Paused || row.QueueMode != "" {
		t.Fatalf("admitted-bootstrap fixture is not unqueued and markerless: row=%+v err=%v", row, err)
	}
	if err := m1.Close(); err != nil {
		t.Fatal(err)
	}
	// Open a fresh manager on the same database, as happens after process exit.
	m2 := reviewManager(t)
	p := &reviewProvider{started: make(chan struct{}, 8), block: true}
	e, ctx := reviewEngine(t, m2, p)
	s := &Server{m: m2, engine: e, ctx: ctx}
	t.Cleanup(func() {
		e.StopTask(interrupted.ID)
		e.StopTask(seeded.ID)
		for _, task := range []*Task{interrupted, seeded} {
			if _, err := m2.DeleteTask(task.ID, DeleteTaskOptions{}); err != nil {
				t.Error(err)
			}
		}
	})
	s.restoreTaskRuntimes()
	reviewWait(t, "restored pending bootstrap did not become done", func() bool { return m2.TaskStatus(interrupted.ID) == "done" })
	select {
	case <-p.started:
	case <-time.After(4 * time.Second):
		t.Fatal("pre-materialized goal did not enter planner")
	}
	local, _ := m2.Task(interrupted.ID)
	goals, err := local.Store.ListByKind(db.KindGoal, 10)
	if err != nil || len(goals) != 0 || local.Goal == "" || isTerminalStatus(m2.TaskStatus(seeded.ID)) {
		t.Fatalf("unexpected bootstrap/control state: goals=%d err=%v seed=%s text=%q", len(goals), err, m2.TaskStatus(seeded.ID), local.Goal)
	}
	t.Logf("interrupted=%s persisted_goal_text=%q materialized_goals=%d seeded_control=%s provider_calls=%d",
		m2.TaskStatus(interrupted.ID), local.Goal, len(goals), m2.TaskStatus(seeded.ID), p.calls.Load())
}

func TestReviewFinalPlannerWait(t *testing.T) {
	m := reviewManager(t)
	task := reviewTask(t, m, "inert final decision")
	if err := m.SetTaskStatus(task.ID, "running"); err != nil {
		t.Fatal(err)
	}
	reviewAddNode(t, task, db.KindGoal, "open")
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	e := NewEngine(m)
	e.deadline.Store(task.ID, time.Now().Add(-time.Minute).Unix())
	resolved := make(chan struct{}, 8)
	e.SetAuthoritativeAgentResolver(func(*Task) (*agent.Planner, *agent.Worker) {
		resolved <- struct{}{}
		return nil, nil
	})
	done := make(chan struct{})
	go func() {
		e.deadlineCoordinator(ctx, task)
		close(done)
	}()
	for range 3 {
		select {
		case <-resolved:
		case <-time.After(3 * time.Second):
			t.Fatal("expected polling of final planner readiness")
		}
	}
	t.Logf("after %s since first readiness check: task=%s settling=%v inflight=%d", 2*deadlinePollInterval, m.TaskStatus(task.ID), e.isSettling(task.ID), e.inflightCount(task.ID))
	if m.TaskStatus(task.ID) != "running" || !e.isSettling(task.ID) || e.inflightCount(task.ID) != 0 {
		t.Fatal("expired task should still be waiting on the observed path")
	}
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("cancellation should release the waiter")
	}
	t.Logf("after cancelling coordinator context: task=%s", m.TaskStatus(task.ID))
	if m.TaskStatus(task.ID) != "timeout" {
		t.Fatal("expected observed post-cancellation terminal write")
	}
}

func TestReviewFinalPlannerReadyAtExpiry(t *testing.T) {
	m := reviewManager(t)
	task := reviewTask(t, m, "inert final decision")
	reviewAddNode(t, task, db.KindGoal, "open")
	p := &reviewProvider{started: make(chan struct{}, 1)}
	e, ctx := reviewEngine(t, m, p)
	e.deadline.Store(task.ID, time.Now().Add(-time.Minute).Unix())
	e.deadlineCoordinator(ctx, task)
	if got := m.TaskStatus(task.ID); got != "timeout" {
		t.Fatalf("eligible final planner did not settle: %s", got)
	}
	t.Logf("ready final planner: task=%s provider_calls=%d", m.TaskStatus(task.ID), p.calls.Load())
}

func TestReviewCoordinatorMarkerLifetime(t *testing.T) {
	m := reviewManager(t)
	task, err := m.CreateTask("coordinator fixture", "", nil, 120, 0)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _, _ = m.DeleteTask(task.ID, DeleteTaskOptions{}) })
	e := NewEngine(m)
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	e.startDeadlineCoordinator(ctx, task)
	if _, ok := e.coordStarted.Load(task.ID); !ok {
		t.Fatal("live coordinator did not publish its marker")
	}
	cancel()
	e.runtimeMu.Lock()
	rt := e.runtimes[task.ID]
	e.runtimeMu.Unlock()
	rt.wg.Wait()
	if _, ok := e.coordStarted.Load(task.ID); ok {
		t.Fatal("coordinator did not clear its marker after cancellation")
	}
	e.startDeadlineCoordinator(ctx, task)
	rt.wg.Wait()
	if _, ok := e.coordStarted.Load(task.ID); ok {
		t.Fatal("pre-cancelled root should leave no live coordinator marker")
	}
	t.Log("live root keeps marker; completed cancelled root removes marker, including on pre-cancelled restart")
}

func TestReviewShutdownIntentState(t *testing.T) {
	for _, shutdown := range []bool{false, true} {
		t.Run(fmt.Sprint("stop_server=", shutdown), func(t *testing.T) {
			m := reviewManager(t)
			task := reviewTask(t, m, "")
			id := reviewAddNode(t, task, db.KindIntent, "open")
			p := &reviewProvider{started: make(chan struct{}, 1), block: true}
			e, base := reviewEngine(t, m, p)
			ctx, cancel := context.WithCancelCause(base)
			defer cancel(nil)
			t.Cleanup(func() { e.StopTask(task.ID) })
			e.Run(ctx, task)
			select {
			case <-p.started:
			case <-time.After(4 * time.Second):
				t.Fatal("local model did not start")
			}
			expected := "open"
			if shutdown {
				cancel(agent.AbortShutdown)
				expected = "blocked"
			} else {
				s := &Server{m: m, engine: e, ctx: ctx}
				if _, err := s.applyTaskControl(task, "pause"); err != nil {
					t.Fatal(err)
				}
			}
			reviewWait(t, "worker did not settle expected state "+expected, func() bool {
				row, err := task.Store.GetNode(id)
				return err == nil && row != nil && row.State == expected
			})
			reset, err := task.Store.ResetRunningIntents()
			if err != nil || reset != 0 {
				t.Fatalf("recovery changed unexpected live rows: reset=%d err=%v", reset, err)
			}
			t.Logf("server_shutdown=%t durable_intent_state=%s rows_reopened_by_startup=%d", shutdown, expected, reset)
		})
	}
}

type reviewCloseProvider struct {
	reviewProvider
	startedCall chan struct{}
	cancelled   chan struct{}
	release     chan struct{}
}

func (p *reviewCloseProvider) Stream(ctx context.Context, _ llm.CompletionRequest) iter.Seq2[llm.StreamEvent, error] {
	return func(yield func(llm.StreamEvent, error) bool) {
		close(p.startedCall)
		<-ctx.Done()
		close(p.cancelled)
		<-p.release
		yield(llm.StreamEvent{}, ctx.Err())
	}
}

func TestReviewServerCloseReturnsBeforeTaskDrain(t *testing.T) {
	m := reviewManager(t)
	task := reviewTask(t, m, "")
	id := reviewAddNode(t, task, db.KindIntent, "open")
	p := &reviewCloseProvider{startedCall: make(chan struct{}), cancelled: make(chan struct{}), release: make(chan struct{})}
	e, base := reviewEngine(t, m, p)
	ctx, cancel := context.WithCancelCause(base)
	defer cancel(nil)
	t.Cleanup(func() { e.StopTask(task.ID) })
	defer close(p.release)
	s := &Server{m: m, engine: e, ctx: ctx}
	s.proxyPoolWG.Add(1)
	go func() { <-ctx.Done(); s.proxyPoolWG.Done() }()
	e.Run(ctx, task)
	select {
	case <-p.startedCall:
	case <-time.After(4 * time.Second):
		t.Fatal("worker did not start")
	}
	cancel(agent.AbortShutdown)
	select {
	case <-p.cancelled:
	case <-time.After(4 * time.Second):
		t.Fatal("worker did not observe shutdown cause")
	}
	closed := make(chan struct{})
	go func() { s.Close(); close(closed) }()
	select {
	case <-closed:
	case <-time.After(time.Second):
		t.Fatal("close waited for worker, contrary to the observed ownership path")
	}
	n, err := task.Store.GetNode(id)
	if err != nil || n == nil || n.State != "running" || e.ActiveLLMCalls(task.ID) != 1 {
		t.Fatalf("expected one unwinding worker after Close: row=%+v err=%v active=%d", n, err, e.ActiveLLMCalls(task.ID))
	}
	t.Logf("server.Close returned with active LLM calls=%d durable state=%s", e.ActiveLLMCalls(task.ID), n.State)
}

type reviewSSEWriter struct {
	headers     http.Header
	writes      chan int64
	replayReady chan struct{}
	release     chan struct{}
	firstFlush  sync.Once
}

func (w *reviewSSEWriter) Header() http.Header { return w.headers }
func (w *reviewSSEWriter) WriteHeader(int)     {}
func (w *reviewSSEWriter) Write(b []byte) (int, error) {
	if before, _, ok := strings.Cut(string(b), "\n"); ok {
		if text, ok := strings.CutPrefix(before, "id: "); ok {
			id, err := strconv.ParseInt(text, 10, 64)
			if err != nil {
				return 0, err
			}
			w.writes <- id
		}
	}
	return len(b), nil
}
func (w *reviewSSEWriter) Flush() {
	w.firstFlush.Do(func() {
		close(w.replayReady)
		<-w.release
	})
}

func TestReviewActivityCursorGap(t *testing.T) {
	for _, later := range []bool{false, true} {
		t.Run(fmt.Sprint("later_live_event=", later), func(t *testing.T) {
			m := reviewManager(t)
			task := reviewTask(t, m, "")
			e := NewEngine(m)
			s := &Server{m: m, engine: e}
			req := httptest.NewRequest(http.MethodGet, "/?task="+task.ID, nil)
			ctx, cancel := context.WithCancel(req.Context())
			defer cancel()
			w := &reviewSSEWriter{
				headers: make(http.Header), writes: make(chan int64, 512),
				replayReady: make(chan struct{}), release: make(chan struct{}),
			}
			var release sync.Once
			defer release.Do(func() { close(w.release) })
			done := make(chan struct{})
			go func() { s.streamActivity(w, req.WithContext(ctx)); close(done) }()
			select {
			case <-w.replayReady:
			case <-time.After(4 * time.Second):
				t.Fatal("SSE did not subscribe and reach its first flush")
			}
			ids := make([]int64, 0, 257)
			for range 257 {
				a := e.emitActivity(task, db.Activity{Kind: "text", Summary: "fixture"})
				if a.ID == 0 {
					t.Fatal("activity audit failed to persist")
				}
				ids = append(ids, a.ID)
			}
			release.Do(func() { close(w.release) })
			for _, want := range ids[:256] {
				select {
				case got := <-w.writes:
					if got != want {
						t.Fatalf("tail ID got %d want %d", got, want)
					}
				case <-time.After(4 * time.Second):
					t.Fatal("SSE failed to drain subscribed buffer")
				}
			}
			cursor := ids[255]
			if later {
				a := e.emitActivity(task, db.Activity{Kind: "text", Summary: "later fixture"})
				select {
				case cursor = <-w.writes:
					if cursor != a.ID || cursor <= ids[256] {
						t.Fatalf("later cursor=%d stored later=%d dropped=%d", cursor, a.ID, ids[256])
					}
				case <-time.After(4 * time.Second):
					t.Fatal("SSE failed to deliver later live event")
				}
			}
			cancel()
			select {
			case <-done:
			case <-time.After(time.Second):
				t.Fatal("SSE did not stop on disconnect")
			}
			caught, _, err := task.Store.ActivityList(nil, cursor, 500)
			history, _, histErr := task.Store.ActivityList(nil, ids[255], 500)
			if err != nil || histErr != nil || len(history) < 1 || history[0].ID != ids[256] {
				t.Fatalf("missing durable row: %+v after cursor %+v errors %v %v", history, caught, err, histErr)
			}
			if (len(caught) == 0) != later {
				t.Fatalf("unexpected reconnect replay: %+v", caught)
			}
			reconnect := httptest.NewRequest(http.MethodGet, "/?task="+task.ID+"&since=1", nil)
			reconnect.Header.Set("Last-Event-ID", strconv.FormatInt(cursor, 10))
			reconnectCtx, stopReconnect := context.WithCancel(reconnect.Context())
			defer stopReconnect()
			replay := &reviewSSEWriter{headers: make(http.Header), writes: make(chan int64, 512), replayReady: make(chan struct{}), release: make(chan struct{})}
			var closeReplay sync.Once
			defer closeReplay.Do(func() { close(replay.release) })
			replayed := make(chan struct{})
			go func() { s.streamActivity(replay, reconnect.WithContext(reconnectCtx)); close(replayed) }()
			select {
			case <-replay.replayReady:
			case <-time.After(4 * time.Second):
				t.Fatal("SSE reconnect did not flush history")
			}
			wantReplay := len(caught)
			if got := len(replay.writes); got != wantReplay {
				t.Fatalf("reconnect wrote %d events want %d", got, wantReplay)
			}
			if wantReplay > 0 {
				if got := <-replay.writes; got != ids[256] {
					t.Fatalf("reconnect recovered cursor %d want %d", got, ids[256])
				}
			}
			stopReconnect()
			closeReplay.Do(func() { close(replay.release) })
			select {
			case <-replayed:
			case <-time.After(time.Second):
				t.Fatal("reconnected SSE handler did not close")
			}
			t.Logf("stored_gap=%d current_cursor=%d recovered_on_reconnect=%d", ids[256], cursor, wantReplay)
		})
	}
}

func TestReviewAtomicClaim(t *testing.T) {
	m := reviewManager(t)
	task := reviewTask(t, m, "")
	id := reviewAddNode(t, task, db.KindIntent, "open")
	type claim struct {
		ok  bool
		err error
	}
	results := make(chan claim, 24)
	begin := make(chan struct{})
	for i := range 24 {
		go func() {
			store := m.pg.Exploration(task.ExpID)
			<-begin
			ok, err := store.ClaimIntent(id, fmt.Sprint("fixture-worker-", i))
			results <- claim{ok, err}
		}()
	}
	close(begin)
	wins := 0
	for range 24 {
		res := <-results
		if res.err != nil {
			t.Fatal(res.err)
		}
		if res.ok {
			wins++
		}
	}
	n, err := task.Store.GetNode(id)
	if err != nil || wins != 1 || n.State != "running" || !strings.HasPrefix(n.Owner, "fixture-worker-") {
		t.Fatalf("atomic claim: wins=%d node=%+v err=%v", wins, n, err)
	}
	other := reviewTask(t, m, "")
	if ok, err := other.Store.ClaimIntent(id, "foreign"); ok || err != nil {
		t.Fatalf("foreign claim ok=%v err=%v", ok, err)
	}
	t.Logf("wins=%d/24 durable_state=%s winner=%s", wins, n.State, n.Owner)
}

func TestReviewTimeoutTriggerOrdering(t *testing.T) {
	m := reviewManager(t)
	oldTask := reviewTask(t, m, "")
	newTask := reviewTask(t, m, "")
	oldID, newID := mustReviewID(t, oldTask.ID), mustReviewID(t, newTask.ID)
	if oldID >= newID {
		t.Fatal("fixture IDs must increase in creation order")
	}
	if err := m.pg.SetSchedState(schedKeyLastTimeout, "0"); err != nil {
		t.Fatal(err)
	}
	s := &Server{m: m}
	sc := newScheduler(s)
	tr := []*db.AgentTrigger{{OnTaskTimeout: true, AgentKey: "fixture", TaskTimeoutMessage: "fixture"}}
	if err := m.SetTaskStatus(newTask.ID, "timeout"); err != nil {
		t.Fatal(err)
	}
	sc.fireTaskTimeouts(tr)
	wm, err := m.pg.GetSchedState(schedKeyLastTimeout)
	if err != nil || wm != newTask.ID {
		t.Fatalf("newer timeout was not observed: watermark=%q err=%v", wm, err)
	}
	if err := m.SetTaskStatus(oldTask.ID, "timeout"); err != nil {
		t.Fatal(err)
	}
	full, err := m.pg.TimedOutTasksSince(0)
	missed, afterErr := m.pg.TimedOutTasksSince(newID)
	if err != nil || afterErr != nil || len(full) != 2 || full[0].TaskID != oldID || full[1].TaskID != newID || len(missed) != 0 {
		t.Fatalf("full=%+v increment=%+v errors=%v %v", full, missed, err, afterErr)
	}
	sc.fireTaskTimeouts(tr)
	after, err := m.pg.GetSchedState(schedKeyLastTimeout)
	if err != nil || after != wm {
		t.Fatalf("cursor changed unexpectedly: %q %v", after, err)
	}
	t.Logf("newer_id=%d timed_out_first, older_id=%d timed_out_second, full=%d incremental=%d final_watermark=%s", newID, oldID, len(full), len(missed), after)
}

func TestReviewOverlappingManagerRestore(t *testing.T) {
	m1 := reviewManager(t)
	task := reviewTask(t, m1, "")
	id := reviewAddNode(t, task, db.KindIntent, "open")
	p1 := &reviewProvider{started: make(chan struct{}, 1), block: true}
	e1, ctx1 := reviewEngine(t, m1, p1)
	t.Cleanup(func() { e1.StopTask(task.ID) })
	e1.Run(ctx1, task)
	select {
	case <-p1.started:
	case <-time.After(4 * time.Second):
		t.Fatal("first worker did not take the intent")
	}
	n, err := task.Store.GetNode(id)
	if err != nil || n == nil || n.State != "running" || e1.ActiveLLMCalls(task.ID) != 1 {
		t.Fatalf("original task not running: row=%+v err=%v active=%d", n, err, e1.ActiveLLMCalls(task.ID))
	}
	m2 := reviewManager(t)
	p2 := &reviewProvider{started: make(chan struct{}, 1), block: true}
	e2, ctx2 := reviewEngine(t, m2, p2)
	t.Cleanup(func() { e2.StopTask(task.ID) })
	s2 := &Server{m: m2, engine: e2, ctx: ctx2}
	s2.restoreTaskRuntimes()
	select {
	case <-p2.started:
	case <-time.After(4 * time.Second):
		t.Fatal("second worker did not reclaim the persisted intent")
	}
	if a, b := e1.ActiveLLMCalls(task.ID), e2.ActiveLLMCalls(task.ID); a != 1 || b != 1 {
		t.Fatalf("expected both owners to be active: %d %d", a, b)
	}
	t.Logf("same PostgreSQL task/intent=%s/%d, simultaneous logical owners=%d+%d", task.ID, id, e1.ActiveLLMCalls(task.ID), e2.ActiveLLMCalls(task.ID))
}

func TestReviewCalendarRestoreBeforeControl(t *testing.T) {
	m1 := reviewManager(t)
	now := time.Now().UTC()
	task := reviewTask(t, m1, "")
	id := reviewAddNode(t, task, db.KindIntent, "open")
	taskID := mustReviewID(t, task.ID)
	item, err := m1.pg.CreateTaskSchedule(db.TaskScheduleInput{
		Name: "closed window fixture", Enabled: true, TimezoneMode: "system", ScheduleType: "once",
		RunDate: now.AddDate(0, 0, -2).Format("2006-01-02"), StartTime: "01:00", EndTime: "02:00", TaskIDs: []int64{taskID},
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = m1.pg.DeleteTaskSchedule(item.ID) })
	if err := m1.pg.TouchTaskSchedule(item.ID, "running", "once:"+item.RunDate, ""); err != nil {
		t.Fatal(err)
	}
	window := evaluateRuntimeScheduleWindow(item, now, now)
	if window.active || !window.complete {
		t.Fatalf("bad control fixture window: %+v", window)
	}
	m2 := reviewManager(t)
	p := &reviewProvider{started: make(chan struct{}, 2), block: true}
	e, ctx := reviewEngine(t, m2, p)
	s := &Server{m: m2, engine: e, ctx: ctx}
	t.Cleanup(func() { e.StopTask(task.ID) })
	s.restoreTaskRuntimes()
	select {
	case <-p.started:
	case <-time.After(3 * time.Second):
		t.Fatal("restore did not start working before calendar tick")
	}
	restored, _ := m2.Task(task.ID)
	if restored.lifecycleSnapshot().Paused {
		t.Fatal("restored task already paused unexpectedly")
	}
	newScheduler(s).fireTaskSchedulesAt(now)
	reviewWait(t, "calendar tick did not park out-of-window work", func() bool {
		n, rowErr := restored.Store.GetNode(id)
		return rowErr == nil && n != nil && restored.lifecycleSnapshot().Paused && n.State == "open"
	})
	t.Logf("closed window=%v model_calls_before_schedule_pause=%d post_tick_intent=open task_paused=%t", !window.active, p.calls.Load(), restored.lifecycleSnapshot().Paused)
}

func TestReviewTerminalWorkerResolverStillTicks(t *testing.T) {
	m := reviewManager(t)
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	e := NewEngine(m)
	e.debounce = time.Millisecond
	var resolverCalls atomic.Int64
	p, w := new(agent.Planner), new(agent.Worker)
	e.SetAuthoritativeAgentResolver(func(*Task) (*agent.Planner, *agent.Worker) {
		resolverCalls.Add(1)
		return p, w
	})
	tasks := make([]*Task, 0, 4)
	for range 4 {
		task := reviewTask(t, m, "")
		tasks = append(tasks, task)
		t.Cleanup(func() { e.StopTask(task.ID) })
		e.Run(ctx, task)
	}
	reviewWait(t, "goalless fixture did not finish", func() bool {
		for _, task := range tasks {
			if m.TaskStatus(task.ID) != "done" {
				return false
			}
		}
		return true
	})
	startCount := resolverCalls.Load()
	reviewWait(t, "terminal worker loops stopped resolving", func() bool { return resolverCalls.Load()-startCount >= int64(2*len(tasks)) })
	t.Logf("four terminal tasks retained worker wakeups, post-terminal resolver calls=%d", resolverCalls.Load()-startCount)
	for _, task := range tasks {
		e.StopTask(task.ID)
	}
	stoppedCount := resolverCalls.Load()
	timer := time.NewTimer(1150 * time.Millisecond)
	defer timer.Stop()
	<-timer.C
	if after := resolverCalls.Load(); after != stoppedCount {
		t.Fatalf("resolver continued after stop: before=%d after=%d", stoppedCount, after)
	}
}

func TestReviewCalendarMetadataOwnership(t *testing.T) {
	m := reviewManager(t)
	sch, err := m.pg.CreateTaskSchedule(db.TaskScheduleInput{
		Name: "scheduled fixture", Enabled: false, ScheduleType: "once", RunDate: "2099-01-01", StartTime: "09:00",
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = m.pg.DeleteTaskSchedule(sch.ID) })
	if err := m.pg.TouchTaskSchedule(sch.ID, "completed", "preserved-key", "preserved-error"); err != nil {
		t.Fatal(err)
	}
	name := "fixture rename"
	renamed, err := m.pg.UpdateTaskScheduleMetadata(sch.ID, db.TaskSchedulePatch{Name: &name})
	if err != nil || renamed == nil || renamed.Name != name || renamed.Status != "completed" || renamed.LastError != "preserved-error" {
		t.Fatalf("rename changed scheduler state: %+v err=%v", renamed, err)
	}
	s := &Server{m: m, engine: NewEngine(m), ctx: t.Context()}
	newScheduler(s).fireTaskSchedulesAt(time.Now())
	ticked, err := m.pg.GetTaskSchedule(sch.ID)
	if err != nil || ticked == nil || ticked.Name != name || ticked.Status != "paused" || ticked.LastError != "" {
		t.Fatalf("calendar tick did not produce expected state: %+v err=%v", ticked, err)
	}
	t.Logf("rename preserved scheduler state %s/%s; scheduler tick applied %s", renamed.Status, renamed.LastError, ticked.Status)
}

func TestReviewRuntimeSegmentRestart(t *testing.T) {
	m := reviewManager(t)
	pending := reviewTask(t, m, "")
	committed := reviewTask(t, m, "")
	pendingID := mustReviewID(t, pending.ID)
	committedID := mustReviewID(t, committed.ID)
	for _, id := range []int64{pendingID, committedID} {
		if _, err := m.pg.Exec(`UPDATE tasks SET active_run_seconds=7,run_segment_started_at=now()-interval '75 seconds' WHERE id=$1`, id); err != nil {
			t.Fatal(err)
		}
	}
	active, _, err := m.pg.FinalizeTaskRunSegment(committedID)
	if err != nil || active < 82 {
		t.Fatalf("positive finalized control got active=%d error=%v", active, err)
	}
	m2 := reviewManager(t)
	p, err := m2.pg.GetTask(pendingID)
	c, err2 := m2.pg.GetTask(committedID)
	if err != nil || err2 != nil || p == nil || c == nil || p.RunSegmentStartedAt != nil || c.RunSegmentStartedAt != nil || p.ActiveRunSeconds != 7 || c.ActiveRunSeconds != active {
		t.Fatalf("bad accounting comparison pending=%+v committed=%+v errors=%v %v", p, c, err, err2)
	}
	t.Logf("after restart unfinalized active_seconds=%d, finalized active_seconds=%d; both segment starts cleared", p.ActiveRunSeconds, c.ActiveRunSeconds)
}

func TestReviewNoResultOnCreatedWithActiveSegment(t *testing.T) {
	m := reviewManager(t)
	task, err := m.CreateTaskWithOptions("inert fixture", "summary", db.TaskCreateOptions{
		NoResultSeconds: 60, NoResultMinFindings: 1,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _, _ = m.DeleteTask(task.ID, DeleteTaskOptions{}) })
	id := mustReviewID(t, task.ID)
	state := task.lifecycleSnapshot()
	if state.Status != "created" {
		t.Fatalf("expected real creation status, got %q", state.Status)
	}
	if err := m.applyTaskAdmission(task.ID, state.Status, state.Status, false, "bootstrap", false, nil); err != nil {
		t.Fatal(err)
	}
	if err := m.StartTaskRunSegment(task.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := m.pg.Exec(`UPDATE tasks SET run_segment_started_at=now()-interval '75 seconds' WHERE id=$1 AND run_segment_started_at IS NOT NULL`, id); err != nil {
		t.Fatal(err)
	}
	if err := m.syncTaskRuntime(task.ID, id); err != nil {
		t.Fatal(err)
	}
	state = task.lifecycleSnapshot()
	if time.Now().Unix()-state.RunSegmentStartedAt < 60 || state.RunSegmentStartedAt == 0 || state.ActiveRunSeconds != 0 {
		t.Fatalf("fixture failed to persist a live segment past its active limit: %+v", state)
	}
	e := NewEngine(m)
	stop, err := e.checkNoResultCheckpoint(task)
	stored, loadErr := m.pg.GetTask(id)
	if err != nil || loadErr != nil || stored == nil || stop || stored.NoResultCheckedAt != nil || stored.Status != "created" {
		t.Fatalf("unexpected checkpoint with created status: stop=%t err=%v row=%+v loadErr=%v", stop, err, stored, loadErr)
	}
	remaining := noResultRemaining(60, state, time.Now().Unix())
	if remaining != time.Minute {
		t.Fatalf("created live segment counted unexpectedly: remaining=%s", remaining)
	}
	if err := m.SetTaskStatus(task.ID, "running"); err != nil {
		t.Fatal(err)
	}
	stop, err = e.checkNoResultCheckpoint(task)
	corrected, loadErr := m.pg.GetTask(id)
	if err != nil || loadErr != nil || corrected == nil || corrected.RunSegmentStartedAt == nil || !corrected.RunSegmentStartedAt.Equal(*stored.RunSegmentStartedAt) || !stop || corrected.NoResultCheckedAt == nil || corrected.StopReason != db.StopReasonNoResult {
		t.Fatalf("running-state control did not claim same segment: stop=%t err=%v row=%+v loadErr=%v", stop, err, corrected, loadErr)
	}
	t.Logf("same 75s segment with 60s budget: created had remaining=%s without marker, running immediately committed stop_reason=%q", remaining, corrected.StopReason)
}

func TestReviewPythonDeadline(t *testing.T) {
	interp, err := exec.LookPath("python3")
	if err != nil {
		t.Fatal(err)
	}
	for _, child := range []bool{false, true} {
		t.Run(fmt.Sprint("inherited_output=", child), func(t *testing.T) {
			code := "import time\nprint('parent-ready', flush=True)\ntime.sleep(10)\n"
			if child {
				code = "import subprocess, sys, time\nsubprocess.Popen([sys.executable, '-c', 'import time; time.sleep(0.55); print(\"child-late\", flush=True)'])\nprint('parent-ready', flush=True)\ntime.sleep(10)\n"
			}
			start := time.Now()
			body, err := execPython(t.Context(), interp, "fixture", code, nil, t.TempDir(), nil, 300*time.Millisecond)
			elapsed := time.Since(start)
			if err != nil || !strings.Contains(body, "parent-ready") || !strings.Contains(body, "超时终止") {
				t.Fatalf("timeout fixture did not reach its normal output: %q %v", body, err)
			}
			if child && (elapsed < 530*time.Millisecond || !strings.Contains(body, "child-late")) {
				t.Fatalf("child did not outlive deadline: %v %q", elapsed, body)
			}
			if !child && elapsed >= 520*time.Millisecond {
				t.Fatalf("solo-process deadline baseline was unexpectedly slow: %v", elapsed)
			}
			t.Logf("child=%t configured_deadline=300ms actual=%s child_late=%t returns_nil_error=%t", child, elapsed.Round(time.Millisecond), strings.Contains(body, "child-late"), err == nil)
		})
	}
}

func TestReviewMCPStartupCancellation(t *testing.T) {
	for _, legacy := range []bool{false, true} {
		t.Run(fmt.Sprint("legacy_sse=", legacy), func(t *testing.T) {
			reqSeen := make(chan struct{})
			release := make(chan struct{})
			var closeRelease sync.Once
			fixture := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "text/event-stream")
				w.WriteHeader(http.StatusOK)
				w.(http.Flusher).Flush()
				close(reqSeen)
				select {
				case <-release:
				case <-r.Context().Done():
				}
			}))
			defer fixture.Close()
			defer closeRelease.Do(func() { close(release) })
			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()
			done := make(chan error, 1)
			go func() {
				var client *mcphttp.Client
				var err error
				if legacy {
					client, err = mcphttp.NewSSE(ctx, "fixture", fixture.URL, nil, false)
				} else {
					client, err = mcphttp.New(ctx, "fixture", fixture.URL, nil, false)
				}
				if client != nil {
					_ = client.Close()
				}
				done <- err
			}()
			select {
			case <-reqSeen:
			case <-time.After(4 * time.Second):
				t.Fatal("loopback fixture did not accept the request")
			}
			cancel()
			select {
			case err := <-done:
				if legacy || !errors.Is(err, context.Canceled) {
					t.Fatalf("unexpected startup return after caller cancellation: %v", err)
				}
				t.Logf("streamable HTTP unwound with caller cancellation")
			case <-time.After(200 * time.Millisecond):
				if !legacy {
					t.Fatal("streamable HTTP did not cancel")
				}
				closeRelease.Do(func() { close(release) })
				select {
				case err := <-done:
					if err == nil {
						t.Fatal("expected error after closing server without endpoint frame")
					}
					t.Logf("legacy SSE blocked 200ms after cancellation, returned only after endpoint stream closed: %v", err)
				case <-time.After(time.Second):
					t.Fatal("legacy SSE failed to exit after fixture shutdown")
				}
			}
		})
	}
}

func TestReviewArchiveFormatFixture(t *testing.T) {
	m := reviewManager(t)
	task := reviewTask(t, m, "")
	if err := m.pg.SetPaused(mustReviewID(t, task.ID), true); err != nil {
		t.Fatal(err)
	}
	snap, err := m.pg.SnapshotTaskArchive(mustReviewID(t, task.ID))
	if err != nil {
		t.Fatal(err)
	}
	encoded, err := json.Marshal(snap)
	if err != nil || len(encoded) == 0 || snap.FormatVersion != db.TaskArchiveFormatVersion {
		t.Fatalf("snapshot format=%d current=%d err=%v", snap.FormatVersion, db.TaskArchiveFormatVersion, err)
	}
	t.Logf("writer format=%d current=%d accepts v1=%t v2=%t v3=%t v4=%t",
		snap.FormatVersion, db.TaskArchiveFormatVersion, db.IsTaskArchiveFormatSupported(1), db.IsTaskArchiveFormatSupported(2), db.IsTaskArchiveFormatSupported(3), db.IsTaskArchiveFormatSupported(4))
}

func TestReviewArchiveQueuePauseControl(t *testing.T) {
	m := reviewManager(t)
	task := reviewTask(t, m, "")
	id := mustReviewID(t, task.ID)
	t.Cleanup(func() { _, _ = m.pg.Exec(`DELETE FROM task_archives WHERE task_id=$1`, id) })
	if err := m.SetConcurrency(true, 1); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	s := &Server{m: m, engine: NewEngine(m), ctx: ctx}
	s.reconcileConcurrency()
	if !task.lifecycleSnapshot().Queued {
		t.Fatal("capacity reconciliation did not park unavailable task")
	}
	if err := m.pg.SetPaused(id, true); err != nil {
		t.Fatal(err)
	}
	if _, err := m.pg.QueueTaskArchive(id); !errors.Is(err, db.ErrTaskArchiveQueued) {
		t.Fatalf("raw paused flag failed to preserve the queued rejection: %v", err)
	}
	if err := m.pg.SetPaused(id, false); err != nil {
		t.Fatal(err)
	}
	if err := m.ApplyTaskPause(task.ID); err != nil {
		t.Fatal(err)
	}
	job, err := m.pg.QueueTaskArchive(id)
	if err != nil || job == nil {
		t.Fatalf("normal pause and dequeue failed to allow archive: %+v %v", job, err)
	}
	t.Log("canceled-root reconciliation queued the row; raw pause kept queued; lifecycle pause cleared queued and archive succeeded")
}
```

<!-- review-file: agent_probe_test.go -->
```go
package agent

import (
	"fmt"
	"sort"
	"testing"
	"time"

	"github.com/Autumn-27/artex/db"
)

func TestReviewOverviewGraphWork(t *testing.T) {
	dsn, _, err := db.DSN()
	if err != nil {
		t.Fatal(err)
	}
	d, err := db.Open(dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	for _, add := range []int{100, 1000, 10000} {
		t.Run(fmt.Sprint(add), func(t *testing.T) {
			task, err := d.CreateTask("inert graph fixture", "summarize test records", nil, 0, 0)
			if err != nil {
				t.Fatal(err)
			}
			defer d.DeleteTask(task.ID)
			s := d.Exploration(task.ExplorationID)
			_, err = d.Exec(`INSERT INTO exploration_nodes(exploration_id,kind,payload,state) SELECT $1,'fact',jsonb_build_object('summary',format('fixture %s',j)),'confirmed' FROM generate_series(1,$2) j`, task.ExplorationID, add)
			if err != nil {
				t.Fatal(err)
			}
			g, nodes, err := loadColdGraph(s)
			if err != nil || len(g.nodes) != add+1 || len(nodes) != add+1 {
				t.Fatalf("loaded graph with %d nodes, error=%v", len(nodes), err)
			}
			ts := NewToolSet(s, "review-fixture")
			var samples []time.Duration
			for range 5 {
				start := time.Now()
				out := ts.graphOverviewData()
				samples = append(samples, time.Since(start))
				if out["facts"] != min(1000, add+1) || len(out["recent_facts"].([]map[string]any)) != 20 {
					t.Fatalf("unanticipated projection counts %v", out["facts"])
				}
			}
			sort.Slice(samples, func(i, j int) bool { return samples[i] < samples[j] })
			t.Logf("rows=%d fact_count=%d serialized_recent=%d median_overview_ms=%.2f", len(nodes), min(1000, add+1), 20, float64(samples[2])/float64(time.Millisecond))
		})
	}
}
```

</details>

### Final checkout integrity

`2026-11-19T06:29:24Z` UTC with the fixture processes stopped. The final checkout check returned `6997a4661921395072290becc50380db8dacb04e`, an empty porcelain status including ignored and untracked paths, and zero from both index and worktree `git diff --quiet`. The review changed only this report outside isolated scratch.
