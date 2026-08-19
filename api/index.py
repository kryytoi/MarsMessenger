import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.getenv('SECRET_KEY', 'mars_messenger_ultra_secret_2026')

# Подключение к Neon.tech
db_url = os.getenv('DATABASE_URL', 'sqlite:///local.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Список пользователей, которые получают ранг Администратора автоматически
ADMIN_USERNAMES = ['mrdarko', 'sunflower']

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(30), default='Пользователь')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    avatar_url = db.Column(db.Text, default='')
    active_frame = db.Column(db.String(50), default='crown') # По умолчанию доступна 'crown'

with app.app_context():
    db.create_all()

def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
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

    # Авто-ранг: MrDarko и Sunflower -> Администратор
    role = 'Администратор' if username.lower() in ADMIN_USERNAMES else 'Пользователь'
    hashed_password = generate_password_hash(password)
    
    # Генерация дефолтной аватарки
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
        
        # Обновляем ранг, если аккаунт MrDarko или Sunflower был создан ранее
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

@app.route('/update_profile', methods=['POST'])
def update_profile():
    user = get_current_user()
    if not user:
        return redirect(url_for('home'))

    avatar_url = request.form.get('avatar_url', '').strip()
    active_frame = request.form.get('active_frame', 'none')

    if avatar_url:
        user.avatar_url = avatar_url

    if active_frame in ['none', 'crown']:
        user.active_frame = active_frame

    db.session.commit()
    flash('Настройки профиля сохранены!', 'success')
    return redirect(url_for('profile'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Вы вышли из аккаунта.', 'info')
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
