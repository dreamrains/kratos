# Gate C 异构模型 kimi-k3 批次预检收据（未执行 Provider）

日期：2026-08-25

## 冻结绑定

- manifest：`tests/acceptance/route_a_gate_c_heterogeneous_kimi.json`（由 `route_a_gate_c_candidates.json` 程序化抽取 R01/R02/R04/R07 四场景，问题与事实包逐字节保留）。
- 受控源码摘要：`sha256:ce01e3c2aef7efe84569fe7eefdfd5a6c1e03320dfa5f98717c7c3b2d0f8a718`（以最终提交后复算为准，执行器校验自守）。
- 模型：`openai/kimi-k3`（manifest 声明 Provider，不绑定主配置）；端点 `api_base=https://api.moonshot.cn/v1`；凭据 `api_key_env=MOONSHOT_API_KEY`（进程环境或仓库 `.env` 解析；预检已确认可解析）。
- 请求：`temperature=0.0`、`timeout_seconds=120`、`response_format={"type":"json_object"}`、`max_tokens_ladder=[2000, 8000, 32000]`。
- 场景与预算：R02、R04、R07、R01 各 `call_budget=3`，总计恰好 12 次（最坏情形）。
- prompt hash：4 场景与主模型批次逐字一致（测试 `test_heterogeneous_kimi_manifest_freezes_identical_prompts_to_the_main_batch` 三方锁定）——同 prompt 跨模型对比的是方法/范围/发布语义纪律，不是逐字一致。

## 执行器扩展（本次实现）

- `_env_or_dotenv`：进程环境优先、`.env` 文件回退解析（pydantic 的 `.env` 不进 `os.environ`，须显式解析）。
- manifest 声明 Provider（`api_base` 字面量或 `api_base_env`/`api_key_env`，互斥校验）时跳过与主配置 `model_id` 的一致性绑定；声明的环境变量缺失在预检即失败（零调用）。
- 旅程执行器同步获得该能力。

## 离线门禁

- `56 passed`（preflight + 旅程 + 守卫套件）；本次扩展 Provider 调用 `0` 次。

## 所需单独授权

```text
我授权 Gate C 异构模型批次：仅在 source digest sha256:ce01e3c2aef7efe84569fe7eefdfd5a6c1e03320dfa5f98717c7c3b2d0f8a718 上，使用 openai/kimi-k3（api_base=https://api.moonshot.cn/v1，凭据 MOONSHOT_API_KEY），执行 R02_paired_before_after、R04_game_a_synthesis、R07_end_to_end_publication、R01_retention_curve：每场景按冻结阶梯 [2000, 8000, 32000] 逐档单次请求、仅前档 response_truncated 才升档、任何一档成功即停，每场景至多 3 次、总计至多 12 次，使用本收据冻结的数据 hash、prompt hash、temperature=0、timeout=120 秒、response_format={"type":"json_object"}，并仅写入 docs/audit/2026-08-25-gate-c-heterogeneous-kimi-batch-report.json。预检不通过则零调用；批内失败记录后继续其余场景；不重试、不换模型、不回退、不补跑。
```
