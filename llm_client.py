"""Unified LLM client for AI Content OS.

The project originally called `claude -p` directly from each module.  This
keeps that default path, while allowing OpenAI-compatible HTTP providers from
`data/llm.json` without adding third-party dependencies.
"""
import json
import os
import subprocess
import urllib.error
import urllib.request

import llm_config


def generate_text(task, prompt, timeout=600, fallback_task=None,
                  default_model=''):
    cfg = llm_config.task_config(task, fallback_task=fallback_task)
    if default_model and not cfg['model']:
        cfg = dict(cfg)
        cfg['model'] = default_model

    provider = cfg['provider']
    if provider in ('claude', 'claude-cli'):
        return _run_claude(prompt, cfg, timeout)
    if provider in ('openai', 'openai-compatible', 'codex'):
        return _run_openai(prompt, cfg, timeout)
    if provider == 'command':
        return _run_command(prompt, cfg, timeout)
    raise RuntimeError('不支持的 LLM provider: %s' % provider)


def _run_claude(prompt, cfg, timeout):
    cmd = ['claude', '-p', prompt]
    if cfg['model']:
        cmd += ['--model', cfg['model']]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            timeout=timeout, env=cfg['env'])
    text = llm_config.strip_preamble(result.stdout)
    if result.returncode != 0 or not text:
        raise RuntimeError(result.stderr.strip() or 'claude CLI 没有输出')
    return text


def _run_command(prompt, cfg, timeout):
    if not cfg['command'] or not isinstance(cfg['command'], list):
        raise RuntimeError('provider=command 需要配置 command 数组')
    cmd = [str(part).replace('{prompt}', prompt) for part in cfg['command']]
    if '{prompt}' not in ' '.join(cfg['command']):
        cmd.append(prompt)
    result = subprocess.run(cmd, capture_output=True, text=True,
                            timeout=timeout, env=cfg['env'])
    text = llm_config.strip_preamble(result.stdout)
    if result.returncode != 0 or not text:
        raise RuntimeError(result.stderr.strip() or 'LLM command 没有输出')
    return text


def _run_openai(prompt, cfg, timeout):
    env = cfg['env'] or os.environ
    api_key = cfg['api_key'] or env.get(cfg['api_key_env']) or ''
    if not api_key:
        raise RuntimeError('缺少 OpenAI API key：请设置 %s 或 data/llm.json'
                           % cfg['api_key_env'])
    if not cfg['model']:
        raise RuntimeError('provider=openai 需要配置 model')

    base_url = (cfg['base_url'] or 'https://api.openai.com/v1').rstrip('/')
    payload = {
        'model': cfg['model'],
        'messages': [{'role': 'user', 'content': prompt}],
    }
    if cfg['temperature'] is not None:
        payload['temperature'] = cfg['temperature']
    if cfg['max_tokens'] is not None:
        payload['max_tokens'] = cfg['max_tokens']

    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        base_url + '/chat/completions',
        data=body,
        headers={
            'Authorization': 'Bearer %s' % api_key,
            'Content-Type': 'application/json',
        },
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='ignore')[-500:]
        raise RuntimeError('OpenAI 请求失败: %s' % (detail or e)) from e
    except urllib.error.URLError as e:
        raise RuntimeError('OpenAI 网络请求失败: %s' % e) from e

    try:
        text = data['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        raise RuntimeError('OpenAI 返回格式不符合预期')
    text = llm_config.strip_preamble(text)
    if not text:
        raise RuntimeError('OpenAI 没有输出')
    return text
