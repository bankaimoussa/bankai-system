# -*- coding: utf-8 -*-
"""
منطق ميزة Cortex: تفريد اسم المندوب للبحث في Amazon Logistics،
وفلترة ملف الـ CSV اللي بيرجع من الاسكريبت لحساب عدد الأوردرات.
"""
import csv
import io


def short_name(full_name):
    """
    أول كلمة + آخر كلمة من الاسم، للبحث في Amazon Logistics.
    'Ahmed Wagdy Ahmed' -> 'Ahmed Ahmed'
    'Sami Zaky' -> 'Sami Zaky' (اسمين بالفعل، يفضلوا زي ما هم)
    """
    parts = full_name.strip().split()
    if len(parts) <= 2:
        return " ".join(parts)
    return f"{parts[0]} {parts[-1]}"


# العمود اللي بنفلتر عليه، والقيمة اللي بنقبلها.
# لو محتاجين نضيف شروط تانية بعدين (مثلاً استبعاد Route Code معين)، هنا المكان.
REASON_CODE_COLUMN = "Reason Code"
ACCEPTED_REASON_CODE = "Delivered to Customer"
ADDRESS_COLUMN = "Address"


def count_orders_from_csv(file_bytes):
    """
    بياخد بايتس ملف الـ CSV اللي نزل من زرار التحميل في Amazon Logistics،
    ويرجع (suggested_orders, raw_row_count, unique_stop_count).

    المنطق:
    1. فلتر: بس الصفوف اللي Reason Code == "Delivered to Customer"
    2. فرّد (dedupe) على أساس Address (بعد trim) — لوكيشن واحد بياخد أوردر واحد
       بغض النظر عن عدد الطرود اللي اتسلمت فيه.
    3. عدد الأوردرز = عدد الـ Address الفريدة.

    بيرمي ValueError لو الأعمدة المتوقعة مش موجودة (شكل ملف مختلف عن المتوقع).
    """
    text = file_bytes.decode("utf-8-sig")  # utf-8-sig عشان يتعامل مع BOM لو موجود
    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        raise ValueError("empty_csv")
    if REASON_CODE_COLUMN not in reader.fieldnames or ADDRESS_COLUMN not in reader.fieldnames:
        raise ValueError("unexpected_csv_format")

    delivered_rows = [
        row for row in reader
        if (row.get(REASON_CODE_COLUMN) or "").strip() == ACCEPTED_REASON_CODE
    ]

    unique_addresses = set()
    for row in delivered_rows:
        addr = (row.get(ADDRESS_COLUMN) or "").strip()
        if addr:
            unique_addresses.add(addr)

    raw_row_count = len(delivered_rows)
    unique_stop_count = len(unique_addresses)
    return unique_stop_count, raw_row_count, unique_stop_count
