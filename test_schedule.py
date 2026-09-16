import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
import bot

class ScheduleTests(unittest.TestCase):
    def test_schedule_request_detection(self):
        self.assertTrue(bot.is_schedule_request("dars jadvali"))
        self.assertTrue(bot.is_schedule_request("dars jadvalim"))
        self.assertTrue(bot.is_schedule_request("haftalik jadval"))
        self.assertTrue(bot.is_schedule_request("haftalik dars jadvali"))
        self.assertTrue(bot.is_schedule_request("jadvalim qanaqa"))
        self.assertTrue(bot.is_schedule_request("darsim qachon?"))
        self.assertTrue(bot.is_schedule_request("jadval"))
        self.assertFalse(bot.is_schedule_request("salom"))
        self.assertFalse(bot.is_schedule_request("rahmat"))

    def test_find_student_and_format(self):
        # Student id=1: Qudratov Sardorbek (TG ID 5682626877)
        mock_user = NS(id=5682626877, full_name="Sardorbek Qudratov", username=None)
        student = bot.find_student_by_user(mock_user)
        self.assertIsNotNone(student)
        self.assertEqual(student["name"], "Qudratov Sardorbek")

        schedule = bot.format_student_weekly_schedule(student)
        self.assertIn("Haftalik dars jadvali", schedule)
        self.assertIn("Qudratov Sardorbek", schedule)
        self.assertIn("Python dasturlash", schedule)

if __name__ == "__main__":
    unittest.main()
