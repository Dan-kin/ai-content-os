import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

import server


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.old_cwd = os.getcwd()
        os.chdir(cls.tmp)
        os.makedirs('content', exist_ok=True)
        cls.httpd = server.ReuseTCPServer(('127.0.0.1', 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        os.chdir(cls.old_cwd)
        shutil.rmtree(cls.tmp)

    def _post(self, path, payload):
        req = urllib.request.Request(
            'http://127.0.0.1:%d%s' % (self.port, path),
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read().decode('utf-8'))

    def _get(self, path):
        url = 'http://127.0.0.1:%d%s' % (self.port, path)
        with urllib.request.urlopen(url) as res:
            return json.loads(res.read().decode('utf-8'))

    def test_topic_crud_roundtrip(self):
        created = self._post('/api/topics/create',
                             {'title': 'API 测试选题', 'type': '教程'})
        tid = created['topic']['id']

        topics = self._get('/api/topics')['topics']
        self.assertTrue(any(t['id'] == tid for t in topics))

        updated = self._post('/api/topics/update',
                             {'id': tid, 'status': '待写作'})
        self.assertEqual(updated['topic']['status'], '待写作')

        self._post('/api/topics/delete', {'id': tid})
        topics = self._get('/api/topics')['topics']
        self.assertFalse(any(t['id'] == tid for t in topics))

    def test_create_without_title_is_400(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post('/api/topics/create', {'title': ''})
        self.assertEqual(ctx.exception.code, 400)


class GenerateTest(ApiTest):
    def test_generate_creates_article_and_updates_topic(self):
        created = self._post('/api/topics/create', {'title': '生成测试选题'})
        tid = created['topic']['id']

        fake = mock.Mock(returncode=0, stdout='# 生成的文章\n\n内容', stderr='')
        with mock.patch('ai_writer.subprocess.run', return_value=fake):
            res = self._post('/api/generate', {'id': tid, 'length': '1000'})
            job_id = res['job']
            for _ in range(50):
                job = self._get('/api/generate/status?job=' + job_id)
                if job['status'] != 'running':
                    break
                time.sleep(0.1)

        self.assertEqual(job['status'], 'done')
        topics = self._get('/api/topics')['topics']
        topic = next(t for t in topics if t['id'] == tid)
        self.assertEqual(topic['status'], '待写作')
        self.assertEqual(topic['article'], res['article'])
        # 生成状态持久化到选题，页面刷新后仍可恢复
        for _ in range(50):
            topic = next(t for t in self._get('/api/topics')['topics']
                         if t['id'] == tid)
            if topic.get('gen') == 'done':
                break
            time.sleep(0.1)
        self.assertEqual(topic.get('gen'), 'done')
        with open(res['article'], encoding='utf-8') as f:
            self.assertIn('# 生成的文章', f.read())

    def test_generate_unknown_topic_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post('/api/generate', {'id': 'nope'})
        self.assertEqual(ctx.exception.code, 404)


class Phase2ApiTest(ApiTest):
    def test_persona_save_and_load(self):
        saved = self._post('/api/persona/save',
                           {'tone': '犀利', 'taboo': '赋能'})
        self.assertEqual(saved['persona']['tone'], '犀利')
        loaded = self._get('/api/persona')['persona']
        self.assertEqual(loaded['taboo'], '赋能')

    def test_templates_endpoint(self):
        data = self._get('/api/templates')
        self.assertIn('新闻解读', data['types'])
        self.assertIn('教程', data['guides'])

    def test_intel_adopt_creates_topic_and_dedups(self):
        item = {'id': 'api-it1', 'title': '情报采纳测试',
                'url': 'https://example.com/n', 'summary': '摘要',
                'score': 88, 'category': 'paper'}
        first = self._post('/api/intel/adopt', item)
        self.assertFalse(first['existed'])
        second = self._post('/api/intel/adopt', item)
        self.assertTrue(second['existed'])
        self.assertEqual(first['topicId'], second['topicId'])
        topics = self._get('/api/topics')['topics']
        adopted = [t for t in topics if t['id'] == first['topicId']]
        self.assertEqual(len(adopted), 1)
        self.assertEqual(adopted[0]['type'], '技术拆解')
        self.assertIn('核实', adopted[0]['notes'])

    def test_intel_adopt_without_id_is_400(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post('/api/intel/adopt', {'title': 'x'})
        self.assertEqual(ctx.exception.code, 400)

    def test_knowledge_crud_and_search(self):
        import urllib.parse
        added = self._post('/api/knowledge/add',
                           {'title': '知识条目A', 'content': '正文内容X',
                            'tags': '测试'})
        kid = added['id']
        q = urllib.parse.quote('内容X')
        items = self._get('/api/knowledge?q=' + q)['items']
        self.assertTrue(any(i['id'] == kid for i in items))
        self._post('/api/knowledge/delete', {'id': kid})
        items = self._get('/api/knowledge')['items']
        self.assertFalse(any(i['id'] == kid for i in items))

    def test_knowledge_add_rejects_empty(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post('/api/knowledge/add', {'title': '', 'content': ''})
        self.assertEqual(ctx.exception.code, 400)

    def test_knowledge_import_url_rejects_bad_scheme(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post('/api/knowledge/import-url',
                       {'url': 'file:///etc/passwd'})
        self.assertEqual(ctx.exception.code, 400)

    def test_publish_starts_job_and_updates_topic_on_success(self):
        import wechat_pub
        from unittest import mock as _m
        created = self._post('/api/topics/create',
                             {'title': '发布测试选题', 'type': '教程'})
        tid = created['topic']['id']
        with open('content/pub-test.md', 'w', encoding='utf-8') as f:
            f.write('# 发布测试\n\n正文')
        fake = _m.Mock(returncode=0, stdout='ok', stderr='')
        with _m.patch('wechat_pub.subprocess.run', return_value=fake), \
             _m.patch('wechat_pub._has_api_creds', return_value=True), \
             _m.patch('wechat_pub.os.path.isdir', return_value=True):
            data = self._post('/api/publish',
                              {'file': 'content/pub-test.md',
                               'topic_id': tid})
            self.assertTrue(data['success'])
            deadline = time.time() + 5
            while time.time() < deadline:
                job = self._get('/api/publish/status?job=' + data['job'])
                if job['status'] != 'running':
                    break
                time.sleep(0.02)
        self.assertEqual(job['status'], 'done')
        topics = self._get('/api/topics')['topics']
        topic = [t for t in topics if t['id'] == tid][0]
        self.assertEqual(topic['status'], '已发布')
        self._post('/api/topics/delete', {'id': tid})

    def test_publish_html_mode_writes_temp_and_passes_title(self):
        import wechat_pub
        from unittest import mock as _m
        fake = _m.Mock(returncode=0, stdout='ok', stderr='')
        with _m.patch('wechat_pub.subprocess.run', return_value=fake), \
             _m.patch('wechat_pub._has_api_creds', return_value=False), \
             _m.patch('wechat_pub.os.path.isdir', return_value=True):
            data = self._post('/api/publish',
                              {'file': 'content/x.md',
                               'title': '样式测试标题',
                               'html': '<p style="color:red">正文</p>'})
        self.assertTrue(data['success'])
        job = self._get('/api/publish/status?job=' + data['job'])
        self.assertTrue(job['file'].startswith('data/publish-'))
        with open(job['file'], encoding='utf-8') as f:
            self.assertIn('color:red', f.read())

    def test_publish_rejects_path_outside_content(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post('/api/publish', {'file': '../etc/passwd'})
        self.assertEqual(ctx.exception.code, 400)

    def test_publish_missing_file_returns_json_error(self):
        data = self._post('/api/publish', {'file': 'content/no-such.md'})
        self.assertFalse(data['success'])
        self.assertIn('不存在', data['error'])

    def test_growth_record_roundtrip(self):
        added = self._post('/api/growth/add',
                           {'article': 'content/g.md', 'platform': '公众号',
                            'read': 800, 'like': 30})
        rid = added['record']['id']
        data = self._get('/api/growth')
        self.assertTrue(any(r['id'] == rid for r in data['records']))
        self._post('/api/growth/delete', {'id': rid})
        data = self._get('/api/growth')
        self.assertFalse(any(r['id'] == rid for r in data['records']))

    def test_growth_analyze_without_data_returns_json_error(self):
        for r in self._get('/api/growth')['records']:
            self._post('/api/growth/delete', {'id': r['id']})
        data = self._post('/api/growth/analyze', {})
        self.assertFalse(data['success'])

    def test_dist_rejects_path_outside_content(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post('/api/dist', {'file': 'server.py',
                                     'platform': 'zhihu'})
        self.assertEqual(ctx.exception.code, 400)

    def test_dist_unknown_platform_returns_json_error(self):
        with open('content/d.md', 'w', encoding='utf-8') as f:
            f.write('# t\n\nx')
        data = self._post('/api/dist', {'file': 'content/d.md',
                                        'platform': 'weibo'})
        self.assertFalse(data['success'])

    def test_intel_rss_source_returns_local_items(self):
        import intel_rss
        os.makedirs('data', exist_ok=True)
        with open(intel_rss.ITEMS_PATH, 'w', encoding='utf-8') as f:
            json.dump({'rss-x1': {
                'id': 'rss-x1', 'title': '本地RSS条目',
                'url': 'https://example.com/r1', 'source': '测试源',
                'publishedAt': '2026-06-10T01:00:00Z', 'summary': 's',
                'category': 'industry', 'score': None,
                'fetched_at': time.time()}}, f)
        data = self._get('/api/intel?source=rss&hours=0')
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['items'][0]['title'], '本地RSS条目')
        self.assertIn('rss', data)

    def test_intel_refresh_endpoint_starts(self):
        from unittest import mock as _m
        import intel_rss
        with _m.patch('intel_rss.refresh_all'):
            data = self._post('/api/intel/refresh', {})
        self.assertIn('started', data)


if __name__ == '__main__':
    unittest.main()
