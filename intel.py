"""情报中心 — AI HOT (aihot.virxact.com) 信源接入与选题采纳。

AI HOT 公开 API 已自带 AI 评分（score）与分类，MVP 直接复用。
注意：/api/public/* 必须带浏览器 UA，否则 403；since 仅支持最近 7 天。
"""
import json
import os
import threading
import time
import urllib.parse
import urllib.request

import net
import store

BASE_URL = 'https://aihot.virxact.com'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 ai-content-os/0.1')
CACHE_PATH = 'data/intel_cache.json'
ADOPTED_PATH = 'data/intel_adopted.json'
CACHE_TTL = 600  # 秒；缓存避免用户频繁切筛选时打爆对方限流

_lock = threading.Lock()


def _read_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_items(hours=24, category='', q='', take=50):
    """拉取 AI HOT 精选条目。返回 (items, from_cache)。

    缓存 key 为参数组合而非完整 URL——since 是动态时间戳，
    直接用 URL 做 key 会导致缓存永远不命中。
    """
    key = 'h%s|c%s|q%s|t%s' % (hours, category, q, take)
    with _lock:
        cache = _read_json(CACHE_PATH, {})
        entry = cache.get(key)
        if entry and time.time() - entry['fetched_at'] < CACHE_TTL:
            return entry['items'], True

    params = {'mode': 'selected', 'take': str(take)}
    if hours:
        params['since'] = time.strftime(
            '%Y-%m-%dT%H:%M:%SZ',
            time.gmtime(time.time() - float(hours) * 3600))
    if category:
        params['category'] = category
    if q:
        params['q'] = q
    url = BASE_URL + '/api/public/items?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with net.urlopen(req, timeout=20) as res:
        data = json.loads(res.read().decode('utf-8'))
    items = data.get('items', [])

    with _lock:
        cache = _read_json(CACHE_PATH, {})
        cache[key] = {'fetched_at': time.time(), 'items': items}
        _write_json(CACHE_PATH, cache)
    return items, False


def adopted_map():
    """item_id → topic_id 的采纳记录。"""
    with _lock:
        return _read_json(ADOPTED_PATH, {})


def adopt(item):
    """把情报条目转为选题。重复采纳返回已有选题，(topic_id, existed)。"""
    item_id = item.get('id') or item.get('url', '')
    if not item_id:
        raise ValueError('item id or url is required')
    with _lock:
        adopted = _read_json(ADOPTED_PATH, {})
        if item_id in adopted:
            return adopted[item_id], True

    notes = []
    if item.get('summary'):
        notes.append(item['summary'])
    if item.get('score') is not None:
        notes.append('AI HOT 评分: %s' % item['score'])
    notes.append('※ 摘要由信源 LLM 生成，写作前务必回原文核实')
    topic = store.create_topic(
        (item.get('title') or '').strip() or '(无标题)',
        type=_category_to_type(item.get('category', '')),
        source=item.get('url', ''),
        notes='\n'.join(notes))

    with _lock:
        adopted = _read_json(ADOPTED_PATH, {})
        adopted[item_id] = topic['id']
        _write_json(ADOPTED_PATH, adopted)
    return topic['id'], False


def _category_to_type(category):
    return {
        'ai-models': '新闻解读',
        'ai-products': '产品测评',
        'industry': '行业分析',
        'paper': '技术拆解',
        'tip': '教程',
    }.get(category, '新闻解读')
