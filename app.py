# -*- coding: utf-8 -*-
import os
import csv
import io
from datetime import datetime, date

from flask import Flask, request, jsonify, render_template, Response

from models import db, Evaluation, ShiftSession
import data as D

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'bankai.db')}"
).replace("postgres://", "postgresql://", 1)  # Railway بيدي postgres:// أحيانًا
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

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

    reps = D.get_overlapping_reps(branch, supervisor_shift_id)

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


@app.route("/api/export_csv")
def api_export_csv():
    branch = request.args.get("branch", "")
    supervisor_id = request.args.get("supervisor_id", "")
    supervisor_shift_id = request.args.get("shift_id", "")
    day = request.args.get("day", "")

    evals = Evaluation.query.filter_by(
        day=day, branch=branch,
        supervisor_id=supervisor_id,
        supervisor_shift_id=supervisor_shift_id,
    ).order_by(Evaluation.rep_start).all()

    buf = io.StringIO()
    buf.write("\ufeff")  # BOM عشان اكسيل يقرأ العربي صح
    writer = csv.writer(buf)
    writer.writerow(["المندوب", "النوع", "بداية الشيفت", "الحضور", "السبب", "الأوردرات", "MISS"])
    for e in evals:
        writer.writerow([
            e.rep_name,
            "دوام كامل" if e.rep_type == "full" else "دوام جزئي",
            f"{e.rep_start}:00",
            {"present": "حضر", "late": "تأخير", "absent": "غياب"}.get(e.attendance, "-"),
            {"with": "بسبب", "without": "بدون سبب"}.get(e.reason, "-"),
            e.orders,
            e.miss,
        ])

    shift = D.get_supervisor_shift(supervisor_shift_id)
    fname = f"bankai-{branch}-{supervisor_id}-{day}-{supervisor_shift_id}.csv"

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
