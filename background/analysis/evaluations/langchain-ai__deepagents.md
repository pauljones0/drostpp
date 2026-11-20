# Deep Agents architecture and reliability evaluation

## 1. Snapshot, scope, and elapsed-time evidence

Reviewed Deep Agents SDK **0.7.40** at **`a502bd69d0677c1ac4d6481622e840977decbf80`**. The checkout is shallow. Its pinned commit is a release-tooling dependency bump dated 2026-11-19 02:28:22 UTC. Findings concern the entire checked-out tree at that commit. The review centers on the Python SDK and follows the coding-agent server, ACP server, Talon runtime and the self-hosted async example where they change orchestration semantics. The terminal UI, provider response quality, hosted infrastructure and operational scalability are outside the evidence. [SDK manifest][sdk-manifest] · [Repository architecture][architecture]

**Assessment.** Deep Agents is a good fit when an application wants an extensible LangChain agent loop, focused child contexts, and LangGraph checkpoint and streaming interfaces. Its strongest reliability behavior lives in the boundaries where it keeps state narrow and defines recovery explicitly. Examples include stable message IDs, capability-aware file tools, and POSIX subprocess ownership. The most consequential weaknesses are at merge and commit boundaries. An inline child's completed state is forwarded as if it were a valid parent update. A remote run can be created before a parent task record exists, and competing tools can replace the same task record from stale snapshots. Local controls distinguish these behaviors from the much larger set of setup failures caused by missing locked dependencies. [Inline state return][inline-return] · [Remote launch][remote-launch] · [Task reducer][task-reducer] · [Subprocess cancellation][shell-cancel]

| UTC | Investigation milestone |
| --- | --- |
| 06:30:39 | Recorded start time, exact HEAD and empty porcelain status. Began rubric, manifest and graph assembly inspection. |
| 06:33:33 | Traced sync and remote delegation, package and cache provenance, and began fallback unit-test and integration-collection controls. |
| 06:35:20 | Isolated glob dependency and pytest-fixture effects under the read-only checkout and private network namespace. |
| 06:37:20 | Audited launch, cancellation and notification results, reviewed persisted task updates and runtime boundaries, and expanded dependency recovery. |
| 06:40:17 | Audited LangGraph replay and serialized checkpoint size, then traced Code, Talon, ACP and the example server. |
| 06:43:23 | Reviewed isolated SDK component and coverage results and confirmed the inline child-to-parent merge findings. |
| 06:47:18 | Completed the assembly-independent backend expansion and checked context recovery and archive append failures in both execution modes. |
| 06:49:21 | Re-ran the Code SQLite adapter and ownership tests against an isolated local fallback and began consolidating the measurement audit. |
| 06:52:11 | Verified the retry-classifier control and completed the first report-wide citation inventory. |
| 06:55:01 | Compared the installed fallback LangGraph source with the adjacent checkout and began replaying the report's embedded commands from a fresh staging directory. |
| 06:57:04 | Isolated the Talon retry boundary and audited Code's failed-restart fencing path. |
| 06:59:33 | Finished replaying the backend, Code, and Talon commands and confirmed the retry, state batching, and writer fencing observations. |
| 07:00:39 | Verified all 16 shell recipes parse. Confirmed the exact pinned HEAD, empty porcelain status including untracked and ignored entries, and successful worktree and index diff checks. |

The active investigation ran from **2026-11-19 06:30:39 UTC to 07:00:39 UTC**, an elapsed **30 minutes**. Both checkout checks returned `a502bd69d0677c1ac4d6481622e840977decbf80` and a clean worktree. Runtime experiments used a read-only mount of the checkout. The temporary staging directories were removed after the checks.

The rubric enumerates nine items and groups strengths and weaknesses in item 4. This report gives each of those its own section to match the requested ten-section structure and the preceding ten-section evaluations. The rubric's execution policy describes evaluation scheduling. No delegation was used. [Evaluation rubric][rubric] · [Preceding ten-section layout][layout-precedent]

## 2. Core architecture and end-to-end control/data flow

### Construction and the model loop

1. A caller passes a model object or a model specification, tools, optional middleware and subagents, a backend, and optional state, context, checkpoint and store settings. `resolve_model` passes a constructed `BaseChatModel` through and resolves a string through LangChain's `init_chat_model` with provider initialization defaults. The harness profile separately controls prompts, tool descriptions and exclusions, extra middleware and the general-purpose subagent. The default file backend is `StateBackend`. Falling back to the default Claude model for `model=None` is deprecated at this pin. [Model resolution][model-resolve] · [Profile resolution][harness-resolve] · [Assembly entry point][assembly-inputs] · [Model and backend defaults][assembly-defaults]
2. The factory divides declarative children, caller-compiled runnables and `graph_id` remote specs. Declarative children get a model and profile, file and summarization middleware, transcript repair, optional skills, and inherited or overridden tools and permissions. The general-purpose child is supplied automatically unless a profile disables it or an explicit inline child replaces it. Caller-compiled children carry their own graph and policy. [Subagent assembly][assembly-children] · [General-purpose defaults][assembly-gp] · [Compiled child contract][compiled-spec]
3. The main stack starts with filesystem, inline delegation when configured, parent notification, summarization and dangling-tool-call repair. Async delegation is installed only when a remote spec exists. New caller middleware goes after the core and before the tail, and same-name middleware replaces an existing slot. The tail can include model-profile middleware, skills and prompt caching, memory, human approval, content filtering and refusal handling. Tool exclusions run late and enforce the same exclusion at dispatch. The factory then calls LangChain `create_agent`, supplying the assembled capabilities and caller infrastructure, and binds recursion and integration metadata to the result. [Middleware merge][assembly-custom] · [Main stack order][assembly-main] · [Exclusion and dispatch][tool-exclusion] · [Compile and bind][assembly-compile]
4. A turn enters the compiled LangGraph with messages, optional state, and run context. LangChain's model/tool loop drives model calls and feeds results back until the model stops requesting tools or another state transition ends the turn. Middleware can contribute state and tools, transform requests, gate calls, and attach `Command` updates. LangGraph schedules nodes and tool work, applies reducers at graph boundaries, manages interrupts, persists when a checkpointer is configured, and streams intermediate events. The main graph's `recursion_limit=9_999` accommodates large runs. A caller still needs an application-level deadline, step/token budgets, and explicit policy for side effects. [Runtime layering][architecture] · [Assembly metadata and recursion bound][assembly-compile] · [Graph write ordering][lg-apply-writes] · [Harness end-to-end test][sdk-e2e]

**Planning is model-directed.** Agent descriptions, tool schemas, and prompts influence decomposition, tool choice and whether the model delegates. The lean factory no longer inserts `TodoListMiddleware` by default. Applications or profiles such as OpenAI Codex can add `write_todos`. That is model-maintained planning state. It does not schedule dependencies or independently enforce completion. The optional rubric middleware and the Code goal workflow provide evaluation and explicit goal transitions on top of the loop. The architecture note and the factory module docstring still use broader wording about default planning. [Planning removal][todo-change] · [Codex planning profile][codex-todo] · [Todo concurrency test][todo-test] · [Rubric middleware][rubric-mw] · [Code goal state and tools][code-goals]

### Inline delegation

The model calls `task(description, subagent_type)`. The tool validates its input and selects a configured child by name. Its runtime supplies authorization/context inputs and a tool-call ID independently of model-written arguments. An isolated invocation starts with a new human task message and eligible parent state. Built-in exclusions remove parent messages, todos, structured output, skill bookkeeping, rubric and detected private state. A declarative fork instead inherits much of the parent state and the effective transcript, dropping the current unanswered tool-call turn and folding any summary event into the copied history. Its task-specific instructions are appended to the task message so the shared prefix can match the parent's prompt. It retains a mirrored `task` schema for prompt-prefix compatibility and refuses further calls to that tool at runtime. A compiled fork gets effective conversation with the opaque runnable's own prompt and policy, and uses the stricter state filter. [Task schema][task-schema] · [Isolated/fork state preparation][inline-prepare] · [Fork transcript][fork-transcript] · [Fork recursion guard][inline-call] · [Fork assembly][assembly-fork] · [Compiled fork contract][compiled-spec]

The inline tool waits for the child within the parent tool execution. A recognized Pregel runnable is streamed for its final values and checkpoint events, letting the `ToolMessage.artifact` identify the namespace actually saved when checkpointing is active. An opaque runnable is invoked normally and can only get a fallback namespace. The result becomes a tool response addressed to the original tool-call ID. It uses structured response JSON when available, otherwise a refusal notice or the last nonempty assistant text. Other eligible changed keys are forwarded in the same `Command`. Model-facing prose is compact while clients can follow checkpoint or streaming metadata to inspect the child. The forwarded state can carry more than the final textual response. [Child stream/namespace handling][inline-stream] · [Inline return and tool identity][inline-return] · [Tracing context and metadata][inline-trace] · [Namespace regression tests][inline-ns-tests]

### Remote delegation

`start_async_task` creates a server thread, then creates a run on it. The remote thread ID becomes the parent-visible task ID. The run ID changes as the same child thread receives follow-ups. The tool stores the record in `async_tasks` through a `Command` after the two API operations. An isolated launch sends the description. Fork mode sends a snapshot of the effective parent conversation, strips nonportable tool artifacts and eviction tags, and rehydrates referenced media for transfer. Same-deployment runs can receive structured context and trace-parent linkage and use resumable streaming. Explicit-URL runs receive no runtime context and have separate server identity and credentials. A configured remote fork still sends its conversation payload to that server. [Remote spec and context][remote-spec] · [Remote serialization][remote-fork] · [Run options and trace headers][remote-options] · [Remote launch and state commit][remote-launch]

`check_async_task` looks up a run and, when necessary, its thread to distinguish completed work from a successful run record whose thread is interrupted for human input. `update_async_task` starts a new run on the same thread with interrupt or enqueue semantics. Queued work tracks earlier run IDs so that older results retain their provenance and cancellation can walk earlier active runs newest-first. `cancel_async_task` calls the server for active work and updates parent state, or locally marks a known waiting task cancelled. `list_async_tasks` filters on cached state before refreshing records. The server owns actual execution and checkpoint state, while the parent owns a projection of the task lifecycle. [Observe run and thread][remote-observe] · [Follow-up rules][remote-update] · [Cancellation][remote-cancel] · [List and refresh][remote-list]

The asynchronous parent can pull unfinished outcomes before agent/model work and once after a final model response, with a bounded per-observation wait. A newly observed result after a final response can route back to the model. A same-deployment child can push a notification by starting a run on an idle or errored parent thread, using the server's reject policy to avoid a competing active run. A paused parent normally learns the result during resumed activity. Notifications are rendered as labeled human-role messages with structured task metadata. Child text is escaped, some output blocks are clipped or dropped, and allowed media remains typed. The two paths support live progress and later reconciliation, with different behavior for standalone sync invocation. [Parent observation hooks][remote-pull] · [Wake policy][remote-wake] · [Notification rendering][remote-notification] · [Child notifier][parent-notifier]

### Context, storage, and resume

- `messages` and the filesystem `files` channel use batched delta reducers with a 50-update snapshot cadence. The message reducer uses stable IDs for replacement/removal and relies on LangGraph to assign IDs before persistence. `StateBackend` reads and writes through Pregel's task-local config and can see its own pending writes while a node is still running. The checkpointer and its retention policy determine whether these values survive runs or process restarts. An in-memory saver survives another call in the same process. A file-backed saver can reopen its database. The SDK takes a caller's checkpointer and supplies no durable saver by default. [Default message state][message-state] · [Message reducer][message-reducer] · [Files channel and tombstones][files-channel] · [State backend context][state-backend] · [Checkpointer contract][assembly-compile]
- A `StoreBackend` provides separately named cross-thread storage using a caller namespace and store. A `FilesystemBackend` or sandbox maps operations to external storage. `CompositeBackend` uses longest-prefix routing for file paths and dispatches shell execution to its default backend. Thread checkpoints, storage paths and remote run IDs are separate durability and ownership domains. Changing one can make pointers stored in another unavailable. Distinct route prefixes can refer to the same store namespace. [Namespace resolution][store-namespace] · [Composite routing][composite-route] · [Shell dispatch][composite-exec] · [Content-addressed payloads][blob-offload]
- The filesystem layer can retain a preview and a retrievable path for large outputs and user inputs. Binary state can use content references with a per-run untracked cache, and binary offload is disabled when its route would store the bytes in checkpointed state again. Summarization builds a reduced model-facing transcript from an event with a cutoff and summary; raw history can remain in checkpoint state. It can archive old turns, leave recent messages intact, trim old tool arguments and attempt one smaller recovery from a recognized context overflow. A stable cutoff message ID takes precedence over its old positional index. Older reasoning blocks whose signatures depended on the prior prefix are dropped for the compacted view. [Eviction and blob routing][fs-evict] · [Blob state][files-channel] · [Summary event and cutoffs][summary-view] · [Budget and overflow][summary-budget] · [Summary update][summary-call]
- Skills load and selectively disclose instructions and tools, with graph state preserving discovery metadata or a pinned skill selection. Memory sources load instructions in a stable order and can be given cache-control hints for Anthropic. These features add context through a request view or middleware-owned fields. They use the same backend abstraction, so graph-ephemeral state, host files and external stores have different lifetimes. [Skills lifecycle][skills-lifecycle] · [Skill tool disclosure][skills-tools] · [Memory lifecycle][memory-lifecycle] · [Prompt cache routing][cache-middleware]
- Human approval uses LangChain middleware over LangGraph interrupts, with caller `interrupt_on` entries taking precedence over generated file-approval predicates. To resume, use the same thread/checkpointer and `Command(resume=...)`. The interrupted node is entered again. A tool should guard or make idempotent an effect it performs before the interrupt. At a new agent entry, transcript repair can synthesize an error tool response for an unanswered call. This fixes message pairing and leaves the real effect's outcome for the caller or a separate reconciliation path. [Approval composition][hitl-merge] · [Filesystem approval generation][fs-interrupt] · [Graph interrupt semantics][lg-interrupt] · [Transcript repair][patch-tool-calls]

## 3. Why the design works and its governing invariants

| Invariant | How the pin implements it and where it matters |
| --- | --- |
| A turn has a common runtime and state vocabulary | Model decisions, tool outputs and approval resume all use the LangChain graph contract, while LangGraph manages execution and checkpointing. Middleware can evolve without a second scheduler. The downstream contracts for reducers, tool runtime, command targets and saver history are operational dependencies. [Compile path][assembly-compile] · [State backend internals][state-backend] · [LangGraph delta contract][lg-delta] |
| Raw history and model input can evolve independently | Stable IDs permit replay and in-place replacement while summary events, clipping, media handling and prompt overlays limit what is sent each turn. Tool response IDs preserve model call/result pairing. Artifact paths and offloaded bytes require their own lifetime. [Message reducer][message-reducer] · [Effective messages][summary-view] · [Tail clipping][overflow-clip] · [Eviction markers][fs-evict] |
| Child visibility and output size are explicit | A separate child prompt and tools keep the parent's context smaller, and a fork deliberately trades that separation for prefix reuse. Structured results and checkpoint artifacts let clients consume a compact result with a diagnosis path. Client context and shared storage require separate scoping decisions. [Child state preparation][inline-prepare] · [Result contract][inline-return] · [Fork mode and output shapes][compiled-spec] |
| A graph reducer receives updates that mean what its schema says | LangGraph folds writes deterministically and a delta reducer must be deterministic and batching-invariant. The SDK's message/file reducers define replacement and tombstones. Tool results must encode valid operations for each parent channel. Section 5 identifies where the SDK forwards snapshots that violate that expectation. [Message reducer][message-reducer] · [File delta and tombstones][files-channel] · [Write ordering][lg-apply-writes] · [Inline state return][inline-return] |
| Capability tests, visibility, execution and authorization are distinct | Tool schemas describe valid calls, request-time filters keep backend/provider-unsupported capabilities out of the model prompt, and file/approval checks govern tool execution. SDK tools and permission rules do not turn a caller-supplied shell, compiled child, or custom tool into a sandbox. [File-tool assembly][fs-visibility] · [Tool exclusion][tool-exclusion] · [Permissions at dispatch][fs-permission] · [Shell contract][local-shell] |
| Scope is explicit at each durability boundary | LangGraph thread IDs scope checkpointer state. Store namespaces scope cross-thread files. Run IDs identify remote attempts within a task thread. A single process managing a SQL journal is another ownership domain. An acknowledgement in one domain does not make effects elsewhere atomic. [State backend][state-backend] · [Store namespace][store-namespace] · [Task record shape][task-state] · [Code writer lease][code-thread-guard] |
| Recovery must change a request or recognize its previous effects | Compaction avoids resending a known oversized or unreduced request. LangGraph can replay a task from its start, so replay-safe state and idempotent side effects are distinct obligations. Backend results, model refusals, and approval pauses intentionally have different representations. [Overflow guard][summary-budget] · [Interrupt replay][lg-interrupt] · [Inline refusal handling][inline-call] |

## 4. What it does well, with source evidence

- **Uses an established graph runtime.** Even relatively complex capabilities are implemented by composing typed middleware, tools, channels and stores around a familiar graph. Callers can pass a custom model or graph and choose storage independently. This keeps the core execution mechanism small enough to reason about and lets consumers use compiled graphs, native checkpoint tooling and stream event formats. [Public compile path][assembly-compile] · [Inline compiled path][compiled-spec] · [Extension methods][sdk-middleware]
- **Makes useful distinctions between delegation modes.** Inline execution is useful for work whose result is needed in the current turn. Remote execution supports follow-ups and human involvement on its own thread. Forks have deliberate history selection, portable media handling and cache-aware prefix layout. The tests name tricky cases such as a queued child pausing, resumed work discovered by the parent, and provider payload parity. [Fork history and recursion][fork-transcript] · [Async fork serialization][remote-fork] · [Queued run tests][remote-queued-tests] · [Fork payload tests][fork-payload-tests]
- **Defines concrete transcript and context recovery.** Tool-call repair marks errors rather than silently inventing success, backend results retain their IDs through eviction, and budget recovery requires a smaller request. Storage offload and provider-specific content filtering let checkpoints preserve more context than a given call can fit. [Transcript repair][patch-tool-calls] · [Budget recovery][summary-budget] · [Eviction][fs-evict] · [Unsupported content][unsupported-content] · [Compaction tests][compaction-tests]
- **Has concrete resource-management code in the file and shell paths.** POSIX execution owns a process group, bounds drain/reap work, and coordinates cancellation around the executor start race. Shell output surviving timeout is useful operational evidence. Sandbox timeouts, bounded sync glob worker admission and native async transport where available address common stuck-worker paths. The credential-free tests exercised real subprocess communication and cancellation on Linux, with fake native Windows handle tests covering a portion of the alternate reader. [Process cleanup][shell-cleanup] · [Cancellation handshake][shell-cancel] · [Timeout response][shell-execute] · [Glob worker ownership][fs-workers] · [Sandbox timeout test][sandbox-timeout-test] · [Windows reader tests][windows-tests]
- **Deals thoughtfully with expected provider, storage and deployment differences.** Runtime type/shape checks and narrow conversion helpers make provider and backend errors discoverable. Profile materialization allows fresh middleware instances, and profile bootstrap coordinates concurrent loads. Context Hub's mutation queue overlays accepted edits, groups bursts, uses parent-commit preconditions, and replays bounded conflicts from an authoritative tree. This is a useful existing design model for task reconciliation. [Profile factories][harness-factories] · [Bootstrap synchronization][profile-bootstrap] · [Context Hub queue][context-hub-queue] · [Context Hub conflict handling][context-hub-conflict]

## 5. What it does poorly, with source evidence

### P1. Inline child snapshots are applied as parent deltas

The return path removes excluded and unchanged keys, but forwards the complete resulting value for every remaining key. The input and output can each satisfy their graph schemas while the transfer between the two violates the parent's reducer contract. The unchanged check prevents a pure read child from rebroadcasting a value. It cannot derive the operation that changed it. This affects ordinary SDK state as well as application-defined channels. [Unchanged-value check][inline-unchanged] · [Input inheritance][inline-prepare] · [Return update][inline-return] · [File delta reducer][files-channel]

| Isolated real-graph control | Expected operation | Observed in sync and async |
| --- | --- | --- |
| Child inherits an additive counter of 10 and contributes 0 | Parent stays 10 | 10. The unchanged check worked. |
| One compiled child contributes +1 | Parent becomes 11 | 21. Parent applied the child's materialized 11 as a delta. |
| Two children each contribute +1 from the same input | Parent becomes 12 | 32. Both materialized child values were added. |
| Children edit separate existing files | Both replacements survive | One survived. The other child's snapshot still carried the original value and replaced the edit. |
| A child deletes an inherited file | Parent gets a deletion marker | Child reads the file as absent. Parent still has it because the completed child map has no tombstone. |

The control used the real SDK `task` tool builder and file reducer, actual compiled StateGraphs, the local ToolNode and an in-memory checkpointer. It confirmed isolation of the task transcript and excluded private field, runtime context propagation, and nonempty child namespace artifacts in the same run. A single-child edit and a two-child same-step edit on distinct files within the **same** graph passed. The harmful case crossed the child-to-parent merge boundary. The default graph assembly passes a custom state schema to declarative children when supplied, and the default filesystem middleware gives declarative children the same kind of file channel, so the mechanism applies beyond this compiled-child test. That broader path is source-supported and was unavailable through the normal SDK entry point here. [State channel assembly][assembly-children] · [Subagent compilation][inline-compile] · [Separate child graph execution][inline-stream] · [Related upstream integration xfail][extended-xfail]

The same reducer also makes two edits to the **same** file last-write-wins when the actions run in one graph superstep. A focused store control showed the equivalent problem for `StoreBackend.edit`, where the underlying get/modify/put lacks a compare-and-swap. This is distinct from the inline snapshot regression because two separate files composed correctly when each yielded a one-key update. [State edit][state-edit] · [Store edit][store-edit] · [LangGraph local read][lg-local-read]

### P1. Remote launch crosses a durable boundary with no recovery key

The launch tool creates a thread and run before returning the parent update. A failure after thread creation leaves a thread with no parent task pointer. A server that starts a run and loses the response leaves active work whose ID the parent never recorded. A retry of the same logical request creates a fresh thread. In a deterministic fake-server test with the same tool-call ID, a pre-commit run failure left two threads and one run after retry. A post-commit response loss left two threads and two runs, with only the second tracked. Success without injection created one of each. The code passes parent metadata that a higher-level service could search, while this tool supplies no stable launch identity, recovery lookup, cleanup or persisted intent. The evidence is about the SDK request/record order. A production server may add its own deduplication under a separate contract. [Launch transaction boundary][remote-launch] · [Thread metadata][remote-options]

### P1. Concurrent tools can overwrite newer task state with older observations

`async_tasks` merges complete records with a shallow map update. A status check observes a snapshot and returns a full replacement record. The cancel tool also returns a full replacement. The two can run in the same model message. With a handshake that guaranteed a check captured `running` before a cancellation succeeded, the order `[cancel, check]` left the parent's `running` record while the mock server had already interrupted the run. Reversed order left `cancelled`. Both results reproduced on sync and async ToolNode paths. A synchronous state fold with the same outputs gives the same result. Timing only determines which remote snapshot the check saw. A parallel-update guard exists for multiple enqueue follow-ups from the same AI turn. It does not coordinate a check, list, cancel or interrupting update with each other. [Shallow task reducer][task-reducer] · [Check result update][remote-check-write] · [Cancel result update][remote-cancel] · [Enqueue-only guard][remote-update-guard] · [List writes][remote-list]

Run reconciliation has related identity gaps. When an interruption's original run has status `success` and the user resumes it to completion elsewhere between polls, a subsequently idle thread can expose the new result while a check still reports the old run ID. The observer searches for the latest run when the thread is busy or errored, and follows a non-cancelled interrupted run, so those paths provide working controls. The notification hook ignores known superseded queued runs, but accepts a different run ID whenever the tracked record is unfinished. The isolated hook accepted an older success for `r1` over `r2` when the earlier run was missing from that list. The production likelihood depends on delivery order and the server's interrupt guarantees. The demonstration establishes how the receiver resolves that ordering if it occurs. The list tool's `success` filter also omitted a remotely completed task whose cached status was `running`, although the unfiltered call refreshed it to success. That reflects filter-before-refresh semantics, with sync callers and status transitions between pulls most exposed. [Run/thread observation][remote-observe] · [Notification reduction][remote-record] · [Filter and refresh][remote-list]

### P1. A failed archive read can overwrite recoverable context

Both offload paths start with empty previous content. A download error result or thrown exception leaves that value empty. The method then takes the new-file `write` path, which can overwrite an existing archive on a backend where the write succeeds. In a local filesystem fixture with a pre-existing first marker, a normal second offload preserved both markers. Injecting a one-time read `OSError` or an error-valued `permission_denied` yielded the same successful path with only the second marker. Both sync and async exhibited it. The result establishes loss of the archive's older section. A separate graph checkpoint may still hold original messages. Attempts to write a truly missing archive are valid and should keep working. [Sync read/append/write][summary-offload] · [Async append][summary-offload-async] · [Filesystem write][fs-backend-write]

The smaller context view also needs coordinated migration with raw message updates. Keeping the cutoff message lets the summarizer relocate it after earlier messages are removed. Removing the cutoff itself reverts to the saved numeric index. In a fixture where two raw tail messages remained and the index exceeded their count, the effective request contained only the summary. This is an extension or migration edge, because ordinary summarization keeps the raw messages. Document which transcript edits must reset or atomically rebase the summary event. [Stable ID fallback and projection][summary-view]

### P2. Integration guarantees depend on the server and backend behind the interface

- The self-hosted example marks cancellation in SQL, leaving the actual asyncio task running. Its worker can later record `success`. The in-process ASGI control observed the complete `running → cancelled → success` transition. The example also passes only the first human message to the agent. A fork-shaped payload delivered the old first human turn and discarded the intended new task. The example's eight original tests pass with a mock model, including a cancellation test that checks only persisted status. These findings apply to the example server. They do not establish the behavior of Agent Server. [Example worker and final commit][example-execute] · [Example task dispatch][example-dispatch] · [Example cancellation endpoint][example-cancel] · [Example tests][example-tests]
- Talon's runtime can retry the entire graph with its original input after a downstream transient fault. In the control, the input message had already been committed and the predecessor node had finished. Replaying the same idless payload produced two user messages and re-entered both nodes. A stable input ID removed the duplicate message while the predecessor still ran twice. Invoking with `None` on the same failed graph thread re-entered only the pending node and kept one user message. This is a focused runtime-layer result after a committed partial attempt. It does not establish that every Talon provider failure reaches that point. [Talon input payload][talon-invoke] · [Whole-graph retry loop][talon-retry] · [Message ID contract][message-reducer]
- A composite prefix controls routing, while the backing store and namespace control data ownership. The repository's expected failures configure separate `StoreBackend` objects over the same store and same namespace. The route test observed the file from both routes. Separate namespaces on the same store eliminated the cross-route alias. The failure is a misleading default assumption about routing and data separation. The backend intentionally lets callers set and share namespaces. [Store namespace contract][store-namespace] · [Composite path handling][composite-route] · [Sync expected failure][composite-xfail-sync] · [Async expected failure][composite-xfail]
- The parent notifier is best-effort and process-local. Marking a run reported before awaiting delivery provides local suppression, with a bounded 1,000-entry map. An exception in client construction can bypass the wake method's catch block. A fake client raising during dispatch was swallowed as intended. An identical probe raising during `get_client()` escaped. Client lifecycle also warrants a clearer contract. The async middleware makes one cache for observation hooks and another for its tools, with no close method in that class. By contrast the LangSmith sandbox adapter explicitly associates its async client with an event loop and has `aclose`. Pool leaks and reuse across event loops were not measured. [Parent notification bookkeeping][parent-notifier] · [Wake and client cache][remote-wake] · [Separate tool cache][remote-tool-factory] · [Sandbox async client ownership][sandbox-client]
- The documented asymptotic storage claim for the main message channel needs a qualification. A fixed interval of 50 updates gives bounded replay depth and saves substantial serialization, but keeping all full snapshots of an indefinitely growing transcript still gives a quadratic snapshot contribution. In the isolated append-only control, 800 messages yielded about 3.05 MB of message snapshots and pending writes under the default cadence versus 129.13 MB when storing the full message value for each step. Raising the snapshot interval beyond the test length removed snapshots entirely and left only 0.32 MB of pending writes. Real retention settings, channels, serializers and workload mix change these figures. The measured benefit is large. A fixed-cadence delta log by itself is not an unbounded linear-storage guarantee. [Message channel comment][message-state] · [LangGraph snapshot cadence][lg-snapshot] · [Saver blob and write persistence][lg-saver]

## 6. Core-code quality: decomposition, state, concurrency, errors, types, tests, observability, extensibility, and maintainability

| Area | Evaluation |
| --- | --- |
| Decomposition | Strong subsystem boundaries between factory, middleware, storage adapters and runtime. Internal complexity concentrates in the long factory and workflow-heavy middleware. At this pin `graph.py` is 1,046 lines, `filesystem.py` 4,000, `summarization.py` 2,472, `async_subagents.py` 1,771 and `subagents.py` 1,177. Order-sensitive helper calls encode policy across multiple inline stacks. The factory builds a task tool and recompiles the child set when it fills private state keys through the setter, even for unchanged keys. Static module count is a maintenance indicator. It does not establish runtime latency. [Graph factory][assembly-inputs] · [Middleware merge and private keys][assembly-compile] · [Child tool rebuild][inline-private-rebuild] |
| State | Typed schemas and pure delta reducers make routine updates explicable. They rely on operation shape, IDs and matching channel contracts. Root and child schema composition can diverge, including the child path which forwards a custom state schema only if supplied. Reflection through `get_type_hints` detects `PrivateStateAttr` but skips an entire schema when an annotation cannot resolve. The method logs the issue and the skipped names can then be forwarded to isolated/compiled children as eligible state. Explicit isolation and reducers deserve first-class schema validation and typed transfer contracts. [Private state reflection][private-state] · [Inline state handling][inline-prepare] · [Child compilation][inline-compile] |
| Concurrency | Pregel node/task isolation and deterministic folds make useful parallelism possible, and async tool calls can progress while peers await I/O. Node-local fresh reads are scoped to one task's pending writes. Shared backends and same-record state updates still need concurrency semantics. The strongest explicit implementations are subprocess ownership, Context Hub conflict handling and the Code thread lease. Remote tool hooks create all observation coroutines at once, with a per-operation timeout for automatic pull. It provides a deadline for a cooperative wait and no concurrency cap for a large task set. The explicit list tool has a separate all-at-once gather and uses SDK/transport defaults. [Local read semantics][lg-local-read] · [Remote gather/timeout][remote-pull] · [List tool gather][remote-list] · [Context Hub conflict][context-hub-conflict] · [Code writer guard][code-thread-guard] |
| Errors and cancellation | Exceptions, model refusals, unfulfilled tool calls and backend result errors are distinguished in several strong paths. The remote operation surface uses several broad catches that return ad hoc strings, while notification output carries typed IDs and a status. The coding-agent build adds a richer retry policy for transient model faults, classified provider status, bounded delay and stream-attempt correlation. Graph control-flow exceptions propagate through it. SDK compaction serves a different purpose and has its own smaller-request gate. Native async cancellation support varies by backend. The local shell implementation documents weaker Windows descendant cleanup and synchronous extension fallback. [Refusals and normal tool return][inline-call] · [Remote error return][remote-launch] · [Code retry classification][code-retry-classify] · [Code loop and streamed attempts][code-retry-loop] · [Shell cancellation][shell-cancel] · [Shell timeout results][shell-execute] |
| Types and extension seams | Public structures use TypedDict, Pydantic schemas, generic middleware and backend results. The runtime overloads support caller context and structured responses. Compatibility with genuinely opaque runnable/adaptor code necessarily uses `Any`, filters and duck typing. The strongest extensions have narrow, public contracts. Examples include declared backend capabilities, named profile entries, and tool schemas. The weakest require private framework symbols, reflective method discovery, a structural state comparison, or caller-owned middleware instances with implicit sharing. [SDK API exports][sdk-exports] · [Backend capability protocols][backend-protocol] · [Tool schema][task-schema] · [Exclusion rules][profile-exclusions] · [Adapter patch][code-adapter] |
| Tests | Good coverage diversity in source. Scripted fake model turns, wire payload capture, native file tests, expected backend incompatibilities, streaming/namespace, compaction, async server fakes and retry fixtures address important contracts. The normal SDK tests remained unavailable without locked local dependencies. The offline components cover a useful storage and host-resource slice. Target gaps are operation-order permutations for remote mutations and observable transfer of concurrent child state changes with a nonzero baseline. [Normal test route][sdk-makefile] · [Scripted SDK tests][sdk-e2e] · [Async task test coverage][remote-queued-tests] · [Compaction fixtures][compaction-tests] |
| Observability | The graph binds integration metadata, subagents stamp the calling tool ID, and saved child namespaces let clients recover a diagnostic view. Request hooks commonly suppress trace input payloads by default. Async subagent results carry source and attribution and Code emits retry/attempt events. Local debug/warning logs remain useful for failures, but response strings, trace metadata, checkpoint state and tool artifacts are separate surfaces. Queue latency, orphan reconciliation and comparable terminal status need durable metrics with a shared operation ID. [Root metadata][assembly-compile] · [Inline tracing][inline-trace] · [Trace input policy][fs-trace] · [Task metadata][remote-notification] · [Retry event envelope][code-retry-event] |
| Dependency and maintainability | The library manifest names LangChain and LangChain Core and gets LangGraph transitively through LangChain, while the SDK imports LangGraph and LangGraph SDK directly. The lock makes concrete versions visible, but a package install without it must satisfy implicit interfaces on channel replay, runtime config, checkpointers, SDK behavior and provider adapters. Code's delta-history monkeypatch is evidence of the operational impact of an upstream private seam. Publish a dependency compatibility matrix and test against the minimum and current supported pins. [Dependency declaration][sdk-manifest] · [Locked LangChain and LangGraph versions][locked-lc] · [Direct graph imports][message-state] · [Agent Protocol client code][remote-wake] · [Code saver adapter][code-adapter] |

### Runtime consumers

- **Code** builds on the SDK with model retry, resume state, goal tools and additional orchestration middleware. Its session journal uses an owned SQLite saver. A client process holds a thread reservation, the saver verifies its fencing token before mutations, and the async mutation gate lets a transaction finish under cancellation before releasing ownership. The local event source manages a Unix socket with ownership and shutdown logic. The delta-history adapter makes the private dev-server wrapper use the inner saver fast path when it actually implements one. The SDK alone has none of this specific local journaling policy. [Code graph assembly][code-assembly] · [Code resume channels][code-resume] · [Code writer guard][code-thread-guard] · [Code session saver][code-session-saver] · [Code event bus][code-event] · [Saver forwarding][code-adapter]
- **Talon** supplies a long-lived async host, request-level recovery and optional local background children with in-memory task handles. Its runtime wraps graph invocation with separate retry and approval handling and opens configured local or pluggable checkpoint implementations. The conversation archive saver forwards the graph saver contract and projects committed messages into a second persistence domain with retry/idempotency logic. The store and archive tests here exercised temporary SQLite and in-memory stores. They did not demonstrate restart of actual in-process child workers. [Talon graph construction][talon-assembly] · [Invocation and approval][talon-invoke] · [Background job lifecycle][talon-background] · [Checkpoint resource opening][talon-checkpointer] · [Archive saver][talon-archive]
- **ACP** maps session IDs to graph thread configs, reads checkpoint state to load a conversation and projects streaming updates and approvals onto the protocol. Its server requires an appropriately persistent checkpointer for session loading across restarts. It uses a memory saver fallback during prompt execution when the caller provided none. Before checking persistence for an approval, the server leaves the graph stream. A cancellation request sets a session flag polled at stream/turn boundaries. A long gap without stream updates can delay that check. ACP was inspected at source level only. [ACP session restore][acp-restore] · [ACP stream and approval loop][acp-prompt] · [ACP cancellation signal][acp-cancel]

## 7. Executed tests/experiments and their limitations

### Test matrix

| Run | Observed result | What the result supports |
| --- | --- | --- |
| Frozen SDK setup, offline. Then unmodified SDK unit and integration collection with locally available dependencies | Frozen install failed on unavailable locked dependencies. Unit collection stopped in the root unit conftest with missing `langchain`. Integration-only collection reported six module import errors and zero collected tests, including missing `langchain_tests`. | The normal SDK test route could not be run in this offline environment. Provider model, LangChain composition, and most full-graph regression tests remain unexecuted. [SDK test setup][sdk-makefile] · [Unit conftest][unit-conftest] · [Provider tests][integration-model] |
| SDK components, first Python 3.12 run with old `wcmatch` and incomplete fixture restoration | **641 passed, 152 failed, 8 skipped, 1 xfailed**. | Initial diagnosis only. Version, package-parent attributes, fixture reset and effective identity differed from the reference environment. |
| Same 15 SDK test files with the original API fallback, correct fixture/namespace setup and unprivileged Linux inside Bubblewrap | **650 passed, 148 failed, 3 skipped, 1 xfailed**. | Remaining failures were correlated with the missing `wcglob.compile` API. |
| The same 15 files with a narrow `wcmatch` adapter | **798 passed, 3 skipped, 1 xfailed**. | The same 148 cases switched to pass. The old matcher API adapter is a control for those failures. |
| Expanded SDK isolated components with version, video, and mocked Context Hub/LangSmith sandbox tests, strict warnings with an explicit known warning exception, and Python tracing for coverage | **991 passed, 2 skipped, 1 xfailed** in **52.18 s**. Coverage reported **26%** for the SDK source tree, including 98% of local shell, 93% of BaseSandbox, 95% of Context Hub, 79% of the message reducer, 75% of StateBackend, and 60% of StoreBackend. `graph.py` and the core middleware assembly modules were at 0% in this run. | Native local filesystem/shell work, sandbox shaping, dependency and optional media behavior, component contracts and mock transport logic. The pytest count and coverage describe an altered test environment using a namespace bypass and dependency adapter. [POSIX tests][shell-tests] · [Message reducer tests][message-tests] · [Context Hub tests][context-hub-tests] |
| Second, disjoint SDK backend set, with the repository file reducer and a minimal `FilesystemState` base | **421 passed, 7 deselected, 1 xfailed** in **1.82 s**. | Broadens real disk/state/store/composite coverage. The seven excluded tests instantiate LangChain filesystem middleware. No replacement implementation is used for them. [Filesystem backend][fs-backend-write] · [File round trips][file-format-tests] |
| Code local ownership, event source and adapter tests on Python 3.14 | First run **24 passed, 3 failed** at imports. Adapter recheck with two actual upstream fallback class definitions **26 passed, 1 deselected**. | Local cross-process fencing, token rotation, SQLite mutations, and ephemeral event sockets ran. The adapter's ancestor-walk and delegated fast path matched in isolation. The app restart test and full dev-server import remain outside the run. [Code fencing tests][code-owner-tests] · [Adapter tests][code-adapter-tests] |
| Talon checkpoint and store archive tests, then the archive saver file | **63 passed** and **18 passed**, respectively. | Temporary SQLite and in-memory persistence, archive writes and failure/recovery ordering, including an isolated source loader for the archive helper's unused runtime import. [Talon checkpoint tests][talon-checkpoint-tests] · [Talon archive tests][talon-archive-tests] |
| Example Agent Protocol endpoint tests with only the model bootstrap bypassed | **8 passed, 1 warning**. Also ran the deliberate single-loop cancellation and conversation transfer controls in process using HTTPX ASGI transport and the real LangGraph SDK client. | Directly tests transport and storage behavior of the sample app with a canned model. The broad test's assertions accept final SQL status without proving worker cancellation. [Example fixtures][example-tests] · [Example cancellation][example-cancel] |
| Read-only static checks | **1,258** tracked Python files compiled in memory on CPython 3.14.8, zero syntax errors. Cached Ruff 0.15.12 gave zero lint findings with `check --no-cache --statistics deepagents tests` and reported **149 files already formatted**. The host's Ruff 0.16.10 found **171** lint results and reported **158 files already formatted**. | Tool/version-specific static evidence. The lock calls for Ruff 0.15.22. This test does not establish type checking or behavior on every supported Python version. [Ruff lock][locked-ruff] · [Lint and type targets][sdk-makefile] |

### Runtime controls

- **Remote task records.** Used the pinned implementation of the launch/check/update/cancel/list helpers. A fake remote server provided deterministic state transitions and ambiguous commit faults. Real LangGraph ToolNode ran the competing check/cancel in both orderings and both execution modes. Additional controls exercised busy/paused/idle/error interpretation, queued notification provenance, filtering on cached status, bounded automatic pull, and parent wake exception phase. These controls do not assume a particular provider LLM will emit the test sequence. [Remote launch][remote-launch] · [Remote concurrency][task-reducer] · [Observation][remote-observe] · [Parent pull][remote-pull]
- **Inline execution and transfer.** Used the pinned `_build_task_tool`, real checkpointer, real child Pregel graphs and a model-free parent with supplied AI tool-call objects. At input count 10, zero-change, one-child and two-child outcomes were 10, 21 and 32. The no-change control, independent tasks in one graph, a single completed child edit, namespace artifacts and filtered private state passed. The conflicting file snapshots and unpropagated deletion reproduced in both modes. [Task preparation][inline-prepare] · [Result transfer][inline-return] · [Files reducer][files-channel]
- **StateBackend and StoreBackend.** Real graphs tested pending-read scope and state checkpoints, while the store probe used a barrier in a real `InMemoryStore.get` subclass after taking the read snapshot. Parallel same-file edits each reported success and one was lost. The sequential schedule preserved both edits. Distinct StateBackend paths in the same graph preserved both writes. Store prefix aliasing disappeared when namespaces differed. [State read/send][state-backend] · [State edit][state-edit] · [Store edit][store-edit] · [Route prefix][composite-route]
- **Resume and side effects.** A graph checkpointed a predecessor file write, then queued a second file write and interrupted before completing its node. In memory and after closing and reopening a real SQLite saver on the same thread, the paused state held the predecessor file and one interrupt. Resuming by interrupt ID re-entered the paused node, committed its file update, and never re-entered the completed predecessor. A distinct SQLite thread returned empty state. The off-graph observation log recorded `predecessor, before interrupt, before interrupt, after interrupt`. This illustrates the semantic difference between re-entrant node work and checkpointed writes. It was a saver reopen in one process rather than a crash-injection test. [LangGraph resume][lg-interrupt] · [SDK state writes][state-backend]
- **Context recovery.** A fake model handler rejected an oversized request once, twice, or with unrelated HTTP 429. The tested budget method made one smaller retry for a recognized 400 overflow, going from a deterministic 4,000-token proxy to 1,067 and retaining the original tool message ID. A second overflow produced `ContextOverflowError` after two attempts. An unrelated 429 escaped after one call. An irreducible system prompt with a known budget was rejected before any handler call. These passed in sync and async. Real filesystem archive and cutoff controls in section 5 tested failure paths separately. [Budget and recovery][summary-budget] · [Tail clip][overflow-clip] · [Context tests in the repository][compaction-tests]
- **Code retry decisions.** Ran the source retry helpers on CPython 3.14 without middleware assembly. Simulated HTTP 403 and unsupported protocol did not retry. HTTP 429/503 and a transport error in an exception group were classified retryable. One 4 ms simulated `Retry-After` fit a 6 ms cumulative budget, a second did not, and the original exception reached the caller. A first transient error followed by success produced two calls and one retry event. `GraphBubbleUp` propagated on the first call. Both sync and async variants matched. This isolates retry decisions and does not measure real provider pacing or streamed chunk recovery. [Retry classifier][code-retry-classify] · [Retry loops][code-retry-loop]
- **Reducer and state-schema controls.** In CPython 3.14, 1,000 seeded operation sequences for the message and file reducers matched an independent reference in four batch groupings. The message cases include ID updates, removal and reset. The file cases cover overwrites and tombstones. The state reflection control used an identity marker standing in for the unavailable imported symbol and real Python typing. It confirmed a valid annotation is detected, an unresolved annotation skips the entire affected schema, and a separate resolvable schema still contributes its field. [Reducer][message-reducer] · [File reducer][files-channel] · [Private schema recognition][private-state]
- **Talon retry and Code restart.** A scripted graph fault after a completed node showed Talon's retry behavior in section 5. Only the delay clock was bypassed, and the runtime's actual retry classifier recognized the connection error. The Code restart control ran the actual reservation, token rotation and restart-failure handling methods with a fake failed subprocess stop. The initial UI-less fixture lacked a field read in `finally`. With the optional input widget represented as absent, the old client and saver token were fenced and the existing reservation survived. No UI or server process was started. [Talon retry loop][talon-retry] · [Code restart boundary][code-respawn] · [Code writer guard][code-thread-guard]

### Checkpoint measurement

Append-only single-node graphs emitted one 256-character human message per step with a stable ID, using synchronous durability and a fresh `InMemorySaver` each run. Each run checked the final reconstructed message count and boundary IDs. The table shows **serialized bytes from nonempty `messages` blobs plus serialized pending writes on that channel only**, excluding Python memory overhead, metadata, other channels and database page effects. The last column removes full snapshot materialization over this short workload by setting a cadence beyond the run length. This third arm checks the source of the growth. [Delta snapshot implementation][lg-snapshot] · [Saver serialization][lg-saver] · [SDK channel][message-state]

| Messages appended | Full-value snapshots + writes | Delta at 50 + writes | Delta beyond run length + writes |
| ---: | ---: | ---: | ---: |
| 100 | 2,070,672 | 99,811 | 40,301 |
| 200 | 8,161,372 | 280,023 | 80,601 |
| 400 | 32,402,772 | 881,651 | 161,201 |
| 800 | 129,125,572 | 3,049,707 | 322,401 |

The default cadence materialized 2, 4, 8 and 16 snapshots. At 800 steps it used roughly **42× fewer bytes** than the full-value arm. The additive writes grew roughly twofold each time the run length doubled. The serialized delta snapshots grew from 59,510 bytes at 100 steps to 2,727,306 bytes at 800 steps, as an increasing number of full values became larger. This is synthetic volume evidence from a compatible local LangGraph version. It does not provide production latency, memory or disk-capacity targets. [Snapshot calculation][lg-snapshot] · [Full snapshot contents][lg-create-checkpoint]

### Evidence boundary

The fallback suite used locally cached LangGraph 1.2.22/checkpoint 4.3.2 and SDK 0.4.14, not the SDK package's locked 1.2.20/4.3.0/0.4.7. Local packaging and fixtures are described in section 8. The strongest findings combine an unchanged application method, an independent supported code path, positive and negative controls, and source confirmation. No actual hosted service, external network, credential or provider model was used. Some SDK tests require real providers or LangSmith services regardless of dependency availability. Timing results include sandbox and shared-host variability. The Linux check does not cover native Windows subprocess behavior. [SDK lock][locked-lg] · [SDK live integration imports][integration-model] · [Sandbox live fixture][integration-sandbox]

## 8. Measurement audit for every negative or surprising result, including alternate commands or code-path checks used to rule out setup mistakes

| Negative or surprising result | Alternate check and interpretation |
| --- | --- |
| Install and original test collection stopped abruptly | The first frozen offline sync used an empty workspace cache and encountered locked NumPy via `langchain-tests`. That error alone is only a cache miss. I staged dependency-only local artifacts from an earlier LangGraph review, checked metadata and `find_spec`, and reran the original pytest collection under network isolation. It reached the precise project import that requires `langchain.agents` and failed before any run or credential check. Integration-only collection ended at imports across all six files. A cache inventory checked the default uv archive/wheel and cached pip wheel response metadata for the required project names. The available LangChain **Core** cannot substitute for LangChain's agent package. [Runtime import][assembly-imports] · [Unit conftest][unit-conftest] · [Dependency declarations][sdk-manifest] |
| Initial Python and pytest harness issues | A bare sanitized environment lacked pytest because it removed the usual user-package path. Explicit `PYTHONPATH` with the staged pytest distribution resolved that. Bubblewrap's first read-only root mount also made `/dev/null` unavailable to fd capture, which was fixed with `--dev /dev`. Neither failure reached the tests. The SDK warning configuration also imports the absent `pytest_benchmark` module at startup. The expanded suite used `-c /dev/null`, explicit asyncio configuration, and `-W error` plus the project’s LangSmith sandbox warning exception. |
| 152 initial component failures and 8 skips | The old glob package lacks `wcglob.compile`, although `globmatch` exists. Exposing the real package-parent attribute fixed the dotted monkeypatch used by the sandbox timeout test. Reintroducing the project's per-test video cache reset fixed three order-dependent video gate failures. Unprivileged user identity restored five permission-sensitive cases skipped in the initial user namespace that had mapped the process to uid 0. This reduced 152 failures to 148 before touching glob compatibility. [Timeout monkeypatch][sandbox-timeout-test] · [Video reset fixture][video-fixture] · [Root skip guard][sandbox-skip] |
| All 148 remaining compatibility-run failures | A one-change re-run bridged the missing `compile` method onto the local 8.5.2 public matcher and flipped every remaining case from fail to pass. JUnit grouped the same failures under glob, state, composite, and local shell wrapper assertions, often surfaced as empty/error results after the utility catches the wrong-version exception. The lock requires 11.0, so neither run establishes exact behavior on that version. [Glob API call][glob-compile] · [Glob lock][locked-glob] |
| Optional media skip and coverage setup | The first pip HTTP-cache Pillow body was for CPython 3.14, while the suite ran 3.12. Wheel `Tag` metadata identified a separate compatible local Pillow 13.0.0 and an `abi3` PyAV 18.1.0. Tests then exercised actual media decoding. The initially staged coverage wheel's C tracer was 3.14 only. Selecting the pure Python tracer resolved the failure while preserving strict warning handling. The final two SDK skips both require native Windows handles. [Optional video declaration][sdk-manifest] · [Native Windows gates][windows-tests] |
| Expected composite failures in two suites | The supplied route configs use the same store and namespace. A separate control read a file through both prefixes with that config, then changed only one namespace and saw a single routed path. This establishes aliasing by design at the store scope. It is independent of matcher provisioning and not a claim that explicit distinct namespaces leak. [Expected failures][composite-xfail] · [Namespace][store-namespace] |
| Code tests originally failed at `textual` and `langgraph_api` imports | The app-level test constructs `DeepAgentsApp`, which brings in UI and other unavailable runtime deps. The other 11 ownership tests exercise the lower-level filesystem lease, owner rotation, interrupted mutations, and saver fence. The two adapter tests had already seeded SQLite before the missing server adapter import. Re-ran them with the corresponding unmodified implementation classes extracted from the cached 0.17.1 adapter and real 3.1.3 SQLite saver. Both fast path and base walk passed. This validates the fallback shape only. The locked 0.18.0 adapter and full server start remain unverified. [App-coupled test][code-restart-test] · [Adapter tests][code-adapter-tests] · [Code lock][code-locked-api] |
| Talon whole-graph retry duplicated work | The fault was deliberately placed after the first node committed. Its first invocation wrote a checkpoint and raised a retryable exception from a separate second node. A stable-ID variant retained the same first-node replay, ruling out simple message-ID duplication as the complete cause. A same-thread `None` continuation retried only the second node. The first-node counter is a local side-effect marker, independent of message state and provider behavior. [Input and retry][talon-retry] |
| Ruff 0.16.10 emitted 171 results while lower 0.15.12 emitted zero | Host run reported 149 `CPY001`, 11 `RUF100`, 6 `PLR0917`, 2 `ISC004`, 2 `LOG004`, 1 `RUF036`. Project selects `ALL` and locks an older Ruff family. Cross-checked using cached 0.15.12 with the same configuration and files. Results depend on rule evolution. Neither binary is the exact lock, and no findings were counted as repository defects. [Lint configuration][sdk-ruff] · [Locked version][locked-ruff] |
| Nested state changed unexpectedly | Tested build, invoke and stream paths with real Pregel and custom `CompiledSubAgent` inputs. The same parent baseline and increment succeeded in a single graph and when a child returned no change. Distinct files composed inside a single graph, a single child edit persisted, and both child operations succeeded from inside their own graphs. With the actual return conversion in place, adding snapshots counts the baseline again and returning a whole file map rewrites stale inherited entries. Deletion is visible within the child, but cannot be inferred from an absent key during parent map merging. No provider, scheduler quota or file permission was required for this reproduction. [Input and result conversion][inline-prepare] · [File merge][files-channel] |
| Store and same-graph same-key edits losing a successful change | Read barriers forced both operations to use the same version. Sequential operations preserved both replacements, and different file keys in one graph composed. An isolated test of state backend writes from one node showed fresh same-node reads worked. This isolates shared-file update semantics and does not depend on parallel executor timing. [State backend][state-backend] · [Store edit][store-edit] · [Pregel local read][lg-local-read] |
| Async lifecycle edge results | Fault injection occurred both before and after the fake server accepted a run. Every attempt used the same task description and tool-call ID under valid input. The record serialized only on success. Events forced the check to read before cancellation, then both sync/async tool orders were tried and produced the same order-sensitive results. Busy/errored thread controls triggered the latest-run lookup, and the pause and queued provenance controls behaved as documented. For the stale unqueued notification, this is a demonstrated receiver behavior, not a measured production race rate. [Launch boundary][remote-launch] · [Reducer and record][task-reducer] · [Observation and notification][remote-observe] |
| Example cancellation test passed despite the worker continuing | Verified a real launch through `LangGraphClient` over `httpx.ASGITransport` on one event loop. An event held the worker active until the API had acknowledged cancellation. `worker.cancelling()` remained zero, and releasing it let success overwrite the cancelled row. A separate normal run on the same loop succeeded. The old human turn in a multi-message payload was delivered to the fake model exactly as the source's first-user selection predicts. The original tests use `TestClient` and wait on the main thread event loop, yielding a Python 3.12 deprecation warning. The focused test uses a definite task handle and event ordering for its assertions. [Example test synchronization][example-tests] · [Example cancellation contract][example-cancel] |
| Summary archive truncated on a read error | A real local backend first stored and reread an existing marker. Fault injection affected only the next download, and the subsequent read verified the overwrite via a successful local file result. The healthy append kept both markers. Both exception-valued and result-valued read faults reproduced in sync and async. No disk-space, permissions, process quota or token-limit failure was involved. The cutoff loss required removal of the anchor itself. Removing only earlier history passed with stable-ID relocation. [Sync and async archive][summary-offload] · [Cutoff fallback][summary-view] |
| Storage growth differed from the SDK comment | Measured actual serialized values via saver blob and pending-write entries, explicitly excluded checkpoint metadata and other channels, verified reconstructed content, and held message size and append rate constant. The no-snapshot control removed the extra growth, and LangGraph source shows full snapshot materialization. The causal claim is the retained full-snapshot contribution, independent of the exact size of this host's serializer output. [Snapshot cadence][lg-snapshot] · [Persistence arrays][lg-saver] |

## 9. Post-mortem: design pressures, accumulated tradeoffs, likely failure modes, and the highest-leverage improvements

The design deliberately favored compatibility with LangChain tools and LangGraph state over a separate orchestration engine. That was a productive choice. The model can delegate without learning a new API, developers compose features with middleware, and agents reuse tested graph capabilities for interrupts, history and checkpointing. A policy boundary becomes fragile when an artifact crosses into a domain with different semantics while keeping the same shape. The source already treats model history and assistant-visible prompts differently and gives subprocesses a concrete ownership protocol. Applying the same discipline to inter-agent state and remote task transitions would address the largest risks. [Architecture layering][architecture] · [Reducer contract][lg-delta] · [Filesystem and delta state][files-channel] · [Shell cleanup][shell-cleanup]

**Reconstructed inline incident.** A parent starts two workers against a workspace snapshot. Each changes a different existing file and returns a plausible final report. Both child checkpoints are correct. The parent receives two full file maps, including each child's stale copy of the other file, and combines them in a valid but harmful reducer fold. One changed file disappears from the parent view. A follow-up write can propagate that stale version into a later artifact. The failure has three contributing conditions: inherited mutable channels, a full-state child output contract, and a parent reducer expecting operations. The key-equality filter addresses duplicate unchanged writes, while the correct patch requires explicit operation boundaries. A user inspecting only final textual reports can miss the overwritten value. [Result update][inline-return] · [State-backed filesystem writes][state-edit] · [File reducer][files-channel]

**Reconstructed remote incident.** A supervisor launches a worker and the tool call loses the post-commit response. The remote job proceeds, but the parent's checkpoint records the tool's failure string with no pointer. A repeated launch creates another job. In the subsequent turn, a check consumes a stale snapshot while cancellation acts on the tracked run, and the reducer can put the old status back. A push notification can race a follow-up and an independent poll can lose run identity when a resumed thread is already idle. These behaviors all follow from using the local task record as a periodically replaced cache while also treating its status as authoritative for mutation, filtering and deduplication. RPC success, state persistence and notification admission require different handling. [Launch ordering][remote-launch] · [Task observation][remote-observe] · [Task reducer][task-reducer] · [Notification recording][remote-record]

**Reconstructed context incident.** A compacting agent archives a prior section and later downloads the same file before appending. A transient read error is treated as no previous content. The next write returns success and replaces the archive with the latest section. The summary's pointer looks valid while part of the older evidence is gone from that artifact. Independent checkpoint retention can make recovery possible for an operator, but the model sees the pointer and assumes history is present. The code already has structured file-download error classes and a more robust backend mutation protocol in Context Hub. [Summary offload][summary-offload] · [File download result][backend-protocol] · [Context Hub version preconditions][context-hub-conflict]

| Priority | Change | Acceptance check |
| --- | --- | --- |
| **P1** | Give inline delegation a parent-channel output contract. Keep the textual/structured response and tracing envelope. Transfer file operations with per-key changed values and tombstones, and require explicit adapters or emitted operations for application reducers. For concurrent writes to the same path, require documented conflict detection, serialization, or deterministic application semantics. | Two children editing two existing files preserve both. A delete of an inherited file persists. An additive field seeded at 10 becomes 12 after two +1 updates. Retry and interrupt variants remain correct. |
| **P1** | Add idempotent remote operations and reconciliation. Persist launch intent with a stable key from parent thread, call identity and operation generation before remote work. Use a server-side idempotency contract or existing lookup by deterministic operation metadata, and reconcile partially accepted creates. Treat cancel as requested/confirmed separately and preserve a recoverable record of pending run IDs. | Fault at every pre/post-commit boundary. Replaying the same intent converges to one tracked job or a terminal failure with a reconciliation pointer. A late acknowledgement updates the intended generation. |
| **P1** | Replace shallow task overwrite with versioned transitions or serialized commands per task. Apply observations only to the generation they read. Record a monotonic operation sequence or server version and define obsolete events, terminal transitions, stale cache evidence and queue ordering. Give status filtering a clear live/cached contract. | Permute start/update/check/list/cancel/notify orderings with duplicate and deferred events. A successful cancellation cannot be reverted by an older read and an older result cannot close a newer run. |
| **P1** | Separate missing archive from failed read and add atomic append or version-checked writes. Namespace and version summary artifacts by logical event/turn so retries can find their own writes. Persist matching anchors for compaction state and actual history. | A read denied or interrupted after a prior archive leaves that archive intact while the attempt reports explicit degradation. Concurrent appends, failed model retries and transcript rebase have deterministic outcomes. |
| **P2** | Put application retries at the narrowest recoverable boundary. Give each Talon inbound event a stable identity, track whether the input already committed, and use checkpoint continuation or a graph-node retry where it is safe. Expose deliberate replay and the risk of repeating external effects when restart is unavoidable. | Inject a fault before and after checkpoint commit and verify a single inbound message and one prior-node effect where the intended semantics are continuation. |
| **P2** | Define ownership for async clients and background work. Reuse one owned per-runtime client pool where safe, close it on host shutdown, and scope it per event loop as appropriate. Cap remote status request fan-out and add a typed sender/receiver envelope and durable latency, retry, cancellation and orphan counters. | Cancellation during connect, busy/paused state, unsupported ASGI transport, duplicate notification and shutdown each have tests that assert final state and released resources. |
| **P2** | Publish a dependency compatibility matrix for LangChain, LangGraph core, checkpoint, prebuilt, SDK, and Agent Server. Make exact frozen fake-model integration and offline dependency bundles reproducible. Use a public adaptor API for runtime config or saver forwarding as dependencies add the seam. Describe the storage tradeoff with snapshot cadence and retention. | Minimum and locked versions pass the same scripted model/tool and SQLite replay scenarios. A compatibility test verifies artifact namespace and branch replay semantics without provider access. Capacity docs include retained snapshots and histories. |
| **P2** | Repair the example or narrow its advertised contract. Own and cancel workers by run ID, atomically fence late results, forward complete conversation input, and dependency-inject a model for tests rather than constructing one at module import. | Tests cancel an event-gated executing task, join its teardown, and verify terminal status and history. Follow-up and fork-shaped payloads reach the intended turn, and unavailable providers do not prevent endpoint tests. |

## 10. Evidence appendix with local file/line references and commands

### Offline inputs and commands

The project source is the pinned checkout. The staged dependency files were copied from local artifacts, with no index access. SDK component runs used CPython 3.12.16, pytest 9.2.0, pytest-asyncio 1.4.1.post1, LangChain Core 1.7.3, LangGraph 1.2.22, prebuilt 1.1.2, checkpoint 4.3.2, LangGraph SDK 0.4.14, SQLite saver 3.1.3, LangSmith 0.14.17, and wcmatch 8.5.2. Video recovery staged Pillow 13.0.0 and AV 18.1.0. Code and Talon selected tests used CPython 3.14.8, cached LangChain Core 1.6.5 and the same LangGraph core and SQLite saver versions. Code used filelock 3.29.0 instead of its lock's 4.2.9. The example used FastAPI 0.162.0, Starlette 1.10.0, HTTPX 0.28.1 and httpx2 2.16.0 for Starlette's TestClient. The linked LangGraph source is the separate local checkout `bbd52757e72d8611b07ae2831b9529a6ba03f2a1`, used to verify contracts alongside the installed fallback. It is not the SDK's lock revision. [SDK runtime dependency lock][locked-lc] · [Graph dependency lock][locked-lg]

Run the environment setup from the evaluation workspace. The staging locations below identify the cached artifacts used during this investigation. Equivalent local installations with the stated versions also work for the isolated probes.

```bash
da_root=$HOME/.t3/scratch/2026-11-18-spend-a-million-tokens-or-d93b80f1
da_repo="$da_root/repos/langchain-ai__deepagents"
da_scratch=$(mktemp -d "$da_root/.deepagents-repeat.XXXXXX")
da_prior=$HOME/.t3/langgraph-eval-bbd5275.ztTirZcX
da_cache=$HOME/.cache/uv/archive-v0
cp -a --reflink=auto "$da_prior/venv-prebuilt/lib/python3.12/site-packages" "$da_scratch/deps"
cp -a --reflink=auto "$da_prior/venv-314/lib/python3.14/site-packages" "$da_scratch/deps314"
cp --reflink=auto "$da_prior/venv/lib/python3.12/site-packages/langgraph_api/_checkpointer/_adapter.py" \
    "$da_scratch/lg-api-adapter-0.17.1.py"
mkdir -p "$da_scratch/example-deps"
for item in MYcA62qvrTC0C0A7 WqSSRXAK8gn1vSAK vdY6Hm2dy84gNdDc Uwy2fnQZKwvLtmBH TNvfH5sN2cKe4n58 ON4ASResDlI5I0pO; do
    cp -a --reflink=auto "$da_cache/$item/." "$da_scratch/deps/"
done
for item in Moyem-pA123G1JTT; do
    cp -a --reflink=auto "$da_cache/$item/." "$da_scratch/deps314/"
done
for dist in "$da_cache"/*/pytest_asyncio-1.4.1.dist-info; do
    if test -d "$dist"; then
        cp -a "$(dirname "$dist")/pytest_asyncio" "$dist" "$da_scratch/deps314/"
        break
    fi
done
for item in gV_qGEXcrpdHmwmb IPaI8qtBq_nlQ0ef iV1_f8zBkpjVDlSY cbIbyXHcEhNg7ihl 6h1bwPQUlgSp8qIT Jr3JMub2pXYPI_QU ixcPx_ciJDyFZDZl; do
    cp -a --reflink=auto "$da_cache/$item/." "$da_scratch/example-deps/"
done

da_offline() {
    local da_pythonpath=$1
    shift
    bwrap --unshare-net --die-with-parent --ro-bind / / \
        --dev /dev --proc /proc --tmpfs /run --tmpfs /tmp \
        --bind "$da_scratch" "$da_scratch" --clearenv \
        --setenv PATH "$PATH" --setenv HOME "$da_scratch" --setenv TMPDIR "$da_scratch" \
        --setenv LANG C.UTF-8 --setenv PYTHONPATH "$da_pythonpath" \
        --setenv PYTEST_DISABLE_PLUGIN_AUTOLOAD 1 --setenv PYTHONDONTWRITEBYTECODE 1 "$@"
}

# Check source identity and cleanliness.
date -u +'%Y-%m-%dT%H:%M:%SZ'
(
    set -e
    da_head=$(git --no-optional-locks -C "$da_repo" rev-parse HEAD)
    test "$da_head" = a502bd69d0677c1ac4d6481622e840977decbf80
    da_status=$(git --no-optional-locks -C "$da_repo" status --porcelain=v1 \
        --untracked-files=all --ignored=matching)
    test -z "$da_status"
    git --no-optional-locks -C "$da_repo" diff --exit-code
    git --no-optional-locks -C "$da_repo" diff --cached --exit-code
    printf 'HEAD %s; checkout clean\n' "$da_head"
)

# Offline install and actual SDK collection, expected to stop at dependency availability.
cd "$da_repo/libs/deepagents"
da_offline "$da_scratch/deps" env UV_OFFLINE=1 UV_NO_CONFIG=1 UV_PYTHON_DOWNLOADS=never \
    UV_CACHE_DIR="$da_scratch/uv-cache" UV_PROJECT_ENVIRONMENT="$da_scratch/venv" \
    uv sync --offline --frozen --no-install-project --no-build --group test
da_offline "$da_scratch/deps" python -B -m pytest -c /dev/null -o asyncio_mode=auto \
    -p pytest_asyncio.plugin -p no:cacheprovider --collect-only -q tests/unit_tests
da_offline "$da_scratch/deps" python -B -m pytest -c /dev/null -o asyncio_mode=auto \
    -p pytest_asyncio.plugin -p no:cacheprovider --collect-only -q tests/integration_tests

# Static lint and format checks, with two locally available tool versions.
ruff check --no-cache --statistics deepagents tests
ruff format --check --no-cache deepagents tests
"$da_cache/CYaQiqBy10Ysyczg/ruff-0.15.12.data/scripts/ruff" check --no-cache --statistics deepagents tests
"$da_cache/CYaQiqBy10Ysyczg/ruff-0.15.12.data/scripts/ruff" format --check --no-cache deepagents tests
```

The next probes use the wrapper above. Python bodies are fed on stdin. They are included here because only the report is a durable evaluation artifact. Source extraction bypasses unrelated unavailable package imports, keeps the methods under test as checked in, and is labeled where the caller or service is simulated. For SDK component pytest, the two staged namespace objects allow backend modules to import without the SDK's eager graph factory import.

Replaying the expanded SDK component command, remote lifecycle, inline tasks, state/SQLite, context and example recipes from a fresh staging directory reproduced the observations. The repeated SDK suite reported the same 991 passes, two native-platform skips, one xfail, and 26% scoped coverage in 43.39 s. The four installed LangGraph files cited for channel snapshot and resume mechanics (`channels/delta.py`, `pregel/_algo.py`, `pregel/_checkpoint.py`, and `types.py`) matched the adjacent checkout byte for byte. Inside Bubblewrap the process remained uid 1000, with loopback only and an empty IPv4 route table.

A second fresh staging run reproduced the 421 SDK backend passes with seven deselections and one xfail, the 26 Code passes with one deselection, and both Talon results of 18 and 63 passes. It also reproduced the focused Code retry and restart fencing, Talon checkpoint replay, and SDK reducer batching and private-annotation controls. The syntax pass covered 1,258 tracked Python files.

<details>
<summary>SDK original-API baseline and compatibility control</summary>

The case with the 8.5.2 adapter uninstalled is expected to return 148 test failures. Running the same file list with the adapter installed is the matching control.

```bash
cd "$da_repo/libs/deepagents"
for DA_VARIANT in 0 1; do
    da_offline "$da_scratch/deps" env DA_GLOB_ADAPTER="$DA_VARIANT" python -B - <<'PY'
from pathlib import Path
import os, sys, types
import pytest
import wcmatch, wcmatch.glob as wcglob
print('wcmatch=', wcmatch.__version__, 'compile=', hasattr(wcglob, 'compile'), 'compat=', os.getenv('DA_GLOB_ADAPTER'), flush=True)
if os.getenv('DA_GLOB_ADAPTER') == '1':
    assert wcmatch.__version__ == '8.5.2' and not hasattr(wcglob, 'compile')
    def compile_compat(pattern, *, flags):
        wcglob.globmatch('', pattern, flags=flags)
        return types.SimpleNamespace(match=lambda path: wcglob.globmatch(path, pattern, flags=flags))
    wcglob.compile = compile_compat
for name in ('deepagents', 'deepagents.backends', 'deepagents.middleware'):
    pkg = types.ModuleType(name)
    pkg.__path__ = [str(Path(*name.split('.')).resolve())]
    sys.modules[name] = pkg
    if '.' in name:
        parent, suffix = name.rsplit('.', 1)
        setattr(sys.modules[parent], suffix, pkg)
class VideoFixture:
    @pytest.fixture(autouse=True)
    def _reset_video_dep_cache(self):
        from deepagents.middleware._video import video_dependencies_available
        video_dependencies_available.cache_clear()
tests = ['test_messages_reducer.py','test_local_shell.py']
tests += ['backends/test_'+x+'.py' for x in ('protocol','utils','state_backend','state_backend_async','composite_backend_async','timeout_compat','glob_semantics','local_shell_backend','posix_process','windows_process','sandbox_backend')]
tests += ['middleware/test_video_deps.py','middleware/test_video.py']
root = Path.home()
label = 'adapted' if os.getenv('DA_GLOB_ADAPTER') == '1' else 'original-api'
raise SystemExit(pytest.main(['-c','/dev/null','-p','pytest_asyncio.plugin','-p','no:cacheprovider','--noconftest','-o','asyncio_mode=auto','-o','asyncio_default_fixture_loop_scope=function','-m','not benchmark','--basetemp',str(root/('pt-components-'+label)),'--junitxml',str(root/('components-'+label+'.xml')),'-q','-ra','--tb=short',*[str(Path('tests/unit_tests')/test) for test in tests]],plugins=[VideoFixture()]))
PY
done
```

</details>

<details>
<summary>Expanded SDK components with coverage</summary>

```bash
cd "$da_repo/libs/deepagents"
da_offline "$da_scratch/deps" env DA_GLOB_ADAPTER=1 COVERAGE_CORE=pytrace \
    COVERAGE_FILE="$da_scratch/coverage" python -B - <<'PY'
from pathlib import Path
import os, sys, types
import pytest
import wcmatch, wcmatch.glob as wcglob
print('wcmatch=', wcmatch.__version__, 'compile=', hasattr(wcglob, 'compile'), 'compat=', os.getenv('DA_GLOB_ADAPTER'), flush=True)
if os.getenv('DA_GLOB_ADAPTER') == '1':
    assert wcmatch.__version__ == '8.5.2' and not hasattr(wcglob, 'compile')
    def compile_compat(pattern, *, flags):
        wcglob.globmatch('', pattern, flags=flags)
        return types.SimpleNamespace(match=lambda path: wcglob.globmatch(path, pattern, flags=flags))
    wcglob.compile = compile_compat
for name in ('deepagents', 'deepagents.middleware'):
    pkg = types.ModuleType(name)
    pkg.__path__ = [str(Path(*name.split('.')).resolve())]
    pkg.__file__ = str(Path(*name.split('.'), '__init__.py').resolve())
    sys.modules[name] = pkg
    if '.' in name:
        parent, suffix = name.rsplit('.', 1)
        setattr(sys.modules[parent], suffix, pkg)
from deepagents._version import __version__
sys.modules['deepagents'].__version__ = __version__
class VideoFixture:
    @pytest.fixture(autouse=True)
    def _reset_video_dep_cache(self):
        from deepagents.middleware._video import video_dependencies_available
        video_dependencies_available.cache_clear()
tests = ['test_messages_reducer.py','test_local_shell.py','test_version.py']
tests += ['backends/test_'+x+'.py' for x in ('protocol','utils','state_backend','state_backend_async','composite_backend_async','timeout_compat','glob_semantics','local_shell_backend','posix_process','windows_process','sandbox_backend','context_hub_backend','langsmith_sandbox')]
tests += ['middleware/test_video_deps.py','middleware/test_video.py']
root = Path.home()
label = 'adapted' if os.getenv('DA_GLOB_ADAPTER') == '1' else 'original-api'
raise SystemExit(pytest.main(['-c','/dev/null','-W','error','-W','ignore:langsmith.sandbox is in alpha:FutureWarning','-p','pytest_cov.plugin','-p','pytest_asyncio.plugin','-o','markers=anyio: asynchronous test','-p','no:cacheprovider','--noconftest','-o','asyncio_mode=auto','-o','asyncio_default_fixture_loop_scope=function','-m','not benchmark','--basetemp',str(root/('pt-components-full-'+label)),'--junitxml',str(root/('components-full-'+label+'.xml')),'-q','-ra','--tb=short','--cov=deepagents','--cov-report=term',*[str(Path('tests/unit_tests')/test) for test in tests]],plugins=[VideoFixture()]))
PY
```

</details>

<details>
<summary>Additional SDK backend contracts</summary>

```bash
cd "$da_repo/libs/deepagents"
da_offline "$da_scratch/deps" python -B - <<'PY'
from __future__ import annotations
import ast, sys, types
from pathlib import Path
from typing import Annotated, NotRequired, TypedDict

import pytest
import wcmatch.glob as wcglob
from langgraph.channels.delta import DeltaChannel

def compile_compat(pattern, *, flags):
    wcglob.globmatch('',pattern,flags=flags)
    return types.SimpleNamespace(match=lambda p:wcglob.globmatch(p,pattern,flags=flags))
wcglob.compile=compile_compat

for name in ('deepagents','deepagents.middleware'):
    module=types.ModuleType(name)
    module.__path__=[str(Path(*name.split('.')).resolve())]
    sys.modules[name]=module
    if '.' in name:
        setattr(sys.modules['deepagents'],'middleware',module)
from deepagents.backends.protocol import FileData

# This component subset never constructs FilesystemMiddleware. Fail if that changes.
class UnavailableFilesMiddleware:
    def __init__(self,*args,**kwargs):
        raise AssertionError('selected a test requiring LangChain middleware')

name='deepagents.middleware.filesystem'
scope=types.ModuleType(name)
scope.__dict__.update(FilesystemMiddleware=UnavailableFilesMiddleware,AgentState=TypedDict,Annotated=Annotated,NotRequired=NotRequired,DeltaChannel=DeltaChannel,FileData=FileData)
sys.modules[name]=scope
sys.modules['deepagents.middleware'].filesystem=scope
path=Path('deepagents/middleware/filesystem.py')
tree=ast.parse(path.read_text())
nodes=[]
for n in tree.body:
    if getattr(n,'name',None) in {'_file_data_delta_reducer','FilesystemState'} or (
        isinstance(n,ast.Assign) and any(getattr(t,'id',None)=='GLOB_TIMEOUT' for t in n.targets)
    ):
        nodes.append(n)
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),scope.__dict__)

class ExcludeToolExecution:
    def pytest_collection_modifyitems(self,config,items):
        import inspect
        excluded=[i for i in items if 'FilesystemMiddleware(' in inspect.getsource(i.obj)]
        for i in excluded:
            print('requires unsupported middleware:', i.nodeid)
        items[:]=[i for i in items if i not in excluded]
        config.hook.pytest_deselected(items=excluded)

names=('filesystem_backend','filesystem_backend_async','store_backend','store_backend_async','composite_backend','file_format')
raise SystemExit(pytest.main(['-c','/dev/null','--noconftest','-p','pytest_asyncio.plugin','-p','no:cacheprovider','-o','asyncio_mode=auto','-o','asyncio_default_fixture_loop_scope=function','--basetemp',str(Path.home()/'pt-backends-extra'),'-q','-ra','--tb=short',*[f'tests/unit_tests/backends/test_{x}.py' for x in names]],plugins=[ExcludeToolExecution()]))
PY
```

</details>

<details>
<summary>Remote lifecycle races and notification controls</summary>

```bash
cd "$da_repo/libs/deepagents"
da_offline "$da_scratch/deps" python -B - <<'PY'
from __future__ import annotations
import __future__, ast, asyncio, logging, sys, threading, types
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, ToolRuntime
from langgraph.types import Command

def load_nodes(path, module, wanted, *, keep_imports=False, methods=None):
    tree = ast.parse(Path(path).read_text())
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = str(getattr(node, 'module', ''))
            if keep_imports and not names.startswith(('deepagents', 'langchain.')):
                selected.append(node)
        names = {getattr(node, 'name', None)}
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {n.id for n in targets if isinstance(n, ast.Name)}
        if names & wanted:
            if methods and isinstance(node, ast.ClassDef) and node.name in methods:
                node.bases = []
                node.body = [part for part in node.body if getattr(part, 'name', None) in methods[node.name]]
            selected.append(node)
    body = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(body, path, 'exec', flags=__future__.annotations.compiler_flag), module.__dict__)

source = types.ModuleType('async_subject')
sys.modules[source.__name__] = source
source.ToolRuntime = ToolRuntime
path = 'deepagents/middleware/async_subagents.py'
wanted = set('logger AsyncSubAgent AsyncTask _tasks_reducer _WAITING _UpdateStrategy _THREAD_TO_TASK_STATUS _TERMINAL_STATUSES StartAsyncTaskSchema CheckAsyncTaskSchema UpdateAsyncTaskSchema CancelAsyncTaskSchema ListAsyncTasksSchema _NEST_UNDER_PARENT _trace_headers _PARENT_KEY _ParentReference _parent_reference _reference_for _thread_metadata _STREAM_OPTIONS _run_options _forwarded_context _launching_agent _NOTIFICATION_SOURCE _NOTIFICATION_KEY _NOTIFICATION_NOTE _NOTIFICATION_PLACEHOLDER _MAX_RESULT_CHARS TaskEvent _TaskUpdate _notification_event _notification_body _superseded_notification_content _header_blocks _labeled _task_header _text_block _MEDIA_BLOCK_TYPES _result_blocks _escape _clip _current_run_id _event _final_content _DELIVERABLE_THREAD_STATUSES _awake_parent _validate_agent_type _start_task_messages _astart_task_messages _build_start_tool _task_status _needs_latest_run _observe _aobserve _pending_interrupts _WAITING_NOTE _build_check_result _build_check_command _check_output _keep_cancelled _resolve_tracked_task _build_check_tool _update_message _parallel_update_error _build_update_command _superseded_after_update _build_update_tool _cancel_earlier_runs _acancel_earlier_runs _build_cancel_tool _fetch_live_status _afetch_live_status _warn_cached_status _format_task_entry _filter_tasks _build_list_command _build_list_tasks_tool _PULL_TIMEOUT_SECONDS _UNFINISHED_STATUSES _check_event _notification_message _observed AsyncSubAgentMiddleware'.split())
source.NUM_CHARS_PER_TOKEN = 4
load_nodes(path, source, wanted, keep_imports=True, methods={'AsyncSubAgentMiddleware': {'_apull', '_aobserve_task','_record_notification'}})
load_nodes('deepagents/middleware/subagents.py', source, {'_refusal_in','_refusal_notice'})
ns = types.SimpleNamespace
S = source
logging.basicConfig(level=logging.ERROR)

def record(status='running', run_id='r1', task_id='t1'):
    return dict(task_id=task_id, agent_name='worker', thread_id=task_id, run_id=run_id,
                status=status, created_at='2026-01-01T00:00:00Z', last_checked_at='2026-01-01T00:00:00Z',
                last_updated_at='2026-01-01T00:00:00Z')

spec = {'name':'worker','description':'offline worker','graph_id':'fake','url':'http://unused.invalid'}
parent_config = {'configurable':{'thread_id':'parent'},'metadata':{'assistant_id':'supervisor'}}
def runtime(task=None, tool_id='call1', *, messages=()):
    return ns(state={'async_tasks':{task['task_id']:task} if task else {}, 'messages':list(messages)},
              config=parent_config, context=None, tool_call_id=tool_id)

class Launch:
    def __init__(self, fail):
        self.thread_ids, self.runs, self.fail = [], [], fail
    def thread(self, **kwargs):
        self.thread_ids.append('t'+str(len(self.thread_ids)+1))
        return {'thread_id':self.thread_ids[-1]}
    def run(self, **kwargs):
        mode, self.fail = self.fail, None
        if mode == 'before':
            raise OSError('response failed before commit')
        self.runs.append(kwargs['thread_id'])
        if mode == 'after':
            raise OSError('response lost after commit')
        return {'run_id': 'r'+str(len(self.runs))}
    def client(self):
        return ns(threads=ns(create=self.thread), runs=ns(create=self.run))

for fail in ('before','after',None):
    fake = Launch(fail)
    tool = S._build_start_tool({'worker':spec}, ns(get_sync=lambda _: fake.client()), 'start fixture')
    a = tool.func('test', 'worker', runtime())
    z = tool.func('test', 'worker', runtime()) if fail else a
    assert isinstance(z, Command) and list(z.update['async_tasks']) == [fake.thread_ids[-1]]
    if fail:
        assert isinstance(a,str) and fake.thread_ids == ['t1','t2']
    assert fake.runs == ({'before':['t2'], 'after':['t1','t2'], None:['t1']}[fail])
    print('launch', fail, 'threads', fake.thread_ids, 'runs', fake.runs, 'tracked', list(z.update['async_tasks']))

class ParentState(TypedDict):
    messages: Annotated[list, add_messages]
    async_tasks: Annotated[dict, S._tasks_reducer]

class Race:
    def __init__(self):
        self.read = threading.Event()
        self.cancelled = threading.Event()
        self.status = 'running'
    def get(self, **kwargs):
        snapshot = self.status
        self.read.set()
        assert self.cancelled.wait(4)
        return {'run_id':kwargs['run_id'], 'status':snapshot}
    def cancel(self, **kwargs):
        assert self.read.wait(4)
        self.status = 'interrupted'
        self.cancelled.set()
    async def aget(self, **kwargs):
        return await asyncio.to_thread(self.get, **kwargs)
    async def acancel(self, **kwargs):
        return await asyncio.to_thread(self.cancel, **kwargs)
    def client(self, asynchronous=False):
        return ns(runs=ns(get=self.aget if asynchronous else self.get, cancel=self.acancel if asynchronous else self.cancel))

def fixture(order):
    fake = Race()
    clients = ns(get_sync=lambda _:fake.client(), get_async=lambda _:fake.client(True))
    tools = [S._build_cancel_tool(clients), S._build_check_tool(clients)]
    graph = StateGraph(ParentState).add_node('tools', ToolNode(tools, handle_tool_errors=False)).add_edge(START,'tools').add_edge('tools',END).compile()
    calls = [dict(name=name+'_async_task', args={'task_id':'t1'}, id=name, type='tool_call') for name in order]
    return fake, graph, {'messages':[AIMessage(content='',tool_calls=calls)],'async_tasks':{'t1':record()}}

for order in (('cancel','check'),('check','cancel')):
    for asynchronous in (False,True):
        f, graph, inputs = fixture(order)
        result = asyncio.run(graph.ainvoke(inputs)) if asynchronous else graph.invoke(inputs)
        status = result['async_tasks']['t1']['status']
        assert status == ('running' if order[-1]=='check' else 'cancelled') and f.status == 'interrupted'
        print('parallel',order,'async',asynchronous, 'remote',f.status,'checkpoint update',status)

def server(status, latest):
    reads = []
    def get_thread(**_):
        return {'status':status,'values':{'messages':[{'role':'assistant','content':'new result'}]}}
    def list_runs(**_):
        reads.append('latest')
        return [{'run_id':'r2','status':latest}]
    client = ns(runs=ns(get=lambda **_: {'run_id':'r1','status':'success'}, list=list_runs),threads=ns(get=get_thread))
    return client, reads

for thread_status, latest_status, expect_id, expect_status in [
    ('interrupted','success','r1','waiting'),
    ('busy','running','r2','running'),
    ('idle','success','r1','success'),
    ('error','error','r2','error'),
]:
    client, reads = server(thread_status, latest_status)
    run, thread = S._observe(client, record('waiting'))
    result = S._build_check_result(run,'t1',thread)
    assert (run['run_id'],result['status'])==(expect_id,expect_status)
    print('observe',thread_status,'stored',run['run_id'],'status',result['status'],'latest lookup',bool(reads),'result',result.get('result'))

# Cached filtering must match the same record that can become successful on an unfiltered read.
client, reads = server('idle','success')
tool = S._build_list_tasks_tool(ns(get_sync=lambda _: client))
assert isinstance(tool.func(runtime(record('running')),status_filter='success'),str)
unfiltered = tool.func(runtime(record('running')),status_filter='all')
assert unfiltered.update['async_tasks']['t1']['status']=='success'
print('list: success filter returned no record, all refreshed it to success')

message = S._notification_message(S._event('t1','worker','success','r1',result=[{'type':'text','text':'worker completed'}]))
message = S.convert_to_messages([message])[0]
hook = S.AsyncSubAgentMiddleware._record_notification
status = record('running', 'r2')
stale = hook({'async_tasks':{'t1':status},'messages':[message]})
queued = hook({'async_tasks':{'t1':{**status,'superseded_run_ids':['r1']}},'messages':[message]})
assert stale['async_tasks']['t1']['run_id']=='r1' and 'async_tasks' not in queued
print('notification: old r1 overwrites r2 when no superseded id; queued control rewrites the message without modifying state')

async def pull_control():
    S._PULL_TIMEOUT_SECONDS = .03
    slow_started, slow_cancelled = asyncio.Event(), asyncio.Event()
    async def run_get(**kwargs):
        if kwargs['thread_id']=='slow':
            slow_started.set()
            try:
                await asyncio.Future()
            finally:
                slow_cancelled.set()
        await slow_started.wait()
        return {'run_id':'r1','status':'error'}
    m=S.AsyncSubAgentMiddleware()
    m._clients=ns(get_async=lambda _:ns(runs=ns(get=run_get)))
    updates=await m._apull({'slow':record(task_id='slow'),'fast':record(task_id='fast')})
    assert slow_cancelled.is_set() and updates['async_tasks']['fast']['status']=='error' and 'slow' not in updates['async_tasks']
    print('pull: unfinished laggard cancelled, peer error recorded, notification count',len(updates['messages']))

async def notification_control():
    async def read(**kwargs):
        return {'status':'idle'}
    async def reject(**kwargs):
        raise RuntimeError('simulated run dispatch failure')
    notified = {'task_id':'t1','agent_name':'worker','status':'success','run_id':'r1','result':[{'type':'text','text':'done'}]}
    S.get_client = lambda:ns(threads=ns(get=read),runs=ns(create=reject))
    await S._awake_parent('parent','assistant',notified)
    def broken_client():
        raise ValueError('simulated client construction error')
    S.get_client = broken_client
    try:
        await S._awake_parent('parent','assistant',notified)
    except ValueError:
        print('notification: dispatch exception suppressed; client construction exception escaped')
    else:
        raise AssertionError('client construction exception unexpectedly swallowed')

asyncio.run(pull_control())
asyncio.run(notification_control())
PY
```

</details>

<details>
<summary>Inline task integration with real subgraphs</summary>

```bash
cd "$da_repo/libs/deepagents"
da_offline "$da_scratch/deps" python -B - <<'PY'
from __future__ import annotations
import __future__, ast, asyncio, logging, sys, threading, types
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, ToolRuntime
from langgraph.types import Command

def load_nodes(path, module, wanted, *, keep_imports=False, methods=None):
    tree = ast.parse(Path(path).read_text())
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = str(getattr(node, 'module', ''))
            if keep_imports and not names.startswith(('deepagents', 'langchain.')):
                selected.append(node)
        names = {getattr(node, 'name', None)}
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {n.id for n in targets if isinstance(n, ast.Name)}
        if names & wanted:
            if methods and isinstance(node, ast.ClassDef) and node.name in methods:
                node.bases = []
                node.body = [part for part in node.body if getattr(part, 'name', None) in methods[node.name]]
            selected.append(node)
    body = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(body, path, 'exec', flags=__future__.annotations.compiler_flag), module.__dict__)

import operator
from langchain_core.messages import AnyMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import get_runtime
source=types.ModuleType('task_subject')
sys.modules[source.__name__]=source
source.ToolRuntime=ToolRuntime
source.__dict__.update(AnyMessage=AnyMessage, BaseMessage=BaseMessage, AIMessage=AIMessage, HumanMessage=HumanMessage, ToolMessage=ToolMessage)
source.__dict__.update(_RUBRIC_KEY='rubric', _SKILL_TOOLS_DISCLOSED_KEY='_skill_tools_disclosed', SUMMARIZATION_EVENT_KEY='_summarization_event', SUMMARIZATION_SESSION_ID_KEY='_summarization_session_id')
# The pinned dependency's refusal exception symbols are absent in this fallback environment.
# These distinct sentinels keep the irrelevant catch branches narrow.
source.ModelRefusalError=type('UnusedRefusalFixture', (Exception,), {})
source.StructuredOutputValidationError=type('UnusedOutputFixture', (Exception,), {})
task_path='deepagents/middleware/subagents.py'
names=set('SUBAGENT_RESPONSE_FORMAT_CONFIG_KEY _FORK_EXCLUDED_STATE_KEYS _FORKED_CONTEXT_KEY _FORK_INSTRUCTIONS_KEY _FORK_RECURSION_REFUSAL _refusal_notice _refusal_in _refusal_notice_for _validate_subagent_mode _validate_unique_subagent_names _is_forked_subagent _is_compiled_subagent _is_forked_compiled_subagent _FORK_TASK_PREAMBLE _fork_messages _EXCLUDED_STATE_KEYS _is_unchanged _TASK_TOOL_INJECTED_ARGS TaskToolSchema TASK_TOOL_DESCRIPTION _FORKED_SUBAGENT_TOOL_NOTE _describe_subagent_for_tool _subagent_tracing_context _get_subagent_response_format _compiled_graph _SUBAGENT_STREAM_MODES _run_subagent _arun_subagent _build_task_tool'.split())
tree=ast.parse(Path(task_path).read_text())
imports=[
    n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))
    and not (getattr(n,'module','') or '').startswith(('langchain.', 'deepagents.', 'langchain_core.messages','langchain_core.exceptions'))
]
exec(compile(ast.Module(body=imports,type_ignores=[]),task_path,'exec',flags=__future__.annotations.compiler_flag),source.__dict__)
load_nodes(task_path,source,names)
S=source

from langgraph.channels.delta import DeltaChannel
pkg = types.ModuleType('deepagents')
pkg.__path__ = [str(Path('deepagents').resolve())]
sys.modules['deepagents'] = pkg
from deepagents._messages_reducer import _messages_delta_reducer
from deepagents.backends.composite import CompositeBackend
from deepagents.backends.protocol import FileData
from deepagents.backends.state import StateBackend
from deepagents.backends.store import StoreBackend
from deepagents.backends.utils import create_file_data

path = 'deepagents/middleware/filesystem.py'
tree = ast.parse(Path(path).read_text())
node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_file_data_delta_reducer')
exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'))

class FileState(TypedDict, total=False):
    files: Annotated[dict[str,FileData], DeltaChannel(_file_data_delta_reducer, snapshot_frequency=50)]
    answer: str

backend=StateBackend()
def file_content(result):
    assert result.error is None and result.file_data is not None, result
    data = result.file_data['content']
    return data if isinstance(data,str) else '\n'.join(data)


class SubState(TypedDict, total=False):
    messages: Annotated[list,add_messages]
    files: Annotated[dict[str,FileData], DeltaChannel(_file_data_delta_reducer, snapshot_frequency=50)]
    count: Annotated[int,operator.add]
    payload: str
    hidden: str

def child(name,action,**kwargs):
    graph=StateGraph(SubState).add_node('worker', action).add_edge(START,'worker').add_edge('worker',END).compile(name=name,**kwargs)
    return {'name':name,'description':'fixture '+name,'runnable':graph}

def action(update):
    def run(state):
        context=get_runtime().context
        assert 'hidden' not in state
        assert len(state['messages'])==1 and isinstance(state['messages'][0],HumanMessage)
        output=update(state)
        return {**output,'messages':[AIMessage(content=f'child done context={context!r}')], 'hidden':'child-owned'}
    return run

def execute(specs,files,*,asynchronous=False):
    tool=S._build_task_tool(specs,private_state_keys=frozenset({'hidden'}))
    graph=StateGraph(SubState).add_node('tools', ToolNode([tool],handle_tool_errors=False)).add_edge(START,'tools').add_edge('tools',END).compile(checkpointer=InMemorySaver())
    req={'count':10,'files':{p:create_file_data(v) for p,v in files.items()},'payload':'equal','hidden':'parent-owned',
         'messages':[HumanMessage(content='private conversation before delegation'),
                     AIMessage(content='',tool_calls=[{'name':'task','args':{'description':'task for '+spec['name'],'subagent_type':spec['name']}, 'id':'call-'+spec['name']} for spec in specs])]}
    cfg={'configurable':{'thread_id':'parent-trial'}}
    context={'request':'context fixture'}
    actual=asyncio.run(graph.ainvoke(req,cfg,context=context)) if asynchronous else graph.invoke(req,cfg,context=context)
    assert actual['hidden']=='parent-owned' and actual['payload']=='equal'
    for item in actual['messages'][2:]:
        assert isinstance(item,ToolMessage) and 'context fixture' in item.content, item
        assert item.artifact and item.artifact['checkpoint_ns'], item
    return actual

for n, delta in [(1,0),(1,1),(2,1)]:
    for asynchronous in [False,True]:
        actual=execute([child(str(i),action(lambda _: {'count':delta})) for i in range(n)],{},asynchronous=asynchronous)
        expected=10 if delta==0 else 10+n*11
        assert actual['count']==expected
        print('subagent aggregate', 'children',n,'child delta',delta,'async',asynchronous,'expected from true deltas',10+n*delta,'observed',actual['count'])

def edit(path, before, after):
    def run(_):
        assert backend.edit(path,before,after).error is None
        assert file_content(backend.read(path))==after
        return {}
    return action(run)
for asynchronous in (False,True):
    files={'/a':'old a','/b':'old b'}
    actual=execute([child('one',edit('/a','old a','new a')),child('two',edit('/b','old b','new b'))],files,asynchronous=asynchronous)
    got={k:v['content'] for k,v in actual['files'].items()}
    assert got in ({'/a':'new a','/b':'old b'},{'/a':'old a','/b':'new b'}), got
    print('subagent parallel edits on separate existing files',asynchronous,got)
    single=execute([child('one',edit('/a','old a','new a'))],files,asynchronous=asynchronous)
    assert single['files']['/a']['content']=='new a'
    def deletion(_):
        assert backend.delete('/a').error is None
        assert backend.read('/a').error is not None
        return {}
    deleted=execute([child('deleted',action(deletion))],files,asynchronous=asynchronous)
    assert '/a' in deleted['files']
    print('subagent delete',asynchronous,'child did not see file, parent files',sorted(deleted['files']))
PY
```

</details>

<details>
<summary>State and store transfers, replay, and checkpoint byte accounting</summary>

```bash
cd "$da_repo/libs/deepagents"
da_offline "$da_scratch/deps" python -B - <<'PY'
from __future__ import annotations
import ast, asyncio, sys, threading, types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.channels.delta import DeltaChannel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command, interrupt

pkg = types.ModuleType('deepagents')
pkg.__path__ = [str(Path('deepagents').resolve())]
sys.modules['deepagents'] = pkg
from deepagents._messages_reducer import _messages_delta_reducer
from deepagents.backends.composite import CompositeBackend
from deepagents.backends.protocol import FileData
from deepagents.backends.state import StateBackend
from deepagents.backends.store import StoreBackend
from deepagents.backends.utils import create_file_data

path = 'deepagents/middleware/filesystem.py'
tree = ast.parse(Path(path).read_text())
node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_file_data_delta_reducer')
exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'))

class FileState(TypedDict, total=False):
    files: Annotated[dict[str,FileData], DeltaChannel(_file_data_delta_reducer, snapshot_frequency=50)]
    answer: str

backend=StateBackend()
def file_content(result):
    assert result.error is None and result.file_data is not None, result
    data = result.file_data['content']
    return data if isinstance(data,str) else '\n'.join(data)

def state_control(parallel, separate):
    branch = StateGraph(FileState)
    path2 = '/second' if separate else '/sample'
    gate = threading.Barrier(2)
    steps = []
    def action(path, old, new):
        def run(_):
            before = file_content(backend.read(path))
            if parallel:
                gate.wait(5)
            edited = backend.edit(path, old, new)
            steps.append((new,before,file_content(backend.read(path))))
            assert edited.error is None and edited.occurrences==1
            return {}
        return run
    branch.add_node('first', action('/sample','alpha','A'))
    branch.add_node('second', action(path2,'beta','B'))
    branch.add_edge(START,'first')
    branch.add_edge(START if parallel else 'first','second')
    branch.add_edge('second',END)
    compare=branch.compile(checkpointer=InMemorySaver())
    cfg={'configurable':{'thread_id':'samples'}}
    files={'/sample':create_file_data('alpha beta'),'/second':create_file_data('alpha beta')}
    compare.invoke({'files':files}, cfg)
    values=compare.get_state(cfg).values['files']
    finals = (values['/sample']['content'],values['/second']['content'])
    print('state files',parallel,separate, sorted(steps), finals)
    if separate:
        assert finals==('A beta','alpha B')
    elif parallel:
        assert finals[0] in {'A beta','alpha B'} and all(v[1]=='alpha beta' for v in steps)
    else:
        assert finals[0]=='A B'

state_control(True,False)
state_control(False,False)
state_control(True,True)

class BarrierStore(InMemoryStore):
    gate = None
    def get(self,*args,**kwargs):
        value=super().get(*args,**kwargs)
        if self.gate is not None:
            self.gate.wait(5)
        return value
store=BarrierStore()
routed=lambda ns: StoreBackend(store=store, namespace=lambda _: (ns,))
S=routed('edit-control')
for parallel in (True,False):
    assert S.write('/file','alpha beta').error is None
    if parallel:
        store.gate=threading.Barrier(2)
        with ThreadPoolExecutor(2) as pool:
            rs=[pool.submit(S.edit,'/file',a,b) for a,b in [('alpha','A'),('beta','B')]]
            rs=[f.result(timeout=6) for f in rs]
        store.gate=None
    else:
        rs=[S.edit('/file','alpha','A'),S.edit('/file','beta','B')]
    final=file_content(S.read('/file'))
    assert all(x.error is None and x.occurrences == 1 for x in rs)
    assert final in ({'A beta','alpha B'} if parallel else {'A B'})
    print('store edits parallel=',parallel,'successes=', len(rs),'final=',repr(final))

for shared in (True,False):
    left,right=routed('left-'+str(shared)),routed('left-'+str(shared) if shared else 'right')
    composite=CompositeBackend(default=routed('unused'),routes={'/left/':left,'/right/':right})
    assert composite.write('/left/hello.txt','contains needle').error is None
    opposite=composite.read('/right/hello.txt')
    results=composite.grep('needle',path='/').matches
    paths=sorted(x['path'] for x in results)
    assert paths==(['/left/hello.txt','/right/hello.txt'] if shared else ['/left/hello.txt'])
    assert (opposite.error is None)==shared
    print('route scope shared namespace=',shared, 'visible paths',paths)

def replay_control(sqlite=False):
    signals=[]
    def pre_step(_):
        signals.append('separate predecessor')
        assert backend.write('/committed','ready').error is None
        return {}
    def approval(_):
        signals.append('before interrupt')
        assert backend.write('/pending','this write belongs to task').error is None
        decision=interrupt({'question':'Continue?'})
        signals.append('after interrupt')
        return {'answer':decision}
    builder=StateGraph(FileState).add_node('pre_step',pre_step).add_node('approval',approval).add_edge(START,'pre_step').add_edge('pre_step','approval').add_edge('approval',END)
    cfg={'configurable':{'thread_id':'same'}}
    database=Path.home()/'replay-checkpoint.db'
    resource=lambda: SqliteSaver.from_conn_string(str(database)) if sqlite else InMemorySaver()
    with resource() as saver:
        first=builder.compile(checkpointer=saver)
        first.invoke({'files':{}},cfg,durability='sync')
        stopped=first.get_state(cfg)
        assert set(stopped.values['files'])=={'/committed'} and len(stopped.interrupts)==1
        assert signals==['separate predecessor','before interrupt']
        if not sqlite:
            check_resume(first,cfg,stopped,signals)
    if sqlite:
        with resource() as new_saver:
            restarted=builder.compile(checkpointer=new_saver)
            loaded=restarted.get_state(cfg)
            assert loaded.interrupts[0].id==stopped.interrupts[0].id
            assert not restarted.get_state({'configurable':{'thread_id':'other'}}).values
            check_resume(restarted,cfg,loaded,signals)
    print('interrupt', 'sqlite reopen' if sqlite else 'memory', signals)

def check_resume(graph,cfg,paused,signals):
    graph.invoke(Command(resume={paused.interrupts[0].id:'allow'}),cfg,durability='sync')
    result=graph.get_state(cfg)
    assert result.values['answer']=='allow' and not result.interrupts
    assert set(result.values['files'])=={'/committed','/pending'}
    assert signals==['separate predecessor','before interrupt','before interrupt','after interrupt']

replay_control()
replay_control(True)

class FullState(TypedDict):
    n: int
    i: int
    messages: Annotated[list,add_messages]
class DeltaState(TypedDict):
    n: int
    i: int
    messages: Annotated[list,DeltaChannel(_messages_delta_reducer,snapshot_frequency=50)]
class DeltaWideState(TypedDict):
    n: int
    i: int
    messages: Annotated[list,DeltaChannel(_messages_delta_reducer,snapshot_frequency=100000)]

def add(s):
    i=s['i']+1
    return {'i':i,'messages':[HumanMessage(content='x'*256,id=f'm{i:06d}')]}
def again(s):
    return 'add' if s['i']<s['n'] else END

def measure(state,n):
    saver=InMemorySaver()
    graph=StateGraph(state).add_node('add',add).add_edge(START,'add').add_conditional_edges('add',again).compile(checkpointer=saver)
    config={'configurable':{'thread_id':'test'},'recursion_limit':n+5}
    graph.invoke({'i':0,'n':n,'messages':[]},config,durability='sync')
    messages=graph.get_state(config).values['messages']
    assert len(messages)==n and messages[0].id=='m000001' and messages[-1].id==f'm{n:06d}'
    blobs=[len(data) for (_,_,channel,_),(_,data) in saver.blobs.items() if channel=='messages' and data]
    writes=sum(len(data) for batch in saver.writes.values() for _,channel,(_,data),_ in batch.values() if channel=='messages')
    return len(blobs),sum(blobs),writes

for n in (100,200,400,800):
    print('storage', n, {s.__name__:measure(s,n) for s in (FullState,DeltaState,DeltaWideState)},flush=True)
PY
```

</details>

<details>
<summary>Context budget and archive append controls</summary>

```bash
cd "$da_repo/libs/deepagents"
da_offline "$da_scratch/deps" python -B - <<'PY'
from __future__ import annotations
import __future__, ast, asyncio, logging, sys, threading, types
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, ToolRuntime
from langgraph.types import Command

def load_nodes(path, module, wanted, *, keep_imports=False, methods=None):
    tree = ast.parse(Path(path).read_text())
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = str(getattr(node, 'module', ''))
            if keep_imports and not names.startswith(('deepagents', 'langchain.')):
                selected.append(node)
        names = {getattr(node, 'name', None)}
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {n.id for n in targets if isinstance(n, ast.Name)}
        if names & wanted:
            if methods and isinstance(node, ast.ClassDef) and node.name in methods:
                node.bases = []
                node.body = [part for part in node.body if getattr(part, 'name', None) in methods[node.name]]
            selected.append(node)
    body = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(body, path, 'exec', flags=__future__.annotations.compiler_flag), module.__dict__)

from collections.abc import Mapping
from datetime import UTC, datetime
from langchain_core.exceptions import ContextOverflowError
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, ToolMessage, get_buffer_string
from typing import Any, Never, cast
import operator

for name in ('deepagents','deepagents.middleware'):
    pkg=types.ModuleType(name)
    pkg.__path__=[str(Path(*name.split('.')).resolve())]
    sys.modules[name]=pkg
    if '.' in name:
        sys.modules['deepagents'].middleware=pkg
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.protocol import FileDownloadResponse
from deepagents.middleware._overflow_clip import _aclip_overflow_tail, _clip_overflow_tail
from langgraph.types import Command

logging.basicConfig(level=logging.CRITICAL)
source=types.ModuleType('summary_subject')
sys.modules[source.__name__]=source
source.__dict__.update({key: value for key,value in globals().items() if not key.startswith('__')})
source.logger=logging.getLogger('summary_subject')
names={'_is_context_overflow','_resolve_cutoff_index','_bound_reasoning_types','_drop_bound_reasoning','_DeepAgentsSummarizationMiddleware'}
keep={'_get_history_path','_is_summary_message','_filter_summary_messages','_apply_event_to_messages','_offload_to_backend','_aoffload_to_backend',
      '_input_budget','_over_budget','_check_reduction','_raise_recovery_exhausted','_call_with_budget','_acall_with_budget'}
load_nodes('deepagents/middleware/summarization.py',source,names,methods={'_DeepAgentsSummarizationMiddleware':keep})
subject=source._DeepAgentsSummarizationMiddleware()
subject._history_path_prefix='/history'
subject._large_tool_results_prefix='/large_tool_results'
subject._get_profile_limits=lambda: 3000
subject.token_counter=lambda messages: sum(len(m.text)//4 for m in messages)
subject._count_tokens=lambda messages,system,tools: subject.token_counter(messages) + (len(system.text)//4 if system else 0) + sum(tools)
subject._backend=FilesystemBackend(root_dir=str(Path.home()/'summary-budget'),virtual_mode=True)

class OneReadFails(FilesystemBackend):
    error = None
    def download_files(self,paths):
        failure,self.error=self.error,None
        if failure=='oserror':
            raise OSError('simulated unreadable backend response')
        if failure=='denied':
            return [FileDownloadResponse(p,error='permission_denied') for p in paths]
        return super().download_files(paths)

def archive_control(asynchronous):
    backend=OneReadFails(root_dir=str(Path.home()/('summary-async' if asynchronous else 'summary-sync')),virtual_mode=True)
    def append(text,sid):
        args=(backend,[HumanMessage(text)],sid)
        return asyncio.run(subject._aoffload_to_backend(*args)) if asynchronous else subject._offload_to_backend(*args)
    for mode in ('normal','oserror','denied'):
        sid='trial-'+mode
        path=append('first archived marker',sid)
        assert path
        backend.error=None if mode=='normal' else mode
        assert append('second archived marker',sid)==path
        new=backend.download_files([path])[0].content.decode()
        assert 'second archived marker' in new
        assert ('first archived marker' in new)==(mode=='normal')
        print('summary append','async',asynchronous,mode,'old marker retained','first archived marker' in new)

archive_control(False)
archive_control(True)

def human(i): return HumanMessage(content=f'turn {i}',id=f'm{i}')
h=[human(i) for i in range(7)]
event={'cutoff_index':4,'cutoff_message_id':'m4','summary_message':HumanMessage('summary',id='s'), 'file_path':None}
for name,history in [('original',h),('trim older',h[3:]),('trim through cutoff',h[5:])]:
    projected=[m.id for m in subject._apply_event_to_messages(history,event)]
    assert projected==(['s'] if name=='trim through cutoff' else ['s','m4','m5','m6'])
    print('summary projection',name,projected)

class Request:
    def __init__(self,messages,system=None,limit=3000,tools=()):
        self.messages=messages
        self.system_message=system
        self.tools=tools
        self.model=types.SimpleNamespace(profile={'max_input_tokens':limit} if limit is not None else {})
        self.model_settings={}
    def override(self,*,messages):
        return Request(messages,self.system_message,self.model.profile.get('max_input_tokens'),self.tools)
class ProviderError(Exception):
    def __init__(self,code,message):
        super().__init__(message)
        self.status_code=code
normal=Request([HumanMessage('small')])
unreducible=Request([HumanMessage('small')],system=SystemMessage('Z'*15000))
options=Request([AIMessage('',tool_calls=[dict(name='read_file',id='r',args={'file_path':'/memo'})]),ToolMessage('Z'*16000,tool_call_id='r',id='m-tail')],limit=None)
for async_mode in (False,True):
    for mode, call in [('simple',normal),('irreducible',unreducible),('429',normal),('retry',options),('again',options)]:
        observed=[]
        def handler(request):
            observed.append(subject.token_counter(request.messages))
            if mode=='429':
                raise ProviderError(429,'rate limit')
            if mode=='again' or (mode=='retry' and len(observed)==1):
                raise ProviderError(400,'maximum context length exceeded')
            return 'ok'
        async def ahandler(r):return handler(r)
        return_value=None
        try:
            return_value=asyncio.run(subject._acall_with_budget(call,ahandler)) if async_mode else subject._call_with_budget(call,handler)
        except (ContextOverflowError,ProviderError) as error:
            outcome=type(error).__name__
        else:
            outcome=return_value[0]
        expected={'simple':('ok',1),'irreducible':('ContextOverflowError',0),'429':('ProviderError',1),'retry':('ok',2),'again':('ContextOverflowError',2)}
        assert (outcome,len(observed))==expected[mode]
        if mode in {'retry','again'}: assert observed[1]<observed[0]
        if mode=='retry': assert return_value[1][0].id=='m-tail'
        print('budget','async',async_mode,mode,outcome,observed)
PY
```

</details>

<details>
<summary>Example server suite and in-process ASGI integration</summary>

```bash
cd "$da_repo/examples/async-subagent-server"
for DA_EXAMPLE_VARIANT in suite control; do
    da_offline "$da_scratch/example-deps:$da_scratch/deps" \
        env DA_EXAMPLE_MODE="$DA_EXAMPLE_VARIANT" python -B - <<'PY'
import ast, asyncio, os, sys, types
from pathlib import Path

import httpx
from langchain_core.messages import AIMessage
from langgraph_sdk.client import LangGraphClient

def load_example():
    source=Path('server.py')
    tree=ast.parse(source.read_text())
    module=types.ModuleType('server')
    module.__file__=str(source.resolve())
    sys.modules['server']=module
    def keep(node):
        if isinstance(node,ast.ImportFrom) and node.module in ('dotenv','langchain_anthropic','deepagents'):
            return False
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and getattr(node.value.func,'id',None)=='load_dotenv':
            return False
        if isinstance(node,ast.Assign) and any(getattr(t,'id',None)=='_agent' for t in node.targets):
            return False
        return True
    tree.body=[n for n in tree.body if keep(n)]
    async def prohibited(*args,**kwargs):
        raise AssertionError('provider fixture was not installed')
    module._agent=types.SimpleNamespace(ainvoke=prohibited)
    exec(compile(tree, str(source.resolve()),'exec'), module.__dict__)
    module._init_db()
    return module

server=load_example()
if os.getenv('DA_EXAMPLE_MODE')=='suite':
    import pytest
    raise SystemExit(pytest.main(['-c','/dev/null','-p','no:cacheprovider','--basetemp',str(Path.home()/'pt-example'),'-q','-ra','--tb=short','test_server.py']))

async def check():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://example') as http:
        sdk=LangGraphClient(http)
        caller_started = asyncio.Event()
        unstick = asyncio.Event()

        async def wait_for_gate(payload):
            caller_started.set()
            await unstick.wait()
            return {'messages':[AIMessage(content='completed despite cancellation request')]}
        server._agent.ainvoke=wait_for_gate

        thread=await sdk.threads.create()
        thread_id=thread['thread_id']
        run=await sdk.runs.create(thread_id=thread_id,assistant_id='worker',input={'messages':[{'role':'user','content':'fake work'}]})
        run_id=run['run_id']
        await asyncio.wait_for(caller_started.wait(),2)
        workers=[t for t in asyncio.all_tasks() if t.get_coro().__qualname__=='_execute_run']
        assert len(workers)==1
        status=lambda: sdk.runs.get(thread_id=thread_id,run_id=run_id)
        assert (await status())['status']=='running'
        await sdk.runs.cancel(thread_id=thread_id,run_id=run_id)
        assert (await status())['status']=='cancelled' and not workers[0].done() and not workers[0].cancelling()
        unstick.set()
        await asyncio.wait_for(workers[0],2)
        assert (await status())['status']=='success'
        final=(await sdk.threads.get(thread_id=thread_id))['values']['messages'][-1]['content']
        assert final=='completed despite cancellation request'
        print('example cancel:', 'pending -> running -> cancelled -> success; worker was never sent cancellation')

        seen=[]
        async def echo(payload):
            seen.append([m.content for m in payload['messages']])
            return {'messages':[AIMessage(content='ok')]}
        server._agent.ainvoke=echo
        messages=[{'role':'user','content':'old user turn'},{'role':'assistant','content':'old answer'},{'role':'user','content':'new task'}]
        send=await sdk.runs.create(thread_id=thread_id,assistant_id='worker',input={'messages':messages})
        for _ in range(8):
            if (await sdk.runs.get(thread_id=thread_id,run_id=send['run_id']))['status']=='success':
                break
            await asyncio.sleep(0)
        assert seen==[['old user turn']],seen
        print('example fork-like ASGI payload:',seen,'control current single input ok')

        # Single-current-message, complete-run control on the same transport.
        send=await sdk.runs.create(thread_id=thread_id,assistant_id='worker',input={'messages':[{'role':'user','content':'current'}]})
        for _ in range(8):
            if (await sdk.runs.get(thread_id=thread_id,run_id=send['run_id']))['status']=='success':
                break
            await asyncio.sleep(0)
        assert seen[-1]==['current']
        print('example single-input lifecycle:',seen[-1],'status',(await sdk.runs.get(thread_id=thread_id,run_id=send['run_id']))['status'])

asyncio.run(check())
PY
done
```

</details>

<details>
<summary>Code ownership, event bus and saver adapter</summary>

This variant loads only the classes used by the adapter tests from the cached upstream file. For the original negative omit the extraction and invoke the three pytest paths directly with the same options and without the selection filter.

```bash
cd "$da_repo/libs/code"
da_offline "$PWD:$da_scratch/deps314" python3.14 -B - <<'PY'
from __future__ import annotations
import ast, sys, types
from dataclasses import dataclass
from pathlib import Path

import pytest
from langgraph.checkpoint.base import BaseCheckpointSaver

name='langgraph_api._checkpointer._adapter'
for path in ('langgraph_api','langgraph_api._checkpointer',name):
    mod=types.ModuleType(path)
    if path!=name: mod.__path__=[]
    sys.modules[path]=mod
    if '.' in path:
        parent,leaf=path.rsplit('.',1)
        setattr(sys.modules[parent],leaf,mod)
adapter=sys.modules[name]
adapter.__dict__.update(BaseCheckpointSaver=BaseCheckpointSaver,dataclass=dataclass)
source=Path.home()/'lg-api-adapter-0.17.1.py'
tree=ast.parse(source.read_text())
selected=[]
wanted={'CheckpointerCapabilities','_CustomCheckpointerAdapter','_validate_required_methods','_is_overridden'}
for node in tree.body:
    if isinstance(node,ast.ImportFrom) and node.module=='__future__':
        selected.append(node)
    if getattr(node,'name',None) in wanted or (
        isinstance(node,ast.Assign) and any(getattr(t,'id',None)=='_REQUIRED' for t in node.targets)
    ):
        selected.append(node)
exec(compile(ast.Module(body=selected,type_ignores=[]),str(source),'exec'),adapter.__dict__)
raise SystemExit(pytest.main(['-c','/dev/null','--noconftest','-p','pytest_asyncio.plugin','-p','no:cacheprovider','-o','asyncio_mode=auto','-o','asyncio_default_fixture_loop_scope=function','--basetemp',str(Path.home()/'pt-code-recheck'),'-q','-ra','--tb=short','-k','not failed_server_restart','tests/unit_tests/test_thread_ownership.py','tests/unit_tests/test_checkpointer_adapter.py','tests/unit_tests/test_event_bus.py']))
PY
```

</details>

<details>
<summary>Code retry helper controls</summary>

```bash
cd "$da_repo/libs/code"
da_offline "$da_scratch/deps314" python3.14 -B - <<'PY'
from __future__ import annotations
import ast, asyncio, sys, types
from pathlib import Path

import httpx
from langgraph.errors import GraphBubbleUp

path=Path('deepagents_code/model_retry.py')
tree=ast.parse(path.read_text())
source=types.ModuleType('retry_subject')
sys.modules[source.__name__]=source
wanted=set('_INITIAL_DELAY_SECONDS _BACKOFF_FACTOR _MAX_DELAY_SECONDS _MAX_RETRY_AFTER_SECONDS _JITTER_FRACTION _RETRYABLE_STATUS_CODES _TRANSIENT_SDK_EXC_NAMES _HTTP_SERVER_ERROR_FLOOR _HTTP_SERVER_ERROR_CEILING _google_api_core_status_code _extract_status_code _retry_after_seconds _backoff_delay _compute_backoff_delay _retry_delay_seconds _is_transient_sdk_error _is_http_transport_error _direct_model_error_retryability _is_retryable_model_error GroqToolLimitError _is_groq_tool_limit_error _log_give_up _retry_call _aretry_call _delay_budget_guard logger'.split())
nodes=[]
for node in tree.body:
    if isinstance(node,(ast.Import,ast.ImportFrom)) and not (getattr(node,'module','') or '').startswith(('deepagents_code','langchain.')):
        nodes.append(node)
    elif getattr(node,'name',None) in wanted or (
        isinstance(node,ast.Assign) and any(getattr(t,'id',None) in wanted for t in node.targets)
    ):
        nodes.append(node)
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),source.__dict__)
class HttpFailure(Exception):
    def __init__(self,code,delay=None):
        super().__init__(str(code))
        self.status_code=code
        self.response=types.SimpleNamespace(headers={'Retry-After':str(delay)} if delay is not None else {})

for exc,expected in [(HttpFailure(403),False),(HttpFailure(429),True),(HttpFailure(503),True),
                     (ExceptionGroup('wrapper',[httpx.ConnectError('mock')]),True),
                     (httpx.UnsupportedProtocol('mock'),False)]:
    assert source._is_retryable_model_error(exc)==expected
    print(type(exc).__name__,getattr(exc,'status_code',None),'retryable',expected)
assert source._retry_after_seconds(HttpFailure(429,999))==60.0
assert source._retry_after_seconds(HttpFailure(429,0)) is None
print('Retry-After numeric cap 60s; zero falls back')
for asynchronous in (False, True):
    for case in ('eventual success','budget','permanent','graph control'):
        seen=[]
        notices=[]
        failure=GraphBubbleUp('control') if case=='graph control' else HttpFailure(403 if case=='permanent' else 429,.004)
        def call():
            seen.append(len(seen))
            if case=='eventual success' and len(seen)==2: return 'good'
            raise failure
        async def acall():
            return call()
        opts=dict(max_retries=3,on_retry=lambda i,*_:notices.append(i),retry_guard=source._delay_budget_guard(.006))
        try:
            result=asyncio.run(source._aretry_call(acall,**opts)) if asynchronous else source._retry_call(call,**opts)
        except (HttpFailure,GraphBubbleUp) as error:
            assert error is failure
            result='original error'
        assert len(seen)==(2 if case in ('budget','eventual success') else 1)
        assert len(notices)==len(seen)-1
        print('retry',asynchronous,case,result,len(seen),notices)
PY
```

</details>

<details>
<summary>Talon conversation saver and SQLite storage</summary>

```bash
cd "$da_repo/libs/talon"
da_offline "$PWD/../code:$da_scratch/deps314" python3.14 -B - <<'PY'
import ast, sys, types
from pathlib import Path
import pytest
module = types.ModuleType('deepagents_talon')
module.__path__ = [str(Path('deepagents_talon').resolve())]
sys.modules[module.__name__] = module
source = Path('tests/archive_helpers.py')
tree = ast.parse(source.read_text())
tree.body = [n for n in tree.body
             if not (isinstance(n,ast.ImportFrom) and n.module=='deepagents_talon.runtime')
             and getattr(n,'name',None) != 'make_runtime']
helpers=types.ModuleType('tests.archive_helpers')
helpers.__file__=str(source.resolve())
sys.modules[helpers.__name__] = helpers
exec(compile(tree,str(source.resolve()),'exec'), helpers.__dict__)
raise SystemExit(pytest.main(['-c','/dev/null','--noconftest','-p','pytest_asyncio.plugin','-p','no:cacheprovider','-o','asyncio_mode=auto','-o','asyncio_default_fixture_loop_scope=function','--basetemp',str(Path.home()/'pt-talon-archives'),'-q','-ra','--tb=short','tests/unit_tests/test_archive_saver.py']))
PY
```

</details>

<details>
<summary>Talon checkpoint and StoreArchive suite, and the tracked-source syntax sweep</summary>

```bash
cd "$da_repo/libs/talon"
da_offline "$da_scratch/deps314" python3.14 -B - <<'PY'
import sys, types
from pathlib import Path
import pytest
module = types.ModuleType('deepagents_talon')
module.__path__ = [str(Path('deepagents_talon').resolve())]
sys.modules[module.__name__] = module
raise SystemExit(pytest.main(['-c','/dev/null','--noconftest','-p','pytest_asyncio.plugin',
    '-p','no:cacheprovider','-o','asyncio_mode=auto','-o','asyncio_default_fixture_loop_scope=function',
    '--basetemp',str(Path.home()/'pt-talon'),'-q','-ra','--tb=short',
    'tests/unit_tests/test_checkpoint_backends.py','tests/unit_tests/test_store_archive.py']))
PY

cd "$da_repo"
python3.14 -B - <<'PY'
import subprocess
from pathlib import Path
paths = [Path(p.decode()) for p in subprocess.check_output(
    ['git','ls-files','-z','--','*.py']).split(b'\0') if p]
for path in paths:
    compile(path.read_bytes(), str(path), 'exec')
print(f'{len(paths)} tracked Python files syntax-compiled in memory')
PY
```

</details>


<details>
<summary>Reducer batching and private state marker controls</summary>

```bash
cd "$da_repo/libs/deepagents"
da_offline "$da_scratch/deps314" python3.14 -B - <<'PY'
from __future__ import annotations
import ast, logging, random, sys, types
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

pkg=types.ModuleType('deepagents')
pkg.__path__=[str(Path('deepagents').resolve())]
sys.modules['deepagents']=pkg
from deepagents._messages_reducer import _messages_delta_reducer

path=Path('deepagents/middleware/filesystem.py')
tree=ast.parse(path.read_text())
method=next(n for n in tree.body if getattr(n,'name',None)=='_file_data_delta_reducer')
exec(compile(ast.Module(body=[method], type_ignores=[]),str(path),'exec'))

rng=random.Random(20261119)
def folds(reducer,writes,stride):
    accumulated=None
    for start in range(0,len(writes),stride):
        accumulated=reducer(accumulated,writes[start:start+stride])
    return accumulated

for case in range(1000):
    messages=[]
    files=[]
    reference_messages={}
    reference_files={}
    for op_index in range(rng.randrange(1,65)):
        key=f'entry-{rng.randrange(12)}'
        mode=rng.randrange(12)
        if mode==0:
            messages.append([RemoveMessage(id=REMOVE_ALL_MESSAGES)])
            reference_messages.clear()
        elif mode<4:
            messages.append([RemoveMessage(id=key)])
            reference_messages.pop(key,None)
        else:
            content=f'{case}-{op_index}'
            messages.append([HumanMessage(id=key,content=content)])
            reference_messages[key]=content
        file_value=None if mode<4 else {'content':str(op_index)}
        files.append({key:file_value})
        if file_value is None:
            reference_files.pop(key,None)
        else:
            reference_files[key]=file_value
    for stride in (1,3,11,len(messages)):
        observed_messages=folds(_messages_delta_reducer,messages,stride)
        assert [(m.id,m.content) for m in observed_messages]==list(reference_messages.items())
        assert folds(_file_data_delta_reducer,files,stride)==reference_files
print('1,000 seeded operation sequences, four fold groupings, both reducers match the reference')

# Keep real typing semantics. The SDK's classifier uses identity on this marker.
PrivateStateAttr=object()
path=Path('deepagents/middleware/_state.py')
tree=ast.parse(path.read_text())
tree.body=[n for n in tree.body if not (isinstance(n,ast.ImportFrom) and n.module.startswith('langchain.'))]
exec(compile(tree,str(path),'exec'))

class Resolved(TypedDict):
    hidden: Annotated[str,PrivateStateAttr]
class Unresolved(TypedDict):
    also_hidden: Annotated[str,PrivateStateAttr]
    custom_field: ScopeNotInRuntime

assert private_state_field_names(Resolved)=={'hidden'}
assert private_state_field_names(Unresolved)==set()
assert private_state_field_names(Unresolved,Resolved)=={'hidden'}
print('unresolved reference skips every marker in its schema, independent schemas still collected')
PY
```

</details>

<details>
<summary>Talon retry after partial graph progress</summary>

```bash
cd "$da_repo/libs/talon"
da_offline "$PWD:$da_scratch/deps314" python3.14 -B - <<'PY'
from __future__ import annotations
import ast, asyncio, contextvars, logging, sys, types
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.channels.delta import DeltaChannel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

pkg=types.ModuleType('deepagents')
pkg.__path__=[str(Path('../deepagents/deepagents').resolve())]
sys.modules['deepagents']=pkg
from deepagents._messages_reducer import _messages_delta_reducer

source=Path('deepagents_talon/runtime.py')
tree=ast.parse(source.read_text())
clazz=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DeepAgentRuntime')
chosen=[n for n in clazz.body if getattr(n,'name',None)=='_invoke_payload_with_retries']
chosen.extend(n for n in tree.body if getattr(n,'name',None)=='_is_retryable')
sleep_durations=[]
async def no_delay(duration):
    sleep_durations.append(duration)
    await asyncio.sleep(0)
scope=dict(asyncio=types.SimpleNamespace(CancelledError=asyncio.CancelledError,sleep=no_delay),
           _HISTORY_SCOPE=contextvars.ContextVar('scope',default=None),
           logger=logging.getLogger('talon-retry-control'))
exec(compile(ast.Module(body=chosen,type_ignores=[]),str(source),'exec'),scope)
method=scope['_invoke_payload_with_retries']

class S(TypedDict,total=False):
    messages: Annotated[list,DeltaChannel(_messages_delta_reducer,snapshot_frequency=50)]
    mark: int

async def run(kind):
    entered=[]
    async def side_effect(state):
        entered.append('step-one')
        return {'mark':1}
    async def transient(state):
        entered.append('step-two')
        if entered.count('step-two')==1:
            raise ConnectionError('finite synthetic model transport failure')
        return {'mark':2}
    graph=StateGraph(S).add_node('one',side_effect).add_node('two',transient).add_edge(START,'one').add_edge('one','two').add_edge('two',END).compile(checkpointer=InMemorySaver())
    runner=types.SimpleNamespace(recursion_limit=20, max_retries=2,
        _graph_invoke=lambda:graph.ainvoke,_add_interruption_callback=lambda _:None,
        _hooks=contextvars.ContextVar('hooks',default=None))
    msg={'role':'user','content':'test request'}
    if kind=='stable ID':
        msg['id']='user-turn-fixture'
    cfg={'configurable':{'thread_id':'same-thread'},'recursion_limit':20}
    payload={'messages':[msg]}
    if kind=='resume':
        try:
            await graph.ainvoke(payload,cfg,durability='sync')
        except ConnectionError:
            final=await graph.ainvoke(None,cfg,durability='sync')
        else:
            raise AssertionError('failure expected')
    else:
        final=await method(runner,payload,'same-thread',None)
    assert final['mark']==2
    print(kind,'nodes',entered,'user copies',len(final['messages']),'IDs',[m.id for m in final['messages']])
    if kind=='resume':
        assert entered==['step-one','step-two','step-two'] and len(final['messages'])==1
    else:
        assert entered==['step-one','step-two','step-one','step-two']
        assert len(final['messages'])==(1 if kind=='stable ID' else 2)
async def main():
    for kind in ('same payload','stable ID','resume'):
        await run(kind)
    assert sleep_durations==[1,1]
asyncio.run(main())
PY
```

</details>

<details>
<summary>Client and saver fencing after a failed Code server restart</summary>

```bash
cd "$da_repo/libs/code"
da_offline "$PWD:$da_scratch/deps314" python3.14 -B - <<'PY'
from __future__ import annotations
import ast, asyncio, logging, sys, types
from dataclasses import dataclass
from pathlib import Path

from deepagents_code import sessions
from deepagents_code.client.remote_client import RemoteAgent
from deepagents_code.thread_ownership import OWNER_KEY, ThreadOwnershipError, release_all, try_acquire, writer_guard

file=Path('deepagents_code/app.py')
source=ast.parse(file.read_text())
klass=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='DeepAgentsApp')
nodes=[n for n in source.body if getattr(n,'name',None)=='_ServerRespawnResult']
nodes+= [n for n in klass.body if getattr(n,'name',None) in {'_reserve_thread','_rotate_thread_ownership','_respawn_server'}]
module=types.ModuleType('local_server_restart_subject')
sys.modules[module.__name__]=module
module.__dict__.update(dataclass=dataclass,asyncio=asyncio,logger=logging.getLogger(module.__name__))
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(file),'exec'),module.__dict__)

async def scenario():
    db=Path.home()/'server-restart-control.db'
    sessions.get_db_path=lambda: db
    failures=[]
    async def fails(*args,**kwargs):
        raise RuntimeError('injected local process stop failure')
    app=types.SimpleNamespace(_server_proc=object(),_server_kwargs={},_thread_leases={},_chat_input=None,
        _restart_server_process=fails,_sync_status_connection=lambda:None,
        ServerStartFailed=lambda **data:data,post_message=failures.append)
    app._rotate_thread_ownership=types.MethodType(module._rotate_thread_ownership,app)
    module._reserve_thread(app,'thread')
    remote=RemoteAgent('http://unused.invalid',local_ownership=True)
    cfg={'configurable':{'thread_id':'thread'}}
    token=remote._prepare_mutation(cfg)['configurable'][OWNER_KEY]
    try:
        result=await module._respawn_server(app,log_message='restart failed',mcp_failure_log='unused',mcp_failure_toast='unused')
        assert result.restarted is False and len(failures)==1
        assert app._thread_leases['thread'].token!=token
        assert try_acquire('thread') is None
        try:
            async with writer_guard('thread',db_path=db,token=token):
                raise AssertionError('stale write admitted')
        except ThreadOwnershipError:
            pass
        try:
            remote._prepare_mutation(cfg)
        except ThreadOwnershipError:
            pass
        else:
            raise AssertionError('old client retained mutation rights')
        print('failed process restart fences both old client and old saver writer, reservation survives')
    finally:
        release_all()
asyncio.run(scenario())
PY
```

</details>

### Source references

[acp-cancel]: repos/langchain-ai__deepagents/libs/acp/deepagents_acp/server.py:503
[code-respawn]: repos/langchain-ai__deepagents/libs/code/deepagents_code/app.py:30735
[fs-trace]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/filesystem.py:1970
[talon-retry]: repos/langchain-ai__deepagents/libs/talon/deepagents_talon/runtime.py:1199

[acp-prompt]: repos/langchain-ai__deepagents/libs/acp/deepagents_acp/server.py:1014
[acp-restore]: repos/langchain-ai__deepagents/libs/acp/deepagents_acp/server.py:389
[architecture]: repos/langchain-ai__deepagents/libs/ARCHITECTURE.md:12
[assembly-children]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/graph.py:713
[assembly-compile]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/graph.py:1005
[assembly-custom]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/graph.py:223
[assembly-defaults]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/graph.py:641
[assembly-fork]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/graph.py:819
[assembly-gp]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/graph.py:848
[assembly-imports]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/graph.py:12
[assembly-inputs]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/graph.py:296
[assembly-main]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/graph.py:920
[backend-protocol]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/protocol.py:404
[blob-offload]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/_blob_offload.py:55
[cache-middleware]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/_prompt_caching.py:117
[code-adapter]: repos/langchain-ai__deepagents/libs/code/deepagents_code/_checkpointer_adapter.py:1
[code-adapter-tests]: repos/langchain-ai__deepagents/libs/code/tests/unit_tests/test_checkpointer_adapter.py:64
[code-assembly]: repos/langchain-ai__deepagents/libs/code/deepagents_code/agent.py:3756
[code-event]: repos/langchain-ai__deepagents/libs/code/deepagents_code/event_bus.py:116
[code-goals]: repos/langchain-ai__deepagents/libs/code/deepagents_code/goal_tools.py:288
[code-locked-api]: repos/langchain-ai__deepagents/libs/code/uv.lock:2968
[code-owner-tests]: repos/langchain-ai__deepagents/libs/code/tests/unit_tests/test_thread_ownership.py:53
[code-restart-test]: repos/langchain-ai__deepagents/libs/code/tests/unit_tests/test_thread_ownership.py:414
[code-resume]: repos/langchain-ai__deepagents/libs/code/deepagents_code/resume_state.py:237
[code-retry-classify]: repos/langchain-ai__deepagents/libs/code/deepagents_code/model_retry.py:434
[code-retry-event]: repos/langchain-ai__deepagents/libs/code/deepagents_code/model_retry.py:950
[code-retry-loop]: repos/langchain-ai__deepagents/libs/code/deepagents_code/model_retry.py:611
[code-session-saver]: repos/langchain-ai__deepagents/libs/code/deepagents_code/sessions.py:2050
[code-thread-guard]: repos/langchain-ai__deepagents/libs/code/deepagents_code/thread_ownership.py:185
[codex-todo]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/profiles/harness/_openai_codex.py:70
[compaction-tests]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/middleware/test_compaction_recovery.py:114
[compiled-spec]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/subagents.py:269
[composite-exec]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/composite.py:814
[composite-route]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/composite.py:195
[composite-xfail]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/backends/test_composite_backend_async.py:907
[composite-xfail-sync]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/backends/test_composite_backend.py:1149
[context-hub-conflict]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/context_hub.py:308
[context-hub-queue]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/context_hub.py:188
[context-hub-tests]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/backends/test_context_hub_backend.py:1195
[example-cancel]: repos/langchain-ai__deepagents/examples/async-subagent-server/server.py:320
[example-dispatch]: repos/langchain-ai__deepagents/examples/async-subagent-server/server.py:261
[example-execute]: repos/langchain-ai__deepagents/examples/async-subagent-server/server.py:169
[example-tests]: repos/langchain-ai__deepagents/examples/async-subagent-server/test_server.py:75
[extended-xfail]: repos/langchain-ai__deepagents/libs/deepagents/tests/integration_tests/test_deepagents.py:103
[file-format-tests]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/backends/test_file_format.py:67
[files-channel]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/filesystem.py:1360
[fork-payload-tests]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/middleware/test_fork_payload.py:18
[fork-transcript]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/subagents.py:419
[fs-backend-write]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/filesystem.py:505
[fs-evict]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/filesystem.py:3501
[fs-interrupt]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/_fs_interrupt.py:174
[fs-permission]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/filesystem.py:417
[fs-visibility]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/filesystem.py:3453
[fs-workers]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/filesystem.py:2101
[glob-compile]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/utils.py:300
[harness-factories]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/profiles/harness/harness_profiles.py:775
[harness-resolve]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/profiles/harness/harness_profiles.py:1319
[hitl-merge]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/graph.py:192
[inline-call]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/subagents.py:933
[inline-compile]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/subagents.py:643
[inline-ns-tests]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/test_subagents.py:2199
[inline-prepare]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/subagents.py:898
[inline-private-rebuild]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/subagents.py:1146
[inline-return]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/subagents.py:836
[inline-stream]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/subagents.py:690
[inline-trace]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/subagents.py:594
[inline-unchanged]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/subagents.py:481
[integration-model]: repos/langchain-ai__deepagents/libs/deepagents/tests/integration_tests/test_deepagents.py:23
[integration-sandbox]: repos/langchain-ai__deepagents/libs/deepagents/tests/integration_tests/test_langsmith_sandbox.py:23
[layout-precedent]: ./RuoJi6__ARTEX.md:87
[lg-apply-writes]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_algo.py:234
[lg-create-checkpoint]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_checkpoint.py:268
[lg-delta]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/channels/delta.py:25
[lg-interrupt]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/types.py:913
[lg-local-read]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_algo.py:190
[lg-saver]: repos/langchain-ai__langgraph/libs/checkpoint/langgraph/checkpoint/memory/__init__.py:430
[lg-snapshot]: repos/langchain-ai__langgraph/libs/langgraph/langgraph/pregel/_checkpoint.py:90
[local-shell]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/local_shell.py:256
[locked-glob]: repos/langchain-ai__deepagents/libs/deepagents/uv.lock:2602
[locked-lc]: repos/langchain-ai__deepagents/libs/deepagents/uv.lock:1043
[locked-lg]: repos/langchain-ai__deepagents/libs/deepagents/uv.lock:1189
[locked-ruff]: repos/langchain-ai__deepagents/libs/deepagents/uv.lock:2233
[memory-lifecycle]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/memory.py:278
[message-reducer]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/_messages_reducer.py:31
[message-state]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/graph.py:77
[message-tests]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/test_messages_reducer.py:38
[model-resolve]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/_models.py:35
[overflow-clip]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/_overflow_clip.py:131
[parent-notifier]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/_parent_notifier.py:61
[patch-tool-calls]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/patch_tool_calls.py:17
[private-state]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/_state.py:13
[profile-bootstrap]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/profiles/_builtin_profiles.py:91
[profile-exclusions]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/_excluded_middleware.py:101
[remote-cancel]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:1263
[remote-check-write]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:998
[remote-fork]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:766
[remote-launch]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:811
[remote-list]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:1405
[remote-notification]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:531
[remote-observe]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:912
[remote-options]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:384
[remote-pull]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:1653
[remote-queued-tests]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/test_async_subagents.py:2295
[remote-record]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:1729
[remote-spec]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:66
[remote-tool-factory]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:1495
[remote-update]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:1174
[remote-update-guard]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:1123
[remote-wake]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:676
[rubric]: ./README.md:6
[rubric-mw]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/rubric.py:491
[sandbox-client]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/langsmith.py:97
[sandbox-skip]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/backends/test_sandbox_backend.py:1701
[sandbox-timeout-test]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/backends/test_sandbox_backend.py:2602
[sdk-e2e]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/test_end_to_end.py:222
[sdk-exports]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/__init__.py:3
[sdk-makefile]: repos/langchain-ai__deepagents/libs/deepagents/Makefile:19
[sdk-manifest]: repos/langchain-ai__deepagents/libs/deepagents/pyproject.toml:1
[sdk-middleware]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/__init__.py:3
[sdk-ruff]: repos/langchain-ai__deepagents/libs/deepagents/pyproject.toml:85
[shell-cancel]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/local_shell.py:445
[shell-cleanup]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/local_shell.py:117
[shell-execute]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/local_shell.py:637
[shell-tests]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/backends/test_local_shell_backend.py:634
[skills-lifecycle]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/skills.py:1166
[skills-tools]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/skills.py:1302
[state-backend]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/state.py:57
[state-edit]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/state.py:206
[store-edit]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/store.py:495
[store-namespace]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/backends/store.py:111
[summary-budget]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/summarization.py:1533
[summary-call]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/summarization.py:1631
[summary-offload]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/summarization.py:1371
[summary-offload-async]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/summarization.py:1448
[summary-view]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/summarization.py:936
[talon-archive]: repos/langchain-ai__deepagents/libs/talon/deepagents_talon/archive_saver.py:40
[talon-archive-tests]: repos/langchain-ai__deepagents/libs/talon/tests/unit_tests/test_archive_saver.py:100
[talon-assembly]: repos/langchain-ai__deepagents/libs/talon/deepagents_talon/runtime.py:552
[talon-background]: repos/langchain-ai__deepagents/libs/talon/deepagents_talon/background.py:308
[talon-checkpoint-tests]: repos/langchain-ai__deepagents/libs/talon/tests/unit_tests/test_checkpoint_backends.py:16
[talon-checkpointer]: repos/langchain-ai__deepagents/libs/talon/deepagents_talon/checkpoint_backends.py:26
[talon-invoke]: repos/langchain-ai__deepagents/libs/talon/deepagents_talon/runtime.py:1132
[task-reducer]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:249
[task-schema]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/subagents.py:498
[task-state]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:192
[todo-change]: repos/langchain-ai__deepagents/libs/deepagents/CHANGELOG.md:362
[todo-test]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/test_todo_middleware.py:17
[tool-exclusion]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/_tool_exclusion.py:34
[unit-conftest]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/conftest.py:9
[unsupported-content]: repos/langchain-ai__deepagents/libs/deepagents/deepagents/middleware/unsupported_content.py:117
[video-fixture]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/conftest.py:65
[windows-tests]: repos/langchain-ai__deepagents/libs/deepagents/tests/unit_tests/backends/test_windows_process.py:189
