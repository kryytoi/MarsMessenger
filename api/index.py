import os
import time
import base64
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)

app.secret_key = os.getenv('SECRET_KEY', 'mars_messenger_ultra_secret_2026')

db_url = os.getenv('DATABASE_URL')
if not db_url:
    db_url = f"sqlite:///{os.path.join('/tmp', 'local.db')}"
elif db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

ADMIN_USERNAMES = ['mrdarko', 'sunflower']

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(30), default='Пользователь')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    avatar_url = db.Column(db.Text, default='')
    active_frame = db.Column(db.String(50), default='crown')
    bio = db.Column(db.Text, default='Исследователь Марса')
    custom_status = db.Column(db.String(50), default='На Марсе 🚀')
    theme = db.Column(db.String(30), default='mars')
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def is_online(self):
        if not self.last_seen:
            return False
        return datetime.utcnow() - self.last_seen < timedelta(minutes=3)

try:
    with app.app_context():
        db.create_all()
except Exception as err:
    print(f"Ошибка БД: {err}")

def get_current_user():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            user.last_seen = datetime.utcnow()
            db.session.commit()
        return user
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
        flash('Пользователь уже существует!', 'error')
        return redirect(url_for('home'))

    role = 'Администратор' if username.lower() in ADMIN_USERNAMES else 'Пользователь'
    new_user = User(
        username=username, 
        password_hash=generate_password_hash(password),
        role=role,
        avatar_url=f'https://api.dicebear.com/7.x/bottts/svg?seed={username}',
        created_at=datetime.utcnow()
    )
    db.session.add(new_user)
    db.session.commit()
    session['user_id'] = new_user.id
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
        return redirect(url_for('profile'))
    
    flash('Неверный логин или пароль!', 'error')
    return redirect(url_for('home'))

@app.route('/profile')
def profile():
    user = get_current_user()
    if not user:
        return redirect(url_for('home'))
    return render_template('profile.html', user=user)

@app.route('/upload-avatar', methods=['POST'])
def upload_avatar():
    user = get_current_user()
    if not user or 'avatar' not in request.files:
        return redirect(url_for('profile'))
    
    file = request.files['avatar']
    if file.filename != '':
        file_bytes = file.read()
        if len(file_bytes) <= 2 * 1024 * 1024:
            ext = file.filename.split('.')[-1].lower() if '.' in file.filename else 'png'
            encoded_b64 = base64.b64encode(file_bytes).decode('utf-8')
            user.avatar_url = f"data:image/{ext};base64,{encoded_b64}"
            db.session.commit()
            flash('Аватарка обновлена!', 'success')
        else:
            flash('Файл слишком большой (макс 2 МБ)', 'error')
    return redirect(url_for('profile'))

@app.route('/profile/update-bio', methods=['POST'])
def update_bio():
    user = get_current_user()
    if user:
        user.bio = request.form.get('bio', '').strip()[:200]
        user.custom_status = request.form.get('custom_status', 'На Марсе 🚀').strip()[:50]
        db.session.commit()
        flash('Профиль обновлен!', 'success')
    return redirect(url_for('profile'))

@app.route('/profile/update-theme', methods=['POST'])
def update_theme():
    user = get_current_user()
    if user:
        data = request.get_json() or {}
        user.theme = data.get('theme', 'mars')
        db.session.commit()
        return jsonify({"success": True, "theme": user.theme})
    return jsonify({"success": False}), 401

@app.route('/shop/buy-frame', methods=['POST'])
def buy_frame():
    user = get_current_user()
    if not user:
        return jsonify({"success": False}), 401
    data = request.get_json() or {}
    user.active_frame = data.get('frame_id', 'none')
    db.session.commit()
    return jsonify({"success": True})

@app.route('/change_password', methods=['POST'])
def change_password():
    user = get_current_user()
    if not user:
        return redirect(url_for('home'))

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')

    if not check_password_hash(user.password_hash, current_password):
        flash('Текущий пароль неверный!', 'error')
    elif len(new_password) < 4:
        flash('Пароль слишком короткий!', 'error')
    else:
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash('Пароль изменён!', 'success')
    return redirect(url_for('profile'))

# --- АДМИН-ПАНЕЛЬ ---
@app.route('/admin')
def admin_panel():
    user = get_current_user()
    if not user or user.role != 'Администратор':
        flash('Доступ запрещен!', 'error')
        return redirect(url_for('home'))
    users = User.query.order_by(User.id.desc()).all()
    return render_template('admin.html', user=user, users=users)

@app.route('/admin/manage-user/<int:user_id>', methods=['POST'])
def manage_user(user_id):
    current = get_current_user()
    if not current or current.role != 'Администратор':
        return redirect(url_for('home'))
    
    target_user = User.query.get_or_404(user_id)
    action = request.form.get('action')
    
    if action == 'toggle_role':
        target_user.role = 'Пользователь' if target_user.role == 'Администратор' else 'Администратор'
    elif action == 'set_frame':
        target_user.active_frame = request.form.get('frame_id', 'none')
    
    db.session.commit()
    flash(f'Данные пользователя {target_user.username} обновлены!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))
