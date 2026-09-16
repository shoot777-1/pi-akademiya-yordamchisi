import re
import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple
import openpyxl
from database import add_or_update_student, save_daily_lessons, get_connection, month_number, is_paid_value
from contextlib import closing

def parse_day_from_val(val: Any) -> int:
    """To'lov sanasidan kun raqamini ajratib olish (masalan '25-sanada' -> 25)"""
    if val is None:
        raise ValueError("To’lov kuni kiritilmagan")
    if hasattr(val, 'day'):
        return val.day
        
    val_str = str(val).strip()
    # Har qanday 1-31 raqamlarni qidirish (03, 08, 15, 25 kabilarni)
    matches = re.findall(r'(\d{1,2})', val_str)
    for m in matches:
        num = int(m)
        if 1 <= num <= 31:
            return num
    raise ValueError("To’lov kuni 1 dan 31 gacha bo’lishi kerak")

def import_pi_academy_excel(file_path: str, *, dry_run=False) -> Dict[str, Any]:
    """
    Pi Akademiya Excel faylini to'liq o'qish:
    1. 'oylik to'lovlar' varag'idan talabalar va to'lov kunlari
    2. 'Sentabr' (yoki dars oylari) varag'idan har kungi dars vaqtlari
    """
    wb = openpyxl.load_workbook(file_path, data_only=True)
    try:
        return _import_workbook(wb, dry_run=dry_run)
    finally:
        wb.close()


def _import_workbook(wb, *, dry_run=False):
    
    students_list = []
    students_imported = 0
    lessons_imported = 0
    
    # 1. Oylik to'lovlar varag'i
    pay_sheet_name = None
    for name in wb.sheetnames:
        if "to'lov" in name.lower() or "tolov" in name.lower() or "oylik" in name.lower():
            pay_sheet_name = name
            break
            
    if pay_sheet_name:
        ws_pay = wb[pay_sheet_name]
        # Qator 5 dan boshlab o'qiymiz
        for row in ws_pay.iter_rows(min_row=5, values_only=True):
            if not row or len(row) < 4:
                continue
            name = row[2]
            if not name or not str(name).strip():
                continue
            name = str(name).strip()
            course_name = str(row[3]).strip() if row[3] else None
            
            # sentabr oyi to'lov holati (row[8])
            sept_paid = str(row[8]).strip() if len(row) > 8 and row[8] else "to'lanmagan"
            
            # To'lov sanasi (row[12])
            due_val = row[12] if len(row) > 12 else None
            due_day = parse_day_from_val(due_val)
            
            # Telegram ID, username yoki telefon (row[13])
            raw_contact = str(row[13]).strip() if len(row) > 13 and row[13] is not None else None
            username = None
            telegram_id = None
            phone = None
            
            if raw_contact and raw_contact != "@":
                # Agar faqat raqam bo'lsa va 7 tadan ortiq bo'lsa
                digits_only = re.sub(r"\D", "", raw_contact)
                if raw_contact.startswith("@"):
                    username = raw_contact.replace("@", "").strip()
                elif raw_contact.lower().startswith("id:") or raw_contact.lower().startswith("id"):
                    try:
                        telegram_id = int(digits_only)
                    except ValueError:
                        pass
                elif len(digits_only) >= 7 and len(digits_only) <= 11 and not digits_only.startswith("998"):
                    # Telegram ID lari odatda 7-10 xonali sonlar (masalan 123456789)
                    try:
                        telegram_id = int(digits_only)
                    except ValueError:
                        pass
                elif digits_only.startswith("998") or len(digits_only) >= 9:
                    phone = raw_contact
                else:
                    username = raw_contact.replace("@", "").strip()
                
            students_list.append(dict(
                name=name,
                due_day=due_day,
                course_name=course_name,
                username=username,
                telegram_id=telegram_id,
                phone=phone,
                september_paid=sept_paid
            ))
            students_imported += 1

    # 2. Dars jadvali varag'i (Sentabr yoki boshqa oy)
    schedule_sheet_name = None
    for name in wb.sheetnames:
        try:
            month_number(name)
        except ValueError:
            continue
        if name != pay_sheet_name:
            schedule_sheet_name = name
            break
            
    lessons_list = []
    if schedule_sheet_name:
        ws_sch = wb[schedule_sheet_name]
        month = month_number(schedule_sheet_name)
        year_match = re.search(r"\b(20\d{2})\b", schedule_sheet_name)
        from operations import tashkent_now
        year = int(year_match.group(1)) if year_match else tashkent_now().year
        # Qator 3 da kunlar: 1, 2, 3 ... 30 (ustun E (index 4) dan boshlab)
        day_cols = {}
        row3 = list(ws_sch.iter_rows(min_row=3, max_row=3, values_only=True))[0]
        for col_idx in range(4, len(row3)):
            val = row3[col_idx]
            try:
                day_num = int(val)
                if 1 <= day_num <= 31:
                    day_cols[col_idx] = day_num
            except (ValueError, TypeError):
                continue
                
        # Qator 5 dan o'quvchilar va ularning dars soatlari
        for row in ws_sch.iter_rows(min_row=5, values_only=True):
            if not row or len(row) < 4:
                continue
            name = row[2]
            if not name or not str(name).strip():
                continue
            name = str(name).strip()
            course_name = str(row[3]).strip() if row[3] else None
            
            for col_idx, day_num in day_cols.items():
                if col_idx < len(row):
                    cell_val = row[col_idx]
                    if cell_val is not None:
                        # Masalan datetime.time(14, 0) yoki "14:00"
                        if isinstance(cell_val, datetime.time):
                            time_str = cell_val.strftime("%H:%M")
                        else:
                            time_str = str(cell_val).strip()
                            
                        # Agar vaqt formati bo'lsa (masalan 14:00, 16:00, 10:00, 18:00)
                        if ":" in time_str and len(time_str) <= 8 and not time_str.startswith("="):
                            parsed_time = datetime.time.fromisoformat(time_str)
                            time_clean = parsed_time.strftime("%H:%M")
                            lesson_date = datetime.date(year, month, day_num).isoformat()
                            lessons_list.append({
                                "month_name": schedule_sheet_name,
                                "lesson_date": lesson_date,
                                "day_number": day_num,
                                "student_name": name,
                                "course_name": course_name,
                                "lesson_time": time_clean
                            })
                            
        lessons_imported = len(lessons_list)
        
    if not pay_sheet_name or not schedule_sheet_name:
        raise ValueError("To’lovlar va oy nomli jadval varaqlari talab qilinadi")
    if not students_list or not lessons_list:
        raise ValueError("O’quvchilar yoki darslar topilmadi. Bo’sh jadval import qilinmaydi")
    names = [s["name"].casefold() for s in students_list]
    if len(names) != len(set(names)):
        raise ValueError("To’lovlar ro’yxatida takroriy ism bor; ularni farqlab yozing")
    if not dry_run:
        with closing(get_connection()) as conn, conn:
            for student in students_list:
                student_id = add_or_update_student(**student, connection=conn)
                if month == 9 and is_paid_value(student.get("september_paid")):
                    conn.execute("INSERT OR IGNORE INTO payments VALUES (?, ?, ?)",
                                 (student_id, f"{year}-09", datetime.datetime.now().isoformat()))
            save_daily_lessons(lessons_list, connection=conn)
    return {
        "students_imported": students_imported,
        "lessons_imported": lessons_imported,
        "schedule_sheet": schedule_sheet_name,
        "payment_sheet": pay_sheet_name
    }
