"""知识库 — SQLite 存储 + 关键词检索 + URL 导入 + 写作注入。

Knowledge OS 的 MVP 简版：data/knowledge.db（gitignore），关键词
LIKE 检索（多关键词 AND），写作时按选题标题分词捞最多 6 条注入
Prompt。向量检索、片段复用留给后续阶段。
"""
import datetime
import html.parser
import os
import re
import sqlite3
import urllib.request

import net

DB_PATH = 'data/knowledge.db'
FETCH_TIMEOUT = 20
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 ai-content-os/0.1')


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        source_url TEXT DEFAULT '',
        tags TEXT DEFAULT '',
        created_at TEXT NOT NULL)''')
    return conn


def add(title, content, source_url='', tags=''):
    title, content = (title or '').strip(), (content or '').strip()
    if not title or not content:
        # 注意：错误消息会进 HTTP 状态行，必须 ASCII（http.server 限制）
        raise ValueError('title and content are required')
    with _conn() as conn:
        cur = conn.execute(
            'INSERT INTO items (title, content, source_url, tags, created_at)'
            ' VALUES (?, ?, ?, ?, ?)',
            (title, content, (source_url or '').strip(),
             (tags or '').strip(),
             datetime.datetime.now().isoformat(timespec='seconds')))
        return cur.lastrowid


def get(item_id):
    with _conn() as conn:
        row = conn.execute('SELECT * FROM items WHERE id = ?',
                           (item_id,)).fetchone()
        return dict(row) if row else None


def delete(item_id):
    with _conn() as conn:
        conn.execute('DELETE FROM items WHERE id = ?', (item_id,))


def search(q='', limit=100):
    """多关键词 AND 检索 title/content/tags；q 为空返回最新条目。"""
    words = [w for w in (q or '').split() if w]
    sql = 'SELECT * FROM items'
    args = []
    if words:
        clauses = []
        for w in words:
            clauses.append(
                '(title LIKE ? OR content LIKE ? OR tags LIKE ?)')
            args += ['%' + w + '%'] * 3
        sql += ' WHERE ' + ' AND '.join(clauses)
    sql += ' ORDER BY id DESC LIMIT ?'
    args.append(limit)
    with _conn() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def relevant_for(title, limit=6):
    """按选题标题分词（中英文词、长度>=2，OR 命中）找相关知识。"""
    words = [w for w in re.findall(r'[A-Za-z0-9.\-]+|[一-鿿]{2,}',
                                   title or '') if len(w) >= 2]
    if not words:
        return []
    clauses, args = [], []
    for w in words:
        clauses.append('(title LIKE ? OR content LIKE ? OR tags LIKE ?)')
        args += ['%' + w + '%'] * 3
    sql = ('SELECT * FROM items WHERE ' + ' OR '.join(clauses) +
           ' ORDER BY id DESC LIMIT ?')
    args.append(limit)
    with _conn() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


class _TextExtractor(html.parser.HTMLParser):
    SKIP = {'script', 'style', 'noscript', 'header', 'footer', 'nav'}

    def __init__(self):
        super().__init__()
        self.title = ''
        self._in_title = False
        self._skip_depth = 0
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self._in_title = True
        if tag in self.SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if not self._skip_depth and data.strip():
            self.chunks.append(data.strip())


def import_url(url):
    """抓取网页，提取标题与正文文本入库。返回新条目 id。"""
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with net.urlopen(req, timeout=FETCH_TIMEOUT) as res:
        raw = res.read()
    text = raw.decode('utf-8', errors='replace')
    parser = _TextExtractor()
    parser.feed(text)
    content = '\n'.join(parser.chunks)[:20000].strip()
    title = parser.title.strip() or url
    if not content:
        raise ValueError('no text content extracted from page')
    return add(title, content, source_url=url)
