# -*- coding: utf-8 -*-
"""
بيانات ثابتة: الفروع، المشرفين، المندوبين، وشيفتات المشرفين.
لاحقًا ممكن ننقل دول لجداول DB لو احتجنا نضيف/نعدل من غير كود.
"""

# ============ شيفتات المشرفين (ثابتة لكل الفروع) ============
# start/end بالساعة (24h). الشيفت اللي بيعدي نص الليل: end < start
SUPERVISOR_SHIFTS = [
    {"id": "sup_2_10", "label": "2:00 ص - 10:00 ص", "start": 2, "end": 10},
    {"id": "sup_10_6", "label": "10:00 ص - 6:00 م", "start": 10, "end": 18},
    {"id": "sup_6_2", "label": "6:00 م - 2:00 ص", "start": 18, "end": 2},
]

# ============ الفروع والمشرفين ============
BRANCHES = {
    "qcd1": {"label": "QCD 1 - الفرع الأول", "supervisors": [
        {"id": "S-001", "name": "محمد أحمد"},
        {"id": "S-002", "name": "علي حسن"},
        {"id": "S-003", "name": "ياسر محمود"},
    ]},
    "qcd2": {"label": "QCD 2 - الفرع الثاني", "supervisors": [
        {"id": "S-004", "name": "Saad"},
        {"id": "S-005", "name": "Bankai"},
        {"id": "S-006", "name": "Taha"},
    ]},
}

# ============ مدة الشيفت حسب نوع الدوام ============
DURATION_HOURS = {
    "full": 11,
    "part": 5,
}

# ============ مندوبين QCD 2 (من الجدول اللي اتبعت) ============
# type: full | part | start: ساعة البداية (24h)
REPS_QCD2 = [
    {"name": "Mohammed Hamdy Abuzaid", "type": "full", "start": 9},
    {"name": "Adham Magdy Abdelsalam", "type": "full", "start": 9},
    {"name": "Ayman Elsayed Soliman", "type": "full", "start": 9},
    {"name": "Ashraf Elsayed Mohamed", "type": "full", "start": 9},
    {"name": "Sameh Attya Maqsed", "type": "full", "start": 10},
    {"name": "Ahmed Abdelqader Othman", "type": "part", "start": 11},
    {"name": "yousef ahmed mohamed", "type": "part", "start": 11},
    {"name": "Ammar Abdelkader", "type": "full", "start": 12},
    {"name": "Mohamed Saber Fadl", "type": "full", "start": 12},
    {"name": "Abdelkader Elsayed Abdelkader", "type": "full", "start": 12},
    {"name": "Gorge Ramzy Masoud", "type": "full", "start": 12},
    {"name": "Mohamed Mostafa Saad", "type": "full", "start": 12},
    {"name": "Mohamed Elaqel Ghareb", "type": "full", "start": 12},
    {"name": "Ahmed Kareem Ahmed", "type": "full", "start": 12},
    {"name": "Ahmed Fouad Abdo", "type": "full", "start": 12},
    {"name": "Ahmed Wagdy Ahmed", "type": "full", "start": 12},
    {"name": "Youssef Mohamed Azhar", "type": "full", "start": 14},
    {"name": "Ahmed Ali Elsayed", "type": "full", "start": 14},
    {"name": "Ahmed Hamdy Abdelmaksoud", "type": "part", "start": 15},
    {"name": "Ahmed Mohamed Hamed", "type": "part", "start": 15},
    {"name": "Ahmed Mohamed Soliman", "type": "part", "start": 15},
    {"name": "Hassan Gomaa Ali", "type": "part", "start": 15},
    {"name": "Kareem Mohamed Abdelnaby", "type": "part", "start": 15},
    {"name": "Mahmoud Nabil Mohamed", "type": "full", "start": 15},
    {"name": "Marwan Ibrahim Gaber", "type": "full", "start": 15},
    {"name": "Mohamed Shaban Saeed", "type": "full", "start": 15},
    {"name": "Rofaael Romany Shhata", "type": "part", "start": 15},
    {"name": "Khaled Mohamed Mohamed", "type": "part", "start": 15},
    {"name": "Mohamed Saeed Mohamed", "type": "part", "start": 15},
    {"name": "Hossam Ahmed Naguib", "type": "full", "start": 15},
    {"name": "Ahmed Saber Hussien", "type": "full", "start": 15},
    {"name": "Wesam Ali Abdelmonaem", "type": "full", "start": 15},
    {"name": "Mohammed Tarek Abdelrazek", "type": "full", "start": 15},
    {"name": "Mohamed Mostafa Mahmoud", "type": "full", "start": 15},
    {"name": "Hossam Mohamed Ali", "type": "full", "start": 18},
    {"name": "Mahmoud Mohamed Badry", "type": "full", "start": 21},
    {"name": "Amr Ahmed Elsayed", "type": "full", "start": 21},
    {"name": "Moamen Ashraf Elsayed", "type": "full", "start": 23},
    {"name": "Moamen Mahmoud Awad", "type": "full", "start": 23},
    {"name": "Moamen Farag Ibrahim", "type": "full", "start": 23},
    {"name": "Ibrahim Ali Ibrahim", "type": "full", "start": 23},
    {"name": "Mohammed Mansour", "type": "full", "start": 23},
    {"name": "Kareem Ragab Mohammed", "type": "full", "start": 23},
]

REPS_QCD1 = []  # هيتضاف بعدين

REPS_BY_BRANCH = {
    "qcd1": REPS_QCD1,
    "qcd2": REPS_QCD2,
}


def get_supervisor_shift(shift_id):
    for s in SUPERVISOR_SHIFTS:
        if s["id"] == shift_id:
            return s
    return None


def rep_end_hour(rep):
    """نهاية شيفت المندوب (float 0-24، ممكن تلف فوق 24 لو عدت نص الليل)."""
    dur = DURATION_HOURS[rep["type"]]
    return rep["start"] + dur


def intervals_overlap(a_start, a_end, b_start, b_end):
    """
    بيتأكد من تقاطع فترتين زمنيتين على مدار 24 ساعة، مع الأخذ في الاعتبار
    إن أي فترة ممكن تعدي نص الليل (end <= start يبقى معناها بتلف لليوم اللي بعده).
    بنشتغل بتمثيل الفترات على محور مطوّل (0-48) لتغطية كل احتمالات اللف.
    """
    def normalize(start, end):
        # لو الفترة بتلف بعد نص الليل، السقف بيبقى start..end+24
        if end <= start:
            end += 24
        return start, end

    a_s, a_e = normalize(a_start, a_end)
    b_s, b_e = normalize(b_start, b_end)

    # بنجرب المقارنة مباشرة، وبعدين بنزحزح فترة (b) بمقدار +24 و -24
    # عشان نغطي حالة إن فترة تبدأ قريب من نص الليل والتانية بعده باليوم اللي بعده
    for shift in (0, 24, -24):
        bs, be = b_s + shift, b_e + shift
        if a_s < be and bs < a_e:
            return True
    return False


def get_overlapping_reps(branch, supervisor_shift_id):
    """المندوبين اللي شيفتهم بيتقاطع مع شيفت المشرف، لفرع معين."""
    shift = get_supervisor_shift(supervisor_shift_id)
    if not shift:
        return []
    reps = REPS_BY_BRANCH.get(branch, [])
    result = []
    for rep in reps:
        rep_end = rep_end_hour(rep)
        if intervals_overlap(shift["start"], shift["end"], rep["start"], rep_end):
            result.append(rep)
    return result
