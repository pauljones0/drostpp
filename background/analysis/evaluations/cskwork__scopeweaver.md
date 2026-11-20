# ScopeWeaver non-UI runtime review

## 1. Snapshot, scope, and elapsed-time evidence

| Item | Evidence |
|---|---|
| Checkout | `repos/cskwork__scopeweaver` |
| Commit | `1f33072cbb09280ffafdec189d64e7ed8e95099a`, local `main`, merge subject `Merge pull request #115 from cskwork/dev` |
| Fresh start | `2026-11-19 06:16:23 UTC`, clock sample immediately before reading all of `evaluations/README.md` |
| Initial integrity | `2026-11-19 06:16:27 UTC`, exact `rev-parse --verify HEAD` and empty `status --porcelain=v1 --untracked-files=all` |
| Work interval | `2026-11-19 06:16:23 UTC` to `2026-11-19 06:46:28 UTC`, **30 min 05 s** across fresh review work. Earlier attempts were excluded. |
| Final integrity | `2026-11-19 06:46:28 UTC`, `rev-parse --verify HEAD` returned `1f33072cbb09280ffafdec189d64e7ed8e95099a`. `status --porcelain=v1 --untracked-files=all` was empty and `git diff --check HEAD` exited 0. Temporary review directories were removed. |
| Runtime | Linux amd64. Primary `go1.27.1` and cached comparison `go1.26.10`. Both module manifests declare `go 1.26.3`. |
| Scope | Standalone Go backend, task/intent and chat execution, task provider routing, embedded SDK, storage, ownership, cleanup, delivery and runtime extension boundaries |

The protocol enumerates nine topics. This report uses ten numbered sections by giving the protocol's combined strengths and weaknesses topic two sections. References are relative to the checkout at the pinned HEAD. Review evidence comes from fresh source tracing, unchanged tests and temporary local controls. The checkout was mounted read-only in the test namespace. The controls exercised generic task and conversation behavior using synthetic requests, an in-process SQL driver, and a locally held no-op tool. They used no accounts, real credentials, external services or remote systems. Browser and frontend evaluation, real providers, hosted CI, and multi-instance production deployment were outside this investigation.

The review followed these UTC work checkpoints. Wall-clock samples bracket source work, fixture development, experiments, report drafting and verification. Test intervals ran alongside source and report work.

| UTC | Work checkpoint |
|---|---|
| 06:16:23–06:20:12 | Read protocol and checked HEAD, traced startup and task ownership, ran first unchanged packages, and separated dispatch projection and stream-order fixture behavior. |
| 06:20:12–06:24:49 | Traced task and intent lifecycle, reproduced shutdown and callback ownership, corrected terminal-write fixture arguments, examined bootstrap/restart and provider health. |
| 06:24:49–06:29:30 | Traced chat, SDK budgets and transcript storage, checked malformed-history and worker-duration controls, and exercised paused manual work and timeout discovery. |
| 06:29:30–06:33:46 | Counted real loopback requests and local callback retries, audited the initial short fixture timeout, checked SQL predicates independently, and compared Go toolchains. |
| 06:33:46–06:37:55 | Completed broad root/nested suites, reviewed release-time state and delivery semantics, and drafted the ten sections and runnable appendix. |
| 06:37:55–06:41:48 | Executed the appendix, checked citations, added process-exit file staging and bootstrap context controls, and reproduced the counter without race instrumentation. |
| 06:41:48–completion | Recomputed counts, rechecked terminal SQL ordering, ran the final evidence runner and attempted the explicit receipt guard selection, then validated the final report and checkout. |

## 2. Core architecture and end-to-end control/data flow

### Process composition and storage

`cmd/artex/main.go:53–152` is the composition root. It establishes signal handling with a named cancellation cause, opens the Manager, constructs the Server and starts HTTP. The Manager owns PostgreSQL, the process task registry and optional local traffic state. `db.Open` sets a bounded connection pool and applies embedded, idempotent schema SQL and built-in seeds under a session-level advisory lock on one pinned connection. The Server owns execution, chat admission, task/provider caches, broadcaster and descendant shutdown. Server startup recovers chat state before starting request producers, resolves provider configuration, restores task runtimes and eligible chat queues, and starts the reconciliation, archive, notification and scheduler loops. See `cmd/artex/main.go:93–131,155–185`, `server/manager.go:379–415,421–485`, `db/db.go:57–75,94–165` and `server/server.go:165–292`.

| State | Authority and consumption |
|---|---|
| Task registry | PostgreSQL `tasks` owns the exploration link, task status, pause, queue position and mode, clock, and profile cursor. Manager hydrates a synchronized process copy for scheduling. `db/schema.sql:514–562`, `server/manager.go:78–148,886–905,1142–1175`. |
| Task work and output | One exploration per task. Typed nodes carry JSONB payloads and kind-specific state, including goals, intents, facts, findings and derived digests. Edges encode relationships and anchors refer to the separate shared asset catalog. A source task contributes a bounded read view and has its own claimable frontier. `db/schema.sql:173–194,245–273,514–523`, `db/exploration.go:202–230,264–293,1187–1232`, `agent/tools.go:560–568,615–628`. |
| Conversation context | JSONL records preserve model turns. A stable exploration/intent ID selects worker history. Main and standalone chat additionally keep gate, turn, run and history revisions in PostgreSQL, with a file/manifest publication protocol for edited histories. `agent/worker.go:95–116,477–479,502–529`, `db/chat_controls.go:68–85,374–465`, `chatstate/transcripts.go:24–35,45–144`. |
| Files and optional indexed traffic | Work and spill paths separate task output from worker output. Optional traffic uses a local SQLite index in WAL mode plus local data files, with dedicated staged cleanup. These resources follow the PostgreSQL task decision through compensation or recovery. `agent/worker.go:265–281,465–479`, `traffic/traffic.go:177–219,258–266,1478–1486`, `server/manager.go:1515–1581`. |
| Live ownership | Contexts and WaitGroups track task goroutines, per-intent operations, chat runs, callbacks and background work. Planner wakeups, steering queues, in-flight counters and subscriptions are process memory. `server/engine.go:94–168,228–248,401–427`, `server/background.go:19–44`, `server/manager.go:1829–1941`. |

### Task creation, admission and planning

1. The HTTP task handler validates input and creates the task. The DB transaction creates the exploration, its origin fact, the task, and associated source, company and profile bindings. The task is visible before the post-creation phase. The same launch path handles programmatically created tasks. `server/server.go:1596–1668`, `db/tasks.go:162–260`, `server/goals.go:21–40`.
2. `admitTaskWhen` serializes task-level admission under `concMu`. It validates the live handle, samples readiness and capacity, honors earlier ready work, and installs a temporary execution pause before a queued or revived transition can race workers. A single conditional SQL update persists pause, queue timestamp, mode, status and, for timeout revival, clock reset. Reconciliation orders entries by persisted enqueue time and ID and skips unavailable or paused tasks. Already-admitted work keeps its slot when the cap is reduced. `server/goals.go:73–219,261–354`, `server/manager.go:1199–1286`.
3. Bootstrap uses an admitted goroutine. It prepares the provider if necessary, records a round-zero marker, then materializes goals using the same task routing layer that drives subsequent calls. The raw objective is the fallback when decomposition produces no goals. Resuming an existing task goes directly to Engine activation. `server/goals.go:43–70,232–258,372–417`.
4. `Engine.Run` registers one planner and the configured number of workers. It starts a deadline coordinator when applicable. A capacity-one wake channel coalesces edges while a separate list retains trigger details. Planning uses an 800 ms debounce and a minimum 600 s heartbeat as a fallback. Seeded open or running work suppresses the initial planner nudge. During normal rounds the planner resolves its role, checks pause/deletion/terminal/settlement state, consumes trigger details, and reconstructs its input from the graph, shared planning notes, and bounded evidence reads. A task with no open goals takes the manual-work branch, which uses frontier exhaustion for completion. `server/engine.go:395–399,751–925`, `server/manager.go:1829–1941`, `agent/planner.go:335–385,411–460`, `agent/planner_evidence.go:14–96`.
5. Every planner round creates a fresh SDK session. Its transcript accumulates trace history under a stable identity. The next round is derived from the graph and the Planner object's in-memory todo store. A goal-state transition and proof edge can commit together. The host only short-circuits a subsequent inference after an authentic successful receipt tied to the originating response. `agent/planner.go:111–121,414–459`, `db/exploration.go:272–294`, `agent/terminal_proof.go:15–48,76–143`.

The context managers handle different units. Graph digests are derived records over cold portions of the task graph. They keep causal nodes and allow a member to reappear when it becomes hot. Conversation compaction retains raw history and reduces the prompt working set. The local small-window policy uses a provider-aware threshold and keeps paired tool-use/result context. The optional Noa layer retains the resolved profile window and its own session archive. The background graph summarizer inherits a bounded server-owned lifetime, which is separate from a normal planner wake. `agent/compaction.go:73–125,131–166,288–323`, `agent/coldgraph.go:81–104`, `agent/tools.go:446–460,551–559`, `agent/local_runtime.go:20–36,49–102`, `agent/noa.go:24–63`.

### Dispatch, workers and settlement

The frontier is local open intents, sorted by priority descending and ID ascending. Idle workers poll and try up to 20 candidates. Each claim is a single conditional update of the exploration, intent, and open-state tuple. A copied, stale frontier can increase contention. The state guard allows one winner for a given open-to-running transition. The winner executes under the task execution context and a per-intent child context. The same execution/settlement logic handles a human continuation, which instead claims a paused intent by CAS and runs outside the configured pool. `server/engine.go:927–1037,1170–1255`, `db/exploration.go:1187–1232`, `server/intent_intervention.go:79–146`.

The worker builds the current mandate into a system segment, assembles the effective capability registry, uses a per-intent working directory, and resumes the stable JSONL conversation. Task hooks, usage capture and the provider share this run context. SDK stop metadata and errors are translated to intent state by the engine. A worker session and any attached clients close via deferred cleanup. Independent global callback ownership accounts for callbacks that are still unwinding when the session returns. See `agent/worker.go:265–281,356–396,424–480,496–539`, `agent/session_ownership.go:14–61` and `server/engine.go:1038–1167`.

| Trigger or outcome | Intended state effect |
|---|---|
| User pauses task | Persist task pause and cancel its shared execution context. Recognized in-flight task-pause causes return an owned intent from `running` to `open`. A resume makes the next execution context fresh and goes through task admission. `server/task_control.go:97–145`, `server/engine.go:178–183,309–345,1102–1109,1225–1236`. |
| User pauses/cancels one intent | Reserve a controller, cancel its execution, and join the worker's final state write. Pause sets `paused`. Cancel parks at `paused` before API cleanup. An interrupted HTTP waiter releases its reservation while the named cancel cause survives. `server/engine.go:409–483,1063–1101`, `server/task_control.go:182–250`. |
| Worker completes, errors, or reaches budget | Normal completion becomes `done`. Error becomes `blocked` unless a cause-specific branch intervenes. Max turns or timeout become `exhausted`. Planner stop or task completion can mark `stopped`. A quota-specific blocked reason enables targeted reopening after profile repair. `server/engine.go:1111–1167`, `db/task_context.go:562–578`. |
| User reruns failed/stopped work | Reopen eligible intent state, preserve earlier output, then admit or revive the task. If admission fails, try to restore the captured intent state. Worker history supplies continuity when readable. `server/server.go:1253–1349`, `db/exploration.go:352–378`, `db/intent_admission.go:8–29`, `agent/worker.go:505–529`. |
| Task clock expires | Stop ordinary planner rounds and worker claims, drain operations for up to 90 s before a hard cancellation backstop, then run a final planner assessment and try a guarded terminal write. Absolute stored time keeps running across pauses and restarts. `db/tasks.go:515–530`, `server/engine_timeout.go:129–268`. |
| Process restarts | Reload live task rows, restore pause, return persisted `running` intents to `open`, start timed coordinators, and launch every admitted nonterminal task. Queued tasks remain with reconciliation. Worker retry/restart is conversation replay with best-effort history. `server/server.go:295–333`, `db/exploration.go:337–350`, `agent/worker.go:502–529`. |

### Independent chat domain and shutdown

Task main-agent and standalone conversation turns use a durable admission gate. The key spans a task's main segments. The active transcript and history revision belong to the session. Admission fingerprints a client request and stores an ordered input. A short transaction claims one input, records its run, makes that run active on the gate and releases the DB locks before inference. The server registers an in-memory cancel handle before returning. Finalization writes run, input and history statuses and releases the gate. Failure pauses the gate. Startup finishes interrupted runs as `unknown` and blocks automatic replay until resolution. This policy is stronger than the task-worker crash policy where a stored `running` intent reopens. See `chatstate/types.go:12–75`, `db/chat_controls.go:124–205,400–505,514–532,564–594` and `server/chat_dispatch.go:21–56,72–165`.

History mutations use expected revisions, a separate preparation identity and a durable publication point. Normal chat turns append to the active revision. Prepared edits write a new JSONL file and a manifest with digest, byte length and final record identity, then publish a DB pointer. Startup cleanup checks ownership before removing unpublished candidates. An unknown run can be discarded using a validated stored prefix through the recorded baseline. Side questions capture bounded parent-session snapshots and own separate request lifetimes. See `chatstate/transcripts.go:45–215,264–328`, `db/chat_history.go:16–57,218–337`, `server/chat_transcript_cleanup.go:17–65`, `server/chat_recovery.go:10–77` and `server/side_questions.go:57–124,146–190,459–546`.

Task delete installs an execution barrier before draining task operations, main chat and side questions. It stages selected task files and optional local traffic, commits the SQL cascade, then finalizes staged cleanup. Failure before commit compensates file moves. Failure after commit returns a typed cleanup warning while runtime teardown still completes. The archive worker uses a separate durable job record, package staging and crash recovery. Process shutdown closes HTTP and descendant admission, joins tracked owners, and flushes final chat snapshots. The Manager separately owns the scheduler and log writer during store close. See `server/server_mgmt.go:97–107,141–228`, `server/manager.go:846–864,1500–1586,1647–1752`, `server/task_archives.go:39–116,123–252` and `server/chat_shutdown.go:14–82`.

### Inference, capability and event interfaces

Task role selection resolves a valid role binding, then the explicit task chain, then global configuration when there is no chain. An exhausted explicit chain has no implicit global escape. The stable task bundle uses fresh role resolution for each inference. A revision-qualified SQL transaction advances an exhausted chain. The per-profile cache shares rate and in-flight controls across users of a profile. Native local-model admission has one gate per normalized endpoint, with explicit FIFO lanes. The optional global pool has a distinct pre-output failover rule and process-wide circuit health. `server/task_llm.go:100–148,209–244,533–619`, `db/task_context.go:468–544`, `server/server.go:483–516,620–659`, `server/ollama.go:164–305` and `llmpool/pool.go:75–140`.

| Concurrency domain | Governing resource |
|---|---|
| Task admission | Optional limit on admitted runnable task handles, default five when enabled. Existing work survives a cap reduction. `server/manager.go:297–315`, `server/goals.go:73–99,149–179`. |
| Intent workers | Worker goroutines sampled per task at Engine start, default three. A directed human continuation can use its independently admitted goroutine. `server/manager.go:295–296,330–348`, `server/engine.go:754–777,1170–1222`. |
| Inference | A profile's shared rate limiter controls cadence. Its semaphore bounds outstanding calls until the stream iterator exits. Native admission shares a normalized endpoint gate and prioritizes interactive roles. `agent/provider.go:321–351,379–386`, `server/llm_concurrency.go:38–79`, `server/ollama.go:164–305`. |
| Tools per session | The SDK defaults to ten executor slots and recognizes per-tool concurrency safety. Incompatible calls wait for earlier execution. This addresses overlap within a session. `third_party/norma/harness/query.go:199–210`, `third_party/norma/harness/streaming.go:55–115`. |
| Conversations and maintenance | One durably active chat run per gate, per-agent trigger concurrency and merge policies, one archive worker claiming persistent jobs, and separate notification leases. `db/chat_controls.go:400–465`, `server/conversations.go:570–666`, `db/task_archives.go:369–395`, `db/notification_delivery.go:212–245`. |

The Go provider and tool interfaces are narrow enough to test with no external infrastructure. `llm.Provider` supports a normalized streaming iterator and a complete response. `CoreTool` describes schema, permissions, concurrency and execution. The host resolves tools and editable prompt metadata by role, augments capabilities with visible skills/MCP, and wires cleanup and metering. The harness limits safe parallel calls and serializes incompatible calls. Its parent/tool contexts carry different cancellation semantics. The vendored Norma patch preserves the original context for asynchronous tool work while settlement uses a live parent. See `third_party/norma/llm/provider.go:153–163`, `third_party/norma/tool/tool.go:84–106`, `agent/assembly.go:37–89`, `server/assembly.go:26–179,213–337`, `third_party/norma/harness/streaming.go:44–115` and `third_party/norma/README.scopeweaver.md:9–26,34–41`.

Task wakeups, activity SSE, scheduled triggers and notification deliveries have different contracts. Planner wakes are coalesced in memory over persisted graph state. The activity capture path coalesces text, preserves tool IDs, emits usage and terminal records, persists each activity and then publishes to bounded in-memory channels. The SSE handler subscribes before SQL replay and advances an ID cursor. The scheduler polls task/graph changes and maintains persisted watermarks while its intermediate trigger queue is in memory. Notification delivery has a separate durable event and lease/attempt model. `agent/capture.go:38–172`, `server/engine.go:644–702`, `server/broadcast.go:22–62`, `server/server.go:3122–3217`, `server/scheduler.go:88–108,182–249,289–317`, `server/conversations.go:570–630` and `db/notification_delivery.go:125–168,212–245,283–345`.

Planner wake details are consumed before the model call. Earlier returns for pause or unreadiness leave pending details in memory. A failed call after the drain can lose the cue, and a later heartbeat redraws the current graph without the same causal annotation. That contract suits best-effort prioritization. Any operation that requires confirmed delivery needs durable state beyond the wake queue. `server/manager.go:1829–1858,1934–1941`, `server/engine.go:831–856,881–924`.

## 3. Why the design works and its governing invariants

| Invariant | Enforcement and boundary |
|---|---|
| A worker owns a successful claim of a local open intent | Conditional `UPDATE` checks exploration, kind and expected state. The detached path wins a separate `paused → running` CAS. State-specific settlement prevents straightforward stale overwrites. Runtime ownership is process-local, with no persisted lease or attempt generation in the claim. `db/exploration.go:390–402,1224–1232`, `server/engine.go:1182–1222`. |
| Admission publishes one consistent lifecycle update | `concMu` protects scheduling decisions, `taskStateMu` serializes Manager writers, and task snapshots copy mutable context. A row status predicate catches concurrent terminal transitions. FIFO falls back deterministically for legacy timestamps. Claims, app startup and bootstrap have additional invariants that the one row update cannot enforce. `server/goals.go:115–219,289–353`, `server/manager.go:78–148,1207–1286`. |
| Stop and delete are distinct from normal completion | Named causes let the engine classify an interruption after a quick eventual resume. Engine admission serializes with deletion, and long-lived loops join before their runtime entry is removed. Chat and SDK callbacks have separate owners and lifetimes. `agent/cancelcause.go:13–75`, `server/engine.go:189–203,228–345,1063–1167`, `server/engine_timeout.go:48–64`, `server/background.go:19–29`. |
| A planner's stopping decision has an auditable boundary | Durable graph proof is independent from the SDK's successful-exchange check. The gate qualifies receipt, originating model call and cancellation before short-circuiting the next request and its compaction prelude. This preserves usage, tool-result pairing and normal settlement behavior. `db/exploration.go:272–293`, `agent/terminal_proof.go:15–48,102–143,188–245`, `agent/capture.go:94–100`. |
| Retry safety is scoped to a layer and an output boundary | A task router may retry the same request before meaningful stream output. The optional pool allows failover before any event. Once committed, a quota error may change the next-call cursor without reissuing the current call. Intent-level replay uses a separate retry policy and conversation history. External effects require their own idempotency. `server/task_llm.go:246–406,425–462`, `llmpool/pool.go:75–120`, `server/engine.go:80–85,1038–1057`. |
| Conversation ownership is durable at one gate | Row locks serialize admission and history mutations, fingerprints key repeats, and a claimed input points at exactly one active run. An ambiguous interruption becomes an explicit barrier. A new history pointer refers to a prepared file revision rather than a file edited in place. `db/chat_controls.go:68–85,135–205,400–505,521–529,564–594`, `chatstate/transcripts.go:45–144`, `db/chat_context_change.go:82–151`. |
| Graph, model context and activity have different lifetimes | The graph is the shared, durable state that survives fresh planner sessions and can be read by a source-linked task. Worker transcripts and compacted prompt views provide continuity. Live delivery and pending cues can be rebuilt only to the extent the underlying authoritative records and replay scheme support it. `agent/planner.go:111–121,359–374,414–460`, `agent/worker.go:477–529`, `agent/tools.go:451–568`, `server/server.go:3155–3216`. |

The execution model is coherent for one backend owner. The restart assumption is visible in startup's unqualified reset of all loaded running intents and in the chat cleanup comment specifying single-owner startup. A PostgreSQL migration lock and per-row claim guard protect individual transactions. A second server's startup would need separate coordination for restoring live attempts, recovering chat runs and claiming addressable filesystem resources. No multi-server claim is supported by this review. `db/db.go:57–75,148–160`, `server/server.go:297–316`, `db/exploration.go:337–350`, `server/chat_transcript_cleanup.go:30–33`.

## 4. Strengths

- **The blackboard is a real work boundary.** Explicit claim CAS, scoped node state and provenance make task scheduling understandable independently of model prose. Workers can start from a prepared frontier. A fresh planner can make sense of durable outputs after any conversation has expired. A transaction covers each inserted node and its anchors, and a separate idempotent link API makes relationship creation straightforward. `db/exploration.go:202–230,263–294,390–402,1187–1232`, `server/engine.go:779–787`.
- **The controls distinguish intent pause, task pause and process drain.** A quick resume cannot retroactively change the cause that an old execution observed. The direct per-intent controller reserves ownership and requires definitive settlement acknowledgement. Compensation on failed task admission and committed-delete errors respects which side of the authority boundary completed. The existing cause tests and live callback control exercised distinct cancellation paths. `server/engine.go:409–483,1063–1109`, `server/engine_cancelcause_test.go:41–124,143–202`, `server/goals.go:184–203`, `server/server_mgmt.go:181–206`.
- **Inference routing makes ambiguous output explicit.** The explicit task-chain cursor is revision-guarded. Safe-window retries preserve the current stream once committed. The terminal proof gate avoids cutting across unfinished tool work or usage emission. Current task-level configuration and the provider cache let a running task observe changes at documented call or session boundaries. `server/task_llm.go:297–405,563–603`, `db/task_context.go:468–544`, `agent/terminal_proof.go:15–48,114–143`, `server/server.go:623–659`.
- **Chat demonstrates a useful recovery discipline.** Active run and queue state are durable. Unknown means caller-visible uncertainty. The file/manifest path checks structure, expected revision and ownership and preserves candidates it cannot prove safe to remove. The transcript package passed its published-prefix, malformed exchange, ownership and appended-byte controls. `db/chat_controls.go:467–505,514–594`, `chatstate/transcripts.go:177–215,264–328`, `chatstate/transcript_cleanup_test.go:40–137`, `chatstate/transcripts_test.go:50–104`.
- **Failures have meaningful diagnostic artifacts.** Named causes, tool-use IDs, terminal reasons, retry notices, optional record bodies, and an always-on lightweight usage ledger make it possible to distinguish a call retry from a worker replay or a local settlement. Inherited activity reads apply their terminal/session filters in SQL. `agent/capture.go:83–172`, `server/engine.go:644–702`, `llmrec/llmrec.go:118–217,229–265,278–304`, `db/exploration.go:1565–1612`.
- **The tests provide useful local seams.** The fake provider and normalized event types let unchanged tests exercise timing, terminal receipts and quota classification. Separate DB fixtures take deliberate locks and compare persistent and live state. Existing local controls cover an orderly return while a callback is active and SDK timeout settlement without relying on remote inference. `agent/session_ownership_test.go:19–104`, `server/task_shutdown_test.go:12–93`, `server/task_admission_test.go:89–125,220–305`, `third_party/norma/harness/timeout_settle_test.go:38–95`.

## 5. Weaknesses and evidence status

### Task lifecycle and durable recovery

1. **An unbootstrapped task can become complete during recovery.** The task row starts at `created`. The raw objective exists before bootstrap materializes goal rows. Admission clears `queue_mode` before the bootstrap goroutine runs. Startup starts the regular engine for an admitted nonterminal row regardless of bootstrap progress. A fresh restored row with a nonempty raw objective, no goal rows, and no intents took the goalless branch and persisted `done` with zero provider calls. The matched fixture with an open goal entered ordinary planning. The same absence-of-goals risk follows from the fallback path discarding its AddNode error while returning a successful-looking spec. This is a crash-window and write-error finding about the Go/SQL boundary. The checkout was never started against PostgreSQL and the fixture supplied the persisted row shape directly. `db/schema.sql:514–527`, `db/tasks.go:176–260`, `server/manager.go:1224–1257`, `server/goals.go:232–247,402–416`, `server/server.go:297–332`, `server/engine.go:852–868`. Controls `TestReviewBootstrapRestoreAndLocale`.
2. **Shutdown leaves a recoverable-intent classification gap.** When shutdown has already canceled the execution context at entry, the claimed intent returns to `open`. When the cause arrives during a provider call, the harness returns a cancellation error and the worker's catch-all error branch persists `blocked`. Startup reopens only `running`. The same local worker and recorded transition yielded `done` on ordinary completion, `open` on named task pause, `blocked` on in-call shutdown and `open` for a crash-style orphan `running` after the reset. An explicit blocked-intent rerun exists, so the finding is loss of automatic continuation and diagnostic precision. The app's chat queue deliberately uses `unknown` after an interrupted run. The task engine's plain `blocked` state makes less distinction between an operator restart, a provider issue and ambiguous side effects. `cmd/artex/main.go:128–146,173–185`, `server/engine.go:993–1004,1102–1166,1225–1236`, `agent/capture.go:83–92,139–172`, `db/exploration.go:337–378`, `db/chat_controls.go:564–594`. Control `TestReviewInterruptedWorkerRecovery`.
3. **A transient final write error strands an expired task in process.** The coordinator marks settlement using a one-way in-memory latch, calls final planning once and tries one guarded terminal write. On error it logs and returns. The coordinator-start marker and settling marker survive. Ordinary workers and planning reject settled work. A fault on the first terminal write left state `running`, one provider call and one write attempt. Retrying the coordinator entry and the settlement entry made no further write. The healthy path produced `timeout` with one write. Starting a new process re-evaluates the persisted deadline with fresh latches. A separate source path waits for a usable planner against the server/task context, so unavailable inference can keep an already-expired task in settlement indefinitely within that process lifetime. The ordinary success path uses a plain status write while the deadline path uses a guarded write. The SQL control confirmed that `done` wins in either order when both paths reach their writes. That can be an intentional completion preference, but it is stronger than a first-terminal-writer contract. `server/engine_timeout.go:29–39,83–93,129–268`, `server/engine.go:844–850,893–905,950–961`, `server/manager.go:1437–1489`, `db/tasks.go:489–512`. Control `TestReviewDeadlineCommitFailure` and independent SQL check. A late normal planner that reaches the plain write after the coordinator settles was source-traced without forcing the 90 s drain backstop.
4. **Manual completion treats paused work as absent.** With no open goal and a paused intent, the actual planner-loop branch can mark the task `done`. A subsequent intent resume succeeds at `paused → open` and emits a wake while the task stays terminal. That terminal state suppresses normal claims and first-run restore. This path matters for manually submitted work and for tasks whose goal rows have all resolved. Counting `open/running` is correct for the initial seed check. Reusing that predicate for terminal completion drops the distinct meaning of `paused`. `db/exploration.go:1202–1221`, `agent/coldgraph.go:81–92`, `server/engine.go:779–787,844–868,956–961`, `server/task_control.go:191–203`, `server/server.go:329–331`. Control `TestReviewPausedIntentAndManualTaskCompletion`.

### Ownership, retries and persisted history

5. **Task-local quiescence does not cover every callback.** A locally held tool that ignored cancellation survived ordinary `ControlWork` acknowledgement and successful `waitTaskQuiescent`. Global `DrainChats` waited on the same callback, timed out at the short fixture deadline, and returned successfully after release. The task barrier tracks the caller's operation through its final SQL write, while the SDK wrapper reserves a separate server-wide counter around callback execution. The task delete/cancel comments promise a stronger boundary than that accounting provides. A context-aware callback can finish before cleanup and DB constraints can reject some stale writes. This experiment establishes the ownership gap with a benign no-op and does not demonstrate corruption of real task output. On process shutdown the CLI still invokes deferred Manager close after a drain deadline, so a timed-out non-scheduler owner may outlive store close. The scheduler timeout path itself preserves the DB for a later close retry. `agent/session_ownership.go:14–61`, `server/background.go:19–29`, `server/engine.go:409–427,1077–1101`, `server/server_mgmt.go:163–181,214–228`, `server/chat_shutdown.go:14–82`, `cmd/artex/main.go:103–107,128–130,155–169`, `server/manager.go:846–864`. Control `TestReviewWorkControlCanReturnBeforeCallback`.
6. **Retry layers compose, and commitment at one layer does not fence the next.** A keyless loopback provider returning HTTP 503 received eight requests with one retry each at SDK-connect, task-stream and intent layers. With intent retry disabled it received four. An HTTP 400 received two with intent retry enabled and one with it disabled. The top-level `model_error` classifier lacks the task-stream layer's deterministic-failure exclusions. A second fixture delivered a tool block, waited for a local counter increment and then returned ordinary `unexpected EOF`. One configured intent retry ran the neutral effect twice. The SDK exited before recording the failed response and its tool result in the transcript, leaving only two user prompts. The equivalent run with intent retry off ran it once. The pre-commit router rule and quota-specific suppression remain valid. The risk is ordinary error replay across side effects without a durable attempt policy. `db/llmretry.go:14–23,79–117`, `agent/provider.go:375–386`, `server/task_llm.go:297–405,425–462`, `server/engine.go:80–85,1038–1057`, `third_party/norma/harness/query.go:415–441,803–863`. Controls `TestReviewLayeredRetryCounts`, `TestReviewNonQuotaStreamRetryAfterTool`.
7. **Worker transcript read failures degrade to silent fresh context.** A healthy seeded JSONL file contributed the prior user turn and remained appendable. A missing file started fresh and wrote two valid records. A file with the same readable prefix followed by a truncated JSON line caused Load to fail. The Worker ignored Resume's error, omitted the prefix from the provider request, appended output and finished as `done`. The file remained unreadable through the same Loader. File bytes confirmed the known prefix still existed, so this was a discarded working view. The test induced a single malformed suffix. It did not measure how often real crashes or disk faults produce one. `agent/worker.go:477–479,505–529`, `third_party/norma/agentcore/agentcore.go:361–392,475–479`, `third_party/norma/transcript/transcript.go:69–126,193–215`. Control `TestReviewWorkerHistoryLoadFailure`.
8. **The worker duration setting bounds tools and turn boundaries.** A context-aware fake inference completed normally after release. At 60 ms on a 20 ms worker budget, it was still running and had received no per-worker deadline. The harness passes the parent context to streaming and non-streaming model calls and applies the deadline to tools. A text-only terminal return can complete without crossing the tool-turn budget check. A separate task-level coordinator, provider or transport timeouts, and caller cancellation can bound specific deployments or phases. The control answers the worker-budget question without external latency, artificial CPU load or an uncooperative provider. `agent/worker.go:425–465,532–539`, `third_party/norma/harness/query.go:376–387,447–505,522–575,820–875`, `server/engine_timeout.go:184–204`. Control `TestReviewModelCallOutlivesWorkerBudget`.

### Delivery, concurrency and operational state

9. **Advancing the stream cursor can make a missing row unrecoverable through routine reconnect.** The consumer drops every event at or below the current cursor. Independent writes can reach Publish in a different order from ID allocation. With an explicit release barrier, production emit and SSE code delivered `2,3` for retained rows `1,2,3`; reconnect at 3 returned none. Buffer overflow gave a second case with monotone writes: release a held consumer after 257 commits into 256 slots, then publish 258. The stream delivered `1…256,258`; reconnect at 258 returned none while fresh replay saw all 258 rows. This is a streaming/delivery gap, and the recorded activities remained available by fresh replay. The isolated driver modeled the commit ordering. The buffering and cursor code was unmodified. `db/schema.sql:301–327`, `db/exploration.go:1256–1268,1529–1562`, `server/engine.go:646–679`, `server/broadcast.go:22–62`, `server/server.go:3139–3212`. Control `TestReviewActivityCursorOrdering`.
10. **The timeout scheduler orders transitions by task creation ID.** A newer task can reach timeout before an older task. Once the cursor advances past the higher ID, the old task's new timeout cannot match `id > cursor`. Discovery saw both transitions in order `1,2`, and only `2` in order `2,1`. A full query still saw both. The control stopped at discovery and made no triggered inference call. Independently, watermark updates and trigger queue processing have different durability. An in-memory enqueue or even an unavailable-agent return can be followed by a persisted cursor update. That is a separate source finding about best-effort delivery, even for events with a monotone cursor. `db/triggers.go:132–144,192–213`, `server/scheduler.go:141–151,289–317`, `server/conversations.go:570–630`. Control `TestReviewTimeoutTriggerWatermark`.
11. **A paired LLM activity count can drop an active increment.** When an End moves the counter to zero, it performs a separate atomic Store of zero. A concurrent Begin between those two operations can be overwritten. With one outstanding Begin and one synchronized new Begin/End pair, the production count sometimes read zero after both returned. The initial uninstrumented trials produced no witness. A longer uninstrumented run reproduced 54 losses across 3,000,000 four-thread trials. In the final race builds the four-thread totals were 1,357 of 600,000 on Go 1.27.1 and 852 of 360,000 on Go 1.26.10. Single-thread controls yielded zero. This is a lost update made of legal atomic operations. Instrumentation changes the observation window, and the observed counts do not estimate production frequency. The counter contributes to task admission and parking. The actual request semaphore is independent. `server/engine.go:369–390`, `server/goals.go:73–89,269–285`, `server/llm_concurrency.go:38–78`. Control `TestReviewLLMCallAccountingOverlap`.
12. **Some recoverable errors disappear at transition boundaries.** An empty frontier, read error, lost claim, and write error all returned the same nil from the actual dispatch helper. The worker's empty-poll sleep then applies to each. The test verified all SQL entry points and the claimed positive branch. The quota-blocked transition has no expected-state predicate and is ignored on error, unlike ordinary settlement. Startup also ignores reset errors for stale claims. These last two are source checks. `server/engine.go:962–969,1157–1166,1248–1255`, `db/exploration.go:342–349,1187–1232`, `db/task_context.go:562–577`, `server/server.go:301–307`. Control `TestReviewClaimFailureSignals`.
13. **Two smaller recovery seams reproduce locally.** A delayed health Save can run after a more recent Clear and leave a breaker open on restart while current memory was healthy. Ordered writes gave healthy state on reload. The mirror is documented as best effort, and the pool can still probe the head when all members are unavailable. A timed restored task can also inherit the server-root locale because its deadline coordinator creates the shared task runtime before `Engine.Run` applies the stored task locale. In the fixture the two paths used the same Japanese task preference. The timed runtime inherited its English parent and the untimed runtime carried Japanese. This tests context propagation; the production prompts consume that context. `llmpool/health.go:117–161`, `server/llmpool.go:20–55`, `db/llmhealth.go:19–56`, `server/server.go:297–331`, `server/engine.go:230–240,754–777`, `server/engine_timeout.go:132–147`, `agent/planner.go:341–380`. Controls `TestReviewHealthMirrorUpdateOrdering`, `TestReviewBootstrapRestoreAndLocale`.

**Ordinary task-file staging outlives its rollback owner on process exit.** Whole-task deletion holds rollback targets in memory. A child test process exited immediately after the production rename routine and before any DB action. The task file was absent at its normal path and intact in `.delete-staging`, including after the archive and restore stage recovery entry points ran. Explicit in-process rollback restored the same bytes in the matched case. The archive and traffic workers have recovery code for separate stage types, and chat cleanup uses a different manifest contract. A source search found only creation and inline compensation for the ordinary stage. A still-live task following an abrupt exit is the source-inferred cross-store consequence. The test did not kill a real database transaction or start the full backend. `server/manager.go:1515–1581,1692–1752`, `server/task_archives.go:39–61`, `server/task_archive_package.go:333–354,397–456`, `traffic/traffic.go:1478–1486`, `server/chat_transcript_cleanup.go:30–65`. Control `TestReviewTaskFileStageProcessExit`.

For newly bootstrapped tasks, a second context issue follows the first-call cache. `startTaskEngine` calls `execContextFor` before it decorates the returned copy with the task locale. Later rounds reuse the cached execution context while it stays alive. A focused helper test applied the same sequence and observed the server language until an ordinary pause invalidated the cache. This control exercises the context helpers, and the startup ordering is source-traced. `server/goals.go:43–54,67–70`, `server/engine.go:328–345,754–777,877–891,993–998`, `locale/locale.go:172–191`. Control `TestReviewBootstrapExecutionContextReuse`.

## 6. Core-code quality

**Decomposition.** The package boundaries carry real responsibilities. `db` owns SQL, `agent` builds sessions, the SDK owns inference/tool iteration, and `server` connects lifecycle and external interfaces. Within `server`, split modules such as chat dispatch, task timeout, scheduler and provider routing are more reviewable than the remaining accumulation in `server.go` (4,051 lines), `manager.go` (1,941), and `engine.go` (1,256). `agent/tools.go` (2,127) similarly mixes input validation, graph rendering and data mutation. The long worker settlement ladder is readable one case at a time. It is harder to audit all precedence combinations because each case owns state writes, logging and notification separately. The differences in expected-state handling and error checking follow that structure. `server/engine.go:993–1167`, `agent/tools.go:404–606,1217–1279`, `server/chat_dispatch.go:72–165`.

**State and types.** Typed node kinds, `TaskClock`, `AbortCause`, `TaskLLMTransition` and SQL checks make concrete invariants possible. Task snapshots use a distinct lock and copy mutable slices. Persisted status, pause and queue flags, started/settling/deleting maps, context cause and provider readiness all participate in whether a task runs. Intent state still flows through string literals in control, recovery and worker settlement. A typed transition result with explicit owner, attempt, phase and cause would reduce the ambiguity. Mixed deadlines use second-precision runtime values while queue position uses nanoseconds. The row schema's 300 s heartbeat default is a historical storage default. The effective backend floor is 600 s at creation and engine read, which matches executable code over older comments. `server/manager.go:31–148,160–195,1199–1286`, `db/schema.sql:173–194,514–562`, `db/tasks.go:80–82,126–130`, `server/engine.go:790–797`.

**Concurrency.** Several locks protect deliberately different domains. `concMu` covers task scheduling decisions, the engine's delete RWMutex serializes operation admission, task/runtime maps have their own mutexes, the work registry acknowledges one controller, and database row locks cover durable mutations. The design avoids holding a DB transaction across inference. The scheduler can hold `concMu` while reading settings/profile state or preparing an admitted task, and chat dispatch holds `chatMu` across claim queries. A slow dependency can therefore delay unrelated admissions, even though drain wraps lock acquisition in a deadline-selectable coordinator. Terminal and paused worker goroutines remain alive to support revival. They check role readiness before several idle guards, so long-lived task populations can continue to incur resolver traffic. That is a source-based scale concern. No database or process-scale load test was performed. `server/goals.go:232–258,261–354`, `server/chat_dispatch.go:80–127`, `server/chat_shutdown.go:14–27`, `server/engine.go:927–969`, `server/task_llm.go:533–555`.

**Errors and ownership.** Named causes preserve useful distinctions and errors.Join keeps both a failed commit and failed cleanup visible at chosen boundaries. Several task paths, particularly best-effort context reads, resuming worker history, startup stale-claim reset and claiming work, still substitute a useful default with no structured diagnostic. UI-derived status is also a separate projection from the persisted lifecycle, with terminal status winning over queue and pause. Runtime API consumers need to understand which status they are consuming. Storage methods called through the embedded `*sql.DB` include context-free claim, reset, activity and terminal writes. Admission barriers make these operations joinable. They still depend on the DB returning, as the held-lock tests are designed to exercise. `server/manager.go:1562–1586,1594–1609`, `agent/tools.go:404–433,451–495`, `server/server.go:301–307,1139–1159`, `db/exploration.go:342–349,1225–1231,1257–1267`, `server/task_shutdown_test.go:12–93,155–221`.

**Observability.** Activity, provider usage, optional raw records, and backend logs are useful at different granularity. The usage recorder normalizes cumulative frames to forwarded increments and meters failures even when raw recording is off. Tool IDs join receipts with activity. The activity insert retries three times and logs the classified drop with an FK diagnostic. This makes stored and streamed data share a provenance path, while the delivery loss and unordered cursor claims need correction. There are several other readily distinguishable states that still share one metric or outcome. The reported in-flight task counter surrounds session execution, including tool time, while profile admission surrounds the actual provider call. Add field-level counters for claim errors and CAS losses, current attempt/generation, safe-window retries, shutdown requeue and completion-write errors before using these signals for operational decisions. `agent/capture.go:94–172`, `llmrec/llmrec.go:118–217,278–304`, `server/engine.go:369–390,644–702,1028–1057`, `server/llm_concurrency.go:56–78`.

**Extension points and configuration.** Extending through `llm.Provider` and `CoreTool` is straightforward. The production system also exposes optional provider metadata, native model preflight and context windows, stored schema and prompt overrides, skill and MCP visibility, custom tool records, and event-triggered conversations. Provider wrappers must preserve iterator cancellation, typed quota errors and usage metadata. The OpenCode Go adapter validates normalized events and error classification. The separate JS bridge owns subprocess cancellation and staging cleanup. Its child process is distinct from an Engine intent worker. Narrow host interfaces make these external integrations replaceable. Package-global callbacks for tool resolution and prompt reads, set by one Server at startup, couple construction to a single-process owner and complicate independent Server instances and parallel tests. `server/server.go:203–251`, `agent/assembly.go:27–69`, `server/assembly.go:213–337`, `opencodesdk/provider.go:73–117,340–448,462–530`, `adapters/opencode-sdk/src/bridge.mjs:18–64,92–134`.

Declaring a task scope or putting a constraint in a prompt is an input to the model and graph filtering. Enforced policy is a separate layer in hook decisions and execution boundaries. Work directories and configurable capability catalogs organize artifacts. They do not by themselves create process isolation. Review of extensions should test permissions, cancellation and cleanup at the host boundary with harmless local fixtures. `agent/constraints.go:15–49`, `agent/worker.go:265–281,432–476`, `guard/guard.go:47–56,82–125`, `third_party/norma/tool/tool.go:84–106`.

**Tests and maintenance.** The existing corpus exercises local fake providers, terminal receipt order, source filtering and ownership. The PostgreSQL suites deliberately isolate a disposable database and contain genuine row-lock regressions. Root `go test` excludes the nested module, so Norma requires a separate test invocation. This is justified by the local replacement and an explicit provenance note. Some doc comments describe older paths, including a 300 s task heartbeat versus the effective 600 s runtime and an earlier plain FIFO trigger policy that now supports parallel lanes and merging. Preserve behavioral assertions while updating the comments at the transition boundaries. Use fault and crash-state tests to prevent a green unit suite from implying DB transaction coverage. `internal/dbtest/dbtest.go:98–174`, `go.mod:64–65`, `third_party/norma/README.scopeweaver.md:30–48`, `db/tasks.go:45–46,80–82`, `server/scheduler.go:16–22`, `server/conversations.go:570–666`.

## 7. Executed tests, experiments, and limitations

Go tests ran in a private network namespace whose IPv4 route table had no routes. Loopback fixtures stayed available. Bubblewrap mounted the checkout and the preexisting toolchain/module cache read-only, with one temporary writable directory inside the workspace for Go caches, test artifacts, controlled fixtures and a clean HOME. The test environment used `env -i`, `GOENV=off`, `GOWORK=off`, `GOPROXY=off`, `GOSUMDB=off` and `GOTOOLCHAIN=local`. No DSN or provider environment variables were supplied. The Go harness automatically set its guard DSN to an absent Unix socket for its DB-backed packages. The config fallback and dependency cache were local. Production database service, PostgreSQL integration, live model latency or cost, and JavaScript dependency installation are outside these results.

The table counts Go JSON test/subtest outcomes including parents. Package statuses are separate.

| Unchanged command or run | Observed result |
|---|---|
| Root `go test -mod=readonly -count=1 -json ./chatstate ./llmpool ./agent ./server ./db ./llmrec` | Six packages passed. Pass/skip by package: chatstate 9/0, llmpool 20/0, agent 875/59, server 317/261, db 112/241, llmrec 15/4. Test events span 06:17:22.596–06:17:29.848 UTC. |
| Root focused `-race -count=15`, causes, ownership, transcript publication, request admission and pool failover | Four packages passed. 360 PASS and 30 SKIP actions. The skipped subcases required DB fixtures. No race-detector diagnostic. Exact selector in the appendix. |
| Root focused `-race -p=2 -count=12`, task router, endpoint admission, lifecycle and terminal receipt guards | Server selector produced 228 PASS. Explicit agent receipt selector produced 24 PASS and 12 SKIP. The skip was the persistent proof fixture requiring PostgreSQL. Both runs exited 0 with no race-detector diagnostic. |
| Root supplemental units for CLI, test harness, config, transport, adapters and side questions | Eight packages passed. 265 PASS, 2 SKIP. The CLI DB-backed fixtures were skipped. |
| Root `./guard ./intercept ./traffic ./notify ./report ./evidence` | Six packages passed, 283 PASS and 4 SKIP. The file/traffic archive staging and rollback tests ran without external services. |
| Full root `go test -mod=readonly -race -p=2 -count=1 -json ./...` | 22 passing packages and one no-test package. 1,939 PASS, 571 SKIP, zero FAIL actions and no race-detector diagnostic. 568 skip messages explicitly reported unavailable DB fixtures. |
| Nested Norma `go test -mod=readonly -p=2 -count=1 -json ./...` | 16 passing packages and six no-test packages. 777 PASS, 4 SKIP and zero FAIL actions. Earlier focused Norma run covered 610 PASS and the same four skips. Two need an absent upstream checkout and two short fuzz seeds are explicitly inapplicable. |
| Root build, selected-package vet, adapter Node parse | `go build -mod=readonly ./...`, selected backend `go vet -mod=readonly` and `node --check` on the two adapters' source files completed with no diagnostics. The Node run validated syntax only. |

The temporary Go overlay added test code and in-process fixtures. It left the production files read-only. State-machine tests invoked production handlers, work loops, DB query entry points, worker SDK execution and publishing against a narrow SQL driver. It deliberately returned controlled rows, errors and completion order. Event ordering, callback release and model progress were synchronized by channels. One control used local HTTP fixtures to count actual adapter requests. A separate in-memory SQLite check executed selected production predicates as SQL. Those controls establish application behavior at defined boundaries. They do not substitute for PostgreSQL locks, transaction visibility, schema migrations, fault recovery under real PostgreSQL or full-process kill/restart.

| Temporary control | Key observation and qualification |
|---|---|
| Activity cursor | Delivery was complete in the ordered control. Late lower ID produced live `2,3` with retained `1,2,3`. The bounded subscriber case omitted 257 from a 258-row sequence. Reconnect stayed empty after the higher cursor in both cases. |
| Frontier failure signals | Empty and read-error cases made one read and zero attempts to claim. CAS loss and write error made one read and one attempted claim. All four returned nil. The positive case returned a node after one read and one claim. |
| Shutdown and callback ownership | Natural end settled `done`. Task pause and pre-canceled execution settled `open`. In-call shutdown settled `blocked`, and reset touched zero rows. Orphan reset touched one row. Ordinary pause quiesced before a held no-op callback returned. Global drain waited for that callback. |
| Expired task and bootstrap | Healthy final write produced `timeout`. A one-shot write error left `running` plus settling true and no repeat. Restored nonempty objective without goal rows finalized `done` without inference. The already-bootstrapped control entered inference. Timed and untimed restore resolved different runtime languages for the same persisted preference. |
| Manual work | With one paused intent and resolved/no goals, planner completion wrote `done`. Intent resume later returned `open` while the task stayed terminal. SQLite independently matched the paused/open predicate. |
| Worker transcript and wall budget | The missing-file case created readable JSONL, and the valid-file case preserved earlier history. A truncated suffix suppressed prior context, persisted completion and left the same file unreadable through the loader. A model stream remained active at three times its 20 ms worker budget until release. |
| Filesystem process exit | An isolated child ran ordinary task staging and exited before DB work. It left the original file path absent and its bytes intact in the stage. Archive recovery entry points did not restore it. The matched in-process rollback did. |
| Timeout discovery and health mirror | A later-created task timing out first suppressed the older task's later timeout. Full read found both. Out-of-order async health writes restored an open circuit despite a later in-memory Pass. In-order writes restored healthy state. |
| Overlap accounting | The race build and a larger uninstrumented run observed zero after two Begin calls and one End. Single-thread runs always retained the active count through that interleave. |
| Request and intent retry | Enabled one retry at each of three layers and observed 503: 8 requests, or 4 with intent replay off. HTTP 400: 2, or 1 with intent replay off. A post-tool ordinary stream error yielded two local counter increments with one intent retry, or one without. |
| SQL predicate control | Exact claim predicate updated a row once across two sequential contenders. Reset and re-claim allowed a stale state-only terminal CAS. This shows why single-owner restart matters and establishes the SQL predicate only. |

## 8. Measurement audit

| Observation or limitation | Alternative explanations checked and disposition |
|---|---|
| DB tests skipped in successful Go runs | Checked `internal/dbtest/dbtest.go:77–84,98–141` and the package TestMain entry points. `psql` and `pg_config` existed, and the reported bindir lacked `postgres`, `initdb` and `pg_ctl`. No DSN was passed. The exit-0 runs cover credential-free selections and deliberate skips. The review did not try the machine's default PostgreSQL endpoint. |
| Receipt selector coverage | The first secondary pattern included `TerminalProof.*`, which returned a passing agent package without selecting a receipt test. Listed the actual test names and reran the three explicit names in the appendix. The two local controls passed and the persistent proof fixture remained a reported skip. `agent/terminal_proof_test.go:322–387,563–607`. |
| Exact code and toolchain | Initial and final Git checks use the repository checkout, since the workspace root is a staging directory. The root module locally replaces Norma and a separate nested run covered its source. Explicit offline and readonly settings avoided module fetches and tracked metadata writes. A locally cached Go 1.26.10 repeated the controls alongside the primary Go 1.27.1 toolchain. Aggregate counts were taken after the final package event and checked against successful shell exits. An intermediate root-race count omitted the final package and is superseded. Neither is evidence about every supported OS or the exact minimum patch release. |
| First frontier fixture failed its positive control | Its first row shape had 13 columns. The production `scanNode` expects 10. The claim query never ran, since scanning failed and the helper ignored that error. Corrected the temporary driver to the actual projection and observed the claim pass under the unchanged helper. Read/write errors were then injected separately from CAS loss and empty results. `db/exploration.go:753–774`. |
| Worker fixtures initially reported unexpected SQL | The graph load also calls a recursive withdrawal query. The fixture treated only plain SELECT statements as read queries, so the first interrupted-worker run produced a harness error. Added the exact empty-withdrawal response and reran ordinary completion, pre-entry cancel, in-call shutdown, task pause and reset cases. The row outcomes persisted after correction. The no-op tool held only in the fixture and had no durable side effect after cancellation. |
| Initial settlement/bootstrap controls missed the terminal CAS | The temporary exec fixture initially checked the task ID argument for the status string. Correcting the index to match `SET status=$1 … WHERE id=$2` produced a healthy `timeout`/default `done` write and isolated the single injected failure. A latched control called both duplicate coordinator start and settlement again after the error. Those calls returned without a second terminal write. No quota, timeout of a real provider, or permission failure was involved. `db/tasks.go:502–512`. |
| Documented terminal precedence | Executed both production status predicates in both orders in memory. Plain `done` overwrote an earlier guarded timeout. A later guarded timeout updated zero rows after `done`. This establishes the two predicates' preference when both writes run. Actual planner/deadline scheduling, transaction locks and intended product preference were outside the predicate test. `db/tasks.go:488–512`, `server/engine.go:893–905`, `server/engine_timeout.go:206–228`. |
| Bootstrap finished unexpectedly on restart | Verified a nonempty raw objective and admitted nonterminal row, matched a second case with a goal already present, and traced create commit, admission-mode clearing and startup. The test resolver was available and did enter inference in the matched case. Source review found the raw-objective fallback belongs to bootstrap and that startup does not call it for a recovered admitted row. This pinpoints lifecycle phase loss without simulating a real database crash. |
| Paused intent dropped from completion check | Read the predicate and executed it independently against paused then open rows in in-memory SQLite. The actual handler performed the resume CAS with its normal return shape. Agent readiness was supplied so the early idle path could not explain the result. A terminal task suppresses workers regardless of the newly open row. The fixture assumes the documented interpretation that per-intent pause leaves resumable work. |
| Shutdown outcome differs from a crash and task pause | The fake provider parked until the test had observed actual inference entry. No timed worker deadline, quota result, competing controller or sleep race was needed. The pre-entry cancel and controlled pause are counterexamples to a blanket conclusion that any cancel becomes blocked. The real CLI passes `AbortShutdown`; the existing held SQL restored-claim test primarily exercises the pre-entry branch and was DB-skipped here. The repeat of `ResetRunningIntents` applied to the fixture state by the production query entry point. |
| Quiescence while callback still executing | Entry and release were explicit channel barriers. Observed callback still blocked after both the worker result and task quiescence, then saw the server drain deadline and successful retry after release. Verified owner wiring in `newOwnedSession` and the distinction between `backgroundWG` and task inflight. This rules out slow assertion sampling and a missing global owner. A taken late write and actual delete remain unmeasured. |
| Database-backed activity appears lost | Forced lower sequence publication after higher and used a third event as the consume barrier. A healthy increasing control kept all IDs. Separately held the subscriber behind a known buffer limit and published a post-overflow marker. Checked persisted rows, a fresh cursor, and a reconnect with `Last-Event-ID`. This rules out missing inserts, small replay limits, filter mismatch, and disconnect timing in the observed examples. The SQL commit interleave is modeled; overflow is an actual broadcaster/handler behavior. |
| Timeout event skipped | No trigger delivery, quotas, timeouts or concurrency were required to select rows in the fixture. Matched an in-order completion, re-read both rows with a zero cursor and then ran the exact SQL filter in SQLite. That isolates ordering by creation ID. The downstream crash/queue durability concern follows separately from its source handoff. |
| Circuit health comes back stale | Ran scheduled callbacks both in registration order and reversed while keeping the registry's logical state changes identical. Read the real DB mirror functions' SQL and verified no revision or conditional upsert fences older changes. No clock expiry or fabricated provider error classification was needed. Actual scheduler frequency and impact on successful fallback were not measured. |
| Wrong stored preference after timed restart | Both task records returned Japanese via the real settings read path. Untimed restore attached Japanese to its runtime. Timed restore reused the runtime already created from an explicitly English root. Checked live context identity and production consumer sites. This is a co-owned-runtime construction observation, independent of missing translations or a provider's language ability. |
| Millisecond duration did not abort inference | Used an explicit local provider start barrier, checked the actual context deadline and held release for 60 ms. The provider selected on cancellation. Confirmed a clean text-only end and traced streaming and complete model calls to the parent context. The existing Norma timeout tests exercise the different tool deadline and settlement path. This is a contract difference, not an estimate of provider timeout behavior. |
| Transcript context vanished despite an intact prefix | Verified the valid fixture's records before and after the run, checked bytes physically remained, and measured the first request's messages rather than inferring from the model's response. The missing-file control had a nil loader error. Only the injected malformed suffix caused the parser error. No filesystem access failure needed to produce it. This isolates ignored recovery error handling and does not quantify crash incidence. |
| Initial overlap trials had zero lost counts | Paired all Begin/End operations and waited for both before sampling. Repeated with one and four simultaneous runtime execution slots on two cached toolchains. Traced the two atomic statements and their values. Race instrumentation increased observability. A 25-repeat uninstrumented run on Go 1.27.1 independently yielded 54 losses with four slots and none with one. The initial negative was a finite-sample result. The count oracle is independent of race-detector messages. No actual cap failure or production occurrence rate is claimed. |
| Retry amplification and a first batch deadline | In one six-repeat race batch a 503 case hit the fixture's 3 s join guard. Cancellation and DB-close messages followed that fixture failure. Its other cases and later repeats produced the expected counts. The second toolchain test finished before the slow fixture batch, so overlap with that compiler was not established. The provider and worker policies both specified 1 ms retry backoffs, the endpoint was loopback, and the count oracle was independent of time. Increased only the fixture's outer join budget to 12 s and joined the worker before cleanup on error. Twenty isolated race repetitions of the two retry controls passed, with 160 test/subtest PASS actions. Remaining measurement is about attempt counts; the exact cause of that one slow repetition and runtime latency distributions are unestablished. |
| Duplicate local effect despite stream commitment | Counted actual no-op handler entry and forced the modeled EOF only afterward. The inner stream selection count did not increase within an attempt. The repeated effect appeared only when whole-intent retry was enabled. Inspected the JSONL records to confirm that the partial assistant/tool exchange was missing. This distinguishes retry layers and ambiguous side effects without executing an external operation. |
| Ordinary delete stage after interrupted ownership | The subprocess ran the actual file rename code in a temporary root and exited before a DB action. Compared with successful inline rollback, checked that the exact data survived staging, and invoked the archive/restore recovery entry points on the same temp tree. Source reads distinguish where those recoverers search from ordinary delete-stage creation, so a filesystem access, unknown stage name or failed rename cannot explain the result. A live PostgreSQL deletion and server restart remain unmeasured. |
| Bootstrap context first-call cache | Applied the documented construction order to the actual context helper and checked both context identity and locale. A localized view used the task language locally while the cached original carried the server language. Pause/resume established a fresh localized context. This identifies a different carrier lifetime from the timed restore case. |
| Source-only scale concerns | Inspected dispatch ordering and provider-readiness calls before terminal checks. Worker size is sampled once, so a changed setting does not resize existing loops. This intentional lifecycle tradeoff means terminal goroutine count alone does not estimate provider traffic. No contention benchmark, large database or long-running deployment was measured. |

## 9. Post-mortem and highest-leverage improvements

The code has two established reliability styles. The exploration engine shares a durable graph, uses short conditional writes and expects graph reconstruction to cover interruption. Chat history and archive code give expensive or ambiguous work an explicit durable phase, an owner and in some cases a recoverable intermediate artifact. The scheduling and streaming layers value short waits and low overhead. Their in-memory coalescing is a good fit for nudges and live diagnostics. When that same handoff also carries the only record of whether persistent work began or an event was delivered, the process state becomes part of an undocumented transaction.

The observed failure sequence is usually small. A task creation commit precedes bootstrap. One failed terminal SQL write is enough to leave a successful settlement latch open. SDK cancellation can return a terminal receipt while a callback is still running. A shared counter's two atomics are separately correct and still erase another operation. A publisher can send a higher ID before a lower ID. These boundaries grew compensating checks around normal synchronous paths. Each check helps a different incident. The system lacks a common way to state the durable phase, expected owner, retry boundary and final evidence together. The successful chat and archive code provide nearby models for making those facts explicit. See `server/goals.go:232–247`, `server/engine_timeout.go:184–228`, `agent/session_ownership.go:19–61`, `server/engine.go:372–389`, `db/chat_controls.go:400–505` and `db/task_archives.go:355–395`.

The most plausible failure modes in a single-owner deployment are lost continuation after restart, an expired task that requires operator intervention, or an ambiguous worker retry that repeats a prior effect. With larger task histories, a brief slow stream subscriber can lose observations while retained storage stays intact. A backend with independent timeout schedules can miss a timeout trigger even at low volume. Same-profile fallback, log retries and scheduler polling are appropriate resilience mechanisms when their contracts are bounded. They cannot reconcile an unrecorded bootstrap, an older worker's ownership or a cursor that advanced past undelivered work.

| Priority | Improvement | Acceptance evidence |
|---|---|---|
| **P0 · Persist task phases and terminal decisions** | Keep `bootstrap_pending` through successful goal materialization, and capture the intended task kind for legitimately goalless work. Make startup resume the persisted phase and fail or surface an actionable error if its writes do not commit. Represent settlement as a durable transition with a bounded retry of the final SQL write and explicit provider-unavailable behavior. Route normal completion and timeout through one conditional policy. Treat paused intents as resumable in task completion or atomically admit their parent on resume. | Use restart fixtures before bootstrap, between goal writes and first run, and after first failing settlement write. Assert raw objectives stay open, one terminal transition wins, one final result is persisted, and a resumed paused intent has a runnable task. Exercise both no-goal manual completion and requested goal materialization. |
| **P0 · Fence ownership and retry by attempt** | Track a claim generation and attach it to task/intent mutation, cancellation acknowledgement and cleanup. Make callback ownership visible to the task-level drain or fence its late writes. Settle interrupted work with a reason that distinguishes safe resume, uncertain effects and terminal stop. Preserve or quarantine an unreadable history prefix with an explicit recovery decision. Count physical request attempts under a common bounded retry budget and only repeat work when its effects are known safe. Use the chat unknown-run pattern. Give the ordinary task-file stage a durable journal and startup reconciliation under the persisted deletion decision. | Pause/delete with an in-flight no-op and a simulated late completion. Restart across each recorder and filesystem-commit boundary. Verify an old generation cannot settle a reclaimed row, that corrupt history has a visible recovery state, and that an ordinary error after an effect does not silently repeat it. Include status-400, quota and 503 tests with actual request/effect counters. |
| **P1 · Make activity and scheduler cursors describe committed progress** | Keep notifications cheap by using them as hints to range-read durable activity. Give activity a read cursor whose order is consistent with visibility. Deal explicitly with lossy buffer saturation by invalidating/replaying the cursor or issuing a snapshot reset. Publish timeout transitions with their own occurrence identity, then durably hand trigger events to dispatch before acknowledging them. Version breaker mirror updates or coalesce them per profile. | Drive reversed commit/publish order, overflow, reconnect, two timeout transitions in reverse task-ID order, and a restart between event acknowledgment and dispatch. Assert each committed event is visible or produces a clear resync. Test reversed breaker mirror writes against the eventual authoritative state. |
| **P1 · Define separate time contracts** | Separate model-call deadlines, tool-run deadlines, settlement turn/time budgets, and operation/drain deadlines. Carry the correct task context into the coordinator before its first goroutine allocation. Make context-aware DB methods and clear, bounded server shutdown ownership the default, including the timeout and callback paths. If an outstanding owner may outlive shutdown, record its uncertain disposition before store close. | Hold inference, a context-aware tool and a DB write independently. Confirm the intended named reason, recovery state, and eventual cleanup for each boundary. Verify timed restore keeps task language and side-context consumers. |
| **P2 · Improve observability and reduce incidental coupling** | Replace the activity-count clamp with one atomic update rule and test formal balance. Distinguish a quiet frontier, SQL failure and CAS contention. Report failed restart recovery. Move immutable lifecycle types and narrow transition results out of large server files and inject per-server tool/prompt configuration. Sample idle readiness costs before altering scheduling. | Keep the existing control matrix and add real PostgreSQL transaction tests in a disposable local fixture. Require explicit skip/execute counts and run the nested module. Assert counter behavior across a last-End/new-Begin interleave. Record idle polling costs and lock time with task count before choosing optimizations. |

The highest-value change is to persist whether the backend is preparing, executing, or settling a task before returning success for that phase. It gives startup, retries, cancellation and reporting a common interpretation of partial progress. The existing schema, ownership barriers and job patterns make incremental changes possible without a replacement scheduler.

## 10. Evidence appendix

### Source cross-reference

| Question | Where to read in the pinned checkout |
|---|---|
| Who starts and closes services? | `cmd/artex/main.go:93–185`, `server/server.go:165–333`, `server/chat_shutdown.go:9–83`, `server/manager.go:846–864`, `server/scheduler.go:41–108`. |
| Where does a task become runnable? | `db/tasks.go:162–260`, `server/goals.go:29–70,101–219,232–354`, `server/manager.go:1207–1286`, `server/engine.go:754–787`. |
| Where are claims, proof and state committed? | `db/exploration.go:202–230,273–293,342–402,1187–1232`, `server/engine.go:993–1167`, `server/engine_timeout.go:48–64,184–268`, `db/tasks.go:489–530`. |
| What owns cancellation and files? | `server/engine.go:178–345,401–483`, `agent/session_ownership.go:14–89`, `server/server_mgmt.go:141–228`, `server/manager.go:1500–1586,1647–1752`, `server/task_archive_package.go:397–456`. |
| What replays after a restart? | `server/server.go:297–333`, `agent/worker.go:477–529`, `third_party/norma/agentcore/agentcore.go:361–392`, `db/chat_controls.go:467–505,564–594`, `chatstate/transcripts.go:45–144,177–215`, `db/task_archives.go:355–395`. |
| Where are request and tool contracts? | `server/task_llm.go:112–148,246–406,425–462`, `db/task_context.go:468–544`, `third_party/norma/llm/provider.go:153–163`, `third_party/norma/tool/tool.go:84–106`, `agent/assembly.go:37–89`. |
| Where are events and accounting delivered? | `server/engine.go:369–390,644–702`, `server/broadcast.go:22–62`, `server/server.go:3139–3217`, `server/scheduler.go:182–249,289–317`, `llmrec/llmrec.go:118–217,278–304`. |
| Which unchanged tests separate database and ownership domains? | `internal/dbtest/dbtest.go:98–174`, `server/task_shutdown_test.go:33–105`, `server/scheduler_shutdown_test.go:35–125`, `agent/session_ownership_test.go:19–104`, `third_party/norma/harness/timeout_settle_test.go:38–95`. |

### Offline reproduction commands

Run from the workspace root. The cache path can point to an already prepared module cache. In this review the Go executables came from `$HOME/.local/go-1.27.1/go/bin/go` and `$HOME/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.10.linux-amd64/bin/go`. This runner uses the supplied Go binary without downloading a different one.

~~~sh
set -eu
date -u +'%Y-%m-%dT%H:%M:%SZ'
workspace=$(pwd -P)
repo="$workspace/repos/cskwork__scopeweaver"
report="$workspace/evaluations/cskwork__scopeweaver.md"
expected=1f33072cbb09280ffafdec189d64e7ed8e95099a
test "$(git -C "$repo" rev-parse --verify HEAD)" = "$expected"
test -z "$(git -C "$repo" status --porcelain=v1 --untracked-files=all)"
review_tmp=$(mktemp -d "$workspace/.scopeweaver-repro.XXXXXXXX")
trap 'rm -r --one-file-system -- "$review_tmp"' EXIT
mkdir -p "$review_tmp/cache" "$review_tmp/tmp" "$review_tmp/home"
review_go=${SCOPEWEAVER_REVIEW_GO:-$HOME/.local/go-1.27.1/go/bin/go}
review_modcache=${SCOPEWEAVER_REVIEW_MODCACHE:-$HOME/go/pkg/mod}

offline_go() {
    review_workdir=$1
    shift
    bwrap --unshare-net --ro-bind / / --bind "$review_tmp" "$review_tmp" \
        --dev /dev --proc /proc --chdir "$review_workdir" -- \
        /usr/bin/env -i PATH=/usr/bin:/bin HOME="$review_tmp/home" LANG=C.UTF-8 TZ=UTC \
        TMPDIR="$review_tmp/tmp" GOCACHE="$review_tmp/cache" GOMODCACHE="$review_modcache" \
        GOTOOLCHAIN=local GOENV=off GOWORK=off GOPROXY=off GOSUMDB=off "$review_go" "$@"
}
offline_go "$repo" version
offline_go "$repo" test -mod=readonly -count=1 -json ./chatstate ./llmpool ./agent ./server ./db ./llmrec >"$review_tmp/root-selected.json"
offline_go "$repo" test -mod=readonly -race -p=2 -count=1 -json ./... >"$review_tmp/root-all.json"
offline_go "$repo/third_party/norma" test -mod=readonly -p=2 -count=1 -json ./... >"$review_tmp/norma-all.json"
offline_go "$repo" build -mod=readonly ./...
offline_go "$repo" vet -mod=readonly ./agent ./server ./db ./chatstate ./llmpool ./llmrec \
    ./cmd/artex ./llmnet ./opencodesdk ./ollama ./sidequestion ./mcphttp
offline_go "$repo" test -mod=readonly -race -count=15 -json \
    -run '^Test(ChatDispatcherCancellationAndQueue|ChatQueueDrainsAfterExternalRun|ShutdownRejectsNewTaskOperations|ShutdownDeadlineBoundsAdmissionMutex|ControlWork.*|PauseCancelsWithNamedCause|TaskPauseCauseSurvivesImmediateResume|ConcurrencyProvider.*|CaptureRunCancellationDoesNotJoinSDKCallbacks|CaptureRunPreservesHookLifecycle|FailoverOnNoCredit|NoFailoverAfterEmit|NoFailoverOnCancel|ChatTranscriptPublishCrashWindows)$' \
    ./server ./agent ./chatstate ./llmpool >"$review_tmp/root-focused-race.json"
offline_go "$repo" test -mod=readonly -race -p=2 -count=12 -json \
    -run '^Test(TerminalProof.*|TaskLLMStream.*|NativeUrgentFIFOAndBackgroundFIFO|NativeQueuedAndGrantCancellationAndLoweredCap|TaskLifecycleSnapshotConcurrentConsistency|EngineDeleteBarrierRejectsNewTaskOperations|StopTaskCancelsRuntimeAndClearsLifecycleState)$' \
    ./agent ./server >"$review_tmp/router-guards-race.json"
offline_go "$repo" test -mod=readonly -race -p=2 -count=12 -json \
    -run '^Test(InterruptedTerminalReceiptAllowsSettlementAfterLateHook|GoalMetToolMeaningSurvivesGate|RealProveGoalSessionGatesAfterFinalProof)$' \
    ./agent >"$review_tmp/receipt-guards-race.json"
offline_go "$repo" test -mod=readonly -count=1 -json \
    ./cmd/artex ./internal/dbtest ./config ./llmnet ./opencodesdk ./ollama ./sidequestion ./mcphttp >"$review_tmp/root-supplement.json"
offline_go "$repo" test -mod=readonly -count=1 -json \
    ./guard ./intercept ./traffic ./notify ./report ./evidence >"$review_tmp/root-supporting.json"

python3 - "$report" "$repo" "$review_tmp" <<'PY'
from pathlib import Path
import json, sys
report, repo, work = map(Path, sys.argv[1:])
content = report.read_text()
source = content.split("<!-- BEGIN SCOPEWEAVER CONTROL SOURCE -->\n~~~go\n", 1)[1].split("\n~~~\n<!-- END SCOPEWEAVER CONTROL SOURCE -->", 1)[0]
control = work / "runtime_controls_test.go"
control.write_text(source + "\n")
overlay = {"Replace": {str(repo / "server" / "zz_scopeweaver_review_test.go"): str(control)}}
(work / "overlay.json").write_text(json.dumps(overlay))
PY
offline_go "$repo" test -mod=readonly -race -overlay="$review_tmp/overlay.json" \
    -p=2 -count=5 -json -run '^TestReview' ./server >"$review_tmp/controls.json"
offline_go "$repo" test -mod=readonly -race -overlay="$review_tmp/overlay.json" \
    -count=20 -json -run '^TestReview(LayeredRetryCounts|NonQuotaStreamRetryAfterTool)$' ./server >"$review_tmp/retry-control.json"
offline_go "$repo" test -mod=readonly -overlay="$review_tmp/overlay.json" \
    -count=25 -json -run '^TestReviewLLMCallAccountingOverlap$' ./server >"$review_tmp/plain-counter.json"
python3 - "$review_tmp" <<'PY'
from collections import Counter
from pathlib import Path
import json, sys
for path in sorted(Path(sys.argv[1]).glob("*.json")):
    if path.name == "overlay.json":
        continue
    counts = Counter()
    for line in path.read_text().splitlines():
        entry = json.loads(line)
        state = entry.get("Action")
        if state in {"pass", "fail", "skip"}:
            counts["test_" + state if "Test" in entry else "package_" + state] += 1
        if "TestReview" in entry.get("Test", "") and "zz_scopeweaver_review_test.go:" in entry.get("Output", ""):
            print(entry["Output"].strip())
    print(path.name, dict(counts))
PY
test "$(git -C "$repo" rev-parse --verify HEAD)" = "$expected"
test -z "$(git -C "$repo" status --porcelain=v1 --untracked-files=all)"
date -u +'%Y-%m-%dT%H:%M:%SZ'
~~~

The final combined overlay, including process-exit staging and a bootstrap context control, passed with 265 test/subtest outcomes at count 5 on Go 1.27.1 and 159 at count 3 on Go 1.26.10. There were no skips or race-detector diagnostics. The latter used the alternate executable and `-count=3`. The final Go 1.27.1 batch's recorded event interval was 06:40:18.998–06:40:37.898 UTC. Its four-slot counter losses were 245, 333, 344, 233 and 202 of 120,000 trials per run. Go 1.26.10 yielded 309, 251 and 292. The uninstrumented run yielded 54 total losses across 25 four-slot trials of 120,000 each. Corresponding single-slot trials returned zero. The relative rates reflect instrumentation and scheduling of the control.

The report's extracted shell runner completed successfully twice during validation. The later replay reproduced the package and outcome counts above, including 265 overlay outcomes, 160 retry-control outcomes and 75 uninstrumented counter outcomes. The supplemented receipt selectors were executed independently in the same environment. Every cited source file was compared byte-for-byte with its pinned Git blob, and citation line bounds were checked. Guided reproduction uses the fixtures embedded below and needs no detached test files from the review.

The adapter check ran the installed Node executable using `--check` for `adapters/agent/src/*.js`, `adapters/agent/pi-extension.js` and `adapters/opencode-sdk/src/*.mjs` inside the same isolated mount and network setup. Both adapter-local `node_modules` directories were absent. The checkout does not contain the upstream prompt comparison tree required by two Norma fixtures. The original backend opt-ins for chat E2E, adapter E2E and a live review provider remained unset. These are separate measurement gaps from the 568 no-DB skips.

### Independent SQL predicate control

Run from the checkout. This reproduces the predicate experiment with SQLite in memory, using the checked-in SQL text and a minimal compatible schema. It does not simulate PostgreSQL concurrency or migrations.

~~~sh
python3 - <<'PY'
import pathlib, re, sqlite3

def query(path, fn):
    text = pathlib.Path(path).read_text().split(" " + fn + "(", 1)[1]
    return re.search(r"`([\s\S]*?)`", text).group(1).strip()

db = sqlite3.connect(":memory:")
db.execute("create table tasks (id integer primary key, status text, deleted_at text, description text, goal text)")
db.executemany("insert into tasks values (?, 'running', null, 'fixture', 'objective')", [(1,), (2,)])
timed_out = query("db/triggers.go", "TimedOutTasksSince")
for task in (2, 1):
    db.execute("update tasks set status='timeout' where id=?", (task,))
    cursor = 0 if task == 2 else 2
    print("timeout", task, "cursor", cursor, "->", db.execute(timed_out, {"1": cursor}).fetchall())
print("full timeout read", [row[0] for row in db.execute(timed_out, {"1": 0})])

db.execute("create table exploration_nodes (id integer, exploration_id integer, kind text, state text, owner text, completed_at text, blocked_reason text, content_version integer default 0)")
db.execute("insert into exploration_nodes (id,exploration_id,kind,state) values (1,1,'intent','paused')")
active = query("db/exploration.go", "HasActiveIntent")
reset = query("db/exploration.go", "ResetRunningIntents")
claim = query("db/exploration.go", "ClaimIntent")
settle = query("db/exploration.go", "CompareAndSetIntentState")
db.create_function("now", 0, lambda: "fixture")
print("active for paused", db.execute(active, {"1": 1}).fetchone())
print("resume CAS", db.execute(settle, {"1": "open", "2": 1, "3": 1, "4": "paused", "5": False}).rowcount)
print("active for open", db.execute(active, {"1": 1}).fetchone())
print("claim first/second", *[db.execute(claim, {"1": owner, "2": 1, "3": 1}).rowcount for owner in ("one", "two")])
print("orphan reset and new claim", db.execute(reset, {"1": 1}).rowcount, db.execute(claim, {"1": "two", "2": 1, "3": 1}).rowcount)
print("old state-only CAS after claim generation changed", db.execute(settle, {"1": "done", "2": 1, "3": 1, "4": "running", "5": True}).rowcount)
print("final state owner", db.execute("select state,owner from exploration_nodes").fetchone())

db.create_function("now", 0, lambda: "tick")
db.execute("alter table tasks add column completed_at text")
for order in (("guarded timeout", "plain done"), ("plain done", "guarded timeout")):
    db.execute("update tasks set status='running', completed_at=null where id=1")
    outcomes = []
    for mode in order:
        fn = "SetTerminalStatusGuarded" if mode.startswith("guarded") else "SetStatus"
        updated = db.execute(query("db/tasks.go", fn), {"1": mode.split()[-1], "2": 1}).rowcount
        outcomes.append((updated, db.execute("select status from tasks where id=1").fetchone()[0]))
    print(order, outcomes)
PY
~~~

Output included timeout 2 at cursor 0 and an empty timeout 1 read at cursor 2, with both IDs in the full read. The active predicate returned 0 while paused and 1 after reopening. Claim row counts were `1 0`, reset and re-claim counts were `1 1`, and the older state-only completion updated the newly claimed row to `('done', 'two')`. In the actual single-server design the earlier owner should be gone after a restart. The predicate alone cannot distinguish the two owners.

The status predicate checks gave `[(1, 'timeout'), (1, 'done')]` for guarded timeout then plain done, and `[(1, 'done'), (0, 'done')]` for the reverse. These are the respective SQL update row counts and task states.

<details>
<summary>Source of the isolated Go controls used in this review</summary>

The extracted `runtime_controls_test.go` had 1,278 lines and SHA-256 `b9ec71e2230e93989e28fbe0ef53a783664ae29c7e8301314f8752d725d8d6c3`.

<!-- BEGIN SCOPEWEAVER CONTROL SOURCE -->
~~~go
package server

import (
	"bytes"
	"context"
	"database/sql"
	"database/sql/driver"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"iter"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Autumn-27/artex/agent"
	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/artex/guard"
	"github.com/Autumn-27/artex/locale"
	"github.com/Autumn-27/norma/llm"
	"github.com/Autumn-27/norma/tool"
	"github.com/Autumn-27/norma/transcript"
)

type reviewConnector struct {
	conn reviewConn
}

func (c reviewConnector) Connect(context.Context) (driver.Conn, error) { return c.conn, nil }
func (c reviewConnector) Driver() driver.Driver                        { return c.conn }

type reviewConn struct {
	query func(context.Context, string, []driver.NamedValue) (driver.Rows, error)
	exec  func(context.Context, string, []driver.NamedValue) (driver.Result, error)
}

func (c reviewConn) Open(string) (driver.Conn, error) { return c, nil }
func (c reviewConn) Close() error                     { return nil }
func (c reviewConn) CheckNamedValue(v *driver.NamedValue) error {
	if _, ok := v.Value.([]int64); ok {
		return nil
	}
	return driver.ErrSkip
}
func (c reviewConn) Prepare(string) (driver.Stmt, error) {
	return nil, errors.New("unexpected prepare")
}
func (c reviewConn) Begin() (driver.Tx, error) {
	return nil, errors.New("unexpected transaction")
}
func (c reviewConn) QueryContext(ctx context.Context, query string, args []driver.NamedValue) (driver.Rows, error) {
	if c.query == nil {
		return nil, errors.New("unexpected query")
	}
	return c.query(ctx, query, args)
}
func (c reviewConn) ExecContext(ctx context.Context, query string, args []driver.NamedValue) (driver.Result, error) {
	if c.exec == nil {
		return nil, errors.New("unexpected exec")
	}
	return c.exec(ctx, query, args)
}

type reviewRows struct {
	cols []string
	data [][]driver.Value
}

func (r *reviewRows) Columns() []string { return r.cols }
func (r *reviewRows) Close() error      { return nil }
func (r *reviewRows) Next(to []driver.Value) error {
	if len(r.data) == 0 {
		return io.EOF
	}
	copy(to, r.data[0])
	r.data = r.data[1:]
	return nil
}

func newReviewDB(t *testing.T, c reviewConn) *db.DB {
	t.Helper()
	sqlDB := sql.OpenDB(reviewConnector{conn: c})
	t.Cleanup(func() { _ = sqlDB.Close() })
	return &db.DB{DB: sqlDB}
}

func reviewRecv[T any](t *testing.T, from <-chan T) T {
	t.Helper()
	select {
	case v := <-from:
		return v
	case <-time.After(3 * time.Second):
		t.Fatal("timed out waiting for controlled step")
		var zero T
		return zero
	}
}

type reviewWriter struct {
	headers http.Header
	body    bytes.Buffer
	flushes chan string
	barrier <-chan struct{}
}

func (w *reviewWriter) Header() http.Header         { return w.headers }
func (w *reviewWriter) WriteHeader(int)             {}
func (w *reviewWriter) Write(b []byte) (int, error) { return w.body.Write(b) }
func (w *reviewWriter) Flush() {
	w.flushes <- w.body.String()
	w.body.Reset()
	if w.barrier != nil {
		<-w.barrier
		w.barrier = nil
	}
}

func reviewStream(t *testing.T, s *Server, since string, barrier <-chan struct{}) (*reviewWriter, func()) {
	t.Helper()
	ctx, cancel := context.WithCancel(t.Context())
	r := httptest.NewRequestWithContext(ctx, "GET", "/activity?task=1", nil)
	if since != "" {
		r.Header.Set("Last-Event-ID", since)
	}
	w := &reviewWriter{headers: make(http.Header), flushes: make(chan string, 300), barrier: barrier}
	done := make(chan struct{})
	go func() {
		defer close(done)
		s.streamActivity(w, r)
	}()
	stop := func() {
		cancel()
		reviewRecv(t, done)
	}
	t.Cleanup(stop)
	return w, stop
}

func reviewIDs(items []db.Activity) []int64 {
	ids := make([]int64, 0, len(items))
	for _, item := range items {
		ids = append(ids, item.ID)
	}
	return ids
}

func TestReviewActivityCursorOrdering(t *testing.T) {
	for _, sequence := range []string{"ascending", "late_lower_id", "slow_consumer"} {
		t.Run(sequence, func(t *testing.T) {
			var mu sync.Mutex
			persisted := map[int64]string{}
			allocated := make(chan struct{})
			release := make(chan struct{})
			var finish sync.Once
			defer finish.Do(func() { close(release) })

			dbHandle := newReviewDB(t, reviewConn{query: func(ctx context.Context, query string, args []driver.NamedValue) (driver.Rows, error) {
				switch {
				case strings.Contains(query, "INSERT INTO activity"):
					summary := args[7].Value.(string)
					id, err := strconv.ParseInt(summary, 10, 64)
					if err != nil {
						return nil, err
					}
					if id == 1 && sequence == "late_lower_id" {
						close(allocated)
						select {
						case <-release:
						case <-ctx.Done():
							return nil, ctx.Err()
						}
					}
					mu.Lock()
					persisted[id] = summary
					mu.Unlock()
					return &reviewRows{cols: []string{"id"}, data: [][]driver.Value{{id}}}, nil
				case strings.Contains(query, "FROM activity") && strings.Contains(query, "id>$2 ORDER BY id"):
					since := args[1].Value.(int64)
					limit := int(args[2].Value.(int64))
					mu.Lock()
					defer mu.Unlock()
					var ids []int64
					for id := range persisted {
						if id > since {
							ids = append(ids, id)
						}
					}
					sort.Slice(ids, func(i, j int) bool { return ids[i] < ids[j] })
					rows := &reviewRows{cols: make([]string, 19)}
					for _, id := range ids[:min(limit, len(ids))] {
						rows.data = append(rows.data, []driver.Value{id, nil, "fixture", "text", "", "", false, persisted[id], []byte("{}"), time.Unix(0, 0), nil, nil, nil, nil, nil, "", "", nil, nil})
					}
					return rows, nil
				default:
					t.Errorf("unexpected SQL: %s", query)
					return nil, errors.New("unexpected SQL")
				}
			}})
			task := &Task{ID: "1", ExpID: 1, Store: dbHandle.Exploration(1)}
			m := &Manager{pg: dbHandle, tasks: map[string]*Task{task.ID: task}}
			s := &Server{m: m, engine: NewEngine(m)}
			emit := func(id int64) db.Activity {
				return s.engine.emitActivity(task, db.Activity{Kind: "text", Worker: "fixture", Summary: strconv.FormatInt(id, 10)})
			}
			var barrier <-chan struct{}
			if sequence == "slow_consumer" {
				barrier = release
			}
			w, stop := reviewStream(t, s, "", barrier)
			if first := reviewRecv(t, w.flushes); first != "" {
				t.Fatalf("initial replay unexpectedly nonempty: %q", first)
			}
			expect := func(id int64) {
				t.Helper()
				prefix := fmt.Sprintf("id: %d\n", id)
				if body := reviewRecv(t, w.flushes); !strings.HasPrefix(body, prefix) {
					t.Fatalf("expected %q, got %q", prefix, body)
				}
			}
			var last int64
			switch sequence {
			case "ascending":
				for id := int64(1); id <= 3; id++ {
					if a := emit(id); a.ID != id {
						t.Fatalf("emit did not persist %d: %+v", id, a)
					}
					expect(id)
				}
				last = 3
			case "late_lower_id":
				lower := make(chan db.Activity, 1)
				go func() { lower <- emit(1) }()
				reviewRecv(t, allocated)
				if a := emit(2); a.ID != 2 {
					t.Fatal(a)
				}
				expect(2)
				finish.Do(func() { close(release) })
				if a := reviewRecv(t, lower); a.ID != 1 {
					t.Fatal(a)
				}
				if a := emit(3); a.ID != 3 {
					t.Fatal(a)
				}
				expect(3)
				last = 3
			case "slow_consumer":
				for id := int64(1); id <= 257; id++ {
					if a := emit(id); a.ID != id {
						t.Fatal(a)
					}
				}
				finish.Do(func() { close(release) })
				for id := int64(1); id <= 256; id++ {
					expect(id)
				}
				if a := emit(258); a.ID != 258 {
					t.Fatal(a)
				}
				expect(258)
				last = 258
			}
			stop()
			resumed, stopResumed := reviewStream(t, s, strconv.FormatInt(last, 10), nil)
			if body := reviewRecv(t, resumed.flushes); body != "" {
				t.Fatalf("resume after last id unexpectedly replayed: %q", body)
			}
			stopResumed()
			rows, cursor, err := task.Store.ActivityList(nil, 0, 500)
			if err != nil || int64(len(rows)) != last || cursor != last {
				t.Fatalf("fresh database replay has len=%d cursor=%d err=%v", len(rows), cursor, err)
			}
			if sequence == "late_lower_id" {
				t.Logf("live=[2 3], reconnect after 3=[], retained rows=%v", reviewIDs(rows))
			} else if sequence == "slow_consumer" {
				t.Logf("live=[1..256,258], reconnect after 258=[], retained rows=1..%d", len(rows))
			} else {
				t.Logf("live=[1 2 3], reconnect after 3=[], retained rows=%v", reviewIDs(rows))
			}
		})
	}
}

func TestReviewClaimFailureSignals(t *testing.T) {
	for _, experiment := range []struct {
		name        string
		wantQueries int
		wantExecs   int
	}{
		{"empty", 1, 0},
		{"read_error", 1, 0},
		{"lost_CAS", 1, 1},
		{"write_error", 1, 1},
		{"claimed", 1, 1},
	} {
		t.Run(experiment.name, func(t *testing.T) {
			queryN, execN := 0, 0
			database := newReviewDB(t, reviewConn{
				query: func(_ context.Context, query string, args []driver.NamedValue) (driver.Rows, error) {
					queryN++
					if !strings.Contains(query, "ORDER BY priority DESC, id ASC LIMIT $2") || args[1].Value != int64(20) {
						t.Fatalf("unexpected frontier query: %s, %v", query, args)
					}
					if experiment.name == "read_error" {
						return nil, errors.New("review read unavailable")
					}
					rows := &reviewRows{cols: make([]string, 10)}
					if experiment.name != "empty" {
						// Keep this fixture synchronized with scanNode and nodeCols.
						rows.data = [][]driver.Value{{int64(1), "intent", []byte("{}"), int64(0), "open", "", "", "", "", time.Unix(0, 0)}}
					}
					return rows, nil
				},
				exec: func(_ context.Context, query string, args []driver.NamedValue) (driver.Result, error) {
					execN++
					if !regexp.MustCompile("(?s)SET state='running'.+state='open'").MatchString(query) || args[0].Value != "fixture-worker" {
						t.Fatalf("unexpected claim query: %s, %v", query, args)
					}
					switch experiment.name {
					case "write_error":
						return nil, errors.New("review write unavailable")
					case "lost_CAS":
						return driver.RowsAffected(0), nil
					default:
						return driver.RowsAffected(1), nil
					}
				},
			})
			task := &Task{ID: "1", ExpID: 1, Store: database.Exploration(1)}
			node := NewEngine(nil).claimNext(task, "fixture-worker")
			if (node != nil) != (experiment.name == "claimed") || queryN != experiment.wantQueries || execN != experiment.wantExecs {
				t.Fatalf("node=%+v query=%d exec=%d", node, queryN, execN)
			}
			t.Logf("%s: claimed=%t queries=%d execs=%d", experiment.name, node != nil, queryN, execN)
		})
	}
}

type reviewProvider struct {
	stream func(context.Context, func(llm.StreamEvent, error) bool)
}

func (p reviewProvider) Stream(ctx context.Context, _ llm.CompletionRequest) iter.Seq2[llm.StreamEvent, error] {
	return func(yield func(llm.StreamEvent, error) bool) { p.stream(ctx, yield) }
}
func (p reviewProvider) Complete(ctx context.Context, _ llm.CompletionRequest) (llm.Message, string, llm.Usage, error) {
	return llm.Message{}, "", llm.Usage{}, errors.New("unexpected Complete")
}

func reviewWorkerFixture(t *testing.T) (*Server, *Task, func() string) {
	t.Helper()
	return reviewWorkerFixturePolicy(t, "")
}

func reviewWorkerFixturePolicy(t *testing.T, retryPolicy string) (*Server, *Task, func() string) {
	t.Helper()
	var mu sync.Mutex
	state := "running"
	activityID := int64(0)
	store := newReviewDB(t, reviewConn{
		query: func(_ context.Context, query string, args []driver.NamedValue) (driver.Rows, error) {
			mu.Lock()
			defer mu.Unlock()
			if strings.Contains(query, "FROM settings WHERE key") && args[0].Value == "llm_retry_policy" && retryPolicy != "" {
				return &reviewRows{cols: []string{"value"}, data: [][]driver.Value{{retryPolicy}}}, nil
			}
			if strings.Contains(query, "INSERT INTO activity") {
				activityID++
				return &reviewRows{cols: []string{"id"}, data: [][]driver.Value{{activityID}}}, nil
			}
			if strings.HasPrefix(strings.TrimSpace(query), "SELECT") || strings.HasPrefix(strings.TrimSpace(query), "WITH RECURSIVE withdrawn(") {
				return &reviewRows{}, nil
			}
			t.Errorf("unexpected SQL: %s", query)
			return nil, errors.New("unexpected SQL")
		},
		exec: func(_ context.Context, query string, args []driver.NamedValue) (driver.Result, error) {
			mu.Lock()
			defer mu.Unlock()
			if strings.Contains(query, "SET state=$1") && strings.Contains(query, "AND state=$4") {
				if expected := args[3].Value.(string); state != expected {
					return driver.RowsAffected(0), nil
				}
				state = args[0].Value.(string)
				return driver.RowsAffected(1), nil
			}
			if strings.Contains(query, "SET state='open'") && strings.Contains(query, "AND state='running'") {
				if state != "running" {
					return driver.RowsAffected(0), nil
				}
				state = "open"
				return driver.RowsAffected(1), nil
			}
			t.Errorf("unexpected SQL: %s", query)
			return nil, errors.New("unexpected SQL")
		},
	})
	task := &Task{ID: "1", ExpID: 1, Status: "running", Store: store.Exploration(1), Guard: guard.New(), notify: make(chan struct{}, 1)}
	m := &Manager{pg: store, tasks: map[string]*Task{"1": task}}
	return &Server{m: m, engine: NewEngine(m), chatBusy: map[string]bool{}}, task, func() string {
		mu.Lock()
		defer mu.Unlock()
		return state
	}
}

func reviewRunWorker(t *testing.T, ctx context.Context, s *Server, task *Task, provider reviewProvider, extras ...tool.CoreTool) <-chan struct{} {
	t.Helper()
	return reviewRunWorkerConfigured(t, ctx, s, task, provider, nil, 0, extras...)
}

func reviewRunWorkerConfigured(t *testing.T, ctx context.Context, s *Server, task *Task, provider reviewProvider, tx *transcript.Store, timeout time.Duration, extras ...tool.CoreTool) <-chan struct{} {
	t.Helper()
	tmp := t.TempDir()
	done := make(chan struct{})
	if !s.engine.beginTaskOperation(task.ID) {
		t.Fatal("task operation rejected")
	}
	go func() {
		defer close(done)
		defer s.engine.decInflight(task.ID)
		worker := agent.NewWorker(provider, "fixture", tmp, tx, 0, 1, extras...)
		worker.SetRunTimeout(timeout)
		intent := &db.Node{ID: 1, Kind: db.KindIntent, State: "running", Payload: []byte(`{"summary":"read fixture"}`)}
		s.engine.runIntent(ctx, task, "fixture", worker, intent, "", "")
	}()
	return done
}

func TestReviewInterruptedWorkerRecovery(t *testing.T) {
	for _, name := range []string{"natural_end", "task_pause", "shutdown_during_call", "shutdown_before_execute", "orphan_running"} {
		t.Run(name, func(t *testing.T) {
			s, task, state := reviewWorkerFixture(t)
			ctx, cancel := context.WithCancelCause(t.Context())
			defer cancel(agent.AbortShutdown)
			entered := make(chan struct{}, 1)
			p := reviewProvider{stream: func(ctx context.Context, yield func(llm.StreamEvent, error) bool) {
				entered <- struct{}{}
				if name == "natural_end" {
					if yield(llm.StreamEvent{Type: llm.SETextDelta, Text: "fixture done"}, nil) {
						yield(llm.StreamEvent{Type: llm.SEMessageDelta, StopReason: "end_turn"}, nil)
					}
					return
				}
				<-ctx.Done()
				yield(llm.StreamEvent{}, ctx.Err())
			}}
			terminal, reset := "done", int64(0)
			if name != "orphan_running" {
				if name == "shutdown_before_execute" {
					cancel(agent.AbortShutdown)
				}
				done := reviewRunWorker(t, ctx, s, task, p)
				if name != "shutdown_before_execute" {
					reviewRecv(t, entered)
				}
				switch name {
				case "task_pause":
					s.engine.Pause(task.ID, agent.AbortPausedByUser)
					terminal = "open"
				case "shutdown_during_call":
					cancel(agent.AbortShutdown)
					terminal = "blocked"
				case "shutdown_before_execute":
					terminal = "open"
				}
				reviewRecv(t, done)
				if name == "shutdown_before_execute" && len(entered) != 0 {
					t.Fatal("provider was invoked on pre-cancelled path")
				}
			} else {
				terminal, reset = "running", 1
			}
			if got := state(); got != terminal {
				t.Fatalf("before reset got %q want %q", got, terminal)
			}
			count, err := task.Store.ResetRunningIntents()
			wantAfter := terminal
			if reset != 0 {
				wantAfter = "open"
			}
			if err != nil || count != reset || state() != wantAfter {
				t.Fatalf("startup reset count=%d state=%q err=%v", count, state(), err)
			}
			t.Logf("before reset=%s, reset rows=%d, after reset=%s", terminal, count, state())
		})
	}
}

func TestReviewWorkControlCanReturnBeforeCallback(t *testing.T) {
	s, task, state := reviewWorkerFixture(t)
	ctx, cancel := context.WithCancelCause(t.Context())
	defer cancel(agent.AbortShutdown)
	ctx = agent.WithCallbackOwner(ctx, s.reserveBackgroundWork)
	entered := make(chan struct{})
	release := make(chan struct{})
	callbackDone := make(chan struct{})
	var once sync.Once
	releaseCallback := func() { once.Do(func() { close(release) }) }
	defer releaseCallback()
	probe := tool.Build(tool.Spec{Name: "ReviewNoop", Schema: map[string]any{"type": "object"}, Run: func(context.Context, json.RawMessage, *tool.ToolContext) (tool.Result, error) {
		close(entered)
		<-release
		close(callbackDone)
		return tool.Text("fixture done"), nil
	}})
	p := reviewProvider{stream: func(_ context.Context, yield func(llm.StreamEvent, error) bool) {
		for _, v := range []llm.StreamEvent{
			{Type: llm.SEToolUseStart, ToolID: "review-noop", ToolName: probe.Name()},
			{Type: llm.SEToolInputJSON, Text: "{}"},
			{Type: llm.SEMessageDelta, StopReason: "tool_use"},
		} {
			if !yield(v, nil) {
				return
			}
		}
	}}
	done := reviewRunWorker(t, ctx, s, task, p, probe)
	reviewRecv(t, entered)
	controlCtx, stop := context.WithTimeout(t.Context(), 3*time.Second)
	defer stop()
	if err := s.engine.ControlWork(controlCtx, 1, "pause"); err != nil {
		t.Fatal(err)
	}
	reviewRecv(t, done)
	if err := s.waitTaskQuiescent(controlCtx, task.ID); err != nil || state() != "paused" {
		t.Fatalf("quiescence=%v state=%q", err, state())
	}
	select {
	case <-callbackDone:
		t.Fatal("test lost held callback before ordinary pause returned")
	default:
	}
	cancel(agent.AbortShutdown)
	timeoutCtx, stopTimeout := context.WithTimeout(t.Context(), 50*time.Millisecond)
	defer stopTimeout()
	if err := s.DrainChats(timeoutCtx); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("shutdown did not wait on held callback: %v", err)
	}
	releaseCallback()
	reviewRecv(t, callbackDone)
	if err := s.DrainChats(controlCtx); err != nil {
		t.Fatalf("shutdown after callback returns: %v", err)
	}
	t.Log("pause and task quiescence returned while local no-op callback held; shutdown timed out on it, then joined after release")
}

func TestReviewDeadlineCommitFailure(t *testing.T) {
	for _, failFirst := range []bool{false, true} {
		t.Run(fmt.Sprintf("fail_first=%t", failFirst), func(t *testing.T) {
			var calls atomic.Int64
			var writes atomic.Int64
			var emitted atomic.Int64
			database := newReviewDB(t, reviewConn{
				query: func(_ context.Context, q string, _ []driver.NamedValue) (driver.Rows, error) {
					switch {
					case strings.Contains(q, "INSERT INTO activity"):
						id := emitted.Add(1)
						return &reviewRows{cols: []string{"id"}, data: [][]driver.Value{{id}}}, nil
					case strings.HasPrefix(strings.TrimSpace(q), "SELECT"), strings.HasPrefix(strings.TrimSpace(q), "WITH RECURSIVE withdrawn("):
						return &reviewRows{}, nil
					default:
						t.Errorf("unexpected query: %s", q)
						return nil, errors.New("unexpected query")
					}
				},
				exec: func(_ context.Context, q string, args []driver.NamedValue) (driver.Result, error) {
					if !strings.Contains(q, "status NOT IN ('done','failed','timeout')") || args[0].Value != "timeout" {
						t.Errorf("unexpected settlement SQL: %s args=%v", q, args)
						return nil, errors.New("unexpected settlement SQL")
					}
					if writes.Add(1) == 1 && failFirst {
						return nil, errors.New("review: one transient terminal write failure")
					}
					return driver.RowsAffected(1), nil
				},
			})
			task := &Task{ID: "1", ExpID: 1, Status: "running", TimeoutSeconds: 30, DeadlineAt: time.Now().Add(-5 * time.Second).Unix(), Store: database.Exploration(1), notify: make(chan struct{}, 1)}
			m := &Manager{pg: database, tasks: map[string]*Task{task.ID: task}}
			e := NewEngine(m)
			p := reviewProvider{stream: func(_ context.Context, yield func(llm.StreamEvent, error) bool) {
				calls.Add(1)
				if yield(llm.StreamEvent{Type: llm.SETextDelta, Text: "fixture complete"}, nil) {
					yield(llm.StreamEvent{Type: llm.SEMessageDelta, StopReason: "end_turn"}, nil)
				}
			}}
			planner := agent.NewPlanner(p, "fixture", t.TempDir(), nil, 0, 1)
			e.SetAuthoritativeAgentResolver(func(*Task) (*agent.Planner, *agent.Worker) { return planner, nil })
			e.startDeadlineCoordinator(t.Context(), task)
			e.runtimeMu.Lock()
			rt := e.runtimes[task.ID]
			e.runtimeMu.Unlock()
			rt.wg.Wait()
			e.startDeadlineCoordinator(t.Context(), task)
			e.settleTask(t.Context(), task)
			rt.wg.Wait()
			expected := "timeout"
			if failFirst {
				expected = "running"
			}
			if m.TaskStatus(task.ID) != expected || !e.isSettling(task.ID) || writes.Load() != 1 || calls.Load() != 1 || emitted.Load() == 0 {
				t.Fatalf("status=%q settling=%t writes=%d calls=%d emitted=%d", m.TaskStatus(task.ID), e.isSettling(task.ID), writes.Load(), calls.Load(), emitted.Load())
			}
			t.Logf("expired task: status=%s, settling=%t, upstream calls=%d, terminal write attempts=%d", m.TaskStatus(task.ID), e.isSettling(task.ID), calls.Load(), writes.Load())
		})
	}
}

func TestReviewBootstrapRestoreAndLocale(t *testing.T) {
	for _, name := range []string{"created_without_goal_rows", "created_with_goal_row", "timed_locale", "untimed_locale"} {
		t.Run(name, func(t *testing.T) {
			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()
			ctx = locale.WithLang(ctx, locale.Lang("en"))
			var commits atomic.Int64
			var calls atomic.Int64
			providerEntered := make(chan struct{}, 10)
			taskDone := make(chan struct{}, 10)
			timed := int64(0)
			if name == "timed_locale" {
				timed = 120
			}
			database := newReviewDB(t, reviewConn{
				query: func(_ context.Context, q string, args []driver.NamedValue) (driver.Rows, error) {
					switch {
					case strings.Contains(q, "FROM tasks WHERE deleted_at IS NULL") && strings.Contains(q, "ORDER BY (pinned_at"):
						return &reviewRows{cols: make([]string, 23), data: [][]driver.Value{{int64(1), "", nil, "", "read fixture", "preserve an objective", int64(1), "created", false, false, nil, "", nil, nil, "", nil, time.Unix(10, 0), nil, timed, int64(600), false, nil, nil}}}, nil
					case strings.Contains(q, "FROM settings WHERE key"):
						var value string
						switch args[0].Value {
						case "task_language.1":
							value = "ja"
						case settingWorkers:
							value = "1"
						default:
							return &reviewRows{}, nil
						}
						return &reviewRows{cols: []string{"value"}, data: [][]driver.Value{{value}}}, nil
					case strings.Contains(q, "kind='goal'") && strings.Contains(q, "SELECT EXISTS"):
						return &reviewRows{cols: []string{"exists"}, data: [][]driver.Value{{name == "created_with_goal_row"}}}, nil
					case strings.Contains(q, "state IN ('open','running')") && strings.Contains(q, "SELECT EXISTS"):
						return &reviewRows{cols: []string{"exists"}, data: [][]driver.Value{{false}}}, nil
					case strings.Contains(q, "INSERT INTO activity"):
						return &reviewRows{cols: []string{"id"}, data: [][]driver.Value{{int64(5)}}}, nil
					case strings.HasPrefix(strings.TrimSpace(q), "SELECT"), strings.HasPrefix(strings.TrimSpace(q), "WITH RECURSIVE withdrawn("):
						return &reviewRows{}, nil
					default:
						t.Errorf("unexpected query: %s", q)
						return nil, errors.New("unexpected query")
					}
				},
				exec: func(_ context.Context, q string, args []driver.NamedValue) (driver.Result, error) {
					switch {
					case strings.Contains(q, "SET state='open'") && strings.Contains(q, "AND state='running'"):
						return driver.RowsAffected(0), nil
					case strings.Contains(q, "status NOT IN ('done','failed','timeout')") && args[0].Value == "done":
						commits.Add(1)
						taskDone <- struct{}{}
						return driver.RowsAffected(1), nil
					default:
						t.Errorf("unexpected exec: %s args=%v", q, args)
						return nil, errors.New("unexpected exec")
					}
				},
			})
			m := &Manager{pg: database, tasks: map[string]*Task{}}
			s := &Server{m: m, engine: NewEngine(m), ctx: ctx}
			e := s.engine
			e.debounce = time.Millisecond
			p := reviewProvider{stream: func(_ context.Context, yield func(llm.StreamEvent, error) bool) {
				calls.Add(1)
				providerEntered <- struct{}{}
				if yield(llm.StreamEvent{Type: llm.SETextDelta, Text: "fixture complete"}, nil) {
					yield(llm.StreamEvent{Type: llm.SEMessageDelta, StopReason: "end_turn"}, nil)
				}
			}}
			if strings.HasPrefix(name, "created") {
				planner := agent.NewPlanner(p, "fixture", t.TempDir(), nil, 0, 1)
				e.SetAuthoritativeAgentResolver(func(*Task) (*agent.Planner, *agent.Worker) { return planner, nil })
			}
			s.restoreTaskRuntimes()
			defer e.StopTask("1")
			task, ok := m.Task("1")
			if !ok || !e.Started("1") || task.Goal == "" {
				t.Fatalf("restore fixture did not load and start: task=%+v found=%t started=%t", task, ok, e.Started("1"))
			}
			if strings.HasSuffix(name, "locale") {
				e.runtimeMu.Lock()
				got := locale.FromContext(e.runtimes["1"].ctx)
				e.runtimeMu.Unlock()
				want := locale.Lang("ja")
				if timed > 0 {
					want = locale.Lang("en")
				}
				if got != want || taskLanguage(database, "1") != locale.Lang("ja") {
					t.Fatalf("timeout=%d run locale=%q want=%q stored=%q", timed, got, want, taskLanguage(database, "1"))
				}
				t.Logf("timeout=%d s; task preference ja; runtime locale=%s", timed, got)
				return
			}
			if name == "created_without_goal_rows" {
				reviewRecv(t, taskDone)
			} else {
				reviewRecv(t, providerEntered)
			}
			cancel()
			e.StopTask("1")
			wantStatus, wantWrites, wantCalls := "done", int64(1), int64(0)
			if name == "created_with_goal_row" {
				wantStatus, wantWrites, wantCalls = "created", 0, 1
			}
			if got := m.TaskStatus("1"); got != wantStatus || commits.Load() != wantWrites || calls.Load() != wantCalls {
				t.Fatalf("status=%q want=%q writes=%d calls=%d", got, wantStatus, commits.Load(), calls.Load())
			}
			t.Logf("restore row status=created, raw objective present; after restore=%s, done writes=%d, provider calls=%d", wantStatus, commits.Load(), calls.Load())
		})
	}
}

func TestReviewLLMCallAccountingOverlap(t *testing.T) {
	const n = 120000
	for _, procs := range []int{1, min(4, runtime.NumCPU())} {
		t.Run(fmt.Sprintf("GOMAXPROCS=%d", procs), func(t *testing.T) {
			previous := runtime.GOMAXPROCS(procs)
			defer runtime.GOMAXPROCS(previous)
			var losses int
			for i := 0; i < n; i++ {
				e := NewEngine(nil)
				e.BeginLLMCall("1")
				start := make(chan struct{})
				var wg sync.WaitGroup
				wg.Go(func() { <-start; e.EndLLMCall("1") })
				wg.Go(func() { <-start; e.BeginLLMCall("1") })
				close(start)
				wg.Wait()
				switch got := e.ActiveLLMCalls("1"); got {
				case 1:
				case 0:
					losses++
				default:
					t.Fatalf("count after paired operations was %d", got)
				}
				e.EndLLMCall("1")
				if got := e.ActiveLLMCalls("1"); got != 0 {
					t.Fatalf("count after final release was %d", got)
				}
			}
			t.Logf("count expected=1 after 2 begins and 1 end; observed count=0 on %d/%d trials", losses, n)
		})
	}
}

func TestReviewHealthMirrorUpdateOrdering(t *testing.T) {
	for _, invert := range []bool{false, true} {
		t.Run(fmt.Sprintf("inverted=%t", invert), func(t *testing.T) {
			var persisted []driver.Value
			var scheduled []func()
			database := newReviewDB(t, reviewConn{
				query: func(_ context.Context, q string, _ []driver.NamedValue) (driver.Rows, error) {
					if !strings.Contains(q, "FROM llm_profile_health WHERE open_until IS NOT NULL") {
						return nil, fmt.Errorf("unexpected query: %s", q)
					}
					rows := &reviewRows{cols: make([]string, 6)}
					if persisted != nil {
						if until := persisted[3].(time.Time); until.After(time.Now()) {
							rows.data = append(rows.data, persisted)
						}
					}
					return rows, nil
				},
				exec: func(_ context.Context, q string, args []driver.NamedValue) (driver.Result, error) {
					switch {
					case strings.Contains(q, "INSERT INTO llm_profile_health"):
						persisted = []driver.Value{args[0].Value, args[1].Value, args[2].Value, args[3].Value, args[4].Value, time.Now()}
					case strings.Contains(q, "DELETE FROM llm_profile_health"):
						persisted = nil
					default:
						return nil, fmt.Errorf("unexpected exec: %s", q)
					}
					return driver.RowsAffected(1), nil
				},
			})
			start := func(work func()) bool { scheduled = append(scheduled, work); return true }
			registry := newLLMHealthRegistry(database, start)
			registry.Trip(1, "controlled failure", true)
			registry.Pass(1)
			if registry.IsOpen(1) || len(scheduled) != 2 {
				t.Fatalf("memory open=%t scheduled=%d", registry.IsOpen(1), len(scheduled))
			}
			order := []int{0, 1}
			if invert {
				order = []int{1, 0}
			}
			for _, i := range order {
				scheduled[i]()
			}
			reloaded := newLLMHealthRegistry(database, start)
			if reloaded.IsOpen(1) != invert {
				t.Fatalf("inverted=%t reloaded open=%t", invert, reloaded.IsOpen(1))
			}
			t.Logf("after logical trip/pass: in-memory open=%t, after asynchronous SQL order %v restored open=%t", registry.IsOpen(1), order, reloaded.IsOpen(1))
		})
	}
}

func TestReviewWorkerHistoryLoadFailure(t *testing.T) {
	for _, name := range []string{"missing", "valid", "truncated_tail"} {
		t.Run(name, func(t *testing.T) {
			known := "preserved fixture context"
			store := transcript.NewStore(t.TempDir())
			session := agent.WorkerSessionID(1, 1)
			path := store.MainPath(session)
			if name != "missing" {
				writer := store.NewWriter(session, "")
				writer.RecordMessage(llm.UserText(known), llm.Usage{})
				if err := writer.Err(); err != nil {
					t.Fatal(err)
				}
				records, err := store.Load(path)
				if err != nil || len(records) != 1 || records[0].Message.Text() != known {
					t.Fatalf("failed to create valid prefix: records=%v err=%v", records, err)
				}
				if name == "truncated_tail" {
					f, err := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0600)
					if err != nil {
						t.Fatal(err)
					}
					_, writeErr := io.WriteString(f, `{"type":`)
					if err = errors.Join(writeErr, f.Close()); err != nil {
						t.Fatal(err)
					}
				}
			}
			before, err := store.Load(path)
			if (err != nil) != (name == "truncated_tail") {
				t.Fatalf("fixture load: records=%d err=%v", len(before), err)
			}
			s, task, state := reviewWorkerFixture(t)
			messages := make(chan []llm.Message, 1)
			recorder := reviewRequestProvider{onStream: func(ctx context.Context, req llm.CompletionRequest, yield func(llm.StreamEvent, error) bool) {
				messages <- req.Messages
				if yield(llm.StreamEvent{Type: llm.SETextDelta, Text: "fixture complete"}, nil) {
					yield(llm.StreamEvent{Type: llm.SEMessageDelta, StopReason: "end_turn"}, nil)
				}
			}}
			provider := recorder
			done := make(chan struct{})
			runDir := t.TempDir()
			go func() {
				defer close(done)
				worker := agent.NewWorker(provider, "fixture", runDir, store, 0, 1)
				intent := &db.Node{ID: 1, Kind: db.KindIntent, State: "running", Payload: []byte(`{"summary":"read fixture"}`)}
				s.engine.runIntent(t.Context(), task, "fixture", worker, intent, "", "")
			}()
			seen := reviewRecv(t, messages)
			reviewRecv(t, done)
			sawPrefix := false
			for _, msg := range seen {
				sawPrefix = sawPrefix || strings.Contains(msg.Text(), known)
			}
			physical, physicalErr := os.ReadFile(path)
			after, afterErr := store.Load(path)
			if sawPrefix != (name == "valid") || state() != "done" || physicalErr != nil ||
				(afterErr != nil) != (name == "truncated_tail") ||
				(name != "missing" && !bytes.Contains(physical, []byte(known))) {
				t.Fatalf("state=%q prefix on wire=%t bytes=%d read=%v load=%v", state(), sawPrefix, len(physical), physicalErr, afterErr)
			}
			t.Logf("history=%s prefix on wire=%t state=%s readable records after=%d validation error=%v", name, sawPrefix, state(), len(after), afterErr)
		})
	}
}

type reviewRequestProvider struct {
	onStream func(context.Context, llm.CompletionRequest, func(llm.StreamEvent, error) bool)
}

func (p reviewRequestProvider) Stream(ctx context.Context, req llm.CompletionRequest) iter.Seq2[llm.StreamEvent, error] {
	return func(yield func(llm.StreamEvent, error) bool) { p.onStream(ctx, req, yield) }
}

func (p reviewRequestProvider) Complete(context.Context, llm.CompletionRequest) (llm.Message, string, llm.Usage, error) {
	return llm.Message{}, "", llm.Usage{}, errors.New("unexpected Complete")
}

func TestReviewModelCallOutlivesWorkerBudget(t *testing.T) {
	s, task, state := reviewWorkerFixture(t)
	deadlines := make(chan bool, 1)
	release := make(chan struct{})
	var once sync.Once
	finish := func() { once.Do(func() { close(release) }) }
	defer finish()
	parent, cancel := context.WithCancel(t.Context())
	defer cancel()
	provider := reviewProvider{stream: func(ctx context.Context, yield func(llm.StreamEvent, error) bool) {
		_, hasDeadline := ctx.Deadline()
		deadlines <- hasDeadline
		select {
		case <-release:
			if yield(llm.StreamEvent{Type: llm.SETextDelta, Text: "fixture complete"}, nil) {
				yield(llm.StreamEvent{Type: llm.SEMessageDelta, StopReason: "end_turn"}, nil)
			}
		case <-ctx.Done():
			yield(llm.StreamEvent{}, ctx.Err())
		}
	}}
	budget := 20 * time.Millisecond
	run := reviewRunWorkerConfigured(t, parent, s, task, provider, nil, budget)
	hasDeadline := reviewRecv(t, deadlines)
	after := time.NewTimer(3 * budget)
	defer after.Stop()
	select {
	case <-run:
		t.Fatalf("model stream returned before fixture release, state=%q", state())
	case <-after.C:
	}
	if hasDeadline || state() != "running" {
		t.Fatalf("at 3x budget state=%q deadline delivered to provider=%t", state(), hasDeadline)
	}
	finish()
	reviewRecv(t, run)
	if state() != "done" {
		t.Fatalf("after releasing text-only completion: %s", state())
	}
	t.Log("provider had no MaxDuration deadline; at 60ms still running on 20ms budget; after release done")
}

func TestReviewPausedIntentAndManualTaskCompletion(t *testing.T) {
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	committing := make(chan struct{}, 1)
	var storedIntent atomic.Value
	storedIntent.Store("paused")
	database := newReviewDB(t, reviewConn{
		query: func(_ context.Context, q string, _ []driver.NamedValue) (driver.Rows, error) {
			switch {
			case strings.Contains(q, "WHERE exploration_id=$1 AND kind='goal' AND state='open'"):
				return &reviewRows{cols: []string{"exists"}, data: [][]driver.Value{{false}}}, nil
			case strings.Contains(q, "WHERE exploration_id=$1 AND kind='intent' AND state IN ('open','running')"):
				state := storedIntent.Load().(string)
				return &reviewRows{cols: []string{"exists"}, data: [][]driver.Value{{state == "open" || state == "running"}}}, nil
			case strings.Contains(q, "FROM exploration_nodes WHERE id=$1 AND exploration_id=$2"):
				return &reviewRows{cols: make([]string, 10), data: [][]driver.Value{{int64(1), "intent", []byte("{}"), int64(0), storedIntent.Load(), "", "", "", "", time.Unix(0, 0)}}}, nil
			case strings.Contains(q, "INSERT INTO activity"):
				return &reviewRows{cols: []string{"id"}, data: [][]driver.Value{{int64(1)}}}, nil
			default:
				t.Errorf("unexpected query: %s", q)
				return nil, errors.New("unexpected query")
			}
		},
		exec: func(_ context.Context, q string, args []driver.NamedValue) (driver.Result, error) {
			switch {
			case strings.Contains(q, "status NOT IN ('done','failed','timeout')") && args[0].Value == "done":
				committing <- struct{}{}
				return driver.RowsAffected(1), nil
			case strings.Contains(q, "SET state=$1") && strings.Contains(q, "AND state=$4"):
				if !storedIntent.CompareAndSwap(args[3].Value, args[0].Value) {
					return driver.RowsAffected(0), nil
				}
				return driver.RowsAffected(1), nil
			default:
				t.Errorf("unexpected exec: %s args=%v", q, args)
				return nil, errors.New("unexpected exec")
			}
		},
	})
	task := &Task{ID: "1", ExpID: 1, Status: "running", Store: database.Exploration(1), notify: make(chan struct{}, 1)}
	m := &Manager{pg: database, tasks: map[string]*Task{task.ID: task}}
	s := &Server{m: m, engine: NewEngine(m)}
	s.engine.debounce = time.Millisecond
	s.engine.SetAuthoritativeAgentResolver(func(*Task) (*agent.Planner, *agent.Worker) { return new(agent.Planner), nil })
	done := make(chan struct{})
	go func() {
		defer close(done)
		s.engine.plannerLoop(ctx, task)
	}()
	task.Notify()
	reviewRecv(t, committing)
	cancel()
	reviewRecv(t, done)
	if got := m.TaskStatus(task.ID); got != "done" {
		t.Fatalf("manual task status with paused intent=%q", got)
	}
	out, err := s.applyIntentControl(t.Context(), task, 1, "resume", "", "")
	if err != nil || out.State != "open" || !isTerminalStatus(m.TaskStatus(task.ID)) || storedIntent.Load() != "open" {
		t.Fatalf("resume=%+v state=%s intent=%v err=%v", out, m.TaskStatus(task.ID), storedIntent.Load(), err)
	}
	t.Log("manual task went done with one paused intent; intent resume returned open while task remained done")
}

func TestReviewTimeoutTriggerWatermark(t *testing.T) {
	for _, forward := range []bool{true, false} {
		t.Run(fmt.Sprintf("ordered_by_task_id=%t", forward), func(t *testing.T) {
			states := map[int64]string{1: "running", 2: "running"}
			watermark := "0"
			var reads [][]int64
			database := newReviewDB(t, reviewConn{
				query: func(_ context.Context, q string, args []driver.NamedValue) (driver.Rows, error) {
					switch {
					case strings.Contains(q, "FROM scheduler_state") && args[0].Value == schedKeyLastTimeout:
						return &reviewRows{cols: []string{"value"}, data: [][]driver.Value{{watermark}}}, nil
					case strings.Contains(q, "WHERE status='timeout' AND deleted_at IS NULL AND id > $1"):
						result := &reviewRows{cols: []string{"id", "description", "goal"}}
						var found []int64
						for id := int64(1); id <= 2; id++ {
							if id > args[0].Value.(int64) && states[id] == "timeout" {
								result.data = append(result.data, []driver.Value{id, "fixture task", "fixture objective"})
								found = append(found, id)
							}
						}
						reads = append(reads, found)
						return result, nil
					case strings.Contains(q, "FROM settings WHERE key"):
						return &reviewRows{}, nil
					default:
						return nil, fmt.Errorf("unexpected query: %s", q)
					}
				},
				exec: func(_ context.Context, q string, args []driver.NamedValue) (driver.Result, error) {
					if !strings.Contains(q, "INSERT INTO scheduler_state") || args[0].Value != schedKeyLastTimeout {
						return nil, fmt.Errorf("unexpected exec: %s", q)
					}
					watermark = args[1].Value.(string)
					return driver.RowsAffected(1), nil
				},
			})
			// Discovery only. The server has no chat provider so dispatch does no work.
			server := &Server{m: &Manager{pg: database}}
			sc := newScheduler(server)
			ids := []int64{1, 2}
			if !forward {
				ids = []int64{2, 1}
			}
			for _, id := range ids {
				states[id] = "timeout"
				sc.fireTaskTimeouts([]*db.AgentTrigger{{OnTaskTimeout: true, AgentKey: "fixture"}})
			}
			observations := append([][]int64(nil), reads...)
			all, err := database.TimedOutTasksSince(0)
			if err != nil || len(all) != 2 || watermark != "2" || len(observations) != 2 || len(observations[0]) != 1 || observations[0][0] != ids[0] || (len(observations[1]) == 1) != forward {
				t.Fatalf("ids=%v reads=%v watermark=%s all=%v err=%v", ids, observations, watermark, all, err)
			}
			t.Logf("timeout transitions=%v, discovered per tick=%v, persisted cursor=%s, full query sees %d rows", ids, observations, watermark, len(all))
		})
	}
}

func TestReviewLayeredRetryCounts(t *testing.T) {
	for _, tc := range []struct {
		status         int
		intent         int
		wantHTTP       int64
		wantSelections int64
	}{
		{503, 1, 8, 2},
		{503, -1, 4, 1},
		{400, 1, 2, 2},
		{400, -1, 1, 1},
	} {
		t.Run(fmt.Sprintf("status=%d/intent_retries=%d", tc.status, tc.intent), func(t *testing.T) {
			var hits atomic.Int64
			var selections atomic.Int64
			upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				hits.Add(1)
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(tc.status)
				io.WriteString(w, `{"error":{"message":"synthetic provider response","type":"fixture"}}`)
			}))
			defer upstream.Close()
			cfg := agent.ConfigFrom("openai", "review-fixture", upstream.URL+"/v1", "", "")
			cfg.Retry = agent.RetryConfig{ConnectAttempts: 1, ConnectInterval: time.Millisecond, EmptyAttempts: -1, StreamAttempts: 1, StreamInterval: time.Millisecond}
			inner, err := cfg.NewProvider()
			if err != nil {
				t.Fatal(err)
			}
			p := reviewRequestProvider{onStream: func(ctx context.Context, req llm.CompletionRequest, yield func(llm.StreamEvent, error) bool) {
				for ev, err := range streamTaskLLM(ctx, "1", req, taskLLMStreamHooks{
					current: func() (taskLLMSelection, error) {
						selections.Add(1)
						return taskLLMSelection{provider: inner, retry: cfg.Retry}, nil
					},
				}) {
					if !yield(ev, err) {
						return
					}
				}
			}}
			s, task, state := reviewWorkerFixturePolicy(t, fmt.Sprintf(`{"intent":{"attempts":%d,"interval_ms":1}}`, tc.intent))
			done := make(chan struct{})
			ctx, cancel := context.WithTimeout(t.Context(), 12*time.Second)
			defer cancel()
			runDir := t.TempDir()
			go func() {
				defer close(done)
				worker := agent.NewWorker(p, "fixture", runDir, nil, 0, 1)
				intent := &db.Node{ID: 1, Kind: db.KindIntent, State: "running", Payload: []byte(`{"summary":"read fixture"}`)}
				s.engine.runIntent(ctx, task, "fixture", worker, intent, "", "")
			}()
			select {
			case <-done:
			case <-ctx.Done():
				<-done // join context-aware provider and settlement before cleanup
				t.Fatalf("fixture deadline after %d HTTP hits and %d selections: %v", hits.Load(), selections.Load(), ctx.Err())
			}
			if state() != "blocked" || hits.Load() != tc.wantHTTP || selections.Load() != tc.wantSelections {
				t.Fatalf("http=%d selections=%d state=%s", hits.Load(), selections.Load(), state())
			}
			t.Logf("HTTP %d with intent retries=%d: HTTP attempts=%d, logical worker selections=%d, state=%s", tc.status, tc.intent, hits.Load(), selections.Load(), state())
		})
	}
}

func TestReviewNonQuotaStreamRetryAfterTool(t *testing.T) {
	for _, retry := range []int{-1, 1} {
		t.Run(fmt.Sprintf("intent_retries=%d", retry), func(t *testing.T) {
			var attempted, handled atomic.Int64
			toolRan := make(chan struct{}, 4)
			probe := tool.Build(tool.Spec{Name: "ReviewLocalCounter", Schema: map[string]any{"type": "object"},
				Run: func(context.Context, json.RawMessage, *tool.ToolContext) (tool.Result, error) {
					handled.Add(1)
					toolRan <- struct{}{}
					return tool.Text("counted"), nil
				},
			})
			p := reviewRequestProvider{onStream: func(ctx context.Context, req llm.CompletionRequest, yield func(llm.StreamEvent, error) bool) {
				call := attempted.Add(1)
				fixture := reviewProvider{stream: func(ctx context.Context, yield func(llm.StreamEvent, error) bool) {
					for _, event := range []llm.StreamEvent{
						{Type: llm.SEToolUseStart, ToolID: fmt.Sprintf("review-counter-%d", call), ToolName: probe.Name()},
						{Type: llm.SEToolInputJSON, Text: "{}"},
						{Type: llm.SEMessageDelta, StopReason: "tool_use"},
					} {
						if !yield(event, nil) {
							return
						}
					}
					select {
					case <-toolRan:
					case <-ctx.Done():
						return
					case <-time.After(2 * time.Second):
						t.Error("local no-op did not run before modeled failure")
					}
					yield(llm.StreamEvent{}, io.ErrUnexpectedEOF)
				}}
				for ev, err := range streamTaskLLM(ctx, "1", req, taskLLMStreamHooks{current: func() (taskLLMSelection, error) {
					return taskLLMSelection{provider: fixture, retry: agent.RetryConfig{StreamAttempts: 1, StreamInterval: time.Millisecond}}, nil
				}}) {
					if !yield(ev, err) {
						return
					}
				}
			}}
			s, task, state := reviewWorkerFixturePolicy(t, fmt.Sprintf(`{"intent":{"attempts":%d,"interval_ms":1}}`, retry))
			done := make(chan struct{})
			tmp := t.TempDir()
			store := transcript.NewStore(t.TempDir())
			go func() {
				defer close(done)
				worker := agent.NewWorker(p, "fixture", tmp, store, 0, 1, probe)
				intent := &db.Node{ID: 1, Kind: db.KindIntent, State: "running", Payload: []byte(`{"summary":"read fixture"}`)}
				s.engine.runIntent(t.Context(), task, "fixture", worker, intent, "", "")
			}()
			reviewRecv(t, done)
			want := int64(1 + max(retry, 0))
			recs, err := store.Load(store.MainPath(agent.WorkerSessionID(1, 1)))
			if err != nil || int64(len(recs)) != want || attempted.Load() != want || handled.Load() != want || state() != "blocked" {
				t.Fatalf("model attempts=%d tool calls=%d saved messages=%d state=%s err=%v", attempted.Load(), handled.Load(), len(recs), state(), err)
			}
			for _, rec := range recs {
				if rec.Message == nil || rec.Message.Role != llm.RoleUser || len(rec.Message.ToolUses()) != 0 {
					t.Fatalf("unexpected recorded partial exchange: %+v", rec)
				}
			}
			t.Logf("ordinary post-tool stream error: worker provider attempts=%d, local no-op effects=%d, transcript prompts=%d, terminal=%s", attempted.Load(), handled.Load(), len(recs), state())
		})
	}
}

func TestReviewTaskFileStageProcessExit(t *testing.T) {
	const childRoot = "SCOPEWEAVER_REVIEW_FILE_STAGE_CHILD"
	if root := os.Getenv(childRoot); root != "" {
		stage, err := stageTaskFiles(root, "1", 1)
		if err != nil || !stage.deleted {
			t.Fatalf("child task staging: %v", err)
		}
		// Model an exit between the local rename step and the DB operation.
		os.Exit(0)
	}
	for _, interrupted := range []bool{false, true} {
		t.Run(fmt.Sprintf("interrupt=%t", interrupted), func(t *testing.T) {
			root := t.TempDir()
			taskDir := filepath.Join(root, "tasks", "1")
			if err := os.MkdirAll(taskDir, 0700); err != nil {
				t.Fatal(err)
			}
			source := filepath.Join(taskDir, "fixture.txt")
			if err := os.WriteFile(source, []byte("retained local task output"), 0600); err != nil {
				t.Fatal(err)
			}
			if !interrupted {
				stage, err := stageTaskFiles(root, "1", 1)
				if err != nil {
					t.Fatal(err)
				}
				if err := stage.rollback(); err != nil {
					t.Fatal(err)
				}
				b, err := os.ReadFile(source)
				if err != nil || string(b) != "retained local task output" {
					t.Fatalf("rollback bytes=%q err=%v", b, err)
				}
				t.Log("in-process stage rollback restored the task file")
				return
			}
			binary, err := os.Executable()
			if err != nil {
				t.Fatal(err)
			}
			ctx, cancel := context.WithTimeout(t.Context(), 10*time.Second)
			defer cancel()
			child := exec.CommandContext(ctx, binary, "-test.run=^TestReviewTaskFileStageProcessExit$")
			child.Env = append(os.Environ(), childRoot+"="+root)
			if out, err := child.CombinedOutput(); err != nil {
				t.Fatalf("local staging child: %v, %s", err, out)
			}
			if err := recoverTaskArchiveStages(root, nil); err != nil {
				t.Fatal(err)
			}
			if err := recoverTaskArchiveRestoreStages(root, nil); err != nil {
				t.Fatal(err)
			}
			if _, err := os.Stat(source); !errors.Is(err, os.ErrNotExist) {
				t.Fatalf("original task file stat after child exit: %v", err)
			}
			staged, err := filepath.Glob(filepath.Join(root, ".delete-staging", "task-1-*", "0-1", "fixture.txt"))
			if err != nil || len(staged) != 1 {
				t.Fatalf("staged=%v err=%v", staged, err)
			}
			b, err := os.ReadFile(staged[0])
			if err != nil || string(b) != "retained local task output" {
				t.Fatalf("staged bytes=%q err=%v", b, err)
			}
			t.Log("child exited after moves and before DB work; normal path absent, intact file still in ordinary delete stage after archive recovery")
		})
	}
}

func TestReviewBootstrapExecutionContextReuse(t *testing.T) {
	engine := NewEngine(nil)
	task := &Task{ID: "1", notify: make(chan struct{}, 1)}
	serverRoot := locale.WithLang(t.Context(), locale.Lang("en"))
	bootstrap := engine.execContextFor(serverRoot, task.ID)
	decomposition := locale.WithLang(bootstrap, locale.Lang("ja"))
	localizedRunRoot := locale.WithLang(serverRoot, locale.Lang("ja"))
	reused := engine.execContextFor(localizedRunRoot, task.ID)
	if locale.FromContext(decomposition) != locale.Lang("ja") || reused != bootstrap || locale.FromContext(reused) != locale.Lang("en") {
		t.Fatalf("decomposition=%s, carrier reused=%t, run=%s", locale.FromContext(decomposition), reused == bootstrap, locale.FromContext(reused))
	}
	engine.Pause(task.ID, agent.AbortPausedByUser)
	engine.Resume(task)
	recreated := engine.execContextFor(localizedRunRoot, task.ID)
	if recreated == bootstrap || locale.FromContext(recreated) != locale.Lang("ja") {
		t.Fatalf("pause replacement reused=%t, language=%s", recreated == bootstrap, locale.FromContext(recreated))
	}
	t.Log("bootstrap setup keeps English cached, Japanese copy applies locally, later reused run gets English until pause invalidates cached context")
}
~~~
<!-- END SCOPEWEAVER CONTROL SOURCE -->

</details>
