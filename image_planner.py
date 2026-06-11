"""AI image planning for article illustrations and prompt packs."""
import json
import os
import re
import threading
import time

import llm_client

PLAN_TIMEOUT = 1200

COUNT_GUIDES = {
    'light': '2-3 张',
    'standard': '3-5 张',
    'rich': '5-7 张',
}

REQUIRED_FIELDS = (
    'id', 'type', 'insert_after_heading', 'purpose', 'context',
    'visual_concept', 'composition', 'cn_prompt', 'en_prompt',
    'negative_prompt', 'aspect_ratio',
)

_jobs = {}
_jobs_lock = threading.Lock()


def build_prompt(md_text, count='standard', instructions='',
                 insert_placeholders=True):
    count_text = COUNT_GUIDES.get(count, COUNT_GUIDES['standard'])
    placeholder_text = '需要生成可插入 Markdown 的图片占位建议' if insert_placeholders else '只需要生成 prompt 包，不插入占位'
    parts = [
        '你是一位中文公众号图片编辑和 AI 出图提示词专家。',
        '请根据文章内容规划配图，而不是泛泛地建议“加图片”。',
        '',
        '## 目标',
        '- 判断文章中最适合插图的位置',
        '- 说明每张图承担的表达任务',
        '- 产出可复制到 ChatGPT、Codex 或图片模型的中文和英文 prompt',
        '- 避免编造事实、品牌 logo、真实人物肖像和无法验证的数据图',
        '',
        '## 数量与插入',
        '- 推荐图片数量：%s' % count_text,
        '- %s' % placeholder_text,
        '',
        '## 输出格式',
        '只输出 JSON，不要 Markdown 解释，不要寒暄。JSON schema:',
        '{',
        '  "images": [',
        '    {',
        '      "id": "cover 或 image-1",',
        '      "type": "cover | section | concept | checklist",',
        '      "insert_after_heading": "建议插入在哪个 Markdown 标题后，封面可为空字符串",',
        '      "purpose": "这张图承担的表达任务",',
        '      "context": "来自原文的语境依据",',
        '      "visual_concept": "画面概念",',
        '      "composition": "主体、背景、镜头、光线、色彩",',
        '      "cn_prompt": "中文出图提示词",',
        '      "en_prompt": "English image generation prompt",',
        '      "negative_prompt": "不要项",',
        '      "aspect_ratio": "16:9 | 4:3 | 3:2 | 1:1",',
        '      "caption": "可选图注"',
        '    }',
        '  ]',
        '}',
        '',
        '## 风格要求',
        '- 公众号文章优先真实、清晰、有信息作用的画面',
        '- 如果文章偏观点文，优先用职场、桌面、人物背影、便签、流程、对比等可理解隐喻',
        '- 默认不要图片内文字，除非用户明确要求',
    ]
    if instructions.strip():
        parts += ['', '## 用户补充方向/禁忌', instructions.strip()]
    parts += ['', '## 原文', md_text]
    return '\n'.join(parts)


def parse_plan(text):
    raw = _strip_code_fence((text or '').strip())
    try:
        data = json.loads(raw)
    except Exception as e:
        raise RuntimeError('配图规划解析失败：LLM 没有返回合法 JSON') from e
    images = data.get('images')
    if not isinstance(images, list) or not images:
        raise RuntimeError('配图规划解析失败：JSON 中缺少 images 列表')
    for idx, image in enumerate(images):
        if not isinstance(image, dict):
            raise RuntimeError('配图规划解析失败：第 %d 个图片建议不是对象' % (idx + 1))
        missing = [field for field in REQUIRED_FIELDS
                   if field not in image or image.get(field) is None]
        if missing:
            raise RuntimeError('配图规划解析失败：第 %d 个图片建议缺少 %s'
                               % (idx + 1, ', '.join(missing)))
        image['id'] = _safe_id(str(image.get('id') or 'image-%d' % (idx + 1)))
        image['caption'] = str(image.get('caption') or '')
    return {'images': images}


def output_paths(md_path):
    base, ext = os.path.splitext(md_path)
    ext = ext or '.md'
    article = base + '-images' + ext
    prompts = base + '-image-prompts' + ext
    n = 1
    while os.path.exists(article) or os.path.exists(prompts):
        n += 1
        article = '%s-images-%d%s' % (base, n, ext)
        prompts = '%s-image-prompts-%d%s' % (base, n, ext)
    return article, prompts


def render_prompt_pack(source_path, plan):
    lines = [
        '# AI 配图 Prompt 包',
        '',
        '原文：`%s`' % source_path,
        '',
        '使用方式：复制对应图片的中文或英文 Prompt 到 ChatGPT、Codex 或出图工具。生成图片后，把文章里的 `assets/images/...png` 占位替换成真实图片路径。',
        '',
    ]
    for image in plan['images']:
        lines += [
            '## %s' % image['id'],
            '',
            '- 类型：%s' % image['type'],
            '- 推荐比例：%s' % image['aspect_ratio'],
            '- 插入位置：%s' % (image.get('insert_after_heading') or '封面/文章开头'),
            '- 用途：%s' % image['purpose'],
            '- 语境依据：%s' % image['context'],
            '- 画面概念：%s' % image['visual_concept'],
            '- 构图建议：%s' % image['composition'],
            '- 图注：%s' % (image.get('caption') or '无'),
            '',
            '### 中文 Prompt',
            '',
            image['cn_prompt'],
            '',
            '### English Prompt',
            '',
            image['en_prompt'],
            '',
            '### Negative Prompt',
            '',
            image['negative_prompt'],
            '',
        ]
    return '\n'.join(lines).rstrip() + '\n'


def insert_placeholders(md_text, plan, prompt_pack_path, source_path=None):
    if source_path:
        base_name = os.path.splitext(os.path.basename(source_path))[0]
    else:
        base_name = os.path.splitext(os.path.basename(prompt_pack_path))[0]
        base_name = re.sub(r'-image-prompts(?:-\d+)?$', '', base_name)
    base_name = base_name or 'article'
    result = md_text
    unmatched = []
    for image in plan['images']:
        placeholder = _placeholder(base_name, image, prompt_pack_path)
        heading = (image.get('insert_after_heading') or '').strip()
        if heading and heading in result:
            result = result.replace(heading, heading + '\n\n' + placeholder, 1)
        elif image.get('type') == 'cover' and not heading:
            result = placeholder + '\n\n' + result
        else:
            unmatched.append(placeholder)
    if unmatched:
        result = result.rstrip() + '\n\n## 配图建议\n\n' + '\n\n'.join(unmatched) + '\n'
    return result


def start_plan(md_path, count='standard', instructions='',
               insert_placeholders=True):
    if not md_path.startswith('content/') or '..' in md_path:
        raise RuntimeError('文章文件必须在 content/ 目录内')
    if not os.path.isfile(md_path):
        raise RuntimeError('文章文件不存在: %s' % md_path)
    with open(md_path, 'r', encoding='utf-8') as f:
        md_text = f.read()
    if len(md_text.strip()) < 20:
        raise RuntimeError('文章内容不足，无法规划配图')
    article_path, prompt_path = output_paths(md_path)
    prompt = build_prompt(md_text, count=count, instructions=instructions,
                          insert_placeholders=insert_placeholders)
    job_id = 'img%d' % int(time.time() * 1000)
    with _jobs_lock:
        _jobs[job_id] = {'status': 'running', 'source': md_path,
                         'output': article_path, 'prompts': prompt_path,
                         'error': ''}
    threading.Thread(target=_run,
                     args=(job_id, md_path, md_text, prompt, article_path,
                           prompt_path, insert_placeholders),
                     daemon=True).start()
    return job_id


def _run(job_id, md_path, md_text, prompt, article_path, prompt_path,
         should_insert_placeholders):
    try:
        text = llm_client.generate_text(
            'image', prompt, timeout=PLAN_TIMEOUT, fallback_task='write')
        plan = parse_plan(text)
        prompt_pack = render_prompt_pack(md_path, plan)
        if should_insert_placeholders:
            article = insert_placeholders(md_text, plan, prompt_path, md_path)
        else:
            article = md_text.rstrip() + '\n\n## 配图建议\n\n详见 `%s`。\n' % prompt_path
        with open(article_path, 'w', encoding='utf-8') as f:
            f.write(article.rstrip() + '\n')
        with open(prompt_path, 'w', encoding='utf-8') as f:
            f.write(prompt_pack)
        with _jobs_lock:
            _jobs[job_id]['status'] = 'done'
    except Exception as e:
        with _jobs_lock:
            _jobs[job_id]['status'] = 'error'
            _jobs[job_id]['error'] = str(e)


def get_job(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def _strip_code_fence(text):
    m = re.match(r'^```(?:json)?\s*(.*?)\s*```$', text, re.S)
    return m.group(1).strip() if m else text


def _safe_id(value):
    value = re.sub(r'[^a-zA-Z0-9_-]+', '-', value.strip()).strip('-')
    return value or 'image'


def _placeholder(base_name, image, prompt_pack_path):
    image_id = image['id']
    alt = '配图建议：%s' % (image.get('visual_concept') or image_id)
    image_path = 'assets/images/%s-%s.png' % (_safe_id(base_name), image_id)
    lines = [
        '![%s](%s)' % (alt, image_path),
        '<!-- image-prompt: 见 %s#%s -->' % (prompt_pack_path, image_id),
    ]
    if image.get('caption'):
        lines.append('> %s' % image['caption'])
    return '\n'.join(lines)
