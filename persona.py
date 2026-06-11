"""人设引擎 — 品牌人设配置，写作时注入 Prompt 保持调性一致。"""
import json
import os
import threading

PERSONA_PATH = 'data/persona.json'

DEFAULTS = {
    'name': '',        # 账号人设（如：一线 AI 实践者，爱用第一人称）
    'tone': '',        # 语气风格描述
    'vocabulary': '',  # 常用词汇/口头禅
    'hook': '',        # 固定开头习惯
    'cta': '',         # 固定结尾/行动号召
    'taboo': '',       # 禁忌词（绝对不可出现）
}

_lock = threading.Lock()


def load():
    with _lock:
        if not os.path.exists(PERSONA_PATH):
            return dict(DEFAULTS)
        with open(PERSONA_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    return merged


def save(data):
    merged = dict(DEFAULTS)
    merged.update({k: str(v).strip() for k, v in data.items()
                   if k in DEFAULTS})
    with _lock:
        os.makedirs(os.path.dirname(PERSONA_PATH), exist_ok=True)
        with open(PERSONA_PATH, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
    return merged


def is_empty(p):
    return not any(p.get(k) for k in DEFAULTS)
