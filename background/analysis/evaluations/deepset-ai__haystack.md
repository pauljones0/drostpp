# Haystack core architecture review

## 1. Snapshot, scope, and active work

| Item | Evidence |
| --- | --- |
| Checkout | `repos/deepset-ai__haystack` in the evaluation workspace |
| Pinned HEAD | `bbf5b2b429670fa866e388f9a734ff3b1c652bf8` |
| Commit | 2026-11-18 15:25:14 +01:00, `build(deps): bump actions/setup-go from 7.0.0 to 7.1.0 (#13804)` |
| Fresh review started | 2026-11-19 03:39:55 UTC. HEAD matched and porcelain status was empty, including untracked files. |
| Fresh review ended | 2026-11-19 04:10:36 UTC. HEAD matched, porcelain status remained empty, and both staged and unstaged diff checks passed. |
| Active review time | 30 minutes 11 seconds (30.18 minutes). The 30-minute, 41-second wall interval excludes 30 seconds of tool turnaround. Earlier attempts and archive generation contribute zero active time. |

The review covered component contracts, graph construction and execution, lifecycle, typing, composition, Agent and tool orchestration, streaming, checkpointing, and observability. I used the checkout, repository tests as behavioral contracts, and completed local artifacts under `$HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out`. The active-time figure covers the fresh source and artifact review, drafting, and verification. I read the complete protocol and applicable repository instructions, including the root, test, and compaction guidelines and their `CLAUDE.md` pointers. [Evaluation protocol][rubric], [repository instructions][repo-instructions], [test instructions][test-instructions], [compaction instructions][compaction-instructions].

The socket model and per-run bookkeeping make ordinary retrieval, routing, and feedback graphs easy to compose and diagnose. The highest-impact weakness is at the point where the scheduler admits work. Different dispatch paths enforce the visit cap differently. Stream completion and snapshot recovery also need more explicit contracts at failure boundaries. The archived dependency failures are a separate measurement result.

## 2. Architecture and end-to-end control and data flow

### Public runtime and component contracts

At this SHA the public class is `Pipeline`. It implements `run`, `run_async`, `run_async_generator`, and `stream`. The repository's 3.0 instructions record the removal of `AsyncPipeline` and `ToolInvoker`. The async implementation reviewed here resides in `Pipeline`, and Agent owns tool invocation. [Public exports][exports], [runtime entry points][pipeline-class], [3.0 API instructions][api-instructions].

`@component` rebuilds and registers the class with `ComponentMeta`. After construction, the metaclass extracts named input sockets from the resolved `run` signature and defaults. Components accepting `**kwargs` can declare instance-specific sockets. Output sockets come from `@component.output_types` or an instance-level declaration. The metaclass requires a coroutine for `run_async` and checks the two methods' input signatures and declared outputs. This lets graph construction, introspection, execution, and wrappers all consult the same metadata. A missing default makes a socket mandatory even when its type admits `None`. [Component registry][component-registry], [socket construction][component-meta], [dynamic sockets][dynamic-sockets], [input socket types][socket-types].

### Graph construction and interface validation

`PipelineBase` owns a NetworkX directed multigraph. Nodes hold component instances and socket metadata. Edges carry sender and receiver sockets, endpoint names and an optional conversion strategy. The instance belongs to one pipeline and one name at a time. Removal clears reciprocal socket references and ownership. `add_components` preflights the batch, while `connect_many` deliberately retains earlier successful connections if a later one fails. Multi-node cycles are supported. `connect` rejects direct self-connections. [Graph initialization][graph-init], [batch add and ownership][graph-add], [component removal][graph-remove], [connect and batch connection][graph-connect].

`connect` accepts qualified socket names and component-only shorthand. It enumerates compatible endpoint pairs, prefers strict annotation matches, and uses a unique same-name match to disambiguate. Unresolved ambiguity is an error. Exact duplicate connections are idempotent. Ordinary sockets have a single source. Eligible list sockets are promoted to lazy variadic and flatten the incoming lists by one level. Explicit `Variadic[T]` receives a list of `T` values, including a list of lists if `T` itself is a list. `GreedyVariadic[T]` receives at most one value wrapped in a list. [Connection resolution][graph-match], [edge registration][graph-edge], [auto-variadic sockets][auto-variadic], [input consumption][consume].

Declared edge types are a wiring check. Compatibility handles common generics, unions, subclasses, and callable shapes. Supported conversions include string and `ChatMessage` adapters and list wrapping. List-to-scalar conversion is limited to the string or chat-message cases and requires exactly one item at runtime. Disabling connection type validation also disables conversion selection. Graph inputs are checked for component and socket names, required open sockets, and conflicting sources. The scheduler generally calls the component with the resulting Python values, checks that its result is a `Mapping`, and warns on undeclared keys. Strict handlers, conversions, and adapters supply additional value checks at their own boundaries. [Type compatibility][strict-types], [conversion selection][conversions], [runtime conversion][convert-value], [input validation][validate-input], [invocation and output check][sync-invoke], [output-key diagnostics][output-warnings].

### The data path

1. A run warms the graph's components and normalizes the input dictionary. Explicit nested input addresses a component and socket. Flat input is distributed by matching exposed socket names, which can fan out to more than one component. There is a special case for dict-valued flat input. Unmatched flat keys are logged. The normalizer copies ordinary payloads, then the scheduler records each supplied value under its component and socket with `sender=None`. [Sync initialization][sync-init], [flat and nested input normalization][prepare-input], [input entries][input-ledger].
2. Dispatch consumes the available entries and assembles keyword arguments. It strips absence markers, keeps external values reusable on non-greedy sockets, and fills socket defaults at the invocation boundary. The component receives a separate best-effort copy. Declared lifecycle methods run before scheduling and may initialize reusable resources. `close` and `close_async` explicitly delegate cleanup to components. [Input consumption][consume], [socket defaults][defaults], [component invocation][sync-invoke], [lifecycle][lifecycle].
3. Every outgoing edge gets either a value or the serializable `_NoOutputProduced` marker for an omitted key. `None`, an empty list, or an empty string are values. The marker records that the source ran and leaves mandatory data missing. A standard or greedy socket holds one entry and a marker cannot overwrite an existing value. A lazy socket appends entries for subsequent ordered consumption. [Absence marker][no-output], [edge delivery][write-output], [socket write helpers][socket-writes].
4. The result keeps unconnected output keys at socket granularity. A component with outgoing edges can therefore still contribute unconnected outputs. `include_outputs_from` retains the full mapping, including an explicitly requested empty result. When a visit contributes no output and the component was excluded from that set, a previously returned unconnected result can remain in the aggregate. [Pruning][prune], [socket-level pruning contract][pruning-test], [sync result update][sync-results], [async result update][async-dispatch], [explicit empty output contract][empty-output-test].

### Scheduling, loops, and joins

The shared run rule requires enough mandatory input and an activation trigger. A real predecessor value triggers every eligible visit. Caller input or a node with no incoming connections can trigger its first visit. This lets an input such as a question stay available across a retry loop without independently retriggering it. A greedy socket with a usable value and readiness across the mandatory and connected sockets receives `HIGHEST`. Other eligible components are `READY` when all connected predecessors have reported, including omissions, and `DEFER` while awaiting potential additional input. Unsatisfied mandatory input or an absent trigger makes a component `BLOCKED`. [Readiness and triggers][readiness], [predecessor completion][predecessors], [priority classifier][priority].

The synchronous loop starts from FIFO within priority, seeding the heap with sorted component names. It runs one component at a time and rebuilds the queue when it empties or its head is below `READY`. When only deferred work is available, it uses topological order to favor available upstream work. Cycles are condensed into strongly connected components for this tie-break, with name order used within a cycle. An initial queue with every node blocked raises `PipelineComponentsBlockedError`. Once work has run, a quiescent graph can return partial results and log a heuristic warning based on expected output components. [FIFO priority queue][fifo], [sync dispatch][sync-loop], [queue refresh and initial blockage][queue-refresh], [deferred ordering][defer-order], [quiescence heuristic][quiescent].

An archived validation loop makes this concrete. `passage` and `schema` seed the prompt builder. The builder can run while its optional feedback inputs have no data. The generator emits replies, the validator returns invalid replies and an error on the first attempt, and those two outputs reactivate the builder using its original prompt variables. A valid reply returns the unconnected result and leaves omission markers on the feedback edges. With no fresh value to trigger the builder, the loop stops. The saved second-visit checkpoint at `llm` shows visit counts of two for the prompt builder and one each for the generator and validator, exactly the state before the next generation. [Feedback graph][loop-test-graph], [later-visit integration contract][loop-test-resume], [archived second-visit snapshot][loop-artifact].

A `BranchJoiner` accepts alternative inputs and forwards the single element offered by the greedy socket. A `ListJoiner` consumes a lazy variadic collection of lists, then concatenates them. A `DocumentJoiner` applies domain rules such as keeping the highest score for an ID or a weighted merge. Lazy variadic values are sorted by the order of distinct sender connections, with caller values first. That order matters for weighted retrieval and survives a configuration round trip. [BranchJoiner][branch-joiner], [ListJoiner][list-joiner], [DocumentJoiner][doc-joiner], [connection-order sorting][fanin-sort], [weighted fan-in contract][weighted-join-test].

In the hybrid breakpoint fixture, sparse retrieval and an embedding branch feed a document joiner. The saved ledger has three documents from each retriever, with BM25 recorded before embedding. The connections were made in the reverse order, so the join receives the embedding branch first on consumption. Joined documents go to the ranker and answer builder. Ranked documents and a question drive a prompt, and replies and metadata flow to the answer builder. The fixture uses an in-memory store and local test doubles for generation, ranking, and embedding. [Hybrid wiring][hybrid-test], [archived join ledger][hybrid-artifact], [order at consumption][consume].

### Async scheduling, cancellation, and output streaming

`run_async_generator` rebuilds priorities after task progress, consumes inputs before creating a task, and tracks scheduled component names within the run. `READY` jobs run under an `asyncio.Semaphore` with a default limit of four active calls. `HIGHEST` drains existing jobs, then runs alone. `DEFER` becomes dispatchable when other jobs have settled. A coroutine implementation runs on the loop. A sync-only component runs through `asyncio.to_thread`, which carries context variables. Output delivery updates the run ledger on the loop after invocation. The generator yields qualifying per-component outputs and ends with the aggregate. `run_async` drains it and returns the final value. Completion order can vary even when an explicit lazy fan-in reorders its inputs. [Async entry point][async-generator], [async loop][async-loop], [isolated execution][async-isolation], [task scheduling][async-dispatch], [sync fallback][async-fallback], [generator completion][async-final].

The partial-output iterator is an output view, so a visit can deliver data downstream without yielding an update. An explicitly included empty mapping always enters the final aggregate. The isolated path also yields it as a partial result, while the ordinary task path emits partials only for truthy mappings. A consumer that counts partials therefore cannot use them as a visit ledger. The repository checks the final empty result and separately checks partials from an isolated component whose nonempty output is consumed downstream. [Task result emission][async-partial], [isolation result emission][async-isolated-partial], [empty aggregate contract][empty-output-test], [isolation partial control][isolated-partial-test].

On failure, the async scheduler cancels and awaits siblings before propagating the error. Its generator also cancels and drains pending work during finalization. Cancellation can unwind a cooperative coroutine. It abandons the await for an already-running sync worker, whose own execution may finish later. Shared graph topology and component resources rely on their own reentrancy contracts. [Sibling cancellation][task-cancel], [generator finalization][async-final], [reentrancy contract][reentrancy-test].

`stream` creates a task on the current event loop. It identifies async-capable components with a `streaming_callback` socket, optionally filters those names, and installs a run-local callback that queues `StreamingChunk` objects before invoking the selected user callback. The component filter selects which chunks to forward while the graph still runs according to its connections. Runtime callbacks take precedence over initialization callbacks. Async invocation awaits awaitable results and runs sync callbacks inline. The handle iterates chunks, awaits the producer at end-of-stream to surface the original error, and exposes the completed pipeline result through `result`. Default abandonment cleanup cancels the producer when the iterator finalizes, and explicit `aclose` requests cancellation. A caller can opt to let the pipeline finish after abandoning the stream. [Stream entry point and forwarder][stream-inject], [component filter contract][stream-filter-test], [callback selection and invocation][callback-select], [stream handle][stream-handle], [callback error control][callback-error-test].

### Failure boundaries

| Boundary | Runtime behavior |
| --- | --- |
| Assembly and preparation | The connector reports socket mismatches or ambiguity. Missing mandatory open inputs raise `ValueError`. An all-blocked initial frontier raises `PipelineComponentsBlockedError`. Warm-up itself occurs before input validation and before the run span. [Assembly errors][graph-match], [validation][validate-input], [entry-point check][queue-refresh], [warm-up ordering][sync-init]. |
| Admission and invocation | The default component visit cap is 100. The head guard raises `PipelineMaxComponentRuns` if a runnable candidate has consumed its budget. Invocation wraps arbitrary component exceptions with a typed `PipelineRuntimeError` and its original cause. Nested runtime errors and breakpoint exceptions propagate from the invocation helper. [Configured cap][graph-init], [guard][visit-limit], [error wrappers][errors], [async nested error contract][nested-error-test]. |
| Delivery and streaming | Edge conversion failures include the sending and receiving socket names and preserve the originating exception. The sync checkpoint handler covers invocation. Async task and stream boundaries provide sibling cleanup and surface failure to the caller. A chunk already enqueued before a callback fails is still visible to the consumer. [Conversion error][write-output], [sync exception handler][sync-break], [async cleanup][task-cancel], [stream callback failure][callback-error-test]. |

### Serialization and recovery

Pipeline definitions record constructor configuration for each component, named edges, graph metadata, the run limit, and the connection-validation flag. The default YAML marshaller handles the document format. Reconstruction resolves registered types, invokes public constructor or deserialization hooks, and replays edge declarations. Reordering edges by receiver socket in `to_dict` preserves the sender order used by lazy variadics. Component configuration uses a type plus `init_parameters` envelope. Tool variants carry type plus `data` and serialize their wrapped definitions. [Pipeline configuration][graph-serde], [reconstruction][graph-load], [YAML marshalling][yaml], [component serialization][component-serde], [connection-order round trip][round-trip-test], [tool configuration][pipeline-tool-serde].

A runtime snapshot is separate from configuration. The sync entry point can stop before a named component at its specified visit count, with zero denoting its first run. It captures the ledger with the selected component's pre-consumption entries restored, the visit counts, normalized original inputs, and selected outputs. Runtime values use a schema plus serialized-data envelope. It describes mixed lists, preserves non-string dictionary keys through JSON, and carries the omission marker. A custom callback can receive the snapshot and report an identifier. Otherwise file output is opt-in and requires a path. Callback and filesystem failures can surface at a planned breakpoint. During component error handling, saving is best-effort so the original runtime error can propagate. [Sync breakpoint dispatch][sync-break], [snapshot format][snapshot-state], [snapshot construction][snapshot-build], [snapshot delivery][snapshot-save], [runtime serialization][runtime-serde], [saved non-string-key control][keys-artifact].

Resume checks component membership, copies visit counts, restores the saved input queues and accumulated outputs, and recomputes readiness. The snapshot determines data and selected outputs for the resumed run. The current format retains senders. The legacy flattened format supports resuming a component's first visit, with special input consumption for that visit only. The public breakpoint, snapshot and resume controls live on `run`. The async helpers preserve nested errors and have no public checkpoint arguments. A pipeline snapshot captures graph execution state. Component internals, such as a generator's own counters and a store's current contents, retain their own lifecycle. [Resume dispatch][resume], [snapshot validation][snapshot-validate], [legacy format][legacy-format], [legacy resume contract][legacy-resume-test], [async signature][async-generator], [nested async errors][nested-error-test].

### Agent, tools, and nested graphs

The scheduler sees an `Agent` as a component. Its mandatory `messages` socket, optional generation and tool controls, declared state/metadata outputs, and dynamically registered prompt variables participate in the ordinary socket contract. The Agent creates per-run `State`, resolves its tools, and runs the conversation loop inside one graph visit. Its own step limit bounds chat-generator calls and associated tool execution independently of the graph's visit budget. It directly calls its chat generator, or uses the shared async execution helper, and keeps its own tracing spans. [Agent socket declaration][agent-io], [Agent signature][agent-signature], [run and step limit][agent-run], [fresh execution state][agent-fresh], [Agent sync step][agent-step], [Agent async step][agent-step-async].

In a local repository graph, a prompt builder provides prior conversation through `agent.messages` and an in-memory retriever sends documents to the Agent's dynamic `documents` socket. The Agent renders its own prompt after the graph dispatch, then appends the mock generator's reply to its message history. The pipeline returns that history and the last message through the Agent's declared outputs. There is also a direct test that the Agent's run span attaches beneath the outer pipeline component span. [Agent graph control][agent-graph-test], [Agent span parent control][agent-parent-test].

Hooks run in order at the six named lifecycle points and receive live `State`. `before_run` can restore the step counter. Before tools execute, the Agent rereads the last message after the `before_tool` hooks, so changes to the queued calls take effect. A step appends replies and tool-result messages through state handlers and updates run metadata. Terminal replies, successful exit-tool conditions, explicit hook signals, and the step cap shape when it returns. `on_exit` can request another step within the cap. `after_run` can adjust the returned state after a normal loop exit. [State handlers][state], [hook protocol and order][hook-order], [hook control flow][agent-exit], [hook contracts][hooks-test].

Tool execution resolves calls by name and derives read/write sets from `inputs_from_state`, `outputs_to_state`, and parameters annotated as live `State`. Explicit call arguments win over mapped state arguments. A live state parameter is treated as touching every state key. The planner groups read-after-write dependencies into sequential batches and breaks dependency cycles by call index. The sync executor uses a thread pool and the async executor uses a semaphore over native async calls or thread fallbacks. Batches prepare arguments after earlier merges, then commit mapped results in call order within each batch. Resolved result messages are assembled by call index. Streamed tool results follow batch order and are emitted during finalization. Missing tools and invocation failures can be returned as error messages or raised, depending on configuration. State merge errors propagate. Dynamic toolsets can provide isolated run-scoped selections through `spawn`. [Tool argument assembly][tool-args], [tool batch scheduling][tool-schedule], [sync tool executor][tool-sync], [async tool executor][tool-async], [tool failure handling][tool-finalize], [toolset spawn][tool-spawn], [tool dependency contracts][tool-schedule-test].

The Agent passes its selected streaming callback to both the chat generator and the tool executor. The executor emits tool-result chunks during finalization and an empty chunk with `finish_reason="tool_call_results"` after results. With callback passthrough enabled, an eligible tool also receives the callback as an argument if its arguments did not already supply one. A surrounding `Pipeline.stream` forwards chunks emitted through the Agent's selected callback to the same queue as other tapped components. [Agent callback wiring][agent-callback], [tool callback injection][tool-callback-injection], [tool result emission][tool-result-stream], [result chunk contract][tool-result-stream-test], [pipeline forwarding][stream-inject].

`SuperComponent` exposes a pipeline as one component. It maps wrapper inputs to one or more inner socket paths, intersects compatible input types, delegates defaults to the child, and rejects duplicate output names. Its output mapping can retain intermediate outputs by requesting the relevant component results. `run` and `run_async` call the corresponding child engine with their own run state, then map available outputs back. `PipelineTool` is a `ComponentTool` wrapping a `SuperComponent`. `ComponentTool` derives a model-facing schema from sockets and descriptions, excludes state-injected and callable parameters from automatic schemas, and converts arguments to Haystack objects or through Pydantic before calling the component. `AgentTool` specializes that wrapper for another `Agent`, with a default single-message input schema and a final-reply formatter. As a result, a tool used inside an Agent can drive the same graph runtime recursively through a narrow mapped interface. [SuperComponent mapping][super-init], [SuperComponent invocation][super-run], [mapping type resolution][super-types], [PipelineTool wrapper][pipeline-tool], [ComponentTool invocation][component-tool], [schema and conversion][component-tool-schema], [AgentTool defaults][agent-tool], [wrapper async round trip][super-round-trip-test].

A failed child pipeline can surface as the cause of a `ToolInvocationError` at the adapter. The Agent can put that error into conversation history or propagate it, depending on its configured tool error policy. In the other direction, a pipeline snapshot taken around an Agent holds the outer dispatch state. The Agent's own state has a separate serializer and a `before_run` hook boundary where a caller can restore conversation state. [Tool invocation and wrapping][tool-invoke], [agent tool result handling][tool-finalize], [Agent state serialization][state-serde], [restored step count control][hooks-test].

## 3. Why the design works and governing invariants

| Invariant | What it buys and where it applies |
| --- | --- |
| Consume a trigger once and distinguish an omitted key from a delivered value. | A loop can keep caller context while requiring fresh feedback after the first visit. Conditional branches can complete without fabricating values for inactive routes. [Activation][readiness], [input consumption][consume], [edge delivery][write-output]. |
| Defer a runnable consumer until better-informed work has had a chance to produce inputs. | Ordinary fan-in receives its available branches. An unreachable branch cannot hold a lazy merge forever once it has a real input and the rest of the graph makes no further progress. The scheduler's topological tie-break limits premature defaults when multiple deferred nodes can run. [Priority classifier][priority], [deferred ordering][defer-order], [optional branch control][optional-join-test]. |
| Keep predecessor identity through delivery, consumption and checkpointing. | The engine can tell which upstream nodes reported even if they omitted a key. For distinct sources it can restore the requested fan-in order independently of arrival order and reconstruct the same pending ledger after a breakpoint. [Predecessor accounting][predecessors], [fan-in ordering][fanin-sort], [omission marker resume control][marker-resume-test]. |
| Give one run its own visits, output map, and pending inputs. | Stateless components can serve overlapping requests without sharing scheduler bookkeeping. The async scheduler also admits at most one in-flight task per component name within a run. Graph and component resource ownership are separate concerns. [Run-local visits][visits], [async run state][async-loop], [scheduled names][async-dispatch], [overlapping-run contract][reentrancy-test]. |
| Apply mapped tool writes after invocation, in the batch's call order. | Readers of earlier batches' writes prepare their arguments from the updated state. Tools that only write the same key can invoke concurrently, then commit deterministically through its handler. Cycles use the documented call-order fallback. Message order is a presentation contract and can differ from state write order across batches. [Tool dependency rules][tool-batching-order], [ordered async result commit][tool-async], [dependency controls][tool-schedule-test]. |
| Check resource budgets when dispatching and distinguish execution from delivery. | The design provides per-component visit caps, per-run concurrency bounds, and the Agent step cap. The implementation has gaps where replacements from the queue or malformed outputs cross those boundaries. [Run-limit guard][visit-limit], [async secondary dispatch][async-ready-batch], [Agent step loop][agent-run], [output validation order][sync-invoke]. |
| Build a checkpoint at a scheduler boundary and replay against compatible wiring. | A planned stop can resume without replaying upstream nodes. On supported checkpoints the pending inputs and successful visit counts remain coherent. The saved graph identity and failure outcomes currently have narrower guarantees than this principle. [Checkpoint boundary][sync-break], [resume verification][snapshot-validate], [retry and visit preservation tests][retry-test]. |

## 4. Strengths

- Components, composition, and tools share a practical interface. The same dynamic socket metadata supports ordinary invocation, graph inspection, one-to-many wrapper maps, and generated tool schemas. Invalid mappings and undeclared endpoints can fail during assembly, before a graph or a wrapped tool runs. [Dynamic sockets][dynamic-sockets], [connection diagnostics][graph-match], [wrapper mapping tests][super-mapping-test], [tool schema contract][pipeline-tool-schema-test].
- Presence and source tracking solve real graph problems with small abstractions. The sentinel is serialized explicitly and uses type checks instead of boolean comparisons on arbitrary values, including arrays and DataFrames. A conditional branch can coexist with a loop, and a weighted retrieval join can depend on stable sender order across differing sync and async completion patterns. [Marker implementation][no-output], [loop join ordering test][loop-order-test], [weighted retrieval test][weighted-join-test].
- Runtime observability follows the same execution boundaries as the code. Component spans carry stable names, socket specs and visits. Agent, step, hook, and tool spans provide the next layer of context. A tool's span can remain associated with the correct step under independent workers, and a sync fallback retains context variables. [Component spans][component-span], [Agent span][agent-span], [tool spans][tool-span], [context propagation contract][context-test].
- The project tests interactions using real public calls and meaningful controls. The integration artifacts cover a later feedback visit, disk serialization and handoffs between real local components. The repository also checks callback failures after chunk enqueue, a failed resumed run followed by successful retry, and the effect of changing wire order on actual document scores. [Later loop visit][loop-test-resume], [callback error control][callback-error-test], [snapshot retry control][retry-test], [weighted join control][weighted-join-test].

## 5. Weaknesses and evidence status

### Defects reproduced in the archive and corroborated by source

| Finding | Scope and consequence |
| --- | --- |
| **D1. Closing a stream before its producer starts can leave its first iterator waiting.** | The archive records a cancelled result and a pending first iteration. The public `aclose()` can cancel the task before execution enters the runner's `try` block. Its `finally` is the only producer of the end-of-stream sentinel, and the iterator only waits on the queue. Normal iteration and close followed by `result` have repository controls. The close control ends before trying to iterate the closed handle. [Archive][probe-close], [handle wait and close][stream-handle], [producer completion][stream-runner], [close and cancellation controls][close-test]. |
| **D2. Automatic stream callbacks can activate an otherwise inactive branch.** | The archived stream returned an optional component's default-derived value and recorded a call with `None`. The forwarder is added to normalized data before scheduling. That makes it a `sender=None` entry and supplies the first-visit trigger even if all the actual graph data sockets are optional and the upstream route delivered no value. The component has enough mandatory inputs and eventually runs with defaults. A normal async run without a supplied callback has no such trigger in that case. The repository's Agent regression uses a mandatory `messages` socket, which protects that component with the mandatory-input gate. That control does not cover arbitrary optional-only graph components. [Archive][probe-routing], [stream result contract][stream-contract], [injection][stream-inject], [trigger checks][readiness], [Agent guard control][agent-stream-test]. |
| **D3. A malformed result can produce a checkpoint that cannot retry a first visit.** | The archive records `root: 1` in the saved visits and a rejected resume. Sync invocation increments the visit count after the method returns and before checking `Mapping`. The error snapshot restores pre-execution inputs with the already-advanced count. A root that depended on its first-visit trigger then has no new trigger on resume. If the graph has no other runnable node, initial queue validation rejects it as blocked. An ordinary exception raised by the method leaves the count unadvanced. A repository crash test confirms a malformed result gets a snapshot. The retry test starts from an earlier planned breakpoint and injects a raised exception, so neither control tests the combined failure. [Archive][probe-bad-map], [visit increment][sync-invoke], [snapshot error path][sync-break], [first-visit trigger][readiness], [initial queue validation][queue-refresh], [malformed-result contract][malformed-output-test], [retry contract][retry-test]. |
| **D4. Valid dict-valued input can be rewritten in snapshot metadata.** | The archive shows a collapsed `original_input_data` field and a successful resume with the full input. The sync entry point already passes normalized caller data. The snapshot helper then recursively unwraps any dictionary with `sender` and `value`, as if it were an internal ledger entry. The saved pending-input ledger follows a separate schema-aware path and preserves the payload in this case. The impact shown is incorrect input metadata, including input tags derived from it during resumed tracing. [Archive][probe-original], [separate snapshot input paths][snapshot-transform], [recursive unwrap][snapshot-unwrap], [resume input paths][resume], [dict-valued input contract][dict-input-test], [snapshot metadata control][snapshot-metadata-test]. |

### Source-supported risks

- **S1. Visit limit enforcement depends on how a node is selected.** `_get_next_runnable_component` checks the heap head. Sync and async can then substitute a different `DEFER` node after the topological tie-break. Async also pops further `READY` nodes and schedules them directly. Neither path checks the selected instance's limit again. A feedback graph can deliver new inputs to a first-visit observer and to a receiver already at its limit in the same write. If both are `READY` and the new observer sorts first, async guards the observer and admits the exhausted receiver through the additional-ready path. This is possible with a one-slot semaphore because task creation precedes permit acquisition. Repository controls exercise a checked ready head, a blocked head, and a simple single-frontier loop. The archive's three budget lines lack the configured cap and wire list, so the source path establishes the finding. [Visit limit][visit-limit], [sync deferred dispatch][sync-defer], [async additional-ready dispatch][async-ready-batch], [semaphore acquisition][async-dispatch], [visit-guard control][limit-test], [single-frontier loop contract][infinite-loop-test], [archive signal][probe-budget].
- **S2. The stream cleanup timeout is cooperative.** The handle says the cleanup window is bounded and calls `wait_for` on the cancelled producer. The scheduler's finally block awaits its cancelled children. In the local Python implementation, a positive `wait_for` timeout still awaits the underlying task while the timeout context requests cancellation. Slow or cancellation-resistant cleanup can retain that dependency. The archive notes a 30 ms configured threshold and a 120 ms observation. The checked-in default is one second, and the fixture and cancellation behavior are unavailable in the archive, so this does not measure the default. The normal sibling cancellation and stream close tests use cooperative tasks. [Cleanup implementation][stream-close], [task draining][task-cancel], [local wait_for implementation][asyncio-waitfor], [cooperative cancellation test][cancel-test], [archive signal][probe-timeout].
- **S3. A greedy join consumes the value left in its socket when dispatched.** Already-ready work can remain ahead of a newly eligible greedy node in the sync queue. In async, the isolation routine waits for work already admitted, which can include more producers. In both cases a later real write replaces the first one. `BranchJoiner` recommends one active branch and also describes one run per value if multiple branches produce output. The normal single-active-branch loop fits the implementation. With overlapping deliveries, values can coalesce before dispatch and the join can run fewer times than described. The archived sequence is consistent with this mechanism in all three modes. The underlying topology and timing controls are unavailable. [Greedy type contract][socket-types], [BranchJoiner contract][branch-contract], [greedy join implementation][branch-joiner], [sync queue refresh][queue-refresh], [async isolation][async-isolation], [single-slot write rule][socket-writes], [greedy controls][greedy-test], [archive signal][probe-greedy].
- **S4. Run-time validation can change the next run's interface.** Adding caller data to a connected list socket promotes shared socket metadata in place, even with a single edge. The ordinary `inputs()` description subsequently exposes the socket as variadic, which changes flat input routing. A serialized definition with only that one edge reconstructs the original socket shape. The repository validates the in-place promotion itself and the input merge, so the concern is the runtime change to the persistent schema and its visibility to concurrent or later callers. [Validation mutation][validate-input], [promotion][auto-variadic], [socket discovery][input-description], [definition format][graph-serde], [promotion contract][promotion-test], [input merge contract][auto-join-test].
- **S5. The blocked diagnostic can replace an ordinary empty outcome with `IndexError`.** Consider one valid leaf that declares a conditional output and returns an empty mapping on this input. After that invocation, the scheduler removes the sole blocked candidate from the recomputed queue. The heuristic sees a declared output with no result and calls the diagnostic with the now-empty queue. The diagnostic indexes the first entry unconditionally. A repository test covers missing outputs in a two-node graph, and the explicitly requested empty-output test covers a different case with no declared output on that component. [Sync blocked exit][sync-loop], [async blocked exit][async-loop], [diagnostic indexing][blocking-diagnostic], [expected-output heuristic][quiescent], [blocked warning control][blocked-test], [empty output control][empty-output-test].
- **S6. Checkpoint compatibility is coarser than execution compatibility.** Validation checks component membership and the snapshot dataclass checks visit-key consistency. Wiring, socket definitions and component configuration can change without a graph identity check. Field fallback operates at the top-level component key of a snapshot payload, so omission of an unsupported value is compatible with parsing an otherwise incomplete snapshot. Delivery conversion and run-budget errors occur outside the synchronous snapshot catch. Even with an identical graph, resume rebuilds the queue from saved inputs. A newly eligible greedy node can run before the originally selected next node, which can change which values are overwritten and the number of visits. The controls establish graph-name rejection, readable fallback payloads, and resume for the exercised frontiers. [Snapshot validation][snapshot-validate], [visit-key checks][snapshot-state], [serialization fallback][field-fallback], [invocation and delivery scopes][sync-break], [queue reconstruction][resume], [sync queue refresh][queue-refresh], [fallback test][fallback-test], [resume membership and retry controls][retry-test].
- **S7. Positional fan-in has a narrower contract than edge order suggests.** Sender sorting uses the first occurrence of each sender name, so interleaved parallel edges from the same sender are grouped by sender. Delivery omissions are filtered out before join invocation. A fixed `DocumentJoiner` weight vector still has one entry per expected list and strict zip will reject a fully absent input list. The optional-filter control skips a filter branch but delivers both retriever lists. These are source-supported boundaries of positional weighting and sender-level ordering. [Sender index][fanin-sort], [marker removal][consume], [weighted merging][doc-merge], [optional-filter controls][optional-join-test].
- **S8. Explicit wrapper input maps can leave required child inputs unreachable.** `SuperComponent` validates each named destination individually. It constructs sockets only for mapped names and forwards only those names to the child, which checks its required open sockets when it runs. A local `PipelineTool` unit fixture builds a retriever and ranker with mandatory `query` inputs, maps only the retriever's query and asserts that both callable forms exist. The downstream query remains mandatory, so a successful constructor or serializer test is insufficient validation of the runnable interface in that fixture. The repo's successful wrapper execution maps the query to all of its required destinations. [Input mapping validator][super-validation], [wrapper forwarding][super-forward], [unmapped child validation][validate-input], [fixture with two query sockets][tool-ranker-fixture], [tool callable control][tool-async-shape-test], [complete mapping control][super-run-test].

### Design tradeoffs and open questions

- The async limit caps concurrently executing component calls within one run. Its current admission loop can queue more tasks than the available permits, and child pipelines and Agent tool batches each have their own limits. Those choices support composition and parallel work, while an application-wide work budget and fair admission remain separate concerns. A queue rebuild scans the graph after progress. The cost on large mostly inactive graphs is unresolved by this evidence. [Task admission][async-ready-batch], [queue build][queue-build], [child run][super-run], [tool semaphore][tool-async].
- Sync warm-up and close fallbacks execute on the event loop in async lifecycle methods. This keeps loop-affine setup on the serving loop and asks authors to keep sync lifecycle operations short. An already-running thread offload can outlive cancellation. The stream queue is unbounded, so producer/consumer rate mismatch and abandonment without cancellation can retain chunks. The archive does not characterize memory growth, fairness, or cancellation latency at scale. [Lifecycle code][lifecycle], [loop-affinity control][lifecycle-test], [thread cancellation][task-cancel], [stream queue][stream-inject].
- The review establishes resume of scheduler state under compatible local graphs and known value types. General cross-process recovery of component-owned state, failures after a component's external side effects, and durable async graph checkpoints remain outside the demonstrated guarantee. [Snapshot state][snapshot-state], [focused fixture][loop-test-resume], [fresh-graph resume control][repeat-visit-test].

## 6. Core-code quality

| Area | Assessment |
| --- | --- |
| Decomposition and maintainability | The distinction between the graph, readiness predicates, dispatch, adapters and domain components is visible. `PipelineBase` still owns graph mutation, validation, serialization, queues, delivery and diagnostics. `Pipeline` duplicates portions of invocation and result handling across sync, async-task and isolated execution branches. Both pass nested dictionaries and parallel collections around, which makes admission and failure invariants easy to implement in one path and miss in another. A separate typed per-run state and a shared selection-to-commit boundary would improve local reasoning. [Shared readiness][readiness], [base dispatch metadata][visits], [sync loop][sync-loop], [async dispatch][async-dispatch], [async isolation][async-isolation]. |
| State and ownership | Runtime data and visits are scoped to a call, with best-effort input copies at normalization and invocation. `Document` optimizes copying the embedding list. Resource-bearing components, tools and toolsets can preserve identity by design. Shared socket promotion and reused component instances delimit reentrancy. The in-memory store uses per-index locks and an owned default executor, an example of a component dependency explicitly managing its own shared resource. [Copy policy][copy-policy], [document copy][document-copy], [socket mutation][auto-variadic], [store locking and ownership][store-ownership]. |
| Concurrency and cancellation | A name registry prevents two active invocations of the same node within an async run. The event loop applies the output ledger updates without awaiting between edge writes. Agent tool batches similarly separate invocation from ordered state merge. Cancellation behavior is good for cooperative tasks, with the deadline and pre-start completion gaps described above. The scheduler and tool executor make different failure choices: the former drains cancelled siblings and the latter can wait for the current tool batch before reporting its first failure in order. [Async dispatch][async-dispatch], [task cancellation][task-cancel], [tool commit][tool-async]. |
| Errors | Construction failures identify endpoints and declared types, component errors preserve their cause, and conversion failures identify both sockets. A branch that omits outputs is legal, so late blockage is a diagnostic heuristic. `PipelineRuntimeError` is separate from the `PipelineError` inheritance chain used for connection and budget errors. Unknown returned keys are warned about and can still appear in public results if unconnected or explicitly included. This matches routing by declared sockets, though the warning's wording suggests they are ignored more generally. [Graph diagnostics][graph-match], [error types][errors], [conversion diagnostics][write-output], [unused output pruning][prune], [extra-key warning][output-warnings]. |
| Types and contracts | The socket model gives strong structural feedback and lets dynamic components participate in graph authoring. The connector intentionally approximates Python assignability. Component invocation depends on declared conventions and Mapping-shaped returns, and `State.set` applies a key-specific merge handler without checking the assigned value against the metadata type. At the tool edge, generated schema shape and runtime adaptation are separate. Using a richer typed model for framework-owned entries would leave arbitrary user payloads flexible. [Type helper][strict-types], [state assignment][state], [tool schema][component-tool-schema], [component invocation][sync-invoke]. |
| Serialization ownership | Top-level pipeline loading copies the definition before constructing components, and the default component decoder copies its constructor dictionary. Specialized decoders vary. Direct `SuperComponent.from_dict` replaces the serialized child entry with a live pipeline in the supplied dictionary. Reusing that dictionary then hands a pipeline object to a loader that expects a mapping. The public round-trip test deserializes its payload once. [Pipeline load][graph-load], [default component decoder][serde-copy], [wrapper decoder][super-decode], [wrapper round trip][super-serde-control]. |
| Tests | Focused predicate tests, public execution tests, relational assertions for order-independence, and serialized round trips cover important seams. The Gherkin suite applies the same scenario definitions to both engines and asserts per-component inputs by visit. Its unavailable collector is material when reading the fallback counts. Current nearby tests generally cover one decision axis at a time for dispatch and cleanup. [Sync/async scenarios][feature-contract], [scenario test adapter][feature-runner], [connection-order control][loop-order-test], [cleanup control][close-test]. |
| Observability | Pipeline spans tag execution mode, graph metadata, normalized run inputs and limit. Child spans carry an explicit parent and add actual argument types and socket declarations. When content tagging is enabled, component argument and output tags are populated around invocation and final pipeline outputs are tagged after scheduling completes. A tracer test uses eager tag serialization to detect recording the result too early. Agent and tool spans identify nested work, and structured warnings identify possible blockers using a heuristic. A stable proxy delegates to a pluggable tracer and starts with a no-op backend. [Run spans][sync-loop], [component spans][component-span], [final async tags][async-final], [content tag method][trace-content], [eager tracer contract][trace-test], [tracer interface][tracer], [quiescence heuristic][quiescent]. |
| Extensibility and contract drift | Component and tool adapters keep registration lightweight for plain Python code. Class recreation can complicate idiomatic inheritance. A repository subclass explicitly calls a base method because zero-argument `super()` does not survive the decoration there. Some checked-in explanations lag the implementation. The component module's opening contract describes dataclass input/output decorators, `connect` describes an older fan-in ordering, and the async run docstring describes leaf-component results even though the pruner works at socket granularity. The sync run docstring describes default disk saving although the snapshot helper defaults to file saving disabled. [Component decorator][component-registry], [subclass control][weighted-join-test], [old component contract][component-doc], [connect docstring][graph-connect], [async result docstring][async-result-docs], [pruning rule][prune], [sync API docs][run-docs], [snapshot save behavior][snapshot-save]. |

## 7. Executed tests and limits

All execution results below are from the completed archive. The fresh review used source, test assertions, and read-only inspection of those outputs.

| Archived operation | Recorded outcome | What it establishes |
| --- | --- | --- |
| Full collection attempt | 7,401 of 7,631 tests collected, 230 deselected, 7 collection errors in 6.68 s. | Partial discovery. The denominator covers the cases pytest discovered before deselection. The log lists 462 node IDs under `test/core/pipeline/` and zero from the unavailable Gherkin group. The cases in the seven unavailable collections have unknown counts. [Collection result][collection-summary]. |
| Broad fallback | **4,293 passed, 4 failed, 2 skipped, 55 deselected, 9 warnings in 12.08 s.** | Wide execution of local component and runtime code on one fallback environment. The failure attribution and warning audit are below. [Broad result][broad-summary], [installed package inventory][inventory]. |
| Focused repository integration selection | **33 passed, 16 warnings in 0.42 s.** | Disk breakpoint/resume coverage for answer, branch, list and string joins, two visits of a validation loop, and a local hybrid retrieval graph. The saved artifact counts are 5, 4, 5, 5, 6 and 8 respectively. The integration fixtures use local test doubles where generation is needed. The second-visit fixture keeps the same mock and its call history while resuming. [Integration result][integration-summary], [answer][answer-breakpoints], [branch][branch-breakpoints], [list][list-breakpoints], [string][string-breakpoints], [integration resume fixture][integration-fixture], [second-visit artifact][loop-artifact]. |
| Archived probe selection | **12 passed in 1.09 s.** | Completion status of the archived assertions. These tests could pass by successfully observing an undesirable outcome. The log reports selected observations without the probe source or full test IDs. Findings promoted from it are limited to the mechanisms and controls audited below. [Probe log][probes]. |

The coverage archive is from coverage.py 7.17.3 and contains one empty-named context, statement bitmaps, and zero branch arcs. The broad run reports 54% overall statement coverage, with 91% for `PipelineBase`, 97% for `Pipeline`, 100% for readiness predicates, and 90% for snapshot helpers. The Agent and tool-calling files are each reported at 99%. Spot checks in the SQLite file show hits even at the extra-ready dispatch, snapshot input unwrap, and stream shutdown statements. They cannot identify which test exercised the line or demonstrate the combination of states needed for a finding. [Coverage report][broad-coverage], [Agent coverage][broad-agent-coverage], [coverage data][coverage-db].

The fallback inventory records Python 3.14.8, pytest 9.0.3, NetworkX 3.7, and Pydantic 2.14.3. Python 3.14 is listed in project metadata. The checked-in CI unit job selects Python 3.11 with the full Hatch test environment. The archived transaction lists installed packages. The wheel inventory lists `lazy-imports` as missing and the package transaction omits it, even though the checkout imports it and the fallback executed Haystack. The source of that import at archive time is unverified. The recorded timing and coverage describe the fallback selection and its environment. [Fallback inventory][inventory], [wheel availability][wheel-gaps], [core dependency declaration][project-deps], [CI runtime][ci-python], [CI unit command][ci-unit].

## 8. Measurement audit

### Broad fallback failures

| Test and original failure | Adjudication |
| --- | --- |
| `TestPipelineBase.test_show_in_notebook`, missing `IPython` | **Setup failure.** The traceback fails inside `unittest.mock` as it imports the `IPython.display` patch target. The test body that calls `show()` is later, and the renderer itself is mocked there. The production display branch separately imports IPython when in a notebook. `ipython` is present in the Hatch test dependency list and absent from the fallback inventory. The archive supplies no measurement of notebook display behavior from this node. [Traceback][notebook-fail], [test patch][notebook-test], [display import][notebook-source], [Hatch dependencies][hatch-pytest]. |
| `test_image_content_show_in_jupyter`, missing `IPython` | **Setup failure.** The fixture opened the image and constructed `ImageContent`. The traceback stops while resolving the `IPython.display.display` patch, before `image_content.show()`. The same Hatch declaration explains the missing patch target. [Traceback][image-fail], [test and patch][image-test], [display branch][image-source], [Hatch dependencies][hatch-pytest]. |
| `test_device_map`, unbound `torch` | **Setup-triggered diagnostic defect, outside graph scheduling.** Integer and string device-map assertions precede and pass before the test reaches the malformed float. Importing optional PyTorch leaves its name unbound in this environment. The int and string checks bypass the name. The float reaches `isinstance(device, torch.device)` before the promised `TypeError` branch. That explains the observed `NameError` independently of any GPU. Hatch pulls PyTorch through `transformers[torch, sentencepiece]`. A correctly installed PyTorch supplies the missing class reference. The limited-dependency diagnostic remains a genuine code-quality issue. [Traceback][device-map-fail], [control and expectation][device-map-test], [optional import][torch-import], [deferred import behavior][lazy-import], [method under test][device-map-source], [Hatch PyTorch dependency][hatch-deps]. |
| `test_component_device_resolution`, missing `torch` | **Setup failure.** The mock decorators import `torch.xpu`, `torch.backends.mps` and `torch.cuda` targets before the body can assert device selection. The body controls hardware availability with mocks. The production default-device path separately catches a missing import and selects CPU. Missing PyTorch prevented the archived test from exercising its mock-driven selection. [Traceback][device-resolution-fail], [patch and assertions][device-resolution-test], [default device selection][device-default], [Hatch PyTorch dependency][hatch-deps]. |

The nine fallback warnings are accounted for by one missing `flaky` mark from the absent `pytest-rerunfailures` plugin, two pandas fixture deprecations, three intentional or fixture-derived dataclass assignment warnings, two Pydantic schema warnings about the wrapper's delegated-default sentinel, and an experimental hook warning. The sentinel's omission from the JSON schema leaves the field optional and the wrapper handles its runtime default. The focused run's 16 warnings are two dataclass assignments across eight hybrid cases. The configured pytest options include strict markers. Unknown markers only warned in the archived runs, so their effective marker handling differed, with the exact settings unavailable. [Broad warnings][broad-warnings], [Hatch plugin list][hatch-pytest], [pytest config][pytest-options], [delegated defaults][super-run], [schema control][pipeline-tool-schema-test], [focused warnings][integration-warnings].

### Seven collection errors

| Modules or test group | Diagnosis |
| --- | --- |
| DOCX, MSG, PPTX and XLSX converters | Four direct test imports fail, respectively `docx`, `oxmsg`, `pptx`, and `openpyxl`. Their corresponding dependencies are declared in Hatch and absent from the fallback install. These are four separate collection errors. [Collection tracebacks][converter-collection], [converter dependencies][hatch-converters]. |
| SAS evaluator | Test import of `sentence_transformers.CrossEncoder` fails. The separate `sentence-transformers` dependency is declared for the test environment and absent from the fallback. [Traceback][sas-collection], [test dependencies][hatch-deps]. |
| Sentence tokenizer | The missing symbol is `CustomPunktLanguageVars`, whose definition is conditional on a successful NLTK import. The test imports that class at module import time. The fallback package and wheel inventories lack NLTK, which Hatch declares. The symptom is an indirect missing-dependency failure. [Traceback][nltk-collection], [definition guard][nltk-guard], [test import][nltk-test], [dependency declaration][hatch-nltk]. |
| Pipeline behavior scenarios | The feature group's conftest imports `pytest_bdd` before selecting either runtime mode. The package is absent. The Gherkin scenarios still document public behavior, including unreachable cycles, the visit cap, mixed optional branches, and per-visit inputs. Their absence from execution is a core coverage limitation. [Traceback][bdd-collection], [fixture and import][feature-runner], [scenario matrix][feature-contract], [Hatch plugin list][hatch-pytest]. |

### Archived probe cross-check

The source controls listed here establish the comparison behavior. The fallback log is aggregated, so test-specific results below are attributed to repository assertions unless an artifact identifies the case.

| Signal | Supported usage, control, and disposition |
| --- | --- |
| Visit budget across concurrency values 1, 2 and 4 | Cyclic graphs seeded by caller input and a per-component cap are supported. The simple infinite-loop scenario and direct ready/blocked budget tests define positive guards. The archive shows two calls in each run but omits the configured cap and full graph. The separate manual trace in S1 checks the unguarded secondary selection, including a one-slot schedule. It establishes a source-supported dispatch risk. [Archived rows][probe-budget], [simple-loop control][infinite-loop-test], [head guard control][limit-test], [secondary selection][async-ready-batch]. |
| Two source events before a greedy value of 2 in sync and both async modes | The public graph permits several sources on a greedy socket. A branch join with only one active route and a helper that consumes one value are positive controls. The archive does not identify which edges delivered or constrain precise timing. The sync cached queue, async drain, and replaceable socket entry explain the limitation of an immediate-first-arrival interpretation. [Archived rows][probe-greedy], [single active route contract][single-route-test], [isolated greedy consumption][greedy-test], [single-slot writes][socket-writes]. |
| Optional branch executes in a streamed run | Automatic forwarding is a public mode, and optional connected inputs are supported. Normal streamed completion with required input and the Agent routing control show where mandatory gating holds. The callback is injected before `sender=None` assignment, supplying the missing activation without any data arriving on the graph input. The blocked warning uses the remainder after removing the first blocked candidate and can name previously executed nodes. The default-derived output and call are the relevant archived observations for D2. [Archive][probe-routing], [stream happy path][stream-happy-test], [Agent routing control][agent-stream-test], [input preparation][input-ledger], [trigger logic][readiness], [warning selection][blocking-diagnostic]. |
| Explicit close, cancelled result, pending iteration | The public close operation and normal consumer are supported. The existing close test checks only the result state after immediate close, and the positive stream test finishes by consuming the sentinel. Producer cancellation before its coroutine enters the try/finally leaves the queue empty. The archived pending first iteration supports D1. [Archive][probe-close], [close contract][close-test], [happy path][stream-happy-test], [sentinel placement][stream-runner]. |
| Cleanup still pending after 120 ms with reported 30 ms threshold | The archive result is bounded to its reported threshold. The default is one second. The archive lacks the instrumented coroutine and details of any timeout override. Cooperative repository cancellation is the positive control. Awaiting cancellation settlement under `wait_for` establishes the lack of a hard deadline in S2 independently of elapsed fixture timing. [Archive][probe-timeout], [cooperative cancellation][cancel-test], [default and close][stream-close], [local wait_for][asyncio-waitfor]. |
| Invalid output creates root visit 1 and resume is rejected | A component returning a non-mapping violates the output contract. Snapshot attachment on this error is an explicit repository behavior under review. A successful normal breakpoint, a raised-method error, and a saved-data retry serve as controls. Advancing the visit before validation and restoring earlier input entries explains D3. The archive does not identify the rejection's exception class. [Archive][probe-bad-map], [crash control][malformed-output-test], [retry control][retry-test], [counter increment][sync-invoke]. |
| Snapshot's recorded original data loses dict fields while resumed work gets them | Arbitrary dict payloads are supported. The simple metadata and non-string-key JSON round trips verify intact data in their cases. The internal-ledger serializer is separate from the recursive original-data transform. The archived payload collapse therefore supports D4 with the demonstrated effect confined to original-input metadata. [Archive][probe-original], [dict control][dict-input-test], [file control][keys-test], [metadata transform][snapshot-transform]. |

An additional passing dot has no associated identifiable output in the archive. Neither its control, code path, nor assertion is attributable from the log. [Probe count][probes].

### Static cross-checks of scheduler edge cases

These traces use the documented graph interface and the checked-in scheduling rules. They show why the findings persist after accounting for a few plausible alternate explanations.

| Case | Predicate and transition trace |
| --- | --- |
| S1 with one async slot | A feedback node starts with a provided seed and an optional connected retry input. It can run as `DEFER` and produces a value for a middle node. The middle node commits outputs to a fresh observer and back to the feedback node. Both receivers are now `READY`, because their respective predecessor entries are present. With a limit of one visit and the observer first by name, the head guard sees the observer's zero visits. With ordinary deferred task starts, the scheduler examines the next heap item before the observer task takes a permit. The feedback node enters the same batch through the unguarded pop. The semaphore orders when calls execute and the second visit is still admitted. [Trigger and readiness][readiness], [priority computation][priority], [head guard][visit-limit], [batch admission][async-ready-batch], [permit acquisition][async-dispatch]. |
| S1 after a deferred tie-break | Add an optional input to both receivers from a node blocked by an omitted mandatory input. Both receivers now remain `DEFER`. Put the feedback receiver upstream of the observer, with the feedback loop condensed into one strongly connected component. The same first-by-name observer passes the guard. Topological order then substitutes the exhausted feedback receiver. Sync and async both consume the selected receiver through paths that do not repeat the guard. The topological tie-break tests check the ordering separately from the budget. [Ordering][defer-order], [sync substitution][sync-defer], [async substitution][async-defer], [tie-break tests][defer-test]. |
| S3 and S6 with the same graph on resume | Consider two ready sources and a greedy receiver with no other connected input. The first source makes the receiver eligible, but the sync queue keeps its already-ready second source next. On an uninterrupted run that second source overwrites the held value before the receiver consumes it. A planned breakpoint just before the second source saves the first value but does not save the remaining priority queue. Resume recomputes the greedy receiver as `HIGHEST`, so it consumes the first value before the second source runs. Both values can then trigger separate visits. The saved input format preserves the value correctly. Recomputing the frontier is what changes the work. [Queue refresh][queue-refresh], [greedy priority][priority], [pre-dispatch checkpoint][sync-break], [snapshot restore][resume], [replace-on-write][socket-writes]. |

## 9. Post-mortem and prioritized improvements

The code balances flexible Python components and dynamic sockets with two execution engines and replay of debugging state. The simplest supported graph shapes compose because the readiness rules are shared. Failures collect around handoffs between those rules and multiple dispatch paths, between operational callbacks and data inputs, and between state describing an attempt and state describing a successful visit. The highest leverage is to make those handoffs explicit before changing the overall component model.

1. **Enforce admission invariants at the actual dispatch boundary.** Apply the visit limit to the final selected node, across the topological tie-break, extra ready jobs, and the isolation path, before consuming its inputs. Reserve capacity when admitting a job. Define greedy multi-producer semantics explicitly. A once-per-value contract needs to retain each arrival or reserve its dispatch. A single-active-producer contract needs to say what happens when several inputs are live. Regression coverage should include an exhausted feedback receiver selected as an additional ready node, a deferred replacement, and a second write already in flight. [Budget guard][visit-limit], [async admission][async-ready-batch], [greedy consumption and writes][socket-writes].
2. **Make stream completion and callback injection independent of component scheduling.** Signal completion from task completion so success, raised errors, and pre-start cancellation all wake the reader. Clarify single-consumer and abandonment semantics. Separate sender-less business input from internal callback injection so tapping a component cannot activate it. Use an explicit waiting policy for cancellation settlement and report pending cleanup honestly while keeping task ownership. Sibling cancellation, result availability, and a failed callback after queueing a chunk are useful existing contracts to preserve. [Stream handle][stream-handle], [forwarder and completion][stream-inject], [callback failure contract][callback-error-test].
3. **Align checkpoints with valid graph transitions.** Keep original inputs as supplied after normalization, preserve the last committed visit count for a retryable failed dispatch, and identify the phase of failures after invocation. Expose whether a snapshot is complete enough to resume. A compatible definition identity should cover socket paths and wiring as well as the node set. Keep legacy decoding isolated with its own tests. Component side effects and process-local resources need a distinct replay contract. [Snapshot construction][snapshot-build], [resume verification][snapshot-validate], [fallback behavior][field-fallback], [legacy resume control][legacy-resume-test].
4. **Strengthen extension boundaries and the local evidence for them.** Add typed framework-owned representations for pending inputs and dispatch. Keep graph socket metadata stable across runs, validate that wrapper mappings reach mandatory child inputs, and preserve caller definitions in specialized deserializers. Make late blockage diagnostics work with an empty remainder and update the runtime docstrings. Evolve the test matrix to cover the combinations of conditional branches, queue position, and cancellation windows. A documented local BDD test group would help keep full collection, selected execution, and per-path assertions distinct. [Run state and queue][queue-build], [blocked diagnostic][blocking-diagnostic], [wrapper validation][super-validation], [collection summary][collection-summary], [shared execution scenarios][feature-contract].

## 10. Evidence appendix

### Artifact provenance

These archived files predate the fresh review. The UTC modification times describe the files on this machine. SHA-256 values identify the exact bytes inspected. The logs identify the checkout path in tracebacks and warnings. The recorded run data has no embedded commit ID. I checked cited traceback locations against the verified checkout. [Example archived checkout path][image-fail], [focused checkout path][integration-warnings].

| Artifact | UTC modification date and time | SHA-256 |
| --- | --- | --- |
| [Full collection log][collection-summary] | 2026-11-19 03:36:04 | `603ab1a9e5e7da80da44611b7e62e086eb17b2f4c8ffaef69a42bccbbdfa3c42` |
| [Broad fallback log][broad-summary] | 2026-11-19 03:36:09 | `7103a1ea6c9910637ae98351abb8b2707a59d608d1c23b8d8d4b71d6509b5f49` |
| [Focused integration log][integration-summary] | 2026-11-19 03:37:27 | `a7051c4c7b02be795eb84bf40344616afac1f95cdc200e24c10c979e0f48eb82` |
| [Probe log][probes] | 2026-11-19 03:37:04 | `4d8ea13adf50c201e2d63b7f5366336709e385b37cefa683603f0e627aee7f66` |
| [Python 3.14 install transaction][inventory] | 2026-11-19 03:35:32 | `9e6de4d2c44d8e0202f5adecc6ebdef7ea9b551157a05726a47473a5801ee327` |
| [Wheel inventory][wheels] | 2026-11-19 03:34:22 | `bda4ed82caaadb92ddd892a4be5284dea893c88b540335bb35200de8d797ae31` |
| [Additional wheel inventory][wheel-gaps] | 2026-11-19 03:34:53 | `0deb34f43e1cfc3f4e60ca243666e654a082921e48956730edc72b7ec30ffd00` |
| [Coverage SQLite file][coverage-db] | 2026-11-19 03:36:06 | `00bcd3ddc1b1d765f75cb986760cfc9650076340762a5ce05fea13fedd0b743a` |

The broad archive has a snapshot of `comp2` before its first visit with an upstream result already committed, and a snapshot that encodes integer dictionary keys as entries. The focused archive has the later generator-visit snapshot. The checked-in fixtures show how those files were written, loaded and resumed. [Ordinary breakpoint artifact][standard-artifact], [integer-key artifact][keys-artifact], [later-visit artifact][loop-artifact], [resume fixture][integration-fixture].

### Source and test map

| Area | Source entry points | Primary repository contracts |
| --- | --- | --- |
| Registration, graph and types | [ComponentMeta][component-meta], [connect resolution][graph-match], [edge metadata][graph-edge], [converter dispatch][convert-value] | [Graph round trip with variadics][round-trip-test], [promotion][promotion-test], [dictionary-valued input][dict-input-test] |
| Scheduling and joins | [Readiness][readiness], [deferral order][defer-order], [sync loop][sync-loop], [async loop][async-loop], [edge delivery][write-output] | [Cross-mode scenarios][feature-contract], [feedback round order][loop-order-test], [optional RAG filter][optional-join-test], [run limit][limit-test] |
| Cancellation and streams | [Sibling cleanup][task-cancel], [queue and callback][stream-inject], [producer terminal signal][stream-runner] | [Normal stream][stream-happy-test], [callback failure][callback-error-test], [cooperative cancellation][close-test], [branch activation guard][agent-stream-test] |
| Snapshot and replay | [Run catch and capture][sync-break], [restore][resume], [value serializer][runtime-serde] | [Crash snapshot][malformed-output-test], [failed retry and reuse][retry-test], [repeated visit][repeat-visit-test], [legacy input format][legacy-resume-test] |
| Agent, tool and nested pipelines | [Agent signature][agent-signature], [step dispatch][agent-step-async], [tool planner][tool-schedule], [tool call adapter][tool-invoke], [nested pipeline][super-run], [mapping type reconciliation][super-reconcile] | [Hook order and restored counter][hooks-test], [tool plan controls][tool-schedule-test], [wrapper async round trip][super-round-trip-test] |

### Review commands and interpretation

- `date -u '+%Y-%m-%dT%H:%M:%SZ'`, `git rev-parse HEAD`, and `git status --porcelain=v1 --untracked-files=all` recorded time and checkout identity. The end check uses `git --no-optional-locks status` with the same porcelain and untracked-file flags.
- `rg --files --hidden` with instruction filename filters, `cat`, `rg -n`, and `nl -ba` found and inspected source, tests, project configuration, and archive lines. `git rev-parse --is-shallow-repository` reported a shallow checkout, so judgments about design pressures are based on the pinned contents.
- Within the archive, `stat -c '%n %s %y' *.log *.tsv broad/coverage` and `sha256sum *.log *.tsv broad/coverage` recorded provenance. `find repo-integration/pytest -name '*.json'` identified the focused snapshots. `jq` inspected breakpoint names, visit counts, input format, and saved input and output entries.
- A read-only `sqlite3 -readonly broad/coverage` query read coverage schema and metadata, checked context and arc counts, and compared selected source line numbers to each file's `line_bits` bitmap. The byte offset is the integer quotient of line number by eight plus one. The bit position is the line number modulo eight. This checks recorded execution at those statements, with no per-test attribution.
- Full previous argv, exact fallback selectors, and probe fixtures are unavailable in the permitted archive. The checked-in baseline commands are `hatch run test:unit` and `hatch run test:integration`. They identify the project's intended test groups. The archive's summaries, tracebacks and fixture artifacts identify what the previous runs established. [Configured test commands][hatch-scripts], [collection summary][collection-summary], [fallback summary][broad-summary], [focused summary][integration-summary], [probe summary][probes].

[rubric]: ./README.md:1
[repo-instructions]: repos/deepset-ai__haystack/AGENTS.md:1
[test-instructions]: repos/deepset-ai__haystack/test/AGENTS.md:1
[compaction-instructions]: repos/deepset-ai__haystack/haystack/hooks/compaction/AGENTS.md:1
[api-instructions]: repos/deepset-ai__haystack/AGENTS.md:81
[exports]: repos/deepset-ai__haystack/haystack/__init__.py:14
[pipeline-class]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:118
[component-doc]: repos/deepset-ai__haystack/haystack/core/component/component.py:58
[component-meta]: repos/deepset-ai__haystack/haystack/core/component/component.py:208
[component-registry]: repos/deepset-ai__haystack/haystack/core/component/component.py:563
[dynamic-sockets]: repos/deepset-ai__haystack/haystack/core/component/component.py:414
[socket-types]: repos/deepset-ai__haystack/haystack/core/component/types.py:19
[graph-init]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:93
[graph-add]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:439
[graph-remove]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:539
[graph-connect]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:600
[graph-match]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:675
[graph-edge]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:780
[input-description]: repos/deepset-ai__haystack/haystack/core/pipeline/descriptions.py:11
[strict-types]: repos/deepset-ai__haystack/haystack/core/type_utils.py:136
[conversions]: repos/deepset-ai__haystack/haystack/core/type_utils.py:229
[convert-value]: repos/deepset-ai__haystack/haystack/core/type_utils.py:323
[validate-input]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1140
[auto-variadic]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1180
[prepare-input]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1234
[input-ledger]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1326
[consume]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1348
[defaults]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1498
[output-warnings]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1930
[no-output]: repos/deepset-ai__haystack/haystack/core/pipeline/component_checks.py:10
[readiness]: repos/deepset-ai__haystack/haystack/core/pipeline/component_checks.py:41
[predecessors]: repos/deepset-ai__haystack/haystack/core/pipeline/component_checks.py:156
[priority]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1429
[fifo]: repos/deepset-ai__haystack/haystack/core/pipeline/utils.py:87
[queue-build]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1410
[visits]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1452
[visit-limit]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1482
[defer-order]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1523
[blocking-diagnostic]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1599
[write-output]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1692
[prune]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1745
[queue-refresh]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1755
[quiescent]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1880
[fanin-sort]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1970
[socket-writes]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:2020
[lifecycle]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1054
[component-span]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:1112
[copy-policy]: repos/deepset-ai__haystack/haystack/core/pipeline/utils.py:22
[run-docs]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:303
[sync-init]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:341
[sync-loop]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:401
[sync-defer]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:442
[sync-invoke]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:157
[sync-break]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:460
[sync-results]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:514
[resume]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:375
[async-generator]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:808
[async-loop]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:922
[async-ready-batch]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:1028
[async-dispatch]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:772
[async-isolation]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:672
[async-final]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:1087
[async-fallback]: repos/deepset-ai__haystack/haystack/utils/async_utils.py:33
[task-cancel]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:615
[stream-handle]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:45
[stream-close]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:106
[stream-contract]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:1222
[stream-inject]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:1300
[stream-runner]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:1339
[callback-select]: repos/deepset-ai__haystack/haystack/dataclasses/streaming_chunk.py:229
[asyncio-waitfor]: /usr/lib/python3.14/asyncio/tasks.py:440
[errors]: repos/deepset-ai__haystack/haystack/core/errors.py:10
[tracer]: repos/deepset-ai__haystack/haystack/tracing/tracer.py:106
[branch-joiner]: repos/deepset-ai__haystack/haystack/components/joiners/branch.py:93
[list-joiner]: repos/deepset-ai__haystack/haystack/components/joiners/list_joiner.py:107
[doc-joiner]: repos/deepset-ai__haystack/haystack/components/joiners/document_joiner.py:102
[doc-merge]: repos/deepset-ai__haystack/haystack/components/joiners/document_joiner.py:221
[document-copy]: repos/deepset-ai__haystack/haystack/dataclasses/document.py:111
[store-ownership]: repos/deepset-ai__haystack/haystack/document_stores/in_memory/document_store.py:154
[graph-serde]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:152
[graph-load]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:229
[component-serde]: repos/deepset-ai__haystack/haystack/core/serialization.py:43
[yaml]: repos/deepset-ai__haystack/haystack/marshal/yaml.py:27
[runtime-serde]: repos/deepset-ai__haystack/haystack/utils/base_serialization.py:20
[field-fallback]: repos/deepset-ai__haystack/haystack/utils/base_serialization.py:150
[snapshot-state]: repos/deepset-ai__haystack/haystack/dataclasses/breakpoints.py:53
[snapshot-validate]: repos/deepset-ai__haystack/haystack/core/pipeline/breakpoint.py:55
[snapshot-save]: repos/deepset-ai__haystack/haystack/core/pipeline/breakpoint.py:141
[snapshot-build]: repos/deepset-ai__haystack/haystack/core/pipeline/breakpoint.py:226
[snapshot-transform]: repos/deepset-ai__haystack/haystack/core/pipeline/breakpoint.py:254
[agent-io]: repos/deepset-ai__haystack/haystack/components/agents/agent.py:551
[agent-run]: repos/deepset-ai__haystack/haystack/components/agents/agent.py:930
[agent-signature]: repos/deepset-ai__haystack/haystack/components/agents/agent.py:882
[agent-fresh]: repos/deepset-ai__haystack/haystack/components/agents/agent.py:787
[agent-step]: repos/deepset-ai__haystack/haystack/components/agents/agent.py:1070
[agent-step-async]: repos/deepset-ai__haystack/haystack/components/agents/agent.py:1138
[agent-span]: repos/deepset-ai__haystack/haystack/components/agents/agent.py:739
[agent-exit]: repos/deepset-ai__haystack/haystack/components/agents/agent.py:1208
[state]: repos/deepset-ai__haystack/haystack/components/agents/state/state.py:144
[hook-order]: repos/deepset-ai__haystack/haystack/hooks/invocation.py:50
[tool-args]: repos/deepset-ai__haystack/haystack/components/agents/tool_calling.py:304
[tool-schedule]: repos/deepset-ai__haystack/haystack/components/agents/tool_calling.py:430
[tool-sync]: repos/deepset-ai__haystack/haystack/components/agents/tool_calling.py:583
[tool-async]: repos/deepset-ai__haystack/haystack/components/agents/tool_calling.py:673
[tool-finalize]: repos/deepset-ai__haystack/haystack/components/agents/tool_calling.py:512
[tool-span]: repos/deepset-ai__haystack/haystack/components/agents/tool_calling.py:184
[tool-spawn]: repos/deepset-ai__haystack/haystack/tools/toolset.py:128
[tool-invoke]: repos/deepset-ai__haystack/haystack/tools/tool.py:267
[super-init]: repos/deepset-ai__haystack/haystack/core/super_component/super_component.py:66
[super-run]: repos/deepset-ai__haystack/haystack/core/super_component/super_component.py:123
[super-types]: repos/deepset-ai__haystack/haystack/core/super_component/super_component.py:217
[super-reconcile]: repos/deepset-ai__haystack/haystack/core/super_component/utils.py:16
[pipeline-tool]: repos/deepset-ai__haystack/haystack/tools/pipeline_tool.py:185
[pipeline-tool-serde]: repos/deepset-ai__haystack/haystack/tools/pipeline_tool.py:202
[component-tool]: repos/deepset-ai__haystack/haystack/tools/component_tool.py:181
[component-tool-schema]: repos/deepset-ai__haystack/haystack/tools/component_tool.py:367
[agent-tool]: repos/deepset-ai__haystack/haystack/tools/agent_tool.py:184
[reentrancy-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline.py:26
[dict-input-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline.py:77
[empty-output-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline.py:97
[blocked-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline.py:222
[loop-order-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline.py:334
[weighted-join-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline.py:424
[optional-join-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline.py:464
[greedy-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline.py:554
[cancel-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline.py:638
[context-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline.py:728
[nested-error-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline.py:776
[stream-happy-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline_stream.py:91
[callback-error-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline_stream.py:305
[close-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline_stream.py:365
[agent-stream-test]: repos/deepset-ai__haystack/test/components/agents/test_agent.py:2444
[hooks-test]: repos/deepset-ai__haystack/test/components/agents/test_agent_hooks.py:269
[tool-schedule-test]: repos/deepset-ai__haystack/test/components/agents/test_tool_calling.py:1069
[super-mapping-test]: repos/deepset-ai__haystack/test/core/super_component/test_super_component.py:137
[super-round-trip-test]: repos/deepset-ai__haystack/test/core/super_component/test_super_component.py:452
[pipeline-tool-schema-test]: repos/deepset-ai__haystack/test/tools/test_pipeline_tool.py:181
[lifecycle-test]: repos/deepset-ai__haystack/test/core/pipeline/test_pipeline_lifecycle.py:189
[limit-test]: repos/deepset-ai__haystack/test/core/pipeline/test_pipeline_base.py:1376
[promotion-test]: repos/deepset-ai__haystack/test/core/pipeline/test_pipeline_base.py:2860
[round-trip-test]: repos/deepset-ai__haystack/test/core/pipeline/test_pipeline_base.py:1839
[malformed-output-test]: repos/deepset-ai__haystack/test/core/pipeline/test_pipeline_crash_regular_pipeline_snapshot_is_raised.py:63
[keys-test]: repos/deepset-ai__haystack/test/core/pipeline/test_breakpoint.py:155
[retry-test]: repos/deepset-ai__haystack/test/core/pipeline/test_breakpoint.py:228
[repeat-visit-test]: repos/deepset-ai__haystack/test/core/pipeline/test_breakpoint.py:310
[marker-resume-test]: repos/deepset-ai__haystack/test/core/pipeline/test_breakpoint.py:324
[legacy-resume-test]: repos/deepset-ai__haystack/test/core/pipeline/test_breakpoint.py:360
[snapshot-metadata-test]: repos/deepset-ai__haystack/test/core/pipeline/test_breakpoint.py:410
[fallback-test]: repos/deepset-ai__haystack/test/core/pipeline/test_breakpoint.py:530
[feature-contract]: repos/deepset-ai__haystack/test/core/pipeline/features/pipeline_run.feature:1
[feature-runner]: repos/deepset-ai__haystack/test/core/pipeline/features/conftest.py:9
[infinite-loop-test]: repos/deepset-ai__haystack/test/core/pipeline/features/test_run.py:90
[single-route-test]: repos/deepset-ai__haystack/test/core/pipeline/features/test_run.py:4672
[auto-join-test]: repos/deepset-ai__haystack/test/core/pipeline/features/test_run.py:4923
[integration-fixture]: repos/deepset-ai__haystack/test/core/pipeline/breakpoints/conftest.py:25
[loop-test-graph]: repos/deepset-ai__haystack/test/core/pipeline/breakpoints/test_pipeline_breakpoints_loops.py:59
[loop-test-resume]: repos/deepset-ai__haystack/test/core/pipeline/breakpoints/test_pipeline_breakpoints_loops.py:149
[hybrid-test]: repos/deepset-ai__haystack/test/core/pipeline/breakpoints/test_pipeline_breakpoints_rag_hybrid.py:57
[notebook-test]: repos/deepset-ai__haystack/test/core/pipeline/test_pipeline_base.py:331
[notebook-source]: repos/deepset-ai__haystack/haystack/core/pipeline/base.py:956
[image-test]: repos/deepset-ai__haystack/test/dataclasses/test_image_content.py:124
[image-source]: repos/deepset-ai__haystack/haystack/dataclasses/image_content.py:123
[device-map-test]: repos/deepset-ai__haystack/test/utils/test_device.py:38
[device-map-source]: repos/deepset-ai__haystack/haystack/utils/device.py:218
[torch-import]: repos/deepset-ai__haystack/haystack/utils/device.py:11
[lazy-import]: repos/deepset-ai__haystack/haystack/lazy_imports.py:46
[device-resolution-test]: repos/deepset-ai__haystack/test/utils/test_device.py:136
[nltk-guard]: repos/deepset-ai__haystack/haystack/components/preprocessors/sentence_tokenizer.py:80
[nltk-test]: repos/deepset-ai__haystack/test/components/preprocessors/test_sentence_tokenizer.py:13
[project-deps]: repos/deepset-ai__haystack/pyproject.toml:44
[hatch-deps]: repos/deepset-ai__haystack/pyproject.toml:88
[hatch-converters]: repos/deepset-ai__haystack/pyproject.toml:106
[hatch-nltk]: repos/deepset-ai__haystack/pyproject.toml:119
[hatch-pytest]: repos/deepset-ai__haystack/pyproject.toml:134
[hatch-scripts]: repos/deepset-ai__haystack/pyproject.toml:149
[ci-python]: repos/deepset-ai__haystack/.github/workflows/tests.yml:32
[ci-unit]: repos/deepset-ai__haystack/.github/workflows/tests.yml:137
[collection-summary]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/full-collect.log:7499
[converter-collection]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/full-collect.log:7403
[sas-collection]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/full-collect.log:7444
[nltk-collection]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/full-collect.log:7454
[bdd-collection]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/full-collect.log:7464
[broad-summary]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/broad.log:580
[broad-coverage]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/broad.log:440
[broad-agent-coverage]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/broad.log:305
[broad-warnings]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/broad.log:263
[notebook-fail]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/broad.log:62
[image-fail]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/broad.log:116
[device-map-fail]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/broad.log:155
[device-resolution-fail]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/broad.log:210
[integration-summary]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/repo-integration.log:26
[integration-warnings]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/repo-integration.log:2
[probes]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/probes.log:1
[probe-budget]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/probes.log:1
[probe-greedy]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/probes.log:4
[probe-routing]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/probes.log:7
[probe-close]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/probes.log:10
[probe-timeout]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/probes.log:11
[probe-bad-map]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/probes.log:12
[probe-original]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/probes.log:13
[inventory]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/installed314.log:1
[wheels]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/wheelhouse-314.tsv:1
[wheel-gaps]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/wheelhouse-314-extra.tsv:7
[coverage-db]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/broad/coverage
[loop-artifact]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/repo-integration/pytest/test_pipeline_breakpoints_seco1/llm_1_2026_11_19_03_37_27.json:105
[keys-artifact]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/broad/pytest/test_resume_from_snapshot_file0/sink_0_2026_11_19_03_36_00.json:24
[standard-artifact]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/broad/pytest/test_breakpoint_saves_intermed0/comp2_0_2026_11_19_03_36_00.json:66
[trace-test]: repos/deepset-ai__haystack/test/core/pipeline/test_tracing.py:160
[answer-breakpoints]: repos/deepset-ai__haystack/test/core/pipeline/breakpoints/test_pipeline_breakpoints_answer_joiner.py:33
[branch-breakpoints]: repos/deepset-ai__haystack/test/core/pipeline/breakpoints/test_pipeline_breakpoints_branch_joiner.py:47
[list-breakpoints]: repos/deepset-ai__haystack/test/core/pipeline/breakpoints/test_pipeline_breakpoints_list_joiner.py:47
[string-breakpoints]: repos/deepset-ai__haystack/test/core/pipeline/breakpoints/test_pipeline_breakpoints_string_joiner.py:37
[async-defer]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:1050
[defer-test]: repos/deepset-ai__haystack/test/core/pipeline/test_pipeline_base.py:1704
[agent-graph-test]: repos/deepset-ai__haystack/test/components/agents/test_agent.py:1978
[agent-parent-test]: repos/deepset-ai__haystack/test/components/agents/test_agent.py:1710
[device-default]: repos/deepset-ai__haystack/haystack/utils/device.py:496
[super-validation]: repos/deepset-ai__haystack/haystack/core/super_component/super_component.py:185
[super-forward]: repos/deepset-ai__haystack/haystack/core/super_component/super_component.py:354
[tool-ranker-fixture]: repos/deepset-ai__haystack/test/tools/test_pipeline_tool.py:26
[tool-async-shape-test]: repos/deepset-ai__haystack/test/tools/test_pipeline_tool.py:372
[super-run-test]: repos/deepset-ai__haystack/test/core/super_component/test_super_component.py:224
[serde-copy]: repos/deepset-ai__haystack/haystack/core/serialization.py:294
[super-decode]: repos/deepset-ai__haystack/haystack/core/super_component/super_component.py:488
[super-serde-control]: repos/deepset-ai__haystack/test/core/super_component/test_super_component.py:245
[stream-filter-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline_stream.py:246
[state-serde]: repos/deepset-ai__haystack/haystack/components/agents/state/state.py:192
[legacy-format]: repos/deepset-ai__haystack/haystack/dataclasses/breakpoints.py:60
[agent-callback]: repos/deepset-ai__haystack/haystack/components/agents/agent.py:832
[tool-callback-injection]: repos/deepset-ai__haystack/haystack/components/agents/tool_calling.py:358
[tool-result-stream]: repos/deepset-ai__haystack/haystack/components/agents/tool_calling.py:714
[tool-result-stream-test]: repos/deepset-ai__haystack/test/components/agents/test_tool_calling.py:274
[async-partial]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:629
[async-isolated-partial]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:727
[isolated-partial-test]: repos/deepset-ai__haystack/test/core/pipeline/test_async_pipeline.py:621
[tool-batching-order]: repos/deepset-ai__haystack/haystack/components/agents/tool_calling.py:456
[trace-content]: repos/deepset-ai__haystack/haystack/tracing/tracer.py:49
[async-result-docs]: repos/deepset-ai__haystack/haystack/core/pipeline/pipeline.py:1188
[pruning-test]: repos/deepset-ai__haystack/test/core/pipeline/test_pipeline_base.py:1232
[snapshot-unwrap]: repos/deepset-ai__haystack/haystack/core/pipeline/breakpoint.py:291
[pytest-options]: repos/deepset-ai__haystack/pyproject.toml:184
[branch-contract]: repos/deepset-ai__haystack/haystack/components/joiners/branch.py:17
[hybrid-artifact]: $HOME/agent-work/scratch/haystack-runtime-20261119.MeVYBUmL/out/repo-integration/pytest/test_pipeline_breakpoints_hybr3/doc_joiner_0_2026_11_19_03_37_27.json:194
