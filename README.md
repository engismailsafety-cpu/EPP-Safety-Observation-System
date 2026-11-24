# EPP-UCA – Unified Cause Analysis

**Release:** Issue 02 – Rev 00  
**Application build:** 1.0.0  
**Deployment state:** Controlled pilot prototype

## Purpose
A bilingual English/Arabic application for structured, evidence-led, non-blaming, risk-based and barrier-focused analysis of incidents, near misses, unsafe acts/conditions, process safety events and loss of primary containment (LOPC).

## Main modules
- Dashboard and investigation register.
- Event registration with three analysis levels.
- Bilingual structured question bank with conditional questions.
- Causal findings register: immediate causes, contributing factors, root causes and human/organizational factors.
- Barrier analysis: intended function, actual performance, status and evidence reference.
- Corrective/preventive action register linked to findings.
- Review workflow: Draft → Submitted → Under Review → Approved / Returned.
- Action follow-up with implementation evidence and effectiveness assessment.
- Controlled taxonomy proposals and review queue.
- Excel investigation workbook export and audit trail.

## Installation
Use Python 3.10 or later. From this folder:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

The application opens in the browser, normally at `http://localhost:8501`.

## Data storage
The local SQLite database is created at `data/epp_uca.db` on first run. Back up this database regularly while the application is stopped. Do not place the database on an uncontrolled shared drive or expose the Streamlit port to an untrusted network.

## Important governance limitations
This release is a pilot prototype, not a production-ready enterprise system. The operator-name field is not authentication. The current review workflow records reviewer decisions but does not enforce independent role-based access control. There is no secure attachment repository, enterprise SSO, encrypted database, automated backup, retention engine, electronic signature, or full approval delegation. Evidence is currently recorded by reference text. Validate all question-bank content and taxonomy with EPP HSE, Operations, Maintenance, Engineering and Process Safety before controlled pilot use.

Root-cause conclusions must be evidence-supported and reviewed by competent investigators. AI, if integrated in a later release, must remain advisory and cannot verify findings or approve investigations.
