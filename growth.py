"""数据回流 — 已发布文章表现数据录入 + AI 复盘建议。

Growth Engine 的 MVP 简版：平台数据暂靠手动录入（公众号后台数字抄过来），
存 data/growth.json；「AI 复盘」把数据交给 claude CLI 生成选题/标题优化
建议。模型接口走 llm.json 的 `growth` 键，回退 `write`，再回退默认登录态。
"""
import datetime
import json
import os
import subprocess
import threading
import time

import llm_config

DATA_PATH = 'data/growth.json'
ANALYZE_TIMEOUT = 600
COUNT_FIELDS = ('read', 'like', 'share', 'comment')

_lock = threading.Lock()
_jobs = {}


def _load():
    try:
        with open(DATA_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.setdefault('records', [])
    data.setdefault('analysis', None)
    return data


def _save(data):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    tmp = DATA_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DATA_PATH)


def add_record(article, platform, read=0, like=0, share=0, comment=0):
    article = (article or '').strip()
    if not article:
        raise ValueError('article is required')
    rec = {'id': 'g%d' % int(time.time() * 1000),
           'article': article,
           'platform': (platform or '公众号').strip() or '公众号',
           'noted_at': datetime.datetime.now().isoformat(timespec='seconds')}
    for field, value in zip(COUNT_FIELDS, (read, like, share, comment)):
        try:
            rec[field] = max(0, int(value))
        except (TypeError, ValueError):
            rec[field] = 0
    with _lock:
        data = _load()
        data['records'].insert(0, rec)
        _save(data)
    return rec


def list_records():
    with _lock:
        return _load()['records']


def delete_record(rec_id):
    with _lock:
        data = _load()
        data['records'] = [r for r in data['records'] if r['id'] != rec_id]
        _save(data)


def last_analysis():
    with _lock:
        return _load()['analysis']


def _build_prompt(records):
    lines = ['%s | %s | 阅读 %d | 点赞 %d | 分享 %d | 评论 %d | %s'
             % (r['article'], r['platform'], r['read'], r['like'],
                r['share'], r['comment'], r['noted_at'])
             for r in records]
    return (
        '你是公众号增长顾问。下面是我各篇文章在各平台的表现数据'
        '（文件名即选题方向）。请分析：1) 哪类选题/标题表现最好，共性是什么；'
        '2) 表现差的内容问题可能在哪；3) 给出 3-5 条下一步选题与写作的'
        '具体建议。直接输出 Markdown，简洁可执行。\n\n%s' % '\n'.join(lines))


def start_analyze():
    """后台 AI 复盘，立即返回 job_id。结果持久化到 data/growth.json。"""
    records = list_records()
    if not records:
        raise RuntimeError('还没有录入任何数据，先添加一条记录')
    job_id = 'ga%d' % int(time.time() * 1000)
    _jobs[job_id] = {'status': 'running', 'error': ''}
    threading.Thread(target=_run, args=(job_id, _build_prompt(records)),
                     daemon=True).start()
    return job_id


def _llm():
    cfg = llm_config.task_config('growth')
    if not cfg['model'] and cfg['env'] is None:
        cfg = llm_config.task_config('write')
    return cfg


def _run(job_id, prompt):
    try:
        llm = _llm()
        cmd = ['claude', '-p', prompt]
        if llm['model']:
            cmd += ['--model', llm['model']]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=ANALYZE_TIMEOUT, env=llm['env'])
        text = llm_config.strip_preamble(result.stdout)
        if result.returncode != 0 or not text:
            raise RuntimeError(
                (result.stderr or '').strip()[-500:] or 'claude CLI 没有输出')
        with _lock:
            data = _load()
            data['analysis'] = {
                'text': text,
                'at': datetime.datetime.now().isoformat(timespec='seconds')}
            _save(data)
        _jobs[job_id]['status'] = 'done'
    except Exception as e:
        _jobs[job_id]['status'] = 'error'
        _jobs[job_id]['error'] = str(e)


def get_job(job_id):
    job = _jobs.get(job_id)
    return dict(job) if job else None
