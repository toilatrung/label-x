#!/usr/bin/env python3
"""Sinh bản HTML cho tài liệu Markdown của LabelX (docs/ và .agent/).

Markdown vẫn là nguồn (kit yêu cầu frontmatter và validate-framework.py kiểm .md);
mỗi foo.md sinh foo.html cạnh nó, link *.md đổi thành *.html, khối ```mermaid được vẽ.

Chạy:
  uv run --no-project --with markdown --with pymdown-extensions python scripts/md2html.py docs .agent
  ... python scripts/md2html.py --check docs .agent   # thoát 1 nếu có HTML thiếu/cũ
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"node_modules", ".venv", "__pycache__", ".git"}
GENERATED_MARK = "<!-- generated-by: scripts/md2html.py -->"
# validate-framework.py (RUNTIME_FILE_INVALID) chỉ cho phép .md/.keep trong hai thư mục runtime này:
# không sinh HTML ở đó và giữ nguyên link .md trỏ tới chúng (GitHub vẫn render .md).
MD_ONLY_DIRS = (ROOT / ".agent" / "governance", ROOT / ".agent" / "reports")


def md_only(path: Path) -> bool:
    resolved = path.resolve()
    return any(resolved.is_relative_to(d) for d in MD_ONLY_DIRS)

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
{mark}
<!-- Nguồn: {src}. Không sửa tay; sửa Markdown rồi chạy lại scripts/md2html.py. -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"
 onload="renderMathInElement(document.querySelector('article'),{{delimiters:[{{left:'$$',right:'$$',display:true}},{{left:'$',right:'$',display:false}}],ignoredTags:['script','noscript','style','textarea','pre','code'],throwOnError:false}})"></script>
<script type="module">import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
mermaid.initialize({{startOnLoad:true,securityLevel:"strict",theme:"neutral"}});</script>
<style>{css}</style></head>
<body><header class="top"><span class="logo">Label<b>X</b></span><span>{crumbs}</span><span class="sp"></span>
<a href="{md_name}">Nguồn Markdown</a></header>
<main><article>
{meta}
{body}
</article></main></body></html>
"""


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if lines and lines[0] == "---":
        try:
            end = lines.index("---", 1)
        except ValueError:
            return {}, text
        meta = {}
        for line in lines[1:end]:
            m = re.match(r"^([a-z][a-z0-9-]*):\s*(.*?)\s*$", line)
            if m:
                meta[m.group(1)] = m.group(2)
        return meta, "\n".join(lines[end + 1:])
    return {}, text


def mermaid_format(source, language, css_class, options, md, **kwargs):  # noqa: ANN001
    return '<pre class="mermaid">' + html.escape(source, quote=False) + "</pre>"


def rewrite_links(body: str, src: Path) -> str:
    def fix(m: re.Match[str]) -> str:
        attr, target = m.group(1), m.group(2)
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            return m.group(0)
        path, sep, anchor = target.partition("#")
        if path.endswith(".md") and (src.parent / path).exists() and not md_only(src.parent / path):
            return f'{attr}="{path[:-3]}.html{sep}{anchor}"'
        if path.endswith("/") and (src.parent / path / "index.md").exists():
            return f'{attr}="{path}index.html{sep}{anchor}"'
        return m.group(0)

    return re.sub(r'(href)="([^"]+)"', fix, body)


def render(src: Path) -> str:
    text = src.read_text(encoding="utf-8-sig")
    meta, body_md = split_frontmatter(text)
    md = markdown.Markdown(
        extensions=["tables", "toc", "sane_lists", "attr_list", "def_list", "pymdownx.highlight",
                    "pymdownx.superfences", "pymdownx.tilde"],
        extension_configs={
            # Không dùng Pygments dù có cài: đầu ra phải giống nhau trên máy dev và runner CI.
            "pymdownx.highlight": {"use_pygments": False},
            "pymdownx.superfences": {"custom_fences": [
                {"name": "mermaid", "class": "mermaid", "format": mermaid_format}]},
        },
    )
    body = rewrite_links(md.convert(body_md), src)
    title = meta.get("title") or src.stem
    meta_html = ""
    if meta:
        rows = "".join(f"<b>{html.escape(k)}</b><span>{html.escape(v)}</span>" for k, v in meta.items())
        meta_html = f'<div class="meta">{rows}</div>'
    rel = src.resolve().relative_to(ROOT)
    parts = rel.parts
    crumbs = " / ".join(html.escape(p) for p in parts[:-1] + (src.stem,))
    return HEAD.format(title=html.escape(title), mark=GENERATED_MARK, src=rel.as_posix(), css=CSS,
                       crumbs=crumbs, md_name=html.escape(src.name), meta=meta_html, body=body)


def iter_md(paths: list[Path]):
    for p in paths:
        if p.is_file() and p.suffix == ".md" and not md_only(p):
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*.md")):
                if not any(part in SKIP_DIRS for part in f.parts) and not md_only(f):
                    yield f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--check", action="store_true", help="không ghi; báo lỗi nếu HTML thiếu hoặc cũ")
    args = ap.parse_args()
    stale = []
    count = 0
    for src in iter_md([Path(p) for p in args.paths]):
        out = src.with_suffix(".html")
        new = render(src)
        count += 1
        if out.exists():
            old = out.read_text(encoding="utf-8")
            if GENERATED_MARK not in old:
                print(f"BỎ QUA {out}: đã có HTML không do script sinh", file=sys.stderr)
                continue
            if old == new:
                continue
        if args.check:
            stale.append(str(out))
        else:
            out.write_text(new, encoding="utf-8")
    if args.check and stale:
        print("HTML thiếu hoặc cũ, chạy lại scripts/md2html.py:\n  " + "\n  ".join(stale), file=sys.stderr)
        return 1
    print(f"{'checked' if args.check else 'rendered'} {count} markdown files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
