# AI Content OS

> 面向公众号创作者的开源 AI 内容生产操作系统：从发现选题到发布复盘，一站跑完。

**情报中心 → 选题池 → 知识库 → AI 写作 → 编辑预览 → 一键发布 → 数据回流**，完整内容生产闭环，全部跑在你自己的电脑上。

## 项目背景

写公众号最大的痛点不是"写"，而是整条流水线太碎：

- 选题靠刷信息流，热点过了才看到；
- 素材散落在收藏夹和聊天记录里，写的时候找不到；
- AI 写出来的稿子没有自己的风格，每次都要重新调教；
- 排版、发布、看数据，要在好几个工具之间来回切换；
- 哪类内容数据好，全凭感觉，没有沉淀。

AI Content OS 把这些环节装进一个本地系统：信息自动抓取打分、选题看板管理、知识库自动注入写作上下文、人设引擎保证文风一致、所见即所得发布到公众号、数据回流让 AI 帮你复盘。**无数据库服务、无前端构建、无云端依赖**——Python 标准库 + 原生 HTML，克隆即用，数据全部留在本地。

## 功能介绍

### 📡 情报中心（intel.html）
- 双信源：AI HOT 聚合源（自带 AI 评分与降噪）+ 自建 RSS 多源（`data/sources.json` 自由增删，内置 OpenAI/DeepMind/TechCrunch/量子位/36氪 等种子源）
- RSS 后台每 30 分钟自动抓取，页面可手动「立即抓取」，源抓取失败会明确提示而不是静默
- 本地 AI 批量评分（热度/商业价值/创新性/传播性/时效性），按时间窗、分类、关键词筛选
- 一键采纳为选题，自动带上原文链接和「写作前回原文核实」提醒，防重复采纳

### 🗂 选题池（topics.html）
- 五状态看板：待调研 / 待写作 / 待审核 / 待发布 / 已发布
- 从选题卡片直接发起 AI 写作、打开文章、发布公众号，状态自动流转

### 📚 知识库（knowledge.html）
- SQLite 存储，关键词检索（多关键词 AND），支持手动录入和 URL 一键导入网页正文
- **写作时自动注入**：按选题标题匹配相关知识（最多 6 条）拼入 Prompt，让 AI 用上你积累的事实、数据和观点

### ✍️ AI 写作
- 按篇幅/风格/目标读者组装 Prompt，后台调用可配置 LLM 生成 Markdown 草稿，绝不覆盖已有文件
- **人设引擎**（persona.html）：账号人设、语气、口头禅、固定开头/结尾、禁忌词，写作时自动生效
- **模板系统**：文章类型与写作指引可通过 `data/templates.json` 覆盖内置类型或新增自定义类型

### 📝 编辑与发布（index.html）
- Markdown 编辑 + iPhone 真机尺寸实时预览 + 16 种排版样式（style-manager.html 可管理/新增）
- 一键复制带内联样式的富文本，直接粘贴进公众号编辑器
- **🚀 一键发布**：调用 [baoyu-post-to-wechat](https://github.com/JimLiu/baoyu-skills) 技能脚本直接存入公众号草稿箱（API / Chrome 浏览器双模式自动选择），**所见即所得**——预览里选的样式就是发出去的样式
- **🌐 多平台版本**：一键把文章转成知乎长文 / 小红书笔记 / X 推文串，输出新文件不覆盖原稿

### 📈 数据回流（growth.html）
- 录入各平台阅读/点赞/分享/评论数据
- 「AI 复盘」自动分析哪类选题表现好、问题出在哪，给出下一步选题建议

### 🔌 任务级模型路由（data/llm.json）
- 写作、评分、转换、复盘四类任务**各自指定 provider、模型和接口**，互不影响
- 支持 `openai` / OpenAI-compatible 接口，也保留 `claude` CLI 作为默认回退
- 环境变量只注入对应任务，不污染你的交互会话；删掉配置即回退默认 Claude 登录态
- 自动剥离 LLM 输出开头的寒暄语，保证产物干净

## 安装使用

### 环境要求

| 依赖 | 用途 | 必需 |
|---|---|---|
| Python 3.10+ | 服务器与全部后端逻辑（仅标准库，无需 pip install） | ✅ |
| OpenAI API Key 或 Claude Code CLI | AI 写作 / 评分 / 转换 / 复盘 | ✅ |
| Node.js + npm | 仅「一键发布公众号」需要 | 可选 |
| Chrome | 浏览器模式发布（无公众号 API 凭据时） | 可选 |

### 快速启动

```bash
git clone https://github.com/Dan-kin/ai-content-os.git
cd ai-content-os
git switch codex-adapter
python3 server.py 8899
```

打开 `http://127.0.0.1:8899/topics.html` 即可使用。首次启动会自动创建 `data/sources.json`（RSS 源配置）并开始第一轮情报抓取。

### 可选配置

**1. 任务级模型/网关**（推荐，控制成本）

```bash
cp data/llm.json.example data/llm.json
# 编辑填入你的模型与密钥配置；该文件已 gitignore，不会被提交
```

OpenAI / Codex 推荐配置方式：

```bash
export OPENAI_API_KEY="你的 OpenAI API Key"
```

然后在 `data/llm.json` 里把 `write` / `score` / `dist` / `growth`
的 `provider` 设为 `openai`，并填入各自模型。`score` 可以用便宜快速的模型，
`write` / `growth` 建议用质量更高的模型。

如果你已经登录 Claude Code CLI，也可以删除 `data/llm.json` 或把某个任务设为
`provider: "claude"`，系统会回退到本机 `claude -p`。

**2. 一键发布公众号**

```bash
# 安装 baoyu-post-to-wechat 技能到 ~/.claude/skills/，然后安装脚本依赖：
cd ~/.claude/skills/baoyu-post-to-wechat/scripts && npm install
```

- 有公众号开发者凭据：在 `~/.baoyu-skills/.env` 配置 `WECHAT_APP_ID` / `WECHAT_APP_SECRET`，走 API 模式
- 没有凭据：自动走 Chrome 浏览器模式，首次发布扫码登录公众号后台即可

**3. 人设与模板**：打开 persona.html 配置人设；编辑 `data/templates.json` 自定义文章类型。

### 运行测试

```bash
python3 -m unittest discover -s tests   # 100+ 用例，全部离线运行
```

## 目录结构

```
ai-content-os/
├── server.py          # HTTP 服务器（标准库，多线程）
├── intel.py           # 情报：AI HOT 信源
├── intel_rss.py       # 情报：自建 RSS 多源 + AI 评分
├── store.py           # 选题池存储
├── knowledge.py       # 知识库（SQLite + 检索 + URL 导入）
├── ai_writer.py       # AI 写作（Prompt 组装 + 知识/人设注入）
├── persona.py         # 人设引擎
├── dist.py            # 多平台格式转换（知乎/小红书/X）
├── wechat_pub.py      # 公众号一键发布（调技能脚本）
├── growth.py          # 数据回流 + AI 复盘
├── llm_config.py      # 任务级模型/Provider 配置
├── llm_client.py      # 统一 LLM 调用层（Claude CLI / OpenAI-compatible）
├── *.html             # 无构建单页前端（每页一个模块）
├── content/           # 文章产出目录
├── data/              # 运行时数据（多为 gitignore）
└── tests/             # 单元 + API 测试
```

## 未来迭代计划

- [ ] **定时 / 分批发布**：选题日历排期，知乎先测试、效果好再同步公众号
- [ ] **A/B 测试**：标题、封面多版本对比
- [ ] **数据自动采集**：对接平台接口自动回流阅读/互动数据，替代手动录入
- [ ] **知识库向量检索**：语义搜索 + 混合检索，片段级复用（案例/数据/金句自动推荐）
- [ ] **情报源扩展**：GitHub Trending、Hacker News、Reddit、Product Hunt，事件聚合去重（Event Merge）
- [ ] **Agent 工作流写作**：Research → Outline → Writer → Reviewer → Fact-Check 多阶段流水线
- [ ] **多平台直发**：知乎 / 小红书 / X 发布自动化（目前已支持格式转换）
- [ ] **选题 ROI 评估**：热度 × 成本 × 竞品覆盖度，自动算选题性价比

欢迎 Issue / PR。

## 致谢

- [baoyu-skills](https://github.com/JimLiu/baoyu-skills) — 公众号发布能力来自 baoyu-post-to-wechat 技能
- AI HOT（aihot.virxact.com）— 聚合情报信源
- [Claude Code](https://claude.com/claude-code) — 原项目的 AI 能力底座，当前 fork 保留兼容

## License

[MIT](LICENSE)
