import hmac
import json
import os
import re
import secrets
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for

UPLOAD_MAX_MIB = int(os.getenv('UPLOAD_MAX_MIB', '256'))
if UPLOAD_MAX_MIB <= 0:
    raise RuntimeError('UPLOAD_MAX_MIB must be a positive integer.')

app = Flask(__name__, static_url_path='/static')
app.config.update(
    SECRET_KEY=os.environ['SESSION_SECRET'],
    MAX_CONTENT_LENGTH=UPLOAD_MAX_MIB * 1024 * 1024,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('SECURE_COOKIES') == '1',
)
admin_password = os.environ['ADMIN_PASSWORD'].encode()
if len(admin_password) < 12 or len(app.secret_key) < 32:
    raise RuntimeError('Set ADMIN_PASSWORD (12+ characters) and SESSION_SECRET (32+ characters).')

TRANSLATE_URL = os.getenv('TRANSLATE_URL', '').strip()
TRANSLATE_API_KEY = os.getenv('TRANSLATE_API_KEY', '')
ENGLISH_FIELDS = {'name_en': 160, 'description_en': 4000, 'notes_en': 2000}

data_dir = Path(os.getenv('DATA_DIR', '/data'))
uploads = data_dir / 'media'
uploads.mkdir(parents=True, exist_ok=True)
with closing(sqlite3.connect(data_dir / 'catalog.db')) as db, db:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
            price INTEGER NOT NULL, condition TEXT NOT NULL, description TEXT NOT NULL,
            notes TEXT NOT NULL, image TEXT NOT NULL, video TEXT NOT NULL,
            published INTEGER NOT NULL
        );
    """)
    db.execute('BEGIN IMMEDIATE')
    item_columns = {row[1] for row in db.execute('PRAGMA table_info(items)')}
    if 'extra_images' not in item_columns:
        db.execute("ALTER TABLE items ADD COLUMN extra_images TEXT NOT NULL DEFAULT '[]'")
    for column in ENGLISH_FIELDS:
        if column not in item_columns:
            db.execute(f"ALTER TABLE items ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    if 'sort_order' not in item_columns:
        db.execute('ALTER TABLE items ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0')
    db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            email TEXT NOT NULL DEFAULT '', whatsapp TEXT NOT NULL DEFAULT '',
            telegram TEXT NOT NULL DEFAULT ''
        )
    """)
    columns = {row[1] for row in db.execute('PRAGMA table_info(settings)')}
    for column in ('whatsapp', 'telegram'):
        if column not in columns:
            db.execute(f"ALTER TABLE settings ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    if not db.execute('SELECT 1 FROM settings WHERE id = 1').fetchone():
        if 'phone' in columns:
            db.execute("INSERT INTO settings (id, email, phone, wechat) VALUES (1, '', '', '')")
        else:
            db.execute('INSERT INTO settings (id) VALUES (1)')


CATEGORIES = ('家居家具', '数码电器', '运动户外', '服饰鞋包', '母婴用品', '图书文具', '交通工具', '其他')
CONDITIONS = ('全新未使用', '几乎全新', '外观良好', '轻微使用痕迹', '正常使用痕迹', '明显使用痕迹', '需维修')


def photos(item):
    return ([item['image']] if item.get('image') else []) + json.loads(item.get('extra_images', '[]'))


def item_form(item, error=None):
    def options(defaults, current):
        return (*defaults, current) if current and current not in defaults else defaults

    return render_template(
        'edit.html', item=item, error=error, photos=photos(item),
        categories=options(CATEGORIES, item.get('category')),
        conditions=options(CONDITIONS, item.get('condition')),
    )


def connection():
    db = sqlite3.connect(data_dir / 'catalog.db')
    db.row_factory = sqlite3.Row
    return closing(db)


def csrf_token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_hex(32)
    return session['csrf']


app.jinja_env.globals.update(csrf_token=csrf_token, upload_max_mib=UPLOAD_MAX_MIB)


@app.errorhandler(413)
def upload_too_large(_error):
    return render_template('upload_error.html'), 413


@app.before_request
def check_admin():
    if request.path == '/admin' or request.path.startswith('/admin/'):
        if request.endpoint != 'login' and not session.get('admin'):
            return redirect(url_for('login')) if request.method == 'GET' else abort(403)
        if request.method == 'POST' and not hmac.compare_digest(
            request.form.get('csrf', '').encode(), session.get('csrf', '-').encode()
        ):
            abort(403)


@app.after_request
def response_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    if request.path.startswith('/admin') or request.path.startswith('/media/') or request.path == '/api/catalog':
        response.headers['Cache-Control'] = 'no-store'
    if request.path.startswith('/admin'):
        response.headers['X-Frame-Options'] = 'DENY'
    return response


@app.get('/')
def index():
    return app.send_static_file('index.html')


@app.get('/api/catalog')
def catalog():
    with connection() as db:
        items = [dict(row) for row in db.execute(
            'SELECT * FROM items WHERE published = 1 ORDER BY sort_order DESC, rowid DESC'
        )]
        seller = dict(db.execute('SELECT email, whatsapp, telegram FROM settings WHERE id = 1').fetchone())
    for item in items:
        item['images'] = [url_for('media', filename=name) for name in photos(item)]
        del item['extra_images']
        for field in ('image', 'video'):
            item[field] = url_for('media', filename=item[field]) if item[field] else ''
    return jsonify(items=items, seller=seller)


@app.get('/media/<filename>')
def media(filename):
    with connection() as db:
        item = db.execute(
            '''SELECT published FROM items WHERE image = ? OR video = ?
               OR EXISTS (SELECT 1 FROM json_each(extra_images) WHERE value = ?)''',
            (filename, filename, filename)
        ).fetchone()
    if not item or not (item['published'] or session.get('admin')):
        abort(404)
    return send_from_directory(uploads, filename)


@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if hmac.compare_digest(request.form.get('password', '').encode(), admin_password):
            session.clear()
            session['admin'] = True
            return redirect(url_for('admin'))
        return render_template('login.html', error='密码不正确。'), 401
    return render_template('login.html')


@app.post('/admin/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.get('/admin')
def admin():
    with connection() as db:
        items = db.execute('SELECT * FROM items ORDER BY sort_order DESC, rowid DESC').fetchall()
        seller = db.execute('SELECT * FROM settings WHERE id = 1').fetchone()
    return render_template('admin.html', items=items, seller=seller)


@app.post('/admin/translate')
def translate():
    texts = {key: request.form.get(key, '').strip() for key in ENGLISH_FIELDS}
    texts = {key: value for key, value in texts.items() if value}
    if not texts or any(len(value) > ENGLISH_FIELDS[key] for key, value in texts.items()):
        return jsonify(error='请填写要翻译的中文内容，并检查长度。'), 400
    if not TRANSLATE_URL:
        return jsonify(error='翻译服务尚未配置。请设置 TRANSLATE_URL。'), 503

    payload = dict(q=list(texts.values()), source='zh', target='en', format='text')
    if TRANSLATE_API_KEY:
        payload['api_key'] = TRANSLATE_API_KEY
    try:
        upstream = Request(TRANSLATE_URL, data=json.dumps(payload).encode(),
                           headers={'Content-Type': 'application/json'})
        with urlopen(upstream, timeout=25) as response:
            translated = json.loads(response.read(128 * 1024))['translatedText']
        if not isinstance(translated, list) or len(translated) != len(texts):
            raise ValueError('Unexpected translation response')
        result = dict(zip(texts, translated))
        if any(not isinstance(value, str) or not value.strip() or len(value) > ENGLISH_FIELDS[key]
               for key, value in result.items()):
            return jsonify(error='译文为空或超过字段长度，请缩短中文内容后重试。'), 422
    except (OSError, ValueError, KeyError, TypeError):
        return jsonify(error='翻译服务暂时不可用，请稍后重试或手动填写英文。'), 502
    return jsonify(translations=result)


@app.post('/admin/contact')
def contact():
    email = request.form.get('email', '').strip()
    whatsapp = re.sub(r'[+ ()-]', '', request.form.get('whatsapp', '').strip())
    telegram = request.form.get('telegram', '').strip().removeprefix('@')
    error = None
    if email and (len(email) > 200 or not re.fullmatch(r'[^@\s]+@[^@\s]+', email)):
        error = '请输入有效的邮箱地址。'
    elif whatsapp and not re.fullmatch(r'[1-9][0-9]{6,14}', whatsapp):
        error = '请输入含国家区号的 WhatsApp 号码。'
    elif telegram and not re.fullmatch(r'[A-Za-z0-9_]{5,32}', telegram):
        error = '请输入 Telegram 用户名。'
    if error:
        with connection() as db:
            items = db.execute('SELECT * FROM items ORDER BY sort_order DESC, rowid DESC').fetchall()
        seller = {key: request.form.get(key, '') for key in ('email', 'whatsapp', 'telegram')}
        return render_template('admin.html', items=items, seller=seller, contact_error=error), 400
    with connection() as db, db:
        db.execute('UPDATE settings SET email = ?, whatsapp = ?, telegram = ? WHERE id = 1',
                   (email, whatsapp, telegram))
    return redirect(url_for('admin'))


def upload_type(field, file):
    extension = Path(file.filename).suffix.lower()
    head = file.stream.read(16)
    file.stream.seek(0)
    signatures = {
        '.jpg': head.startswith(b'\xff\xd8\xff'),
        '.jpeg': head.startswith(b'\xff\xd8\xff'),
        '.png': head.startswith(b'\x89PNG\r\n\x1a\n'),
        '.webp': head.startswith(b'RIFF') and head[8:12] == b'WEBP',
        '.mp4': head[4:8] == b'ftyp',
    }
    allowed = {'.jpg', '.jpeg', '.png', '.webp'} if field == 'image' else {'.mp4'}
    if extension not in allowed or not signatures[extension]:
        raise ValueError('请上传 JPG、PNG、WebP 图片或 MP4 视频。')
    return extension


@app.route('/admin/item', defaults={'item_id': None}, methods=['GET', 'POST'])
@app.route('/admin/item/<item_id>', methods=['GET', 'POST'])
def edit(item_id):
    with connection() as db:
        original = db.execute('SELECT * FROM items WHERE id = ?', (item_id,)).fetchone()
    if item_id and not original:
        abort(404)
    if request.method == 'GET':
        return item_form(dict(original) if original else {})

    item = dict(original) if original else {'id': uuid4().hex, 'image': '', 'video': ''}
    item.update({key: request.form.get(key, '').strip() for key in (
        'name', 'category', 'price', 'condition', 'description', 'notes'
    )})
    for key in ENGLISH_FIELDS:
        item[key] = request.form.get(key, item.get(key, '')).strip()
    sort_order = request.form.get('sort_order')
    if sort_order is not None:
        item['sort_order'] = sort_order.strip() or '0'
    item['published'] = int(request.form.get('published') == '1')
    remove = set(request.form.getlist('remove_image'))
    try:
        for key in ('name', 'category', 'condition'):
            if not 1 <= len(item[key]) <= 80:
                raise ValueError('名称、分类和成色须填写，且各不超过 80 字。')
        for key, choices in (('category', CATEGORIES), ('condition', CONDITIONS)):
            if item[key] not in choices and (not original or item[key] != original[key]):
                raise ValueError('请选择列表中的分类和成色。')
        if sort_order is not None and not re.fullmatch(r'[0-9]{1,6}', item['sort_order']):
            raise ValueError('排序值须为 0 到 999999 的整数。')
        if not re.fullmatch(r'[0-9]{1,9}', item['price']):
            raise ValueError('瓦图价格须填写 0 到 999999999 的整数。')
        if not 1 <= len(item['description']) <= 4000 or len(item['notes']) > 2000:
            raise ValueError('请填写商品介绍，并确保介绍和看货说明符合长度限制。')
        if any(len(item[key]) > limit for key, limit in ENGLISH_FIELDS.items()):
            raise ValueError('英文内容超过长度限制。')
        pending_images = [(file, upload_type('image', file))
                          for file in request.files.getlist('image') if file.filename]
        video = request.files.get('video')
        pending_video = (video, upload_type('video', video)) if video and video.filename else None
    except ValueError as error:
        for key, choices in (('category', CATEGORIES), ('condition', CONDITIONS)):
            if item[key] not in choices:
                item[key] = original[key] if original else ''
        return item_form(item, error=str(error)), 400

    saved = []
    try:
        with connection() as db, db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT * FROM items WHERE id = ?', (item['id'],)).fetchone()
            if item_id and not current:
                abort(404)
            if sort_order is None:
                item['sort_order'] = current['sort_order'] if current else 0
            old_images = photos(dict(current)) if current else []
            kept = [name for name in old_images if name not in remove]
            if item['published'] and not (kept or pending_images):
                raise ValueError('发布前请上传至少一张商品照片。')

            def save_upload(upload):
                file, extension = upload
                filename = uuid4().hex + extension
                path = uploads / filename
                saved.append(path)
                file.save(path)
                return filename

            images = kept + [save_upload(upload) for upload in pending_images]
            item['image'] = images[0] if images else ''
            item['extra_images'] = json.dumps(images[1:])
            old_video = current['video'] if current else ''
            item['video'] = save_upload(pending_video) if pending_video else old_video
            db.execute("""
                INSERT INTO items (id,name,category,price,condition,description,notes,image,video,published,extra_images,sort_order,
                    name_en,description_en,notes_en)
                VALUES (:id,:name,:category,:price,:condition,:description,
                    :notes,:image,:video,:published,:extra_images,:sort_order,:name_en,:description_en,:notes_en)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, category=excluded.category,
                    price=excluded.price, condition=excluded.condition, description=excluded.description,
                    notes=excluded.notes, image=excluded.image, video=excluded.video,
                    published=excluded.published, extra_images=excluded.extra_images,
                    sort_order=excluded.sort_order, name_en=excluded.name_en,
                    description_en=excluded.description_en, notes_en=excluded.notes_en
            """, item)
    except ValueError as error:
        return item_form(item, error=str(error)), 400
    except Exception:
        for path in saved:
            path.unlink(missing_ok=True)
        raise
    obsolete = set(old_images) - set(images)
    if old_video and old_video != item['video']:
        obsolete.add(old_video)
    for name in obsolete:
        (uploads / name).unlink(missing_ok=True)
    return redirect(url_for('admin'))


@app.post('/admin/item/<item_id>/unpublish')
def unpublish(item_id):
    with connection() as db, db:
        if not db.execute('UPDATE items SET published = 0 WHERE id = ?', (item_id,)).rowcount:
            abort(404)
    return redirect(url_for('admin'))
