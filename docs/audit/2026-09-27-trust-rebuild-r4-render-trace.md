# R4.2 宿主原位渲染追踪与只读审核视图

目标树 `codex/trust-rebuild-20260927@b92034a`，供体 `main@b181646` 固定只读。本片按 R4.1 裁决，把现有 `answer_bindings.v1` 的宿主渲染结果与候选解释在同一最终答案中的位置绑定到发布包。`answer_render_trace.v1` 记录最终答案、packet、每个 claim 和待审核片段的 SHA-256 与字符区间；`publication_audit_view.v1` 只读复核已提交包、源回执、规范历史、现有 renderer 与实际正文后，给 Shadow 提供可定位输入。视图不调用模型、不改变正文、不授予发布或需求覆盖。

功能取用经过供体最终版本和目标树依赖核对：供体 `publication_audit.py` 整文件依赖目标树不存在的四类 binding 验证接口，本片仅按目标树已有 `observed_fact`、`descriptive_fit`、`observed_comparison`、`observed_aggregate`、`scenario_extrapolation` renderer 建立最小输入视图。多轮复用同一 packet 的规范历史允许定位最新匹配 assistant 轮；聚合块中由宿主生成的 fact 引用须由实际 renderer 校验，不能要求其存在于原始 `source.facts`。这两项初始只读检查误拒在最终批次前修正。

## 正常 app 验证

批前选择 `control_route=local_http_api`，独立判据沿用 R4.1 的 M01 六轮和 B04 十三轮；picker、视觉答复及浏览器刷新为 `unassessed`。先核 `git worktree list --porcelain`、目标 HEAD、`.venv\Scripts\python.exe`、指定 rehearsal 入口、空目录和端口。最终新批次 `tmp/r4trace2` 使用 `scripts/testing/run_p7_browser_rehearsal.py`（SHA-256 `60A2DDA79EF85971B0CC99D55D70F0963CB5E9E250418F9805F64DF6022E6765`），端口 5234、监听 OS PID 14404、长时 exec session 29185；批前及两组间健康均为 `ok=true, provider_enabled=false`，批后在同一 exec session 停止。

- M01 控制脚本 `tmp/r3_m01_http_probe.py` SHA-256 `CD607059FCFD3C10415E273188B928FD74F45FBCF6FD953EFC747FB7C8EF9BED`。`F-SALES.csv` 上传票据文件名及 SHA-256 `1e6629876a79225fceac0b2dc0f1d16071e532ca989b842c0489afc082f8e59d` 核对通过；会话 `9985e0ae0644` 六轮各唯一 `turn_end`、durable completed，持久会话和 Markdown 导出成功。结果 `m01-http-result.json` SHA-256 `38C6562176E8B01C2FD8FCF6EBB7D1F69152531CBC7775121186C7A29FC43A64`。
- B04 控制脚本 `tmp/r3_m04_http_probe.py` SHA-256 `B3F885F5B7C13CE790281A02877F02A6E48159EBB0F055455318A11DF943D70B`。`F-HYP.csv`、`F-HYP-FLAT.csv` 按原定顺序上传并核对票据；会话 `03b12c7e3467` 十三轮各唯一 `turn_end`、durable completed，持久会话和 Markdown 导出成功。结果 `m04-http-result.json` SHA-256 `4C5170FBBC78DF0D3FEB5AFF5329FBD9A97F7461464D7449CD5576385E93DE08`。
- 只读探针 `tmp/r4trace2/check_audit_view.py` SHA-256 `4677A67C5313F2AFA9C8FED0640829325DEA36751893D1F6D932F910B383034B`，读取上述真实会话的 analysis state、canonical conversation/meta；两会话均 `ready`。M01 定位 1 claim / 0 pending，B04 定位 1 claim / 1 pending；篡改 trace 答案 SHA 后均 `unavailable`，`publication_effect=none`。结果 `audit-view-result.json` SHA-256 `A56A87DCFF197A57EA945FE16868FC57FFBF69EA0E2BF7081B74EE7D1A581FE8`。
- `runtime.jsonl` 中 `forbidden_provider_transport` 事件为 0，实际 Provider initiated calls 为 0。本批是 Provider 禁用的 HTTP app 路径，不是自然模型、视觉、真实 Provider、正式默认或外部发布证据。

## 回归与剩余判据

定向 `test_publication_audit_view.py`、`test_publication_synthesis.py`、`test_answer_publication_contract.py`：162 passed。完整 E2 新目录 `tmp/r4tracefo`：2897 passed / 1 skipped / 16 warnings / 0 failed，runner 禁止 Provider 调用，JUnit SHA-256 `0A25C8FCC4FF1FA19DABF3198DA3FB05543AE2D1EA5BD8B0E43955FE51637D53`。

本片不改变当前 M01 内容：六种表达仍可重复同一正确的 120/12/方法/未知单位宿主正文，条件建议未交付。M06 确认后没有新的金额回执、净收益未算与成本证据不足仍未分层交付。`ready` 只表示可定位宿主结果及候选片段，不能当语义审核通过。下一片须在同一发布包及正常 app 路径实现局部组合和缺口状态，保持已算结果；开放建议的自动动作须等独立自然质量校准及相应授权。
