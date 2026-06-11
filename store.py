"""选题池数据存储 — data/topics.json 的读写封装。

所有函数使用进程内全局锁串行化读写；路径相对当前工作目录，
与 server.py 的静态文件服务保持同一约定。
"""
import json
import os
import threading
import time

TOPICS_PATH = 'data/topics.json'
STATUSES = ['待调研', '待写作', '待审核', '待发布', '已发布']

_lock = threading.Lock()


def _load():
    if not os.path.exists(TOPICS_PATH):
        return {'topics': []}
    with open(TOPICS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save(data):
    os.makedirs(os.path.dirname(TOPICS_PATH), exist_ok=True)
    with open(TOPICS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_topics():
    with _lock:
        return _load()['topics']


def create_topic(title, type='新闻解读', source='', notes=''):
    if not title or not title.strip():
        raise ValueError('title is required')
    with _lock:
        data = _load()
        topic = {
            'id': 't%d' % int(time.time() * 1000),
            'title': title.strip(),
            'type': type,
            'source': source,
            'notes': notes,
            'status': '待调研',
            'article': '',
            'created': time.strftime('%Y-%m-%d %H:%M'),
        }
        data['topics'].insert(0, topic)
        _save(data)
        return topic


def update_topic(topic_id, **fields):
    allowed = {'title', 'type', 'source', 'notes', 'status', 'article',
               'gen', 'gen_error'}
    with _lock:
        data = _load()
        for t in data['topics']:
            if t['id'] == topic_id:
                for k, v in fields.items():
                    if k not in allowed:
                        continue
                    if k == 'status' and v not in STATUSES:
                        raise ValueError('invalid status: %s' % v)
                    t[k] = v
                _save(data)
                return t
        raise KeyError(topic_id)


def delete_topic(topic_id):
    with _lock:
        data = _load()
        remaining = [t for t in data['topics'] if t['id'] != topic_id]
        if len(remaining) == len(data['topics']):
            raise KeyError(topic_id)
        data['topics'] = remaining
        _save(data)
