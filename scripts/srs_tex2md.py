#!/usr/bin/env python3
"""Sinh tài liệu Markdown tra cứu từ SRS LaTeX (docs/label-x_system-requirement-specification).

Ghi: docs/01-business/{requirements,use-cases,domain-model}.md, docs/00-project/{glossary,stakeholders}.md.
Chạy: python3 scripts/srs_tex2md.py  (sau đó chạy scripts/md2html.py để cập nhật HTML).
Không sửa tay các file trên; sửa LaTeX rồi chạy lại.
"""
import re, sys, json, os
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1])
sys.path.insert(0,str(Path(__file__).resolve().parent))
from srs_tex2html import Converter, collect_labels, strip_comments, SRC, CHAPTER_FILES, find_group
def tex(name): return strip_comments((SRC/'sections'/f'{name}.tex').read_text())
def md(s):
    s=re.sub(r'\\req\{([^}]*)\}',r'`\1`',s)
    s=re.sub(r'\\(code|texttt)\{((?:[^{}]|\{[^{}]*\})*)\}',r'`\2`',s)
    s=re.sub(r'\\TBD\[([^\]]*)\]',r'TBD\1',s); s=s.replace('\\TBD{}','TBD')
    s=re.sub(r'\\textbf\{((?:[^{}]|\{[^{}]*\})*)\}',r'**\1**',s)
    s=re.sub(r'\\(emph|term)\{((?:[^{}]|\{[^{}]*\})*)\}',r'*\2*',s)
    s=s.replace('\\must','M').replace('\\should','S').replace('\\could','C')
    s=re.sub(r'\$\\rightarrow\$','→',s); s=re.sub(r'\$\\ge\$','≥',s); s=re.sub(r'\$\\le\$','≤',s)
    s=re.sub(r'\$\\Rightarrow\$','⇒',s); s=s.replace('$\\times$','×')
    s=re.sub(r'\\\((.*?)\\\)',r'$\1$',s)
    s=re.sub(r'(mục|bảng|hình|chương|Phụ lục|phương trình)~\\(eq)?ref\{[^}]*\}',r'\1 tương ứng trong labelX.html',s)
    s=re.sub(r'\\(eq)?ref\{[^}]*\}','(xem labelX.html)',s)
    s=s.replace('\\%','%').replace('\\&','&').replace('\\_','_').replace('\\#','#').replace('{,}',',').replace('``','"').replace("''",'"')
    s=s.replace('\\newline',' ').replace('~',' ')
    s=re.sub(r'\\begin\{(enumerate|itemize)\}(\[[^\]]*\])?','',s); s=re.sub(r'\\end\{(enumerate|itemize)\}','',s)
    s=re.sub(r'\s*\\item\s*',' • ',s)
    s=re.sub(r'\\[a-zA-Z]+\{([^{}]*)\}',r'\1',s)
    maths=[]
    def keep(m):
        maths.append(m.group(0)); return '@@M%d@@' % (len(maths)-1)
    s=re.sub(r'\$[^$]*\$',keep,s)
    s=s.replace('{','').replace('}','').replace('|','\\|')
    for k,v in enumerate(maths): s=s.replace('@@M%d@@' % k, v.replace('|','\\|'))
    return re.sub(r'\s+',' ',s).strip()
def rows(text, caption_label):
    i=text.index('\\label{'+caption_label+'}')
    start=text.rfind('\\begin{xltabular}',0,i); end=text.index('\\end{xltabular}',i)
    body=text[start:end]
    if '\\endfirsthead' in body:
        rest=body.split('\\endfirsthead',1)[1]
        rest=rest.split('\\endhead',1)[1]
        for t in ('\\endlastfoot','\\endfoot'):
            if t in rest: rest=rest.split(t,1)[1]; break
    else: rest=body.split('\\midrule',1)[1]
    rest=rest.replace('\\bottomrule','').replace('\\midrule','')
    return [Converter.split_cells(r) for r in Converter.split_rows(rest) if r.strip()]
out={}
ch6=tex('06-functional')
fr=[]
for lab in ['tab:fr-snp','tab:fr-eng','tab:fr-agg','tab:fr-rnk','tab:fr-rev','tab:fr-esc','tab:fr-rwk','tab:fr-gdl','tab:fr-evl','tab:fr-rpt','tab:fr-sec','tab:fr-gte']:
    fr.append((lab,[[md(c) for c in r] for r in rows(ch6,lab)]))
out['fr']=fr
out['nfr']=[[md(c) for c in r] for r in rows(tex('08-nonfunctional'),'tab:nfr')]
out['uc']=[[md(c) for c in r] for r in rows(tex('04-usecases'),'tab:uclist')]
out['gloss']=[[md(c) for c in r] for r in rows(tex('01-introduction'),'tab:glossary')]
out['ac']=[[md(c) for c in r] for r in rows(tex('07-evaluation'),'tab:acceptance')]
out['kpi']=[[md(c) for c in r] for r in rows(tex('02-overview'),'tab:kpis')]
out['users']=[[md(c) for c in r] for r in rows(tex('02-overview'),'tab:users')]
out['assum']=[[md(c) for c in r] for r in rows(tex('02-overview'),'tab:assumptions')]
out['scope']=[[md(c) for c in r] for r in rows(tex('01-introduction'),'tab:scope')]
out['br']=[[md(c) for c in r] for r in rows(tex('03-data-errors'),'tab:countrules')]+[[md(c) for c in r] for r in rows(tex('03-data-errors'),'tab:refrules')]
out['errors']=[[md(c) for c in r] for r in rows(tex('03-data-errors'),'tab:errors')]
out['tbd']=[[md(c) for c in r] for r in rows(tex('11-traceability'),'tab:tbd')]
out['risks']=[[md(c) for c in r] for r in rows(tex('11-traceability'),'tab:risks')]
# UC specs
ch4=tex('04-usecases'); ucs=[]
for m in re.finditer(r'\\subsection\*\{(UC-\d+)[^}]*\}',ch4):
    title=re.search(r'\{(.*)\}',m.group(0)).group(1)
    st=ch4.index('\\begin{xltabular}',m.end()); en=ch4.index('\\end{xltabular}',st)
    body=ch4[st:en].split('\\toprule',1)[1].replace('\\bottomrule','')
    rs=[Converter.split_cells(r) for r in Converter.split_rows(body) if r.strip()]
    ucs.append((md(title),[(md(r[0]),md(r[1]) if len(r)>1 else '') for r in rs]))
out['ucspec']=ucs

# ---- ghi Markdown ----
import re
D=out
def fm(id_,title,domain,module,tags,prio=2):
    return f"---\nid: {id_}\ntitle: {title}\ntype: reference\ndomain: {domain}\nmodule: {module}\ntags: [{', '.join(tags)}]\npriority: {prio}\n---\n"
def table(head,rows):
    o=['| '+' | '.join(head)+' |','|'+'---|'*len(head)]
    for r in rows:
        r=(r+['']*len(head))[:len(head)]
        o.append('| '+' | '.join(r)+' |')
    return '\n'.join(o)
SRC_NOTE="Nguồn chuẩn: [labelX.html](labelX.html) (bản HTML) và `docs/label-x_system-requirement-specification/` (bản LaTeX), SRS M13 v1.0, 05/10/2026. Khi có khác biệt, bản LaTeX là gốc; HTML được sinh lại bằng `python3 scripts/srs_tex2html.py`."
FRT={'tab:fr-snp':'SNP — CVAT Adapter và Snapshot','tab:fr-eng':'ENG — Engine phân tích nghi vấn','tab:fr-agg':'AGG — Candidate, Issue và Coverage ledger','tab:fr-rnk':'RNK — Chấm điểm rủi ro và xếp hạng','tab:fr-rev':'REV — Hàng đợi và Review Workspace','tab:fr-esc':'ESC — Chuyển cấp và phân xử','tab:fr-rwk':'RWK — Rework và kiểm lại','tab:fr-gdl':'GDL — Tra cứu guideline','tab:fr-evl':'EVL — Reference, đo lường và effort','tab:fr-rpt':'RPT — Báo cáo hiệu quả','tab:fr-sec':'SEC — Phân quyền và kiểm toán','tab:fr-gte':'GTE — Quality Gate tối thiểu'}
# requirements.md
o=[fm('business-requirements','Yêu cầu nghiệp vụ và hệ thống — SRS M13','business','requirements',['requirements','functional','non-functional','kpi','m13'],1)]
o.append("# Yêu cầu nghiệp vụ và hệ thống — SRS M13\n\n## Purpose\n\nTóm tắt có thể tra cứu của các yêu cầu trong SRS M13 của LabelX (người dùng chấp nhận nội dung 05/10/2026, chờ ký theo vai trò): mục tiêu, KPI, phạm vi, yêu cầu chức năng, phi chức năng và tiêu chí nghiệm thu, giữ nguyên mã định danh.\n\n"+SRC_NOTE+"\n")
o.append("## Phạm vi\n\n"+table(['Nhóm','Nội dung'],D['scope'])+"\n")
o.append("## Mục tiêu và chỉ số thành công\n\n"+table(['Mã','Chỉ số','Định nghĩa','Ngưỡng'],D['kpi'])+"\n\nNgưỡng G-2, G-3, G-4 là cấu hình khởi điểm pilot đã chốt (nguồn R); ngưỡng KPI-1/KPI-2 chốt từ đo baseline trước khi chạy held-out (B-14).\n")
o.append("## Yêu cầu chức năng\n\nƯu tiên MoSCoW: M = Must, S = Should, C = Could.\n")
for lab,rs in D['fr']:
    o.append(f"### {FRT[lab]}\n\n"+table(['Mã','Yêu cầu','Ưu tiên','Truy vết'],rs)+"\n")
o.append("## Yêu cầu phi chức năng\n\nCác con số là đề xuất khởi điểm; ngưỡng nghiệm thu chốt sau khi đo pilot (B-14).\n\n"+table(['Mã','Nhóm','Yêu cầu','Cách kiểm'],D['nfr'])+"\n")
o.append("## Tiêu chí nghiệm thu\n\n"+table(['Mã','Tiêu chí','Mục tiêu','Yêu cầu'],D['ac'])+"\n")
o.append("## Giả định và phụ thuộc\n\n"+table(['Mã','Giả định / phụ thuộc','Nếu sai thì'],D['assum'])+"\n")
o.append("## Tham số còn mở\n\n"+table(['Mã','Nội dung','Người chốt','Hạn chốt'],D['tbd'])+"\n")
o.append("## Rủi ro\n\n"+table(['Mã','Rủi ro','Khả năng','Tác động','Giảm thiểu'],D['risks'])+"\n")
open('docs/01-business/requirements.md','w').write('\n'.join(o))
# use-cases.md
o=[fm('business-use-cases','Use case — SRS M13','business','use-cases',['use-cases','actors','m13'],1)]
o.append("# Use case — SRS M13\n\n## Purpose\n\nDanh sách và đặc tả 14 use case của chức năng M13 (Reviewer Prioritization Assistant) trong LabelX. Sơ đồ use case, sequence diagram và state machine nằm trong [labelX.html](labelX.html) chương 4–5.\n\n"+SRC_NOTE+"\n")
o.append("## Danh sách\n\n"+table(['Mã','Tên','Actor chính','Ưu tiên','Mục tiêu'],D['uc'])+"\n")
o.append("## Đặc tả")
for title,rs in D['ucspec']:
    o.append(f"\n### {title}\n\n"+table(['Mục','Nội dung'],[[a,b] for a,b in rs]))
open('docs/01-business/use-cases.md','w').write('\n'.join(o)+'\n')
# domain-model.md (business-level)
o=[fm('business-domain-model','Mô hình nghiệp vụ — dữ liệu, nhóm lỗi, quy tắc','business','domain',['domain','errors','business-rules','bdd100k'],2)]
o.append("# Mô hình nghiệp vụ — dữ liệu, nhóm lỗi, quy tắc\n\n## Purpose\n\nKhái niệm nghiệp vụ cốt lõi của M13: dữ liệu BDD100K, ba nhóm lỗi, quy tắc đếm lỗi và lập reference. Thiết kế aggregate/value object kỹ thuật ở `docs/03-domain/`.\n\n"+SRC_NOTE+"\n")
o.append("## Dữ liệu\n\nBDD100K 2D detection, ảnh 1280×720, 10 lớp: `car`, `truck`, `bus`, `train`, `motorcycle`, `bicycle`, `pedestrian`, `rider`, `traffic light`, `traffic sign`. Thuộc tính cảnh (thời tiết, loại cảnh, thời điểm) và cờ `occluded`/`truncated` dùng để phân tầng và báo cáo theo slice. Tập hiệu chỉnh và held-out tách theo video nguồn.\n")
o.append("## Nhóm lỗi\n\n"+table(['Nhóm','Định nghĩa','Nguồn candidate','Tiêu chí xác minh'],D['errors'])+"\n\nHoãn trong bản đầu: box lệch/lỏng (B-06), box quá nhỏ (chỉ là cảnh báo cấu trúc), sai thuộc tính, lỗi track.\n")
o.append("## Quy tắc nghiệp vụ\n\n"+table(['Mã','Quy tắc'],D['br'])+"\n")
o.append("## Khái niệm chính\n\n"+table(['Khái niệm','Ý nghĩa'],[r for r in D['gloss'] if len(r)==2 and r[0] in ('Snapshot','Revision','QC Run','Candidate','Issue','Evidence (bằng chứng)','Risk score $s(f)$','Coverage ledger','Reference','Lỗi đã xác minh','Rework','QC run cuối','Quality Gate','Waiver','Lease')])+"\n")
open('docs/01-business/domain-model.md','w').write('\n'.join(o))
# glossary
o=[fm('project-glossary','Thuật ngữ LabelX','project','repository',['glossary','terminology'],2)]
o.append("# Thuật ngữ LabelX\n\n## Purpose\n\nThuật ngữ dùng chung trong tài liệu và giao diện LabelX, trích từ SRS M13 (bảng thuật ngữ, chương 1). Quy ước giao diện: viết đầy đủ tên (Quality Control, Intersection over Union, Ground Truth) theo Design System LabelX; viết tắt chỉ dùng trong tài liệu kỹ thuật.\n\nNguồn: [SRS M13](../01-business/labelX.html).\n")
rows=[]
for r in D['gloss']:
    if len(r)==1:
        g=re.sub(r'^\d@l','',r[0]).replace('\\sffamily ','').replace('**','').strip()
        o.append('\n'.join(['' if not rows else table(['Thuật ngữ','Định nghĩa'],rows)])); rows=[]
        o.append(f"\n## {g}\n")
    else: rows.append(r)
o.append(table(['Thuật ngữ','Định nghĩa'],rows))
open('docs/00-project/glossary.md','w').write('\n'.join(x for x in o if x is not None)+'\n')
# stakeholders
o=[fm('project-stakeholders','Stakeholder và lớp người dùng LabelX','project','repository',['stakeholders','roles','users'],2)]
o.append("# Stakeholder và lớp người dùng LabelX\n\n## Purpose\n\nVai trò tham gia dự án và người dùng hệ thống, trách nhiệm phê duyệt và quyền chính. Tên người cụ thể chưa được gán (cần điền khi giao việc).\n\n## Lớp người dùng\n\n"+table(['Vai trò','Mô tả và nhiệm vụ','Quyền chính'],D['users']))
o.append("\n## Trách nhiệm phê duyệt SRS\n\n"+table(['Vai trò','Phê duyệt','Người được gán'],[["Product Owner M13","Phạm vi, KPI, tiêu chí nghiệm thu","chưa gán"],["Quality Assurance Lead","Taxonomy lỗi, reference, quy trình phân xử","chưa gán"],["Quality Control Admin","Cấu hình kỹ thuật, quyền, engine","chưa gán"],["Tech Lead Backend","Kiến trúc, API, yêu cầu phi chức năng","chưa gán"],["Data/Model Owner","Dữ liệu BDD100K, Detector baseline","chưa gán"]]))
o.append("\n## Quy tắc tách nhiệm vụ\n\n- Reviewer không review annotation của chính mình (assignee tại snapshot) — B-12.\n- Người duyệt waiver, khoá reference, phân xử khác người yêu cầu — B-11, B-12.\n- Super Admin không là người duyệt mặc định; ghi đè phải có lý do và gắn nhãn trong audit.\n\nNguồn: [SRS M13](../01-business/labelX.html) mục 2.6, bảng ma trận quyền chương 6; `docs/00-project/sources/architecture_review.html`.\n")
open('docs/00-project/stakeholders.md','w').write('\n'.join(o))
