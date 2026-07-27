# -*- coding: utf-8 -*-
import os
import io
from datetime import datetime, date

from flask import Flask, request, jsonify, render_template, Response

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from models import db, Evaluation, ShiftSession, Fine, Rep
import data as D

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'bankai.db')}"
).replace("postgres://", "postgresql://", 1)  # Railway بيدي postgres:// أحيانًا
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

def get_supervisor(branch, supervisor_id):
    """يرجع بيانات المشرف (بما فيها shift_id الثابت بتاعه) أو None."""
    b = D.BRANCHES.get(branch)
    if not b:
        return None
    for s in b["supervisors"]:
        if s["id"] == supervisor_id:
            return s
    return None


with app.app_context():
    db.create_all()


# ============================================================
# Pages
# ============================================================
@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
# Static config data (branches, supervisors, shifts)
# ============================================================
@app.route("/api/branches")
def api_branches():
    return jsonify({
        "branches": {
            bid: {"label": b["label"], "supervisors": b["supervisors"]}
            for bid, b in D.BRANCHES.items()
        },
        "supervisor_shifts": D.SUPERVISOR_SHIFTS,
    })


# ============================================================
# Reps management (إضافة مندوبين من الواجهة)
# ============================================================
@app.route("/api/manage_reps")
def api_manage_reps_list():
    branch = request.args.get("branch", "")
    q = Rep.query.filter_by(active=True)
    if branch:
        q = q.filter_by(branch=branch)
    reps = q.order_by(Rep.created_at.desc()).all()
    return jsonify({"reps": [r.to_dict() for r in reps]})


@app.route("/api/manage_reps", methods=["POST"])
def api_manage_reps_add():
    payload = request.get_json(force=True) or {}
    required = ["name", "branch", "rep_type", "start", "end"]
    missing = [k for k in required if k not in payload]
    if missing:
        return jsonify({"error": f"missing: {missing}"}), 400

    name = str(payload["name"]).strip()
    branch = payload["branch"]
    rep_type = payload["rep_type"]
    email = (payload.get("email") or "").strip() or None

    if not name:
        return jsonify({"error": "invalid_name"}), 400
    if branch not in D.BRANCHES:
        return jsonify({"error": "invalid_branch"}), 400
    if rep_type not in ("full", "part"):
        return jsonify({"error": "invalid_type"}), 400
    try:
        start = int(payload["start"])
        end = int(payload["end"])
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_hours"}), 400
    if not (0 <= start <= 23) or not (0 <= end <= 23):
        return jsonify({"error": "invalid_hours"}), 400

    rep = Rep(name=name, email=email, branch=branch, rep_type=rep_type, start=start, end=end)
    db.session.add(rep)
    db.session.commit()
    return jsonify({"ok": True, "rep": rep.to_dict()})


@app.route("/api/manage_reps/<int:rep_id>", methods=["DELETE"])
def api_manage_reps_delete(rep_id):
    rep = Rep.query.get(rep_id)
    if rep:
        rep.active = False
        db.session.commit()
    return jsonify({"ok": True})


# ============================================================
# Reps overlapping a supervisor's shift, merged with saved evaluations
# ============================================================
@app.route("/api/reps")
def api_reps():
    branch = request.args.get("branch", "")
    supervisor_id = request.args.get("supervisor_id", "")
    supervisor_shift_id = request.args.get("shift_id", "")
    day = request.args.get("day", "")

    if not all([branch, supervisor_id, supervisor_shift_id, day]):
        return jsonify({"error": "missing params"}), 400

    reps = D.get_overlapping_reps(
        branch, supervisor_shift_id,
        extra_reps=[r.to_rep_dict() for r in Rep.query.filter_by(branch=branch, active=True).all()],
    )

    # هات التقييمات المحفوظة لنفس (اليوم/الفرع/المشرف/شيفته)
    evals = Evaluation.query.filter_by(
        day=day, branch=branch,
        supervisor_id=supervisor_id,
        supervisor_shift_id=supervisor_shift_id,
    ).all()
    evals_by_name = {e.rep_name: e for e in evals}

    session = ShiftSession.query.filter_by(
        day=day, branch=branch,
        supervisor_id=supervisor_id,
        supervisor_shift_id=supervisor_shift_id,
    ).first()

    out = []
    for rep in reps:
        ev = evals_by_name.get(rep["name"])
        out.append({
            "name": rep["name"],
            "type": rep["type"],
            "start": rep["start"],
            "end_hour": D.rep_end_hour(rep) % 24,
            "attendance": ev.attendance if ev else None,
            "reason": ev.reason if ev else None,
            "orders": ev.orders if ev else 0,
            "miss": ev.miss if ev else 0,
            "saved": ev.saved if ev else False,
        })

    return jsonify({
        "reps": out,
        "shift_closed": session is not None,
    })


# ============================================================
# Save / upsert a single rep evaluation
# ============================================================
@app.route("/api/evaluate", methods=["POST"])
def api_evaluate():
    payload = request.get_json(force=True) or {}

    required = ["branch", "supervisor_id", "supervisor_name", "supervisor_shift_id",
                "day", "rep_name", "rep_type", "rep_start"]
    missing = [k for k in required if k not in payload]
    if missing:
        return jsonify({"error": f"missing: {missing}"}), 400

    # امنع الحفظ لو الشيفت اتقفل بالفعل
    session = ShiftSession.query.filter_by(
        day=payload["day"], branch=payload["branch"],
        supervisor_id=payload["supervisor_id"],
        supervisor_shift_id=payload["supervisor_shift_id"],
    ).first()
    if session:
        return jsonify({"error": "shift_closed"}), 409

    ev = Evaluation.query.filter_by(
        day=payload["day"], branch=payload["branch"],
        supervisor_id=payload["supervisor_id"],
        supervisor_shift_id=payload["supervisor_shift_id"],
        rep_name=payload["rep_name"],
    ).first()

    if not ev:
        ev = Evaluation(
            day=payload["day"], branch=payload["branch"],
            supervisor_id=payload["supervisor_id"],
            supervisor_name=payload["supervisor_name"],
            supervisor_shift_id=payload["supervisor_shift_id"],
            rep_name=payload["rep_name"],
            rep_type=payload["rep_type"],
            rep_start=payload["rep_start"],
        )
        db.session.add(ev)

    if "attendance" in payload:
        ev.attendance = payload["attendance"]
    if "reason" in payload:
        ev.reason = payload["reason"]
    if "orders" in payload:
        ev.orders = max(0, int(payload["orders"]))
    if "miss" in payload:
        ev.miss = max(0, int(payload["miss"]))
    if "saved" in payload:
        ev.saved = bool(payload["saved"])

    db.session.commit()
    return jsonify({"ok": True, "evaluation": ev.to_dict()})


# ============================================================
# Reset a single rep's evaluation for the day
# ============================================================
@app.route("/api/reset", methods=["POST"])
def api_reset():
    payload = request.get_json(force=True) or {}
    ev = Evaluation.query.filter_by(
        day=payload.get("day"), branch=payload.get("branch"),
        supervisor_id=payload.get("supervisor_id"),
        supervisor_shift_id=payload.get("supervisor_shift_id"),
        rep_name=payload.get("rep_name"),
    ).first()
    if ev:
        db.session.delete(ev)
        db.session.commit()
    return jsonify({"ok": True})


# ============================================================
# Close shift -> lock evaluations + return CSV export
# ============================================================
@app.route("/api/close_shift", methods=["POST"])
def api_close_shift():
    payload = request.get_json(force=True) or {}
    required = ["branch", "supervisor_id", "supervisor_name", "supervisor_shift_id", "day"]
    missing = [k for k in required if k not in payload]
    if missing:
        return jsonify({"error": f"missing: {missing}"}), 400

    existing = ShiftSession.query.filter_by(
        day=payload["day"], branch=payload["branch"],
        supervisor_id=payload["supervisor_id"],
        supervisor_shift_id=payload["supervisor_shift_id"],
    ).first()
    if not existing:
        session = ShiftSession(
            day=payload["day"], branch=payload["branch"],
            supervisor_id=payload["supervisor_id"],
            supervisor_name=payload["supervisor_name"],
            supervisor_shift_id=payload["supervisor_shift_id"],
        )
        db.session.add(session)

    evals = Evaluation.query.filter_by(
        day=payload["day"], branch=payload["branch"],
        supervisor_id=payload["supervisor_id"],
        supervisor_shift_id=payload["supervisor_shift_id"],
    ).all()
    for ev in evals:
        ev.closed = True

    db.session.commit()
    return jsonify({"ok": True})


# ============================================================
# Fines (الغرامات)
# ============================================================
@app.route("/api/fines")
def api_fines_list():
    branch = request.args.get("branch", "")
    supervisor_id = request.args.get("supervisor_id", "")
    supervisor_shift_id = request.args.get("shift_id", "")
    day = request.args.get("day", "")

    if not all([branch, supervisor_id, supervisor_shift_id, day]):
        return jsonify({"error": "missing params"}), 400

    fines = Fine.query.filter_by(
        day=day, branch=branch,
        supervisor_id=supervisor_id,
        supervisor_shift_id=supervisor_shift_id,
    ).order_by(Fine.created_at.desc()).all()

    return jsonify({"fines": [f.to_dict() for f in fines]})


@app.route("/api/fines", methods=["POST"])
def api_fines_add():
    payload = request.get_json(force=True) or {}
    required = ["branch", "supervisor_id", "supervisor_name", "supervisor_shift_id",
                "day", "rep_name", "amount"]
    missing = [k for k in required if k not in payload]
    if missing:
        return jsonify({"error": f"missing: {missing}"}), 400

    session = ShiftSession.query.filter_by(
        day=payload["day"], branch=payload["branch"],
        supervisor_id=payload["supervisor_id"],
        supervisor_shift_id=payload["supervisor_shift_id"],
    ).first()
    if session:
        return jsonify({"error": "shift_closed"}), 409

    try:
        amount = float(payload["amount"])
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_amount"}), 400
    if amount <= 0:
        return jsonify({"error": "invalid_amount"}), 400

    fine = Fine(
        day=payload["day"], branch=payload["branch"],
        supervisor_id=payload["supervisor_id"],
        supervisor_name=payload["supervisor_name"],
        supervisor_shift_id=payload["supervisor_shift_id"],
        rep_name=payload["rep_name"],
        amount=amount,
        reason=(payload.get("reason") or "").strip(),
    )
    db.session.add(fine)
    db.session.commit()
    return jsonify({"ok": True, "fine": fine.to_dict()})


@app.route("/api/fines/<int:fine_id>", methods=["DELETE"])
def api_fines_delete(fine_id):
    fine = Fine.query.get(fine_id)
    if fine:
        db.session.delete(fine)
        db.session.commit()
    return jsonify({"ok": True})


# ============================================================
# Export -> ملف Excel منظم بشيتين: التقييمات + الغرامات
# ============================================================
HEADER_FILL = PatternFill("solid", fgColor="1E3A8A")
HEADER_FONT = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="Calibri", size=16, bold=True, color="1E3A8A")
SUBTITLE_FONT = Font(name="Calibri", size=11, color="475569")
THIN = Side(style="thin", color="CBD5E1")
CELL_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="right", vertical="center", wrap_text=True)

ROW_FILL_EVEN = PatternFill("solid", fgColor="F1F5F9")
ROW_FILL_PRESENT = PatternFill("solid", fgColor="DCFCE7")
ROW_FILL_LATE = PatternFill("solid", fgColor="FEF3C7")
ROW_FILL_ABSENT = PatternFill("solid", fgColor="FEE2E2")
FINE_FILL = PatternFill("solid", fgColor="FEE2E2")


def _sheet_header(ws, title, subtitle, ncols):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    c = ws.cell(row=1, column=1, value=title)
    c.font = TITLE_FONT
    c.alignment = Alignment(horizontal="right", vertical="center")
    ws.row_dimensions[1].height = 26

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncols)
    c2 = ws.cell(row=2, column=1, value=subtitle)
    c2.font = SUBTITLE_FONT
    c2.alignment = Alignment(horizontal="right", vertical="center")
    ws.row_dimensions[2].height = 20
    ws.sheet_view.rightToLeft = True


def _write_table_header(ws, row, headers):
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=i, value=h)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = CENTER
        c.border = CELL_BORDER
    ws.row_dimensions[row].height = 22


# ============================================================
# Export -> ملف Excel بنفس منظر الشيت الأصلي (full/part + الاسم + start)
# مع إضافة أعمدة الأوردرات / MISS / الغرامات جنب كل مندوب
# ============================================================
HEADER_FILL = PatternFill("solid", fgColor="FFF200")   # أصفر زي الصورة
HEADER_FONT = Font(name="Calibri", size=12, bold=True, color="000000")
TITLE_FONT = Font(name="Calibri", size=16, bold=True, color="1E3A8A")
SUBTITLE_FONT = Font(name="Calibri", size=11, color="475569")
THIN = Side(style="thin", color="CBD5E1")
CELL_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="right", vertical="center", wrap_text=True)

FULL_TYPE_FILL = PatternFill("solid", fgColor="E8DDF7")    # بنفسجي فاتح لصفوف الفول تايم
FULL_TYPE_FILL_ALT = PatternFill("solid", fgColor="F3ECFA")  # تبادل أفتح شوية
PART_TYPE_FILL = PatternFill("solid", fgColor="9B59B6")    # أرجواني غامق لبادچ البارت تايم
PART_ROW_FILL = PatternFill("solid", fgColor="F0E6F7")
FULL_BADGE_FILL = PatternFill("solid", fgColor="EDE7F6")
FINE_FILL = PatternFill("solid", fgColor="FEE2E2")

FULL_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")


def _sheet_header(ws, title, subtitle, ncols):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    c = ws.cell(row=1, column=1, value=title)
    c.font = TITLE_FONT
    c.alignment = Alignment(horizontal="right", vertical="center")
    ws.row_dimensions[1].height = 26

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncols)
    c2 = ws.cell(row=2, column=1, value=subtitle)
    c2.font = SUBTITLE_FONT
    c2.alignment = Alignment(horizontal="right", vertical="center")
    ws.row_dimensions[2].height = 20
    ws.sheet_view.rightToLeft = True


def _write_table_header(ws, row, headers, fill=None):
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=i, value=h)
        c.font = HEADER_FONT
        c.fill = fill or HEADER_FILL
        c.alignment = CENTER
        c.border = CELL_BORDER
    ws.row_dimensions[row].height = 22


@app.route("/api/export_csv")
def api_export_csv():
    branch = request.args.get("branch", "")
    supervisor_id = request.args.get("supervisor_id", "")
    supervisor_shift_id = request.args.get("shift_id", "")
    day = request.args.get("day", "")

    reps = D.get_overlapping_reps(
        branch, supervisor_shift_id,
        extra_reps=[r.to_rep_dict() for r in Rep.query.filter_by(branch=branch, active=True).all()],
    )

    evals = Evaluation.query.filter_by(
        day=day, branch=branch,
        supervisor_id=supervisor_id,
        supervisor_shift_id=supervisor_shift_id,
    ).all()
    eval_by_name = {e.rep_name: e for e in evals}

    fines = Fine.query.filter_by(
        day=day, branch=branch,
        supervisor_id=supervisor_id,
        supervisor_shift_id=supervisor_shift_id,
    ).order_by(Fine.created_at).all()
    fines_by_name = {}
    for f in fines:
        fines_by_name.setdefault(f.rep_name, []).append(f)

    branch_label = D.BRANCHES.get(branch, {}).get("label", branch)
    shift = D.get_supervisor_shift(supervisor_shift_id)
    shift_label = shift["label"] if shift else supervisor_shift_id
    sup_name = evals[0].supervisor_name if evals else (fines[0].supervisor_name if fines else "")
    subtitle = f"الفرع: {branch_label}   |   المشرف: {sup_name}   |   الشيفت: {shift_label}   |   اليوم: {day}"

    # ترتيب زي الصورة: full time الأول (مرتبين بالـ start)، بعدين part time (مرتبين بالـ start)
    reps_sorted = sorted(reps, key=lambda r: (0 if r["type"] == "full" else 1, r["start"]))

    wb = Workbook()

    # ---------------- Sheet 1: full / part - DA Name - start + الأداء ----------------
    ws = wb.active
    ws.title = "المندوبين"
    headers = ["full / part", "DA Name", "start", "الأوردرات", "MISS", "الغرامات (جنيه)"]
    ncols = len(headers)
    _sheet_header(ws, "BANKAI - جدول المندوبين", subtitle, ncols)

    header_row = 4
    _write_table_header(ws, header_row, headers)

    # data validation (dropdown) لعمود full/part زي الشيت الأصلي بالظبط
    dv = DataValidation(type="list", formula1='"full time,part time"', allow_blank=True)
    ws.add_data_validation(dv)

    r = header_row + 1
    full_count = part_count = 0
    for rep in reps_sorted:
        ev = eval_by_name.get(rep["name"])
        rep_fines = fines_by_name.get(rep["name"], [])
        fine_total = sum(f.amount for f in rep_fines)

        orders = ev.orders if ev else 0
        miss = ev.miss if ev else 0
        type_label = "full time" if rep["type"] == "full" else "part time"

        # عمود 1: البادچ (dropdown)
        c1 = ws.cell(row=r, column=1, value=type_label)
        c1.font = FULL_FONT if rep["type"] == "full" else Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        c1.fill = PART_TYPE_FILL if rep["type"] == "part" else PatternFill("solid", fgColor="6C3FA8")
        c1.alignment = CENTER
        c1.border = CELL_BORDER
        dv.add(c1)

        # عمود 2: الاسم
        c2 = ws.cell(row=r, column=2, value=rep["name"])
        c2.font = Font(name="Calibri", size=11, bold=True)
        c2.alignment = LEFT
        c2.border = CELL_BORDER

        # عمود 3: start
        c3 = ws.cell(row=r, column=3, value=rep["start"])
        c3.font = Font(name="Calibri", size=11, bold=True)
        c3.alignment = CENTER
        c3.border = CELL_BORDER

        # عمود 4: الأوردرات
        c4 = ws.cell(row=r, column=4, value=orders)
        c4.alignment = CENTER
        c4.border = CELL_BORDER
        c4.font = Font(name="Calibri", size=11)

        # عمود 5: MISS
        c5 = ws.cell(row=r, column=5, value=miss)
        c5.alignment = CENTER
        c5.border = CELL_BORDER
        c5.font = Font(name="Calibri", size=11, color="DC2626" if miss > 0 else "000000")

        # عمود 6: الغرامات
        c6 = ws.cell(row=r, column=6, value=fine_total if fine_total else 0)
        c6.alignment = CENTER
        c6.border = CELL_BORDER
        c6.number_format = "#,##0.00"
        c6.font = Font(name="Calibri", size=11, bold=fine_total > 0, color="DC2626" if fine_total > 0 else "000000")

        row_fill = PART_ROW_FILL if rep["type"] == "part" else (FULL_TYPE_FILL if r % 2 == 0 else FULL_TYPE_FILL_ALT)
        for c in (c2, c3, c4, c5, c6):
            if not c.fill or c.fill.fgColor.rgb in (None, "00000000"):
                c.fill = row_fill

        if rep["type"] == "full":
            full_count += 1
        else:
            part_count += 1
        r += 1

    if reps_sorted:
        total_row = r
        ws.cell(row=total_row, column=1, value=f"الإجمالي ({full_count} فل / {part_count} بارت)").font = Font(bold=True, size=10)
        ws.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=3)
        ws.cell(row=total_row, column=1).alignment = Alignment(horizontal="right", vertical="center")
        c_orders = ws.cell(row=total_row, column=4, value=f"=SUM(D{header_row+1}:D{r-1})")
        c_miss = ws.cell(row=total_row, column=5, value=f"=SUM(E{header_row+1}:E{r-1})")
        c_fines = ws.cell(row=total_row, column=6, value=f"=SUM(F{header_row+1}:F{r-1})")
        c_fines.number_format = "#,##0.00"
        for c in (ws.cell(row=total_row, column=1), c_orders, c_miss, c_fines):
            c.font = Font(bold=True)
            c.border = CELL_BORDER
            c.fill = PatternFill("solid", fgColor="E2E8F0")
            c.alignment = CENTER
    else:
        ws.cell(row=header_row + 1, column=1, value="لا يوجد مندوبين لهذا الشيفت")
        ws.merge_cells(start_row=header_row+1, start_column=1, end_row=header_row+1, end_column=ncols)
        ws.cell(row=header_row+1, column=1).alignment = CENTER

    col_widths = [14, 30, 8, 12, 8, 16]
    for i, w in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = f"A{header_row+1}"

    # ---------------- Sheet 2: الغرامات (تفصيلي بالسبب) ----------------
    ws2 = wb.create_sheet("الغرامات")
    headers2 = ["#", "المندوب", "المبلغ (جنيه)", "السبب"]
    ncols2 = len(headers2)
    _sheet_header(ws2, "BANKAI - تقرير الغرامات", subtitle, ncols2)

    header_row2 = 4
    _write_table_header(ws2, header_row2, headers2, fill=PatternFill("solid", fgColor="1E3A8A"))
    for c in ws2[header_row2]:
        c.font = Font(name="Calibri", size=12, bold=True, color="FFFFFF")

    r2 = header_row2 + 1
    for idx, f in enumerate(fines, start=1):
        values = [idx, f.rep_name, f.amount, f.reason or "-"]
        row_fill = FINE_FILL if idx % 2 == 1 else None
        for ci, v in enumerate(values, start=1):
            c = ws2.cell(row=r2, column=ci, value=v)
            c.border = CELL_BORDER
            c.alignment = CENTER if ci != 4 else LEFT
            c.font = Font(name="Calibri", size=11)
            if ci == 3:
                c.number_format = "#,##0.00"
            if row_fill:
                c.fill = row_fill
        r2 += 1

    if fines:
        total_row2 = r2
        ws2.cell(row=total_row2, column=1, value="إجمالي الغرامات").font = Font(bold=True)
        ws2.merge_cells(start_row=total_row2, start_column=1, end_row=total_row2, end_column=2)
        ws2.cell(row=total_row2, column=1).alignment = Alignment(horizontal="right", vertical="center")
        c_total = ws2.cell(row=total_row2, column=3, value=f"=SUM(C{header_row2+1}:C{r2-1})")
        c_total.number_format = "#,##0.00"
        for c in (ws2.cell(row=total_row2, column=1), c_total, ws2.cell(row=total_row2, column=4)):
            c.font = Font(bold=True)
            c.border = CELL_BORDER
            c.fill = PatternFill("solid", fgColor="FCA5A5")
            c.alignment = CENTER
    else:
        ws2.cell(row=header_row2 + 1, column=1, value="لا توجد غرامات مسجلة لهذا الشيفت")
        ws2.merge_cells(start_row=header_row2+1, start_column=1, end_row=header_row2+1, end_column=ncols2)
        ws2.cell(row=header_row2+1, column=1).alignment = CENTER

    col_widths2 = [5, 28, 16, 40]
    for i, w in enumerate(col_widths2, start=1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    ws2.freeze_panes = f"A{header_row2+1}"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    fname = f"bankai-{branch}-{supervisor_id}-{day}-{supervisor_shift_id}.xlsx"
    return Response(
        buf.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
