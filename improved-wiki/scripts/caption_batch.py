#!/usr/bin/env python3
"""
caption_batch.py — Stage 0.6 批量版
每请求传 8 张图，1 次产出 8 个 caption
支持断点续传、--batch-size 调大小、--start 调起点

参数：
  --project <path>       Wiki 项目根目录（必传）
  --source-slug <name>   源 slug（如 "电源篇"，必传）
  --batch-size <N>       每批 N 张图（默认 8）
  --start <N>            从第 N 批开始（断点续传）
  --model <name>         LLM 模型（默认 MiniMax-M3）
  --api-key-file <path>  API key 文件（默认 /tmp/_api_key.txt）
"""
import os
import json
import base64
import urllib.request
import urllib.error
import time
import sys
import argparse

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--project", default=os.environ.get("IMPROVED_WIKI_PROJECT"),
                   help="Wiki 项目根目录（必传）")
    p.add_argument("--source-slug", default=os.environ.get("IMPROVED_WIKI_SOURCE"),
                   help="源 slug（必传）")
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--model", default="MiniMax-M3")
    p.add_argument("--api-key-file", default="/tmp/_api_key.txt")
    args = p.parse_args()
    if not args.project:
        p.error("--project is required (or set IMPROVED_WIKI_PROJECT env)")
    if not args.source_slug:
        p.error("--source-slug is required (or set IMPROVED_WIKI_SOURCE env)")
    return args

ARGS = parse_args()
ROOT = ARGS.project
SOURCE_SLUG = ARGS.source_slug
MEDIA = f"{ROOT}/wiki/media/{SOURCE_SLUG}"
if not os.path.isdir(MEDIA):
    # Fallback: search for matching subdirectory (HardwareWiki-style naming)
    media_root = f"{ROOT}/wiki/media"
    if os.path.isdir(media_root):
        for d in os.listdir(media_root):
            if SOURCE_SLUG in d or d.replace(" ", "") in SOURCE_SLUG.replace(" ", ""):
                MEDIA = os.path.join(media_root, d)
                break
MANIFEST = f"{MEDIA}/_manifest.json"
BATCH_SIZE = ARGS.batch_size
api_key = open(ARGS.api_key_file).read().strip()
MODEL = ARGS.model


# 读 manifest
m = json.load(open(MANIFEST, encoding="utf-8"))
images = m["images"]
print(f"Total images: {len(images)}, batch_size: {BATCH_SIZE}, batches: {(len(images)+BATCH_SIZE-1)//BATCH_SIZE}")

# 计算 batch 列表
batches = []
for i in range(0, len(images), BATCH_SIZE):
    batches.append(images[i:i+BATCH_SIZE])

# 过滤：跳过已完成的 batch（所有图都有 caption）
def batch_done(batch):
    for img in batch:
        cp = ROOT + "/wiki/" + img["path"] + ".caption.txt"
        if not os.path.exists(cp) or os.path.getsize(cp) < 20:
            return False
    return True

pending = [b for b in batches if not batch_done(b)]
print(f"Pending batches: {len(pending)}")

# Prompt 设计：让 LLM 按指定格式产出
SYSTEM = "你是硬件知识库的图像解读专家。每次给你 8 张图，按图顺序逐张描述：1-3 句中文，不超过 100 字。聚焦：图类型（电路/波形/框图/PCB/曲线/参数表/公式/实物/示意等）+ 关键内容 + 关键参数/标注。\n\n**重要**：caption 文本中禁止使用 ASCII 双引号 \"，如需引用请用「」或『』替代。禁止在 caption 中使用反斜杠 \\。\n\n输出格式：严格按以下 JSON 数组：\n```json\n[\n  {\"idx\": 1, \"caption\": \"...\"},\n  {\"idx\": 2, \"caption\": \"...\"},\n  ...\n  {\"idx\": 8, \"caption\": \"...\"}\n]\n```\n\n8 个对象都要有，idx 与图顺序一致。即使图不清楚也尽量给个最合理的简短描述。"


def _repair_json(text: str) -> str:
    """Try to repair common LLM JSON errors: unescaped quotes inside string values."""
    import re
    # Pattern: inside a "caption": "..." value, unescaped double quotes break JSON.
    # Strategy: find "caption": "..." segments and escape internal quotes.
    # More robust: try to fix line by line for array-of-objects format.

    # First attempt: standard json.loads
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # Fix unescaped quotes in caption values using regex
    repaired = re.sub(
        r'"caption":\s*"([^"]*(?:"[^"]*)*)"',
        lambda m: '"caption": "' + m.group(1).replace('"', '\\"') + '"',
        text
    )

    return repaired

def caption_batch(batch, batch_idx):
    """1 个请求处理 8 张图"""
    # Use display_name from manifest if available, otherwise SOURCE_SLUG
    book_name = m.get("display_name", SOURCE_SLUG)
    page_start = batch[0].get("page", 0)
    page_end = batch[-1].get("page", 0)
    page_hint = f"第 {page_start}-{page_end} 页的" if page_start and page_end else ""
    content = [{"type": "text", "text": f"这是《{book_name}》{page_hint}{len(batch)} 张图，请按顺序逐张描述：\n\n"}]
    for i, img in enumerate(batch):
        content[0]["text"] += f"[图{i+1}] p{img['page']}, {img['width']}x{img['height']}\n"
        img_path = ROOT + "/wiki/" + img["path"]
        with open(img_path, "rb") as f:
            img_data = base64.standard_b64encode(f.read()).decode()
        ext = img.get("ext") or img["filename"].split(".")[-1]
        media_type = f"image/{'jpeg' if ext == 'jpg' or ext == 'jpeg' else ext}"
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": img_data},
        })
        # 标注提示
        content.append({"type": "text", "text": f"[/图{i+1}]\n"})

    payload = {
        "model": MODEL,
        "max_tokens": 4096,  # 增加到 4096，防止复杂图截断
        "system": SYSTEM,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.3,
    }

    base_url = os.environ.get("LLM_BASE_URL", "https://api.minimaxi.com")
    api_url = f"{base_url.rstrip('/')}/anthropic/v1/messages"
    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            text = "".join(c["text"] for c in result["content"] if c["type"] == "text").strip()
            usage = result.get("usage", {})
            return text, usage, None
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")
        return None, None, f"HTTP {e.code}: {err[:300]}"
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"

# 跑
start_t = time.time()
total_done_imgs = 0
for bi, batch in enumerate(pending):
    # 跳过已完成的（再次检查）
    if batch_done(batch):
        total_done_imgs += len(batch)
        continue

    t0 = time.time()
    text, usage, err = caption_batch(batch, bi)
    elapsed = time.time() - t0

    if err:
        print(f"  ✗ batch {bi+1}/{len(pending)} (p{batch[0].get('page','?')}-{batch[-1].get('page','?')}): {err}")
        continue

    # 解析 JSON 数组
    # 去掉 markdown fence
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        if text.endswith("```"):
            text = text[:-3]
    try:
        captions = json.loads(text.strip())
    except json.JSONDecodeError:
        # Try to repair malformed JSON
        repaired = _repair_json(text.strip())
        try:
            captions = json.loads(repaired)
        except json.JSONDecodeError as e:
            print(f"  ✗ batch {bi+1}: JSON 解析失败 ({e}), text 前 300: {text[:300]}")
            continue

    # 写盘
    saved = 0
    for cap in captions:
        idx = cap.get("idx", 0) - 1  # 0-indexed
        if 0 <= idx < len(batch):
            img = batch[idx]
            cp = ROOT + "/wiki/" + img["path"] + ".caption.txt"
            with open(cp, "w", encoding="utf-8") as f:
                f.write(cap.get("caption", "").strip())
            saved += 1
    total_done_imgs += saved
    in_tok = usage.get("input_tokens", 0) if usage else 0
    out_tok = usage.get("output_tokens", 0) if usage else 0
    rate = saved / max(elapsed, 0.1)
    eta = (len(pending) - bi - 1) * elapsed
    print(f"  [{bi+1:3d}/{len(pending)}] p{batch[0].get('page',0):3d}-{batch[-1].get('page',0):3d} ✓ {saved}/8 ({elapsed:.1f}s, {rate:.1f}img/s, ETA {eta:.0f}s) | in={in_tok} out={out_tok}")

total_elapsed = time.time() - start_t
print(f"\n=== Summary ===")
print(f"  Total images captioned: {total_done_imgs}/{len(images)}")
print(f"  Total time: {total_elapsed:.1f}s")
print(f"  Avg per image: {total_elapsed/max(total_done_imgs,1):.2f}s")
