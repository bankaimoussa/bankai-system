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


class Rep(db.Model):
    """
    مندوب مُضاف من الواجهة (بالإضافة للمندوبين الثابتين في data.py).
    بيتحسب تقاطعه مع شيفتات المشرفين بنفس منطق REPS_BY_BRANCH بالظبط.
    """
    __tablename__ = "reps"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(200), nullable=False, index=True)
    email = db.Column(db.String(200), nullable=True)
    branch = db.Column(db.String(20), nullable=False, index=True)
    rep_type = db.Column(db.String(10), nullable=False)   # full | part
    start = db.Column(db.Integer, nullable=False)          # hour 0-23
    end = db.Column(db.Integer, nullable=False)            # hour 0-23 (يُخزن صراحة، مش مشتق من DURATION_HOURS)

    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_rep_dict(self):
        """نفس شكل القواميس الثابتة في data.py عشان يندمج معاها بسهولة."""
        return {
            "name": self.name, "type": self.rep_type,
            "start": self.start, "_end_override": self.end,
            "email": self.email, "db_id": self.id,
        }

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "email": self.email,
            "branch": self.branch, "type": self.rep_type,
            "start": self.start, "end": self.end, "active": self.active,
        }


class CortexRequest(db.Model):
    """
    طلب "Cortex" لجلب بيانات مندوب أوتوماتيك من Amazon Logistics عبر
    الـ Tampermonkey script، وربط الملف اللي بيرجع بتقييم المندوب.

    دورة الحياة: pending -> uploaded -> applied (أو failed).
    - pending: المشرف داس Cortex، لسه الاسكريبت ما جابش الملف.
    - uploaded: الاسكريبت رفع CSV، اتفلتر واتحسب suggested_orders، مستني المشرف يأكد.
    - applied: المشرف قبل الرقم المقترح وانحفظ في orders بتاع الـ Evaluation.
    - failed: الاسكريبت مقدرش يجيب الملف (سبب في error_message).
    """
    __tablename__ = "cortex_requests"

    id = db.Column(db.Integer, primary_key=True)
    request_uid = db.Column(db.String(36), nullable=False, unique=True, index=True)

    # مفتاح التقييم اللي الطلب ده مرتبط بيه
    day = db.Column(db.String(10), nullable=False, index=True)
    branch = db.Column(db.String(20), nullable=False)
    supervisor_id = db.Column(db.String(20), nullable=False)
    supervisor_shift_id = db.Column(db.String(20), nullable=False)

    rep_name = db.Column(db.String(200), nullable=False, index=True)
    short_name = db.Column(db.String(200), nullable=False)  # أول + آخر كلمة، للبحث في Amazon

    status = db.Column(db.String(10), nullable=False, default="pending", index=True)
    # pending | uploaded | applied | failed

    suggested_orders = db.Column(db.Integer, nullable=True)
    raw_row_count = db.Column(db.Integer, nullable=True)      # عدد صفوف Delivered to Customer قبل التفريد
    unique_stop_count = db.Column(db.Integer, nullable=True)  # نفس suggested_orders، محفوظ منفصل للوضوح

    error_message = db.Column(db.String(300), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_at = db.Column(db.DateTime, nullable=True)
    applied_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "request_uid": self.request_uid,
            "day": self.day,
            "branch": self.branch,
            "supervisor_id": self.supervisor_id,
            "supervisor_shift_id": self.supervisor_shift_id,
            "rep_name": self.rep_name,
            "short_name": self.short_name,
            "status": self.status,
            "suggested_orders": self.suggested_orders,
            "raw_row_count": self.raw_row_count,
            "unique_stop_count": self.unique_stop_count,
            "error_message": self.error_message,
        }
