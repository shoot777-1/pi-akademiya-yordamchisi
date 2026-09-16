import json
import asyncio
import logging
from datetime import datetime, date, timedelta
from aiohttp import web
from config import BASE_DIR, OPENAI_MODEL
from operations import tashkent_now
from database import (
    get_connection,
    get_all_students,
    get_paid_students,
    get_lessons_for_date,
    get_student_learning_logs,
    get_leaderboard,
    add_student_xp,
    get_student_gamification,
    get_setting
)

logger = logging.getLogger(__name__)

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Cyber Tech Academy — Boshqaruv Paneli</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #070913;
      --card-bg: rgba(18, 24, 43, 0.75);
      --card-border: rgba(255, 255, 255, 0.08);
      --card-hover: rgba(26, 35, 64, 0.9);
      --primary: #00f2fe;
      --primary-glow: rgba(0, 242, 254, 0.25);
      --accent: #4facfe;
      --purple: #9d4edd;
      --gold: #ffb703;
      --green: #10b981;
      --red: #ef4444;
      --text: #f8fafc;
      --text-dim: #94a3b8;
    }
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
      font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
      -webkit-tap-highlight-color: transparent;
    }
    body {
      background-color: var(--bg);
      background-image: 
        radial-gradient(circle at 10% 20%, rgba(157, 78, 221, 0.12) 0%, transparent 40%),
        radial-gradient(circle at 90% 80%, rgba(0, 242, 254, 0.1) 0%, transparent 40%);
      color: var(--text);
      min-height: 100vh;
      padding-bottom: 70px;
    }
    .header {
      padding: 20px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid var(--card-border);
      backdrop-filter: blur(12px);
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(7, 9, 19, 0.85);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .logo-badge {
      width: 42px;
      height: 42px;
      background: linear-gradient(135deg, #00f2fe, #4facfe, #9d4edd);
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 22px;
      font-weight: 800;
      color: #070913;
      box-shadow: 0 0 20px var(--primary-glow);
    }
    .brand-text h1 {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0.5px;
      background: linear-gradient(to right, #fff, #94a3b8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .brand-text p {
      font-size: 12px;
      color: var(--primary);
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .brand-text p::before {
      content: '';
      width: 7px;
      height: 7px;
      background: var(--green);
      border-radius: 50%;
      display: inline-block;
      box-shadow: 0 0 8px var(--green);
    }
    .nav-tabs {
      display: flex;
      gap: 8px;
      padding: 16px 24px 8px;
      overflow-x: auto;
      scrollbar-width: none;
    }
    .nav-tabs::-webkit-scrollbar { display: none; }
    .tab-btn {
      padding: 10px 18px;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text-dim);
      border-radius: 30px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      white-space: nowrap;
      transition: all 0.25s ease;
    }
    .tab-btn.active {
      background: linear-gradient(135deg, rgba(0, 242, 254, 0.15), rgba(79, 172, 254, 0.1));
      color: #fff;
      border-color: var(--primary);
      box-shadow: 0 0 15px var(--primary-glow);
    }
    .container {
      padding: 16px 24px;
      max-width: 1200px;
      margin: 0 auto;
    }
    .grid-stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .stat-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 20px;
      padding: 20px;
      backdrop-filter: blur(16px);
      transition: transform 0.2s ease, border-color 0.2s ease;
      position: relative;
      overflow: hidden;
    }
    .stat-card:hover {
      transform: translateY(-3px);
      border-color: rgba(0, 242, 254, 0.3);
    }
    .stat-card::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0; height: 3px;
      background: linear-gradient(90deg, var(--primary), var(--purple));
      opacity: 0.6;
    }
    .stat-title {
      font-size: 13px;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 8px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .stat-value {
      font-size: 28px;
      font-weight: 700;
      font-family: 'Space Grotesk', sans-serif;
      color: #fff;
      margin-bottom: 4px;
    }
    .stat-desc {
      font-size: 12px;
      color: var(--text-dim);
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 20px;
      padding: 22px;
      backdrop-filter: blur(16px);
      margin-bottom: 24px;
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 18px;
    }
    .card-title {
      font-size: 18px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .badge {
      padding: 4px 10px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
    }
    .badge-success { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-danger { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .badge-xp { background: rgba(255, 183, 3, 0.15); color: #fbbf24; border: 1px solid rgba(255, 183, 3, 0.3); }
    .badge-purple { background: rgba(157, 78, 221, 0.15); color: #c084fc; border: 1px solid rgba(157, 78, 221, 0.3); }

    /* Podiums */
    .podium-container {
      display: flex;
      justify-content: center;
      align-items: flex-end;
      gap: 16px;
      margin: 24px 0 32px;
    }
    .podium-card {
      flex: 1;
      max-width: 220px;
      background: rgba(26, 35, 64, 0.6);
      border: 1px solid var(--card-border);
      border-radius: 18px;
      padding: 16px;
      text-align: center;
      position: relative;
    }
    .podium-card.first {
      border-color: rgba(255, 183, 3, 0.5);
      background: linear-gradient(180deg, rgba(255, 183, 3, 0.15) 0%, rgba(18, 24, 43, 0.8) 100%);
      transform: scale(1.05);
      box-shadow: 0 0 25px rgba(255, 183, 3, 0.2);
    }
    .podium-rank {
      font-size: 28px;
      margin-bottom: 6px;
    }
    .podium-name {
      font-weight: 700;
      font-size: 15px;
      margin-bottom: 4px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .podium-xp {
      font-size: 16px;
      font-weight: 800;
      color: var(--gold);
      font-family: 'Space Grotesk', sans-serif;
    }

    /* Table */
    .table-responsive {
      overflow-x: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
    }
    th {
      padding: 12px 16px;
      font-size: 12px;
      text-transform: uppercase;
      color: var(--text-dim);
      border-bottom: 1px solid var(--card-border);
    }
    td {
      padding: 14px 16px;
      font-size: 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }
    tr:hover td {
      background: rgba(255, 255, 255, 0.02);
    }
    .progress-bar {
      width: 100px;
      height: 6px;
      background: rgba(255, 255, 255, 0.1);
      border-radius: 10px;
      overflow: hidden;
      display: inline-block;
      vertical-align: middle;
      margin-right: 8px;
    }
    .progress-fill {
      height: 100%;
      background: linear-gradient(90deg, var(--primary), var(--purple));
      border-radius: 10px;
    }
    .tab-content {
      display: none;
    }
    .tab-content.active {
      display: block;
      animation: fadeIn 0.3s ease;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .lesson-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 16px;
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      margin-bottom: 10px;
    }
    .lesson-time {
      font-family: 'Space Grotesk', sans-serif;
      font-weight: 700;
      color: var(--primary);
      font-size: 16px;
    }
    .btn-action {
      background: linear-gradient(135deg, var(--primary), var(--accent));
      border: none;
      color: #070913;
      font-weight: 700;
      padding: 8px 16px;
      border-radius: 20px;
      font-size: 13px;
      cursor: pointer;
      box-shadow: 0 0 15px var(--primary-glow);
      transition: all 0.2s ease;
    }
    .btn-action:hover {
      transform: scale(1.04);
    }
  </style>
</head>
<body>
  <div class="header">
    <div class="brand">
      <div class="logo-badge">π</div>
      <div class="brand-text">
        <h1>Cyber Tech Academy</h1>
        <p>AI Yordamchi "Pi" Dashboard</p>
      </div>
    </div>
    <div>
      <button class="btn-action" onclick="refreshData()">🔄 Yangilash</button>
    </div>
  </div>

  <div class="nav-tabs">
    <button class="tab-btn active" onclick="switchTab('overview')">📊 Umumiy</button>
    <button class="tab-btn" onclick="switchTab('leaderboard')">🏆 Reyting (XP)</button>
    <button class="tab-btn" onclick="switchTab('students')">👥 O'quvchilar</button>
    <button class="tab-btn" onclick="switchTab('schedule')">📅 Dars Jadvallari</button>
    <button class="tab-btn" onclick="switchTab('ai_insights')">🧠 AI Tahlili</button>
  </div>

  <div class="container">
    <!-- 1. OVERVIEW TAB -->
    <div id="tab-overview" class="tab-content active">
      <div class="grid-stats">
        <div class="stat-card">
          <div class="stat-title">O'quvchilar Soni <span>👥</span></div>
          <div class="stat-value" id="stat-students">0</div>
          <div class="stat-desc">Akademiyadagi faol talabalar</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">To'lov Holati <span>💳</span></div>
          <div class="stat-value" id="stat-paid">0%</div>
          <div class="stat-desc" id="stat-paid-detail">0 ta to'langan</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Qarzdorlar <span>⚠️</span></div>
          <div class="stat-value" style="color: var(--red);" id="stat-unpaid">0</div>
          <div class="stat-desc">To'lov kutilayotgan talabalar</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Bugungi Darslar <span>⏰</span></div>
          <div class="stat-value" id="stat-lessons">0</div>
          <div class="stat-desc" id="stat-lessons-date">Jadval bo'yicha</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">🏆 Top O'quvchilar (Gamifikatsiya)</div>
          <button class="tab-btn" onclick="switchTab('leaderboard')">Barchasi →</button>
        </div>
        <div class="podium-container" id="overview-podium"></div>
      </div>
    </div>

    <!-- 2. LEADERBOARD TAB -->
    <div id="tab-leaderboard" class="tab-content">
      <div class="card">
        <div class="card-header">
          <div class="card-title">🏆 CYBER TECH ACADEMY — O'QUVCHILAR REYTINGI</div>
          <span class="badge badge-xp">XP Leaderboard</span>
        </div>
        <div class="podium-container" id="full-podium"></div>
        <div class="table-responsive">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>O'quvchi</th>
                <th>Kurs</th>
                <th>Daraja (Level)</th>
                <th>Yechilgan</th>
                <th>Savollar</th>
                <th>XP Ball</th>
              </tr>
            </thead>
            <tbody id="leaderboard-tbody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 3. STUDENTS TAB -->
    <div id="tab-students" class="tab-content">
      <div class="card">
        <div class="card-header">
          <div class="card-title">👥 Barcha O'quvchilar va To'lovlar</div>
        </div>
        <div class="table-responsive">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Ism-Familiya</th>
                <th>Kurs</th>
                <th>To'lov Kuni</th>
                <th>Joriy Oy</th>
                <th>Telefon</th>
                <th>XP Balli</th>
              </tr>
            </thead>
            <tbody id="students-tbody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 4. SCHEDULE TAB -->
    <div id="tab-schedule" class="tab-content">
      <div class="card">
        <div class="card-header">
          <div class="card-title">☀️ Bugungi Darslar</div>
          <span class="badge badge-purple" id="today-label">Bugun</span>
        </div>
        <div id="today-lessons-list"></div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">🌙 Ertangi Darslar</div>
          <span class="badge badge-xp" id="tomorrow-label">Ertaga</span>
        </div>
        <div id="tomorrow-lessons-list"></div>
      </div>
    </div>

    <!-- 5. AI INSIGHTS TAB -->
    <div id="tab-ai_insights" class="tab-content">
      <div class="card">
        <div class="card-header">
          <div class="card-title">🧠 O'quvchilar Savollari va AI Diagnostikasi</div>
          <span class="badge badge-success">GPT-4o Insights</span>
        </div>
        <div id="ai-logs-list"></div>
      </div>
    </div>
  </div>

  <script>
    if (window.Telegram && window.Telegram.WebApp) {
      window.Telegram.WebApp.ready();
      window.Telegram.WebApp.expand();
    }

    function switchTab(tabId) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById('tab-' + tabId).classList.add('active');
    }

    async function loadData() {
      try {
        const res = await fetch('/api/dashboard_data');
        const data = await res.json();

        // Stats
        document.getElementById('stat-students').innerText = data.stats.total_students;
        document.getElementById('stat-paid').innerText = data.stats.paid_pct + '%';
        document.getElementById('stat-paid-detail').innerText = data.stats.paid_count + ' ta to\\'langan';
        document.getElementById('stat-unpaid').innerText = data.stats.unpaid_count;
        document.getElementById('stat-lessons').innerText = data.today_lessons.length;
        document.getElementById('stat-lessons-date').innerText = data.today_date;

        // Podiums
        const top3 = data.leaderboard.slice(0, 3);
        const ranks = ['🥇', '🥈', '🥉'];
        let podiumHtml = '';
        top3.forEach((item, i) => {
          podiumHtml += `
            <div class="podium-card ${i === 0 ? 'first' : ''}">
              <div class="podium-rank">${ranks[i]}</div>
              <div class="podium-name">${item.student_name}</div>
              <div class="badge badge-purple" style="margin-bottom: 6px;">Level ${item.level}</div>
              <div class="podium-xp">${item.xp} XP</div>
            </div>
          `;
        });
        document.getElementById('overview-podium').innerHTML = podiumHtml;
        document.getElementById('full-podium').innerHTML = podiumHtml;

        // Leaderboard Table
        let lbHtml = '';
        data.leaderboard.forEach((item, idx) => {
          const medal = idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : (idx + 1);
          lbHtml += `
            <tr>
              <td><strong>${medal}</strong></td>
              <td><strong>${item.student_name}</strong></td>
              <td>${item.course_name || 'Kurs'}</td>
              <td><span class="badge badge-purple">${item.title}</span></td>
              <td>${item.tasks_solved || 0} ta</td>
              <td>${item.questions_asked || 0} ta</td>
              <td><strong style="color: var(--gold);">${item.xp} XP</strong></td>
            </tr>
          `;
        });
        document.getElementById('leaderboard-tbody').innerHTML = lbHtml;

        // Students Table
        let stHtml = '';
        data.students.forEach(s => {
          const isPaid = data.paid_ids.includes(s.id);
          const badge = isPaid 
            ? '<span class="badge badge-success">To\\'langan ✅</span>'
            : '<span class="badge badge-danger">Qarzdor ❌</span>';
          stHtml += `
            <tr>
              <td>#${s.id}</td>
              <td><strong>${s.name}</strong></td>
              <td>${s.course_name || '-'}</td>
              <td>Har oyning <strong>${s.due_day}-sanasi</strong></td>
              <td>${badge}</td>
              <td>${s.phone || '-'}</td>
              <td><strong style="color: var(--gold);">${s.xp || 0} XP</strong></td>
            </tr>
          `;
        });
        document.getElementById('students-tbody').innerHTML = stHtml;

        // Schedule
        let todayHtml = '';
        if (data.today_lessons.length === 0) {
          todayHtml = '<p style="color: var(--text-dim); padding: 10px;">Bugun darslar belgilanmagan.</p>';
        } else {
          data.today_lessons.forEach(l => {
            todayHtml += `
              <div class="lesson-item">
                <div>
                  <div style="font-weight: 700;">${l.student_name}</div>
                  <div style="font-size: 12px; color: var(--text-dim);">${l.course_name || 'Kurs'}</div>
                </div>
                <div class="lesson-time">⏰ ${l.lesson_time}</div>
              </div>
            `;
          });
        }
        document.getElementById('today-lessons-list').innerHTML = todayHtml;

        let tomHtml = '';
        if (data.tomorrow_lessons.length === 0) {
          tomHtml = '<p style="color: var(--text-dim); padding: 10px;">Ertaga darslar belgilanmagan.</p>';
        } else {
          data.tomorrow_lessons.forEach(l => {
            tomHtml += `
              <div class="lesson-item">
                <div>
                  <div style="font-weight: 700;">${l.student_name}</div>
                  <div style="font-size: 12px; color: var(--text-dim);">${l.course_name || 'Kurs'}</div>
                </div>
                <div class="lesson-time">⏰ ${l.lesson_time}</div>
              </div>
            `;
          });
        }
        document.getElementById('tomorrow-lessons-list').innerHTML = tomHtml;

        // AI Insights
        let logsHtml = '';
        if (data.logs.length === 0) {
          logsHtml = '<p style="color: var(--text-dim); padding: 10px;">Hali savol-javoblar qayd etilmagan.</p>';
        } else {
          data.logs.forEach(l => {
            logsHtml += `
              <div class="lesson-item" style="display: block; margin-bottom: 14px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                  <span style="font-weight: 700; color: var(--primary);">👤 ${l.student_name || 'Talaba'}</span>
                  <span style="font-size: 11px; color: var(--text-dim);">${(l.created_at || '').substring(0, 16)}</span>
                </div>
                <div style="font-size: 14px; margin-bottom: 6px;">❓ <strong>Savol:</strong> ${l.question}</div>
                <div style="font-size: 13px; color: var(--text-dim); background: rgba(0,0,0,0.25); padding: 8px 12px; border-radius: 8px;">💡 <strong>AI Javobi:</strong> ${(l.ai_response || '').substring(0, 200)}...</div>
              </div>
            `;
          });
        }
        document.getElementById('ai-logs-list').innerHTML = logsHtml;

      } catch (err) {
        console.error('Yuklashda xatolik:', err);
      }
    }

    function refreshData() {
      loadData();
    }

    loadData();
  </script>
</body>
</html>
"""

async def handle_index(request):
    return web.Response(text=DASHBOARD_HTML, content_type="text/html", charset="utf-8")

async def handle_api_data(request):
    now = tashkent_now()
    period = now.strftime("%Y-%m")
    students = get_all_students(active_only=True)
    paid_ids = get_paid_students(period)
    
    total = len(students)
    paid_count = len([s for s in students if s["id"] in paid_ids])
    unpaid_count = total - paid_count
    pct = round((paid_count / total * 100)) if total > 0 else 0

    leaderboard = get_leaderboard(limit=20)
    # XP ni talabalar ro'yxatiga ham biriktiramiz
    xp_map = {row["student_id"]: row["xp"] for row in leaderboard}
    augmented_students = []
    for s in students:
        s_dict = dict(s)
        s_dict["xp"] = xp_map.get(s["id"], 0)
        augmented_students.append(s_dict)

    today_lessons = get_lessons_for_date(now.date())
    tomorrow_lessons = get_lessons_for_date(now.date() + timedelta(days=1))
    logs = get_student_learning_logs(limit=15)

    data = {
        "stats": {
            "total_students": total,
            "paid_count": paid_count,
            "unpaid_count": unpaid_count,
            "paid_pct": pct
        },
        "paid_ids": list(paid_ids),
        "today_date": f"{now.day}-sana, {now.strftime('%H:%M')}",
        "students": augmented_students,
        "leaderboard": leaderboard,
        "today_lessons": today_lessons,
        "tomorrow_lessons": tomorrow_lessons,
        "logs": logs
    }
    return web.json_response(data)


async def create_web_app():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/dashboard_data", handle_api_data)
    return app


async def start_web_dashboard(host="0.0.0.0", port=8088):
    """aiohttp serverini bot bilan birga ishga tushirish"""
    try:
        app = await create_web_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info(f"🌐 Cyber Tech Web Dashboard muvaffaqiyatli ishga tushdi: http://localhost:{port}")
        return runner
    except Exception as e:
        logger.warning(f"Web Dashboardni ishga tushirishda ogohlantirish: {e}")
        return None
