import sqlite3
import os
import shutil
import random
import time
import ssl
import threading
import urllib.request
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.switch import Switch
from kivy.core.window import Window
from kivy.core.clipboard import Clipboard
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.graphics import Color, RoundedRectangle

# ==========================================
# CONFIGURATION & DYNAMIC PATHS
# ==========================================
DB_PATH = ""
STATS_DB_PATH = ""
SECRET_PASSCODE = "PUNJAB100"

GITHUB_VERSION_URL = "https://raw.githubusercontent.com/happysinghgurusar-beep/punjab-exam-academy-data/refs/heads/main/Version.txt"
GITHUB_DB_URL = "https://raw.githubusercontent.com/happysinghgurusar-beep/punjab-exam-academy-data/refs/heads/main/exam_bank.db"

THEME_STATE = {
    "bg": (0.95, 0.95, 0.95, 1),
    "opacity": 0.85,
    "is_dark": False,
    "text": (0.1, 0.1, 0.1, 1),
    "glass": 1.0,
    "db_error": ""
}


def is_valid_content_db(path):
    """Checks that a database file exists and contains required tables."""
    if not path or not os.path.exists(path):
        return False
    try:
        conn = sqlite3.connect(path)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        return 'Categories' in tables and 'App_Theme' in tables
    except Exception:
        return False


def init_storage_paths(app):
    """Sets up Android-safe private storage and seeds exam_bank.db."""
    global DB_PATH, STATS_DB_PATH
    base_dir = app.user_data_dir
    os.makedirs(base_dir, exist_ok=True)

    DB_PATH = os.path.join(base_dir, 'exam_bank.db')
    STATS_DB_PATH = os.path.join(base_dir, 'user_stats.db')

    pydroid_db = '/storage/emulated/0/Download/exam_bank.db'
    bundled_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exam_bank.db')

    if is_valid_content_db(pydroid_db):
        if (not is_valid_content_db(DB_PATH)) or (os.path.getmtime(pydroid_db) > os.path.getmtime(DB_PATH)):
            shutil.copy2(pydroid_db, DB_PATH)
    elif not is_valid_content_db(DB_PATH) and is_valid_content_db(bundled_db):
        shutil.copy2(bundled_db, DB_PATH)


def goto(manager, screen_name, direction='left'):
    manager.transition = SlideTransition(direction=direction)
    manager.current = screen_name


def fmt_marks(val):
    return f"{val:g}" if val == int(val) else f"{val:.2f}"


# ==========================================
# LOCAL USER DATABASE (NEVER OVERWRITTEN)
# ==========================================
def ensure_user_db():
    try:
        conn = sqlite3.connect(STATS_DB_PATH)
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS Question_Logs ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "status TEXT NOT NULL, "
            "marks REAL NOT NULL, "
            "time_spent REAL NOT NULL)"
        )
        c.execute("CREATE TABLE IF NOT EXISTS User_Meta (key TEXT PRIMARY KEY, val TEXT)")
        c.execute("INSERT OR IGNORE INTO User_Meta (key, val) VALUES ('db_version', '0')")
        c.execute("INSERT OR IGNORE INTO User_Meta (key, val) VALUES ('is_premium', '0')")
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_meta(key, default='0'):
    try:
        conn = sqlite3.connect(STATS_DB_PATH)
        row = conn.execute("SELECT val FROM User_Meta WHERE key=?", (key,)).fetchone()
        conn.close()
        return row[0] if row else default
    except Exception:
        return default


def set_meta(key, val):
    try:
        conn = sqlite3.connect(STATS_DB_PATH)
        conn.execute("INSERT OR REPLACE INTO User_Meta (key, val) VALUES (?, ?)", (key, str(val)))
        conn.commit()
        conn.close()
    except Exception:
        pass


def is_premium_unlocked():
    return get_meta('is_premium', '0') == '1'


# ==========================================
# CONTENT DATABASE & THEME SYNC
# ==========================================
def sync_theme_from_db():
    if not is_valid_content_db(DB_PATH):
        THEME_STATE["db_error"] = "No quiz database found. Tap 'Sync New Quizzes'."
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT r, g, b, opacity, is_dark FROM App_Theme WHERE id=1").fetchone()
        conn.close()
        if row:
            r, g, b, op, dark = row
            is_dark = bool(dark)
            THEME_STATE["bg"] = (float(r), float(g), float(b), 1)
            THEME_STATE["opacity"] = float(op)
            THEME_STATE["is_dark"] = is_dark
            THEME_STATE["text"] = (1, 1, 1, 1) if is_dark else (0.1, 0.1, 0.1, 1)
            THEME_STATE["glass"] = 0.12 if is_dark else 1.0
            THEME_STATE["db_error"] = ""
            Window.clearcolor = THEME_STATE["bg"]
    except Exception as e:
        THEME_STATE["db_error"] = f"Theme read error: {e}"


def get_cats():
    if not is_valid_content_db(DB_PATH):
        THEME_STATE["db_error"] = "No quiz database found. Tap 'Sync New Quizzes'."
        return {}
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT id, name FROM Categories WHERE is_premium <= ? ORDER BY id ASC",
            (1 if is_premium_unlocked() else 0,)
        ).fetchall()
        conn.close()
        THEME_STATE["db_error"] = ""
        return {r[1]: r[0] for r in rows}
    except Exception as e:
        THEME_STATE["db_error"] = f"Category read error: {e}"
        return {}


def get_subs(cat_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT id, name FROM Subcategories WHERE cat_id=? ORDER BY id ASC", (cat_id,)).fetchall()
        conn.close()
        return {r[1]: r[0] for r in rows}
    except Exception:
        return {}


def get_subsubs(subcat_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT id, name FROM SubSubcategories WHERE subcat_id=? ORDER BY id ASC", (subcat_id,)).fetchall()
        conn.close()
        return {r[1]: r[0] for r in rows}
    except Exception:
        return {}


def get_daily_quiz():
    """Returns (quiz_id, quiz_name, subject_name) if an active daily quiz exists and is accessible."""
    if not is_valid_content_db(DB_PATH):
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(SubSubcategories)").fetchall()}
        if 'is_daily' not in cols:
            conn.close()
            return None
        max_prem = 1 if is_premium_unlocked() else 0
        row = conn.execute(
            "SELECT ss.id, ss.name, c.name "
            "FROM SubSubcategories ss "
            "JOIN Subcategories s ON ss.subcat_id = s.id "
            "JOIN Categories c ON s.cat_id = c.id "
            "WHERE ss.is_daily = 1 AND c.is_premium <= ? LIMIT 1",
            (max_prem,)
        ).fetchone()
        conn.close()
        return row
    except Exception:
        return None


# ==========================================
# UI COMPONENTS
# ==========================================
class GlassCard(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            self.c = Color(THEME_STATE["glass"], THEME_STATE["glass"], THEME_STATE["glass"], THEME_STATE["opacity"])
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[20])
        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def refresh_glass(self):
        self.c.rgba = (THEME_STATE["glass"], THEME_STATE["glass"], THEME_STATE["glass"], THEME_STATE["opacity"])


class ModernButton(Button):
    def __init__(self, bg_color=(0.1, 0.55, 0.6, 1), **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_color = (0, 0, 0, 0)
        self.custom_color = bg_color
        self.bold = True
        with self.canvas.before:
            self.c = Color(*self.custom_color)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[15])
        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def set_color(self, rgba):
        self.c.rgba = rgba


# ==========================================
# SCREENS
# ==========================================
class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.daily_item = None
        layout = BoxLayout(padding=25)
        self.card = GlassCard(orientation='vertical', padding=24, spacing=12)

        self.title_lbl = Label(
            text="[b]Punjab Exam\nAcademy[/b]",
            markup=True, font_size=30, color=THEME_STATE["text"], halign='center', size_hint_y=0.24
        )
        self.card.add_widget(self.title_lbl)

        self.status_lbl = Label(
            text="", font_size=13, color=(0.1, 0.6, 0.25, 1), halign='center', size_hint_y=None, height=26
        )
        self.card.add_widget(self.status_lbl)

        self.btn_daily = ModernButton(
            text="Daily Quiz", bg_color=(0.85, 0.42, 0.08, 1), font_size=19, size_hint_y=0.17
        )
        self.btn_daily.bind(on_press=self.open_daily_quiz)
        self.card.add_widget(self.btn_daily)

        btn_quiz = ModernButton(
            text="Subject wise Quizzes", bg_color=(0.1, 0.55, 0.6, 1), font_size=19, size_hint_y=0.17
        )
        btn_quiz.bind(on_press=lambda x: goto(self.manager, 'subject_list', 'left'))
        self.card.add_widget(btn_quiz)

        btn_stats = ModernButton(
            text="View My Stats", bg_color=(0.3, 0.3, 0.4, 1), font_size=17, size_hint_y=0.14
        )
        btn_stats.bind(on_press=lambda x: goto(self.manager, 'stats', 'left'))
        self.card.add_widget(btn_stats)

        self.btn_sync = ModernButton(
            text="Sync New Quizzes", bg_color=(0.15, 0.45, 0.75, 1), font_size=17, size_hint_y=0.14
        )
        self.btn_sync.bind(on_press=self.start_sync)
        self.card.add_widget(self.btn_sync)

        self.btn_unlock = ModernButton(
            text="Unlock Premium", bg_color=(0.8, 0.6, 0.1, 1), font_size=17, size_hint_y=0.14
        )
        self.btn_unlock.bind(on_press=lambda x: goto(self.manager, 'unlock', 'left'))
        self.card.add_widget(self.btn_unlock)

        layout.add_widget(self.card)
        self.add_widget(layout)

    def refresh_home_widgets(self):
        sync_theme_from_db()
        self.card.refresh_glass()
        self.title_lbl.color = THEME_STATE["text"]

        self.daily_item = get_daily_quiz()
        if self.daily_item:
            self.btn_daily.text = f"Daily Quiz: {self.daily_item[1]}"
            self.btn_daily.set_color((0.85, 0.42, 0.08, 1))
            self.btn_daily.disabled = False
        else:
            self.btn_daily.text = "Daily Quiz (Coming Soon)"
            self.btn_daily.set_color((0.55, 0.48, 0.42, 1))
            self.btn_daily.disabled = True

        if THEME_STATE["db_error"]:
            self.status_lbl.color = (0.8, 0.1, 0.1, 1)
            self.status_lbl.text = THEME_STATE["db_error"]
        else:
            self.status_lbl.text = ""

        if is_premium_unlocked():
            self.btn_unlock.text = "Premium Active"
            self.btn_unlock.set_color((0.2, 0.65, 0.3, 1))
            self.btn_unlock.disabled = True

    def on_pre_enter(self):
        self.refresh_home_widgets()

    def open_daily_quiz(self, instance):
        if not self.daily_item:
            return
        app = App.get_running_app()
        app.sel_quiz_id = self.daily_item[0]
        app.sel_quiz_name = f"Daily: {self.daily_item[1]}"
        app.quiz_return_screen = 'home'
        goto(self.manager, 'active_quiz', 'left')

    def start_sync(self, instance):
        if "YOUR_USERNAME" in GITHUB_VERSION_URL:
            self.status_lbl.color = (0.1, 0.45, 0.75, 1)
            self.status_lbl.text = "Offline mode active. Add GitHub URL to enable cloud sync."
            return
        self.btn_sync.disabled = True
        self.status_lbl.color = (0.1, 0.45, 0.75, 1)
        self.status_lbl.text = "Checking for new quizzes..."
        threading.Thread(target=self._sync_worker, daemon=True).start()

    def _open_url(self, url):
        try:
            return urllib.request.urlopen(url, timeout=8)
        except Exception:
            ctx = ssl._create_unverified_context()
            return urllib.request.urlopen(url, context=ctx, timeout=8)

    def _sync_worker(self):
        try:
            with self._open_url(GITHUB_VERSION_URL) as resp:
                remote_ver = resp.read().decode('utf-8').strip()
            local_ver = get_meta('db_version', '0')

            if remote_ver == local_ver and is_valid_content_db(DB_PATH):
                Clock.schedule_once(lambda dt: self._sync_done("Already up to date!", (0.1, 0.6, 0.25, 1)))
                return

            Clock.schedule_once(lambda dt: setattr(self.status_lbl, 'text', f"Downloading update v{remote_ver}..."))
            tmp_path = DB_PATH + ".tmp"
            with self._open_url(GITHUB_DB_URL) as resp, open(tmp_path, 'wb') as out:
                shutil.copyfileobj(resp, out)

            if not is_valid_content_db(tmp_path):
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                Clock.schedule_once(lambda dt: self._sync_done("Invalid database file on server.", (0.8, 0.15, 0.15, 1)))
                return

            os.replace(tmp_path, DB_PATH)
            set_meta('db_version', remote_ver)
            Clock.schedule_once(
                lambda dt: self._sync_done(f"Updated to v{remote_ver}! New quizzes ready.", (0.1, 0.6, 0.25, 1), reload_ui=True)
            )
        except Exception:
            Clock.schedule_once(lambda dt: self._sync_done("Sync failed: check internet.", (0.8, 0.15, 0.15, 1)))

    def _sync_done(self, msg, color, reload_ui=False):
        self.btn_sync.disabled = False
        if reload_ui:
            self.refresh_home_widgets()
        self.status_lbl.color = color
        self.status_lbl.text = msg


class SubjectListScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.all_data = {}
        layout = BoxLayout(padding=20)
        self.card = GlassCard(orientation='vertical', padding=15, spacing=10)
        top = BoxLayout(size_hint_y=None, height=50, spacing=10)
        b = ModernButton(text="<", size_hint_x=0.2, bg_color=(0.5, 0.5, 0.5, 1))
        b.bind(on_press=lambda x: goto(self.manager, 'home', 'right'))
        self.head = Label(text="[b]Subjects[/b]", markup=True, color=THEME_STATE["text"], font_size=22)
        top.add_widget(b)
        top.add_widget(self.head)
        self.card.add_widget(top)

        self.search = TextInput(hint_text="Search subjects...", size_hint_y=None, height=46, multiline=False)
        self.search.bind(text=self.filter_list)
        self.card.add_widget(self.search)

        self.grid = GridLayout(cols=1, spacing=10, size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter('height'))
        scroll = ScrollView()
        scroll.add_widget(self.grid)
        self.card.add_widget(scroll)
        layout.add_widget(self.card)
        self.add_widget(layout)

    def on_pre_enter(self):
        sync_theme_from_db()
        self.card.refresh_glass()
        self.head.color = THEME_STATE["text"]
        self.search.text = ""
        self.all_data = get_cats()
        self.populate(self.all_data)

    def filter_list(self, instance, text):
        filtered = {k: v for k, v in self.all_data.items() if text.lower() in k.lower()}
        self.populate(filtered)

    def populate(self, data):
        self.grid.clear_widgets()
        if THEME_STATE["db_error"]:
            self.grid.add_widget(Label(text=THEME_STATE["db_error"], color=(0.8, 0.1, 0.1, 1), font_size=15, halign='center', size_hint_y=None, height=90))
            return
        if not data:
            self.grid.add_widget(Label(text="Content coming soon!\nCheck back later.", color=THEME_STATE["text"], font_size=18, halign='center', size_hint_y=None, height=100))
            return
        for name, item_id in data.items():
            btn = ModernButton(text=name, size_hint_y=None, height=58, bg_color=(0.1, 0.4, 0.7, 1))
            btn.bind(on_press=lambda x, n=name, i=item_id: self.select(n, i))
            self.grid.add_widget(btn)

    def select(self, name, i):
        app = App.get_running_app()
        app.sel_sub_id = i
        app.sel_sub_name = name
        goto(self.manager, 'chapter_list', 'left')


class ChapterListScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.all_data = {}
        layout = BoxLayout(padding=20)
        self.card = GlassCard(orientation='vertical', padding=15, spacing=10)
        top = BoxLayout(size_hint_y=None, height=50, spacing=10)
        b = ModernButton(text="<", size_hint_x=0.2, bg_color=(0.5, 0.5, 0.5, 1))
        b.bind(on_press=lambda x: goto(self.manager, 'subject_list', 'right'))
        self.lbl = Label(text="", markup=True, color=THEME_STATE["text"], font_size=20)
        top.add_widget(b)
        top.add_widget(self.lbl)
        self.card.add_widget(top)

        self.search = TextInput(hint_text="Search chapters...", size_hint_y=None, height=46, multiline=False)
        self.search.bind(text=self.filter_list)
        self.card.add_widget(self.search)

        self.grid = GridLayout(cols=1, spacing=10, size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter('height'))
        scroll = ScrollView()
        scroll.add_widget(self.grid)
        self.card.add_widget(scroll)
        layout.add_widget(self.card)
        self.add_widget(layout)

    def on_pre_enter(self):
        sync_theme_from_db()
        self.card.refresh_glass()
        self.lbl.color = THEME_STATE["text"]
        app = App.get_running_app()
        self.lbl.text = f"[b]{app.sel_sub_name}[/b]"
        self.search.text = ""
        self.all_data = get_subs(app.sel_sub_id)
        self.populate(self.all_data)

    def filter_list(self, instance, text):
        filtered = {k: v for k, v in self.all_data.items() if text.lower() in k.lower()}
        self.populate(filtered)

    def populate(self, data):
        self.grid.clear_widgets()
        if not data:
            self.grid.add_widget(Label(text="Chapters are being uploaded.\nStay tuned!", color=THEME_STATE["text"], font_size=18, halign='center', size_hint_y=None, height=100))
            return
        for name, item_id in data.items():
            btn = ModernButton(text=name, size_hint_y=None, height=58, bg_color=(0.2, 0.6, 0.8, 1))
            btn.bind(on_press=lambda x, n=name, i=item_id: self.select(n, i))
            self.grid.add_widget(btn)

    def select(self, name, i):
        app = App.get_running_app()
        app.sel_chap_id = i
        app.sel_chap_name = name
        goto(self.manager, 'quiz_list', 'left')


class QuizListScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.all_data = {}
        layout = BoxLayout(padding=20)
        self.card = GlassCard(orientation='vertical', padding=15, spacing=10)
        top = BoxLayout(size_hint_y=None, height=50, spacing=10)
        b = ModernButton(text="<", size_hint_x=0.2, bg_color=(0.5, 0.5, 0.5, 1))
        b.bind(on_press=lambda x: goto(self.manager, 'chapter_list', 'right'))
        self.lbl = Label(text="", markup=True, color=THEME_STATE["text"], font_size=20)
        top.add_widget(b)
        top.add_widget(self.lbl)
        self.card.add_widget(top)

        self.search = TextInput(hint_text="Search quizzes...", size_hint_y=None, height=46, multiline=False)
        self.search.bind(text=self.filter_list)
        self.card.add_widget(self.search)

        self.grid = GridLayout(cols=1, spacing=10, size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter('height'))
        scroll = ScrollView()
        scroll.add_widget(self.grid)
        self.card.add_widget(scroll)
        layout.add_widget(self.card)
        self.add_widget(layout)

    def on_pre_enter(self):
        sync_theme_from_db()
        self.card.refresh_glass()
        self.lbl.color = THEME_STATE["text"]
        app = App.get_running_app()
        self.lbl.text = f"[b]{app.sel_chap_name}[/b]"
        self.search.text = ""
        self.all_data = get_subsubs(app.sel_chap_id)
        self.populate(self.all_data)

    def filter_list(self, instance, text):
        filtered = {k: v for k, v in self.all_data.items() if text.lower() in k.lower()}
        self.populate(filtered)

    def populate(self, data):
        self.grid.clear_widgets()
        if not data:
            self.grid.add_widget(Label(text="Quizzes dropping soon!\nKeep preparing.", color=THEME_STATE["text"], font_size=18, halign='center', size_hint_y=None, height=100))
            return
        for name, item_id in data.items():
            btn = ModernButton(text=name + " Quiz", size_hint_y=None, height=58, bg_color=(0.4, 0.2, 0.6, 1))
            btn.bind(on_press=lambda x, n=name, i=item_id: self.select(n, i))
            self.grid.add_widget(btn)

    def select(self, name, i):
        app = App.get_running_app()
        app.sel_quiz_id = i
        app.sel_quiz_name = name
        app.quiz_return_screen = 'quiz_list'
        goto(self.manager, 'active_quiz', 'left')


# ==========================================
# ACTIVE QUIZ WITH NEGATIVE MARKING & LIVE STATS
# ==========================================
class ActiveQuizScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.main_layout = BoxLayout(padding=20)
        self.card = GlassCard(orientation='vertical', padding=18, spacing=12)
        self.main_layout.add_widget(self.card)
        self.add_widget(self.main_layout)
        self.neg_marking = False

    def _exit_screen(self):
        app = App.get_running_app()
        return getattr(app, 'quiz_return_screen', 'quiz_list') or 'quiz_list'

    def on_pre_enter(self):
        sync_theme_from_db()
        self.card.refresh_glass()
        app = App.get_running_app()
        conn = sqlite3.connect(DB_PATH)
        self.qs = conn.execute(
            "SELECT question_text, option_a, option_b, option_c, option_d, correct_answer, explanation FROM Questions WHERE subsubcat_id=?",
            (app.sel_quiz_id,)
        ).fetchall()
        conn.close()

        self.card.clear_widgets()
        if not self.qs:
            self.card.add_widget(Label(
                text="[b]Coming Soon![/b]\n\nNew MCQs for this topic\nare being prepared.\n\nCheck back shortly!",
                markup=True, color=THEME_STATE["text"], font_size=20, halign='center'
            ))
            b = ModernButton(text="Back to Menu", size_hint_y=None, height=50, bg_color=(0.1, 0.55, 0.6, 1))
            b.bind(on_press=lambda x: goto(self.manager, self._exit_screen(), 'right'))
            self.card.add_widget(b)
            return

        self.show_pre_quiz_setup()

    def show_pre_quiz_setup(self):
        self.card.clear_widgets()
        app = App.get_running_app()
        total_q = len(self.qs)

        self.card.add_widget(Label(
            text=f"[b]{app.sel_quiz_name} Quiz[/b]",
            markup=True, font_size=26, color=THEME_STATE["text"], size_hint_y=0.25
        ))
        self.card.add_widget(Label(
            text=f"Total Questions: [b]{total_q}[/b]\nTotal Marks: [b]{total_q}[/b]  (+1 per right answer)",
            markup=True, font_size=18, color=THEME_STATE["text"], halign='center', size_hint_y=0.25
        ))

        neg_row = BoxLayout(size_hint_y=None, height=55, spacing=10, padding=[10, 0])
        neg_row.add_widget(Label(text="[b]Negative Marking (-0.25)[/b]", markup=True, font_size=17, color=THEME_STATE["text"], size_hint_x=0.7))
        self.neg_switch = Switch(active=self.neg_marking, size_hint_x=0.3)
        neg_row.add_widget(self.neg_switch)
        self.card.add_widget(neg_row)

        start_btn = ModernButton(text="START QUIZ", size_hint_y=None, height=58, bg_color=(0.1, 0.6, 0.3, 1), font_size=20)
        start_btn.bind(on_press=self.begin_quiz)
        self.card.add_widget(start_btn)

        back_btn = ModernButton(text="Back", size_hint_y=None, height=48, bg_color=(0.45, 0.45, 0.5, 1))
        back_btn.bind(on_press=lambda x: goto(self.manager, self._exit_screen(), 'right'))
        self.card.add_widget(back_btn)

    def begin_quiz(self, instance):
        self.neg_marking = self.neg_switch.active
        random.shuffle(self.qs)
        self.q_idx = 0
        self.right_cnt = 0
        self.wrong_cnt = 0
        self.skip_cnt = 0
        self.marks = 0.0
        self.quiz_start_time = time.time()
        self.build_quiz_ui()
        self.load_q()

    def build_quiz_ui(self):
        self.card.clear_widgets()

        self.live_lbl = Label(text="", markup=True, font_size=15, color=(0.1, 0.5, 0.65, 1), size_hint_y=None, height=34, halign='center')
        self.card.add_widget(self.live_lbl)

        self.q_lbl = Label(text="", color=THEME_STATE["text"], font_size=19, text_size=(Window.width - 80, None), halign='center', size_hint_y=0.28)
        self.card.add_widget(self.q_lbl)

        self.opt_btns = []
        for _ in range(4):
            btn = ModernButton(text="", size_hint_y=None, height=52, bg_color=(0.9, 0.9, 0.9, 1))
            btn.color = (0.1, 0.1, 0.1, 1)
            btn.bind(on_press=self.check_ans)
            self.opt_btns.append(btn)
            self.card.add_widget(btn)

        self.exp_lbl = Label(text="", color=THEME_STATE["text"], font_size=14, text_size=(Window.width - 80, None), halign='center')
        self.card.add_widget(self.exp_lbl)

        action_row = BoxLayout(size_hint_y=None, height=50, spacing=10)
        self.skip_btn = ModernButton(text="Skip", bg_color=(0.55, 0.55, 0.6, 1))
        self.skip_btn.bind(on_press=self.skip_q)
        self.nxt_btn = ModernButton(text="Next", bg_color=(0.1, 0.55, 0.6, 1))
        self.nxt_btn.bind(on_press=self.nxt_q)
        action_row.add_widget(self.skip_btn)
        action_row.add_widget(self.nxt_btn)
        self.card.add_widget(action_row)

    def update_live_bar(self):
        att = self.right_cnt + self.wrong_cnt
        neg_tag = "Neg: ON" if self.neg_marking else "Neg: OFF"
        self.live_lbl.text = (
            f"[b]Marks: {fmt_marks(self.marks)}/{len(self.qs)}[/b]  |  "
            f"Att: {att}  |  R: {self.right_cnt}  |  W: {self.wrong_cnt}  |  "
            f"Skip: {self.skip_cnt}  |  {neg_tag}"
        )

    def load_q(self):
        q = self.qs[self.q_idx]
        self.update_live_bar()
        self.q_lbl.text = f"Q{self.q_idx + 1}/{len(self.qs)}: {q[0]}"
        for i in range(4):
            self.opt_btns[i].text = f"{['A', 'B', 'C', 'D'][i]}: {q[i + 1]}"
            self.opt_btns[i].set_color((0.9, 0.9, 0.9, 1))
            self.opt_btns[i].color = (0.1, 0.1, 0.1, 1)
            self.opt_btns[i].disabled = False
        self.ans = q[5]
        self.exp_lbl.text = ""
        self.skip_btn.disabled = False
        self.skip_btn.opacity = 1
        self.nxt_btn.disabled = True
        self.nxt_btn.opacity = 0.35
        self.q_start_t = time.time()

    def log_question(self, status, marks_delta, elapsed):
        try:
            conn = sqlite3.connect(STATS_DB_PATH)
            conn.execute("INSERT INTO Question_Logs (status, marks, time_spent) VALUES (?, ?, ?)", (status, marks_delta, elapsed))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def check_ans(self, btn):
        t = time.time() - self.q_start_t
        cl = btn.text[0]
        for b in self.opt_btns:
            b.disabled = True
        self.skip_btn.disabled = True
        self.skip_btn.opacity = 0.35

        if cl == self.ans:
            self.right_cnt += 1
            delta = 1.0
            self.marks += delta
            btn.set_color((0.2, 0.7, 0.3, 1))
            btn.color = (1, 1, 1, 1)
            self.log_question('right', delta, t)
        else:
            self.wrong_cnt += 1
            delta = -0.25 if self.neg_marking else 0.0
            self.marks += delta
            btn.set_color((0.8, 0.3, 0.3, 1))
            btn.color = (1, 1, 1, 1)
            for b in self.opt_btns:
                if b.text[0] == self.ans:
                    b.set_color((0.2, 0.7, 0.3, 1))
                    b.color = (1, 1, 1, 1)
            self.log_question('wrong', delta, t)

        self.update_live_bar()
        q = self.qs[self.q_idx]
        if q[6]:
            self.exp_lbl.text = f"Explanation: {q[6]}"
        self.nxt_btn.disabled = False
        self.nxt_btn.opacity = 1

    def skip_q(self, instance):
        t = time.time() - self.q_start_t
        self.skip_cnt += 1
        self.log_question('unattempted', 0.0, t)
        self.nxt_q(instance)

    def nxt_q(self, i):
        self.q_idx += 1
        if self.q_idx < len(self.qs):
            self.load_q()
        else:
            self.show_scorecard()

    def show_scorecard(self):
        self.card.clear_widgets()
        total = len(self.qs)
        att = self.right_cnt + self.wrong_cnt
        acc = (self.right_cnt / att * 100) if att > 0 else 0.0
        time_taken = int(time.time() - self.quiz_start_time)

        self.card.add_widget(Label(text="[b]Test Complete![/b]", markup=True, font_size=26, color=THEME_STATE["text"], size_hint_y=None, height=40))
        self.card.add_widget(Label(
            text=f"[b]Marks: {fmt_marks(self.marks)} / {total}[/b]",
            markup=True, font_size=30,
            color=(0.1, 0.6, 0.2, 1) if (self.marks / total) >= 0.6 else (0.8, 0.3, 0.1, 1),
            size_hint_y=None, height=46
        ))

        neg_txt = "ON (-0.25)" if self.neg_marking else "OFF"
        summary = (
            f"Attempted: [b]{att}[/b]   |   Unattempted: [b]{self.skip_cnt}[/b]\n"
            f"Right: [b]{self.right_cnt}[/b]   |   Wrong: [b]{self.wrong_cnt}[/b]\n"
            f"Accuracy: [b]{acc:.1f}%[/b]   |   Time: [b]{time_taken}s[/b]\n"
            f"Negative Marking: [b]{neg_txt}[/b]"
        )
        self.card.add_widget(Label(text=summary, markup=True, font_size=16, color=THEME_STATE["text"], halign='center'))

        self.share_lbl = Label(text="", color=(0, 0.6, 0, 1), size_hint_y=None, height=28)
        self.card.add_widget(self.share_lbl)

        share_btn = ModernButton(text="Share Score & Challenge", size_hint_y=None, height=58, bg_color=(0.8, 0.4, 0.1, 1))
        share_btn.bind(on_press=lambda x: self.share_score(acc, time_taken))
        self.card.add_widget(share_btn)

        exit_btn = ModernButton(text="Back to Menu", size_hint_y=None, height=50, bg_color=(0.3, 0.3, 0.3, 1))
        exit_btn.bind(on_press=lambda x: goto(self.manager, self._exit_screen(), 'right'))
        self.card.add_widget(exit_btn)

    def share_score(self, acc, time_taken):
        app = App.get_running_app()
        msg = (
            f"🔥 I scored {fmt_marks(self.marks)}/{len(self.qs)} marks ({acc:.1f}% accuracy) "
            f"in '{app.sel_quiz_name}' on Punjab Exam Academy! "
            f"(Right: {self.right_cnt}, Wrong: {self.wrong_cnt}, Skipped: {self.skip_cnt}) ⏱️ {time_taken}s.\n\n"
            f"Think you can beat me? Join t.me/punjabdruginspector and download the app!"
        )
        Clipboard.copy(msg)
        self.share_lbl.text = "Copied! Paste it in WhatsApp or Telegram"


# ==========================================
# ALL-TIME STATS SCREEN
# ==========================================
class StatsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.raw_marks = 0.0
        self.raw_total = 0
        self.raw_att = 0
        self.raw_acc = 0.0
        self.raw_spd = 0.0

        layout = BoxLayout(padding=20)
        self.card = GlassCard(orientation='vertical', padding=18, spacing=12)
        self.head = Label(text="[b]All-Time Performance[/b]", markup=True, font_size=24, color=THEME_STATE["text"], size_hint_y=0.14)
        self.card.add_widget(self.head)

        self.grid = GridLayout(cols=2, spacing=10, size_hint_y=0.58)
        self.l_marks = self.add_stat("Total Marks", "0 / 0")
        self.l_acc = self.add_stat("Accuracy", "0%")
        self.l_att = self.add_stat("Attempted", "0")
        self.l_unatt = self.add_stat("Unattempted", "0")
        self.l_rw = self.add_stat("Right / Wrong", "0 / 0")
        self.l_spd = self.add_stat("Avg Speed", "0s")
        self.card.add_widget(self.grid)

        self.share_lbl = Label(text="", color=(0, 0.6, 0, 1), size_hint_y=None, height=26)
        self.card.add_widget(self.share_lbl)

        flex_btn = ModernButton(text="Flex My Stats", size_hint_y=None, height=52, bg_color=(0.1, 0.6, 0.8, 1))
        flex_btn.bind(on_press=self.share_all_time)
        self.card.add_widget(flex_btn)

        b_btn = ModernButton(text="Back", size_hint_y=None, height=48, bg_color=(0.5, 0.5, 0.5, 1))
        b_btn.bind(on_press=lambda x: goto(self.manager, 'home', 'right'))
        self.card.add_widget(b_btn)
        layout.add_widget(self.card)
        self.add_widget(layout)

    def add_stat(self, title, val):
        box = BoxLayout(orientation='vertical')
        box.add_widget(Label(text=title, color=THEME_STATE["text"], font_size=14))
        lbl = Label(text=val, color=(0.1, 0.55, 0.6, 1), font_size=21, bold=True)
        box.add_widget(lbl)
        self.grid.add_widget(box)
        return lbl

    def on_pre_enter(self):
        sync_theme_from_db()
        self.card.refresh_glass()
        self.head.color = THEME_STATE["text"]
        try:
            conn = sqlite3.connect(STATS_DB_PATH)
            row = conn.execute(
                "SELECT "
                "COUNT(*), "
                "SUM(CASE WHEN status='right' THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN status='wrong' THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN status='unattempted' THEN 1 ELSE 0 END), "
                "SUM(marks), "
                "SUM(CASE WHEN status!='unattempted' THEN time_spent ELSE 0 END) "
                "FROM Question_Logs"
            ).fetchone()
            conn.close()
            if row and row[0] > 0:
                total, right, wrong, unatt, marks, att_time = row
                att = (right or 0) + (wrong or 0)
                self.raw_total = total
                self.raw_marks = marks or 0.0
                self.raw_att = att
                self.raw_acc = ((right or 0) / att * 100) if att > 0 else 0.0
                self.raw_spd = ((att_time or 0.0) / att) if att > 0 else 0.0

                self.l_marks.text = f"{fmt_marks(self.raw_marks)} / {total}"
                self.l_acc.text = f"{self.raw_acc:.1f}%"
                self.l_att.text = str(att)
                self.l_unatt.text = str(unatt or 0)
                self.l_rw.text = f"{right or 0} / {wrong or 0}"
                self.l_spd.text = f"{self.raw_spd:.1f}s"
        except Exception:
            pass

    def share_all_time(self, instance):
        msg = (
            f"🏆 My All-Time Stats on Punjab Exam Academy:\n"
            f"Marks: {fmt_marks(self.raw_marks)}/{self.raw_total} | Attempted: {self.raw_att} | "
            f"Accuracy: {self.raw_acc:.1f}% | Avg Speed: {self.raw_spd:.1f}s/Q!\n\n"
            f"Can you beat my score? Join t.me/punjabdruginspector to get the app."
        )
        Clipboard.copy(msg)
        self.share_lbl.text = "Copied! Paste in WhatsApp/Telegram"


class UnlockScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(padding=30)
        self.card = GlassCard(orientation='vertical', padding=30, spacing=20)
        self.head = Label(text="[b]Premium Access[/b]", markup=True, font_size=26, color=THEME_STATE["text"])
        self.info = Label(text="DM @punjabpharmacy on Telegram\nto get your unlock PIN.", font_size=16, color=THEME_STATE["text"], halign='center')
        self.code_in = TextInput(hint_text="Enter PIN...", size_hint_y=None, height=60, font_size=20, halign="center", multiline=False)
        self.status = Label(text="", color=(0.8, 0, 0, 1), size_hint_y=None, height=40)
        v_btn = ModernButton(text="VERIFY", size_hint_y=None, height=60, bg_color=(0.2, 0.7, 0.3, 1))
        v_btn.bind(on_press=self.check)
        b_btn = ModernButton(text="Back", size_hint_y=None, height=50, bg_color=(0.5, 0.5, 0.5, 1))
        b_btn.bind(on_press=lambda x: goto(self.manager, 'home', 'right'))
        for w in [self.head, self.info, self.code_in, self.status, v_btn, b_btn]:
            self.card.add_widget(w)
        layout.add_widget(self.card)
        self.add_widget(layout)

    def on_pre_enter(self):
        sync_theme_from_db()
        self.card.refresh_glass()
        self.head.color = THEME_STATE["text"]
        self.info.color = THEME_STATE["text"]

    def check(self, i):
        if self.code_in.text.strip().upper() == SECRET_PASSCODE:
            set_meta('is_premium', '1')
            self.status.text = "Premium Unlocked Permanently!"
            self.status.color = (0.2, 0.7, 0.3, 1)
        else:
            self.status.text = "Invalid PIN."


class StudentApp(App):
    sel_sub_id = None
    sel_sub_name = ""
    sel_chap_id = None
    sel_chap_name = ""
    sel_quiz_id = None
    sel_quiz_name = ""
    quiz_return_screen = 'quiz_list'

    def build(self):
        init_storage_paths(self)
        ensure_user_db()
        sync_theme_from_db()
        sm = ScreenManager()
        screens = [
            (HomeScreen, 'home'),
            (SubjectListScreen, 'subject_list'),
            (ChapterListScreen, 'chapter_list'),
            (QuizListScreen, 'quiz_list'),
            (ActiveQuizScreen, 'active_quiz'),
            (UnlockScreen, 'unlock'),
            (StatsScreen, 'stats')
        ]
        for cls, name in screens:
            sm.add_widget(cls(name=name))
        return sm


if __name__ == '__main__':
    StudentApp().run()
