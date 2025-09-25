import os
from datetime import datetime
from pathlib import Path
from flask import (
   Flask, render_template, request, redirect, url_for,
   flash, send_from_directory, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
   LoginManager, UserMixin, login_user, logout_user,
   login_required, current_user
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func
from typing import Optional, Iterable, Union
import requests  # для Telegram

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "devkey-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
   "DATABASE_URL",
   f"sqlite:///{BASE_DIR/'app.db'}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64MB

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "admin_login"


# --- HR Telegram (отклики на вакансии) ---
HR_BOT_TOKEN = "8433958065:AAHWno2pkaLwhw56qQ-5qZMNJOPszlIy2iQ"
HR_CHAT_ID = "1045702977"
HR_SEND_MESSAGE_URL = f"https://api.telegram.org/bot{HR_BOT_TOKEN}/sendMessage"


def send_hr_message(text: str) -> bool:
    try:
        r = requests.post(HR_SEND_MESSAGE_URL, data={"chat_id": HR_CHAT_ID, "text": text}, timeout=15)
        if not r.ok:
            print("HR telegram error:", r.text)
        return r.ok
    except Exception as e:
        print("HR telegram exception:", e)
        return False






# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class Admin(UserMixin, db.Model):
   __tablename__ = "admins"
   id = db.Column(db.Integer, primary_key=True)
   login = db.Column(db.String(64), unique=True, nullable=False)
   password_hash = db.Column(db.String(255), nullable=False)

   @staticmethod
   def create_default():
       """Create/ensure default admin from env."""
       login = os.getenv("ADMIN_LOGIN", "Bhniw2Ew;RraAwF")
       password = os.getenv("ADMIN_PASSWORD", "M5no%Oqk]xJIp/P")
       item = Admin.query.filter_by(login=login).first()
       if not item:
           item = Admin(login=login, password_hash=generate_password_hash(password))
           db.session.add(item)
           db.session.commit()

class News(db.Model):
   __tablename__ = "news"
   id = db.Column(db.Integer, primary_key=True)
   title = db.Column(db.String(255), nullable=False)
   excerpt = db.Column(db.String(600))
   body = db.Column(db.Text)
   cover = db.Column(db.String(512))
   pinned = db.Column(db.Boolean, default=False, index=True)
   created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

   images = db.relationship(
       "NewsImage", backref="post", cascade="all,delete-orphan", lazy="dynamic"
   )

class NewsImage(db.Model):
   __tablename__ = "news_images"
   id = db.Column(db.Integer, primary_key=True)
   post_id = db.Column(db.Integer, db.ForeignKey("news.id"), nullable=False, index=True)
   path = db.Column(db.String(512), nullable=False)
   sort_order = db.Column(db.Integer, default=0, index=True)

class Employee(db.Model):
   __tablename__ = "employees"
   id = db.Column(db.Integer, primary_key=True)
   full_name = db.Column(db.String(255), nullable=False)
   title = db.Column(db.String(255), nullable=False)
   dept = db.Column(db.String(255), nullable=False)
   email = db.Column(db.String(255))
   phone = db.Column(db.String(64))
   photo = db.Column(db.String(512))
   span2 = db.Column(db.Boolean, default=False)
   sort_order = db.Column(db.Integer, index=True)

class Project(db.Model):
   __tablename__ = "projects"
   id = db.Column(db.Integer, primary_key=True)
   title = db.Column(db.String(255), nullable=False)       # заголовок на карточке/в модалке
   subtitle = db.Column(db.String(255))                    # подпись под заголовком на карточке
   image = db.Column(db.String(512))                       # путь/URL обложки
   description = db.Column(db.Text)                        # первый абзац в модалке
   purpose = db.Column(db.Text)                            # назначение
   advantages = db.Column(db.Text)                         # «;» разделённый список
   application = db.Column(db.Text)                        # применение
   created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Vacancy(db.Model):
    __tablename__ = "vacancies"
    id = db.Column(db.Integer, primary_key=True)


    # где вакансия: office / plant
    location = db.Column(db.String(16), nullable=False, index=True)  # "office" | "plant"


    # основные поля
    title = db.Column(db.String(255), nullable=False)                # должность
    salary = db.Column(db.String(255))                               # заработная плата (строкой, чтобы гибко)
    pay_period = db.Column(db.String(255))                           # частота выплат
    experience = db.Column(db.String(255))                           # опыт работы
    employment_type = db.Column(db.String(64))                       # полная | частичная
    schedule = db.Column(db.String(255))                             # график
    work_hours = db.Column(db.String(255))                           # рабочие часы
    work_format = db.Column(db.String(255))                          # формат работы (офис/смешанный/удалённо и т.п.)
    description = db.Column(db.Text)                                 # описание


    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


    @property
    def location_human(self) -> str:
        return "Офис (Новосибирск, Депутатская 2)" if self.location == "office" \
               else "Производство (Новосибирск, Электровозная 3 к1)"







# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
@login_manager.user_loader
def load_user(uid):
   return Admin.query.get(int(uid))

def save_upload(file_storage) -> Optional[str]:
   """Save uploaded file into static/uploads and return relative path like 'static/uploads/xxx.jpg'."""
   if not file_storage or not getattr(file_storage, "filename", ""):
       return None
   filename = secure_filename(file_storage.filename)
   if not filename:
       return None
   dest = UPLOAD_DIR / filename
   # avoid collision
   stem, ext = dest.stem, dest.suffix
   i = 1
   while dest.exists():
       dest = UPLOAD_DIR / f"{stem}_{i}{ext}"
       i += 1
   file_storage.save(dest)
   rel = dest.relative_to(BASE_DIR).as_posix()
   return rel  # e.g. 'static/uploads/img_1.jpg'

def next_employee_order() -> int:
   max_val = db.session.query(func.max(Employee.sort_order)).scalar()
   return (max_val or 0) + 1

# ------------------------ Telegram helpers ------------------------
TELEGRAM_BOT_TOKEN = "8259098255:AAEX9DooJ__4TbuaZAXhN79aOxfokHHI0ko"
TELEGRAM_CHAT_ID = "1098660825"
TG_SEND_MESSAGE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
TG_SEND_DOCUMENT_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"

def send_telegram_message(text: str) -> bool:
   """Отправка текстового сообщения в Telegram."""
   try:
       r = requests.post(
           TG_SEND_MESSAGE_URL,
           data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
           timeout=15,
       )
       if not r.ok:
           print("Telegram sendMessage error:", r.text)
       return r.ok
   except Exception as e:
       print("Telegram sendMessage exception:", e)
       return False

def send_telegram_document(doc: Union[str, Path, object], caption: Optional[str] = None) -> bool:
   """
   Отправить документ ЛЮБОГО формата в Telegram.
   doc:
     - URL (str) -> отправится по ссылке
     - локальный путь (str|Path) -> отправится содержимое файла
     - FileStorage/файловый объект (имеет .read/.stream/.filename)
   """
   data = {"chat_id": TELEGRAM_CHAT_ID}
   if caption:
       data["caption"] = caption

   try:
       # 1) Ссылка
       if isinstance(doc, (str, Path)):
           doc = str(doc)
           if doc.startswith("http://") or doc.startswith("https://"):
               data["document"] = doc
               r = requests.post(TG_SEND_DOCUMENT_URL, data=data, timeout=30)
               if not r.ok:
                   print("Telegram sendDocument(url) error:", r.text)
               return r.ok

           # 2) Локальный путь
           p = Path(doc)
           if not p.exists() or not p.is_file():
               print("send_telegram_document: file not found:", p)
               return False
           with p.open("rb") as f:
               files = {"document": (p.name, f)}
               r = requests.post(TG_SEND_DOCUMENT_URL, data=data, files=files, timeout=60)
               if not r.ok:
                   print("Telegram sendDocument(file) error:", r.text)
               return r.ok

       # 3) FileStorage / файловый-like объект
       fs = doc
       filename = getattr(fs, "filename", None) or "file"
       stream = getattr(fs, "stream", None) or getattr(fs, "read", None)
       if hasattr(stream, "seek"):
           try:
               stream.seek(0)
           except Exception:
               pass

       file_tuple = (filename, stream if hasattr(stream, "read") else fs)
       files = {"document": file_tuple}
       r = requests.post(TG_SEND_DOCUMENT_URL, data=data, files=files, timeout=60)
       if not r.ok:
           print("Telegram sendDocument(filestorage) error:", r.text)
       return r.ok

   except Exception as e:
       print("Telegram sendDocument exception:", e)
       return False

# -----------------------------------------------------------------------------
# Public routes (match templates)
# -----------------------------------------------------------------------------
@app.route("/")
def home():
   # Можно ничего не передавать — шаблон умеет работать и без списка проектов.
   # Если хочешь показывать последние 5 проектов из БД на главной —
   # раскомментируй две строки ниже и передай в шаблон:
   # projects_latest = Project.query.order_by(Project.created_at.desc(), Project.id.desc()).limit(5).all()
   # return render_template("index.html", projects_latest=projects_latest)
   return render_template("index.html")

@app.route("/about")
def about():
   employees = (
       Employee.query
       .order_by(Employee.sort_order.asc().nulls_last(), Employee.id.asc())
       .all()
   )
   depts = sorted(
       set(e.dept.strip() for e in employees if e.dept),
       key=lambda d: d.lower()
   )
   return render_template("about.html", employees=employees, depts=depts)

@app.route("/products")
def products():
   return render_template("products.html")

@app.route("/clients")
def clients():
   projects = Project.query.order_by(Project.created_at.desc(), Project.id.desc()).all()
   return render_template("clients.html", projects=projects)

@app.route("/faq")
def faq():
   return render_template("faq.html")


@app.route("/vacancies")
def vacancies():
    items = Vacancy.query.order_by(Vacancy.created_at.desc(), Vacancy.id.desc()).all()
    # адреса офис/производство для вывода
    addr_office = "Новосибирск, Депутатская 2"
    addr_plant = "Новосибирск, Электровозная 3 к1"
    return render_template("vacancies.html", items=items,
                           addr_office=addr_office, addr_plant=addr_plant)


@app.post("/vacancies/<int:vid>/apply")
def vacancy_apply(vid: int):
    v = Vacancy.query.get_or_404(vid)
    name = (request.form.get("name") or "—").strip()
    phone = (request.form.get("phone") or "—").strip()
    note = (request.form.get("note") or "—").strip()


    text = (
        "🧩 Новый отклик на вакансию\n\n"
        f"Вакансия: {v.title}\n"
        f"Локация: {v.location_human}\n\n"
        f"👤 ФИО: {name}\n"
        f"📞 Телефон: {phone}\n"
        f"✍️ Комментарий:\n{note}"
    )
    ok = send_hr_message(text)
    flash("Отклик отправлен HR" if ok else "Не удалось отправить отклик, попробуйте ещё раз", "success" if ok else "error")
    return redirect(url_for("vacancies"))





# ---------- Admin: Vacancies ----------
@app.route("/admin/vacancies")
@login_required
def admin_vacancies_list():
    items = Vacancy.query.order_by(Vacancy.created_at.desc(), Vacancy.id.desc()).all()
    return render_template("admin/vacancies_list.html", items=items)


@app.route("/admin/vacancies/create", methods=["GET", "POST"])
@login_required
def admin_vacancy_create():
    if request.method == "POST":
        v = Vacancy(
            location=(request.form.get("location") or "office"),
            title=(request.form.get("title") or "").strip(),
            salary=request.form.get("salary") or None,
            pay_period=request.form.get("pay_period") or None,
            experience=request.form.get("experience") or None,
            employment_type=request.form.get("employment_type") or None,
            schedule=request.form.get("schedule") or None,
            work_hours=request.form.get("work_hours") or None,
            work_format=request.form.get("work_format") or None,
            description=request.form.get("description") or None,
        )
        db.session.add(v)
        db.session.commit()
        flash("Вакансия создана", "success")
        return redirect(url_for("admin_vacancies_list"))
    return render_template("admin/vacancy_form.html", item=None)


@app.route("/admin/vacancies/<int:vid>/edit", methods=["GET", "POST"])
@login_required
def admin_vacancy_edit(vid: int):
    item = Vacancy.query.get_or_404(vid)
    if request.method == "POST":
        item.location = (request.form.get("location") or item.location)
        item.title = (request.form.get("title") or "").strip()
        item.salary = request.form.get("salary") or None
        item.pay_period = request.form.get("pay_period") or None
        item.experience = request.form.get("experience") or None
        item.employment_type = request.form.get("employment_type") or None
        item.schedule = request.form.get("schedule") or None
        item.work_hours = request.form.get("work_hours") or None
        item.work_format = request.form.get("work_format") or None
        item.description = request.form.get("description") or None


        db.session.commit()
        flash("Сохранено", "success")
        return redirect(url_for("admin_vacancies_list"))
    return render_template("admin/vacancy_form.html", item=item)


@app.post("/admin/vacancies/<int:vid>/delete")
@login_required
def admin_vacancy_delete(vid: int):
    item = Vacancy.query.get_or_404(vid)
    db.session.delete(item)
    db.session.commit()
    flash("Удалено", "success")
    return redirect(url_for("admin_vacancies_list"))







@app.route("/news")
def news():
   posts = News.query.order_by(News.created_at.desc()).all()
   highlighted = (
       News.query.filter_by(pinned=True)
       .order_by(News.created_at.desc())
       .first()
   )
   return render_template("news.html", posts=posts, highlighted=highlighted)

@app.route("/news/<int:pid>")
def news_detail(pid):
   post = News.query.get_or_404(pid)

   # 1) Фото из БД в порядке сортировки
   images = (post.images
             .order_by(NewsImage.sort_order.asc(), NewsImage.id.asc())
             .all())

   # 2) Соберём единый список "слайдов": сначала cover, затем images
   slides = []
   if post.cover:
       slides.append({"path": post.cover})
   for img in images:
       # если вдруг cover уже совпадает с одним из путей — не дублируем
       if not post.cover or img.path != post.cover:
           slides.append({"path": img.path})

   # 3) Боковая колонка "Последние"
   recent = (News.query
             .filter(News.id != pid)
             .order_by(News.created_at.desc())
             .limit(5)
             .all())

   # 4) (Опционально) если показываете «fallback» в боковой — можно ещё передать все посты
   posts = News.query.order_by(News.created_at.desc()).all()

   return render_template("news_detail.html",
                          post=post,
                          gallery=slides,   # <— ЕДИНЫЙ список слайдов (cover+images)
                          recent=recent,
                          posts=posts)

# ------------------------ CONTACT -> Telegram (text + any docs) ------------------------
@app.route("/contact", methods=["GET", "POST"])
def contact():
   if request.method == "POST":
       # Поля формы
       name = (request.form.get("name") or "Гость").strip()
       email = (request.form.get("email") or "—").strip()
       phone = (request.form.get("phone") or "—").strip()
       message = (request.form.get("message") or "—").strip()

       # 1) Текст
       text = (
           "📩 Новое сообщение с сайта\n\n"
           f"👤 Имя: {name}\n"
           f"📧 Email: {email}\n"
           f"📞 Телефон: {phone}\n"
           f"💬 Сообщение:\n{message}"
       )
       ok_msg = send_telegram_message(text)

       # 2) Прикреплённые файлы (любые поля/имена)
       file_keys = ("attachments", "attachment", "document", "file", "files")
       files_to_send = []
       for k in file_keys:
           for fs in request.files.getlist(k):
               if fs and fs.filename:
                   files_to_send.append(fs)

       # 3) Ссылки на файлы по полям file_urls/doc_urls (по одной ссылке в строке)
       url_fields = ("file_urls", "doc_urls")
       url_list = []
       for fkey in url_fields:
           raw = request.form.get(fkey) or ""
           for line in raw.splitlines():
               u = line.strip()
               if u:
                   url_list.append(u)

       ok_files = True
       for fs in files_to_send:
           caption = f"📎 Файл: {fs.filename}\nОт: {name} ({email}, {phone})"
           # отправка файла напрямую
           try:
               # переиспользуем send_telegram_document из above
               if not send_telegram_document(fs, caption=caption):
                   ok_files = False
           except Exception as e:
               print("send doc error:", e)
               ok_files = False

       for u in url_list:
           caption = f"🔗 Файл по ссылке\nОт: {name} ({email}, {phone})"
           if not send_telegram_document(u, caption=caption):
               ok_files = False

       if ok_msg and ok_files:
           flash("Сообщение и вложения отправлены!", "success")
       elif ok_msg and not ok_files:
           flash("Сообщение отправлено, но часть файлов отправить не удалось.", "warning")
       else:
           flash("Не удалось отправить сообщение. Попробуйте ещё раз.", "error")

       return redirect(url_for("success", name=name))

   return render_template("contact.html")

# -----------------------------------------------------------------------------
# Admin: Projects CRUD
# -----------------------------------------------------------------------------
@app.route("/admin/projects")
@login_required
def admin_projects_list():
   items = Project.query.order_by(Project.created_at.desc(), Project.id.desc()).all()
   return render_template("admin/projects_list.html", items=items)

@app.route("/admin/projects/create", methods=["GET", "POST"])
@login_required
def admin_project_create():
   if request.method == "POST":
       title = (request.form.get("title") or "").strip()
       subtitle = request.form.get("subtitle") or None
       image = request.form.get("image") or None
       desc = request.form.get("description") or None
       purpose = request.form.get("purpose") or None
       advantages = request.form.get("advantages") or None
       application = request.form.get("application") or None

       # загрузка файла
       file = request.files.get("image_file")
       if file:
           saved = save_upload(file)
           if saved:
               image = saved

       p = Project(title=title, subtitle=subtitle, image=image,
                   description=desc, purpose=purpose,
                   advantages=advantages, application=application)
       db.session.add(p)
       db.session.commit()
       flash("Решение добавлено", "success")
       return redirect(url_for("admin_projects_list"))
   return render_template("admin/project_form.html", item=None)

@app.route("/admin/projects/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def admin_project_edit(pid: int):
   item = Project.query.get_or_404(pid)
   if request.method == "POST":
       item.title = (request.form.get("title") or "").strip()
       item.subtitle = request.form.get("subtitle") or None
       image = request.form.get("image") or item.image
       file = request.files.get("image_file")
       if file:
           saved = save_upload(file)
           if saved:
               image = saved
       item.image = image
       item.description = request.form.get("description") or None
       item.purpose = request.form.get("purpose") or None
       item.advantages = request.form.get("advantages") or None
       item.application = request.form.get("application") or None

       db.session.commit()
       flash("Сохранено", "success")
       return redirect(url_for("admin_projects_list"))
   return render_template("admin/project_form.html", item=item)

@app.post("/admin/projects/<int:pid>/delete")
@login_required
def admin_project_delete(pid: int):
   item = Project.query.get_or_404(pid)
   db.session.delete(item)
   db.session.commit()
   flash("Удалено", "success")
   return redirect(url_for("admin_projects_list"))

# -----------------------------------------------------------------------------
# Success page
# -----------------------------------------------------------------------------
@app.route("/success")
def success():
   name = request.args.get("name", "Гость")
   return render_template("success.html", name=name)

# -----------------------------------------------------------------------------
# Admin: auth (Flask-Login)
# -----------------------------------------------------------------------------
ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "Bhniw2Ew;RraAwF")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "M5no%Oqk]xJIp/P")

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
   # Гарантируем, что админ из окружения существует
   env_admin = Admin.query.filter_by(login=ADMIN_LOGIN).first()
   if not env_admin:
       env_admin = Admin(login=ADMIN_LOGIN, password_hash=generate_password_hash(ADMIN_PASSWORD))
       db.session.add(env_admin)
       db.session.commit()

   if request.method == "POST":
       login_val = request.form.get("login","")
       password = request.form.get("password","")

       # если логин совпал с тем, что в окружении — на всякий случай синхронизируем пароль
       if login_val == ADMIN_LOGIN and not check_password_hash(env_admin.password_hash, ADMIN_PASSWORD):
           env_admin.password_hash = generate_password_hash(ADMIN_PASSWORD)
           db.session.commit()

       user = Admin.query.filter_by(login=login_val).first()
       if user and check_password_hash(user.password_hash, password):
           login_user(user)
           flash("Успешный вход", "success")
           return redirect(url_for("admin_dashboard"))
       flash("Неверный логин или пароль", "warning")

   return render_template("admin/login.html")

@app.route("/admin/logout", methods=["GET","POST"])
@login_required
def admin_logout():
   logout_user()
   return redirect(url_for("admin_login"))

# -----------------------------------------------------------------------------
# Admin: dashboard
# -----------------------------------------------------------------------------
@app.route("/admin")
@login_required
def admin_dashboard():
   cnt_news = db.session.query(func.count(News.id)).scalar() or 0
   cnt_emp = db.session.query(func.count(Employee.id)).scalar() or 0
   return render_template("admin/dashboard.html", cnt_news=cnt_news, cnt_emp=cnt_emp)

# -----------------------------------------------------------------------------
# Admin: News CRUD + images
# -----------------------------------------------------------------------------
@app.route("/admin/news")
@login_required
def admin_news_list():
   posts = News.query.order_by(News.created_at.desc()).all()
   return render_template("admin/news_list.html", posts=posts)

@app.route("/admin/news/create", methods=["GET", "POST"])
@login_required
def admin_news_create():
   if request.method == "POST":
       title = request.form.get("title", "").strip()
       excerpt = request.form.get("excerpt") or None
       body = request.form.get("body") or None
       pinned = bool(request.form.get("pinned"))
       cover = request.form.get("cover") or None
       cover_file = request.files.get("cover_file")
       if cover_file:
           saved = save_upload(cover_file)
           if saved:
               cover = saved

       post = News(title=title, excerpt=excerpt, body=body, pinned=pinned, cover=cover)
       db.session.add(post)
       db.session.commit()

       # gallery (files)
       for fs in request.files.getlist("gallery_files"):
           path = save_upload(fs)
           if path:
               db.session.add(NewsImage(post_id=post.id, path=path, sort_order=0))
       # gallery (urls)
       urls_raw = request.form.get("gallery_urls") or ""
       for line in urls_raw.splitlines():
           u = line.strip()
           if u:
               db.session.add(NewsImage(post_id=post.id, path=u, sort_order=0))
       db.session.commit()

       flash("Новость создана", "success")
       return redirect(url_for("admin_news_list"))
   return render_template("admin/news_form.html", post=None, images=None)

@app.route("/admin/news/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def admin_news_edit(pid: int):
   post = News.query.get_or_404(pid)
   if request.method == "POST":
       post.title = request.form.get("title", "").strip()
       post.excerpt = request.form.get("excerpt") or None
       post.body = request.form.get("body") or None
       post.pinned = bool(request.form.get("pinned"))

       cover = request.form.get("cover") or post.cover
       cover_file = request.files.get("cover_file")
       if cover_file:
           saved = save_upload(cover_file)
           if saved:
               cover = saved
       post.cover = cover

       # обновление порядка картинок (sort_<id>)
       for img in post.images.all():
           key = f"sort_{img.id}"
           if key in request.form:
               try:
                   img.sort_order = int(request.form[key])
               except ValueError:
                   pass
       # добавление новых файлов/URL
       for fs in request.files.getlist("gallery_files"):
           path = save_upload(fs)
           if path:
               db.session.add(NewsImage(post_id=post.id, path=path, sort_order=0))
       urls_raw = request.form.get("gallery_urls") or ""
       for line in urls_raw.splitlines():
           u = line.strip()
           if u:
               db.session.add(NewsImage(post_id=post.id, path=u, sort_order=0))

       db.session.commit()
       flash("Сохранено", "success")
       return redirect(url_for("admin_news_list"))
   images = post.images.order_by(NewsImage.sort_order.asc(), NewsImage.id.asc()).all()
   return render_template("admin/news_form.html", post=post, images=images)

@app.post("/admin/news/<int:pid>/delete")
@login_required
def admin_news_delete(pid: int):
   post = News.query.get_or_404(pid)
   db.session.delete(post)
   db.session.commit()
   flash("Удалено", "success")
   return redirect(url_for("admin_news_list"))

@app.post("/admin/news/<int:pid>/image/<int:iid>/delete")
@login_required
def admin_news_image_delete(pid: int, iid: int):
   # находим пост
   post = News.query.get_or_404(pid)
   # находим фото, принадлежащее этому посту
   img = post.images.filter_by(id=iid).first_or_404()
   # удаляем запись
   db.session.delete(img)
   db.session.commit()
   flash("Фото удалено", "success")
   return redirect(url_for("admin_news_edit", pid=pid))

# -----------------------------------------------------------------------------
# Admin: Team (Employees) CRUD + move up/down
# -----------------------------------------------------------------------------
@app.route("/admin/team")
@login_required
def admin_team_list():
   employees = (
       Employee.query
       .order_by(Employee.sort_order.asc().nulls_last(), Employee.id.asc())
       .all()
   )
   return render_template("admin/team_list.html", employees=employees)

@app.route("/admin/team/create", methods=["GET", "POST"])
@login_required
def admin_team_create():
   if request.method == "POST":
       emp = Employee(
           full_name=request.form.get("full_name", "").strip(),
           title=request.form.get("title", "").strip(),
           dept=request.form.get("dept", "").strip(),
           email=(request.form.get("email") or None),
           phone=(request.form.get("phone") or None),
           span2=bool(request.form.get("span2")),
           sort_order=next_employee_order()
       )
       # фото: либо URL, либо файл
       photo = request.form.get("photo")
       photo_file = request.files.get("photo_file")
       if photo_file:
           saved = save_upload(photo_file)
           if saved:
               photo = saved
       emp.photo = photo

       db.session.add(emp)
       db.session.commit()
       flash("Сотрудник добавлен", "success")
       return redirect(url_for("admin_team_list"))
   return render_template("admin/team_form.html", emp=None)

@app.route("/admin/team/<int:eid>/edit", methods=["GET", "POST"])
@login_required
def admin_team_edit(eid: int):
   emp = Employee.query.get_or_404(eid)
   if request.method == "POST":
       emp.full_name = request.form.get("full_name", "").strip()
       emp.title = request.form.get("title", "").strip()
       emp.dept = request.form.get("dept", "").strip()
       emp.email = request.form.get("email") or None
       emp.phone = request.form.get("phone") or None
       emp.span2 = bool(request.form.get("span2"))

       photo = request.form.get("photo") or emp.photo
       photo_file = request.files.get("photo_file")
       if photo_file:
           saved = save_upload(photo_file)
           if saved:
               photo = saved
       emp.photo = photo

       db.session.commit()
       flash("Сохранено", "success")
       return redirect(url_for("admin_team_list"))
   return render_template("admin/team_form.html", emp=emp)

@app.post("/admin/team/<int:eid>/delete")
@login_required
def admin_team_delete(eid: int):
   emp = Employee.query.get_or_404(eid)
   db.session.delete(emp)
   db.session.commit()
   flash("Удалено", "success")
   return redirect(url_for("admin_team_list"))

# --- move up / move down ---
@app.post("/admin/team/<int:eid>/up")
@login_required
def admin_team_move_up(eid: int):
   cur = Employee.query.get_or_404(eid)
   if cur.sort_order is None:
       cur.sort_order = next_employee_order()
       db.session.commit()

   prev_emp = (
       Employee.query
       .filter(Employee.sort_order < cur.sort_order)
       .order_by(Employee.sort_order.desc())
       .first()
   )
   if not prev_emp:
       flash("Уже на самом верху", "info")
       return redirect(url_for("admin_team_list"))

   cur.sort_order, prev_emp.sort_order = prev_emp.sort_order, cur.sort_order
   db.session.commit()
   return redirect(url_for("admin_team_list"))

@app.post("/admin/team/<int:eid>/down")
@login_required
def admin_team_move_down(eid: int):
   cur = Employee.query.get_or_404(eid)
   if cur.sort_order is None:
       cur.sort_order = next_employee_order()
       db.session.commit()

   next_emp = (
       Employee.query
       .filter(Employee.sort_order > cur.sort_order)
       .order_by(Employee.sort_order.asc())
       .first()
   )
   if not next_emp:
       flash("Уже в самом низу", "info")
       return redirect(url_for("admin_team_list"))

   cur.sort_order, next_emp.sort_order = next_emp.sort_order, cur.sort_order
   db.session.commit()
   return redirect(url_for("admin_team_list"))

# -----------------------------------------------------------------------------
# Files (serve uploads in dev)
# -----------------------------------------------------------------------------
@app.route("/uploads/<path:name>")
def uploads(name):
   # На проде эти файлы должен отдавать веб-сервер (nginx). Это — для dev.
   return send_from_directory(UPLOAD_DIR, name)

# -----------------------------------------------------------------------------
# CLI helpers
# -----------------------------------------------------------------------------
@app.cli.command("init-db")
def init_db():
   """flask init-db: создать БД и дефолтного админа"""
   db.create_all()
   Admin.create_default()
   # Инициализируем sort_order у сотрудников, если пусто
   emps = Employee.query.order_by(Employee.id.asc()).all()
   changed = False
   cur = 1
   for e in emps:
       if e.sort_order is None:
           e.sort_order = cur
           cur += 1
           changed = True
   if changed:
       db.session.commit()
   print("DB ready.")

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
if __name__ == "__main__":
   with app.app_context():
       db.create_all()
       Admin.create_default()
   app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))



