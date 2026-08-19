import os
import base64
import requests
import time
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# Динамическое определение путей для Vercel
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)

app.secret_key = os.getenv('SECRET_KEY', 'mars_messenger_ultra_secret_2026')

# Если DATABASE_URL не задан (PostgreSQL), перенаправляем SQLite в изолированную временную папку /tmp
db_url = os.getenv('DATABASE_URL')
if not db_url:
    db_url = f"sqlite:///{os.path.join('/tmp', 'local.db')}"
elif db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

ADMIN_USERNAMES = ['mrdarko', 'sunflower']
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPO = "kryytoi/MarsMessenger"

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(30), default='Пользователь')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    avatar_url = db.Column(db.Text, default='')
    active_frame = db.Column(db.String(50), default='crown')

# Безопасное создание таблиц без аварийного завершения сервера
try:
    with app.app_context():
        db.create_all()
except Exception as err:
    print(f"Ошибка инициализации БД: {err}")

def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

def save_avatar_to_github(file_storage, username):
    if not GITHUB_TOKEN:
        return None
    
    file_bytes = file_storage.read()
    ext = file_storage.filename.split('.')[-1].lower() if '.' in file_storage.filename else 'png'
    filename = f"{username}_avatar.{ext}"
    
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/avatarks/{filename}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Проверяем, существует ли уже файл, чтобы получить его sha
    get_res = requests.get(url, headers=headers)
    sha = get_res.json().get('sha') if get_res.status_code == 200 else None

    content_b64 = base64.b64encode(file_bytes).decode('utf-8')
    data = {
        "message": f"Update avatar for {username}",
        "content": content_b64,
        "branch": "main"
    }
    if sha:
        data["sha"] = sha

    put_res = requests.put(url, json=data, headers=headers)
    if put_res.status_code in [200, 201]:
        # ?v=timestamp заставляет браузер и GitHub CDN сразу подгружать новую картинку
        timestamp = int(time.time())
        return f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/avatarks/{filename}?v={timestamp}"
    return None
@app.route('/')
def home():
    user = get_current_user()
    return render_template('index.html', user=user)

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    if not username or not password:
        flash('Заполните все поля!', 'error')
        return redirect(url_for('home'))

    if User.query.filter_by(username=username).first():
        flash('Пользователь с таким именем уже существует!', 'error')
        return redirect(url_for('home'))

    role = 'Администратор' if username.lower() in ADMIN_USERNAMES else 'Пользователь'
    hashed_password = generate_password_hash(password)
    default_avatar = f'https://api.dicebear.com/7.x/bottts/svg?seed={username}'

    new_user = User(
        username=username, 
        password_hash=hashed_password,
        role=role,
        avatar_url=default_avatar,
        active_frame='crown'
    )
    db.session.add(new_user)
    db.session.commit()

    session['user_id'] = new_user.id
    flash(f'Добро пожаловать в Mars, {username}!', 'success')
    return redirect(url_for('profile'))

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    user = User.query.filter_by(username=username).first()

    if user and check_password_hash(user.password_hash, password):
        session['user_id'] = user.id
        if user.username.lower() in ADMIN_USERNAMES and user.role != 'Администратор':
            user.role = 'Администратор'
            db.session.commit()

        flash('С возвращением на Марс!', 'success')
        return redirect(url_for('profile'))
    else:
        flash('Неверный логин или пароль!', 'error')
        return redirect(url_for('home'))

@app.route('/profile')
def profile():
    user = get_current_user()
    if not user:
        flash('Сначала войдите в аккаунт!', 'error')
        return redirect(url_for('home'))
    return render_template('profile.html', user=user)

@app.route('/upload-avatar', methods=['POST'])
def upload_avatar():
    user = get_current_user()
    if not user:
        return redirect(url_for('home'))

    if 'avatar' not in request.files:
        flash('Файл не выбран!', 'error')
        return redirect(url_for('profile'))
    
    file = request.files['avatar']
    if file.filename == '':
        flash('Файл не выбран!', 'error')
        return redirect(url_for('profile'))

    avatar_url = save_avatar_to_github(file, user.username)
    if avatar_url:
        user.avatar_url = avatar_url
        db.session.commit()
        flash('Аватарка успешно сохранена на GitHub!', 'success')
    else:
        flash('Ошибка при загрузке на GitHub. Проверьте GITHUB_TOKEN.', 'error')
    
    return redirect(url_for('profile'))

@app.route('/shop/buy-frame', methods=['POST'])
def buy_frame():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.get_json() or {}
    frame_id = data.get('frame_id', 'none')

    user.active_frame = frame_id
    db.session.commit()
    return jsonify({"success": True, "active_frame": frame_id})

@app.route('/change_password', methods=['POST'])
def change_password():
    user = get_current_user()
    if not user:
        return redirect(url_for('home'))

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')

    if not check_password_hash(user.password_hash, current_password):
        flash('Текущий пароль введён неверно!', 'error')
        return redirect(url_for('profile'))

    if len(new_password) < 4:
        flash('Новый пароль слишком короткий (минимум 4 символа)!', 'error')
        return redirect(url_for('profile'))

    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    flash('Пароль успешно изменён!', 'success')
    return redirect(url_for('profile'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Вы вышли из аккаунта.', 'info')
    return redirect(url_for('home'))
