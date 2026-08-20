import os
import secrets
import time
from datetime import datetime
from flask import Flask, request, jsonify, session, render_template, redirect, make_response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text

# Корректное определение абсолютных путей для Vercel Serverless
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mars-messenger-super-secret-key-2026')

# Настройка базы данных
db_url = os.environ.get('DATABASE_URL', 'sqlite:////tmp/mars.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,   # проверяет соединение перед использованием, переоткрывает если Neon его закрыл
    'pool_recycle': 280,     # переоткрывать соединение до того, как Neon/pgbouncer сам его закроет
}

db = SQLAlchemy(app)

# ==================== МОДЕЛИ ====================

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='user')
    bio = db.Column(db.Text, default='Исследователь Марса')
    custom_status = db.Column(db.String(50), default='На Марсе 🚀')
    theme = db.Column(db.String(30), default='mars')
    avatar_url = db.Column(db.Text, default='')
    banner_url = db.Column(db.Text, default='')
    selected_frame = db.Column(db.String(50), default='none')
    coins = db.Column(db.Integer, default=100)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'bio': self.bio or 'Исследователь Марса',
            'custom_status': self.custom_status or 'На Марсе 🚀',
            'theme': self.theme or 'mars',
            'avatar_url': self.avatar_url or '',
            'banner_url': self.banner_url or '',
            'selected_frame': self.selected_frame or 'none',
            'coins': self.coins or 0,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'last_seen': self.last_seen.strftime('%Y-%m-%d %H:%M:%S') if self.last_seen else ''
        }

class Message(db.Model):
    __tablename__ = 'message'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id])

    def to_dict(self):
        return {
            'id': self.id,
            'sender_id': self.sender_id,
            'sender_name': self.sender.username if self.sender else 'Неизвестно',
            'sender_avatar': self.sender.avatar_url if self.sender else '',
            'sender_frame': self.sender.selected_frame if self.sender else 'none',
            'receiver_id': self.receiver_id,
            'content': self.content,
            'timestamp': self.timestamp.strftime('%H:%M:%S') if self.timestamp else ''
        }

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def render_app():
    """ Безопасная отдача index.html """
    current_user = get_current_user()
    try:
        return render_template('index.html', user=current_user)
    except Exception:
        index_file = os.path.join(TEMPLATE_DIR, 'index.html')
        if os.path.exists(index_file):
            with open(index_file, 'r', encoding='utf-8') as f:
                return f.read()
        return jsonify({'error': 'index.html not found'}), 404

def init_db():
    try:
        with app.app_context():
            db.create_all()
            columns_to_add = [
                ('role', 'VARCHAR(20) DEFAULT "user"'),
                ('bio', 'TEXT DEFAULT "Исследователь Марса"'),
                ('custom_status', 'VARCHAR(50) DEFAULT "На Марсе 🚀"'),
                ('theme', 'VARCHAR(30) DEFAULT "mars"'),
                ('avatar_url', 'TEXT DEFAULT ""'),
                ('banner_url', 'TEXT DEFAULT ""'),
                ('selected_frame', 'VARCHAR(50) DEFAULT "none"'),
                ('coins', 'INTEGER DEFAULT 100'),
                ('created_at', 'TIMESTAMP'),
                ('last_seen', 'TIMESTAMP')
            ]
            
            with db.engine.connect() as conn:
                for col_name, col_type in columns_to_add:
                    try:
                        conn.execute(text(f'ALTER TABLE "user" ADD COLUMN {col_name} {col_type};'))
                        conn.commit()
                    except Exception:
                        pass
    except Exception as e:
        print(f"Ошибка БД при старте: {e}")

try:
    init_db()
except Exception:
    pass

ADMIN_USERNAMES = ['MrDarko', 'Sunflower']

def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    try:
        user = User.query.get(user_id)
        if user:
            user.last_seen = datetime.utcnow()
            if user.username in ADMIN_USERNAMES and user.role != 'admin':
                user.role = 'admin'
            db.session.commit()
        return user
    except Exception:
        return None

# ==================== МАРШРУТЫ API И СТРАНИЦ ====================

@app.route('/api/status')
def status():
    return jsonify({"status": "online", "system": "Mars Messenger API", "version": "1.0"})

@app.route('/login', methods=['GET', 'POST'])
@app.route('/api/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_app()

    data = request.get_json(silent=True) or request.form
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password, password):
        if request.is_json:
            return jsonify({'error': 'Неверный логин или пароль'}), 400
        return render_app()

    if user.username in ADMIN_USERNAMES:
        user.role = 'admin'
    
    user.last_seen = datetime.utcnow()
    db.session.commit()
    session['user_id'] = user.id

    if request.is_json:
        return jsonify({'message': 'Успешный вход', 'user': user.to_dict()})
    return redirect('/')

@app.route('/register', methods=['GET', 'POST'])
@app.route('/api/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_app()

    data = request.get_json(silent=True) or request.form
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        if request.is_json:
            return jsonify({'error': 'Заполните все поля'}), 400
        return render_app()

    if User.query.filter_by(username=username).first():
        if request.is_json:
            return jsonify({'error': 'Имя пользователя уже занято'}), 400
        return render_app()

    hashed_pw = generate_password_hash(password)
    role = 'admin' if username in ADMIN_USERNAMES else 'user'
    
    new_user = User(
        username=username,
        password=hashed_pw,
        role=role,
        bio='Исследователь Марса',
        custom_status='На Марсе 🚀',
        theme='mars'
    )
    db.session.add(new_user)
    db.session.commit()

    session['user_id'] = new_user.id

    if request.is_json:
        return jsonify({'message': 'Регистрация успешна', 'user': new_user.to_dict()})
    return redirect('/')

@app.route('/logout', methods=['GET', 'POST'])
@app.route('/api/logout', methods=['GET', 'POST'])
def logout():
    session.pop('user_id', None)
    if request.is_json:
        return jsonify({'message': 'Вышли из системы'})
    return redirect('/')

# ==================== ВХОД ЧЕРЕЗ САЙТ ДЛЯ ДЕСКТОП-ПРИЛОЖЕНИЯ ====================
# Приложение открывает /auth/desktop-login?return_uri=http://127.0.0.1:PORT/callback
# в системном браузере. Пользователь логинится (или уже залогинен), после чего
# страница получает одноразовый код и редиректит браузер на return_uri?code=...
# Приложение принимает код на локальном сервере и меняет его на сессию через
# /api/auth/desktop/exchange.
# NOTE: коды хранятся в памяти процесса — на serverless (Vercel) это работает,
# пока оба запроса (issue + exchange) попадают на один и тот же тёплый инстанс,
# что в рамках одного логина за пару секунд почти всегда так и есть.
DESKTOP_LOGIN_CODES = {}
DESKTOP_CODE_TTL = 300  # секунд

@app.route('/auth/desktop-login', methods=['GET'])
def desktop_login_page():
    return_uri = request.args.get('return_uri', '')
    return f'''<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<title>Mars Messenger — вход для приложения</title>
<style>
  body {{ background:#07080C; color:#fff; font-family:Segoe UI,Arial,sans-serif;
         display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }}
  .card {{ background:#0F1015; border-radius:20px; padding:36px; width:340px; }}
  h1 {{ font-size:22px; margin:0 0 6px; }}
  p.sub {{ color:#9A9AA5; font-size:13px; margin:0 0 20px; }}
  input {{ width:100%; box-sizing:border-box; background:#1A1A20; border:none; border-radius:12px;
           color:#fff; padding:14px 16px; font-size:15px; margin-bottom:12px; }}
  button {{ width:100%; background:#7832FF; color:#fff; border:none; border-radius:12px;
            padding:14px; font-size:15px; font-weight:600; cursor:pointer; }}
  button:disabled {{ opacity:.5; cursor:default; }}
  .tabs {{ display:flex; gap:8px; margin-bottom:16px; }}
  .tabs span {{ color:#6EA8FF; cursor:pointer; font-size:13px; text-decoration:underline; }}
  .err {{ color:#F87171; font-size:13px; margin:-4px 0 12px; min-height:16px; }}
</style></head>
<body>
  <div class="card">
    <h1 id="title">Войти</h1>
    <p class="sub">Авторизуй Mars Messenger Desktop, чтобы продолжить в приложении.</p>
    <input id="username" placeholder="Login" autocomplete="username" />
    <input id="password" type="password" placeholder="Password" autocomplete="current-password" />
    <div class="err" id="err"></div>
    <button id="submit" onclick="submitForm()">Войти и продолжить в приложении</button>
    <div class="tabs"><span id="toggle" onclick="toggleMode()">Нет аккаунта? Зарегистрироваться</span></div>
  </div>
<script>
  let mode = 'login';
  const returnUri = {return_uri!r};

  function toggleMode() {{
    mode = mode === 'login' ? 'register' : 'login';
    document.getElementById('title').textContent = mode === 'login' ? 'Войти' : 'Регистрация';
    document.getElementById('toggle').textContent = mode === 'login'
      ? 'Нет аккаунта? Зарегистрироваться' : 'Уже есть аккаунт? Войти';
  }}

  async function callJson(url, options) {{
    const resp = await fetch(url, options);
    const text = await resp.text();
    let data;
    try {{ data = JSON.parse(text); }}
    catch (e) {{
      const preview = text.length > 150 ? text.slice(0, 150) + '…' : text;
      throw new Error('Сервер вернул ' + resp.status + ' и не-JSON ответ: ' + preview);
    }}
    if (!resp.ok) {{ throw new Error(data.error || ('Ошибка ' + resp.status)); }}
    return data;
  }}

  async function submitForm() {{
    const btn = document.getElementById('submit');
    const err = document.getElementById('err');
    err.textContent = '';
    btn.disabled = true;
    btn.textContent = 'Подождите…';
    try {{
      const username = document.getElementById('username').value.trim();
      const password = document.getElementById('password').value;
      const endpoint = mode === 'login' ? '/api/login' : '/api/register';

      await callJson(endpoint, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        credentials: 'include',
        body: JSON.stringify({{ username, password }})
      }});

      const codeData = await callJson('/api/auth/desktop/code', {{
        method: 'POST', credentials: 'include'
      }});

      if (returnUri) {{
        window.location.href = returnUri + (returnUri.includes('?') ? '&' : '?') + 'code=' + encodeURIComponent(codeData.code);
      }} else {{
        document.querySelector('.card').innerHTML = '<h1>Готово ✅</h1><p class="sub">Можешь вернуться в приложение.</p>';
      }}
    }} catch (e) {{
      err.textContent = e.message;
      btn.disabled = false;
      btn.textContent = 'Войти и продолжить в приложении';
    }}
  }}
</script>
</body></html>'''

@app.route('/api/auth/desktop/code', methods=['POST'])
def issue_desktop_code():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Необходима авторизация'}), 401

    code = secrets.token_urlsafe(24)
    DESKTOP_LOGIN_CODES[code] = {'user_id': user.id, 'expires': time.time() + DESKTOP_CODE_TTL}
    return jsonify({'code': code})

@app.route('/api/auth/desktop/exchange', methods=['POST'])
def exchange_desktop_code():
    data = request.get_json(silent=True) or {}
    code = data.get('code', '')

    entry = DESKTOP_LOGIN_CODES.pop(code, None)
    if not entry or entry['expires'] < time.time():
        return jsonify({'error': 'Код недействителен или истёк. Попробуй войти через сайт ещё раз.'}), 400

    user = User.query.get(entry['user_id'])
    if not user:
        return jsonify({'error': 'Пользователь не найден'}), 404

    session['user_id'] = user.id
    return jsonify({'message': 'Вход выполнен', 'user': user.to_dict()})

@app.route('/api/me', methods=['GET'])
def me():
    user = get_current_user()
    if not user:
        return jsonify({'authenticated': False}), 401
    return jsonify({'authenticated': True, 'user': user.to_dict()})

@app.route('/api/frames', methods=['GET'])
def list_frames():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Необходима авторизация'}), 401
    return jsonify({
        'frames': sorted(ALLOWED_FRAMES),
        'selected': user.selected_frame or 'none'
    })

@app.route('/api/profile/update', methods=['POST'])
def update_profile():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Необходима авторизация'}), 401

    data = request.get_json() or {}
    if 'bio' in data: user.bio = data['bio']
    if 'custom_status' in data: user.custom_status = data['custom_status']
    if 'theme' in data: user.theme = data['theme']
    if 'avatar_url' in data: user.avatar_url = data['avatar_url']
    if 'banner_url' in data: user.banner_url = data['banner_url']
    if 'selected_frame' in data: user.selected_frame = data['selected_frame']

    db.session.commit()
    return jsonify({'message': 'Профиль обновлен', 'user': user.to_dict()})

@app.route('/api/messages', methods=['GET', 'POST'])
def handle_messages():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Необходима авторизация'}), 401

    if request.method == 'POST':
        data = request.get_json() or {}
        content = data.get('content', '').strip()
        receiver_id = data.get('receiver_id')
        if not content:
            return jsonify({'error': 'Пустое сообщение'}), 400
        if not receiver_id:
            return jsonify({'error': 'Не указан получатель'}), 400
        msg = Message(sender_id=user.id, receiver_id=receiver_id, content=content)
        db.session.add(msg)
        db.session.commit()
        return jsonify({'message': 'Отправлено', 'data': msg.to_dict()})

    # GET: history of a private dialogue with ?with=<user_id>
    with_id = request.args.get('with', type=int)
    if not with_id:
        return jsonify({'error': 'Не указан собеседник (параметр with)'}), 400

    messages = Message.query.filter(
        db.or_(
            db.and_(Message.sender_id == user.id, Message.receiver_id == with_id),
            db.and_(Message.sender_id == with_id, Message.receiver_id == user.id)
        )
    ).order_by(Message.timestamp.desc()).limit(100).all()
    messages.reverse()
    return jsonify([m.to_dict() for m in messages])

@app.route('/api/users/search', methods=['GET'])
def search_users():
    """ Глубокий поиск по нику: и среди тех, с кем уже переписывались, и среди новых людей. """
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Необходима авторизация'}), 401

    q = request.args.get('q', '').strip()
    query = User.query.filter(User.id != user.id)
    if q:
        query = query.filter(User.username.ilike(f'%{q}%'))
    users = query.order_by(User.username.asc()).limit(30).all()
    return jsonify([u.to_dict() for u in users])

@app.route('/api/conversations', methods=['GET'])
def conversations():
    """ Список диалогов текущего пользователя: собеседник + последнее сообщение. """
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Необходима авторизация'}), 401

    msgs = Message.query.filter(
        db.or_(Message.sender_id == user.id, Message.receiver_id == user.id)
    ).filter(Message.receiver_id.isnot(None)).order_by(Message.timestamp.desc()).all()

    seen = set()
    result = []
    for m in msgs:
        other_id = m.receiver_id if m.sender_id == user.id else m.sender_id
        if other_id in seen:
            continue
        seen.add(other_id)
        other = User.query.get(other_id)
        if not other:
            continue
        result.append({
            'user': other.to_dict(),
            'last_message': m.content,
            'last_timestamp': m.timestamp.strftime('%H:%M:%S') if m.timestamp else ''
        })
    return jsonify(result)

@app.route('/api/admin/users', methods=['GET'])
def admin_users():
    user = get_current_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Доступ запрещен'}), 403
    users = User.query.order_by(User.id.asc()).all()
    return jsonify([u.to_dict() for u in users])

import base64

ALLOWED_THEMES = {'mars', 'purple', 'green'}
ALLOWED_FRAMES = {'none', 'crown', 'lightning', 'fire', 'dust', 'ufo', 'saturn', 'comet', 'rocket', 'alien', 'crystal'}

@app.route('/admin/manage-user/<int:user_id>', methods=['POST'])
def manage_user(user_id):
    admin = get_current_user()
    if not admin or admin.role != 'admin':
        return redirect('/')

    target = User.query.get(user_id)
    action = request.form.get('action', '')

    if target and action == 'toggle_role':
        target.role = 'user' if target.role == 'admin' else 'admin'
        db.session.commit()

    return redirect('/admin')

@app.route('/profile/update-bio', methods=['POST'])
def update_bio():
    user = get_current_user()
    if not user:
        return redirect('/login')

    data = request.get_json(silent=True) or request.form
    if 'custom_status' in data:
        user.custom_status = data.get('custom_status', '').strip() or user.custom_status
    if 'bio' in data:
        user.bio = data.get('bio', '').strip()

    db.session.commit()
    return redirect('/profile')

@app.route('/profile/update-theme', methods=['POST'])
def update_theme():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Необходима авторизация'}), 401

    data = request.get_json(silent=True) or {}
    theme = data.get('theme', '')
    if theme not in ALLOWED_THEMES:
        return jsonify({'error': 'Недопустимая тема'}), 400

    user.theme = theme
    db.session.commit()
    return jsonify({'message': 'Тема обновлена', 'theme': user.theme})

@app.route('/shop/buy-frame', methods=['POST'])
def buy_frame():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Необходима авторизация'}), 401

    data = request.get_json(silent=True) or {}
    frame_id = data.get('frame_id', '')
    if frame_id not in ALLOWED_FRAMES:
        return jsonify({'error': 'Недопустимая рамка'}), 400

    user.selected_frame = frame_id
    db.session.commit()
    return jsonify({'message': 'Рамка применена', 'selected_frame': user.selected_frame})

@app.route('/upload-avatar', methods=['POST'])
def upload_avatar():
    user = get_current_user()
    if not user:
        return redirect('/login')

    file = request.files.get('avatar')
    if not file or file.filename == '':
        return redirect('/profile')

    allowed_types = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}
    if file.mimetype not in allowed_types:
        return redirect('/profile')

    file_bytes = file.read()
    # Ограничение размера ~2MB, чтобы не раздувать базу
    if len(file_bytes) > 2 * 1024 * 1024:
        return redirect('/profile')

    encoded = base64.b64encode(file_bytes).decode('utf-8')
    user.avatar_url = f'data:{file.mimetype};base64,{encoded}'
    db.session.commit()

    return redirect('/profile')

@app.route('/profile', methods=['GET'])
def profile_page():
    user = get_current_user()
    if not user:
        return redirect('/login')
    return render_template('profile.html', user=user)

@app.route('/admin', methods=['GET'])
def admin_page():
    user = get_current_user()
    if not user or user.role != 'admin':
        return redirect('/')
    users = User.query.order_by(User.id.asc()).all()
    return render_template('admin.html', user=user, users=users)

# ==================== CATCH-ALL ROUTE ====================

@app.route('/', defaults={'path': ''}, methods=['GET'])
@app.route('/<path:path>', methods=['GET'])
def serve_spa(path):
    if path.startswith('api/'):
        return jsonify({'error': 'API endpoint not found'}), 404
    return render_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
