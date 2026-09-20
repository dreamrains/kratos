# Data Agent repository instructions

## Built-in browser acceptance workflow

These instructions are mandatory for local browser acceptance, especially after context compaction. Do not improvise a different browser, upload path, or automation method while a matrix is in progress.

### 1. Verify the rehearsal service before touching the browser

- Use the existing Provider-disabled entry point only:

  ```powershell
  .venv\Scripts\python.exe scripts\testing\run_p7_browser_rehearsal.py --port <port> --run-dir tmp\<fresh-run-dir>
  ```

- The run directory must not already exist. Prefer starting the command as a long-lived Codex exec session and retain both its exec-session ID and the listening OS PID. Poll that same exec session during the batch. A detached `Start-Process -WindowStyle Hidden` may be used only when its PID and redirected stdout/stderr are retained; do not assume it survived a turn interruption or context compaction.
- Verify `http://127.0.0.1:<port>/__p7__/health` before navigating. The response must contain `"ok": true` and `"provider_enabled": false`.
- Recheck the health endpoint before every major matrix group and immediately after any interrupted turn. If the page says the site cannot be reached or shows `Failed to fetch`, check the retained exec session/PID, listening port, health endpoint, stdout, and stderr first. Those messages mean the frontend could not reach the local service until proven otherwise; do not troubleshoot the page, upload control, fixture, or browser security policy until the service is healthy.
- Never enable Provider transport for this rehearsal. At the end, verify `runtime.jsonl` has zero `forbidden_provider_transport` events and report actual Provider initiated calls as 0.

### 2. Reuse the Codex built-in browser and existing tab

- Use the installed Browser/Computer Use capability with `browser: "iab"`. Do not launch Chrome, Edge, Playwright CLI, Selenium, or a native file picker.
- After a REPL reset or context compaction, reacquire the already-open tab for `http://127.0.0.1:<port>/`; do not create a second tab merely because the previous JavaScript `tab` binding was lost.
- In a fresh `cua_repl` session, the first call must contain exactly this one API call (replace `<port>` only):

  ```javascript
  let tab = await cua.getTab(
    { url: "http://127.0.0.1:<port>/" },
    { browser: "iab" },
  );
  ```

  The returned state must identify `Codex In-app Browser` / `iab` and the expected localhost URL. Then use `await tab.getAXState()` or the tab's Playwright locators; do not enumerate or select Edge/Chrome as a fallback.
- Keep one persistent `tab` binding for the batch. Use accessibility state (`getAXState`) and role/name locators for observation and actions. Avoid screen coordinates and brittle exact-text waits.
- If the browser control bridge itself is unavailable, first verify the installed Browser plugin/runtime path and restore that official binding. Do not switch automation stacks mid-batch.

### 3. Use exactly one upload procedure

Always trigger the visible upload label and handle the Browser tool's `filechooser`. Attach the rejection handler when creating the promise so a timeout cannot reset the browser kernel:

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

- Resolve every fixture to an absolute local path before starting the browser action and keep those paths in the `paths` array. Never pass a guessed or relative path to `setFiles`.
- Upload all files required by a scenario in one `setFiles` call.
- Do not operate the hidden input directly and do not open or automate the native Windows file picker.
- After `setFiles`, fetch fresh accessibility/DOM state and confirm every expected filename is visible before sending the prompt. If the list is incomplete, record the scenario as blocked; do not improvise a second upload mechanism.

### 4. Stable chat and confirmation operations

- Fill the visible `textarea`, then click the button named `发送消息`.
- Start a fresh scenario with the button named `新建会话`; preserve same-session chains such as B02 -> B02-NEG and IC-B03 -> IC-B04-REUSE -> IC-B04-CHANGE.
- Select clarification options by their visible radio label and click `提交`. Use `跳过` only where the matrix explicitly requires it.
- Observe completion through a scenario-specific final sentence, clarification card, or fail-closed notice, then confirm `run_state.json` or the existing task/session API before starting the next session. `思考中...` can disappear while a tool is still running, so its disappearance alone is not a completion signal. Visible and hidden copies of text can coexist, so do not depend on an exact-text locator that requires a single match.

### 5. Execute and evaluate the matrix consistently

- Run the whole frozen matrix in order. For ordinary scenario failures, record the session ID and evidence and continue; diagnose and repair only after the batch finishes.
- Preserve the established multi-turn browser sequences: B04 uses its frozen initial prompt followed in the same session by `【B04】继续第2步` through `【B04】继续第13步`; B03 and CONTENT-B03 send `好的，继续。` in the same session before using the compression dialog, because a single short turn is intentionally not compressible.
- Stop a dependent path only for session/data isolation failure, incomplete event transport, evidence-level escalation, or whole-service unavailability.
- Do not locally rerun only a failed scenario and present it as a complete batch. After a code fix, use a fresh run directory and execute the required complete batch again.
- At the end, inspect browser console warnings/errors, refresh the required sessions, verify exports and persisted state, check unique terminal events, and reconcile the runtime trace.
- Local scripted-browser evidence is not real-Provider, staging, production, or deployment evidence. A real-Provider batch requires a newly frozen exact commit, model, endpoint, fixture/prompt/oracle digest, matrix, budget, ledger path, and new explicit user authorization.

### 6. Preserve evidence and repository state

- Record the service PID, port, run directory, session IDs, stdout/stderr paths, matrix results, and Provider initiated call count in the existing implementation/audit record.
- Do not add a new browser test framework, model-review call, probe family, or duplicate ledger mechanism.
- Preserve unrelated dirty or untracked user files. Stage only named files and never reset or bulk-stage the worktree.
