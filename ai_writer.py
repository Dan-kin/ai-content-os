"""AI 写作模块 — Prompt 组装 + 调用本机 claude CLI 后台生成文章。"""
import json
import os
import re
import subprocess
import threading
import time

import knowledge
import llm_config
import persona as persona_module

TYPE_GUIDES = {
    '新闻解读': '聚焦事件本身：发生了什么、为什么重要、对行业和读者的影响。',
    '产品测评': '突出真实使用体验：核心功能、上手过程、优缺点、适合人群。',
    '技术拆解': '深入原理与实现：架构、关键技术点、与同类方案对比。',
    '行业分析': '宏观视角：市场格局、趋势判断、机会与风险。',
    '教程': '手把手步骤：环境准备、操作过程、常见问题、最终效果。',
}

TEMPLATES_PATH = 'data/templates.json'


def type_guides():
    """内置类型指引与 data/templates.json 合并（自定义可覆盖、可新增类型）。"""
    guides = dict(TYPE_GUIDES)
    try:
        with open(TEMPLATES_PATH, 'r', encoding='utf-8') as f:
            custom = json.load(f)
        for k, v in custom.items():
            if k and isinstance(v, str):
                guides[k] = v
    except (OSError, ValueError):
        pass
    return guides


def build_prompt(topic, length='2000', style='通俗易懂',
                 audience='关注 AI 的公众号读者', extra='', persona=None):
    guide = type_guides().get(topic.get('type', ''), '')
    parts = [
        '你是一位资深的微信公众号作者。请根据以下要求写一篇完整的公众号文章，'
        '直接输出 Markdown 正文，不要输出任何解释或前言。',
        '',
        '## 选题',
        '标题方向：%s' % topic['title'],
        '文章类型：%s。%s' % (topic.get('type', '通用'), guide),
    ]
    if topic.get('source'):
        parts.append('参考来源：%s' % topic['source'])
    if topic.get('notes'):
        parts.append('选题备注：%s' % topic['notes'])
    parts += [
        '',
        '## 写作要求',
        '- 目标读者：%s' % audience,
        '- 篇幅：约 %s 字' % length,
        '- 风格：%s' % style,
        '- 第一行用 `# 标题` 给出最终标题（可以优化原标题）',
        '- 用二级标题组织正文结构，开头要有吸引人的引入，结尾给出总结或观点',
        '- 内容必须基于真实可靠的事实，不确定的信息明确标注，禁止编造数据和引用',
    ]
    if persona and not persona_module.is_empty(persona):
        parts += ['', '## 品牌人设（必须贯穿全文）']
        if persona.get('name'):
            parts.append('账号人设：%s' % persona['name'])
        if persona.get('tone'):
            parts.append('语气风格：%s' % persona['tone'])
        if persona.get('vocabulary'):
            parts.append('常用词汇/口头禅（自然融入）：%s' % persona['vocabulary'])
        if persona.get('hook'):
            parts.append('开头习惯：%s' % persona['hook'])
        if persona.get('cta'):
            parts.append('结尾习惯/CTA：%s' % persona['cta'])
        if persona.get('taboo'):
            parts.append('禁忌词（全文绝对不可出现）：%s' % persona['taboo'])
    try:
        related = knowledge.relevant_for(topic['title'])
    except Exception:
        related = []  # 知识库故障不阻塞写作
    if related:
        parts += ['', '## 参考知识（来自本地知识库，可选择性引用，仍需核实）']
        for it in related:
            parts.append('- %s：%s' % (it['title'],
                                       it['content'][:300].replace('\n', ' ')))
    if extra:
        parts += ['', '## 补充要求', extra]
    return '\n'.join(parts)


def unique_path(title):
    base = re.sub(r'[\\/:*?"<>|#\s]+', '-', title).strip('-')[:40] or 'draft'
    path = os.path.join('content', base + '.md')
    n = 1
    while os.path.exists(path):
        n += 1
        path = os.path.join('content', '%s-%d.md' % (base, n))
    return path


_jobs = {}
_jobs_lock = threading.Lock()

CLAUDE_TIMEOUT = 1200  # 秒；长文生成可能需要数分钟


def start_job(topic, params, on_finish=None):
    """启动后台生成任务，立即返回 (job_id, 输出文件路径)。

    on_finish(status, error) 在任务结束时于工作线程中回调，
    status 为 'done' 或 'error'，用于把结果持久化（如写回选题）。
    """
    out_path = unique_path(topic['title'])
    prompt = build_prompt(
        topic,
        length=params.get('length', '2000'),
        style=params.get('style', '通俗易懂'),
        audience=params.get('audience', '关注 AI 的公众号读者'),
        extra=params.get('extra', ''),
        persona=persona_module.load())
    job_id = 'job%d' % int(time.time() * 1000)
    with _jobs_lock:
        _jobs[job_id] = {'status': 'running', 'article': out_path, 'error': ''}
    threading.Thread(target=_run, args=(job_id, prompt, out_path, on_finish),
                     daemon=True).start()
    return job_id, out_path


def _run(job_id, prompt, out_path, on_finish=None):
    status, error = 'done', ''
    try:
        llm = llm_config.task_config('write')
        cmd = ['claude', '-p', prompt]
        if llm['model']:
            cmd += ['--model', llm['model']]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=CLAUDE_TIMEOUT, env=llm['env'])
        text = llm_config.strip_preamble(result.stdout)
        if result.returncode != 0 or not text:
            raise RuntimeError(result.stderr.strip() or 'claude CLI 没有输出')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(text + '\n')
        with _jobs_lock:
            _jobs[job_id]['status'] = 'done'
    except Exception as e:
        status, error = 'error', str(e)
        with _jobs_lock:
            _jobs[job_id]['status'] = 'error'
            _jobs[job_id]['error'] = error
    if on_finish:
        try:
            on_finish(status, error)
        except Exception:
            pass


def get_job(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None
