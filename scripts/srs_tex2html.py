#!/usr/bin/env python3
"""Sinh docs/01-business/labelX.html từ nguồn LaTeX của SRS M13.

Chỉ hỗ trợ tập con LaTeX dùng trong docs/label-x_system-requirement-specification.
Hình TikZ được thay bằng sơ đồ Mermaid/SVG khai báo trong srs_figures.py.
Chạy: python3 scripts/srs_tex2html.py
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "label-x_system-requirement-specification"
OUT = ROOT / "docs" / "01-business" / "labelX.html"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from srs_figures import FIGURES  # noqa: E402

CHAPTER_FILES = [
    "01-introduction", "02-overview", "03-data-errors", "04-usecases", "05-dynamics",
    "06-functional", "07-evaluation", "08-nonfunctional", "09-interfaces",
    "10-architecture", "11-traceability", "12-appendix",
]


def strip_comments(s: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", s)


def find_group(s: str, i: int, open_c: str = "{", close_c: str = "}") -> tuple[str, int]:
    """s[i] == open_c; trả về nội dung và vị trí sau dấu đóng."""
    assert s[i] == open_c, (s[i:i + 40])
    depth = 0
    j = i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == open_c:
            depth += 1
        elif c == close_c:
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    raise ValueError("unbalanced group: " + s[i:i + 60])


# ---------------------------------------------------------------- numbering
class Numbers:
    def __init__(self) -> None:
        self.labels: dict[str, str] = {}
        self.anchor: dict[str, str] = {}


def collect_labels(chapters: list[tuple[str, str]]) -> Numbers:
    nums = Numbers()
    chap = 0
    appendix = False
    app_idx = 0
    for name, text in chapters:
        if name == "12-appendix":
            appendix = True
        sec = sub = 0
        tab = fig = eq = 0
        cur_anchor = ""
        chap_label = ""
        tokens = re.finditer(
            r"\\(chapter|section|subsection)(\*?)\{|\\label\{([^}]*)\}|\\caption\{|\\begin\{(equation)\}|\\begin\{(xltabular|figure)\}",
            text,
        )
        last_kind = None
        for m in tokens:
            if m.group(1):
                kind, star = m.group(1), m.group(2)
                if kind == "chapter":
                    if appendix:
                        app_idx += 1
                        chap_label = chr(ord("A") + app_idx - 1)
                    else:
                        chap += 1
                        chap_label = str(chap)
                    sec = sub = tab = fig = eq = 0
                    cur_anchor = f"ch-{chap_label}"
                    last_kind = ("chapter", chap_label, cur_anchor)
                elif kind == "section" and not star:
                    sec += 1
                    sub = 0
                    cur_anchor = f"s-{chap_label}-{sec}"
                    last_kind = ("section", f"{chap_label}.{sec}", cur_anchor)
                elif kind == "subsection":
                    if not star:
                        sub += 1
                        cur_anchor = f"s-{chap_label}-{sec}-{sub}"
                        last_kind = ("subsection", f"{chap_label}.{sec}.{sub}", cur_anchor)
                    else:
                        cur_anchor = f"s-{chap_label}-{sec}-x{m.start()}"
                        last_kind = ("subsection*", "", cur_anchor)
            elif m.group(4):
                eq += 1
                last_kind = ("equation", f"{chap_label}.{eq}", f"eq-{chap_label}-{eq}")
            elif m.group(5) == "xltabular":
                last_kind = ("table-pending", "", "")
            elif m.group(5) == "figure":
                last_kind = ("figure-pending", "", "")
            elif m.group(0).startswith("\\caption"):
                if last_kind and last_kind[0] == "table-pending":
                    tab += 1
                    last_kind = ("table", f"{chap_label}.{tab}", f"tab-{chap_label}-{tab}")
                elif last_kind and last_kind[0] == "figure-pending":
                    fig += 1
                    last_kind = ("figure", f"{chap_label}.{fig}", f"fig-{chap_label}-{fig}")
            elif m.group(3):
                if last_kind:
                    nums.labels[m.group(3)] = last_kind[1]
                    nums.anchor[m.group(3)] = last_kind[2]
    return nums


# ---------------------------------------------------------------- inline
SIMPLE_MACROS = {
    r"\must": '<span class="pri pri-m" title="Must">M</span>',
    r"\should": '<span class="pri pri-s" title="Should">S</span>',
    r"\could": '<span class="pri pri-c" title="Could">C</span>',
    r"\ldots": "…",
    r"\quad": " ",
    r"\qquad": "  ",
    r"\newline": "<br>",
    r"\par": "",
    r"\noindent": "",
    r"\centering": "",
    r"\bigskip": "",
    r"\medskip": "",
}


class Inline:
    def __init__(self, nums: Numbers) -> None:
        self.nums = nums

    def ref(self, label: str, eq: bool = False) -> str:
        n = self.nums.labels.get(label, "??")
        a = self.nums.anchor.get(label, "")
        text = f"({n})" if eq else n
        return f'<a href="#{a}">{text}</a>'

    def convert(self, s: str) -> str:
        out: list[str] = []
        i = 0
        while i < len(s):
            c = s[i]
            # math: giữ nguyên cho KaTeX
            if s.startswith("\\(", i):
                j = s.index("\\)", i)
                out.append(html.escape(s[i:j + 2], quote=False))
                i = j + 2
                continue
            if s.startswith("\\[", i):
                j = s.index("\\]", i)
                out.append(html.escape(s[i:j + 2], quote=False))
                i = j + 2
                continue
            if c == "$":
                j = s.index("$", i + 1)
                out.append(html.escape("\\(" + s[i + 1:j] + "\\)", quote=False))
                i = j + 1
                continue
            if c == "\\":
                m = re.match(r"\\([A-Za-z]+)\*?", s[i:])
                if not m:
                    nxt = s[i + 1] if i + 1 < len(s) else ""
                    if nxt == "\\":
                        out.append("<br>")
                        i += 2
                        if i < len(s) and s[i] == "[":
                            _, i = find_group(s, i, "[", "]")
                        continue
                    esc = {"%": "%", "&": "&amp;", "_": "_", "#": "#", "{": "{", "}": "}", "$": "$", ",": " ", " ": " "}
                    out.append(esc.get(nxt, nxt))
                    i += 2
                    continue
                name = m.group(1)
                full = "\\" + name
                i += m.end()
                if full in SIMPLE_MACROS:
                    out.append(SIMPLE_MACROS[full])
                    continue
                if name in ("textbf", "emph", "textit", "texttt", "code", "req", "term", "src",
                            "textcolor", "ref", "eqref", "url", "mbox", "text", "textsf", "underline",
                            "sffamily", "small", "footnotesize", "scriptsize", "normalsize", "bfseries",
                            "rmfamily", "large", "Large", "itshape"):
                    if name == "textcolor":
                        _, i = find_group(s, i)
                        arg, i = find_group(s, i)
                        out.append(self.convert(arg))
                        continue
                    if name in ("sffamily", "small", "footnotesize", "scriptsize", "normalsize",
                                "bfseries", "rmfamily", "large", "Large", "itshape"):
                        continue
                    arg, i = find_group(s, i)
                    if name in ("ref", "eqref"):
                        out.append(self.ref(arg, eq=(name == "eqref")))
                    elif name == "textbf":
                        out.append(f"<strong>{self.convert(arg)}</strong>")
                    elif name in ("emph", "textit", "term"):
                        out.append(f"<em>{self.convert(arg)}</em>")
                    elif name in ("texttt", "code"):
                        out.append(f"<code>{self.convert(arg)}</code>")
                    elif name == "req":
                        out.append(f'<code class="req">{self.convert(arg)}</code>')
                    elif name == "src":
                        out.append(f'<span class="src">[{self.convert(arg)}]</span>')
                    else:
                        out.append(self.convert(arg))
                    continue
                if name == "TBD":
                    tag = ""
                    if i < len(s) and s[i] == "[":
                        tag, i = find_group(s, i, "[", "]")
                    out.append(f'<span class="tbd">TBD{html.escape(tag)}</span>')
                    continue
                if name in ("hspace", "vspace", "label", "addcontentsline", "rule", "setcounter"):
                    while i < len(s) and s[i] in "*":
                        i += 1
                    while i < len(s) and s[i] == "{":
                        _, i = find_group(s, i)
                    continue
                if name == "multicolumn":
                    _, i = find_group(s, i)
                    _, i = find_group(s, i)
                    arg, i = find_group(s, i)
                    out.append(self.convert(arg))
                    continue
                if name in ("rightarrow", "Rightarrow", "ge", "le", "times", "ne", "geq", "leq"):
                    sym = {"rightarrow": "→", "Rightarrow": "⇒", "ge": "≥", "le": "≤", "geq": "≥",
                           "leq": "≤", "times": "×", "ne": "≠"}[name]
                    out.append(sym)
                    continue
                # macro không biết: bỏ tên, giữ đối số
                out.append("")
                continue
            if c == "{" or c == "}":
                i += 1
                continue
            if c == "~":
                out.append("&nbsp;")
                i += 1
                continue
            if s.startswith("``", i):
                out.append("“")
                i += 2
                continue
            if s.startswith("''", i):
                out.append("”")
                i += 2
                continue
            if s.startswith("---", i):
                out.append("—")
                i += 3
                continue
            if s.startswith("--", i):
                out.append("–")
                i += 2
                continue
            if c == "<":
                out.append("&lt;")
            elif c == ">":
                out.append("&gt;")
            elif c == "&":
                out.append("&amp;")
            else:
                out.append(c)
            i += 1
        return "".join(out)


# ---------------------------------------------------------------- blocks
class Converter:
    def __init__(self, nums: Numbers) -> None:
        self.nums = nums
        self.inl = Inline(nums)
        self.toc: list[tuple[int, str, str]] = []
        self.chap_label = ""
        self.sec = 0
        self.sub = 0
        self.tab = 0
        self.fig = 0
        self.eq = 0
        self.appendix_count = 0
        self.in_appendix = False

    # --- helpers
    def para(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        parts = re.split(r"\n\s*\n", text)
        res = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            m = re.match(r"\\paragraph\{", p)
            if m:
                head, k = find_group(p, len("\\paragraph"))
                rest = p[k:].strip()
                res.append(f"<p><strong>{self.inl.convert(head)}</strong> {self.inl.convert(rest)}</p>")
                continue
            if p.startswith("\\[") and p.endswith("\\]"):
                res.append(f'<div class="math">{html.escape(p, quote=False)}</div>')
                continue
            res.append(f"<p>{self.inl.convert(p)}</p>")
        return "\n".join(res)

    def env_body(self, s: str, i: int, name: str) -> tuple[str, int]:
        """i trỏ ngay sau \\begin{name}; trả về thân và vị trí sau \\end{name}."""
        depth = 1
        pat = re.compile(r"\\(begin|end)\{" + re.escape(name) + r"\}")
        for m in pat.finditer(s, i):
            if m.group(1) == "begin":
                depth += 1
            else:
                depth -= 1
                if depth == 0:
                    return s[i:m.start()], m.end()
        raise ValueError("unclosed env " + name)

    def lists(self, body: str, ordered: bool) -> str:
        body = re.sub(r"^\s*\[[^\]]*\]", "", body)
        items = re.split(r"\\item\b", body)
        tag = "ol" if ordered else "ul"
        lis = [f"<li>{self.blocks(it.strip(), inline_ok=True)}</li>" for it in items[1:]]
        return f"<{tag}>" + "".join(lis) + f"</{tag}>"

    def callout(self, kind: str, title: str, body: str) -> str:
        return (f'<div class="callout callout-{kind}"><div class="callout-title">{self.inl.convert(title)}</div>'
                f"{self.blocks(body)}</div>")

    def table(self, body: str) -> str:
        # bỏ spec cột
        body = body.lstrip()
        _, k = find_group(body, 0)  # width
        _, k = find_group(body, k)  # colspec
        body = body[k:]
        caption = ""
        anchor = ""
        mcap = re.search(r"\\caption\{", body)
        if mcap:
            cap, k2 = find_group(body, mcap.end() - 1)
            caption = cap
            body = body[:mcap.start()] + body[k2:]
        mlab = re.search(r"\\label\{([^}]*)\}", body)
        if mlab:
            anchor = self.nums.anchor.get(mlab.group(1), "")
            body = body[:mlab.start()] + body[mlab.end():]
        # bỏ phần head lặp và các dòng foot của longtable
        if "\\endfirsthead" in body:
            first, rest = body.split("\\endfirsthead", 1)
            if "\\endhead" in rest:
                rest = rest.split("\\endhead", 1)[1]
            for tok in ("\\endlastfoot", "\\endfoot"):
                if tok in rest:
                    rest = rest.split(tok, 1)[1]
                    break
            body = first + "\\ENDHEADMARK" + rest
        body = body.replace("\\endfoot", "")
        for t in ("\\toprule", "\\bottomrule"):
            body = body.replace(t, "")
        head_rows: list[str] = []
        if "\\ENDHEADMARK" in body:
            head_part, body = body.split("\\ENDHEADMARK", 1)
            head_part = head_part.replace("\\midrule", "")
            head_rows = [r for r in self.split_rows(head_part) if r.strip()]
        elif "\\midrule" in body:
            head_part, body = body.split("\\midrule", 1)
            head_rows = [r for r in self.split_rows(head_part) if r.strip()]
        body = body.replace("\\midrule", "")
        rows = [r for r in self.split_rows(body) if r.strip()]
        h = []
        if caption:
            num = self.nums.labels.get(mlab.group(1), "") if mlab else ""
            h.append(f'<caption><span class="capnum">Bảng {num}.</span> {self.inl.convert(caption)}</caption>')
        if head_rows:
            h.append("<thead>")
            for r in head_rows:
                h.append("<tr>" + "".join(f"<th>{self.inl.convert(c.strip())}</th>" for c in self.split_cells(r)) + "</tr>")
            h.append("</thead>")
        h.append("<tbody>")
        for r in rows:
            cells = self.split_cells(r)
            if len(cells) == 1 and "\\multicolumn" in r:
                k0 = r.index("\\multicolumn") + len("\\multicolumn")
                n, k0 = find_group(r, r.index("{", k0))
                _, k0 = find_group(r, r.index("{", k0))
                g, _ = find_group(r, r.index("{", k0))
                h.append(f'<tr class="grouprow"><td colspan="{n}">{self.inl.convert(g)}</td></tr>')
                continue
            h.append("<tr>" + "".join(f"<td>{self.blocks(c.strip(), inline_ok=True)}</td>" for c in cells) + "</tr>")
        h.append("</tbody>")
        idattr = f' id="{anchor}"' if anchor else ""
        cls = "" if head_rows else ' class="kv"'
        return f'<div class="tablewrap"><table{idattr}{cls}>' + "".join(h) + "</table></div>"

    @staticmethod
    def split_rows(s: str) -> list[str]:
        rows, depth, cur, i = [], 0, [], 0
        while i < len(s):
            c = s[i]
            if c == "\\" and i + 1 < len(s) and s[i + 1] == "\\" and depth == 0:
                rows.append("".join(cur))
                cur = []
                i += 2
                continue
            if c == "\\":
                cur.append(s[i:i + 2])
                i += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            cur.append(c)
            i += 1
        rows.append("".join(cur))
        # gộp dòng bị cắt nhầm trong môi trường enumerate (không xảy ra nhờ depth) — giữ nguyên
        return rows

    @staticmethod
    def split_cells(row: str) -> list[str]:
        cells, depth, cur, i = [], 0, [], 0
        env_depth = 0
        while i < len(row):
            c = row[i]
            if row.startswith("\\begin{", i):
                env_depth += 1
            if row.startswith("\\end{", i):
                env_depth -= 1
            if c == "\\":
                cur.append(row[i:i + 2])
                i += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            if c == "&" and depth == 0 and env_depth == 0:
                cells.append("".join(cur))
                cur = []
                i += 1
                continue
            cur.append(c)
            i += 1
        cells.append("".join(cur))
        return cells

    def figure(self, body: str) -> str:
        mlab = re.search(r"\\label\{([^}]*)\}", body)
        label = mlab.group(1) if mlab else ""
        mcap = re.search(r"\\caption\{", body)
        cap = find_group(body, mcap.end() - 1)[0] if mcap else ""
        num = self.nums.labels.get(label, "")
        anchor = self.nums.anchor.get(label, "")
        fig = FIGURES.get(label)
        if fig is None:
            raise KeyError("thiếu hình cho nhãn " + label)
        return (f'<figure id="{anchor}">{fig}<figcaption><span class="capnum">Hình {num}.</span> '
                f"{self.inl.convert(cap)}</figcaption></figure>")

    def blocks(self, s: str, inline_ok: bool = False) -> str:
        """Chuyển một đoạn có thể chứa môi trường."""
        out: list[str] = []
        pos = 0
        pat = re.compile(
            r"\\begin\{(itemize|enumerate|xltabular|notebox|decisionbox|tbdbox|figure|center|equation|tcolorbox)\}"
            r"|\\(chapter|section|subsection)(\*?)\{"
        )
        while True:
            m = pat.search(s, pos)
            if not m:
                break
            pre = s[pos:m.start()]
            out.append(self.inline_or_para(pre, inline_ok))
            if m.group(1):
                name = m.group(1)
                body, end = self.env_body(s, m.end(), name)
                if name in ("itemize", "enumerate"):
                    out.append(self.lists(body, name == "enumerate"))
                elif name == "xltabular":
                    out.append(self.table(body))
                elif name in ("notebox", "decisionbox", "tbdbox"):
                    title = {"notebox": "Ghi chú", "decisionbox": "Quyết định đã chốt",
                             "tbdbox": "Chưa chốt — cần quyết định"}[name]
                    b = body
                    if b.startswith("["):
                        title, k = find_group(b, 0, "[", "]")
                        b = b[k:]
                    kind = {"notebox": "note", "decisionbox": "ok", "tbdbox": "tbd"}[name]
                    out.append(self.callout(kind, title, b))
                elif name == "figure":
                    out.append(self.figure(body))
                elif name == "center":
                    out.append(FIGURES["scopeflow"])
                elif name == "equation":
                    mlab = re.search(r"\\label\{([^}]*)\}", body)
                    lab = mlab.group(1) if mlab else ""
                    body2 = re.sub(r"\\label\{[^}]*\}", "", body).strip()
                    num = self.nums.labels.get(lab, "")
                    anc = self.nums.anchor.get(lab, "")
                    out.append(f'<div class="math eq" id="{anc}">\\[{html.escape(body2, quote=False)}\\]'
                               f'<span class="eqnum">({num})</span></div>')
                elif name == "tcolorbox":
                    out.append(self.callout("note", "", re.sub(r"^\[[^\]]*\]", "", body)))
                pos = end
            else:
                kind, star = m.group(2), m.group(3)
                title, k = find_group(s, m.end() - 1)
                pos = k
                mlab = re.match(r"\s*\\label\{([^}]*)\}", s[pos:])
                label = None
                if mlab:
                    label = mlab.group(1)
                    pos += mlab.end()
                out.append(self.heading(kind, star, title, label))
        out.append(self.inline_or_para(s[pos:], inline_ok))
        return "\n".join(x for x in out if x)

    def inline_or_para(self, text: str, inline_ok: bool) -> str:
        if not text.strip():
            return ""
        if inline_ok and not re.search(r"\n\s*\n", text.strip()):
            return self.inl.convert(text.strip())
        return self.para(text)

    def heading(self, kind: str, star: str, title: str, label: str | None) -> str:
        t = self.inl.convert(title)
        if kind == "chapter":
            if self.in_appendix:
                self.appendix_count += 1
                self.chap_label = chr(ord("A") + self.appendix_count - 1)
                prefix = f"Phụ lục {self.chap_label}"
            else:
                self.chap_label = str(int(self.chap_label) + 1) if self.chap_label.isdigit() else "1"
                prefix = f"{self.chap_label}"
            self.sec = self.sub = 0
            anchor = f"ch-{self.chap_label}"
            self.toc.append((1, anchor, f"{prefix} · {t}"))
            return f'<h2 id="{anchor}"><span class="num">{prefix}</span>{t}</h2>'
        if kind == "section":
            if star:
                return f"<h3>{t}</h3>"
            self.sec += 1
            self.sub = 0
            anchor = f"s-{self.chap_label}-{self.sec}"
            n = f"{self.chap_label}.{self.sec}"
            self.toc.append((2, anchor, f"{n} {t}"))
            return f'<h3 id="{anchor}"><span class="num">{n}</span>{t}</h3>'
        if star:
            return f"<h4>{t}</h4>"
        self.sub += 1
        anchor = f"s-{self.chap_label}-{self.sec}-{self.sub}"
        return f'<h4 id="{anchor}"><span class="num">{self.chap_label}.{self.sec}.{self.sub}</span>{t}</h4>'


def main() -> None:
    chapters = []
    for name in CHAPTER_FILES:
        text = strip_comments((SRC / "sections" / f"{name}.tex").read_text(encoding="utf-8"))
        chapters.append((name, text))
    nums = collect_labels(chapters)
    conv = Converter(nums)
    body_parts = []
    for name, text in chapters:
        if name == "12-appendix":
            conv.in_appendix = True
        body_parts.append(f'<section class="chapter">{conv.blocks(text)}</section>')
    front = (SRC / "sections" / "00-frontmatter.tex").read_text(encoding="utf-8")
    front_html = build_front(conv, strip_comments(front))
    toc = build_toc(conv.toc)
    template = (Path(__file__).resolve().parent / "srs_template.html").read_text(encoding="utf-8")
    page = (template.replace("{{TOC}}", toc).replace("{{FRONT}}", front_html)
            .replace("{{BODY}}", "\n".join(body_parts)))
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(page)//1024} KiB)")


def build_front(conv: Converter, front: str) -> str:
    # lấy các bảng sau titlepage: lịch sử phiên bản, phê duyệt, nguồn
    after = front.split("\\end{titlepage}", 1)[1]
    after = after.split("\\tableofcontents", 1)[0]
    after = re.sub(r"\\(pagenumbering|setcounter)\{[^}]*\}(\{[^}]*\})?", "", after)
    after = re.sub(r"\\addcontentsline\{[^}]*\}\{[^}]*\}\{[^}]*\}", "", after)
    after = after.replace("\\chapter*{", "\\section*{")
    return f'<section class="chapter front">{conv.blocks(after)}</section>'


def build_toc(items: list[tuple[int, str, str]]) -> str:
    out = ['<nav class="toc" aria-label="Mục lục"><div class="toc-title">Mục lục</div><ol>']
    open_sub = False
    for level, anchor, text in items:
        if level == 1:
            if open_sub:
                out.append("</ol></li>")
                open_sub = False
            out.append(f'<li><a href="#{anchor}">{text}</a><ol>')
            open_sub = True
        else:
            out.append(f'<li><a href="#{anchor}">{text}</a></li>')
    if open_sub:
        out.append("</ol></li>")
    out.append("</ol></nav>")
    return "".join(out)


if __name__ == "__main__":
    main()
