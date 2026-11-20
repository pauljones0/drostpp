# PentAGI backend architecture and reliability review

## 1. Snapshot, scope, and elapsed-time evidence

| Item | Evidence |
|---|---|
| Checkout | `repos/vxcontrol__pentagi`, branch `main`, shallow local clone |
| Requested commit | `cffed9485aa1cca70762cd08a57ac62a80406258` |
| Start | 2026-11-19 05:50:54 UTC. `git rev-parse HEAD` returned the full pin and `git status --porcelain=v1 --untracked-files=all` was empty. |
| Finish | 2026-11-19 06:20:54 UTC. HEAD returned the same full pin. Porcelain, the ignored-file check, and the diff against HEAD were empty. |
| Artifact | `evaluations/vxcontrol__pentagi.md` |

I read the complete rubric and the relevant test instructions. The rubric combines strengths and weaknesses under item 4. Sections 4 and 5 separate those topics, preserving the rubric order and the ten headings used in the evaluation series. The review covers backend lifecycle, ownership, durability, interruption, provider and executor interfaces, and observations from synthetic local fixtures. The tool and provider discussion concerns their software contracts. Operational workflows, product UI, and hosted behavior are outside this review. All test execution took place in a separate namespace with loopback only, an empty home, a cleared environment, a disk-backed scratch tree and offline package settings. The temporary artifacts were cleaned after their reproduction commands and results were recorded here. The original checkout was used for reads. A byte and symlink-target comparison against its Git archive matched all 1,728 regular files and symlinks. [Evaluation protocol][rubric] · [Backend test tiers][test-guide] · [CI backend setup][ci-generate].

| UTC | Fresh work in this run |
|---|---|
| 05:50:54–05:54 | Verified the checkout and rubric, set up isolation, traced service entry points and flow ownership, measured dependency availability, and ran preliminary package checks. |
| 05:54–05:58 | Audited recovery, cancellation and status writes, ran race-enabled suites for buildable packages, and built exact-declaration controls for replies, status and event fan-out. |
| 05:58–06:04 | Recovered an embedded PostgreSQL runtime from the local content store, ran migrations and exact generated SQL on synthetic data, tested a local wire adapter, and reproduced lifecycle handoffs under controlled scheduling. |
| 06:04–06:10 | Audited request and worker lifetime boundaries, exercised admission and telemetry methods, compared SQLC protocol behavior, and drafted source-backed architecture and findings. |
| 06:10–06:15 | Isolated the wire rollback error using driver, psql and direct-SQL controls, assembled the reproduction appendix, and reran its commands from a fresh archive. |
| 06:15–06:20:54 | Exercised expired-context failure recording and blocked admission publication, repeated the source controls from the report, checked the terminal-latch assertion with a sensitivity control, verified the original checkout byte-for-byte and audited the evidence index. |

Elapsed time measures this fresh active pass from start verification through final source, experiment and report checks. Test commands could run concurrently with investigation. Their durations are evidence for the experiments and are counted only once in the elapsed interval. Earlier runs receive zero credit. The verified interval was **30 minutes 00 seconds** (1800 seconds).

## 2. Core architecture and end-to-end control/data flow

**Composition.** The Go server installs optional observation clients, opens a bounded shared SQL pool, applies migrations, constructs the runtime and provider adapters, and passes those and the subscriptions controller to `FlowController`. It restores workers before opening the HTTP listener. REST and GraphQL query and authorize at the service boundary, then call the controller using database IDs. The flow controller holds the process-wide registry. Individual flow workers receive input and own per-flow task and assistant registries. SQLC queries persist the lifecycle state. GORM v1 services and SQLC share the SQL pool, and the request-context-aware controller is built against `database.Querier`. [Server initialization][main-db] · [Migrations and worker composition][main-wire] · [GraphQL admission][graphql-entry] · [GraphQL ownership][graphql-owner] · [REST admission][rest-entry] · [REST ownership][rest-owner] · [GORM sharing][gorm] · [Controller definition][registry].

**Admission and scheduling.** Flow creation writes an initial `created` row with identity and placeholder metadata, inserts a registry slot, publishes creation and launches asynchronous preparation. The successful return identifies the row. While the slot is preparing, lookup excludes it. Preparation resolves local configuration, persists resolved metadata, builds the worker and runtime dependencies, and commits the slot unless teardown has started. A flow receives work with an unbuffered channel. The worker handles one ordinary input at a time and hands it to the first waiting task in ID order, or creates a task when none is waiting. The follow-up call distinguishes a receiver accepting the input from a worker having replied, and uses different context lifetimes for request and worker. This is per-flow serialization in one process, with independent flows able to make progress concurrently. The handoff exists only in the process-local mailbox. [Reservation][flow-reserve] · [Create and prepare][create-flow] · [Slot visibility][entry-available] · [Initial worker launch][flow-launch] · [Resource readiness][runtime-prepare] · [Input handoff][flow-put] · [Task sort][task-order] · [Worker intake][flow-process].

**Tasks and subtasks.** A task persists its input and records an input event after title resolution. A subtask controller manages the plan, selects the first persisted `created` or `waiting` item by ID, and caches the associated worker. Task execution advances serially, returns to the parent when the task becomes waiting, and records terminal status and a result when the task is done. The flow status records whether a flow is open and currently waiting or running. Successful work on one task leaves the flow open for a later input. The subtask context carries its primary conversation ID. The durable conversation row has the owning IDs and serialized history, updated as work advances. Reporting is a separate asynchronous operation with its own join group and allowance. It can cancel the preceding task and attempts a bounded drain before proceeding. It therefore represents a separate execution schedule that can overlap ordinary work at its drain boundary. [Task creation][task-create] · [Queue SQL][planned-query] · [Worker cache][subtask-pop] · [Task loop][task-run] · [Status propagation][task-status] · [Subtask chain][subtask-load] · [Durable chain update][chain-sql] · [Report admission and drain][report-admission] · [Report lifetime][report-run].

**Assistants and owners.** An assistant is linked to a flow, with its own mailbox, worker context, provider reference and persisted conversation ID. It can share the flow's resources, and its worker can outlive the submitting HTTP request. An assistant can create or request loading a parent flow. The parent protects the assistant registry separately and refuses attachments after cancellation. The ordinary flow and assistant lifetimes are controlled separately, including their in-memory waiting and cancellation state. [Assistant creation][create-assistant] · [Assistant parent lookup][assistant-parent] · [Assistant attachment][add-assistant] · [Assistant worker registration][assistant-build] · [Assistant loop][assistant-worker].

**Recovery.** Startup reads non-deleted flow rows. Only `running` and `waiting` are candidates for restored flow workers. The loader reconstructs the runtime, reattaches the stored metadata and restores child workers. Failure of the initial flow query prevents startup. Individual restore failures are logged and skipped, including a missing primary resource row. It skips a created task and attempts startup continuation of loaded incomplete, non-waiting tasks. A previously running subtask has its status reset to created, then the loader attempts to associate its latest primary conversation. Waiting work expects new input. The chain consistency pass can reconcile structural conversation gaps, such as an outstanding response. A previously running assistant is instead returned to waiting with a restart note. An unloadable assistant is logged and skipped so later children and its parent can remain available. These rules recover from persisted snapshots and status inference. The restoration scope is persisted fields and reconstructable workers. In-flight mailboxes and side effect outcomes require independent evidence. [Startup scans][load-flows] · [Flow eligibility][flow-load] · [Worker reconstruction and child isolation][flow-load-children] · [Task reconstruction][task-load] · [Subtask reconstruction][subtask-load] · [Startup continuation][flow-restart] · [Assistant restart][assistant-restart] · [Conversation repair][chain-repair].

**Provider, executor and observation boundaries.** `Provider` exposes typed configuration and identity alongside context-bearing call methods. Provider resolution is owner-scoped for stored overrides, and a static registry supplies built-in constructor and configuration contracts. The flow-facing interface turns provider responses into typed task and subtask outcomes. Conversation checkpoints pair the recorded response with its call identity. The orchestration loop stops at defined boundaries and has an upper iteration limit. The executor boundary supplies the set of callable definitions and typed per-context configuration, accepts JSON arguments and returns a result or an error. Flow, task, subtask and conversation IDs scope durable records. The orchestration has separate paths for status writes, message and tool-call observations, subscriptions and optional tracing. PostgreSQL remains the read-side record for committed rows. GraphQL subscriptions are live projections produced in the same process after the relevant writes. [Provider interface][provider-interface] · [Flow-facing provider][flow-provider-contract] · [Iteration guard][agent-iteration-guard] · [Checkpoint commit][agent-checkpoint] · [Provider registry][provider-registry] · [Provider resolution][provider-resolve] · [Executor interfaces][executor-interface] · [Tool-call log][tclog] · [Flow event publication][publisher] · [Subscription channels][channels].

## 3. Why the design works and its governing invariants

| Intended invariant | Mechanism and boundary |
|---|---|
| One usable registry entry per flow in one server | The short controller mutex protects map identity and slot fields. A separate per-entry channel lock serializes lifecycle operations. Claim revalidates identity and availability after acquiring it. A pending or closing slot is unavailable. The lock is process-local. The documented shared-infrastructure deployment uses a separate tenant namespace for each installation. [Entry and lock][flow-entry] · [Claim validation][claim] · [Reservation and commit][entry-commit] · [Shared-infrastructure scope][tenant-docs]. |
| Distinct lifetimes for request, preparation, idle worker and run | The admitted flow outlives the request, with a deadline for preparation and a worker context independent of the request. Stop acts on present work, while finish cancels the worker itself and starts cleanup. The boundaries depend on forwarding the appropriate context at each call and on workers respecting it. [Preparation][prepare] · [Worker context and launch][flow-launch] · [Stop and finish][flow-finish] · [Task run context][flow-run]. |
| One destination for a terminal input acknowledgement | A one-slot channel and an atomic waiting-to-delivered or waiting-to-abandoned transition let either the caller receive the error or the worker report it. The input result is an acknowledgement of a channel handoff or subsequent processing result. Durable storage occurs on a separate path. [Reply primitive][reply] · [Flow acknowledgement][flow-put] · [Failure delivery][flow-process] · [Assistant acknowledgement][assistant-put]. |
| Terminal state and incomplete work have different treatment | The worker latch rejects later nonterminal flow transitions after finalization is recorded in memory. Task and subtask memory mirrors are rebuilt from database enums. SQL distinguishes same-row single-statement updates from separate parent, child and event writes. Persistent state still requires its own transition guard for ordering across writers. [Terminal latch][flow-status] · [Task mirror][task-status] · [Status SQL][flow-status-sql] · [Atomic result SQL][task-result-sql]. |
| Active work is stoppable while cleanup remains possible after caller cancellation | Controller teardown withdraws the registry slot from service, detaches cleanup, and gives the database leftovers pass its own timeout after worker cleanup. Subtask and task paths can write an interrupted status on a fresh context. The API can finish an extant row even when no worker loaded. [Loaded flow teardown][finish-controller] · [Unloaded flow teardown][finish-unloaded] · [Task interruption][task-interrupt] · [Subtask interruption][subtask-interrupt]. |
| Live events follow relevant state publication paths | Typed publishers convert stored data and scope delivery by user or flow, after caller-side permission checks. The event channel buffers individual listeners and treats overrun as best-effort delivery. Durable row queries can be reconciled independently. [Publisher conversion and routing][publisher] · [Subscription ownership check][graphql-sub] · [Fan-out][channels]. |

The registry lock establishes local ownership. The per-flow mailbox orders normal input consumption. A successful autocommit statement establishes a durable PostgreSQL row update. Return from a publisher establishes that fan-out was attempted. An HTTP deadline can expire between those checkpoints. [Registry claim][claim] · [Flow input][flow-put] · [SQL status update][flow-status-sql] · [Subscription implementation][channels].

## 4. Strengths

- **The registry isolates slow lifecycle work to one flow.** The controller releases its global mutex before waiting for the per-flow operation lock and verifies slot identity after waking. It has explicit closing states for loaded and unloaded flows. The checked-in tests name the same-flow serialization and cross-flow progress properties, and the isolated controls exercise claim and independent cleanup contexts. [Claim and settle][claim] · [Finish paths][finish-controller] · [Lifecycle test][unrelated-flow-test].
- **Cancellation and slow acknowledgment are intentionally distinguished.** The reply state has only two winning transitions with an atomic compare-and-swap, and a one-slot buffer keeps a successful deliver from blocking on the caller. The REST adaptation treats an accepted input that outlasted its request as accepted, while an unaccepted input gets a distinct response. The repository reply test passed 100 uncached repetitions under the race detector with the original fixture helper. [Input reply][reply] · [Shipped reply test][reply-test] · [REST outcome mapping][rest-put].
- **Recovery allows partial availability and gives operators evidence.** One invalid assistant can remain unloaded without removing its parent flow from service. The assistant loader records interrupted work and retries writing its interruption note when the first write fails. An unloaded flow can still be finished from its durable row. These behaviors make provider or runtime failures visible while preserving the ability to close affected work. [Child recovery][flow-load-children] · [Restart note][assistant-restart] · [Unloaded cleanup][finish-unloaded].
- **Resource ownership is explicit at important boundaries.** Executor teardown only closes its own vector-store connection, leaving a shared pool available to other workers. The API bootstrap also shares the SQL pool between GORM and SQLC. Tenant schema setup uses a dedicated session for advisory locks, validates the resolved schema, and refuses to serve on a half-migrated schema. The advisory lock covers schema work. [Executor release][executor-release] · [GORM pool][gorm] · [Tenant schema verification][tenant-verify] · [Migration lock][migration-lock] · [Startup failure policy][main-wire].
- **The data model makes provenance and partial progress queryable.** Flow, task and subtask enums and parent keys support readable state reconstruction. Conversation snapshots, status and observations are separately queryable. Some writes pair terminal status and result in one PostgreSQL statement. The offline PostgreSQL fixture exercised those statements as well as owner and soft-delete query predicates. [Schema tables][schema] · [Assistant schema][assistant-schema] · [Generated query][flow-status-sql] · [Task combined result query][task-result-sql] · [Conversation update][chain-sql].
- **Maintenance tests encode concrete failures.** The controller suite has targeted cases for deferred preparation, waiting callers, stale slot identity, interruption and leftover state. The project documents that default tests can skip integration prerequisites and specifies the separate PostgreSQL tier. Compiler and execution evidence for the actual checkout and for isolated slices is recorded separately in §7. [Preparation tests][prep-tests] · [Per-flow lifecycle tests][unrelated-flow-test] · [Teardown budget tests][budget-test] · [Integration tier guidance][test-guide].

## 5. Weaknesses and evidence status

**1. The terminal latch protects an ordered call sequence while the database permits stale writes.** A nonterminal `SetStatus` can pass `takeStatus`, pause before the database call, and write after a different call has set the terminal latch and committed `finished`. The exact-method control used a context-aware fake to order those writes, observed `[finished running]` in the publisher and found the stored row running. A separate exact PostgreSQL query control verified the same permitted row transition and inspected the migrated flow table for transition triggers. The stubs demonstrate the interleaving at the method boundary. Its frequency in a live controller is unmeasured. The ordinary worker and controller drain narrow that exposure, while status writers from report and recovery paths and separate processes have different ownership. The same test suite showed that failure of the terminal SQL write leaves the latch set and later normal updates return nil without changing the database. A successful status write followed by a failed container read returns an error without publishing. The shipped sequential test covers a genuine positive case, which also passed in isolation. [Latch and update][flow-status] · [Generated status SQL][flow-status-sql] · [Sequential regression test][finished-test] · [Report worker][report-run].

**2. Flow reservation and readiness have a crash window.** Creation returns a row ID while the supplied input and resources are still in the preparation closure from the controller's point of view. The reservation SQL has stored identity and placeholder metadata. The starting input is written later when task title work has returned, and a flow still in `created` is skipped during ordinary startup. A shutdown in between can leave a visible flow with no redispatched input. A task interrupted while still `created` is also skipped when rebuilding task workers. The disk-reopen control proved all five row statuses survive and are returned by the initial query. The application-specific decision to skip certain statuses follows from its loader, and process-kill timing at the server level remains unmeasured. [Flow reservation][flow-reserve] · [Admission handoff][create-flow] · [GetFlows query][get-flows] · [Flow eligibility][flow-load] · [First durable task input][task-create] · [Task loader][task-load].

**3. Cancellation budgets have gaps at ownership transitions.** The controller bounds preparation, and the builder creates the worker's independent background context before the resource preparation call. Cancellation of the preparation context therefore no longer governs that call. The closing flag still denies pre-commit visibility. If finish wins before the preparation goroutine installs `entry.abort`, the controller executes unloaded cleanup and the later builder can still receive a live context. The isolated scheduler control reproduced that ordering and confirmed that commit was refused. In the loaded finish path, controller lock acquisition waits before the finish budget starts. The production `flowWorker.finish` then joins its worker with a blocking `Wait`. The bounded leftover phase executes once the earlier stage returns. The deadline bounds cooperative cleanup after an independently blocking queue and join. If preparation instead returns a deadline error, the controller hands the same expired context to its failure logger and status writer. Exact-method controls with a context-sensitive store recorded both attempts and zero commits on the expired context. The live-context comparison recorded the failed row and its update. Source also shows that after the worker goroutine starts, a synchronous error returning from the initial `PutInput` can return a nil worker to the controller without calling cancel in that branch. [Preparation context][prepare] · [Builder context and tail][flow-launch] · [Finish controller][finish-controller] · [Worker join][flow-join] · [Closing budget test][budget-test] · [Preparation failure writes][fail-flow].

**4. A stop result is weaker than a proof that all work has quiesced.** The flow stop path cancels its current slot, cancels the current report handle, requests runtime cleanup and waits with a timer. It logs runtime cleanup errors. Ordinary execution assigns the run cancel handle under `taskMX` and registers its wait group after releasing the lock. The assistant run increments its wait group before installing the current cancel function, while assistant `Stop` reads the function outside the assigning mutex. Those sequences leave timing windows around startup. The completion helper observes a new edge after each task and returns nil when the worker context ends. The isolated helper control observed a late watcher timing out and a cancelled worker context yielding nil. The assistant boundary forwards that contract. Its caller reads task status before waiting, treats nil as completion and performs no second durable status read in that return branch. At process level, the signal branch drains telemetry, and flow and assistant worker contexts derive from background contexts. The entry point exits without joining those workers. These facts support a concern about shutdown observability. Complete worker and runtime teardown behavior remains source-level. [Flow stop][flow-stop] · [Flow registration][flow-run] · [Assistant run][assistant-run] · [Assistant stop][assistant-stop] · [Task notification][task-completion] · [Assistant completion bridge][assistant-wait] · [Completion status precheck][completion-handler] · [Process shutdown][main-shutdown].

**5. Partial progress can become the new durable plan.** Refinement deletes previously created subtasks, invalidates cached workers and then inserts replacements one at a time. SQLC exposes transaction support, while the controller uses bare query calls and explicitly records the missing transaction as a TODO. The PostgreSQL control used the generated statements with an injected `23502` on a later insert. It kept the existing waiting item and one new item after deleting the preceding plan. The same statements inside one transaction preserved the pre-fault plan on rollback. In task completion, result, status and message-log writes likewise have separate failure boundaries. `UpdateTaskFinishedResult` exists as a combined primitive and ordinary task completion follows the split path. [Plan replacement][plan-patch] · [SQLC delete][subtask-delete] · [Transactional primitive][sqlc-tx] · [Task result writes][task-write] · [Generated combined statement][task-result-sql].

**6. A slow subscriber can delay control work and miss events.** Fan-out holds the channel read lock and iterates through subscribers, waiting up to five seconds per full queue. An exact-channel control with two full subscribers delayed a healthy subscriber by about 10.006 seconds, then delivered immediately in the drained-buffer control. A shorter publisher deadline ended the loop before it reached the healthy subscriber. Slot creation publishes before the background preparation goroutine is launched. The exact admission method held both its response and preparation behind a synthetic publisher after the reservation callback returned. Flow status, task transitions and some log writes also publish synchronously. The channel exposes no receipt or recorded drop to callers. In a stream of assistant logs, partial content can be published before periodic persistence, making the gap between an observed chunk and a durable row explicit. [Channel constants][channel-defaults] · [Channel timeout and locking][channels] · [Flow creation call sites][create-flow] · [Flow status publication][flow-status] · [Task publication][task-status] · [Assistant stream publish][stream-chunks] · [Assistant periodic persistence][stream-save].

**7. Input acknowledgement has a narrow boundary, with different API behavior.** `PutInput` switches provider and attempts resource work before waiting for the worker to accept the channel send. The isolated method with stub preparation proved both callbacks can occur before a caller receives `ErrInputNotAccepted`. In a separate control, a receiver accepted input and the caller observed `ErrInputAccepted` when its context ended. That distinction describes the mailbox. REST maps the sentinel to success in the accepted case. The GraphQL resolver propagates any returned error, and the assistant has its own acknowledgment code without these sentinels. The first flow lifetime check also returns plain wrapped cancellation. API consumers therefore need a consistent visible contract for handoff and uncertain completion, with preparation effects reported independently. [Flow input implementation][flow-put] · [REST mapping][rest-put] · [GraphQL mapping][graphql-put] · [Assistant mapping][assistant-put].

**8. Provider and message state have independent visibility.** A successful provider switch changes the in-memory provider and template under lock. Persistence happens in the flow caller afterward, with values assembled from that request's provider. This keeps each row update internally consistent. A failed SQL update leaves the in-memory provider selected and the saved provider unchanged. Two concurrent inputs can also persist their complete provider tuples in a different order from memory swaps. The public input call reaches the switch before serialized mailbox consumption. Conversation persistence replaces a JSON body by row ID and updates duration additively. The PostgreSQL control observed body B after writing A then B and the sum of both durations. That confirms replacement semantics in the storage layer and leaves whole-application concurrency unmeasured. [Provider swap][provider-swap] · [Flow provider persistence][provider-write] · [Input path][flow-put] · [Persisted chain query][chain-sql] · [Conversation transform][process-chain].

## 6. Core-code quality

| Dimension | Evaluation |
|---|---|
| Decomposition | Service permission checks, controller lifetime operations, provider adaptation, typed executor boundary and SQL projection are recognizable seams. Multiple responsibilities accumulate in the large implementation files. At this pin `flow.go` is 1,595 lines, `performer.go` 1,225 and `tools.go` 1,851. Flow create and restore reassemble parallel lists of logging and runtime dependencies. `FlowContext` embeds multiple capabilities, and it is copied into narrower task and subtask contexts. These patterns make a change to one stage easy to miss in a sibling. [Controller context][flow-context] · [Build wiring][flow-build-wire] · [Restore wiring][flow-restore-wire] · [Executor surface][executor-interface]. |
| State | Typed status values and narrow SQL updates are readable. Ownership, authoritative row state and cached waiting/completed booleans are split across workers. Parent state updates are callbacks after child writes. Changes can partially commit before a later read or publish fails. State transition meaning is spread across loaders, task and subtask workers, and flow teardown. The published word `finished` can mean explicit cleanup of unfinished work as well as an execution outcome. [Task status][task-status] · [Subtask status][subtask-status] · [Leftover state writes][finish-work] · [Initial schema][schema]. |
| Scheduling and concurrency | Per-entry locking and short map operations give better isolation than a global lifecycle lock. Per-worker timing and status protection depend on several mutexes, wait groups, per-run cancellation functions and a separate report group. The assistant message stream uses a bounded channel with a `TryLock` on idle retirement to avoid a lock/channel cycle. Foreground stream submission can still block on a full channel and sends no context signal at the actual channel write. [Entry and claim][claim] · [Worker structure][flow-fields] · [Assistant stream enqueue][stream-enqueue] · [Stream idle drain][stream-save]. |
| Errors and retry | Wrapped errors allow callers to distinguish cancellation, missing state and terminal conditions. Setup retry classifies deterministic errors and gives its backoff a context gate. The provider failover wrapper has its own cancellation check and the outer agent call owns another retry boundary. Reports add an allowance for the whole report. Several failure paths swallow follow-up errors after an earlier step has persisted. Typed disposition at each interface would make the difference between errors, terminal outcomes and lost observations easier to audit. [Setup retry][setup-retry] · [Provider fallback context predicate][fallback] · [Outer call boundary][provider-call-errors] · [Report retries][report-run] · [Status catch-up][flow-restart]. |
| Types and extension | Provider definitions and tool/executor configuration expose interfaces and types at their edges, which enable simple fakes. Implementations share a concrete model SDK, string identifiers and JSON schema at the provider/executor boundary. The registry is a compile-time constructor list. The custom executor checks definition/handler pairing and barrier registration, with provider and runtime behavior wired through controllers. The count check and name check are useful invariants. The handler map remains mutable and validation and runtime dispatch share string names. [Provider contract][provider-interface] · [Provider registry][provider-registry] · [Custom executor contract][custom-executor] · [Tool invocation boundary][tool-execute]. |
| Observability | Correlation IDs, database rows, structured logs and optional tracing support different levels of investigation. No-op initialization keeps absent sinks off the critical path. The telemetry drain runs sinks independently under one context because a blocked exporter can outlive its own deadline. Subscription and stream observations have distinct flush timing, and their error or drop accounting is thinner than the state path. [Startup telemetry][main-observe] · [Observer defaults][observer-init] · [Independent sink drain][observer-drain] · [Channel delivery][channels] · [Stream final flush][stream-save]. |
| Tests and maintainability | The controller package declares 68 top-level test functions in the pinned tree. Tests exercise meaningful error and recovery contracts with fakes and explicit waits. The maintainer guide is unusually precise about reaching public entry points, context-sensitive doubles and avoiding assertions that cannot fail. Tests still share a fixture file with broad dependencies. Attempting to run a small reply test by file uncovered one hidden helper dependency. The default backend build also requires generation for installer embeds. The documentation and CI explain these layers. [Testing conventions][test-design] · [Representative lifecycle tests][prep-tests] · [Shared reply fixture][reply-fixture] · [Generate step][ci-generate]. |

## 7. Executed tests/experiments and their limitations

The stock package and file-selection cases used Go 1.26.10, a locally cached patch release in the module's required 1.26 line. The source and generator came from a `git archive HEAD` copy. The tests were run with `-count=1` or explicit uncached repetition. Test counts below distinguish top-level tests from Go JSON test events, which include subtests. An exit-zero fault control means the harness observed the stated behavior and its comparison. [Module directive][go-module] · [Test guidance][test-guide].

| Check | Observed result |
|---|---|
| Initial core package run with the shared cache mounted read-only | Exit 1. Three of 12 package outcomes passed, covering 49 test and subtest pass events. Nine failed in build setup. |
| Embedded installer generation in archive copy | `go generate ./cmd/installer/files/` succeeded. Output listed generated deployment assets and the generated installer test package later passed under race instrumentation. |
| Backend-wide discovery and compile probe, writable private cache, `go test -json -count=1 -p 4 -run '^$' ./...` | Exit 1. 119 terminal package events comprising 76 build or setup failures, 10 successful test-binary starts with no test selected, and 33 packages with no test files. Production controller, provider, tool and subscriptions packages were in the blocked set. |
| Race-enabled run over every buildable package with tests | Exit 0. 10 package passes, 83 top-level tests, 328 passing test and subtest events, zero skips. Included migration filenames, data limits, resource filesystem behavior, timezone resolution, password policy, version metadata, installer embeds and process-local UI-window logic as dependency controls, and the observation HTTP API internals and constructor. The HTTP retrier tests used isolated `httptest` servers. |
| Explicit `go vet` on buildable packages and experiment packages | Exit 0, zero diagnostics, 16 packages. The scope matched the ten buildable stock packages plus six isolated fixture packages. |
| File-selection persistence units | Exit 0. Statement-timeout URI behavior and migration-renumbering plan passed, with 11 pass events. The database-enforcement test skipped because `TEST_DATABASE_URL` was unset. |
| Shipped input acknowledgement test | Exit 0 after extracting its original helper. 100 runs under `-race`, 400 pass events. Its race subtest runs 1,000 acknowledgement races per run. |
| Exact-declaration flow status, completion signal, slot acquisition and subscription channel controls | Exit 0. Nine tests under `-race`. Terminal overtaking, split commit and publish, failed write latch, current/late completion edges, cancellation, subscriber scope and slow-subscriber head-of-line delay were observed. The event test used the original 50 slots and five-second send timeout. |
| Exact-declaration controller lifecycle tests and flow acknowledgement boundary | Exit 0. Four lifecycle cases repeated 20 times and three acknowledgement cases repeated 20 times under `-race`. The full prerequisite callbacks were replaced by local stubs, with the control schedules defined in §10. |
| Exact-declaration admission publication | Exit 0. Twenty race-enabled repetitions held a synthetic publisher after reservation, confirmed preparation and response were both pending, then released publication and observed both advance. |
| Exact-declaration startup failure recording | Exit 0. One expired-versus-live context case repeated 20 times under `-race`. The fixture refused writes after the first context ended. The fresh-context comparison persisted and published failed status. |
| Exact-declaration telemetry drain | Exit 0. Two cases repeated 20 times under `-race`. A healthy sink got to shutdown despite a blocked peer, the caller got a deadline error, and independent sink errors survived a joined result. Exporter transports are outside this control. |
| Repository `postgres` build-tag tier, `-p 1 -tags postgres -run '^$'` | Exit 1. Two package targets compiled with no selected tests. Five hit setup errors including missing Goose, GORM and the provider fork. The shipped tagged integration tier therefore remains unexecuted. |
| Local embedded PostgreSQL 17.5, PGlite 0.4.1 | Exit 0 for direct SQL and reopen. All 37 UP files applied in order with `pg_trgm` and `vector` installed. Passed owner scope, soft deletion, status and result updates, enum rejection, partial and rolled-back plan replacement, whole-JSON replacement, and reopen of five synthetic statuses. Applied migration SQL directly outside Goose. |
| Generated SQLC methods over a local PostgreSQL wire adapter | Pinned lib/pq passed three clean rollback and state cycles under `-race`. It failed after the injected check constraint. Pinned pgx in simple protocol mode passed all three fault-injected cycles over the same embedded adapter, including rollback. Generated query files and selected exact model declarations were compiled unchanged. |
| Shipped statement-timeout enforcement case against that adapter | Failed in 30.03 seconds. Independent `psql` and direct embedded-engine controls attributed that result to missing startup option propagation and timer enforcement in this fixture. §8 records the diagnostic controls. |

There was no live service beyond short-lived, credential-free fixtures in the isolated namespace. The Go compile boundary prevented a stock application build, product restart, controller package race run or end-to-end provider/container run. The method slices test the selected code with controlled interfaces. The embedded engine test exercises real PostgreSQL statements, enum and transaction behavior in one local database. Its wire adapter and storage engine properties differ from a native deployment with database pools and multiple sessions. Native statement cancellation, deployment startup, persistence across an abrupt app death and runtime resource termination remain unverified. [Live test fixture][pg-live] · [Statement-timeout test][statement-live] · [Checked-in Docker fixture][docker-fixture].

## 8. Measurement audit

| Negative or surprising observation | Discriminating check and disposition |
|---|---|
| Initial build failures said `read-only file system`. | The first run mounted the shared Go cache read-only. A Btrfs reflink copy exposed a fully writable private cache with the same package objects. The resulting failures were `module lookup disabled by GOPROXY=off`, with the same compiler and source tree. The available packages compiled in both environments. Neither disk space nor file permissions blocked the corrected run. |
| The local cache left the agent core unbuildable offline. | Enumerated the 219 requirements from `go mod edit -json` and searched for exact extracted module directories or matching ZIP and ZIP hash pairs. The cache lacked 92 exact payloads, including 38 of 77 direct requirements. The provider fork, Moby client, GORM and pinned Goose were missing. The upstream `github.com/tmc/langchaingo` copy has a different module identity from the required fork. Other available cached versions differ from the pins. Repeated representative builds with Go 1.27.1 in the same offline environment and got the same missing imports. Generation had already succeeded. This is an environment coverage gap. [Dependency pins][go-module] · [CI assets step][ci-generate]. |
| A hand-selected input reply test reported `undefined: controllerReceive`. | The shared fixture file supplies it at lines 26–39. Including the exact function with its two imports recovered the unchanged test. The broader fixture imports bring back the missing dependencies. The first lifecycle slice likewise omitted the `var` wrapper around `errFlowAbandoned`. Adding the wrapper in the fixture fixed the syntax, and the original tested method bodies were unchanged. [Reply fixture][reply-fixture] · [Controller sentinel][abandoned]. |
| A tagged PostgreSQL probe reached a partial compile, and the default file-selection tier reported a skip. | The tagged fixture requires `PENTAGI_TEST_DSN` and fails when it is absent. Its pinned Goose dependency blocked test execution before any connection. The file-selected timeout test independently skips if `TEST_DATABASE_URL` is unset. `pg_config` and `psql` were present, while the native server binaries and pgvector install were absent from the checked local package paths. The existing pnpm store had an embedded alternative. Recovered 338 SHA-512-verified PGlite package files. The cache decoder exposed per-file hex `digest` fields after an initial decoder assumption of SRI-form `integrity` failed. [Tag and DSN][pg-live] · [Default-tier skip][statement-live]. |
| First embedded SQL control failed during seeding and then during a query. | The full migration UP set completed in both attempts. Two synthetic users had the same hash surrogate, triggering the real `users_hash_unique` constraint. Distinct values fixed the fixture. Then `DeleteSubtasks` failed with `42703` because the harness accidentally fed the SQLC input macro `@ids` directly to PostgreSQL. Switching to the generated Go raw SQL using `$1::BIGINT[]` corrected the test across all query cases. The generated execution path and source SQL remain separately linked. [User constraint][user-hash] · [SQLC authoring query][subtask-author] · [Generated bind][subtask-delete]. |
| Stock statement timeout failed even when local PostgreSQL was reachable. | The first immediate reconnect on the one-connection socket limit closed before query execution. Raising the test-only adapter limit to four let a second independent `psql` invocation connect. It returned `0` from `SHOW statement_timeout` despite the startup option. The unchanged Go URI construction test passed. Bypassing the adapter and helper altogether, direct PGlite `SET statement_timeout = '100ms'` made `SHOW` return `100ms`, while `SELECT pg_sleep(0.6)` still returned successfully at 602.1 ms. The fixture cannot answer the native timeout question. [URI production code][statement] · [Shipped integration case][statement-live]. |
| Rollback after the constrained insert failed only on one wire path. | The first disk-backed server fixture exited before readiness with an empty server log. An in-memory fixture with the same schema reached readiness. Later disk-backed controls reused the original data directory through the same wire adapter. They connected with and without explicit extension bundles and each read eight flow rows. The early startup miss did not recur, and its exact cause remains unresolved. In the lib/pq run, the constrained insert returned the expected constraint error. The ensuing rollback returned `unexpected ReadyForQuery` in all three trials. Clean rollback with the same generated methods and driver passed three times. A separate psql transaction recovered from a deliberately invalid statement and returned 42 after rollback. Direct embedded SQL restored the plan and pgx simple protocol repeated the generated-method fault case successfully, returning SQLSTATE `23514` for the intended insert and restoring the plan all three times. This narrows the residual failure to the lib/pq extended-query interaction with the embedded wire fixture. Native lib/pq recovery remains unverified. [SQLC DBTX binding][sqlc-tx] · [Generated array bind][subtask-delete]. |
| Terminal sampled state became running. | Sequential exact-method control left `finished` in both fake and published sequence. Disabling the latch check in a copy made the sequential control fail with `[running finished running]`. Restoring the original declaration made it pass again. The overtaking test only released the earlier running write after the terminal call returned, eliminating scheduling inference. Embedded PostgreSQL accepted the generated unguarded query and refused a conditional update in the comparison. The migrated table's only noninternal trigger was `update_flows_modified`. An invalid enum value failed with `22P02`. This triangulates what the local Go and SQL permit. Deployment reachability and frequency remain unmeasured. [Status method][flow-status] · [SQL update][flow-status-sql] · [Checked-in sequential test][finished-test]. |
| Plan replacement lost plan rows after a later failure. | Used the generated array bind, read the resulting plan from the generated planned-subtasks statement and verified the failing insert was rejected with `23502`. Repeated the same delete and insert shape in a transaction with an induced fault. Rollback preserved the previous plan. This isolates commit boundaries from enum, parameter or ordering mistakes. [Delete and insert sequence][plan-patch] · [Planned query][planned-query]. |
| Two slow subscribers consumed about ten seconds and one short-deadline event went missing. | Filled exactly two 50-event queues on a shared key before enrolling a healthy reader. The 51st publish waited 10.00613007 seconds, reaching the healthy subscription while both full ones lacked that value. The same three listeners with room took 8.937 μs in that run. The separate 30 ms publisher context expired at the blocked first queue and the later listener remained empty. Scoped publish, broadcast and cancellation/close passed. This measures fan-out and queue effects for three synthetic listeners. [Subscriber constants][channel-defaults] · [Send loop][channels]. |
| Cancellation depends on the stage that holds ownership. | An exhausted request context still permitted bounded preparation by design. The separate pre-abandon ordering let the builder start but made commit return `errFlowAbandoned`. A loaded slot held by a fake lifecycle operation stayed closing past a cancelled caller until the fixture released the slot. Once the earlier operation returned, the budget was fresh and the leftover control proved the cleanup timeout was independent. The already-cancelled idle slot race exercised both ready select cases, 111 successful acquisitions in 200 iterations on the recorded run. The held slot had zero successful acquisitions. [Prepare and commit][prepare] · [Slot acquire][flow-entry] · [Loaded finish][finish-controller]. |
| Flow admission could be delayed before preparation. | The admission slice gated only its publisher, after the synthetic reservation step returned. No worker was scheduled and no response arrived while the gate was held. Both completed after release. The actual fan-out control independently supplied evidence for the slow publication boundary. [CreateFlow ordering][create-flow] · [Publish loop][channels]. |
| An expired setup budget suppressed failure evidence in the source slice. | Injected an already-expired context into the exact failure method, then repeated with an equivalent fresh context using the same context-sensitive fake. Both write attempts occurred in each branch. Only the fresh context permitted the failed status and an event. The call site uses the preparation context when invoking this method after a non-abandoned build failure. [Failure call site][prepare] · [Failure writes][fail-flow]. |
| An unaccepted input could follow preparation effects, and a nil completion result could follow cancellation. | Stub hooks isolate the pre-mailbox operations. With no reader, the callbacks ran and the caller got `ErrInputNotAccepted`. With a receiver and deliberate cancellation, the accepted sentinel and exactly-one abandonment behavior held. The original task-completion edge was explicitly captured and closed in its positive control, then a late watcher timed out on the new edge, and a cancelled worker context produced nil. These are contracts observable without any provider or task runtime. [Input handoff][flow-put] · [Completion channel][task-completion]. |

Evidence labels are used consistently here. **Isolated Go** means production declarations and test doubles. **PostgreSQL** means generated SQL executed against the migrated test schema. **Source-level** means code paths were cross-checked through the caller, lower interface and corresponding test source. A missing dependency and a failed behavioral assertion are kept as separate measurements.

## 9. Post-mortem

The code is optimized for a single server that gives a caller a usable record quickly while work continues asynchronously. The flow registry and goroutines provide an economical scheduler, and SQL stores useful durable evidence. The architecture consequently leans on three assumptions. Processes own each flow locally. Workers and runtime calls respond to context cancellation. Status records are usually written in the order produced by one worker. The code contains explicit recovery and repair for several ways those assumptions fail, such as stale worker rows and unloadable assistants. It assembles these repairs across multiple code paths as the API surface has grown. [Flow registry][registry] · [Initial admission][create-flow] · [Teardown fallback][finish-unloaded] · [Partial assistant recovery][flow-load-children].

Three likely incident classes follow directly from the evidence.

1. **A successful response can leave an ambiguous work record.** Creation can expose a row before the task input is durable. A follow-up may be accepted into memory before its reply or persistence arrives. Input preparation and API-specific interpretation have separate checkpoints. After a stopped process or a slow request, an operator needs to tell deferred work, interrupted work, state committed with observation missing, and confirmed completion apart. [Admission][create-flow] · [Initial task write][task-create] · [Acknowledgement][flow-put] · [REST translation][rest-put].
2. **A terminal record can coexist with pending activity or cleanup.** Slot closure and the lifecycle budget are different stages. Some joins assume cooperation, stop records runtime cleanup failures as warnings, and the database guards status validity without guarding terminal transitions. Reordering, cancellation or process exit can therefore leave contradictory rows or unfinished work. Status writes that precede event construction make that contradiction harder to understand from a live feed. [Controller close][finish-controller] · [Worker stop][flow-stop] · [Worker join][flow-join] · [Status method][flow-status] · [Generated SQL][flow-status-sql].
3. **The same durable history can be interpreted differently by different readers.** A partial plan change and a full conversation-body replacement have distinct failure and concurrency envelopes. Listener overload can postpone updates or leave a subscriber missing an event. Background stream persistence adds another boundary. Crash recovery has enough state to make a local choice and limited evidence about in-flight effects. Treating the durable snapshot and the event stream as interchangeable obscures the cause. [Plan mutations][plan-patch] · [Chain SQL][chain-sql] · [Recovery rules][flow-restart] · [Fan-out][channels] · [Stream checkpoints][stream-save].

The highest-leverage changes are safeguards at the ownership boundaries. First, validate durable terminal transitions at the write boundary, make ambiguity explicit after interruption, and prevent an unknown prior outcome from being interpreted as confirmed completion. Ordinary result and status writes should have a clearly documented commit point. Second, give the application a shutdown owner that stops admitting work, withdraws active ownership, and records whether cleanup actually settled under a bounded deadline. Exercise the earliest preparation and latest teardown transitions with controlled failures. Third, make event loss and delay observable and let clients reconcile against a revision or cursor on the authoritative record. A dependency-light lifecycle and event test surface with a small real-PostgreSQL fixture would put these contracts under routine coverage. This prioritization is based on the reproduced synthetic cases and source review. [State write boundary][flow-status-sql] · [Application shutdown][main-shutdown] · [Current lifecycle coverage][budget-test] · [Subscription send loop][channels] · [Test layers][test-guide].

## 10. Evidence appendix

### Checkout and offline runner

The following commands recreate the source archive and isolated runner on this machine. Run them from the evaluation workspace. The `run` script takes a command and its arguments. All Go commands in §10 are relative to `backend/` inside the archive. The initial probe used the host cache read-only at `/gomod`. The substitute writable cache contains reflinked local content. [Module versions][go-module] · [Repository CI][ci-test].

```bash
repo="$PWD/repos/vxcontrol__pentagi"
pin=cffed9485aa1cca70762cd08a57ac62a80406258
test "$(git -C "$repo" rev-parse HEAD)" = "$pin"
test -z "$(GIT_OPTIONAL_LOCKS=0 git -C "$repo" status --porcelain=v1 --untracked-files=all)"
work=$(mktemp -d $HOME/agent-work/scratch/pentagi-review-XXXXXX)
mkdir -p "$work"/{src,home,cache,tmp,modcopy}
git -C "$repo" archive HEAD | tar -xf - -C "$work/src"
cp -a --reflink=always $HOME/go/pkg/mod/. "$work/modcopy/"
```

Save the runner as `$work/run` and make it executable.

```bash
#!/bin/bash
set -euo pipefail
scratch=$(dirname "$0")
disk_go=$HOME/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.10.linux-amd64
exec unshare -Urn /bin/bash -c '
  set -euo pipefail
  ip link set lo up
  scratch=$1
  disk_go=$2
  shift 2
  exec bwrap --unshare-pid --unshare-ipc --unshare-uts --die-with-parent \
    --clearenv --ro-bind /usr /usr --symlink usr/bin /bin --symlink usr/lib /lib \
    --symlink usr/lib /lib64 --symlink usr/bin /sbin --dev /dev --proc /proc \
    --dir /etc --ro-bind /etc/ld.so.cache /etc/ld.so.cache \
    --ro-bind /etc/ssl/certs /etc/ssl/certs --ro-bind /etc/passwd /etc/passwd \
    --ro-bind "$disk_go" /toolchain --bind "$scratch/modcopy" /gomod \
    --bind "$scratch" /work --dir /run --chdir /work/src/backend \
    --setenv HOME /work/home --setenv PATH /toolchain/bin:/usr/bin:/bin \
    --setenv GOCACHE /work/cache --setenv GOMODCACHE /gomod --setenv TMPDIR /work/tmp \
    --setenv GOPROXY off --setenv GOSUMDB off --setenv GOTOOLCHAIN local \
    --setenv GOWORK off --setenv GOFLAGS -mod=readonly --setenv TZ UTC \
    --setenv AWS_EC2_METADATA_DISABLED true --setenv LC_ALL C \
    -- "$@"
' bash "$scratch" "$disk_go" "$@"
```

```bash
"$work/run" sh -c 'go version; ip -br link; ip route show; ip -6 route show; test ! -e /run/docker.sock'
"$work/run" go mod edit -json
"$work/run" go generate ./cmd/installer/files/
"$work/run" go test -json -count=1 -p 4 -run '^$' ./...
"$work/run" go test -json -race -count=1 -p 4 \
    ./cmd/installer/files ./cmd/installer/wizard/window ./migrations \
    ./pkg/database/knowledge/limits ./pkg/password \
    ./pkg/observability/langfuse/api/internal ./pkg/observability/langfuse/api/client \
    ./pkg/resources ./pkg/timezone ./pkg/version
"$work/run" go test -json -count=1 -p 1 -tags postgres -run '^$' \
    ./pkg/database/... ./pkg/timezone/... ./migrations
"$work/run" go test -json -race -count=1 \
    pkg/database/statement_timeout.go pkg/database/statement_timeout_test.go \
    pkg/database/renumbered_migrations.go pkg/database/renumbered_migrations_test.go
```

To count outcomes, parse each JSON line and count package records with `Action` equal to `pass`, `fail` or `skip` and no `Test` field. Count test records separately. A top-level test's `Test` name contains no slash. For coverage of exact dependency payloads, enumerate `Require` from `go mod edit -json`, apply Go module escaping for uppercase components, and check either `/gomod/$module@$version` or both `cache/download/$module/@v/$version.zip` and its `.ziphash`. The isolated Go 1.27.1 comparison used the same mounts and environment, binding `$HOME/.local/go-1.27.1/go` at `/toolchain`.

### Go source slices and controls

The unchanged reply test can be run with a two-import extraction of the shipped helper.

```bash
{
    printf 'package controller\n\nimport ("testing"; "time")\n\n'
    sed -n '26,39p' "$repo/backend/pkg/controller/fixtures_test.go"
} > "$work/src/backend/pkg/controller/review_input_fixture_test.go"
"$work/run" go test -json -race -count=100 pkg/controller/input_reply.go \
    pkg/controller/input_reply_test.go pkg/controller/review_input_fixture_test.go
```

The remaining isolated Go controls compiled copied declarations from the spans below. Package names and imports were adapted to the scratch package. The input and admission cases substitute interface and argument types at their boundaries, preserving the source logic. Side effects in these tests are local counters, synthetic row state, and Go channels.

| Control | Exact source used | Compare and observe |
|---|---|---|
| Event fan-out | [Channel defaults][channel-defaults] and [Channel methods][channels] | Two 50-value queues are full before a third subscriber is added. Publish one more value with and without a 30 ms request deadline. Drain the full queues and repeat. Separately exercise publication to one key, broadcast to two and cancellation-triggered close. |
| Status write/state publication | [Latch and SetStatus][flow-status] | Local store can pause a running write before acquiring the store lock, reject a terminal write, or reject the follow-up snapshot read. Compare with sequential running–finished–running, and verify returned errors and ordered observations separately from final row and latch state. |
| Completion edge and slot locks | [Completion edge][task-completion] and [Slot declarations][flow-entry] | Capture the original channel, signal completion, attach a late waiter with a 25 ms deadline and then cancel the worker. Cancel a caller while the entry is busy and compare it to 200 iterations on a free slot. |
| Lifecycle | [Controller ownership][claim], [Builder wrapper][prepare], [Reservation and commit][entry-commit], [Finish][finish-controller] | Claim a committed worker after request cancellation. Close an uncommitted reservation before the builder installs abort and check commit fails. Hold the loaded slot through cancellation, release it and compare the result. Give a fake worker 30 ms and inspect the following independent leftovers deadline. |
| Input admission | [Flow reply][flow-put] and [Reply primitive][reply] | Record provider and resource preparation callbacks through a timeout with no mailbox reader. Use a blocked reply receiver for the accepted comparison. Cancel the worker before entry for the plain cancellation case. |
| Admission ordering | [CreateFlow][create-flow] | Block the publisher after reservation and require preparation and response to remain pending. Resume the publisher and observe both. |
| Failure recording | [Failure method][fail-flow] | Send it an expired context and the same failure on a live context. Record attempts, committed status and events independently. |
| Sink drain | [Drain implementation][observer-drain] | Hold one sink until after the caller returns. Verify the second got to shutdown and the caller received `DeadlineExceeded`. Use two distinct errors to verify the joined error keeps both causes. |

<details>
<summary>Copyable Go fixtures and execution commands</summary>

```bash
mkdir -p "$work/src/backend/offline_review_control/database" "$work/src/backend/offline_observer"
cat > "$work/src/backend/offline_review_control/channel.go" <<'PENTAGI_OFFLINE_FIXTURE'
package offline_review_control

import (
	"context"
	"sync"
	"time"
)

const (
	defChannelLen  = 50
	defSendTimeout = 5 * time.Second
)

type Channel[T any] interface {
	Subscribe(ctx context.Context, id int64) <-chan T
	Publish(ctx context.Context, id int64, data T)
	Broadcast(ctx context.Context, data T)
}

func NewChannel[T any]() Channel[T] {
	return &channel[T]{
		mx:   &sync.RWMutex{},
		subs: make(map[int64][]chan T),
	}
}

type channel[T any] struct {
	mx   *sync.RWMutex
	subs map[int64][]chan T
}

func (c *channel[T]) Subscribe(ctx context.Context, id int64) <-chan T {
	c.mx.Lock()
	defer c.mx.Unlock()

	ch := make(chan T, defChannelLen)
	c.subs[id] = append(c.subs[id], ch)

	go func() {
		<-ctx.Done()

		c.mx.Lock()
		defer c.mx.Unlock()

		if subs, ok := c.subs[id]; ok {
			for i, sub := range subs {
				if sub == ch {
					c.subs[id] = append(subs[:i], subs[i+1:]...)
					break
				}
			}
		}

		if len(c.subs[id]) == 0 {
			delete(c.subs, id)
		}

		close(ch)
	}()

	return ch
}

func (c *channel[T]) Publish(ctx context.Context, id int64, data T) {
	c.mx.RLock()
	defer c.mx.RUnlock()

	for _, ch := range c.subs[id] {
		timer := time.NewTimer(defSendTimeout)
		select {
		case ch <- data:
			timer.Stop()
		case <-ctx.Done():
			timer.Stop()
			return
		case <-timer.C:
			// subscriber is slow or disconnected; drop the event after timeout
		}
	}
}

func (c *channel[T]) Broadcast(ctx context.Context, data T) {
	c.mx.RLock()
	defer c.mx.RUnlock()

	for _, subs := range c.subs {
		for _, ch := range subs {
			timer := time.NewTimer(defSendTimeout)
			select {
			case ch <- data:
				timer.Stop()
			case <-ctx.Done():
				timer.Stop()
				return
			case <-timer.C:
				// subscriber is slow or disconnected; drop the event after timeout
			}
		}
	}
}
PENTAGI_OFFLINE_FIXTURE
cat > "$work/src/backend/offline_review_control/control_test.go" <<'PENTAGI_OFFLINE_FIXTURE'
package offline_review_control

import (
	"context"
	"errors"
	"fmt"
	"pentagi/offline_review_control/database"
	"sync"
	"testing"
	"time"
)

func receive[T any](t *testing.T, values <-chan T) T {
	t.Helper()
	select {
	case value := <-values:
		return value
	case <-time.After(15 * time.Second):
		t.Fatal("timed out waiting for fixture")
	}
	var zero T
	return zero
}

func TestChannelScopeAndCancellation(t *testing.T) {
	streams := NewChannel[int]()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	run := streams.Subscribe(ctx, 1)
	elsewhere := streams.Subscribe(ctx, 2)
	streams.Publish(ctx, 1, 42)
	if got := receive(t, run); got != 42 {
		t.Fatalf("scoped publish yielded %d", got)
	}
	if len(elsewhere) != 0 {
		t.Fatalf("unexpected delivery to a different key")
	}
	streams.Broadcast(ctx, 73)
	for _, ch := range []<-chan int{run, elsewhere} {
		if got := receive(t, ch); got != 73 {
			t.Fatalf("broadcast yielded %d", got)
		}
	}
	cancel()
	for _, ch := range []<-chan int{run, elsewhere} {
		select {
		case _, ok := <-ch:
			if ok {
				t.Fatal("received a value after draining and cancelling")
			}
		case <-time.After(2 * time.Second):
			t.Fatal("subscriber not closed")
		}
	}
}

func TestChannelComposesSlowSubscriberBudgets(t *testing.T) {
	streams := NewChannel[int]()
	subCtx, cancelSubs := context.WithCancel(context.Background())
	defer cancelSubs()
	slow1, slow2 := streams.Subscribe(subCtx, 1), streams.Subscribe(subCtx, 1)
	for i := 0; i < 50; i++ {
		streams.Publish(subCtx, 1, i)
	}
	if len(slow1) != 50 || len(slow2) != 50 {
		t.Fatal("fixture did not fill both buffers")
	}
	healthy := streams.Subscribe(subCtx, 1)
	started := time.Now()
	done := make(chan time.Duration, 1)
	go func() {
		streams.Publish(subCtx, 1, 99)
		done <- time.Since(started)
	}()
	got := receive(t, healthy)
	elapsed := receive(t, done)
	if got != 99 || elapsed < 9*time.Second {
		t.Fatalf("healthy delivery=%d elapsed=%s", got, elapsed)
	}
	t.Logf("two full subscribers delayed healthy delivery by %s", elapsed)
	for _, ch := range []<-chan int{slow1, slow2} {
		for i := 0; i < 50; i++ {
			if got := receive(t, ch); got != i {
				t.Fatalf("buffer at %d contains %d", i, got)
			}
		}
		if len(ch) != 0 {
			t.Fatal("timed-out event was inserted")
		}
	}
	started = time.Now()
	streams.Publish(subCtx, 1, 100)
	if got := receive(t, healthy); got != 100 {
		t.Fatalf("drained-buffer control yielded %d", got)
	}
	if elapsed := time.Since(started); elapsed > time.Second {
		t.Fatalf("healthy control exceeded one second: %s", elapsed)
	} else {
		t.Logf("same subscribers with space took %s", elapsed)
	}
}

func TestChannelShortPublisherBudgetStopsFanout(t *testing.T) {
	streams := NewChannel[int]()
	subCtx, cancelSubs := context.WithCancel(context.Background())
	defer cancelSubs()
	slow := streams.Subscribe(subCtx, 1)
	for i := 0; i < 50; i++ {
		streams.Publish(subCtx, 1, i)
	}
	healthy := streams.Subscribe(subCtx, 1)
	sendCtx, cancelSend := context.WithTimeout(subCtx, 30*time.Millisecond)
	defer cancelSend()
	streams.Publish(sendCtx, 1, 99)
	if sendCtx.Err() != context.DeadlineExceeded || len(slow) != 50 || len(healthy) != 0 {
		t.Fatalf("err=%v slow=%d healthy=%d", sendCtx.Err(), len(slow), len(healthy))
	}
}

type fakeFlowStore struct {
	mu        sync.Mutex
	status    database.FlowStatus
	updateErr error
	readErr   error
	entered   chan struct{}
	proceed   chan struct{}
}

func (f *fakeFlowStore) UpdateFlowStatus(ctx context.Context, arg database.UpdateFlowStatusParams) (database.Flow, error) {
	if f.entered != nil && arg.Status == database.FlowStatusRunning {
		close(f.entered)
		select {
		case <-f.proceed:
		case <-ctx.Done():
			return database.Flow{}, ctx.Err()
		}
	}
	if err := ctx.Err(); err != nil {
		return database.Flow{}, err
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.updateErr != nil {
		return database.Flow{}, f.updateErr
	}
	f.status = arg.Status
	return database.Flow{ID: arg.ID, Status: arg.Status}, nil
}

func (f *fakeFlowStore) GetFlowContainers(ctx context.Context, id int64) ([]database.Container, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return nil, f.readErr
}

func (f *fakeFlowStore) current() database.FlowStatus {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.status
}

type recordEvents struct {
	mu       sync.Mutex
	statuses []database.FlowStatus
}

func (r *recordEvents) FlowUpdated(ctx context.Context, flow database.Flow, containers []database.Container) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.statuses = append(r.statuses, flow.Status)
}

func newFlow(ctx context.Context, store *fakeFlowStore, publisher *recordEvents) *flowWorker {
	return &flowWorker{ctx: ctx, taskCCH: make(chan struct{}), flowCtx: &FlowContext{
		FlowID: 1, DB: store, Publisher: publisher,
	}}
}

func TestStatusCanOvertakeFinalization(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 4*time.Second)
	defer cancel()
	store := &fakeFlowStore{entered: make(chan struct{}), proceed: make(chan struct{})}
	events := new(recordEvents)
	flow := newFlow(ctx, store, events)
	pending := make(chan error, 1)
	go func() { pending <- flow.SetStatus(ctx, database.FlowStatusRunning) }()
	receive(t, store.entered)
	if err := flow.SetStatus(ctx, database.FlowStatusFinished); err != nil {
		t.Fatal(err)
	}
	if !flow.finalized.Load() || store.current() != database.FlowStatusFinished {
		t.Fatal("terminal control failed before releasing the earlier status writer")
	}
	close(store.proceed)
	if err := receive(t, pending); err != nil {
		t.Fatal(err)
	}
	if store.current() != database.FlowStatusRunning {
		t.Fatalf("expected reordered write to be visible, got %q", store.current())
	}
	if got := fmt.Sprint(events.statuses); got != "[finished running]" {
		t.Fatalf("published statuses %s", got)
	}
}

func TestStatusSequentialFinalizationControl(t *testing.T) {
	ctx := context.Background()
	store := new(fakeFlowStore)
	events := new(recordEvents)
	flow := newFlow(ctx, store, events)
	for _, status := range []database.FlowStatus{database.FlowStatusRunning, database.FlowStatusFinished, database.FlowStatusRunning} {
		if err := flow.SetStatus(ctx, status); err != nil {
			t.Fatal(err)
		}
	}
	if store.current() != database.FlowStatusFinished || fmt.Sprint(events.statuses) != "[running finished]" {
		t.Fatalf("state=%q published=%v", store.current(), events.statuses)
	}
}

func TestStatusSeparatesCommitFromPublish(t *testing.T) {
	ctx := context.Background()
	readFailure := errors.New("snapshot read unavailable")
	store := &fakeFlowStore{readErr: readFailure}
	events := new(recordEvents)
	flow := newFlow(ctx, store, events)
	if err := flow.SetStatus(ctx, database.FlowStatusFinished); !errors.Is(err, readFailure) {
		t.Fatalf("status operation returned %v", err)
	}
	if store.current() != database.FlowStatusFinished || len(events.statuses) != 0 {
		t.Fatalf("state=%q published=%v", store.current(), events.statuses)
	}
}

func TestStatusLatchSurvivesFailedTerminalWrite(t *testing.T) {
	ctx := context.Background()
	writeFailure := errors.New("write unavailable")
	store := &fakeFlowStore{status: database.FlowStatusRunning, updateErr: writeFailure}
	events := new(recordEvents)
	flow := newFlow(ctx, store, events)
	if err := flow.SetStatus(ctx, database.FlowStatusFinished); !errors.Is(err, writeFailure) {
		t.Fatal(err)
	}
	store.updateErr = nil
	if err := flow.SetStatus(ctx, database.FlowStatusRunning); err != nil {
		t.Fatal(err)
	}
	if !flow.finalized.Load() || store.current() != database.FlowStatusRunning || len(events.statuses) != 0 {
		t.Fatalf("latch=%v state=%q published=%v", flow.finalized.Load(), store.current(), events.statuses)
	}
	if err := flow.SetStatus(ctx, database.FlowStatusFinished); err != nil {
		t.Fatal(err)
	}
	if store.current() != database.FlowStatusFinished || len(events.statuses) != 1 {
		t.Fatalf("terminal retry state=%q published=%v", store.current(), events.statuses)
	}
}

func TestCompletionIsEdgeTriggeredAndStopIsNil(t *testing.T) {
	flowCtx, stop := context.WithCancel(context.Background())
	defer stop()
	flow := newFlow(flowCtx, nil, nil)
	first := flow.taskCCH
	flow.signalTaskComplete()
	select {
	case <-first:
	default:
		t.Fatal("the previously captured edge was not closed")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 25*time.Millisecond)
	defer cancel()
	if err := flow.WaitTaskCompletion(ctx); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("late subscriber returned %v", err)
	}
	stop()
	if err := flow.WaitTaskCompletion(context.Background()); err != nil {
		t.Fatalf("stop returned %v", err)
	}
}

func TestEntryContextDistinguishesHeldAndFree(t *testing.T) {
	entry := newFlowEntry()
	entry.lock()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if entry.acquire(ctx) {
		t.Fatal("acquired busy slot with cancelled context")
	}
	entry.release()
	granted := 0
	for i := 0; i < 200; i++ {
		if entry.acquire(ctx) {
			granted++
			entry.release()
		}
	}
	if granted == 0 || granted == 200 {
		t.Fatalf("one select branch was never exercised: %d", granted)
	}
	t.Logf("already-cancelled context with available slot: %d/200 successful acquisitions", granted)
}
PENTAGI_OFFLINE_FIXTURE
cat > "$work/src/backend/offline_review_control/database/database.go" <<'PENTAGI_OFFLINE_FIXTURE'
package database

type FlowStatus string

const (
	FlowStatusRunning  FlowStatus = "running"
	FlowStatusFinished FlowStatus = "finished"
	FlowStatusFailed   FlowStatus = "failed"
)

type UpdateFlowStatusParams struct {
	Status FlowStatus
	ID     int64
}
type Flow struct {
	ID     int64
	Status FlowStatus
}
type Container struct{}
type UserResource struct{}
PENTAGI_OFFLINE_FIXTURE
cat > "$work/src/backend/offline_review_control/entry.go" <<'PENTAGI_OFFLINE_FIXTURE'
package offline_review_control

import "context"

type flowEntry struct {
	op        chan struct{}
	worker    FlowWorker
	preparing bool
	closing   bool
	committed bool
	abort     context.CancelFunc

	// done is closed once the teardown of an unloaded flow has ended and its
	// slot is gone; it is nil on a slot that holds a worker or a preparation.
	done chan struct{}
}

func newFlowEntry() *flowEntry {
	return &flowEntry{op: make(chan struct{}, 1)}
}

func (e *flowEntry) acquire(ctx context.Context) bool {
	select {
	case e.op <- struct{}{}:
		return true
	case <-ctx.Done():
		return false
	}
}

func (e *flowEntry) lock() {
	e.op <- struct{}{}
}

func (e *flowEntry) release() {
	<-e.op
}

func (e *flowEntry) available() bool {
	return e.worker != nil && !e.preparing && !e.closing
}

type FlowWorker interface {
	GetFlowID() int64
	Finish(context.Context) error
}
PENTAGI_OFFLINE_FIXTURE
cat > "$work/src/backend/offline_review_control/flow.go" <<'PENTAGI_OFFLINE_FIXTURE'
package offline_review_control

import (
	"context"
	"fmt"
	"github.com/sirupsen/logrus"
	database "pentagi/offline_review_control/database"
	"sync"
	"sync/atomic"
)

func (fw *flowWorker) takeStatus(status database.FlowStatus) bool {
	switch status {
	case database.FlowStatusFinished, database.FlowStatusFailed:
		fw.finalized.Store(true)

		return true
	default:
		return !fw.finalized.Load()
	}
}
func (fw *flowWorker) SetStatus(ctx context.Context, status database.FlowStatus) error {
	if !fw.takeStatus(status) {
		return nil
	}

	flow, err := fw.flowCtx.DB.UpdateFlowStatus(ctx, database.UpdateFlowStatusParams{
		Status: status,
		ID:     fw.flowCtx.FlowID,
	})
	if err != nil {
		return fmt.Errorf("failed to set flow %d status: %w", fw.flowCtx.FlowID, err)
	}

	containers, err := fw.flowCtx.DB.GetFlowContainers(ctx, fw.flowCtx.FlowID)
	if err != nil {
		return fmt.Errorf("failed to get flow %d containers: %w", fw.flowCtx.FlowID, err)
	}

	fw.flowCtx.Publisher.FlowUpdated(ctx, flow, containers)

	return nil
}
func (fw *flowWorker) signalTaskComplete() {
	fw.taskCMX.Lock()
	old := fw.taskCCH
	fw.taskCCH = make(chan struct{})
	fw.taskCMX.Unlock()
	close(old)
}

// WaitTaskCompletion blocks until the currently running task completes,
// the supplied context expires, or the flow worker itself is stopped.
// Multiple concurrent callers are all unblocked at once when a task finishes.
func (fw *flowWorker) WaitTaskCompletion(ctx context.Context) error {
	fw.taskCMX.Lock()
	ch := fw.taskCCH
	fw.taskCMX.Unlock()

	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-ch:
		return nil
	case <-fw.ctx.Done():
		return nil
	}
}

type flowWorker struct {
	ctx         context.Context
	finalized   atomic.Bool
	flowCtx     *FlowContext
	taskCMX     sync.Mutex
	taskCCH     chan struct{}
	input       chan flowInput
	logger      *logrus.Entry
	onSwitch    func(context.Context) error
	onResources func(context.Context) error
}

type FlowContext struct {
	FlowID int64
	DB     interface {
		UpdateFlowStatus(context.Context, database.UpdateFlowStatusParams) (database.Flow, error)
		GetFlowContainers(context.Context, int64) ([]database.Container, error)
	}
	Publisher interface {
		FlowUpdated(context.Context, database.Flow, []database.Container)
	}
}
PENTAGI_OFFLINE_FIXTURE
cat > "$work/src/backend/offline_review_control/input.go" <<'PENTAGI_OFFLINE_FIXTURE'
package offline_review_control

import (
	"context"
	"errors"
	"fmt"
	database "pentagi/offline_review_control/database"
	"time"
)

const flowInputTimeout = 1 * time.Second

// ErrInputAccepted reports that the worker took the input but had not finished
// with it before the CALLER's deadline. The work continues, so the caller must
// observe the outcome through the flow's status rather than send it again.
// A worker that merely outlives flowInputTimeout returns nil, as it always has.
var ErrInputAccepted = errors.New("input accepted, still being processed")

// ErrInputNotAccepted reports the opposite: the worker never took the input, so
// nothing was started and sending it again is safe. Telling these two apart is
// the whole point -- a caller that cannot duplicates the action or drops it.
var ErrInputNotAccepted = errors.New("input was not accepted")

type flowInput struct {
	input string
	reply *inputReply
}

func (fw *flowWorker) PutInput(
	ctx context.Context,
	input string,
	prv fakeProvider,
	resources []database.UserResource,
) error {
	ctx, span := obs.Observer.NewSpan(ctx, obs.SpanKindInternal, "controller.flowWorker.PutInput")
	defer span.End()

	if err := fw.ctx.Err(); err != nil {
		return fmt.Errorf("flow %d stopped: %w", fw.flowCtx.FlowID, err)
	}

	if err := fw.switchProvider(ctx, prv); err != nil {
		return fmt.Errorf("failed to switch provider: %w", err)
	}

	if err := fw.PutResources(ctx, resources); err != nil {
		fw.logger.WithError(err).Warn("failed to copy resources before user input")
	}

	flin := flowInput{input: input, reply: newInputReply()}
	select {
	case <-fw.ctx.Done():
		return fmt.Errorf("flow %d stopped: %w: %w", fw.flowCtx.FlowID, ErrInputNotAccepted, fw.ctx.Err())
	case <-ctx.Done():
		return fmt.Errorf("flow %d input processing timeout: %w: %w",
			fw.flowCtx.FlowID, ErrInputNotAccepted, ctx.Err())
	case fw.input <- flin:
		timer := time.NewTimer(flowInputTimeout)
		defer timer.Stop()

		// The worker has the input. Whether it answers in time decides only what
		// this caller learns, not whether the work happens -- so the timer
		// expiring stays the ordinary quiet success it has always been, and only
		// the caller's own deadline needs a name, because that is the one that
		// reaches an HTTP client deciding whether to send the input again.
		var stopErr error
		select {
		case err := <-flin.reply.done:
			return err
		case <-timer.C:
		case <-fw.ctx.Done():
			stopErr = fmt.Errorf("flow %d stopped: %w", fw.flowCtx.FlowID, fw.ctx.Err())
		case <-ctx.Done():
			stopErr = fmt.Errorf("flow %d input processing timeout: %w: %w",
				fw.flowCtx.FlowID, ErrInputAccepted, ctx.Err())
		}

		if isDelivered, err := flin.reply.abandon(); isDelivered {
			return err
		}

		return stopErr
	}
}

type fakeProvider interface{}
type neutralSpan struct{}

func (neutralSpan) End() {}

type neutralObserver struct{}

func (neutralObserver) NewSpan(ctx context.Context, ignore any, label string) (context.Context, neutralSpan) {
	return ctx, neutralSpan{}
}

var obs = struct {
	Observer         neutralObserver
	SpanKindInternal any
}{}

func (fw *flowWorker) switchProvider(ctx context.Context, prv fakeProvider) error {
	if fw.onSwitch != nil {
		return fw.onSwitch(ctx)
	}
	return nil
}
func (fw *flowWorker) PutResources(ctx context.Context, resources []database.UserResource) error {
	if fw.onResources != nil {
		return fw.onResources(ctx)
	}
	return nil
}
PENTAGI_OFFLINE_FIXTURE
cat > "$work/src/backend/offline_review_control/input_reply.go" <<'PENTAGI_OFFLINE_FIXTURE'
package offline_review_control

import "sync/atomic"

const (
	replyWaiting int32 = iota
	replyDelivered
	replyAbandoned
)

type inputReply struct {
	state atomic.Int32
	done  chan error
}

func newInputReply() *inputReply {
	return &inputReply{done: make(chan error, 1)}
}

func (r *inputReply) deliver(err error) bool {
	if !r.state.CompareAndSwap(replyWaiting, replyDelivered) {
		return false
	}
	r.done <- err

	return true
}

func (r *inputReply) abandon() (isDelivered bool, err error) {
	if r.state.CompareAndSwap(replyWaiting, replyAbandoned) {
		return false, nil
	}

	return true, <-r.done
}
PENTAGI_OFFLINE_FIXTURE
cat > "$work/src/backend/offline_review_control/input_test.go" <<'PENTAGI_OFFLINE_FIXTURE'
package offline_review_control

import (
	"context"
	"errors"
	"reflect"
	"testing"
	"time"
)

func TestInputAcknowledgementCanFollowPreparationSideEffects(t *testing.T) {
	flowCtx, cancelFlow := context.WithCancel(context.Background())
	defer cancelFlow()
	flow := newFlow(flowCtx, nil, nil)
	flow.input = make(chan flowInput)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	got := []string{}
	flow.onSwitch = func(ctx context.Context) error {
		if err := ctx.Err(); err != nil {
			return err
		}
		got = append(got, "switch")
		return nil
	}
	flow.onResources = func(ctx context.Context) error {
		if err := ctx.Err(); err != nil {
			return err
		}
		got = append(got, "resources")
		return nil
	}
	err := flow.PutInput(ctx, "inert request", nil, nil)
	if !errors.Is(err, ErrInputNotAccepted) || !errors.Is(err, context.DeadlineExceeded) ||
		!reflect.DeepEqual(got, []string{"switch", "resources"}) {
		t.Fatalf("outcome=%v calls=%v", err, got)
	}
}

func TestInputAcknowledgementReportsAcceptedAfterHandoff(t *testing.T) {
	flowCtx, cancelFlow := context.WithCancel(context.Background())
	defer cancelFlow()
	flow := newFlow(flowCtx, nil, nil)
	flow.input = make(chan flowInput)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	completed := make(chan error, 1)
	go func() { completed <- flow.PutInput(ctx, "inert request", nil, nil) }()
	input := receive(t, flow.input)
	cancel()
	err := receive(t, completed)
	if !errors.Is(err, ErrInputAccepted) || !errors.Is(err, context.Canceled) ||
		input.reply.deliver(errors.New("late fixture rejection")) {
		t.Fatalf("outcome=%v or late reply incorrectly accepted", err)
	}
}

func TestInputAcknowledgementFirstShutdownPathHasPlainCancellation(t *testing.T) {
	flowCtx, cancelFlow := context.WithCancel(context.Background())
	cancelFlow()
	flow := newFlow(flowCtx, nil, nil)
	err := flow.PutInput(context.Background(), "inert request", nil, nil)
	if !errors.Is(err, context.Canceled) || errors.Is(err, ErrInputNotAccepted) || errors.Is(err, ErrInputAccepted) {
		t.Fatalf("outcome=%v", err)
	}
}
PENTAGI_OFFLINE_FIXTURE
cat > "$work/src/backend/offline_review_control/lifecycle.go" <<'PENTAGI_OFFLINE_FIXTURE'
package offline_review_control

import (
	"context"
	"errors"
	"fmt"
	"github.com/sirupsen/logrus"
	database "pentagi/offline_review_control/database"
	"sync"
	"time"
)

var errFlowAbandoned = errors.New("flow was closed while it was preparing")

const flowPrepareTimeout = 30 * time.Minute
const flowFinishTimeout = 5 * time.Minute
const flowLeftoversTimeout = 30 * time.Second

func (fc *flowController) unregister(flowID int64, entry *flowEntry) {
	fc.mx.Lock()
	defer fc.mx.Unlock()

	if fc.flows[flowID] == entry {
		delete(fc.flows, flowID)
	}
}

// lockSettled takes fc.mx once no teardown of an unloaded flow holds flowID's
// slot, so a delete or a new assistant acts on the flow the teardown left and
// not on containers still being removed. It returns with fc.mx held, or with
// ctx's error and fc.mx released.
func (fc *flowController) lockSettled(ctx context.Context, flowID int64) (*flowEntry, bool, error) {
	for {
		fc.mx.Lock()
		entry, ok := fc.flows[flowID]
		if !ok || entry.done == nil {
			return entry, ok, nil
		}
		done := entry.done
		fc.mx.Unlock()

		select {
		case <-done:
		case <-ctx.Done():
			return nil, false, ctx.Err()
		}
	}
}

func (fc *flowController) entryOf(flowID int64) (*flowEntry, bool) {
	fc.mx.Lock()
	defer fc.mx.Unlock()

	entry, ok := fc.flows[flowID]
	if !ok || !entry.available() {
		return nil, false
	}

	return entry, true
}

// claim hands out a flow with its lifecycle lock already held: the caller must
// release it with defer entry.release().
func (fc *flowController) claim(ctx context.Context, flowID int64) (*flowEntry, FlowWorker, bool) {
	entry, ok := fc.entryOf(flowID)
	if !ok {
		return nil, nil, false
	}

	if !entry.acquire(ctx) {
		return nil, nil, false
	}

	fc.mx.Lock()
	still := fc.flows[flowID] == entry && entry.available()
	worker := entry.worker
	fc.mx.Unlock()

	if !still {
		entry.release()
		return nil, nil, false
	}

	return entry, worker, true
}
func (fc *flowController) prepareFlow(
	ctx context.Context,
	entry *flowEntry,
	flow database.Flow,
	build func(context.Context, func() error) (FlowWorker, error),
) {
	ctx, cancel := context.WithTimeout(context.WithoutCancel(ctx), flowPrepareTimeout)
	defer cancel()

	fc.mx.Lock()
	entry.abort = cancel
	fc.mx.Unlock()

	entry.lock()
	defer entry.release()

	worker, err := build(ctx, func() error { return fc.commitPreparation(entry) })
	logger := logrus.WithContext(ctx).WithField("flow_id", flow.ID)

	fc.mx.Lock()
	entry.preparing = false
	entry.worker = worker
	abandoned := !entry.committed && (entry.closing || fc.flows[flow.ID] != entry)
	if err != nil || abandoned {
		if fc.flows[flow.ID] == entry {
			delete(fc.flows, flow.ID)
		}
	}
	fc.mx.Unlock()

	switch {
	case abandoned && worker != nil:
		finishCtx, cancelFinish := context.WithTimeout(context.WithoutCancel(ctx), flowFinishTimeout)
		defer cancelFinish()

		if err := worker.Finish(finishCtx); err != nil {
			logger.WithError(err).Error("failed to release a flow that was closed while it was preparing")
		}
	case abandoned:
		logger.WithError(err).Warn("a flow closed while preparing failed to prepare")
	case err != nil:
		logger.WithError(err).Error("failed to prepare a flow")
		fc.failFlow(ctx, flow, err)
	}
}
func (fc *flowController) reserveEntry(flowID int64) (*flowEntry, bool) {
	fc.mx.Lock()
	defer fc.mx.Unlock()

	if existing, taken := fc.flows[flowID]; taken {
		return existing, false
	}

	entry := newFlowEntry()
	entry.preparing = true
	fc.flows[flowID] = entry

	return entry, true
}

func (fc *flowController) commitPreparation(entry *flowEntry) error {
	fc.mx.Lock()
	defer fc.mx.Unlock()

	if entry.closing {
		return errFlowAbandoned
	}
	entry.committed = true

	return nil
}
func (fc *flowController) FinishFlow(ctx context.Context, flowID int64) error {
	return fc.finishFlowWithin(ctx, flowID, flowFinishTimeout)
}

func (fc *flowController) finishFlowWithin(ctx context.Context, flowID int64, budget time.Duration) error {
	entry, ok, err := fc.lockSettled(ctx, flowID)
	if err != nil {
		return err
	}
	if !ok {
		// A closing slot rather than fc.mx guards the teardown: other flows stay
		// served, and no assistant reloads this one while its containers go.
		entry = newFlowEntry()
		entry.closing = true
		entry.done = make(chan struct{})
		fc.flows[flowID] = entry
		fc.mx.Unlock()
		defer func() {
			fc.unregister(flowID, entry)
			close(entry.done)
		}()

		unloadedCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), budget)
		defer cancel()

		return fc.finishUnloadedFlow(unloadedCtx, flowID)
	}

	if entry.closing {
		fc.mx.Unlock()
		return nil
	}

	entry.closing = true
	abandon := entry.preparing && !entry.committed
	if abandon && entry.abort != nil {
		entry.abort()
	}
	fc.mx.Unlock()

	if abandon {
		preparingCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), budget)
		defer cancel()

		return fc.finishUnloadedFlow(preparingCtx, flowID)
	}

	entry.lock()
	defer entry.release()

	fc.mx.Lock()
	flow := entry.worker
	fc.mx.Unlock()

	ctx, cancel := context.WithTimeout(context.WithoutCancel(ctx), budget)
	defer cancel()

	defer fc.unregister(flowID, entry)

	if flow == nil {
		return fc.finishUnloadedFlow(ctx, flowID)
	}

	var finishErr error
	if err := flow.Finish(ctx); err != nil {
		finishErr = fmt.Errorf("failed to finish flow %d: %w", flowID, err)
	}

	leftoversCtx, cancelLeftovers := context.WithTimeout(context.WithoutCancel(ctx), flowLeftoversTimeout)
	defer cancelLeftovers()

	return errors.Join(finishErr, fc.finishFlowLeftovers(leftoversCtx, flowID))
}

type flowController struct {
	mx          *sync.Mutex
	flows       map[int64]*flowEntry
	onUnloaded  func(context.Context, int64) error
	onLeftovers func(context.Context, int64) error
	onFailure   func(context.Context, database.Flow, error)
}

func (fc *flowController) failFlow(ctx context.Context, flow database.Flow, cause error) {
	if fc.onFailure != nil {
		fc.onFailure(ctx, flow, cause)
	}
}
func (fc *flowController) finishUnloadedFlow(ctx context.Context, id int64) error {
	if fc.onUnloaded != nil {
		return fc.onUnloaded(ctx, id)
	}
	return nil
}
func (fc *flowController) finishFlowLeftovers(ctx context.Context, id int64) error {
	if fc.onLeftovers != nil {
		return fc.onLeftovers(ctx, id)
	}
	return nil
}
PENTAGI_OFFLINE_FIXTURE
cat > "$work/src/backend/offline_review_control/lifecycle_test.go" <<'PENTAGI_OFFLINE_FIXTURE'
package offline_review_control

import (
	"context"
	"errors"
	"fmt"
	"pentagi/offline_review_control/database"
	"sync"
	"testing"
	"time"
)

type finishStub struct{ finish func(context.Context) error }

func (w finishStub) GetFlowID() int64                 { return 1 }
func (w finishStub) Finish(ctx context.Context) error { return w.finish(ctx) }

func newController() *flowController {
	return &flowController{mx: new(sync.Mutex), flows: make(map[int64]*flowEntry)}
}

func TestPreparationAfterCallerCancelKeepsBoundedContext(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	fc := newController()
	row := database.Flow{ID: 1}
	entry, created := fc.reserveEntry(row.ID)
	if !created {
		t.Fatal("fixture did not reserve entry")
	}
	fc.prepareFlow(ctx, entry, row, func(ctx context.Context, commit func() error) (FlowWorker, error) {
		if ctx.Err() != nil {
			t.Fatalf("builder got cancelled request: %v", ctx.Err())
		}
		deadline, exists := ctx.Deadline()
		if !exists || time.Until(deadline) > 30*time.Minute || time.Until(deadline) < 29*time.Minute {
			t.Fatalf("unexpected prep deadline %s, present=%t", deadline, exists)
		}
		return finishStub{func(ctx context.Context) error { return ctx.Err() }}, commit()
	})
	obtained, worker, ok := fc.claim(context.Background(), row.ID)
	if !ok || worker == nil || obtained != entry {
		t.Fatal("committed worker not available")
	}
	obtained.release()
}

func TestPreparationAlreadyAbandonedStillReachesBuilder(t *testing.T) {
	fc := newController()
	row := database.Flow{ID: 1}
	entry, _ := fc.reserveEntry(row.ID)
	unloadedCalls := 0
	fc.onUnloaded = func(ctx context.Context, id int64) error {
		unloadedCalls++
		return ctx.Err()
	}
	if err := fc.finishFlowWithin(context.Background(), row.ID, time.Second); err != nil {
		t.Fatal(err)
	}
	attempted := false
	fc.prepareFlow(context.Background(), entry, row, func(ctx context.Context, commit func() error) (FlowWorker, error) {
		attempted = true
		if ctx.Err() != nil {
			t.Fatalf("builder context unexpectedly cancelled: %v", ctx.Err())
		}
		if err := commit(); !errors.Is(err, errFlowAbandoned) {
			t.Fatalf("commit error %v", err)
		}
		return nil, errFlowAbandoned
	})
	if !attempted || unloadedCalls != 1 || len(fc.flows) != 0 {
		t.Fatalf("attempted=%v unloaded=%d slots=%d", attempted, unloadedCalls, len(fc.flows))
	}
}

func TestClosureWaitingForEarlierOperationIgnoresCallerDeadline(t *testing.T) {
	fc := newController()
	entry := newFlowEntry()
	fc.flows[1] = entry
	entry.lock()
	entry.worker = finishStub{func(ctx context.Context) error { return ctx.Err() }}
	ctx, cancel := context.WithCancel(context.Background())
	result := make(chan error, 1)
	go func() { result <- fc.finishFlowWithin(ctx, 1, 3*time.Second) }()
	guard := time.NewTimer(2 * time.Second)
	defer guard.Stop()
	for {
		fc.mx.Lock()
		closing := entry.closing
		fc.mx.Unlock()
		if closing {
			break
		}
		select {
		case <-guard.C:
			t.Fatal("never reached closing state")
		default:
			time.Sleep(time.Millisecond)
		}
	}
	cancel()
	select {
	case err := <-result:
		t.Fatalf("finish returned while lease held: %v", err)
	case <-time.After(30 * time.Millisecond):
	}
	entry.release()
	if err := receive(t, result); err != nil {
		t.Fatal(err)
	}
}

func TestClosureLeftoversGetIndependentBudget(t *testing.T) {
	fc := newController()
	entry := newFlowEntry()
	fc.flows[1] = entry
	entry.worker = finishStub{func(ctx context.Context) error {
		<-ctx.Done()
		return ctx.Err()
	}}
	visited := false
	fc.onLeftovers = func(ctx context.Context, id int64) error {
		visited = true
		if ctx.Err() != nil {
			return fmt.Errorf("leftovers inherited timeout: %v", ctx.Err())
		}
		if expiry, ok := ctx.Deadline(); !ok || time.Until(expiry) < 29*time.Second {
			return errors.New("independent leftovers budget absent")
		}
		return nil
	}
	err := fc.finishFlowWithin(context.Background(), 1, 30*time.Millisecond)
	if !errors.Is(err, context.DeadlineExceeded) || !visited || len(fc.flows) != 0 {
		t.Fatalf("err=%v leftovers=%v slots=%d", err, visited, len(fc.flows))
	}
}
PENTAGI_OFFLINE_FIXTURE
cat > "$work/src/backend/offline_observer/drain.go" <<'PENTAGI_OFFLINE_FIXTURE'
package offline_observer

import (
	"context"
	"errors"
	"fmt"
)

func (obs *observer) Drain(ctx context.Context) error {
	type sink struct {
		name            string
		flush, shutdown func(context.Context) error
	}
	var sinks []sink
	if obs.lfclient != nil {
		sinks = append(sinks, sink{"langfuse", obs.lfclient.ForceFlush, obs.lfclient.Shutdown})
	}
	if obs.otelclient != nil {
		sinks = append(sinks, sink{"opentelemetry", obs.otelclient.ForceFlush, obs.otelclient.Shutdown})
	}

	results := make(chan error, len(sinks))
	for _, s := range sinks {
		go func(s sink) {
			var errs []error
			if err := s.flush(ctx); err != nil {
				errs = append(errs, fmt.Errorf("%s flush: %w", s.name, err))
			}
			if err := s.shutdown(ctx); err != nil {
				errs = append(errs, fmt.Errorf("%s shutdown: %w", s.name, err))
			}
			results <- errors.Join(errs...)
		}(s)
	}

	var errs []error
	for range sinks {
		select {
		case err := <-results:
			if err != nil {
				errs = append(errs, err)
			}
		case <-ctx.Done():
			return errors.Join(append(errs, ctx.Err())...)
		}
	}
	return errors.Join(errs...)
}

type timedSink interface {
	ForceFlush(context.Context) error
	Shutdown(context.Context) error
}
type observer struct{ lfclient, otelclient timedSink }
PENTAGI_OFFLINE_FIXTURE
cat > "$work/src/backend/offline_observer/drain_test.go" <<'PENTAGI_OFFLINE_FIXTURE'
package offline_observer

import (
	"context"
	"errors"
	"testing"
	"time"
)

type sinkStub struct {
	flush    func(context.Context) error
	shutdown func(context.Context) error
}

func (s sinkStub) ForceFlush(ctx context.Context) error { return s.flush(ctx) }
func (s sinkStub) Shutdown(ctx context.Context) error   { return s.shutdown(ctx) }

func TestIndependentSinksAndDeadline(t *testing.T) {
	letGo := make(chan struct{})
	defer close(letGo)
	blocked, healthy := make(chan struct{}), make(chan struct{})
	o := observer{
		lfclient: sinkStub{flush: func(context.Context) error { close(blocked); <-letGo; return nil },
			shutdown: func(context.Context) error { return nil }},
		otelclient: sinkStub{flush: func(context.Context) error { return nil },
			shutdown: func(context.Context) error { close(healthy); return nil }},
	}
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	err := o.Drain(ctx)
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("drain returned %v", err)
	}
	for _, ch := range []<-chan struct{}{blocked, healthy} {
		select {
		case <-ch:
		default:
			t.Fatal("a sink was not reached")
		}
	}
}

func TestBothSinkErrorsAreRetained(t *testing.T) {
	first, second := errors.New("flush fixture"), errors.New("shutdown fixture")
	no := func(context.Context) error { return nil }
	o := observer{
		lfclient:   sinkStub{flush: func(context.Context) error { return first }, shutdown: no},
		otelclient: sinkStub{flush: no, shutdown: func(context.Context) error { return second }},
	}
	err := o.Drain(context.Background())
	if !errors.Is(err, first) || !errors.Is(err, second) {
		t.Fatalf("drain returned %v", err)
	}
}
PENTAGI_OFFLINE_FIXTURE

"$work/run" go test -json -race -count=1 -timeout=45s -run '^Test(Channel|Status|Completion|Entry)' ./offline_review_control
"$work/run" go test -json -race -count=20 -timeout=35s -run '^Test(Preparation|Closure)' ./offline_review_control
"$work/run" go test -json -race -count=20 -timeout=35s -run '^TestInputAcknowledgement' ./offline_review_control
"$work/run" go test -json -race -count=20 -timeout=20s ./offline_observer

mkdir -p "$work/src/backend/offline_start_failure/database"
cat > "$work/src/backend/offline_start_failure/database/database.go" <<'PENTAGI_OFFLINE_FIXTURE'
package database

type FlowStatus string

const FlowStatusFailed FlowStatus = "failed"

type Flow struct {
	ID, UserID int64
	Status     FlowStatus
}
type Container struct{}
type UpdateFlowStatusParams struct {
	ID     int64
	Status FlowStatus
}
type MsglogType string

const MsglogTypeReport MsglogType = "report"
PENTAGI_OFFLINE_FIXTURE
cat > "$work/src/backend/offline_start_failure/fail_flow.go" <<'PENTAGI_OFFLINE_FIXTURE'
package controller

import (
	"context"
	"fmt"
	"github.com/sirupsen/logrus"
	database "pentagi/offline_start_failure/database"
)

func (fc *flowController) failFlow(ctx context.Context, flow database.Flow, cause error) {
	logger := logrus.WithContext(ctx).WithField("flow_id", flow.ID)
	pub := fc.subs.NewFlowPublisher(flow.UserID, flow.ID)

	if mlw, err := fc.mlc.NewFlowMsgLog(ctx, flow.ID, pub); err != nil {
		logger.WithError(err).Warn("failed to open the message log of a flow that could not start")
	} else if _, err := mlw.PutFlowMsg(
		ctx, database.MsglogTypeReport, "", fmt.Sprintf("This flow could not be started: %s", cause),
	); err != nil {
		logger.WithError(err).Warn("failed to record why a flow could not start")
	}

	failed, err := fc.db.UpdateFlowStatus(ctx, database.UpdateFlowStatusParams{
		ID:     flow.ID,
		Status: database.FlowStatusFailed,
	})
	if err != nil {
		logger.WithError(err).Error("failed to mark a flow failed after its preparation broke")
		return
	}

	containers, err := fc.db.GetFlowContainers(ctx, flow.ID)
	if err != nil {
		logger.WithError(err).Warn("failed to read containers of a failed flow, publishing it without them")
	}

	pub.FlowUpdated(ctx, failed, containers)
}

type terminalPublisher interface {
	FlowUpdated(context.Context, database.Flow, []database.Container)
}
type flowController struct {
	subs interface {
		NewFlowPublisher(int64, int64) terminalPublisher
	}
	mlc interface {
		NewFlowMsgLog(context.Context, int64, terminalPublisher) (flowMessageLog, error)
	}
	db interface {
		UpdateFlowStatus(context.Context, database.UpdateFlowStatusParams) (database.Flow, error)
		GetFlowContainers(context.Context, int64) ([]database.Container, error)
	}
}
type flowMessageLog interface {
	PutFlowMsg(context.Context, database.MsglogType, string, string) (int64, error)
}
PENTAGI_OFFLINE_FIXTURE
cat > "$work/src/backend/offline_start_failure/fail_flow_test.go" <<'PENTAGI_OFFLINE_FIXTURE'
package controller

import (
	"context"
	"errors"
	"testing"
	"time"

	database "pentagi/offline_start_failure/database"
)

type recorder struct {
	logAttempts   int
	writeAttempts int
	events        int
	saved         database.Flow
}

func (r *recorder) NewFlowPublisher(userID, flowID int64) terminalPublisher { return r }
func (r *recorder) FlowUpdated(ctx context.Context, f database.Flow, c []database.Container) {
	r.events++
}
func (r *recorder) NewFlowMsgLog(ctx context.Context, flowID int64, p terminalPublisher) (flowMessageLog, error) {
	return r, nil
}
func (r *recorder) PutFlowMsg(ctx context.Context, category database.MsglogType, a, b string) (int64, error) {
	r.logAttempts++
	if err := ctx.Err(); err != nil {
		return 0, err
	}
	return 1, nil
}
func (r *recorder) UpdateFlowStatus(ctx context.Context, p database.UpdateFlowStatusParams) (database.Flow, error) {
	r.writeAttempts++
	if err := ctx.Err(); err != nil {
		return database.Flow{}, err
	}
	r.saved.Status = p.Status
	return r.saved, nil
}
func (r *recorder) GetFlowContainers(ctx context.Context, flowID int64) ([]database.Container, error) {
	return nil, ctx.Err()
}

func TestFailedPreparationUsesTheSuppliedExpiredContext(t *testing.T) {
	initial := database.Flow{ID: 1, UserID: 7, Status: "created"}
	recorder := &recorder{saved: initial}
	ctrl := &flowController{db: recorder, mlc: recorder, subs: recorder}
	expired, cancel := context.WithDeadline(context.Background(), time.Now().Add(-time.Second))
	defer cancel()
	if !errors.Is(expired.Err(), context.DeadlineExceeded) {
		t.Fatal("fixture context is live")
	}
	ctrl.failFlow(expired, initial, expired.Err())
	if recorder.logAttempts != 1 || recorder.writeAttempts != 1 || recorder.saved.Status != "created" || recorder.events != 0 {
		t.Fatalf("expired result %+v", recorder)
	}
	live, stop := context.WithTimeout(context.WithoutCancel(expired), time.Second)
	defer stop()
	ctrl.failFlow(live, initial, expired.Err())
	if recorder.logAttempts != 2 || recorder.writeAttempts != 2 || recorder.saved.Status != "failed" || recorder.events != 1 {
		t.Fatalf("live control %+v", recorder)
	}
}
PENTAGI_OFFLINE_FIXTURE
"$work/run" go test -json -race -count=20 -timeout=15s ./offline_start_failure

mkdir -p "$work/src/backend/offline_admission"
cat > "$work/src/backend/offline_admission/create.go" <<'PENTAGI_OFFLINE_FIXTURE'
package offline_admission

import (
	"context"
	"fmt"
)

func (fc *flowController) CreateFlow(
	ctx context.Context,
	userID int64,
	input string,
	prvname providerName,
	prvtype providerType,
	functions *functionsSpec,
	resources []resource,
) (int64, error) {
	fwc := newFlowWorkerCtx{
		userID:        userID,
		input:         input,
		prvname:       prvname,
		prvtype:       prvtype,
		functions:     functions,
		resources:     resources,
		flowWorkerCtx: fc.flowWorkerCtx(),
	}

	flow, err := reserveFlow(ctx, fwc)
	if err != nil {
		return 0, fmt.Errorf("failed to create flow: %w", err)
	}

	entry, _ := fc.reserveEntry(flow.ID)
	fc.subs.NewFlowPublisher(userID, flow.ID).FlowCreated(ctx, flow, nil)

	go fc.prepareFlow(ctx, entry, flow, func(c context.Context, commit func() error) (FlowWorker, error) {
		return fc.build(c, flow, fwc, commit)
	})

	return flow.ID, nil
}

type providerName string
type providerType string
type functionsSpec struct{}
type resource struct{}
type FlowWorker interface{}
type recordedFlow struct{ ID int64 }
type flowEntry struct{ id int64 }
type workerCtx struct{ inserted chan struct{} }
type newFlowWorkerCtx struct {
	userID        int64
	input         string
	prvname       providerName
	prvtype       providerType
	functions     *functionsSpec
	resources     []resource
	flowWorkerCtx workerCtx
}
type flowPublisher interface {
	FlowCreated(context.Context, recordedFlow, []resource)
}
type flowController struct {
	inserted chan struct{}
	started  chan struct{}
	subs     interface {
		NewFlowPublisher(int64, int64) flowPublisher
	}
	build func(context.Context, recordedFlow, newFlowWorkerCtx, func() error) (FlowWorker, error)
}

func (fc *flowController) flowWorkerCtx() workerCtx { return workerCtx{fc.inserted} }
func reserveFlow(ctx context.Context, args newFlowWorkerCtx) (recordedFlow, error) {
	if err := ctx.Err(); err != nil {
		return recordedFlow{}, err
	}
	close(args.flowWorkerCtx.inserted)
	return recordedFlow{ID: 71}, nil
}
func (fc *flowController) reserveEntry(id int64) (*flowEntry, bool) { return &flowEntry{id: id}, true }
func (fc *flowController) prepareFlow(ctx context.Context, entry *flowEntry, flow recordedFlow, build func(context.Context, func() error) (FlowWorker, error)) {
	close(fc.started)
}
PENTAGI_OFFLINE_FIXTURE
cat > "$work/src/backend/offline_admission/create_test.go" <<'PENTAGI_OFFLINE_FIXTURE'
package offline_admission

import (
	"context"
	"testing"
	"time"
)

type gatedPublisher struct{ entered, release chan struct{} }

func (p gatedPublisher) NewFlowPublisher(user, flow int64) flowPublisher { return p }
func (p gatedPublisher) FlowCreated(ctx context.Context, row recordedFlow, unused []resource) {
	close(p.entered)
	select {
	case <-p.release:
	case <-ctx.Done():
	}
}

type admission struct {
	id  int64
	err error
}

func read[T any](t *testing.T, ch <-chan T) T {
	t.Helper()
	select {
	case got := <-ch:
		return got
	case <-time.After(4 * time.Second):
		t.Fatal("no fixture signal")
	}
	var zero T
	return zero
}
func TestAnnouncementRunsBeforeWorkerAndResponse(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	p := gatedPublisher{make(chan struct{}), make(chan struct{})}
	fc := &flowController{inserted: make(chan struct{}), started: make(chan struct{}), subs: p}
	done := make(chan admission, 1)
	go func() { id, err := fc.CreateFlow(ctx, 1, "inert", "", "", nil, nil); done <- admission{id, err} }()
	read(t, fc.inserted)
	read(t, p.entered)
	select {
	case <-fc.started:
		t.Fatal("preparation started before the announcement returned")
	case result := <-done:
		t.Fatalf("admission returned during announcement: %+v", result)
	default:
	}
	close(p.release)
	got := read(t, done)
	read(t, fc.started)
	if got.id != 71 || got.err != nil {
		t.Fatalf("admission result %+v", got)
	}
}
PENTAGI_OFFLINE_FIXTURE
"$work/run" go test -json -race -count=20 -timeout=15s ./offline_admission
```

</details>

The terminal-check sensitivity control used the second scratch copy. Replacing `return !fw.finalized.Load()` with `return true` in its `offline_review_control/flow.go` made `go test -race -count=1 -run '^TestStatusSequentialFinalizationControl$' ./offline_review_control` fail at the state and publication assertion. The same command passed after restoring the copied method.

### PostgreSQL reproduction

The embedded test applies only the UP portion of the 37 migration files, in sorted filename order. It wraps each transactional migration in explicit `BEGIN` and `COMMIT`, and executes the three statements of the `NO TRANSACTION` migration separately. The source-derived SQL run uses the raw strings from generated `.sql.go` files. Run against an isolated database. All test identities and row contents are synthetic. [Migration filesystem test][migration-unit] · [Concurrent index migration][concurrent-index] · [Generated status][flow-status-sql] · [Generated queue delete][subtask-delete].

<details>
<summary>Exact embedded fixtures, generated query extraction and execution commands</summary>

```bash
pnpm_bundle=$HOME/.cache/node/corepack/v1/pnpm/11.13.0/dist/pnpm.mjs
{
    sed -n '2,21p;96770,97883p' "$pnpm_bundle"
    printf '\ninit_unpack();\nexport { unpack };\n'
} > "$work/decode.mjs"
sed '/--bind "\$scratch" \/work /i\    --ro-bind $HOME/.local/share/pnpm/store/v11/index.db /package-index.db --ro-bind $HOME/.local/share/pnpm/store/v11/files /package-files \\' \
    "$work/run" > "$work/run-pg-asset"
chmod +x "$work/run-pg-asset"
mkdir -p "$work/pg" "$work/src/backend/offline_sqlc"

cat > "$work/recover-generic.mjs" <<'PENTAGI_OFFLINE_FIXTURE'
import {DatabaseSync} from "node:sqlite";
import {unpack} from "./decode.mjs";
import {mkdirSync, readFileSync, writeFileSync} from "node:fs";
import {createHash} from "node:crypto";
import {dirname, resolve} from "node:path";
const db = new DatabaseSync("file:/package-index.db?immutable=1", {readOnly:true});
const [name, version, targetDirectory] = process.argv.slice(2);
const row = db.prepare("SELECT data FROM package_index WHERE key LIKE ?").get("%\t"+name+"@"+version);
if (!row) throw new Error("offline package index has no candidate");
const pkg = unpack(Buffer.from(row.data));
const root = "/work/pg/" + targetDirectory;
let total = 0;
for (const [name, entry] of Object.entries(pkg.files)) {
    const target = resolve(root, name);
    if (!target.startsWith(root + "/")) throw new Error("unexpected package path: " + name);
    const checksum = entry.digest;
    if (!/^[a-f0-9]{128}$/.test(checksum)) throw new Error("unexpected checksum for " + name);
    const hash = checksum;
    const content = readFileSync("/package-files/" + hash.slice(0,2) + "/" + hash.slice(2) + (entry.mode & 0o111 ? "-exec" : ""));
    const actual = createHash("sha512").update(content).digest("hex");
    if (hash !== actual || content.length !== entry.size) throw new Error("failed integrity for " + name);
    mkdirSync(dirname(target), {recursive:true});
    writeFileSync(target, content);
    total++;
}
console.log("Recovered", pkg.manifest.name, pkg.manifest.version, "files:", total);
PENTAGI_OFFLINE_FIXTURE
cat > "$work/pg-check.mjs" <<'PENTAGI_OFFLINE_FIXTURE'
import assert from "node:assert/strict";
import {readFileSync,readdirSync} from "node:fs";
import {PGlite} from "./pg/package/dist/index.js";
import {vector} from "./pg/package/dist/vector/index.js";
import {pg_trgm} from "./pg/package/dist/contrib/pg_trgm.js";
const root = "/work/src/backend";
const migrations = root + "/migrations/sql";
const db = await PGlite.create({extensions:{vector,pg_trgm}});
const one = async (txt, args = []) => (await db.query(txt,args)).rows[0];
const version = await one("select current_setting('server_version') as version");
console.log(new Date().toISOString(), "Embedded PostgreSQL", version.version);
try {
    const files = readdirSync(migrations).filter(x => x.endsWith(".sql")).sort();
    assert.equal(files.length,37);
    for (const file of files) {
        const src = readFileSync(migrations + "/" + file, "utf8");
        const up = src.split(/^-- \+goose Up\s*$/m)[1].split(/^-- \+goose Down\s*$/m)[0];
        try {
            if (src.includes("-- +goose NO TRANSACTION")) {
                for (const statement of up.split(";").map(s=>s.trim()).filter(Boolean)) {
                    await db.exec(statement + ";");
                }
            } else {
                await db.exec("BEGIN;\n" + up + "\nCOMMIT;");
            }
        } catch (error) {
            console.error("blocked at", file, error.code, error.message);
            throw error;
        }
        console.log("migration OK", file);
    }
    const extensions = (await db.query("select extname from pg_extension order by extname")).rows.map(x=>x.extname);
    assert.ok(extensions.includes("vector") && extensions.includes("pg_trgm"));
    console.log("extensions:",extensions.join(","));
    const query = (table, name) => {
        const generated = readFileSync(root + "/pkg/database/" + table + ".sql.go","utf8");
        const quote = String.fromCharCode(96);
        const header = quote + "-- name: " + name + " :";
        const start = generated.indexOf(header);
        if (start < 0) throw new Error("query not found: " + name);
        return generated.slice(start + 1, generated.indexOf(quote, start + 1));
    };
    const user = async (name) => (await one(
        "insert into users (hash, mail, name, status, role_id, type, provider) values ($1,$2,$3,'active',1,'local','local') returning id",
        ["offline fixture " + name,name+"@example.test",name]
    )).id;
    const Alice = await user("local-alice");
    const Bob = await user("local-bob");
    const createFlow = async () => (await one(query("flows","CreateFlow"),
        ["local fixture","created","mock-model","mock-provider","openai","English","fixture","{}",Alice]
    )).id;
    const readFlow = query("flows","GetFlow");
    const readUserFlow = query("flows","GetUserFlow");
    const statusFlow = query("flows","UpdateFlowStatus");
    const flow = await createFlow();
    assert.equal(await one(readUserFlow,[flow,Bob]),undefined);
    assert.equal((await one(readUserFlow,[flow,Alice])).status,"created");
    const recorded = ["running","finished","running"];
    for (const value of recorded) assert.equal((await one(statusFlow,[value,flow])).status,value);
    assert.equal((await one(readFlow,[flow])).status,"running");
    const predicate = statusFlow.replace("WHERE id = $2","WHERE id = $2 AND status NOT IN ('finished','failed')");
    await one(statusFlow,["finished",flow]);
    assert.equal(await one(predicate,["running",flow]),undefined);
    assert.equal((await one(readFlow,[flow])).status,"finished");
    console.log("exact row update sequence:",recorded.join(" -> "),"; terminal predicate negative control left finished");
    const invalid = await db.query("select status from flows where id=$1",[flow]);
    assert.equal(invalid.rows.length,1);
    await assert.rejects(one(statusFlow,["bad-status",flow]),{code:"22P02"});
    console.log("real status enum rejected unknown value, accepted the legal-value regression");
    const task = (await one(query("tasks","CreateTask"),["running","local task","inert text",flow])).id;
    const insertSub = query("subtasks","CreateSubtask");
    const removeSub = query("subtasks","DeleteSubtasks");
    const viewSub = query("subtasks","GetTaskPlannedSubtasks");
    const insert = (title, fire = "benign description") => one(insertSub,["created",title,fire,task]);
    const plan = async () => (await db.query(viewSub,[task])).rows.map(x=>x.title);
    const writeSubStatus = query("subtasks","UpdateSubtaskStatus");
    const a = await insert("old A");
    const b = await insert("old B");
    const w = await insert("old waiting");
    await one(writeSubStatus,["waiting",w.id]);
    await db.query(removeSub,[[a.id,b.id]]);
    await insert("new A");
    await assert.rejects(one(insertSub,["created",null,"invalid title fixture",task]),{code:"23502"});
    assert.deepEqual(await plan(),["old waiting","new A"]);
    console.log("autocommit replace with a fault retained only:",JSON.stringify(await plan()));
    const pre = await plan();
    const toDelete = (await db.query(viewSub,[task])).rows.filter(x=>x.status==="created").map(x=>x.id);
    await db.exec("BEGIN;");
    await db.query(removeSub,[toDelete]);
    await insert("new B");
    await assert.rejects(one(insertSub,["created",null,"invalid title fixture",task]),{code:"23502"});
    await db.exec("ROLLBACK;");
    assert.deepEqual(await plan(),pre);
    console.log("transaction control restored prior plan:",JSON.stringify(await plan()));
    const addChain = query("msgchains","CreateMsgChain");
    const updateChain = query("msgchains","UpdateMsgChain");
    const getChain = query("msgchains","GetMsgChain");
    const chain = (await one(addChain,["primary_agent","model","mock",0,0,0,0,0,0,0,"[]",flow,task,w.id])).id;
    const first = await one(updateChain,['[{"marker":"A"}]',1.25,"model","mock",chain]);
    assert.equal(first.chain[0].marker,"A");
    const second = await one(updateChain,['[{"marker":"B"}]',2.5,"model","mock",chain]);
    assert.equal(second.chain[0].marker,"B");
    assert.equal(Number((await one(getChain,[chain])).duration_seconds),3.75);
    console.log("whole-chain overwrite retained B, additive duration 3.75");
    const finishTask = query("tasks","UpdateTaskFinishedResult");
    const final = await one(finishTask,["synthetic completion",task]);
    assert.deepEqual([final.status,final.result],["finished","synthetic completion"]);
    const softDelete = query("flows","DeleteFlow");
    await one(softDelete,[flow]);
    assert.equal(await one(readFlow,[flow]),undefined);
    assert.equal(await one(readUserFlow,[flow,Alice]),undefined);
    assert.equal((await db.query(query("tasks","GetFlowTasks"),[flow])).rows.length,0);
    console.log("atomic terminal result and soft-delete read guards held");
} finally {
    await db.close();
}
PENTAGI_OFFLINE_FIXTURE
cat > "$work/pg-reopen.mjs" <<'PENTAGI_OFFLINE_FIXTURE'
import assert from "node:assert/strict";
import {readFileSync,readdirSync} from "node:fs";
import {PGlite} from "./pg/package/dist/index.js";
import {vector} from "./pg/package/dist/vector/index.js";
import {pg_trgm} from "./pg/package/dist/contrib/pg_trgm.js";
const root = "/work/src/backend";
const migrations = root + "/migrations/sql";
const mode=process.argv[2];
const db = await PGlite.create({dataDir:"/work/pg/pgdata",extensions:{vector,pg_trgm}});
const one = async (txt, args=[]) => (await db.query(txt,args)).rows[0];
try {
    const query = (table, name) => {
        const generated = readFileSync(root + "/pkg/database/" + table + ".sql.go","utf8");
        const quote = String.fromCharCode(96);
        const header = quote + "-- name: " + name + " :";
        const start = generated.indexOf(header);
        if (start < 0) throw new Error("query not found: " + name);
        return generated.slice(start + 1, generated.indexOf(quote, start + 1));
    };
    if (mode === "write") {
    const files = readdirSync(migrations).filter(x => x.endsWith(".sql")).sort();
    assert.equal(files.length,37);
    for (const file of files) {
        const src = readFileSync(migrations + "/" + file, "utf8");
        const up = src.split(/^-- \+goose Up\s*$/m)[1].split(/^-- \+goose Down\s*$/m)[0];
        try {
            if (src.includes("-- +goose NO TRANSACTION")) {
                for (const statement of up.split(";").map(s=>s.trim()).filter(Boolean)) {
                    await db.exec(statement + ";");
                }
            } else {
                await db.exec("BEGIN;\n" + up + "\nCOMMIT;");
            }
        } catch (error) {
            console.error("blocked at", file, error.code, error.message);
            throw error;
        }
        console.log("migration OK", file);
    }
    const user = async (name) => (await one(
        "insert into users (hash, mail, name, status, role_id, type, provider) values ($1,$2,$3,'active',1,'local','local') returning id",
        ["offline fixture " + name,name+"@example.test",name]
    )).id;
    const Alice = await user("local-alice");
    const Bob = await user("local-bob");
    const createFlow = async () => (await one(query("flows","CreateFlow"),
        ["local fixture","created","mock-model","mock-provider","openai","English","fixture","{}",Alice]
    )).id;
        for (const status of ["created","running","waiting","finished","failed"]) {
            const flow=await createFlow();
            await one(query("flows","UpdateFlowStatus"),[status,flow]);
            await one(query("tasks","CreateTask"),[status,"case " + status,"inert text",flow]);
        }
        console.log("committed five synthetic flow/task statuses");
    } else if (mode === "read") {
        const rows=(await db.query(query("flows","GetFlows"))).rows;
        assert.deepEqual(new Set(rows.map(row=>row.status)),new Set(["created","running","waiting","finished","failed"]));
        for (const row of rows) {
            const tasks=(await db.query(query("tasks","GetFlowTasks"),[row.id])).rows;
            assert.equal(tasks.length,1);
            assert.equal(tasks[0].status,row.status);
        }
        const triggers=(await db.query(
            "select tgname,pg_get_triggerdef(oid) as def from pg_trigger where tgrelid='flows'::regclass and not tgisinternal order by tgname"
        )).rows;
        assert.deepEqual(triggers.map(t=>t.tgname),["update_flows_modified"]);
        console.log("reopened all five statuses; GetFlows retains all non-deleted rows");
        console.log("explicit controller selection is required; triggers:", JSON.stringify(triggers));
    } else {
        throw new Error("expected write or read");
    }
} finally { await db.close(); }
PENTAGI_OFFLINE_FIXTURE
cat > "$work/pg-timeout.mjs" <<'PENTAGI_OFFLINE_FIXTURE'
import {PGlite} from "./pg/package/dist/index.js";
const db=await PGlite.create();
try {
    const result=await db.query("SHOW statement_timeout");
    console.log("default",result.rows[0].statement_timeout);
    await db.exec("SET statement_timeout = '100ms'");
    const set=await db.query("SHOW statement_timeout");
    console.log("after SET",set.rows[0].statement_timeout);
    const before=performance.now();
    try {
        await db.query("SELECT pg_sleep(0.6)");
        console.log("short sleep completed", (performance.now()-before).toFixed(1), "ms");
    } catch (err) {
        console.log("short sleep failed",err.code,err.message,(performance.now()-before).toFixed(1),"ms");
    }
} finally {await db.close();}
PENTAGI_OFFLINE_FIXTURE
cat > "$work/pg/wire.mjs" <<'PENTAGI_OFFLINE_FIXTURE'
import {PGlite} from "@electric-sql/pglite";
import {PGLiteSocketServer} from "@electric-sql/pglite-socket";
const db=await PGlite.create();
console.log("embedded self-check", (await db.query("SELECT version()")).rows[0].version);
const server = new PGLiteSocketServer({db,port:51432,host:"127.0.0.1",inspect:false,maxConnections:4});
await server.start();
console.log("ready");
const end=async()=>{await server.stop(); await db.close(); process.exit(0);};
process.once("SIGTERM",end);
process.once("SIGINT",end);
PENTAGI_OFFLINE_FIXTURE
cat > "$work/pg/wire-check.sh" <<'PENTAGI_OFFLINE_FIXTURE'
set -euo pipefail
node /work/pg/wire.mjs > /work/wire-server.log 2>&1 &
pg_pid=$!
trap 'kill "$pg_pid" 2>/dev/null || :; wait "$pg_pid" 2>/dev/null || :' EXIT
for ((n=0; n<50; n++)); do
    if grep -qx ready /work/wire-server.log; then break; fi
    kill -0 "$pg_pid"
    sleep 0.05
done
grep -qx ready /work/wire-server.log
ds='postgres://postgres@127.0.0.1:51432/postgres?sslmode=disable&connect_timeout=2'
timeout 5s psql -X -w "$ds" -c 'select current_database(), current_setting('"'statement_timeout'"');'
timeout 5s psql -X -w "${ds}&options=-c+statement_timeout%3D2000" -c 'show statement_timeout;' || :
TEST_DATABASE_URL="$ds" go test -json -race -count=1 -timeout=44s \
    pkg/database/statement_timeout.go pkg/database/statement_timeout_test.go
PENTAGI_OFFLINE_FIXTURE
cat > "$work/pg/sqlc-wire.mjs" <<'PENTAGI_OFFLINE_FIXTURE'
import assert from "node:assert/strict";
import {readFileSync,readdirSync} from "node:fs";
import {PGlite} from "./package/dist/index.js";
import {vector} from "./package/dist/vector/index.js";
import {pg_trgm} from "./package/dist/contrib/pg_trgm.js";
const root = "/work/src/backend";
const migrations = root + "/migrations/sql";
const db = await PGlite.create({extensions:{vector,pg_trgm}});
import {PGLiteSocketServer} from "@electric-sql/pglite-socket";
    const files = readdirSync(migrations).filter(x => x.endsWith(".sql")).sort();
    assert.equal(files.length,37);
    for (const file of files) {
        const src = readFileSync(migrations + "/" + file, "utf8");
        const up = src.split(/^-- \+goose Up\s*$/m)[1].split(/^-- \+goose Down\s*$/m)[0];
        try {
            if (src.includes("-- +goose NO TRANSACTION")) {
                for (const statement of up.split(";").map(s=>s.trim()).filter(Boolean)) {
                    await db.exec(statement + ";");
                }
            } else {
                await db.exec("BEGIN;\n" + up + "\nCOMMIT;");
            }
        } catch (error) {
            console.error("blocked at", file, error.code, error.message);
            throw error;
        }
        console.log("migration OK", file);
    }
await db.query("insert into users (hash,mail,name,status,role_id,type,provider) values ($1,$2,$3,'active',1,'local','local'),($4,$5,$6,'active',1,'local','local')",["synthetic-alice","local-alice@example.test","Alice","synthetic-bob","local-bob@example.test","Bob"]);
const server = new PGLiteSocketServer({db,port:51433,host:"127.0.0.1",inspect:false,maxConnections:4});
await server.start();
console.log("ready");
const end=async()=>{await server.stop(); await db.close(); process.exit(0);};
process.once("SIGTERM",end);
process.once("SIGINT",end);
PENTAGI_OFFLINE_FIXTURE
cat > "$work/pg/sqlc-wire.sh" <<'PENTAGI_OFFLINE_FIXTURE'
set -euo pipefail
node /work/pg/sqlc-wire.mjs > /work/sqlc-wire-server.log 2>&1 &
pg_pid=$!
trap 'kill "$pg_pid" 2>/dev/null || :; wait "$pg_pid" 2>/dev/null || :' EXIT
for ((n=0; n<200; n++)); do
    if grep -qsx ready /work/sqlc-wire-server.log; then break; fi
    kill -0 "$pg_pid"
    sleep 0.05
done
grep -qsx ready /work/sqlc-wire-server.log
ds='postgres://postgres@127.0.0.1:51433/postgres?sslmode=disable&connect_timeout=2'
OFFLINE_WIRE_DSN="$ds" go test -json -race -count=3 -timeout=40s ./offline_sqlc
PENTAGI_OFFLINE_FIXTURE
cat > "$work/pg/sqlc-fault.sh" <<'PENTAGI_OFFLINE_FIXTURE'
set -euo pipefail
node /work/pg/sqlc-wire.mjs > /work/sqlc-wire-server.log 2>&1 &
pg_pid=$!
trap 'kill "$pg_pid" 2>/dev/null || :; wait "$pg_pid" 2>/dev/null || :' EXIT
for ((n=0; n<200; n++)); do
    if grep -qsx ready /work/sqlc-wire-server.log; then break; fi
    kill -0 "$pg_pid"
    sleep 0.05
done
grep -qsx ready /work/sqlc-wire-server.log
ds='postgres://postgres@127.0.0.1:51433/postgres?sslmode=disable&connect_timeout=2'
timeout 10s psql -X -w -v VERBOSITY=verbose "$ds" -c "BEGIN" -c "SELECT 1/0" -c "ROLLBACK" -c "SELECT 42 AS after_rollback" || :
OFFLINE_WIRE_FAULT=1 OFFLINE_WIRE_DSN="$ds" go test -json -race -count=3 -timeout=40s ./offline_sqlc
PENTAGI_OFFLINE_FIXTURE
cat > "$work/src/backend/offline_sqlc/wire_test.go" <<'PENTAGI_OFFLINE_FIXTURE'
package database

import (
    "context"
    "database/sql"
    "errors"
    "os"
    "slices"
    "testing"
    "time"

    _ "github.com/lib/pq"
)

func TestGeneratedFlowTaskAndSubtaskQueries(t *testing.T) {
    ctx,cancel:=context.WithTimeout(context.Background(),10*time.Second)
    defer cancel()
    dsn:=os.Getenv("OFFLINE_WIRE_DSN")
    if dsn=="" { t.Fatal("isolated wire fixture DSN required") }
    db,err:=sql.Open("postgres",dsn)
    if err!=nil { t.Fatal(err) }
    defer db.Close()
    db.SetMaxOpenConns(1)
    q:=New(db)
    must:=func(err error){t.Helper();if err!=nil{t.Fatal(err)}}
    var owner,other int64
    must(db.QueryRowContext(ctx,"select id from users where mail = 'local-alice@example.test'").Scan(&owner))
    must(db.QueryRowContext(ctx,"select id from users where mail = 'local-bob@example.test'").Scan(&other))
    flow,err:=q.CreateFlow(ctx,CreateFlowParams{Title:"wire fixture",Status:"created",Model:"fixture",
        ModelProviderType:"openai",ModelProviderName:"example",Language:"English",Functions:[]byte("{}"),
        ToolCallIDTemplate:"inert",UserID:owner})
    must(err)
    if _,err:=q.GetUserFlow(ctx,GetUserFlowParams{ID:flow.ID,UserID:other}); !errors.Is(err,sql.ErrNoRows) {
        t.Fatalf("foreign fixture returned %v",err)
    }
    for _,status:=range []FlowStatus{"running","finished","running"} {
        row,err:=q.UpdateFlowStatus(ctx,UpdateFlowStatusParams{ID:flow.ID,Status:status})
        must(err)
        if row.Status!=status {t.Fatalf("requested %q, got %q",status,row.Status)}
    }
    task,err:=q.CreateTask(ctx,CreateTaskParams{Status:"created",Title:"wire fixture",Input:"inert",FlowID:flow.ID})
    must(err)
    add:=func(q *Queries,name string)(Subtask,error) {
        return q.CreateSubtask(ctx,CreateSubtaskParams{Status:"created",Title:name,Description:"inert",TaskID:task.ID})
    }
    older,err:=add(q,"original")
    must(err)
    _,err=db.ExecContext(ctx,"alter table subtasks add constraint offline_fixture_check check(title <> 'rejected')")
    must(err)
    defer db.ExecContext(context.Background(),"alter table subtasks drop constraint offline_fixture_check")
    tx,err:=db.BeginTx(ctx,nil)
    must(err)
    defer tx.Rollback()
    qt:=q.WithTx(tx)
    must(qt.DeleteSubtasks(ctx,[]int64{older.ID}))
    _,err=add(qt,"replacement")
    must(err)
    if os.Getenv("OFFLINE_WIRE_FAULT") == "1" {
        if _,err=add(qt,"rejected");err==nil{t.Fatal("fixture fault did not trigger")} else {t.Logf("injected constraint call returned %T %v",err,err)}
    }
    must(tx.Rollback())
    remaining,err:=q.GetTaskPlannedSubtasks(ctx,task.ID)
    must(err)
    ids:=[]int64{}
    for _,s:=range remaining{ ids=append(ids,s.ID) }
    if !slices.Equal(ids,[]int64{older.ID}) {t.Fatalf("rollback preserved %v, expected old %d",ids,older.ID)}
    closed,err:=q.UpdateTaskFinishedResult(ctx,UpdateTaskFinishedResultParams{ID:task.ID,Result:"synthetic completion"})
    must(err)
    if closed.Status!="finished" || closed.Result!="synthetic completion" {t.Fatalf("unexpected terminal row: %+v",closed)}
    _,err=q.DeleteFlow(ctx,flow.ID)
    must(err)
    if _,err=q.GetFlow(ctx,flow.ID); !errors.Is(err,sql.ErrNoRows){t.Fatalf("soft deletion yielded %v",err)}
    t.Log("generated methods exercised owner scope, overwritten terminal state, plan rollback, terminal result and soft deletion")
}
PENTAGI_OFFLINE_FIXTURE

"$work/run-pg-asset" node /work/recover-generic.mjs @electric-sql/pglite 0.4.1 package
"$work/run-pg-asset" node /work/recover-generic.mjs @electric-sql/pglite-socket 0.1.1 node_modules/@electric-sql/pglite-socket
ln -s ../../package "$work/pg/node_modules/@electric-sql/pglite"
"$work/run" node /work/pg-check.mjs
"$work/run" sh -c 'set -e; node /work/pg-reopen.mjs write; node /work/pg-reopen.mjs read'
"$work/run" node /work/pg-timeout.mjs
"$work/run" bash /work/pg/wire-check.sh    # expected failure in this embedded fixture
cp "$repo"/backend/pkg/database/{db.go,flows.sql.go,tasks.sql.go,subtasks.sql.go} "$work/src/backend/offline_sqlc/"
{
    printf 'package database\n\nimport ("database/sql"; "encoding/json"; "fmt")\n\n'
    sed -n '149,170p;422,451p;524,545p;569,590p;939,955p;1066,1087p' "$repo/backend/pkg/database/models.go"
} > "$work/src/backend/offline_sqlc/models.go"
"$work/run" bash /work/pg/sqlc-wire.sh
"$work/run" bash /work/pg/sqlc-fault.sh   # generates the wire comparison after a constraint failure
mkdir -p "$work/src/backend/offline_sqlc_pgx"
cp "$work/src/backend/offline_sqlc/"*.go "$work/src/backend/offline_sqlc_pgx/"
sed -i 's@github.com/lib/pq@github.com/jackc/pgx/v5/stdlib@; s/sql.Open("postgres",dsn)/sql.Open("pgx",dsn+"\&default_query_exec_mode=simple_protocol")/' \
    "$work/src/backend/offline_sqlc_pgx/wire_test.go"
sed 's|./offline_sqlc|./offline_sqlc_pgx|; s/^OFFLINE_WIRE_DSN=/OFFLINE_WIRE_FAULT=1 OFFLINE_WIRE_DSN=/' \
    "$work/pg/sqlc-wire.sh" > "$work/pg/sqlc-pgx.sh"
"$work/run" bash /work/pg/sqlc-pgx.sh

```

</details>

After assembling the isolated packages, the additional vet command used the same disk contents and offline runner.

```bash
"$work/run" go vet ./cmd/installer/files ./cmd/installer/wizard/window \
    ./migrations ./pkg/database/knowledge/limits ./pkg/password \
    ./pkg/observability/langfuse/api/internal ./pkg/observability/langfuse/api/client \
    ./pkg/resources ./pkg/timezone ./pkg/version \
    ./offline_review_control ./offline_observer ./offline_start_failure \
    ./offline_admission ./offline_sqlc ./offline_sqlc_pgx
```

### Result excerpts and source index

```text
2026-11-19T05:55:55.669818045Z  two full subscribers delayed healthy delivery by 10.00613007s
2026-11-19T05:55:55.671821657Z  same subscribers with space took 8.937 µs
2026-11-19T05:55:55.727011118Z  available slot with already-cancelled context: 111/200 acquired
2026-11-19T06:00:32.025Z        Embedded PostgreSQL 17.5
migration UP files applied      37/37
extensions                      pg_trgm, plpgsql, vector
generated row status            running -> finished -> running
plan after second insert fault  ["old waiting","new A"]
whole-chain replacement         B, duration 3.75
disk reopen                     all five states present
wire timeout test               expected an error, got nil (30.03s)
wire fault case                 lib/pq 3/3 unexpected ReadyForQuery, pgx 3/3 pass
terminal latch negative control mutated control failed, original control passed
direct embedded timeout probe   SHOW 100ms, sleep completed 602.1 ms
```

The embedded and isolated-Go reproduction packets ran independently from a second fresh archive. Expected passes and the intentionally injected failures repeated. The final Go packet, including admission and startup-failure controls, also executed from that archive. The source index contains 126 repository line anchors across 55 pinned files and one rubric anchor. Each cited source line was checked against the pinned Git object. Supporting controls came from the archive or the extracted spans above. The disk-backed wire read used a temporary `PGLite.create({dataDir: "/work/pg/pgdata"})` after the reopen script, then again with `extensions: {vector, pg_trgm}`. A local `psql` query for `select count(*) from flows` succeeded in both cases. The exact count includes rows committed by earlier local controls.

[rubric]: ./README.md:1
[test-guide]: repos/vxcontrol__pentagi/CLAUDE.md:118
[test-design]: repos/vxcontrol__pentagi/CLAUDE.md:138
[go-module]: repos/vxcontrol__pentagi/backend/go.mod:1
[ci-generate]: repos/vxcontrol__pentagi/.github/workflows/ci.yml:115
[ci-test]: repos/vxcontrol__pentagi/.github/workflows/ci.yml:138
[main-observe]: repos/vxcontrol__pentagi/backend/cmd/pentagi/main.go:85
[main-db]: repos/vxcontrol__pentagi/backend/cmd/pentagi/main.go:109
[main-wire]: repos/vxcontrol__pentagi/backend/cmd/pentagi/main.go:182
[main-shutdown]: repos/vxcontrol__pentagi/backend/cmd/pentagi/main.go:266
[gorm]: repos/vxcontrol__pentagi/backend/pkg/database/database.go:124
[get-flows]: repos/vxcontrol__pentagi/backend/pkg/database/flows.sql.go:155
[flow-status-sql]: repos/vxcontrol__pentagi/backend/pkg/database/flows.sql.go:527
[task-result-sql]: repos/vxcontrol__pentagi/backend/pkg/database/tasks.sql.go:251
[subtask-delete]: repos/vxcontrol__pentagi/backend/pkg/database/subtasks.sql.go:65
[chain-sql]: repos/vxcontrol__pentagi/backend/pkg/database/msgchains.sql.go:1211
[sqlc-tx]: repos/vxcontrol__pentagi/backend/pkg/database/db.go:27
[statement]: repos/vxcontrol__pentagi/backend/pkg/database/statement_timeout.go:10
[statement-live]: repos/vxcontrol__pentagi/backend/pkg/database/statement_timeout_test.go:63
[tenant-verify]: repos/vxcontrol__pentagi/backend/pkg/database/tenant.go:164
[migration-lock]: repos/vxcontrol__pentagi/backend/pkg/database/tenant.go:184
[schema]: repos/vxcontrol__pentagi/backend/migrations/sql/20241026_115120_initial_state.sql:109
[user-hash]: repos/vxcontrol__pentagi/backend/migrations/sql/20241026_115120_initial_state.sql:79
[assistant-schema]: repos/vxcontrol__pentagi/backend/migrations/sql/20250331_200137_assistant_mode.sql:114
[concurrent-index]: repos/vxcontrol__pentagi/backend/migrations/sql/20260722_120000_embedding_metadata_indexes.sql:1
[pg-live]: repos/vxcontrol__pentagi/backend/migrations/migrations_live_test.go:29
[migration-unit]: repos/vxcontrol__pentagi/backend/migrations/migrations_test.go:9
[planned-query]: repos/vxcontrol__pentagi/backend/sqlc/models/subtasks.sql:48
[subtask-author]: repos/vxcontrol__pentagi/backend/sqlc/models/subtasks.sql:125
[graphql-entry]: repos/vxcontrol__pentagi/backend/pkg/graph/schema.resolvers.go:35
[graphql-put]: repos/vxcontrol__pentagi/backend/pkg/graph/schema.resolvers.go:126
[graphql-sub]: repos/vxcontrol__pentagi/backend/pkg/graph/schema.resolvers.go:2687
[graphql-owner]: repos/vxcontrol__pentagi/backend/pkg/graph/context.go:107
[rest-entry]: repos/vxcontrol__pentagi/backend/pkg/server/services/flows.go:356
[rest-put]: repos/vxcontrol__pentagi/backend/pkg/server/services/flows.go:516
[rest-owner]: repos/vxcontrol__pentagi/backend/pkg/server/services/flows.go:430
[channel-defaults]: repos/vxcontrol__pentagi/backend/pkg/graph/subscriptions/controller.go:13
[channels]: repos/vxcontrol__pentagi/backend/pkg/graph/subscriptions/controller.go:378
[publisher]: repos/vxcontrol__pentagi/backend/pkg/graph/subscriptions/publisher.go:34
[abandoned]: repos/vxcontrol__pentagi/backend/pkg/controller/flows.go:22
[flow-entry]: repos/vxcontrol__pentagi/backend/pkg/controller/flows.go:87
[entry-available]: repos/vxcontrol__pentagi/backend/pkg/controller/flows.go:123
[registry]: repos/vxcontrol__pentagi/backend/pkg/controller/flows.go:127
[claim]: repos/vxcontrol__pentagi/backend/pkg/controller/flows.go:228
[load-flows]: repos/vxcontrol__pentagi/backend/pkg/controller/flows.go:253
[create-flow]: repos/vxcontrol__pentagi/backend/pkg/controller/flows.go:276
[prepare]: repos/vxcontrol__pentagi/backend/pkg/controller/flows.go:310
[fail-flow]: repos/vxcontrol__pentagi/backend/pkg/controller/flows.go:356
[create-assistant]: repos/vxcontrol__pentagi/backend/pkg/controller/flows.go:405
[assistant-parent]: repos/vxcontrol__pentagi/backend/pkg/controller/flows.go:460
[entry-commit]: repos/vxcontrol__pentagi/backend/pkg/controller/flows.go:600
[finish-controller]: repos/vxcontrol__pentagi/backend/pkg/controller/flows.go:673
[prep-tests]: repos/vxcontrol__pentagi/backend/pkg/controller/flows_test.go:349
[unrelated-flow-test]: repos/vxcontrol__pentagi/backend/pkg/controller/flows_test.go:716
[budget-test]: repos/vxcontrol__pentagi/backend/pkg/controller/flows_test.go:1240
[flow-fields]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:58
[flow-reserve]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:142
[flow-build-wire]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:246
[flow-launch]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:279
[flow-load]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:339
[flow-restore-wire]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:392
[flow-load-children]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:471
[flow-status]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:543
[add-assistant]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:604
[flow-put]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:680
[flow-finish]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:841
[flow-stop]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:877
[report-admission]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:945
[report-run]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:996
[provider-write]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:1177
[flow-join]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:1217
[task-completion]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:1259
[flow-restart]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:1307
[flow-process]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:1353
[flow-run]: repos/vxcontrol__pentagi/backend/pkg/controller/flow.go:1431
[finished-test]: repos/vxcontrol__pentagi/backend/pkg/controller/flow_test.go:377
[flow-context]: repos/vxcontrol__pentagi/backend/pkg/controller/context.go:20
[finish-unloaded]: repos/vxcontrol__pentagi/backend/pkg/controller/flow_finish.go:30
[finish-work]: repos/vxcontrol__pentagi/backend/pkg/controller/flow_finish.go:173
[assistant-build]: repos/vxcontrol__pentagi/backend/pkg/controller/assistant.go:276
[assistant-restart]: repos/vxcontrol__pentagi/backend/pkg/controller/assistant.go:476
[assistant-worker]: repos/vxcontrol__pentagi/backend/pkg/controller/assistant.go:517
[assistant-run]: repos/vxcontrol__pentagi/backend/pkg/controller/assistant.go:520
[assistant-put]: repos/vxcontrol__pentagi/backend/pkg/controller/assistant.go:637
[assistant-stop]: repos/vxcontrol__pentagi/backend/pkg/controller/assistant.go:696
[assistant-wait]: repos/vxcontrol__pentagi/backend/pkg/providers/assistant.go:494
[task-create]: repos/vxcontrol__pentagi/backend/pkg/controller/task.go:50
[task-load]: repos/vxcontrol__pentagi/backend/pkg/controller/task.go:157
[task-status]: repos/vxcontrol__pentagi/backend/pkg/controller/task.go:242
[task-run]: repos/vxcontrol__pentagi/backend/pkg/controller/task.go:341
[task-write]: repos/vxcontrol__pentagi/backend/pkg/controller/task.go:382
[task-interrupt]: repos/vxcontrol__pentagi/backend/pkg/controller/task.go:493
[task-order]: repos/vxcontrol__pentagi/backend/pkg/controller/tasks.go:83
[subtask-load]: repos/vxcontrol__pentagi/backend/pkg/controller/subtask.go:80
[subtask-status]: repos/vxcontrol__pentagi/backend/pkg/controller/subtask.go:187
[subtask-interrupt]: repos/vxcontrol__pentagi/backend/pkg/controller/subtask.go:355
[plan-patch]: repos/vxcontrol__pentagi/backend/pkg/controller/subtasks.go:129
[subtask-pop]: repos/vxcontrol__pentagi/backend/pkg/controller/subtasks.go:162
[reply]: repos/vxcontrol__pentagi/backend/pkg/controller/input_reply.go:11
[reply-test]: repos/vxcontrol__pentagi/backend/pkg/controller/input_reply_test.go:10
[reply-fixture]: repos/vxcontrol__pentagi/backend/pkg/controller/fixtures_test.go:26
[tclog]: repos/vxcontrol__pentagi/backend/pkg/controller/tclog.go:47
[stream-enqueue]: repos/vxcontrol__pentagi/backend/pkg/controller/aslog.go:232
[stream-chunks]: repos/vxcontrol__pentagi/backend/pkg/controller/aslog.go:313
[stream-save]: repos/vxcontrol__pentagi/backend/pkg/controller/aslog.go:373
[provider-interface]: repos/vxcontrol__pentagi/backend/pkg/providers/provider/provider.go:106
[fallback]: repos/vxcontrol__pentagi/backend/pkg/providers/provider/failover.go:37
[provider-registry]: repos/vxcontrol__pentagi/backend/pkg/providers/registry.go:22
[provider-resolve]: repos/vxcontrol__pentagi/backend/pkg/providers/providers.go:673
[provider-swap]: repos/vxcontrol__pentagi/backend/pkg/providers/provider.go:199
[flow-provider-contract]: repos/vxcontrol__pentagi/backend/pkg/providers/provider.go:77
[setup-retry]: repos/vxcontrol__pentagi/backend/pkg/providers/retry.go:74
[provider-call-errors]: repos/vxcontrol__pentagi/backend/pkg/providers/performer.go:551
[agent-iteration-guard]: repos/vxcontrol__pentagi/backend/pkg/providers/performer.go:116
[agent-checkpoint]: repos/vxcontrol__pentagi/backend/pkg/providers/performer.go:232
[chain-repair]: repos/vxcontrol__pentagi/backend/pkg/providers/helpers.go:311
[process-chain]: repos/vxcontrol__pentagi/backend/pkg/providers/helpers.go:634
[executor-interface]: repos/vxcontrol__pentagi/backend/pkg/tools/tools.go:194
[executor-release]: repos/vxcontrol__pentagi/backend/pkg/tools/tools.go:745
[runtime-prepare]: repos/vxcontrol__pentagi/backend/pkg/tools/tools.go:481
[custom-executor]: repos/vxcontrol__pentagi/backend/pkg/tools/tools.go:765
[tool-execute]: repos/vxcontrol__pentagi/backend/pkg/tools/executor.go:283
[docker-fixture]: repos/vxcontrol__pentagi/backend/pkg/docker/fixtures_test.go:20
[observer-init]: repos/vxcontrol__pentagi/backend/pkg/observability/obs.go:145
[observer-drain]: repos/vxcontrol__pentagi/backend/pkg/observability/obs.go:240

[tenant-docs]: repos/vxcontrol__pentagi/README.md:709
[completion-handler]: repos/vxcontrol__pentagi/backend/pkg/tools/flow_manager.go:556
