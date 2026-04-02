# does-she-like-me-web（管理页面 MVP）

管理页面：支持导入 **微信聊天导出 txt 文本** → 生成“证据卡片/多透镜分析” → 调用 **DeepSeek（OpenAI 兼容接口）**并展示报告。

## 运行方式（开发）

### 1) 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000  # 端口被占用可改成 8001

:: 建议：用 `.env` 管理密钥（见下方「推荐配置」），避免把环境变量写进 README
```

说明：如果不配置 `OPENAI_API_KEY`，后端会进入 stub 模式，返回演习占位文本（用于联调前后端）。

### 推荐配置（强烈建议使用 .env）

1. 在 `does-she-like-me-web/` 目录创建 `.env`
2. 把 `.env.example` 里的内容复制一份填上自己的 Key（绝不要提交到开源仓库）

### 模板来源（Skill prompts）

默认从本仓库内的 `../does-she-like-me/skills/does-she-like-me` 自动加载提示词模板。
若你把 web 项目单独拷走/发布，请设置：

```bash
set DOES_SHE_LIKE_ME_SKILL_ROOT=绝对路径\to\skills\does-she-like-me
```

### 2) 前端

```bash
cd frontend
npm i
npm run dev
```

前端默认把 `/api` 转发到 `http://127.0.0.1:${VITE_BACKEND_PORT}`；不设则为 `8000`。

## 隐私说明

1. 上传内容会在本地后端以文件方式存储到 `backend/data/uploads/`（可在代码中调整）。
2. 调用 DeepSeek 会把“你上传的聊天文本”发送到你配置的 `OPENAI_BASE_URL`；若你使用的是自建/本地 DeepSeek 网关，则依然是纯本地数据通道。

