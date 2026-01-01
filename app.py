from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
from sqlalchemy import or_, func, text
from dotenv import load_dotenv
from sqlalchemy.pool import NullPool
from urllib.parse import urlparse

load_dotenv()
IS_LOCAL_DEV = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ваш-ключ')

# 🔧 ИСПРАВЛЕННАЯ НАСТРОЙКА СЕССИИ
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Сессия на 7 дней
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

# --- НАСТРОЙКА БАЗЫ ДАННЫХ (ТОЛЬКО POSTGRESQL) ---
database_url = os.environ.get('DATABASE_URL')

if not database_url:
    print("❌ ОШИБКА: DATABASE_URL не установлен!")
    print("✅ Настройте DATABASE_URL в Render Dashboard")
    print("✅ Или добавьте в .env файл для локальной разработки")
    exit(1)

# Для локальной разработки выводим больше информации
if IS_LOCAL_DEV:
    print("⚠️  РЕЖИМ ЛОКАЛЬНОЙ РАЗРАБОТКИ")
    print(f"📦 DATABASE_URL из .env: {database_url[:50]}...")

# Преобразование URL для psycopg3
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
elif database_url.startswith('postgresql://'):
    database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)

# Определяем, работаем ли мы на Render (для SSL)
is_render = 'onrender.com' in database_url or 'RENDER' in os.environ

# Настройки движка
engine_options = {
    'pool_recycle': 300,
    'pool_pre_ping': True,
    'poolclass': NullPool,
}

# SSL только для Render
if is_render and not IS_LOCAL_DEV:
    engine_options['connect_args'] = {"sslmode": "require"}
    print(f"✅ Настроено SSL подключение (требуется для Render)")
elif IS_LOCAL_DEV:
    print(f"✅ Локальная разработка - SSL не требуется")

# Логирование (без пароля)
safe_url = database_url
if '@' in database_url:
    parts = database_url.split('@')
    user_pass = parts[0].split(':')
    if len(user_pass) > 2:
        user_pass[2] = '***'
    safe_url = ':'.join(user_pass) + '@' + '@'.join(parts[1:])

print(f"✅ Используется PostgreSQL с диалектом psycopg3")
print(f"✅ Преобразованный URL: {safe_url[:100]}...")

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = engine_options
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# --- КОНЕЦ НАСТРОЙКИ БАЗЫ ---

db = SQLAlchemy(app)

# ДОБАВЬТЕ ЭТОТ МАРШРУТ ДЛЯ FAVICON
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', 
                               mimetype='image/vnd.microsoft.icon')

# Модель пользователя
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связь с контрагентами
    contragents = db.relationship('Contragent', backref='owner', lazy=True, cascade="all, delete-orphan")
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Модель телефона
class Phone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contragent_id = db.Column(db.Integer, db.ForeignKey('contragent.id'), nullable=False)
    number = db.Column(db.String(50), nullable=False)

# Модель email
class Email(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contragent_id = db.Column(db.Integer, db.ForeignKey('contragent.id'), nullable=False)
    address = db.Column(db.String(120), nullable=False)

# Модель сайта
class Website(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contragent_id = db.Column(db.Integer, db.ForeignKey('contragent.id'), nullable=False)
    url = db.Column(db.String(200), nullable=False)

# Модель контрагента
class Contragent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    org_name = db.Column(db.String(200), nullable=False)
    inn = db.Column(db.String(20))
    contact_person = db.Column(db.String(100))
    position = db.Column(db.String(100))
    address = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # ВАЖНО: привязка к пользователю
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    phones = db.relationship('Phone', backref='contragent', lazy=True, cascade="all, delete-orphan")
    emails = db.relationship('Email', backref='contragent', lazy=True, cascade="all, delete-orphan")
    websites = db.relationship('Website', backref='contragent', lazy=True, cascade="all, delete-orphan")

# Декоратор для проверки авторизации
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Для доступа к этой странице необходимо авторизоваться', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Главная страница
@app.route('/')
def index():
    search_query_input = request.args.get('q', '').strip()
    search_query_lower = search_query_input.lower()
    search_field = request.args.get('field', 'all')
    
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            query = Contragent.query.filter_by(user_id=session['user_id'])
            
            if search_query_lower:
                if search_field == 'all':
                    all_contragents = query.options(
                        db.joinedload(Contragent.phones),
                        db.joinedload(Contragent.emails),
                        db.joinedload(Contragent.websites)
                    ).all()
                    
                    filtered_contragents = []
                    for contragent in all_contragents:
                        if (search_query_lower in (contragent.org_name or '').lower() or
                            search_query_lower in (contragent.inn or '').lower() or
                            search_query_lower in (contragent.contact_person or '').lower() or
                            search_query_lower in (contragent.position or '').lower() or
                            search_query_lower in (contragent.address or '').lower()):
                            filtered_contragents.append(contragent)
                            continue
                        
                        if any(search_query_lower in phone.number.lower() for phone in contragent.phones):
                            filtered_contragents.append(contragent)
                            continue
                        
                        if any(search_query_lower in email.address.lower() for email in contragent.emails):
                            filtered_contragents.append(contragent)
                            continue
                        
                        if any(search_query_lower in website.url.lower() for website in contragent.websites):
                            filtered_contragents.append(contragent)
                            continue
                    
                    contragents = sorted(filtered_contragents, key=lambda x: x.id, reverse=True)
                    
                    return render_template('index.html', 
                                        contragents=contragents, 
                                        search_query=search_query_input, 
                                        search_field=search_field,
                                        user=user)
                
                elif search_field in ['org_name', 'contact_person', 'position', 'address']:
                    all_contragents = query.all()
                    filtered = []
                    
                    if search_field == 'org_name':
                        filtered = [c for c in all_contragents 
                                  if c.org_name and search_query_lower in c.org_name.lower()]
                    elif search_field == 'contact_person':
                        filtered = [c for c in all_contragents 
                                  if c.contact_person and search_query_lower in c.contact_person.lower()]
                    elif search_field == 'position':
                        filtered = [c for c in all_contragents 
                                  if c.position and search_query_lower in c.position.lower()]
                    elif search_field == 'address':
                        filtered = [c for c in all_contragents 
                                  if c.address and search_query_lower in c.address.lower()]
                    
                    contragents = sorted(filtered, key=lambda x: x.id, reverse=True)
                    
                else:
                    if search_field == 'inn':
                        query = query.filter(Contragent.inn.like(f'%{search_query_lower}%'))
                    elif search_field == 'phones':
                        query = query.join(Phone).filter(Phone.number.like(f'%{search_query_lower}%'))
                    elif search_field == 'emails':
                        query = query.join(Email).filter(Email.address.like(f'%{search_query_lower}%'))
                    elif search_field == 'websites':
                        query = query.join(Website).filter(Website.url.like(f'%{search_query_lower}%'))
                    
                    contragents = query.order_by(Contragent.id.desc()).all()
                
                return render_template('index.html', 
                                    contragents=contragents, 
                                    search_query=search_query_input, 
                                    search_field=search_field,
                                    user=user)
            
            else:
                contragents = query.order_by(Contragent.id.desc()).all()
                return render_template('index.html', 
                                    contragents=contragents, 
                                    search_query=search_query_input, 
                                    search_field=search_field,
                                    user=user)
    
    return render_template('index.html', 
                         contragents=[], 
                         search_query=search_query_input, 
                         search_field=search_field,
                         user=None)

# Регистрация (через форму)
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        email = request.form.get('email')
        
        if not username or not password:
            flash('Заполните все обязательные поля', 'danger')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('Пароли не совпадают', 'danger')
            return redirect(url_for('register'))
        
        if email == '':
            email = None
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Пользователь с таким именем уже существует', 'danger')
            return redirect(url_for('register'))
        
        if email:
            existing_email = User.query.filter_by(email=email).first()
            if existing_email:
                flash('Пользователь с таким email уже существует', 'danger')
                return redirect(url_for('register'))
        
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Регистрация успешна! Теперь вы можете войти.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('Произошла ошибка при регистрации', 'danger')
            return redirect(url_for('register'))
    
    return render_template('register.html')

# Авторизация (через форму)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Введите имя пользователя и пароль', 'danger')
            return redirect(url_for('login'))
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session.permanent = True  # Делаем сессию постоянной
            flash('Авторизация успешна!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль', 'danger')
            return redirect(url_for('login'))
    
    return render_template('login.html')

# Выход
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('index'))

# API для авторизации (для AJAX запросов из index.html)
@app.route('/api/login', methods=['POST'], endpoint='api_login')
def api_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    user = User.query.filter_by(username=username).first()
    
    if user and user.check_password(password):
        session['user_id'] = user.id
        session.permanent = True  # Делаем сессию постоянной
        return jsonify({'success': True, 'message': 'Авторизация успешна'})
    else:
        return jsonify({'success': False, 'message': 'Неверное имя пользователя или пароль'})

# API для регистрации (для AJAX запросов из index.html)
@app.route('/api/register', methods=['POST'], endpoint='api_register')
def api_register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    
    if email == '':
        email = None
    
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({'success': False, 'message': 'Пользователь с таким именем уже существует'})
    
    if email:
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            return jsonify({'success': False, 'message': 'Пользователь с таким email уже существует'})
    
    new_user = User(username=username, email=email)
    new_user.set_password(password)
    
    try:
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Регистрация успешна! Теперь вы можете войти.'})
    except:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Произошла ошибка при регистрации'})

# Добавление контрагента (ИСПРАВЛЕНО КОПИРОВАНИЕ)
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_contragent():
    # 🔧 ИСПРАВЛЕНИЕ: Правильное получение copy_id
    copy_id_str = request.args.get('copy_id')
    contragent_to_copy = None
    
    if copy_id_str:
        try:
            copy_id = int(copy_id_str)  # Преобразуем в int
            contragent_to_copy = Contragent.query.filter_by(
                id=copy_id, 
                user_id=session['user_id']
            ).first()
            
            if not contragent_to_copy:
                flash('Контрагент для копирования не найден', 'danger')
                return redirect(url_for('index'))
        except (ValueError, TypeError):
            flash('Некорректный ID для копирования', 'danger')
            return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            org_name = request.form.get('org_name', '').strip()
            inn = request.form.get('inn', '').strip()
            contact_person = request.form.get('contact_person', '').strip()
            position = request.form.get('position', '').strip()
            address = request.form.get('address', '').strip()
            
            if not org_name:
                flash('Название организации обязательно для заполнения', 'danger')
                return redirect(url_for('add_contragent'))
            
            contragent = Contragent(
                org_name=org_name,
                inn=inn if inn else None,
                contact_person=contact_person if contact_person else None,
                position=position if position else None,
                address=address if address else None,
                user_id=session['user_id']
            )
            
            db.session.add(contragent)
            db.session.flush()  # Получаем ID
            
            # Телефоны
            phones = request.form.getlist('phones[]')
            for phone in phones:
                if phone and phone.strip():
                    phone_obj = Phone(contragent_id=contragent.id, number=phone.strip())
                    db.session.add(phone_obj)
            
            # Emails
            emails = request.form.getlist('emails[]')
            for email in emails:
                if email and email.strip():
                    email_obj = Email(contragent_id=contragent.id, address=email.strip())
                    db.session.add(email_obj)
            
            # Сайты
            websites = request.form.getlist('websites[]')
            for website in websites:
                if website and website.strip():
                    website_obj = Website(contragent_id=contragent.id, url=website.strip())
                    db.session.add(website_obj)
            
            db.session.commit()
            
            flash('Контрагент успешно добавлен', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении контрагента: {str(e)}', 'danger')
            return redirect(url_for('add_contragent'))
    
    return render_template('add.html', 
                         contragent=contragent_to_copy, 
                         is_copy=bool(copy_id_str))

# Редактирование контрагента (ИСПРАВЛЕНО СОХРАНЕНИЕ)
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_contragent(id):
    contragent = Contragent.query.filter_by(id=id, user_id=session['user_id']).first_or_404()
    
    if request.method == 'POST':
        try:
            # 🔧 ИСПРАВЛЕНИЕ: Сохраняем даже пустые значения
            contragent.org_name = request.form.get('org_name', '').strip()
            contragent.inn = request.form.get('inn', '').strip() or None
            contragent.contact_person = request.form.get('contact_person', '').strip() or None
            contragent.position = request.form.get('position', '').strip() or None
            contragent.address = request.form.get('address', '').strip() or None
            
            # Удаляем старые контакты
            Phone.query.filter_by(contragent_id=contragent.id).delete()
            Email.query.filter_by(contragent_id=contragent.id).delete()
            Website.query.filter_by(contragent_id=contragent.id).delete()
            
            # Добавляем новые
            phones = request.form.getlist('phones[]')
            for phone in phones:
                if phone and phone.strip():
                    phone_obj = Phone(contragent_id=contragent.id, number=phone.strip())
                    db.session.add(phone_obj)
            
            emails = request.form.getlist('emails[]')
            for email in emails:
                if email and email.strip():
                    email_obj = Email(contragent_id=contragent.id, address=email.strip())
                    db.session.add(email_obj)
            
            websites = request.form.getlist('websites[]')
            for website in websites:
                if website and website.strip():
                    website_obj = Website(contragent_id=contragent.id, url=website.strip())
                    db.session.add(website_obj)
            
            db.session.commit()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'message': 'Контрагент успешно обновлен'})
            else:
                flash('Контрагент успешно обновлен', 'success')
                return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            error_message = f'Ошибка при обновлении контрагента: {str(e)}'
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': error_message})
            else:
                flash(error_message, 'danger')
                return redirect(url_for('edit_contragent', id=id))
    
    return render_template('edit.html', contragent=contragent)

# Удаление контрагента
@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_contragent(id):
    try:
        contragent = Contragent.query.filter_by(id=id, user_id=session['user_id']).first()
        
        if not contragent:
            return jsonify({'success': False, 'message': 'Контрагент не найден'})
        
        db.session.delete(contragent)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Контрагент успешно удален'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Ошибка при удалении: {str(e)}'})

# Создание тестового пользователя и инициализация БД
def init_database():
    with app.app_context():
        try:
            db.create_all()
            print("✅ Таблицы базы данных созданы/проверены")
            
            if User.query.count() == 0:
                test_user = User(username='admin', email='admin@example.com')
                test_user.set_password('admin123')
                db.session.add(test_user)
                db.session.commit()
                print("✅ Создан тестовый пользователь:")
                print("   Логин: admin")
                print("   Пароль: admin123")
            else:
                print(f"ℹ️  В базе уже есть {User.query.count()} пользователей")
                
        except Exception as e:
            print(f"❌ Ошибка при инициализации базы данных: {e}")
            db.session.rollback()

# Инициализируем базу данных при запуске
init_database()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
    print(f"🚀 Приложение запущено на порту {port}")