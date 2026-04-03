# 报告生成流水线：实现说明与扩展设计

> 配套 `技术方案-标杆流水线与成本控制.md` 的**工程落地文档**。  
> 当前已实现：**graph-v1**（LangGraph：`build → base → reasoner | finalize`）、**用量落库**、**深度推理可选 + 分档扣次/失败退款**、**Analyze API 返回分步 usage（含缓存字段）**。

---

## 1. 目录与模块职责

| 路径 | 职责 |
|------|------|
| `backend/app/llm_types.py` | `CompletionUsage` / `CompletionResult`；从 OpenAI SDK 的 `usage` 抽取 `prompt_cache_hit_tokens`、`prompt_cache_miss_tokens`（[DeepSeek Context Caching](https://api-docs.deepseek.com/guides/kv_cache)）。 |
| `backend/app/llm_client.py` | `DeepSeekClient` / `StubLLMClient` 的 `complete()`；`default_reasoner_model()`。 |
| `backend/app/pipeline/report_graph.py` | LangGraph `StateGraph` 定义；`REASONER_SYSTEM`；节点内写 `llm_usage_log`。 |
| `backend/app/pipeline/runner.py` | `run_report_pipeline()` 对外入口；组装 `PipelineOutput`。 |
| `backend/app/pipeline/schemas.py` | `SupportsLLMComplete` Protocol；`usage_to_step_dict`。 |
| `backend/app/db.py` | 表 `llm_usage_log`；`log_llm_usage()`。 |
| `backend/app/entitlements_db.py` | `consume_credits` / `refund_credits`；保留 `consume_credit_for_analyze` 兼容 1 次扣减。 |
| `backend/app/main.py` | `/api/archives/{id}/analyze` 计费编排；`/api/config/analyze` 前端开关说明。 |

---

## 2. 运行时序（计费与异常）

### 2.1 正常路径

1. 客户端 `POST .../analyze`，body 含 `temperature`、`deep_reasoning`。  
2. 若 `ENTITLEMENTS_ENFORCE=1`：  
   - 扣次 `charge = 1`（仅基础）或 `1 + DEEP_REASON_EXTRA_CREDITS`（开启深度）。  
3. `run_report_pipeline` 执行 LangGraph：  
   - **build**：`build_system_and_user_prompts`（与旧版单次 Prompt 等价）。  
   - **base**：`deepseek-chat`（或环境变量主模型）生成初稿。  
   - **finalize** 或 **reasoner**：未开深度则 `final = base`；开启则 `deepseek-reasoner` 整稿审稿。  
4. 若深度节点**内部捕获异常**（网络/429 等）：`final` 回退为 `base`，`reasoner_failed=true`，服务端 **退还 `DEEP_REASON_EXTRA_CREDITS` 对应次数**（基础 1 次不退）。  
5. 若 **build/base 抛错**（含 skills 缺失 503）：**全额退还**当次已扣的 `charge`。  
6. `reports` 表写入 `model = PipelineOutput.model_label`（如 `deepseek-chat+deepseek-reasoner`）。

### 2.2 与「分阶段扣次」方案的关系

技术方案书中曾讨论「先扣 1、再扣附加」。当前实现为**单次扣 `1+extra`**，以降低事务与竞态复杂度；**语义等价**于：深度失败时退附加、整体失败时全退。

---

## 3. 数据模型

### 3.1 `llm_usage_log`（SQLite）

| 列 | 说明 |
|----|------|
| `archive_id` | 档案 ID |
| `run_id` | 单次分析 UUID（与返回 JSON 无强绑定，便于联表排查） |
| `step` | `base` \| `reasoner` |
| `model` | 实际调用模型名 |
| `prompt_tokens` / `completion_tokens` / `total_tokens` | 标准用量 |
| `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` | 缓存命中（POC 对账） |

### 3.2 `AnalyzeResult` 扩展字段

- `usage_steps[]`：与日志一致的结构化摘要，便于前端展示或调试。  
- `deep_reasoning_requested` / `deep_reasoning_used` / `reasoner_failed` / `reasoner_error`：产品与客服排障。

---

## 4. 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `DEEP_REASON_EXTRA_CREDITS` | `1` | 开启深度推理时，在基础 1 次之外多扣的次数 |
| `DEEPSEEK_REASONER_MODEL` | `deepseek-reasoner` | 深度节点模型 |
| `OPENAI_MODEL` / `DEEPSEEK_MODEL` | `deepseek-chat` | 基础节点模型 |

---

## 5. 扩展路线图（与代码的挂钩点）

### 5.1 M1：结构化子图（证据 / 量表 JSON）

- 在 `report_graph.py` 中于 **base 之前**插入节点 `extract_evidence`、`score_rubric`，输出 Pydantic 模型写入 `ReportGraphState` 新字段。  
- **base** 的 `user_prompt` 改为「仅传摘要 + JSON」，显著降本（见总方案书）。  
- 建议在 `schemas.py` 增加 `EvidencePack`、`RubricScores` 等模型，解析失败时节点级重试。

### 5.2 M2：透镜子图并行

- 使用 LangGraph `Send` API 或 `fan-out` 模式，每透镜一节点；聚合节点再进 **synthesis**（可仍为 chat，或局部 reasoner）。  
- `reasoner` 调用次数仍受 `DEEP_REASON_MAX_CALLS_PER_RUN` 约束（待实现 env）。

### 5.3 上下文缓存 POC（工程侧）

- **不改 API**：DeepSeek 侧前缀命中依赖 [官方前缀规则](https://api-docs.deepseek.com/guides/kv_cache)。  
- **要做的事**：  
  1. 多步请求间保持 **相同 system 与静态 user 前缀**（拆分节点后尤其注意顺序）。  
  2. 用 `llm_usage_log` 聚合 `prompt_cache_hit_tokens`，对比「单段巨型 Prompt」与「多步共享前缀」的命中差。  
  3. 文档化结论写入运维 README 或 Grafana（若上云）。

### 5.4 质检节点 T6

- 在 `reasoner` 与 `END` 之间增加 `lint` 节点：规则引擎 + 可选极短 LLM；失败则 **仅重试** `reasoner` 或 `synthesis` 子图。

---

## 6. 前端约定

- `GET /api/config/analyze`：展示深度推理附加扣次与 `reasoner_model`。  
- `POST .../analyze`：`deep_reasoning: boolean`； enforced 时若剩余次数不足 `1+extra`，后端 402。

---

## 7. 测试建议

- **烟测**：`backend/test_chain_smoke.py`（Stub 无 Key）应仍通过；深度开关在 Stub 下会多一段占位文案。  
- **集成**：配置真实 Key 后，开/关深度各跑一份归档，检查 `llm_usage_log` 行数与 `usage_steps`。  
- **计费**：`ENTITLEMENTS_ENFORCE=1`，深度失败场景（可 mock reasoner 抛错）验证附加次数退回。

---

*文档随 `pipeline_version` 演进；当前：`graph-v1`。*
