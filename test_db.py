from database import get_lessons_for_day, get_all_students

print("--- Talabalar ---")
for s in get_all_students():
    print(f"{s['id']}. {s['name']} - Kurs: {s['course_name']} - To'lov kuni: {s['due_day']} - Username: {s['username']}")

print("\n--- Bugungi darslar (13-sentyabr) ---")
for l in get_lessons_for_day(13):
    print(f"{l['lesson_time']} - {l['student_name']} ({l['course_name']})")
