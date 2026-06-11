"""按任务加载 LLM 模型/接口覆盖配置 — data/llm.json。

让"AI 写作"和"RSS 评分"各自指定模型、Provider 与接口配置。
默认仍使用 claude CLI；配置 provider=openai 后走 OpenAI 兼容接口。
llm.json 含密钥，已加入 .gitignore，禁止提交。

格式（任务键有 write / score / dist / growth，缺文件或缺任务项即回退默认登录态）：
{
  "write": {"provider": "openai",
            "model": "填写你要用的模型",
            "base_url": "https://api.openai.com/v1",
            "api_key_env": "OPENAI_API_KEY"},
  "score": {"provider": "claude", "model": "haiku", "env": {...}}
}
"""
import json
import os
import re

CONFIG_PATH = 'data/llm.json'

# claude CLI 会加载全局 CLAUDE.md（要求称呼"主人"等），-p 模式下模型常在
# 产物前加一句开场白，必须剥掉，否则混进文章/转换结果文件
_PREAMBLE = re.compile(r'^(主人|好的|当然|以下是|这是|没问题)[，,、]?'
                       r'[^\n]{0,40}[:：]$')


def strip_preamble(text):
    """去掉 LLM 输出开头的寒暄行（及紧随的 --- 分隔线/空行）。"""
    lines = (text or '').strip().split('\n')
    if lines and _PREAMBLE.match(lines[0].strip()) and '#' not in lines[0]:
        lines = lines[1:]
        while lines and lines[0].strip() in ('', '---'):
            lines = lines[1:]
    return '\n'.join(lines).strip()


def _load_config():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _task_entry(cfg, task, fallback_task=None):
    entry = cfg.get(task)
    if not entry and fallback_task:
        entry = cfg.get(fallback_task)
    return entry or {}


def task_config(task, fallback_task=None):
    """返回任务 LLM 配置。

    model 为空表示不传 --model（跟随 CLI 默认）；env 为 None 表示
    继承父进程环境，否则是 os.environ 与覆盖项合并后的完整环境。
    """
    cfg = _load_config()
    entry = _task_entry(cfg, task, fallback_task)
    provider = (entry.get('provider') or os.environ.get('LLM_PROVIDER')
                or 'claude').lower()
    model = entry.get('model') or ''
    overrides = entry.get('env') or {}
    env = None
    if overrides:
        env = dict(os.environ)
        env.update({k: str(v) for k, v in overrides.items()})
    return {
        'provider': provider,
        'model': model,
        'env': env,
        'base_url': entry.get('base_url') or os.environ.get(
            'OPENAI_BASE_URL', 'https://api.openai.com/v1'),
        'api_key': entry.get('api_key') or '',
        'api_key_env': entry.get('api_key_env') or 'OPENAI_API_KEY',
        'command': entry.get('command') or [],
        'temperature': entry.get('temperature'),
        'max_tokens': entry.get('max_tokens'),
    }
