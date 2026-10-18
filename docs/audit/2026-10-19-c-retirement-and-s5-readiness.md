# C保全交接与S5准备审核

更新：2026-10-19。唯一实施根D:/Project/Daily/data-agent，main；当前计划仍为总计划§9。此页记录核验和剩余事项，不另设阶段计划。Provider/远端MCP调用0，未推送、未进入S5，未实际删除C工作树或分支。

## 结论与运行身份

当前冻结身份下，C已无后续开发所需的唯一代码、输入或可用证据；可以在再次核同无新增工作后受控移除。C原HEAD f7210e170d4dd1945abec15d57e364e04942eae4、索引c5d7162d88d68139842eca5717fc5ad3bb6f59126aeade8aa5bac01042d653c3及228项状态均在D独立复现。C分支的历史提交通过自包含Git bundle保留，不再逐个混回main。

当前426/407/431身份仍为35290917/ba0de7cd/e25d06f8。运行源码与46dbb967cd6bd0d7699eb39bf672f967c5a9305f相同：完整7953通过/0失败/2skip、7955节点，artifacts/mt07。当前仅增状态文档和本地保全控制材料，未改生产、测试、资产、算法或权限。

## 已完成的C承接

| 内容 | D侧结果 |
| --- | --- |
| 678项完整候选 | 生产/运行资源同C；9个既有测试观察器修正保持具名。原23旧文件继续只存历史与保全，未回流活动树 |
| 全体实存文件/目录 | 1655597文件、1761039目录、25091013046字节；C-complete-r3/C-all-files.tar.gz逐项回读核同，标准tar hardlink按相同SHA复用原字节，空目录保留 |
| Git与原工作区 | git-state/all-refs.bundle自包含验证；原HEAD、原始索引、228项状态、三份Git差异及索引/reflog对象在restored-worktree独立核同 |
| 独立恢复 | restored-evidence共2119文件，包含678候选、1249受保护原件、15历史答案和177份可用文档文件引用；从归档恢复，不读取C或直接副本 |
| 历史引用 | 175份缺失D/tmp原件已补回，2份同SHA复用，0处不同D文件保留；D侧完整原件与映射可查 |
| D开发独立性 | 既有两个历史输入责任组21项通过/0失败/0skip；测试进程禁止C读取，零尝试，拒绝机制另以实际C路径挑战。只签该具名E2范围，不称新整库或浏览器 |
| D原材料 | 六项旧材料匹配清理前SHA；4280个恢复点文件大小/mtime保持，D的.env原字节及独立虚拟环境导入D/src保持 |

归档SHA256：54df261f9296fb0744ce6fac2da504602a2004f29132742a7964c32af67b5fd7。全文件索引files.jsonl及archive-verification.json同目录，Git bundle SHA及元数据见git-state/receipt.json。完整tar保留所有当前C文件；C-preserved-r3提供当前原件直接读取副本。压缩格式中的hardlink仅用于去重，restore_files.py恢复为独立普通文件。虚拟环境原字节作为环境证据保存，后续执行使用D自己的.venv。

原第一次归档在源复制前因Path类型失败；第二次串行IO尝试因耗时过长被准确停止，两次现场均保留且不计完整通过。第三次r3归档末端另发现15个历史路径分隔符归属差异，保留诊断、统一引用表示；原归档和索引未改，以独立完整回读和2119文件恢复核SHA闭合后才签当前normalized_paths收据。保全脚本的有界并行读取不涉及产品或A/B/C性能提案。

历史引用扫描覆盖main@ca59a40当时223份跟踪Markdown：177个可用C原文件已交接，65个旧路径在现存C/D中未定位，逐条列在reference-handoff-result.json。来源不一，不全部归因于本次清理。当前总计划、验收、S4收据/交接和性能附件没有因此缺失必需文件；不能宣称清理前全部D历史已恢复。

## 后续如何取用

- 当前开发、测试、自然批次均从D/main运行。旧mt02/mt06控制脚本保留历史C路径；当前检查用artifacts/mt08/verify_D_handoff.py，不依赖活C。
- 原C相对路径p对应C-preserved-r3/p或restored-evidence/p；全部文件均可从C-complete-r3按files.jsonl检索。原JSON、会话和AcceptedAnswer中的历史路径与内容保持原文，C旧会话不覆盖D活动会话。
- 未直接展开的文件可用restore_files.py，将原相对路径列表写入JSON，以--request和全新artifacts内--destination从标准tar恢复并核SHA。Git恢复过程及原始索引另见restore_git_check.py和restore-verification.json。原.git指针单独作为元数据保存，恢复Git使用独立bundle克隆。
- 移除C前再次核HEAD/索引/状态与全文件集合无新增工作；先受控移除工作树，再处理分支引用。D保全目录和Git bundle继续保留。本轮没有执行删除。
- 两个既有离线测试输入仍按原合同从D/tmp读取，原件和SHA已在D的mt02/regression-input-recovery保全。清理tmp或只克隆Git后，需按该收据恢复；这不是活C依赖，本轮没有改测试接口。

## S5前的实际剩余工作

已核.env模型openai/deepseek-flash、端点https://api.deepseek.com、凭证已配置；凭证未输出、未在线验证。官方当前文档给出deepseek-flash/DeepSeek-V4.1-Flash-1017、上下文1M、最大输出393216，默认思考开启且high。[模型说明](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)、[请求参数](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/)、[思考/工具回传](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)。此处仅为官方说明核对，不是实际模型调用收据。

当前本地目录未收录该别名，.env容量字段为空；零调用resolve_request_budget报request_model_capacity_unknown。建议本批独立进程设置MODEL_CONTEXT_TOKENS=1000000、MODEL_MAX_INPUT_TOKENS=1000000、MODEL_MAX_OUTPUT_TOKENS=393216，沿现有launcher MAX_TOKENS=65536；1000000是对1M标称的保守上界选择，不猜其精确整数。现有UTF8保守估算和10%余量给输入额度834464；无tokenizer下载。以上只形成方案，未改.env或生产代码。

393216是模型能力；现有AgentConfig对显式MAX_TOKENS上限128000、launcher固定65536。建议先保留本批65536。若要求本批实际使用393216，应先讨论配置/launcher兼容范围，修正并重新核相应证据，不能只把.env数字调大。

用户暂定最多400次、无金额上限；拟作为第一批完整M01—M06的共享总物理上限，意图、工具循环、既有一次审核、压缩和其他调用均消耗同一个总额，没有额外隐藏额度。400不是保证完成，不足时保留停止终局，不自动加额或将补跑拼为一次完整通过；第二批不继承这份预算或授权。

最终干净main上的零调用精确freeze及结果见artifacts/mt10，核对项为：HEAD＋426/407/431映射、13原CSV/20提示/3恢复选项、独立oracle/driver、完整非秘密配置、输出和容量、当前120秒请求墙钟截止、one-shot无重试/回退/续跑、控制路线local_http_api、新目录/端口/ledger及停止策略。冻结清单需用户逐批明确授权后才能启用Provider。当前实际授权调用为0，未建立Provider ledger，未启动服务。HTTP自然批次的视觉项保持未评估；原S4视觉证据仅按同生产字节和原身份复用。

## 保留的具名边界

原180仍118完整/62局部/0待审，不是完成率；105退役不重开。45项自然语义/内容、2项真实方法质量及整体自然门待S5规定的连续两批完整验收；当前不签自然通过。F5原件ddb9daa/71e23d0缺口、用户已接受的D历史tmp清理缺口、65个旧未定位路径和Windows symlink能力项保留。禁用live smoke与Windows symlink两个skip不计通过。

51分钟性能问题仍未解决；本次46分钟完整回归仅为单次观察。A/B/C仍未批准、未实施，不自动以性能改造作为本次先行工作。后续源码/方法/配置/输入/oracle改变，应重新冻结并核受影响证据；不得继承旧自然授权。
