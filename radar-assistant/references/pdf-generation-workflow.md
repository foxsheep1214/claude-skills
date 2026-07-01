# Tracker II 竞品分析报告 PDF 生成工作流

> 生成竞品分析报告 PDF（中文渲染）时使用本流程。2026-05-11 确认。

---

## 方案A：Pandoc + Chrome Headless（推荐，已验证）

**适用于**：md 文件已有完整内容，需要导出 PDF 到桌面。

**前提**：Chrome 已安装。

```bash
OUT="/tmp/report.pdf"
IN="/path/to/report.md"

# Step 1: Pandoc md → HTML
pandoc "$IN" \
  -f markdown+tex_math_dollars+autolink_bare_uris \
  -t html5 --standalone \
  -o /tmp/report.html

# Step 2: Chrome headless → PDF
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --headless --disable-gpu \
  --no-pdf-header-footer \
  --print-to-pdf="$OUT" \
  --print-to-pdf-no-header \
  --margins-top=20 --margins-bottom=20 \
  --margins-left=25 --margins-right=20 \
  /tmp/report.html

# Step 3: 复制到桌面
cp "$OUT" ~/Desktop/
```

**验证结果**（2026-05-11）：
- `Echodyne_EchoShield雷达技术分析报告.pdf` → 671KB，11页 ✓
- `Robin_Radar_IRIS_3D技术分析报告.pdf` → 2.4MB，6页 ✓
- 均使用 Skia/PDF m147 渲染（Chrome 内核），中文正常 ✓

---

## 方案B：Python reportlab（备用）

**适用于**：无法调用 Chrome 的环境。

### 陷阱1：STHeiti 字体需注册两次 + FontFamily

macOS 的 `STHeiti Medium.ttc` 不能用 `-Bold` 后缀直接访问。正确注册方式：
```python
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

f1 = TTFont('STHeiti', '/System/Library/Fonts/STHeiti Medium.ttc')
f2 = TTFont('STHeiti-Bold', '/System/Library/Fonts/STHeiti Medium.ttc')
pdfmetrics.registerFont(f1)
pdfmetrics.registerFont(f2)
pdfmetrics.registerFontFamily('STHeiti',
    normal='STHeiti', bold='STHeiti-Bold',
    italic='STHeiti', boldItalic='STHeiti-Bold')
```
仅注册 `TTFont('STHeiti', ...)` 会导致 `ValueError: Can't map determine family/bold/italic for stheiti-bold` 错误。

### 陷阱2：xelatex/pdflatex 不可用时 Pandoc 崩溃

错误：`xelatex: createProcess: find_executable: failed`
处理：**不要修复，直接用方案A**。

### 陷阱3：CJK TTC 字体兼容性

`Hiragino Sans GB.ttc` → `postscript outlines are not supported`（不可用）
`STHeiti Medium.ttc` → 可用 ✓

---

## 快速命令

```bash
# md → HTML（需：pip3 install markdown）
python3 -c "
import markdown, sys
with open(sys.argv[1]) as f: c=f.read()
print(markdown.markdown(c, extensions=['tables','fenced_code']))
" /path/to/report.md > /tmp/report.html

# Chrome headless PDF
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf=/tmp/out.pdf --print-to-pdf-no-header \
  /tmp/report.html && cp /tmp/out.pdf ~/Desktop/
```
