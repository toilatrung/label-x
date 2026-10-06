"""Định dạng HTML của tài liệu LabelX (docs/, .agent/, AGENT.html) — CR-103.

HTML là nguồn duy nhất. Metadata của kit nằm trong <head>:
    <meta name="labelx:id" content="..."> (id, title, type, domain, module, tags, priority)
Cấu trúc thân giữ quy ước của kit: <h2> là heading ổn định, <li><strong>Field</strong>: <code>giá trị</code></li>
là trường, bảng <table> là bản ghi.

- render_document(meta, body_markdown, path): dựng trang HTML (dùng cho bộ sinh từ SRS LaTeX).
- page(meta, body_html, path): bọc thân HTML có sẵn thành trang đầy đủ.
- read_document(path): đọc HTML → (metadata, văn bản dạng kit, danh sách link) cho validate-framework.py.
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
META_PREFIX = "labelx:"
META_KEYS = ("id", "title", "type", "domain", "module", "tags", "priority")

CSS = """
:root{--canvas:#f6f7f9;--surface:#fff;--sunken:#f3f4f6;--selected:#eef1f5;--border:#e3e6ea;
--ink:#1a1d23;--muted:#4b5262;--subtle:#6b7280;--primary:#1f2933;--brand:#d1202d;--info:#1d5ea8;
--warn:#8a5300;--warn-soft:#fdf2d8;--neutral-soft:#eceef2;
--font:Inter,"Segoe UI",system-ui,-apple-system,sans-serif;--mono:"JetBrains Mono",ui-monospace,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--canvas);color:var(--ink);font:15px/1.6 var(--font)}
.top{position:sticky;top:0;z-index:5;height:48px;background:var(--primary);color:#fff;display:flex;align-items:center;
gap:14px;padding:0 24px;font-size:13px}.logo{font-weight:800;font-size:17px}.logo b{color:var(--brand)}
.top a{color:#cfd4dc;text-decoration:none}.top a:hover{color:#fff}.top .sp{flex:1}
main{max-width:1100px;margin:24px auto;padding:0 24px 64px}
article{background:var(--surface);border:1px solid var(--border);padding:8px 32px 28px}
.meta{display:grid;grid-template-columns:120px 1fr;gap:2px 12px;font-size:12.5px;color:var(--subtle);
border:1px solid var(--border);background:var(--sunken);padding:8px 12px;margin:16px 0}
.meta b{color:var(--muted);font-weight:600}
h1{font-size:24px;line-height:1.25;margin:20px 0 12px}h2{font-size:19px;margin:28px 0 8px;padding-bottom:6px;
border-bottom:1px solid var(--border)}h3{font-size:16px;margin:22px 0 6px}h4{font-size:15px}
a{color:var(--info)}code{font-family:var(--mono);font-size:.86em;background:var(--sunken);padding:1px 4px}
pre{background:var(--sunken);border:1px solid var(--border);padding:10px 12px;overflow:auto}pre code{background:none;padding:0}
table{border-collapse:collapse;width:100%;font-size:13.5px;margin:12px 0;display:block;overflow-x:auto}
th{background:var(--sunken);text-align:left;font-size:12px;text-transform:uppercase;color:var(--subtle);font-weight:600}
th,td{border:1px solid var(--border);padding:6px 8px;vertical-align:top}
blockquote{margin:12px 0;padding:8px 14px;border-left:3px solid var(--warn);background:var(--warn-soft)}
pre.mermaid{background:var(--surface);text-align:center;border:1px solid var(--border)}
.toc{font-size:13px;border:1px solid var(--border);padding:8px 14px;margin:12px 0}
.toc ul{margin:2px 0;padding-left:18px}
ul.dir{columns:2;font-size:14px}
@media print{.top{display:none}article{border:0}}
"""

HEAD = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — LabelX</title>
{metatags}
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"
 onload="renderMathInElement(document.querySelector('article'),{{delimiters:[{{left:'$$',right:'$$',display:true}},{{left:'$',right:'$',display:false}}],ignoredTags:['script','noscript','style','textarea','pre','code'],throwOnError:false}})"></script>
<script type="module">import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
mermaid.initialize({{startOnLoad:true,securityLevel:"strict",theme:"neutral"}});</script>
<style>{css}</style></head>
<body><header class="top"><span class="logo">Label<b>X</b></span><span>{crumbs}</span><span class="sp"></span></header>
<main><article>
{meta}
{body}
</article></main></body></html>
"""


def page(meta: dict[str, str], body_html: str, path: Path) -> str:
    """Bọc thân HTML thành trang đầy đủ, metadata đặt trong <head> và hiển thị ở đầu bài."""
    title = meta.get("title") or path.stem
    metatags = "\n".join(
        f'<meta name="{META_PREFIX}{html.escape(k)}" content="{html.escape(v, quote=True)}">' for k, v in meta.items())
    rows = "".join(f"<b>{html.escape(k)}</b><span>{html.escape(v)}</span>" for k, v in meta.items())
    meta_html = f'<div class="meta">{rows}</div>' if meta else ""
    try:
        rel = path.resolve().relative_to(ROOT)
        crumbs = " / ".join(html.escape(p) for p in rel.parts[:-1] + (path.stem,))
    except ValueError:
        crumbs = html.escape(path.stem)
    return HEAD.format(title=html.escape(title), metatags=metatags, css=CSS, crumbs=crumbs, meta=meta_html,
                       body=body_html)


def _mermaid_format(source, language, css_class, options, md, **kwargs):  # noqa: ANN001
    return '<pre class="mermaid">' + html.escape(source, quote=False) + "</pre>"


def markdown_to_html(body_md: str) -> str:
    import markdown  # chỉ cần khi dựng từ Markdown (bộ sinh SRS)

    md = markdown.Markdown(
        extensions=["tables", "toc", "sane_lists", "attr_list", "def_list", "pymdownx.highlight",
                    "pymdownx.superfences", "pymdownx.tilde"],
        extension_configs={
            # Không dùng Pygments: đầu ra phải giống nhau trên máy dev và runner CI.
            "pymdownx.highlight": {"use_pygments": False},
            "pymdownx.superfences": {"custom_fences": [
                {"name": "mermaid", "class": "mermaid", "format": _mermaid_format}]},
        },
    )
    return md.convert(body_md)


def render_document(meta: dict[str, str], body_md: str, path: Path) -> str:
    return page(meta, markdown_to_html(body_md), path)


class _KitText(HTMLParser):
    """Chuyển thân HTML thành văn bản theo quy ước kit (## heading, - **Field**: `v`, | bảng |)."""

    BLOCK = {"p", "div", "pre", "blockquote", "ul", "ol", "table", "section", "article", "br"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.links: list[str] = []
        self.lines: list[str] = []
        self.buf: list[str] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.skip = 0
        self.in_body = False
        self.in_meta_div = 0

    def _out(self) -> list[str]:
        return self.cell if self.cell is not None else self.buf

    def _flush(self) -> None:
        text = "".join(self.buf).strip()
        if text:
            self.lines.extend(text.splitlines())
        self.buf = []

    def handle_starttag(self, tag, attrs):  # noqa: ANN001
        a = dict(attrs)
        if tag == "meta" and (a.get("name") or "").startswith(META_PREFIX):
            self.meta[a["name"][len(META_PREFIX):]] = a.get("content") or ""
            return
        if tag in ("script", "style", "title", "header"):
            self.skip += 1
            return
        if tag == "article":
            self.in_body = True
        if self.skip or not self.in_body:
            return
        if tag == "div" and "meta" in (a.get("class") or "").split():
            self.in_meta_div += 1
            return
        if self.in_meta_div:
            if tag == "div":
                self.in_meta_div += 1
            return
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush()
            self.buf.append("#" * int(tag[1]) + " ")
        elif tag == "li":
            self._flush()
            self.buf.append("- ")
        elif tag == "tr":
            self._flush()
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
        elif tag in ("strong", "b"):
            self._out().append("**")
        elif tag == "code":
            self._out().append("`")
        elif tag in self.BLOCK:
            self._flush()

    def handle_endtag(self, tag):  # noqa: ANN001
        if tag in ("script", "style", "title", "header"):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or not self.in_body:
            return
        if self.in_meta_div:
            if tag == "div":
                self.in_meta_div -= 1
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "li"):
            self._flush()
        elif tag in ("td", "th"):
            if self.row is not None and self.cell is not None:
                self.row.append("".join(self.cell).strip().replace("\n", " "))
            self.cell = None
        elif tag == "tr":
            if self.row is not None:
                self.lines.append("| " + " | ".join(self.row) + " |")
            self.row = None
        elif tag in ("strong", "b"):
            self._out().append("**")
        elif tag == "code":
            self._out().append("`")
        elif tag in self.BLOCK:
            self._flush()
        elif tag == "article":
            self._flush()
            self.in_body = False

    def handle_data(self, data):  # noqa: ANN001
        if self.skip or not self.in_body or self.in_meta_div:
            return
        out = self._out()
        if self.cell is not None:
            out.append(" ".join(data.split()) if data.strip() else " ")
        else:
            out.append(data)


def read_document(path: Path) -> tuple[dict[str, str], str, list[str]]:
    parser = _KitText()
    parser.feed(path.read_text(encoding="utf-8-sig"))
    parser.close()
    parser._flush()
    text = "\n".join(re.sub(r"[ \t]+$", "", line) for line in parser.lines)
    return parser.meta, text, parser.links
