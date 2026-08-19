import base64
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
# ... твои остальные импорты ...

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")  # Добавь токен в Vercel Env Variables
GITHUB_REPO = "kryytoi/MarsMessenger"

def save_avatar_to_github(file_storage, username):
    if not GITHUB_TOKEN:
        return None
    
    file_bytes = file_storage.read()
    ext = file_storage.filename.split('.')[-1].lower()
    filename = f"{username}_avatar.{ext}"
    
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/avatarks/{filename}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    # Проверяем, существует ли файл, чтобы получить sha для перезаписи
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
        # Возвращаем прямую ссылку на аватарку
        return f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/avatarks/{filename}"
    return None

@app.route('/upload-avatar', methods=['POST'])
def upload_avatar():
    if 'avatar' not in request.files:
        flash('Файл не выбран')
        return redirect(url_for('profile'))
    
    file = request.files['avatar']
    if file.filename == '':
        return redirect(url_for('profile'))

    avatar_url = save_avatar_to_github(file, current_user.username)
    if avatar_url:
        current_user.avatar_url = avatar_url
        db.session.commit()
        flash('Аватарка успешно загружена на GitHub!')
    else:
        flash('Ошибка загрузки на GitHub. Проверь GITHUB_TOKEN.')
    
    return redirect(url_for('profile'))

@app.route('/shop/buy-frame', methods=['POST'])
def buy_frame():
    frame_id = request.json.get('frame_id')
    # Доп. логика списывания баланса/покупки в будущем
    current_user.active_frame = frame_id
    db.session.commit()
    return jsonify({"success": True, "active_frame": frame_id})
