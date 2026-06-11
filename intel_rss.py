"""自建 RSS 信源 — 多源抓取、本地入库、AI 评分。

与 AI HOT 信源互补：源列表完全自主可配（data/sources.json，种子来自
AI-Daily 技能的源清单），条目本地滚动保存 7 天，可选用 LLM
批量打分（默认 haiku 模型控制成本）。

实时性说明：RSS 生态没有推送机制，"实时"即轮询。server.py 启动后台
线程按 settings.poll_minutes 定期刷新；页面也可手动触发。瓶颈通常在
信源自身的发布延迟，而非轮询频率。
"""
import datetime
import email.utils
import hashlib
import json
import os
import re
import threading
import time
import urllib.request

import llm_client
import net
import xml.etree.ElementTree as ET

SOURCES_PATH = 'data/sources.json'
ITEMS_PATH = 'data/intel_items.json'
KEEP_DAYS = 7
FETCH_TIMEOUT = 15
FEED_LIMIT = 30          # 单源单轮最多入库条数（feed 通常最新在前）
SCORE_BATCH = 20
MAX_SCORE_PER_RUN = 60   # 单轮最多评分条数，防止队列失控烧 token
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 ai-content-os/0.1')

# 种子源（精选自 AI-Daily 技能的源清单）；首次运行写入 sources.json 后以文件为准
DEFAULT_SOURCES = [
    {'id': 'openai-blog', 'name': 'OpenAI Blog',
     'url': 'https://openai.com/blog/rss.xml',
     'category': 'ai-models', 'enabled': True},
    {'id': 'deepmind', 'name': 'Google DeepMind',
     'url': 'https://deepmind.google/blog/rss.xml',
     'category': 'ai-models', 'enabled': True},
    {'id': 'google-research', 'name': 'Google Research',
     'url': 'https://research.google/blog/rss/',
     'category': 'paper', 'enabled': True},
    {'id': 'ms-ai', 'name': 'Microsoft AI',
     'url': 'https://blogs.microsoft.com/ai/rss/',
     'category': 'industry', 'enabled': False},
    {'id': 'techcrunch-ai', 'name': 'TechCrunch AI',
     'url': 'https://techcrunch.com/category/artificial-intelligence/feed/',
     'category': 'industry', 'enabled': True},
    {'id': 'venturebeat-ai', 'name': 'VentureBeat AI',
     'url': 'https://venturebeat.com/category/ai/feed',
     'category': 'industry', 'enabled': True},
    {'id': 'theverge', 'name': 'The Verge',
     'url': 'https://www.theverge.com/rss/index.xml',
     'category': 'ai-products', 'enabled': False},
    {'id': 'qbitai', 'name': '量子位',
     'url': 'https://www.qbitai.com/rss/',
     'category': 'industry', 'enabled': True},
    {'id': '36kr', 'name': '36氪',
     'url': 'https://36kr.com/feed',
     'category': 'industry', 'enabled': True},
    {'id': 'geekpark', 'name': '极客公园',
     'url': 'https://www.geekpark.net/rss',
     'category': 'ai-products', 'enabled': False},
    {'id': 'synced', 'name': '机器之心 Synced',
     'url': 'https://syncedreview.com/feed/',
     'category': 'paper', 'enabled': True},
    {'id': 'ithome', 'name': 'IT之家',
     'url': 'https://www.ithome.com/rss/',
     'category': 'industry', 'enabled': False},
    # arXiv 量大噪音高，默认关闭，需要时在 sources.json 打开
    {'id': 'arxiv-ai', 'name': 'arXiv cs.AI',
     'url': 'http://export.arxiv.org/rss/cs.AI',
     'category': 'paper', 'enabled': False},
    {'id': 'arxiv-cl', 'name': 'arXiv cs.CL',
     'url': 'http://export.arxiv.org/rss/cs.CL',
     'category': 'paper', 'enabled': False},
]

SETTINGS_DEFAULTS = {
    'auto_score': True,     # 抓取后自动用 claude 给新条目打分
    'score_model': 'haiku',  # 控制成本；置空字符串则用默认模型
    'poll_minutes': 30,      # 后台轮询间隔
}

_lock = threading.Lock()
_state = {'running': False, 'last_run': 0, 'last_errors': {}}


# ---------- 配置 ----------

def load_config():
    """读 sources.json；不存在则用默认种子创建。"""
    with _lock:
        if not os.path.exists(SOURCES_PATH):
            cfg = {'sources': DEFAULT_SOURCES,
                   'settings': dict(SETTINGS_DEFAULTS)}
            _write_json(SOURCES_PATH, cfg)
            return cfg
        with open(SOURCES_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    settings = dict(SETTINGS_DEFAULTS)
    settings.update(cfg.get('settings', {}))
    cfg['settings'] = settings
    cfg.setdefault('sources', [])
    return cfg


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _read_items():
    if not os.path.exists(ITEMS_PATH):
        return {}
    with open(ITEMS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


# ---------- Feed 解析 ----------

def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _strip_html(text):
    return re.sub(r'<[^>]+>', '', text or '').strip()


def _parse_feed(xml_text):
    """解析 RSS 2.0 / Atom，返回 [{title, link, date, summary}]。"""
    root = ET.fromstring(xml_text)
    entries = [el for el in root.iter() if _local(el.tag) in ('item', 'entry')]
    out = []
    for el in entries:
        d = {}
        for child in el:
            name = _local(child.tag)
            if name == 'title':
                d['title'] = (child.text or '').strip()
            elif name == 'link':
                link = (child.get('href') or child.text or '').strip()
                if link and 'link' not in d:
                    d['link'] = link
            elif name in ('pubDate', 'published', 'updated', 'date'):
                d.setdefault('date', (child.text or '').strip())
            elif name in ('description', 'summary'):
                d.setdefault('summary', _strip_html(child.text)[:300])
        if d.get('title') and d.get('link'):
            out.append(d)
    return out


def _to_iso(date_str):
    if not date_str:
        return ''
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
    except (TypeError, ValueError):
        try:
            dt = datetime.datetime.fromisoformat(
                date_str.replace('Z', '+00:00'))
        except ValueError:
            return ''
    if dt.tzinfo:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


# ---------- 抓取与入库 ----------

def refresh_all():
    """抓取全部启用的源，去重入库并清理过期条目。返回执行摘要。"""
    with _lock:
        if _state['running']:
            return {'new': 0, 'errors': {}, 'skipped': 'already running'}
        _state['running'] = True
    try:
        cfg = load_config()
        items = _read_items()
        new_count = 0
        errors = {}
        for src in cfg['sources']:
            if not src.get('enabled'):
                continue
            try:
                req = urllib.request.Request(src['url'],
                                             headers={'User-Agent': UA})
                with net.urlopen(req, timeout=FETCH_TIMEOUT) as res:
                    xml_text = res.read().decode('utf-8', errors='replace')
                deadline_ts = time.time() - KEEP_DAYS * 86400
                for entry in _parse_feed(xml_text)[:FEED_LIMIT]:
                    key = 'rss-' + hashlib.sha1(
                        entry['link'].encode('utf-8')).hexdigest()[:16]
                    if key in items:
                        continue
                    # 部分源（如 OpenAI Blog）的 feed 含全部历史存档，
                    # 入库时按发布日期挡掉过期内容
                    published = _to_iso(entry.get('date', ''))
                    if published and _iso_to_ts(published) < deadline_ts:
                        continue
                    items[key] = {
                        'id': key,
                        'title': entry['title'],
                        'url': entry['link'],
                        'source': src.get('name', src['id']),
                        'publishedAt': _to_iso(entry.get('date', '')),
                        'summary': entry.get('summary', ''),
                        'category': src.get('category', ''),
                        'score': None,
                        'fetched_at': time.time(),
                    }
                    new_count += 1
            except Exception as e:
                errors[src['id']] = '%s: %s' % (e.__class__.__name__, e)

        # 滚动清理：超过 KEEP_DAYS 的条目出库（与 AI HOT 的 7 天窗口对齐）
        deadline = time.time() - KEEP_DAYS * 86400
        items = {k: v for k, v in items.items()
                 if v.get('fetched_at', 0) >= deadline}
        with _lock:
            _write_json(ITEMS_PATH, items)
            _state['last_run'] = time.time()
            _state['last_errors'] = errors

        if new_count and cfg['settings'].get('auto_score'):
            try:
                score_pending(model=cfg['settings'].get('score_model', ''))
            except Exception:
                pass  # 评分失败不影响抓取结果，下轮再补
        return {'new': new_count, 'errors': errors}
    finally:
        with _lock:
            _state['running'] = False


def get_items(hours=0, category='', q=''):
    """读取本地条目，按发布时间倒序。hours=0 表示不限（库内最多 7 天）。"""
    items = list(_read_items().values())
    if hours:
        deadline = time.time() - float(hours) * 3600
        items = [it for it in items
                 if it.get('fetched_at', 0) >= deadline or
                 (it.get('publishedAt') and
                  _iso_to_ts(it['publishedAt']) >= deadline)]
    if category:
        items = [it for it in items if it.get('category') == category]
    if q:
        q_low = q.lower()
        items = [it for it in items
                 if q_low in (it.get('title', '') +
                              it.get('summary', '')).lower()]
    items.sort(key=lambda it: it.get('publishedAt', ''), reverse=True)
    return items


def _iso_to_ts(iso_str):
    try:
        dt = datetime.datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.timestamp()
    except ValueError:
        return 0


def status():
    with _lock:
        return {'running': _state['running'], 'last_run': _state['last_run'],
                'last_errors': dict(_state['last_errors'])}


# ---------- AI 评分 ----------

def score_pending(model='haiku'):
    """用可配置 LLM 给未评分条目批量打分（0-100）。返回成功评分条数。

    模型优先级：data/llm.json 的 score.model > sources.json 的 score_model。
    """
    items = _read_items()
    pending = [it for it in items.values() if it.get('score') is None]
    scored = 0
    for i in range(0, len(pending), SCORE_BATCH):
        batch = pending[i:i + SCORE_BATCH]
        listing = '\n'.join(
            '%d. %s — %s' % (n + 1, it['title'],
                             (it.get('summary') or '')[:100])
            for n, it in enumerate(batch))
        prompt = (
            '你是公众号选题助手。给下列 AI 资讯逐条打 0-100 分，'
            '综合考虑热度、商业价值、创新性、传播性、时效性。'
            '只输出一个 JSON 数组（长度 %d，与条目顺序一一对应），'
            '例如 [82,55]，不要输出任何其他文字。\n\n%s'
            % (len(batch), listing))
        try:
            text = llm_client.generate_text(
                'score', prompt, timeout=300, default_model=model)
            m = re.search(r'\[[\d,\s]*\]', text or '')
            scores = json.loads(m.group(0)) if m else []
        except Exception:
            scores = []
        if len(scores) != len(batch):
            continue  # 输出不合规，本批放弃，下轮重试
        for it, s in zip(batch, scores):
            items[it['id']]['score'] = max(0, min(100, int(s)))
            scored += 1
    if scored:
        with _lock:
            _write_json(ITEMS_PATH, items)
    return scored
