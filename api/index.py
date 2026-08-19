import os
from datetime import datetime
from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mars-messenger-super-secret-key-2026')

# Настройка базы данных (Neon.tech PostgreSQL или SQLite в /tmp для Vercel)
db_url = os.environ.get('DATABASE_URL', 'sqlite:////tmp/mars.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==================== МОДЕЛИ ====================

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='user')  # 'admin' или 'user'
    bio = db.Column(db.Text, default='Исследователь Марса')
    custom_status = db.Column(db.String(50), default='На Марсе 🚀')
    theme = db.Column(db.String(30), default='mars')
    avatar_url = db.Column(db.Text, default='')
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
            'selected_frame': self.selected_frame or 'none',
            'coins': self.coins or 0,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'last_seen': self.last_seen.strftime('%Y-%m-%d %H:%M:%S') if self.last_seen else ''
        }

class Message(db.Model):
    __tablename__ = 'message'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # None = Общий чат
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

# ==================== МИГРАЦИЯ И ИНИЦИАЛИЗАЦИЯ БД ====================

def init_db():
    try:
        with app.app_context():
            db.create_all()
            # Авто-добавление отсутствующих колонок в таблицу user
            columns_to_add = [
                ('role', 'VARCHAR(20) DEFAULT "user"'),
                ('bio', 'TEXT DEFAULT "Исследователь Марса"'),
                ('custom_status', 'VARCHAR(50) DEFAULT "На Марсе 🚀"'),
                ('theme', 'VARCHAR(30) DEFAULT "mars"'),
                ('avatar_url', 'TEXT DEFAULT ""'),
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
                        pass  # Колонка уже была создана ранее
    except Exception as e:
        print(f"Ошибка при инициализации БД: {e}")

init_db()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

ADMIN_USERNAMES = ['MrDarko', 'Sunflower']

def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    user = User.query.get(user_id)
    if user:
        user.last_seen = datetime.utcnow()
        # Выдача прав администратора ключевым аккаунтам
        if user.username in ADMIN_USERNAMES and user.role != 'admin':
            user.role = 'admin'
        db.session.commit()
    return user

# ==================== МАРШРУТЫ (ROUTES) ====================

@app.route('/')
def home():
    return jsonify({"status": "online", "system": "Mars Messenger API", "version": "1.0"})

# Регистрация
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'error': 'Заполните все поля'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Имя пользователя уже занято'}), 400

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
    return jsonify({'message': 'Регистрация успешна', 'user': new_user.to_dict()})

# Вход
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({'error': 'Неверный логин или пароль'}), 400

    if user.username in ADMIN_USERNAMES:
        user.role = 'admin'
    
    user.last_seen = datetime.utcnow()
    db.session.commit()

    session['user_id'] = user.id
    return jsonify({'message': 'Успешный вход', 'user': user.to_dict()})

# Выход
@app.route('/api/logout', methods=['POST', 'GET'])
def logout():
    session.pop('user_id', None)
    return jsonify({'message': 'Вышли из системы'})

# Данные текущего пользователя
@app.route('/api/me', methods=['GET'])
def me():
    user = get_current_user()
    if not user:
        return jsonify({'authenticated': False}), 401
    return jsonify({'authenticated': True, 'user': user.to_dict()})

# Обновление профиля
@app.route('/api/profile/update', methods=['POST'])
def update_profile():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Необходима авторизация'}), 401

    data = request.get_json() or {}
    
    if 'bio' in data:
        user.bio = data['bio']
    if 'custom_status' in data:
        user.custom_status = data['custom_status']
    if 'theme' in data:
        user.theme = data['theme']
    if 'avatar_url' in data:
        user.avatar_url = data['avatar_url']
    if 'selected_frame' in data:
        user.selected_frame = data['selected_frame']

    db.session.commit()
    return jsonify({'message': 'Профиль успешно обновлен', 'user': user.to_dict()})

# Смена пароля
@app.route('/api/change-password', methods=['POST'])
def change_password():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Необходима авторизация'}), 401

    data = request.get_json() or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not check_password_hash(user.password, old_password):
        return jsonify({'error': 'Старый пароль введен неверно'}), 400

    if len(new_password) < 4:
        return jsonify({'error': 'Пароль должен содержать не менее 4 символов'}), 400

    user.password = generate_password_hash(new_password)
    db.session.commit()
    return jsonify({'message': 'Пароль успешно изменен'})

# Чат и сообщения
@app.route('/api/messages', methods=['GET', 'POST'])
def handle_messages():
    user = get_current_user()
    
    if request.method == 'POST':
        if not user:
            return jsonify({'error': 'Необходима авторизация'}), 401

        data = request.get_json() or {}
        content = data.get('content', '').strip()
        receiver_id = data.get('receiver_id')

        if not content:
            return jsonify({'error': 'Сообщение не может быть пустым'}), 400

        msg = Message(
            sender_id=user.id,
            receiver_id=receiver_id if receiver_id else None,
            content=content
        )
        db.session.add(msg)
        db.session.commit()
        return jsonify({'message': 'Отправлено', 'data': msg.to_dict()})

    # Получение последних 50 сообщений общего чата
    messages = Message.query.filter_by(receiver_id=None).order_by(Message.timestamp.desc()).limit(50).all()
    messages.reverse()
    return jsonify([m.to_dict() for m in messages])

# Админ-панель: список пользователей
@app.route('/api/admin/users', methods=['GET'])
def admin_users():
    user = get_current_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Доступ запрещен'}), 403

    users = User.query.order_by(User.id.asc()).all()
    return jsonify([u.to_dict() for u in users])

# Админ-панель: смена роли пользователя
@app.route('/api/admin/user/<int:user_id>/role', methods=['POST'])
def admin_set_role(user_id):
    user = get_current_user()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Доступ запрещен'}), 403

    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({'error': 'Пользователь не найден'}), 404

    data = request.get_json() or {}
    new_role = data.get('role', 'user')
    target_user.role = new_role
    db.session.commit()
    return jsonify({'message': f'Роль пользователя {target_user.username} изменена на {new_role}'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
