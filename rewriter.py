"""AI revision module for editor-side article rewriting."""
import os
import threading
import time

import llm_client

REWRITE_TIMEOUT = 1200

MODE_GUIDES = {
    'title': '优化标题：给出更适合公众号传播的标题，但不要标题党。',
    'hook': '重写开头：前 300 字要更有场景感、冲突感和阅读钩子。',
    'deai': '去掉 AI 味：删掉空泛套话、机械转折和过度总结，改成自然中文表达。',
    'logic': '增强逻辑：让观点递进更清楚，减少重复段落。',
    'examples': '补具体例子：每个核心观点尽量补一个职场、学习或内容创作场景。',
    'wechat': '公众号化：语言更像中文公众号长文，保留观点密度和可读性。',
    'shorten': '压缩篇幅：删掉重复内容，在不丢核心观点的前提下更紧凑。',
    'checklist': '强化结尾：结尾加入可执行的自检清单或行动建议。',
}

_jobs = {}
_jobs_lock = threading.Lock()


def build_prompt(md_text, modes=None, instructions=''):
    modes = modes or []
    guides = [MODE_GUIDES[m] for m in modes if m in MODE_GUIDES]
    if not guides:
        guides = [MODE_GUIDES['deai'], MODE_GUIDES['wechat']]
    parts = [
        '你是一位资深中文公众号编辑。请在保留原文核心观点和事实边界的基础上改稿。',
        '',
        '## 改稿原则',
        '- 不要把文章改成另一篇文章；保留原有主题、立场和主要结构',
        '- 不要编造数据、案例、引用或来源；不确定的信息要保守表达',
        '- 删除空泛鸡汤、营销腔、AI 味重的句子',
        '- 输出完整 Markdown 正文，不要解释你的修改过程',
        '',
        '## 本次改稿方向',
    ]
    parts.extend('- ' + g for g in guides)
    if instructions.strip():
        parts += ['', '## 用户读后反馈/具体要求', instructions.strip()]
    parts += ['', '## 原文', md_text]
    return '\n'.join(parts)


def output_path(md_path):
    base, ext = os.path.splitext(md_path)
    ext = ext or '.md'
    path = base + '-revised' + ext
    n = 1
    while os.path.exists(path):
        n += 1
        path = '%s-revised-%d%s' % (base, n, ext)
    return path


def start_rewrite(md_path, modes=None, instructions=''):
    if not md_path.startswith('content/') or '..' in md_path:
        raise RuntimeError('文章文件必须在 content/ 目录内')
    if not os.path.isfile(md_path):
        raise RuntimeError('文章文件不存在: %s' % md_path)
    with open(md_path, 'r', encoding='utf-8') as f:
        md_text = f.read()
    out_path = output_path(md_path)
    prompt = build_prompt(md_text, modes=modes, instructions=instructions)
    job_id = 'rev%d' % int(time.time() * 1000)
    with _jobs_lock:
        _jobs[job_id] = {'status': 'running', 'source': md_path,
                         'output': out_path, 'error': ''}
    threading.Thread(target=_run, args=(job_id, prompt, out_path),
                     daemon=True).start()
    return job_id


def _run(job_id, prompt, out_path):
    try:
        text = llm_client.generate_text(
            'rewrite', prompt, timeout=REWRITE_TIMEOUT, fallback_task='write')
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
