import hmac
import os
import re
import secrets
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for

app = Flask(__name__, static_url_path='/static')
app.config.update(
    SECRET_KEY=os.environ['SESSION_SECRET'],
    MAX_CONTENT_LENGTH=100 * 1024 * 1024,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('SECURE_COOKIES') == '1',
)
admin_password = os.environ['ADMIN_PASSWORD'].encode()
if len(admin_password) < 12 or len(app.secret_key) < 32:
    raise RuntimeError('Set ADMIN_PASSWORD (12+ characters) and SESSION_SECRET (32+ characters).')

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
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            email TEXT NOT NULL, phone TEXT NOT NULL, wechat TEXT NOT NULL
        );
        INSERT OR IGNORE INTO settings VALUES (1, '', '', '');
    """)


CATEGORIES = ('家居家具', '数码电器', '运动户外', '服饰鞋包', '母婴用品', '图书文具', '交通工具', '其他')
CONDITIONS = ('全新未使用', '几乎全新', '外观良好', '轻微使用痕迹', '正常使用痕迹', '明显使用痕迹', '需维修')


def item_form(item, error=None):
    def options(defaults, current):
        return (*defaults, current) if current and current not in defaults else defaults

    return render_template(
        'edit.html', item=item, error=error,
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


app.jinja_env.globals['csrf_token'] = csrf_token


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
            'SELECT * FROM items WHERE published = 1 ORDER BY rowid DESC'
        )]
        seller = dict(db.execute('SELECT email, phone, wechat FROM settings WHERE id = 1').fetchone())
    for item in items:
        for field in ('image', 'video'):
            item[field] = url_for('media', filename=item[field]) if item[field] else ''
    return jsonify(items=items, seller=seller)


@app.get('/media/<filename>')
def media(filename):
    with connection() as db:
        item = db.execute(
            'SELECT published FROM items WHERE image = ? OR video = ?', (filename, filename)
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
        items = db.execute('SELECT * FROM items ORDER BY rowid DESC').fetchall()
        seller = db.execute('SELECT * FROM settings WHERE id = 1').fetchone()
    return render_template('admin.html', items=items, seller=seller)


@app.post('/admin/contact')
def contact():
    fields = tuple(request.form.get(key, '').strip() for key in ('email', 'phone', 'wechat'))
    if any(len(value) > 200 for value in fields):
        abort(400, '联系方式最多 200 字。')
    with connection() as db, db:
        db.execute('UPDATE settings SET email = ?, phone = ?, wechat = ? WHERE id = 1', fields)
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
    item['published'] = int(request.form.get('published') == '1')
    pending_files = {}
    try:
        for key in ('name', 'category', 'condition'):
            if not 1 <= len(item[key]) <= 80:
                raise ValueError('名称、分类和成色须填写，且各不超过 80 字。')
        for key, choices in (('category', CATEGORIES), ('condition', CONDITIONS)):
            if item[key] not in choices and (not original or item[key] != original[key]):
                raise ValueError('请选择列表中的分类和成色。')
        if not re.fullmatch(r'[0-9]{1,9}', item['price']):
            raise ValueError('瓦图价格须填写 0 到 999999999 的整数。')
        if not 1 <= len(item['description']) <= 4000 or len(item['notes']) > 2000:
            raise ValueError('请填写商品介绍，并确保介绍和看货说明符合长度限制。')
        for field in ('image', 'video'):
            file = request.files.get(field)
            if file and file.filename:
                pending_files[field] = (file, upload_type(field, file))
        if item['published'] and not (item['image'] or 'image' in pending_files):
            raise ValueError('发布前请上传商品照片。')
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
            for field in ('image', 'video'):
                if current:
                    item[field] = current[field]
                if field in pending_files:
                    file, extension = pending_files[field]
                    filename = uuid4().hex + extension
                    path = uploads / filename
                    saved.append(path)
                    file.save(path)
                    item[field] = filename
            db.execute("""
                INSERT INTO items VALUES (:id,:name,:category,:price,:condition,:description,
                    :notes,:image,:video,:published)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, category=excluded.category,
                    price=excluded.price, condition=excluded.condition, description=excluded.description,
                    notes=excluded.notes, image=excluded.image, video=excluded.video,
                    published=excluded.published
            """, item)
    except Exception:
        for path in saved:
            path.unlink(missing_ok=True)
        raise
    if current:
        for field in ('image', 'video'):
            if current[field] and current[field] != item[field]:
                (uploads / current[field]).unlink(missing_ok=True)
    return redirect(url_for('admin'))


@app.post('/admin/item/<item_id>/unpublish')
def unpublish(item_id):
    with connection() as db, db:
        if not db.execute('UPDATE items SET published = 0 WHERE id = ?', (item_id,)).rowcount:
            abort(404)
    return redirect(url_for('admin'))
