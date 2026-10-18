# Data Agent repository instructions

## Local acceptance control routes

Choose and record the control route **before** a batch: built-in browser UI,
existing app HTTP API, or a combined HTTP-created session plus browser visual
inspection. A route change requires a fresh run directory and a new result
identity; never merge sessions or call a nonvisual run a browser pass. Preserve
the same frozen scenarios and independent oracles across routes. Ordinary
control-tool failures must not block unrelated engine, receipt, or Provider-
disabled work; mark the affected UI oracle `unassessed` and continue on a
labelled route. This is an evidence-level choice, not a product upload defect.

The P08 real-Provider HTTP matrix below remains a separate, frozen batch with
its own authorization and Provider ledger. The local control-route flexibility
does not authorize a real Provider call or change formal publication defaults.

### 1. Verify the rehearsal service before touching the browser

- Before launching, run `git worktree list --porcelain` and verify the selected
  worktree contains both `.venv\Scripts\python.exe` and
  `scripts\testing\run_p7_browser_rehearsal.py`.  Check that the chosen run
  directory does not exist and that the port is not already listening.  These
  are launch preconditions, not reasons to invent a different entry point.
- Use the existing Provider-disabled entry point only:

  ```powershell
  .venv\Scripts\python.exe scripts\testing\run_p7_browser_rehearsal.py --port <port> --run-dir tmp\<fresh-run-dir>
  ```

- The run directory must not already exist. Prefer starting the command as a long-lived Codex exec session and retain both its exec-session ID and the listening OS PID. Poll that same exec session during the batch. A detached `Start-Process -WindowStyle Hidden` may be used only when its PID and redirected stdout/stderr are retained; do not assume it survived a turn interruption or context compaction.
- On Windows, `CreateProcessWithLogonW failed: 1909` is a command-host launch
  failure: the rehearsal child did not start.  Do not retry the same default
  command channel, change ports, switch launch methods, or debug the browser.
  First verify that no PID/listener/run directory was created, then rerun the
  exact command once through the approved elevated exec channel and retain its
  exec-session ID.  If an interruption occurs after a launch returned a
  session ID, poll that session and the health endpoint before considering any
  restart.
- Verify `http://127.0.0.1:<port>/__p7__/health` before navigating. The response must contain `"ok": true` and `"provider_enabled": false`.
- Recheck the health endpoint before every major matrix group and immediately after any interrupted turn. If the page says the site cannot be reached or shows `Failed to fetch`, check the retained exec session/PID, listening port, health endpoint, stdout, and stderr first. Those messages mean the frontend could not reach the local service until proven otherwise; do not troubleshoot the page, upload control, fixture, or browser security policy until the service is healthy.
- Never enable Provider transport for this rehearsal. At the end, verify `runtime.jsonl` has zero `forbidden_provider_transport` events and report actual Provider initiated calls as 0.

### 2. Select an available visual control capability

- Prefer the installed Browser capability for the existing Codex in-app browser
  tab at `http://127.0.0.1:<port>/`. After a REPL reset, reacquire that tab by
  URL before creating another. If `cua_repl` is the available interface, its
  first call in a fresh session is:

  ```javascript
  let tab = await cua.getTab(
    { url: "http://127.0.0.1:<port>/" },
    { browser: "iab" },
  );
  ```

  Check the returned browser identity and URL. Use fresh accessibility/DOM
  state and role/name locators where available. Do not substitute an unrelated
  Chrome/Edge profile or add Playwright CLI/Selenium.
- If this binding is unavailable, check the installed Browser plugin/runtime
  once. The Computer Use skill prohibits operating the Codex desktop UI, so
  it is not a fallback for the in-app browser. Mark visual oracles `unassessed`
  and use the existing HTTP app path for nonvisual oracles. Do not infer that
  a nearby click succeeded from pointer position alone.
- HTTP may create/upload/chat in a session and the browser may subsequently
  inspect that same session's visible answer, chart, export, and refresh. Such
  a combined run assesses those visual oracles, while the upload picker remains
  `unassessed`. Keep session IDs and control actions in one run record.
- For a Provider-disabled HTTP-only run, use the same healthy rehearsal
  service and its existing `/api/upload`, `/api/chat`, SSE, session, and export
  endpoints. A bounded run-dir script may drive those endpoints; record its
  digest, scenario inputs, upload ticket filename/SHA, session IDs, one
  terminal per turn, persisted state, and `provider_calls=0`. This is app-path
  evidence, not E3 visual evidence. Do not use the frozen real-Provider P08
  driver against the rehearsal service or call the route a browser pass.

### 3. Upload and verify through the selected route

For a browser-upload oracle, first use the visible upload control with the
Browser tool's `filechooser`. Attach the rejection handler when creating the
promise so a timeout cannot reset the browser kernel:

```javascript
const chooserPromise = tab.playwright
  .waitForEvent("filechooser", { timeoutMs: 10000 })
  .catch(error => ({ error: String(error) }));
await tab.playwright
  .locator('label:has(input[type="file"])')
  .first()
  .click();
const chooser = await chooserPromise;
if (chooser.error) throw new Error(chooser.error);
await chooser.setFiles(paths, { timeoutMs: 10000 });
```

- Resolve fixtures to absolute paths first and attach all files for a scenario
  together. After any upload action, fetch fresh visible state and confirm each
  filename and the returned upload ticket before sending the prompt.
- If the visible control click misses or the filechooser bridge fails, capture
  fresh UI evidence once. An official Browser `setFiles` on a verified file
  control is permitted as a **new labelled UI procedure**; verify filenames
  and tickets afterward. Do not repeatedly click guessed coordinates or use
  Computer Use to operate the Codex window. If Browser upload is unavailable,
  use the existing `/api/upload` HTTP route and mark the picker oracle
  `unassessed`; do not call the product upload broken from automation alone.

### 4. Stable chat and confirmation operations

- Fill the visible `textarea`, then click the button named `发送消息`.
- Start a fresh scenario with the button named `新建会话`; preserve same-session chains such as B02 -> B02-NEG and IC-B03 -> IC-B04-REUSE -> IC-B04-CHANGE.
- Select clarification options by their visible radio label and click `提交`. Use `跳过` only where the matrix explicitly requires it.
- Observe completion through a scenario-specific final sentence, clarification card, or fail-closed notice, then confirm `run_state.json` or the existing task/session API before starting the next session. `思考中...` can disappear while a tool is still running, so its disappearance alone is not a completion signal. Visible and hidden copies of text can coexist, so do not depend on an exact-text locator that requires a single match.

### 5. Execute and evaluate the matrix consistently

- Run the whole frozen matrix in order. For ordinary scenario failures, record the session ID and evidence and continue; diagnose and repair only after the batch finishes.
- Preserve the established multi-turn browser sequences: B04 uses its frozen initial prompt followed in the same session by `【B04】继续第2步` through `【B04】继续第13步`; B03 and CONTENT-B03 send `好的，继续。` in the same session before using the compression dialog, because a single short turn is intentionally not compressible.
- Stop a dependent path only for session/data isolation failure, incomplete event transport, evidence-level escalation, or whole-service unavailability.
- Do not locally rerun only a failed scenario and present it as an uninterrupted complete batch. A separately frozen and authorized supplement may cover only an unfinished scenario when the earlier scenarios have intact, independently reviewable receipts and the interruption is an explicit Provider call cap. Record the two result identities and the supplement boundary; a code or route change affecting product behavior still needs the relevant complete batch again.
- At the end, inspect browser console warnings/errors, refresh the required sessions, verify exports and persisted state, check unique terminal events, and reconcile the runtime trace.
- Local scripted-browser evidence is not real-Provider, staging, production, or deployment evidence. A real-Provider batch requires a newly frozen exact commit, model, endpoint, fixture/prompt/oracle digest, matrix, budget, ledger path, and new explicit user authorization.

### 6. Preserve evidence and repository state

- Record the service PID, port, run directory, session IDs, stdout/stderr paths, matrix results, and Provider initiated call count in the existing implementation/audit record.
- Do not add a new browser test framework, model-review call, probe family, or duplicate ledger mechanism.
- Preserve unrelated dirty or untracked user files. Stage only named files and never reset or bulk-stage the worktree.

## P08 HTTP-controlled matrix when browser automation is unusable

The user authorized changing the control path on 2026-09-26 after confirming
that manual upload works while automated clicks missed the control. Do not call
this a product upload failure. A Provider-disabled local probe of the existing
`/api/upload` → `/api/chat` → SSE → persisted session path completed with one
terminal event and zero Provider calls in `tmp/phase9-http-probe-20260926-r1`.

- Keep the existing `run_p08_real_matrix.py` isolated service and authoritative
  `provider-calls.jsonl` ledger. The frozen contract must identify
  `control_route=local_http_api` and include the HTTP driver's digest. Freeze a
  new HEAD, launcher/driver/contract, model, endpoint, fixtures, all M01–M06
  prompts/oracles, a finite call cap and ledger path. Obtain explicit authorization
  for that exact batch; the earlier browser-protocol r2 freeze is invalid for
  this route. No real call may precede that authorization.
- Use only `scripts/testing/run_p08_http_matrix.py` against the existing local
  app endpoints. The driver posts frozen files to `/api/upload`, checks returned
  filename and SHA256, passes those tickets to `/api/chat`, consumes SSE, checks
  the single terminal against durable run state, and records session IDs. M04
  uploads v1 and v2 in the frozen order within one session. M06 resumes only
  the frozen business option. Do not silently retry a partial batch.
- Run the whole matrix in order. Continue ordinary scenario failures; stop for
  event/session isolation, Provider/accounting, or whole-service failures. Keep
  the Provider ledger separate from HTTP control evidence. At the end reconcile
  started/dispatched/failed counts, persisted sessions, exports and actual
  Provider calls.
- This route tests real model behavior through the normal app/AgentLoop/tools,
  upload ticket binding, SSE and persistence. It does **not** test whether an
  automated or human click opens the upload picker, visual claim rendering, or
  a browser refresh. Mark those UI oracles `unassessed`; do not report full
  browser E4 or Phase 5–8 exit from this batch alone. The user-confirmed manual
  upload is context, not an auditable matrix receipt.

### Call-cap supplement after an otherwise intact matrix

If a frozen matrix reaches its explicit Provider call cap during its final
scenario, keep the original freeze, ledger, sessions and failure record
immutable. A user-authorized supplement may run only that unfinished scenario
through the same app path, with its own fresh directory, freeze, finite cap,
ledger and exact authorization. Freeze the prior freeze, ledger and HTTP result
digests and the scenario scope; verify that the old ledger ended at the cap and
the failed session has no resumable confirmation. Keep the original scenario
fixtures, prompts and oracles. An already failed turn starts in a fresh isolated
session; never mutate its old run state or restart an old ledger counter.

Report a composite assessment as two labelled result identities. Previously
completed scenarios may retain their receipts, but the supplement cannot turn
the original atomic batch into a pass or assess its visual oracles. If product
code, model, endpoint, fixture, prompt, oracle or control route changes, do not
splice results; run the relevant complete matrix on one new identity. Diagnose
any ordinary semantic failures separately from this cost-saving supplement.
