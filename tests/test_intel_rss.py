import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import intel_rss

RSS_SAMPLE = '''<?xml version="1.0"?>
<rss version="2.0"><channel><title>Demo</title>
<item>
  <title>新模型发布</title>
  <link>https://example.com/a</link>
  <pubDate>Tue, 10 Jun 2026 08:00:00 GMT</pubDate>
  <description>&lt;p&gt;模型 &lt;b&gt;X&lt;/b&gt; 上线了&lt;/p&gt;</description>
</item>
<item>
  <title>第二条</title>
  <link>https://example.com/b</link>
  <pubDate>Mon, 09 Jun 2026 12:00:00 GMT</pubDate>
</item>
</channel></rss>'''

ATOM_SAMPLE = '''<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Atom Demo</title>
<entry>
  <title>Atom 条目</title>
  <link href="https://example.com/atom1"/>
  <published>2026-06-10T06:30:00Z</published>
  <summary>摘要文字</summary>
</entry>
</feed>'''


def _fake_http(text):
    class FakeRes(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

    return FakeRes(text.encode('utf-8'))


class TmpDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp)


class ParseTest(unittest.TestCase):
    def test_parse_rss2(self):
        entries = intel_rss._parse_feed(RSS_SAMPLE)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]['title'], '新模型发布')
        self.assertEqual(entries[0]['link'], 'https://example.com/a')
        self.assertIn('模型', entries[0]['summary'])
        self.assertNotIn('<b>', entries[0]['summary'])  # HTML 已剥离

    def test_parse_atom(self):
        entries = intel_rss._parse_feed(ATOM_SAMPLE)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['link'], 'https://example.com/atom1')

    def test_date_to_iso(self):
        self.assertEqual(intel_rss._to_iso('Tue, 10 Jun 2026 08:00:00 GMT'),
                         '2026-06-10T08:00:00Z')
        self.assertEqual(intel_rss._to_iso('2026-06-10T06:30:00Z'),
                         '2026-06-10T06:30:00Z')
        self.assertEqual(intel_rss._to_iso('garbage'), '')


class ConfigTest(TmpDirTest):
    def test_config_created_with_defaults(self):
        cfg = intel_rss.load_config()
        self.assertTrue(os.path.exists('data/sources.json'))
        self.assertTrue(any(s['id'] == 'qbitai' for s in cfg['sources']))
        self.assertIn('auto_score', cfg['settings'])


class RefreshTest(TmpDirTest):
    def _config_one_source(self):
        os.makedirs('data', exist_ok=True)
        with open('data/sources.json', 'w', encoding='utf-8') as f:
            json.dump({'sources': [{'id': 's1', 'name': '测试源',
                                    'url': 'https://example.com/rss',
                                    'category': 'industry',
                                    'enabled': True}],
                       'settings': {'auto_score': False,
                                    'poll_minutes': 30}}, f)

    def test_refresh_stores_and_dedups(self):
        self._config_one_source()
        with mock.patch('net.urlopen',
                        return_value=_fake_http(RSS_SAMPLE)):
            result = intel_rss.refresh_all()
        self.assertEqual(result['new'], 2)
        items = intel_rss.get_items()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['source'], '测试源')  # 按时间倒序，第一条最新
        self.assertEqual(items[0]['category'], 'industry')
        self.assertTrue(items[0]['id'].startswith('rss-'))

        # 再抓一次：同样条目不重复入库
        with mock.patch('net.urlopen',
                        return_value=_fake_http(RSS_SAMPLE)):
            result2 = intel_rss.refresh_all()
        self.assertEqual(result2['new'], 0)
        self.assertEqual(len(intel_rss.get_items()), 2)

    def test_refresh_records_source_error(self):
        self._config_one_source()
        with mock.patch('net.urlopen',
                        side_effect=OSError('boom')):
            result = intel_rss.refresh_all()
        self.assertEqual(result['new'], 0)
        self.assertIn('s1', result['errors'])
        # 失败信息要能被前端看到：status() 暴露最近一轮的源错误
        self.assertIn('s1', intel_rss.status()['last_errors'])

        # 下一轮成功后错误清空，不残留旧告警
        with mock.patch('net.urlopen',
                        return_value=_fake_http(RSS_SAMPLE)):
            intel_rss.refresh_all()
        self.assertEqual(intel_rss.status()['last_errors'], {})

    def test_get_items_filters(self):
        self._config_one_source()
        with mock.patch('net.urlopen',
                        return_value=_fake_http(RSS_SAMPLE)):
            intel_rss.refresh_all()
        hit = intel_rss.get_items(q='第二')
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0]['title'], '第二条')
        none = intel_rss.get_items(category='paper')
        self.assertEqual(none, [])


class ScoreTest(TmpDirTest):
    def test_score_pending_assigns_scores(self):
        self._seed_items()
        fake = mock.Mock(returncode=0, stdout='[88, 62]', stderr='')
        with mock.patch('llm_client.subprocess.run', return_value=fake):
            n = intel_rss.score_pending(model='haiku')
        self.assertEqual(n, 2)
        items = intel_rss.get_items()
        scores = sorted([it['score'] for it in items])
        self.assertEqual(scores, [62, 88])

    def test_score_pending_tolerates_bad_output(self):
        self._seed_items()
        fake = mock.Mock(returncode=0, stdout='抱歉我没法打分', stderr='')
        with mock.patch('llm_client.subprocess.run', return_value=fake):
            n = intel_rss.score_pending()
        self.assertEqual(n, 0)
        self.assertTrue(all(it['score'] is None
                            for it in intel_rss.get_items()))

    def _seed_items(self):
        os.makedirs('data', exist_ok=True)
        with open('data/sources.json', 'w', encoding='utf-8') as f:
            json.dump({'sources': [{'id': 's1', 'name': '测试源',
                                    'url': 'https://example.com/rss',
                                    'category': 'industry',
                                    'enabled': True}],
                       'settings': {'auto_score': False}}, f)
        with mock.patch('net.urlopen',
                        return_value=_fake_http(RSS_SAMPLE)):
            intel_rss.refresh_all()


if __name__ == '__main__':
    unittest.main()
