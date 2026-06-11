"""一键发布公众号 — 直接调用 baoyu-post-to-wechat 技能脚本。

不经 claude -p（旧副本验证过：直接调脚本更快更稳）。两条路径自动选择：
- api：~/.baoyu-skills/.env 或环境变量里有 WECHAT_APP_ID/SECRET 时，
  走官方 API 创建草稿（wechat-api.ts）
- browser：否则走 Chrome CDP 粘贴并存草稿（wechat-article.ts --submit），
  需要本机 Chrome 已登录公众号后台

两条路径产物都是公众号「草稿」，最终群发仍在公众号后台人工确认。
"""
import os
import subprocess
import threading
import time

SKILL_DIR = os.path.expanduser('~/.claude/skills/baoyu-post-to-wechat')
ENV_FILE = os.path.expanduser('~/.baoyu-skills/.env')
PUBLISH_TIMEOUT = 600

_jobs = {}
_jobs_lock = threading.Lock()


def _has_api_creds():
    if os.environ.get('WECHAT_APP_ID') and os.environ.get('WECHAT_APP_SECRET'):
        return True
    try:
        with open(ENV_FILE, 'r', encoding='utf-8') as f:
            text = f.read()
    except OSError:
        return False
    return 'WECHAT_APP_ID' in text and 'WECHAT_APP_SECRET' in text


def build_command(path, html=False, title=''):
    """返回 (命令, 模式)。模式为 'api' 或 'browser'。

    html=True 时 path 是编辑器渲染好的带行内样式 HTML（所见即所得，
    保留用户自选风格）；否则是 Markdown，由技能用自带主题渲染。
    """
    if not os.path.isdir(SKILL_DIR):
        raise RuntimeError(
            '未找到 baoyu-post-to-wechat 技能（%s），请先安装该技能'
            % SKILL_DIR)
    if not os.path.isfile(path):
        raise RuntimeError('文章文件不存在: %s' % path)
    if _has_api_creds():
        script = os.path.join(SKILL_DIR, 'scripts', 'wechat-api.ts')
        cmd = ['npx', '-y', 'bun', script, path]
        if title:
            cmd += ['--title', title]
        return cmd, 'api'
    script = os.path.join(SKILL_DIR, 'scripts', 'wechat-article.ts')
    cmd = ['npx', '-y', 'bun', script]
    cmd += ['--html', path] if html else ['--markdown', path]
    if title:
        cmd += ['--title', title]
    cmd += ['--submit']
    return cmd, 'browser'


def start_publish(path, on_finish=None, html=False, title=''):
    """后台发布，立即返回 job_id。on_finish(status, error) 结束时回调。"""
    # 配置类错误在启动前同步抛出
    cmd, mode = build_command(path, html=html, title=title)
    job_id = 'pub%d' % int(time.time() * 1000)
    with _jobs_lock:
        _jobs[job_id] = {'status': 'running', 'file': path,
                         'mode': mode, 'error': ''}
    threading.Thread(target=_run, args=(job_id, cmd, on_finish),
                     daemon=True).start()
    return job_id


def _run(job_id, cmd, on_finish=None):
    status, error = 'done', ''
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=PUBLISH_TIMEOUT)
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or '').strip()[-500:]
            raise RuntimeError(tail or '发布脚本退出码 %d' % result.returncode)
        with _jobs_lock:
            _jobs[job_id]['status'] = 'done'
    except Exception as e:
        status, error = 'error', str(e)
        with _jobs_lock:
            _jobs[job_id]['status'] = 'error'
            _jobs[job_id]['error'] = error
    if on_finish:
        try:
            on_finish(status, error)
        except Exception:
            pass


def get_job(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None
