# -*- coding: utf-8 -*-
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Evaluation(db.Model):
    """
    تقييم مندوب واحد، بواسطة مشرف واحد، في شيفت مشرف معين، في يوم معين.
    المفتاح المنطقي الفريد: (day, branch, supervisor_id, supervisor_shift_id, rep_name)
    -> ده اللي بيخلي كل مشرف يقيّم نفس المندوب بشكل منفصل تمامًا عن مشرف تاني
       حتى لو نفس المندوب بيتقاطع مع أكتر من شيفت مشرف.
    """
    __tablename__ = "evaluations"

    id = db.Column(db.Integer, primary_key=True)

    day = db.Column(db.String(10), nullable=False, index=True)  # YYYY-MM-DD
    branch = db.Column(db.String(20), nullable=False, index=True)
    supervisor_id = db.Column(db.String(20), nullable=False, index=True)
    supervisor_name = db.Column(db.String(120), nullable=False)
    supervisor_shift_id = db.Column(db.String(20), nullable=False, index=True)

    rep_name = db.Column(db.String(200), nullable=False, index=True)
    rep_type = db.Column(db.String(10), nullable=False)   # full | part
    rep_start = db.Column(db.Integer, nullable=False)      # hour 0-23

    attendance = db.Column(db.String(10), nullable=True)   # present | late | absent
    reason = db.Column(db.String(10), nullable=True)       # with | without
    orders = db.Column(db.Integer, nullable=False, default=0)
    miss = db.Column(db.Integer, nullable=False, default=0)

    saved = db.Column(db.Boolean, nullable=False, default=False)
    closed = db.Column(db.Boolean, nullable=False, default=False)  # اتقفل مع إنهاء الشيفت

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            "day", "branch", "supervisor_id", "supervisor_shift_id", "rep_name",
            name="uq_eval_key",
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "day": self.day,
            "branch": self.branch,
            "supervisor_id": self.supervisor_id,
            "supervisor_name": self.supervisor_name,
            "supervisor_shift_id": self.supervisor_shift_id,
            "rep_name": self.rep_name,
            "rep_type": self.rep_type,
            "rep_start": self.rep_start,
            "attendance": self.attendance,
            "reason": self.reason,
            "orders": self.orders,
            "miss": self.miss,
            "saved": self.saved,
            "closed": self.closed,
        }


class ShiftSession(db.Model):
    """
    سجل بإنهاء شيفت مشرف معين في يوم معين (لما يدوس 'إنهاء الشيفت').
    بيستخدم كمرجع إن الشيفت ده اتقفل، ومنع إعادة الفتح غير عمدًا (اختياري).
    """
    __tablename__ = "shift_sessions"

    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(10), nullable=False, index=True)
    branch = db.Column(db.String(20), nullable=False)
    supervisor_id = db.Column(db.String(20), nullable=False)
    supervisor_name = db.Column(db.String(120), nullable=False)
    supervisor_shift_id = db.Column(db.String(20), nullable=False)
    closed_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            "day", "branch", "supervisor_id", "supervisor_shift_id",
            name="uq_session_key",
        ),
    )


class Fine(db.Model):
    """
    غرامة مالية على مندوب: قيمة بالجنيه + سبب، مرتبطة بيوم/فرع/مشرف/شيفت المشرف
    اللي سجلها (نفس منطق التقييمات) عشان تظهر وتتصدّر مع باقي بيانات الشيفت.
    """
    __tablename__ = "fines"

    id = db.Column(db.Integer, primary_key=True)

    day = db.Column(db.String(10), nullable=False, index=True)
    branch = db.Column(db.String(20), nullable=False, index=True)
    supervisor_id = db.Column(db.String(20), nullable=False, index=True)
    supervisor_name = db.Column(db.String(120), nullable=False)
    supervisor_shift_id = db.Column(db.String(20), nullable=False, index=True)

    rep_name = db.Column(db.String(200), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False, default=0)
    reason = db.Column(db.String(300), nullable=False, default="")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "day": self.day,
            "branch": self.branch,
            "supervisor_id": self.supervisor_id,
            "supervisor_name": self.supervisor_name,
            "supervisor_shift_id": self.supervisor_shift_id,
            "rep_name": self.rep_name,
            "amount": self.amount,
            "reason": self.reason,
        }
