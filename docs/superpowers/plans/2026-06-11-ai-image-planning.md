# AI Image Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an editor-side AI image planning workflow that generates article image slots and reusable prompts without directly calling an image model.

**Architecture:** Follow the existing `dist.py` and `rewriter.py` background-job pattern. Add a focused `image_planner.py` module that builds the LLM prompt, parses structured JSON, creates a non-overwriting Markdown copy with image placeholders, and writes a separate prompt pack. Wire it into `server.py`, `index.html`, `data/llm.json.example`, and README.

**Tech Stack:** Python 3.8 standard library, existing `llm_client.generate_text`, `unittest`, plain HTML/CSS/JavaScript.

---

### Task 1: Core Image Planner Module

**Files:**
- Create: `image_planner.py`
- Create: `tests/test_image_planner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_image_planner.py` with tests for prompt construction, JSON parsing, non-overwriting output paths, Markdown placeholder insertion, prompt-pack rendering, successful background jobs, and failed background jobs.

- [ ] **Step 2: Run tests to verify RED**

Run: `python3 -m unittest tests.test_image_planner`

Expected: FAIL because `image_planner` does not exist.

- [ ] **Step 3: Implement `image_planner.py`**

Create a module with:
- `build_prompt(md_text, count='standard', instructions='', insert_placeholders=True)`
- `parse_plan(text)`
- `output_paths(md_path)`
- `render_prompt_pack(source_path, plan)`
- `insert_placeholders(md_text, plan, prompt_pack_path)`
- `start_plan(md_path, count='standard', instructions='', insert_placeholders=True)`
- `get_job(job_id)`

Use `llm_client.generate_text('image', prompt, timeout=1200, fallback_task='write')`.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python3 -m unittest tests.test_image_planner`

Expected: PASS.

### Task 2: Server API

**Files:**
- Modify: `server.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Add failing API tests**

Extend existing API tests to cover:
- `POST /api/images/plan` rejects files outside `content/`.
- `POST /api/images/plan` returns a job id and output paths.
- `GET /api/images/status?job=...` returns job state.

- [ ] **Step 2: Run API tests to verify RED**

Run: `python3 -m unittest tests.test_api`

Expected: FAIL because the endpoints do not exist.

- [ ] **Step 3: Implement endpoints**

Import `image_planner` in `server.py`. Add:
- `GET /api/images/status`
- `POST /api/images/plan`

Validate `file` is within `content/`, normalize `count`, `instructions`, and `insert_placeholders`, then call `image_planner.start_plan`.

- [ ] **Step 4: Run API tests to verify GREEN**

Run: `python3 -m unittest tests.test_api`

Expected: PASS.

### Task 3: Editor UI

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Add toolbar entry and modal**

Add an “AI 配图” button next to “AI 改稿”. Add a modal with:
- Count select: light, standard, rich.
- Checkbox: insert placeholders.
- Textarea for visual direction and constraints.
- Submit button.

- [ ] **Step 2: Add front-end behavior**

Add JavaScript functions:
- `showImageModal()`
- `hideImageModal()`
- `makeImagePlan()`

Follow the existing `makeRewrite()` polling pattern and redirect to the generated `article-images.md` file when done.

- [ ] **Step 3: Smoke check page**

Run: `python3 -m py_compile server.py image_planner.py llm_client.py`

Open or curl `http://127.0.0.1:8899/index.html` and confirm the page returns 200 and contains “AI 配图”.

### Task 4: Config, Docs, and Verification

**Files:**
- Modify: `data/llm.json.example`
- Modify: `README.md`

- [ ] **Step 1: Update config sample**

Add an `image` task to `data/llm.json.example` and mention that it can use a text model to generate image prompts.

- [ ] **Step 2: Update README**

Document the “AI 配图” workflow under editor features and task-level model routing.

- [ ] **Step 3: Run full verification**

Run:
- `python3 -m unittest tests.test_image_planner tests.test_api`
- `python3 -m unittest discover -s tests`
- `python3 -m py_compile image_planner.py server.py llm_client.py`
- `python3 -m json.tool data/llm.json.example`
- `git diff --check`

Expected: all pass.

- [ ] **Step 4: Commit and push**

Stage only code/docs/tests, not generated `content/` article drafts. Commit with `Add AI image planning workflow` and push `codex-adapter`.
