"""按任务加载 LLM 模型/接口覆盖配置 — data/llm.json。

让"AI 写作"和"RSS 评分"各自指定模型与 Anthropic 兼容网关，
环境变量只注入对应的 claude 子进程，不影响服务器和交互会话。
llm.json 含密钥，已加入 .gitignore，禁止提交。

格式（任务键目前有 write / score，缺文件或缺任务项即回退默认登录态）：
{
  "write": {"model": "glm-5.1",
            "env": {"ANTHROPIC_AUTH_TOKEN": "...",
                    "ANTHROPIC_BASE_URL": "https://open.bigmodel.cn/api/anthropic"}},
  "score": {"model": "glm-5-turbo", "env": {...}}
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


def task_config(task):
    """返回 {'model': str, 'env': dict|None}。

    model 为空表示不传 --model（跟随 CLI 默认）；env 为 None 表示
    继承父进程环境，否则是 os.environ 与覆盖项合并后的完整环境。
    """
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f) or {}
    except (OSError, ValueError):
        cfg = {}
    entry = cfg.get(task) or {}
    model = entry.get('model') or ''
    overrides = entry.get('env') or {}
    env = None
    if overrides:
        env = dict(os.environ)
        env.update({k: str(v) for k, v in overrides.items()})
    return {'model': model, 'env': env}
