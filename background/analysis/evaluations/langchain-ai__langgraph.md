# LangGraph core orchestration runtime review

## 1. Snapshot, scope, and elapsed time

| Field | Value |
| --- | --- |
| Repository | `langchain-ai/langgraph`, Python runtime package `langgraph` 1.2.22 |
| Checkout | [repos/langchain-ai__langgraph](repos/langchain-ai__langgraph) |
| Pinned HEAD | `bbd52757e72d8611b07ae2831b9529a6ba03f2a1` |
| Commit | `fix(prebuilt): make wrap_tool_call state overrides reach the tool (#9730)` |
| Commit timestamp | `2026-11-18 21:32:59 UTC` |
| UTC start | `2026-11-18 23:46:26 UTC` |
| UTC end | `2026-11-19 00:16:27 UTC` |
| Elapsed active time | **30.02 minutes** (30 min 1 s) |
| Checkout status | Verified clean at start and end with an exact HEAD match and an empty porcelain status. |

The UTC clock readings below record milestones during the active review.

| UTC | Review milestone |
| --- | --- |
| Nov 18 23:46:26 | Started the rubric and checkout verification. |
| Nov 18 23:51:00 | Traced graph compilation, scheduling, task completion, checkpoint capture, and the initial failure controls. |
| Nov 18 23:55:44 | Drafted the architecture and main findings. Checked method spans and earlier test selections. |
| Nov 19 00:00:04 | Completed byte comparisons of selected tests. Read the saver write-failure and task-status assertions. |
| Nov 19 00:05:17 | Checked the executable-task construction paths, checkpoint futures, cache mapping, and stream buffer by AST and source. |
| Nov 19 00:06:39 | Verified the per-packet planner's list-copy cost. |
| Nov 19 00:14:17 | Cross-checked channel lifetimes, checkpoint stage ordering, and the source-only scheduling and policy cases against their closest existing controls. |
| Nov 19 00:16:27 | Verified the pinned HEAD, clean checkout, report sections, and local file and line references. |

The review covers `StateGraph`, direct Pregel and the Functional API, including the local scheduler, channels, task and retry lifecycle, checkpoints, resume and replay, streaming, cache, and extension contracts. The memory and SQLite savers are useful concrete implementations of the persistence contract. Prebuilt test results provide adjacent integration evidence. The assessment excludes UI, SDK transport, hosted execution, security, and external service behavior. This pass uses fresh source and evidence inspection. The test and diagnostic executions cited below come from the earlier local attempts. [Package manifest][package] · [Evaluation rubric][rubric]

**Assessment.** Pregel provides a coherent execution model for parallel state updates, restartable work, and inspection of a run's history. The strongest parts are the shared scheduling and reduction rules, stable task identities, and the distinction between a completed superstep and work already finished within the next superstep. Two issues deserve priority at this pin. The synchronous completion path can lose writes used to reconstruct a `DeltaChannel` under `exit` durability. Worker capacity can also be exhausted by stream waiting or by parents waiting for functional child tasks, leaving runnable work with no execution slot. The earlier local observations agree with the pinned source on these mechanisms. Sections 5 and 8 give their scope and the controls used to check them.

## 2. Architecture and end-to-end control and data flow

### Graph construction

`StateGraph` is a builder for the channel runtime. It collects nodes, edges, branches, schemas, and policies, then creates a `CompiledStateGraph`, a subclass of `Pregel`. An ordinary state key becomes a `LastValue` channel. A compatible `Annotated` reducer becomes a `BinaryOperatorAggregate`, and explicit channel annotations can select other behaviors, including the beta `DeltaChannel`. State, input, output, and node-specific input schemas determine which fields enter, leave, and are read by a graph. The hidden `START` node accepts the input and publishes its initial state and routing writes. `PregelNode` holds the bound runnable, input selectors, triggering channels, writers, and policies. Direct `Pregel` construction with `NodeBuilder` exposes these same components. [State registration][graph-schema] · [Channel selection][graph-channel] · [Compilation][graph-compile] · [Compiled node][graph-node] · [Pregel node][node] · [NodeBuilder][node-builder]

Lifetime and merge behavior are separate decisions. `EphemeralValue` preserves an available value in a checkpoint, then clears it on a later advancing step with no write. `UntrackedValue` retains the latest value during the run and restores empty. Managed values such as `RemainingSteps` are computed from task metadata when projecting input. This lets routing, recoverable application state, and transient runtime inputs coexist without a common storage policy. [Ephemeral channel][ephemeral-channel] · [Untracked channel][untracked-channel] · [Managed value][managed-steps] · [Input projection][algo-input]

The builder compiles a named edge to a write on the destination's routing channel. Several independent incoming edges act as alternatives. A list of sources on one edge creates a named barrier that requires all sources to report before the destination becomes available. Conditional routing executes as a writer after the node body. Its fresh read overlays that task's writes on copies of channels so the branch can use the update just produced by its node. A named route writes a trigger, while each `Send` appends a destination and explicit argument to the internal `TASKS` topic. The destination for a `Send` is run once for each scheduled packet. `Command` couples a state update with routing and can target the parent namespace. In `StateGraph`, `END` suppresses further routing on that edge. Other active work can still proceed. [Edge and join compilation][graph-edge] · [Branches][graph-branch] · [Fresh read][algo-local-read] · [Control writes][command-route] · [Send mapping][send-write]

The Functional API converges on the same engine. `@entrypoint` builds a single Pregel node with input, output, and `PREVIOUS` channels. `entrypoint.final` can distinguish the returned value from the one recorded for the next invocation. `@task` uses the injected call hook and returns a future. The loop can schedule that work within the current superstep, using the parent task's path and call ordinal to re-identify it. A graph `Send` instead becomes a separate task in the following superstep. Calls can reuse a recorded `RETURN` write on replay. An awaiting functional parent can therefore restart while previously completed child work is recovered by identity. [Functional entrypoint][functional-entry] · [Functional call][functional-task] · [Child task preparation][algo-functional] · [Runner child submission][runner-call] · [Send task preparation][algo-send]

### Invocation and supersteps

1. `invoke` and `ainvoke` consume the values stream and assemble the return value. `stream` and `astream` normalize config, select output keys and policies, install callbacks and a `Runtime`, and open the corresponding loop context. The loop loads a checkpoint by thread and namespace, or creates an empty state, reconstructs channel instances, and interprets the input as a fresh turn, continuation, or replay. The runtime carries contextual dependencies separately from state, including the store, writer, heartbeat, execution metadata, and run drain signal. [Invoke][invoke] · [Stream driver][sync-driver] · [Async driver][async-driver] · [Loop entry][loop-enter] · [Runtime][runtime]
2. `tick()` plans the next superstep with `prepare_next_tasks`. It reads the queued `Send`s and prepares a PULL task for a node when an available subscribed trigger has a version the node has yet to see. A reverse trigger index limits the candidate set when prior changed channels are known. The plan gives each task a stable ID, input projection, config, write deque, scratchpad, and policy. On a continued head, successfully completed tasks receive their recorded writes and can be skipped. The loop checks static breakpoints and the drain signal before submitting work. [Plan][algo-plan] · [PULL task][algo-pull] · [Version predicate][algo-trigger] · [Tick and reuse][loop-tick]
3. The driver matches node cache entries and passes executable tasks with empty write buffers to `PregelRunner`. A single task can execute inline when there is no step timeout or stream waiter. The regular lane submits work to the synchronous thread pool or asynchronous event-loop executor. Each task runs through its runnable and writers. Writers hand off state changes and route events through the injected `CONFIG_KEY_SEND` callback into the task's deque. Completion records ordinary output, a no-output marker, or control records for an exception or interrupt. The runner yields to the driver so it can deliver events as work completes, and waits for completion callbacks on the normal success path. [Task config][algo-pull] · [Write adapter][write-adapter] · [Sync runner][runner-tick] · [Async runner][runner-atick] · [Completion][runner-commit] · [Executors][executor]
4. `after_tick()` applies writes from the tasks at the barrier. It records the trigger versions consumed, calls channel `consume`, sorts by canonical task path, groups writes by channel, and calls each channel's reducer or update operation. A changed, available channel is eligible to trigger its subscribers in a later step. Unwritten available channels receive an empty update on an advancing step, which expires transient values. A tentative finish calls channel `finish`, which can release deferred work. The loop publishes `values`, stages checkpoint persistence, and checks after-breakpoints. It terminates when there are no tasks, when control requests a drain at a boundary, or when execution exhausts its step budget or raises. [Barrier][algo-apply] · [After tick][loop-after] · [Run exit][run-exit]

For two ordinary parallel nodes that append to one state key, both receive inputs from the same committed step. They may complete and stream updates in either order, but their writes reduce in the task-path order. A node that reads that key in the following step sees the reduced value. If the state key uses a single-value channel, the same step instead receives an explicit multiple-write error. A list-edge join tracks completion signals separately from this state merge. This separation is the reason control flow, execution order, and state ordering can be reasoned about independently. [Barrier][algo-apply] · [Single-value guard][last-value] · [Join channel][barrier-channel] · [Live versus replay order assertions][test-order]

For a concrete trace, consider a dispatcher that writes a `query`, conditionally queues two `Send` packets, and has an aggregate `results` field. The conditional writer can select packets using the query it just produced. The next barrier publishes the query and the packet topic. Planning the following step creates a task per packet with that packet's argument. If both workers signal the same ordinary downstream destination, its unguarded routing channel coalesces those signals into one PULL in the next plan. Its input includes the aggregate of both workers' results. A named join encodes the stronger condition that particular source names have all signaled. An ordinary downstream subscription alone carries no count of outstanding packet tasks. [Fresh routing][graph-branch] · [Packet writes][send-write] · [Packet task construction][algo-send] · [Trigger coalescing][graph-node] · [Named join][graph-edge]

### Durable state, resumption, and replay

A saver addresses a revision by `thread_id`, `checkpoint_ns`, and `checkpoint_id`. A `CheckpointTuple` includes its configuration, channel values and versions, per-node `versions_seen`, metadata, parent configuration, and pending task writes. The parent pointer describes checkpoint lineage, while `versions_seen` preserves what downstream nodes should run. Ordinary channel state hydrates through `from_checkpoint`. The `TASKS` topic is part of the state, and task IDs are derived from checkpoint identity, namespace, step, and task path or push ordinal. This lets execution rebuild the frontier and attach the writes to the tasks that made them. Compatibility code migrates older routing and pending-send representations. [Checkpoint objects][checkpoint-types] · [Hydration][checkpoint-hydration] · [Task identity][algo-pull] · [Graph migrations][graph-migrate]

Savers allocate comparable monotonically increasing versions, and the scheduler uses one version type across the channel map when setting defaults and comparisons. Ordinary checkpoint writes are keyed by task occurrence and write position. Control outcomes can use reserved positions so an interrupted task's latest question can replace its earlier question. This is how the saver can retain each task's completion record and update control records during continuation at the same checkpoint. [Version contract][saver-version] · [Version comparison][algo-trigger] · [Write keys][memory-write-keys] · [Task status][task-status]

Pending writes are recorded against the checkpoint from which a task ran. A successor checkpoint describes the state after reducing that step. A fresh turn can create an input checkpoint before the first task executes, and historical replay can create a fork checkpoint at the same stage. With a saver, `sync` waits for the checkpoint save after a completed tick before entering the next tick, `async` lets work overlap with ordered saves, and `exit` generally defers the saver writes until the loop exits. The latter still advances in-memory checkpoints and has special handling for accumulated delta history and unfinished work at exit. Checkpoint saves in one loop are chained. The successor save explicitly waits for pending delta write futures it relies on, and executor teardown settles outstanding jobs during an ordinary completed or interrupted invocation. A stream event and saver durability can therefore occur at different points. [Durability definitions][durability] · [Input checkpoint][loop-input-checkpoint] · [Fork checkpoint][loop-first] · [Checkpoint submission][loop-save] · [Save dependencies][loop-save-ordered] · [Exit writes][loop-exit-saves] · [Executor teardown][executor-exit]

`DeltaChannel` trades repeated full-value persistence for saved writes with periodic full snapshots. Hydration batches the channels that need history into one saver call. The reference saver walks the target's parent chain once, finds the nearest seed for each channel, and returns the deltas leading to the target. The target checkpoint's own pending writes belong to work proceeding from it. Within each ancestor, saver ordering mirrors the live task-path ordering. Since replay can send many supersteps' writes to a reducer in one batch, the reducer must be deterministic and batching-invariant. Cadence can force a snapshot after updates or after a number of elapsed supersteps. An overwrite or a fork that must exclude another branch's pending writes can also force a snapshot. A snapshot-only version bump is marked seen for subscribers that already saw the old value, so a storage-only change preserves the existing scheduling frontier. In `exit` mode a first run can leave a minimal ancestor to anchor deltas that the final checkpoint needs. Synthetic write identities preserve step order with one physical anchor and keep the staged rows distinct from real task completion records. [Delta channel][delta] · [History contract][checkpoint-history] · [Reference saver walk][saver-history-walk] · [Snapshot cadence][snapshot-cadence] · [Snapshot-only versions][snapshot-bumps] · [Exit delta staging][loop-exit-deltas] · [Synthetic identity and ordering][exit-delta-ids]

`interrupt()` in a node either returns the reply for its task-local slot or raises a `GraphInterrupt` with an ID and payload. When a Python response type is supplied, the function validates the reply before emitting its resume record. A raw JSON Schema is an advertised response shape. The runner persists interrupt and resume control records and lets already-running siblings finish on the normal interrupt path. At the root, interruption is translated into output and lifecycle events. On that exit path the loop can apply available sibling writes to its in-memory output view while the saver retains the step's task records for continuation. Continuation starts the interrupted node from its first line, reuses its earlier slot answers, and uses completed sibling writes where applicable. Static `interrupt_before` and `interrupt_after` work at step boundaries and use channel versions to tell whether a breakpoint has already been passed. Strict resume can reject an unknown or ambiguous answer before applying it. [Interrupt][interrupt] · [Completion and sibling handling][runner-commit] · [Interrupt exit][loop-interrupt-exit] · [Breakpoint versions][algo-interrupt] · [Resume classification][loop-first] · [Strict resume validation][loop-resume]

Running from the current interrupted head and intentionally replaying a historical checkpoint have different semantics. The former can reuse the recorded outputs of tasks at the current step. Historical replay can run them again, removes old resume answers for time travel, and can create a new fork before tasks execute so subsequent interrupts attach to that fork. Subgraphs carry namespace mappings and can inherit the parent's saver with per-invocation task scope. `checkpointer=True` on a subgraph uses a stable task-ID-free namespace for a persistent subgraph history, and `False` opts out. During parent replay, the first visit to a child scope loads the latest applicable checkpoint before the replay bound. Later visits can pick up checkpoints created by the replay itself. [Resume and forks][loop-first] · [Subgraph saver selection][resolve-saver] · [Nested replay context][loop-replay-context] · [Replay state][replay-state]

The state APIs expose live and historical views. The reader reconstructs channels and task identities for a revision. A head read overlays saved task outputs and reports the remaining tasks and unanswered interrupts. An addressed read shows the checkpoint and the original frontier, including recorded interrupts, with task outcomes available as records. Both views can apply writes scoped to the whole step through the null task. State history materializes the saver results before yielding snapshots to release the storage cursor. For mutations, `update_state` delegates to the same mechanism as one bulk-update superstep. It selects a node explicitly or infers it from version history when unambiguous, runs its writers on the supplied output, and persists a new transition including routing. [State snapshot][state-snapshot] · [Pending-write overlay][state-overlay] · [History materialization][state-history] · [Writer inference][infer-writer] · [Update-state writers][state-update]

### Streaming, retries, caching, and extension surfaces

- **Streaming.** The loop emits `updates` and task results on individual task completion and `values` when the barrier updates an output channel. It can also emit checkpoints, tasks, debug, custom writer output, and message or tool events through callbacks. `stream`/`astream` v1 shape depends on mode and namespaces. V2 yields tagged parts with `type`, `ns`, and `data`, plus interrupts on values parts. `stream_events`/`astream_events` v3 is a separate experimental consumer layer over the same v2 driver. A run handle pumps on demand, normalizes parts to protocol events, and dispatches them through a scoped `StreamMux`. The mux offers projections for values, messages, lifecycle, and subgraphs with additional transformers at build or call time. Child scopes share the root pump. The async handle coordinates pulls so only one consumer advances the underlying generator at a time. [Stream emission][loop-emit] · [Versioned output][stream-output] · [V3 adapter][stream-v3] · [Transformer dispatcher][stream-mux] · [Async pump][stream-pump]
- **Retries and failure.** Retry selects the first matching policy, clears previous attempt writes, and reruns with backoff and attempt metadata. The runner's step deadline covers the execution wave. The async lane can additionally start a run watchdog, an idle watchdog, or both for each attempt. Idle progress can come from the heartbeat alone or from selected writes, callbacks, stream events and child calls. On timeout the attempt closes its write scope, clears the task buffer, and requests cancellation before raising a typed timeout. Node error handlers are separate tasks prepared with the failed node and exception context. The loop records an error-routing marker for resume and waits on tracked write futures when scheduling handlers. `GraphBubbleUp` signals take a separate path from ordinary policy failures. `RunControl` requests a cooperative stop before the next superstep. [Retry][retry] · [Step deadline][runner-submit] · [Progress and guarded writes][timed-scope] · [Attempt watchdogs][timeout] · [Error-handler scheduling][loop-handler] · [Run control][run-control]
- **Caching.** Optional policies turn projected PULL input, the `Send` argument, or Functional call arguments into a digest under a runnable namespace. The cache stores task writes, which allows a hit to participate in the same reducers and routing as a real invocation. Cache hits pass through the write path for persistence and skip cache insertion. Error and interrupt records are excluded from caching. A checkpoint can reuse writes for a particular task occurrence without a cache policy. The cache can reuse equivalent input across occurrences and threads if its configuration makes that equivalence valid. [Cache policy][cache-policy] · [PULL key][algo-pull] · [Send key][algo-send] · [Functional key][algo-functional] · [Cache matching][loop-cache] · [Cache hit assertions][test-cache]
- **Extensions.** A custom channel supplies update, read, availability, checkpoint, and restoration behavior, with possible consume and finish hooks. A saver supplies synchronous or asynchronous retrieval, ordered enumeration, checkpoint and write persistence, channel versions, and delta history support. `BaseStore` is dependency injection for application data with its own lifecycle. The graph's checkpoint only describes graph progress. `BaseCache` and stream transformers are separate extension interfaces. `Runtime` and LangChain runnables give nodes access to context, observation, and graph execution without having to implement the scheduler. [Channel interface][base-channel] · [Saver methods][base-saver] · [Store API][base-store] · [Cache API][base-cache] · [Transformer registration][stream-register] · [Runnable adaptation][runnable-coerce]

## 3. Why the design works and its governing invariants

| Invariant | What preserves it and where the guarantee ends |
| --- | --- |
| Single logical state transition per completed superstep | Tasks buffer writes in private deques. `apply_writes` performs the shared transition once after task completion. A fresh route sees its own writes. The abstraction assumes callbacks treat nested channel values as read-only. `_proc_input` builds a projection and only shallow-copies a reused projection. Channels such as `LastValue` return the value object. An aggregate's fresh-read copy can also share its accumulator with the live channel, so reducers should return a value without mutating the existing accumulator in place. |
| Eligibility derives from available, unseen triggers | The framework advances the version when a channel's update, consume, or finish hook reports a change. This is a channel-defined transition and can occur even when a newly written value compares equal to the previous one. A node's observed versions suppress repeat scheduling until its trigger changes. The updated-channel index narrows the scan. The `Send` topic has separate eligibility in `prepare_next_tasks`. |
| Task identity is repeatable for a checkpoint and plan | Task IDs derive from the persisted step identity and task path. Functional calls also use the call ordinal. A restart of the same plan finds the same writes. Changing the graph or the order of calls during replay can change how recorded work is addressed. |
| Completion order and reducer order are distinct | Updates can stream as tasks finish. The barrier and delta playback use task-path order. `LastValue` enforces single-write cardinality. Aggregates explicitly define how multiple writes combine. Delta reducers must additionally produce the same value after equivalent regroupings of the same ordered writes. |
| Visible checkpoints that depend on a delta log need complete ancestry | Save chaining orders writes and snapshots, and snapshots stop the read walk at a branch-safe boundary. Replay excludes the target's own following-step writes. The synchronous `exit` write-collection issue in section 5 violates completeness upstream of the saver. |
| Task completion and whole-run completion are separate | Checkpoints hold task-level outputs and control records. `NO_WRITES` distinguishes a finished no-output task from an unfinished one. A snapshot or resumed step derives pending interrupts and task status from those records. `invoke` returns the accumulated result after the run settles or pauses. |
| Durability concerns graph state and task records | User side effects, callbacks, application store operations, and arbitrary node code have separate lifecycles. A retry or replay can run a task again. External side effects need their own idempotence or coordination. One run's ordered checkpoint writes also give no transaction spanning independent invocations on the same logical thread. |

[Input projection][algo-input] · [Channel reads and copies][last-value] · [Aggregate copy][aggregate-copy] · [Scheduling][algo-plan] · [Reduction][algo-apply] · [Checkpoint ancestry][checkpoint-history] · [Task status][task-status] · [Retry][retry] · [Saver contract][base-saver]

## 4. Strengths

- **One execution model for three programming styles.** The state builder translates high-level topology into a node/channel plan. Functional entrypoints and direct Pregel construction participate in the same loop. The benefit is that persistence, task identity, retry, and streaming are available across these front doors without three independent schedulers. [Compilation][graph-compile] · [Functional entrypoint][functional-entry] · [NodeBuilder][node-builder]
- **Deterministic aggregation with observable concurrency.** Stable path order makes reducer behavior and persisted playback comparable even during a parallel wave. Explicit single-writer failures and join channels make two common reasoning errors easy to diagnose. Completion-time events still surface progress before the whole step finishes. [Barrier][algo-apply] · [Single-value guard][last-value] · [Join channel][barrier-channel] · [Stream emission][loop-emit]
- **Checkpointing records execution progress as well as data.** The state includes channel versions, task status, pending writes, and branch lineage, giving users tools to continue a partially finished step, inspect the current frontier, and deliberately replay a past decision. Tests around scoped subgraph histories, addressed-head resumes, interrupted siblings, and multiple durability modes document important behavioral contracts. [Checkpoint structure][checkpoint-types] · [State and replay][loop-first] · [Addressed-head regression][test-resume-head] · [Parallel interruption regression][test-exit-parallel]
- **Ready-to-use observability without a separate scheduler.** Task, checkpoint, state and lifecycle streams provide different perspectives on the same transitions. `ExecutionInfo` includes checkpoint, namespace, task, and attempt metadata. Experimental v3 transformers can project a run's native event flow into specialized views while reusing the existing runtime. [Execution metadata][execution-info] · [Lifecycle callback contract][graph-callbacks] · [V3 adapter][stream-v3]
- **Saver contracts have executable conformance tests.** Task writes are tested for task identity, ordering and idempotence across savers. Delta history tests check ancestor selection, exclusion of target pending writes, and the ordering needed by noncommutative reducers. A migration test compares the reference saver fallback with the optimized memory path at every snapshot. [Write conformance][saver-write-conformance] · [Delta order conformance][saver-delta-conformance] · [Fallback parity][test-saver-fallback]
- **Operationally useful compatibility work.** Old checkpoint versions, pending sends, task path support in savers, and old and current streaming envelopes are handled explicitly. Delta snapshot cadence is separated from logical trigger state, and the tests check that migration and replay preserve meaningful state. [Graph migrations][graph-migrate] · [Saver signature compatibility][saver-path] · [Snapshot-only versions][snapshot-bumps] · [Versioned output][stream-output]

## 5. Weaknesses

### W1. High impact — synchronous `exit` durability can lose delta writes

Earlier runs with parallel synchronous `Send` tasks returned a complete list live and subsequently restored an incomplete list from the same thread. Repeated observations exist for both the memory and SQLite savers, including observations at the normal interpreter switch interval. The logs and source support state loss on this path. Section 8 documents the controls and distinguishes the observed condition from other durability modes. [Synchronous memory evidence][fanout-normal] · [Synchronous SQLite evidence][fanout-sqlite]

Synchronous futures can call `FuturesDict.on_done()` on different workers. It invokes `PregelRunner.commit()` before acquiring its bookkeeping lock. `commit()` calls the loop's `put_writes()`, which reads the accumulated list, filters it into a replacement list, assigns the replacement, and extends it with the current task's writes. Two callbacks can construct replacements from the same previous list. If one installs a replacement and adds its writes before the other installs its stale replacement, those added rows can disappear. The sequence of reading, replacing, and appending to the shared list has no atomic boundary. [Completion callback][runner-future] · [Commit][runner-commit] · [Pending-write mutation][loop-put-writes] · [Worker completion semantics][stdlib-worker] · [Future callbacks][stdlib-future]

The live barrier reduces the tasks' own write deques. In `exit` mode, the delta accumulator instead reads the shared pending-write list after the barrier. Under snapshot cadence, missing accumulator entries are missing from the saved history even though the live value was right. Publication waits on the writes that were actually staged. That ordering cannot recover writes lost before staging. The two representations explain how a call can succeed and restore short. The same list replacement also scans existing rows on each commit, giving quadratic traversal in the number of similarly sized completions in a wide step. The evidence establishes this code shape and the observed failure, without estimating a production failure rate. [Barrier and delta capture][loop-after] · [Per-task persistence in other modes][loop-write-save] · [Exit delta staging][loop-exit-deltas] · [Save ordering][loop-save-ordered]

### W2. High impact — a stream waiter can occupy the only synchronous worker

With synchronous `StateGraph.stream`, `stream_mode="custom"`, and `max_concurrency=1`, the saved run recorded the sole worker waiting on an empty stream and the driver waiting in `PregelRunner.tick`. The recorded progress stopped before the first user node. The runner submits its stream waiter before submitting the producers. The waiter uses the same pool, and the pool size comes directly from the configured cap. With an empty stream, the waiter needs the producer and the producer needs the only worker slot. The cleanup release is reached only once the loop exits. The async stream puts its waiter on a separate event-loop task. [Sync stream waiter][sync-waiter] · [Runner submission order][runner-submit] · [Worker pool][executor] · [Pool sizing][lc-pool] · [Queue wait][queue-wait] · [Async waiter][async-waiter] · [Prior stack and controls][conc-stream]

### W3. High impact — functional parents can exhaust capacity while waiting for children

An entrypoint or node that waits on an unresolved `@task` can occupy a worker or hold a semaphore permit while the child needs capacity from that same executor. If all slots are occupied that way, submitting the child and chaining its future creates a wait cycle. In the async path, awaiting a future yields event-loop execution but the semaphore stays acquired around the parent coroutine. In the sync path, the parent blocks inside its worker. The single-task inline fast path can leave a slot free, which accounts for the successful single-node graph controls. The Functional API's eager streaming ordinarily selects the scheduling lane where the parent is itself submitted. The synchronous waiter can consume an additional slot, but the two-parent graph controls and async findings show that this is a separate problem. [Sync child scheduling][runner-call] · [Async child scheduling][runner-acall] · [Async permit lifetime][executor-gate] · [Functional entrypoint][functional-entry] · [Inline lane][runner-tick] · [Prior controls][conc-functional]

### W4. Medium impact — queued `Send` work can release deferred nodes early

Source establishes a scheduling case shared by sync and async. A `defer=True` trigger stays unavailable until `finish()`. The tentative finish test asks whether the changed channels intersect the reverse subscription index. A `Send` packet makes `TASKS` available through its own scheduling path. `StateGraph` nodes subscribe to named routing channels and any join channels, leaving the `TASKS` topic outside their subscription index. When a deferred trigger is ready and the only remaining ordinary work is queued by `Send`, `finish()` can release the deferred channel, and the next plan contains both the deferred PULL and the packet tasks. The deferred node then gets its input before those packet results are applied. This is a mismatch with the documented late execution of a deferred node. Existing defer regressions exercise normal edge and join triggers. I traced this combination statically. [Defer contract][defer-doc] · [Deferred channel][defer-channel] · [Finish predicate][algo-finish] · [Trigger index][trigger-index] · [Task plan][algo-plan] · [Defer regression][test-defer]

For example, a dispatcher can return one packet and the deferred node name from its conditional route. The branch accepts that mixed list and publishes a packet and a deferred trigger. If the worker then routes to an ordinary successor, the next step still contains that successor after the deferred node has already run. That topology distinguishes premature release from the harmless case where the packet and the deferred node happen to be the last things to finish. [Branch destination handling][mixed-branch] · [Branch writes][branch-writes] · [Finish predicate][algo-finish]

### W5. Medium impact — recompilation can turn a generated default handler into a collision

`compile()` inserts its generated default handler into the builder's `self.nodes` and applies inherited settings directly to the node specs. The next compilation with the same default handler reaches the existing-name check and raises a collision on the name that the first compilation installed. This is recorded in the prior local output. Changing another default after one compilation can also leave existing specs holding earlier resolved values, since the next resolution fills only unset fields. There is evidence for calling `compile()` repeatedly on the same builder in ordinary use. The default-handler tests cover explicit user collisions and first compilation. [Default configuration][node-defaults] · [Compile-time mutation][compile-mutation] · [Recorded result][contracts-compile] · [Repeated builder use][test-recompile] · [Default-handler coverage][test-defaults]

### W6. Medium impact — a batch cache hit is delivered to one task per key

Both cache matchers build a dictionary from the cache key to a single task. Several distinct `Send` occurrences of the same node can share a key if their projected arguments match. The matcher asks the cache once, then fills only the last task retained for that key. Other tasks still have empty writes and go through execution. Equivalent input can therefore miss the intended reuse within a warm batch. This is a source-derived inefficiency for cacheable, interchangeable results. There is no evidence that normal cache reads or checkpoint reuse generally fail. [Distinct scheduled sends][algo-send] · [Topic retention][task-topic] · [Sync cache matching][loop-cache] · [Async cache matching][loop-cache-async] · [Driver scheduling][runner-driver]

### W7. Documentation and delivery tradeoff — v3 `maxlen` is unenforced

The v3 `AsyncGraphRunStream` docstring describes a subscribed reader's `maxlen` as backpressure. `StreamChannel` validates and retains that argument for compatibility, creates an unbounded deque, and appends to it with no size check. The async mux calls this same immediate append. Caller-driven pumping and lazy subscription avoid buffering for channels nobody subscribes to. A faster projection or raw event cursor can still fill another subscribed cursor's buffer, and `tee` branches each keep their own queue. The evidence establishes the queue behavior and documentation mismatch. [Async handle documentation][stream-buffer-doc] · [Channel constructor][stream-channel] · [Push semantics][stream-channel-push] · [Async mux append][stream-mux-async] · [Tee queues][stream-tee]

### W8. Low impact — an empty command raises an internal exception

`_first()` sets `resume_is_map` only when the command has a non-`None` resume value. A `Command()` or `Command(resume=None)` with no effective update or destination yields an empty write set. The empty-command guard then reads that unassigned local and raises `UnboundLocalError` before it can issue its intended `EmptyInputError`. The earlier bare-null observation reached this line in the matched runtime. An ID-addressed reply can carry `None` as its value. [Command mapping][map-command] · [Empty-command guard][empty-command] · [Recorded bare-null traceback][contracts-resume-error] · [Typed resume lookup][interrupt-implementation]

### W9. Medium impact — error-handler dispatch drops the configured node timeout

`set_node_defaults(timeout=...)` explicitly covers error handlers and compilation sets the prepared handler node's timeout. The separate `prepare_node_error_handler_task` path leaves `PregelExecutableTask.timeout` at `None`. Async retry starts the watchdog only from the executable task's timeout field. This means a configured deadline can constrain the failed node and leave its automatically scheduled recovery handler unlimited by the same policy. The result follows directly from the constructor and both dispatch paths. Timing and production frequency are unmeasured. [Builder defaults][node-defaults] · [Compiled policies][node-policies] · [Handler task constructor][handler-task] · [Executable task fields][executable-task] · [Timeout selection][async-retry]

### W10. Medium impact — `sync` durability assumes a checkpoint future even with persistence disabled

Both drivers warn that an explicit durability mode has no effect without a saver. `_defaults` retains `"sync"` and the loop creates a persistence future only if it can submit a save. After the first completed tick, the sync and async drivers access the missing `_put_checkpoint_fut`. The resulting `AttributeError` follows from the source path even for a graph with otherwise valid input and an ordinary completing node. The same condition can arise when a parent propagates `"sync"` to an opt-out subgraph. This path was checked by source inspection. [Warning][sync-durability-warning] · [Durability defaults][runtime-defaults] · [Saver selection][resolve-saver] · [No-saver configuration][sync-no-saver] · [Checkpoint submission guard][checkpoint-enabled] · [Sync wait][sync-save-wait] · [Async wait][async-save-wait]

### W11. Scaling cost — each packet task copies the entire pending `Send` topic

The planner uses one `Topic.get()` to enumerate packet indices, then the per-packet constructor calls `Topic.get()` again to fetch each indexed argument. The built-in `Topic.get()` returns a list copy. For a frontier of *n* packets this path copies *n* references *n* additional times, for quadratic list-copy work during planning before user task execution begins. The cost is independent of worker mode and the programmed node bodies. Keeping the original packet snapshot or passing the packet with its index would preserve occurrence identity and remove the extra copies. The archived timings combine planning, work, persistence and readback, so they do not quantify this cost in isolation. [Internal topic][task-topic-init] · [Packet enumeration][push-plan-read] · [Packet fetch][push-arg-read] · [Topic copy][topic-read]

## 6. Core code quality

| Dimension | Assessment |
| --- | --- |
| Decomposition | The distinction among plan compilation, scheduling and reducers, loop state, runner and executor, and storage is clear. Checkpoint ordering and task-status reconstruction are deliberate units. `main.py` owns state inspection and mutation, invocation shape and versions, callback orchestration, and streaming adaptation. It spans 4,585 lines in this checkout. The synchronous and asynchronous bulk-update implementations span 502 and 498 lines. |
| State and concurrency | Channel instances and the loop are per-run. Task-local buffers and ordered barrier application are a strong model. The implicit `configurable` protocol mixes callbacks, task identity, dependencies, and control flags. Shared mutable values, the completion callback's thread context, and shared worker capacity depend on runtime conventions visible in the implementation. |
| Error handling | Invalid graph updates, recursion exhaustion, timeout, interrupts, drains, and invalid resume values have distinguishable paths. Retry clears attempt writes and labels attempts. A node-raised cancellation is translated to a node failure where the framework can distinguish it from runtime cancellation. Running synchronous Python work is cooperative with teardown and a step timeout cannot preempt that work. |
| Types | Public graph generics, `Command` and `Interrupt` types, stream-part types, and the channel and saver interfaces help callers. Dynamic projection and Python callable normalization warrant some `Any`. Deep pathways still depend on spellings of string keys, tuple paths, control-channel names, and overload-heavy compatibility code. Runtime schema coercion is distinct from type hints. A state input schema rarely implies validation of all intermediate channel updates. |
| Tests | Backend and durability parametrization, state and pending-write assertions, and paired sync/async files provide strong regression support. Smaller targeted tests cover ordering, retry policy, and event transformation. The important blind spots in the reviewed evidence are composition cases across concurrency settings, functional child calls, auxiliary streaming work, delta replay, and deferred scheduling. |
| Observability | Lifecycle and task events, graph callbacks, attempt metadata, and history make ordinary progress inspectable. Node-level `TracePolicy` can summarize that node's tracer payload while operational callbacks and stream consumers retain the runtime values. A `values` or `updates` event represents a runtime observation. Checkpoint durability depends on the saver and the configured persistence mode. A worker dependency cycle can stall before an expected task event or node callback. |
| Extensibility | The channel, saver, store, cache, Runnable, and transformer boundaries are useful and distinct. A saver that's structurally compatible still needs correct version progression, ancestry, write identity and ordering, and sync or async behavior for the methods it serves. Keeping optional capabilities such as task paths working across saver versions adds real maintenance work. |
| Maintainability | Shared `_algo` and loop methods make invariants findable. Scheduling setup, state snapshots, explicit state updates, retries, and streaming still have duplicated sync and async paths. Delta exit staging and fork guards carry numerous temporal flags. `_put_checkpoint` identifies its exit call by metadata object identity, a concrete example where call order and representation are doing the work of an explicit protocol. |

[Graph API][graph-schema] · [Sync bulk update][bulk-update] · [Async bulk update][abulk-update] · [Config and injected parameters][runnable-injection] · [Attempt metadata][execution-info] · [Retry and cancellation][retry] · [Node trace callbacks][trace-policy] · [Checkpoint phase check][loop-save] · [Extension contracts][base-channel] · [Saver contract][base-saver]

## 7. Executed tests and limits of the evidence

This pass executed read-only source and evidence checks. The two earlier isolated attempts produced the results below. The counts describe separate runs with different selections.

| Existing run | Result | Interpretation |
| --- | --- | --- |
| CPython 3.12.16 core, archived default run | **2,950 passed**, 43 skipped, 181 warnings, 58 snapshots passed in 119.39 s | Broad core behavior with a reduced fixture selection. Fixture availability, deselection and skips limit coverage. [Log][core-312] |
| CPython 3.13.16 core, archived strict run | **1,750 passed**, 147 warnings, 44 snapshots passed in 78.29 s | Independent environment and selected cases, with fixture coverage that differs from the Python 3.12 run. [Log][core-313] |
| CPython 3.12.16 prebuilt, later run | **446 passed**, 193 warnings, 16 snapshots passed in 6.22 s | Adjacent integration evidence. The log shows 446 collected items, the active `pytest-asyncio` plugin, and two passing state-override cases specific to the pinned commit's subject. [Log][prebuilt] · [State override cases][prebuilt-state-test] |

The prior attempts also generated targeted local logs for delta restoration, concurrency, and same-thread branching. They are used in section 8 with their controls. I compared the archived source and installed runtime files against the clean pinned checkout. This confirms the reviewed implementations match the archived environments. The quiet core summaries retain aggregate results and selected test names. The assertions below describe test design. The warning totals are part of each run's metadata. [Test fixture selection][test-fixtures] · [Default core summary][core-312] · [Strict core summary][core-313]

| Repository tests inspected | What their assertions establish when they run |
| --- | --- |
| Pregel sync and async fan-out and concurrency tests | Complete reduced outputs, explicit caps on simply parallel nodes, interruption, and resumed output. The showcased cap test uses independent leaves. |
| Delta exit-mode, write-failure and parallel-order tests | A first sparse run creates an ancestor stub when required, snapshots can replace deltas, replay order agrees with live order, and a resumed step combines saved and new writes. Other tests assert that a failed saver write leaves valid history and can be retried. The small parallel cases and async ordering tests leave the synchronous wide exit-mode collector exposed. |
| Time travel, subgraph persistence, and strict resume tests | An explicitly addressed current head can continue, historical replay re-asks as appropriate, nested namespaces resolve to the right state, and invalid or ambiguous answers leave the pending question available. |
| Runner-futures, retry, and node defaults tests | The completion event distinguishes handled and unhandled failures, watchdogs enforce their attempt policies, and the graph can route an error to a configured handler. The futures unit tests complete mock futures serially. |
| Core stream events and projection tests | Version adapters, namespace scoping, transformer output, interleaving and teardown have direct assertions. A transformer unit test by itself says little about graph executor progress under a worker cap. |

[Capacity assertion][test-cap] · [Delta hydration][test-exit-first] · [Parallel order][test-order] · [Write failure][test-delta-write-failure] · [Head versus replay][test-resume-head] · [Live versus historical state][test-live-state] · [Concurrent interrupt replies][test-interrupts] · [Futures unit tests][test-futures] · [V3 end-to-end tests][test-v3]

## 8. Measurement audit

### Provenance and measurement boundaries

I checked the commit and clean status directly on the source checkout. The earlier testing directory has a source snapshot and separate virtual environments. I used read-only byte comparison on 76 scoped core Python modules, 10 checkpoint/cache/store modules, 8 SQLite modules, and 7 prebuilt modules. The compared files matched in the archived snapshot and both the Python 3.12 and Python 3.13 core environments. The prebuilt modules also matched in the dedicated prebuilt environment and the SQLite modules matched in the dedicated SQLite environment. All 29 selected test and fixture files matched the archive. The concurrency logs also identify the actual executor import path. This checks for install or snapshot drift in the paths used for the findings. [3.12 environment][venv-312] · [3.13 environment][venv-313] · [Prebuilt environment][prebuilt]

### W1. Restore mismatch versus a graph, saver, or measurement error

| Archived comparison | Observed result |
| --- | --- |
| Synchronous memory saver, `exit`, 1,000 results, normal 0.005 s switch interval | All 1,000 live each time. Restored counts `1000`, `847`, and `958`. [Log][fanout-normal] |
| Same mode, 5,000 results, normal switch interval | All 5,000 live each time. Restored counts `4810`, `4697`, `3914`, and `4856`. [Log][fanout-wide] |
| `exit`, shorter recorded switch interval, same 1,000-result shape | Memory restored `696`, `695`, `700`. SQLite restored `693`, `703`, `681`. [Memory log][fanout-short] · [SQLite log][fanout-sqlite] |
| Synchronous memory saver, per-step `sync` and `async` durability | Both comparisons restored all 1,000 in all three runs. [Sync mode][fanout-sync-mode] · [Async mode][fanout-async-mode] |
| Async execution with `exit`, or synchronous `exit` with one worker | Both restored all 1,000 in all three runs. [Async execution][fanout-async-exec] · [One worker][fanout-serial] |
| Synchronous `exit` with a full snapshot or an ordinary aggregate | Both restored all 1,000 in all three runs. They bypass sparse-history reconstruction for the value. [Snapshot control][fanout-snapshot] · [Aggregate control][fanout-plain] |

- **Oracle and identity.** The archived harness used a deterministic batch concatenation reducer and one distinct integer per `Send`. It compared both live and restored lists with the full expected sequence. Each repeated measurement used a fresh thread, and the history read used the config returned by `get_state` for that thread. The restored results were unique. The field logged as `write_blobs` counts history writes returned by the saver API. It was exactly restored length plus one for the sparse cases, consistent with the input's empty-list write adding one history entry and zero elements. This rules out ordinary ordering changes, a stale selected branch, and a length-only oracle as explanations. [Archived oracle and state read][fanout-oracle]
- **Mechanism.** The worker invokes registered callbacks synchronously when its future completes. The runner's lock covers the done set, counter and wakeup, after invoking the callback. Successful writes live independently in each task deque, and the barrier uses those deques. The exit accumulator reads the shared pending list whose compound reassignment is unsynchronized. Distinct task IDs are part of the plan, and the mechanism loses records before the exit helper groups and persists them. Waits on the write futures therefore order publication without noticing the missing records. [Worker completion][stdlib-worker] · [Future callbacks][stdlib-future] · [Runner lock][runner-future] · [Pending-write mutation][loop-put-writes] · [Exit accumulator][loop-after]
- **Alternatives and bounds.** A single worker removes overlapping sync callbacks. Async keeps these callbacks on its event loop. Per-step durability persists each task's writes individually in addition to updating the in-memory list. Forced snapshots and plain channels read the saved full aggregate. These controls change the relevant mechanism and behave as expected. The two saver implementations use different history retrieval paths, and the normal-interval runs reproduced the effect. Earlier tests of parallel order and exit snapshots remain valid for their asserted configurations. A race rate for other runtimes, savers, modes or graph shapes is unmeasured. [Memory history][memory-history] · [SQLite history][sqlite-history] · [Per-task save][loop-write-save] · [Existing order tests][test-order] · [Existing exit tests][test-exit-first]

### W2 and W3. Distinguishing two forms of capacity exhaustion

| Comparison | Result and interpretation |
| --- | --- |
| Synchronous custom stream, cap 1 | Two-second diagnostic shows the worker in `SyncQueue.wait` and the driver in the futures wait. The progress markers stop before entry. The queue waiter was scheduled ahead of the node. [Blocked case][conc-stream] |
| Sync custom cap 2, sync values cap 1, async custom cap 1 | The node entered and each run returned. In custom mode empty output was expected because the node emitted no custom events. The controls separate graph completion from custom payload count. [Extra slot][conc-stream-two] · [Values mode][conc-stream-values] · [Async waiter][conc-stream-async] |
| Sync functional entrypoint, caps 1, 2, and 3 | At cap 1 the waiter prevented the root from entering. At cap 2 the root entered and waited on its child with the other worker in the stream waiter. At cap 3 both root and child entered and the call returned. [Cap 1][conc-func-one] · [Cap 2][conc-functional] · [Cap 3][conc-func-three] |
| Async functional entrypoint, caps 1 and 2 | Only the root entered at cap 1. Both entered and returned with one additional permit. The async waiter uses no executor permit. [Cap 1][conc-afunc-one] · [Cap 2][conc-afunc-two] |
| Two graph parents each waiting on a child, sync and async | Both configurations stalled when the limit admitted only one or two parents. At cap 3 the children and parents finished. A single graph parent returned at cap 1 on the inline path in each lane. These graph invocations use the default stream settings. [Sync cap 1][conc-parent-sync-one] · [Sync cap 2][conc-parent-sync] · [Sync cap 3][conc-parent-sync-control] · [Async cap 1][conc-parent-async-one] · [Async cap 2][conc-parent-async] · [Async cap 3][conc-parent-async-control] · [Sync inline][conc-parent-inline] · [Async inline][conc-parent-inline-async] |

The saved logs include a scheduled stack dump after two seconds. The async stacks show event-loop frames, so the progress markers and runner paths supply the scheduling evidence for those cases. The harness uses the documented wait on child results, and its leaf tasks log entry and return a small arithmetic result. `stream_mode=custom` in the shared log header is a parser default. The functional and graph cases invoke without passing it. Their waiter selection is explained by the entrypoint's eager flag or the normal graph invocation lane as applicable. The cases have no saver or explicit step deadline. The source accounts for the circular dependencies even if the diagnostic threshold were raised. [Archived harness control flow][conc-harness] · [Documented task futures][task-contract] · [Sync executor and waiter][sync-waiter] · [Child scheduling][runner-call] · [Async semaphore ownership][executor-gate]

### W4–W11. Direct source and targeted log checks

| Item | Checks against alternate explanations |
| --- | --- |
| **W4** Deferred scheduling | Verified that valid `Send` packets become writes to the `TASKS` topic, that its availability is checked separate from node subscriptions, and that compilation builds the reverse index only from declared node triggers. The topic can be available while the finish predicate sees no trigger intersection. The deferred channel then becomes available in time to be planned alongside the sends, before the barrier applies their writes. All task inputs are built before execution regardless of their planning order. Edge-based defer controls use subscribed routing channels and cover a different eligibility mechanism. [Send writes][send-write] · [Finish test][algo-finish] · [Plan order][algo-plan] · [Defer controls][test-defer] |
| **W5** Builder recompilation | `validate()` records compilation and is callable again. The `compile()` path has no general once-only guard, and existing tests compile the same builder with different options. The earlier harness confirmed first compilation and handler execution, then hit the collision without user creation of a colliding node. The same builder recompiled with a per-node handler or without defaults, and a fresh builder with the same default compiled as expected. The default registration and subsequent name check are before task execution or saver I/O. The sticky-default observation follows from filling the underlying `StateNodeSpec` only when its field is `None`. [Compile validation][graph-validation] · [Default assignment][compile-mutation] · [Repeated compilation in tests][test-recompile] · [Archived controls][contracts-compile] |
| **W6** Repeated cache key | Checked that the topic keeps distinct packet occurrences, that scheduled IDs incorporate the packet's index, and that the cache key uses the node namespace plus an input digest. Eligible tasks with empty writes and the same key are different tasks. The bulk lookup is legitimately keyed by cache identity, while applying the result to only one task is a loop-level mapping choice made before either backend method runs. This bulk lookup is the cache check for ordinary queued `Send`s. Current cache assertions cover the persistence of successful hits and the treatment of failed tasks. [Packet topic][task-topic] · [Send identity and cache key][algo-send] · [Cache match][loop-cache] · [Async cache match][loop-cache-async] · [Cache regressions][test-cache] |
| **W7** Streaming `maxlen` | The async pump's condition is for single-flight pulls. The mux waits for transformer processing, then uses `push` with no size or reader check. The channel constructor saves the requested capacity without passing it to the deque. The repository explicitly tests unbounded push behavior, so the contradictory v3 docstring is the defect evidenced here. Ordinary single-reader and unsubscribed-buffer tests remain compatible with that behavior. [Pump condition][stream-pump] · [Async dispatch][stream-mux-async] · [Queue API][stream-channel] · [Unbounded delivery assertions][test-stream-buffers] |
| **W8** Empty command | The archived case successfully reached an interrupt and also completed a separate run with an ID-addressed null reply. The bare-null case reached the loop's empty-command guard and the runtime raised before invoking a resumed node. An empty request should exercise error handling even when it intentionally contains no resume value. `map_command` and the assignment in the non-`None` branch account for the exact traceback. Both loop drivers call `_first`. The uncaught `UnboundLocalError` stopped the harness before the later rows executed. [Harness and reply forms][contracts-resume-harness] · [Recorded outcomes][contracts-resume] · [Recorded traceback][contracts-resume-error] · [Guard][empty-command] |
| **W9** Error-handler timeout | Compilation applies the default to the async handler and validates it as an async runnable. Both the inline-failure and executor-failure branches of `atick` call `aschedule_error_handler`, and that method and the resume classifier both reach the specialized task constructor. The constructor passes retry policy and writer metadata, leaving the timeout field unset. Ordinary PULL and `Send` tasks explicitly pass their timeout field to the retry runner. The existing timeout test sets a builder default on a normal node. The observer test times the failing node and uses an untimed handler. Their assertions are compatible with the omission. [Handler scheduling][async-handler] · [Resume handling][resume-handler] · [Handler constructor][handler-task] · [Default timeout test][test-default-timeout] · [Observer test][test-handler-observer] |
| **W10** Saver-free `sync` mode | `_defaults` chooses the explicit or inherited durability and resolves the saver independently. Both loop subclasses disable checkpoint submission when the saver is absent. The only assignments to `_put_checkpoint_fut` are a submitted checkpoint save or a submitted exit-delta anchor save. Neither path assigns it in this case. Both drivers then wait on that field for `sync` without checking whether a saver submitted anything. This is an unset field before any save backend or interpreter-specific timing can affect it. The existing durability inheritance tests supply a saver to both parent and child. [Durability selection][runtime-defaults] · [No-saver initialization][sync-no-saver] · [Save submission][loop-save] · [Exit anchor][loop-exit-deltas] · [Sync wait][sync-save-wait] · [Async wait][async-save-wait] · [Inheritance test][test-durability-inheritance] |
| **W11** Packet planning cost | Confirmed that `Pregel` installs the built-in topic and that the ordinary `PUSH` path dispatches to the per-packet method with an index. `Topic.get()` constructs a list from the whole contents on each call. Neither the node-input cache nor the cache policy avoids this read, which runs before executable task construction. The count describes cumulative references copied, with no inference of quadratic peak memory or a specific wall time. [Topic creation][task-topic-init] · [Planning][push-plan-read] · [Indexed read][push-arg-read] · [List copy][topic-read] |

### Other earlier signals and what they establish

- **Same-thread concurrent invocations are independent writers.** Earlier `exit` runs in both lanes and both savers returned two complete sibling children of the same seed. History showed both children, while a subsequent read and continuation selected one head. The harness checked parent IDs, compared separate-thread execution, and ran a serial same-thread control, which accumulated both updates. Local loop entry reads its own initial checkpoint and saver `put` records a parent without a run-spanning compare-and-swap. Default reads pick a checkpoint by ID. Both committed revisions remained visible in these controls. [Harness and checks][branch-harness] · [Memory sync][branch-sync-memory] · [SQLite sync][branch-sync-sqlite] · [Memory async][branch-async-memory] · [SQLite async][branch-async-sqlite] · [Memory head selection][memory-head] · [SQLite head selection][sqlite-head] · [Saver API][base-saver]
- **Default cache identity is input-only.** With identical state and two different run context values, both archived cache backends reused the result of the first invocation. With caching disabled, both contexts reached the callable. Changing the projected state also caused a miss. This follows the declared `CachePolicy.key_func` contract and the PULL key construction, which both operate on node input. For a result to be interchangeable, its effective inputs must be represented in that projection or in the cache's configured scope. This is separate from W6's loss of multiple eligible tasks sharing a key within one plan. [Archived cache controls][contracts-cache] · [Policy][cache-policy] · [Key construction][algo-pull]
- **Interrupt schema behavior follows the documented validation boundary.** The archived comparison accepted a value that mismatched a raw schema, rejected an incompatible typed reply with the interrupt still pending, and returned a coerced model for a compatible reply. The implementation advertises the supplied raw schema directly and constructs a `TypeAdapter` for supported Python types. The repository also checks that a rejected typed reply leaves the pending interrupt answerable. [Archived controls][contracts-resume] · [Adapter and resume handling][interrupt-implementation] · [Invalid reply regression][test-resume-schema]
- **Logical state isolation relies on read-only values.** The archived mutation comparison arranged for one parallel node to observe state after the other node either returned a write or mutated its nested list directly. The reducer-mediated update stayed invisible during the step. The in-place change was visible through the aliased list, including in the original caller value. The top-level mapping change stayed local to its node. Source matches the distinction between shallow projections and shared nested values. The barrier's isolation depends on how nodes and reducers treat those shared values. [Archived controls][contracts-mutation] · [Input projection][algo-input] · [LastValue reads][last-value]
- **Earlier prebuilt collection failure was a test setup artifact.** The early log had strict config checking, an unknown `asyncio_mode`, and no active `pytest-asyncio` plugin. The prebuilt manifest declares that setting and the test dependency. A later environment activated the plugin and passed all 446 collected cases. This is evidence of repaired test setup, with fixture and environment differences preventing a direct count comparison with the earlier collection. [Early log][prebuilt-fast] · [Pytest config][prebuilt-pytest] · [Later log][prebuilt]
- **One core async assertion test gives false confidence.** The 3.12 log warns that the coroutine in `test_config_ensured_async` was never awaited. The test initializes `RunnableCallable` with the coroutine function in the sync argument. `ainvoke` falls back to `invoke` when `afunc` is absent, and the test discards the coroutine returned by that call. The assertions inside its body can therefore be skipped while the test passes. The ordinary graph callable adapter supplies async callables in the async slot, which is a different path. The warning weakens the evidence from that specific assertion test. [Warning][core-coroutine-warning] · [Test][test-async-config] · [Fallback][runnable-async] · [Normal callable adapter][runnable-coerce]
- **SQLite store TTL retry is unresolved and outside the checkpoint findings.** The earlier suite records a timing-dependent assertion failure and a pass on retry. The test uses a one-second TTL, sleeps near its threshold, and refreshes on reads. The final assertion compares the sweep count with one. SQLite's refresh and strict timestamp comparison allow a sweep at the same whole-second timestamp as expiration to defer deletion. The archived failure lacks timestamp data to confirm that explanation. [Refresh query][ttl-refresh] · [Sweep predicate][ttl-sweep] · [Retry report][sqlite-ttl-log] · [TTL test][test-ttl]

## 9. Post-mortem and highest-leverage improvements

The design separates node completion for responsiveness, stable application of writes for state, and write publication for replay. The split works well when the state transition and persistence pipeline consume the same complete set of outcomes. W1 shows the cost of having two representations of completion with different ownership. Worker callbacks rebuild the shared persistence list after each completion, even though the barrier already has the individual task buffers. Historical replay has to preserve old checkpoint and task identities and keep a new branch isolated from writes made for another descendant. Snapshot cadence, branch guards, and synthetic IDs show where the current record model has accumulated complexity. [Barrier][algo-apply] · [Pending writes][loop-put-writes] · [Exit staging][loop-exit-deltas] · [Fork sealing][checkpoint-fork]

The scheduler also combines infrastructure operations with bounded user execution. A stream waiter consumes the same resource needed by producers. A parent and child share a cap without a dependency-aware way to relinquish or borrow execution capacity. The inline lane can keep a worker slot available for a child. The same lane is disabled when a stream waiter is needed. This explains why broad green suites and ordinary DAG fan-out coverage can coexist with stalled progress in a small composition. [Sync waiter][sync-waiter] · [Executor][executor] · [Child task submission][runner-call] · [Existing concurrency assertion][test-cap]

1. **Give a single component ownership of completion records.** Have workers publish task outcomes and one coordinator register them, or protect one task-keyed write ledger with a clear commit contract. The ledger should feed both the barrier and persistence with the same complete results. Preserve null-task write ordering, saver compatibility, and live versus replay path ordering. Keep child futures downstream of completion registration so parents still see the child outcome after it is recorded. Check that a completed barrier's live result matches a cold read across durability modes and overlapping completions. [Completion callback][runner-future] · [Task writes][loop-put-writes] · [Barrier and exit accumulator][loop-after] · [Child completion order][runner-call]
2. **Separate internal waiting from user execution budget, then account for parent-child dependencies.** Keep stream-notification waits outside worker capacity. Give functional children a scheduling path that can proceed while their parents await them, with an explicit definition of what the cap limits. Test forward progress independently from measurement of peak parallelism. Use bounded termination in regressions so CI can report a failed liveness condition. [Sync waiter][sync-waiter] · [Async waiter][async-waiter] · [Parent-child runner][runner-call] · [Permit acquisition][executor-gate]
3. **Make the step plan the source of truth for quiescence and policy.** Gate deferred release on available subscriptions and eligible queued packet work. Reuse the packet snapshot within a plan. Resolve defaults and generated handlers into a fresh compiled plan, and transfer the same handler policies when constructing executable work. [Tentative finish][algo-finish] · [Planning][algo-plan] · [Compile-time defaults][compile-mutation] · [Handler task][handler-task]
4. **Reduce persistence and API drift where behavior is duplicated.** An explicit checkpoint phase and a shared write/snapshot plan would make input, barrier commit, state update, replay and exit easier to compare between lanes. Treat the checkpoint future as optional when no save is in flight. Classify command input before its resume and write paths diverge. Apply a cached result to every equivalent eligible occurrence and retain each task identity. Align v3 documentation with actual buffering. [Checkpoint phase][loop-save] · [Sync save wait][sync-save-wait] · [State updates][bulk-update] · [Command guard][empty-command] · [Cache matcher][loop-cache] · [Stream queue][stream-channel]

## 10. Evidence appendix

### Reference map

| Area | Entry points in the pinned checkout and supporting local evidence |
| --- | --- |
| Compile and plan | [Schema registration][graph-schema] · [Compiled node and writers][graph-node] · [Edges and joins][graph-edge] · [Functional compilation][functional-entry] · [PULL/PUSH planning][algo-plan] |
| State transitions | [Fresh branch reads][algo-local-read] · [Grouped versioned writes][algo-apply] · [Task write commit][runner-commit] · [After-tick state and exit accumulator][loop-after] |
| Persistence and replay | [Saver tuple contract][base-saver] · [Ordered history][checkpoint-history] · [Checkpoint creation and submission][loop-save] · [Exit anchor and staging][loop-exit-deltas] · [Restore][checkpoint-hydration] · [Resume and replay][loop-first] |
| Concurrency | [Runner completion callback and lock][runner-future] · [Sync executor][executor] · [Async semaphore][executor-gate] · [Sync waiter][sync-waiter] · [Functional child submission][runner-call] |
| Streaming | [Output parts][stream-output] · [V3 adapter][stream-v3] · [Mux][stream-mux] · [Backlog storage][stream-channel] |
| Earlier runs | [Core 3.12 summary][core-312] · [Core 3.13 summary][core-313] · [Prebuilt summary][prebuilt] · [Fan-out oracle][fanout-oracle] · [Concurrency harness source][conc-harness] · [Branching oracle][branch-harness] |

### Read-only commands and evidence handling

Run from the workspace root unless the checkout is selected with `-C`.

```sh
cat evaluations/README.md
git -C repos/langchain-ai__langgraph rev-parse HEAD
git -C repos/langchain-ai__langgraph log -1 --format='%H%n%aI%n%cI%n%s'
git -C repos/langchain-ai__langgraph status --porcelain=v1 --untracked-files=all
git -C repos/langchain-ai__langgraph diff --exit-code HEAD --
git -C repos/langchain-ai__langgraph rev-parse --is-shallow-repository
rg --files repos/langchain-ai__langgraph/libs/langgraph
nl -ba repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py
nl -ba repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_runner.py
rg -n 'get_waiter|wait\(futs\)|resume_is_map' repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel
rg -n '2950 passed|1750 passed|446 passed' $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/{core-default,run-strict-313,prebuilt-service}.log
```

I used `nl -ba` with targeted `sed -n` ranges for implementation, test, and log checks. Read-only Python file scans compared archived module bytes, parsed method spans with `ast.parse`, and checked that report citations resolve to local files and valid line numbers. Those checks did not import or run LangGraph. The earlier harness references document the stored measurements and controls. The checkout is shallow, so the post-mortem interprets design pressures from the pinned source and its compatibility code.

[abulk-update]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:2137
[algo-apply]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_algo.py:234
[algo-finish]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_algo.py:335
[algo-functional]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_algo.py:800
[algo-input]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_algo.py:1353
[algo-interrupt]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_algo.py:157
[algo-local-read]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_algo.py:190
[algo-plan]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_algo.py:392
[algo-pull]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_algo.py:597
[algo-send]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_algo.py:938
[algo-trigger]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_algo.py:1260
[async-driver]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:3462
[async-waiter]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:3506
[barrier-channel]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/channels/named_barrier_value.py:56
[base-cache]: repos/langchain-ai__langgraph/libs/checkpoint/langgraph/cache/base/__init__.py:15
[base-channel]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/channels/base.py:19
[base-saver]: repos/langchain-ai__langgraph/libs/checkpoint/langgraph/checkpoint/base/__init__.py:262
[base-store]: repos/langchain-ai__langgraph/libs/checkpoint/langgraph/store/base/__init__.py:708
[branch-async-memory]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/branch-async-memory.log:1
[branch-async-sqlite]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/branch-async-sqlite.log:1
[branch-harness]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/work/thread_branch_probe.py:27
[branch-sync-memory]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/branch-sync-memory.log:1
[branch-sync-sqlite]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/branch-sync-sqlite.log:1
[bulk-update]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:1634
[cache-policy]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/types.py:531
[checkpoint-fork]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_checkpoint.py:140
[checkpoint-history]: repos/langchain-ai__langgraph/libs/checkpoint/langgraph/checkpoint/base/__init__.py:150
[checkpoint-hydration]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_checkpoint.py:458
[checkpoint-types]: repos/langchain-ai__langgraph/libs/checkpoint/langgraph/checkpoint/base/__init__.py:93
[command-route]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/graph/state.py:1753
[compile-mutation]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/graph/state.py:1287
[conc-afunc-one]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-7.log:1
[conc-afunc-two]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-8.log:1
[conc-func-one]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-4.log:1
[conc-func-three]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-6.log:1
[conc-functional]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-5.log:1
[conc-harness]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/work/concurrency_probe.py:34
[conc-parent-async]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-15.log:1
[conc-parent-async-control]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-16.log:1
[conc-parent-inline]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-9.log:1
[conc-parent-sync]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-11.log:1
[conc-parent-sync-control]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-12.log:1
[conc-stream]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-0.log:1
[conc-stream-async]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-3.log:1
[conc-stream-two]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-1.log:1
[conc-stream-values]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-2.log:1
[contracts-cache]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/contracts.log:8
[contracts-compile]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/contracts.log:2
[contracts-mutation]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/contracts.log:12
[contracts-resume]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/contracts.log:15
[contracts-resume-error]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/contracts.log:36
[contracts-resume-harness]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/work/contracts_probe.py:95
[core-312]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/core-default.log:140
[core-313]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/run-strict-313.log:48
[core-coroutine-warning]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/core-default.log:85
[defer-channel]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/channels/last_value.py:81
[defer-doc]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/graph/state.py:692
[delta]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/channels/delta.py:25
[durability]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/types.py:99
[empty-command]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1082
[execution-info]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/runtime.py:27
[executor]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_executor.py:48
[executor-exit]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_executor.py:101
[executor-gate]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_executor.py:139
[fanout-async-exec]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/fanout-4.log:1
[fanout-async-mode]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/fanout-3.log:1
[fanout-normal]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/fanout-0.log:1
[fanout-oracle]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/work/fanout_persistence_probe.py:49
[fanout-plain]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/fanout-6.log:1
[fanout-serial]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/fanout-8.log:1
[fanout-short]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/fanout-1.log:1
[fanout-snapshot]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/fanout-7.log:1
[fanout-sqlite]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/fanout-5.log:1
[fanout-sync-mode]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/fanout-2.log:1
[fanout-wide]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/fanout-9.log:1
[functional-entry]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/func/__init__.py:516
[functional-task]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/func/__init__.py:86
[graph-branch]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/graph/state.py:1581
[graph-callbacks]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/callbacks.py:87
[graph-channel]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/graph/state.py:1819
[graph-compile]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/graph/state.py:1346
[graph-edge]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/graph/state.py:1555
[graph-migrate]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/graph/state.py:1630
[graph-node]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/graph/state.py:1444
[graph-schema]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/graph/state.py:252
[graph-validation]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/graph/state.py:1129
[interrupt]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/types.py:913
[interrupt-implementation]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/types.py:1023
[invoke]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:3995
[last-value]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/channels/last_value.py:44
[lc-pool]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/venv/lib/python3.12/site-packages/langchain_core/runnables/config.py:660
[loop-after]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:708
[loop-cache]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1765
[loop-cache-async]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:2021
[loop-emit]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1599
[loop-enter]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1847
[loop-exit-deltas]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1422
[loop-exit-saves]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1542
[loop-first]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:931
[loop-handler]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1788
[loop-interrupt-exit]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1555
[loop-put-writes]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:471
[loop-replay-context]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1226
[loop-resume]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1030
[loop-save]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1275
[loop-save-ordered]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1748
[loop-tick]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:658
[loop-write-save]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:521
[map-command]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_io.py:56
[memory-head]: repos/langchain-ai__langgraph/libs/checkpoint/langgraph/checkpoint/memory/__init__.py:284
[memory-history]: repos/langchain-ai__langgraph/libs/checkpoint/langgraph/checkpoint/memory/__init__.py:152
[node]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_read.py:97
[node-builder]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:212
[node-defaults]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/graph/state.py:272
[package]: repos/langchain-ai__langgraph/libs/langgraph/pyproject.toml:5
[prebuilt]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/prebuilt-service.log:788
[prebuilt-fast]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/prebuilt-fast.log:6
[prebuilt-pytest]: repos/langchain-ai__langgraph/libs/prebuilt/pyproject.toml:73
[queue-wait]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/_internal/_queue.py:108
[resolve-saver]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:844
[retry]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_retry.py:593
[rubric]: ./README.md:1
[run-control]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/runtime.py:79
[run-exit]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:3118
[runnable-async]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/_internal/_runnable.py:484
[runnable-coerce]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/_internal/_runnable.py:582
[runnable-injection]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/_internal/_runnable.py:198
[runner-acall]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_runner.py:919
[runner-atick]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_runner.py:366
[runner-call]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_runner.py:715
[runner-commit]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_runner.py:583
[runner-driver]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:3081
[runner-future]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_runner.py:103
[runner-submit]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_runner.py:261
[runner-tick]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_runner.py:179
[runtime]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/runtime.py:125
[saver-path]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_checkpoint.py:56
[send-write]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_write.py:172
[snapshot-bumps]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_checkpoint.py:344
[snapshot-cadence]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_checkpoint.py:90
[sqlite-head]: repos/langchain-ai__langgraph/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py:245
[sqlite-history]: repos/langchain-ai__langgraph/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py:517
[sqlite-ttl-log]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/suite-checkpoint-sqlite.log:226
[state-snapshot]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:1228
[state-update]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:2021
[stdlib-future]: $HOME/.local/share/mise/installs/python/3.12.16/lib/python3.12/concurrent/futures/_base.py:408
[stdlib-worker]: $HOME/.local/share/mise/installs/python/3.12.16/lib/python3.12/concurrent/futures/thread.py:54
[stream-buffer-doc]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/stream/run_stream.py:357
[stream-channel]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/stream/stream_channel.py:49
[stream-channel-push]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/stream/stream_channel.py:120
[stream-mux]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/stream/_mux.py:269
[stream-mux-async]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/stream/_mux.py:351
[stream-output]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:4433
[stream-pump]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/stream/run_stream.py:463
[stream-register]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/stream/_mux.py:227
[stream-tee]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/stream/stream_channel.py:245
[stream-v3]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:3618
[sync-driver]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:3012
[sync-waiter]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:3053
[task-contract]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/func/__init__.py:144
[task-status]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_task_status.py:99
[task-topic]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/channels/topic.py:77
[test-async-config]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_runnable.py:408
[test-cache]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_delta_channel_node_cache.py:56
[test-cap]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_pregel_async.py:3553
[test-defaults]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_retry.py:2350
[test-defer]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_pregel.py:2087
[test-exit-first]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_delta_channel_exit_mode.py:128
[test-exit-parallel]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_delta_channel_exit_mode.py:424
[test-fixtures]: repos/langchain-ai__langgraph/libs/langgraph/tests/conftest.py:55
[test-futures]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_runner_futures.py:24
[test-interrupts]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_interruption.py:263
[test-order]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_delta_channel_parallel_order.py:57
[test-recompile]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_pregel_async.py:3618
[test-resume-head]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_time_travel.py:1116
[test-stream-buffers]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_pregel_stream_events_v3.py:1751
[test-ttl]: repos/langchain-ai__langgraph/libs/checkpoint-sqlite/tests/test_ttl.py:50
[test-v3]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_stream_events_v3_e2e.py:220
[timeout]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_retry.py:425
[trigger-index]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:4389
[venv-312]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/venv/pyvenv.cfg:4
[venv-313]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/venv-313/pyvenv.cfg:4
[write-adapter]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_write.py:106
[async-handler]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:2044
[async-retry]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_retry.py:706
[async-save-wait]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:3573
[checkpoint-enabled]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1324
[executable-task]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/types.py:705
[handler-task]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_algo.py:1201
[infer-writer]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:1613
[memory-write-keys]: repos/langchain-ai__langgraph/libs/checkpoint/langgraph/checkpoint/memory/__init__.py:497
[node-policies]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/graph/state.py:1535
[prebuilt-state-test]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/prebuilt-service.log:54
[replay-state]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/_internal/_replay.py:52
[resume-handler]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:856
[runtime-defaults]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:2664
[saver-version]: repos/langchain-ai__langgraph/libs/checkpoint/langgraph/checkpoint/base/__init__.py:721
[state-history]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:1561
[sync-no-saver]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1735
[sync-save-wait]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:3103
[test-default-timeout]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_retry.py:2615
[test-delta-write-failure]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_delta_channel_write_failures.py:91
[test-handler-observer]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_retry.py:1868
[ttl-refresh]: repos/langchain-ai__langgraph/libs/checkpoint-sqlite/langgraph/store/sqlite/base.py:317
[ttl-sweep]: repos/langchain-ai__langgraph/libs/checkpoint-sqlite/langgraph/store/sqlite/base.py:1133
[conc-parent-async-one]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-14.log:1
[conc-parent-inline-async]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-13.log:1
[conc-parent-sync-one]: $HOME/.t3/langgraph-eval-bbd5275.ztTirZcX/conc-10.log:1
[push-arg-read]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_algo.py:961
[push-plan-read]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_algo.py:437
[saver-delta-conformance]: repos/langchain-ai__langgraph/libs/checkpoint-conformance/langgraph/checkpoint/conformance/spec/test_delta_channel_history.py:276
[saver-write-conformance]: repos/langchain-ai__langgraph/libs/checkpoint-conformance/langgraph/checkpoint/conformance/spec/test_put_writes.py:148
[task-topic-init]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:809
[test-live-state]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_interrupt_state.py:100
[test-saver-fallback]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_delta_channel_migration.py:289
[topic-read]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/channels/topic.py:87
[trace-policy]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/_internal/_runnable.py:658
[aggregate-copy]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/channels/binop.py:110
[ephemeral-channel]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/channels/ephemeral_value.py:48
[loop-input-checkpoint]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1151
[managed-steps]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/managed/is_last_step.py:18
[untracked-channel]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/channels/untracked_value.py:48
[mixed-branch]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/graph/_branch.py:192
[branch-writes]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/graph/state.py:1584
[state-overlay]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:1315
[timed-scope]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_retry.py:131
[saver-history-walk]: repos/langchain-ai__langgraph/libs/checkpoint/langgraph/checkpoint/base/__init__.py:607
[sync-durability-warning]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/main.py:2927
[test-durability-inheritance]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_pregel.py:3284
[test-resume-schema]: repos/langchain-ai__langgraph/libs/langgraph/tests/test_interruption.py:187
[exit-delta-ids]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_loop.py:1493
