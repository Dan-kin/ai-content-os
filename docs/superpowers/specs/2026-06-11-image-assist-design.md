# AI 配图规划首版设计

## 背景

当前系统已经支持选题、写作、改稿、多平台转换和公众号复制。新的痛点是：文章写完后，还缺少一层“图片编辑”能力，帮助判断哪里应该配图、每张图表达什么、以及如何把这些判断转成可复制给 ChatGPT、Codex 或其他图片模型的提示词。

首版按用户确认的方案 A 实现：在编辑器内加一个“AI 配图”按钮，不直接依赖图片生成模型。DeepSeek 等文本模型负责做配图规划和 prompt 生成；真正出图可以先由用户复制 prompt 到 ChatGPT/Codex 完成。

## 目标

- 根据当前文章内容生成 3-5 个图片建议，包括封面图、章节图、观点图或结尾清单图。
- 每个图片建议说明插入位置、图片用途、语境依据、构图建议、中文 prompt、英文 prompt、负面提示词和推荐比例。
- 支持把图片占位插入当前 Markdown，生成新稿而不覆盖原稿。
- 支持导出完整 prompt 包，方便复制到 ChatGPT、Codex 或其他出图工具。
- 沿用现有 `data/llm.json` 任务级模型路由，新增 `image` 任务，缺省回退 `write`。

## 非目标

- 首版不直接调用图片生成 API。
- 首版不管理真实图片素材文件上传。
- 首版不做复杂多步向导。
- 首版不自动判断公众号后台最终排版效果，只生成 Markdown 级占位和 prompt 包。

## 用户流程

1. 用户在 `index.html` 编辑器打开一篇文章。
2. 点击工具栏里的“AI 配图”。
3. 弹窗中选择配图强度：轻量 2-3 张、标准 3-5 张、重配图 5-7 张。
4. 用户可补充方向，例如“不要赛博风，多用职场真实场景”“封面要适合公众号传播”“图片不要出现文字”。
5. 后端保存当前文章，启动后台配图规划任务。
6. 任务完成后，系统打开一份新文件：
   - `content/<原文件名>-images.md`：带图片占位的新稿。
   - 同时生成 `content/<原文件名>-image-prompts.md`：完整 prompt 包。
7. 用户复制 prompt 到 ChatGPT/Codex 出图，再把生成图片路径替换进 Markdown 占位。

## 生成内容结构

每个图片建议使用结构化 JSON 作为 LLM 中间输出，字段如下：

- `id`：稳定编号，如 `cover`、`image-1`。
- `type`：`cover`、`section`、`concept`、`checklist`。
- `insert_after_heading`：建议插入在哪个标题或段落之后。
- `purpose`：这张图承担的表达任务。
- `context`：来自原文的语境依据。
- `visual_concept`：画面概念。
- `composition`：主体、背景、镜头、光线、色彩。
- `cn_prompt`：中文出图提示词。
- `en_prompt`：英文出图提示词。
- `negative_prompt`：避免项。
- `aspect_ratio`：如 `16:9`、`4:3`、`3:2`、`1:1`。
- `caption`：可选图注。

后端会校验 JSON，失败时保留原始文本并返回可读错误。

## Markdown 插入规则

生成的新稿不覆盖原稿。系统会在建议位置插入类似占位：

```markdown
![配图建议：判断力从工具熟练度中浮现](assets/images/ai-talent-01.png)
<!-- image-prompt: 见 AI 时代下的人才标准-image-prompts.md#image-1 -->
```

如果无法稳定匹配标题或段落，就把所有图片建议放到文章末尾的“配图建议”附录中，避免误插入。

## 架构

- 新增 `image_planner.py`：负责 prompt 构造、后台任务、JSON 解析、输出文件生成。
- `server.py` 新增：
  - `POST /api/images/plan`
  - `GET /api/images/status?job=...`
- `index.html` 新增：
  - “AI 配图”按钮。
  - 配图弹窗：图片数量、风格/禁忌补充、是否插入占位。
  - 轮询任务状态，完成后跳转新稿。
- `data/llm.json.example` 新增 `image` 任务配置，默认可使用 OpenAI-compatible 文本模型。
- `README.md` 更新功能说明。

## 错误处理

- 缺少 LLM key：复用现有 `llm_client` 错误提示。
- LLM 返回非 JSON：记录原始输出，返回“配图规划解析失败”。
- 文章过短：返回“文章内容不足，无法规划配图”。
- 插入位置匹配失败：仍生成 prompt 包，新稿只在末尾追加配图建议。

## 测试

- `tests/test_image_planner.py`
  - prompt 包含原文、用户方向、图片数量。
  - 能解析合法 JSON。
  - 非法 JSON 给出清晰错误。
  - 输出路径不覆盖原稿。
  - 能生成带图片占位的新 Markdown 和 prompt 包。
- API 层测试：
  - 非 `content/` 文件被拒绝。
  - 正常请求返回 job id。
  - 状态接口返回 done/error。

## 后续扩展

- B 方案：配图向导，增加文章气质、统一视觉风格、平台 prompt 模板。
- C 方案：抽成 Codex Skill，支持脱离本系统对任意文章生成配图方案。
- 真正出图：后续可接 OpenAI 图片模型、Replicate、Fal、ComfyUI 或本地出图服务。
