"""
著作权文档生成服务 — 生成计算机软件著作权登记申请文档。

三份文档：
  1. 源代码文档（前30页 + 后30页，每页≥50行代码，55行/页）
  2. 软件说明书（markdown → 图文排版，含 mermaid 流程图）
  3. 申请信息汇总表（markdown → 表格化排版）

PDF 渲染：
  - 行内嵌入 mermaid.min.js，Edge headless --print-to-pdf 一次完成
  - 无需 Node.js / puppeteer
"""

import base64
import os
import re
import subprocess
import tempfile
import json
import urllib.request
from datetime import datetime
from pathlib import Path

# ── 项目根路径 ──
PROJECT_ROOT = Path(__file__).parent.parent.parent
DOCS_DIR = PROJECT_ROOT / 'docs' / 'copyright'
MERMAID_JS_PATH = PROJECT_ROOT / 'tools' / 'mermaid' / 'mermaid.min.js'
SOURCE_DIR = PROJECT_ROOT / 'src'

# ── 浏览器候选路径（按优先级） ──
BROWSER_CANDIDATES = [
    # Edge
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    # Chrome
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    # Edge Dev/Canary
    os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge SxS\Application\msedge.exe'),
]

# ── 运行时配置（由 _load_config 填充） ──
_CFG = {}  # type: ignore

def _load_config() -> dict:
    """从 config/copyright.json 加载著作权配置。"""
    cfg_path = PROJECT_ROOT / 'config' / 'copyright.json'
    defaults = {
        'software_name': '左右道飞MCP服务系统',
        'software_name_en': 'Daofy MCP Server',
        'version': 'V2026.06.08.1',
        'completed_date': '2026年6月8日',
        'copyright_holder': '吉林省左右软件开发有限公司',
        'copyright_holder_en': 'Equilibrium Software Development Co., Ltd, Jilin',
        'unified_social_credit_code': '',
        'contact_person': '',
        'contact_phone': '',
        'contact_address': '',
        'source_code': {
            'front_pages': 30,
            'back_pages': 30,
            'lines_per_page': 55,
            'front_files': [
                'server.py',
                'tools/file_tool.py',
            ],
            'back_files': [
                'services/compiler_service.py',
                'services/config_manager.py',
                'services/process_manager.py',
                'services/args_generator.py',
                'services/knowledge_base/__init__.py',
                'services/knowledge_base/schema.py',
                'services/knowledge_base/embedding_service.py',
                'services/knowledge_base/project_knowledge_base.py',
                'services/knowledge_base/thirdparty_knowledge_base.py',
                'services/knowledge_base/document_knowledge_base.py',
                'services/knowledge_base/service.py',
                'services/knowledge_base/smart_cache.py',
                'services/knowledge_base/scan_service.py',
                'services/knowledge_base/async_task_manager.py',
                'utils/logger.py',
                'utils/validator.py',
                'utils/dproj_parser.py',
                'utils/delphi_env.py',
            ],
        },
    }
    try:
        if cfg_path.exists():
            with open(str(cfg_path), 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            # 递归合并（loaded 覆盖 defaults）
            def _deep_merge(d, u):
                for k, v in u.items():
                    if k in d and isinstance(d[k], dict) and isinstance(v, dict):
                        _deep_merge(d[k], v)
                    elif k not in d:
                        d[k] = v
            _deep_merge(loaded, defaults)
            return loaded
    except Exception as e:
        print(f'    ⚠ 读取版权配置失败: {e}，使用默认值')
    return defaults

# 模块级快捷引用
def _cfg_val(*keys: str, default=''):
    """从 _CFG 中安全读取嵌套值。"""
    val = _CFG
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k, {})
        else:
            return default
    return val if val else default

_CFG = _load_config()

# ── 工具函数 ──

def detect_browser() -> str:
    """查找系统上可用的 Chromium 系浏览器，返回 exe 路径。"""
    for path in BROWSER_CANDIDATES:
        if os.path.isfile(path):
            return path
    # 注册表查找 Edge
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe')
        path = winreg.QueryValueEx(key, '')[0]
        winreg.CloseKey(key)
        if os.path.isfile(path):
            return path
    except Exception:
        pass
    raise RuntimeError(
        '未找到浏览器。请安装 Edge 或 Chrome。'
        '\n已搜索路径: ' + '\n  '.join(BROWSER_CANDIDATES)
    )


def _load_mermaid_js() -> str:
    """读取 mermaid.min.js 用于行内嵌入。"""
    if MERMAID_JS_PATH.exists():
        with open(str(MERMAID_JS_PATH), 'r', encoding='utf-8') as f:
            return f.read()
    # 从 CDN 远程加载（降级）
    try:
        url = 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js'
        resp = urllib.request.urlopen(url, timeout=30)
        js = resp.read().decode('utf-8')
        # 缓存到本地
        MERMAID_JS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(str(MERMAID_JS_PATH), 'w', encoding='utf-8') as f:
            f.write(js)
        return js
    except Exception as e:
        raise RuntimeError(f'无法加载 mermaid.min.js: {e}')


# ── CSS 定义 ──

STANDARD_CSS = r"""
@page {
    size: A4;
    margin: 20mm 25mm 25mm 25mm;
    @bottom-center {
        content: attr(data-footer);
        font-size: 9pt;
        color: #666;
        font-family: "Microsoft YaHei", sans-serif;
    }
}
body {
    font-family: "Microsoft YaHei", "SimSun", sans-serif;
    font-size: 11pt;
    line-height: 1.7;
    color: #222;
}
h1 { font-size: 18pt; text-align: center; margin: 20mm 0 10mm 0; }
h2 { font-size: 15pt; border-bottom: 2px solid #333; padding-bottom: 3px; margin-top: 15mm; }
h3 { font-size: 13pt; margin-top: 12mm; }
h4 { font-size: 11pt; margin-top: 8mm; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 10pt; }
table, th, td { border: 1px solid #666; }
th, td { padding: 5px 8px; text-align: left; }
th { background-color: #f0f0f0; }
code {
    font-family: "Consolas", "Courier New", monospace;
    font-size: 9pt; background: #f5f5f5; padding: 1px 4px; border-radius: 2px;
}
pre {
    background: #fafafa; border: 1px solid #ddd; border-left: 4px solid #4CAF50;
    padding: 10px; overflow-x: auto; font-size: 8.5pt; line-height: 1.35;
    page-break-inside: avoid;
}
pre code { background: none; padding: 0; }
blockquote {
    border-left: 4px solid #ccc; margin: 8px 0; padding: 6px 14px; background: #f9f9f9;
}
p { margin: 6px 0; text-indent: 2em; }
ul, ol { margin: 6px 0; padding-left: 2em; }
li { margin: 3px 0; }
.mermaid { text-align: center; margin: 15px 0; page-break-inside: avoid; }
.mermaid svg { max-width: 100%; height: auto; }
"""

SOURCE_CODE_CSS = r"""
@page {
    size: A4;
    margin: 12mm 15mm 15mm 15mm;
}
body {
    font-family: "Consolas", "Courier New", monospace;
    background: #fff;
    margin: 0;
    padding: 0;
}
.page + .page {
    page-break-before: always;
}
.page-header {
    font-family: "Microsoft YaHei", sans-serif;
    font-size: 9pt;
    border-bottom: 2px solid #333;
    padding-bottom: 3px;
    margin-bottom: 5px;
    display: flex;
    justify-content: space-between;
}
.page-header .left { font-weight: bold; }
.page-header .right { color: #555; }
.page-footer {
    font-family: "Microsoft YaHei", sans-serif;
    font-size: 7.5pt;
    color: #999;
    text-align: center;
    border-top: 1px solid #ddd;
    padding-top: 3px;
    margin-top: 4px;
}
.code-block {
    font-size: 7.5pt;
    line-height: 1.5;
    font-family: "Consolas", "Courier New", monospace;
}
.code-line {
    display: flex;
    border-bottom: 1px dotted #eee;
}
.line-num {
    width: 28px;
    text-align: right;
    padding-right: 6px;
    color: #999;
    flex-shrink: 0;
    border-right: 1px solid #ddd;
    margin-right: 6px;
    font-size: 7pt;
}
.line-content {
    white-space: pre;
    flex: 1;
    overflow: hidden;
}
.page-cover {
    width: 180mm;
    height: 270mm;
    box-sizing: border-box;
    text-align: center;
    padding-top: 60mm;
    font-family: "Microsoft YaHei", sans-serif;
}
.page-cover h1 { font-size: 20pt; margin-bottom: 15mm; }
.page-cover table { width: 60%; margin: 0 auto; font-size: 11pt; border: none; }
.page-cover table td { border: 1px solid #999; padding: 6px 12px; }
.page-cover table td:first-child {
    font-weight: bold;
    background: #f5f5f5;
    width: 35%;
    text-align: right;
}
.page-subtitle {
    font-family: "Microsoft YaHei", sans-serif;
    font-size: 9pt;
    color: #666;
    margin-bottom: 8px;
}
"""


# ════════════════════════════════════════════════════
# HTML → PDF（Edge headless）
# ════════════════════════════════════════════════════

def html_to_pdf(html_content: str, pdf_path: str) -> tuple[bool, str]:
    """渲染 HTML 到 PDF，使用浏览器 headless 模式。"""
    fd, html_path = tempfile.mkstemp(suffix='.html', prefix='doc_')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(html_content)

    file_url = 'file:///' + html_path.replace('\\', '/')
    browser = detect_browser()

    try:
        cmd = [
            browser,
            '--headless=new',
            '--disable-gpu',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-extensions',
            f'--print-to-pdf={pdf_path}',
            file_url,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        stderr = result.stderr.decode('utf-8', errors='replace')[:300]

        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000:
            size = os.path.getsize(pdf_path)
            return True, f'{size / 1024:.0f} KB'
        else:
            return False, f'Output too small / {stderr}'

    except subprocess.TimeoutExpired:
        return False, 'Timeout (60s)'
    except Exception as e:
        return False, str(e)
    finally:
        try:
            os.unlink(html_path)
        except Exception:
            pass


# ════════════════════════════════════════════════════
# Markdown → HTML（预渲染 mermaid → SVG）
# ════════════════════════════════════════════════════

def _render_mermaid_to_svg(mermaid_code: str) -> str:
    """使用 Edge headless 将一段 mermaid 代码渲染为 SVG 字符串。"""
    mermaid_js = _load_mermaid_js()
    browser = detect_browser()

    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body{{margin:0;text-align:center;font-family:"Microsoft YaHei","SimSun",sans-serif;}}svg{{max-width:100%;height:auto;}}</style>
<script>{mermaid_js}</script>
<script>mermaid.initialize({{startOnLoad:true,theme:"default",htmlLabels:false,flowchart:{{useMaxWidth:true}},themeVariables:{{fontFamily:"Microsoft YaHei, SimSun, sans-serif"}}}});</script>
</head><body>
<div class="mermaid">
{mermaid_code}
</div>
</body></html>'''

    fd, html_path = tempfile.mkstemp(suffix='.html', prefix='mermaid_render_')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(html)

    file_url = 'file:///' + html_path.replace('\\', '/')

    try:
        cmd = [browser, '--headless=new', '--disable-gpu',
               '--virtual-time-budget=5000', '--dump-dom', file_url]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        dom = result.stdout.decode('utf-8', errors='replace')

        # 在 DOM 中找 <div class="mermaid" ...> 内的 <svg>...</svg>
        # 渲染后 mermaid 会给 div 加上 data-processed="true"
        m = re.search(
            r'<div\s+class="mermaid"[^>]*>\s*(<svg[^>]*>.*?</svg>)\s*</div>',
            dom, re.DOTALL,
        )
        if m:
            svg = m.group(1)
            return svg

        # fallback: 直接找任意 <svg>
        m = re.search(r'(<svg[^>]*>.*?</svg>)', dom, re.DOTALL)
        return m.group(1) if m else ''

    except Exception as e:
        print(f'  ⚠ mermaid 预渲染失败: {e}')
        return ''
    finally:
        try:
            os.unlink(html_path)
        except Exception:
            pass


def _embed_images_as_base64(md_content: str, base_dir: Path) -> str:
    """将 markdown 中所有外部图片引用（非 data URI）替换为 base64 内嵌，避免 PDF 渲染时路径失效。

    匹配格式: ![alt](path) 或 ![alt](path "title")
    跳过 data: 开头的 URI。
    支持 jpg/jpeg/png/gif/bmp/svg/webp 格式，自动检测 MIME 类型。
    如果图片文件不存在或读取失败，保持原样并打印警告。
    """
    def _replace(match):
        alt_text = match.group(1)
        img_path = match.group(2)
        title = match.group(3) or ''

        # 跳过已经是 data URI 的
        if img_path.startswith('data:'):
            return match.group(0)

        # 解析图片路径
        resolved = (base_dir / img_path).resolve()
        if not resolved.exists():
            print(f'  ⚠ 图片文件不存在，跳过 base64 编码: {resolved}')
            return match.group(0)

        # 读取文件并编码
        ext = resolved.suffix.lower()
        mime_map = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png', '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.svg': 'image/svg+xml',
            '.webp': 'image/webp',
        }
        mime = mime_map.get(ext, 'image/jpeg')
        try:
            data = resolved.read_bytes()
            b64 = base64.b64encode(data).decode('ascii')
            data_uri = f'data:{mime};base64,{b64}'
            if title:
                return f'![{alt_text}]({data_uri} "{title}")'
            else:
                return f'![{alt_text}]({data_uri})'
        except Exception as e:
            print(f'  ⚠ 图片 base64 编码失败 ({resolved}): {e}')
            return match.group(0)

    # 匹配 ![alt](path) 或 ![alt](path "title")
    return re.sub(
        r'!\[([^\]]*)\]\(([^)]+?)(?:\s+"([^"]*)")?\)',
        _replace,
        md_content,
    )


def _pre_render_mermaid_in_md(md_content: str) -> str:
    """将 markdown 中所有 ```mermaid 块预渲染为内联 SVG。"""
    def _fix_text_anchor(svg: str) -> str:
        """给所有 <text> 元素加上 text-anchor="middle"，确保文字在节点中居中。"""
        # 只处理包含中文或字母内容的 <text> 标签（排除空的占位标签）
        def _add_anchor(match):
            tag = match.group(0)
            if 'text-anchor' in tag:
                return tag
            # 在 <text 后面、第一个 > 之前插入 text-anchor="middle"
            return tag.replace('<text', '<text text-anchor="middle"', 1)
        
        return re.sub(r'<text[^>]*>.*?</text>', _add_anchor, svg, flags=re.DOTALL)
    
    def _replace(match):
        code = match.group(1).strip()
        svg = _render_mermaid_to_svg(code)
        if svg and len(svg) > 500:
            svg = _fix_text_anchor(svg)
            return (
                f'<div style="text-align:center;margin:15px 0;'
                f'page-break-inside:avoid;">\n'
                f'{svg}\n'
                f'</div>'
            )
        return match.group(0)

    return re.sub(
        r'```mermaid\s*\n(.*?)```',
        _replace,
        md_content,
        flags=re.DOTALL,
    )

    return re.sub(
        r'```mermaid\s*\n(.*?)```',
        _replace,
        md_content,
        flags=re.DOTALL,
    )


def md_to_html(content: str, base_dir: Path | None = None) -> str:
    """将 markdown 转为 HTML，mermaid 代码块预渲染为内联 SVG（浏览器端不需要 mermaid.js）。

    base_dir: 用于解析相对路径图片的基准目录。不传则不进行 base64 图片嵌入。
    """
    import markdown  # 可选依赖，延迟导入

    # 自动将外部图片 base64 嵌入（避免 PDF 渲染时路径失效）
    if base_dir is not None:
        content = _embed_images_as_base64(content, base_dir)

    # 预渲染 mermaid 块为 SVG（已指定 fontFamily 以匹配中文 PDF 字体）
    content = _pre_render_mermaid_in_md(content)

    html_body = markdown.markdown(
        content,
        extensions=['extra', 'toc', 'tables', 'fenced_code', 'codehilite', 'sane_lists'],
    )

    # 安全网：清理 markdown 解析后残留的 <pre><code class="language-mermaid">
    html_body = re.sub(
        r'<pre[^>]*><code class="language-mermaid">(.*?)</code></pre>',
        r'<div class="mermaid">\1</div>',
        html_body,
        flags=re.DOTALL,
    )

    sw_name = _cfg_val('software_name', default='左右道飞MCP服务系统')
    version = _cfg_val('version', default='V2026.06.08.1')

    # 如果有残留的 mermaid 块（预渲染失败的），嵌入 mermaid.js 保底
    has_mermaid_fallback = '<div class="mermaid">' in html_body
    mermaid_script = ''
    if has_mermaid_fallback:
        mermaid_js = _load_mermaid_js()
        mermaid_script = f'<script>{mermaid_js}</script>\n<script>mermaid.initialize({{startOnLoad:true,theme:"default",htmlLabels:false,themeVariables:{{fontFamily:"Microsoft YaHei, SimSun, sans-serif"}}}});</script>\n'

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>{STANDARD_CSS}</style>
{mermaid_script}</head>
<body data-footer="{sw_name} {version}">
{html_body}
</body>
</html>'''


# ════════════════════════════════════════════════════
# 源代码文档 → HTML（分页 + 行号）
# ════════════════════════════════════════════════════

def _collapse_blank_lines(code_lines: list[str], max_blank: int = 2) -> list[str]:
    """折叠连续空白行，最多保留 max_blank 行。"""
    result = []
    blank_count = 0
    for line in code_lines:
        if line.strip() == '':
            blank_count += 1
            if blank_count <= max_blank:
                result.append(line)
        else:
            blank_count = 0
            result.append(line)
    return result


def _render_page(html_parts: list, page_num: int, section: str,
                 file_info: str, code_lines: list[str]) -> None:
    """渲染一页代码到 html_parts。"""
    sw_name = _cfg_val('software_name', default='左右道飞MCP服务系统')
    holder = _cfg_val('copyright_holder', default='吉林省左右软件开发有限公司')
    html_parts.extend([
        '<div class="page">',
        '<div class="page-header">',
        f'<span class="left">{sw_name} 源代码</span>',
        f'<span class="right">第 {page_num} 页 — {section}</span>',
        '</div>',
        file_info,
        '<div class="code-block">',
    ])

    for idx, code_line in enumerate(code_lines, 1):
        escaped = (code_line
                   .replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;'))
        html_parts.append(
            f'<div class="code-line">'
            f'<span class="line-num">{idx:3d}</span>'
            f'<span class="line-content">{escaped}</span>'
            f'</div>'
        )

    html_parts.extend([
        '</div>',
        f'<div class="page-footer">{holder} 版权所有</div>',
        '</div>',
    ])


def _read_source_chunks(file_entries: list[str], section_prefix: str,
                        total_pages: int, file_lines: int,
                        lines_per_page: int) -> list[tuple[str, str, str, list[str]]]:
    """读取源码文件并分为 LINES_PER_PAGE 行一页的块。

    Returns:
        [(section_title, file_info_html, file_relative_path, chunk_lines), ...]
    """
    chunks = []
    page_counter = 0

    for rel_path in file_entries:
        full_path = SOURCE_DIR / rel_path
        if not full_path.exists():
            print(f'    ⚠ 文件不存在: {full_path}')
            continue

        with open(str(full_path), 'r', encoding='utf-8', errors='replace') as f:
            raw_lines = f.readlines()

        # 保留末尾换行符，去掉最后的空串
        stripped = [l.rstrip('\n').rstrip('\r') for l in raw_lines]
        code_lines = _collapse_blank_lines(stripped)

        total = len(code_lines)
        for i in range(0, total, lines_per_page):
            chunk = code_lines[i:i + lines_per_page]
            page_counter += 1
            if page_counter > total_pages:
                break
            section = f'{section_prefix} 第 {page_counter} 页 — {rel_path} ({i+1}-{min(i+lines_per_page, total)}行)'
            file_info = f'<div class="page-subtitle">文件: {rel_path} (原始行号 {i+1}-{min(i+lines_per_page, total)})</div>'
            chunks.append((section, file_info, rel_path, chunk))

        if page_counter >= total_pages:
            break

    # 如果不够页数，用空白页补充
    while page_counter < total_pages:
        page_counter += 1
        section = f'{section_prefix} 第 {page_counter} 页 — (空)'
        file_info = ''
        chunks.append((section, file_info, '', [' '] * 55))

    return chunks


def generate_source_code_html() -> str:
    """生成源代码文档的完整 HTML。"""
    sw_name = _cfg_val('software_name', default='左右道飞MCP服务系统')
    sw_en = _cfg_val('software_name_en', default='Daofy MCP Server')
    version = _cfg_val('version', default='V2026.06.08.1')
    holder = _cfg_val('copyright_holder', default='吉林省左右软件开发有限公司')
    sc = _CFG.get('source_code', {})
    front_pages = sc.get('front_pages', 30)
    back_pages = sc.get('back_pages', 30)
    lpp = sc.get('lines_per_page', 55)
    front_files = sc.get('front_files', ['server.py'])
    back_files = sc.get('back_files', [])

    total_pages = front_pages + back_pages
    html_parts = [
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
        '<meta charset="utf-8">\n'
        f'<style>{SOURCE_CODE_CSS}</style>\n'
        '</head>\n<body>',
    ]

    # 封面页
    html_parts.append('<div class="page-cover">')
    html_parts.append('<h1>源代码文档</h1>')
    html_parts.append('<table>')
    html_parts.append(f'<tr><td>软件名称</td><td>{sw_name}</td></tr>')
    html_parts.append(f'<tr><td>英文名称</td><td>{sw_en}</td></tr>')
    html_parts.append(f'<tr><td>版本号</td><td>{version}</td></tr>')
    html_parts.append(f'<tr><td>著作权人</td><td>{holder}</td></tr>')
    html_parts.append('<tr><td>开发语言</td><td>Python 3.10+</td></tr>')
    html_parts.append(f'<tr><td>代码规模</td><td>约 {total_pages * lpp} 行（{total_pages}页）</td></tr>')
    html_parts.append('</table>')
    html_parts.append('</div>')

    # 前页
    page_num = 0
    front_chunks = _read_source_chunks(front_files, '前', front_pages, lpp, lpp)
    for section, file_info, _rel, chunk in front_chunks:
        page_num += 1
        _render_page(html_parts, page_num, section, file_info, chunk)

    # 后页
    back_chunks = _read_source_chunks(back_files, '后', back_pages, lpp, lpp)
    for section, file_info, _rel, chunk in back_chunks:
        page_num += 1
        _render_page(html_parts, page_num, section, file_info, chunk)

    html_parts.append('</body></html>')
    return '\n'.join(html_parts)


# ════════════════════════════════════════════════════
# 文件名辅助
# ════════════════════════════════════════════════════

def _filename(doc_type: str, ext: str) -> str:
    """生成标准文件名，如 源代码文档-左右道飞MCP服务系统.pdf"""
    sw = _cfg_val('software_name', default='左右道飞MCP服务系统')
    names = {
        'source': '源代码文档',
        'manual': '软件说明书',
        'summary': '申请信息汇总表',
    }
    prefix = names.get(doc_type, doc_type)
    return f'{prefix}-{sw}.{ext}'


# ════════════════════════════════════════════════════
# 截图保存目录
# ════════════════════════════════════════════════════

SNAPSHOTS_DIR = PROJECT_ROOT / 'docs' / 'copyright' / 'snapshots'

def get_snapshots_dir() -> str:
    """获取截图保存目录，不存在时自动创建。"""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    return str(SNAPSHOTS_DIR)


# ════════════════════════════════════════════════════
# 配置校验与保存
# ════════════════════════════════════════════════════

# 生成著作权文档必需的字段（为空时阻止生成）
REQUIRED_FIELDS = {
    'software_name': '软件名称',
    'copyright_holder': '著作权人',
    'unified_social_credit_code': '统一社会信用代码',
    'contact_person': '联系人',
    'contact_phone': '联系电话',
    'contact_address': '联系地址',
    'version': '版本号',
}

def _get_config_path() -> Path:
    """获取 config/copyright.json 的完整路径。"""
    return PROJECT_ROOT / 'config' / 'copyright.json'


def _validate_config() -> list[dict]:
    """检查必填字段，返回缺失/空值的字段列表。"""
    missing = []
    for key, label in REQUIRED_FIELDS.items():
        val = _cfg_val(key, default='')
        if not val or (isinstance(val, str) and val.strip() == ''):
            missing.append({'key': key, 'label': label})
    return missing


def _save_config(updates: dict) -> dict:
    """将 updates 合并写入 config/copyright.json 并重载 _CFG。

    Args:
        updates: 要更新的键值对，如 {"contact_person": "张三"}

    Returns:
        保存后的完整配置。
    """
    cfg_path = _get_config_path()
    global _CFG

    # 读取当前配置
    if cfg_path.exists():
        with open(str(cfg_path), 'r', encoding='utf-8') as f:
            current = json.load(f)
    else:
        current = {}

    # 递归合并
    def _deep_merge(d, u, path=''):
        for k, v in u.items():
            if k in d and isinstance(d[k], dict) and isinstance(v, dict):
                _deep_merge(d[k], v, f'{path}.{k}')
            else:
                d[k] = v

    _deep_merge(current, updates)

    # 写回文件
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(cfg_path), 'w', encoding='utf-8') as f:
        json.dump(current, f, ensure_ascii=False, indent=2)

    # 重载内存配置
    _CFG = _load_config()
    return _CFG


# ════════════════════════════════════════════════════
# 源码扫描与内容草稿生成
# ════════════════════════════════════════════════════

def _scan_project() -> dict:
    """扫描 src/ 目录，返回结构化项目信息，用于生成文档草稿。"""
    src = SOURCE_DIR
    if not src.exists():
        return {'error': f'src/ 目录不存在: {src}'}

    scan = {
        'total_files': 0,
        'total_lines': 0,
        'py_files': 0,
        'modules': {},
        'tools_count': 0,
        'services_count': 0,
        'models_count': 0,
        'utils_count': 0,
        'all_files': [],
    }

    for py_file in sorted(src.rglob('*.py')):
        rel = py_file.relative_to(src)
        parts = rel.parts
        module = parts[0] if len(parts) > 1 else 'root'
        scan['all_files'].append(str(rel))
        scan['py_files'] += 1
        lines = py_file.read_text('utf-8', errors='replace').count('\n')
        scan['total_lines'] += lines

        if module not in scan['modules']:
            scan['modules'][module] = {'count': 0, 'lines': 0}
        scan['modules'][module]['count'] += 1
        scan['modules'][module]['lines'] += lines

        # 分类计数
        if module == 'tools':
            scan['tools_count'] += 1
        elif module == 'services':
            scan['services_count'] += 1
        elif module == 'models':
            scan['models_count'] += 1
        elif module in ('utils',):
            scan['utils_count'] += 1

    # 附加信息
    cfg_path = PROJECT_ROOT / 'config'
    scan['config_files'] = [f.name for f in sorted(cfg_path.glob('*.json'))] if cfg_path.exists() else []

    tests_path = PROJECT_ROOT / 'tests'
    scan['test_files'] = len(list(tests_path.rglob('*.py'))) if tests_path.exists() else 0

    docs_path = PROJECT_ROOT / 'docs'
    scan['doc_files'] = len(list(docs_path.rglob('*'))) if docs_path.exists() else 0

    return scan


def _build_module_table(scan: dict) -> str:
    """从扫描数据生成模块统计表格 markdown。"""
    rows = []
    for module in sorted(scan['modules']):
        info = scan['modules'][module]
        label = {'root': '入口（server.py）', 'config': '配置', 'models': '数据模型',
                 'services': '业务逻辑', 'tools': '工具实现', 'utils': '工具类'}.get(module, module)
        rows.append(f'| {label} ({module}/) | {info["count"]} | {info["lines"]} |')
    return '\n'.join(rows)


def _generate_manual_draft(scan: dict) -> str:
    """生成软件说明书草稿 markdown（通用基础模板，正文由 AI Agent 根据项目实际补充）。"""
    sw_name = _cfg_val('software_name', default='')
    sw_en = _cfg_val('software_name_en', default='')
    version = _cfg_val('version', default='')
    holder = _cfg_val('copyright_holder', default='')
    completed_date = _cfg_val('completed_date', default='')

    total_py = scan['py_files']
    total_lines = scan['total_lines']
    module_table = _build_module_table(scan)

    # 备选语言描述（如非 Python 项目，AI 应替换为实际语言和行数）
    lang = scan.get('language', 'Python')

    return f"""# 计算机软件著作权登记用软件说明书

## 软件名称：{sw_name}

**英文名称**：{sw_en}

**版本号**：{version}

**开发完成日期**：{completed_date}

**著作权人**：{holder}

**编程语言**：{lang}

**运行环境**：<!-- 请根据项目实际填写运行环境，如操作系统、依赖框架等，50字以内 -->

**软件类型**：<｜请根据项目实际填写软件分类，如"应用软件 — XXX"、50字以内>

---

## 第一章 引言

### 1.1 背景

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 背景】

必须包含以下内容（150-300字）：
1. 软件所属技术领域的现状与发展趋势
2. 当前存在什么问题或痛点（说明需要开发本软件的原因）
3. 本软件针对这些痛点提供了什么解决方案
4. 软件名称的含义或定位

⚠️ 避免：过于空泛的行业背景描述、抄袭其他软件的背景说明
⚠️ 避免：使用"随着社会的进步""随着科技的发展"等空洞套话
✅ 要求：具体到目标用户的真实痛点，与软件功能直接相关
════════════════════════════════════════════════════════════ -->

### 1.2 目的

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 目的】

必须包含以下内容（80-150字）：
1. 本说明书编写的直接目的（如：全面介绍 XXX 系统的功能特性、系统架构、安装配置和操作使用方法）
2. 用户通过阅读本说明书能够获得的认知（了解什么、掌握什么）

⚠️ 避免：写入"推广市场""扩大知名度"等商业营销性质表述
✅ 要求：客观、文档化的口吻，只说"帮助用户了解/掌握/使用"
════════════════════════════════════════════════════════════ -->

### 1.3 范围

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 范围】

必须列出本说明书涵盖的全部章节名称（100-200字），格式如下：
- 第一章 引言：背景、目的、范围和术语定义
- 第二章 系统概述：...
- ...
- 直到第七章

⚠️ 避免：遗漏章节、章节号与正文不一致
✅ 要求：与输出文档的实际章节结构完全对应
════════════════════════════════════════════════════════════ -->

### 1.4 术语与定义

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 术语与定义】

必须用表格列出本项目中使用的专有术语及其定义，格式：
| 术语 | 定义 |
|------|------|

至少包含 5 个与本软件密切相关的术语，不相关的外部术语不要罗列。

⚠️ 避免：照搬通用术语词典
✅ 要求：只列本系统文档中实际使用的、用户可能不熟悉的专业术语
════════════════════════════════════════════════════════════ -->

---

## 第二章 系统概述

### 2.1 软件简介

{sw_name}（{sw_en}）是一款 <!-- 请用一句话概括软件的核心定位（30-50字），说明是什么类型、解决什么问题 -->。

系统共包含 **{total_py} 个源文件**（约 {total_lines:,} 行代码），按功能划分为以下模块：

{module_table}

**测试覆盖**：{scan.get('test_files', 0)} 个测试文件

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 核心价值】

列出 3-4 条软件的核心价值/特色（每条 10-20 字），用 **粗体短句** + 冒号 + 一句话说明的格式。

例如：
- **自动化处理**：自动识别并处理 XXX，减少人工干预
- **智能检索**：内置 XXX 知识库，支持语义搜索

⚠️ 避免：营销用语（"业界领先""最先进"）
✅ 要求：每条对应一个实际功能模块
════════════════════════════════════════════════════════════ -->

### 2.2 功能总览

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 功能总览】

1. 先用一段话总结系统提供了哪些主要功能类型（150-250字）
2. 然后用表格列出每个功能模块/接口，格式：
| 功能类别 | 功能模块 | 说明 |

表格中的「说明」列必须写清楚每个功能做什么，不少于 15 字/个。

⚠️ 避免：表格说明只有 3-5 个字
✅ 要求：每个功能的说明至少包含 2 个具体用途
════════════════════════════════════════════════════════════ -->

### 2.3 运行环境

#### 2.3.1 硬件环境

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 硬件环境】

用表格列出建议的最低配置和推荐配置：
| 项目 | 最低配置 | 推荐配置 |
|------|----------|----------|

⚠️ 避免：填入过于夸张的要求（如"128GB内存"）
✅ 要求：根据实际开发测试环境填写合理数值
════════════════════════════════════════════════════════════ -->

#### 2.3.2 软件环境

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 软件环境】

用表格列出所需的操作系统、运行时、依赖框架及版本。

| 项目 | 要求 |
|------|------|

⚠️ 避免：遗漏关键依赖
✅ 要求：版本号精确到主版本号
════════════════════════════════════════════════════════════ -->

---

## 第三章 系统架构

### 3.1 总体架构

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 总体架构】

用 ```mermaid 流程图 + 文字描述系统的分层架构，包括：
1. 系统分为几层，每层的名称和职责
2. 各层之间的依赖关系和通信/调用方式
3. 核心数据流（用户请求从进入到返回的完整路径）
4. 可用表格列出各层包含的模块/组件

推荐格式：先用一段文字总述，然后使用 ```mermaid graph TD 绘制分层架构流程图，
最后用表格列出各层包含的模块组件。

✅ 要求：必须使用 ```mermaid 流程图展示分层架构（PDF 渲染已支持，服务端预渲染为 SVG）
✅ 辅助：流程图之后，用文字+表格进一步补充说明各模块职责
════════════════════════════════════════════════════════════ -->

### 3.2 模块划分

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 模块划分】

先用一段话总结系统共划分为几个模块，各模块的代码分布。
然后用表格列出各模块的：模块名称、路径、文件数、代码行数、职责说明
格式：
| 模块名 | 路径 | 文件数 | 代码行数 | 职责说明 |

职责说明要写清楚该模块做什么（15-30字/个）

⚠️ 避免：职责说明只有"配置管理"4个字
✅ 要求：职责说明必须包含具体管理/定义/处理的内容
════════════════════════════════════════════════════════════ -->

---

## 第四章 模块详细设计

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 模块详细设计】

⚠️ 这是审查最严格的章节，必须写得足够详细。

每个模块按以下结构展开：

### 4.X 模块名（对应文件路径）

**功能概述**（必写，100-200字）：
- 该模块的核心职责
- 在系统中扮演什么角色
- 输入/输出是什么

**核心类与函数**（必写，表格形式）：
| 核心组件 | 所属文件 | 职责 |
|----------|----------|------|

**核心流程/工作流**（必写，版式强制：先用 ```mermaid 流程图整体展示，然后每个步骤单独一段展开说明）：
✅ 格式（先图，再逐段说明）：
```mermaid
graph TD
    A[开始] --> B{{条件判断}}
    B -->|是| C[处理A]
    B -->|否| D[处理B]
    C --> E[结束]
```
⚠️ 注意：条件判断节点用 `{{条件}}` 单花括号（菱形节点），不要用 `{{{{条件}}}}` 双花括号（六边形节点，双花括号图形可能造成文字居中不准）

每个步骤展开为独立段落，不要挤在一段：
**步骤 1：起始状态 / 触发条件**
详细说明步骤 1 的触发条件、前置条件和具体操作内容。

**步骤 2：步骤名称**
详细说明步骤 2 的具体操作，包括涉及的数据、判断逻辑等。

**步骤 N：结束状态 / 输出结果**
描述流程结束时的输出、后续处理或异常情况。

**关键特性**（必写，列表形式，至少3条）

════════════════════════════════════════════════════════════

需要覆盖以下根据扫描结果识别的模块：
{_build_module_table(scan).replace('|', '·')}

⚠️ 避免：各模块篇幅相近——核心模块必须比非核心模块长 2-3 倍
⚠️ 避免：只有功能概述没有流程步骤
⚠️ 避免：流程步骤过于简略（每个步骤应写明具体操作）
✅ 要求：核心模块各占一页以上篇幅
-->

---

## 第五章 安装与配置

### 5.1 系统要求

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 系统要求】

列出软件运行必需的先决条件，用列表形式（每项一行）：

- 操作系统：具体的版本要求
- 编程语言/运行时：版本号
- （可选）第三方依赖：可选安装项，附说明

⚠️ 避免：遗漏关键前提条件
✅ 要求：每项写清楚版本要求
════════════════════════════════════════════════════════════ -->

### 5.2 安装方式

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 安装方式】

提供完整的安装步骤说明（50-150字），包括：
1. 前提条件确认
2. 安装命令或步骤（pip / npm / mvn / 源码编译等）
3. 安装后验证

⚠️ 避免：给出与本项目无关的安装命令
✅ 要求：安装步骤应当真实可操作
════════════════════════════════════════════════════════════ -->

### 5.3 配置方法

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 配置方法】

说明软件的主要配置方式（80-200字）：
1. 配置文件位置和格式（JSON/YAML/TOML 等）
2. 核心配置项及其含义
3. 可选：配置示例

⚠️ 避免：编造不存在的配置文件路径
✅ 要求：配置项描述必须准确
════════════════════════════════════════════════════════════ -->

---

## 第六章 操作说明

### 6.1 操作模式概述

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 操作模式概述】

用一段话说明系统的操作模式（100-150字）：
- 用户通过什么方式与系统交互（GUI/CLI/API 等）
- 系统的工作流程和调用方式

⚠️ 避免：模糊描述
✅ 要求：写清楚交互方式
════════════════════════════════════════════════════════════ -->

### 6.2 操作示例

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 操作示例】

必须覆盖软件的各个功能模块，每个模块至少提供一个典型操作示例。

每个示例按以下结构展开：

**示例 N：示例标题**
操作描述："用户执行的操作原文或交互场景"

系统响应（版式强制：先用 ```mermaid 流程图展示整体调用链，然后每个步骤单独一段展开说明）：

✅ 格式（先图，再逐段说明）：
```mermaid
graph TD
    A[用户指令] --> B[系统响应]
    B --> C[处理步骤1]
    C --> D[处理步骤2]
    D --> E[返回结果]
```

每个步骤展开为独立段落，不要挤在一段，版式强制：
**步骤 1：步骤名称**
详细说明当前步骤的系统行为、调用方式和关键参数。

**步骤 2：步骤名称**
详细说明当前步骤的处理逻辑和中间结果。

**步骤 N：步骤名称**
详细说明最终返回结果和用户侧响应。

建议覆盖以下类别的示例（根据项目实际功能模块补充）：
1. 核心业务操作类（主要功能入口）
2. 数据查询/检索类（搜索、过滤、浏览）
3. 文件/数据操作类（导入、导出、编辑、保存）
4. 配置/诊断类（环境检测、系统设置）
5. 管理类（项目管理、用户管理、权限控制）
6. 辅助功能类（日志查看、帮助文档、系统更新）

⚠️ 避免：只覆盖核心功能，遗漏辅助性功能模块
⚠️ 避免：示例过于简单或一步完成
✅ 要求：每个示例包含完整的输入→处理→输出描述，覆盖软件的主要功能模块

📸 截图使用规则（重要）：
- 对于涉及图形界面操作或界面状态变化的示例，必须在步骤中嵌入截图
- ⚠️ 截图格式强制：图片必须独占一行，上下各留一个空行，与文字完全分开，绝不能让图片和文字在同一行
- ✅ 正确的截图排版格式（文字段落后空一行，图片后空一行再接说明）：
  ```
  步骤文字描述段落（描述当前步骤的操作内容）。

  ![图片说明](images/screenshot.jpg)

  *图片说明文字（用斜体描述截图内容）*
  ```
- ⚠️ 错误示例（禁止）：文字和图片挤在一行，或图片与说明文字之间缺少空行
  ```
  ❌ 错误的：步骤文字描述段落。![图片说明](path.jpg)*说明文字*
  ```
- 截图文件统一放到项目 docs/ 下的子目录中，markdown 中路径使用**相对于说明书 md 文件所在目录的相对路径**
- 获取截图的方法：
  a) 可使用自动化测试工具或UI脚本捕获界面截图
  b) 对于 Web 界面，可用浏览器开发者工具截取
  c) 每个截图文件名要描述步骤（如 01_main_interface.jpg、03_operation_result.jpg）
- 截图应展示关键步骤的界面状态，不是无意义的空界面
- 每个截图配一句斜体说明文字，与图片之间空一行，步骤描述与图片之间空一行
════════════════════════════════════════════════════════════ -->

---

## 第七章 测试与验收

### 7.1 测试方案

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 测试方案】

说明本软件的测试策略（80-150字）：
1. 使用的测试框架和测试语言
2. 测试范围（单元测试/集成测试/E2E）
3. 测试覆盖情况（{scan.get('test_files', 0)} 个测试文件）

⚠️ 避免：测试描述与项目实际情况不符
✅ 要求：使用实际扫描得到的数据
════════════════════════════════════════════════════════════ -->

### 7.2 验收标准

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 验收标准】

必须用表格列出至少 8 项验收标准，格式：
| 编号 | 验收项 | 验收标准 |
|------|--------|----------|

验收项应覆盖各功能模块（至少覆盖 3 个模块，每个模块至少 2 项）

⚠️ 避免：验收标准过于笼统（如"系统运行正常"）
✅ 要求：每项标准必须具体、可验证
════════════════════════════════════════════════════════════ -->

---


"""


def _generate_summary_draft(scan: dict) -> str:
    """生成申请信息汇总表草稿 markdown（通用基础模板，正文由 AI Agent 根据项目实际补充）。"""
    sw_name = _cfg_val('software_name', default='')
    sw_en = _cfg_val('software_name_en', default='')
    version = _cfg_val('version', default='')
    holder = _cfg_val('copyright_holder', default='')
    holder_en = _cfg_val('copyright_holder_en', default='')
    credit_code = _cfg_val('unified_social_credit_code', default='')
    contact = _cfg_val('contact_person', default='')
    phone = _cfg_val('contact_phone', default='')
    address = _cfg_val('contact_address', default='')
    completed_date = _cfg_val('completed_date', default='')

    total_py = scan['py_files']
    total_lines = scan['total_lines']
    test_count = scan.get('test_files', 0)

    # 模块摘要
    module_summary = []
    for module in sorted(scan['modules']):
        info = scan['modules'][module]
        module_summary.append(f'{module}/ {info["count"]} 文件/{info["lines"]} 行')
    module_text = '；'.join(module_summary)

    return f"""# 计算机软件著作权登记申请信息汇总表

## {sw_name}（{sw_en}）

---

## 一、软件基本信息表

| 字段 | 内容 |
|------|------|
| **软件中文全称** | {sw_name} |
| **软件英文全称** | {sw_en} |
| **软件简称** | <｜请填写软件简称，如与全称一致可留空> |
| **版本号** | {version} |
| **开发完成日期** | {completed_date} |
| **首次发表日期** | 未发表 |
| **软件分类** | <｜请填写分类，格式参考"应用软件 — XXX（YYYY-0000）"> |
| **编程语言** | <｜请填写实际编程语言及版本> |
| **源程序量** | {total_py} 个源文件（约 {total_lines:,} 行） |
| **主要功能** | <｜请用一句话概括软件的三大核心功能（50字以内）> |
| **运行环境** | <｜请填写操作系统及版本要求> |
| **硬件要求** | <｜请填写最低硬件配置要求> |
| **技术特点** | <｜请用 30 字以内概括主要技术特点，含 2-3 个关键技术术语> |

---

## 二、著作权人信息表

| 字段 | 内容 |
|------|------|
| **名称（中文）** | {holder} |
| **名称（英文）** | {holder_en} |
| **类型** | <｜企业法人 / 事业单位 / 自然人 / 其他，请选择> |
| **证件号（统一社会信用代码）** | {credit_code} |
| **联系人** | {contact} |
| **联系电话** | {phone} |
| **联系地址** | {address} |
| **国籍/地区** | 中国 |

---

## 三、软件功能与特点概述

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 功能与特点概述】

请扩展为完整的概述文字（总计 500-800 字）。

**项目规模**（必写）：
- 源文件数、测试文件数、总代码行数（使用下方骨架中的数据）

**核心功能**（必写，6-10条）：
每条用编号 1. 2. 3. ... 列出，格式：
1. **功能名称**：一句话说明功能 + 一句话说明实现方式或效果。
   必须覆盖扫描到的各模块的核心功能。

**技术特点**（必写，4-6条）：
每条用编号 1. 2. 3. ... 列出。
必须包含与项目实际技术栈相关的具体技术术语。

**应用场景**（必写，3-5条）：
每条用编号 1. 2. 3. ... 列出。
必须具体，描述使用本软件解决哪些实际问题。

⚠️ 避免：只有一句话的核心功能列表
⚠️ 避免：技术特点写成营销文案（如"业界领先""最先进的"）
✅ 要求：每个功能至少写2句话，技术特点必须包含具体技术术语
════════════════════════════════════════════════════════════ -->

{sw_name}（{sw_en}）是一款 <!-- 请用一句话描述软件类型和核心定位（30-50字） -->。

**项目规模：**
- 源文件：{total_py} 个源文件（{module_text}）
- 测试文件：{test_count} 个
- 总代码行数：约 {total_lines:,} 行

**核心功能：**

<!-- 请按生成要求扩展，每个功能 2 句以上，编号 1. 2. 3. ... -->

**技术特点：**

<!-- 请按生成要求扩展，4-6 条，包含具体技术术语 -->

**应用场景：**

<!-- 请按生成要求扩展，3-5 条，具体描述 -->

---

## 四、源程序与文档信息

| 项目 | 内容 |
|------|------|
| **源程序量** | {total_py} 个源文件，约 {total_lines:,} 行 |
| **源代码页数** | 建议 A4 纸前 30 页 + 后 30 页（共 60 页，每页 55 行） |
| **说明书页数** | 建议 15—30 页 |
| **测试用例** | {test_count} 个测试文件 |

---

## 五、提交材料清单

| 序号 | 材料名称 | 说明 |
|------|----------|------|
| 1 | 计算机软件著作权登记申请表 | 在线填写生成，需盖章扫描 |
| 2 | 软件源代码（前 30 页 + 后 30 页） | 每页至少 50 行 |
| 3 | 软件说明书（15—30 页） | 用户手册或设计说明书 |
| 4 | 营业执照复印件 | 申请人提交，加盖公章 |

---

## 六、在线申请填写指南

<!-- ════════════════════════════════════════════════════════════
【生成要求 — 在线申请填写指南】

必须提供中国版权保护中心在线申请的完整步骤说明，至少包含以下环节：
1. 注册与登录（官网 https://register.ccopyright.com.cn/）
2. 新建登记申请
3. 填写软件信息（软件名称、版本号、开发完成日期、分类号、编程语言、源程序量）
4. 填写著作权人信息
5. 上传材料
6. 提交与缴费

⚠️ 避免：省略关键步骤
✅ 要求：步骤完整可操作，软件名称/版本号等变量用真实数据填入

软件名称：{sw_name}
版本号：{version}
著作权人：{holder}
统一社会信用代码：{credit_code}
════════════════════════════════════════════════════════════ -->

---


"""


def _generate_content_drafts() -> dict:
    """扫描源码并生成说明书+汇总表的草稿 markdown 文件。"""
    print('扫描项目源码...')
    scan = _scan_project()
    if 'error' in scan:
        return {'status': 'error', 'message': scan['error']}

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # 生成说明书草稿
    manual_md = _generate_manual_draft(scan)
    manual_path = DOCS_DIR / _filename('manual', 'md')
    manual_path.write_text(manual_md, encoding='utf-8')
    manual_size = len(manual_md.encode('utf-8'))
    print(f'  → 说明书草稿: {manual_path.name} ({manual_size / 1024:.0f} KB)')

    # 生成汇总表草稿
    summary_md = _generate_summary_draft(scan)
    summary_path = DOCS_DIR / _filename('summary', 'md')
    summary_path.write_text(summary_md, encoding='utf-8')
    summary_size = len(summary_md.encode('utf-8'))
    print(f'  → 汇总表草稿: {summary_path.name} ({summary_size / 1024:.0f} KB)')

    # 模块信息供返回
    module_list = []
    for m in sorted(scan['modules']):
        info = scan['modules'][m]
        label = {'root': '入口', 'config': '配置', 'models': '数据模型',
                 'services': '业务逻辑', 'tools': '工具实现', 'utils': '工具类'}.get(m, m)
        module_list.append({'module': m, 'label': label, 'files': info['count'], 'lines': info['lines']})

    return {
        'status': 'ok',
        'message': '内容草稿生成完成。AI Agent 请读取上述两个 markdown 文件，为各章节补充正文内容后调用 generate 渲染 PDF。',
        'project_summary': {
            'total_py_files': scan['py_files'],
            'total_lines': scan['total_lines'],
            'modules': module_list,
            'test_files': scan.get('test_files', 0),
            'config_files': scan.get('config_files', []),
        },
        'generated_files': {
            'manual': str(manual_path),
            'summary': str(summary_path),
        },
        'workflow_tip': (
            '生成内容细化要求：\n'
            '1. 软件说明书（软件说明书-*.md）：每个章节的 <!-- 生成要求 --> 块内都标注了具体的内容要求和禁止事项，'
            '请严格按各节要求逐节生成正文内容。\n'
            '  - 第四章（模块详细设计）是审查重点，核心模块必须写最详细（篇幅为非核心模块的2-3倍）\n'
'  - 第六章（操作说明）：示例须覆盖软件的各功能模块，每个示例包含完整的输入→处理→输出\n'
'  - 第六章中涉及 UI 操作的示例必须嵌入截图：截图独占一行，上下空行隔开，说明文字另起一行用斜体，详见模板中 📸 截图使用规则\n'
            '  - 所有表格中的说明列必须10字以上\n'
            '  - 禁止使用 "随着XXX的发展" 等空洞套话\n'
            '  - 禁止使用 "业界领先""最先进的" 等营销用语\n'
            '  - 第三章（系统架构）推荐使用 ```mermaid 流程图展示分层架构（PDF 渲染已支持，服务端预渲染为 SVG）\n'
            '2. 申请信息汇总表（申请信息汇总表-*.md）：核心功能6-10条，技术特点4-6条，应用场景3-5条\n'
            '3. 全部正文补充完成后，调用 generate_copyright(action="generate") 渲染 PDF\n'
            '4. ⚠️ 免责声明：本文档由道飞/Daofy MCP 服务系统生成，结果仅为参考，请以实际人工审核为准。'
            '智同道合，相辅相成，请认真校对并提供修改意见后生成最终文档。'
        ),
    }


# ════════════════════════════════════════════════════
# 入口函数（供 MCP tool call）
# ════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# 文档审计 — 检查生成内容是否可能被驳回
# ═══════════════════════════════════════════════════════════════

# 软著申请驳回/补正常见原因（对应检查项编号）
_REJECTION_PATTERNS = {
    'placeholder': {
        'pattern': r'<!--.*?-->',
        'severity': '严重',
        'reason': '文档中存在未填充的占位符注释（<!-- ... -->），审查员会判定为内容不完整。',
        'suggestion': '将 <!-- ... --> 注释块替换为实际内容后删除注释标记。例如将 '
                      '`<!-- AI Agent: 请在此补充XXX -->` 替换为 XXX 的具体描述文字。',
    },
    'marketing_language': {
        'patterns': [
            r'业界领先',
            r'行业领先',
            r'最先进',
            r'国际领先',
            r'国内领先',
            r'领先水平',
            r'遥遥领先',
            r'领军[者位]',
            r'第一[位名]',
            r'首屈一指',
            r'独一无二',
            r'前所未有',
            r'填补空白',
            r'突破性',
            r'革命性',
            r'巨大[的]?[进突]',
            r'全球[第最]',
            r'唯一[的]?',
            r'超越训练数据边界',
            r'数据量最大',
            r'构建最复杂',
            r'全流程闭环',
            r'即可[以]?完成',
        ],
        'severity': '严重',
        'reason': '含有商业广告/营销宣传用语，软著申请文档应使用客观技术描述语言。',
        'suggestion': '将广告用语替换为客观技术描述。例如：'
                      '"业界领先" → "采用"；'
                      '"最先进" → "支持"；'
                      '"突破性" → "实现了"；'
                      '"唯一" → "提供"；'
                      '"巨大提升" → "优化了"。'
                      '修改后整句用平实的技术语言重写。',
    },
    'too_few_lines': {
        'min_lines_per_module': 50,
        'severity': '一般',
        'reason': '模块描述过于简略（少于50字），审查员可能认为文档内容不充实。',
        'suggestion': '为每个模块补充以下内容：① 该模块的核心职责（2-3句）；'
                      '② 包含的类/函数（举例说明）；③ 关键工作流程（分步骤描述）。'
                      '如果该模块内容确实较少，可合并到相邻模块中描述。',
    },
    'no_architecture_desc': {
        'pattern': r'(?:架构|体系结构)',
        'severity': '严重',
        'reason': '文档缺少系统架构描述。软著说明书必须包含架构说明。',
        'suggestion': '新增一个"系统架构"章节（建议放在第三章），内容包括：\n'
                      '  ① 系统的分层架构（如 MVC、五层等），每层的名称和职责\n'
                      '  ② 各层之间的依赖关系和通信方式\n'
                      '  ③ 核心数据流（用户请求从进入到返回的完整路径）\n'
                      '  ④ 可用表格列出各层包含的模块/组件',
    },
    'no_module_detail': {
        'pattern': r'模块详细设计|功能设计',
        'severity': '严重',
        'reason': '文档缺少模块详细设计章节。软著说明书必须包含各模块的详细功能设计说明。',
        'suggestion': '新增"模块详细设计"章节（建议放在第四章），对每个核心模块依次描述：\n'
                      '  ① 功能概述（该模块做什么，100-200字）\n'
                      '  ② 核心类/函数表格（名称、所属文件、职责）\n'
                      '  ③ 核心工作流程（先 mermaid 图，再逐段描述每个步骤）\n'
                      '  ④ 关键特性（列表，3条以上）\n'
                      '  覆盖的模块：编译模块、知识库模块、文件操作模块（至少3个）',
    },
    'no_operating_instructions': {
        'pattern': r'操作说明|使用说明|操作指南',
        'severity': '一般',
        'reason': '文档缺少操作说明章节。建议补充至少3个具体的操作示例。',
        'suggestion': '新增"操作说明"章节（建议放在第六章），提供至少3个具体示例。'
                      '每个示例按以下格式：\n'
                      '  **示例N：示例标题**\n'
                      '  用户提问："用户的问题原文"\n'
                      '  AI 助手调用：- 工具：xxx - 参数：action="..."\n'
                      '  返回结果示例：（文字描述）',
    },
    'empty_table_cell': {
        'pattern': r'\|\s*\|\s*\|',  # 空表格单元
        'severity': '严重',
        'reason': '表格中存在空白单元，说明内容未填写完整。',
        'suggestion': '找到空白表格单元并填入内容。如果该单元格确实无需填写，'
                      '删除该行或合并到相邻行。'
                      '注意检查表格的完整性，每行每列都应有内容。',
    },
    'pending_todo': {
        'pattern': r'(?:TODO|FIXME|TBD|待补充|待完善|请补充|AI\s*Agent)',
        'severity': '严重',
        'reason': '文档中包含未完成的标记（TODO/FIXME/待补充/AI Agent等），审查员会判定文档未完成。',
        'suggestion': '将 TODO/FIXME/TBD/待补充/AI Agent 等标记替换为实际内容后删除标记。'
                      '搜索文档中的上述关键词，逐处确认后替换为完整的内容描述。',
    },
    'copyright_violation_words': {
        'patterns': [
            r'版权所有',
            r'All Rights Reserved',
            r'专利[号申]',
            r'Patent',
        ],
        'severity': '一般',
        'reason': '文档中出现了"版权所有""专利"等敏感词。软著文档中建议仅在中注明著作权人信息，正文避免使用。',
        'suggestion': '正文中删除或替换这些词：\n'
                      '  "版权所有" → 仅保留在封面/页脚的著作权人信息中，正文删除\n'
                      '  "专利" → 如果软件确实有专利申请，需提供证明材料；'
                      '否则删除相关描述\n'
                      '  "All Rights Reserved" → 建议删除，中文软著文档使用中文即可',
    },
    'too_short_section': {
        'max_sections_below_100chars': 3,
        'severity': '一般',
        'reason': '存在多个内容过短的章节（少于100字），审查员可能认为文档内容不充实。',
        'suggestion': '将短章节（少于100字）扩充至300字以上，或合并到相邻章节中。'
                      '具体做法：① 补充具体的技术细节；② 增加示例；'
                      '③ 用表格列出相关内容。避免仅有一两句话的"空章节"。',
    },
}


def _check_section_count(text: str, heading: str) -> int:
    """统计指定标题下的字数（不含标题行本身）。"""
    lines = text.split('\n')
    in_section = False
    count = 0
    for line in lines:
        if line.strip().startswith('#') and heading in line:
            in_section = True
            count = 0
            continue
        if in_section:
            if line.strip().startswith('#') and line.strip()[0] == '#':
                # 遇到同级或更高级标题，结束
                heading_level = len(line.strip().split()[0])
                if heading_level <= heading.count('#') + 1:
                    in_section = False
                    continue
            count += len(line.strip())
    return count


def _strip_template_comments(text: str) -> str:
    """移除 <!-- 生成要求 --> 块，避免审计时误报注释内的文字。

    匹配以 ``<!-- ══`` 开头的 HTML 注释块，到下一个 ``-->`` 结束。
    注意不能要求结尾 ``═+`` 前缀，因为生成要求块中 ``═══`` 装饰行
    和 ``-->`` 可能不在同一行。
    """
    return re.sub(r'<!--\s*═+[\s\S]*?-->', '', text)


def _audit_markdown_file(file_path: Path, doc_type: str) -> dict:
    """审计单个 markdown 文件，返回检查结果。"""
    if not file_path.exists():
        return {
            'file': file_path.name,
            'type': doc_type,
            'status': 'ERROR',
            'checks': [],
            'warnings': ['文件不存在，无法审计。'],
        }

    raw_text = file_path.read_text(encoding='utf-8')
    # 正文 = 去掉 <!-- 生成要求 --> 注释块后的纯内容（用于检测营销用语等）
    text = _strip_template_comments(raw_text)
    lines = text.split('\n')
    checks = []
    warnings = []
    total_issues = 0

    def _check(key: str, **extra) -> dict:
        """从 _REJECTION_PATTERNS 构造检查结果，自动注入 suggestion。"""
        cfg = _REJECTION_PATTERNS[key]
        return {
            'id': key,
            'severity': cfg['severity'],
            'reason': cfg['reason'],
            'suggestion': cfg.get('suggestion', ''),
            'pass': False,
            **extra,
        }

    # ── 检查 1: 未填充的占位符 ──
    # 只检测 <!-- AI Agent: 等非生成要求的注释（去掉生成要求块后剩下的简单注释）
    placeholders = re.findall(r'<!--\s*.*?-->', text, re.DOTALL)
    real_placeholders = [p for p in placeholders if '生成要求' not in p and '══' not in p]
    if real_placeholders:
        checks.append(_check('placeholder',
            detail=f'发现 {len(real_placeholders)} 处未填充的占位符注释'))
        total_issues += 1

    # ── 检查 2: 营销用语 ──
    marketing_found = []
    for pat in _REJECTION_PATTERNS['marketing_language']['patterns']:
        matches = re.findall(pat, text)
        if matches:
            marketing_found.extend(matches)
    if marketing_found:
        checks.append(_check('marketing_language',
            detail=f'发现 {len(marketing_found)} 处营销用语: {", ".join(set(marketing_found))}'))
        total_issues += 1

    # ── 以下检查仅适用于说明书 ──
    if doc_type == 'manual':
        # 检查 4: 缺少架构描述
        if not re.search(_REJECTION_PATTERNS['no_architecture_desc']['pattern'], text, re.IGNORECASE):
            checks.append(_check('no_architecture_desc',
                detail='未找到"架构"或"体系结构"相关章节'))
            total_issues += 1

        # 检查 5: 缺少模块详细设计
        if not re.search(_REJECTION_PATTERNS['no_module_detail']['pattern'], text):
            checks.append(_check('no_module_detail',
                detail='未找到"模块详细设计"或"功能设计"章节'))
            total_issues += 1

        # 检查 6: 缺少操作说明
        if not re.search(_REJECTION_PATTERNS['no_operating_instructions']['pattern'], text):
            checks.append(_check('no_operating_instructions',
                detail='未找到"操作说明"或"使用说明"相关章节'))
            total_issues += 1

    # ── 检查 7: 空表格单元 ──
    empty_cells = re.findall(r'^\|\s*\|\s*\|', text, re.MULTILINE)
    if empty_cells:
        checks.append(_check('empty_table_cell',
            detail=f'发现 {len(empty_cells)} 处空白表格单元'))
        total_issues += 1

    # ── 检查 8: 待完成标记 ──
    todos = re.findall(_REJECTION_PATTERNS['pending_todo']['pattern'], text)
    if todos:
        checks.append(_check('pending_todo',
            detail=f'发现 {len(todos)} 处未完成的标记（TODO/TBD/待补充等）'))
        total_issues += 1

    # ── 检查 9: 敏感词 ──
    copyright_words = []
    for pat in _REJECTION_PATTERNS['copyright_violation_words']['patterns']:
        matches = re.findall(pat, text)
        if matches:
            copyright_words.extend(matches)
    if copyright_words:
        checks.append(_check('copyright_violation_words',
            detail=f'发现敏感词: {", ".join(set(copyright_words))}'))
        total_issues += 1

    # ── 检查 10: 章节过短 ──
    short_sections = []
    section_headings = re.findall(r'^#{2,3}\s+(.+?)$', text, re.MULTILINE)
    for h in section_headings:
        h_clean = h.strip()
        char_count = _check_section_count(text, h_clean)
        if char_count > 0 and char_count < 100:
            short_sections.append(f'"{h_clean}" ({char_count}字)')

    if len(short_sections) >= _REJECTION_PATTERNS['too_short_section']['max_sections_below_100chars']:
        checks.append(_check('too_short_section',
            detail=f'发现 {len(short_sections)} 个短章节（<100字）: {"; ".join(short_sections[:5])}'))
        total_issues += 1

    # ── 检查 11: 总页数估算 ──
    total_chars = len(text)
    estimated_pages = total_chars / 800  # 每页约800字（含表格、代码块）
    if doc_type == 'manual' and estimated_pages < 15:
        warnings.append({
            'type': 'page_count_too_low',
            'detail': f'说明书估算页数约 {estimated_pages:.0f} 页（{total_chars:,} 字），建议 15-30 页为宜。',
            'suggestion': '扩展以下章节来增加篇幅：\n'
                          '  ① 第四章（模块详细设计）：每个模块补充核心类/函数表格和工作流程步骤\n'
                          '  ② 第六章（操作说明）：增加示例数量，每个示例写清楚调用参数和返回结果\n'
                          '  ③ 第三章（系统架构）：用表格列出各层模块及其职责\n'
                          '  ④ 第一章（引言）：补充背景和目的的详细论述',
        })
    elif doc_type == 'manual' and estimated_pages > 50:
        warnings.append({
            'type': 'page_count_too_high',
            'detail': f'说明书估算页数约 {estimated_pages:.0f} 页，建议控制在 30 页以内。',
            'suggestion': '精简正文内容：\n'
                          '  ① 删除重复或啰嗦的描述\n'
                          '  ② 合并内容过少的子章节\n'
                          '  ③ 代码示例用省略号（...）截断非关键部分',
        })

    # ── 统计 ──
    severe = sum(1 for c in checks if c['severity'] == '严重' and not c['pass'])
    general = sum(1 for c in checks if c['severity'] == '一般' and not c['pass'])

    if severe == 0 and general == 0 and not warnings:
        status = 'PASS'
    elif severe > 0:
        status = 'FAIL'
    else:
        status = 'WARN'

    return {
        'file': file_path.name,
        'type': doc_type,
        'status': status,
        'total_chars': total_chars,
        'estimated_pages': round(estimated_pages),
        'checks': checks,
        'warnings': warnings,
        'summary': {
            'total': len(checks),
            'passed': sum(1 for c in checks if c.get('pass', True)),
            'failed': sum(1 for c in checks if not c.get('pass', True)),
            'severe': severe,
            'general': general,
        },
    }


def audit_generated_docs() -> dict:
    """审计已生成的 markdown 文档，检查可能被驳回的内容。"""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    # 审计说明书
    manual_path = DOCS_DIR / _filename('manual', 'md')
    results.append(_audit_markdown_file(manual_path, 'manual'))

    # 审计汇总表
    summary_path = DOCS_DIR / _filename('summary', 'md')
    results.append(_audit_markdown_file(summary_path, 'summary'))

    # 综合结论
    all_pass = all(r['status'] == 'PASS' for r in results)
    any_fail = any(r['status'] == 'FAIL' for r in results)

    if all_pass:
        verdict = '通过 ✅ — 文档内容检查通过，可以生成 PDF。'
    elif any_fail:
        severe_count = sum(r['summary']['severe'] for r in results)
        verdict = (
            f'存在 {severe_count} 项严重问题 ❌ — 建议修复后再生成 PDF，否则易被驳回/补正。'
        )
    else:
        verdict = (
            '存在一般性问题 ⚠️ — 建议选择性修复，不影响紧急提交但可能有补正风险。'
        )

    # ── 自动模式无法覆盖的检查项，提醒用户人工复查 ──
    manual_review_notes = [
        '📋 检查正文中是否存在自动化规则无法覆盖的夸张/营销表述（如"一键即可""无需任何操作"等语义级问题）',
        '📋 检查各章节的表格格式是否一致（列数、路径格式、术语风格等）',
        '📋 确认文档中的产品名称、公司名称、版本号、日期等信息的准确性',
        '📋 检查正文中是否引用了不存在的功能、组件或文件',
        '📋 检查模块详细设计中的核心类/函数名称是否与实际代码一致',
        '📋 确认操作示例中的调用参数和返回格式与实际行为一致',
    ]

    return {
        'status': 'audit_complete',
        'verdict': verdict,
        'disclaimer': '本文档由道飞/Daofy MCP 服务系统生成，结果仅为参考，请以实际人工审核为准。智同道合，相辅相成，请认真校对并提供修改意见后生成最终文档。',
        'manual_review_notes': manual_review_notes,
        'documents': results,
        'summary': {
            'total_docs': len(results),
            'passed': sum(1 for r in results if r['status'] == 'PASS'),
            'warned': sum(1 for r in results if r['status'] == 'WARN'),
            'failed': sum(1 for r in results if r['status'] == 'FAIL'),
        },
    }


def generate_copyright(action: str = 'generate',
                       doc_type: str = 'all',
                       output_dir: str = '',
                       config: dict = None,
                       **kwargs) -> dict:
    """著作权文档生成主入口。

    Args:
        action: 'generate' | 'validate' | 'update_config' | 'status' | 'list'
               | 'generate_content' | 'audit'
               - generate: 渲染 PDF
               - generate_content: 扫描源码生成 markdown 草稿（包含详细的生成要求注释）
               - audit: 审计已生成的 markdown 草稿，检查可能被驳回的内容
               - validate: 检查配置完整性
               - update_config: 更新配置
               - status: 环境状态检查
               - list: 列出已生成的文件
        doc_type: 'all' | 'source' | 'manual' | 'summary'
        output_dir: 输出目录，默认 docs/copyright
        config: [仅 update_config] 要更新的配置字典

    Returns:
        dict 包含结果。
    """
    # ── validate: 检查配置完整性 ──
    if action == 'validate':
        missing = _validate_config()
        result = {
            'complete': len(missing) == 0,
            'missing_fields': missing,
            'required_fields': list(REQUIRED_FIELDS.keys()),
            'current_config': {
                k: _cfg_val(k, default='')
                for k in REQUIRED_FIELDS
            },
        }
        if not result['complete']:
            result['hint'] = (
                '请使用 action="update_config" 补充缺失字段。'
                ' 例如: generate_copyright(action="update_config", config={"contact_person":"张三"})'
            )
        return result

    # ── update_config: 更新配置 ──
    if action == 'update_config':
        if not config or not isinstance(config, dict):
            return {'status': 'error', 'message': '缺少 config 参数，须传入 dict'}
        saved = _save_config(config)
        still_missing = _validate_config()
        return {
            'status': 'ok' if not still_missing else 'partial',
            'saved_fields': list(config.keys()),
            'still_missing': still_missing,
            'config': {
                k: _cfg_val(k, default='')
                for k in REQUIRED_FIELDS
            },
        }

    # ── status: 环境检查 ──
    if action == 'status':
        missing = _validate_config()
        status = {
            'browser': None,
            'mermaid_js': False,
            'config_complete': len(missing) == 0,
            'missing_fields': missing,
            'docs_exist': {},
        }
        try:
            browser = detect_browser()
            status['browser'] = browser
            status['browser_ok'] = True
        except RuntimeError as e:
            status['browser'] = str(e)
            status['browser_ok'] = False

        status['mermaid_js'] = MERMAID_JS_PATH.exists()
        status['config'] = {
            k: _cfg_val(k, default='')
            for k in REQUIRED_FIELDS
        }

        for f in [_filename('source', 'md'), _filename('manual', 'md'), _filename('summary', 'md')]:
            p = DOCS_DIR / f
            status['docs_exist'][f] = p.exists()

        return status

    # ── list: 列出已生成文件 ──
    if action == 'list':
        files = []
        if DOCS_DIR.exists():
            for f in sorted(DOCS_DIR.iterdir()):
                files.append({
                    'name': f.name,
                    'size': f.stat().st_size,
                    'modified': f.stat().st_mtime,
                })
        return {'files': files}

    # ── generate_content: 扫描源码 → 生成说明书+汇总表草稿 ──
    if action == 'generate_content':
        return _generate_content_drafts()

    # ── audit: 审计已生成的文档内容 ──
    if action == 'audit':
        return audit_generated_docs()

    if action != 'generate':
        return {'error': f'未知 action: {action}'}

    # ── generate: 生成前校验配置 ──
    missing = _validate_config()
    if missing:
        field_list = ', '.join(f'{m["label"]}({m["key"]})' for m in missing)
        return {
            'status': 'config_incomplete',
            'message': (
                f'以下必填字段为空，无法生成著作权文档：{field_list}。\n'
                '请先联系用户填写缺失信息，然后调用 action="update_config" 保存。\n'
                '示例：generate_copyright(action="update_config", config={'
                '"unified_social_credit_code": "912201...", '
                '"contact_person": "张三", '
                '"contact_phone": "13800138000", '
                '"contact_address": "吉林省长春市..."})'
            ),
            'missing_fields': missing,
        }

    # ── 正式生成 ──
    if output_dir:
        out = Path(output_dir)
    else:
        out = DOCS_DIR
    out.mkdir(parents=True, exist_ok=True)

    results = []

    # ── 源代码文档 ──
    if doc_type in ('all', 'source'):
        print('生成源代码文档...')
        try:
            html = generate_source_code_html()
            pdf_path = str(out / _filename('source', 'pdf'))
            ok, info = html_to_pdf(html, pdf_path)
            html_path = str(out / _filename('source', 'html'))
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
            results.append({
                'type': 'source',
                'pdf': pdf_path,
                'html': html_path,
                'status': 'OK' if ok else 'FAILED',
                'info': info,
            })
            print(f'  → {"OK" if ok else "FAILED"}: {info}')
        except Exception as e:
            results.append({'type': 'source', 'status': 'ERROR', 'info': str(e)})
            print(f'  → ERROR: {e}')

    # ── 软件说明书 ──
    if doc_type in ('all', 'manual'):
        md_name = _filename('manual', 'md')
        md_path = DOCS_DIR / md_name
        print(f'生成软件说明书 ({md_path.name})...')
        try:
            if not md_path.exists():
                raise FileNotFoundError(f'markdown 文件不存在: {md_path}')
            with open(str(md_path), 'r', encoding='utf-8') as f:
                content = f.read()
            html = md_to_html(content, base_dir=DOCS_DIR)
            pdf_path = str(out / _filename('manual', 'pdf'))
            ok, info = html_to_pdf(html, pdf_path)
            results.append({
                'type': 'manual',
                'pdf': pdf_path,
                'status': 'OK' if ok else 'FAILED',
                'info': info,
            })
            print(f'  → {"OK" if ok else "FAILED"}: {info}')
        except Exception as e:
            results.append({'type': 'manual', 'status': 'ERROR', 'info': str(e)})
            print(f'  → ERROR: {e}')

    # ── 申请信息汇总表 ──
    if doc_type in ('all', 'summary'):
        md_name = _filename('summary', 'md')
        md_path = DOCS_DIR / md_name
        print(f'生成申请信息汇总表 ({md_path.name})...')
        try:
            if not md_path.exists():
                raise FileNotFoundError(f'markdown 文件不存在: {md_path}')
            with open(str(md_path), 'r', encoding='utf-8') as f:
                content = f.read()
            html = md_to_html(content, base_dir=DOCS_DIR)
            pdf_path = str(out / _filename('summary', 'pdf'))
            ok, info = html_to_pdf(html, pdf_path)
            results.append({
                'type': 'summary',
                'pdf': pdf_path,
                'status': 'OK' if ok else 'FAILED',
                'info': info,
            })
            print(f'  → {"OK" if ok else "FAILED"}: {info}')
        except Exception as e:
            results.append({'type': 'summary', 'status': 'ERROR', 'info': str(e)})
            print(f'  → ERROR: {e}')

    all_ok = all(r.get('status') == 'OK' for r in results)
    return {
        'status': 'ok' if all_ok else 'partial',
        'results': results,
        'output_dir': str(out),
        'disclaimer': '本文档由道飞/Daofy MCP 服务系统生成，结果仅为参考，请以实际人工审核为准。'
                      '智同道合，相辅相成，请认真校对并提供修改意见后生成最终文档。',
    }
