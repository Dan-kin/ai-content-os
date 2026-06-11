"""多平台格式适配 — 公众号文章一键转知乎 / 小红书 / X 版本。

Content Ops 的 MVP 简版：可配置 LLM 后台转换，输出到 content/
同名加平台后缀的新文件（绝不覆盖）。模型与接口走 data/llm.json 的
`dist` 任务键，缺省回退 `write` 配置，再回退默认登录态。
"""
import os
import threading
import time

import llm_client

CONVERT_TIMEOUT = 600

PLATFORMS = {
    'zhihu': {
        'name': '知乎',
        'guide': (
            '改写为知乎回答/文章风格：保留完整论证和长文结构，'
            '开头直接给出核心观点，正文用小标题分层，可保留 Markdown，'
            '语气理性专业、可有适度个人观点，结尾欢迎讨论。'),
    },
    'xhs': {
        'name': '小红书',
        'guide': (
            '改写为小红书笔记：总长不超过 1000 字，短段落，每段不超过 3 行，'
            '适度使用 emoji 增强可读性，开头一句抓眼球的钩子，'
            '结尾给出 3-6 个相关话题标签（#开头）。'),
    },
    'x': {
        'name': 'X(Twitter)',
        'guide': (
            '改写为 X 推文串（thread）：第一条必须有钩子，'
            '每条不超过 280 字符，条与条之间用「---」分隔并按 1/ 2/ 3/ 编号，'
            '总共 5-10 条，最后一条做总结并引导关注。'),
    },
}

_jobs = {}
_jobs_lock = threading.Lock()


def build_prompt(platform, md_text):
    if platform not in PLATFORMS:
        raise ValueError('unsupported platform: %s' % platform)
    p = PLATFORMS[platform]
    return (
        '你是多平台内容分发编辑。把下面的公众号文章改写成适合「%s」平台的版本。'
        '%s\n要求：保留原文事实与核心观点，不得新增编造内容；'
        '直接输出改写结果，不要任何解释。\n\n--- 原文 ---\n\n%s'
        % (p['name'], p['guide'], md_text))


def output_path(md_path, platform):
    """content/a.md + zhihu -> content/a-zhihu.md；已存在则追加序号。"""
    base, ext = os.path.splitext(md_path)
    path = '%s-%s%s' % (base, platform, ext or '.md')
    n = 1
    while os.path.exists(path):
        n += 1
        path = '%s-%s-%d%s' % (base, platform, n, ext or '.md')
    return path


def start_convert(md_path, platform):
    """后台转换，立即返回 job_id。"""
    if platform not in PLATFORMS:
        raise RuntimeError('unsupported platform: %s' % platform)
    if not os.path.isfile(md_path):
        raise RuntimeError('文章文件不存在: %s' % md_path)
    with open(md_path, 'r', encoding='utf-8') as f:
        md_text = f.read()
    out_path = output_path(md_path, platform)
    job_id = 'dist%d' % int(time.time() * 1000)
    with _jobs_lock:
        _jobs[job_id] = {'status': 'running', 'platform': platform,
                         'source': md_path, 'output': out_path, 'error': ''}
    threading.Thread(target=_run,
                     args=(job_id, build_prompt(platform, md_text), out_path),
                     daemon=True).start()
    return job_id


def _run(job_id, prompt, out_path):
    try:
        text = llm_client.generate_text(
            'dist', prompt, timeout=CONVERT_TIMEOUT, fallback_task='write')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(text + '\n')
        with _jobs_lock:
            _jobs[job_id]['status'] = 'done'
    except Exception as e:
        with _jobs_lock:
            _jobs[job_id]['status'] = 'error'
            _jobs[job_id]['error'] = str(e)


def get_job(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None
