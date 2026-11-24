"""EPP-UCA | Unified Cause Analysis
Version 1.0.0 | Controlled pilot build
Evidence-led, non-blaming, risk-based and barrier-focused investigation workflow.
"""
from __future__ import annotations
import json, sqlite3, uuid, hashlib
from datetime import datetime, date
from pathlib import Path
from typing import Any
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DB_PATH = DATA / "epp_uca.db"
BANK_PATH = DATA / "question_bank.json"
APP_VERSION = "1.0.0"
STATUSES = ["Draft", "Submitted", "Under Review", "Returned", "Approved", "Closed"]
LEVELS = {1: "Level 1 – Basic / أساسي", 2: "Level 2 – Structured / منظم", 3: "Level 3 – Advanced / متقدم"}

st.set_page_config(page_title="EPP-UCA | Unified Cause Analysis", page_icon="🛡️", layout="wide")

# ------------------------------- Persistence -------------------------------
def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS events(
          event_id TEXT PRIMARY KEY, title TEXT NOT NULL, event_date TEXT NOT NULL,
          department TEXT NOT NULL, location TEXT NOT NULL, level INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'Draft', created_at TEXT NOT NULL,
          created_by TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}',
          updated_at TEXT, submitted_at TEXT, approved_by TEXT, approved_at TEXT,
          revision INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS findings(
          finding_id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
          finding_type TEXT NOT NULL, category TEXT NOT NULL, statement TEXT NOT NULL,
          evidence_ref TEXT NOT NULL, rationale TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS barriers(
          barrier_id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
          barrier_name TEXT NOT NULL, barrier_type TEXT NOT NULL, expected_function TEXT NOT NULL,
          actual_performance TEXT NOT NULL, status TEXT NOT NULL, evidence_ref TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS actions(
          action_id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
          linked_finding_id TEXT, action_type TEXT NOT NULL, description TEXT NOT NULL,
          hierarchy_level TEXT NOT NULL, owner TEXT NOT NULL, due_date TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'Open', completion_evidence TEXT DEFAULT '',
          effectiveness TEXT DEFAULT 'Not assessed', created_at TEXT NOT NULL,
          FOREIGN KEY(linked_finding_id) REFERENCES findings(finding_id)
        );
        CREATE TABLE IF NOT EXISTS reviews(
          review_id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
          reviewer TEXT NOT NULL, decision TEXT NOT NULL, comments TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS library_proposals(
          proposal_id TEXT PRIMARY KEY, category TEXT NOT NULL, code TEXT NOT NULL,
          en TEXT NOT NULL, ar TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending',
          submitted_by TEXT NOT NULL, reviewed_by TEXT DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_log(
          log_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT, action TEXT NOT NULL,
          actor TEXT NOT NULL, timestamp TEXT NOT NULL, details TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
        CREATE INDEX IF NOT EXISTS idx_actions_due ON actions(due_date,status);
        CREATE INDEX IF NOT EXISTS idx_findings_event ON findings(event_id);
        """)
        # Safe additive migration for databases created by Issue 01 prototype.
        cols = {r[1] for r in con.execute("PRAGMA table_info(events)")}
        additions = {
            "updated_at": "TEXT", "submitted_at": "TEXT", "approved_by": "TEXT",
            "approved_at": "TEXT", "revision": "INTEGER NOT NULL DEFAULT 1"
        }
        for name, typ in additions.items():
            if name not in cols:
                con.execute(f"ALTER TABLE events ADD COLUMN {name} {typ}")

def audit(event_id: str | None, action: str, actor: str, details: str = ""):
    with connect() as con:
        con.execute("INSERT INTO audit_log(event_id,action,actor,timestamp,details) VALUES(?,?,?,?,?)",
                    (event_id, action, actor, now(), details))

def now(): return datetime.now().isoformat(timespec="seconds")

def load_bank():
    if not BANK_PATH.exists(): return {"questions": [], "principles": []}
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))

def event_code(): return "UCA-" + datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()

def get_event(eid: str):
    with connect() as con: return con.execute("SELECT * FROM events WHERE event_id=?", (eid,)).fetchone()

def save_event(eid: str | None, title: str, event_date: date, dept: str, loc: str,
               level: int, actor: str, payload: dict[str, Any]):
    stamp = now()
    with connect() as con:
        if eid:
            con.execute("UPDATE events SET title=?,event_date=?,department=?,location=?,level=?,payload=?,updated_at=?,revision=revision+1 WHERE event_id=?",
                        (title, str(event_date), dept, loc, level, json.dumps(payload, ensure_ascii=False), stamp, eid))
            action = "Updated event record"
        else:
            eid = event_code()
            con.execute("INSERT INTO events(event_id,title,event_date,department,location,level,status,created_at,created_by,payload,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (eid,title,str(event_date),dept,loc,level,"Draft",stamp,actor,json.dumps(payload,ensure_ascii=False),stamp))
            action = "Created event record"
    audit(eid, action, actor)
    return eid

# --------------------------------- UI helpers -------------------------------
def bilingual(en, ar): return f"{en}  |  {ar}"
def section(title): st.markdown(f"<div class='section-title'>{title}</div>", unsafe_allow_html=True)
def status_badge(status):
    colors = {"Draft":"#64748b","Submitted":"#2563eb","Under Review":"#7c3aed","Returned":"#d97706","Approved":"#059669","Closed":"#0f766e"}
    c=colors.get(status,"#64748b")
    st.markdown(f"<span style='background:{c};color:white;padding:4px 10px;border-radius:20px;font-size:12px'>{status}</span>", unsafe_allow_html=True)
def question_control(q, key_prefix=""):
    label = bilingual(q["en"], q["ar"])
    opts=q.get("options", [])
    labels=[f"{o[1]} / {o[2]}" for o in opts]
    codes=[o[0] for o in opts]
    if q.get("type")=="multi":
        selected=st.multiselect(label, labels, key=f"{key_prefix}{q['id']}")
        return [codes[labels.index(x)] for x in selected]
    selected=st.selectbox(label,["— Select / اختر —"]+labels,key=f"{key_prefix}{q['id']}")
    return None if selected.startswith("—") else codes[labels.index(selected)]
def trigger_ok(trigger, answers):
    if not trigger: return True
    try:
        qid, vals=trigger.split("=",1); vals=[x.strip() for x in vals.split(",")]
        current=answers.get(qid)
        return any(v in current for v in vals) if isinstance(current,list) else current in vals
    except Exception: return False

def export_event(eid: str):
    ev=get_event(eid)
    with connect() as con:
        findings=pd.read_sql_query("SELECT finding_type,category,statement,evidence_ref,rationale,verified FROM findings WHERE event_id=?",con,params=(eid,))
        barriers=pd.read_sql_query("SELECT barrier_name,barrier_type,expected_function,actual_performance,status,evidence_ref FROM barriers WHERE event_id=?",con,params=(eid,))
        actions=pd.read_sql_query("SELECT action_type,description,hierarchy_level,owner,due_date,status,completion_evidence,effectiveness FROM actions WHERE event_id=?",con,params=(eid,))
        reviews=pd.read_sql_query("SELECT reviewer,decision,comments,created_at FROM reviews WHERE event_id=?",con,params=(eid,))
    summary=pd.DataFrame([{"Event ID":eid,"Title":ev["title"],"Date":ev["event_date"],"Department":ev["department"],"Location":ev["location"],"Analysis Level":ev["level"],"Status":ev["status"],"Revision":ev["revision"]}])
    import io
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine="openpyxl") as writer:
        summary.to_excel(writer,index=False,sheet_name="Event")
        findings.to_excel(writer,index=False,sheet_name="Findings")
        barriers.to_excel(writer,index=False,sheet_name="Barrier Analysis")
        actions.to_excel(writer,index=False,sheet_name="Actions")
        reviews.to_excel(writer,index=False,sheet_name="Reviews")
    return out.getvalue()

init_db()
bank=load_bank(); questions=bank.get("questions",[])
st.markdown("""
<style>
.block-container{max-width:1500px;padding-top:1.2rem;padding-bottom:3rem}
.uca-head{background:linear-gradient(110deg,#102f46,#1e5875);padding:22px 26px;border-radius:14px;color:white;margin-bottom:18px}
.uca-head h1{color:white;margin:0;font-size:30px}.uca-head p{color:#d9e9f2;margin:5px 0 0 0}
.section-title{font-size:19px;font-weight:700;border-bottom:1px solid #d7e0e7;padding:8px 0;margin:18px 0 12px;color:var(--text-color)}
div[data-testid="stMetric"]{background:rgba(100,116,139,.08);padding:12px;border-radius:10px;border:1px solid rgba(100,116,139,.15)}
.small-note{font-size:12px;color:#64748b}
</style>
<div class='uca-head'><h1>EPP-UCA</h1><div style='font-size:18px;font-weight:600'>Unified Cause Analysis</div><p>Issue 02 | Rev 00 • Evidence-led investigation • English / العربية</p></div>
""",unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🛡️ EPP-UCA")
    page=st.radio("Navigation / التنقل",[
        "Dashboard / لوحة المعلومات", "New Analysis / تحليل جديد", "Analysis Register / سجل التحليلات",
        "Investigation Workspace / مساحة التحقيق", "Action Tracker / متابعة الإجراءات",
        "Library Proposals / مقترحات المكتبة", "Methodology & Governance / المنهجية والحوكمة"
    ])
    actor=st.text_input("Operator name / اسم المستخدم", "HSE Analyst")
    st.caption(f"Build {APP_VERSION} • Local SQLite")
    st.warning("Pilot build: user identity and permissions require integration with EPP IT authentication before production use.")

# -------------------------------- Dashboard ---------------------------------
if page.startswith("Dashboard"):
    with connect() as con:
        events=con.execute("SELECT * FROM events ORDER BY created_at DESC").fetchall()
        open_actions=con.execute("SELECT COUNT(*) n FROM actions WHERE status NOT IN ('Completed','Cancelled')").fetchone()["n"]
        overdue=con.execute("SELECT COUNT(*) n FROM actions WHERE status NOT IN ('Completed','Cancelled') AND due_date < ?",(str(date.today()),)).fetchone()["n"]
        pending=con.execute("SELECT COUNT(*) n FROM library_proposals WHERE status='Pending'").fetchone()["n"]
    c=st.columns(5)
    c[0].metric("Total analyses / إجمالي التحليلات",len(events))
    c[1].metric("Under review / قيد المراجعة",sum(x["status"] in ("Submitted","Under Review") for x in events))
    c[2].metric("Approved / معتمد",sum(x["status"] in ("Approved","Closed") for x in events))
    c[3].metric("Open actions / إجراءات مفتوحة",open_actions)
    c[4].metric("Overdue actions / متأخرة",overdue)
    section("Recent investigations / أحدث التحقيقات")
    if events:
        st.dataframe(pd.DataFrame([{"Event ID":x["event_id"],"Title":x["title"],"Date":x["event_date"],"Department":x["department"],"Level":x["level"],"Status":x["status"]} for x in events]),use_container_width=True,hide_index=True)
    else: st.info("No investigations recorded / لا توجد تحقيقات مسجلة حتى الآن.")
    section("System control principles / مبادئ ضبط النظام")
    st.markdown("- Evidence before conclusion / الدليل قبل الاستنتاج\n- Root cause must be traceable to verified findings / يجب ربط السبب الجذري بنتائج مثبتة\n- Actions must address causes and failed barriers / الإجراءات تعالج الأسباب وفشل الحواجز\n- AI output is advisory only and never an approval / مخرجات الذكاء الاصطناعي استرشادية وليست اعتماداً")

# ------------------------------- New Analysis -------------------------------
elif page.startswith("New Analysis"):
    section("Event registration / تسجيل الحالة")
    with st.form("new_event_form"):
        a,b,c=st.columns(3)
        title=a.text_input("Event title / عنوان الحالة *")
        event_date=b.date_input("Event date / تاريخ الحدث",date.today())
        level=c.selectbox("Analysis level / مستوى التحليل",[1,2,3],format_func=lambda x:LEVELS[x])
        d,e=st.columns(2)
        dept=d.selectbox("Department / الإدارة",["Production","Maintenance","Utilities","Offsite","HSE","Administration","Contractor","Security","Warehouse","Engineering"])
        loc=e.selectbox("Area / المنطقة",["PDH","PP","Utilities","Tank Farm","Loading Area","Chemical Warehouse","Workshop","Laboratory","Substation","Administration","Other"])
        submitted=st.form_submit_button("Create Draft / إنشاء مسودة",type="primary")
    if submitted:
        if not title.strip(): st.error("Event title is mandatory / عنوان الحالة إلزامي.")
        else:
            eid=save_event(None,title.strip(),event_date,dept,loc,level,actor,{"answers":{}})
            st.success(f"Draft created: {eid}")
            st.info("Open Investigation Workspace to complete the analysis / افتح مساحة التحقيق لاستكمال التحليل.")

# -------------------------- Investigation Workspace -------------------------
elif page.startswith("Investigation Workspace"):
    with connect() as con: rows=con.execute("SELECT event_id,title,status FROM events WHERE status NOT IN ('Closed') ORDER BY created_at DESC").fetchall()
    if not rows: st.info("Create an event record first / أنشئ سجل حالة أولاً.")
    else:
        selected=st.selectbox("Select event / اختر الحالة",rows,format_func=lambda r:f"{r['event_id']} | {r['title']} | {r['status']}")
        ev=get_event(selected["event_id"]); eid=ev["event_id"]
        status_badge(ev["status"])
        section("1. Event profile & structured questions / بيانات الحالة والأسئلة المنظمة")
        payload=json.loads(ev["payload"] or "{}")
        answers=payload.get("answers",{})
        with st.form(f"answers_{eid}"):
            new_answers={}
            for stage in sorted(set(q["stage"] for q in questions),key=lambda x:int(x[:2])):
                st.markdown(f"**{stage}**")
                for q in [z for z in questions if z["stage"]==stage and z.get("level",1)<=ev["level"] and trigger_ok(z.get("trigger",""),new_answers)]:
                    val=question_control(q,f"{eid}_")
                    if val is not None: new_answers[q["id"]]=val
            save_answers=st.form_submit_button("Save structured answers / حفظ الإجابات",type="primary")
        if save_answers:
            payload["answers"]=new_answers
            save_event(eid,ev["title"],date.fromisoformat(ev["event_date"]),ev["department"],ev["location"],ev["level"],actor,payload)
            st.success("Answers saved / تم حفظ الإجابات."); st.rerun()

        section("2. Causal findings register / سجل النتائج السببية")
        with st.form(f"finding_{eid}"):
            f1,f2=st.columns(2)
            ftype=f1.selectbox("Finding type / نوع النتيجة",["Immediate Cause / سبب مباشر","Contributing Factor / عامل مساهم","Root Cause / سبب جذري","Human & Organizational Factor / عامل بشري أو تنظيمي"])
            category=f2.selectbox("Category / التصنيف",["People / الأفراد","Equipment / المعدات","Procedure / الإجراءات","Materials / المواد","Environment / البيئة","Management System / نظام الإدارة","Competence / الكفاءة","Supervision / الإشراف","Design / التصميم","Maintenance / الصيانة","Other / أخرى"])
            statement=st.text_area("Finding statement / وصف النتيجة *",height=75)
            evidence_ref=st.text_input("Evidence reference / مرجع الدليل *",placeholder="Evidence ID, document, photo, interview record...")
            rationale=st.text_area("Causal rationale / المبرر السببي",height=65)
            verified=st.checkbox("Verified by investigation team / تم التحقق بواسطة فريق التحقيق")
            add_finding=st.form_submit_button("Add finding / إضافة نتيجة")
        if add_finding:
            if not statement.strip() or not evidence_ref.strip(): st.error("Statement and evidence reference are mandatory / الوصف ومرجع الدليل إلزاميان.")
            elif ftype.startswith("Root Cause") and not verified: st.error("A root cause cannot be recorded as verified without verification / لا يمكن تسجيل السبب الجذري كمثبت دون تحقق.")
            else:
                with connect() as con:
                    con.execute("INSERT INTO findings VALUES(?,?,?,?,?,?,?,?,?)",("FND-"+uuid.uuid4().hex[:10].upper(),eid,ftype,category,statement.strip(),evidence_ref.strip(),rationale.strip(),int(verified),now()))
                audit(eid,"Added causal finding",actor,ftype); st.success("Finding added / تمت إضافة النتيجة."); st.rerun()
        with connect() as con: frows=con.execute("SELECT * FROM findings WHERE event_id=? ORDER BY created_at",(eid,)).fetchall()
        if frows:
            st.dataframe(pd.DataFrame([{"ID":r["finding_id"],"Type":r["finding_type"],"Category":r["category"],"Finding":r["statement"],"Evidence":r["evidence_ref"],"Verified":bool(r["verified"])} for r in frows]),use_container_width=True,hide_index=True)

        section("3. Barrier analysis / تحليل الحواجز")
        with st.form(f"barrier_{eid}"):
            b1,b2=st.columns(2)
            bname=b1.text_input("Barrier / الحاجز")
            btype=b2.selectbox("Barrier type / نوع الحاجز",["Engineering","Instrumented protection","Alarm / Operator response","Administrative / Procedure","Physical","PPE","Emergency response","Other"])
            expected=st.text_area("Intended function / الوظيفة المطلوبة",height=60)
            actual=st.text_area("Observed performance / الأداء الفعلي",height=60)
            bstatus=st.selectbox("Barrier status / حالة الحاجز",["Effective","Degraded","Failed","Absent","Not Applicable","Unknown"])
            bref=st.text_input("Evidence reference / مرجع الدليل للحاجز")
            add_barrier=st.form_submit_button("Add barrier / إضافة حاجز")
        if add_barrier:
            if not bname.strip() or not expected.strip() or not actual.strip() or not bref.strip(): st.error("Complete barrier, function, performance and evidence / استكمل الحاجز ووظيفته وأداءه والدليل.")
            else:
                with connect() as con: con.execute("INSERT INTO barriers VALUES(?,?,?,?,?,?,?,?,?)",("BAR-"+uuid.uuid4().hex[:10].upper(),eid,bname,btype,expected,actual,bstatus,bref,now()))
                audit(eid,"Added barrier analysis",actor,bstatus); st.success("Barrier recorded / تم تسجيل الحاجز."); st.rerun()
        with connect() as con: brows=con.execute("SELECT * FROM barriers WHERE event_id=?",(eid,)).fetchall()
        if brows: st.dataframe(pd.DataFrame([{"Barrier":r["barrier_name"],"Type":r["barrier_type"],"Expected":r["expected_function"],"Actual":r["actual_performance"],"Status":r["status"],"Evidence":r["evidence_ref"]} for r in brows]),use_container_width=True,hide_index=True)

        section("4. Corrective & preventive actions / الإجراءات التصحيحية والوقائية")
        with st.form(f"action_{eid}"):
            linked=st.selectbox("Linked finding / النتيجة المرتبطة",["Not linked"]+[r["finding_id"] for r in frows])
            atype=st.selectbox("Action type / نوع الإجراء",["Corrective","Preventive","Barrier restoration","System improvement","Learning / communication"])
            desc=st.text_area("Action description / وصف الإجراء *",height=70)
            hlevel=st.selectbox("Control hierarchy / مستوى التحكم",["Elimination","Substitution","Engineering","Administrative","PPE","To be assessed"])
            x,y=st.columns(2); owner=x.text_input("Responsible owner / المسؤول"); due=y.date_input("Due date / تاريخ الاستحقاق",date.today())
            add_action=st.form_submit_button("Add action / إضافة إجراء")
        if add_action:
            if not desc.strip() or not owner.strip(): st.error("Action and owner are mandatory / الإجراء والمسؤول إلزاميان.")
            else:
                with connect() as con: con.execute("INSERT INTO actions(action_id,event_id,linked_finding_id,action_type,description,hierarchy_level,owner,due_date,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",("ACT-"+uuid.uuid4().hex[:10].upper(),eid,None if linked=="Not linked" else linked,atype,desc,hlevel,owner,str(due),"Open",now()))
                audit(eid,"Added action",actor,desc); st.success("Action added / تمت إضافة الإجراء."); st.rerun()
        with connect() as con: arows=con.execute("SELECT * FROM actions WHERE event_id=?",(eid,)).fetchall()
        if arows: st.dataframe(pd.DataFrame([{"ID":r["action_id"],"Action":r["description"],"Owner":r["owner"],"Due":r["due_date"],"Status":r["status"],"Effectiveness":r["effectiveness"]} for r in arows]),use_container_width=True,hide_index=True)

        section("5. Submission & independent review / الإرسال والمراجعة")
        with connect() as con:
            verified_roots=con.execute("SELECT COUNT(*) n FROM findings WHERE event_id=? AND finding_type LIKE 'Root Cause%' AND verified=1",(eid,)).fetchone()["n"]
            evidence_count=con.execute("SELECT COUNT(*) n FROM findings WHERE event_id=? AND evidence_ref<>''",(eid,)).fetchone()["n"]
            action_count=con.execute("SELECT COUNT(*) n FROM actions WHERE event_id=?",(eid,)).fetchone()["n"]
            review_rows=con.execute("SELECT * FROM reviews WHERE event_id=? ORDER BY created_at DESC",(eid,)).fetchall()
        st.write({"Verified root causes":verified_roots,"Evidence-backed findings":evidence_count,"Actions":action_count})
        if ev["status"] in ("Draft","Returned"):
            if st.button("Submit for review / إرسال للمراجعة",type="primary",key=f"submit_{eid}"):
                if evidence_count==0 or action_count==0: st.error("At least one evidence-backed finding and one action are required / يلزم نتيجة مدعومة بدليل وإجراء واحد على الأقل.")
                elif ev["level"]>=2 and verified_roots==0: st.error("Level 2/3 requires at least one verified root cause / المستوى 2 و3 يتطلب سبباً جذرياً مثبتاً.")
                else:
                    with connect() as con: con.execute("UPDATE events SET status='Submitted',submitted_at=?,updated_at=? WHERE event_id=?",(now(),now(),eid))
                    audit(eid,"Submitted for review",actor); st.success("Submitted / تم الإرسال."); st.rerun()
        elif ev["status"] in ("Submitted","Under Review"):
            with st.form(f"review_{eid}"):
                decision=st.selectbox("Review decision / قرار المراجعة",["Under Review","Returned","Approved"])
                comments=st.text_area("Reviewer comments / ملاحظات المراجع")
                review_submit=st.form_submit_button("Record review decision / تسجيل قرار المراجعة")
            if review_submit:
                if decision in ("Returned","Approved") and not comments.strip(): st.error("Comments are required for return or approval / الملاحظات إلزامية عند الإعادة أو الاعتماد.")
                else:
                    with connect() as con:
                        con.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?)",("REV-"+uuid.uuid4().hex[:10].upper(),eid,actor,decision,comments,now()))
                        con.execute("UPDATE events SET status=?,approved_by=?,approved_at=?,updated_at=? WHERE event_id=?",(decision,actor,now() if decision=="Approved" else None,now(),eid))
                    audit(eid,"Review decision",actor,decision); st.success("Review recorded / تم تسجيل المراجعة."); st.rerun()
        if review_rows:
            st.markdown("**Review history / سجل المراجعات**")
            st.dataframe(pd.DataFrame([{"Reviewer":r["reviewer"],"Decision":r["decision"],"Comments":r["comments"],"Date":r["created_at"]} for r in review_rows]),use_container_width=True,hide_index=True)
        st.download_button("Export investigation workbook / تصدير ملف التحقيق Excel",data=export_event(eid),file_name=f"{eid}_Investigation.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ------------------------------ Analysis Register ---------------------------
elif page.startswith("Analysis Register"):
    with connect() as con: rows=con.execute("SELECT * FROM events ORDER BY created_at DESC").fetchall()
    if rows:
        st.dataframe(pd.DataFrame([{"Event ID":r["event_id"],"Title":r["title"],"Date":r["event_date"],"Department":r["department"],"Location":r["location"],"Level":r["level"],"Status":r["status"],"Revision":r["revision"]} for r in rows]),use_container_width=True,hide_index=True)
        chosen=st.selectbox("Open event / فتح الحالة",rows,format_func=lambda r:f"{r['event_id']} | {r['title']}")
        ev=chosen
        status_badge(ev["status"])
        st.json(json.loads(ev["payload"] or "{}"))
        st.download_button("Download Excel / تحميل Excel",data=export_event(ev["event_id"]),file_name=f"{ev['event_id']}_UCA.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if st.button("Show audit trail / عرض سجل المراجعة"):
            with connect() as con: logs=con.execute("SELECT action,actor,timestamp,details FROM audit_log WHERE event_id=? ORDER BY timestamp",(ev["event_id"],)).fetchall()
            st.dataframe(pd.DataFrame([dict(x) for x in logs]),use_container_width=True,hide_index=True)
    else: st.info("No records / لا توجد سجلات.")

# -------------------------------- Action Tracker -----------------------------
elif page.startswith("Action Tracker"):
    with connect() as con: rows=con.execute("SELECT a.*,e.title,e.department FROM actions a JOIN events e ON a.event_id=e.event_id ORDER BY a.due_date").fetchall()
    if rows:
        st.dataframe(pd.DataFrame([{"Action ID":r["action_id"],"Event":r["event_id"],"Title":r["title"],"Action":r["description"],"Owner":r["owner"],"Due":r["due_date"],"Status":r["status"],"Effectiveness":r["effectiveness"]} for r in rows]),use_container_width=True,hide_index=True)
        selected=st.selectbox("Update action / تحديث إجراء",rows,format_func=lambda r:f"{r['action_id']} | {r['description'][:65]}")
        with st.form("update_action"):
            new_status=st.selectbox("Status / الحالة",["Open","In Progress","Completed","Cancelled"],index=["Open","In Progress","Completed","Cancelled"].index(selected["status"]) if selected["status"] in ["Open","In Progress","Completed","Cancelled"] else 0)
            completion=st.text_area("Completion evidence / دليل التنفيذ",selected["completion_evidence"] or "")
            effectiveness=st.selectbox("Effectiveness verification / التحقق من الفاعلية",["Not assessed","Effective","Partially effective","Ineffective","Pending verification"])
            updater=st.form_submit_button("Save action update / حفظ التحديث")
        if updater:
            if new_status=="Completed" and (not completion.strip() or effectiveness in ("Not assessed","Pending verification")):
                st.error("Completion requires evidence and an effectiveness assessment / الإغلاق يتطلب دليل تنفيذ وتقييماً للفاعلية.")
            else:
                with connect() as con: con.execute("UPDATE actions SET status=?,completion_evidence=?,effectiveness=? WHERE action_id=?",(new_status,completion,effectiveness,selected["action_id"]))
                audit(selected["event_id"],"Updated action",actor,selected["action_id"]); st.success("Updated / تم التحديث."); st.rerun()
    else: st.info("No actions recorded / لا توجد إجراءات مسجلة.")

# ------------------------------ Library governance --------------------------
elif page.startswith("Library Proposals"):
    section("Controlled taxonomy proposal / اقتراح اختيار للمكتبة")
    with st.form("proposal_form"):
        category=st.selectbox("Category / التصنيف",["Immediate Cause","Contributing Factor","Human Factors","Technical Factors","Work Factors","Organizational Factors","Barrier","Root Cause","Action","Other"])
        x,y=st.columns(2); en=x.text_input("English option / الاختيار بالإنجليزية"); ar=y.text_input("Arabic option / الاختيار بالعربية")
        code=st.text_input("Unique code / كود فريد")
        send=st.form_submit_button("Submit for review / إرسال للمراجعة")
    if send:
        if not en.strip() or not ar.strip() or not code.strip(): st.error("All fields are mandatory / جميع الحقول إلزامية.")
        else:
            with connect() as con:
                exists=con.execute("SELECT 1 FROM library_proposals WHERE code=?",(code.strip().upper(),)).fetchone()
                if exists: st.error("Code already exists / الكود مستخدم بالفعل.")
                else: con.execute("INSERT INTO library_proposals VALUES(?,?,?,?,?,?,?,?,?)",("PR-"+uuid.uuid4().hex[:8].upper(),category,code.strip().upper(),en.strip(),ar.strip(),"Pending",actor,"",now()))
            audit(None,"Submitted taxonomy proposal",actor,code); st.success("Submitted / تم الإرسال.")
    with connect() as con: props=con.execute("SELECT * FROM library_proposals ORDER BY created_at DESC").fetchall()
    for p in props:
        with st.expander(f"{p['proposal_id']} | {p['code']} | {p['en']} / {p['ar']} | {p['status']}"):
            st.write({"Category":p["category"],"Submitted by":p["submitted_by"],"Created":p["created_at"]})
            if p["status"]=="Pending":
                reviewer=st.text_input("Reviewer / المراجع",actor,key=f"reviewer_{p['proposal_id']}")
                c1,c2=st.columns(2)
                if c1.button("Approve / اعتماد",key=f"approve_{p['proposal_id']}"):
                    with connect() as con: con.execute("UPDATE library_proposals SET status='Approved',reviewed_by=? WHERE proposal_id=?",(reviewer,p["proposal_id"]))
                    audit(None,"Approved taxonomy proposal",reviewer,p["code"]); st.rerun()
                if c2.button("Reject / رفض",key=f"reject_{p['proposal_id']}"):
                    with connect() as con: con.execute("UPDATE library_proposals SET status='Rejected',reviewed_by=? WHERE proposal_id=?",(reviewer,p["proposal_id"]))
                    audit(None,"Rejected taxonomy proposal",reviewer,p["code"]); st.rerun()

# ------------------------------- Governance ---------------------------------
else:
    section("Purpose / الغرض")
    st.markdown("A consistent investigation framework for incidents, near misses, unsafe acts, unsafe conditions, process safety events and loss of primary containment (LOPC).")
    section("Analysis levels / مستويات التحليل")
    st.markdown("- **Level 1 – Basic:** event classification, immediate causes, evidence and proportionate action.\n- **Level 2 – Structured:** contributing factors, barrier performance, verified root cause and effectiveness follow-up.\n- **Level 3 – Advanced:** multidisciplinary investigation, causal relationships, human/organizational factors, complex barrier analysis and formal review.")
    section("Mandatory decision rules / قواعد إلزامية")
    st.markdown("1. **Evidence before conclusion:** each material finding must reference verifiable evidence.\n2. **Non-blaming:** investigate system conditions and work context; do not use blame as a root cause.\n3. **Unknown ≠ Not Applicable:** preserve uncertainty explicitly.\n4. **Root cause verification:** Level 2 and 3 require at least one verified root cause before submission.\n5. **Action traceability:** actions should link to findings and failed/degraded barriers where applicable.\n6. **Effectiveness:** an action is not considered fully closed merely because it was implemented; effectiveness must be assessed.\n7. **AI governance:** any future AI output is a hypothesis for investigator review, never a verified finding or approval.")
    section("Workflow / دورة العمل")
    st.code("Draft → Submitted → Under Review → Approved → Closed\n                         ↘ Returned → Revision → Resubmitted",language="text")
    section("Release limitations / حدود الإصدار")
    st.warning("This is a controlled pilot application. Before production deployment, EPP must validate the taxonomy and question bank; configure authenticated user accounts and role-based permissions; establish backup, retention, cybersecurity, document-control and approval rules; and perform UAT with HSE, Operations, Maintenance, Engineering and Process Safety.")

st.markdown("---")
st.caption(f"EPP-UCA | Issue 02 – Rev 00 | Build {APP_VERSION} | Controlled pilot – not an approved production system")
