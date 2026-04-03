这里整理了**最主流、可直接部署的「去AI味Skills开源项目」**，覆盖Claude Code/OpenClaw、独立工具、本地部署三类，附核心功能、安装与使用方法，全部开源可二次修改。

### 一、核心去AI味Skills（Claude Code/OpenClaw专用）
这类是**直接嵌入AI助手的Skill插件**，用斜杠命令一键去AI腔，最适合日常写作/润色。

#### 1. Humanizer（英文原版，去AI味基准）
- GitHub：https://github.com/blader/humanizer
- 核心：基于维基百科「AI写作特征指南」，内置**24条AI痕迹检测规则**（过度连接词、套话、句式工整、语气刻板、冗余修饰等），自动重写更自然的英文表达
- 适用：Claude Code、OpenClaw
- 安装：
  ```bash
  git clone https://github.com/blader/humanizer.git ~/.claude/skills/humanizer
  ```
- 使用：`/humanizer 待处理文本`

#### 2. Humanizer-zh（中文专属，最推荐）
- GitHub：https://github.com/op7418/Humanizer-zh
- 核心：Humanizer的**中文深度本地化**，专治中文AI腔：
  - 剔除「首先/其次/最后、综上所述、值得注意的是、彰显了、至关重要」等高频套话
  - 拆分长句、调整语序、加入口语化停顿、减少书面化冗余
  - 保留原意、不丢逻辑，重写更像真人写作
- 适用：Claude Code、OpenClaw
- 安装：
  ```bash
  git clone https://github.com/op7418/Humanizer-zh.git ~/.claude/skills/humanizer-zh
  ```
- 使用：`/humanizer-zh 待处理文本`

#### 3. Stop-Slop（极简去废话+评分）
- GitHub：https://github.com/hardikpandya/stop-slop
- 核心：5维度评分（直接性、节奏感、信任度、真实感、信息密度），每项0-10分，**低于35分强制精简重写**，砍掉AI式空话、重复、过度修饰
- 适用：Claude Code、OpenClaw
- 安装：
  ```bash
  git clone https://github.com/hardikpandya/stop-slop.git ~/.claude/skills/stop-slop
  ```
- 使用：`/stop-slop 待处理文本`

#### 4. HumanWrite-Native（中文原生风格优化）
- GitHub：https://github.com/xxx/HumanWrite-Native（OpenClaw生态）
- 核心：针对自媒体/公众号/知乎优化，支持**严谨/口语/幽默/正式**4种风格切换，重构节奏、去套话、加自然表达，适配中文平台调性
- 适用：OpenClaw
- 安装：OpenClaw内直接执行「帮我安装 HumanWrite-Native」

### 二、独立开源去AI味工具（本地部署，非Skill）
适合不想依赖Claude/OpenClaw、需要本地私有化部署的场景。

#### 1. Umani（余香，个人文风建模）
- GitHub：https://github.com/fengin/umani
- 核心：**训练专属个人写作Skill**，导入你的历史文章/笔记，提取用词、句式、标点、语气偏好，生成固定风格规则，让AI每次生成都贴合你的「人话」，彻底去AI模板味
- 特点：本地运行、隐私安全、风格可迭代、支持导出为Skill嵌入Claude

#### 2. Raw.AI（英文文本拟人化）
- GitHub：https://github.com/arshverma/raw.ai
- 核心：轻量NLP模型，识别AI生成特征（句式对称、连接词密度、被动语态、抽象词），重写为更自然、口语化、有人类表达波动的英文，可绕过GPTZero等检测

#### 3. BaibaiAIGC（中文去AI痕迹+润色）
- GitHub：https://github.com/poleHansen/baibaiAIGC
- 核心：中文专用，内置去AI规则库+同义词替换+句式重构，支持批量处理，适合自媒体、文案、内容创作场景

### 三、去AI味核心Skills原理&使用技巧（避坑）
1. 核心AI味特征（Skills都在抓这些）：
   - 连接词泛滥：此外、然而、与此同时、综上所述
   - 句式过度工整：排比、对称、长难句、无口语停顿
   - 套话/空词：至关重要、深入探讨、彰显、值得注意
   - 语气刻板：过度礼貌、无个人观点、无情绪、无口语化表达
2. 最佳实践：
   - 先用 `/humanizer-zh` 去套话、拆长句
   - 再用 `/stop-slop` 精简、提密度、去废话
   - 最后手动微调：加个人语气词、短句、口语化表达、错别字/标点小瑕疵（模拟真人）
3. 二次开发：所有项目均MIT/Apache开源，可修改规则库、添加中文AI腔黑名单、自定义风格

### 四、快速安装&一键启用（Claude Code）
```bash
# 一键安装3个核心去AI味Skills
cd ~/.claude/skills
git clone https://github.com/blader/humanizer.git
git clone https://github.com/op7418/Humanizer-zh.git
git clone https://github.com/hardikpandya/stop-slop.git
# 重启Claude Code即可使用
```

需要我把这些Skills整理成一份**一键安装脚本+中文去AI味黑名单词表+最佳使用流程**，你直接复制就能用吗？

---

## 五、在 does-she-like-me-app 的工程化接入（已落地）

后端已提供可插拔后处理链（`backend/app/report_humanizer.py`）：

1. 先做启发式审计（非来源鉴定，只评估模板味风险）  
2. 做确定性清洗（重复前缀、重复行、空行归一）  
3. 按配置选择是否调用外部开源 humanizer CLI（失败自动回退，不阻塞主流程）

可用环境变量：

```bash
# off | heuristic | auto | external
REPORT_HUMANIZER_MODE=auto
REPORT_AI_TRACE_THRESHOLD=0.35
REPORT_HUMANIZER_CMD=python c:/tools/humanizer_zh_cli.py
REPORT_HUMANIZER_TIMEOUT_SEC=12
```

推荐：

- 线上：`REPORT_HUMANIZER_MODE=auto`
- 你本地验证开源效果：先设 `REPORT_HUMANIZER_MODE=external`，确认命令输出质量后再切回 `auto`。