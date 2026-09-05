# MATRIX-A01 六场景真实 Provider 浏览器诊断验收冻结

日期：2026-08-30。状态：**已冻结，等待用户明确授权，尚未执行真实请求**。

本批次覆盖上传绑定、统计分析与会话留存/恢复等六个针对性旅程，不声称覆盖产品全部功能。它用于系统收集跨场景问题；不是已通过的验收，也不是部署许可。M01-A03 已消费，不能续用或重置其收据。

## 1. 固定身份

| 项目 | 冻结值 |
| --- | --- |
| release source digest | `sha256:2daab429dbf8d0d874d1aee6486096d81592f76bdcd99cb82163e8b084247d76` |
| 模型 | `openai/deepseek-v4-flash` |
| 整批 candidate | `sha256:a56329ac294ecc66a59435d9fe3f932328b6429df029c255afb6a3b7a191ceb6` |
| 数据包 | `sha256:c5e080e96c89fc257def56956733ef294119e89167f34ea29df22617f7f63912` |
| prompt 包 | `sha256:82b559704004318144136ac80d78116601341f0cd4a035a02abfcf80769bab16` |
| oracle 包 | `sha256:3b79a3acac2847ee666453ee0a82d10a5d3b5779ce9d3978294e08f6443fcc50` |
| 计数启动器 | `sha256:e67b10fcfaf6f9fb002d59ddba6dce54a169f5881229d2c049c620635ce74659` |

整批清单：`docs/audit/2026-08-30-real-provider-browser-matrix-a01-candidate.json`。

启动器：`tmp/real-provider-browser-matrix-a01-counted-server.py`。

六份场景清单的路径、全部提示词原文、确认选项、浏览器步骤、oracle、端口与写入范围都由整批 candidate 绑定，不能临时改词、增加追问或切换算法来争取通过。

| 场景 | 场景 candidate 哈希 |
| --- | --- |
| M01 | `sha256:40135fdca67021f7628001fcf6ac0787f571f99aab057ff0b4eb1444d9eac666` |
| M02 | `sha256:340ac3680e41456f29e7419b5827e4c940960218a1d3a57891e84d5b3fe8bd12` |
| M03 | `sha256:166ddec8da60fb123b52202c6b089558a01334d3e8ffabdaf762b280a11dcf70` |
| M04 | `sha256:822487e75973bba6ba2a64e6b377350c982e8615746deff01c32c4eecd949377` |
| M05 | `sha256:853b15207fe0863b1510046de68dc0d03b6631c54ca98862826926b74bec3e6e` |
| M06 | `sha256:b29c8505e699130d5dc29f0b48f39b5447cf21da48778465b64c9e4c16d9f954` |

哈希规则：candidate/启动器文件先将 CRLF 归一化为 LF，再对 UTF-8 字节做 SHA-256；原始 XLSX 按原始字节计。数据包为按 id 排序、去重后的 data 条目列表；prompt/oracle 包分别为 M01–M06 对应的完整 prompts 数组/oracle 对象。三种包使用 `json.dumps(ensure_ascii=False, sort_keys=True, separators=(',',':'))` 的 UTF-8 字节。源码身份由 `scripts/acceptance/release_source.py` 计算，不写 Git。

## 2. 六场景矩阵及预算

| 场景 | 主题 | 分析回合上限 | Provider 次数硬上限 | 本地端口 |
| --- | --- | --- | --- | --- |
| M01 | 上传绑定与留存闭环 | 1 | 32 | 5201 |
| M02 | 三源同周期综合 | 2 | 40 | 5202 |
| M03 | 脏数值与分析单位 | 1 | 32 | 5203 |
| M04 | 期间比较与导出 | 1 | 32 | 5204 |
| M05 | 配对前后与因果边界 | 1 | 32 | 5205 |
| M06 | 关系、cohort与优惠券 | 3 | 48 | 5206 |

合计：6 个独立场景，最多 9 个用户分析回合，全部主生成及辅助请求合计硬上限 **216 次**。上限不是消耗目标。每场景余量作废、不转移；后续场景不能补跑前面的失败内容。

共同用户路径：新会话 → 页面上传原始文件 → 按清单发送原文 → 仅响应允许的方法确认 → 实时完成/失败观察 → 场景指定的刷新、切换或导出 → 只读证据核对 → 进程关闭及计数核对。必须使用真实浏览器；不允许以直接调用 chat API、手工放入 inbox 或修改持久化文件代替浏览器路径。桌面 viewport 为 1440×1000。

- M01：留存质量、三类曲线比较、实际值与最佳拟合值双序列、证据、刷新恢复、HTML 导出。
- M02：游戏 A 视频/内购/banner 三源同周期聚合与 lineage；两回合间切到空白页且不发送，再返回；综合趋势与结论边界。
- M03：游戏互推脏数值、缺失语义、原始数据保留、分析单位与分组排名、刷新。
- M04：固定两个各 15 天的收入/订单比较，零订单日分母；会话 HTML/MD 导出和最终单条回复 Markdown 下载。
- M05：购卡前后每用户配对聚合与配对检验，保留主分析原始重复数据，区别关联与因果，刷新。
- M06：订单与付费数据关系审计、拒绝原始 many-to-many join；首次观测付费月份 cohort 与右截断；优惠券独立描述与单位披露；三回合后会话切换、HTML 导出。

所有场景检查 Workbench 会话 ID、输入框生成态、根滚动、console、工具错误、证据与任务归属。适用的确认恢复必须显示友好投影，不能显示原始 confirmation_response 协议。图表按相应 oracle 检查真实序列与图例，不能以截图存在替代数据语义。

已知 Workbench 证据延迟问题：完成事件后立即记录，再在 10 秒和 30 秒观察无刷新状态；30 秒仍未更新记失败。后续计划内刷新仍可执行，但不能把刷新恢复判为实时投影通过。观察不能触发额外模型请求。

## 3. 数据清单

共 9 份用户提供的原始文件，全部由页面上传。本批不会修改原始文件。

| 文件 | SHA-256 |
| --- | --- |
| reference/test_doc/游戏Abanner汇总数据.xlsx | `sha256:21919b8480488a3a24a19b27e75f8bf5ee9c9d36b3003e2f6d823cc154b39a8a` |
| reference/test_doc/游戏A内购数据.xlsx | `sha256:fe1644834de2c3495870ea9780d9a866bf780126368c3128924725647399624e` |
| reference/test_doc/游戏A激励视频汇总数据报表.xlsx | `sha256:cd70017a106f6f2a64ff81bab7c75f4b8936745931679fd4782c414db1088ff7` |
| reference/test_doc/游戏B留存.xlsx | `sha256:63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0` |
| reference/test_doc/游戏互推.xlsx | `sha256:063f5415f490f90967b48d2e29972b3d2e1b908335aeb4a6420a90fb2eb19f83` |
| reference/test_doc/省钱卡购卡前后订单.xlsx | `sha256:e110c7e9e4abe5e21cede1e99a77e8f8a6827ef562a773eea16482808f6dce37` |
| reference/test_doc/省钱卡订单.xlsx | `sha256:9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3` |
| reference/test_doc/省钱卡0201到0510购卡用户付费数据.xlsx | `sha256:cb0dab0ad6e0f8b7edf3ba2476bc525371f667a934242d29cf8d891a60e8ab03` |
| reference/test_doc/省钱卡代金券明细订单.xlsx | `sha256:cda47a61c8bbbcd6bcf545c485dbeb1eb877e2f0d2ad244613e7c7199c4a5e90` |

oracle 依据当前离线真实数据测试与已有 Route A replay，不依赖模型自报通过。数值容差、工具、缺失处理、统计和因果边界在各场景 candidate 中；不得执行中放宽。

## 4. 固定 Provider 与确认策略

temperature=0、timeout=120 秒、num_retries=0。主生成初始 max_tokens=8000；仅在没有可见正文且 finish_reason=length 时，允许同一逻辑调用按 8000→32000→128000 每档至多一次升档，均计入硬上限。

辅助请求采用 one-shot，初始300，授权范围仅300或800；本冻结实现固定300，不自行升档。禁止 stream→sync 补发、失败重试、模型切换、Provider fallback、额外提示词、额外分析旅程。

每个分析回合最多回应一次当前方法的 method_confirmation，只选择 value=confirm_method、标签“按此方法继续”；不允许自由文本或为新分析选择作答。未知确认/文件恢复提问停止该场景后续生成，不能擅自代用户回答。

## 5. 失败继续与整批停止边界

非阻断失败：单序列/图例、标题、根滚动、输入框状态、确认投影、console、证据延迟、统计数值、刷新恢复、导出缺失或内容等 oracle 失败，只记录并继续同一冻结场景中可达步骤。没有依赖产物的步骤记 blocked，不能标记 passed 或假称执行。

场景级停止：Provider 传输/超时/策略/并发失败、场景调用上限、上传完整性/当前会话绑定失败、需要新用户选择的确认、文件恢复提问、阻止后续状态产生的工具/流程错误。停止该场景后续生成和写操作；保留现有状态的可达只读核对。首个 Provider 失败后，该场景内所有后续逻辑调用只能本地拒绝，不增加真实次数。

**场景失败不等于整批停止。** 关闭场景进程，确认真实进程退出、没有在途 Provider 请求，核对 calls、blocked_attempts 及持久化收据后，进入下一个独立场景。即便六个场景均遇到同一类 Provider 错误，也逐个尝试一次，不重试前面场景。

只有共享边界失效才停止整批：源码/模型/数据/提示词/oracle/启动器授权不匹配，跨会话隔离或数据暴露问题，计数不明/缺失/损坏/在途，进程退出或进程锁无法证明，整批额度耗尽。首个真实调用之前任何整批预检失败必须是零调用；执行中发现上述问题只停止剩余调用，如实保留已消费次数。

硬停止优先于覆盖率目标。崩溃后不删除标记、不重建收据、不绕过未证明的计数继续。批次结束或共享停止时统一分析全部已收集反馈，不边测边改源码。

## 6. 进程、账本和允许写入

每个场景使用新 OS 进程，严格串行；进程生命期独占 batch.lock。首次进入场景前写入不可复用的 started 记录，正常结束才依据最终收据关闭。旧进程即使有延迟后台线程，仍保留关闭后的拒绝护栏，直至进程退出。下一场景启动前核实 PID 已退出，并对延迟本地拒绝计数再对账。

各场景最多写：

- `tmp/real-provider-browser-matrix-a01/Mxx/workspace/`：日志、图表、工具文件和浏览器验收证据。
- `tmp/real-provider-browser-matrix-a01/Mxx/sessions/`：新会话及会话导出文件。
- `tmp/real-provider-browser-matrix-a01/Mxx/provider-calls.json`：Provider 收据。
- `docs/audit/2026-08-30-real-provider-browser-matrix-a01-mxx-report.json`：对应场景报告，mxx 小写。

整批只增加 `tmp/real-provider-browser-matrix-a01/batch.lock`、`provider-batch.json`、上述收据的相邻原子写 .tmp 文件，以及 `docs/audit/2026-08-30-real-provider-browser-matrix-a01-report.json`。可保留浏览器工具正常产生的验收截图/DOM/console 缓存，报告中记录实际位置；不得借此读写其他浏览器用户数据。

M04 单条回复导出是唯一额外下载范围：通过页面导出新增 **一份** Markdown，默认建议名 reply.md，仅位于浏览器管理的下载位置，不覆盖任何既有文件，报告记实际绝对路径。若工具不能保证新建或拿不到安全下载目标，标记此子项 blocked，不能擅自更改全局下载设置或写到其他位置。

测试中不修改冻结源代码、candidate、launcher、原始数据或本冻结要求；不授权 Git 写操作、部署、staging、production、删除原会话或清理旧验收资料。

## 7. 只读预检与正式启动

工作目录 `D:\Project\Daily\data-agent`。当前可用运行时 `tmp/matrix-python-3.12.10/python.exe`，复用现有 .venv 包；原 .venv 基础可执行文件缺失。真实执行必须使用批准的网络路径，不以重试“测试网络”。

先设置用户已明确批准的以下固定值（值不从可变文件自动推导）：

```powershell
$env:AUTHORIZED_BATCH_SHA256='sha256:a56329ac294ecc66a59435d9fe3f932328b6429df029c255afb6a3b7a191ceb6'
$env:AUTHORIZED_SOURCE_DIGEST='sha256:2daab429dbf8d0d874d1aee6486096d81592f76bdcd99cb82163e8b084247d76'
$env:AUTHORIZED_LAUNCHER_SHA256='sha256:e67b10fcfaf6f9fb002d59ddba6dce54a169f5881229d2c049c620635ce74659'
$env:AUTHORIZED_DATA_BUNDLE_SHA256='sha256:c5e080e96c89fc257def56956733ef294119e89167f34ea29df22617f7f63912'
$env:AUTHORIZED_PROMPT_BUNDLE_SHA256='sha256:82b559704004318144136ac80d78116601341f0cd4a035a02abfcf80769bab16'
$env:AUTHORIZED_ORACLE_BUNDLE_SHA256='sha256:3b79a3acac2847ee666453ee0a82d10a5d3b5779ce9d3978294e08f6443fcc50'
$env:PYTHONDONTWRITEBYTECODE='1'
```

在首个真实调用前，必须为六个场景全部执行只读预检，并确认隔离根目录和整批报告都尚未存在；任何失败不启动服务器。只读预检不要求启用网络标记，不产生真实请求、账本或场景目录：

```powershell
$env:DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED='0'
foreach ($matrixCase in @('M01','M02','M03','M04','M05','M06')) {
  & tmp/matrix-python-3.12.10/python.exe tmp/real-provider-browser-matrix-a01-counted-server.py --case $matrixCase --preflight-only
  if ($LASTEXITCODE -ne 0) { throw 'Whole-batch preflight failed; zero real calls required.' }
}
```

正式执行仅在收到新授权之后：批准网络执行路径，令 DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED=1；以独立进程运行同一启动器的 `--case M01`（不带 --preflight-only），在浏览器完成该 case 冻结步骤。结束并对账后，依次新进程启动 M02…M06。不要用并发循环自动启动六个服务器。每次启动仍重验全批输入和当前场景全新路径。

报告必须逐场景记录会话 ID、每回合发送/确认次数、实际工具与 oracle、每项 passed/failed/blocked、可达未执行项理由、DOM/截图/console/请求证据、导出归属、实际调用/本地拒绝、停止原因、进程退出证明；整批报告汇总这些结果，不能仅报“跑过6项”。

## 8. 冻结验证状态与证据边界

详见 `docs/audit/2026-08-30-real-provider-browser-matrix-a01-freeze-validation.json`。

当前源：定向护栏40项通过；完整 `pytest tests` 2403 passed、9 skipped、39 warnings；前端语法和 git diff --check 通过。六个 --preflight-only 均 ready，真实 Provider 0次，网络启用标记0；只验证凭据存在，不验证其有效性或网络可达性。

首次从根目录无范围运行 pytest，误收集保留在 tmp 的合成测试仓库而产生 import mismatch；没有删除旧证据，改为明确 tests 范围后完整通过。

之前 M01 本地真实浏览器使用的是 scripted transport、源 bdff31c…，发现了证据延迟，不能冒充本次源的真实 Provider 验收。M02–M06 尚未完成独立全旅程浏览器预演。本次冻结属于受控诊断批次，不宣称这些路径已经通过；缺陷、环境或步骤依赖受阻将如实记录。

## 9. 可直接复制的授权文案

我授权 MATRIX-A01 六场景真实 Provider 完整浏览器诊断验收：仅在 release source digest sha256:2daab429dbf8d0d874d1aee6486096d81592f76bdcd99cb82163e8b084247d76 上，通过已批准的网络可用执行路径并设置 DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED=1，使用 openai/deepseek-v4-flash、整批 candidate sha256:a56329ac294ecc66a59435d9fe3f932328b6429df029c255afb6a3b7a191ceb6、数据包 sha256:c5e080e96c89fc257def56956733ef294119e89167f34ea29df22617f7f63912、prompt 包 sha256:82b559704004318144136ac80d78116601341f0cd4a035a02abfcf80769bab16、oracle 包 sha256:3b79a3acac2847ee666453ee0a82d10a5d3b5779ce9d3978294e08f6443fcc50 和计数启动器 sha256:e67b10fcfaf6f9fb002d59ddba6dce54a169f5881229d2c049c620635ce74659，执行 2026-08-30-real-provider-browser-matrix-a01-authorization-freeze.md 及其 candidate 冻结的 M01→M06 浏览器旅程，各场景尝试一次，共最多9个分析回合；全部主请求与辅助请求共用整批硬上限216次，M01–M06分别不得超过32/40/32/32/32/48次，余量不转移。temperature=0、timeout=120秒、num_retries=0；主生成初始max_tokens=8000，仅无可见正文且finish_reason=length时允许按8000→32000→128000每档每个逻辑调用至多一次升档；辅助请求固定初始300，仅允许300或800且禁止升档。禁止stream→sync补发、模型切换、Provider fallback、失败重试、额外提示词及补充旅程。非阻断oracle失败只记录，继续同一场景的可达步骤；场景级Provider失败、调用上限、上传绑定失败、非预期确认、文件恢复提问或阻断性工具/流程错误，只终止该场景后续生成与写操作，保留可达只读检查，缺失依赖记blocked。首个Provider失败后该场景全局熔断；确认进程退出、无在途请求且计数闭合后，继续下一个独立场景，即使前面的场景出现相同错误也不据此中止整批。首轮整批预检任一不匹配则零调用；后续发现冻结不匹配、跨会话隔离失效、计数或进程退出无法证明、整批额度耗尽时停止整批并记录各场景及合计calls与blocked_attempts。只允许写入冻结的隔离workspace、sessions、批次锁、计数收据、六份场景报告及docs/audit/2026-08-30-real-provider-browser-matrix-a01-report.json，并保留浏览器工具生成的验收证据；另仅允许M04单条回复导出新增一份浏览器Markdown下载文件，禁止覆盖并记录实际绝对路径，不能保证安全新建则只阻断该子项。不复用M01-A03旧授权，不授权Git写操作、部署、staging、production、删除原会话或测试中途改源码。

