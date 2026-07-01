"""Convert Tracker II requirement论证 markdown to presentation-style HTML slides.

Usage: python3 scripts/md-to-slides.py <input.md> <output.html> [title]
"""

import subprocess, re, sys
from pathlib import Path

def convert_md(md_text):
    """Convert markdown chunk to HTML via pandoc."""
    result = subprocess.run(
        ['pandoc', '-f', 'markdown+autolink_bare_uris+simple_tables', '-t', 'html'],
        input=md_text, capture_output=True, text=True, timeout=30
    )
    return result.stdout.strip() if result.returncode == 0 else ""

def main(input_path, output_path, title="Presentation"):
    md_text = Path(input_path).read_text()
    lines = md_text.split('\n')
    
    # Split on ## headings into slide chunks
    slides_raw = []
    current_slide = []
    is_first = True
    
    for line in lines:
        if line.startswith('## '):
            if current_slide:
                slides_raw.append('\n'.join(current_slide).strip())
            current_slide = [line]
        elif line.startswith('# ') and not line.startswith('## '):
            if current_slide:
                slides_raw.append('\n'.join(current_slide).strip())
            current_slide = [line]
        else:
            if is_first and not line.startswith('#'):
                current_slide.append(line)
            else:
                current_slide.append(line)
        is_first = False
    
    if current_slide:
        slides_raw.append('\n'.join(current_slide).strip())
    
    # Load template
    template_path = Path(__file__).resolve().parent.parent / 'templates' / 'slide-template.html'
    template = template_path.read_text()
    
    # Build slides
    slides_html = []
    for part in slides_raw:
        if not part.strip():
            continue
        
        is_cover = part.strip().startswith('# Tracker') or part.strip().startswith(f'# {title}')
        is_section = bool(re.match(r'^# (一、|二、|三、)', part.strip()))
        
        slide_class = "slide"
        if is_cover:
            slide_class += " cover"
        elif is_section:
            slide_class += " section"
        
        html_body = convert_md(part)
        if not html_body:
            continue
        
        # Fix empty cover slide
        if is_cover and '<h1>' not in html_body:
            html_body = f'<h1>{title}</h1>\n<p class="subtitle">Skyfend Technology</p>'
        
        slide_html = f'<section class="{slide_class}">\n<div class="slide-content">\n{html_body}\n</div>\n</section>'
        slides_html.append(slide_html)
    
    # Assemble
    final_html = template.replace('REPLACE_TITLE', title).replace('$body$', '\n'.join(slides_html))
    Path(output_path).write_text(final_html)
    print(f"Done: {output_path} ({len(final_html)} chars, {len(slides_html)} slides)")

if __name__ == '__main__':
    inp = sys.argv[1]
    out = sys.argv[2]
    ttl = sys.argv[3] if len(sys.argv) > 3 else "Presentation"
    main(inp, out, ttl)
