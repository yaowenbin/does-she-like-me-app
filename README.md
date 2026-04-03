# does-she-like-me-web（管理页面 MVP）

管理页面：支持导入 **微信聊天导出 txt 文本** → 生成“证据卡片/多透镜分析” → 调用 **DeepSeek（OpenAI 兼容接口）**并展示报告。

## 运行方式（开发）

### 1) 后端uvicorn app.main:app --reload --port 8000

```bash
cd backend
pip install -r requirements.txt
python -m playwright install chromium
uvicorn app.main:app --reload --port 8000  # 端口被占用可改成 8001

:: 建议：用 `.env` 管理密钥（见下方「推荐配置」），避免把环境变量写进 README
```

说明：如果不配置 `OPENAI_API_KEY`，后端会进入 stub 模式，返回演习占位文本（用于联调前后端）。

### 推荐配置（强烈建议使用 .env）

1. 在 `does-she-like-me-web/` 目录创建 `.env`
2. 把 `.env.example` 里的内容复制一份填上自己的 Key（绝不要提交到开源仓库）

### 模板来源（Skill prompts）

技能包来自开源仓库 **[does-she-like-me](https://github.com/yaowenbin/does-she-like-me)**（`skills/does-she-like-me`）。

**解析顺序（工程化默认）：** 显式环境变量 → 与本仓库并排的 monorepo 开发路径 → `DATA_DIR/.skills/does-she-like-me` 缓存 → **首次需要时自动 `git clone` 官方仓库并安装到缓存**（需本机已安装 Git 且可访问 GitHub；可用 `DOES_SHE_LIKE_ME_SKILLS_GIT_URL` 指向镜像）。

**命令行预装（推荐发布/离线前执行）：** 在 `backend` 目录：

```bash
python -m app.skills_bundle install
python -m app.skills_bundle status
```

仅拷贝 web 项目、不需要自动下载时：关闭自动安装并手动指定路径：

```bash
set DOES_SHE_LIKE_ME_SKILLS_AUTO_INSTALL=0
set DOES_SHE_LIKE_ME_SKILL_ROOT=绝对路径\to\skills\does-she-like-me
```

### 2) 前端

```bash
cd frontend
npm i
npm run dev
```

前端默认把 `/api` 转发到 `http://127.0.0.1:${VITE_BACKEND_PORT}`；不设则为 `8000`。

可选：`frontend/.env` 中设置 `VITE_WECHAT_MP_URL=https://mp.weixin.qq.com/...` 显示「关注公众号」外链。

### 报告流水线（LangGraph · graph-v1）

- 生成报告走 **多步图**：`build → base（主模型）→ finalize`；若勾选「深度推理」，在 `base` 之后追加 **`deepseek-reasoner`（可配）** 对整稿再审。
- **用量与缓存 POC**：每次 LLM 调用写入 SQLite 表 **`llm_usage_log`**（含 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`，便于对照 [DeepSeek Context Caching](https://api-docs.deepseek.com/guides/kv_cache)）。
- **接口**：`POST /api/archives/{id}/analyze`  body 支持 `deep_reasoning`；`GET /api/config/analyze` 返回附加扣次与 reasoner 模型名（给前端展示）。
- **设计文档**：`docs/PIPELINE实现与扩展设计.md`；总方案：`技术方案-标杆流水线与成本控制.md`。

环境变量补充：

- **`DEEP_REASON_EXTRA_CREDITS`**（默认 `1`）：开启深度推理时，在基础 1 次之外多扣的次数；reasoner 节点失败会自动**退回**该附加次数。
- **`DEEPSEEK_REASONER_MODEL`**（默认 `deepseek-reasoner`）：深度节点模型名。

### 次数、卡密与公众号引流（自建）

- 前端通过请求头 **`X-Device-Id`**（本地 `localStorage` UUID）标识设备；**不建账号体系**也可按设备扣次。
- **`ENTITLEMENTS_ENFORCE=1`**：每次「生成报告」至少消耗 **1** 次；若开启深度推理，消耗 **`1 + DEEP_REASON_EXTRA_CREDITS`**；次数不足返回 HTTP 402。
- **`INITIAL_DEVICE_CREDITS`**：新设备默认赠送次数（生产可设 `0`；联调可设 `99`）。
- **卡密表 `gift_codes`**：在 SQLite 中插入 `code` + `credits`，用户在前端兑换后增加次数（一次性使用）。

```sql
INSERT INTO gift_codes (code, credits) VALUES ('你的卡密', 5);
```

- **公众号带参二维码**：`GET /api/entitlements/wechat-scene` 返回 `short_code`。在微信公众平台创建二维码时 **scene** 填该字符串；用户扫码关注后，微信服务器 `POST /api/wechat/callback`，服务端给对应设备增加 **`OA_FOLLOW_BONUS_CREDITS`（默认 1）**，且 **`oa_follow_bonus_claimed`** 保证每设备仅一次。
- 需配置 **`WECHAT_MP_TOKEN`**（与公众平台「基本配置」Token 一致），并将服务器 URL 设为 `https://你的域名/api/wechat/callback`。
- **导出 PDF**：`GET /api/archives/{id}/export/pdf`（Playwright 无头 Chromium，渲染 Markdown）；与浏览器页面布局独立，版式更稳定。

## 隐私说明

1. 上传内容会在本地后端以文件方式存储到 `backend/data/uploads/`（可在代码中调整）。
2. 调用 DeepSeek 会把“你上传的聊天文本”发送到你配置的 `OPENAI_BASE_URL`；若你使用的是自建/本地 DeepSeek 网关，则依然是纯本地数据通道。

