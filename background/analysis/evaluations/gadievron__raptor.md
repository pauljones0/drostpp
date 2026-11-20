# RAPTOR architecture and reliability evaluation

## 1. Snapshot, scope, and elapsed-time evidence

| Item | Evidence |
| --- | --- |
| Checkout | `repos/gadievron__raptor`, commit `ad278b6e0afecfe7cf31afdc7d49749e13b598cf`, “docs: pin container instructions to the published image” |
| Start | 2026-11-19 06:46:49 UTC, epoch 1795070809. Exact HEAD matched and porcelain with all untracked files was empty. |
| End | 2026-11-19 07:16:57 UTC, epoch 1795072617. Exact requested HEAD matched. Porcelain including untracked and ignored files was empty. Staged and unstaged diffs were empty. The isolated experiment directory was removed. |
| Elapsed | **30 minutes 8 seconds (30.13 minutes)**. Source tracing, test execution, fixture diagnosis, fault injection, and report verification occupied the interval. |
| Scope | Local launcher and command handoffs, audit coordination, provider and worker ownership, persisted state, scheduling, and the dependency-analysis pipeline as a second execution surface. Tests used inert review handlers and synthetic source. GUI, live services, and security-testing operations were outside scope. |
| Test isolation | Pinned local scratch checkout inside a fresh network namespace with loopback only, isolated PID and filesystem views, empty inherited environment, fresh Home, read-only system/cache inputs, and no credentials. The assigned checkout remained untouched. |

Activity checkpoints in UTC were 06:46:49 checkout and rubric, 06:50:57 offline dependency and test collection triage, 06:53:57 graph and core audit tests, 06:59:00 subprocess restart and parser controls, 07:04:56 lifecycle failure and SDK diagnostics, and 07:08:09 projection crash and tool-worker controls. 07:11:45 source-link and suite reconciliation, 07:14:13 lock fault and reentrancy comparisons, and 07:16:57 final checkout and report integrity checks. The protocol groups strengths and weaknesses together. The ten sections below split them, consistent with the neighboring evaluation. [Evaluation protocol](./README.md:6) [Adjacent report](./usestrix__strix.md:1)

**Assessment.** RAPTOR is a file-backed local control plane with multiple entry points. The audit command has the strongest recovery model. It combines an exclusive run owner, deterministic plan reconstruction, provenance-bound review evidence, and an attempt ledger written before paid dispatch. The most consequential flaws appear when software crosses ownership boundaries. The audit executor can abandon live callbacks after a coordinator error, the CLI can report exit zero after failing to seal run status, and completed runs can remain absent from project projections until reprocessed. The tests confirm substantial offline behavior. The package cache could only support compatible substitutes for some pinned dependencies, which limits confidence in the exact provider and native-parser stacks. [Run ownership](repos/gadievron__raptor/core/audit/run_lock.py:116) [Resume planning](repos/gadievron__raptor/core/audit/gaps.py:3831) [Prepared attempts](repos/gadievron__raptor/core/audit/attempt_reservations.py:280) [Executor cleanup](repos/gadievron__raptor/core/audit/executor.py:312) [CLI finalization](repos/gadievron__raptor/libexec/raptor-audit:2614) [Lifecycle commit](repos/gadievron__raptor/core/run/metadata.py:2090)

## 2. Core architecture and end-to-end control/data flow

1. **Entry points and work ownership.** The shell launcher assembles runtime policy and the session environment. The external assistant harness owns its conversation and hook lifecycle. Python commands own their run directories and local work. The lifecycle hook is secondary to a completion claimed by the owning command. `raptor.py`, the audit CLI, the SCA pipeline, and the phased agentic runner have separate roots, with shared libraries for run state, adapters, and reporting. Terms such as “agent” cover several lifetimes here. A harness session hosts conversation, an audit task is a reviewable source unit, a study job generates auxiliary context, and a provider attempt is the accounting and admission unit. Those owners explain the division between CLI status, review coverage, and model usage. [Architecture](repos/gadievron__raptor/docs/architecture.md:56) [Launcher](repos/gadievron__raptor/bin/raptor:888) [Session environment](repos/gadievron__raptor/bin/raptor:1036) [Harness hooks](repos/gadievron__raptor/.claude/settings.json:82) [Coverage hook](repos/gadievron__raptor/plugins/coverage/hooks/hooks.json:2) [Python entry](repos/gadievron__raptor/raptor.py:627) [Phased runner](repos/gadievron__raptor/raptor_agentic.py:4526) [Hook precedence tests](repos/gadievron__raptor/core/run/tests/test_hook_finalize_precedence.py:231)

2. **Audit start and planning.** The audit entry prepares a run or reopens an eligible one. The run lock controls same-directory ownership while metadata and snapshot/pinning checks bind the source, project, and command. The CLI forms pipeline options and calls the orchestrator. Planning inventories source spans and constructs a review checklist and gap plan, joins source and previous coverage, classifies what needs work, and assigns bounded study passes where the run policy allows. The review graph turns planned work into keyed review units with dependencies, ranks and branch labels. Fresh, project-reuse and interrupted-run paths have different evidence eligibility. The run reconstructs a plan and proves prior work against it when resuming. [Audit entry](repos/gadievron__raptor/libexec/raptor-audit:1755) [Pipeline handoff](repos/gadievron__raptor/libexec/raptor-audit:2284) [Pipeline options](repos/gadievron__raptor/core/audit/pipeline.py:54) [Pin verification](repos/gadievron__raptor/core/run/pin.py:469) [Orchestrator entry](repos/gadievron__raptor/core/audit/orchestrator.py:2246) [Planning](repos/gadievron__raptor/core/audit/orchestrator.py:9015) [Gap selection](repos/gadievron__raptor/core/audit/gaps.py:3651) [Resume eligibility](repos/gadievron__raptor/core/audit/gaps.py:3831) [Graph construction](repos/gadievron__raptor/core/audit/orchestrator.py:9758)

3. **Scheduling and execution.** `TaskGraph` tracks dependencies, readiness and completion. Main audit enables a two-lane admission queue for fresh initial work and continuations, with bounded priority boost and a 3-to-1 preference under contention. A private asyncio loop dispatches ready graph work, runs blocking review handlers in a thread pool, and refills as results release graph capacity. A synchronous path remains. Review concurrency and provider concurrency are separate boundaries. The study coordinator owns a separate job runtime, deduplicates per lineage and uses completion callbacks to expire work ownership. Parser workers are process-owned, with a startup probe, finite polls, stuck-worker termination, per-file retry, and a recorded gap if recovery is incomplete. The SCA pipeline gives a separate example of staged ownership, including a cache session limited by an `ExitStack` and explicit states for unresolved offline dependencies. [Task graph](repos/gadievron__raptor/core/audit/task_graph.py:191) [Fairness](repos/gadievron__raptor/core/audit/review_fairness.py:26) [Executor loop](repos/gadievron__raptor/core/audit/executor.py:701) [Blocking handoff](repos/gadievron__raptor/core/audit/executor.py:969) [Main audit dispatch](repos/gadievron__raptor/core/audit/orchestrator.py:9987) [Study coordinator](repos/gadievron__raptor/core/audit/knowledge_runtime.py:1959) [Parser supervisor](repos/gadievron__raptor/core/inventory/builder.py:337) [Per-file retry](repos/gadievron__raptor/core/inventory/builder.py:446) [SCA cache ownership](repos/gadievron__raptor/packages/sca/pipeline.py:428)

   The process supervisor publishes a handle after exec readiness and makes the parent-death policy explicit. It owns teardown. Security confinement is a distinct analyzer boundary, and the default analyzer policy refuses when the sandbox interface is unavailable. The dispatcher spawn helper passes a scoped descriptor, closes the parent's copy after either successful transfer or spawn failure, and leaves the returned child handle to its caller. [Supervisor contract](repos/gadievron__raptor/core/sandbox/supervised.py:1975) [Analyzer boundary](repos/gadievron__raptor/core/run/sandbox_policy.py:55) [Dispatcher descriptor ownership](repos/gadievron__raptor/core/llm/dispatcher/spawn.py:101)

4. **Provider and tool boundaries.** Model routing and provider capabilities feed a common client. The client applies caching, schema/cost policy and retries, then calls an adapter. Managed audit binds admission and reconciliation hooks before a prepared provider request can reach transport. Recent amounts and leases matter independently of scheduler work-unit completion. The optional local dispatcher can own provider connectivity for workers by handing them a scoped capability and route. Its broker tracks whether response delivery has started and has a distinct retry boundary for route failures before headers. A transport retry boundary is an observation at this hop, and billing can still be ambiguous upstream. The separate typed tool loop represents messages, calls, results, stop reasons and events. Its fixed set of tools and callbacks is scoped to a phase invocation. [Provider capabilities](repos/gadievron__raptor/core/llm/providers.py:327) [Client policy](repos/gadievron__raptor/core/llm/client.py:2933) [Prepared hooks](repos/gadievron__raptor/core/llm/prepared_admission.py:24) [Pipeline preflight](repos/gadievron__raptor/core/audit/pipeline.py:336) [Dispatch ownership](repos/gadievron__raptor/core/llm/dispatcher/lifecycle.py:77) [FD handoff](repos/gadievron__raptor/core/llm/dispatcher/spawn.py:101) [Retry boundary](repos/gadievron__raptor/core/llm/dispatcher/server.py:798) [Tool contracts](repos/gadievron__raptor/core/llm/tool_use/types.py:419) [Phase scope](repos/gadievron__raptor/core/llm/tool_use/loop.py:192)

5. **Results, progress and closure.** A handler produces a result; the collector serializes batches and acknowledges what reached persistent publication. Downstream coverage accounting checks the acknowledged row against its binding. The run journal and validated checkpoint support replay into a rebuilt plan. Heartbeats, report summaries, sharded records, dispatcher decisions, and usage telemetry expose separate views of the run. Terminal work proceeds through admission stop, drain or interrupt, journal/log flush, report and metadata finalization, then project merges and derived coverage. Resume reads authoritative run artifacts and rederives unfinished work, reconciling paid settlement against retained trails and budget floors. Project views may lag that run-local truth. [Collector queue](repos/gadievron__raptor/core/audit/collector.py:967) [Batch publication](repos/gadievron__raptor/core/audit/collector.py:1134) [Acknowledgment binding](repos/gadievron__raptor/core/audit/orchestrator.py:14799) [Journal](repos/gadievron__raptor/core/coverage/journal.py:466) [Checkpoint](repos/gadievron__raptor/core/coverage/journal_checkpoint.py:328) [Usage recovery](repos/gadievron__raptor/core/audit/resume.py:286) [Heartbeat](repos/gadievron__raptor/core/audit/heartbeat.py:78) [Sharded log](repos/gadievron__raptor/core/audit/record.py:431) [Project projection order](repos/gadievron__raptor/core/run/metadata.py:2090)

## 3. Why the design works and its governing invariants

| Invariant | Mechanism and consequence |
| --- | --- |
| One physical run owner normally governs recovery and shutdown. | A run-scoped lock spans the live cycle. Process identity incorporates generation evidence such as start time and boot or namespace identity when available. Project admission uses a distinct short gate. Command and run pin checks guard lifecycle writes. Same-directory recovery can reject a live owner even when status logs are stale. An in-process re-entry is an intentional no-op, and filesystem create failures can produce a loud unlocked fallback. An embedding caller must serialize invocations that share a run directory. [Run lease](repos/gadievron__raptor/core/audit/run_lock.py:116) [Re-entry](repos/gadievron__raptor/core/audit/run_lock.py:504) [Create failure](repos/gadievron__raptor/core/audit/run_lock.py:468) [Project gate](repos/gadievron__raptor/core/run/metadata.py:1004) [Resume admission](repos/gadievron__raptor/core/run/resume.py:97) [Pin](repos/gadievron__raptor/core/run/pin.py:329) |
| Admission follows retained dependencies and a key has one live ready entry. | The graph tracks pending prerequisites and breaks detected cycles before execution. The freshness/continuation queue accounts for updates and retirements of ready items. Priorities affect admission order, while worker latency determines completion order. Exhaustive isolated four-node fixtures supported dependency and single-dispatch behavior. [Graph](repos/gadievron__raptor/core/audit/task_graph.py:191) [Ready path](repos/gadievron__raptor/core/audit/task_graph.py:235) [Lane retirement](repos/gadievron__raptor/core/audit/review_fairness.py:75) [Lane selection](repos/gadievron__raptor/core/audit/review_fairness.py:89) |
| Restart credit requires attributable work publication. | Findings and progress alone do not settle units. Reuse considers the current source and foundation, journal/checkpoint eligibility, and acknowledged scope. Reconstruction lets it discard unsafe credit and recompute outstanding units without trusting the old scheduler heap. A quiesce owner pauses writers, takes a bounded checkpoint and hands admission back on recovery. [Reuse policy](repos/gadievron__raptor/core/audit/gaps.py:3831) [Acknowledgment](repos/gadievron__raptor/core/audit/orchestrator.py:14816) [Quiesce ownership](repos/gadievron__raptor/core/audit/journal_quiesce.py:90) [Checkpoint publication](repos/gadievron__raptor/core/audit/journal_quiesce.py:263) |
| A possibly paid attempt occupies capacity before request dispatch. | Admission appends a qualified identity and reservation, then a terminal action records settlement or explicit non-consumption. On interruption an unresolved hold can survive. Recovery combines budget floors using the maximum across overlapping evidence and separately treats pending holds. This preserves a conservative spend bound while avoiding duplicate attribution. [Append](repos/gadievron__raptor/core/audit/attempt_reservations.py:246) [Reservation](repos/gadievron__raptor/core/audit/attempt_reservations.py:280) [Prepared scope](repos/gadievron__raptor/core/llm/prepared_admission.py:70) [Reconciliation](repos/gadievron__raptor/core/audit/resume.py:286) |
| Work retirement follows the resource owner. | Study admissions deduplicate live jobs by lineage. Callable termination owns release, and a late result has a publication gate. The parser worker supervisor can terminate a process; a thread handler admits only cooperative physical cancellation. Process-local throttling deliberately coordinates admissions across callers. [Study ledger](repos/gadievron__raptor/core/audit/study_job_ledger.py:81) [Study terminal gate](repos/gadievron__raptor/core/audit/knowledge_runtime.py:2093) [Parser worker retirement](repos/gadievron__raptor/core/inventory/builder.py:255) [Tool timeout ownership](repos/gadievron__raptor/core/llm/tool_use/loop.py:1385) [Shared throttle](repos/gadievron__raptor/core/llm/throttle.py:398) |
| Operational progress and terminal completeness are independent. | The heartbeat writes status and progress snapshots, and the audit report classifies complete or explicit partial states using terminal audit data. Project index and coverage are derived from committed run material. A budget- or duration-limited partial run can be a legitimate command result. [Heartbeat write](repos/gadievron__raptor/core/audit/heartbeat.py:126) [Run progress guard](repos/gadievron__raptor/core/audit/orchestrator.py:711) [Completeness reporting](repos/gadievron__raptor/core/audit/report.py:1063) [Projection repair](repos/gadievron__raptor/core/run/metadata.py:2228) |

The resulting execution model is restartable work with guarded publication, selective reuse, and conservative handling of uncertain billing. It earns strong process-crash behavior from local records and owners. The crash and timeout controls below identify where guarantees end.

## 4. Strengths

- **Recovery is integrated into the actual command lifecycle.** The tested cold-resume path runs a CLI subprocess, kills it, starts a fresh process and checks genuine run artifacts. Signal handling has separate tests for graceful salvage, and lock tests use a real competing process while draining. This is stronger than asserting only the state of an in-memory executor. [Cold resume test](repos/gadievron__raptor/core/audit/tests/test_resume_e2e.py:325) [Signal grace test](repos/gadievron__raptor/core/audit/tests/test_sigterm_grace.py:250) [Competing owner test](repos/gadievron__raptor/core/audit/tests/test_run_lock.py:591)
- **The design separates checkpoints, source authority and derived data.** Full-record validation gates resume credit. Checkpoints and coverage folds have verification and finite-work machinery. Explicit projection repair is idempotent for trusted runs. The ability to rebuild a missing project entry from the run journal was measured. [Journal fold](repos/gadievron__raptor/core/coverage/journal.py:1664) [Checkpoint validation](repos/gadievron__raptor/core/coverage/journal_checkpoint.py:370) [Eligibility](repos/gadievron__raptor/core/audit/gaps.py:3831) [Projection repair](repos/gadievron__raptor/core/run/metadata.py:2228)
- **Concurrency controls address distinct bottlenecks.** Review slots, LLM capacity, study leases and parser workers have different lifetimes and observability. Admission fairness mitigates a continual stream of newly ready units. Tests cover descriptor ownership, cancellation preserving the primary error, and reaping stuck parser children. [Fairness implementation](repos/gadievron__raptor/core/audit/review_fairness.py:89) [Provider throttle](repos/gadievron__raptor/core/llm/throttle.py:269) [Study job runtime](repos/gadievron__raptor/core/audit/knowledge_runtime.py:1570) [Supervisor cancellation tests](repos/gadievron__raptor/core/sandbox/tests/test_supervised_ready_cancellation.py:1) [Parser ownership tests](repos/gadievron__raptor/core/sandbox/tests/test_parser_worker_ownership.py:1)
- **Accounting and data quality degrade explicitly in many paths.** Typed budget errors distinguish limits, malformed or interrupted paid responses have conservative handling, deliverable reports surface partial coverage, and subprocess fixtures test durable prepared attempts. The SCA pipeline has meaningful offline plan, build-information collection and verification behavior, including limitations when evidence is unavailable. [Budget error types](repos/gadievron__raptor/core/llm/budget_errors.py:12) [Attempt recovery tests](repos/gadievron__raptor/core/audit/tests/test_prepared_attempt_recovery.py:1) [Partial reporting](repos/gadievron__raptor/core/audit/report.py:1063) [SCA pipeline](repos/gadievron__raptor/packages/sca/pipeline.py:307) [SCA end-to-end tests](repos/gadievron__raptor/packages/sca/tests/test_e2e_pipeline.py:1)
- **Observability has independent channels.** Heartbeats surface liveness, append-only records identify audit decisions, the broker logs routing reasons, and receipts preserve per-attempt accounting identity. Optional client telemetry is best-effort. These views permit separating scheduling delay, provider use and result publication in a local incident. [Heartbeat](repos/gadievron__raptor/core/audit/heartbeat.py:57) [Record writer](repos/gadievron__raptor/core/audit/record.py:239) [Decision log](repos/gadievron__raptor/core/dispatch/broker/decision_log.py:29) [Telemetry emission](repos/gadievron__raptor/core/llm/telemetry.py:458)

## 5. Weaknesses and evidence status

| Priority and evidence | Finding and consequence |
| --- | --- |
| **P0, reproduced twice** | An exception in the parallel coordinator can leave review handlers live after the executor returns. With two workers inside benign blocking callbacks, `on_idle` raised its original exception. Both callbacks subsequently finished, but all four graph tasks stayed pending and asyncio reported destroyed pending tasks. Top-level failure cleanup drains study work and closes other resources, but lacks the executor's callback handles. A worker can therefore overlap closure of its run collaborators. I saw callbacks finish late. Persistence corruption remains hypothetical. [Private-loop finalizer](repos/gadievron__raptor/core/audit/executor.py:312) [Inflight ownership](repos/gadievron__raptor/core/audit/executor.py:737) [Worker handoff](repos/gadievron__raptor/core/audit/executor.py:969) [Orchestrator failure cleanup](repos/gadievron__raptor/core/audit/orchestrator.py:8522) |
| **P0, reproduced** | The audit finalizer returns zero both when the completion subprocess exits 9 and when it raises `TimeoutExpired`. The real metadata remained `running` in both controls, versus `completed` on the successful child path. The diagnostics go to stderr and the caller gets success. A timeout injected after the same metadata write gave the same exit and timeout diagnostic with state already `completed`, confirming that callers need the resulting state to tell the two cases apart. This directly affects wrappers and external run owners that use exit status. Intentional partial completion is a separate expected outcome. [Completion call and return](repos/gadievron__raptor/libexec/raptor-audit:2614) [Diagnostic and return paths](repos/gadievron__raptor/libexec/raptor-audit:2633) [Process exit adapter](repos/gadievron__raptor/libexec/raptor-audit:5382) [Existing finalizer tests](repos/gadievron__raptor/core/audit/tests/test_finalize_interrupt_lifecycle.py:91) |
| **P1, reproduced** | A per-task exception from `on_tick` can escape the inner error accounting. Five units were dispatched, four reached the completed counter, none reached the failed counter, one stayed pending, and the executor reported `complete`. The task exception was logged. Its effect on a complete CLI invocation depends on the surrounding final checks and callback implementation. [Drain status](repos/gadievron__raptor/core/audit/executor.py:232) [Callback placement](repos/gadievron__raptor/core/audit/executor.py:958) [Outer stop mapping](repos/gadievron__raptor/core/audit/orchestrator.py:16013) [Task exception logging](repos/gadievron__raptor/core/audit/executor.py:1219) |
| **P1, reproduced** | Run metadata reaches `completed` ahead of derived project visibility. An isolated child exited after the status write and before the journal merge. The index was missing while the journal remained readable. Invoking projection repair twice produced exactly one index entry. Project add/adopt wires this routine, but I found no equivalent replay in normal run completion startup. This is a recoverable projection gap and a misleading aggregate if consumers treat status as a visibility barrier. [Commit and projections](repos/gadievron__raptor/core/run/metadata.py:2090) [Projection repair](repos/gadievron__raptor/core/run/metadata.py:2228) [Adoption caller](repos/gadievron__raptor/core/project/project.py:1847) |
| **P1, reproduced in isolated children** | An armed SIGTERM watchdog can outlive the caller that installed it. A signal followed by handler removal and restoration still exited the process with 130, while the no-signal control exited 0. A slow synchronous hook pushed a nominal 0.12-second grace result from about 0.30 seconds to 1.00 second. CLI process-wide termination is intentional. Reuse in a long-lived host and interpreting the grace as a hard upper bound are the vulnerable assumptions. [Watchdog](repos/gadievron__raptor/core/audit/orchestrator.py:548) [Install/uninstall](repos/gadievron__raptor/core/audit/orchestrator.py:582) [Sync hooks](repos/gadievron__raptor/core/audit/orchestrator.py:606) [Flush contract](repos/gadievron__raptor/core/audit/final_log_flush.py:37) |
| **P1, measured boundary** | Reservation append survives abrupt process death in the tested filesystem, but its write path calls neither `fsync` nor a synchronous-open mode. One recovered pending hold was preserved, and a truncated tail was rejected. The durability claim at this boundary requires a storage failure model. No power loss or filesystem fault was simulated. The coverage journal has a separate explicit sync discipline. [Reservation append](repos/gadievron__raptor/core/audit/attempt_reservations.py:246) [Append primitives](repos/gadievron__raptor/core/json/jsonl.py:111) [Coverage sync](repos/gadievron__raptor/core/coverage/journal.py:1127) |
| **P1, documented and quantified** | The generic tool loop waits for a timed handler, then detaches it. Thirty-six timed-out handlers stayed live while diagnostics retained only 32 references. They all joined after the fixture released them. The cap limits retained diagnostics. Multi-model fanout also treats cancellation of queued futures separately from calls already running. A distinct observer exception was propagated before any provider call, unlike optional LLM accounting telemetry. [Tool worker timeout](repos/gadievron__raptor/core/llm/tool_use/loop.py:1385) [Observer contract](repos/gadievron__raptor/core/llm/tool_use/loop.py:1185) [Fanout cleanup](repos/gadievron__raptor/core/llm/multi_model/dispatch.py:418) [Telemetry](repos/gadievron__raptor/core/llm/telemetry.py:458) |
| **P2, reproduced** | The audit help offers a cost scheduler. Normal audit enables fairness and the ready path enters the fairness queue before legacy cost ordering. With opposed priority and cost inputs, each legacy mode produced a different order, while both managed configurations produced the same order. This is a CLI contract issue; fairness semantics are tested and appear intentional. [CLI help](repos/gadievron__raptor/libexec/raptor-audit:4972) [Managed selection](repos/gadievron__raptor/core/audit/orchestrator.py:9758) [Graph routing](repos/gadievron__raptor/core/audit/task_graph.py:235) [Fairness precedence test](repos/gadievron__raptor/core/audit/tests/test_review_fairness_cost.py:21) |
| **P2, reproduced extension limitation** | Synthetic transcript replay worked for a metadata-free client. Adding managed-audit lifecycle metadata or a same-run flag failed preflight before any outbound work because replay blocks primary provider construction. This constrains offline end-to-end fixture use for that entry point. It preserves the replay no-provider contract. [Pipeline preflight](repos/gadievron__raptor/core/audit/pipeline.py:336) [Provider property](repos/gadievron__raptor/core/llm/client.py:1837) [Replay guard](repos/gadievron__raptor/core/llm/transcript.py:884) [Replay scope in docs](repos/gadievron__raptor/docs/llm.md:626) |
| **P2, reproduced for lock and throttle scope** | Synthetic lock I/O failure caused two metadata writers to proceed without serialization. After a controlled interleave, both operations returned but only one distinct update survived. The locked control preserved both. This is deliberate availability degradation with a warning. Audit usually has a stronger, separate process lifetime lock. One rate broadcast also reduced two throttle instances from 4 and 8 to 2 and 4, reflecting process-wide coordination for embedded callers. [Metadata fallback](repos/gadievron__raptor/core/run/metadata.py:757) [Status read-modify-write](repos/gadievron__raptor/core/run/metadata.py:3146) [Run lock](repos/gadievron__raptor/core/audit/run_lock.py:116) [Throttle broadcast](repos/gadievron__raptor/core/llm/throttle.py:398) |

## 6. Core-code quality

- **Decomposition.** The task graph, fairness queue, parser supervisor, reservation ledger, quiescer and collector have meaningful narrower responsibilities. They are individually testable and split ownership at natural boundaries. Their integration flows through several oversized modules. The pinned audit orchestrator spans 38,704 lines, the provider module 5,663, the audit CLI 5,386 and the run metadata module 3,356. The direct maintenance concern is coordinating changes across callbacks, module state, side effects, and terminal paths, rather than any line-count threshold. [Graph](repos/gadievron__raptor/core/audit/task_graph.py:191) [Reservations](repos/gadievron__raptor/core/audit/attempt_reservations.py:87) [Collector](repos/gadievron__raptor/core/audit/collector.py:967) [Orchestrator integration](repos/gadievron__raptor/core/audit/orchestrator.py:9987) [CLI completion](repos/gadievron__raptor/libexec/raptor-audit:2614)
- **Types and extension paths.** Provider capabilities, retry classification, structured review results, tool protocol data classes, and budget exception scopes make key seams explicit. Generic dispatch typing records route and result distinctions. Lifecycle and publication use many untyped result dictionaries and callback conventions where identities and failure state are security- or accounting-relevant. The replay mismatch illustrates that support for a client interface does not imply support for every lifecycle capability. [Provider API](repos/gadievron__raptor/core/llm/providers.py:327) [Tool result/types](repos/gadievron__raptor/core/llm/tool_use/types.py:99) [Multi-model types](repos/gadievron__raptor/core/llm/multi_model/types.py:129) [Budget error types](repos/gadievron__raptor/core/llm/budget_errors.py:12) [Lifecycle assembly](repos/gadievron__raptor/core/audit/pipeline.py:336)
- **Concurrency and retries.** Locks and owner identities are often selected to match their resource. The parser supervisor has a killable boundary; graph work and tool handlers use threads whose future cancellation does not stop the underlying function. Retry policies recognize caller cancellation, rate limits, usage, continuation, and scope. They are split across the client, dispatcher and executors. In the lower-level executor, a typed budget exception by itself allowed all five work items to be visited when no budget callback was supplied. With a callback latching closure, only already-issued work was allowed. Production audit supplies its own callback, so this finding concerns the reusable executor contract. [Parser ownership](repos/gadievron__raptor/core/inventory/builder.py:255) [Retry policy](repos/gadievron__raptor/core/run/retry.py:38) [Refinement driver](repos/gadievron__raptor/core/orchestration/driver.py:74) [Task exception handling](repos/gadievron__raptor/core/audit/executor.py:958) [Production budget gate](repos/gadievron__raptor/core/audit/orchestrator.py:10059) [Budget latch](repos/gadievron__raptor/core/audit/orchestrator.py:16601)
- **Error handling and observability.** Preservation of an original failure through noisy cleanup is a recurring code pattern and test discipline. Journal, metadata, report, telemetry and optional event sinks carry different authority. The boundary is sometimes implicit. The status finalizer logs failure without a machine-readable failed exit, and an exception in an observational callback can alter task accounting. Alignment of terminal status, failure propagation and counters needs an explicit contract across these owners. [Collector](repos/gadievron__raptor/core/audit/collector.py:1134) [Retry cleanup](repos/gadievron__raptor/core/llm/dispatcher/server.py:2421) [Report state](repos/gadievron__raptor/core/audit/report.py:1063) [Finalizer](repos/gadievron__raptor/libexec/raptor-audit:2633) [Callback boundary](repos/gadievron__raptor/core/audit/executor.py:958)
- **Tests and maintainability.** Integration-style local subprocess cases are substantial and distinguish ownership, restart and settlement. Several negative findings required exercising a real worker or real metadata boundary where neighboring tests substitute both sides of the handoff. For example, the owned-cleanup test stubs the async body, and finalizer tests check interrupted status and diagnostics. A few otherwise valuable test fixtures depend on undocumented pytest mutation ordering or exec behavior of a diagnostic shell program. [Async cleanup tests](repos/gadievron__raptor/core/audit/tests/test_executor_owned_cleanup.py:13) [Finalizer tests](repos/gadievron__raptor/core/audit/tests/test_finalize_interrupt_lifecycle.py:91) [Pytest mutation fixture](repos/gadievron__raptor/core/testing/tests/test_process_state_guards.py:294) [Argv fixture](repos/gadievron__raptor/core/llm/tests/test_cc_adapter.py:141)


## 7. Executed tests/experiments and their limitations

| Run | Scope | Observed result |
| --- | --- | --- |
| Base substrate | Atomic files, artifacts, state, storage, project, run, environment, dispatch, reporting, coverage and startup | 10,590 passed, 105 skipped, 11 failed, three subtests passed in 80.63s. All 11 passed in the corrected 76-test installation guard rerun. |
| Reconstruction and executor | Audit graph, fairness, executor, checkpoint, resume, quiesce, study and selected orchestration modules | Initially 613 passed and 22 failed. With local C grammar, 635 passed in 9.35s. A focused in-memory grammar bridge run independently passed 251. |
| Runtime recovery | Audit cold resume, interruption, ownership, scope, budgets, reservations, study, and collector acknowledgment | 242 passed and one identity test skipped in 14.46s. The runner lacked the required machine/boot identity. The subprocess tests used controlled review work and exercised actual process termination. |
| Supervisors and SCA | Selected sandbox resource ownership, subprocess timeout, cache, SBOM and local SCA pipeline tests | Initially 2,661 passed, one skipped, two failed. With the namespace's read-only system view corrected, 2,664 passed in 19.46s. |
| LLM | Client, adapters, local dispatcher, multi-model, scorecard, typed loop and stream handling | Initial 5,493 passed, 121 failed, 122 skipped and 74 deselected in 155.75s. With cached transitive dependencies present, 5,704 passed, 50 failed, 10 skipped and four setup errors in 64.94s, with two separately diagnosed observer cases excluded. The 119-node targeted rerun passed 115. The final truststore/route rerun passed 78 of 80. Exact pinned provider behavior remains unmeasured. |
| Foundations | Artifact packaging, configuration, build, schema, source, testing utilities and local engines' common support | 28,690 passed, 144 skipped and two failed in 76.16s. The alternate pytest run passed the relevant fixture's 15 cases. |
| Inventory and audit publication | Inventory, understand graph, concepts and six audit publication/queue tests | 4,741 passed, 365 skipped and 15 failed in 78.22s. Replacing only the removed timeout descriptor for a narrow control yielded 11/11. Four cases depend on missing grammars. |
| Handoffs | Extra audit retries, work queue and journal ownership, prepared result, publication scope, deadline, shutdown, and study ownership | 168 passed in 5.64s. |
| Language floor | Compile each tracked Python source or Python-shebang `libexec` entry to an in-memory code object under CPython 3.13.16 | 9,411 compiled, zero errors. The standalone graph experiment also passed 4,096 cases on both tested interpreters with fairness enabled and batch pulls of three. This verifies syntax at the supported floor and graph behavior on the synthetic workload. |

Deduplicating the retained full-suite and focused XMLs by class and case name, and substituting the corrective follow-ups for repeated cases, yielded 54,141 cases with 53,449 passes, 625 skips, 63 failures and four setup errors before the separately scripted parser-interface controls. This is a descriptive total across measured configurations. It combines different dependency strata and does not describe a lockfile or release test run. The two separately analyzed observer cases and the independent fault probes are outside this count. The report gives suite-level results because they retain the setup context.

Locked offline installation failed on uncached `z3-solver==4.15.4.0`. The pinned Instructor, several native grammars, pyelftools and exact SDK wheels were also absent from the local cache. The extracted Pydantic core wheel required the cached CPython 3.14 environment. Main runs used CPython 3.14.8 with Pydantic 2.13.4, pytest 9.2.0, xdist 3.8.0, HTTPX 0.28.1, OpenAI 3.36.1, Anthropic 1.17.0, Google GenAI 2.32.0, botocore 1.43.117 and tree-sitter 0.26.1. Pytest 9.0.3 served as an alternate fixture control. C parser controls called the available system grammar through a temporary local adapter. The pins and CI's C/Go preflight explain why these profiles do not equal CI. Network, hosted models, live limits, container/runtime services, full grammar coverage, optional toolchains, full repository CI and long stress runs remain unmeasured. [Python floor and dependency pins](repos/gadievron__raptor/pyproject.toml:9) [SDK pins](repos/gadievron__raptor/pyproject.toml:21) [Grammar pins](repos/gadievron__raptor/pyproject.toml:57) [Pytest pin](repos/gadievron__raptor/pyproject.toml:97) [CI grammar preflight](repos/gadievron__raptor/.github/workflows/tests.yml:428)

## 8. Measurement audit

| Negative or surprising observation | Checks, controls and interpretation |
| --- | --- |
| The first archived snapshot could not collect the intended suites. | The commit's export rules omit test infrastructure, including root conftest. A shallow local Git clone at the identical SHA restored tracked fixtures without network access. The original source tree was never used for pytest execution. The optional submodule was uninitialized and no remote material was fetched. [Export rules](repos/gadievron__raptor/.gitattributes:10) [Submodule declaration](repos/gadievron__raptor/.gitmodules:1) |
| Offline install and interpreter compatibility. | The first cache copy mistakenly left metadata itself read-only, and uv attempted default development dependencies. A writable copy of public package cache metadata and `--no-default-groups` got to the actual missing locked solver artifact. A separate offline pip check under 3.13 found no compatible cached Pydantic core wheel. Cache enumeration and installed package metadata supported the fallback version claims. This explains the execution setup and distinguishes it from a repository defect. [Dependencies](repos/gadievron__raptor/pyproject.toml:19) [Test group](repos/gadievron__raptor/pyproject.toml:96) |
| Eleven base tests failed. | Namespace TLS setup initially omitted the certificate inputs. After mounting them read-only, all remaining failures followed the opt-in installation guard's Btrfs exclusions for both fixture paths and the interpreter. Retesting the fixtures alone on tmpfs preserved the interpreter-side failure. A staged tmpfs interpreter plus its host-resolved ELF libraries exposed two plain utility omissions, `mv` and `true`. With those restored the entire installation guard and launcher group passed 76/76. The tests establish how that optional policy treats this filesystem. [Filesystem policy](repos/gadievron__raptor/core/startup/install_guard.py:228) [Launcher stamp handoff](repos/gadievron__raptor/bin/raptor:1046) [Guard fixtures](repos/gadievron__raptor/core/startup/tests/test_install_guard.py:256) |
| All 22 reconstruction failures followed the same fixture. | No C parser meant the reference foundation was incomplete and correctly denied credit. A native C ABI-15 capsule was parsed successfully, then the 251-test in-memory subset and 635-test subprocess-capable suite both turned green. The real end-to-end restart group used the same adapter. The lone boot test skipped due to missing machine identity in the sanitized environment. Patching synthetic machine and boot IDs passed the same assertion, which verifies adjudication logic only. [Reference foundation](repos/gadievron__raptor/core/audit/reference_foundation.py:233) [Fixture binding](repos/gadievron__raptor/core/audit/tests/reuse_foundation_fixtures.py:15) [Resume rejection](repos/gadievron__raptor/core/audit/gaps.py:3845) |
| Two supervisor tests failed. | The outer measurement sandbox had hidden system metadata needed by the sandbox probe. Adding a read-only `/sys` mapping changed availability as expected, yielded five standalone passes, and converted the full group to 2,664/2,664. The repository's controls still ran inside the test namespace. [Supervisor test location](repos/gadievron__raptor/core/sandbox/tests/test_spawn_lifecycle_hardening.py:1) |
| SDK imports, constructor errors and request counters. | Adding cached transitive packages restored imports. The full rerun grouped 42 failures and four setup errors on explicit Anthropic `httpx.Client` versus `httpx2.Client` rejection. A subprocess dispatcher test and three consumed-attempt counter tests fail before their mock upstream receives a request for the same reason. The two initial `truststore` errors were removable setup failures, and the 80-case rerun after installation exposed two other constructor failures. Older exact wheels were unavailable. Zero mock request counts therefore do not establish a retry or billing defect under the pins. [Dispatcher construction](repos/gadievron__raptor/core/llm/dispatcher/client.py:508) [Subprocess assertion](repos/gadievron__raptor/core/llm/dispatcher/tests/test_dispatcher.py:1016) [Consumed-attempt fixture](repos/gadievron__raptor/core/llm/tests/test_consumed_attempt_e2e.py:151) |
| Malformed-output usage and two observer-cancellation cases. | The fixtures modify a response's first `tool_calls` entry. With Instructor absent, the provider selected JSON fallback and the MockTransport fixture raised `KeyError` before any fake completion was received. One test subsequently reported zero billed tokens and the observer controls could raise intentional `KeyboardInterrupt` or `SystemExit` through the fallback emission path. An independent mock produced valid or malformed JSON content in the actual fallback shape. In both cases one mock request, six billed tokens and one signed receipt were recorded, with no pending hold. A mistaken control compared the whole response wrapper to a dict, then the corrected comparator used its result. The measured fallback covers consumption accounting. The full Instructor and observer-cancellation contracts remain unverified. [Optional import](repos/gadievron__raptor/core/llm/providers.py:319) [JSON fallback](repos/gadievron__raptor/core/llm/providers.py:1890) [Malformed fixture](repos/gadievron__raptor/core/llm/tests/test_prepared_attempt_reservation.py:391) [Observer fixture](repos/gadievron__raptor/core/llm/tests/test_prepared_attempt_reservation.py:433) |
| A child argv hygiene assertion saw only `tr`. | Its shell pipeline opened `/proc/self/cmdline` from a diagnostic command. Two controls read the actual calling shell through its PID with a command following the read, and the Python probe read its own argv. Both showed the prompt-file flag and neither contained the synthetic prompt. This resolves the missing flag observed by the test. [Original proc reader](repos/gadievron__raptor/core/llm/tests/test_cc_adapter.py:141) |
| Two process-state fixtures failed. | A simulated failure occurs after setting the environment but before pytest 9.2.0 records undo state. The 15 selected cases split 13/2 on 9.2.0, while cached 9.0.3 records before assignment and passed 15/15. The exact 9.1.1 pin was absent. Treat this as fixture sensitivity to pytest internals. [Fixture injection](repos/gadievron__raptor/core/testing/tests/test_process_state_guards.py:294) [Root fixture](repos/gadievron__raptor/conftest.py:412) |
| Fifteen inventory cases failed. | Nine timeout getter and two timeout publication failures used a 0.26.1 native parser that lacks the pinned `timeout_micros` descriptor. The compatibility branch explicitly logs and removes the parser-local bound on that binding. Substituting a local descriptor in memory passed all 11 setter/resync tests, including failed publication. One expected grammar census entry was missing, two JS/Go parser-sharing cases returned empty results, and PHP edge recomputation returned the explicitly unavailable census with no `recomputed_files`. Its source and hash controls passed. Missing grammar modules and the actual PHP early return explain those four outcomes. The measured facts cover degraded behavior in this environment. They leave the exact native timeout and missing-grammar positive cases unverified. [Native feature check](repos/gadievron__raptor/core/inventory/_ts_cache.py:165) [Timeout publication test](repos/gadievron__raptor/core/inventory/tests/test_parse_timeout_publication.py:13) [PHP extraction](repos/gadievron__raptor/core/inventory/call_graph.py:4635) [Include recompute](repos/gadievron__raptor/core/inventory/include_graph.py:274) [Shared tree fixture](repos/gadievron__raptor/core/inventory/tests/test_call_graph_tree_sharing.py:86) |
| Executor orphaned handlers and lost a tick failure. | The two-worker barrier proved both callbacks were already executing. The normal run drained the graph. Twice, raising from the real coordinator left two live callbacks and four pending units, even after callbacks eventually finished. An independent tick failure used a specific key and verified the graph, report result and counters. The budget control initially assumed two issued tasks implied two entered callbacks. The corrected bound counts issuance and checks that no new work is admitted. An initial combined-script timeout was investigated by running the cases individually with unbuffered diagnostics, then together. The timeout did not recur. [Loop closure](repos/gadievron__raptor/core/audit/executor.py:312) [Tick placement](repos/gadievron__raptor/core/audit/executor.py:951) [Task retirement backstop](repos/gadievron__raptor/core/audit/executor.py:1219) |
| Finalization, crash window and signal behavior. | Isolated temp runs compared the same finalizer under real metadata success, stubbed exit 9 and stubbed timeout before or after the write. The successful case rules out fixture ownership or missing baseline metadata. Independent process death immediately after an actual status write demonstrated the missing project index. A real journal repair twice yielded one row. Two post-SIGTERM children measured watchdog retention while a no-signal child survived, and the slow-hook comparison moved the exit time by roughly the injected delay. These controls have no provider, quota, or external timing dependency. [Finalize call](repos/gadievron__raptor/libexec/raptor-audit:2626) [Poststatus work](repos/gadievron__raptor/core/run/metadata.py:2090) [Watchdog](repos/gadievron__raptor/core/audit/orchestrator.py:548) |
| Attempt durability, ready ordering, and replay. | A child died after append and a fresh process recovered an unresolved hold. A deliberately partial final line was rejected and reconciliation removed the restored hold only on explicit settlement. Instrumentation saw no fsync calls, consistent with the append implementation. Scheduling initially used priorities tied to lexical order. A second fixture used deliberately opposing cost/priority ranks and tested both paths. For replay the same saved input succeeded without lifecycle metadata and failed with it and with same-run, before provider activity. [Attempt recovery](repos/gadievron__raptor/core/audit/attempt_reservations.py:131) [Write primitive](repos/gadievron__raptor/core/json/jsonl.py:111) [Scheduler selection](repos/gadievron__raptor/core/audit/task_graph.py:235) [Replay guard](repos/gadievron__raptor/core/llm/transcript.py:884) |
| Lock behavior under contention. | A held audit lock refused a new process, while another thread in the owner's process got the documented no-op re-entry handle. In a separate metadata control, both workers used normal JSON reads and writes. A barrier paused the first writer after its read and let the second attempt entry. With the healthy lock both disjoint keys survived. Injecting an `EIO` into validation of that scratch metadata lock let the second publish before the first released. Both returned successfully, but the final JSON contained only the first key. This isolates lock degradation from quota, storage corruption and source changes. [Audit re-entry](repos/gadievron__raptor/core/audit/run_lock.py:504) [Metadata lock fallback](repos/gadievron__raptor/core/run/metadata.py:757) [Status update](repos/gadievron__raptor/core/run/metadata.py:3146) |

## 9. Post-mortem and highest-leverage improvements

The code evolved toward stronger recovery and truthful paid-attempt accounting while continuing to support a shell harness, standalone commands, and reusable Python components. The pressure is visible at boundaries where older contracts were kept intact. The finalizer now prints lifecycle errors but still chooses the exit code only from the pipeline reason. The executor added graph discrepancy logging and guarded cleanup helpers, yet a private async loop can still die before its worker ownership is settled. Run-local status is atomic; secondary project views deliberately use repeatable best-effort work following that atomic point. This structure is practical for a one-command local tool and leaves precise gaps when a caller needs an all-resources-retired or all-views-current guarantee. [Completion status contract](repos/gadievron__raptor/libexec/raptor-audit:2648) [Graph discrepancy](repos/gadievron__raptor/core/audit/executor.py:232) [Executor/outer cleanup](repos/gadievron__raptor/core/audit/orchestrator.py:8522) [Project repair semantics](repos/gadievron__raptor/core/run/metadata.py:2228)

1. **P0. Consolidate review execution ownership through failure.** Put dispatch, in-flight tracking, bounded drain and publication eligibility under a single run-scoped owner in both serial and parallel paths. Stop admission, stop queued work, retain running worker identities and make unresolved work explicit before collaborators close. A late callback should be unable to publish through a retired owner. Keep the original exception visible. Exercise a live blocked worker, failed ticks and cancellation in tests, and assert that graph state, failed counts and terminal reason agree. A bounded cooperative timeout should report remaining ownership explicitly. [Executor close](repos/gadievron__raptor/core/audit/executor.py:312) [Worker handoff](repos/gadievron__raptor/core/audit/executor.py:969) [Study late-result contract](repos/gadievron__raptor/core/audit/knowledge_runtime.py:2093)
2. **P0. Make terminal lifecycle status part of command success.** Have completion return a typed outcome that includes verified metadata state and explicit interrupted or failed status. Propagate completion subprocess failure and timeout to callers. Preserve the recognized successful partial outcomes after their metadata is sealed. Add state-and-exit controls for nonzero child, timeout, verified success and a timeout after state replacement. [Finalize path](repos/gadievron__raptor/libexec/raptor-audit:2614) [Legitimate partial stops](repos/gadievron__raptor/libexec/raptor-audit:2658)
3. **P1. Make projection lag durable and repairable on normal use.** Associate a projection generation or pending marker with terminal state and reuse idempotent projection repair on project read/startup after an interrupted merge. Record visible lag separately from local run completion. Define durability explicitly for reservations, checkpoints and audit artifacts, then match the pre-send storage operation to the promised failure model. Test abrupt process death now and add filesystem-level durability tests if the product promises recovery after storage failure. [Commit order](repos/gadievron__raptor/core/run/metadata.py:2090) [Repair](repos/gadievron__raptor/core/run/metadata.py:2228) [Reservation append](repos/gadievron__raptor/core/audit/attempt_reservations.py:246) [Coverage sync cadence](repos/gadievron__raptor/core/coverage/journal.py:1127)
4. **P1. State cancellation and observer boundaries in the APIs.** Give install/uninstall a cancellable watchdog lifetime and disclose whether end-to-end time includes final hooks. Make observational callbacks best-effort by default or explicitly designate them as policy gates. Require cooperative tool cancellation for trusted threaded callbacks, or provide isolated ownership for callbacks whose physical stop is a requirement. Keep counters for live detached work so clipping diagnostic references does not hide it. [Signals](repos/gadievron__raptor/core/audit/orchestrator.py:548) [Callback](repos/gadievron__raptor/core/llm/tool_use/loop.py:1185) [Detached tools](repos/gadievron__raptor/core/llm/tool_use/loop.py:1421)
5. **P2. Consolidate configuration and test capability handshakes.** Describe the effective audit scheduler and label the remaining legacy scheduler controls. Let replay capability be checked explicitly, with an inert prepared-capability test fixture if managed audit is meant to support it. Keep package profiles and an offline integration fixture inventory evidence alongside the source so a failed parser or SDK preflight becomes a precise unmeasured capability. Cover a serial and a parallel executor contract suite with the same scenarios. [Scheduler choice](repos/gadievron__raptor/core/audit/orchestrator.py:9758) [Replay preflight](repos/gadievron__raptor/core/audit/pipeline.py:336) [Grammar check](repos/gadievron__raptor/.github/workflows/tests.yml:428)


## 10. Evidence appendix

### Checkout and test commands

The command set below identifies the measured nodes and setup. Execute the test commands in the pinned local scratch clone with the recorded compatible package profile. `scratch` denotes its parent directory inside the work root. The measurement mount mapped that directory to `/work` and its temporary directory to `/tmp`. Four workers with file-level scheduling provided the broad runs. The isolated controls used serial pytest or direct Python. Repository defaults exclude integration, corpus, and slow work. The explicit marker expression in the runtime/handoff runs also admits local slow cases. [Pytest configuration](repos/gadievron__raptor/pytest.ini:25) [Default options](repos/gadievron__raptor/pytest.ini:40) [Runner safeguards](repos/gadievron__raptor/conftest.py:106)

```bash
root="$PWD/repos/gadievron__raptor"
git -C "$root" rev-parse --verify HEAD
git -C "$root" status --porcelain=v1 --untracked-files=all
git -C "$root" status --porcelain=v1 --untracked-files=all --ignored
git -C "$root" diff --quiet
git -C "$root" diff --cached --quiet
date -u +'%Y-%m-%dT%H:%M:%SZ %s'

git clone --depth 1 --no-tags --template= "file://$root" "$scratch/checkout"
# In the scratch clone, use the empty-environment, loopback-only namespace.
uv sync --offline --locked --no-python-downloads --no-default-groups --group test --extra grammars
# Locked install failed on the available local cache. Use the profile in §7 for the tests below.

export PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
run_suite() {
  local name="$1"
  shift
  /work/env14/bin/python -m pytest -q -p no:cacheprovider -p xdist.plugin \
    -n 4 --dist loadfile --basetemp="/tmp/$name" --junitxml="/work/$name.xml" "$@"
}

run_suite base-a  \
  core/atomic_fs core/artifacts \
  core/json core/logging \
  core/paths core/progress \
  core/status core/git \
  core/project core/run \
  core/env core/dispatch \
  core/reporting core/coverage \
  core/startup
run_suite audit-c  \
  core/audit/tests/test_task_graph.py core/audit/tests/test_review_fairness.py \
  core/audit/tests/test_executor.py core/audit/tests/test_executor_cleanup.py \
  core/audit/tests/test_executor_floor.py core/audit/tests/test_executor_imports.py \
  core/audit/tests/test_executor_owned_cleanup.py core/audit/tests/test_checkpoint_encoded_append.py \
  core/audit/tests/test_checkpoint_reader_ownership.py core/audit/tests/test_quiesce_checkpoint_precedence.py \
  core/audit/tests/test_quiesce_deadline_contract.py core/audit/tests/test_quiesce_pause_ownership.py \
  core/audit/tests/test_quiesce_run_deadline_integration.py core/audit/tests/test_journal_quiesce.py \
  core/audit/tests/test_resume_substrate.py core/audit/tests/test_resume_checklist_gate.py \
  core/audit/tests/test_resume_max_cost.py core/audit/tests/test_resume_reopen.py \
  core/audit/tests/test_same_run_resume.py core/audit/tests/test_run_progress.py \
  core/audit/tests/test_study_job_ledger.py core/audit/tests/test_study_job_runtime.py \
  core/audit/tests/test_sweep_checkpoint.py core/audit/tests/test_cost_tracker.py \
  core/audit/tests/test_cost_reconciliation.py core/audit/tests/test_lifecycle_call_timeouts.py \
  core/orchestration/tests/test_driver.py core/orchestration/tests/test_llm_json.py \
  core/orchestration/tests/test_funnel.py core/orchestration/tests/test_fail_open_channel.py \
  core/orchestration/tests/test_run_discovery.py core/orchestration/tests/test_lifecycle_trust_marker.py \
  core/orchestration/tests/test_prompt_file_lifetime.py
run_suite audit-b -m 'not integration and not corpus' \
  core/audit/tests/test_prepared_attempt_recovery.py core/audit/tests/test_prepared_provider_preflight.py \
  core/audit/tests/test_attempt_reader_cleanup.py core/audit/tests/test_attempt_observability.py \
  core/audit/tests/test_attempt_validity_scope.py core/audit/tests/test_budget_terminal.py \
  core/audit/tests/test_run_lock.py core/audit/tests/test_run_lock_retirement.py \
  core/audit/tests/test_sigterm_grace.py core/audit/tests/test_resume_e2e.py \
  core/audit/tests/test_review_fairness_cost.py core/audit/tests/test_reservation_close_admission.py \
  core/audit/tests/test_study_attempt_admission.py core/audit/tests/test_unit_attempt_admission.py \
  core/audit/tests/test_knowledge_runtime_coordinator.py core/audit/tests/test_knowledge_runtime_clock.py \
  core/audit/tests/test_knowledge_runtime_delivery_integration.py core/audit/tests/test_knowledge_runtime.py \
  core/audit/tests/test_knowledge_terminal_retirement.py core/audit/tests/test_finalize_interrupt_lifecycle.py \
  core/audit/tests/test_validate_postpass_lifecycle.py core/audit/tests/test_timeout_recovery.py \
  core/audit/tests/test_collector_acknowledgement.py
run_suite support-c  \
  core/sandbox/tests/test_death_pipe_sibling_fds.py core/sandbox/tests/test_death_pipe_atfork_failure.py \
  core/sandbox/tests/test_supervisor_pipe_ownership.py core/sandbox/tests/test_supervised_waiter_contract.py \
  core/sandbox/tests/test_supervised_ready_cancellation.py core/sandbox/tests/test_spawn_lifecycle_hardening.py \
  core/sandbox/tests/test_spawn_cleanup_query_errors.py core/sandbox/tests/test_spawn_child_not_ready.py \
  core/sandbox/tests/test_spawn_capture_preflight.py core/sandbox/tests/test_run_sandboxed_timeout.py \
  core/sandbox/tests/test_parser_worker_ownership.py core/sandbox/tests/test_parser_worker_cancellation.py \
  core/sandbox/tests/test_parser_jail_startup_cleanup.py core/sandbox/tests/test_context_preyield_ownership.py \
  core/sandbox/tests/test_context_finalizer_ownership.py core/sandbox/tests/test_tracer_wait_loop.py \
  core/sandbox/tests/test_scratch_owner_cleanup.py core/sandbox/tests/test_daemon_group_ownership.py \
  core/sandbox/tests/test_daemon_process_group_cleanup.py core/sandbox/tests/test_proxy_startup_cleanup.py \
  core/sandbox/tests/test_proxy_submission_cleanup.py core/sandbox/tests/test_status_pipe_fixture_ownership.py \
  core/sandbox/tests/test_timeout_preflight.py core/sandbox/tests/test_timeout_snapshot_encoding.py \
  core/sandbox/tests/test_timeout_output_bytes.py packages/sca/versions \
  packages/sca/parsers packages/sca/sbom_inventory \
  packages/sca/tests/test_{cache,cache_budget,cache_database_guard_ownership,cache_lock_ownership,cache_session_diagnostics,discovery,e2e_pipeline,pipeline,pipeline_phases,pipeline_analysis_gaps,prepare_sbom,sbom,sbom_import,sca_review_followups}.py
run_suite llm-d -k 'not paid_refusal_survives_secondary_telemetry_cancellation' \
  core/llm/tests core/llm/dispatcher/tests \
  core/llm/multi_model/tests core/llm/scorecard/tests \
  core/llm/tool_use/tests/test_loop.py core/llm/tool_use/tests/test_types.py \
  core/llm/tool_use/tests/test_streaming.py core/llm/tool_use/tests/test_wire_converters.py
run_suite foundation-d  \
  core/annotations core/archive \
  core/build core/config \
  core/dockerfile core/evidence \
  core/hash core/http \
  core/license core/schema_constants \
  core/source core/staleness \
  core/tar core/testing \
  core/tuning core/zip
run_suite inventory-e  \
  core/inventory core/understand_graph \
  core/concepts core/audit/tests/test_{study_queue_livelock,initial_publication_ack_integration,initial_publication_failure,publication_finalization_integration,attempt_projection,accounted_review_publication}.py

# Serial follow-ups on each corrected or alternate fixture environment.
python -m pytest -q core/startup/tests/test_install_guard.py core/startup/tests/test_install_launcher.py
python -m pytest -q core/llm/tests/test_transport_misroute_guard.py \
  core/llm/dispatcher/tests/test_lifecycle.py \
  core/llm/dispatcher/tests/test_upstream_pooling.py core/llm/dispatcher/tests/test_upstream_timeout.py
python -m pytest -q core/testing/tests/test_process_state_guards.py \
  -k 'binary_cache_fixture'
python -m pytest -q -m 'not integration and not corpus' \
  core/audit/tests/test_backlog_source_handoff.py \
  core/audit/tests/test_error_retry.py \
  core/audit/tests/test_journal_queue_ownership.py \
  core/audit/tests/test_knowledge_fairness_sdk.py \
  core/audit/tests/test_prepared_result_publication_link.py \
  core/audit/tests/test_publication_scope.py \
  core/audit/tests/test_report_publication_limitations.py \
  core/audit/tests/test_review_unit_ownership_sdk.py \
  core/audit/tests/test_rotate_cleanup_diagnostics.py \
  core/audit/tests/test_run_deadline_binding.py \
  core/audit/tests/test_spawn_seam_llm_env.py \
  core/audit/tests/test_stop_join_backstop.py \
  core/audit/tests/test_study_input_publication.py \
  core/audit/tests/test_study_publication_owner.py \
  core/audit/tests/test_temp_setup_cleanup.py \
  core/audit/tests/test_work_queue_constructor_ownership.py
```

The offline boundary was a user/network namespace with only the loopback interface brought up and capabilities dropped, followed by Bubblewrap's isolated PID and mount views and a cleared environment. All dependency inputs came from local caches or mounted system directories. The public TLS data and `/sys` were mounted read-only after discovery of the measurement omissions. The optional installation guard control used an ephemeral staged `/usr` and `/tmp` on tmpfs. Only scratch paths received bytecode-disabled test outputs. [Fixture and engine policy](repos/gadievron__raptor/conftest.py:82) [CI test profile](repos/gadievron__raptor/.github/workflows/tests.yml:470)

For the C-only adapter, place the following module at `tree_sitter_c.py` in a scratch import path or the scratch virtual environment. This was only a local native grammar availability control. [Grammar import path](repos/gadievron__raptor/core/inventory/extractors.py:2303) [Audit foundation](repos/gadievron__raptor/core/audit/reference_foundation.py:233)

```python
from ctypes import CDLL, c_char_p, c_void_p, py_object, pythonapi

c_lib = CDLL("/usr/lib/libtree-sitter-c.so.15.0")
c_lib.tree_sitter_c.restype = c_void_p
capsule = pythonapi.PyCapsule_New
capsule.argtypes = [c_void_p, c_char_p, c_void_p]
capsule.restype = py_object
def language():
    return capsule(c_lib.tree_sitter_c(), b"tree_sitter.Language", None)
```

For the parser timeout-interface control, run the two named test modules with only the parser descriptor supplied in memory. Compare to the native 0.26.1 feature probe and to the full inventory run. [Timeout compatibility](repos/gadievron__raptor/core/inventory/_ts_cache.py:165)

```python
import pytest
import tree_sitter
print('cached native timeout property', hasattr(tree_sitter.Parser,'timeout_micros'))
class TimeoutDescriptorFixture:
    timeout_micros = 0
tree_sitter.Parser = TimeoutDescriptorFixture
raise SystemExit(pytest.main(['-q','core/inventory/tests/test_parse_timeout_resolution.py','core/inventory/tests/test_parse_timeout_publication.py']))
```

### Independent fault controls

Run each Python excerpt with the scratch interpreter from the clone root, e.g. `/work/env14/bin/python -u -`. These are benign coordination fixtures. They create no persistent outputs.

**Parallel executor.** The following produced normal `(4, 4, 0, 0)`, then fault `(2, 0, 2, 4)` twice, followed by two completed callbacks and four pending graph entries. [Executor entry](repos/gadievron__raptor/core/audit/executor.py:248)

```python
from pathlib import Path
from types import SimpleNamespace
from threading import Event, Lock
import time
from core.audit.executor import ExecutorConfig, review_work_inflight, run_executor_sync
from core.audit.task_graph import TaskGraph

def exercise(raise_from_owner):
    nodes = [{"file": "plain.txt", "name": str(i), "line_start": 1}
             for i in range(4)]
    graph = TaskGraph.from_workqueue(nodes, [], review_fairness=True)
    owner_fault = RuntimeError("injected coordinator failure")
    entered_twice = Event()
    release = Event()
    lock = Lock()
    began = []
    finished = []

    def handler(gap, *_args, **_kwargs):
        with lock:
            began.append(gap["name"])
            if len(began) == 2:
                entered_twice.set()
        if raise_from_owner:
            if not release.wait(5.0):
                raise TimeoutError("control failed to release handler")
        with lock:
            finished.append(gap["name"])

    def idle():
        if raise_from_owner and entered_twice.is_set():
            raise owner_fault
        return 0.05 if raise_from_owner else None

    try:
        stats = run_executor_sync(graph, lambda *args: None, SimpleNamespace(),
                                  SimpleNamespace(out_dir=Path("/tmp/no-output")),
                                  SimpleNamespace(terminated_by=""),
                                  ExecutorConfig(2), on_idle=idle, review_one_fn=handler)
    except RuntimeError as error:
        assert raise_from_owner and error is owner_fault
        observed = (len(began), len(finished), review_work_inflight(), graph.pending)
        assert observed == (2, 0, 2, 4), observed
        print("fault returned with entered/finished/inflight/pending:", observed, flush=True)
    else:
        assert not raise_from_owner and stats.completed == 4
        observed = (len(began), len(finished), review_work_inflight(), graph.pending)
        assert observed == (4, 4, 0, 0), observed
        print("normal returned with entered/finished/inflight/pending:", observed, flush=True)
    finally:
        release.set()
    deadline = time.monotonic() + 2.0
    while review_work_inflight() and time.monotonic() < deadline:
        Event().wait(0.01)
    if raise_from_owner:
        assert len(finished) == 2 and graph.pending == 4
        print("after caller returned and released:", len(finished), graph.pending, flush=True)

exercise(False)
exercise(True)
exercise(True)
```

**Completion command.** This uses the checked-in fixture to substitute incidental report/environment inputs while preserving the CLI finalizer and the real successful metadata transition. The respective outcomes were `(completed, 0)`, `(running, 0)`, `(running, 0)`, and `(completed, 0)`. [Finalize fixture](repos/gadievron__raptor/core/audit/tests/test_finalize_interrupt_lifecycle.py:1) [Completion branch](repos/gadievron__raptor/libexec/raptor-audit:2614)

```python
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from types import SimpleNamespace
import subprocess
from core.audit.tests import test_finalize_interrupt_lifecycle as tests
from core.json.utils import save_json
from core.run.metadata import complete_run, load_run_metadata

for failure in ("none","status","timeout","late_timeout"):
    with TemporaryDirectory() as tmp, MonkeyPatch.context() as monkey:
        path=Path(tmp)
        out,result=tests.finalize_env.__wrapped__(path, monkey)
        save_json(out / ".raptor-run.json", {"command":"audit","status":"running"})
        result.terminated_by="complete"
        cli=tests._load_cli()
        real_temporary_scope=tests._private_finalize_run.__wrapped__(monkey)
        install=next(real_temporary_scope)
        called=[]
        def child(cmd, **kwargs):
            called.append(cmd)
            assert cmd[1] == "complete"
            if failure == "late_timeout":
                complete_run(out, expected_command="audit")
                raise subprocess.TimeoutExpired(cmd, 1)
            if failure == "timeout":
                raise subprocess.TimeoutExpired(cmd, 1)
            if failure == "status":
                return SimpleNamespace(returncode=9, stderr="fixture publication refused")
            complete_run(out, expected_command="audit")
            return SimpleNamespace(returncode=0, stderr="")
        try:
            install(cli, child)
            out_text=StringIO()
            err_text=StringIO()
            with redirect_stdout(out_text),redirect_stderr(err_text):
                rc=cli._finalize_run(out,result,"")
            status=load_run_metadata(out)["status"]
            assert rc==0 and status==("completed" if failure in ("none","late_timeout") else "running")
            assert ("lifecycle complete failed" in err_text.getvalue()) is (failure!="none")
            print(failure,"entry calls",len(called),"status",status,"exit",rc)
        finally:
            real_temporary_scope.close()
```

**Project projection crash.** The run first wrote a normal journal row, then a separate process exited after metadata changed. This produced `(73, completed, False)` for child exit, run status and existence of the project index. Two repairs yielded one row each. [Metadata status](repos/gadievron__raptor/core/run/metadata.py:2090) [Projection repair](repos/gadievron__raptor/core/run/metadata.py:2228)

```python
import json,os,sys,tempfile,subprocess
from pathlib import Path
from unittest.mock import patch
from core.coverage.journal import INDEX_FILENAME, ReviewJournalEntry, append_entry, now_iso
from core.run import metadata as m
with tempfile.TemporaryDirectory() as d:
    place = Path(d)
    project = place/'index'; project.mkdir()
    run = place/'audit-fixture'; run.mkdir()
    m.start_run(run,'audit')
    append_entry(run,ReviewJournalEntry(ts=now_iso(),run_id=run.name,file='fixture.c',function='f',verdict='clean',source_hash='deadbeef',line_start=1))
    child = '''
import os,sys
from pathlib import Path
from unittest.mock import patch
from core.run import metadata as m
with patch.object(m,'_merge_run_journal',side_effect=lambda _:os._exit(73)):
    m.complete_run(Path(sys.argv[1]),expected_command='audit')
'''
    rc = subprocess.run([sys.executable,'-c',child,str(run)],check=False).returncode
    status = json.loads((run/m.RUN_METADATA_FILE).read_text())['status']
    index = project/INDEX_FILENAME
    print('postcommit child rc, run status, index exists',rc,status,index.exists())
    assert (rc,status,index.exists()) == (73,'completed',False)
    m.project_run_projections(run,project_dir=project)
    assert 'fixture.c' in index.read_text()
    row_count = len(json.loads(index.read_text())['entries'])
    m.project_run_projections(run,project_dir=project)
    print('repaired entry count, second repair',row_count,len(json.loads(index.read_text())['entries']))
    assert row_count == len(json.loads(index.read_text())['entries']) == 1
```

| Other bounded control | Reproduction and result |
| --- | --- |
| Graph and schedule | Call `TaskGraph.from_workqueue` with three named records in `demo.txt`, cost hints 1/50/1000 and priorities 100/20/0, then pop with schedules `priority` and `cost`, each with fairness false and true. Orders diverged only with fairness false. Enumerate all masks on the 12 directed pairs on four distinct keys, feed `caller` and `callee` records for the same file, drain one item per pop, assert retained prerequisites already completed and keys unique. All 4,096 drained and 3,553 dropped one or more cycle back-edges. Repeated with fairness enabled and three ready items per batch on each tested interpreter, with the same counts. [Graph scheduling](repos/gadievron__raptor/core/audit/task_graph.py:235) |
| Tick and budget counters | Use `ExecutorConfig(2)` with five independent `plain.txt` units. Raise one ordinary exception in `on_tick` for a single key. Then compare to a run where a worker raises `LLMBudgetExceededError` without a budget callback and to one that latches a budget callback. Tick result measured dispatched/completed/failed/pending 5/4/0/1 with `complete`. The no-gate budget run visited all five; the latched control issued at most two with no later admission. [Per-task loop](repos/gadievron__raptor/core/audit/executor.py:951) |
| Reservation trail | Create fresh reporting identity, then in a separate Python process use the `_prepared` fixture and `AttemptReservations.admit` before `os._exit(77)`. Wrap `os.fsync` in the child. Reopen with resume, read pending and known spend, add a partial final row, reopen, then restore and reconcile. Measured zero sync calls, one unresolved hold of 240 tokens and $0.25, known zero spend, `truncated_attempt_recovery_trail`, then no pending hold after explicit reconciliation. [Fixture](repos/gadievron__raptor/core/audit/tests/test_prepared_attempt_recovery.py:1) [Reservation reader](repos/gadievron__raptor/core/audit/attempt_reservations.py:131) |
| Watchdog lifetime | In a dedicated child set the grace value to 0.7 seconds, install the handler, signal only that child, uninstall and prove the old handler is restored, then wait past the adjusted grace. No-signal control exits 0; the signaled child exits 130 after its host marker. In another pair use 0.12-second grace and compare a no-delay hook against a local 0.7-second hook. Observed about 0.30s versus 1.00s, exit 130 each. [Signal implementation](repos/gadievron__raptor/core/audit/orchestrator.py:548) |
| Handler and observer lifetime | Inject a benign `ToolDef` that waits on one event, invoke 36 times with a 2ms wait timeout, count the named threads, then release the event and join. Compare the loop with an in-memory text replay and with an observer raising on first emission. Measured 36 live threads versus 32 retained references, all joined after release. The observer's exception retained identity and provider call count was zero. [Loop fixture](repos/gadievron__raptor/core/llm/tool_use/tests/test_loop.py:46) [Tool timeout](repos/gadievron__raptor/core/llm/tool_use/loop.py:1385) |
| Transcript coverage | Use `TranscriptRecorder.record_generate` for one synthetic text response, then build `AuditPipelineOpts` and call the pipeline's client factory with an empty output directory. Repeat with managed running metadata and with the same-run flag. Plain replay yielded the response. Both managed controls raised `TranscriptError` before provider construction. [Audit client factory](repos/gadievron__raptor/core/audit/pipeline.py:336) [Replay guard](repos/gadievron__raptor/core/llm/transcript.py:884) |
| Ownership and metadata fallback | Acquire `acquire_run_lock` in the parent; compare a second thread to a subprocess. Observed `held=True/False` for the two local handles and separate-process refusal. For metadata create a new temp audit, use two `_update_status` calls with distinct `extra` keys, pause the first after `_load_meta`, and compare native validation to injected `OSError(errno.EIO)` from `validate_lock_fd`. Healthy keys `(True, True)`, degraded keys `(True, False)`. [Run lock](repos/gadievron__raptor/core/audit/run_lock.py:411) [Metadata status](repos/gadievron__raptor/core/run/metadata.py:3116) |
