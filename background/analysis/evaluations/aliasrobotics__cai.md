# CAI v1.1.5 runtime evaluation

## 1. Snapshot, scope, and elapsed-time evidence.

I reviewed the detached checkout of `aliasrobotics/cai` at **`6dc79257777f5f1c9500b4d2319935d34a47412e`**, titled *CAI v1.1.5 — final archival snapshot*. The checkout was clean at entry and at the final verification. All source inspection used this revision. The repository advertises Python 3.10 and later and lists Python 3.10–3.12 in its classifiers. [pyproject.toml:1](repos/aliasrobotics__cai/pyproject.toml:1) [pyproject.toml:45](repos/aliasrobotics__cai/pyproject.toml:45)

The core SDK has a clear turn model and can run a substantial suite against local fake models. The largest correctness problems are at the transitions between a run and its caller. The API can run a request twice and commit a reply different from the one it delivered. The SDK can leave work active after rejection or stream abandonment. The continuous worker supervisor can report a successful exit while the child is still running. These were reproduced with synthetic inputs and local state only. The evidence supports fixing lifecycle ownership and commit semantics before reorganizing provider adapters.

I covered the headless CLI, SDK, in-process API, worker supervision, state recovery, and observability. Product-domain tools and prompts provided background context. Live provider behavior, platform-specific worker terminals, system service management, and frontend behavior were outside the dynamic evaluation. Python ran in a private Bubblewrap namespace with a cleared environment, read-only sources, and private temporary storage. Calls in the API controls dispatched directly into ASGI in the same process. The runner fixtures used only text and inert callbacks.

| UTC on 2026-11-19 | Activity |
| --- | --- |
| 07:24:39 | Checked the pinned HEAD and clean status and read the complete evaluation protocol. |
| 07:24:47–07:29:08 | Mapped runtime entry points, inspected package requirements and fixtures, established the read-only test namespace, and ran the first repository tests. |
| 07:29:08–07:33:58 | Restored usable local dependencies, ran SDK and history tests, and exercised retention, session state, and stream termination. |
| 07:33:58–07:37:57 | Cross-checked worker ownership and retries, exercised exact route and event bodies, and verified trace and guardrail behavior with independent controls. |
| 07:37:57–07:41:10 | Checked MCP cleanup against local package artifacts, exercised actual ASGI dispatch, tested usage parity, and compared persistence code with restart paths. |
| 07:41:10–07:45:15 | Confirmed process-level accounting, drafted the architecture and findings, and verified snapshot replay in separate processes. |
| 07:45:15–07:49:41 | Reran the report's repository tests and key controls, checked cancellation on two interpreters, measured replay allocation, and rechecked lifecycle and source references. |
| 07:49:41–07:54:43 | Verified the history stores and report reproduction, audited the source references, and rechecked the report and checkout. |

**Elapsed active review window** was 30 minutes and 4 seconds (07:24:39 to 07:54:43 UTC). This is wall elapsed time for inspection, experiment design and execution, and writing. The trace lifetime control ran while I inspected other code. There were no idle or padding waits. The protocol enumerates nine headings. I kept those headings and used the requested tenth heading for prioritized improvements. [evaluations/README.md:8](./README.md:8)

## 2. Core architecture and end-to-end control/data flow.

### Entry points and run scopes

| Scope | Owner and flow | State boundary |
| --- | --- | --- |
| SDK invocation | `Runner.run` owns an awaited turn loop. `run_streamed` starts a producer task and returns a result with an event iterator. Both pass model responses to the same step interpreter. [src/cai/sdk/agents/run.py:179](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:179) [src/cai/sdk/agents/run.py:537](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:537) [src/cai/sdk/agents/run.py:889](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:889) | Original input, generated items, model responses, current agent, tracing scope, and a context wrapper live for that invocation. The caller can carry the transcript into a later run through `to_input_list()`. [src/cai/sdk/agents/run.py:188](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:188) [src/cai/sdk/agents/result.py:29](repos/aliasrobotics__cai/src/cai/sdk/agents/result.py:29) [src/cai/sdk/agents/result.py:76](repos/aliasrobotics__cai/src/cai/sdk/agents/result.py:76) |
| Headless CLI session | The installed `cai` dispatcher selects headless or API mode. The headless path initializes active-agent state, reads a user turn, invokes the SDK, and records or retains its history. The chat-completions adapter ordinarily owns the existing history, so the CLI passes the new message for an established conversation. [pyproject.toml:281](repos/aliasrobotics__cai/pyproject.toml:281) [src/cai/cli.py:299](repos/aliasrobotics__cai/src/cai/cli.py:299) [src/cai/cli.py:385](repos/aliasrobotics__cai/src/cai/cli.py:385) [src/cai/cli_headless.py:650](repos/aliasrobotics__cai/src/cai/cli_headless.py:650) [src/cai/cli_headless.py:1264](repos/aliasrobotics__cai/src/cai/cli_headless.py:1264) | The active-agent manager, model histories, parallel isolation store, and JSONL records have different lifetimes. A resumed conversation rehydrates model history and mirrors it into the agent manager. [src/cai/sdk/agents/simple_agent_manager.py:22](repos/aliasrobotics__cai/src/cai/sdk/agents/simple_agent_manager.py:22) [src/cai/repl/session_resume.py:725](repos/aliasrobotics__cai/src/cai/repl/session_resume.py:725) |
| API session | The application owns a `SessionManager`. Its factory creates an agent per session on the factory-backed path. Ordinary inference delegates to `SessionState.run_inference`. Streaming endpoints use their own generator adapters and commit paths. [src/cai/api/app.py:94](repos/aliasrobotics__cai/src/cai/api/app.py:94) [src/cai/api/sessions.py:31](repos/aliasrobotics__cai/src/cai/api/sessions.py:31) [src/cai/api/sessions.py:98](repos/aliasrobotics__cai/src/cai/api/sessions.py:98) [src/cai/api/app.py:663](repos/aliasrobotics__cai/src/cai/api/app.py:663) [src/cai/api/app.py:761](repos/aliasrobotics__cai/src/cai/api/app.py:761) | Manager state is a process-local mapping. The session holds history, timestamps, a per-session lock, the current task handle, and recent stream steps. Model switching builds a new agent and clears history. [src/cai/api/sessions.py:65](repos/aliasrobotics__cai/src/cai/api/sessions.py:65) [src/cai/api/sessions.py:169](repos/aliasrobotics__cai/src/cai/api/sessions.py:169) [src/cai/api/sessions.py:211](repos/aliasrobotics__cai/src/cai/api/sessions.py:211) |
| Headless parallel run | The logical path gathers per-instance coroutines and retains their results and histories by slot. The parent owns those coroutines. The optional external-worker path creates separate processes through a terminal backend and aggregates JSON result files. [src/cai/cli_headless.py:1763](repos/aliasrobotics__cai/src/cai/cli_headless.py:1763) [src/cai/cli_headless.py:1830](repos/aliasrobotics__cai/src/cai/cli_headless.py:1830) [src/cai/cli_headless.py:1978](repos/aliasrobotics__cai/src/cai/cli_headless.py:1978) [src/cai/cli_headless.py:2199](repos/aliasrobotics__cai/src/cai/cli_headless.py:2199) | Logical history is copied by slot unless a selected configuration shares it. The detached path receives a history and usage payload from each successful publication. The caller retains a file-level observation channel for detached workers. [src/cai/repl/commands/_parallel_monolith.py:66](repos/aliasrobotics__cai/src/cai/repl/commands/_parallel_monolith.py:66) [src/cai/sdk/agents/parallel_isolation.py:39](repos/aliasrobotics__cai/src/cai/sdk/agents/parallel_isolation.py:39) [src/cai/parallel_worker.py:71](repos/aliasrobotics__cai/src/cai/parallel_worker.py:71) [src/cai/cli_headless.py:2281](repos/aliasrobotics__cai/src/cai/cli_headless.py:2281) |
| Continuous loop | A parent process reads a run directory and starts one child for a tick. It owns the child's direct process handle and an output pump, then records status, updates state, and calculates the remaining interval. An optional generated service supervises the parent process. [src/cai/continuous_ops/loop_runner.py:511](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:511) [src/cai/continuous_ops/loop_runner.py:273](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:273) [src/cai/continuous_ops/loop_runner.py:582](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:582) [src/cai/continuous_ops/systemd_unit.py:59](repos/aliasrobotics__cai/src/cai/continuous_ops/systemd_unit.py:59) | The directory stores task metadata, a bounded conversation snapshot, context, and logs. In-memory iteration and anomaly counters are initialized again when the loop process starts. [src/cai/continuous_ops/loop_runner.py:551](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:551) [src/cai/continuous_ops/loop_runner.py:575](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:575) [src/cai/continuous_ops/loop_runner.py:596](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:596) |

### One SDK turn

1. The entry point builds a context wrapper and opens a trace if needed. At the start of an agent segment the runner gets the agent's available tools and begins a span. At each turn it checks the turn count, evaluates instructions, resolves a model and model settings, and assembles the next input from the original items plus the generated items. The non-streaming entry point checks the initial input through a sibling coroutine. The streamed entry point starts input checks in their own task. The mutable context wrapper passes application dependencies to hooks and tools. The model receives the request assembled by the runner. [src/cai/sdk/agents/run.py:179](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:179) [src/cai/sdk/agents/run.py:207](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:207) [src/cai/sdk/agents/run.py:235](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:235) [src/cai/sdk/agents/run.py:666](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:666) [src/cai/sdk/agents/run.py:918](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:918) [src/cai/sdk/agents/run_context.py:12](repos/aliasrobotics__cai/src/cai/sdk/agents/run_context.py:12)
2. The `Model` interface supplies a whole response or an iterator of response events. `ModelProvider` resolves names. The active OpenAI provider is lazy and shares HTTP client resources across requests. CAI's chat-completions class delegates provider I/O and normalization to helper modules, with state and retry decisions still in the main class. The streamed runner relays raw events and needs a completed response event to produce a `ModelResponse` for the same step interpreter. [src/cai/sdk/agents/models/interface.py:34](repos/aliasrobotics__cai/src/cai/sdk/agents/models/interface.py:34) [src/cai/sdk/agents/models/openai_provider.py:17](repos/aliasrobotics__cai/src/cai/sdk/agents/models/openai_provider.py:17) [src/cai/sdk/agents/models/openai_provider.py:67](repos/aliasrobotics__cai/src/cai/sdk/agents/models/openai_provider.py:67) [src/cai/sdk/agents/models/openai_chatcompletions.py:119](repos/aliasrobotics__cai/src/cai/sdk/agents/models/openai_chatcompletions.py:119) [src/cai/sdk/agents/models/openai_chatcompletions.py:3951](repos/aliasrobotics__cai/src/cai/sdk/agents/models/openai_chatcompletions.py:3951) [src/cai/sdk/agents/run.py:845](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:845)
3. `RunImpl` classifies response items, resolves callable tools and handoffs by name, runs permitted function calls, and generates typed items. Function calls can overlap. The response list pairs results back to the original calls in input order even when callbacks finish in a different order. An unknown local function call can receive a synthetic result so the conversation keeps a call/output pair. The interpreter yields a final output, a handoff, or a request to continue. A handoff has priority over final-output detection after the tool phase. [src/cai/sdk/agents/_run_impl.py:327](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:327) [src/cai/sdk/agents/_run_impl.py:432](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:432) [src/cai/sdk/agents/_run_impl.py:483](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:483) [src/cai/sdk/agents/_run_impl.py:552](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:552) [src/cai/sdk/agents/_run_impl.py:622](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:622) [src/cai/sdk/agents/_run_impl.py:844](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:844) [src/cai/sdk/agents/_run_impl.py:884](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:884)
4. A handoff produces paired typed transcript items and selects one new active agent. Additional handoff requests in the same step receive rejection outputs. The selected handoff's input filter can reshape the next agent's transcript. The same context and run turn budget cross the handoff. `Agent.as_tool` calls an inner `Runner.run` and returns an extracted result to the caller. It passes the application context and starts a separate run with its own defaults. The application also has an in-memory plan associated with the resolved model instance. That plan records progress for the caller. The periodic loop's planned task metadata is a separate storage contract. [src/cai/sdk/agents/_run_impl.py:945](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:945) [src/cai/sdk/agents/_run_impl.py:989](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:989) [src/cai/sdk/agents/_run_impl.py:1020](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:1020) [src/cai/sdk/agents/run.py:330](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:330) [src/cai/sdk/agents/agent.py:173](repos/aliasrobotics__cai/src/cai/sdk/agents/agent.py:173) [src/cai/tools/plan.py:66](repos/aliasrobotics__cai/src/cai/tools/plan.py:66) [src/cai/continuous_ops/task_queue.py:149](repos/aliasrobotics__cai/src/cai/continuous_ops/task_queue.py:149)
5. A final output may be text, an explicitly selected tool result, or a validated structured response. The runner records the guardrail results and the last active agent with the new items. The stream producer publishes raw, semantic item, and agent-change events and signals completion on its usual paths. The SSE layer translates these events or emits high-level lifecycle events through `RunHooks`. Independently, the process output bus publishes typed activity notifications to synchronous subscribers. The activity registry stores bounded records for inspection. [src/cai/sdk/agents/_run_impl.py:453](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:453) [src/cai/sdk/agents/agent_output.py:40](repos/aliasrobotics__cai/src/cai/sdk/agents/agent_output.py:40) [src/cai/sdk/agents/run.py:314](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:314) [src/cai/sdk/agents/run.py:755](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:755) [src/cai/sdk/agents/_run_impl.py:1135](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:1135) [src/cai/api/streaming.py:132](repos/aliasrobotics__cai/src/cai/api/streaming.py:132) [src/cai/output.py:203](repos/aliasrobotics__cai/src/cai/output.py:203) [src/cai/output.py:401](repos/aliasrobotics__cai/src/cai/output.py:401)

### Scheduling, failure, and restart

The continuous scheduler materializes model-assisted planning as local task data, has a single-task bootstrap for an older run directory, and ranks tasks by recency with a preference for entries that are due. The fallback picks from the full list when no entry is due. This makes the recurrence values scheduling preferences. The parent attributes completion on a successful child status, merges log-derived records, and updates summaries before entering provider recovery. The loop observes pause and stop at tick boundaries. The pause wait and provider recovery wait have their own loops, which explains why a stop request can be delayed. [src/cai/continuous_ops/model_parse.py:44](repos/aliasrobotics__cai/src/cai/continuous_ops/model_parse.py:44) [src/cai/continuous_ops/task_queue.py:127](repos/aliasrobotics__cai/src/cai/continuous_ops/task_queue.py:127) [src/cai/continuous_ops/task_queue.py:191](repos/aliasrobotics__cai/src/cai/continuous_ops/task_queue.py:191) [src/cai/continuous_ops/loop_runner.py:110](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:110) [src/cai/continuous_ops/loop_runner.py:199](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:199) [src/cai/continuous_ops/loop_runner.py:582](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:582) [src/cai/continuous_ops/loop_runner.py:626](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:626)

The SDK owns transitions within one run. Provider adapters can retry a request, and the headless non-streaming wrapper can retry an entire invocation on selected transport exceptions. The logical worker group gathers errors and recovers surviving histories. A detached-worker deadline ends the parent's wait while the detached process may continue. The continuous parent has its own child deadline and failure recovery loop. These clocks represent different operations, so an elapsed waiter deadline and an ended execution are different states. [src/cai/sdk/agents/models/openai_chatcompletions.py:908](repos/aliasrobotics__cai/src/cai/sdk/agents/models/openai_chatcompletions.py:908) [src/cai/cli_headless.py:1542](repos/aliasrobotics__cai/src/cai/cli_headless.py:1542) [src/cai/cli_headless.py:1830](repos/aliasrobotics__cai/src/cai/cli_headless.py:1830) [src/cai/cli_headless.py:2199](repos/aliasrobotics__cai/src/cai/cli_headless.py:2199) [src/cai/cli_headless.py:2333](repos/aliasrobotics__cai/src/cai/cli_headless.py:2333) [src/cai/continuous_ops/loop_runner.py:319](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:319) [src/cai/continuous_ops/loop_runner.py:666](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:666)

Ordinary SDK and API histories represent conversation state. CLI JSONL can replay or hydrate messages and usage metadata from older formats. Continuous snapshots export a bounded tail, then rehydrate that tail for a later child with the model and manager sharing the chosen list. Queue updates and snapshot files replace earlier files by rename. These checkpoints contain inputs, transcripts, or recency metadata. Mid-turn tasks, cancellation handles, and effects in flight live with their owning process. A crash between an effect and the successful task mark leaves the next process with the earlier checkpoint. [src/cai/sdk/agents/result.py:76](repos/aliasrobotics__cai/src/cai/sdk/agents/result.py:76) [src/cai/repl/session_resume.py:76](repos/aliasrobotics__cai/src/cai/repl/session_resume.py:76) [src/cai/repl/session_resume.py:725](repos/aliasrobotics__cai/src/cai/repl/session_resume.py:725) [src/cai/continuous_ops/session_snapshot.py:44](repos/aliasrobotics__cai/src/cai/continuous_ops/session_snapshot.py:44) [src/cai/continuous_ops/session_snapshot.py:90](repos/aliasrobotics__cai/src/cai/continuous_ops/session_snapshot.py:90) [src/cai/continuous_ops/task_queue.py:109](repos/aliasrobotics__cai/src/cai/continuous_ops/task_queue.py:109) [src/cai/continuous_ops/loop_runner.py:635](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:635)

## 3. Why the design works and its governing invariants.

- **A run has one active agent per turn.** The explicit next-step types give the SDK a small state machine. Provider choice and item I/O can vary independently of the state transitions. Tool replies stay correlated by call ID. The first selected handoff changes the active agent and the subsequent turn uses the filtered transcript. Typed completion and filter checks expose malformed input at the layer that owns the decision. [src/cai/sdk/agents/_run_impl.py:239](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:239) [src/cai/sdk/agents/_run_impl.py:277](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:277) [src/cai/sdk/agents/_run_impl.py:884](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:884) [src/cai/sdk/agents/_run_impl.py:945](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:945) [src/cai/sdk/agents/_run_impl.py:1020](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:1020)
- **Session history needs one authoritative snapshot per turn.** Deep-copying caller input, returning a new input list, and copying parallel history at the isolation boundary protect the caller's transcript. The API's serialization intent is clear from the per-session lock. Correct serialization also requires the composition and commit of one turn to use the same ownership boundary. The adapter's private history and intentional shared-history modes make that requirement especially important. [src/cai/sdk/agents/run.py:188](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:188) [src/cai/sdk/agents/result.py:76](repos/aliasrobotics__cai/src/cai/sdk/agents/result.py:76) [src/cai/sdk/agents/parallel_isolation.py:27](repos/aliasrobotics__cai/src/cai/sdk/agents/parallel_isolation.py:27) [src/cai/api/sessions.py:98](repos/aliasrobotics__cai/src/cai/api/sessions.py:98) [src/cai/sdk/agents/run.py:335](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:335)
- **Tool and model changes fit defined extension interfaces.** An injected model supplies the normalized response contract. Function schemas inspect the signature and document the shape passed to the model. The wrapper validates arguments before invoking the callable and supports separate user-error behavior. MCP adapters turn a connected server's inventory into function tools and expect a caller to own the connection lifecycle. This supports testing the turn loop independently of external adapters. [src/cai/sdk/agents/models/interface.py:34](repos/aliasrobotics__cai/src/cai/sdk/agents/models/interface.py:34) [src/cai/sdk/agents/tool.py:194](repos/aliasrobotics__cai/src/cai/sdk/agents/tool.py:194) [src/cai/sdk/agents/tool.py:232](repos/aliasrobotics__cai/src/cai/sdk/agents/tool.py:232) [src/cai/sdk/agents/mcp/util.py:96](repos/aliasrobotics__cai/src/cai/sdk/agents/mcp/util.py:96) [src/cai/sdk/agents/agent.py:115](repos/aliasrobotics__cai/src/cai/sdk/agents/agent.py:115)
- **Cancellation is a request plus a cleanup obligation.** The function batch explicitly cancels and drains its tasks on the cancellation path. It attempts to retain call/output coherence for interrupted work. The model, MCP transport, thread-pool callback, API generator, and supervisor each have a distinct owner. A cancellation contract is only complete when the owner settles or explicitly reports outstanding work. [src/cai/sdk/agents/_run_impl.py:375](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:375) [src/cai/sdk/agents/_run_impl.py:856](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:856) [src/cai/sdk/agents/tool.py:270](repos/aliasrobotics__cai/src/cai/sdk/agents/tool.py:270) [src/cai/api/sessions.py:136](repos/aliasrobotics__cai/src/cai/api/sessions.py:136) [src/cai/continuous_ops/loop_runner.py:319](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:319)
- **Observability and persistence should document the same outcome.** Lifecycle spans, semantic events, and JSONL session records provide independent debugging evidence. They are useful when independently consumed. Their agreement depends on associating one event stream and one committed result with one run, and on the publisher distinguishing validated output from diagnostic data. The evidence below shows where that agreement breaks. [src/cai/sdk/agents/tracing/setup.py:148](repos/aliasrobotics__cai/src/cai/sdk/agents/tracing/setup.py:148) [src/cai/sdk/agents/stream_events.py:12](repos/aliasrobotics__cai/src/cai/sdk/agents/stream_events.py:12) [src/cai/sdk/agents/run_to_jsonl.py:319](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:319) [src/cai/api/app.py:677](repos/aliasrobotics__cai/src/cai/api/app.py:677)

## 4. What it does well and poorly, with source evidence.

### Strengths

- The shared step interpreter makes ordinary and streamed runs agree on core response classification, structured output, tool calls, and handoffs. Both accept an injected model. Repository tests exercise fake-model runs through the normal SDK entry points, including guardrail errors, lifecycle hooks, and turn limits. [src/cai/sdk/agents/run.py:889](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:889) [src/cai/sdk/agents/run.py:962](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:962) [tests/agents/test_agent_runner.py:40](repos/aliasrobotics__cai/tests/agents/test_agent_runner.py:40) [tests/agents/test_agent_runner_streamed.py:38](repos/aliasrobotics__cai/tests/agents/test_agent_runner_streamed.py:38) [tests/agents/test_max_turns.py:14](repos/aliasrobotics__cai/tests/agents/test_max_turns.py:14)
- Handoff selection, argument conversion, error handling, and the distinction between raw and semantic events have readable contracts. Structured output wraps non-object shapes for schema generation and unwraps after validation. Synchronous function tools use an executor, keeping the event loop available to asynchronous callbacks. [src/cai/sdk/agents/_run_impl.py:945](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:945) [src/cai/sdk/agents/agent_output.py:50](repos/aliasrobotics__cai/src/cai/sdk/agents/agent_output.py:50) [src/cai/sdk/agents/tool.py:256](repos/aliasrobotics__cai/src/cai/sdk/agents/tool.py:256) [src/cai/sdk/agents/tool.py:270](repos/aliasrobotics__cai/src/cai/sdk/agents/tool.py:270) [src/cai/sdk/agents/stream_events.py:12](repos/aliasrobotics__cai/src/cai/sdk/agents/stream_events.py:12)
- Session detail returns copies, parallel history has copy-on-transfer helpers, and the recorder has compatibility coverage for several log shapes. Atomic rename preserves the previous snapshot when a replacement fails before publication. The budget limiter uses monotonic time, distinguishes pre-dispatch failures from ambiguous delivery, and releases reservations on cancellation while waiting. [src/cai/api/sessions.py:79](repos/aliasrobotics__cai/src/cai/api/sessions.py:79) [src/cai/sdk/agents/parallel_isolation.py:105](repos/aliasrobotics__cai/src/cai/sdk/agents/parallel_isolation.py:105) [tests/core/test_backwards_compatibility.py:22](repos/aliasrobotics__cai/tests/core/test_backwards_compatibility.py:22) [src/cai/continuous_ops/session_snapshot.py:60](repos/aliasrobotics__cai/src/cai/continuous_ops/session_snapshot.py:60) [src/cai/util/gateway_rate_limiter.py:240](repos/aliasrobotics__cai/src/cai/util/gateway_rate_limiter.py:240) [src/cai/util/gateway_rate_limiter.py:275](repos/aliasrobotics__cai/src/cai/util/gateway_rate_limiter.py:275)
- The scheduler writes iteration data before provider recovery. The direct supervisor propagates normal nonzero exits and can kill and reap an ordinary child that exceeds its output-pump deadline. Both behaviors held in local controls. The in-memory output dispatcher isolates subscriber exceptions from later subscribers. [src/cai/continuous_ops/loop_runner.py:319](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:319) [src/cai/continuous_ops/loop_runner.py:656](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:656) [src/cai/output.py:226](repos/aliasrobotics__cai/src/cai/output.py:226)

### Confirmed gaps

| Finding | Consequence and source |
| --- | --- |
| **F1. Rejection and publication disagree.** | A non-streaming first-turn tripwire raised while its sibling was still alive. That sibling then executed an inert callback. Separately, actual token SSE dispatch returned an error and a final frame containing the rejected test output, and committed the same text to session history. The two issues arise at separate input execution and output commit boundaries. [src/cai/sdk/agents/run.py:249](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:249) [src/cai/sdk/agents/run.py:755](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:755) [src/cai/api/streaming.py:305](repos/aliasrobotics__cai/src/cai/api/streaming.py:305) [src/cai/api/app.py:773](repos/aliasrobotics__cai/src/cai/api/app.py:773) |
| **F2. API turns can be executed or committed inconsistently.** | High-level streaming did a second run after delivering its final event. With successive replies `shown` and `saved`, the client received the first while the history stored the second. Ordinary API calls compose input before acquiring the per-session lock. The controlled overlap serialized model calls but replaced the first turn's history with a stale composition. Reset and deletion can leave active work holding a reference to the session. [src/cai/api/app.py:663](repos/aliasrobotics__cai/src/cai/api/app.py:663) [src/cai/api/app.py:677](repos/aliasrobotics__cai/src/cai/api/app.py:677) [src/cai/api/sessions.py:98](repos/aliasrobotics__cai/src/cai/api/sessions.py:98) [src/cai/api/sessions.py:182](repos/aliasrobotics__cai/src/cai/api/sessions.py:182) [src/cai/api/sessions.py:258](repos/aliasrobotics__cai/src/cai/api/sessions.py:258) |
| **F3. Stream termination lacks a complete owner.** | Early producer failure and producer cancellation each left a waiting reader without a wakeup. Closing the SDK consumer after a yield left its producer active. An ordinary tool-hook exception left a sibling callback active while explicit run cancellation reached that callback. Early hook-SSE closure elicited `RuntimeError: async generator ignored GeneratorExit`. `interrupt_and_wait` can also outwait its advertised timeout when the task delays cancellation. [src/cai/sdk/agents/run.py:628](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:628) [src/cai/sdk/agents/run.py:778](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:778) [src/cai/sdk/agents/result.py:147](repos/aliasrobotics__cai/src/cai/sdk/agents/result.py:147) [src/cai/api/streaming.py:182](repos/aliasrobotics__cai/src/cai/api/streaming.py:182) [src/cai/api/streaming.py:199](repos/aliasrobotics__cai/src/cai/api/streaming.py:199) [src/cai/api/sessions.py:147](repos/aliasrobotics__cai/src/cai/api/sessions.py:147) |
| **F4. Retry and worker state can overstate what completed.** | The headless retry repeated an inert callback when a connection error came after that callback, because it restarted the whole run. The periodic process helper returned zero after the pipe closed and a separate wait timed out, while the child was still running. This zero feeds the parent's successful-completion bookkeeping. The detached path waits for publication and explicitly allows workers to outlive its wait. [src/cai/cli_headless.py:1542](repos/aliasrobotics__cai/src/cai/cli_headless.py:1542) [src/cai/continuous_ops/loop_runner.py:342](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:342) [src/cai/continuous_ops/loop_runner.py:635](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:635) [src/cai/cli_headless.py:2333](repos/aliasrobotics__cai/src/cai/cli_headless.py:2333) |
| **F5. Trace delivery and accounting can drift from the run.** | The batch thread terminated at about 30 seconds even with a functioning memory exporter. Late events stayed queued until an explicit flush. Streaming under a separate task context raised a trace reset error. The SSE workaround avoided that error by discarding its trace reference, leaving the owner's trace bound and unended in the local control. Per-response token counts were present in both run modes, but only the ordinary run accumulated those counts into the end hook's context. [src/cai/sdk/agents/tracing/processors.py:231](repos/aliasrobotics__cai/src/cai/sdk/agents/tracing/processors.py:231) [src/cai/sdk/agents/tracing/traces.py:156](repos/aliasrobotics__cai/src/cai/sdk/agents/tracing/traces.py:156) [src/cai/sdk/agents/result.py:180](repos/aliasrobotics__cai/src/cai/sdk/agents/result.py:180) [src/cai/api/streaming.py:260](repos/aliasrobotics__cai/src/cai/api/streaming.py:260) [src/cai/sdk/agents/run.py:857](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:857) [src/cai/sdk/agents/run.py:1161](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:1161) |
| **F6. Recovery and accounting rely on lossy inference about persisted data.** | Transcript heuristics dropped legitimate repeated input and chose the earlier of two equal-length request records. Usage updates from two independent processes were lost despite atomic rename. Log compression advanced the file's effective retention age. The snapshot reader handled missing and malformed JSON files but raised on valid non-object JSON and invalid UTF-8. Its production caller suppresses these exceptions, so the observed impact there is silent omission of restored history. [src/cai/sdk/agents/run_to_jsonl.py:476](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:476) [src/cai/sdk/agents/run_to_jsonl.py:539](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:539) [src/cai/sdk/agents/global_usage_tracker.py:117](repos/aliasrobotics__cai/src/cai/sdk/agents/global_usage_tracker.py:117) [src/cai/sdk/agents/global_usage_tracker.py:287](repos/aliasrobotics__cai/src/cai/sdk/agents/global_usage_tracker.py:287) [src/cai/continuous_ops/log_maintenance.py:39](repos/aliasrobotics__cai/src/cai/continuous_ops/log_maintenance.py:39) [src/cai/continuous_ops/session_snapshot.py:72](repos/aliasrobotics__cai/src/cai/continuous_ops/session_snapshot.py:72) [src/cai/continuous_ops/loop_tick_epilogue.py:65](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_tick_epilogue.py:65) |
| **F7. Extension contracts lack parity and cleanup in some branches.** | A false continuation callback stopped the hook iteration while the model ran another turn. The streamed path skipped those loop hooks. MCP initialization cancellation left entered resources in its exit stack, and a failed tool-inventory refresh marked the previous cache clean. Synchronous output delivery can skip a listener when a preceding listener removes itself. [src/cai/sdk/agents/hooks.py:78](repos/aliasrobotics__cai/src/cai/sdk/agents/hooks.py:78) [src/cai/sdk/agents/run.py:288](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:288) [src/cai/sdk/agents/run.py:628](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:628) [src/cai/sdk/agents/mcp/server.py:124](repos/aliasrobotics__cai/src/cai/sdk/agents/mcp/server.py:124) [src/cai/sdk/agents/mcp/server.py:155](repos/aliasrobotics__cai/src/cai/sdk/agents/mcp/server.py:155) [src/cai/output.py:220](repos/aliasrobotics__cai/src/cai/output.py:220) |

**Separate source-backed privacy finding.** The session-start recorder writes the configured service key field directly into JSONL. The conditionally enabled recorder also probes the network by default. The isolated writer test ran with the network check disabled and an empty environment. The unredacted assignment is explicit in source, independent of the provider, tracing, and fixture dependency versions. Session logs should carry run identifiers and redacted metadata. [src/cai/sdk/agents/run_to_jsonl.py:55](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:55) [src/cai/sdk/agents/run_to_jsonl.py:106](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:106) [src/cai/sdk/agents/run_to_jsonl.py:150](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:150)

## 5. Core-code quality: decomposition, state, concurrency, errors, types, tests, observability, extensibility, and maintainability.

| Dimension | Evaluation |
| --- | --- |
| Decomposition | `Agent`, `Model`, `RunImpl`, and the result types identify coherent responsibilities. The CLI and chat-completions modules still combine runtime decisions, session mutation, recovery, and display-oriented callbacks. Measured at 2,924 and 4,653 lines, respectively, they are expensive places to reason about state changes. The chat-completions package extracts useful units, and the old entry file still remains the live class. [src/cai/sdk/agents/agent.py:57](repos/aliasrobotics__cai/src/cai/sdk/agents/agent.py:57) [src/cai/sdk/agents/models/chatcompletions/__init__.py:8](repos/aliasrobotics__cai/src/cai/sdk/agents/models/chatcompletions/__init__.py:8) [src/cai/sdk/agents/models/openai_chatcompletions.py:124](repos/aliasrobotics__cai/src/cai/sdk/agents/models/openai_chatcompletions.py:124) [src/cai/cli_headless.py:593](repos/aliasrobotics__cai/src/cai/cli_headless.py:593) |
| State | Explicit `RunContextWrapper` and result objects make run-local state testable. The active-agent manager, model history, session history, and parallel store still mirror or alias mutable data. `Agent.clone` uses a shallow dataclass replacement, and the legacy agent selection path can return the original object when cloning is unavailable. API isolation therefore depends on the factory contract as well as the manager lock. [src/cai/sdk/agents/run_context.py:11](repos/aliasrobotics__cai/src/cai/sdk/agents/run_context.py:11) [src/cai/sdk/agents/agent.py:165](repos/aliasrobotics__cai/src/cai/sdk/agents/agent.py:165) [src/cai/agents/__init__.py:291](repos/aliasrobotics__cai/src/cai/agents/__init__.py:291) [src/cai/agents/__init__.py:301](repos/aliasrobotics__cai/src/cai/agents/__init__.py:301) [src/cai/agents/__init__.py:361](repos/aliasrobotics__cai/src/cai/agents/__init__.py:361) [src/cai/api/sessions.py:229](repos/aliasrobotics__cai/src/cai/api/sessions.py:229) |
| Concurrency | SDK calls use task-local trace and model references in important places. The logical CLI changes process-level stream flags for a group of coroutines and restores them in `finally`. The per-session lock covers ordinary invocation, while streaming and session management use separate paths. Calls sharing an agent or model can share mutable settings, context, and tool objects. An executor gives synchronous callbacks event-loop isolation, with their thread lifetime governed by the callback after it starts. [src/cai/sdk/agents/tracing/scope.py:11](repos/aliasrobotics__cai/src/cai/sdk/agents/tracing/scope.py:11) [src/cai/sdk/agents/models/chatcompletions/model.py:171](repos/aliasrobotics__cai/src/cai/sdk/agents/models/chatcompletions/model.py:171) [src/cai/cli_headless.py:1851](repos/aliasrobotics__cai/src/cai/cli_headless.py:1851) [src/cai/cli_headless.py:1880](repos/aliasrobotics__cai/src/cai/cli_headless.py:1880) [src/cai/sdk/agents/run.py:1186](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:1186) [src/cai/sdk/agents/tool.py:270](repos/aliasrobotics__cai/src/cai/sdk/agents/tool.py:270) |
| Errors | Typed exceptions distinguish bad model behavior, turn limits, and guardrail tripwires. Some boundaries intentionally translate expected failures into transcript output. Elsewhere broad catches silence failed commits, cleanup, and accounting. Error handling changes by entry point. With an ASGI payload of zero turns, ordinary inference rejected before invoking its fake model, while token SSE fell back to the default and completed. [src/cai/sdk/agents/exceptions.py:7](repos/aliasrobotics__cai/src/cai/sdk/agents/exceptions.py:7) [src/cai/sdk/agents/tool.py:296](repos/aliasrobotics__cai/src/cai/sdk/agents/tool.py:296) [src/cai/api/sessions.py:118](repos/aliasrobotics__cai/src/cai/api/sessions.py:118) [src/cai/api/app.py:575](repos/aliasrobotics__cai/src/cai/api/app.py:575) [src/cai/api/app.py:761](repos/aliasrobotics__cai/src/cai/api/app.py:761) [src/cai/api/schemas.py:67](repos/aliasrobotics__cai/src/cai/api/schemas.py:67) |
| Types | The response-item types and strict schemas make dynamically produced instructions easier to validate. A provider-facing Pydantic transport schema also shapes internal types, so dependency drift affects unit fixtures. Flexibility at snapshot, JSONL, and external-worker file boundaries depends on runtime shape checks. The code parses and compiles across the 137 inspected non-UI runtime files with the checked grammar modes. [src/cai/sdk/agents/items.py:58](repos/aliasrobotics__cai/src/cai/sdk/agents/items.py:58) [src/cai/sdk/agents/agent_output.py:40](repos/aliasrobotics__cai/src/cai/sdk/agents/agent_output.py:40) [src/cai/sdk/agents/models/interface.py:37](repos/aliasrobotics__cai/src/cai/sdk/agents/models/interface.py:37) [src/cai/continuous_ops/session_snapshot.py:72](repos/aliasrobotics__cai/src/cai/continuous_ops/session_snapshot.py:72) |
| Tests | Fake-model tests exercise SDK run and handoff behavior without invoking providers. Global fixtures replace trace processors and normally disable real OpenAI model methods. The default conftest also imports the adapter graph during collection, coupling small utility tests to production dependencies. The checked-in CI's lint and type-check jobs are commented out, and its active runs emphasize project smoke tests and docs. Local positive tests provide SDK behavior evidence, with weaker cross-entry-point and long-lived service coverage. [tests/conftest.py:7](repos/aliasrobotics__cai/tests/conftest.py:7) [tests/conftest.py:31](repos/aliasrobotics__cai/tests/conftest.py:31) [tests/conftest.py:60](repos/aliasrobotics__cai/tests/conftest.py:60) [.github/workflows/tests.yml:16](repos/aliasrobotics__cai/.github/workflows/tests.yml:16) [.github/workflows/tests.yml:45](repos/aliasrobotics__cai/.github/workflows/tests.yml:45) |
| Observability | Spans carry parent relationships, typed events make progress visible, and file logging gives operator evidence independent of the model client. The trace thread has a finite lifetime, the output bus silently drops handler exceptions, and usage accounting spans several stores. The in-memory activity registry bounds record count and keeps payloads for inspection. Run duration measurements are mixed between monotonic and wall time. [src/cai/sdk/agents/tracing/processors.py:173](repos/aliasrobotics__cai/src/cai/sdk/agents/tracing/processors.py:173) [src/cai/output.py:226](repos/aliasrobotics__cai/src/cai/output.py:226) [src/cai/output.py:413](repos/aliasrobotics__cai/src/cai/output.py:413) [src/cai/util/timing.py:19](repos/aliasrobotics__cai/src/cai/util/timing.py:19) [src/cai/util/gateway_rate_limiter.py:248](repos/aliasrobotics__cai/src/cai/util/gateway_rate_limiter.py:248) |
| Extensibility and maintainability | Agent factories, hooks, model providers, tool schemas, and trace processors offer several useful seams. The loop-hook continuation mismatch and repeated class methods show that extensions need executable contract tests. An AST inventory found four undecorated duplicate definitions in the scanned packages. Python binds the last SSE `cleanup` definition and the later three terminal-count definitions. Much of the remaining complexity is in compatibility paths and ownership transitions. [src/cai/agents/factory.py:18](repos/aliasrobotics__cai/src/cai/agents/factory.py:18) [src/cai/sdk/agents/lifecycle.py:8](repos/aliasrobotics__cai/src/cai/sdk/agents/lifecycle.py:8) [src/cai/sdk/agents/hooks.py:51](repos/aliasrobotics__cai/src/cai/sdk/agents/hooks.py:51) [src/cai/sdk/agents/mcp/server.py:394](repos/aliasrobotics__cai/src/cai/sdk/agents/mcp/server.py:394) [src/cai/sdk/agents/mcp/server.py:423](repos/aliasrobotics__cai/src/cai/sdk/agents/mcp/server.py:423) [src/cai/sdk/agents/simple_agent_manager.py:849](repos/aliasrobotics__cai/src/cai/sdk/agents/simple_agent_manager.py:849) [src/cai/sdk/agents/simple_agent_manager.py:865](repos/aliasrobotics__cai/src/cai/sdk/agents/simple_agent_manager.py:865) |

## 6. Executed tests/experiments and their limitations.

The clean-room test run used CPython 3.12.16. The directly loadable repository suites use pytest 9.1.1 and pytest-asyncio 1.5.0. The SDK suites used the actual runner, result, schema, guards, hooks, and fake models from the checkout. One unavailable chat transport was replaced with a module that raises if called. An import-only utility namespace exposed the real required leaf modules without evaluating the legacy re-export module. The related test fixture still blocked real model methods where it applied. A converter test group linked the real extracted converter to its compatibility name on the unavailable transport module. See the setup and commands in §9. [tests/conftest.py:7](repos/aliasrobotics__cai/tests/conftest.py:7) [tests/conftest.py:60](repos/aliasrobotics__cai/tests/conftest.py:60) [tests/fake_model.py:23](repos/aliasrobotics__cai/tests/fake_model.py:23) [src/cai/sdk/agents/models/openai_chatcompletions.py:4645](repos/aliasrobotics__cai/src/cai/sdk/agents/models/openai_chatcompletions.py:4645)

| Test group | Result | Local evidence covered |
| --- | ---: | --- |
| Direct utility tests for configuration, log retention, and tick context | 8 passed | Existing parser behavior, temporary gzip/delete operations, and context round-trip |
| Leaf utilities, worker context isolation, and recorder logging | 13 passed | Per-task context scoping, compacted state helpers, and JSONL logger formatting |
| SDK contracts | 41 passed | Guardrails, result types, models/settings precedence, item conversion, and strict schema |
| CLI history formats | 11 passed | Generated and checked-in JSONL shapes with legacy and fast readers |
| SDK runner parity on ordinary paths | 60 passed | Run and stream behavior, lifecycle hooks, handoffs, tool-selected output, and maximum turns |
| SDK step dispatch, handoff, and converter | 43 passed | Response classification, inert calls, error outputs, and legacy converter import binding |
| Quota and boundary utilities | 46 passed | Local pacing with fake timing, reservation cancellation, base URL parsing, and wall-limit policy arithmetic |
| SDK function schemas and decorators | 38 passed | Docstring metadata, type conversion, schema validation, and inert callback dispatch |
| MCP error fixtures | 2 passed | Initialization exception cleanup and required connection state before operations |
| **Total** | **262 passed** | Distinct repository test cases in the completed groups |

I also compiled 137 selected runtime Python files in memory with Python 3.12 and parsed those files using its Python 3.10 grammar mode. Both checks had zero failures. Grammar parsing checks syntax only. Version-specific imports, native dependencies, and production integrations still require a real pinned environment.

| Isolated control | Observed result |
| --- | --- |
| First-turn validation and continuation | A rejected input returned control to the caller before the sibling finished. Releasing the sibling's fixture gate then triggered its inert callback. A loop hook that returned false ran twice in ordinary mode, and the stream consumed the same two responses with zero loop-hook observations. |
| Session lock and cancellation | Serial stateful calls presented user inputs `[A]`, then `[A,B]`. The overlap presented `[A]`, then `[B]` and retained only `B`. Stateless overlap also presented two independent prompts. Reset and delete removed the current session state even though an old reference could still finish and write history. A task that observed both cancellation signals remained pending beyond the requested wait limit under CPython 3.10.22 and 3.12.16. |
| Stream event termination | Early tool-discovery failure left the consumer waiting with an empty queue. An error inside the turn reached the consumer. Cancelling the producer left a pending consumer and `is_complete=False`. Closing a consumer after its initial event left the producer active. Releasing it yielded a completed result and three remaining queued events. In a separate two-callback control, explicit run cancellation reached the waiting callback. An ordinary exception from the other tool's hook returned the run error while the callback still waited. |
| Actual ASGI streaming | High-level SSE returned HTTP 200 with `shown`. The history contained `saved`. The same observation appeared when consuming the exact generator without ASGI. Token SSE with an output tripwire emitted both error and final. The finalized text entered history. A zero turn budget produced a pre-model error in ordinary inference and selected the default in token SSE. |
| SSE translation and trace capture | Hook generator closure first raised the asynchronous-generator closure error. A raw text boundary followed by the semantic message produced two message steps, versus one with raw events alone. Same-context SDK consumption ended its trace. A separate consuming task raised `ValueError`. The SSE adapter completed while the originating trace stayed attached and unended. |
| Usage and background tracing | The fake response reported six tokens in both run modes. The end hook saw six ordinary tokens and zero streamed tokens. With a memory exporter, the worker accepted and exported an initial trace, exited at 30.011 monotonic seconds with shutdown unset (30.012 seconds on rerun), and queued a later trace until manual flush. |
| Headless retry and generic worker supervision | An error before an inert effect yielded one callback, and the same error after it yielded two. The real child supervisor yielded status 9 for a normal nonzero exit and 124 for a held pipe past its deadline. When the child closed both output descriptors while continuing, the supervisor returned 0 after 5.006 seconds with its captured child handle still pending. The fixture then terminated and reaped that child. In the detached-worker entry-point fixture, ordinary success, cancellation, and execution error each published a distinct JSON status with process status 0. Injected serialization failure returned 2 and left incomplete JSON. |
| History, snapshot, and retention | Both the standard JSON and the locally available orjson paths lost part of a legitimate repeated conversation. Fast selection retained the earlier same-length request. Both readers raised on a completion record with empty choices. A snapshot round-trip restored 40 of 45 fixture messages with bounded string content. An independent writer and reader process recovered a one-message fixture. Injected rename denial preserved the previous file. Valid non-object JSON and invalid UTF-8 raised at the reader boundary. A 17-day-old log survived after compression advanced its mtime by 10 days. Restoring the original mtime made it expire. |
| History ownership transfer | Two nested draft histories remained independent. A defensive getter returned a copy. Explicit selection and longest-history selection each matched the store contract. After choosing a history, the prior slots remained present until cleared. Snapshot application updated the existing canonical list in place, and an empty export kept the prior checkpoint. |
| MCP, output bus, and persisted accounting | Normal MCP fixture error closed both entered contexts. Cancellation during initialization left both registered until explicit cleanup. A failed inventory refresh left the old list cached until further invalidation. A normal or raising output subscriber allowed the next delivery. A self-removing subscriber skipped it. Two independently incremented usage snapshots produced one persisted request, while serial updates produced two. |

The pinned dependency set was unavailable in the inspected local stores. The substitute packages included OpenAI 3.55.1, Pydantic 2.14.3, and griffelib 2.4.1, versus lock entries 2.8.1, 2.11.1, and griffe 1.7.2. The MCP control used 1.30.0 instead of the locked 1.23.0. The in-process API used FastAPI 0.165.0 and Starlette 1.10.0, with fixture-only command and account adapters. The API observations used the checkout's actual session, route, runner, and event implementations. The repository API fixture sets a header key, so I used the credential-free in-process control for this path. These results characterize code behavior through the exercised seams. Provider routing, live MCP transports, platform service behavior, and package installation remain source-only for this review. [uv.lock:2679](repos/aliasrobotics__cai/uv.lock:2679) [uv.lock:3233](repos/aliasrobotics__cai/uv.lock:3233) [uv.lock:1406](repos/aliasrobotics__cai/uv.lock:1406) [uv.lock:2230](repos/aliasrobotics__cai/uv.lock:2230) [uv.lock:1080](repos/aliasrobotics__cai/uv.lock:1080) [uv.lock:4212](repos/aliasrobotics__cai/uv.lock:4212) [pyproject.toml:9](repos/aliasrobotics__cai/pyproject.toml:9) [tests/api/test_api.py:34](repos/aliasrobotics__cai/tests/api/test_api.py:34)

## 7. Measurement audit for every negative or surprising result, including alternate commands or code-path checks used to rule out setup mistakes.

**Isolation and dependencies.** The first temporary archive failed with `Disk quota exceeded` even though `df` reported free space on the host tmpfs. The partial artifact occupied 3.3 MiB and was removed. Read-only bind mounts removed the copy requirement. `statvfs` confirmed read-only flags on the three individual source, tests, and configuration mounts. The private directory accepted test writes, the process saw only loopback, the real home and service sockets were absent, and socket connection stubs protected the higher-level fixture lanes. Background tools did real work only for their controls. The elapsed window includes no waiting for a clock target.

The initial stock SDK collection exited 4 on missing `openai`. The inspected native system Python had still fewer dependencies. Local metadata showed that available OpenAI 3.x wheels require `httpx2` and `sniffio`. Mounting those exposed the next missing packages. The Griffe import was present under the cache distribution name `griffelib`. Collection then exited 4 on unavailable `litellm`. The utility import also required unavailable or unmounted presentation dependencies, initially Mako. The reduced fixture packs used actual repository leaf code with explicit excluded transport behavior. Initial synchronous-only selection had two pytest configuration warnings because the async plugin was absent. Explicit local plugin loading removed those warnings and expanded the direct repository lane. The MCP import initially failed on its dependencies, including a CPython 3.13 binary in one local environment. Checking `WHEEL` tags and selecting a CPython 3.12 `rpds` artifact resolved the import. None of these collection failures count against the runtime.

The first run-step group passed 38 tests and failed to set up five converter tests because the shim omitted the compatibility alias. Reproducing the real import relationship at the leaf module yielded 43 passes. The stored usage fixture initially failed validation on the alternate OpenAI package's required cache-write field. Defining only the fields that the active type required produced the six-token result. A required-field inventory confirmed the optional nested field that made an early fixture amendment invalid. The trace and usage findings concern the behavior after the valid fixture entered the runner. [src/cai/sdk/agents/models/openai_chatcompletions.py:4645](repos/aliasrobotics__cai/src/cai/sdk/agents/models/openai_chatcompletions.py:4645) [src/cai/sdk/agents/run.py:857](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:857)

| Observation | Alternate explanation tested and conclusion |
| --- | --- |
| F1 input guardrail and F1 output publication | Used gates to order model entry, rejection, and release, so the callback after rejection was caused by the surviving sibling task. For the output path, ran the same inert message with allow and reject guardrails in each serializer, then drove the token route through actual ASGI. Only the rejected case produced an error, and both still produced a final. The ASGI session held the rejected message even after the iterator drained. The direct SDK error tests passed, so the publication discrepancy is a caller boundary issue. In the budget-control request, zero reached the ordinary runner and left its response unconsumed. The token path consumed the fixture response because the route uses a truth-value fallback. [src/cai/sdk/agents/run.py:249](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:249) [src/cai/sdk/agents/run.py:755](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:755) [src/cai/api/streaming.py:115](repos/aliasrobotics__cai/src/cai/api/streaming.py:115) [src/cai/api/app.py:773](repos/aliasrobotics__cai/src/cai/api/app.py:773) |
| F2 stale session history and duplicate stream inference | The stateful serial and stateless controls distinguished pre-lock composition from missing locking and from intentional statelessness. Events confirmed only one fake model call was inside the lock before release. An exact nested handler body consumed two predetermined replies. Actual ASGI reproduced the same visible/stored difference with the normal handler, ruling out AST extraction and HTTP buffering as explanations. Post-deletion work continued only in the previously held session object, and the manager lookup failed as expected. [src/cai/api/sessions.py:98](repos/aliasrobotics__cai/src/cai/api/sessions.py:98) [src/cai/api/sessions.py:251](repos/aliasrobotics__cai/src/cai/api/sessions.py:251) [src/cai/api/app.py:677](repos/aliasrobotics__cai/src/cai/api/app.py:677) |
| F3 reader wakeup, close, and cancellation | Reader and producer gates established that the reader was awaiting an empty queue before failure or cancellation. Failure inside the normal turn woke the reader with the original exception, separating liveness from a bad event fixture. Closing the external consumer while the producer fixture still waited left the producer active, and releasing it completed the work. The hook generator's first close raised before a final frame. Trying to close it repeatedly surfaced a fixture cleanup issue, so I drained its remaining final frame in a controlled path and observed the generator close. For the session wait I observed a second delivered cancellation, then confirmed the wait still needed the task's explicit release. The same original method body showed this behavior on Python 3.10.22 and 3.12.16. This effect follows Python's cooperative cancellation and the method's unbounded drain path. In the tool batch, the same second callback was observed under normal return, explicit cancellation, and an ordinary first-callback hook failure. Only the ordinary error left it active after the run reported a terminal error. [src/cai/sdk/agents/_run_impl.py:727](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:727) [src/cai/sdk/agents/_run_impl.py:844](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:844) [src/cai/sdk/agents/run.py:628](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:628) [src/cai/sdk/agents/run.py:778](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:778) [src/cai/sdk/agents/result.py:147](repos/aliasrobotics__cai/src/cai/sdk/agents/result.py:147) [src/cai/api/streaming.py:199](repos/aliasrobotics__cai/src/cai/api/streaming.py:199) [src/cai/api/sessions.py:147](repos/aliasrobotics__cai/src/cai/api/sessions.py:147) |
| F4 retry and supervisor status | Replayed the identical model error before and after a pure callback with the actual `Runner.run` and the original headless wrapper body. The backoff function recorded its requested delay without sleeping. The callback count changed only when the failed attempt already ran it. For child status, the normal nonzero, pipe-held timeout, and early EOF variants used the same mounted Python and writable log directory. A captured real process handle proved that the last child was still alive at apparent success. Both process creation and logging had worked in the controls. The detached worker main-body control differentiated error, cancelled, and incomplete-file publication. Its parent retries paths that exist but fail JSON decoding. The code creates its result directory with a standalone temporary-directory call and has no removal reference in the external-worker function. Terminal launch and service integration remain source-only. [src/cai/parallel_worker.py:111](repos/aliasrobotics__cai/src/cai/parallel_worker.py:111) [src/cai/cli_headless.py:2123](repos/aliasrobotics__cai/src/cai/cli_headless.py:2123) [src/cai/cli_headless.py:2208](repos/aliasrobotics__cai/src/cai/cli_headless.py:2208) [src/cai/cli_headless.py:1542](repos/aliasrobotics__cai/src/cai/cli_headless.py:1542) [src/cai/continuous_ops/loop_runner.py:288](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:288) [src/cai/continuous_ops/loop_runner.py:342](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:342) |
| F5 trace lifetime, context and usage | Used local callbacks as the exporter and compared early automatic delivery with late forced delivery. A monotonic timer, thread liveness, and the unset shutdown event distinguish the configured thread lifetime from HTTP auth, cadence, or exporter failure. Same-task consumption, separate-task consumption, and SSE consumption shared an in-memory trace processor. A fixture-owned finish reset the context afterward. For usage, both raw responses independently held the same six-token total and only the context accumulator differed. [src/cai/sdk/agents/tracing/processors.py:225](repos/aliasrobotics__cai/src/cai/sdk/agents/tracing/processors.py:225) [src/cai/sdk/agents/tracing/processors.py:231](repos/aliasrobotics__cai/src/cai/sdk/agents/tracing/processors.py:231) [src/cai/sdk/agents/tracing/scope.py:38](repos/aliasrobotics__cai/src/cai/sdk/agents/tracing/scope.py:38) [src/cai/sdk/agents/run.py:857](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:857) [src/cai/sdk/agents/run.py:1161](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:1161) |
| F6 persistence and retained age | Replayed distinct conversations, correctly formatted repeated requests, equal-length requests, and malformed completion variants. Flipped the fast flag and repeated with orjson 3.13.0, so whitespace and the JSON backend cannot explain the lost entries. For logs, decompressed content was identical, and an explicit timestamp reset caused expected expiry on the same path. For snapshots, a round-trip and an injected rename denial controlled for permissions and last-good preservation. Reader exceptions followed shape and encoding. The higher epilogue catches them. An independent writer and reader also confirmed that valid snapshots survive process boundaries. For accounting, process barriers froze both real `track_usage` calls after reading and incrementing but before saving. The serial control on a separate fresh file retained both. Writes completed with no permission errors. [src/cai/sdk/agents/run_to_jsonl.py:444](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:444) [src/cai/sdk/agents/run_to_jsonl.py:523](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:523) [src/cai/continuous_ops/log_maintenance.py:39](repos/aliasrobotics__cai/src/cai/continuous_ops/log_maintenance.py:39) [src/cai/continuous_ops/session_snapshot.py:60](repos/aliasrobotics__cai/src/cai/continuous_ops/session_snapshot.py:60) [src/cai/continuous_ops/loop_tick_epilogue.py:73](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_tick_epilogue.py:73) [src/cai/sdk/agents/global_usage_tracker.py:287](repos/aliasrobotics__cai/src/cai/sdk/agents/global_usage_tracker.py:287) |
| F7 callbacks, MCP, and output subscribers | Used the documented false return and recorded callback order over two separate normal turns. Searching all references shows the streamed loop lacks a corresponding global loop-hook call. MCP success, ordinary exception, and cancellation entered the same local context managers. Only cancellation failed to unwind them automatically. Inventory first fetched successfully, cached normally, failed refresh, and fetched normally after explicit invalidation. For the output bus, two sinks both received the normal and throwing-first events, while mutation of the live subscriber list affected iteration. [src/cai/sdk/agents/hooks.py:78](repos/aliasrobotics__cai/src/cai/sdk/agents/hooks.py:78) [src/cai/sdk/agents/run.py:288](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:288) [src/cai/sdk/agents/mcp/server.py:124](repos/aliasrobotics__cai/src/cai/sdk/agents/mcp/server.py:124) [src/cai/sdk/agents/mcp/server.py:155](repos/aliasrobotics__cai/src/cai/sdk/agents/mcp/server.py:155) [src/cai/output.py:220](repos/aliasrobotics__cai/src/cai/output.py:220) |
| Source-only privacy, launch, and maintenance findings | The recorder's serializer field comes directly from an environment lookup and has an independent recording enable check. Its actual local repo test wrote JSONL with an empty private environment. No key value was used to establish behavior. I checked the no-terminal fallback and the explicit detached timeout notice before attributing worker ownership to the external launcher. The generated service's unconditional restart and the in-process stop check are separate source contracts. AST duplicate detection excluded decorated overloads and confirmed the four relevant lexical definitions. [src/cai/sdk/agents/run_to_jsonl.py:55](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:55) [src/cai/sdk/agents/run_to_jsonl.py:150](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:150) [src/cai/cli_headless.py:2065](repos/aliasrobotics__cai/src/cai/cli_headless.py:2065) [src/cai/cli_headless.py:2333](repos/aliasrobotics__cai/src/cai/cli_headless.py:2333) [src/cai/continuous_ops/systemd_unit.py:65](repos/aliasrobotics__cai/src/cai/continuous_ops/systemd_unit.py:65) [src/cai/sdk/agents/mcp/server.py:423](repos/aliasrobotics__cai/src/cai/sdk/agents/mcp/server.py:423) |

## 8. Post-mortem: design pressures, accumulated tradeoffs, likely failure modes, and the highest-leverage improvements.

CAI brings a reusable agent SDK into a process-oriented CLI with model-specific memory and a continuous parent/child loop, then exposes a session API over both streamed and non-streamed execution. The SDK's typed step interpreter held up across the tested paths. The adapter code retains multiple ways to compose input, finish a trace, commit history, and represent success. The migration comments, compatibility exports, model-history aliases, and independent normal and stream loops indicate incremental layering. That history is an inference from source. The runtime failures consistently follow from more than one component assuming it owns the same transition. [src/cai/sdk/agents/models/chatcompletions/__init__.py:1](repos/aliasrobotics__cai/src/cai/sdk/agents/models/chatcompletions/__init__.py:1) [src/cai/sdk/agents/run.py:188](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:188) [src/cai/sdk/agents/run.py:610](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:610) [src/cai/api/app.py:663](repos/aliasrobotics__cai/src/cai/api/app.py:663) [src/cai/output.py:1](repos/aliasrobotics__cai/src/cai/output.py:1)

The API's history reconstruction is a direct example. A complete result already exists inside the hook generator. Rebuilding its history via a second invocation treats model execution as a pure transformation, even though a run can have effects and produce a different answer. The ordinary session lock serializes execution but leaves a read outside the transaction. Streaming owns a producer in the runner, an iterator in the adapter, and a task reference in the session. On several terminal paths none of the owners publishes a guaranteed terminal signal or settles the other side. Async trace scope has a similar split. That accounts for incompatible lifecycle behavior despite good fake-model happy-path coverage. [src/cai/api/streaming.py:173](repos/aliasrobotics__cai/src/cai/api/streaming.py:173) [src/cai/api/streaming.py:199](repos/aliasrobotics__cai/src/cai/api/streaming.py:199) [src/cai/api/app.py:677](repos/aliasrobotics__cai/src/cai/api/app.py:677) [src/cai/api/sessions.py:98](repos/aliasrobotics__cai/src/cai/api/sessions.py:98) [src/cai/sdk/agents/run.py:516](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:516) [src/cai/sdk/agents/result.py:147](repos/aliasrobotics__cai/src/cai/sdk/agents/result.py:147)

Local file persistence fits a small, single-operator runtime and makes failures inspectable. It becomes fragile when file contents are inferred from transcript equality, when a file timestamp doubles as retention state, or when independent process counters merge by comparing totals. Atomic rename provides a coherent single-file view. It supplies neither a transactional read/update cycle across processes nor an operation completion record. The continuous parent adds a checkpoint after successful child status, so an inaccurate process result can become an inaccurate restart record. The systemd restart directive and process-local counters explain why service restart and durable execution have independent semantics. [src/cai/sdk/agents/run_to_jsonl.py:523](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:523) [src/cai/sdk/agents/global_usage_tracker.py:125](repos/aliasrobotics__cai/src/cai/sdk/agents/global_usage_tracker.py:125) [src/cai/continuous_ops/loop_runner.py:619](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:619) [src/cai/continuous_ops/loop_runner.py:635](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:635) [src/cai/continuous_ops/systemd_unit.py:65](repos/aliasrobotics__cai/src/cai/continuous_ops/systemd_unit.py:65)

The highest-leverage changes are ownership and policy changes at narrow interfaces. A committed session turn should have a single result, a single terminal event, and one owner for all work started on its behalf. Rejection should prevent effects and publication. Failed or uncertain work needs a durable, explicit state if callers may retry. The local test seams already make it practical to enforce these invariants across the Python runner, the API, and inert worker fixtures. Provider and UI refactoring can then proceed against stable behavioral contracts.

## 9. Evidence appendix with local file/line references and commands.

### Revision and isolation checks

Run the shell commands from the workspace using Bash. The example uses local package cache artifacts from this machine. The fixture identifies their distribution versions in §6. The checkout is mounted read-only and test writes go to the private temporary mount. There is no server binding in the ASGI lane.

~~~bash
GIT_OPTIONAL_LOCKS=0 git -C repos/aliasrobotics__cai rev-parse HEAD
GIT_OPTIONAL_LOCKS=0 git -C repos/aliasrobotics__cai status --porcelain=v1 --untracked-files=all --ignore-submodules=none
GIT_OPTIONAL_LOCKS=0 git -C repos/aliasrobotics__cai diff --no-ext-diff --exit-code HEAD --
date -u +%FT%TZ
~~~

The first command printed `6dc79257777f5f1c9500b4d2319935d34a47412e`. Status and diff produced zero output and succeeded. Entry and final-check timestamps appear in §1. The return codes and all positive and negative outcomes below refer to this checkout.

### Test shell

~~~bash
review_repo=repos/aliasrobotics__cai
review_local=$HOME/.local/share
review_cache=$HOME/.cache/uv/archive-v0

review_box() {
    local -a review_args=(
        --unshare-all --die-with-parent --clearenv
        --ro-bind /usr /usr --symlink usr/bin /bin
        --symlink usr/lib /lib --symlink usr/lib /lib64
        --proc /proc --dev /dev --tmpfs /tmp --dir /tmp/home --dir /etc
        --ro-bind "$review_local/mise/installs/python/3.12.16" /opt/python
        --ro-bind "$review_local/uv/tools/pytest/lib/python3.13/site-packages" /opt/pytest
        --ro-bind "$review_local/uv/tools/perplexity-web-mcp-cli/lib/python3.13/site-packages" /opt/mcpdeps
        --ro-bind "$review_repo/src" /repo/src --ro-bind "$review_repo/tests" /repo/tests
        --ro-bind "$review_repo/pyproject.toml" /repo/pyproject.toml
        --chdir /repo --setenv HOME /tmp/home --setenv LC_ALL C.UTF-8
        --setenv PATH /opt/python/bin:/usr/bin --setenv PYTHONDONTWRITEBYTECODE 1
        --setenv PYTEST_DISABLE_PLUGIN_AUTOLOAD 1
    )
    local -a review_wheels=(
        openai=U7p_SMhdnYaldDp5 distro=FrzZMFmVmL6oNsTs jiter=FCkw06vV_FL0ILG6
        asyncio=TktGhOHPwhCuLeXS pytz=1DYOnvcAO0jDpvKK mcp=ORxJrMFgcNw9A9A9
        httpx2=HWe7c622w7I2Xsl3 sniffio=ROk22Le6VojLBy9Z dotenv=yIDehK2f_kN1tToN
        httpsse=8-9QZO_wVASn6Cdi griffe=gZTM6bpFPULucx9H httpcore2=EZReHjoPaF8P8OGv
        rpds=3Ubzix5UpNnnFk4_ fastapi=LKrM3UoUJ8IRqjjK starlette=IPaI8qtBq_nlQ0ef
    )
    local review_pair review_name review_python_path=/repo/src:/repo:/opt/pytest
    if [[ ${REVIEW_ORJSON:-0} == 1 ]]; then
        review_wheels+=(orjson=gaySWY3_yLgJhS9v)
    fi
    for review_pair in "${review_wheels[@]}"; do
        review_name=${review_pair%%=*}
        review_args+=(--ro-bind "$review_cache/${review_pair#*=}" "/opt/dep/$review_name")
        review_python_path="$review_python_path:/opt/dep/$review_name"
    done
    bwrap "${review_args[@]}" --setenv PYTHONPATH "$review_python_path" -- "$@"
}

review_sdk_prologue=$(cat <<'PY'
import os, socket, sys, types
os.environ["CAI_TRACING"]="false"
os.environ["CAI_SKIP_NETWORK_CHECK"]="true"
os.environ["CAI_DISABLE_SESSION_RECORDING"]="true"
def no_network(*_a, **_kw):
    raise AssertionError("network is forbidden")
socket.create_connection=no_network
socket.socket.connect=no_network
socket.socket.connect_ex=no_network
name="cai.sdk.agents.models.openai_chatcompletions"
transport=types.ModuleType(name)
class OpenAIChatCompletionsModel:
    def __init__(self, *_a, **_kw):
        raise AssertionError("ChatCompletions transport unavailable in this fixture")
    async def get_response(self, *_a, **_kw):
        raise AssertionError("unexpected real model call")
    async def stream_response(self, *_a, **_kw):
        raise AssertionError("unexpected real model stream")
transport.OpenAIChatCompletionsModel=OpenAIChatCompletionsModel
sys.modules[name]=transport
import cai
def pkg(name,path):
    package=types.ModuleType(name)
    package.__package__=name
    package.__path__=[path]
    sys.modules[name]=package
    parent, child=name.rsplit(".",1)
    setattr(sys.modules[parent],child,package)
    return package

util=pkg("cai.util","/repo/src/cai/util")
from cai.util import timing
util.get_active_time=timing.get_active_time
util.get_idle_time=timing.get_idle_time
PY
)
review_sdk() {
    { printf '%s\n' "$review_sdk_prologue"; cat; } | review_box python -B - "$@"
}
review_suite() {
    review_sdk "$@" <<'PY'
import pytest
if "tests/mcp/test_server_errors.py" in sys.argv:
    sys.path.append("/opt/mcpdeps")
if "tests/tools/test_malformed_tool_call.py" in sys.argv:
    import cai.sdk.agents.models
    pkg("cai.sdk.agents.models.chatcompletions", "/repo/src/cai/sdk/agents/models/chatcompletions")
    from cai.sdk.agents.models.chatcompletions.message_builder import Converter
    transport._Converter = Converter
raise SystemExit(pytest.main(["-q", "-p", "no:cacheprovider", "-p", "pytest_asyncio.plugin", *sys.argv[1:]]))
PY
}

review_api_prologue=$(cat <<'PY'
from types import SimpleNamespace as NS
from cai.util.config_utils import update_agent_models_recursively
util.update_agent_models_recursively=update_agent_models_recursively
pkg("cai.api","/repo/src/cai/api")
fixture_agents=pkg("cai.agents","/repo/src/cai/agents")
def no_builtin_agent(*_a,**_kw):
    raise AssertionError("fixture always passes an explicit agent factory")
fixture_agents.get_agent_by_name=no_builtin_agent
PY
)
review_api() {
    { printf '%s\n' "$review_api_prologue"; cat; } | review_sdk "$@"
}

review_box python -B - <<'PY'
import os
import socket
from pathlib import Path
for p in ("/repo/src", "/repo/tests", "/repo/pyproject.toml"):
    assert os.statvfs(p).f_flag & os.ST_RDONLY
assert [name for _, name in socket.if_nameindex()] == ["lo"]
assert not Path("/run").exists() and not Path("/repo/.git").exists()
print("three readonly mounts, loopback only")
PY
~~~

### Repository tests and source checks

After assembling the report, I parsed its Markdown, compared its first nine section headings with the protocol, verified local file and line targets, checked the fenced Bash with `bash -n`, and parsed the Python heredocs. The repository test commands were then rerun from the saved report and produced the same 262 passes and 137 successful runtime-file syntax checks.

The nine commands run in separate Python processes to bound fixture state. The shim delegates converter behavior to the real leaf implementation. The history and other leaf commands omit the root conftest because they do not use its model and trace fixtures. [tests/conftest.py:7](repos/aliasrobotics__cai/tests/conftest.py:7) [tests/conftest.py:31](repos/aliasrobotics__cai/tests/conftest.py:31) [src/cai/sdk/agents/models/openai_chatcompletions.py:4645](repos/aliasrobotics__cai/src/cai/sdk/agents/models/openai_chatcompletions.py:4645)

~~~bash
review_box python -B -m pytest -q -p no:cacheprovider -p pytest_asyncio.plugin --noconftest \
    tests/test_config_loader_agents.py tests/continuous_ops/test_log_maintenance.py \
    tests/continuous_ops/test_tick_context.py

review_suite --noconftest tests/util/test_worker_silence.py tests/util/test_session_compact.py \
    tests/sdk/test_datarecorder_logger_compat.py

review_suite tests/others/test_strict_schema.py tests/others/test_result_cast.py \
    tests/agents/test_guardrails.py tests/agents/test_items_helpers.py tests/core/test_run_config.py

review_suite --noconftest tests/core/test_backwards_compatibility.py

review_suite tests/agents/test_agent_runner.py tests/agents/test_agent_runner_streamed.py \
    tests/agents/test_max_turns.py tests/agents/test_global_hooks.py tests/agents/test_agent_hooks.py \
    tests/tools/test_tool_use_behavior.py tests/tools/test_tool_choice_reset.py

review_suite tests/core/test_run_step_processing.py tests/core/test_run_step_execution.py \
    tests/tools/test_handoff_tool.py tests/tools/test_malformed_tool_call.py

review_suite --noconftest tests/util/test_gateway_rate_limiter.py tests/core/test_llm_api_base.py \
    tests/continuous_ops/test_loop_runner_timeout.py

review_suite tests/others/test_function_schema.py tests/others/test_doc_parsing.py \
    tests/tools/test_function_tool_decorator.py tests/tools/test_function_tool.py

review_suite tests/mcp/test_server_errors.py

review_box python -B - <<'PY'
from pathlib import Path
import ast
root = Path("src/cai")
dirs = ["api", "continuous_ops", "sdk/agents", "util"]
main = ["cli", "cli_headless", "parallel_worker", "output", "config_loader", "continuation"]
paths = {p for d in dirs for p in (root / d).rglob("*.py")}
paths |= {root / (n + ".py") for n in main}
for path in sorted(paths):
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    ast.parse(source, filename=str(path), feature_version=(3, 10))
print(len(paths))
PY
~~~

The stock collection control used `python -B -m pytest -q -p no:cacheprovider --collect-only tests/others/test_strict_schema.py` with the base interpreter and no cached OpenAI package. It exited 4 in the root conftest. Adding the local dependencies advanced it to `ModuleNotFoundError: No module named 'litellm'`. The fixtures above are the route by which the tested SDK portions could be loaded offline.

Useful read-only checks for the key transitions and their callers follow. The checked-in CI workflow can be inspected without running its setup or smoke jobs. [.github/workflows/tests.yml:13](repos/aliasrobotics__cai/.github/workflows/tests.yml:13)

~~~bash
cd "$review_repo"
rg -n 'DEFAULT_LOOP_HOOKS|QueueCompleteSentinel|_run_impl_task|should_continue' \
    src/cai/sdk/agents/{run,result,hooks}.py
rg -n 'run_inference|set_running_task|recon_result|session.history' \
    src/cai/api/{app,sessions,streaming}.py
rg -n '_run_cai_with_tee|p\.poll|mark_task_run|iteration =|Restart=' \
    src/cai/continuous_ops/{loop_runner,systemd_unit}.py
rg -n 'MAX_RUNTIME|def force_flush|on_trace_start|on_span_end' \
    src/cai/sdk/agents/tracing/processors.py
wc -l src/cai/cli_headless.py src/cai/sdk/agents/models/openai_chatcompletions.py
~~~

### Runner controls

The first-turn guard and the loop hook fixtures use text and one inert callback. The other branches compare consumer closure, failure before a turn, and an exception in a turn. The observations are in §6. [src/cai/sdk/agents/run.py:249](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:249) [src/cai/sdk/agents/run.py:288](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:288) [src/cai/sdk/agents/run.py:628](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:628) [src/cai/sdk/agents/result.py:147](repos/aliasrobotics__cai/src/cai/sdk/agents/result.py:147)

~~~bash
review_sdk <<'PY'
import asyncio
from types import SimpleNamespace
from cai.sdk.agents import (
    Agent, FunctionTool, GuardrailFunctionOutput, InputGuardrailTripwireTriggered,
    RunConfig, Runner, input_guardrail, tracing,
)
from cai.sdk.agents.hooks import DEFAULT_LOOP_HOOKS
from tests.fake_model import FakeModel
from tests.core.test_responses import get_text_message, get_function_tool_call
from cai.sdk.agents.stream_events import AgentUpdatedStreamEvent

cfg=RunConfig(tracing_disabled=True)
tool_schema={"type":"object","properties":{},"additionalProperties":False,"required":[]}
def toy(fn):
    return FunctionTool(name="format_note",description="toy fixture",params_json_schema=tool_schema,on_invoke_tool=fn)

async def loop_hooks():
    class Stop:
        def __init__(self): self.seen=[]
        async def on_turn_start(self, turn, *_): self.seen.append(("start",turn))
        async def on_turn_end(self, turn, *_): self.seen.append(("end",turn))
        async def should_continue(self, turn, *_):
            self.seen.append(("stop",turn)); return False
    async def format_note(*_): return "formatted"
    for streamed in (False,True):
        h=Stop()
        DEFAULT_LOOP_HOOKS.append(h)
        try:
            m=FakeModel()
            m.add_multiple_turn_outputs([[get_function_tool_call("format_note","{}")],[get_text_message("done")]])
            a=Agent("Fixture",model=m,tools=[toy(format_note)])
            if streamed:
                r=Runner.run_streamed(a,"test",max_turns=2,run_config=cfg)
                async for _ in r.stream_events(): pass
            else:
                r=await Runner.run(a,"test",max_turns=2,run_config=cfg)
            assert r.final_output=="done" and len(r.raw_responses)==2
            print("hook return False",streamed,len(r.raw_responses),h.seen)
        finally:
            DEFAULT_LOOP_HOOKS.pop()

async def tripwire():
    entered=asyncio.Event()
    release=asyncio.Event()
    invoked=asyncio.Event()
    async def format_note(*_):
        invoked.set()
        return "formatted"
    class WaitingModel(FakeModel):
        async def get_response(self,*a,**k):
            entered.set()
            await release.wait()
            return await super().get_response(*a,**k)
    @input_guardrail
    async def reject(*_):
        await entered.wait()
        return GuardrailFunctionOutput(output_info="fixture",tripwire_triggered=True)
    a=Agent("Fixture",model=WaitingModel(initial_output=[get_function_tool_call("format_note","{}")]),tools=[toy(format_note)],input_guardrails=[reject])
    try:
        await Runner.run(a,"test",max_turns=1,run_config=cfg)
    except InputGuardrailTripwireTriggered:
        assert not invoked.is_set()
        release.set()
        await invoked.wait()
        print("rejected initial input; in-flight sibling later ran inert callback",invoked.is_set())
    else: raise AssertionError("expected rejection")

async def stream_close():
    gate=asyncio.Event()
    class WaitingModel(FakeModel):
        async def stream_response(self,*a,**k):
            await gate.wait()
            async for event in super().stream_response(*a,**k): yield event
    a=Agent("Fixture",model=WaitingModel(initial_output=[get_text_message("done")]))
    r=Runner.run_streamed(a,"test",max_turns=1,run_config=cfg)
    it=r.stream_events()
    assert isinstance(await anext(it),AgentUpdatedStreamEvent)
    await it.aclose()
    print("producer pending after consumer close",not r._run_impl_task.done())
    assert not r._run_impl_task.done()
    gate.set()
    await r._run_impl_task
    print("abandoned stream completion",r.is_complete,r.final_output,"queued",r._event_queue.qsize())
    assert r.final_output=="done"

async def stalled_error():
    listening=asyncio.Event()
    fail=asyncio.Event()
    class Queue(asyncio.Queue):
        async def get(self):
            if self.empty(): listening.set()
            return await super().get()
    class GateAgent(Agent):
        async def get_all_tools(self):
            await fail.wait()
            raise LookupError("fixture failure before turn")
    a=GateAgent("Fixture",model=FakeModel())
    r=Runner.run_streamed(a,"test",max_turns=1,run_config=cfg)
    r._event_queue=Queue()
    it=r.stream_events()
    assert isinstance(await anext(it),AgentUpdatedStreamEvent)
    read=asyncio.create_task(anext(it))
    await listening.wait()
    fail.set()
    await asyncio.gather(r._run_impl_task,return_exceptions=True)
    print("early producer failure",type(r._run_impl_task.exception()).__name__,"reader pending",not read.done(),"queued",r._event_queue.qsize())
    assert not read.done()
    read.cancel()
    await asyncio.gather(read,return_exceptions=True)
    await it.aclose()
    bad=Agent("Fixture",model=FakeModel(initial_output=LookupError("fixture failure in turn")))
    rr=Runner.run_streamed(bad,"test",max_turns=1,run_config=cfg)
    try:
        async for _ in rr.stream_events(): pass
    except LookupError as exc: print("ordinary turn failure delivered to reader",str(exc))
    else: raise AssertionError("expected original error")

async def main():
    await loop_hooks()
    await tripwire()
    await stream_close()
    await stalled_error()
asyncio.run(asyncio.wait_for(main(),3.0))
tracing.default_processor().shutdown()
PY
~~~

### Producer cancellation and usage

The usage fixture creates the required integer fields of the cached transport schema. The event-backed queue confirms that a read is pending before cancellation. [src/cai/sdk/agents/run.py:778](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:778) [src/cai/sdk/agents/run.py:857](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:857) [src/cai/sdk/agents/run.py:1161](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:1161)

~~~bash
review_sdk <<'PY'
import asyncio
from cai.sdk.agents import Agent, Runner, RunConfig, RunHooks, tracing
from cai.sdk.agents.usage import Usage
from openai.types.responses.response_usage import ResponseUsage, InputTokensDetails, OutputTokensDetails
from tests.fake_model import FakeModel
from tests.core.test_responses import get_text_message
from cai.sdk.agents.stream_events import AgentUpdatedStreamEvent

class WatchedQueue(asyncio.Queue):
    def __init__(self):
        super().__init__()
        self.blocked=asyncio.Event()
    async def get(self):
        if self.empty(): self.blocked.set()
        return await super().get()

class Waiting(FakeModel):
    def __init__(self):
        super().__init__(initial_output=[get_text_message("note")])
        self.streaming=asyncio.Event()
        self.stop=asyncio.Event()
    async def stream_response(self,*a,**k):
        self.streaming.set()
        await self.stop.wait()
        async for event in super().stream_response(*a,**k): yield event

async def cancelled_producer():
    model=Waiting()
    r=Runner.run_streamed(Agent("Fixture",model=model),"note",run_config=RunConfig(tracing_disabled=True))
    r._event_queue=WatchedQueue()
    it=r.stream_events()
    assert isinstance(await anext(it),AgentUpdatedStreamEvent)
    await model.streaming.wait()
    nxt=asyncio.create_task(anext(it))
    await r._event_queue.blocked.wait()
    r._run_impl_task.cancel()
    await asyncio.gather(r._run_impl_task,return_exceptions=True)
    print("cancelled producer",r._run_impl_task.cancelled(),"consumer done",nxt.done(),"complete",r.is_complete)
    assert not nxt.done() and not r.is_complete
    nxt.cancel()
    await asyncio.gather(nxt,return_exceptions=True)
    await it.aclose()

async def usage():
    class Measured(FakeModel):
        async def get_response(self,*a,**k):
            resp=await super().get_response(*a,**k)
            resp.usage=Usage(requests=1,input_tokens=4,output_tokens=2,total_tokens=6)
            return resp
        async def stream_response(self,*a,**k):
            async for evt in super().stream_response(*a,**k):
                evt.response.usage=ResponseUsage(input_tokens=4,output_tokens=2,total_tokens=6,
                   input_tokens_details=InputTokensDetails(**{k:0 for k,v in InputTokensDetails.model_fields.items() if v.is_required() and v.annotation is int}),
                   output_tokens_details=OutputTokensDetails(**{k:0 for k,v in OutputTokensDetails.model_fields.items() if v.is_required() and v.annotation is int}))
                yield evt
    class Hooks(RunHooks):
        async def on_agent_end(self,ctx,agent,output): self.total=ctx.usage.total_tokens

    for streamed in (False,True):
        h=Hooks()
        a=Agent("Fixture",model=Measured(initial_output=[get_text_message("note")]))
        if streamed:
            r=Runner.run_streamed(a,"note",hooks=h)
            async for _ in r.stream_events(): pass
        else:
            r=await Runner.run(a,"note",hooks=h)
        print("usage",streamed,"response",r.raw_responses[0].usage.total_tokens,"end hook",h.total)
        assert r.raw_responses[0].usage.total_tokens==6 and h.total==(0 if streamed else 6)

async def main():
    await cancelled_producer()
    await usage()
asyncio.run(asyncio.wait_for(main(),3))
tracing.default_processor().shutdown()
PY
~~~

### Session transaction controls

This uses the checkout's session code, actual runner, and fake model. The test subclass observes when the second input has been composed. The lock and mutation code remain the actual implementations. [src/cai/api/sessions.py:98](repos/aliasrobotics__cai/src/cai/api/sessions.py:98) [src/cai/api/sessions.py:147](repos/aliasrobotics__cai/src/cai/api/sessions.py:147)

~~~bash
review_api <<'PY'
import asyncio
from cai.api.sessions import SessionManager, SessionState, SessionNotFoundError
from cai.sdk.agents import Agent, Runner, RunConfig
from tests.fake_model import FakeModel
from tests.core.test_responses import get_text_message

def texts(items):
    return [m["content"] for m in items if m["role"]=="user"]

class Gated(FakeModel):
    def __init__(self):
        super().__init__()
        self.entered=asyncio.Event()
        self.release=asyncio.Event()
        self.seen=[]
    async def get_response(self,*args,**kwargs):
        self.seen.append(texts(kwargs["input"]))
        call=len(self.seen)
        if call==1:
            self.entered.set()
            await self.release.wait()
        self.set_next_output([get_text_message(f"answer{call}")])
        return await super().get_response(*args,**kwargs)

class ObservedSession(SessionState):
    def __init__(self,model,**kw):
        super().__init__(agent_name="Fixture",model_name="dummy",metadata=None,
                         agent_factory=lambda *_: Agent("Fixture",model=model),**kw)
        self.b_composed = asyncio.Event()
    def _compose_input(self,new_input):
        out = super()._compose_input(new_input)
        if new_input=="B": self.b_composed.set()
        return out

async def scenario(overlap, stateful=True):
    model=Gated()
    s=ObservedSession(model,stateful=stateful)
    t1=asyncio.create_task(s.run_inference("A"))
    await model.entered.wait()
    if overlap:
        t2=asyncio.create_task(s.run_inference("B"))
        await s.b_composed.wait()
        assert len(model.seen)==1
        model.release.set()
        await asyncio.gather(t1,t2)
    else:
        model.release.set()
        await t1
        await s.run_inference("B")
    assert s._current_task is None
    print("conversation",overlap,stateful,model.seen,texts(s.history))

async def lifetime():
    model=Gated()
    manager=SessionManager(lambda *_: Agent("Fixture",model=model))
    first=manager.create_session()
    t=asyncio.create_task(first.run_inference("A"))
    await model.entered.wait()
    old_agent=first.agent
    manager.reset_session(first.id)
    assert first.agent is not old_agent and not first.history
    manager.delete_session(first.id)
    assert not manager.list_sessions()
    try: manager.get_session(first.id)
    except SessionNotFoundError: pass
    else: raise AssertionError("deleted session visible")
    assert not t.done() and first._current_task is not None
    model.release.set()
    await t
    print("deleted session's old task completed after reset",texts(first.history))
    assert manager.list_sessions()==SessionManager(lambda *_: None).list_sessions()==[]

async def cancellation():
    s=ObservedSession(FakeModel(),stateful=True)
    started=asyncio.Event()
    first_cancel=asyncio.Event()
    second_cancel=asyncio.Event()
    allow_finish=asyncio.Event()
    async def target():
        started.set()
        for signal in (first_cancel,second_cancel):
            try: await allow_finish.wait()
            except asyncio.CancelledError: signal.set()
        await allow_finish.wait()
        return "finished"
    task=asyncio.create_task(target())
    s.set_running_task(task)
    await started.wait()
    cancel=asyncio.create_task(s.interrupt_and_wait(timeout=.01))
    await asyncio.wait_for(first_cancel.wait(),1)
    await asyncio.wait_for(second_cancel.wait(),1)
    print("cancellation delivered twice, waiting task finished?",cancel.done())
    assert not cancel.done()
    allow_finish.set()
    print("reported interruption after natural completion",await cancel,await task,s._current_task)

async def main():
    await scenario(False)
    await scenario(True)
    await scenario(True,False)
    await lifetime()
    await cancellation()
asyncio.run(asyncio.wait_for(main(), 3.0))
PY
~~~

### Actual ASGI dispatch

Commands and account handling are stubbed and never exercised. HTTPX dispatches requests directly to the factory's ASGI app. The script uses a synthetic conversation and no API header. [src/cai/api/app.py:94](repos/aliasrobotics__cai/src/cai/api/app.py:94) [src/cai/api/app.py:653](repos/aliasrobotics__cai/src/cai/api/app.py:653) [src/cai/api/app.py:707](repos/aliasrobotics__cai/src/cai/api/app.py:707)

~~~bash
review_api <<'PY'
sys.path.append("/opt/mcpdeps")
commands=pkg("cai.api.commands","/tmp")
commands.CommandExecutor=object
auth=pkg("cai.api.auth","/tmp")
auth.AuthManager=object
auth.InvalidCredentialsError=type("FixtureInvalid",(Exception,),{})
auth.UserAlreadyExistsError=type("FixtureExists",(Exception,),{})

import asyncio, json
from types import SimpleNamespace
from httpx import ASGITransport,AsyncClient
from importlib.metadata import version
from cai.api.app import create_cai_api_app
from cai.api.sessions import SessionManager
from cai.sdk.agents import Agent, GuardrailFunctionOutput, output_guardrail, tracing
from tests.fake_model import FakeModel
from tests.core.test_responses import get_text_message

def messages(body):
    frames=body.strip().split("\n\n")
    return [(n.removeprefix("event: "),json.loads(d.removeprefix("data: ")))
             for n,d in [f.split("\n",1) for f in frames]]
def history(s):
    return [p["text"] for m in s.history if m.get("role")=="assistant" for p in m["content"]]

async def call(client, args, endpoints):
    s=manager.create_session()
    model=s.agent.model
    model.add_multiple_turn_outputs([[get_text_message(x)] for x in args])
    for suffix,data in endpoints:
        r=await client.post(f"/api/v1/sessions/{s.id}/messages"+suffix,json={"input":"fixture",**data})
        print("ASGI status",suffix or "ordinary",r.status_code,"remaining",len(model.turn_outputs))
        if r.status_code==200 and suffix:
            events=messages(r.text)
            print("ASGI events",[x[0] for x in events],"final",events[-1][1]["final_output"],"history",history(s))
        else:
            print("ASGI body",r.json())
    return s

@output_guardrail
async def check(*_):
    return GuardrailFunctionOutput(output_info="inert",tripwire_triggered=True)

async def main():
    global manager
    manager=SessionManager(lambda *_: Agent("Fixture",model=FakeModel()))
    app=create_cai_api_app(session_manager=manager,command_executor=object())
    print("in-process versions",version("fastapi"),version("starlette"))
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://fixture.invalid") as c:
        s=await call(c,["shown","saved"],[("/stream",{})])
        assert history(s)==["saved"] and not s.agent.model.turn_outputs
        await call(c,["final"],[("",{"max_turns":0}),("/stream_tokens",{"max_turns":0})])
        blocked=manager.create_session()
        blocked.agent.output_guardrails=[check]
        blocked.agent.model.set_next_output([get_text_message("blocked test text")])
        reply=await c.post(f"/api/v1/sessions/{blocked.id}/messages/stream_tokens",json={"input":"fixture"})
        events=messages(reply.text)
        print("ASGI gated events",[x[0] for x in events],"final",events[-1][1]["final_output"],"history",history(blocked))
        assert events[-2][0]=="error" and events[-1][1]["final_output"]=="blocked test text"
        assert history(blocked)==["blocked test text"]
asyncio.run(asyncio.wait_for(main(),5))
tracing.default_processor().shutdown()
PY
~~~

### SSE generator and trace ownership controls

The extracted AST route uses the original body without route-declaration annotations. It is an independent comparison with normal ASGI dispatch. The synthetic token sequence checks duplicate translation and the hook close control drains its final frame for test cleanup. [src/cai/api/app.py:653](repos/aliasrobotics__cai/src/cai/api/app.py:653) [src/cai/api/streaming.py:199](repos/aliasrobotics__cai/src/cai/api/streaming.py:199) [src/cai/api/streaming.py:269](repos/aliasrobotics__cai/src/cai/api/streaming.py:269)

~~~bash
review_api <<'PY'
import ast, asyncio, copy, json
from pathlib import Path
from types import SimpleNamespace as NS
from cai.api import streaming
from cai.api.sessions import SessionState
from cai.sdk.agents import Agent, ItemHelpers, MessageOutputItem, Runner, tracing
from cai.sdk.agents.stream_events import (
 AgentUpdatedStreamEvent, RawResponsesStreamEvent, RunItemStreamEvent
)
from tests.fake_model import FakeModel
from tests.core.test_responses import get_text_message

def load_handler(name, env):
    p=Path("/repo/src/cai/api/app.py")
    tree=ast.parse(p.read_text())
    outer=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="create_cai_api_app")
    target=next(n for n in outer.body if isinstance(n,ast.AsyncFunctionDef) and n.name==name)
    target.decorator_list=[]
    target.returns=None
    for arg in target.args.args:
        arg.annotation=None
    target.args.defaults=[]
    exec(compile(ast.Module(body=[target], type_ignores=[]),str(p),"exec"),env)
    return env[name]

def decode(chunk):
    event, data=chunk.decode().strip().split("\n",1)
    return event.removeprefix("event: "),json.loads(data.removeprefix("data: "))

def state(model):
    return SessionState(agent_name="Fixture", model_name="fixture", stateful=True,
        metadata=None, agent_factory=lambda *_: Agent("Fixture",model=model))

async def duplicated():
    m=FakeModel()
    m.add_multiple_turn_outputs([[get_text_message("visible")],[get_text_message("stored")]])
    s=state(m)
    def response(gen,**kw): return gen
    ep=load_handler("send_message_stream", {"sse_stream_via_hooks":streaming.sse_stream_via_hooks,
                                            "StreamingResponse":response})
    gen=await ep("id",NS(input="note",context=None,max_turns=None),NS(get_session=lambda _:s))
    events=[]
    async for chunk in gen:
        events.append(decode(chunk))
    assert len(m.turn_outputs)==0
    final=events[-1][1]["final_output"]
    persisted=ItemHelpers.extract_last_text(get_text_message("stored"))
    history_texts=[p.get("text") for m in s.history if m.get("role")=="assistant" for p in m["content"]]
    assert (final,history_texts)==("visible",["stored"])
    print("hook route sent",final,"history contains",history_texts,"remaining fake responses",len(m.turn_outputs))

async def hook_close():
    release=asyncio.Event()
    class Gate(FakeModel):
        async def get_response(self,*a,**k):
            await release.wait()
            return await super().get_response(*a,**k)
    s=state(Gate(initial_output=[get_text_message("done")]))
    gen=streaming.sse_stream_via_hooks(s.agent,"note",session=s)
    first=decode(await anext(gen))
    assert first[1]["type"]=="agent_switched"
    assert s._current_task is not None
    release.set()
    try: await gen.aclose()
    except RuntimeError as exc: print("early hook iterator close",str(exc))
    else: raise AssertionError("expected GeneratorExit violation")
    remaining=[]
    try:
        async for chunk in gen:
            remaining.append(decode(chunk)[0])
    except GeneratorExit:
        pass
    print("test cleanup drained",remaining,"generator closed",gen.ag_frame is None)
    assert gen.ag_frame is None and s._current_task is None

async def token_duplicate():
    a=Agent("Fixture",model=FakeModel())
    async def event_source(include_semantic):
        yield AgentUpdatedStreamEvent(a)
        for typ in ("response.output_item.added","response.output_text.delta","response.output_item.done"):
            yield RawResponsesStreamEvent(NS(type=typ,delta="serialized note"))
        if include_semantic:
            yield RunItemStreamEvent(name="message_output_created",item=MessageOutputItem(a,get_text_message("serialized note")))
    for sem in (False,True):
        emitted = [decode(frame) async for frame in streaming.sse_stream_tokens_for_run(
            NS(stream_events=lambda:event_source(sem), final_output="serialized note", _trace=None))]
        messages=[step["text"] for step in emitted[-1][1]["steps"] if step["type"]=="message"]
        print("token+semantic",sem,"messages in summary",messages)
        assert len(messages)==1+int(sem)

async def main():
    await duplicated()
    await hook_close()
    await token_duplicate()
asyncio.run(asyncio.wait_for(main(), 3))
tracing.default_processor().shutdown()
PY
~~~

### Trace context in separate tasks

The processor records start and finish calls in memory. Each case restores the trace in its original task after checking the observation. [src/cai/sdk/agents/run.py:516](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:516) [src/cai/sdk/agents/result.py:180](repos/aliasrobotics__cai/src/cai/sdk/agents/result.py:180) [src/cai/sdk/agents/tracing/traces.py:166](repos/aliasrobotics__cai/src/cai/sdk/agents/tracing/traces.py:166)

~~~bash
review_api <<'PY'
import asyncio
from cai.api.streaming import sse_stream_tokens_for_run
from cai.sdk.agents import Agent, Runner, RunConfig, get_current_trace
from cai.sdk.agents.tracing import set_trace_processors
from cai.sdk.agents.tracing.processors import default_processor
from tests.fake_model import FakeModel
from tests.core.test_responses import get_text_message

class MemoryProcessor:
    def __init__(self): self.started=[]; self.ended=[]
    def on_trace_start(self,t): self.started.append(t.trace_id)
    def on_trace_end(self,t): self.ended.append(t.trace_id)
    def on_span_start(self,s): pass
    def on_span_end(self,s): pass
    def shutdown(self): pass

async def one(mode):
    pr=MemoryProcessor()
    set_trace_processors([pr])
    assert get_current_trace() is None
    agent=Agent("Fixture",model=FakeModel(initial_output=[get_text_message("done")]))
    r=Runner.run_streamed(agent,"note",run_config=RunConfig())
    created=get_current_trace()
    assert created is r._trace and created is not None
    async def consume(via_sse=False):
        target=sse_stream_tokens_for_run(r) if via_sse else r.stream_events()
        async for _ in target: pass
    outcome="ok"
    try:
        if mode=="same_context": await consume()
        else: await asyncio.create_task(consume(via_sse=mode=="sse"))
    except ValueError as e:
        outcome=type(e).__name__
        assert "different Context" in str(e)
    print("trace closure",mode,outcome,"owner still bound", get_current_trace() is created,
          "start/end",len(pr.started),len(pr.ended))
    expected={"same_context":("ok",False,1),"different_task":("ValueError",True,1),"sse":("ok",True,0)}
    assert (outcome,get_current_trace() is created,len(pr.ended))==expected[mode]
    if get_current_trace() is created:
        created.finish(reset_current=True)
    assert get_current_trace() is None
    await r._run_impl_task

async def main():
    for mode in ("same_context","different_task","sse"):
        await one(mode)
asyncio.run(asyncio.wait_for(main(),3))
set_trace_processors([])
default_processor().shutdown()
PY
~~~

### Trace export worker lifetime

This control measures an actual 30-second worker lifetime using an in-memory exporter. The trace review concurrently proceeded through other code. No transport was exercised. [src/cai/sdk/agents/tracing/processors.py:173](repos/aliasrobotics__cai/src/cai/sdk/agents/tracing/processors.py:173) [src/cai/sdk/agents/tracing/processors.py:231](repos/aliasrobotics__cai/src/cai/sdk/agents/tracing/processors.py:231)

~~~bash
review_box python -B - <<'PY'
import os, sys, threading, time, types
os.environ["CAI_TRACING"]="false"
import cai
for name in ("cai.sdk","cai.sdk.agents"):
    pkg=types.ModuleType(name)
    pkg.__path__=["/repo/src/"+name.replace(".", "/")]
    sys.modules[name]=pkg
from cai.sdk.agents.tracing import processors
class MemoryExporter:
    def __init__(self):
        self.batches=[]
        self.received=threading.Event()
    def export(self, items):
        self.batches.append(list(items))
        self.received.set()

print("import threads:", [t.name for t in threading.enumerate()], flush=True)
ex=MemoryExporter()
p=processors.BatchTraceProcessor(ex, schedule_delay=.01)
start=time.monotonic()
p.on_trace_start("early")
assert ex.received.wait(2.0)
assert ex.batches==[["early"]]
print("early exported", flush=True)
p._worker_thread.join(33.0)
elapsed=time.monotonic()-start
assert not p._worker_thread.is_alive()
print("worker exited on its own", round(elapsed,3), "shutdown flag",p._shutdown_event.is_set(),flush=True)
assert not p._shutdown_event.is_set()
p.on_trace_start("late")
assert ex.batches==[["early"]] and p._queue.qsize()==1
p.force_flush()
assert ex.batches==[["early"],["late"]]
print("late queued until explicit flush",ex.batches,flush=True)
p.shutdown()
processors.default_processor().shutdown()
PY
~~~

### Retry boundary and worker process exit

The headless retry body is evaluated with its real runner. Timing and display dependencies are inert and two response sequences differ only by the phase of the injected failure. [src/cai/cli_headless.py:1542](repos/aliasrobotics__cai/src/cai/cli_headless.py:1542)

~~~bash
review_sdk <<'PY'
import ast, asyncio, logging, time
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from cai.sdk.agents import Agent, FunctionTool, Runner
from cai.sdk.agents.exceptions import (
    MaxTurnsExceeded, InputGuardrailTripwireTriggered, OutputGuardrailTripwireTriggered
)
from cai.sdk.agents.items import ToolCallOutputItem
from tests.core.test_responses import get_function_tool_call,get_text_message
from tests.fake_model import FakeModel
p=Path("/repo/src/cai/cli_headless.py")
src=ast.parse(p.read_text())
fn=next(n for n in src.body if isinstance(n,ast.FunctionDef) and n.name=="_run_non_streamed")
g=dict(globals(),Timeout=TimeoutError,RateLimitError=type("DummyRateError",(Exception,),{}),
       verbose_http_retries=lambda:False)
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(p),"exec"),g)
for where in ("before","after"):
    effects=[]
    pauses=[]
    model=FakeModel()
    model.message_history=[]
    model.add_to_message_history=model.message_history.append
    async def pure(*_): effects.append("marker"); return "fixture"
    tool=FunctionTool("format_note","fixture",{"type":"object","properties":{}},pure)
    call=[get_function_tool_call("format_note","{}")]
    done=[get_text_message("done")]
    err=ConnectionError("injected transient fixture fault")
    model.add_multiple_turn_outputs([err,call,done] if where=="before" else [call,err,call,done])
    with patch.object(time,"sleep",lambda delay:pauses.append(delay)):
        g["_run_non_streamed"](Agent("Fixture",model=model,tools=[tool]),"note",None,False,None)
    print("failure",where,"callbacks",len(effects),"retries",len(pauses),"responses left",len(model.turn_outputs))
    assert len(effects)==(1 if where=="before" else 2)
    assert len(pauses)==1 and not model.turn_outputs
PY
~~~

### Direct worker exit and cleanup

The helper launches only benign local Python children. The recorded process handle verifies poll state. Each case closes its pipe and terminates any fixture child left alive. [src/cai/continuous_ops/loop_runner.py:273](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:273) [src/cai/continuous_ops/loop_runner.py:319](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:319) [src/cai/continuous_ops/loop_runner.py:342](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:342)

~~~bash
review_sdk <<'PY'
import os, signal, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from cai.continuous_ops import loop_runner
from time import monotonic

with TemporaryDirectory() as dp:
    d=Path(dp)
    def test(name, script, timeout, expected, pending=False):
        real_popen=subprocess.Popen
        children=[]
        def record(*a,**kw):
            child=real_popen(*a,**kw)
            children.append(child)
            return child
        before=monotonic()
        with patch.object(loop_runner.subprocess,"Popen",side_effect=record):
            code=loop_runner._run_cai_with_tee([sys.executable,"-B","-c",script],
                d/(name+".log"),dict(os.environ),d,timeout_sec=timeout)
        dur=monotonic()-before
        child=children[0]
        actual=child.poll()
        print(name,"returned",code,"child poll",actual,"seconds",round(dur,3),flush=True)
        try:
            assert code==expected
            assert (actual is None)==pending
        finally:
            if actual is None:
                child.terminate()
                child.wait(timeout=2)
            child.stdout.close()

    print("child fixtures",flush=True)
    test("normal","import sys; print('fixture',flush=True); sys.exit(9)",2.0,9)
    test("pipe_timeout","import time; time.sleep(1)",.12,124)
    test("closed_pipe","import os,time; os.close(1); os.close(2); time.sleep(8); os._exit(9)",2.0,0,True)
PY
~~~

### Snapshot shape, rename, and retention

All files are within a temporary directory. Permission failure is injected into the final rename. Source timestamps are set explicitly and the gzip data is decompressed as a positive control. [src/cai/continuous_ops/session_snapshot.py:44](repos/aliasrobotics__cai/src/cai/continuous_ops/session_snapshot.py:44) [src/cai/continuous_ops/session_snapshot.py:72](repos/aliasrobotics__cai/src/cai/continuous_ops/session_snapshot.py:72) [src/cai/continuous_ops/log_maintenance.py:39](repos/aliasrobotics__cai/src/cai/continuous_ops/log_maintenance.py:39)

~~~bash
review_box python -B - <<'PY'
import gzip, json, os, time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from cai.continuous_ops.log_maintenance import maintain_log_tree
from cai.continuous_ops.session_snapshot import export_snapshot, load_snapshot_messages

with TemporaryDirectory() as dirname:
    d=Path(dirname)
    day=86400
    now=time.time()
    full=d/"full"
    full.mkdir()
    mid=full/"middle.log"
    mid.write_text("fixture",encoding="utf-8")
    mid_mtime=now-10*day
    os.utime(mid,(mid_mtime,mid_mtime))
    maintain_log_tree(d,now=now)
    gz=mid.with_suffix(".log.gz")
    assert not mid.exists() and gzip.decompress(gz.read_bytes())==b"fixture"
    print("gzip compression advanced mtime by days:",round((gz.stat().st_mtime-mid_mtime)/day,3))
    maintain_log_tree(d,now=now+7*day)
    assert gz.exists()
    os.utime(gz,(mid_mtime,mid_mtime))
    maintain_log_tree(d,now=now+7*day)
    assert not gz.exists()
    print("17-day original retained after gzip; restoring original mtime makes it expire")
    snap=d/"state.json"
    msgs=[{"role":"user","content":f"note {i}"} for i in range(45)]
    msgs[-1]["content"]="é"*12030
    assert export_snapshot(snap,msgs)
    restored=load_snapshot_messages(snap)
    assert len(restored)==40 and restored[0]==msgs[5]
    assert restored[-1]["content"].startswith("é"*12000)
    assert len(msgs[-1]["content"])==12030 and len(restored[-1]["content"])<12030+30
    orig=snap.read_bytes()
    with patch.object(Path,"replace",side_effect=PermissionError("injected replace denial")):
        assert not export_snapshot(snap,[{"role":"user","content":"alternate"}])
    assert snap.read_bytes()==orig
    print("snapshot round-trip:",len(restored),"first",restored[0]["content"],"failed replace preserves prior",snap.with_suffix(".json.tmp."+str(os.getpid())).is_file())
    for data in (b'{"messages": []}',b'{',b'[]',b'null',b'\xff'):
        snap.write_bytes(data)
        try: print("snapshot",repr(data), "=>", load_snapshot_messages(snap))
        except Exception as e: print("snapshot",repr(data), "=>",type(e).__name__)
    assert load_snapshot_messages(d/"absent")==[]
PY
~~~

### History replay heuristics

Run this command once as displayed and once with `REVIEW_ORJSON=1 review_sdk` to compare the alternate parser. The JSONL fixtures contain only user and assistant text. [src/cai/sdk/agents/run_to_jsonl.py:444](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:444) [src/cai/sdk/agents/run_to_jsonl.py:523](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:523) [src/cai/sdk/agents/run_to_jsonl.py:609](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:609)

~~~bash
review_sdk <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from cai.sdk.agents.run_to_jsonl import load_history_from_jsonl, _find_last_model_record_fast, _deduplicate_messages_fast
import json
from unittest.mock import patch

def item(role, text):
    return {"role":role,"content":text}

def request(*msgs):
    return {"model":"fixture","messages":list(msgs)}

def reply(text):
    return {"id":"ident-"+text,"object":"chat.completion","choices":[{"message":item("assistant",text)}]}

with TemporaryDirectory() as dirname:
    f=Path(dirname)/"sample.jsonl"
    a=item("user","Repeat"); b=item("assistant","first"); c=item("user","Repeat")
    turn=[request(a),reply("first"),request(a,b,c),reply("second")]
    def write(records):
        f.write_text("".join(json.dumps(r)+"\n" for r in records),encoding="utf-8")
    def summary(result):
        return [(m.get("role"),m.get("content")) for m in result]
    write(turn)
    print("file bytes",f.stat().st_size, "fast pick",summary(_find_last_model_record_fast(str(f))[0]["messages"]))
    print("repeat fast", summary(load_history_from_jsonl(f)))
    print("repeat slow", summary(load_history_from_jsonl(f,use_last_record_optimization=False)))
    print("direct dedup",summary(_deduplicate_messages_fast([a,b,c,item("assistant","second")])))
    d=item("user","Different")
    write([request(a),reply("first"),request(a,b,d),reply("second")])
    print("distinct fast",summary(load_history_from_jsonl(f)))
    print("distinct slow",summary(load_history_from_jsonl(f,use_last_record_optimization=False)))
    write([request(a),reply("early"),request(d),reply("latest")])
    print("equal length disjoint requests fast",summary(load_history_from_jsonl(f)))
    print("equal length disjoint requests slow",summary(load_history_from_jsonl(f,use_last_record_optimization=False)))
    write([request(a),{"object":"chat.completion","choices":[]}])
    for fast in (True,False):
        try: print("empty choices",fast,summary(load_history_from_jsonl(f,use_last_record_optimization=fast)))
        except Exception as e: print("empty choices",fast,type(e).__name__)
PY
~~~

### Accounting across separate processes

The two sibling processes wait after read and increment and before the real save. They share a private test file. The serial control uses another empty test directory and the same logic. [src/cai/sdk/agents/global_usage_tracker.py:117](repos/aliasrobotics__cai/src/cai/sdk/agents/global_usage_tracker.py:117) [src/cai/sdk/agents/global_usage_tracker.py:287](repos/aliasrobotics__cai/src/cai/sdk/agents/global_usage_tracker.py:287)

~~~bash
review_box python -B - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
import json, os, subprocess, sys

worker = """
import importlib.util, sys
spec=importlib.util.spec_from_file_location("usage_fixture","/repo/src/cai/sdk/agents/global_usage_tracker.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
t=m.GLOBAL_USAGE_TRACKER
save=t._save_usage_data
def gate():
    print("ready",flush=True)
    assert sys.stdin.readline()=="go\\n"
    save()
t._save_usage_data=gate
t.track_usage(sys.argv[1],int(sys.argv[2]),1,1.0)
"""
with TemporaryDirectory() as td:
    for parallel in (False,True):
        target=Path(td)/str(parallel)
        target.mkdir()
        env=dict(os.environ, HOME=str(target))
        def start(name,tokens):
            return subprocess.Popen([sys.executable,"-B","-c",worker,name,str(tokens)],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
        def ready(p):
            msg=p.stdout.readline().strip()
            assert msg=="ready",msg
        def finish(p):
            _,err=p.communicate("go\n",timeout=3)
            assert p.returncode==0,err
        first=start("alpha",4)
        ready(first)
        if parallel:
            second=start("beta",7)
            ready(second)
            finish(first)
        else:
            finish(first)
            second=start("beta",7)
            ready(second)
        finish(second)
        data=json.loads((target/".cai"/"usage.json").read_text())
        summary=data["global_totals"]; labels=sorted(data["model_usage"])
        print("stale copies",parallel,"requests",summary["total_requests"],"input",summary["total_input_tokens"],"models",labels)
        assert (summary["total_requests"],summary["total_input_tokens"],labels)==(
             (1,7,["beta"]) if parallel else (2,11,["alpha","beta"]))
PY
~~~

### MCP resource ownership and inventory

The two entered contexts are in memory. Initialization succeeds, raises, or waits for cancellation. The cache sequence counts calls to the same fixture inventory. [src/cai/sdk/agents/mcp/server.py:124](repos/aliasrobotics__cai/src/cai/sdk/agents/mcp/server.py:124) [src/cai/sdk/agents/mcp/server.py:155](repos/aliasrobotics__cai/src/cai/sdk/agents/mcp/server.py:155)

~~~bash
review_sdk <<'PY'
sys.path.append("/opt/mcpdeps")
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS
from unittest.mock import patch
from cai.sdk.agents.mcp import server
from cai.sdk.agents.tracing.processors import default_processor

class FakeTransport(server._MCPServerWithClientSession):
    def __init__(self):
        super().__init__(cache_tools_list=True)
        self.events=[]
    @property
    def name(self): return "memory"
    @asynccontextmanager
    async def create_streams(self):
        self.events.append("transport open")
        try: yield object(),object()
        finally: self.events.append("transport close")

async def connect_case(mode):
    srv=FakeTransport()
    entered=asyncio.Event()
    gate=asyncio.Event()
    @asynccontextmanager
    async def session(*_):
        srv.events.append("session open")
        async def initialize():
            entered.set()
            if mode=="error": raise ValueError("init fixture")
            if mode=="cancel": await gate.wait()
        try: yield NS(initialize=initialize)
        finally: srv.events.append("session close")
    with patch.object(server,"ClientSession",session):
        task=asyncio.create_task(srv.connect())
        await entered.wait()
        if mode=="cancel": task.cancel()
        result=(await asyncio.gather(task,return_exceptions=True))[0]
    print("MCP init",mode,type(result).__name__,srv.events,
          "pending exit callbacks",len(srv.exit_stack._exit_callbacks))
    if mode=="ok":
        assert srv.session is not None
    if mode=="cancel":
        assert len(srv.exit_stack._exit_callbacks)==2 and srv.session is None
    if mode=="error":
        assert len(srv.exit_stack._exit_callbacks)==0 and srv.session is None
    await srv.cleanup()
    assert srv.events==["transport open","session open","session close","transport close"]

async def cache_case():
    srv=FakeTransport()
    calls=0
    async def fetch():
        nonlocal calls
        calls+=1
        if calls==2: raise ValueError("refresh fixture")
        return NS(tools=[f"revision{calls}"])
    srv.session=NS(list_tools=fetch)
    assert await srv.list_tools()==["revision1"]
    assert await srv.list_tools()==["revision1"] and calls==1
    srv.invalidate_tools_cache()
    try: await srv.list_tools()
    except ValueError: pass
    else: raise AssertionError("expected refresh failure")
    again=await srv.list_tools()
    assert again==["revision1"] and calls==2
    srv.invalidate_tools_cache()
    assert await srv.list_tools()==["revision3"] and calls==3
    print("MCP failed refresh cached stale inventory; explicit subsequent invalidation refetched",calls)

async def main():
    for mode in ("ok","error","cancel"): await connect_case(mode)
    await cache_case()
asyncio.run(asyncio.wait_for(main(),3.0))
default_processor().shutdown()
PY
~~~

### Synchronous event bus

Two subscribers share one event emission. The final mode removes the active subscriber while iterating. [src/cai/output.py:220](repos/aliasrobotics__cai/src/cai/output.py:220)

~~~bash
review_box python -B - <<'PY'
from cai.output import OutputManager, StatusEvent
def scenario(mode):
    bus = OutputManager()
    seen = []
    class Left:
        def handle(self, event):
            seen.append("left")
            if mode == "remove":
                bus.unsubscribe(self)
            if mode == "error":
                raise RuntimeError("fixture")
    class Right:
        def handle(self, event):
            seen.append("right")
    bus.subscribe(Left())
    bus.subscribe(Right())
    bus.emit(StatusEvent(message="fixture"))
    return seen
for mode in ["normal", "error", "remove"]:
    print(mode, scenario(mode))
PY
~~~


### JSONL archive allocation check

The fast path is unconditional when its flag is true and loads its line array before selecting the best record. Under CPython 3.12, fixture files of 528,640, 1,057,280, and 2,114,560 bytes produced Python allocation peaks of 693,239, 1,181,916, and 2,244,540 bytes respectively. This measures Python allocations in the reader, with no RSS or disk-latency claim. [src/cai/sdk/agents/run_to_jsonl.py:476](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:476) [src/cai/sdk/agents/run_to_jsonl.py:609](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:609)

~~~bash
review_sdk <<'PY'
import json
import tracemalloc
from pathlib import Path
from tempfile import TemporaryDirectory
from cai.sdk.agents.run_to_jsonl import _find_last_model_record_fast

with TemporaryDirectory() as td:
    path = Path(td) / "history.jsonl"
    row = json.dumps({"model":"fixture","messages":[{"role":"user","content":"x"*8192}]}) + "\n"
    for count in (64,128,256):
        with path.open("w",encoding="utf-8") as f:
            for _ in range(count):
                f.write(row)
        tracemalloc.start()
        request,_=_find_last_model_record_fast(str(path))
        _, peak=tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert request["model"]=="fixture"
        print("bytes",path.stat().st_size,"peak Python allocations",peak)
PY
~~~

### Cancellation across Python versions

The test uses the original method body and its two public dependencies, the current task reference and its setter. For Python 3.10, add `--ro-bind $HOME/.local/share/uv/python/cpython-3.10.22-linux-x86_64-gnu /opt/cp310` to `review_args` and use `/opt/cp310/bin/python3.10 -IB -`. Both versions reported a pending waiter after delivery of both cancellation signals. [src/cai/api/sessions.py:147](repos/aliasrobotics__cai/src/cai/api/sessions.py:147)

~~~bash
review_box python -IB - <<'PY'
import ast, asyncio, sys
from pathlib import Path
from types import SimpleNamespace
source=Path("/repo/src/cai/api/sessions.py")
tree=ast.parse(source.read_text())
c=next(n for n in tree.body if getattr(n,"name",None)=="SessionState")
f=next(n for n in c.body if getattr(n,"name",None)=="interrupt_and_wait")
g={"asyncio":asyncio}
exec(compile(ast.Module(body=[f],type_ignores=[]),str(source),"exec"),g)

async def main():
    ready=asyncio.Event()
    signals=[asyncio.Event(),asyncio.Event()]
    release=asyncio.Event()
    async def target():
        ready.set()
        for s in signals:
            try: await release.wait()
            except asyncio.CancelledError: s.set()
        await release.wait()
        return "end"
    child=asyncio.create_task(target())
    host=SimpleNamespace(_current_task=child)
    host.set_running_task=lambda task: setattr(host,"_current_task",task)
    await ready.wait()
    waiter=asyncio.create_task(g["interrupt_and_wait"](host,.01))
    for s in signals:
        await asyncio.wait_for(s.wait(),1)
    print(sys.version.split()[0],"after two cancellation signals waiter done:",waiter.done())
    assert not waiter.done()
    release.set()
    assert await waiter and await child=="end"
asyncio.run(asyncio.wait_for(main(),2))
PY
~~~

### Sibling callbacks on run failure

Running two inert callbacks distinguishes failure propagation from cancellation. The gate waits for the second callback to enter before the first callback's hook raises. [src/cai/sdk/agents/_run_impl.py:727](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:727) [src/cai/sdk/agents/_run_impl.py:844](repos/aliasrobotics__cai/src/cai/sdk/agents/_run_impl.py:844)

~~~bash
review_sdk <<'PY'
import asyncio
from cai.sdk.agents import Agent, FunctionTool, RunConfig, Runner, RunHooks, UserError, tracing
from tests.fake_model import FakeModel
from tests.core.test_responses import get_function_tool_call, get_text_message

async def trial(mode):
    started = asyncio.Event()
    finish = asyncio.Event()
    stopped = asyncio.Event()
    finished = asyncio.Event()
    async def first(*_): return "first"
    async def second(*_):
        started.set()
        try:
            await finish.wait()
        except asyncio.CancelledError:
            stopped.set()
            raise
        finished.set()
        return "second"
    class Hooks(RunHooks):
        async def on_tool_start(self, ctx, agent, tool):
            if tool.name=="first" and mode=="exception":
                await started.wait()
                raise LookupError("fixture hook")
    model = FakeModel()
    model.add_multiple_turn_outputs([
        [get_function_tool_call("first","{}"),get_function_tool_call("second","{}")], [get_text_message("done")]
    ])
    tools = [FunctionTool(n,"fixture",{"type":"object","properties":{}},f)
             for n,f in (("first",first),("second",second))]
    task=asyncio.create_task(Runner.run(Agent("Fixture",model=model,tools=tools),
                "note",hooks=Hooks(),run_config=RunConfig(tracing_disabled=True)))
    await started.wait()
    if mode=="exception":
        try: await task
        except UserError: pass
        else: raise AssertionError("expected hook exception")
        assert not stopped.is_set() and not finished.is_set()
        finish.set()
        await finished.wait()
        print("ordinary hook exception left sibling callback alive")
    elif mode=="cancel":
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        assert stopped.is_set() and not finished.is_set()
        print("explicit run cancellation reached sibling callback")
    else:
        finish.set()
        r=await task
        assert r.final_output=="done" and finished.is_set()
        print("normal tool batch completed")

async def main():
    for m in ("normal","cancel","exception"): await trial(m)
asyncio.run(asyncio.wait_for(main(),3))
tracing.default_processor().shutdown()
PY
~~~

### Parallel and snapshot history ownership

These fixtures compare nested copy isolation, selection by explicit identity or history length, and restoration into an existing list. They also establish when a prior checkpoint or slot remains present. [src/cai/sdk/agents/parallel_isolation.py:39](repos/aliasrobotics__cai/src/cai/sdk/agents/parallel_isolation.py:39) [src/cai/sdk/agents/parallel_isolation.py:69](repos/aliasrobotics__cai/src/cai/sdk/agents/parallel_isolation.py:69) [src/cai/continuous_ops/session_snapshot.py:90](repos/aliasrobotics__cai/src/cai/continuous_ops/session_snapshot.py:90)

~~~bash
review_sdk <<'PY'
from cai.sdk.agents.parallel_isolation import ParallelHistoryIsolation

s = ParallelHistoryIsolation()
base = [{"role":"user","content":[{"text":"base"}]}]
copies = s.transfer_to_parallel(base,2,["one","two"])
copies["one"][0]["content"][0]["text"]="one"
assert base[0]["content"][0]["text"]=="base"
assert copies["two"][0]["content"][0]["text"]=="base"
assert s.get_isolated_history("one")[0]["content"][0]["text"]=="one"
copy_of_state=s.get_isolated_history("one")
copy_of_state[0]["content"][0]["text"]="outside"
assert s.get_isolated_history("one")[0]["content"][0]["text"]=="one"
copies["two"].append({"role":"assistant","content":"longer"})
chosen=s.transfer_from_parallel(copies,selected_agent_id="one")
assert s.get_selected_agent_id()=="one" and len(chosen)==1
chosen[0]["content"][0]["text"]="single"
assert copies["one"][0]["content"][0]["text"]=="one"
assert len(s.transfer_from_parallel(copies))==2 and s.get_selected_agent_id()=="two"
print("nested copies isolated; explicit and longest selections follow contract")
print("slot histories retained after selection",s.has_isolated_histories(),"parallel mode",s.is_parallel_mode())
s.clear_all_histories()
assert not s.has_isolated_histories()
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from cai.continuous_ops.session_snapshot import export_snapshot, load_snapshot_messages, apply_snapshot_to_agent
from cai.sdk.agents.simple_agent_manager import AGENT_MANAGER

with TemporaryDirectory() as td:
    p=Path(td)/"snapshot.json"
    old=[{"role":"user","content":"old"}]
    seed=[{"role":"user","content":"resumed"}]
    a=NS(name="fixture",model=NS(message_history=old))
    AGENT_MANAGER._message_history["fixture"]=old
    assert export_snapshot(p,seed)
    assert not export_snapshot(p,[])
    records=load_snapshot_messages(p)
    assert records==seed
    apply_snapshot_to_agent(a,records)
    assert a.model.message_history is old is AGENT_MANAGER._message_history["fixture"]
    assert old==seed and old is not records
    print("snapshot restores existing canonical list; empty export preserves prior checkpoint")
PY
~~~

### Snapshot across process restart

A fresh interpreter wrote a one-message fixture, and a second interpreter read it. Both used the checked-in snapshot functions and the same temporary file. [src/cai/continuous_ops/session_snapshot.py:44](repos/aliasrobotics__cai/src/cai/continuous_ops/session_snapshot.py:44) [src/cai/continuous_ops/session_snapshot.py:72](repos/aliasrobotics__cai/src/cai/continuous_ops/session_snapshot.py:72)

~~~bash
review_box python -B - <<'PY'
import json, subprocess, sys
from pathlib import Path
from tempfile import TemporaryDirectory

with TemporaryDirectory() as td:
    snap = Path(td) / "session.json"
    writer = """from cai.continuous_ops.session_snapshot import export_snapshot
from pathlib import Path
import sys
assert export_snapshot(Path(sys.argv[1]), [{"role":"user","content":"fresh note"}])"""
    reader = """from cai.continuous_ops.session_snapshot import load_snapshot_messages
from pathlib import Path
import sys,json
print(json.dumps(load_snapshot_messages(Path(sys.argv[1]))))"""
    subprocess.run([sys.executable, "-B", "-c", writer, str(snap)], check=True)
    r = subprocess.run([sys.executable, "-B", "-c", reader, str(snap)],
                       check=True, capture_output=True, text=True)
    assert json.loads(r.stdout) == [{"role":"user","content":"fresh note"}]
    print("independent writer and reader recovered same one-message snapshot")
PY
~~~

### Worker result publication

The exact worker entry-point body writes to temporary fixture files. Inert outcomes establish the difference between its process status and the status in the report file. [src/cai/parallel_worker.py:111](repos/aliasrobotics__cai/src/cai/parallel_worker.py:111) [src/cai/cli_headless.py:2208](repos/aliasrobotics__cai/src/cai/cli_headless.py:2208)

~~~bash
review_box python -B - <<'PY'
import ast, asyncio, json, sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

path=Path("/repo/src/cai/parallel_worker.py")
tree=ast.parse(path.read_text())
body=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="main")
with TemporaryDirectory() as td:
    for mode in ("ok","cancel","error","unserializable"):
        out=Path(td)/(mode+".json")
        args=SimpleNamespace(agent="fixture",agent_id="slot",model="fixture",result_file=str(out))
        async def fake_run(_):
            if mode=="cancel": raise asyncio.CancelledError()
            if mode=="error": raise ValueError("fixture")
            if mode=="unserializable": return {"status":"ok","bad":object()}
            return {"status":"ok"}
        g=dict(asyncio=asyncio,json=json,sys=sys,_parse_args=lambda:args,_run=fake_run)
        exec(compile(ast.Module(body=[body],type_ignores=[]),str(path),"exec"),g)
        rc=g["main"]()
        try: record=json.loads(out.read_text(encoding="utf-8"))
        except json.JSONDecodeError: record={"status":"incomplete json"}
        status=record["status"]
        assert (rc,status)=={
           "ok":(0,"ok"),"cancel":(0,"cancelled"),"error":(0,"error"),
           "unserializable":(2,"incomplete json")}[mode]
        print(mode,rc,status)
PY
~~~

## 10. Prioritized improvements.

| Priority | Change | Acceptance check |
| --- | --- | --- |
| **P0** | Eliminate plaintext secret fields from recording. Use an allowlist for recorder metadata and make trace and recorder privacy independent, explicit controls. | A local recorder test asserts the persisted metadata schema contains identifiers and timestamps only. Test body and sink redaction and add a migration note for existing logs. [src/cai/sdk/agents/run_to_jsonl.py:150](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:150) [src/cai/sdk/agents/run.py:104](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:104) |
| **P0** | Make rejected input ineligible for tool effects and make rejected output ineligible for publication and session commit. Set the policy for streamed provisional events explicitly. | Inert tripwire tests observe zero callback executions after rejection. Streaming tests see one terminal rejection frame and an unchanged committed transcript. Test close and cancellation while validation is pending. [src/cai/sdk/agents/run.py:249](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:249) [src/cai/sdk/agents/run.py:755](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:755) [src/cai/api/streaming.py:305](repos/aliasrobotics__cai/src/cai/api/streaming.py:305) [src/cai/api/app.py:773](repos/aliasrobotics__cai/src/cai/api/app.py:773) |
| **P0** | Commit the single real inference result through a shared session transaction. Build the input snapshot while owning the session, associate the result with that snapshot, and make reset, delete, and model change invalidate old work. | With the same gated fake model, a pair of stateful requests commits both turns. A streaming request consumes one fake response, and delivered output matches stored output. Mutation during an active run leaves an unambiguous final state. [src/cai/api/sessions.py:98](repos/aliasrobotics__cai/src/cai/api/sessions.py:98) [src/cai/api/sessions.py:169](repos/aliasrobotics__cai/src/cai/api/sessions.py:169) [src/cai/api/app.py:677](repos/aliasrobotics__cai/src/cai/api/app.py:677) |
| **P1** | Give each stream and child execution an owner that handles shutdown. Separate complete, cancelled, failed, and still-running outcomes. Tie termination to the producer and process handle, and make terminal events wake waiters under all exits. Scope cleanup to the task that acquired the resource. | Tests cover an acquisition failure, ordinary callback error, explicit cancel, timeout, caller disconnect, and shutdown with work outstanding. A reader reaches exactly one terminal state. A closed output pipe never proves successful child exit. [src/cai/sdk/agents/result.py:147](repos/aliasrobotics__cai/src/cai/sdk/agents/result.py:147) [src/cai/sdk/agents/run.py:628](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:628) [src/cai/api/sessions.py:147](repos/aliasrobotics__cai/src/cai/api/sessions.py:147) [src/cai/continuous_ops/loop_runner.py:273](repos/aliasrobotics__cai/src/cai/continuous_ops/loop_runner.py:273) [src/cai/sdk/agents/mcp/server.py:124](repos/aliasrobotics__cai/src/cai/sdk/agents/mcp/server.py:124) |
| **P1** | Restrict automatic retries to boundaries with a known effect state. Expose uncertainty to the caller when a run may already have changed state. Make the stop callback a real transition and honor it consistently across entry points. | The same connection error before and after a callback leaves the callback invoked at most once for the operation. The loop stops or returns a typed terminal status when requested, in ordinary and streamed runs. [src/cai/cli_headless.py:1542](repos/aliasrobotics__cai/src/cai/cli_headless.py:1542) [src/cai/sdk/agents/hooks.py:78](repos/aliasrobotics__cai/src/cai/sdk/agents/hooks.py:78) [src/cai/sdk/agents/run.py:288](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:288) |
| **P1** | Keep trace workers alive until owner shutdown. Bind trace lifetime to its originating context, report drop and export status, and normalize usage aggregation before hooks. | A memory exporter receives a late trace during steady operation. Long-lived and re-entrant streams end their spans in the owner scope. Usage matches typed model results and final hooks in both modes. [src/cai/sdk/agents/tracing/processors.py:231](repos/aliasrobotics__cai/src/cai/sdk/agents/tracing/processors.py:231) [src/cai/sdk/agents/tracing/traces.py:166](repos/aliasrobotics__cai/src/cai/sdk/agents/tracing/traces.py:166) [src/cai/sdk/agents/run.py:857](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:857) [src/cai/sdk/agents/run.py:1161](repos/aliasrobotics__cai/src/cai/sdk/agents/run.py:1161) |
| **P2** | Preserve ordered, versioned transcript records and make each state store's commit contract explicit. Use a transactional read and update for shared accounting, validate snapshots on read, and preserve retention timestamps. Keep legacy readers with explicit diagnostics for inferred recovery. | Repeated prompts retain distinct identities, legacy and new fixtures have predictable replay, and two process increments both persist. Failed snapshot replacement leaves the previous snapshot readable. Retention expires log data according to its original age. [src/cai/sdk/agents/run_to_jsonl.py:523](repos/aliasrobotics__cai/src/cai/sdk/agents/run_to_jsonl.py:523) [src/cai/sdk/agents/global_usage_tracker.py:117](repos/aliasrobotics__cai/src/cai/sdk/agents/global_usage_tracker.py:117) [src/cai/continuous_ops/session_snapshot.py:60](repos/aliasrobotics__cai/src/cai/continuous_ops/session_snapshot.py:60) [src/cai/continuous_ops/log_maintenance.py:39](repos/aliasrobotics__cai/src/cai/continuous_ops/log_maintenance.py:39) |
| **P2** | Add an offline core test job with the pinned dependencies. Keep transport and presentation setup lazy, remove dead duplicate definitions, and run the same lifecycle contract tests from each integration boundary. | A base utility suite collects without initializing provider, trace exporter, CLI, or MCP transports. The SDK and API lanes have deterministic fake models and typed fixtures. A static check detects duplicate methods. [tests/conftest.py:7](repos/aliasrobotics__cai/tests/conftest.py:7) [.github/workflows/tests.yml:16](repos/aliasrobotics__cai/.github/workflows/tests.yml:16) [src/cai/sdk/agents/mcp/server.py:394](repos/aliasrobotics__cai/src/cai/sdk/agents/mcp/server.py:394) [src/cai/sdk/agents/simple_agent_manager.py:849](repos/aliasrobotics__cai/src/cai/sdk/agents/simple_agent_manager.py:849) |
