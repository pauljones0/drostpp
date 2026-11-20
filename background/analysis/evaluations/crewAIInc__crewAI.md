# CrewAI core orchestration evaluation

## 1. Snapshot, scope, and elapsed-time evidence

| Item | Evidence |
| --- | --- |
| Repository | `crewAIInc/crewAI` |
| Checkout | `repos/crewAIInc__crewAI` |
| Commit | `7cd52acbe8afbb0a1d02dfe52ed294deaae35070`, detached HEAD |
| Package version | `1.15.42` from the pinned workspace wheels |
| UTC start | `2026-11-18T23:00:40Z`, captured with the initial HEAD and clean-worktree checks |
| UTC end | `2026-11-18T23:30:45Z` |
| Elapsed active investigation | **30.08 minutes** |
| Repository status | `git status --porcelain=v1 --untracked-files=all` produced no entries at the start and the end. |
| History available | Shallow, blob-filtered clone. Findings concern the pinned tree. Historical causes and regression dates are unverified. |

I evaluated the Python orchestration runtime, its persistence and policy boundaries, and the local tests that exercise them. I excluded front ends and GUIs. I used the pinned source and documentation, installed the workspace wheels and test dependencies into an isolated environment, and ran tests from a Git archive outside the checkout. Local mock transports and deterministic models exercised public APIs without real API credentials. The sole deliverable is this report.

**Assessment.** CrewAI has a useful separation between explicit workflow control and model-driven work. The Crew can run a short task list with little boilerplate. Flow adds typed state, routing and composition, and the agent executor reuses Flow internally. Tool invocation, policy, and observability have substantive implementations and regression suites. The core is strongest when one run owns its mutable objects and recovery happens at a tested boundary. Concurrent tasks, repeated use of objects, and checkpoint restore expose gaps in task identity, ownership of in-flight work, and terminal state. The most consequential results are misattributed output when two tasks share an executor, loss of explicit task context across checkpoints, and a configured LLM checkpoint event that emits without saving. [Crew task scheduling][crew-native] · [Agent executor admission][agent-invoke] · [Checkpoint dispatch][checkpoint-dispatch]

## 2. Core architecture and end-to-end control/data flow

### Package and authoring boundaries

- The workspace separates the orchestration package `crewai`, its shared settings, authentication, storage-path and telemetry support in `crewai-core`, and CLI, tool, file and maintenance packages. Most scheduling and execution logic is in `lib/crewai/src/crewai`. The package declares native OpenAI as a baseline and uses extras for multiple provider SDKs, A2A, file processing and other integrations. [Workspace members][workspace] · [Core dependency contract][dependencies] · [Provider and integration extras][extras]
- Construction supports Python objects, project-bound YAML and declarative Crew/Agent definitions. `CrewBase` resolves project definitions and callable references into live agents and tasks. Flow projects decorated Python methods into a `FlowDefinition` or loads one directly, then binds actions and state at runtime. A declarative Crew or Agent action resolves inputs through the expression evaluator and invokes the corresponding public entry point. CEL expressions see state and previous method outputs. Nested `each` actions execute steps and items in sequence with per-item outputs. [Crew project setup][crew-project] · [Flow public surface][flow-public] · [Flow definition models][flow-definition] · [Flow binding][flow-bind] · [Declarative actions][flow-actions] · [Each action][flow-each]
- There are two framework-level scheduling contracts. `Crew` is an ordered list with a choice of sequential or manager-driven execution. `Flow` dispatches named starts, listeners and routers, including conditional re-entry and branching. An agent itself runs a specialized, internal `Flow[AgentExecutorState]`, so a user Flow can invoke a Crew that invokes several internal Flows. Memory also reuses the Flow runtime for encoding and recall. [Crew process selection][crew-kickoff] · [Flow routing][flow-route] · [Agent executor state][agent-state] · [Memory encoding][memory-encode] · [Memory recall][memory-recall]

### Crew lifecycle

1. `Crew.kickoff` applies optional checkpoint configuration and opens execution, event and baggage scopes. `prepare_kickoff` dispatches execution-start and input hooks, applies before-kickoff callbacks, emits the start event, resets the latest task log and binds files. It interpolates inputs and configures agent executors, knowledge, skills, callbacks and optional planning. The sync API performs the run inline at the Crew level, `kickoff_async` calls it in a thread, and `akickoff` drives an asyncio task scheduler. Streaming uses a wrapper and event-derived chunks with final result or error. [Crew kickoff][crew-kickoff] · [Kickoff preparation][prepare-kickoff] · [Thread wrapper][crew-thread-wrap] · [Native async kickoff][crew-akickoff] · [Streaming adapters][streaming]
2. Sequential execution uses each task's agent. The hierarchical mode creates or reuses a manager, selecting the manager for every top-level task and equipping it with coworker delegation. Task tools take precedence over agent defaults when populated. Preparation may add memory, file, MCP and platform tools. Default synchronous context concatenates accumulated raw outputs. Explicit `context=[...]` reads the referenced tasks' outputs. Empty or `None` context disables this input. The scheduler forms contiguous cohorts of `async_execution` tasks and drains them in task order at a synchronous or conditional barrier or at the end. Conditional tasks test the immediately preceding output after the barrier. [Manager creation][crew-manager] · [Tool selection][prepare-task] · [Tool enrichment][crew-tools] · [Task context][crew-context] · [Async scheduler][crew-native] · [Sync scheduler][crew-sync] · [Conditional execution][conditional]
3. A `Task` establishes task context, dispatches pre-step policy and opens a tool-failure collector. The agent builds instructions and schema, appends context and selected memory and knowledge, configures tools and enters the executor. At the return boundary the Task records raw output, optional typed JSON/Pydantic data, messages and tool failures. Guardrails can validate, rewrite or request a retry with feedback. Task post-step hooks, output assignment, callbacks, optional file write and terminal event sit on the result path. The task clears its file bindings and task ID on exit. [Task execution][task-execute] · [Sync task execution][task-execute-sync] · [Agent preparation][agent-prepare] · [Agent sync execution][agent-sync] · [Agent async execution][agent-async] · [Output conversion][task-convert] · [Guardrail retry][task-guardrail]
4. The Crew appends task outputs and records replay metadata. It derives the public output from the last task with non-empty raw output, preserving the task output list. Output and execution-end hooks can transform the final value. It drains memory writes, flushes pending events and emits completion. Legacy after-kickoff callbacks run after this step. Final cleanup detaches contexts and file bindings. `kickoff_for_each` and its async variants allocate per-input Crew copies, with the async variants gathering results. [Crew finalization][crew-result] · [Crew evidence storage][crew-store] · [Batch scheduling][crew-batch] · [Crew copy][crew-copy]

### Agent execution, tools and delegation

- `AgentExecutorState` owns the message list, iteration, current answer, pending tools, plan, todos, observations and replan counters. Setup turns role, goal, task and tool descriptions into provider messages. The agent routes by plan readiness and iteration budget, calls the model and selects final-answer or tool-action transitions. Native function calls use provider call IDs and assistant/tool messages. ReAct calls parse textual actions into structured arguments and append the observation. Parser or context-window failures feed recovery routes. The iteration budget can force a final answer. [Agent state and setup][agent-state] · [ReAct inference][agent-react] · [Native inference][agent-native] · [Iteration guard][agent-iterations] · [Parser and context recovery][agent-recovery]
- Planning happens at two levels. Crew-level planning adds a plan to task instructions before execution. Agent planning resolves a plan into typed todos with dependency information and keeps execution observations separately from chat history. Eligible independent todos can run in separate step executors, each with isolated prompt context. Progress and observation may trigger replanning, and the agent synthesizes a final answer from completed work. The no-plan route keeps ordinary execution available if there is no usable plan. [Crew planning][crew-plan] · [Agent planning][agent-plan] · [Todo dependencies][todo-dependencies] · [Parallel todos][agent-todos] · [Plan synthesis][agent-synthesis]
- `BaseTool` and `CrewStructuredTool` infer or accept a Pydantic argument schema. Parameter handling, provider schema, invocation and output rendering meet at this boundary. A locked usage claim enforces configured invocation budgets, and a typed `ToolFailure` carries failures that should reach policy rather than appearing as ordinary tool prose. ReAct and native loops implement similar behavior through separate call paths. Crew caching is opt-in. Individual tools can control which results are cacheable, which is useful for repeatable work. Native batches preserve provider call order for observations even when execution overlaps. [Tool schema and claim][tool-claim] · [Structured invocation][tool-structured] · [ReAct dispatch][tool-react] · [Native batching][tool-native] · [Cache policy][crew-cache] · [Tool failure scope][tool-failure]
- Local delegation is a tool call. The manager or peer agent chooses a coworker by normalized role and passes a new task plus explicit context. The worker runs through its own executor and returns the result into the caller's model loop. This lets the model decide which expertise to use while the outer Crew retains the task sequence. MCP adapts server schemas into the same tool surface, with discovery separated from per-invocation transports. The optional A2A path negotiates a remote agent's card, auth, transport and output mode, passes conversation and task identifiers and handles remote task state. [Local delegation][delegation] · [MCP discovery and per-call instances][mcp-resolver] · [MCP client operation][mcp-client] · [Remote delegation][a2a]
- `LLM` routes to a native provider or the optional LiteLLM path. `BaseLLM` supplies a common model contract, usage normalization, call context and events. Provider implementations negotiate tool capabilities, response formats, streaming and request differences. Provider throttling has bounded sync/async retries with retry hints and backoff. ReAct parse retries, guardrail retries, agent exception retries and provider retries have separate budgets and distinct effects. [LLM routing][llm-factory] · [LLM call contract][llm-base] · [Provider retry][llm-retry] · [Agent retry][agent-retry]

### Flow lifecycle

1. The runtime builds or accepts a definition, binds methods and actions, initializes a dict or Pydantic state and provides a flow ID. Kickoff opens a context and loads durable state when an ID and persistence backend are provided. Checkpoint restoration can hydrate execution bookkeeping in addition to state. Hooks see input, step payloads and result. [Flow definition binding][flow-bind] · [Flow state setup][flow-state] · [Flow restore at kickoff][flow-kickoff]
2. Unconditional starts run at entry. The dispatcher evaluates router labels and listener conditions, tracks arrivals for AND gates and firing state for OR gates, then recurses through the resulting triggers. Cycles can re-enter start methods, with a method-call limit as a backstop. Fan-out generally uses `asyncio.gather`. Exclusive alternatives feeding an OR can form a race. Async methods are awaited and sync methods execute in workers with copied context. [Flow starts][flow-starts] · [Flow routing][flow-route] · [Race eligibility and execution][flow-race] · [Flow invocation bound][flow-count] · [Sync method offload][flow-method]
3. Method results feed listeners and the named expression output map. The runtime records successful completion, optional state persistence and events. The public return is the last recorded method output. A human-feedback pause persists state plus a continuation context and returns a pending object. `from_pending` reconstructs the Flow instance and `resume_async` routes the reply without rerunning the initial method. Flows can also emit conversation/tool/model frames, with trace identity propagated into nested calls. [Flow method completion][flow-completion] · [Flow result and events][flow-result] · [Feedback pause][flow-pause] · [Feedback restore][flow-pending] · [Feedback continuation][flow-resume]

## 3. Why the design works and its governing invariants

| Invariant or intended contract | Architectural consequence |
| --- | --- |
| An ordered Crew can only consume valid earlier task outputs. | Validation rejects future dependencies, conditional first tasks, async conditionals, adjacent async dependencies on one another and multiple final async tasks. That keeps the scheduler simple and gives a single final result. The explicit list vs omitted vs empty distinction matters for prompt construction. [Crew validation][crew-validate] · [Context aggregation][crew-context] |
| One live executor invocation owns message state and its task binding. | Agent state is reusable between tasks and serialized where needed, while invocation admission rejects overlapping runs. That invariant must also hold during prompt and tool preparation and cleanup. It currently breaks before the admission check, as shown below. [Executor admission][agent-invoke] · [Binding update][agent-rebind] |
| Routing decisions are explicit even when the work between nodes is probabilistic. | Labels, listener conditions and validated outputs govern control flow. Task role, tool schema, pending tool call IDs and iteration budget give model calls a bounded execution environment. Planning stores progress as todos and yields a separate way to structure longer work. [Flow routing][flow-route] · [Agent state][agent-state] · [Tool schema][tool-structured] |
| Execution identity and causal relationships travel across nested boundaries. | The runtime uses ContextVars and copied thread/async contexts. Parent, previous, trigger and start IDs support tracing and event replay. The event graph supports causality even when parallel operations finish out of order. Replay keeps captured IDs and exposes an indicator that lets listeners suppress repeat side effects. [Execution lifetime][execution-lifetime] · [Event emission][event-emit] · [Event graph][event-record] · [Replay contract][event-replay] |
| State used for task results, memory retrieval and recovery has different lifetime and consistency requirements. | Task output is a run artifact, memory is scoped knowledge reused across runs, a Flow state snapshot is data hydration, and a runtime checkpoint can include instructions and progress. Durable replay depends on preserving the identity of state references and matching the saved boundary to where external effects actually happen. [Latest task storage][replay-sql] · [Memory configuration][memory-config] · [Flow persistence][flow-sql] · [Runtime checkpoint serialization][checkpoint-runtime] |
| Policy decisions are synchronous with the operation they control. | Hooks can modify payloads and deliberately abort. Events can be observed out of band. Tool failures have warn, ignore and raise policies. Save and telemetry listeners have best-effort policies so an auxiliary failure can be surfaced without converting every successful user task into a failure. [Hook dispatch][hook-dispatch] · [Tool policy][tool-failure] · [Checkpoint failure behavior][checkpoint-dispatch] |

## 4. What works well and where it breaks

### What works well

- **Routine execution is easy to compose.** The ordered Crew is a small conceptual entry point. Explicit dependencies, tool selection, schemas and guardrails express common workflows directly. Flow gives the caller a place to put routing, joins and state that would otherwise live in agent prompts. The observed task result always included ordered outputs for the completed Crew tasks in the dependency controls. The Flow definition, routing, cyclic resumption and tool action suites passed with the required extras. [Crew validation][crew-validate] · [Task aggregation][crew-result] · [Definition coverage][test-definition] · [Cyclic flow coverage][test-resume]
- **The tool boundary can preserve useful structure.** Native and text paths support validated arguments, failure policy and hooks. Direct usage limits use a lock. Deferred tool results let an executor keep a manageable message history while retaining an in-run way to read larger artifacts, then clean up on exit. Native and ReAct hook conformance, usage limits, failure attribution, and artifact lifetime tests passed. [Tool usage claim][tool-claim] · [Failure records][tool-failure] · [Deferred artifact lifetime][agent-artifacts] · [Native hook contracts][test-native-hooks]
- **There is practical recovery and extension work already present.** Default task-completion checkpoints saved and resumed without rerunning the completed task. Flow SQLite persistence, checkpoint lineage, callback restoration, pending feedback and memory backend contracts had passing tests. Event IDs, scopes and replay let integrations follow execution causality. The storage/provider layers, client adapters, scoped hooks and typed action definitions make customization possible at defined seams. [Checkpoint configuration][checkpoint-config] · [Crew restore][crew-restore] · [Flow persistence][flow-sql] · [Backend contracts][memory-backend] · [Scoped hooks][hook-scope]

### Verified scheduling and run-state defects

| Finding | What the public API did and why |
| --- | --- |
| **Omitted context drops the preceding sync output for an async task.** | In `kickoff`, `kickoff_async` and `akickoff`, two distinct agents produced and consumed a unique token. A sync consumer or an async consumer with explicit `context=[producer]` saw it. The same async consumer with omitted context received an empty string. Both scheduler variants initialize `last_sync_output` and pass it to async tasks. Normal sync completion only appends to `task_outputs`. The helper updates the variable when loading an already-skipped prefix, which explains how a restored path can appear to behave differently. [Sync scheduler][crew-sync] · [Native scheduler][crew-native] · [Replay-prefix helper][prepare-task] · [Context docs and example][task-docs] |
| **Overlapping tasks sharing one agent can corrupt the running task.** | A gated first async task had entered its LLM call before a second task started. The second invocation was rejected as “Executor is already running,” yet the first task returned the second task's token. Its subsequent LLM request also carried the second task association. Separate agents produced the correct first output and the Crew completed. Both schedulers showed the same result. Agent preparation mutates the shared executor's task, tools, prompt and response model before invoking the guard. The docs show adjacent async tasks sharing a researcher, so this configuration is an important normal path. [Reuse and binding][agent-rebind] · [Admission lock][agent-invoke] · [Async admission][agent-ainvoke] · [Documented layout][task-docs] |
| **A failing cohort can return while a sibling still does work.** | Two separate agents in a Crew cohort reached their local model calls. The first failed while the second waited for a release signal. After the public kickoff raised, releasing the sibling let its task callback run. The tail task never ran. This worked in the sync and native pathways. The joins wait in declared order and do not settle remaining handles on exception. An ordinary Flow fan-out reproduced the same late mutation with true async listener methods and a gated sibling. [Crew join][crew-join] · [Native join][crew-native-join] · [Flow gather][flow-fanout] |
| **Flow race groups can report success while every alternative fails.** | Two failing alternatives inside an OR race resulted in a normal return. One winning alternative also allowed an unrelated sibling's exception to be ignored. Removing the OR caused a regular listener error to propagate. The race consumes alternative exceptions while looking for success and uses `return_exceptions=True` for other listeners without examining the results. Continued failure of one candidate on the way to a genuine winner is useful. Losing all candidates and ignoring an independent failure need separate outcomes. [Race detection and result handling][flow-race] · [Ordinary fan-out][flow-fanout] |
| **A reused conditional task keeps its last successful output when skipped.** | In a two-run Crew the conditional ran once, then skipped. The second `CrewOutput` contained a blank skipped output, but a later task explicitly referencing the conditional saw its first-run token. This held in sync and native async. The skip helper constructs a placeholder for the current output list, and explicit context reads the referenced task object's output, which still holds the previous result. [Conditional placeholder][conditional-type] · [Skip helper][conditional] · [Explicit context formatter][context-format] |
| **Batch copying can rewire a dependency to an identically described task.** | Two different task objects had the same description and expected output, distinct names and different model results. The original downstream task referenced the first. After `Crew.copy()` it referenced the second, and `kickoff_for_each` passed the second token. With distinct descriptions the copy preserved the first. The copy maps dependencies by content key and the later task overwrites the earlier entry. [Task key][task-key] · [Copy mapping][crew-copy] |
| **A repeated hierarchical kickoff can change eligible workers.** | With two named workers and a task assigned to one, the first manager prompt offered only the assigned worker. The second run of the same Crew offered both. The task object retains the manager after execution, and the next preparation handles manager-as-task-agent by using the full roster. Both sync and async behaved this way. The fallback prevents self-delegation, while the original task assignment no longer constrains the next run. [Crew manager tool routing][crew-manager-tools] · [Task agent assignment][task-execute] · [Delegation roster][delegation-roster] |
| **An exception retry budget survives successful completion of a task.** | Two tasks each hit one transient error with `max_retry_limit=1`. Shared agent calls were 2 then 1 and the second task failed. With separate agents calls were 2 then 2 and the run succeeded. Sync and native matched. `_times_executed` is initialized per agent, incremented in the generic error path, and is not reset on successful task completion. The field describes retrying task execution. [Retry field][agent-retry-field] · [Error handler][agent-retry] · [Execution finalizer][agent-finalize] |

### Verified recovery and observation defects

| Finding | What the public API did and why |
| --- | --- |
| **A Crew checkpoint changes explicit task context.** | A real SDK-backed Crew used a local HTTPX transport and configurable context. A checkpoint saved after task A, before task B, encoded the assigned dependency in task C as `"NOT_SPECIFIED"`. After restore, C saw both A and B instead of the one it selected. Sync and native restore ran B and C, skipping A as expected. Omitted and `None` controls retained their meaning. A focused serializer check reproduced the collapse with an assigned dependency on Pydantic 2.12.5 and 2.11.10. A bare-task control and a direct `list[Task]` serializer preserved the list. Supplying the list in a scratch snapshot exposed a second boundary: restore produced a separate dependency object, so an explicit dependency that ran after restore still had no output in the dependent prompt. [Task context type][task-context-type] · [Sentinel serializer][sentinel] · [Snapshot model dump][checkpoint-runtime] · [Crew restore bindings][crew-restore] |
| **Replay loses the earlier task's concrete output model.** | The original task returned a valid custom Pydantic `Answer`. The SQLite row held its fields, but replaying the next task passed the stored dictionary to a `TaskOutput` field typed as bare `BaseModel`. Replay returned and reran the expected suffix. Its reconstructed prefix held a bare `BaseModel`. Accessing the typed field and `str(output)` raised `AttributeError`, and `to_dict()` raised `PydanticUserError`. Raw and JSON variants retained their values. Pydantic 2.12.5 and 2.11.10 showed the same result. [Replay materialization][replay-materialize] · [TaskOutput model and accessors][task-output] · [JSON encoder][replay-encoder] |
| **A configured model-completion checkpoint trigger does not save for the tested OpenAI path.** | With a real `OpenAICompletion` and a local HTTPX response, a subscriber observed `LLMCallCompletedEvent` with the correct task and response ID. `on_events=["llm_call_completed"]` saved zero files. The SQLite provider gave the same result, while its task-completion control wrote one row. Default `task_completed` saved a file that already contained the LLM event in its history. `["*"]` saved task, agent and Crew events and still skipped the model event. The auto-checkpoint listener looks up config by the emitting source's entity class. `BaseLLM` emits using itself, while task/agent metadata is present on the event. This directly contradicts the documented fine-grained trigger for the tested path. [Checkpoint trigger docs][checkpoint-docs] · [Owner resolution][checkpoint-owner] · [Dispatch gating][checkpoint-dispatch] · [LLM event source][model-event] |
| **Partial Flow restore can omit the next node's payload or route.** | Original runs of a start → listener → consumer chain saved the listener's output before the consumer failed deliberately. On restore the consumer ran with `None`. Replacing the completed listener with a router returning a label caused the label listener to be skipped and kickoff to return the saved label. A single start → consumer control correctly passed the start result. With two completed starts and two pending listeners, both listeners instead received the same last-recorded start value. All snapshots contained the named outputs, and sync and async Flow entry points matched. A completed listener advances with `None`, while a skipped completed router does not return its label to the router-dispatch loop. [Start resumption][flow-start-resume] · [Completed listener resumption][flow-count] · [Router result dispatch][flow-route] |
| **Automatic checkpoint serialization can race with event append.** | A real two-start Flow using `method_execution_finished` checkpoints produced PyO3 `PanicException: dictionary changed size during iteration` inside `RuntimeState._serialize`. One run lost both candidate method snapshots. Two of three reruns also logged the panic while retaining a usable snapshot. A gated test held serialization of one event payload while another was added to the same record, reproducing both the panic and its absence under a read-lock control on Pydantic 2.12.5 and 2.11.10. The event graph locks its writers, but checkpoint serialization iterates the live dict without that lock. [Runtime snapshot][checkpoint-runtime] · [Event graph write lock][event-record] · [Event handler dispatch][event-emit] |
| **A post-kickoff callback can produce two Crew terminal events.** | A callback threw after a successful single-task execution. Captured events showed both `CrewKickoffCompletedEvent` and `CrewKickoffFailedEvent` for the same start ID, followed by an empty event-scope warning. Both entry points raised to the caller. The run emits completion in the output builder before the legacy callback runs and handles callback exceptions in the outer failure path. [Completion emission][crew-result] · [Callback and failure emission][crew-kickoff] · [Scope pairing][event-emit] |
| **Crew token usage can include earlier runs and count one shared model twice.** | Two calls each reported 13 total tokens. Distinct model instances gave Crew totals 26 and then 52 across two runs. A shared model instance gave 52 then 104. A containing Flow correctly measured 26 on each kickoff in both configurations. The provider object holds lifetime counters, which the Crew sums by agent, while Flow measures events per execution. This affects budgeting and attribution even when task output is correct. [Crew token aggregation][crew-usage] · [Model counters][llm-usage] · [Flow usage accounting][flow-usage] |

### Verified limits of the present contracts

- **Async orchestration is hybrid.** Recording models implemented both `call` and `acall`. The default agent inference called `call` on worker threads, including under native `Crew.akickoff` and `Agent.akickoff`. Other code paths, including async conversion and some provider or transport operations, can use true async. Native Crew finalization also ran the blocking bus flush on the caller's loop. A held event handler prevented that loop from processing an independent callback until release. The thread-wrapped kickoff let the same caller loop service the callback. These controls establish execution mode and responsiveness in the tested seam. They support no throughput estimate for a real deployment. [Default inference route][agent-react] · [Flow method offload][flow-method] · [Native Crew finalization][crew-native] · [Bus flush][event-flush] · [Async conversion][task-convert]
- **Flow success output depends on completion order.** Two terminal listeners with independently controlled order yielded whichever output was appended last. The same graph returned `a` or `b` as the release order changed. A join with an explicit final result is the stable contract for applications combining outputs. Shared state writes in concurrent methods need application coordination. [Method output collection][flow-completion] · [Final output selection][flow-result]
- **Latest-task replay is project-wide convenience storage.** Replay of Crew A worked after A's run. A later Crew B kickoff in the same storage directory reset and replaced the rows, after which A's task ID could no longer be replayed. A separate backing database kept A replayable. Store locks and SQLite transactions protect individual calls. The schema and reset operation give the store latest-run semantics without Crew or execution ownership. The docs explicitly scope this feature to the latest kickoff. [Replay docs][replay-docs] · [Replay validation][crew-replay] · [SQLite storage][replay-sql] · [Reset on kickoff][prepare-kickoff]
- **Pending feedback is a continuation record with separate load and clear operations.** Two instances hydrated the same real SQLite row. After one resumed and deleted the row, the already-loaded instance still delivered a second continuation. A fresh load failed as expected. In a separate case a downstream listener threw and the row had already been cleared. The API provides a single-owner continuation, with no durable claim or retry contract across resume and downstream side effects. [Pending loader][flow-pending] · [Clear before routing][flow-resume-clear] · [SQLite pause and clear][flow-sql-pending]

## 5. Core-code quality and operational boundaries

### Decomposition, types and extensions

The clearest abstractions are at the edges. Pydantic models define task inputs and outputs, AgentExecutor state, structured tools, Flow action variants and checkpoint fields. The Flow DSL/runtime split makes it possible to parse and validate a definition independently of execution. The hooks centralize ordering, payload replacement and abort semantics. Support code behind the core package includes reusable settings and storage paths. Storage and model contracts support deterministic local substitutes. Those are strong seams for tests and integrations. [Flow model definitions][flow-definition] · [Agent state][agent-state] · [Hook dispatch][hook-dispatch] · [Memory backend protocol][memory-backend] · [LLM base class][llm-base]

Execution methods have more responsibilities than those edge contracts suggest. The AST count at the pin gives 4,085 physical lines in Flow runtime and 431 lines for `kickoff_async`. `AgentExecutor` spans 3,654 lines, including a 238-line native single-tool method. The two Task execution cores are 158 lines each, and `ToolUsage` has separate 264-line async and 256-line sync implementations. These counts include comments and whitespace and are indicators of review surface. The core duplication appears in branches independently managing state, callbacks, logging, retry and cleanup. Several observed faults appear in both variants, which provides stronger evidence than size alone. The pinned Ruff checks passed. [Flow main path][flow-entry] · [Task paths][task-execute] · [Native tool path][tool-native-single] · [Sync tool usage][tool-react] · [Async tool usage][tool-async] · [Typing policy][type-config]

Type precision varies by seam. Outputs and event identities are strongly modeled. Third-party payloads, method dispatch, model arguments, tool results and compatibility validators necessarily admit dynamic values. Code uses assertions, casts and reconstruction at these transitions. The checkpoint context failure shows why runtime serialization tests need to exercise assigned agents and complete snapshots in addition to isolated type models. Provider classes and older APIs stay wired through adapters and compatibility imports. External agent adapters expose tool binding and structured output configuration on the same base agent interface. The checkpoint provider base supports sync and async operations, while the public configuration union currently declares its two built-in providers. Memory and Flow persistence expose separate backend injection points. [Task contract][task-context-type] · [Agent adapter][agent-adapter] · [Checkpoint provider interface][checkpoint-provider] · [Checkpoint public config][checkpoint-config] · [Memory factory][memory-factory] · [Flow persistence factory][flow-factory]

### State and persistence

| State | Scope and durability |
| --- | --- |
| Run state | Mutable Crew, Task, agent executor and Flow objects. ContextVars carry identity and event scope through the runtime, with copied contexts for worker execution. Save/restore copies selected private fields to public checkpoint fields. State ownership is strongest for independent instances, as the concurrent shared-agent probe illustrates. [Runtime scope][event-runtime] · [Checkpoint field sync][checkpoint-fields] |
| Crew replay | SQLite latest-task log contains the task UUID, a task content key, index, inputs, selected output fields, messages and replay status. The replay path validates the saved prefix against the current Crew and can handle older rows without the task key. It reconstructs skipped outputs and reruns a suffix. [Replay storage][replay-sql] · [Prefix check][crew-replay] |
| Flow state and feedback | SQLite state rows are append-only by method and Flow ID, and the latest state is selected by row ID. A state-only reload hydrates values and starts execution against them. Pauses add a separate feedback context under the Flow ID. Persistence can be provided per instance or resolved from method or Flow metadata. SQLite enables WAL, retries locked schema creation, and closes its connections. [Flow SQLite lifecycle][flow-sql] · [Flow state load][flow-kickoff] · [Persistence backend precedence][flow-persist] |
| Runtime checkpoints | Versioned entity snapshots and event records, with parent and branch metadata. The default trigger is task completion. Event-driven writes are best-effort and manual writes propagate errors. JSON writes files directly, while SQLite has transactional rows. Restore rebuilds runtime references and skips completed work using saved progress. Forking changes lineage. These are snapshots at framework boundaries. They cannot generally commit external effects and progress together, and the JSON write path has no atomic rename around the final file. [Checkpoint state and versions][checkpoint-runtime] · [Checkpoint writer][checkpoint-writer] · [JSON provider][checkpoint-json] · [SQLite provider][checkpoint-sql] |
| Memory and knowledge | Memory has structural scopes, an embedding backend and separate analysis/recall flows. Encoding batches embeddings, considers consolidation and writes through a serialized save pool. Recall combines semantic relevance, recency and importance, using deeper search where configured. With agent or Crew memory enabled, results can yield new records. Knowledge embeds and queries configured sources as a distinct retrieval input. LanceDB is the default local memory store. Qdrant Edge and explicit backends are exercised by contract tests. LanceDB uses a named write lock and retries commit conflicts. [Memory configuration and save pool][memory-config] · [Encoding workflow][memory-encode] · [Recall workflow][memory-recall] · [Agent memory write][agent-memory] · [Memory write pool][memory-save-pool] · [LanceDB writes][memory-write] · [LanceDB save][memory-save] · [Knowledge query][knowledge] |

### Errors, observability and policy

- **Error behavior.** Context-window retries and parser recovery protect the agent loop from provider and output format variation. Agent exceptions can rerun the agent's work for a task. Guardrail retries rerun the agent against validation feedback, which can repeat effectful tools. Policy exceptions such as `HookAborted` are propagated by several retry and tool paths. Flow race exceptions, Crew cohort lifetimes and pending feedback consumption show why application-level actions need explicit failure and idempotency contracts. The code distinguishes observable, best-effort persistence from required completion, though the externally visible event sequence needs the same care as the result. [Agent retries][agent-retry] · [Context recovery][agent-recovery] · [Guardrail retry][task-guardrail] · [Native tool abort][tool-native] · [Checkpoint failure policy][checkpoint-dispatch]
- **Observability.** The event bus collects structured start, completion, failure, chunk, model, tool, memory and checkpoint events. Context propagation relates them to run and task IDs. Stream events have a synchronous fast path to preserve order. The bus supports dependency-ordered handlers, async handlers on its own loop, sync worker callbacks, a flush barrier and replay-aware listeners. OpenTelemetry spans and execution tracing have distinct configuration, including session-scoped export with grants. Internal agent and memory flows suppress their private steps at the interception boundary. A top-level standalone agent can still own its execution-level hooks. Trace startup with a rejected credential can continue without taking down the work. Bookkeeping needs run-specific ownership at teardown, as the hook, callback and token accounting probes show. [Event registration and delivery][event-emit] · [Flush behavior][event-flush] · [Event IDs][event-ids] · [Trace execution setup][trace-setup] · [Trace session][trace-session] · [Internal Flow interception][flow-hook-boundary]
- **Policy and trust.** Registered hooks can rewrite or deliberately deny model, tool, task and workflow operations. Hook failures other than `HookAborted` are explicitly fail-open, a compatibility decision that callers need to account for if hooks enforce mandatory policy. Tool failure policy applies from specific tool through task, agent and Crew configuration. Dynamic callback or tool imports during deserialization are gated, and inline Flow Python is opt-in trusted project code. Configured Python tools and MCP transports retain their process-level privileges. The resolved checkpoint serializer includes conversation/task material and an execution-context field that can carry a platform token if supplied. This is a source-reviewed storage and access-control implication. The policy review used static call-path tracing and credential-free tests. [Hook exception handling][hook-dispatch] · [Failure precedence][tool-failure] · [Checkpoint callback trust][checkpoint-trust] · [Tool restore guard][tool-trust] · [Script trust][flow-script] · [Execution context serialization][checkpoint-context] · [Checkpoint writer][checkpoint-writer]
- **Tests.** The suite mixes pure unit tests, mocks at provider boundaries, VCR playback, storage backend contracts, real local SQLite and thread/async concurrency. CI uses four supported Python versions, a shared randomization seed within a split matrix and all extras. Local fixtures reset event/tracing registries and storage. Tests often patch the task/executor seam to verify routing and callbacks, which is useful coverage of public behavior with limited visibility into concurrency below that seam. The async Crew basic and multi-task tests and the checkpoint resume tests are examples. Several probe failures were outside those specific assertions, especially same-agent overlap, named input identity and restore of pending listener payloads. [Workspace pytest config][pytest-config] · [CI matrix][pytest-ci] · [Fixtures][pytest-fixtures] · [Basic async Crew tests][test-async-crew] · [Crew callback checkpoint tests][test-resume-crew] · [Flow resumability tests][test-resume]

## 6. Executed tests and experiments

### Build and test runs

| Check | Outcome |
| --- | --- |
| Initial frozen sync in a `/tmp` venv and cache | Failed while extracting NumPy with `EDQUOT`. The reported free tmpfs space did not reflect the effective quota. |
| Frozen workspace install on `/var/tmp` | Built pinned `crewai`, `crewai-core` and `crewai-cli` wheels and installed 118 packages. Workspace file-processing and tools wheels built on later extra syncs. Interpreter was CPython 3.12.16. |
| Package and checkout consistency | Imported the intended package locations at 1.15.42. The 544 CrewAI, 30 shared core, 91 CLI, 36 files and 268 tools tracked Python files matched their installed wheel copies byte-for-byte. Parsed all 574 CrewAI/shared-core Python files with `ast.parse`. The principal behavior probes also matched when the checkout's own source directories were first on `PYTHONPATH`. |
| First orchestration collection | 960 tests found and one collection error from missing `crewai_files`. Installed the workspace file-processing extra. |
| First orchestration suite | 969 passed, 2 failed, 133.75 seconds. Both failures imported `crewai_tools`, which was absent from this initial selection. |
| First expanded suite | 662 passed, 4 failed, 41 skipped, 17.98 seconds. Failures imported `crewai_tools`. Backend contract coverage expanded after installing `qdrant-edge`. |
| Targeted optional dependency rerun | **6 passed**, 1.52 seconds. These were the exact six failed test nodes across the previous two runs. |
| Combined orchestration and expanded suites | **1,678 passed** with the relevant extras and replay-only cassettes, 51.57 seconds, four workers. No skips or failures. |
| Interfaces suite | **473 passed**, 21.01 seconds, four workers. Included provider hooks and response-tool loops, MCP transports and schema discovery, A2A utilities, storage parity and trace behavior. Some memory tests overlap the combined run. |
| Lifecycle suite | **361 passed, 1 skipped**, 148.49 seconds, two workers. Included Crew, context, planning, project loading, streaming and guardrail event tests. The skipped native RPM log assertion was investigated separately below. |
| Dependency-focused tests | **119 passed, 9 skipped**, 6.73 seconds. Converter and Chroma client cases passed. LiteLLM async cassette tests had explicit skips. Nearby local LiteLLM tests had **26 passes**. Temporarily collecting the skipped tests yielded **8 passes and 1 fixture failure**, diagnosed below. |
| Installed metadata check | `uv pip check` reported three dependency conflicts. Root lock overrides explain both version conflicts and the missing ONNX Runtime. The Chroma default embedding constructor fails in this environment. Explicit embeddings passed. |
| Async-tool warning audit | **61 passed**. Allocation tracing identified an unawaited coroutine created in a test that patched out `asyncio.run`. |
| Ruff with the pinned version and mutation disabled | Lint passed. Format check reported 225 files already formatted for the selected directories. |

The main post-setup suites exercise several layers and include existing cassettes and mock adapters. Counts are per invocation and overlap. I used CPython 3.12.16 and SQLite 3.53.1 on Linux, a deliberately selected set of extras and local SQLite, LanceDB and Qdrant Edge. This run did not measure general throughput, paid-provider response quality, distributed deployment, other Python versions, or the full optional integrations matrix. The shallow checkout constrained historical claims. [Pytest configuration][pytest-config] · [CI environment][pytest-ci] · [VCR mode and cassette directory][pytest-vcr]

### Controlled experiments

| Experiment | Setup and observable |
| --- | --- |
| Task context and async model pathway | Deterministic model pair in three public kickoff modes. Captured model messages, `Task.prompt_context`, model API used and thread identity. Tested explicit dependency, omitted context, disabled context and sync reference. |
| Shared executor and cohort lifetime | Held the first model call behind an event. Started a second public async task with the same or a separate agent. Recorded result attribution and sibling progress. A second two-agent experiment made one task raise while holding the sibling, then released the sibling after public failure to observe its callback. |
| Reused Crew, copying and replay | Ran a conditional twice with a changed outcome, cloned a Crew with colliding or distinct task content keys, compared two hierarchical kickoffs, and replayed shared and isolated backing database cases. Recorded model prompt tokens, actual task pointer, configured roster and SQLite task IDs. |
| Flow scheduling | Used application-owned async events to control ordinary fan-out failure and the order of two terminal listeners. Compared both-failed OR, successful fallback, unrelated error within a race batch, and a normal listener without the OR group. |
| Model checkpoint ownership and Crew hydration | Used OpenAI's actual SDK integration with an in-memory HTTPX transport returning deterministic Chat Completions. Compared explicit model-completion, default task-completion and wildcard checkpoints. Restored the first-task snapshot with omitted, explicit and disabled context. Repeated against the pinned import path and isolated serializers. |
| Flow checkpoint lifecycle | A consumer raised a controlled exception after receiving its input. Inspected the actual automatic JSON snapshot and restored via public Flow APIs. Compared completed start, completed listener and completed router configurations. |
| Parallel checkpoint snapshot | Compared naturally interleaved automatic snapshots with a deterministic event-record append during serialization. Repeated on both supported Pydantic versions. An experimental read lock removed the panic and allowed inspection of the restored multi-start routing. |
| JSON checkpoint write failure | Injected an OSError after a five-byte partial write through the real JSON provider in an isolated directory. The earlier checkpoint remained valid, and the new final-path file failed JSON decoding. This tested error handling without simulating an operating-system crash. |
| Flow pending feedback | A custom local provider paused a Flow using real SQLite. Hydrated two instances, resumed one, tested the already-loaded second instance and fresh-load rejection. Separately forced a downstream listener error and rechecked the database row. |
| Terminal events, usage and native loop | Captured real Crew terminal events around a raising callback. Metered two calls in a containing Flow. Held an event handler and compared loop responsiveness and flush thread identity in two async entry modes. |
| RPM skip | Replaced only the minute wait with a mock. Both model tool-calling paths showed two calls, one wait and the expected verbose message. A one-call native control showed zero waits and no throttle log. |

None of the gate waits served as elapsed-time padding. They set up controlled interleavings or isolated an actual join. Model outputs were fixed markers. Timing observations establish ordering and limited responsiveness under a held listener, with no throughput extrapolation.

## 7. Measurement audit

### Setup, skipped cases and revised hypotheses

- **Disk quota and package placement.** The first install reached the locked NumPy wheel and failed on an actual file write. `df -h` showed spare global tmpfs space, which the extraction error superseded. Repeating frozen resolution in a venv and cache on the disk-backed `/var/tmp` with explicit CPython completed. The source tree and lock remained unmodified.
- **Missing optionals.** `crewai_files` came from the declared `file-processing` extra. The initial collection error disappeared with it. Two `TestPlatformActionTool` cases, `test_a_platform_ref_amp_cannot_resolve_names_the_app`, `test_kickoff_response_format_with_planning_and_tools` and two deferred-reader cases all failed while importing `crewai_tools`. I enabled `tools` plus the tool package's `exa-py` extra, reran all six exact nodes, then reran their parent suites. Backend test markers were checked against the optional Qdrant Edge import. Those cases ran in the package-complete selection. These were setup limitations. [Crew extras][extras] · [Tool packaging][tool-package] · [Exa extra][exa-extra] · [Backend skip marker][memory-test-marker]
- **Workspace dependency metadata.** `uv pip check` evaluated 195 installed distributions. Instructor 1.15.1 requires Rich below 15, while the workspace override allowed locked 15.0.0. LiteLLM 1.105.3 requires Filelock below 4, while the workspace override selected locked 4.2.4 on Python 3.12. Native converter and local LiteLLM tests passed in these versions. This verifies runtime paths used in the tests and leaves general compatibility unverified. ChromaDB 1.5.9 declares ONNX Runtime unconditionally in its wheel, while the pinned workspace lock includes that edge only for Python below 3.11. The optional Chroma package was installed. A credential-free constructor for its default embedder failed because that dependency was absent, while a local collection worked with provided vectors. CrewAI's Chroma adapter takes its own embedding function. The result is specific to a missing dependency from the workspace lock and the upstream fallback's default embedder. [Workspace overrides][dependency-overrides] · [Filelock override][filelock-override] · [Chroma lock entry][lock-chroma] · [LiteLLM lock entry][lock-litellm] · [Chroma adapter][chroma-explicit]
- **LiteLLM's skipped VCR cases.** All nine tests are explicitly marked skipped. Selecting them through a temporary pytest hook verified that eight could play their recordings under the current dependencies. The one failing test asks for two completions, while its pinned file has only one matching POST. Both the VCR error and the cassette entries confirmed the exhausted playback. A repeat-enabled control passed and exercised two calls using the same recorded response. It diagnoses the fixture without establishing independent second-response coverage. [Skip marker][litellm-vcr-test] · [Multiple-call test][litellm-vcr-two] · [Pinned cassette][litellm-vcr-data]
- **VCR and imported package identity.** The initial suites ran with the workspace's network-blocking option and sanitized process environment, with cassettes drawn from the pinned archive. The final runs explicitly used `--record-mode=none`. All 595 cassette files matched the checkout. The fixture added only empty directories to the temporary copy. Five wheel trees matched the checkout's Python files. The major Crew scheduling, LLM checkpoint and Flow restore probes were rerun using the pinned source directly, ruling out a stale installed library or generated wrapper. No commit history was needed to inspect those code paths. [Network-blocking option][pytest-config] · [Cassette fixture][pytest-vcr]
- **RPM skip.** The selected release suite explicitly marks its VCR log assertion skipped. Source inspection found `enforce_rpm_limit` in both main executor routes. The first local probe assumed the ReAct parser strips `Final Answer:` in the native path too. That assertion was wrong for this fake response. I preserved the separate native/text rendering expectations and measured wait invocation and emitted log independently. The two-turn local control establishes that the skip reason is not a general absence of native throttling or logging. It leaves the original cassette's coverage and live rate limiting unmeasured. [Skipped test][rpm-test] · [Native limit call][agent-native] · [Rate controller][rpm-controller]
- **Warnings and misattributed coroutine allocation.** The aggregate warning count is large, primarily repeated `datetime.utcnow()` deprecations from instantiated memory models and storage defaults. Callback/config deprecations and optional behaviors account for much of the rest. The unawaited coroutine warning appeared under a later test because collection occurs after allocation. `-X tracemalloc=12` traced it to `test_run_calls_asyncio_run_for_async_tools`, which replaces the awaited call with a mock. Nearby direct async and sync execution tests passed. I did not count that warning as a normal tool execution defect. [Mocked bridge test][test-coroutine] · [Tool execution bridge][tool-claim] · [Memory timestamp defaults][memory-time]
- **Checkpoint serializer hypothesis.** The first end-to-end probe attempted to subscript a restored context list and found a sentinel. A minimal Task without an agent serialized a list correctly on both allowed Pydantic versions, invalidating the hypothesis that lists in this union always collapse. The assigned-dependency matrix reproduced the behavior before and after kickoff, with same or separate agents. A direct `TypeAdapter(list[Task])` serialized the same assigned dependency successfully. Removing the dependency's agent restored output shape. These controls establish the affected serialized field boundary without claiming a specific internal Pydantic dispatch algorithm. The hand-edited artifact was a temporary checkpoint copy used to isolate rebinding, not a modified source or shipped workaround. [Task context field][task-context-type] · [Sentinel][sentinel] · [Restore setup][crew-restore]

### Controls for the runtime findings

| Result | What the audit ruled out |
| --- | --- |
| Missing implicit async context | Same producer and consumer prompt path with different context selections. Unique tokens were visible in the sync, explicit-context and disabled-context controls as expected for each case. Source search found the only non-initializing write to `last_sync_output` in prefix restoration, not the normal sync-completion paths. |
| Shared-agent invocation and late sibling work | Thread/async events fixed the order. Different handlers and distinct agents gave successful control runs. The first task's next model call showed that mutation preceded reject-on-overlap. The late sibling experiment used distinct agents, ruling out the shared-executor guard as its cause. The Flow variant used true async listeners, ruling out a provider thread as the only source of the issue. |
| Conditional state, batch context and hierarchical roster | The tests held task definitions and model outputs constant while changing the conditional outcome, giving tasks distinct versus equal content keys, or repeating a run. Capturing actual prompts distinguished internal state from a logging artifact. Explicit assertions checked original versus copied dependency object, and actual run outputs showed the effect. |
| Retry exhaustion | A fresh agent at the same retry limit recovered from the same deterministic transient error. Separate task IDs and recorded model attempt counts isolated the failure from provider retry behavior, classification and a reused response. |
| Flow failure and final-output behavior | A plain listener error propagated without an OR cohort. A successful alternate ran its join. Both failures and independent sibling errors were delivered to the runtime, which reported them locally but returned normally. A separate two-lane test swapped completion order without changing topology to explain final-output differences. |
| Scope of replay | Verified A's task ID twice, once before and once after B's run. Queried the actual SQLite task rows and changed only the backing path for the isolation control. The result fits the documented latest-run contract. |
| No auto-checkpoint on model completion | Observed the completed event with task and response identity in a direct subscriber and in a later checkpoint's history. Default and wildcard checkpoints proved provider and handler registration and directory access. A real SQLite checkpoint repeated the test with row inspection, ruling out a JSON file backend problem. `flush()` completed. The source used for lookup is the provider object. The experiment tested the native OpenAI path and code-reviewed the shared emitter. |
| Partial Flow restore | Raw checkpoint progress and named outputs were inspected before restore. The callback failed by design only on the original run. Root-to-consumer resume was successful, while the completed listener/router cases lost their handoff. The two runtime entry points and source imports agreed. |
| Replay of typed task results | Initial kickoff returned the exact class, saved SQLite payload preserved its value, and replay actually called the second model again. The failing operation was access through the reconstructed prefix result. Tested raw, JSON and Pydantic variants on the locked and alternate supported Pydantic versions. The first probe inadvertently raised while formatting the returned model. It was corrected to record types, accessors and the call count separately. |
| Concurrent checkpoint serialization | The production-style failure arose with two ordinary async starts. Three fresh-process repeats showed that usable checkpoint count depends on interleaving. The small serializer gate held the existing event payload while a second record entered through the real write lock. A read lock around the dump allowed stable serialization and ruled out package import, missing providers or a corrupt JSON file. The lock control was in the probe process only. |
| Pending feedback lifetime | The control used fresh Flow instances and independent SQLite connections, a valid pending row and a successful first resume. A new lookup failed after consumption, while the earlier duplicate instance still resumed. The downstream-failure variant toggled only the listener outcome. |
| Contradictory terminal events | A real event subscriber captured both outcome types and their identical start ID. `flush()` and explicit callback exceptions differentiated actual terminal events from asynchronously reordered logs. |
| Usage and native-loop claims | Comparing Flow's event metrics with Crew's per-object counters distinguished provider totals from aggregation error. A distinct-model-instance control isolated double counting. A second model compatibility probe used the real OpenAI SDK with a local transport and reproduced the totals. Its initial request count assertion mistook token preflights for generations. Separating eight count requests from eight generation requests established comparable traffic and completion metrics. [OpenAI token preflight][openai-token-preflight] The loop check used real bus flushing, a captured loop-thread identity and the same blocking listener under native and threaded calls. It did not infer globally synchronous behavior from the `akickoff` name. |

### Scope of source-reviewed conclusions

The code shows a single-process coordinator with local stores and extension points. I traced source paths for atomicity, import trust, hook exception semantics and persistence of execution context. I did not simulate process crashes, compare remote providers for all model-event source classes, or exercise external service permissions. I confirmed the direct JSON write behavior with a partial-write injection. A truncated file remained at its final checkpoint path, while an earlier good snapshot was readable. The checkpoint credential-handling observation follows from the source's serialization contract. The public runtime results above were verified with local tests. [Checkpoint provider][checkpoint-json] · [Context capture][checkpoint-context] · [Hook abort handling][hook-dispatch]

## 8. Post-mortem

### How the tradeoffs accumulated

The causes below are inferred from the code structure and compatibility comments at the pin. The shallow history does not establish when each tradeoff was introduced.

1. **Configuration objects grew runtime responsibilities.** An ordered task list and reusable role-configured agents are effective for short scripts. The same objects also hold last output, prompt context, assigned agent, retry count and live executor bindings. Scope was added around individual pieces, such as failure collectors and event IDs, leaving the broader objects shared. That explains how a lock can prevent the second invocation and still let the second task's preparation alter the first. It also explains stale conditional results, repeated-run manager reassignment and lifetime retries. [Agent binding][agent-rebind] · [Invocation lock][agent-invoke] · [Task assignment][task-execute] · [Failure scope][tool-failure]
2. **Compatibility paths acquired independent scheduling and error decisions.** Separate sync, thread-bridged and native entry points serve real use cases. Agent inference and tool execution inside those paths still contain both direct and offloaded sync work. Task, Crew and tool execution repeat large result-processing and cleanup sections. Branches have accumulated separate decisions about what to await, cancel, retry and report. That is consistent with the observed split between threaded loop responsiveness and native finalization, and with the common missing update in both Crew schedulers. [Kickoff entry points][crew-thread-wrap] · [Native scheduling][crew-native] · [Tool invocation][tool-react] · [Blocking finalization][crew-result]
3. **Event history became a recovery surface.** The event graph is useful for tracing and selected replay. An automatic snapshot can give useful progress without making every method explicitly persist. Async listeners benefit from running off the work path, which creates an ownership question when they serialize the live run at the same time it records new events. The runtime then needs to reconstruct task aliases, output lifetimes and pending routes from mutable entities and event records. Event class, emitter and run owner are separate concepts, and a completed node name does not uniquely reconstruct its causal payload or next transition. The missing LLM trigger, changed task-context shape and skipped router continuation follow from those boundaries. [Event graph][event-record] · [Snapshot writer][checkpoint-writer] · [LLM source][model-event] · [Flow resume branch][flow-count]
4. **Best-effort observability and persistence keep the common path moving.** Optional listeners, lazy provider SDKs and local fallback stores let programs run without extensive services. Outcomes still need strict ownership when downstream code can fail or when one listener participates in execution correctness. Treating callbacks, fan-out, tracing and checkpoints as ancillary can produce conflicting terminal signals, missing snapshots, or an action that outlives the result. That matters most for a long-running flow with effectful tools and human handoffs. [Event delivery][event-emit] · [Checkpoint dispatch][checkpoint-dispatch] · [Feedback resume][flow-resume-clear] · [Crew finalization][crew-result]

### Likely operational failure modes

- An integration consuming completion events can acknowledge work before a callback surfaces failure. A retry may then run while a sibling from the first attempt still owns effectful work. Later successful callbacks, inconsistent terminal signals and duplicated business operations are distinct symptoms of the same ownership problem. [Crew finalization][crew-result] · [Public failure path][crew-kickoff] · [Async join][crew-native-join]
- A paused human-review workflow can resume once from the intended row and again from a consumer that already hydrated it. Combining that behavior with a snapshot that resumes the wrong edge or loses a payload can leave third-party operations ahead of the durable workflow record. Idempotency and careful run ownership are most important around that boundary. [Feedback resume][flow-resume-clear] · [Flow restore][flow-start-resume] · [Listener resume][flow-count]
- Checkpoints on common high-frequency events can appear healthy in simple, sequential tests. Under fan-out, the event or progress representation may be read during another update. A surviving saved file then needs independent verification of its trigger, saved edge outputs and usable schema before it can support recovery. [Checkpoint writer][checkpoint-writer] · [Event graph][event-record] · [Checkpoint serialization][checkpoint-runtime]

### Highest-leverage improvements

1. **Separate definitions from per-run and per-task execution state.** Make the executor's task, tool schema, inputs, retry counters and messages invocation-owned. Allocate a fresh executor state or hold admission across the first binding mutation through cleanup. Resolve context from current-run outputs by stable task identity. Keep authored assignee separate from effective manager. Capture and settle sibling work on failure through structured task ownership, with an explicit policy for thread-backed actions that have already started. First regression cases should reproduce the gated same-agent overlap and verify that one failed cohort cannot publish completion after its parent is terminal. [Binding][agent-rebind] · [Join behavior][crew-join] · [Async join][crew-native-join]
2. **Normalize durable workflow progress.** Use canonical task IDs and dependency references, an explicit versioned schema, and recorded edge or routing state alongside completed nodes. Checkpoint triggers should resolve to the execution owner using explicit IDs and policy, and restore should validate those references and forward saved inputs. Key replay records to execution and make “latest” a query. Reconstruct typed outputs with the workflow's validated output schema and record the version needed to resolve it. Take stable event and progress snapshots before asynchronous writes, make checkpoint replacement atomic, and define a claim/commit lifecycle for pending feedback. External side effects still need idempotency keys or application-owned compensation. [Replay store][replay-sql] · [Checkpoint schema][checkpoint-runtime] · [Flow restore][flow-start-resume] · [Feedback SQLite operations][flow-sql-pending]
3. **Give each run one authoritative outcome and meter.** Resolve legacy callbacks and final hooks before publishing one terminal result. Preserve distinct outcomes for cancelled, failed, paused and successful work, and aggregate usage by run and call ID. An OR race should suppress loser failures only when a winner exists, maintain ordinary error propagation outside the race, and await cancellation cleanup. Record policy handler errors distinctly from successful policy evaluation. [Crew finalization][crew-result] · [Flow race][flow-race] · [Flow usage listener][flow-usage] · [Hook dispatch][hook-dispatch]
4. **Enforce async and side-effect contracts across extension points.** Route async-capable provider calls through their async adapters, move unavoidable synchronous waits off the caller loop, and bound fan-out by configured capacity. Retain explicit limits for safe parallel tool calls and add an application-facing way to declare order or shared resource constraints. Use the same deterministic transport and barrier tests across all published execution variants. Add a checkpoint matrix across triggers, providers, graph shapes, partial completion and model/config restore. [Offload behavior][flow-method] · [Native tool batching][tool-native] · [Crew batch fan-out][crew-batch] · [Checkpoint provider contract][checkpoint-provider]

## 9. Evidence appendix

### UTC work log

| UTC window on 2026-11-18 | Active work |
| --- | --- |
| 23:00:40–23:03 | Verified HEAD, worktree and shallow status. Read the evaluation rubric and workspace rules. Mapped package, Crew and Flow entry points. Moved the dependency installation after the quota failure and resolved the first optional import. |
| 23:03–23:07 | Traced Task and Agent requests into the executor. Ran context, retries, overlap, Flow race and terminal event experiments. Read both suite failure logs and reran their six failing tests with the required tool extras. |
| 23:07–23:11 | Followed the event and checkpoint ownership paths. Ran the local SDK trigger and context restore experiments. Separated warnings from failures. Started expanded interface and combined regressions. Compared metrics and caller-loop finalization. |
| 23:11–23:15 | Isolated serializer behavior with real Task shapes and a second allowed Pydantic version. Tested SQLite feedback continuation and verified wheels against pinned files. Ran Flow checkpoint payload and route cases. Drafted architecture and invariants with line evidence. |
| 23:15–23:20 | Traced memory, tool policy and storage boundaries, confirmed partial Flow restore, audited the RPM skip, reran the primary probes with direct source imports and recorded both the findings and the measurement controls. |
| 23:20–23:30:45 | Traced typed-output replay, tested SQLite and multi-start checkpoint controls, isolated the concurrent snapshot race and audited dependency metadata. Checked skipped cassettes, ran a checkpoint write-failure control and reran usage with the SDK transport. Validated references, reproduction commands and final checkout status. |

### Environment, build and provenance commands

These commands summarize the executed invocations. `$R` names the checkout in section 1, `$T` is the disk-backed experiment directory, and `$P` names its isolated interpreter. Continued tests ran from `$T/tree`.

```bash
date -u +'%Y-%m-%dT%H:%M:%SZ'
git rev-parse HEAD
git status --porcelain=v1 --untracked-files=all
git log -1 --format=fuller
git rev-parse --is-shallow-repository
git remote -v
cat ../../evaluations/README.md
cat AGENTS.md

T=/var/tmp/crewai-eval.63RRlA1f
P="$T/frozen/bin/python"
df -h /tmp /var/tmp $HOME
env UV_CACHE_DIR=/tmp/crewai-eval.wVnoEYZu/uv \
    UV_PROJECT_ENVIRONMENT=/tmp/crewai-eval.wVnoEYZu/frozen \
    PYTHONDONTWRITEBYTECODE=1 \
    uv sync --frozen --package crewai --no-install-local --python 3.12
env TMPDIR="$T" UV_CACHE_DIR="$T/uv" UV_PROJECT_ENVIRONMENT="$T/frozen" \
    PYTHONDONTWRITEBYTECODE=1 \
    uv sync --frozen --package crewai --no-editable --python "$(command -v python)"
env TMPDIR="$T" UV_CACHE_DIR="$T/uv" uv pip install --python "$P" \
    pytest==9.0.3 pytest-asyncio==1.3.0 pytest-subprocess==1.5.3 \
    vcrpy==8.2.1 pytest-recording==0.13.4 pytest-randomly==4.0.1 \
    pytest-timeout==2.4.0 pytest-xdist==3.8.0 pytest-split==0.11.0 ruff==0.15.1
git archive HEAD -- lib pyproject.toml conftest.py .env.test .github .python-version \
    | tar -x -C "$T/tree"
env TMPDIR="$T" UV_CACHE_DIR="$T/uv" UV_PROJECT_ENVIRONMENT="$T/frozen" \
    PYTHONDONTWRITEBYTECODE=1 \
    uv sync --frozen --package crewai --no-editable --inexact --python "$(command -v python)" \
    --extra file-processing --extra a2a --extra anthropic --extra litellm \
    --extra azure-ai-inference --extra bedrock --extra google-genai --extra chromadb
# Repeated this command adding --extra tools --extra qdrant-edge.
env TMPDIR="$T" UV_CACHE_DIR="$T/uv" UV_PROJECT_ENVIRONMENT="$T/frozen" \
    PYTHONDONTWRITEBYTECODE=1 \
    uv sync --frozen --package crewai-tools --extra exa-py --no-editable --inexact \
    --python "$(command -v python)"
env TMPDIR="$T" UV_CACHE_DIR="$T/uv" uv pip install --target "$T/pyd211" \
    --python "$P" 'pydantic==2.11.10'
env TMPDIR="$T" UV_CACHE_DIR="$T/uv" uv pip check --python "$P"

"$T/frozen/bin/ruff" check --no-fix --no-cache \
    lib/crewai/src/crewai/{crew.py,task.py,agent,agents,flow,state,hooks,mcp,events,llms,memory,crews} \
    lib/crewai-core/src/crewai_core
"$T/frozen/bin/ruff" format --check --no-cache \
    lib/crewai/src/crewai/{crew.py,task.py,agent,agents,flow,state,hooks,mcp,events,llms,memory,crews} \
    lib/crewai-core/src/crewai_core
```

The provenance check enumerated `git ls-files` under each package, compared installed and tracked Python bytes, and ran `ast.parse` for the two core package trees. Separate checks used `rg -n` and `nl -ba` against the pinned checkout. Python function lengths subtract AST line endpoints and add one. The package and tests have no dependency on previous commits for these checks. [Workspace config][workspace] · [Core Python range][dependencies]

### Exact test selections

The initial core and extended attempts ran the corresponding arrays below separately with the same pytest arguments except `--record-mode=none`. The first collection and core runs used `-n 0`. The first expanded run used `-n 4`. The later combined and focused runs reproduced the intended CI cassette policy. `run.sh` uses `env -i` to set temporary home, storage, XDG and cache locations, and invokes the isolated interpreter with bytecode disabled.

```bash
C=lib/crewai/tests
core=(
  "$C/crew" "$C/task" "$C/test_custom_llm.py" "$C/test_flow.py"
  "$C/test_flow_persistence.py" "$C/test_flow_resumability_regression.py"
  "$C/events" "$C/utilities/events" "$C/hooks" "$C/tools" "$C/test_checkpoint.py"
)
expanded=(
  "$C/test_flow_definition.py" "$C/test_flow_from_definition.py"
  "$C/test_flow_tool_action_usage.py" "$C/test_flow_tool_action_failure_policy.py"
  "$C/test_flow_persistence_factory.py" "$C/test_async_human_feedback.py"
  "$C/test_task_guardrails.py" "$C/test_sqlite_connection_lifecycle.py" "$C/storage"
  "$C/agents/test_agent_execution_timeout.py" "$C/agents/test_crew_agent_parser.py"
  "$C/agents/test_agent_executor.py" "$C/agents/test_native_tool_hook_contract.py"
  "$C/agents/test_react_tool_hook_contract.py" "$C/llms/test_base_llm.py"
  "$C/llms/test_retry.py" "$C/memory/test_storage_backend_contract.py"
  "$C/memory/test_storage_backend_async_parity.py" "$C/memory/test_concurrent_storage.py"
  "$C/memory/test_lancedb_update.py" "$C/memory/test_unified_memory.py"
)
interfaces=(
  "$C/mcp" "$C/a2a/utils" "$C/knowledge/test_storage_factory.py"
  "$C/knowledge/test_knowledge_storage_providers.py" "$C/memory/test_qdrant_edge_storage.py"
  "$C/memory/test_storage_backend_contract.py" "$C/memory/test_storage_backend_async_parity.py"
  "$C/memory/test_dimension_mismatch.py" "$C/telemetry/test_trace_lifecycle.py"
  "$C/telemetry/test_event_trace_session.py" "$C/telemetry/test_task_failure_instrumentation.py"
  "$C/telemetry/test_execution_span_assignment.py" "$C/test_flow_usage_metrics.py"
  "$C/test_crew_copy_resume_state.py" "$C/test_crew_thread_safety.py"
  "$C/llms/openai/test_responses_tool_loop.py" "$C/llms/hooks"
  lib/crewai-core/tests/test_runtime_env.py lib/crewai-core/tests/test_settings.py
)
lifecycle=(
  "$C/test_crew.py" "$C/test_context.py" "$C/test_guardrail_events_on_exception.py"
  "$C/test_stream_frames.py" "$C/test_streaming.py" "$C/test_streaming_integration.py"
  "$C/utilities/test_structured_planning.py" "$C/agents/test_agent_reasoning.py"
  "$C/project/test_crew_loader.py" "$C/project/test_json_loader.py"
)
bash "$T/run.sh" combined -m pytest -n 4 -p no:randomly -p no:cacheprovider \
    --record-mode=none -rs --basetemp="$T/runs/combined/pytest" "${core[@]}" "${expanded[@]}"
bash "$T/run.sh" interfaces -m pytest -n 4 -p no:randomly -p no:cacheprovider \
    --record-mode=none -rs --basetemp="$T/runs/interfaces/pytest" "${interfaces[@]}"
bash "$T/run.sh" lifecycle -m pytest -n 2 -p no:randomly -p no:cacheprovider \
    --record-mode=none -rs --basetemp="$T/runs/lifecycle/pytest" "${lifecycle[@]}"
bash "$T/run.sh" focused-retry -m pytest -n 0 -p no:randomly -p no:cacheprovider \
    --basetemp="$T/runs/focused-retry/pytest" \
    "$C/tools/test_tool_failure.py::TestPlatformActionTool" \
    "$C/test_flow_from_definition.py::test_a_platform_ref_amp_cannot_resolve_names_the_app" \
    "$C/agents/test_agent_executor.py::TestResponseFormatWithKickoff::test_kickoff_response_format_with_planning_and_tools" \
    "$C/agents/test_agent_executor.py::TestDeferredNativeToolResults::test_existing_file_reader_keeps_local_access_when_artifact_reader_is_added" \
    "$C/agents/test_agent_executor.py::TestDeferredNativeToolResults::test_cleanup_removes_artifact_and_revokes_existing_reader_alias"
bash "$T/run.sh" async-tool-audit -X tracemalloc=12 -m pytest -n 0 -p no:randomly \
    -p no:cacheprovider --basetemp="$T/runs/async-tool-audit/pytest" \
    -W error::pytest.PytestUnraisableExceptionWarning \
    "$C/tools/test_async_tools.py" "$C/tools/test_base_tool.py"
bash "$T/run.sh" dep-audit -m pytest -n 2 -p no:randomly -p no:cacheprovider \
    --record-mode=none -rs --basetemp="$T/runs/dep-audit/pytest" \
    "$C/test_task_converter_output.py" "$C/utilities/test_converter.py" \
    "$C/llms/litellm/test_litellm_async.py" "$C/rag/chromadb/test_client.py"
bash "$T/run.sh" litellm-local -m pytest -n 0 -p no:randomly -p no:cacheprovider \
    --record-mode=none --basetemp="$T/runs/litellm-local/pytest" \
    "$C/test_llm_litellm_usage_events.py" "$C/test_llm_litellm_streaming_errors.py" \
    "$C/llms/litellm/test_litellm_import_compat.py"
bash "$T/run.sh" litellm-nine "$T/read_one_cassette.py" -n 0 -p no:randomly \
    -p no:cacheprovider --record-mode=none --basetemp="$T/runs/litellm-nine/pytest" \
    "$C/llms/litellm/test_litellm_async.py"
bash "$T/run.sh" litellm-repeat "$T/repeat_one_cassette.py" -n 0 -p no:randomly \
    -p no:cacheprovider --record-mode=none --basetemp="$T/runs/litellm-repeat/pytest" \
    "$C/llms/litellm/test_litellm_async.py::test_litellm_async_multiple_calls"
```

### Probe commands and primary evidence

Each `bash "$T/run.sh" <run-name> "$T/<script>"` call below used isolated storage. Outputs were redirected to `$T/runs/<run-name>.log`. The experiments in this report contain the setup, changed variable and outcome so they can be recreated independently of temporary files.

| Run name | Script | Key output or controlled comparison |
| --- | --- | --- |
| `crewprobe` | `crew_probes.py` | Sync consumer saw producer. Implicit async context empty, explicit context correct. Default inference used `call` in a worker. Shared retry counts 2 and 1 versus separate counts 2 and 2. |
| `concurrency` | `crew_concurrency.py` | Shared executor rejected a second invocation after misbinding the first. Separate agent control passed. A gated sibling callback ran after failure returned, in both Crew modes. |
| `crewstate` | `crew_state_probes.py` | Conditional skipped output empty while downstream prompt kept old token. Equal-key copy selected the second task. Latest-run replay A lost after B unless database separated. Contradictory terminal events shared one start ID. Reused hierarchy expanded its worker scope. |
| `flowprobe` | `flow_probes.py` | Race fallback success, all-failure normal return, extra branch failure suppressed. Non-race control propagated. A regular fan-out sibling completed after kickoff raised. Swapping branch completion swapped the final output. |
| `checkpointprobe2` | `checkpoint_probes.py` | Actual model event arrived with response ID, no model-event checkpoint. Defaults saved. Task-completion restore ran B/C and changed explicit context to implicit. Alternate snapshot restored a detached task pointer. |
| `serializeprobe` and `serialize211` | `serialize_probe.py` | Assigned dependency serialized as sentinel on two allowed Pydantic versions. No-agent and direct list serializer controls succeeded. The 2.11.10 run prepended `$T/pyd211` in a separate process. |
| `flowcheckpointprobe` | `flow_checkpoint_probe.py` | An automatically saved completed listener had its output in the snapshot, but the resumed consumer received `None`. Router-label consumer skipped. Completed-start control passed. |
| `feedbackprobe` | `feedback_probe.py` | SQLite pending row cleared. Already-loaded second continuation ran anyway. A downstream error also left the row cleared. |
| `usageprobe` and `usagetransport3` | `usage_probe.py` and `usage_transport_probe.py` | Two 13-token calls per kickoff measured 26 by the containing Flow. Crew totals depended on previous runs and shared provider identity. |
| `loopprobe` | `loop_probe.py` | Native Crew flush blocked the caller loop during a held handler. Thread-wrapped kickoff with the same handler left the loop responsive. |
| `rpmprobe2` | `rpm_probe.py` | One mocked wait and verbose throttle message for two calls in each provider mode. Zero for one native call. |
| `sqlitecheckpoint` | `sqlite_checkpoint_trigger.py` | SQLite 3.53.1 recorded one task-completion checkpoint. The model-completion event was delivered but produced zero SQLite rows. |
| `multistart`, three fresh-process reruns and `multistartlock` | `multi_start_checkpoint.py` | The first unguarded run produced concurrent snapshot exceptions. The repeat runs produced the incorrect common payload for both restored starts. The read-lock control produced a clean snapshot with the same routing outcome. |
| `snapshotrace` and `snapshotrace211` | `event_snapshot_race.py` | A writer entered while Pydantic serialized a live event record. Controlled failure on 2.12.5 and 2.11.10. With a read lock the saved record held one event and the original later held two. |
| `jsonwrite` | `json_write_probe.py` | Partial write left a truncated file at the generated checkpoint's final path, and an earlier checkpoint remained valid. |
| `chromaprobe` | `chroma_probe.py` | Matched active package requirements to installed metadata. The Chroma default embedder lacked ONNX, and an ephemeral collection using supplied vectors worked. |
| `typedreplay2` and `typedreplay211` | `typed_replay_probe.py` | Compared raw, JSON and Pydantic results after replay of the next task. Verified the stored JSON row and public result access on both Pydantic versions. |

Direct source reruns used `PYTHONPATH="$R/lib/crewai/src:$R/lib/crewai-core/src"` with `$P` and the scripts `crew_probes.py`, `crew_concurrency.py`, `checkpoint_probes.py` and `flow_checkpoint_probe.py`. The temporary source tree remained an archive of the pin plus isolated test outputs. When comparing cassette directories, the path-level diff showed empty directories added by fixture setup. The file-level checksum check confirmed equality.

### Final verification

```bash
git rev-parse HEAD
git diff --exit-code HEAD -- lib
git status --porcelain=v1 --untracked-files=all
test -s ../../evaluations/crewAIInc__crewAI.md
date -u +'%Y-%m-%dT%H:%M:%SZ'
```

### Local source references

[a2a]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/a2a/utils/delegation.py:516
[agent-ainvoke]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agents/agent_executor.py:3229
[agent-artifacts]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agents/agent_executor.py:312
[agent-async]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agent/core.py:1197
[agent-finalize]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agent/core.py:871
[agent-invoke]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agents/agent_executor.py:3132
[agent-iterations]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agents/agent_executor.py:2520
[agent-memory]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agents/agent_builder/base_agent_executor.py:31
[agent-native]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agents/agent_executor.py:1724
[agent-plan]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agents/agent_executor.py:573
[agent-prepare]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agent/core.py:708
[agent-react]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agents/agent_executor.py:1642
[agent-rebind]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agent/core.py:1343
[agent-recovery]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agents/agent_executor.py:3094
[agent-retry]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agent/core.py:908
[agent-retry-field]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agent/core.py:325
[agent-state]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agents/agent_executor.py:165
[agent-sync]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agent/core.py:1031
[agent-synthesis]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agents/agent_executor.py:2768
[agent-todos]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agents/agent_executor.py:1448
[checkpoint-config]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/state/checkpoint_config.py:160
[checkpoint-context]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/context.py:85
[checkpoint-dispatch]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/state/checkpoint_listener.py:219
[checkpoint-docs]: repos/crewAIInc__crewAI/docs/edge/en/concepts/checkpointing.mdx:27
[checkpoint-fields]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/state/runtime.py:52
[checkpoint-json]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/state/provider/json_provider.py:37
[checkpoint-owner]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/state/checkpoint_listener.py:88
[checkpoint-provider]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/state/provider/core.py:10
[checkpoint-runtime]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/state/runtime.py:183
[checkpoint-sql]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/state/provider/sqlite_provider.py:50
[checkpoint-trust]: repos/crewAIInc__crewAI/docs/edge/en/concepts/checkpointing.mdx:54
[checkpoint-writer]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/state/checkpoint_listener.py:113
[conditional]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crews/utils.py:180
[conditional-type]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/tasks/conditional_task.py:41
[context-format]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/utilities/formatter.py:16
[crew-akickoff]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:1226
[crew-batch]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crews/utils.py:424
[crew-cache]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:233
[crew-context]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:1895
[crew-copy]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:2233
[crew-join]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:2035
[crew-kickoff]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:1006
[crew-manager]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:1542
[crew-manager-tools]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:1881
[crew-native]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:1365
[crew-native-join]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:1459
[crew-plan]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:1475
[crew-project]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/project/crew_base.py:193
[crew-replay]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:2061
[crew-restore]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:483
[crew-result]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:1949
[crew-store]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:1503
[crew-sync]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:1586
[crew-thread-wrap]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:1146
[crew-tools]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:1673
[crew-usage]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:2327
[crew-validate]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:781
[delegation]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/tools/agent_tools/base_agent_tools.py:46
[delegation-roster]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/tools/agent_tools/agent_tools.py:16
[dependencies]: repos/crewAIInc__crewAI/lib/crewai/pyproject.toml:9
[event-emit]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/events/event_bus.py:537
[event-flush]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/events/event_bus.py:734
[event-ids]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/events/base_events.py:66
[event-record]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/state/event_record.py:99
[event-replay]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/events/event_bus.py:673
[event-runtime]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/events/event_bus.py:282
[exa-extra]: repos/crewAIInc__crewAI/lib/crewai-tools/pyproject.toml:102
[execution-lifetime]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/execution.py:89
[extras]: repos/crewAIInc__crewAI/lib/crewai/pyproject.toml:59
[flow-actions]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/_actions.py:190
[flow-bind]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:840
[flow-completion]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:3044
[flow-count]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:3363
[flow-definition]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/flow_definition.py:650
[flow-each]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/_actions.py:373
[flow-entry]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:2195
[flow-factory]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/persistence/factory.py:31
[flow-fanout]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:3280
[flow-kickoff]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:2341
[flow-method]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:3013
[flow-pause]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:2464
[flow-pending]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:1260
[flow-persist]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:3124
[flow-public]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/flow.py:1
[flow-race]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:1135
[flow-result]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:2523
[flow-resume]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:1469
[flow-resume-clear]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:1543
[flow-route]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:3183
[flow-script]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/_actions.py:312
[flow-sql]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/persistence/sqlite.py:91
[flow-sql-pending]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/persistence/sqlite.py:285
[flow-start-resume]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:2849
[flow-starts]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:2437
[flow-state]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:1708
[flow-usage]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:940
[hook-dispatch]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/hooks/dispatch.py:265
[hook-scope]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/hooks/dispatch.py:159
[knowledge]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/knowledge/knowledge.py:111
[llm-base]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/llms/base_llm.py:222
[llm-factory]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/llm.py:298
[llm-retry]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/llms/retry.py:124
[llm-usage]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/llms/base_llm.py:1212
[mcp-client]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/mcp/client.py:453
[mcp-resolver]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/mcp/tool_resolver.py:335
[memory-backend]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/memory/storage/backend.py:44
[memory-config]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/memory/unified_memory.py:76
[memory-encode]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/memory/encoding_flow.py:75
[memory-factory]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/memory/storage/factory.py:33
[memory-recall]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/memory/recall_flow.py:58
[memory-save]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/memory/storage/lancedb_storage.py:314
[memory-save-pool]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/memory/unified_memory.py:302
[memory-test-marker]: repos/crewAIInc__crewAI/lib/crewai/tests/memory/test_storage_backend_contract.py:22
[memory-time]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/memory/types.py:20
[memory-write]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/memory/storage/lancedb_storage.py:153
[model-event]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/llms/base_llm.py:846
[prepare-kickoff]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crews/utils.py:243
[prepare-task]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crews/utils.py:118
[pytest-ci]: repos/crewAIInc__crewAI/.github/workflows/tests.yml:30
[pytest-config]: repos/crewAIInc__crewAI/pyproject.toml:139
[pytest-fixtures]: repos/crewAIInc__crewAI/conftest.py:190
[pytest-vcr]: repos/crewAIInc__crewAI/conftest.py:413
[replay-docs]: repos/crewAIInc__crewAI/docs/edge/en/concepts/crews.mdx:434
[replay-encoder]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/utilities/crew_json_encoder.py:15
[replay-materialize]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/crew.py:2158
[replay-sql]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/memory/storage/kickoff_task_outputs_storage.py:25
[rpm-controller]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/utilities/rpm_controller.py:38
[rpm-test]: repos/crewAIInc__crewAI/lib/crewai/tests/test_crew.py:894
[sentinel]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/utilities/constants.py:72
[streaming]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/utilities/streaming.py:482
[task-context-type]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/task.py:174
[task-convert]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/task.py:1288
[task-docs]: repos/crewAIInc__crewAI/docs/edge/en/concepts/tasks.mdx:795
[task-execute]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/task.py:691
[task-execute-sync]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/task.py:850
[task-guardrail]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/task.py:1425
[task-key]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/task.py:636
[task-output]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/tasks/task_output.py:23
[test-async-crew]: repos/crewAIInc__crewAI/lib/crewai/tests/crew/test_async_crew.py:45
[test-coroutine]: repos/crewAIInc__crewAI/lib/crewai/tests/tools/test_base_tool.py:187
[test-definition]: repos/crewAIInc__crewAI/lib/crewai/tests/test_flow_from_definition.py:90
[test-native-hooks]: repos/crewAIInc__crewAI/lib/crewai/tests/agents/test_native_tool_hook_contract.py:1
[test-resume]: repos/crewAIInc__crewAI/lib/crewai/tests/test_flow_resumability_regression.py:12
[test-resume-crew]: repos/crewAIInc__crewAI/lib/crewai/tests/test_checkpoint.py:989
[todo-dependencies]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/utilities/planning_types.py:112
[tool-async]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/tools/tool_usage.py:238
[tool-claim]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/tools/base_tool.py:329
[tool-failure]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/tools/tool_failure.py:180
[tool-native]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agents/agent_executor.py:2010
[tool-native-single]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agents/agent_executor.py:2231
[tool-package]: repos/crewAIInc__crewAI/lib/crewai-tools/pyproject.toml:9
[tool-react]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/tools/tool_usage.py:503
[tool-structured]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/tools/structured_tool.py:356
[tool-trust]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/tools/base_tool.py:59
[trace-session]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/telemetry/tracing/session.py:117
[trace-setup]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/execution.py:154
[type-config]: repos/crewAIInc__crewAI/pyproject.toml:121
[workspace]: repos/crewAIInc__crewAI/pyproject.toml:384
[dependency-overrides]: repos/crewAIInc__crewAI/pyproject.toml:332
[filelock-override]: repos/crewAIInc__crewAI/pyproject.toml:365
[lock-chroma]: repos/crewAIInc__crewAI/uv.lock:1118
[lock-litellm]: repos/crewAIInc__crewAI/uv.lock:4424
[chroma-explicit]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/rag/chromadb/client.py:52
[litellm-vcr-test]: repos/crewAIInc__crewAI/lib/crewai/tests/llms/litellm/test_litellm_async.py:8
[litellm-vcr-two]: repos/crewAIInc__crewAI/lib/crewai/tests/llms/litellm/test_litellm_async.py:86
[litellm-vcr-data]: repos/crewAIInc__crewAI/lib/crewai/tests/cassettes/llms/litellm/test_litellm_async_multiple_calls.yaml:1
[openai-token-preflight]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/llms/providers/openai/completion.py:594
[flow-hook-boundary]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/flow/runtime/__init__.py:2627
[agent-adapter]: repos/crewAIInc__crewAI/lib/crewai/src/crewai/agents/agent_adapters/base_agent_adapter.py:15
