# 可信重构候选接回main

日期：2026-10-19。状态：本地接管、观察器修正、当前完整离线回归与身份核对已完成。唯一实施计划仍为总计划，本页记录接管及验收身份。Provider/远端MCP调用0，不推送、不进入S5。

## 当前身份

实施根D:/Project/Daily/data-agent，分支main。接管提交38f47ed98d6841239365ec7cd65911f6da485d85，父b181646ff66ea9ea3b0e6a38ffcd3d16b6687312；观察器执行提交46dbb967cd6bd0d7699eb39bf672f967c5a9305f，树735bfbc28310f209fd8ad94e10855bece85f56e2。完整回归绑定该执行提交，随后只收口本计划/验收头/本审计三个状态文档，不声称文档提交又跑整库。

来源为C:/Users/duguy/.codex/worktrees/trust-rebuild/data-agent完整工作区，codex/trust-rebuild-20260927@f7210e170d4dd1945abec15d57e364e04942eae4，加全部dirty/untracked。原678项为627跟踪当前字节、50未跟踪和明确Plotly资源；main679项另含本审计。C原HEAD、索引c5d7162d88d68139842eca5717fc5ad3bb6f59126aeade8aa5bac01042d653c3及228项状态保持。清单见artifacts/mt02/candidate-materials.json、artifacts/mt06/main-candidate-K2.json。

当前426 SHA256 35290917237eec8be006d1fc9515ca668457826016f3571717c14eb9e1ec0fed；launcher407规范化摘要ba0de7cda4d551e7308deaf4a7c56056f28bf29c7b4383301e44a86a34a298fc；两者交集402、并集431摘要e25d06f86b9d2540ba123bf381aac7c79e232543b0ff5b5ec0d0eb853f50a631。相对C只调整9个既有测试文件，生产文件与运行资源逐字节相同；新旧清单及差异见artifacts/mt06/source-change-review.json。原23文件在活动树中移除，Git原文保存于artifacts/mt02/old-main23-Git-blobs，旧Git历史及C分支引用保持。

## 保全与用户清理缺口

原tmp/mt01保全完成后，用户明确确认永久清理了D/tmp，原mt01及D历史tmp不可完整恢复。D六项材料随后全部匹配清理前独立记录SHA恢复：四项来自C原字节、一份来自Git blob 2478d16f265373a441a10631e6cdaa3addacf382、一份按此前唯一M03行diff逆转且匹配原SHA。原件、来源与索引保存在artifacts/mt02/D6-recovered、D6-recovery.json及D-index-before.bin。

用户已明确接受“保留历史清理缺口，继续提交和回归”，见artifacts/mt02/cleanup-incident-accepted.json。不得声称全部D历史tmp或清理前569项工作区换行前像已恢复。C的1249受保护原件和15历史答案保持；D从恢复点记录的4280个非接管文件核大小/时间戳保持，不以元数据核对冒充清理前全部字节证明。

## 完整回归与失败轨迹

| 身份 | 结果与边界 |
| --- | --- |
| mf1 / artifacts/mt02 | 默认沙箱宿主总运行370.071秒后仍停在静态图渲染，247个测试进度标记，未完成、无JUnit；保留原件 |
| md1诊断 | 同一现有渲染用例在提升宿主8.009秒通过；只作环境诊断，命令宿主隔离为怀疑原因 |
| mf2 / artifacts/mt03 | 7942通过、11失败、2skip，7955节点，2961.427秒；全部失败为两项固定历史输入缺失 |
| mf3 / artifacts/mt04 | 7952通过、1失败、2skip，7955节点，2823.405秒；合法ID中的999被全文数值观察器误报 |
| 观察器定向 / artifacts/mt06/focus | 20个既有函数、62实例通过，75.742秒；只作定向证据 |
| 当前mf4 / artifacts/mt07 | 7953通过/0失败/2跳过，7955节点，2778.536秒；独立完整批次，前述失败没有拼入通过 |

当前JUnit SHA256 c111596faedb6316a42fbf32b3398c6eb07c5bc6571ddf54a3a72706acfcbad9，原件已复制到artifacts/mt07/junit.xml。7955节点身份多重集与C原full3核同，无删除或新增skip。两个既有skip为live smoke禁用与Windows不允许symlink创建，均不计通过。官方入口始终为run_regression.py full-offline；每批31个证据变量及UUID分区均全新，保留进程PID、Codex exec-session、源码、控制记录和输出。

## 观察器修正与独立输入

mf3失败原ID为hypotheses_sales_trend_plan_19e3fc41f999422b016f130b_h2；原测量1.0、派生值和supported同源关系均已通过，全文子串999命中了ID。依原业务数值判据，8个既有测试文件的21处负例改用现有呈现helper识别可见数值，排除不透明ID；保留999、1000等伪造数值、派生算术、来源和持久化断言。也核了999.0、9.99e2和不同值1999，见observer-boundary-check.json、observer-repair.json及原失败原件。无产品算法、事实权限、模型调用或测试节点变化，105退役审核不重开。

mf2结束后从C按独立原SHA补回tmp/s3-chart-modes-20261014-r2/preimages/src/data_agent/tools/visualization.py及tmp/p5-real-20261009-r3/fixtures/M01-sales.csv。前者匹配原source-red.json的73d6176b摘要，后者匹配原13CSV的1e662987摘要。完整来源与耐久副本在artifacts/mt02/regression-input-recovery；后续完整批次运行前后均核C源、D目标及副本SHA。这两项历史输入不包含在Git克隆本身，清理tmp后需从保全副本按SHA恢复；未改测试路径或跳过反例。

## 环境与证据复用

D Python3.14.0、导入D/src；仅用本地uv缓存offline补齐C已有pytest-asyncio1.3.0，D原pip25.2保留，无下载或依赖升级。D实际.env未改；离线子进程MODEL_ID=gpt-4o、API_BASE回环拒绝端口、网络0、MCP false、自动发现false，测试conftest禁止未mock Provider。9份原XLSX已核同C。模型容量设置只作合成离线测试，不授权自然调用。

C原S4 full3、m09 HTTP47组/90轮零失败、六链52/52、生命周期13/13、m07/m08实际1440/747及精确MD人工实看保留原运行身份。复用条件为生产/运行资源、原13CSV/20提示/3恢复输入、独立oracle及相关隔离配置一致，且C原收据完整可读。main本轮只新核当前完整E2，不冒称新main HTTP、浏览器、自然Provider或部署批次；新导出不继承旧精确MD人工确认。改变相应源/输入/路线/配置需重新冻结并补相应验收。

## 本轮材料封存与剩余边界

当前实存D/tmp另存artifacts/mt05/current-D-tmp.zip，共162799文件、原2050128258字节，每一归档文件回读SHA一致，原件未删除。ZIP SHA256 508d6762bea4ece32e36534212e3042dec206ca5f31692df5c96c0acfa08a865；完整清单及archive-verification.json同目录。这是本轮结束时实物保全，D历史永久清理缺口保持。

原180仍118完整/62局部/0待审，不是完成率；F5缺原件ddb9daa/71e23d0、45项自然内容/语义、2项自然方法、Windows符号链接能力、整体自然门及51分钟性能问题保持，A/B/C未批准未实施。main现有launcher clean-source检查已通过，原C p04只保留历史不可执行身份；模型/端点/上下文与输出能力、新物理预算、精确新批次及授权均未批准，预算0、无自然Provider ledger启动。

当前及后续实施根为D/main。最终清洁提交与零调用身份见artifacts/mt06/main-identity-final.json，保全核对见artifacts/mt06/final-verification.json。C原件尚未全部独立封存，C工作树与分支继续保留；移除工作树前须完成可恢复保全和证据引用核验。本轮未授权或执行C删除、不推送、不进入S5、不继承旧授权。
