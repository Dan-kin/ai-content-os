"""
AI Content OS - MVP 服务器
提供选题池管理、AI 写作、Markdown 编辑、实时预览、样式管理等功能。

用法:
    python3 server.py            # 默认端口 8080
    python3 server.py 3000      # 指定端口
"""

import http.server
import socketserver
import json
import os
import socket
import sys
import time
import urllib.parse

import threading

import ai_writer
import dist
import growth
import image_planner
import intel
import intel_rss
import knowledge
import persona
import rewriter
import store
import wechat_pub

DEFAULT_PORT = 8080


def find_free_port(start_port, host="127.0.0.1", max_tries=200):
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free port in range {start_port}..{start_port + max_tries - 1}")


class Handler(http.server.SimpleHTTPRequestHandler):
    """处理静态文件和 API 请求"""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if parsed.path == '/':
            self.send_response(302)
            self.send_header('Location', '/index.html')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            return

        elif parsed.path == '/api/content':
            try:
                query_path = (qs.get('path') or [None])[0]
                if query_path:
                    if not query_path.startswith('content/'):
                        self.send_error(400, "Path must be within content/ directory")
                        return
                    cpath = query_path
                else:
                    self.send_error(400, "Missing path parameter")
                    return

                with open(cpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                self._json_response({'content': content, 'path': cpath})
            except FileNotFoundError:
                # 错误消息必须 ASCII：http.server 用 latin-1 编码状态行
                self.send_error(404, "File not found")
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/files':
            try:
                content_dir = 'content'
                if not os.path.exists(content_dir):
                    os.makedirs(content_dir)
                files = []
                for filename in os.listdir(content_dir):
                    if filename.endswith('.md') or filename.endswith('.txt'):
                        filepath = os.path.join(content_dir, filename)
                        files.append({'name': filename, 'path': filepath})
                files.sort(key=lambda x: x['name'])
                self._json_response({'files': files})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/topics':
            try:
                self._json_response({'topics': store.list_topics()})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/intel':
            try:
                source = (qs.get('source') or ['aihot'])[0]
                hours = float((qs.get('hours') or ['24'])[0])
                category = (qs.get('category') or [''])[0]
                q = (qs.get('q') or [''])[0]
                if source == 'rss':
                    items = intel_rss.get_items(hours=hours,
                                                category=category, q=q)
                    self._json_response({'items': items, 'cached': True,
                                         'adopted': intel.adopted_map(),
                                         'rss': intel_rss.status()})
                else:
                    items, cached = intel.fetch_items(
                        hours=hours, category=category, q=q,
                        take=int((qs.get('take') or ['50'])[0]))
                    self._json_response({'items': items, 'cached': cached,
                                         'adopted': intel.adopted_map()})
            except Exception as e:
                # 信源不可达/超时等：明确告知前端，前端展示重试入口
                self.send_error(502, 'Intel source unavailable: %s'
                                % e.__class__.__name__)

        elif parsed.path == '/api/knowledge':
            try:
                q = (qs.get('q') or [''])[0]
                self._json_response({'items': knowledge.search(q)})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/persona':
            try:
                self._json_response({'persona': persona.load()})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/templates':
            try:
                guides = ai_writer.type_guides()
                self._json_response({'types': list(guides.keys()),
                                     'guides': guides})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/growth':
            try:
                self._json_response({'records': growth.list_records(),
                                     'analysis': growth.last_analysis()})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/growth/analyze/status':
            job_id = (qs.get('job') or [None])[0]
            job = growth.get_job(job_id) if job_id else None
            if job is None:
                self.send_error(404, "Job not found")
                return
            if job['status'] == 'done':
                job['analysis'] = growth.last_analysis()
            self._json_response(job)

        elif parsed.path == '/api/dist/status':
            job_id = (qs.get('job') or [None])[0]
            job = dist.get_job(job_id) if job_id else None
            if job is None:
                self.send_error(404, "Job not found")
                return
            self._json_response(job)

        elif parsed.path == '/api/rewrite/status':
            job_id = (qs.get('job') or [None])[0]
            job = rewriter.get_job(job_id) if job_id else None
            if job is None:
                self.send_error(404, "Job not found")
                return
            self._json_response(job)

        elif parsed.path == '/api/images/status':
            job_id = (qs.get('job') or [None])[0]
            job = image_planner.get_job(job_id) if job_id else None
            if job is None:
                self.send_error(404, "Job not found")
                return
            self._json_response(job)

        elif parsed.path == '/api/publish/status':
            job_id = (qs.get('job') or [None])[0]
            job = wechat_pub.get_job(job_id) if job_id else None
            if job is None:
                self.send_error(404, "Job not found")
                return
            self._json_response(job)

        elif parsed.path == '/api/generate/status':
            job_id = (qs.get('job') or [None])[0]
            job = ai_writer.get_job(job_id) if job_id else None
            if job is None:
                self.send_error(404, "Job not found")
                return
            self._json_response(job)

        elif parsed.path == '/api/styles':
            try:
                styles_path = 'data/styles.json'
                if not os.path.exists(styles_path):
                    self._json_response({'styles': {}})
                    return
                with open(styles_path, 'r', encoding='utf-8') as f:
                    styles = json.load(f)
                self._json_response({'styles': styles})
            except Exception as e:
                self.send_error(500, str(e))

        else:
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == '/api/save':
            try:
                data = self._read_json()
                content = data.get('content', '')
                path = data.get('path', '')

                if not path:
                    self.send_error(400, "Path is required")
                    return
                if not path.startswith('content/'):
                    self.send_error(400, "Path must be within content/ directory")
                    return

                dir_path = os.path.dirname(path)
                if dir_path and not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)

                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)

                self._json_response({'success': True, 'path': path})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/create':
            try:
                data = self._read_json()
                filename = data.get('filename', '').strip()

                if not filename:
                    self.send_error(400, "Filename is required")
                    return

                if not (filename.endswith('.md') or filename.endswith('.txt')):
                    filename += '.md'

                if '/' in filename or '\\' in filename:
                    self.send_error(400, "Filename cannot contain path separators")
                    return

                path = os.path.join('content', filename)

                if os.path.exists(path):
                    self.send_error(400, "File already exists")
                    return

                if not os.path.exists('content'):
                    os.makedirs('content')

                with open(path, 'w', encoding='utf-8') as f:
                    f.write('')

                self._json_response({'success': True, 'path': path, 'filename': filename})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/topics/create':
            try:
                data = self._read_json()
                topic = store.create_topic(
                    data.get('title', ''),
                    type=data.get('type', '新闻解读'),
                    source=data.get('source', ''),
                    notes=data.get('notes', ''))
                self._json_response({'success': True, 'topic': topic})
            except ValueError as e:
                self.send_error(400, str(e))
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/topics/update':
            try:
                data = self._read_json()
                topic_id = data.pop('id', '')
                topic = store.update_topic(topic_id, **data)
                self._json_response({'success': True, 'topic': topic})
            except KeyError:
                self.send_error(404, "Topic not found")
            except ValueError as e:
                self.send_error(400, str(e))
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/topics/delete':
            try:
                data = self._read_json()
                store.delete_topic(data.get('id', ''))
                self._json_response({'success': True})
            except KeyError:
                self.send_error(404, "Topic not found")
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/intel/refresh':
            try:
                if intel_rss.status()['running']:
                    self._json_response({'started': False,
                                         'reason': 'already running'})
                    return
                threading.Thread(target=intel_rss.refresh_all,
                                 daemon=True).start()
                self._json_response({'started': True})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/intel/adopt':
            try:
                data = self._read_json()
                topic_id, existed = intel.adopt(data)
                self._json_response({'success': True, 'topicId': topic_id,
                                     'existed': existed})
            except ValueError as e:
                self.send_error(400, str(e))
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/knowledge/add':
            try:
                data = self._read_json()
                kid = knowledge.add(data.get('title', ''),
                                    data.get('content', ''),
                                    source_url=data.get('source_url', ''),
                                    tags=data.get('tags', ''))
                self._json_response({'success': True, 'id': kid})
            except ValueError as e:
                self.send_error(400, str(e))
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/knowledge/delete':
            try:
                data = self._read_json()
                knowledge.delete(int(data.get('id', 0)))
                self._json_response({'success': True})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/knowledge/import-url':
            try:
                data = self._read_json()
                url = (data.get('url') or '').strip()
                if not url.startswith(('http://', 'https://')):
                    self.send_error(400, 'invalid url')
                    return
                kid = knowledge.import_url(url)
                self._json_response({'success': True, 'id': kid,
                                     'item': knowledge.get(kid)})
            except ValueError as e:
                self.send_error(400, str(e))
            except Exception as e:
                self.send_error(502, 'fetch failed: %s' % e)

        elif parsed.path == '/api/growth/add':
            try:
                data = self._read_json()
                rec = growth.add_record(
                    data.get('article', ''), data.get('platform', ''),
                    read=data.get('read', 0), like=data.get('like', 0),
                    share=data.get('share', 0),
                    comment=data.get('comment', 0))
                self._json_response({'success': True, 'record': rec})
            except ValueError as e:
                self.send_error(400, str(e))
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/growth/delete':
            try:
                data = self._read_json()
                growth.delete_record(data.get('id', ''))
                self._json_response({'success': True})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/growth/analyze':
            try:
                try:
                    job_id = growth.start_analyze()
                except RuntimeError as e:
                    self._json_response({'success': False, 'error': str(e)})
                    return
                self._json_response({'success': True, 'job': job_id})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/dist':
            try:
                data = self._read_json()
                path = (data.get('file') or '').strip()
                platform = (data.get('platform') or '').strip()
                if not path.startswith('content/') or '..' in path:
                    self.send_error(400, 'file must be within content/')
                    return
                try:
                    job_id = dist.start_convert(path, platform)
                except (RuntimeError, ValueError) as e:
                    self._json_response({'success': False, 'error': str(e)})
                    return
                self._json_response({'success': True, 'job': job_id,
                                     'output': dist.get_job(job_id)['output']})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/rewrite':
            try:
                data = self._read_json()
                path = (data.get('file') or '').strip()
                if not path.startswith('content/') or '..' in path:
                    self.send_error(400, 'file must be within content/')
                    return
                modes = data.get('modes') or []
                if not isinstance(modes, list):
                    modes = []
                instructions = data.get('instructions') or ''
                try:
                    job_id = rewriter.start_rewrite(
                        path, modes=modes, instructions=instructions)
                except RuntimeError as e:
                    self._json_response({'success': False, 'error': str(e)})
                    return
                self._json_response({'success': True, 'job': job_id,
                                     'output': rewriter.get_job(job_id)['output']})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/images/plan':
            try:
                data = self._read_json()
                path = (data.get('file') or '').strip()
                if not path.startswith('content/') or '..' in path:
                    self.send_error(400, 'file must be within content/')
                    return
                count = (data.get('count') or 'standard').strip()
                if count not in ('light', 'standard', 'rich'):
                    count = 'standard'
                instructions = data.get('instructions') or ''
                insert_placeholders = data.get('insert_placeholders', True)
                insert_placeholders = bool(insert_placeholders)
                try:
                    job_id = image_planner.start_plan(
                        path, count=count, instructions=instructions,
                        insert_placeholders=insert_placeholders)
                except RuntimeError as e:
                    self._json_response({'success': False, 'error': str(e)})
                    return
                job = image_planner.get_job(job_id)
                self._json_response({'success': True, 'job': job_id,
                                     'output': job['output'],
                                     'prompts': job['prompts']})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/publish':
            try:
                data = self._read_json()
                path = (data.get('file') or '').strip()
                if not path.startswith('content/') or '..' in path:
                    self.send_error(400, 'file must be within content/')
                    return
                topic_id = data.get('topic_id', '')
                html_content = data.get('html') or ''
                title = (data.get('title') or '').strip()[:64]

                def _pub_finish(status, error):
                    # 发布成功才推进选题状态；topic_id 为空表示编辑器直发
                    if status == 'done' and topic_id:
                        try:
                            store.update_topic(topic_id, status='已发布')
                        except Exception:
                            pass

                try:
                    if html_content:
                        # 编辑器渲染好的带样式 HTML（所见即所得发布），
                        # 落临时文件交给技能脚本的 --html 模式
                        os.makedirs('data', exist_ok=True)
                        tmp_path = 'data/publish-%d.html' % int(
                            time.time() * 1000)
                        with open(tmp_path, 'w', encoding='utf-8') as f:
                            f.write(html_content)
                        job_id = wechat_pub.start_publish(
                            tmp_path, on_finish=_pub_finish,
                            html=True, title=title)
                    else:
                        job_id = wechat_pub.start_publish(
                            path, on_finish=_pub_finish, title=title)
                except RuntimeError as e:
                    # 配置类错误（技能未装/文件缺失）：中文消息走 JSON 体，
                    # 不能进 send_error 状态行（http.server 仅限 ASCII）
                    self._json_response({'success': False, 'error': str(e)})
                    return
                job = wechat_pub.get_job(job_id)
                self._json_response({'success': True, 'job': job_id,
                                     'mode': job['mode']})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/persona/save':
            try:
                data = self._read_json()
                saved = persona.save(data)
                self._json_response({'success': True, 'persona': saved})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/generate':
            try:
                data = self._read_json()
                matches = [t for t in store.list_topics()
                           if t['id'] == data.get('id')]
                if not matches:
                    self.send_error(404, "Topic not found")
                    return
                topic = matches[0]
                topic_id = topic['id']

                def _finish(status, error):
                    store.update_topic(topic_id, gen=status, gen_error=error)

                # 先标记 running 再启动任务，避免任务瞬间失败后被覆盖
                store.update_topic(topic_id, status='待写作',
                                   gen='running', gen_error='')
                job_id, out_path = ai_writer.start_job(topic, data,
                                                       on_finish=_finish)
                store.update_topic(topic_id, article=out_path)
                self._json_response({'success': True, 'job': job_id,
                                     'article': out_path})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/styles/save':
            try:
                data = self._read_json()
                style_id = data.get('id', '').strip()
                style_name = data.get('name', '').strip()
                style_data = data.get('styles', {})

                if not style_id:
                    self.send_error(400, "Style ID is required")
                    return

                if not os.path.exists('data'):
                    os.makedirs('data')

                styles_path = 'data/styles.json'
                styles = {}
                if os.path.exists(styles_path):
                    with open(styles_path, 'r', encoding='utf-8') as f:
                        styles = json.load(f)

                styles[style_id] = {
                    'name': style_name,
                    'styles': style_data
                }

                with open(styles_path, 'w', encoding='utf-8') as f:
                    json.dump(styles, f, ensure_ascii=False, indent=2)

                self._json_response({'success': True, 'id': style_id})
            except Exception as e:
                self.send_error(500, str(e))

        elif parsed.path == '/api/styles/delete':
            try:
                data = self._read_json()
                style_id = data.get('id', '').strip()

                if not style_id:
                    self.send_error(400, "Style ID is required")
                    return

                styles_path = 'data/styles.json'
                if not os.path.exists(styles_path):
                    self.send_error(404, "Styles file not found")
                    return

                with open(styles_path, 'r', encoding='utf-8') as f:
                    styles = json.load(f)

                if style_id not in styles:
                    self.send_error(404, "Style not found")
                    return

                del styles[style_id]

                with open(styles_path, 'w', encoding='utf-8') as f:
                    json.dump(styles, f, ensure_ascii=False, indent=2)

                self._json_response({'success': True})
            except Exception as e:
                self.send_error(500, str(e))

        else:
            self.send_error(404, "Not Found")

    # ---- helpers ----

    def _read_json(self):
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len).decode('utf-8')
        return json.loads(body)

    def _json_response(self, obj):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode('utf-8'))


class ReuseTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}")
            sys.exit(1)

    # If default port is occupied, find next free
    if port == DEFAULT_PORT:
        port = find_free_port(port)
    else:
        port = find_free_port(port, max_tries=1)

    base_url = f"http://127.0.0.1:{port}"

    # 上次进程退出时未完成的生成任务已无人收尾，重置为失败避免永远卡在"生成中"
    for t in store.list_topics():
        if t.get('gen') == 'running':
            store.update_topic(t['id'], gen='error',
                               gen_error='服务器重启，生成任务中断，请重新生成')

    # RSS 信源后台轮询：启动即抓一轮，之后按 poll_minutes 周期刷新
    def _rss_poll_loop():
        while True:
            try:
                intel_rss.refresh_all()
            except Exception:
                pass
            minutes = intel_rss.load_config()['settings'].get(
                'poll_minutes', 30)
            time.sleep(max(5, float(minutes)) * 60)

    threading.Thread(target=_rss_poll_loop, daemon=True).start()

    print(f"🗂 AI Content OS (MVP)")
    print(f"✅ 服务器运行中: {base_url}")
    print(f"➡️  选题池: {base_url}/topics.html")
    print(f"➡️  编辑器: {base_url}/index.html")
    print(f"📂 工作目录: {os.getcwd()}")
    print(f"🛑 按 Ctrl+C 停止服务器\n")

    with ReuseTCPServer(("0.0.0.0", port), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 服务器已停止。")
