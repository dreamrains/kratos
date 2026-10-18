# 新发布核心合同实施收据

日期：2026-09-30。执行状态只见[唯一总计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)。依据[单路径设计](../superpowers/specs/2026-09-30-trusted-answer-pipeline-redesign.md)和[新验收契约](../superpowers/validation/2026-09-30-trusted-answer-pipeline-acceptance.md)。这是本地实现/验收记录，不是第二份计划。

## 1. 身份与授权边界

实施树 `C:\Users\duguy\.codex\worktrees\trust-rebuild\data-agent`，分支 `codex/trust-rebuild-20260927`，HEAD `71e23d0ac26091365508ae1b50fa7dd88b238591`。供体 `D:\Project\Daily\data-agent@b181646ff66ea9ea3b0e6a38ffcd3d16b6687312` 只读；现有 dirty/untracked 全部保留，未暂存/提交。本轮核读本树 AGENTS、唯一计划与 PRD，沿已整理的 VP/IC/CP 原编号映射承接；worktree/HEAD/环境已核，`DATA_AGENT_SEMANTIC_AUDIT_TRIAL` 和 `PYTHONPATH` 未设置。

采用已批准的 P2 开发边界：未接入的新发布核心与预期行为测试先独立实施，产品仍只有当前旧运行路径。没有 v1 wrapper、feature flag、兼容模型草案或新的规划器/账本。没有启服务、真实 Provider、浏览器、配置切换、部署或外部 Git；本轮 Provider initiated 0。审核回调仅使用本地脚本，不是自然审核质量证据。

## 2. 本次实现与事实边界

| 责任 | 实现与实际行为 |
| --- | --- |
| 不可变快照/草案 | `agent/publication/contracts.py`；answer_bindings.v2，当前 session/turn/revision、需求、数据身份、精确 basis 与 byte digest。严格拒绝重复 JSON 键、未知字段、v1、摘要不符、异常类型、非有限值/无效 Unicode，输入/节点有界。模型 claim/artifact 节点只有 ref，不能改值。 |
| 事实字段来源 | `facts.py::resolve_result_claim`；唯一成功回执、明确文件路径与字节 SHA、原 structured SHA、当前 Workspace 版本/指纹、明确字段路径，从实际文件重读；不走 legacy 名称匹配、latest 或散文数字。缺单位保持未知。 |
| 产物来源 | `facts.py::resolve_artifact`；既有会话路径解析器、真实文件、登记字节 SHA、有界读取；当前会话所有权、跨会话/路径穿越和摘要失败拒绝。契约另验证会话相对路径，renderer 转义链接标签与路径。 |
| 一次审核 | `audit.py`；本轮至多一次回调，64 KB 请求/响应上限；绑定同一 snapshot/draft，finding 指向当前片段及其需求/claim；无重写事实、复核或重试。缺决策/超时/错误身份/无定位仅影响开放片段。纯概念咨询无需此调用。 |
| 原位组合 | `renderer.py`、`service.py`；按 sections 组织已接受文本和宿主事实、产物，缺失草案仍交付独立宿主事实；错误引用局部拒绝，附件引用去重，trace 位置对应实际正文。相同草案重复 publish 返回同一 answer_id。 |
| 需求投影 | 只从最终公开事实/产物及已接受用途产生逐项结果；九项需求八项可交付、一项具体缺口；未计算、证据不足、待业务确认、失败、部分完成与撤回分开。引用归属从宿主有效需求绑定决定，模型不能挪用撤回项。 |

`resolve_result_claim` 只证明具体工具输出字段，不授予因果、推断/预测验证或口径正确性。原生工具适配器仍须承接方法、样本、范围、单位、算术及业务确认；字段读取得到数字不是全部 FACTS 通过。HostSnapshot 的需求/claim/产物输入由宿主负责，当前不验证用户自然需求与这些语义绑定是否正确。service 不执行工具、不调规划器、不持久化；提交前 revision/current identity 重核和 durable-before-SSE 属 P3 责任。

无文件咨询测试证明该 service 可处理合法空 facts，不证明实际 intent 权限已经接通。六种表达为手写的不同正确片段，证明 renderer 不抹平成同一摘要；不计自然 M05-STYLE 通过。条件行动审核为脚本决策，不能替代独立自然正反评估。

## 3. RED→GREEN 行为收据

全部使用现有 `scripts/testing/run_regression.py`、全新目录、全局 Provider 禁用与 completion 护栏；不是新增验收框架。前两组 RED 是缺少新合同/解析器，不冒充旧自然问题重放。

| 运行目录（tmp 下） | 结果 | JUnit SHA-256 |
| --- | --- | --- |
| trust-publication-contract-red-20260930-r1 | 28 failed；新模块不存在 | 1755d48b7d4a4e2cfba639d5af59d0e51e89e53e0fbc7d83502a47396e15fa55 |
| trust-publication-contract-green-20260930-r1 | 28 passed | 0c3a46d5e13e4bdf307282b604518a91f2baaea0123c70ab649d60335ed8cbc5 |
| trust-publication-source-red-20260930-r1 | 14 failed；新事实解析器不存在 | 7f7aa0b8bc777dfcbdd0a1a8e98f889997198f05d4b5677b743ce020cf1f7d75 |
| trust-publication-source-green-20260930-r1 | 42 passed；合同与实际结果文件 | 80559c50686176a1b4b21005948f7389199cd88654426b095e46c655f83b7973 |
| trust-publication-boundary-red-20260930-r1 | 31 passed / 6 failed；kind/purpose 类型崩溃、无效 Unicode 未拒绝、3 类非法产物路径 | 85c9af32998c77316c2af093500fda30d5010845da9d5be49aeb201b4264c7b3 |
| trust-publication-boundary-green-20260930-r1 | 51 passed；上述边界修复 | 695e3b19bc5aa26a52d02b1b3814a6b94a5aca4171d4da97030bb35cad8d0ac3 |
| trust-publication-ownership-red-20260930-r1 | 51 passed / 10 failed；撤回事实/产物能被草案挪用、trace 误归属，产物解析器未实现 | 84a90e35320ec5a0e37bbe1d97eab5557462280608d281baa7471cbe1f6baf61 |
| trust-publication-ownership-green-20260930-r1 | 60 passed / 1 skipped；归属修正局部身份 | 7066c0dbf710039bed0bbcd171a661d3895640c0a1ac4533a7b7a25671fc2eea |
| trust-publication-full-offline-20260930-r1 | 3048 passed / 3 failed / 2 skipped / 16 warnings；178.00 秒 | bbb66a70299139d6c54e92ca8eaa611abc1df9ffcefab0f0d955a9a8af4762dc |
| tpub-scope-red-r1 | 60 passed / 4 failed / 1 skipped；受限范围当前回执误拒与开放片段借用他项事实 | 0c4b27e6c313591e9c67203691db4bf877c39b05cd1099a66df214d12b9bc8c6 |
| tpub-scope-green-r1 | 281 passed / 1 skipped；新合同、回执、workspace 范围、原生命周期与上传联合通过 | 679541e9b5626a31930abda0e5d0f7e9db56c5bd2f6de752147362b7e34d75f5 |

skip 是操作系统不允许创建测试用符号链接，该注入未评估；普通跨会话、缺文件、字节 SHA、穿越负例均通过。旧版/其他会话/重复回执/伪摘要/缺字段/非有限值均拒绝；局部审核失败及错误引用保留独立正确值。失败场景没有改 oracle 再报通过，RED 原目录保留。

首个完整回归暴露两项事实测试失败：source fixture 的 `s1` 会继承其他测试全局 TaskManager 目录中的 scope，而现有 `load_result_reference` 在 planning/execution/synthesis 受限范围读取 `get_data_identity` 得到空对象后误判 stale。新 fixture 隔离既有 TaskManager 存储；三个受限范围新增实际正反验收重现了产品读取缺陷，不能靠隔离测试掩盖。已沿同一 reader 用既有 `_receipt_identity_matches` 比较宿主已捕获身份，不暴露原数据；当前值保留、旧身份拒绝，范围内 `get/get_data_identity` 仍不可读。修改现有 `tools/result_reference.py` 共增 3 行说明，不新增 reader 或特权接口。新 service 同时限制开放 claim_refs 必须属于实际交付用途的有效需求，不能因 section 还包含另一问题而借用它的事实。

第三项上传失败的原子临时文件路径长度为 267，父目录存在且 payload/正式 upload.json 存在。没有修改上传产品逻辑；换短的新回归目录后相关上传测试通过，完整复验使用 `tmp/tpub-e2-r2`。原失败收据完整保留；不升级为产品上传缺陷，也不声明 Windows 长路径场景已修复。

完整复验结果见第 5 节。所有本地脚本通过均不升级 E3/E4、视觉、自然路由/语义质量或历史原始收据重放。

## 4. 代码增长与未满足的收缩门

新包 609 行：contracts 244、facts 93、renderer 59、audit 44、service 168、init 1。旧 synthesis 5417、audit 903、loop 4647，共 10967 行，本轮未修改。旧三文件与新包合计 11576，暂比基线增加 609；既有 result_reference helper 另增 3 行注释，同样计入替代逻辑核算；**尚不满足 R5 收缩/删除出口**。P2 未接入开发是设计允许的过渡，不能算减少旧债务；P3 切换必须删除旧同功能入口及承接完毕的实现测试，按旧三文件+新包+替代 helpers 合并核算，不能搬文件报缩减。

源码搜索确认新包目前只有新增 tests 调用，loop/report/旧 audit 仍调用旧 synthesis。尚未接入工作台、状态、保存/导出、旧会话只读和新会话恢复，不把 core service 通过说成 app 通过。

原始自然批次 `tmp/trust-rebuild-p08-real-71e23d0-r1` 在两个指定树下均未找到，沿用上一轮已核实的缺口；当前仅保留审核摘要，未执行原收据重放。自然源文件、默认审核质量、真实工具语义绑定、M04 原测量公开状态、应用唯一终局及视觉仍需按唯一计划继续。


## 5. 最终完整离线签收

现有入口 `.venv\Scripts\python.exe scripts\testing\run_regression.py full-offline --run-dir tmp/tpub-e2-r2`，新目录、Provider transport 禁用，exec session `69457` 最终 exit 0。结果 **3055 passed / 2 skipped / 16 warnings，174.01 秒，Provider initiated 0**；JUnit tests=3057、failures=0、errors=0、skipped=2、time=173.994，SHA-256 `9966772349e1b1f7d789b8452e0f954f8b1bc625e0be8429c2be54e8248d3a85`。

两项 skip 为既有 live smoke（本轮不授权、不执行真实调用）及新符号链接注入（OS 无创建权限）。16 项警告为已存在的退化统计样本和 JUnit record_property 配置，没有因本轮 core pass 而报修复。r1 失败收据保留；r2 是完整重新执行，非拼接失败项补测。

完整离线验证当前 core 和既有应用实现未回归；P3 未切换，因此不能签收 P4 新 app 整链、R5 收缩、E3/视觉或自然 E4。没有提交/暂存/部署/外部 Git，HEAD 未变。下一动作与缺口只在唯一总计划第 0 节维护。
