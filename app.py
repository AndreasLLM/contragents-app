from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
from sqlalchemy import or_, func, text

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ваш-секретный-ключ-сделайте-его-очень-длинным-и-сложным'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///contragents.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['STATIC_FOLDER'] = 'static'

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
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, default=1)
    
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

# Функция для регистронезависимого поиска в SQLite
def case_insensitive_like(field, value):
    """
    Создает условие для регистронезависимого поиска в SQLite.
    Для кириллицы используем COLLATE NOCASE
    """
    # Используем LIKE с COLLATE NOCASE для поддержки кириллицы
    return field.like(f'%{value}%')

# Главная страница
@app.route('/')
def index():
    search_query_input = request.args.get('q', '').strip()  # сохраняем как ввел пользователь
    search_query_lower = search_query_input.lower()  # для поиска в нижнем регистре
    search_field = request.args.get('field', 'all')
    
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            # Базовый запрос для текущего пользователя
            query = Contragent.query.filter_by(user_id=session['user_id'])
            
            if search_query_lower:  # ИСПРАВЛЕНО: используем search_query_lower
                if search_field == 'all':
                    # Получаем всех контрагентов пользователя
                    all_contragents = query.options(
                        db.joinedload(Contragent.phones),
                        db.joinedload(Contragent.emails),
                        db.joinedload(Contragent.websites)
                    ).all()
                    
                    # Фильтруем на стороне Python
                    filtered_contragents = []
                    for contragent in all_contragents:
                        # Проверяем основные поля
                        if (search_query_lower in (contragent.org_name or '').lower() or
                            search_query_lower in (contragent.inn or '').lower() or
                            search_query_lower in (contragent.contact_person or '').lower() or
                            search_query_lower in (contragent.position or '').lower() or
                            search_query_lower in (contragent.address or '').lower()):
                            filtered_contragents.append(contragent)
                            continue
                        
                        # Проверяем телефоны
                        if any(search_query_lower in phone.number.lower() for phone in contragent.phones):
                            filtered_contragents.append(contragent)
                            continue
                        
                        # Проверяем email
                        if any(search_query_lower in email.address.lower() for email in contragent.emails):
                            filtered_contragents.append(contragent)
                            continue
                        
                        # Проверяем сайты
                        if any(search_query_lower in website.url.lower() for website in contragent.websites):
                            filtered_contragents.append(contragent)
                            continue
                    
                    # Сортировка по убыванию ID (новые сверху)
                    contragents = sorted(filtered_contragents, key=lambda x: x.id, reverse=True)
                    
                    # ИСПРАВЛЕНО: передаем search_query_input (оригинальную строку)
                    return render_template('index.html', 
                                        contragents=contragents, 
                                        search_query=search_query_input, 
                                        search_field=search_field,
                                        user=user)
                
                # Для конкретных полей используем фильтрацию на стороне Python
                elif search_field in ['org_name', 'contact_person', 'position', 'address']:
                    # Получаем всех контрагентов и фильтруем
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
                    
                # Для остальных полей (INN, телефоны, email, сайты) используем SQL LIKE
                # так как они обычно не содержат кириллицу
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
                
                # ИСПРАВЛЕНО: передаем search_query_input (оригинальную строку)
                return render_template('index.html', 
                                    contragents=contragents, 
                                    search_query=search_query_input, 
                                    search_field=search_field,
                                    user=user)
            
            else:
                # Если нет поискового запроса, просто показываем все
                contragents = query.order_by(Contragent.id.desc()).all()
                
                # ИСПРАВЛЕНО: передаем search_query_input (оригинальную строку)
                return render_template('index.html', 
                                    contragents=contragents, 
                                    search_query=search_query_input, 
                                    search_field=search_field,
                                    user=user)
    
    # ИСПРАВЛЕНО: передаем search_query_input (оригинальную строку)
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
        
        # Проверки
        if not username or not password:
            flash('Заполните все обязательные поля', 'danger')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('Пароли не совпадают', 'danger')
            return redirect(url_for('register'))
        
        # Если email пустой, ставим None
        if email == '':
            email = None
        
        # Проверяем, существует ли пользователь
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Пользователь с таким именем уже существует', 'danger')
            return redirect(url_for('register'))
        
        if email:  # Проверяем email только если он указан
            existing_email = User.query.filter_by(email=email).first()
            if existing_email:
                flash('Пользователь с таким email уже существует', 'danger')
                return redirect(url_for('register'))
        
        # Создаем нового пользователя
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
    
    # Если email пустой, ставим None
    if email == '':
        email = None
    
    # Проверяем, существует ли пользователь
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({'success': False, 'message': 'Пользователь с таким именем уже существует'})
    
    if email:
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            return jsonify({'success': False, 'message': 'Пользователь с таким email уже существует'})
    
    # Создаем нового пользователя
    new_user = User(username=username, email=email)
    new_user.set_password(password)
    
    try:
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Регистрация успешна! Теперь вы можете войти.'})
    except:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Произошла ошибка при регистрации'})

# Добавление контрагента
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_contragent():
    copy_id = request.args.get('copy_id')
    contragent_to_copy = None
    
    if copy_id:
        # Проверяем, что контрагент для копирования принадлежит текущему пользователю
        contragent_to_copy = Contragent.query.filter_by(id=copy_id, user_id=session['user_id']).first()
    
    if request.method == 'POST':
        try:
            # Получаем данные из формы
            org_name = request.form.get('org_name')
            inn = request.form.get('inn')
            contact_person = request.form.get('contact_person')
            position = request.form.get('position')
            address = request.form.get('address')
            
            # Получаем списки телефонов, email и сайтов
            phones = request.form.getlist('phones[]')
            emails = request.form.getlist('emails[]')
            websites = request.form.getlist('websites[]')
            
            # Проверяем обязательные поля
            if not org_name:
                flash('Название организации обязательно для заполнения', 'danger')
                return redirect(url_for('add_contragent'))
            
            # Создаем нового контрагента с привязкой к текущему пользователю
            contragent = Contragent(
                org_name=org_name,
                inn=inn if inn else None,
                contact_person=contact_person if contact_person else None,
                position=position if position else None,
                address=address if address else None,
                user_id=session['user_id']
            )
            
            db.session.add(contragent)
            db.session.flush()
            
            # Добавляем телефоны
            for phone in phones:
                if phone and phone.strip():
                    phone_obj = Phone(contragent_id=contragent.id, number=phone.strip())
                    db.session.add(phone_obj)
            
            # Добавляем email
            for email in emails:
                if email and email.strip():
                    email_obj = Email(contragent_id=contragent.id, address=email.strip())
                    db.session.add(email_obj)
            
            # Добавляем сайты
            for website in websites:
                if website and website.strip():
                    website_obj = Website(contragent_id=contragent.id, url=website.strip())
                    db.session.add(website_obj)
            
            db.session.commit()
            
            if copy_id:
                flash('Копия контрагента успешно создана', 'success')
            else:
                flash('Контрагент успешно добавлен', 'success')
                
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении контрагента: {str(e)}', 'danger')
            return redirect(url_for('add_contragent'))
    
    return render_template('add.html', contragent=contragent_to_copy, is_copy=bool(copy_id))

# Редактирование контрагента
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_contragent(id):
    # Получаем контрагента и проверяем, что он принадлежит текущему пользователю
    contragent = Contragent.query.filter_by(id=id, user_id=session['user_id']).first_or_404()
    
    if request.method == 'POST':
        try:
            # Обновляем основные данные
            contragent.org_name = request.form.get('org_name')
            contragent.inn = request.form.get('inn')
            contragent.contact_person = request.form.get('contact_person')
            contragent.position = request.form.get('position')
            contragent.address = request.form.get('address')
            
            # Удаляем старые телефоны, email и сайты
            Phone.query.filter_by(contragent_id=contragent.id).delete()
            Email.query.filter_by(contragent_id=contragent.id).delete()
            Website.query.filter_by(contragent_id=contragent.id).delete()
            
            # Получаем данные из формы
            phones = request.form.getlist('phones[]')
            emails = request.form.getlist('emails[]')
            websites = request.form.getlist('websites[]')
            
            # Добавляем новые телефоны
            for phone in phones:
                if phone and phone.strip():
                    phone_obj = Phone(contragent_id=contragent.id, number=phone.strip())
                    db.session.add(phone_obj)
            
            # Добавляем новые email
            for email in emails:
                if email and email.strip():
                    email_obj = Email(contragent_id=contragent.id, address=email.strip())
                    db.session.add(email_obj)
            
            # Добавляем новые сайты
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
        # Проверяем, что контрагент принадлежит текущему пользователю
        contragent = Contragent.query.filter_by(id=id, user_id=session['user_id']).first()
        
        if not contragent:
            return jsonify({'success': False, 'message': 'Контрагент не найден или у вас нет прав на его удаление'})
        
        db.session.delete(contragent)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Контрагент успешно удален'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Ошибка при удалении: {str(e)}'})

# Создание тестового пользователя для разработки
def create_test_user():
    with app.app_context():
        if User.query.count() == 0:
            test_user = User(username='admin', email='admin@example.com')
            test_user.set_password('admin123')
            db.session.add(test_user)
            db.session.commit()
            print("Создан тестовый пользователь:")
            print("Логин: admin")
            print("Пароль: admin123")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_test_user()
    app.run(host='0.0.0.0', port=5000, debug=True)