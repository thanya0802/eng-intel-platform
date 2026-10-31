"""Generate the synthetic dataset.
  data/structured/*.csv   requirements -> tests -> results -> failures -> change requests
  data/raw/*.pdf          engineering PDFs + a duplicate + a corrupt file + a scan-like page
  evals/ground_truth.json the known traceability chains
Bad data is deliberate: the quality checks must catch it."""
import csv
import json
import random
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.corpus import DOCS                                  # noqa: E402
from engintel import config                                   # noqa: E402

SUBSYSTEMS = ["battery", "thermal", "brakes", "charging", "adas", "body", "vcu"]
FIXED_REQ = {
    104: ("Thermal runaway shall not propagate between modules for 5 minutes", "battery", "high"),
    109: ("Brake response latency shall be within 120 ms", "brakes", "high"),
    112: ("HV connector shall survive vibration profile V3", "charging", "high"),
    118: ("DC link pre-charge shall complete within 300 ms", "charging", "medium"),
    121: ("Cabin pre-conditioning shall reach 21 C in 15 minutes", "thermal", "low"),
    125: ("Underbody parts shall resist 720 h salt spray", "body", "medium"),
}
# (req, failure, change request, CR status, severity, failure text, CR title)
FAIL_CHAINS = [
    (104, "FAIL-87", "CR-12", "open", "critical", "Propagation to adjacent module at 3.5 min in nail test",
     "Add second mica barrier layer"),
    (109, "FAIL-90", "CR-15", "open", "high", "Latency 138 ms at -40 C on HIL rig", "Revise valve timing calibration"),
    (112, "FAIL-88", "CR-13", "open", "high", "Contact resistance above 5 mOhm after 14 h Z axis", "Silver plating and secondary lock"),
    (125, "FAIL-89", "CR-14", "closed", "medium", "Red rust at 480 h on subframe weld seam", "Add e-coat touch up step"),
    (121, "FAIL-91", None, None, "low", "Reached 21 C in 17 minutes at -20 C ambient", None),
]

def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)

def gen_structured(out: Path):
    rng = random.Random(7)
    today = date.today()
    out.mkdir(parents=True, exist_ok=True)
    reqs, tcs, results, fails, crs = [], [], [], [], []
    fail_by_req = {c[0]: c for c in FAIL_CHAINS}
    res_n = 5000
    for i in range(32):
        n = 100 + i
        title, sub, prio = FIXED_REQ.get(n, (f"Generic requirement {n}", rng.choice(SUBSYSTEMS), rng.choice(["high", "medium", "low"])))
        reqs.append([f"REQ-{n}", title, sub, prio, rng.choice(["approved", "approved", "draft"]) if n not in FIXED_REQ else "approved"])
        if n >= 130:
            continue                                   # REQ-130, REQ-131: no test coverage (gap)
        tc_ids = [f"TC-{200 + i}"] + ([f"TC-{250 + i}"] if i % 2 == 0 else [])
        for tc in tc_ids:
            tcs.append([tc, f"REQ-{n}", f"Verify {title.lower()}"])
            for k in range(rng.randint(1, 2)):
                results.append([f"RES-{res_n}", tc, "pass", str(today - timedelta(days=rng.randint(5, 25)))]); res_n += 1
        if n in fail_by_req:
            _, fid, crid, status, sev, ftxt, crtitle = fail_by_req[n]
            rid = f"RES-{res_n}"; res_n += 1
            results.append([rid, tc_ids[0], "fail", str(today - timedelta(days=rng.randint(1, 4)))])
            fails.append([fid, rid, tc_ids[0], ftxt, sev, str(today - timedelta(days=1))])
            if crid:
                crs.append([crid, fid, crtitle, status, str(today)])
    # ---- deliberate bad data ----
    reqs.append(["REQ-107", "Generic requirement 107 (revised title)", "vcu", "medium", "approved"])  # duplicate key
    # missing required title -> rejected (REQ-129 already exists, so the original row is kept)
    reqs.append(["REQ-129", "", "body", "low", "draft"])
    tcs.append(["TC-299", "REQ-999", "Orphan test for a requirement that does not exist"])           # orphan
    write_csv(out / "requirements.csv", ["req_id", "title", "subsystem", "priority", "status"], reqs)
    write_csv(out / "test_cases.csv", ["tc_id", "req_id", "title"], tcs)
    write_csv(out / "test_results.csv", ["result_id", "tc_id", "outcome", "run_date"], results)
    write_csv(out / "failure_logs.csv", ["fail_id", "result_id", "tc_id", "description", "severity", "logged_at"], fails)
    write_csv(out / "change_requests.csv", ["cr_id", "fail_id", "title", "status", "opened_at"], crs)
    (out / "test_results__late_batch.csv").write_text(          # malformed: ragged rows
        "result_id,tc_id,outcome,run_date\nRES-9001,TC-201,pass\nRES-9002,TC-202,fail,2026-01-01,extra\n")
    return {
        "open_chain_requirements": sorted(f"REQ-{c[0]}" for c in FAIL_CHAINS if c[3] == "open"),
        "closed_chain_requirements": sorted(f"REQ-{c[0]}" for c in FAIL_CHAINS if c[3] == "closed"),
        "chains": [{"req": f"REQ-{c[0]}", "tc": f"TC-{200 + c[0] - 100}", "fail": c[1], "cr": c[2],
                    "cr_status": c[3]} for c in FAIL_CHAINS],
        "uncovered_requirements": ["REQ-130", "REQ-131"],
        "expected_quality_failures": ["duplicate_key:requirements:REQ-107", "required_fields:requirements:REQ-129",
                                      "ref_integrity_test_to_req:TC-299", "file_schema:test_results__late_batch.csv"],
    }

def make_pdf(path: Path, title, sections):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    ss = getSampleStyleSheet()
    story = [Paragraph(title, ss["Title"]), Spacer(1, 8)]
    for heading, body in sections:
        story.append(Paragraph(heading, ss["Heading2"]))
        if isinstance(body, list):
            t = Table(body)
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
            story.append(t)
        else:
            story.append(Paragraph(body, ss["BodyText"]))
        story.append(Spacer(1, 6))
    SimpleDocTemplate(str(path), pagesize=letter, title=title).build(story)

def make_scan_like_pdf(path: Path):
    """A page with only vector shapes and no text layer, like a scanned image. Must be flagged needs_ocr."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=letter)
    for i in range(12):
        c.rect(60, 700 - i * 50, 480, 30, stroke=0, fill=1 if i % 2 else 0)
    c.showPage(); c.save()

def gen_pdfs(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    for name, title, sections in DOCS:
        make_pdf(out / name, title, sections)
    shutil.copy(out / DOCS[0][0], out / "battery_thermal_design_spec_COPY.pdf")   # duplicate upload
    (out / "corrupt_upload.pdf").write_bytes(b"%PDF-1.4\n%garbage bytes, truncated upload\n")  # corrupt
    make_scan_like_pdf(out / "scanned_wiring_diagram.pdf")                       # no text layer

if __name__ == "__main__":
    for d in (config.RAW_DIR, config.STRUCTURED_DIR):
        if d.exists():
            shutil.rmtree(d)
    gt = gen_structured(config.STRUCTURED_DIR)
    gen_pdfs(config.RAW_DIR)
    gt_path = config.ROOT / "evals" / "ground_truth.json"
    gt_path.write_text(json.dumps(gt, indent=2))
    print(f"structured -> {config.STRUCTURED_DIR}\npdfs -> {config.RAW_DIR}\nground truth -> {gt_path}")
