# Drost Community Edition offline runtime review

## 1. Snapshot, scope, and elapsed-time evidence.

| Field | Evidence |
| --- | --- |
| Local checkout | [repos/drost-ai__drost-community](repos/drost-ai__drost-community) |
| Pinned commit | `3a410ee3f786a94e99e111884d9dd1bf80884013` |
| Pinned Git tree | `729f276347f17c774798ab1625404510b3f19f2f`, 45 tracked paths |
| Initial source integrity | Exact `git rev-parse HEAD` and empty `git status --porcelain=v1 --untracked-files=all` at review start. An ignored-inclusive status was empty as well. |
| Start and finish | 2026-11-19 UTC. Started at **07:55:33**. Final evidence and source verification completed at **08:25:37**. Elapsed **30 minutes 4 seconds**. |
| Final source integrity | Exact pinned HEAD and empty tracked, untracked and ignored-inclusive status. An independent comparison recomputed the Git blob digest of each of the 45 tracked paths and matched all executable mode bits to the pinned tree. |
| Test environments | Linux `7.2.15-1-omarchy` on x86-64. Local CPython 3.14.8 and 3.12.16. Tests ran with an empty inherited environment, a fresh temporary home and workspace, and isolated Linux user, PID and network namespaces. |
| Evidence boundary | Source and generic lifecycle, state, storage and resource behavior. A fake Docker executable, synthetic browser handles and a recording MCP decorator were used where the distribution runtime was out of scope. The review made zero Docker-daemon, browser, endpoint, account, provider or registry calls and ran zero product-domain workflows. |

Drost Community Edition packages a local tool server for an external MCP client. The client owns agent progression and task coordination. The server owns tool registration, per-call execution, engagement namespaces, persisted artifacts, and selected session state. This boundary explains both the simple deployment and the places where process cleanup, concurrency and recovery still need server-side decisions. The open source scope is explicit in `README.md:54–58`, `README.md:114–168` and `README.md:277–286`.

The implementation review covers the pinned Python sources, the container entrypoint, the installer and the relevant source tests. Browser inspection covers process and session ownership and generic event persistence. Model decisions, user interface behavior, bundled utility behavior, images and release artifacts remain outside the measurement boundary.

| UTC checkpoint | Active work |
| --- | --- |
| 07:55:33–07:57:02 | Read the evaluation protocol, confirmed the commit and clean tree, mapped the package and test surfaces, checked local runtime availability and ran scoped repository units. |
| 07:57:02–07:59:13 | Built process-group cancellation controls, independently verified child state and signal delivery, exercised persistence and faulted writes, and reopened stored state from another interpreter. |
| 07:59:13–08:01:39 | Traced async manager allocation and registry mutation, injected browser-handle and journal failures, and exercised installer transitions in an independent fake engine. |
| 08:01:39–08:04:43 | Verified the source registration count and readiness predicate, traced CPython startup and cancellation, compared parent death to graceful teardown, and applied bounded resource pressure. |
| 08:04:43–08:08:38 | Wrote the architecture and initial findings, constructed independent multi-process storage controls on two filesystems and isolated the installer signal disposition in a Bash counterfactual. |
| 08:08:38–08:10:01 | Audited the repository fixtures and stdio readers, reproduced before/after publication crashes, corrected a raw file control, and measured stable versus transient output allocations. |
| 08:10:01–08:13:12 | Wrote the measurement audit and post-mortem, tested cold-start serialization and cancellation in the manager, separated queued and running worker cancellation, and ran competing installer and lock controls. |
| 08:13:12–08:19:00 | Recorded runnable reproductions, ran them from the report, investigated a stopped installer and nested PID namespace teardown, tested independent cleanup ownership and compared both dispatch adapters with generic input. |
| 08:19:00–08:21:01 | Checked private descriptor lifetime, audited report links and source ranges, verified all 45 source blobs against the commit, and replayed cancellation under an independently installed AnyIO runtime. |
| 08:21:01–08:23:51 | Replayed appendix commands with both explicit interpreter versions, audited the final adapter and engagement-lifetime wording, and corrected a namespace capability issue in the real filesystem permission control. |
| 08:23:51–08:25:37 | Repeated permission checks on Btrfs, proved the one-attempt dispatch contract on explicit failure, replayed the report's shell and Python blocks, and verified required headings, source anchors, HEAD, status and tracked file content. |

## 2. Core architecture and end-to-end control/data flow.

~~~text
External MCP client                         Docker-managed container
  conversation, model, approval               PID 1: tini -> sleep infinity
  selects engagement and next call            named volume mounted at /workspace
  launches docker exec -i ------------------> drost-mcp process for that client
                                                FastMCP over stdio
                                                import-time tool registration
                                                |
                       +------------------------+-------------------------+
                       |                        |                         |
                 catalog adapters         native functions          BrowserManager
                 explicit argv            async or thread           in this process
                 subprocess session       await result              driver -> browser
                 child stdout/stderr           |                    -> context/page
                       |                       |                         |
                       +------ engagement filesystem and artifacts -----+
                                                |
  consumes result <----------------------- structured MCP reply
  decides whether to issue another call
~~~

### Deployment, supervision and ownership

The installed executable maps to `drost_ai.server:main` in `pyproject.toml:25–26`. The Docker image puts the package venv on `PATH`, sets `DROST_WORKSPACE=/workspace`, declares a volume, and uses `tini -- sleep infinity` for its primary process. The image health check invokes a separate `drost-mcp --self-test` process every 30 seconds. The persistent container is an execution environment. Each client launches its own server with `docker exec -i` and speaks stdio over that process. Separate client launches therefore have separate Python registries and browser managers while reading the same mounted volume. The container-wide init, per-client server, per-call process group, and filesystem volume have distinct lifetimes. [Dockerfile](repos/drost-ai__drost-community/Dockerfile:241), [README.md](repos/drost-ai__drost-community/README.md:114)

The installer is an external Bash supervisor. It validates architecture and version, requests the tagged image, provisions or reuses the volume, stops and renames a labelled predecessor, starts the replacement with `--restart unless-stopped`, and verifies it using the inventory command. Success removes the backup. After the rename, a trap attempts restoration on failure or interruption. Uninstall removes a managed container and ordinarily preserves the workspace. The explicit purge path additionally checks the volume label. Container restarting under Docker's restart policy makes new client exec sessions possible. A client process and its in-flight tool call still require the client to reconnect or decide what to do next. [install.sh](repos/drost-ai__drost-community/install.sh:101)

### Planning, tool interface and dispatch

`server.py:27–41` constructs FastMCP and configures client-facing instructions. `main()` selects self-test JSON, executable catalog JSON, or `mcp.run(transport="stdio")`. FastMCP owns the wire-level lifecycle. The source's input boundary is a set of typed callable signatures, with structured output requested on the tool decorators. The external client owns its model and conversation state, tool choice and call sequencing. `workflows.py:93–132` returns plan or recommendation data from static templates and deterministic objective matching. The result explicitly requires a separate call per step. `workflows.py:135–162` sorts or summarizes supplied data and returns it to the client. The call graph ends at the returned result and leaves the next decision to the caller. [server.py](repos/drost-ai__drost-community/src/drost_ai/server.py:514), [workflows.py](repos/drost-ai__drost-community/src/drost_ai/workflows.py:93)

The executable tool sources are immutable `ToolSpec` records generated from grouped inventory entries. Catalog construction rejects duplicate tool names. Full mode creates a closure and tool declaration per selected entry at import. Startup configuration can narrow individually registered categories. Compact mode keeps the fixed tools and offers exact-name dispatch against the whole executable inventory through the generic execution adapter. Discovery normally returns counts and accepts explicit filters or a request for contracts. The full and compact surfaces share the same underlying executor. A manager present on the SDK object supplies the fixed-tool names and schemas used for discovery. The architecture has one extension point for command inventory, another for application-specific typed functions, and a shared path for process semantics. [catalog.py](repos/drost-ai__drost-community/src/drost_ai/catalog.py:183), [server.py](repos/drost-ai__drost-community/src/drost_ai/server.py:44)

On an executable call, the server resolves the selected engagement and working directory, checks availability on `PATH`, validates argv elements and constructs the environment. `create_subprocess_exec` creates the child in a fresh POSIX session, with separate stdin, stdout and stderr pipes. One `communicate` awaits drained output and exit. The result contains argv, working directory, exit status and decoded output. Lookup failure and spawn failure return different response shapes. The regular external adapter passes literal argv. The explicit shell and Python wrappers choose their own interpreter and then reuse the same process runner. `CancelledError` received while awaiting communication enters process-group cleanup and is re-raised to the calling layer. [executor.py](repos/drost-ai__drost-community/src/drost_ai/executor.py:63), [execution_tools.py](repos/drost-ai__drost-community/src/drost_ai/execution_tools.py:11)

Fixed functions use three paths. Short return-value helpers run synchronously. Most workspace and native operations use `asyncio.to_thread` through an async tool wrapper. Browser operations remain async and await the process-local manager. AST inspection counted 52 fixed declarations, including 27 thread-backed adapters and 13 direct manager adapters. These methods, FastMCP request handling, the asyncio event loop, the default executor and the OS supply execution scheduling. The source's commitment boundary is one tool call. Job admission, a durable queue, step retries, a run journal, recovery of in-flight calls, and a scheduler for future work would require additional contracts. Current retry decisions belong to the client. [server.py](repos/drost-ai__drost-community/src/drost_ai/server.py:248)

The synthetic dispatch comparison verified the one-attempt contract on failure. The generic child wrote one local attempt marker and exited 7. A named wrapper invocation appended one marker and returned the failure. An explicit generic dispatch of the same fixture appended exactly one further marker and returned the same result. Artifact count recorded the number of actual processes independently of the reported code. `server.py:91–108, 227–235` and `executor.py:106–124`.

### State, persistence and events

| Lifetime | Owner and representation | What a new process can recover |
| --- | --- | --- |
| Model conversation and engagement selection | External client retains the selected engagement ID | The server can enumerate IDs so the client can select again. Conversation and plan progression are client concerns. `README.md:142–158`. |
| MCP transport and call | Client-launched FastMCP process, coroutine or worker thread | A new stdio server reconstructs its tool surface at import. A fresh call is a new execution. `server.py:27–58, 116–126, 514–528`. |
| Subprocess | `execute_tool` creates the OS session and returns the captured result | The process outcome is delivered to the current client. Durable output depends on a tool or caller writing artifacts. `executor.py:84–124`. |
| Engagement | `engagement.json`, artifact directories and a synthetic UTC-date/UUID ID | The manifest and files reopen from the mounted volume by ID. Creation uses a hidden staging directory and publishes it with a rename. `engagements.py:36–58, 61–150`. |
| Persisted HTTP configuration and history | Session JSON and separate JSONL file beneath an engagement | Metadata and history are re-read by ID. A request reconstructs transient client state from disk, performs work, then saves state and appends a history entry in separate operations. `http_workbench.py:24–65, 119–165, 197–269, 326–339`. |
| Browser context and event view | One process-local `BrowserManager` with live Playwright handles and an in-memory event list | A new manager starts with an empty registry. Artifacts such as the JSONL event file remain on the shared volume. `browser.py:21–62, 83–174, 327–343`. |

Engagement creation validates inputs, stages subdirectories and manifest, then publishes the complete namespace. A path-sensitive call loads the manifest and resolves its working path beneath the selected root. Where the server controls file functions, it reserves the top-level manifest from replacement and deletion. The workspace workers read and write text and can enumerate artifacts without an index service. Metadata about a declared target belongs to the manifest. The documented trust boundary for arbitrary code is the container, and separate trust domains use separate containers and volumes. [engagements.py](repos/drost-ai__drost-community/src/drost_ai/engagements.py:36), [workspace.py](repos/drost-ai__drost-community/src/drost_ai/workspace.py:42), [README.md](repos/drost-ai__drost-community/README.md:165)

The engagement management contract consists of create, list and get, with persistent IDs and a creation timestamp. The browser close description alludes to an engagement close operation, while the registered management surface provides no engagement completion state or close transition. An engagement therefore remains a selectable file namespace after client or browser closure. The volume and its retention choices govern its overall lifetime. `server.py:248–260, 403–405`, `engagements.py:96–109, 112–134` and `install.sh:105–124`.

Browser creation lazily obtains a driver and browser, allocates a context and page, creates an artifact directory, attaches callbacks and inserts the session in the registry. Browser get/list depends on live page state. Close awaits context closure and then removes the session ID. Request and response callbacks put an event in memory and append a JSON line synchronously. The HTTP history has one line per recorded result and is read back from disk. These records make specific tool state inspectable. Generic application observability comes from the structured responses, the self-test, and a source-defined on-demand process snapshot. Request-level metrics, cleanup accounting, and an application event bus would be new interfaces. The published container health check is an independent inventory operation, with its own timeout and retry settings. [browser.py](repos/drost-ai__drost-community/src/drost_ai/browser.py:64), [http_workbench.py](repos/drost-ai__drost-community/src/drost_ai/http_workbench.py:197), [native_tools.py](repos/drost-ai__drost-community/src/drost_ai/native_tools.py:16)

## 3. Why the design works and its governing invariants.

| Invariant or intended contract | Code mechanism and its practical limit |
| --- | --- |
| Calls identify their namespace explicitly. | The client retains the engagement ID and durable session calls additionally take a session ID. Engagement IDs combine a UTC date and a UUID. Human-readable names live in the manifest. The browser also checks that the ID belongs to the supplied engagement. Different clients can select independently. Multiple clients that intentionally share an ID also share its files. `engagements.py:14–33, 61–109, 137–150` and `browser.py:58–62`. |
| A newly visible engagement has its manifest and initial directories. | Creation reserves a hidden directory, writes the initial tree, and replaces within the same parent. Discovery filters out staging names. Six simultaneous independent processes published six complete IDs in the test. The publication invariant covers visibility on the tested filesystem. Recovery of an unpublished staging tree and durability through OS or storage loss need separate guarantees. `engagements.py:79–125`. |
| A registered executable call represents one deliberate process invocation. | The catalog carries the executable, caller input carries the argv list, and the spawn API receives the executable and tokens separately. Caller-selected Bash or Python invocation is an explicit alternative interface using the same lower-level owner. `catalog.py:10–23`, `server.py:91–126, 227–245` and `executor.py:14–22, 72–94`. |
| Execution can wait without monopolizing the asyncio thread. | The process work and pipe reads are asynchronous. Most blocking native operations run via a worker thread. One long process and a quick process completed independently in the unit. Shared descriptors, memory, CPU, volume throughput and thread capacity still affect all clients. `executor.py:86–112` and `server.py:248–385`. |
| The process group is the initial cancellation unit. | `start_new_session=True` establishes an owned group and ordinary cooperative cancellation sends TERM to that group. The code escalates when the leader wait times out. The control verified correct signal delivery in the live-leader case. The production cleanup currently uses direct-child state as a proxy for the group, which limits this invariant in several exit orders. `executor.py:45–60, 86–112`. |
| Long runners and complete outputs are supported. | No app-level deadline or truncation is applied by the runner. The client decides acceptable elapsed time and consumes a complete result. Separate stdout and stderr make accumulated diagnostic output available without mixing it into stdio protocol traffic. Server and container capacity still bound the work in practice. `README.md:78–84` and `executor.py:71, 106–124`. |
| The public tool surface is configuration-derived and domain work is explicitly requested. | Startup mode and category selection control direct declarations. The generic exact lookup uses the full immutable executable inventory. The smaller declaration surface reduces initial schema load while preserving dispatch reachability. Planning returns static suggestions and imposes no scheduler. `server.py:44–58, 116–126, 129–235` and `workflows.py:93–103`. |
| Container replacement and data replacement have distinct intent. | The script has separate managed-container and managed-volume checks, passes a named volume into the new container and requires explicit purge. Most upgrade failures after a successful backup rename can restore the old container identity. Signal handling and precise recovery state are important to making this intent reliable. `install.sh:51–70, 105–124, 134–166`. |

The design fits a local client that already has its own planning, approval, concurrency and deadlines. A per-client stdio process keeps protocol lifecycle and browser handles local to that client, while the shared volume offers resumable artifacts and file-based sessions with little operational setup. The same division means that exchanging the agent client leaves the artifact contract largely intact and that multiple clients can still contend for mutable files or machine resources. These are consequences of choosing shared volume and client-scoped processes together.

## 4. What it does well and poorly, with source evidence.

### Strengths

- **Clear ownership boundary.** The image is usable as a shared execution environment with a distinct process per client and no application listener. The container, execution request and storage volume can be reasoned about separately. Documented responsibility for deadlines, approval, artifact retention and browser-session closure gives an external client an integration contract. `README.md:60–84, 114–168, 186–195, 366–368` and `Dockerfile:253–263`.
- **Small and reusable execution core.** Literal argv, workspace resolution, environment validation, one async spawn path and separate stdout/stderr are all in one place. Both explicit interpreter adapters reuse it. Tests establish argv fidelity, concurrent availability, output completeness, normal cancellation propagation and several input contracts. `executor.py:14–41, 63–124`, `execution_tools.py:11–67` and `tests/test_executor.py:13–124`.
- **Useful stateless discovery.** Declarative catalog records and duplicate rejection make assembly predictable. Compact mode preserves the same underlying inventory without paying for all direct registration contracts. The source declares 159 direct tools by default and 52 in compact mode. The calculations matched recorded decorators under the fixture. `catalog.py:183–210` and `server.py:44–58, 116–126, 129–235`.
- **Low-dependency storage and portable recovery.** Durable identifiers and ordinary files allow offline operator inspection and independent process re-entry. Publication stages the initial engagement as a unit. A new interpreter reopened namespace, session configuration, history and workspace bytes. `engagements.py:79–109`, `workspace.py:30–56` and `http_workbench.py:45–65, 119–126, 326–339`.
- **Pragmatic deployment.** Ownership labels provide guardrails for the installer. Default uninstall preserves data. The image source separates distribution dependencies, Python dependencies, workspace data and PID 1. Release automation builds native AMD64 and ARM64 platform images, generates digest-bound provenance and software inventories, and assembles the manifest after both platform artifacts. These are source properties. `install.sh:101–125, 134–166`, `Dockerfile:3–80, 241–263` and `.github/workflows/publish-container.yml:64–85, 117–135, 155–182, 247–284`.

### Findings

**1. A canceled request can finish while its process group still has live work.** The cleanup returns immediately when the direct child's return code is already set. A child that inherited a pipe can keep `communicate()` pending after the leader exits. In both Python versions, the canceled request returned while the descendant was still live in the original group. Manually signaling that same group from the isolated controller terminated the ordinary descendant. A second case proved that delivery of TERM and reaping the leader are different from waiting for the group. An ordinary worker performing post-TERM cleanup with separate stdio was still live after the request returned. One uncooperative leader exercised the expected two-second TERM-to-KILL escalation. A second cancellation while that wait was active interrupted cleanup before escalation. The root cause is ownership expressed through the direct child's `returncode` and `wait()`, with cleanup running on the same cancelable request task. The README's process-group claim applies to a narrower case than its wording indicates. `executor.py:45–60, 86–112` and `README.md:78–81, 172–177`.

**2. Other exit boundaries are outside the executor's cleanup region.** UTF-8 encoding of stdin takes place after spawn, inside a region that only handles cancellation. An encoding failure made the call fail while its spawned process was live. This direct-call input is a Python string containing an isolated surrogate. Actual SDK transport and input validation for it remain unverified. A controlled startup delay inside the real CPython subprocess transport also showed that a startup cancellation can kill the direct child before returning the Python `Process` while leaving a descendant live. The scheduler gate establishes a possible ordering. Its natural frequency is unknown. In a separate supervisor test, SIGTERM of the calling process left a running child adopted by PID 1. The graceful-exit control canceled and reaped its child. The test demonstrates Linux process behavior. FastMCP and Docker EOF handling remain distinct integration questions. The source supplies no app-level lifespan hook or run registry to close this ownership gap across the client-server lifecycle. `executor.py:63–112` and `server.py:27–41, 514–528`.

**3. Persisted session updates have two independent concurrency hazards.** Each update reads an entire snapshot, modifies fields and writes it back. Two disjoint updates both returned successfully, but the later write restored the former value of the field it had not changed. Serial execution retained both changes. Independently, a single fixed staging filename per session permits one writer to consume the other's staging file. With interleaving controlled immediately before real rename in two different processes, the first writer acknowledged its intended state while disk already held the second writer's snapshot, and the second rename failed with `ENOENT`. A distinct-session control succeeded. A stress sample without an internal barrier also produced unreadable final JSON. Separate staging names corrected which bytes each process published but preserved the stale-snapshot overwrite. Cross-process serialization around the whole update corrected both effects in its control. A history append is a separate commit from the configuration update, so it requires its own consistency policy. `http_workbench.py:37–59, 129–165, 197–200, 248–269` and `server.py:369–385`.

**4. The installer can remove the recovered predecessor on a signal path.** A normal self-test failure after backup rename restored the previous container in the fake engine. In the signal test, TERM arrived while the fake verification command was awaiting release, and the command later returned success. Bash ran the signal trap, restored the predecessor, continued into backup removal using the same backup name, hit an error because the backup had already been renamed, then ran the ERR trap. The second restoration removed the recovered container and its rename and start failed. The resulting simulated state had the named volume and zero containers. Verification failing on release also triggered two restores. A counterfactual signal trap that disarmed the traps before restoring and exited immediately ran one restore and retained the previous identity under both command statuses. The fixture gates command and signal timing and establishes the shell transition, with actual daemon behavior outside the test. Related gaps include failed backup rename after stopping the old instance, unsuccessful fresh self-test leaving a replacement running, and best-effort restore steps whose outcomes are discarded. `install.sh:61–70, 138–166`.

The same rollback also acts on a shared mutable name. With A paused immediately before its candidate creation, B saw a vacant name, installed successfully and had its identity verified by the controller. A's resumed candidate creation failed on that occupied name. A's rollback removed B and restored the old identity. The solo A control succeeded, and a per-name lock around both complete installs let them finish serially with B active. An abrupt installer exit after a successful backup rename also left an old stopped backup after the next healthy install. All operations were against a stateful fake engine. The operational concern is stale ownership and missing recovery state across name transitions. `install.sh:61–70, 141–166`.

**5. Browser handle allocation and list traversal lack coordinated lifecycle transitions.** Two cold creates can both pass the cached-browser check and launch distinct drivers. The singleton subsequently references the most recent launch even though contexts exist under both launches. Closing those sessions closed their contexts in the fake but left both drivers untouched. Serial and lock-guarded cold starts both used one launch. Page creation, route registration and artifact-directory failures left a context open before any ID was published. Cancellation after context allocation had that same outcome. A metadata failure after publication left a registered ID despite an error from create. List awaits metadata during live dictionary iteration, so a controlled concurrent close invalidated the iteration. Taking a shallow snapshot of the registry avoided structural invalidation and still attempted to access a closed ID. A disconnected session remained in the registry after reconnect and could abort listing in the stub. These are confirmed application control-flow results against faithful async handle interfaces. Actual driver processes, Chromium disconnection behavior and child cleanup by the SDK were outside runtime measurement. `browser.py:36–62, 73–99, 140–174` and `server.py:389–407`.

**6. File-based recovery is less defensive than initial publication.** An engagement with valid JSON and the correct ID but a missing or ill-typed timestamp could abort the full listing. Ordinary malformed JSON was reported per record. HTTP state listing similarly skipped malformed JSON syntax but raised on a valid array, and direct get had different handling. A torn history tail could make the whole valid prefix inaccessible through the history reader while the metadata endpoint counted the incomplete line. Manifest staging left a hidden directory after a forced final publication failure and no later reconciliation found it. Workspace overwrites modify the existing file directly. Both an injected partial-write failure and an actual small per-process file-size limit left a truncated replacement where the prior file had been valid. A dangling link inside the namespace raised from `stat()` and stopped the workspace listing. These conditions are plausible after tool output, manual data repair, concurrent mutation or storage errors and should map to an explicit recovery policy. `engagements.py:36–50, 94–130`, `workspace.py:11–27, 42–56` and `http_workbench.py:52–59, 104–126, 326–339`.

**7. Cancellation and admission mean different things across tool families.** Canceling a waiter for a running `to_thread` call ended the await and the underlying worker committed its deterministic file write later. The executable path has a cancellation hook and a separate set of cleanup limits. The browser path depends on awaited SDK operations and context lifetime. Per-call output and native histories can grow with workload size. A lower test file-descriptor limit yielded real spawn `EMFILE` errors at a forced concurrent width. Narrower waves and a larger limit completed successfully. The baseline/post descriptor count matched in these ordinary successful and failed spawn cases. This demonstrates concurrency sensitivity under a known test quota. `server.py:248–385, 389–450`, `executor.py:86–124` and `http_workbench.py:326–339`.

**8. Health and event reporting omit parts of the actual lifecycle.** The inventory command's JSON can say `healthy` with missing executables. The CLI separately exits nonzero for that condition. Browser runtime and workspace paths appear as inventory fields. A fixture where every catalog executable resolved but browser dependencies and the workspace were absent exited zero under the source predicate. Image readiness itself remains outside that test. Browser callbacks update the in-memory ledger before the file append and clear it before truncating disk. Injected file failures made the views diverge in opposite directions. This is a recoverability issue when one is treated as authoritative. `server.py:488–524`, `Dockerfile:257–258` and `browser.py:103–128, 327–339`.

## 5. Core-code quality: decomposition, state, concurrency, errors, types, tests, observability, extensibility, and maintainability.

| Dimension | Review |
| --- | --- |
| Decomposition | Small modules own catalog assembly, subprocess execution, namespace validation, workspace I/O, persisted sessions and browser handles. That is a useful natural boundary for generic tests. `server.py` is primarily registration and delegation. Splitting it by tool family would be optional. Defining explicit process and storage lifetimes would provide more value than moving wrappers between files. `server.py:14–24, 91–126, 248–450`. |
| State and recovery | UUID IDs, predictable paths and staging for initial engagement creation make the data model inspectable. Schema versions are stored, while validation primarily checks identity. List and get do not share a complete decoder or malformed-record policy. Local file replace, snapshot mutation and JSONL append are separate operations. `engagements.py:36–58, 94–125` and `http_workbench.py:45–65, 84–126, 129–165`. |
| Concurrency | Independent async subprocess setup and `to_thread` preserve responsiveness on ordinary work. Caller requests can advance concurrently within a process and separate clients can change the same volume. The tested risks are ownership gaps on cancellation, a thread that commits after its waiter cancels, shared scratch names, stale snapshots, and browser-context races across awaits. Existing global configuration and the live manager are process-scoped. `executor.py:45–60, 84–112`, `server.py:248–385` and `browser.py:36–56, 146–174`. |
| Error semantics | A launch attempt may be represented by an availability flag, structured error or process exit status. Input and data errors can be raised, and independent tool families return their own ad hoc fields. Combining them requires method-specific knowledge. Explicit error codes for invalid arguments, missing dependencies, startup failure, cancellation disposition, storage conflict and partial commit would be more dependable for a caller. `executor.py:72–124`, `engagements.py:36–49` and `http_workbench.py:52–59, 104–126`. |
| Types | `ToolSpec` is an immutable slotted dataclass and `BrowserSession` has explicit runtime handles and fresh containers of events per instance. Most persisted documents and outputs are `dict[str, Any]`, leaving required fields and variants implicit. `_external_tool` annotates its return as a callable returning a dict even though it constructs an async function. An awaitable-aware annotation and typed persisted data would make boundaries easier to check. `catalog.py:10–18`, `browser.py:21–40`, `server.py:91–113` and `engagements.py:36–58`. |
| Observability | The structured result captures process exit code and streams. Engagement and session IDs tie files to work, and stored records have timestamps. The health response conveys inventory, and the process snapshot is a point-in-time view. Time to spawn, active call count, retained bytes, cancellation/cleanup disposition and reasons for storage recovery are absent from the server's result contract. The client and SDK may supply their own telemetry independently. `executor.py:114–124`, `server.py:488–524`, `http_workbench.py:251–269` and `native_tools.py:16–39`. |
| Testing | Repository units provide core positive coverage and checks on distribution source. The cancellation test checks the canceled task but lacks an explicit process-state assertion. The installer fixture uses a single active container marker and its generic `rm` removes that marker even when invoked for a backup name. The repeat-install assertions validate intermediate commands and volume preservation. Evidence for resulting active identity requires a separate fixture and state assertions. `tests/test_executor.py:54–91` and `tests/test_installer.py:30–60, 109–131`. |
| Extensibility | A new executable can use the same inventory and adapter contract. A native tool can add a registered callable and the tests can verify the exposed shape. Coupling surfaces include manual category/count conventions, private FastMCP manager fields, and continued compatibility with the packaged SDK. The registry fixture's normalized compact mode suppressed direct declarations as designed. An unsupported mode string used full defaults and was reported verbatim, while invalid categories failed import in full mode and were unused in compact mode. A source-owned registry or public SDK enumeration could derive counts and report a normalized startup configuration. `server.py:44–88, 133–172, 200–217` and `pyproject.toml:19–23`. |
| Distribution | The image pins base digests, separates build stages and uses the distro MCP package plus a venv that can see system packages. The project metadata describes a broader Python dependency range. Reproducing the exact supported runtime requires the image/digest and actual packaged dependency versions. Source and local Python units cover core semantics but establish neither ARM64 runtime parity nor MCP support across the declared range. `Dockerfile:3, 43, 62, 76, 141–150, 241–258` and `pyproject.toml:11, 19–23`. |

The recurring maintainability issue is an absent explicit owner for transitions that cross an await, move between two stored objects or survive a failed supervisor command. Function size is generally manageable. The consequential failures emerge when local success is mistaken for completion of the enclosing lifecycle, such as leader exit for group completion, rename for a transaction, and process availability for usable service readiness.

## 6. Executed tests/experiments and their limitations.

| Experiment | Observed result | Evidence boundary |
| --- | --- | --- |
| Scoped repository units | **30 passed** on each interpreter in isolated namespaces, comprising 7 executor, 3 engagement, 6 installer, 8 static distribution and 6 catalog tests. The PID 1 test wrapper reaped one adopted child with status `-15` on each interpreter after the standard cancellation test. | Scope selected from source after reading the test bodies. The installer called its bundled fake engine. Tests inventory catalogs and templates without dispatching domain workflows. |
| Subprocess completion and cancellation | Ordinary short work completed while long work waited. One live-leader group canceled cleanly. An already-exited leader with an open inherited pipe and independently a worker doing TERM cleanup with closed pipes each left a live descendant at task return. Repeated cancel returned before escalation. Single cancellation with a blocked leader escalated at about 2.002 s. | Real CPython processes and Linux signals, readiness synchronized by local files and measured with `/proc` and `waitpid`. The test harness owns the PID namespace and reaps all fixture children. |
| Launch failures and parent lifecycle | Missing binary created an unavailable result, file as cwd produced `ENOTDIR`, and nonzero exit returned code 7 with stderr and replacement decoding of invalid UTF-8 output. Valid UTF-8 stdin arrived as four bytes. An isolated surrogate failed encoding after spawn. A gated transport-start cancellation reaped the direct leader while the worker survived. Graceful generic supervisor exit canceled its worker, and SIGTERM of the supervisor left a worker adopted by PID 1. | Real generic local child programs and an instrumented CPython transport path. No inference about SDK validation of surrogate input, production startup race frequency or actual Docker exec shutdown. |
| Output buffering, descriptor and file-size budgets | Both streams returned the full 128 KiB, 512 KiB and 2 MiB aggregate payloads. Immediate `tracemalloc` samples grew with payload. Width 20 with soft `RLIMIT_NOFILE=64` returned 13 successes and 7 `EMFILE` spawn failures. Four waves of width four at the same limit all passed, and all 20 passed at limit 256. Baseline/post FD counts were 7/7. A 4 KiB file-size limit returned `EFBIG` and left a 4 KiB prefix. | Deliberately reduced process-only limits. These are causal controls, not load limits for a normal container. Traced Python allocations exclude process-tree RSS, SDK serialization and stdio transport. |
| Namespace and workspace persistence | Another process reopened the workspace text, engagement ID, HTTP session ID and synthetic history. Six independent processes published six complete namespaces. Corrupt timestamps could stop a list. Injected publication failure retained hidden staging, injected overwrite failure left a prefix, and a dangling local link halted both listing modes. | Real local file operations with controlled fault injection for selected syscall boundaries. Tmpfs and process restarts expose visibility and parsing behavior. Power loss, production volume durability and quota are outside the test. |
| HTTP-session storage controls | Both disjoint concurrent updates could acknowledge while one reverted. Shared staging rename returned `ENOENT` under a separate schedule. Serial and distinct-session cases passed. A malformed manifest and partial history affected list/get/history differently. | Metadata creation/update and synthetic history only. No HTTP request, listening server or external session ran. |
| Running thread cancellation | The exact workspace write wrapper AST, with only its MCP decorator removed, delivered `CancelledError` and then completed a real write after the blocked worker was released. | The worker-call boundary is application code. Timer, wire cancel and SDK integration are unmeasured. |
| Browser manager and event lifecycle | A two-caller cold start launched two fake drivers, while serial calls used one. Allocation failure, close/list race, stale IDs, ephemeral registry and two memory/file divergence directions were confirmed on fake handles. | Test doubles implement the relevant async interfaces. Synthetic callbacks use local metadata. No browser executable, UI, target, network call or SDK was used. |
| Installer lifecycle | An independently implemented fake engine modeled active names, container identity and running state, volumes and command-specific errors. Normal paths and ordinary rollback passed. Signal re-entry removed the restored name. Fresh verification failure, rename failure, stop failure, failed restore start and refused purge exhibited the expected partial states. | Bash and filesystem execution were real. Only the fake command was resolved as Docker. Its behavior isolates shell transition logic and cannot certify actual Docker daemon, restart, privileges or image semantics. |
| MCP registration and inventory | A recording decorator and AST check agreed on 52 fixed functions. Counts were 159 full, 52 compact, and 66 for a 14-entry family filter. Unfiltered discovery returned zero entries and comprehensive metadata retained 159. Two readiness cases showed `status=healthy` when exits were 0 and 1, respectively. | A source-backed fixture captured function signatures, registration, availability lookups and CLI control flow. It does not exercise real schema validation, JSON-RPC, wire cancellation or an installed MCP SDK. |
| Cross-process storage and two filesystems | On tmpfs and Btrfs, shared staging could acknowledge different bytes from the bytes it published. Independent staging avoided that error and still lost a stale disjoint update. In four 256-trial ungated pairs of writers, locking around the full update produced 256 merged results in every pair. Direct updates produced a mixture of lost changes, rename failures and some invalid final JSON. | Two worker processes with real replace calls. Simultaneous submission increases overlap. The distributions identify plausible failure forms and give no real-world incidence estimate. |
| Commit boundary and damaged JSON | An abrupt subprocess exit before directory or session replacement left old visible state and scratch. Exit afterward left published state without a return. Repeating an unacknowledged create published two records with the same logical label. Two raw descriptors reproduced a published JSON trailer. A generic transactional store committed state and journal together and rolled both back on process death before commit. | `os._exit(73)` simulates abrupt interpreter termination. Tests ran on tmpfs and Btrfs. This establishes visibility and a recovery design option. Power-loss safety would require a separate storage experiment. |
| Fixture cross-check | The repository's repeat-install assertions passed with the fake active container marker absent. Both smoke helper readers missed an ID already in the Python text buffer, while a raw byte control read both messages. | Only generic fixture methods and extracted reader functions were invoked. The two actual smoke test main routines stayed outside scope. |
| Traced allocation lifetime | For two 1 MiB streams, the immediate delta was about 4.21 MB and the settled delta about 2.10 MB with the returned value held. Releasing the result returned below 1.4 KiB over baseline. Draining both streams to files instead preserved the bytes with a smaller traced peak. | Warmed interpreter, event-loop settling and garbage collection between samples. These are Python allocation measurements. Scheduling, allocator behavior and capture machinery affect the peak. |
| Process and descriptor lifetime after return | Counting actual descriptor links with no retained `Process` reference gave 6, 8, 8 and 6 across baseline, request in flight, canceled return and reaped group. The extra two were pipes. An independent shielded cleanup task could still reach a terminal result after a second cancel of the waiter. A nested PID namespace's worker and init disappeared when that init exited. | No actual Docker or Tini process. Descriptor numbers here exclude the ephemeral directory-iteration descriptor. The earlier 7/7 comparison included it. |
| Cancellation under an alternate local scheduler | Under AnyIO 4.16.0's asyncio backend, a single task-group cancel returned with the worker still alive. A standard asyncio task on the same loop let the worker finish its post-TERM cleanup. An in-memory counterfactual with a shielded AnyIO cleanup scope also reached the expected terminal exit. | Available only on the local 3.12.16 interpreter. Measures scheduler semantics in a generic task group and leaves installed FastMCP behavior unverified. |
| Real permission errors | With DAC override capabilities dropped, mode-000 engagement manifest reads produced raw `EACCES` and an application `ValueError` carrying that cause. HTTP get raised `PermissionError` and list skipped the unreadable record. A mode-0444 workspace overwrite failed before truncating it. Restoring the file modes recovered all three paths. | Tested on both filesystems and interpreters after determining that mapped namespace root could bypass those bits. Actual Docker volume permission configuration remains an integration concern. |
| Installer interruption and restart | Killing the installer immediately after the fake engine committed a rename left only the stopped rollback identity. A new invocation started a healthy replacement and retained that stale rollback entry. A normal upgrade removed its backup. | The test killed only a verified child installer PID within the private namespace. The state transition involved an offline fake name registry and a retained workspace fixture. |
| Direct and compact dispatch | A one-entry synthetic catalog and benign Python child produced identical complete results through the named closure and exact-name generic dispatch. Literal argv, stdin, selected subdirectory, tool name and status were asserted. An unknown test name raised before spawn. Each explicit failed dispatch appended exactly one attempt and returned exit 7. | One substitute catalog entry exercised the real executor and wrapper bodies. The recording decorator supplies metadata only. The pinned package's 13 Python modules also parsed using the 3.11 grammar and the shell passed `bash -n`. |

The published image, Docker daemon, real MCP library and real Chromium launch are outside the test scope. Both local Python environments lacked MCP and Playwright. The image declares these dependencies through its package/venv setup, so host absence is an environment fact. The integration smoke scripts exercise broader product behavior, including a local HTTP server, and were inspected as test surfaces only. `README.md:469–489`, `tests/mcp_smoke.py:50–78` and `tests/mcp_epic_smoke.py:7–23` explain why the isolated subsets and fixtures are the appropriate evidence here.

## 7. Measurement audit for every negative or surprising result, including alternate commands or code-path checks used to rule out setup mistakes.

### Process ownership, timing and memory

1. **A return from the cancellation hook can precede group completion.** The controller read each PID from an atomically published ready marker, checked `os.getpgid(worker) == leader_pid` and verified that the process was live before cancellation. In the leader-exit case it waited for the actual direct `returncode == 0` while the request still awaited inherited pipe EOF. A `/proc/PID/stat` state of `S` established that the remaining worker was live. A `Z` state in the cooperative control meant terminated and awaiting reap. The controller's direct TERM to the same group killed the worker; this rules out bad PID, wrong group, signal permission, and a nonresponsive worker in that case. In the separate-pipe case a marker proved TERM delivery before the worker completed a normal cleanup handshake. The control then let that cleanup finish. With one remaining direct child whose TERM handler waited, the actual fallback killed it at approximately 2.002 s. Both Python versions passed those controls. The first branch roots in `executor.py:47–48`. The other branches root in relying on direct-child `wait()` at `executor.py:53–60`. The readiness protocol provides ordering instead of inferring it from a sleep delay.
2. **Cancellation arrives at different ownership phases.** In the repeat case the second cancel followed a real TERM acknowledgment and preceded the end of the configured grace period. The corresponding single-cancel case performed escalation. This distinguishes cancellation interrupting cleanup from a failed first signal. For startup, the controller first let CPython connect the real subprocess pipes, then delayed the waiter that would return its `Process` object. The library killed the direct child when that waiter was canceled. This matches installed Linux asyncio source in `_make_subprocess_transport` and `BaseSubprocessTransport.close()`. The observed direct return status was `-SIGKILL` while the worker was live. The delay is deliberate. It proves the path and its ownership gap when work starts before the object is returned. It supplies no timing frequency for an uninstrumented production spawn. The worker and transport were drained or killed and reaped in the fixture.
3. **Abrupt supervisor exit and workspace restart are different events.** The generic parent received SIGTERM by its own PID within the private PID namespace. The worker's PPID changed to `1` while it remained live in its own group. A separate normal-exit control canceled the same runner and left no worker. Linux's PID 1 adoption behavior and the runner's cancellation path are separate from Docker/SDK integration. A real stdio EOF, protocol-level cancel, container stop and image replacement have different cleanup initiators. Their exact wiring remains for an integration test within the published runtime. Reading `Dockerfile:257–263` and `server.py:514–528` confirms the two invocation paths.
4. **Unexpected encoding failure preceded communication and followed a verified spawn.** The isolated surrogate entered the Python callable and raised `UnicodeEncodeError`. The child wrote its readiness record in the correct directory and was alive. Valid supplementary-plane UTF-8 input produced four bytes in the child. The same binary was resolved and accepted in other cases, expected nonzero exit was represented correctly, and logs used an ASCII-safe harness. This rules out absent executable, permissions or locale as the cause. This is an executor-layer defect. End-to-end acceptance of that value by an installed SDK is unverified. The robust ownership boundary should cover all exceptional exits after spawn even when argument validation normally excludes the particular value.
5. **FD and output results have deliberately different meanings.** Host soft/hard descriptor limits started at `524288/524288`. The test set only the test parent's soft descriptor limit to 64, then repeated with the same tools, working directory and ready protocol at 256. Width four in four separate waves also passed at 64. Seven failures carried actual spawn `[Errno 24]` at width 20 and the final FD count returned to baseline. The diagnostic relates to simultaneous admission and validates an error path. It establishes neither a product default quota nor a steady FD leak. For output, payload lengths were asserted independently of allocation count. `communicate()` retains both full streams, decoding adds result strings, and CPython may keep async intermediates briefly. The initial allocation sample included both kinds of objects. After warming, three event-loop turns and GC, the 2 MiB returned payload held roughly 2.10 MB in the Python heap. Discarding it freed the retained memory, and streaming the identical two pipes to files stayed below 0.65 MB of peak traced allocation in these samples. CPU, transport and container RSS were outside that measurement. `executor.py:86–124` and the Python source locations below explain the difference.

### Store integrity, permissions and concurrency

6. **Persisted session conflicts separate into lost updates and incorrect staging ownership.** A barrier after snapshot read let the first update finish before the second wrote, with each computing from the original snapshot. Both reported success and the disk proved one field reverted. The serial sequence and two different session IDs passed. A distinct barrier immediately before rename made the first writer successfully publish the second writer's stage and made the latter fail on an absent staging pathname. The stage and destination parent were confirmed to be the same valid scratch directory and the final file existed. This rules out a missing mount or a destination path typo. Two full Python processes reproduced the schedule on tmpfs and Btrfs. Same-schedule unique filenames allowed both replacements and still lost one acknowledged update. `flock` around read through write fixed both hazards in synchronized two-process trials. It is a counterfactual, not a guarantee of the production store or every filesystem's locking behavior.
7. **Unreadable stored JSON has a concrete filesystem route.** The ungated workers occasionally left malformed final state. A raw control opened the same staging path twice, wrote a longer valid JSON record and then overwrote it via the shorter open descriptor. A one-byte size difference initially left just trailing whitespace, which the parser validly accepted. Repeating with the actual two-byte style of field-size difference left extra non-whitespace and yielded `JSONDecodeError: Extra data`. Reading from a unique staging path parsed normally. The malformed samples are a subset of the worker races, and no count here extrapolates to production. The direct control excludes absent JSON packages, encoding and ordinary quota. `http_workbench.py:45–59` names the staging path and parser.
8. **Manifest and history failure cases are distinguished by decoder boundaries.** Tests modified scratch manifests directly with syntactically invalid JSON, well-formed objects missing or mistyping `created_at`, a valid array, and an invalid UTF-8 byte. The original record was restored and list/get worked again. Namespace list correctly reported syntax damage per record, then crashed when accepted objects could not supply a comparable sort key. HTTP list suppressed syntax errors and aborted when a valid array had no `.get()`. Reading the same synthetic two-line history by raw bytes proved that line one was valid and the tail malformed. Metadata counted both nonblank lines, while the history function decoded every line and raised. This is a recovery and consistency problem rather than a file lookup or module loading failure. An unrecognized schema version was accepted, which establishes current schema handling. Migration policy remains a design decision.
9. **Publication, first acknowledgment and durability separate.** Raising `ENOSPC` only at final rename kept earlier namespaces valid, and a regular successful retry showed the scratch location was writable. An actual subprocess that exited immediately before the same rename also left staging and no new visible namespace. Exiting after rename left a complete visible namespace without returning its ID. Repeating that logical creation made a second ID. For session metadata, before/after replacement likewise preserved the old or the new visible value. These are process-death boundaries on two local filesystems. No disk-wide exhaustion, host crash or power cut was used. For an ordinary workspace overwrite, a three-byte partial writer injected `EIO` after the new prefix, and a real per-process 4 KiB file-size ceiling separately produced `EFBIG` and the expected partial bytes. The subsequent normal write passed. These controls distinguish file truncation by opening in `w` mode from failure of a storage system to honor rename.
10. **A broken artifact name can stop enumeration.** The temporary link pointed to another name within the same engagement. `lstat()` established that the directory entry existed, following the link established the referent was absent, and the original listing raised through `item.stat()`. Creating the missing intermediate artifact made both listing modes useful again. This checks ordinary workspace state and distinguishes an invalid directory, cross-namespace path, permission failure or test fixture text type.
11. **Native cancellation is a waiter operation after worker startup.** The AST-extracted adapter was the pinned `drost_workspace_write` with its registration decorator removed. A ready signal established that the underlying thread had entered the backend. The request completed as canceled before the write existed. After the caller's cancellation and an independent release the real workspace write completed with the expected bytes. A second control used an observed one-worker pool, submitted a queued write behind the blocked one and canceled both awaiters. The queued future became canceled and created no file, while the already-started future later created its file. This separates real cancellation before scheduling from loss of the waiter once work starts. The actual SDK's cancel propagation and default thread-pool width are outside this test.

### Installer, manager and integration fixtures

12. **Bash executes two restore attempts on the signal path.** The independently implemented fake engine records actual names, running states and volume state. It removes only the named record, while the repository fixture clears its active marker even when a rollback name is deleted. Fresh and upgrade success, ordinary rollback after a failed candidate verification, and an isolated install failure established that the independent fake follows variant order. For the signal case, the controller held the verification subprocess until TERM had been sent to the installer's PID, then released it. The trace showed two exact active-name removals with the backup already recovered after the first. Both verification-completion codes, zero and 72, led to an empty container set under the pinned trap. An in-memory script control that disarmed the traps, restored once and exited 143 preserved the predecessor in both cases. File contents of the fake workspace remained intact. The relevant Bash version was 5.3.20. The experiment establishes shell control flow with a command-level fake. Actual Docker behaviors such as stderr delivery, rename failures and container stop time remain integration questions. `install.sh:61–70, 138–166`.
13. **Other installer partial states are stage-specific.** Failing `run` before creating a replacement left the new-install volume and zero containers. Failing verification after a fresh run retained the new container in the fake. The same verification failure after an upgrade restored the backed-up predecessor. Failing rename after stopping left the old name stopped because the trap had not been installed. Failing restoration's `start` left it stopped despite an attempted rollback, and an originally stopped predecessor became running under a successful restore. The fake also demonstrated that an explicit purge can remove the managed container before the script declines an unmanaged volume. In the two-installer test, A's fake run paused before looking up its proposed name, so B's successful name creation was visible to the real conflict check when A resumed. A then restored the earlier identity. The solo and per-name-lock controls distinguish the race from a mocked scheduler cache or name-file mistake. Command statuses and preserved volume data rule out fake-volume churn. An engine-specific test should verify permission and container behavior. `install.sh:51–70, 105–124, 134–166`.
14. **Browser observations concern application handle/state transitions.** The fixture allowed both create calls to pass the cache check before releasing either simulated launch. The serial and lock-guarded cases allocated one driver and two contexts. Verified activation of the second launch established the lost tracked handle. Context counts and explicit close markers distinguished a returned exception or canceled creation from closure. A title await yielded a deterministic window to close another registered context during list. With no concurrent close, listing succeeded. Snapshotting the dictionary still led to a dead ID during the same schedule. After synthetic disconnection and relaunch, removing the old ID restored listing. These tests qualify scheduling and fixture assumptions. They establish what the Python manager releases or retains and leave actual SDK teardown and production resource leaks unmeasured. `browser.py:36–62, 73–99, 140–174`.
15. **Browser event persistence has two authorities under fault.** Two normal synthetic callbacks first matched the memory view and parsed JSONL. An injected `ENOSPC` at file open produced 3 events in memory and 2 on disk. An injected `EIO` at clear left 0 in memory and 2 on disk. The same path was valid before each fault. A second manager had no live ID and the durable bytes remained. The production callback body is real and runtime delivery of callback exceptions by Playwright is outside the fixture. This separates event storage from browser backend or network availability. `browser.py:103–128, 327–339`.
16. **Readiness, availability and SDK presence are distinct.** Two independently selected local interpreters reported `mcp` and `playwright` unavailable through `importlib.util.find_spec`. The image explicitly installs `python3-mcp` and Playwright, so the host result is no evidence about the image. The catalog count comes from the source AST, registry records and the immutable executable inventory. Mocked availability checks covered 107 resolved and zero resolved external entries; the JSON label was `healthy` in both, with different CLI exits. A missing workspace was checked independently, and browser availability was simulated absent in both. This isolates the predicate from local PATH, missing packages, Docker daemon access and volume permissions. Counting recorded signatures makes no claim about the real SDK's JSON Schema, exact compatible versions or transport behavior. `Dockerfile:141–150, 241–258`, `pyproject.toml:19–26` and `server.py:44–58, 116–126, 488–524`.
17. **Smoke-test infrastructure has an independent stream-reader edge.** Each extracted `receive()` was given a worker that wrote two complete JSON lines in one syscall and then waited for input with stdout open. It raised waiting for ID 2 even though a direct next `readline()` immediately returned that record and the worker was still alive. A binary reader using readiness and explicit buffering read both records from the same worker script. The original implementation pairs kernel readiness with a read-ahead text stream. The test exercises exactly that boundary, without running product smoke calls. The timeout is a fixture observation and provides no evidence of a production MCP failure. `tests/mcp_smoke.py:20–31, 53–60` and `tests/mcp_epic_smoke.py:83–93`.
18. **Orphaned work can hold application pipe descriptors until a group is cleaned up.** An independent leader-exit control used readiness records from the processes themselves and held no Python `Process` reference. It verified the leader had disappeared and the worker remained live. The descriptor inventory was six live links before spawn and eight after leader exit. Eight remained after canceling, deleting the waiter and collecting garbage. Independently terminating and reaping the known group restored six. Reading every FD target omitted the iteration's transient descriptor, explaining the one-unit difference from the earlier 7/7 count. The two new links were both pipes, and identical outcomes on both Python versions rule out the observer holding a reference. A separate application-level counterfactual shielded an independently retained cleanup task. It still allowed the waiter to return before completion, and the retained owner reached terminal cleanup when the worker was released. This distinguishes protecting the cleanup task from promising a terminal response to a client.
19. **Container-style teardown has a larger lifecycle boundary than caller exit.** In a nested Linux PID namespace the controller verified both actual processes belonged to that namespace and the worker was live. The fixture PID 1 handled TERM by exiting normally. Both IDs disappeared after the namespace ended. This is a kernel-only comparison with the earlier case where a non-init parent died and its worker was adopted. The actual image's init and Docker behavior require separate integration evidence. It supports reasoning about three boundaries, namely request, client server process and full execution environment.
20. **An interrupted install can leave state outside the next invocation's view.** The fake engine committed the stopped predecessor's rename, verified its own parent PID was the intended installer and ended that process with SIGKILL. The controller checked the exit signal, missing primary name and exact predecessor identity before retrying. Retry succeeded from the same filesystem and kept the volume, proving the workspace and name were usable. The old backup remained because startup examines the exact primary name. A normal upgrade on identical initial state removed the backup. SIGKILL is inherently untrappable. The source limitation is the absent reconciliation of prior interrupted transitions. `install.sh:138–166`.
21. **A distinct cancellation model exposes the same vulnerable await.** CPython 3.12.16 had local AnyIO 4.16.0, while 3.14.8 lacked it. In `anyio.run(..., backend="asyncio")` the standard `Task.cancel()` control let the TERM handler finish once the controller released it. Canceling the actual AnyIO task-group scope once caused the original executor to return while its worker still waited. Both cases observed the TERM marker and used identical code and interpreter. A source copy executed in memory with `CancelScope(shield=True)` around `_terminate_process_group` preserved cleanup across the canceled scope and the worker exited with code 0. The standard library event loop, package absence on the other interpreter and the fixture's deterministic release conditions were distinguished. The test supports checking the installed SDK's actual cancellation model before choosing a production fix. `executor.py:45–60, 106–112`.
22. **Permission behavior required a different namespace capability setup.** Plain `chmod(0)` initially failed to induce an error. A raw `read_text()` and the repository call both succeeded with mode `0o000` under the mapped effective UID 0. Dropping DAC override/read-search capabilities with `setpriv --bounding-set=-dac_override,-dac_read_search` before launching Python changed the raw check to real `EACCES`. The repository then reported an invalid engagement with `EACCES` preserved as a cause, and HTTP state get raised `PermissionError` while list omitted the record. Testing a read-only existing artifact separately confirmed a denied overwrite before any data changed. Restoring access made every operation work. These controls repeated on tmpfs and Btrfs using both interpreters. They distinguish actual permission failures from the distinct quota, parsing and staging cases. `engagements.py:36–50, 112–125`, `http_workbench.py:52–59, 104–115` and `workspace.py:42–56`.

These controls separate confirmed source behavior from intended design limits and omitted environments. Actual container CPU/memory policy, system permissions, filesystem semantics of a deployed volume, packaged dependency versions, browser teardown and wire cancellation need different fixtures. The strongest findings survived direct handling with no product dependencies, both local interpreters and independent positive controls. Any limited inference about the real container is explicitly scoped to a code path.

## 8. Post-mortem: design pressures, accumulated tradeoffs, likely failure modes, and the highest-leverage improvements.

The repository's size and clear division of responsibilities fit its packaging goal. An existing agent can use a large installed inventory behind a single protocol. Stdio and a container remove the need for a separate service, credential store and embedded agent loop. A shared volume lets clients restart and retain artifacts. Keeping workflow logic deterministic and returning data only maintains that separation. There is little value in adding a general scheduler just to fix the current issues.

Several choices optimize for the common sequential case. The direct subprocess leader supplies a convenient local completion signal. A temporary filename and atomic rename keep a normal single-writer JSON reader away from partially written data. Browser launch is lazy and cheap after the first call. A Bash trap provides a compact rollback procedure for a failed command. These work well during a normal tool call, normal state change, serial browser start or straightforward failing upgrade. The complexity arrives at the boundary between a local completion signal and the resource or transaction that actually needs ownership.

The first likely failure class is **a request finishing before cleanup**. Cancellation, startup error or loss of a caller can leave the result unavailable while its resource remains active. In a shared container subsequent calls can see unrelated work, hit descriptor or memory pressure, or spend time waiting for dependencies held by old work. The process supervisor needs an explicit owner until it can report a terminal state. For unavoidable thread work, the API needs to expose whether work started, committed or merely lost its waiter. These changes preserve per-request design and client scheduling.

The second is **durable state that appears fresher or more complete than it is**. A successful setter can return a value never stored by that invocation, a late write can restore a stale field, and a damaged history record can hide good older rows. Four authorities currently matter for recovery: acknowledgment, JSON snapshot, JSONL history and process-local handles. Give each a clear job. Use one authoritative transition for conflicting session mutations, version the on-disk data, and make removal or repair of abandoned staging observable. A store with real transactions would simplify a future combined state/history commitment. An initial fix can use a reusable file mutation protocol with cross-process coordination and a narrowly specified journal contract.

The third is **partial infrastructure recovery presented as a completed transition**. The image self-test mostly verifies availability on PATH, while the installer relies on its status to keep or remove the predecessor. Recovery runs in a signal handler that can resume the interrupted path, silently ignores several failures, and follows the mutable container name independently from identity. Separate readiness from capability inventory, and make the install/upgrade state machine explicit about name, identity, original running state and phase. Restore or report each observed state after one recovery attempt. This is small compared with image build breadth and materially improves operator confidence in upgrade and restart.

Both the detailed command adapters and shared deployment will keep evolving. Changes are safest when source-owned registry metadata, runtime state modules and OS lifecycle handling remain independently testable. Generic barriers and injected failures add coverage without depending on installed product tools, network services, the current container engine or real Chromium. An integration suite with the already built distribution can then verify the package/protocol contracts that those tests intentionally delegate.

## 9. Evidence appendix with local file/line references and commands.

### Source map

| Boundary | Local evidence |
| --- | --- |
| Executable and image boot | [pyproject.toml](repos/drost-ai__drost-community/pyproject.toml:19) lines 19–26, [Dockerfile](repos/drost-ai__drost-community/Dockerfile:241) lines 241–263 |
| Container operations and rollback | [install.sh](repos/drost-ai__drost-community/install.sh:51) lines 51–70 and 101–169 |
| Client boundary and configuration | [README.md](repos/drost-ai__drost-community/README.md:114) lines 54–84, 114–195, 277–286, 366–368 and 400–412 |
| Build metadata and platform workflow | [publish-container.yml](repos/drost-ai__drost-community/.github/workflows/publish-container.yml:64) lines 64–85, 117–135, 155–182 and 247–284 |
| Protocol, dispatch, concurrency and readiness | [server.py](repos/drost-ai__drost-community/src/drost_ai/server.py:27) lines 27–58, 91–126, 129–235, 248–450, 468–485 and 488–532 |
| Catalog and advisory helpers | [catalog.py](repos/drost-ai__drost-community/src/drost_ai/catalog.py:183) lines 10–23 and 183–210, [workflows.py](repos/drost-ai__drost-community/src/drost_ai/workflows.py:93) lines 93–162 |
| Child process contract | [executor.py](repos/drost-ai__drost-community/src/drost_ai/executor.py:45) lines 14–41 and 45–124, [execution_tools.py](repos/drost-ai__drost-community/src/drost_ai/execution_tools.py:11) lines 11–67 |
| Artifact namespaces | [engagements.py](repos/drost-ai__drost-community/src/drost_ai/engagements.py:36) lines 14–58 and 61–150, [workspace.py](repos/drost-ai__drost-community/src/drost_ai/workspace.py:11) lines 11–70 |
| Persisted session and event history | [http_workbench.py](repos/drost-ai__drost-community/src/drost_ai/http_workbench.py:37) lines 24–65, 66–165, 197–269 and 326–339 |
| Process-local manager | [browser.py](repos/drost-ai__drost-community/src/drost_ai/browser.py:36) lines 21–62, 73–174 and 327–343 |
| Native diagnostic and file output | [native_tools.py](repos/drost-ai__drost-community/src/drost_ai/native_tools.py:16) lines 16–39 and 206–224, [api_audit.py](repos/drost-ai__drost-community/src/drost_ai/api_audit.py:39) lines 22–43 |
| Critical test expectations | [test_executor.py](repos/drost-ai__drost-community/tests/test_executor.py:54) lines 54–91, [test_installer.py](repos/drost-ai__drost-community/tests/test_installer.py:24) lines 24–103 and 109–169, [mcp_smoke.py](repos/drost-ai__drost-community/tests/mcp_smoke.py:20) lines 20–31 and 53–60, [mcp_epic_smoke.py](repos/drost-ai__drost-community/tests/mcp_epic_smoke.py:83) lines 83–93 |

### Offline invocation and unit output

From the pinned checkout, the following shell setup and unit command use the package's source and the reviewed fixtures. `-B` and `PYTHONDONTWRITEBYTECODE` both suppress Python bytecode writes in source. The PID 1 wrapper makes process identification and orphan reaping independent from the desktop's init. The extra `--net` namespace is isolated and the tests issue only local process and file operations. Substitute a fresh scratch directory beneath `/var/tmp` to repeat the two-filesystem controls, and use `"$(command -v python3)"` to select the second local interpreter.

~~~bash
review_tmp=$(mktemp -d /tmp/drost-repro.XXXXXX)
trap 'rmdir "$review_tmp"' EXIT
run_offline() {
  local interpreter=$1
  shift
  /usr/bin/unshare --user --map-root-user --net --pid --fork --mount-proc \
    --kill-child=SIGKILL -- /usr/bin/env -i PATH=/usr/bin:/bin HOME="$review_tmp" \
    TMPDIR="$review_tmp" LANG=C.UTF-8 PYTHONPATH="$PWD/src:$PWD/tests" \
    PYTHONDONTWRITEBYTECODE=1 DROST_WORKSPACE="$review_tmp/workspace" \
    "$interpreter" -B "$@"
}
for interpreter in /usr/bin/python3 "$(command -v python3)"; do
  run_offline "$interpreter" - <<'PY'
import os, sys, unittest
assert os.getpid() == 1
names = ("test_executor", "test_engagements", "test_installer",
         "test_distribution", "test_catalog")
suite = unittest.defaultTestLoader.loadTestsFromNames(names)
result = unittest.TextTestRunner(verbosity=2).run(suite)
adopted = []
while True:
    try:
        pid, status = os.waitpid(-1, os.WNOHANG)
    except ChildProcessError:
        break
    if not pid:
        break
    adopted.append((pid, os.waitstatus_to_exitcode(status)))
print(sys.version.split()[0], "adopted child statuses", adopted)
sys.exit(not result.wasSuccessful())
PY
done
~~~

Both runs returned `Ran 30 tests` and `OK`. Unit runtimes were 0.264 s and 0.265 s. Each wrapper reported one adopted child exited by signal `-15`. A direct 23-test comparison without the executor suite also passed. The downstream kernel and Python observations can be checked locally without importing the product SDK.

~~~bash
git rev-parse --verify HEAD
git rev-parse 'HEAD^{tree}'
GIT_OPTIONAL_LOCKS=0 git status --porcelain=v1 --untracked-files=all --ignored
git diff --no-ext-diff --exit-code HEAD --
git diff --check
nl -ba src/drost_ai/executor.py | sed -n '43,124p'
nl -ba src/drost_ai/http_workbench.py | sed -n '37,65p;129,165p;326,339p'
nl -ba install.sh | sed -n '51,70p;134,169p'
/usr/bin/stat -f -c '%n %T' /tmp /var/tmp
/usr/bin/bash --version | head -n 1
run_offline /usr/bin/python3 - <<'PY'
import asyncio, importlib.util, inspect, platform, resource
from asyncio import base_subprocess, unix_events
print(platform.python_version(), platform.machine(), resource.getrlimit(resource.RLIMIT_NOFILE))
for package in ("mcp", "playwright", "requests", "psutil"):
    print(package, importlib.util.find_spec(package) is not None)
for function in (unix_events._UnixSelectorEventLoop._make_subprocess_transport,
                 base_subprocess.BaseSubprocessTransport.close,
                 base_subprocess.BaseSubprocessTransport._wait,
                 asyncio.subprocess.Process.communicate, asyncio.to_thread):
    print(inspect.getsourcefile(function), inspect.getsourcelines(function)[1])
PY
~~~

The CPython 3.14 system library inspection located `_make_subprocess_transport` at [unix_events.py](/usr/lib/python3.14/asyncio/unix_events.py:198) line 198 with exception cleanup at 214–215, `BaseSubprocessTransport.close()` at [base_subprocess.py](/usr/lib/python3.14/asyncio/base_subprocess.py:99) line 99, `_wait()` at line 263, and `communicate()` at [subprocess.py](/usr/lib/python3.14/asyncio/subprocess.py:188) line 188. The corresponding Python 3.12 locations are [unix_events.py]($HOME/.local/share/mise/installs/python/3.12.16/lib/python3.12/asyncio/unix_events.py:195) line 195, [base_subprocess.py]($HOME/.local/share/mise/installs/python/3.12.16/lib/python3.12/asyncio/base_subprocess.py:96) lines 96 and 221, and [subprocess.py]($HOME/.local/share/mise/installs/python/3.12.16/lib/python3.12/asyncio/subprocess.py:188) line 188. Both ultimately dispatch `to_thread` through `loop.run_in_executor(None, ...)`.

### Reproduce process-group cancellation after leader exit

Run the Python body via `run_offline /usr/bin/python3 -`. It starts a generic idle worker, bounds all controller waits, then manually cleans up its own namespace. The second signal is the independent positive control for OS group delivery.

~~~python
import asyncio, os, signal, sys, tempfile, time
from pathlib import Path
from unittest.mock import patch
from drost_ai import engagements as store, executor

worker_code = '''
import os, time
from pathlib import Path
marker = Path("child.tmp")
marker.write_text(str(os.getpid()))
marker.replace("child.ready")
while True:
    time.sleep(.01)
'''
leader_code = '''
import subprocess, sys, time
from pathlib import Path
subprocess.Popen([sys.executable, "-c", sys.argv[1]])
while not Path("child.ready").exists():
    time.sleep(.004)
'''

async def until(condition):
    deadline = time.monotonic() + 3
    while not condition():
        assert time.monotonic() < deadline
        await asyncio.sleep(.004)

def state(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except FileNotFoundError:
        return "-"

async def run(temp):
    store.WORKSPACE = Path(temp)
    record = store.create_engagement("ownership fixture", ["fixture"])
    marker = Path(record["workspace"]) / "child.ready"
    original = asyncio.create_subprocess_exec
    created = []
    async def record_spawn(*args, **kwargs):
        process = await original(*args, **kwargs)
        created.append(process)
        return process
    with patch.object(executor.asyncio, "create_subprocess_exec", record_spawn):
        task = asyncio.create_task(executor.execute_tool(
            sys.executable, ["-c", leader_code, worker_code], record["engagement_id"]))
        await until(lambda: created and marker.exists() and created[0].returncode == 0)
        worker = int(marker.read_text())
        leader = created[0].pid
        assert not task.done() and os.getpgid(worker) == leader
        assert state(worker) not in {"Z", "-"}
        try:
            task.cancel()
            try:
                await asyncio.wait_for(task, 3)
            except asyncio.CancelledError:
                assert state(worker) not in {"Z", "-"}
                print("return after cancel", created[0].returncode, state(worker))
            else:
                raise AssertionError("cancel did not propagate")
            os.killpg(leader, signal.SIGTERM)
            await until(lambda: state(worker) == "Z")
            assert os.waitstatus_to_exitcode(os.waitpid(worker, 0)[1]) == -signal.SIGTERM
            print("same group signal reaped worker")
        finally:
            if state(worker) != "-":
                os.killpg(leader, signal.SIGKILL)
                await until(lambda: state(worker) == "Z")
                os.waitpid(worker, 0)
        await created[0].wait()

assert os.getpid() == 1
with tempfile.TemporaryDirectory() as temp:
    asyncio.run(run(temp))
~~~

The paired control with a live leader reported leader return code `-15` and terminated worker state `Z`. With the leader already exited, the request returned `CancelledError` while its worker state was `S`. A worker that did post-TERM cleanup with separated descriptors acknowledged TERM and was still live as the request returned. The single-leader fallback took 2002.5 ms and 2002.4 ms in the two Python runs. Repeated cancellation took 4.3 ms and 4.2 ms in its controlled schedule, with cleanup interrupted before escalation. Millisecond readings are individual monotonic samples.

### Reproduce independent session-writer hazards

Run this body with the same namespace function. The URL is parsed as inert session metadata. No request or fixture service is involved.

~~~python
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, current_thread
from unittest.mock import patch
from drost_ai import engagements as e, http_workbench as h

with tempfile.TemporaryDirectory() as temp:
    e.WORKSPACE = Path(temp)
    eng = e.create_engagement("storage fixture", ["fixture"])["engagement_id"]
    sid = h.create_http_session(eng, "metadata only", "https://fixture.invalid")["session_id"]
    final = h._session_path(eng, sid)
    original = final.read_text()

    loaded, release = Event(), Event()
    real_load = h._load_state
    def pause_after_load(*args):
        data = real_load(*args)
        if current_thread().name.startswith("later"):
            loaded.set()
            assert release.wait(3)
        return data

    with ThreadPoolExecutor(1, thread_name_prefix="later") as pool:
        with patch.object(h, "_load_state", pause_after_load):
            later = pool.submit(h.update_http_session, eng, sid, verify_tls=False)
            try:
                assert loaded.wait(3)
                assert h.update_http_session(eng, sid, include_subdomains=True)["include_subdomains"]
            finally:
                release.set()
            assert not later.result(3)["verify_tls"]
    state = h.get_http_session(eng, sid)
    assert (state["include_subdomains"], state["verify_tls"]) == (False, False)

    final.write_text(original)
    h.update_http_session(eng, sid, include_subdomains=True)
    h.update_http_session(eng, sid, verify_tls=False)
    state = h.get_http_session(eng, sid)
    assert (state["include_subdomains"], state["verify_tls"]) == (True, False)

    ready, release = Event(), Event()
    real_replace = Path.replace
    def pause_replace(stage, target):
        if stage == final.with_suffix(".json.tmp") and current_thread().name.startswith("waiting"):
            ready.set()
            assert release.wait(3)
        return real_replace(stage, target)

    with ThreadPoolExecutor(1, thread_name_prefix="waiting") as pool:
        with patch.object(Path, "replace", pause_replace):
            pending = pool.submit(h.update_http_session, eng, sid, include_subdomains=False)
            try:
                assert ready.wait(3)
                assert h.update_http_session(eng, sid, verify_tls=True)["verify_tls"]
            finally:
                release.set()
            try:
                pending.result(3)
            except FileNotFoundError as err:
                assert err.errno == 2 and final.is_file()
            else:
                raise AssertionError("expected the shared staging file to be consumed")
    print("two successful replies lost a field; serial control merged; shared stage produced ENOENT")
~~~

The two-process version starts two copies of the same interpreter with stdin/stdout pipes. Each calls the source `update_http_session` with a distinct Boolean field. In the forced schedule, both workers send a ready marker after their real staging write and before `Path.replace`. Publish A, read disk, then publish B. The shared-stage result was `A ack [true,true], disk [false,false], B ENOENT, final [false,false]`. Repeating with separate staged files yielded `A ack [true,true], disk [true,true], B ack [false,false], final [false,false]`. The final state on a serial pair is `[true,false]`.

For the ungated comparison two workers each acknowledge the previous trial before the controller restores the known initial bytes. The controller then writes one start marker to each worker's input pipe, collects statuses and reopens the resulting file. The locked comparison surrounds the source call by `flock(LOCK_EX)` on the same session lock file in both processes.

| Storage / CPython | Trials | Direct, merged with two acknowledgments | Direct, lost with two acknowledgments | Direct, staging error | Direct, final unreadable JSON | Locked, merged with two acknowledgments |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| tmpfs / 3.14.8 | 256 | 0 | 116 | 140 | 31 | 256 |
| tmpfs / 3.12.16 | 256 | 21 | 135 | 100 | 19 | 256 |
| Btrfs / 3.14.8 | 256 | 0 | 153 | 103 | 15 | 256 |
| Btrfs / 3.12.16 | 256 | 23 | 132 | 101 | 25 | 256 |

The final-unreadable column overlaps the staging-error column. The file and thread experiments answer different questions. Gating identifies the operation order, while the ungated trials demonstrate the same kinds of outcome with real concurrent writers and no internal barrier. These samples are a test of mechanism and do not measure typical use.

### Reproduce installer rollback and shared-name ownership

This compact control runs the pinned `install.sh` using a local fake executable on `PATH`. The fake implements just name, identity and verification semantics. Its `pull` branch does no work. Use the fuller transition table below to distinguish the signal and name-ordering paths from other failures.

~~~python
import json, os, signal, subprocess, sys, tempfile, time
from pathlib import Path

installer = Path("install.sh").resolve()
fake_engine = r'''#!/usr/bin/python3
import json, os, sys, time
from pathlib import Path
root = Path(os.environ["REVIEW_ENGINE"])
args = sys.argv[1:]
op = args[0]
with (root / "calls.jsonl").open("a") as out:
    out.write(json.dumps([os.environ["ACTOR"], args]) + "\n")
def gate():
    (root / "entered").touch()
    end = time.monotonic() + 4
    while not (root / "release").exists():
        assert time.monotonic() < end
        time.sleep(.004)
def name(value):
    return root / ("container." + value)
if op == "info":
    print("amd64")
elif op in {"pull", "stop", "start"}:
    pass
elif op == "volume":
    assert args[1] == "inspect" and (root / "volume").is_file()
elif op == "container":
    sys.exit(0 if name(args[-1]).exists() else 1)
elif op == "inspect":
    assert name(args[-1]).exists()
    print("true")
elif op == "rename":
    source, target = map(name, args[1:])
    if not source.exists() or target.exists():
        sys.exit(1)
    source.rename(target)
elif op == "run":
    if os.environ.get("HOLD") == "run":
        gate()
    candidate = name(args[args.index("--name") + 1])
    if candidate.exists():
        sys.exit(1)
    candidate.write_text(os.environ["ACTOR"])
elif op == "exec":
    assert name(args[1]).exists() and args[2:] == ["drost-mcp", "--self-test"]
    if os.environ.get("HOLD") == "exec":
        gate()
        sys.exit(int(os.environ.get("VERIFY_RC", "0")))
elif op == "rm":
    candidate = name(args[-1])
    if not candidate.exists() and "-f" not in args:
        sys.exit(1)
    candidate.unlink(missing_ok=True)
else:
    raise AssertionError(args)
'''

def await_entry(worker, path):
    end = time.monotonic() + 3
    while not path.exists():
        assert worker.poll() is None and time.monotonic() < end
        time.sleep(.004)

def one(hold, verify_rc=0, counterfactual=False):
    with tempfile.TemporaryDirectory() as dirname:
        root = Path(dirname)
        fake = root / "docker"
        fake.write_text(fake_engine)
        fake.chmod(0o755)
        (root / "volume").write_text("retained")
        service = root / "container.service"
        service.write_text("old")
        env = {
            **os.environ, "PATH": f"{root}:/usr/bin:/bin",
            "REVIEW_ENGINE": str(root), "DROST_CONTAINER_NAME": "service",
            "DROST_VOLUME_NAME": "storage", "DROST_IMAGE": "fixture-image",
            "ACTOR": "A", "HOLD": hold, "VERIFY_RC": str(verify_rc),
        }
        if counterfactual:
            original = installer.read_text()
            changed = original.replace(
                "trap restore_backup ERR INT TERM",
                "trap restore_backup ERR\n"
                "  trap 'trap - ERR INT TERM; restore_backup; exit 143' TERM\n"
                "  trap 'trap - ERR INT TERM; restore_backup; exit 130' INT",
            )
            assert changed != original
            command = ["/usr/bin/bash", "-c", changed]
        else:
            command = [str(installer)]
        with subprocess.Popen(command, env=env, cwd=root, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as a:
            try:
                await_entry(a, root / "entered")
                if hold == "exec":
                    a.send_signal(signal.SIGTERM)
                else:
                    assert not service.exists()
                    other = subprocess.run([str(installer)], cwd=root, text=True,
                                           env={**env, "ACTOR": "B", "HOLD": ""},
                                           capture_output=True, timeout=3)
                    assert other.returncode == 0 and service.read_text() == "B"
                (root / "release").touch()
                a.communicate(timeout=5)
            finally:
                (root / "release").touch()
                if a.poll() is None:
                    a.kill()
                    a.wait()
        final = service.read_text() if service.exists() else None
        assert (root / "volume").read_text() == "retained"
        calls = [json.loads(line) for line in (root / "calls.jsonl").read_text().splitlines()]
        removes = sum(
            actor == "A" and args == ["rm", "-f", "service"]
            for actor, args in calls
        )
        if hold == "run":
            assert (a.returncode, final, removes) == (1, "old", 1)
        elif counterfactual:
            assert (a.returncode, final, removes) == (143, "old", 1)
        else:
            assert (a.returncode, final, removes) == (verify_rc or 1, None, 2)
        print(hold, verify_rc, counterfactual, a.returncode, final, removes)

assert os.getpid() == 1
one("exec")
one("exec", verify_rc=72)
one("exec", counterfactual=True)
one("exec", verify_rc=72, counterfactual=True)
one("run")
~~~

The fuller fake recorded running state and rejected removal of a running backup without a force flag. The code under test was unchanged. The extra cases produced the following state outcomes on both local interpreters. Injected failures returned 70. Engine rejection from a name or running-state check returned 1.

| Scenario | Installer exit | Final simulated state |
| --- | ---: | --- |
| Fresh success | 0 | New identity, running, volume present |
| Fresh create command fails | 70 | No container, newly created volume present |
| Fresh verification fails | 70 | New identity, running, volume present |
| Upgrade succeeds | 0 | New identity, running, original volume payload |
| Upgrade verification fails | 70 | Predecessor restored and running, original volume payload |
| Upgrade create fails | 70 | Predecessor restored and running |
| Backup rename fails | 70 | Predecessor still at primary name, stopped |
| Stop fails, then fake allows rename | 1 | Removal of running backup rejected, predecessor restored |
| Backup removal fails after successful verification | 70 | Verified candidate replaced by restored predecessor |
| Start in restore fails | 70 | Predecessor at primary name and stopped |
| Restoration starts an initially stopped predecessor | 70 | Predecessor at primary name and running |
| Purge of an unlabelled volume | 1 | Container removed, unlabelled volume retained |
| TERM while verification is outstanding | 1 or 72 | No container after restoration ran twice, original volume payload |
| Single-shot TERM counterfactual | 143 | Predecessor at primary name and running, original volume payload |
| Two concurrent installers, A paused before candidate creation | A exit 1, B exit 0 | B succeeded first, then A's rollback removed B and restored the predecessor |
| Named lock around the same two installers | Both 0 | B becomes active after the serialized second install |
| Installer abruptly ended after backup rename, followed by retry | First -9, retry 0 | New active identity and unchanged volume, prior stopped predecessor still under rollback name |

### Reproduce the browser cold-start ownership gap

These fake drivers test the process-local manager only. The sentinel executable path is never opened.

~~~python
import asyncio, sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from drost_ai import browser as source

class Driver:
    def __init__(self):
        self.chromium = self
        self.ready = asyncio.Event()
        self.release = asyncio.Event()
        self.handle = SimpleNamespace(is_connected=lambda: True)
    async def start(self):
        return self
    async def launch(self, **options):
        self.ready.set()
        await self.release.wait()
        return self.handle

async def run():
    first, second = Driver(), Driver()
    drivers = iter((first, second))
    playwright = ModuleType("playwright")
    async_api = ModuleType("playwright.async_api")
    async_api.async_playwright = lambda: next(drivers)
    manager = source.BrowserManager()
    with patch.dict(sys.modules, {"playwright": playwright, "playwright.async_api": async_api}):
        with patch.object(source.shutil, "which", return_value="/fixture/chromium"):
            a = asyncio.create_task(manager._ensure_browser())
            await asyncio.wait_for(first.ready.wait(), 3)
            b = asyncio.create_task(manager._ensure_browser())
            await asyncio.wait_for(second.ready.wait(), 3)
            first.release.set()
            assert await a is first.handle
            second.release.set()
            assert await b is second.handle
            assert manager._browser is second.handle and manager._playwright is second
            assert await manager._ensure_browser() is second.handle
    print("two overlapping launches and only the second pair retained in the singleton")

asyncio.run(run())
~~~

The fuller control exercised both `create()` paths, verified which contexts belonged to which launch, and closed them. It injected errors at `launch`, `new_page`, `route`, artifact directory creation and `title`. A close-vs-list case paused the first page's title and closed a separate session before resuming. Expanded event controls appended two synthetic records and injected faults at the file operations for subsequent append and clear. These fixtures exercise source callbacks and leave UI, real renderer and network health outside the test.

### Reproduce malformed state, partial history and real write limits

These failures use a valid namespace first, and then modify only its disposable files. The limit is specific to the test process. It requires no disk exhaustion.

~~~python
import errno, json, os, resource, signal, sys, tempfile
from pathlib import Path
from drost_ai import engagements as e, http_workbench as h, workspace as w

assert os.getpid() == 1
with tempfile.TemporaryDirectory() as tmp:
    e.WORKSPACE = Path(tmp)
    meta = e.create_engagement("Persistence fixture", ["fixture"])
    eng, root = meta["engagement_id"], Path(meta["workspace"])
    manifest = root / "engagement.json"
    saved = manifest.read_text()
    manifest.write_text("{")
    assert e.list_engagements()["invalid_engagements"][0]["engagement_id"] == eng
    manifest.write_text(json.dumps({"engagement_id": eng}))
    assert e.get_engagement(eng)["engagement_id"] == eng
    try:
        e.list_engagements()
    except KeyError as exc:
        assert exc.args == ("created_at",)
    else:
        raise AssertionError("expected missing timestamp failure")
    manifest.write_text(saved)
    assert len(e.list_engagements()["engagements"]) == 1

    sid = h.create_http_session(eng, "Storage only", "https://fixture.invalid")["session_id"]
    h._append_history(eng, sid, {"i": 1})
    path = h._history_path(eng, sid)
    prefix = path.read_text()
    path.write_text(prefix + '{"i":')
    assert h.get_http_session(eng, sid)["history_count"] == 2
    try:
        h.read_http_history(eng, sid)
    except json.JSONDecodeError:
        assert json.loads(path.read_text().splitlines()[0]) == {"i": 1}
    else:
        raise AssertionError("expected damaged tail failure")
    path.write_text(prefix)
    assert h.read_http_history(eng, sid)["entries"] == [{"i": 1}]

    w.write_workspace_file(eng, "artifact.txt", "earlier valid content")
    old_limit = resource.getrlimit(resource.RLIMIT_FSIZE)
    old_signal = signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    resource.setrlimit(resource.RLIMIT_FSIZE, (4096, old_limit[1]))
    try:
        try:
            w.write_workspace_file(eng, "artifact.txt", "x" * 16384)
        except OSError as exc:
            assert exc.errno == errno.EFBIG
        else:
            raise AssertionError("expected the file size limit")
    finally:
        resource.setrlimit(resource.RLIMIT_FSIZE, old_limit)
        signal.signal(signal.SIGXFSZ, old_signal)
    assert (root / "artifact.txt").read_bytes() == b"x" * 4096
    print(sys.version.split()[0], "missing timestamp, partial history, and partial overwrite confirmed")
~~~

The storage-abort control replaces only the last `Path.replace` call in the created subprocess with a gate that calls `os._exit(73)` immediately before or after the original operation. Creation left a hidden staging directory before publication and a discoverable ID after publication. Session update left the previous setting before replacement and the new setting after replacement. A raw store feasibility control wrote a metadata row and journal row in one local SQLite `BEGIN IMMEDIATE` transaction and ended with `os._exit(73)`. Independent readers saw `(0, 0)` for the uncommitted transaction and `(1, 1)` for the committed transaction on both filesystems.

For memory, the generic worker wrote a fixed number of bytes to both pipes. The wrapper recorded `tracemalloc.get_traced_memory()` immediately after return, after three loop yields and GC, and after discarding the result. The isolated streaming control drained the same output through separate loops of `await reader.read(16 * 1024)` to temporary files. Both file sizes and result-string lengths were checked to be `1048576` bytes per stream.

| Filesystem / CPython | Full-output peak delta | Settled while result held | After result released | Stream-to-file peak delta |
| --- | ---: | ---: | ---: | ---: |
| tmpfs / 3.14.8 | 4,213,261 B | 2,098,404 B | 586 B | 640,871 B |
| tmpfs / 3.12.16 | 4,210,789 B | 2,099,212 B | 1,346 B | 384,073 B |
| Btrfs / 3.14.8 | 4,213,364 B | 2,098,425 B | 586 B | 641,035 B |
| Btrfs / 3.12.16 | 4,210,831 B | 2,099,233 B | 1,346 B | 384,115 B |

These measures are Python allocation samples from the server-side executor before protocol output. Keeping complete captured streams retains the full decoded result in the Python process. The measured file-backed control preserved all bytes with a smaller traced peak. General comparisons between interpreters or filesystems would need representative production workloads.

For the permission control, place `/usr/bin/setpriv --bounding-set=-dac_override,-dac_read_search` immediately before `"$interpreter"` in the namespace function. On a disposable engagement, save and temporarily clear the manifest's permission bits, compare direct `Path.read_text()` to `get_engagement()`, and restore modes in a `finally` block. The raw operation's `errno` was 13 in both environments. The application raised `ValueError` with `__cause__.errno == 13`. Apply the same step to the fake metadata session's JSON file for the HTTP get/list comparison. Both checks used normal POSIX file operations after verifying the capability change caused the raw errno.

## 10. Prioritized improvements.

| Priority | Improvement | Acceptance evidence |
| --- | --- | --- |
| P1 | **Own process teardown through completion.** Validate and encode input before launching. Keep a lifecycle owner across spawn, pipe communication, cancellation and server shutdown. Manage the group through a defined TERM/grace/forced-stop policy. Make cleanup survive repeat cancellation and expose its outcome. Track initial process/group identity explicitly and use a supervisor mechanism appropriate to the intended lifetime when plain process groups are insufficient. | Positive and negative subprocess cases with verified PIDs, pipes, signal acknowledgments, grace boundaries and reap results. Include early direct exit, concurrent cancellation, startup before the handle is returned, exception during communication and server endpoint shutdown. Actual client EOF and Docker exec behavior need an integration test. |
| P1 | **Make install rollback single-shot and state-aware.** Install error and signal behavior before changing the predecessor, track each completed transition by identity, record initial running state, and report recovery failures. A signal should terminate the interrupted transaction after one cleanup. Treat post-verification deletion of a backup as a separate, recoverable maintenance step. Coordinate contenders for the same configured name and verify purge preconditions before removals. | Fake-engine state assertions at every injected failure point. Termination before and after verification, failed stop/rename/start, failed fresh installation and two competing installations should leave an explainable identity and an intact workspace. Retest against the deployed engine separately. |
| P1 | **Serialize durable session mutation across server processes.** Use unique same-directory staging plus a cross-process lock or transactional database for read-modify-write. Specify how metadata and history commit or recover together. Add an operation or version check where clients need safe retry. | Gated two-writer tests must retain both disjoint edits or return an explicit conflict. A response must correspond to committed data. Abrupt exit before commit should retain the previous coherent value. A journal reader should return its valid prefix with an explicit damaged-tail diagnostic. |
| P2 | **Bound and clean up browser resources.** Coordinate cold start, publish only after successful setup and release any partially allocated handles. Define explicit manager shutdown and a stale/disconnected-session transition. List from a stable metadata view under concurrent close. Give the event ledger one declared persistence policy and bounded retention or pagination. | One driver for a concurrent cold start, no leaked handles in a failing create, predictable listing under close or disconnect and a verified manager shutdown. Inject event write and clear faults in both orders. |
| P2 | **Validate and recover persisted documents.** Share decoders between list and get, validate required schema fields and report damaged entries. Use replace-on-success for full workspace overwrites. Add deliberate stale-stage cleanup and preserve existing IDs and files across changes. | Bad syntax, wrong shape, version mismatch, failed overwrite, partial append, absent link targets, and aborted publication each yield an explicit result while keeping good records available. Test existing version-one data after a fresh process startup. |
| P2 | **Align readiness, cancellation and lifecycle observability with the advertised contract.** Report separate required capability and workspace checks, surface structured errors and call outcomes, and make running-thread side effects and retry semantics clear. Expose basic counters for active work, queued work, spawned and reaped children, output bytes and storage recovery. Keep stdio stdout reserved for the protocol. | CLI readiness reflects defined hard prerequisites and labels optional capability loss separately. A local protocol fixture can distinguish pre-start cancellation, cancellation with cleanup, lost acknowledgment after commit and incomplete cleanup. Logs or stderr contain sufficient correlation without copying whole user payloads. |
| P3 | **Offer explicit resource policy compatible with complete output.** Add shared admission and configurable deadlines or output-to-artifact spooling. Preserve complete output via an artifact reference when the caller selects that policy. Record budgets for active processes, memory, persistent journals and browser contexts. | Bounded descriptor test stops admitting early or sends a consistent capacity error. Small full-output calls remain compatible. Large controlled output remains complete with lower peak buffering when spooled. |
| P3 | **Derive tool metadata and strengthen integration fixtures.** Keep one source of direct registration and counts, make async annotations correct, use a public SDK interface or source registry, and test the pinned SDK in both supported image variants. Parse buffered stdio records with one consistent buffering model and a monotonic deadline. Assert resource outcomes in unit fixtures as well as returned statuses. | Full, compact and category-filtered counts match the recorded registration. The fixture correctly handles two frames in one write and reports the stream reader's true deadline. A supported image test verifies init, discovery, cancellation and graceful process ownership with benign fixtures. |
