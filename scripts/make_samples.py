"""Generate the demo scenarios: submission JSONs + synthetic PDF documents
(GST certificate, PAN card, cancelled cheque) + the existing vendor master.

Run:  python scripts/make_samples.py
All data is synthetic; GSTINs carry valid checksums so the logic is realistic.
"""
import csv
import json
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.validators import make_gstin  # noqa: E402

SAMPLES = ROOT / "samples"
DOCS = SAMPLES / "docs"
DATA = ROOT / "data"
for p in (SAMPLES, DOCS, DATA):
    p.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------ PDFs ---
def _watermark(c, w, h):
    c.saveState()
    c.setFont("Helvetica", 8)
    c.setFillGray(0.55)
    c.drawString(30, 18, "SYNTHETIC TEST DOCUMENT - generated for a case-study demo, not a real record")
    c.restoreState()


def gst_cert(path, gstin, legal, trade, constitution, address, status="Active"):
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(w / 2, h - 60, "Government of India")
    c.setFont("Helvetica", 11)
    c.drawCentredString(w / 2, h - 80, "Form GST REG-06")
    c.drawCentredString(w / 2, h - 96, "[See Rule 10(1)]")
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(w / 2, h - 122, "Registration Certificate")
    c.setFont("Helvetica", 10)
    c.drawCentredString(w / 2, h - 138, "Goods and Services Tax")
    y = h - 180
    rows = [("Registration Number", gstin), ("Legal Name", legal), ("Trade Name, if any", trade),
            ("Constitution of Business", constitution), ("Address of Principal Place of Business", address),
            ("Date of Liability", "01/04/2021"), ("Type of Registration", "Regular"), ("Status", status)]
    for k, v in rows:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(60, y, f"{k}:")
        c.setFont("Helvetica", 10)
        c.drawString(290, y, v)
        y -= 24
    _watermark(c, w, h)
    c.save()


def pan_card(path, pan, name):
    size = (340, 215)
    c = canvas.Canvas(str(path), pagesize=size)
    c.setFillColorRGB(0.85, 0.92, 1)
    c.rect(0, 0, *size, fill=1, stroke=0)
    c.setFillGray(0)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20, 185, "INCOME TAX DEPARTMENT")
    c.drawRightString(320, 185, "GOVT. OF INDIA")
    c.setFont("Helvetica", 8)
    c.drawString(20, 150, "Permanent Account Number")
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20, 132, pan)
    c.setFont("Helvetica", 9)
    c.drawString(20, 100, f"Name: {name}")
    c.drawString(20, 84, "Date of Incorporation: 12/06/2016")
    c.setFont("Helvetica", 6)
    c.drawString(20, 12, "SYNTHETIC TEST DOCUMENT - not a real record")
    c.save()


def cheque(path, bank, branch, ifsc, account, holder):
    size = landscape((300, 620))
    c = canvas.Canvas(str(path), pagesize=size)
    w, h = size
    c.setFont("Helvetica-Bold", 14)
    c.drawString(24, h - 36, bank)
    c.setFont("Helvetica", 9)
    c.drawString(24, h - 52, f"Branch: {branch}")
    c.drawString(24, h - 66, f"IFSC Code: {ifsc}")
    c.drawRightString(w - 24, h - 36, "Date: __ __ __ __")
    c.setFont("Helvetica", 11)
    c.drawString(24, h - 110, "PAY ______________________________________________ or Bearer")
    c.drawString(24, h - 140, "RUPEES ______________________________________")
    c.drawString(24, h - 180, f"A/C No: {account}")
    c.drawRightString(w - 24, h - 200, f"For: {holder}")
    c.drawRightString(w - 24, h - 240, "Authorised Signatory")
    c.saveState()
    c.setFont("Helvetica-Bold", 54)
    c.setFillColorRGB(0.8, 0.1, 0.1)
    c.translate(w / 2, h / 2 - 20)
    c.rotate(12)
    c.drawCentredString(0, 0, "CANCELLED")
    c.restoreState()
    _watermark(c, w, h)
    c.save()


# ------------------------------------------------------------- scenarios ---
def base(ref, legal, trade, etype, pan, gstin, addr, contact, website, bank, **extra):
    return {"submission_ref": ref, "legal_name": legal, "trade_name": trade, "entity_type": etype, "pan": pan,
            "gstin": gstin, "address": addr, "contact": contact, "website": website, "bank": bank, **extra}


scenarios = []

# 1. HAPPY PATH ------------------------------------------------------------
pan = "AAACN4821K"
g = make_gstin("29", pan)
gst_cert(DOCS / "nimbus_gst_certificate.pdf", g, "NIMBUS LOGISTICS PRIVATE LIMITED", "Nimbus Logistics",
         "Private Limited Company", "42, 2nd Cross, Indiranagar, Bengaluru, Karnataka 560038")
pan_card(DOCS / "nimbus_pan.pdf", pan, "NIMBUS LOGISTICS PRIVATE LIMITED")
cheque(DOCS / "nimbus_cancelled_cheque.pdf", "HDFC Bank", "Indiranagar, Bengaluru", "HDFC0001234",
       "50200012345678", "NIMBUS LOGISTICS PVT. LTD.")
scenarios.append(("01_happy_path", "Happy path: clean, consistent submission", "APPROVED", base(
    "VS-2026-101", "Nimbus Logistics Private Limited", "Nimbus Logistics", "Private Limited Company", pan, g,
    {"line1": "42, 2nd Cross, Indiranagar", "city": "Bengaluru", "state": "Karnataka", "pincode": "560038"},
    {"name": "Priya Raman", "email": "accounts@nimbuslogistics.in", "phone": "+91 98450 12345"},
    "https://nimbuslogistics.in",
    {"account_holder": "NIMBUS LOGISTICS PVT. LTD.", "account_number": "50200012345678", "ifsc": "HDFC0001234",
     "bank_name": "HDFC Bank"}),
    ["nimbus_gst_certificate.pdf", "nimbus_pan.pdf", "nimbus_cancelled_cheque.pdf"]))

# 2. EDGE 1: cross-field inconsistencies (fixable) --------------------------
real_pan = "AAACR7781P"
typo_pan = "AAACR7731P"
g_ka = make_gstin("29", real_pan)
gst_cert(DOCS / "ridgeway_gst_certificate_KA.pdf", g_ka, "RIDGEWAY PACKAGING PRIVATE LIMITED", "Ridgeway Packaging",
         "Private Limited Company", "Plot 17, KIADB Industrial Area, Bengaluru, Karnataka 562123")
pan_card(DOCS / "ridgeway_pan.pdf", real_pan, "RIDGEWAY PACKAGING PRIVATE LIMITED")
cheque(DOCS / "ridgeway_cancelled_cheque_icici.pdf", "ICICI Bank", "Hinjewadi, Pune", "ICIC0004417",
       "441705001122", "RIDGEWAY PACKAGING PVT LTD")
ridgeway_v1 = base(
    "VS-2026-102", "Ridgeway Packaging Private Limited", "Ridgeway Packaging", "Private Limited Company", typo_pan,
    g_ka, {"line1": "Unit 4, Hinjewadi Phase 2", "city": "Pune", "state": "Maharashtra", "pincode": "411057"},
    {"name": "Rohan Kulkarni", "email": "finance@ridgewaypack.com", "phone": "9822012345"},
    "https://ridgewaypack.com",
    {"account_holder": "Ridgeway Packaging Pvt Ltd", "account_number": "441705001122", "ifsc": "ICIC0004417",
     "bank_name": "ICICI Bank"})
scenarios.append(("02_edge_cross_field", "Edge 1: every field valid alone; cross-checks reveal a PAN typo + "
                  "GSTIN from the wrong state", "PENDING", ridgeway_v1,
                  ["ridgeway_gst_certificate_KA.pdf", "ridgeway_pan.pdf", "ridgeway_cancelled_cheque_icici.pdf"]))

# 3. EDGE 2: third-party bank account that belongs to an existing vendor ----
pan = "AAACS5527Q"
g = make_gstin("07", pan)
gst_cert(DOCS / "sunrise_gst_certificate.pdf", g, "SUNRISE OFFICE SUPPLIES PRIVATE LIMITED", "Sunrise Office Supplies",
         "Private Limited Company", "B-14, Okhla Industrial Area Phase 1, New Delhi, Delhi 110020")
pan_card(DOCS / "sunrise_pan.pdf", pan, "SUNRISE OFFICE SUPPLIES PRIVATE LIMITED")
cheque(DOCS / "sunrise_cancelled_cheque.pdf", "State Bank of India", "Karol Bagh, New Delhi", "SBIN0001789",
       "34567890123", "KAVERI TRADERS")
scenarios.append(("03_edge_third_party_bank", "Edge 2: paperwork is genuine, but payments would go to a "
                  "third party's account that already belongs to another vendor", "REJECTED", base(
    "VS-2026-103", "Sunrise Office Supplies Private Limited", "Sunrise Office Supplies", "Private Limited Company",
    pan, g, {"line1": "B-14, Okhla Industrial Area Phase 1", "city": "New Delhi", "state": "Delhi", "pincode": "110020"},
    {"name": "Vikas Mehra", "email": "sunrise.officesupplies@gmail.com", "phone": "9811098765"},
    "https://sunriseofficesupplies.in",
    {"account_holder": "Kaveri Traders", "account_number": "34567890123", "ifsc": "SBIN0001789",
     "bank_name": "Axis Bank"}),
    ["sunrise_gst_certificate.pdf", "sunrise_pan.pdf", "sunrise_cancelled_cheque.pdf"]))

# 4. EDGE 3: wrong documents attached ---------------------------------------
pan = "AAACV3390M"
g = make_gstin("33", pan)
sister_gstin = make_gstin("33", "AAACV3391N")
gst_cert(DOCS / "vertex_gst_certificate.pdf", sister_gstin, "VERTEX ENGINEERING SERVICES PRIVATE LIMITED",
         "Vertex Services", "Private Limited Company", "88, Guindy Industrial Estate, Chennai, Tamil Nadu 600032")
pan_card(DOCS / "vertex_pan.pdf", pan, "VERTEX ENGINEERING SOLUTIONS PRIVATE LIMITED")
# The file is NAMED like a cheque but is actually another PAN card upload
pan_card(DOCS / "vertex_cancelled_cheque.pdf", pan, "VERTEX ENGINEERING SOLUTIONS PRIVATE LIMITED")
scenarios.append(("04_edge_wrong_documents", "Edge 3: form is perfect, but the uploads are wrong: a sister "
                  "company's GST certificate and a 'cheque' file that is actually a PAN card", "PENDING", base(
    "VS-2026-104", "Vertex Engineering Solutions Private Limited", "Vertex Engineering", "Private Limited Company",
    pan, g, {"line1": "88, Guindy Industrial Estate", "city": "Chennai", "state": "Tamil Nadu", "pincode": "600032"},
    {"name": "Karthik Subramanian", "email": "vendor@vertexengg.co.in", "phone": "9840011223"},
    "https://vertexengg.co.in",
    {"account_holder": "Vertex Engineering Solutions Pvt Ltd", "account_number": "918020045566778",
     "ifsc": "UTIB0000072", "bank_name": "Axis Bank"}),
    ["vertex_gst_certificate.pdf", "vertex_pan.pdf", "vertex_cancelled_cheque.pdf"]))

# 5. EDGE 4: resubmission of #2 fixes what was asked AND swaps the bank -----
g_mh = make_gstin("27", real_pan)
gst_cert(DOCS / "ridgeway_gst_certificate_MH.pdf", g_mh, "RIDGEWAY PACKAGING PRIVATE LIMITED", "Ridgeway Packaging",
         "Private Limited Company", "Unit 4, Hinjewadi Phase 2, Pune, Maharashtra 411057")
cheque(DOCS / "ridgeway_cancelled_cheque_yes.pdf", "Yes Bank", "Andheri East, Mumbai", "YESB0000219",
       "021963700004412", "RIDGEWAY PACKAGING PVT LTD")
ridgeway_v2 = json.loads(json.dumps(ridgeway_v1))
ridgeway_v2.update({"pan": real_pan, "gstin": g_mh})
ridgeway_v2["bank"] = {"account_holder": "Ridgeway Packaging Pvt Ltd", "account_number": "021963700004412",
                       "ifsc": "YESB0000219", "bank_name": "Yes Bank"}
scenarios.append(("05_edge_resubmission_bank_swap", "Edge 4 (run AFTER #2): vendor fixes exactly what we asked, "
                  "and quietly changes the bank account too. Every document checks out.", "PENDING", ridgeway_v2,
                  ["ridgeway_gst_certificate_MH.pdf", "ridgeway_pan.pdf", "ridgeway_cancelled_cheque_yes.pdf"]))

# 6. BONUS: proprietorship, account in owner's personal name (legit) --------
pan = "AHXPI6620L"
g = make_gstin("32", pan)
gst_cert(DOCS / "meera_gst_certificate.pdf", g, "MEERA IYER", "Meera Prints", "Proprietorship",
         "21/455, MG Road, Ernakulam, Kochi, Kerala 682016")
pan_card(DOCS / "meera_pan.pdf", pan, "MEERA IYER")
cheque(DOCS / "meera_cancelled_cheque.pdf", "Federal Bank", "MG Road, Kochi", "FDRL0001021", "10210100045678",
       "MEERA IYER")
scenarios.append(("06_bonus_proprietorship", "Bonus: name mismatch that is NOT fraud. A proprietorship paid "
                  "into the owner's personal account. Shows the rules aren't blunt.", "APPROVED", base(
    "VS-2026-106", "Meera Iyer", "Meera Prints", "Proprietorship", pan, g,
    {"line1": "21/455, MG Road, Ernakulam", "city": "Kochi", "state": "Kerala", "pincode": "682016"},
    {"name": "Meera Iyer", "email": "meeraprints.kochi@gmail.com", "phone": "9447012345"}, "",
    {"account_holder": "MEERA IYER", "account_number": "10210100045678", "ifsc": "FDRL0001021",
     "bank_name": "Federal Bank"}, proprietor_name="Meera Iyer"),
    ["meera_gst_certificate.pdf", "meera_pan.pdf", "meera_cancelled_cheque.pdf"]))

for slug, title, expected, sub, docs in scenarios:
    sub = {**sub, "documents": docs}
    meta = {"title": title, "expected": expected, "submission": sub}
    (SAMPLES / f"{slug}.json").write_text(json.dumps(meta, indent=2))

# ------------------------------------------------------------ vendor master ---
master = [
    ("V-1001", "Bharat Steel Fabricators Private Limited", "AAACB1120F", make_gstin("27", "AAACB1120F"), "60112233445", "SBIN0000300"),
    ("V-1017", "Coastal Freight LLP", "AAKFC4410H", make_gstin("33", "AAKFC4410H"), "50100223344556", "HDFC0000540"),
    ("V-1029", "Greenleaf Housekeeping Services Private Limited", "AADCG7781B", make_gstin("29", "AADCG7781B"), "917010022334455", "UTIB0000009"),
    ("V-1042", "Kaveri Traders", "AAFFK2210D", make_gstin("07", "AAFFK2210D"), "34567890123", "SBIN0001789"),
    ("V-1056", "Pinnacle IT Solutions Private Limited", "AAICP9054R", make_gstin("36", "AAICP9054R"), "77889900112", "ICIC0000047"),
    ("V-1063", "Shree Ganesh Printers", "AMVPS3321K", make_gstin("24", "AMVPS3321K"), "20345678901", "BARB0SURATX"),
]
with open(DATA / "vendor_master.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["vendor_id", "legal_name", "pan", "gstin", "bank_account", "ifsc", "status"])
    for r in master:
        w.writerow([*r, "Active"])

scenario_pdf_count = len({filename for _, _, _, _, filenames in scenarios for filename in filenames})
print(f"Wrote {len(scenarios)} scenarios, {scenario_pdf_count} scenario PDFs, {len(master)} vendors")
