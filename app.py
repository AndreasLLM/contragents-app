from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ваш-секретный-ключ-сделайте-его-очень-длинным-и-сложным'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///contragents.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Модель пользователя
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Существующие модели (оставляем как было)
class Phone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contragent_id = db.Column(db.Integer, db.ForeignKey('contragent.id'), nullable=False)
    number = db.Column(db.String(50), nullable=False)

class Email(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contragent_id = db.Column(db.Integer, db.ForeignKey('contragent.id'), nullable=False)
    address = db.Column(db.String(120), nullable=False)

class Website(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contragent_id = db.Column(db.Integer, db.ForeignKey('contragent.id'), nullable=False)
    url = db.Column(db.String(200), nullable=False)

class Contragent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    org_name = db.Column(db.String(200), nullable=False)
    inn = db.Column(db.String(20))
    contact_person = db.Column(db.String(100))
    position = db.Column(db.String(100))
    address = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
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
    search_query = request.args.get('q', '')
    search_field = request.args.get('field', 'all')
    
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            # Получаем контрагентов с учетом поиска
            contragents_query = Contragent.query
            
            if search_query:
                if search_field == 'all':
                    contragents_query = contragents_query.filter(
                        Contragent.org_name.ilike(f'%{search_query}%') |
                        Contragent.inn.ilike(f'%{search_query}%') |
                        Contragent.contact_person.ilike(f'%{search_query}%') |
                        Contragent.address.ilike(f'%{search_query}%') |
                        Contragent.position.ilike(f'%{search_query}%')
                    )
                elif search_field == 'org_name':
                    contragents_query = contragents_query.filter(Contragent.org_name.ilike(f'%{search_query}%'))
                elif search_field == 'inn':
                    contragents_query = contragents_query.filter(Contragent.inn.ilike(f'%{search_query}%'))
                elif search_field == 'contact_person':
                    contragents_query = contragents_query.filter(Contragent.contact_person.ilike(f'%{search_query}%'))
                elif search_field == 'address':
                    contragents_query = contragents_query.filter(Contragent.address.ilike(f'%{search_query}%'))
                elif search_field == 'position':
                    contragents_query = contragents_query.filter(Contragent.position.ilike(f'%{search_query}%'))
                elif search_field == 'phones':
                    # Поиск по телефонам через связанную таблицу
                    contragents_query = contragents_query.join(Phone).filter(Phone.number.ilike(f'%{search_query}%'))
                elif search_field == 'emails':
                    # Поиск по email через связанную таблицу
                    contragents_query = contragents_query.join(Email).filter(Email.address.ilike(f'%{search_query}%'))
                elif search_field == 'websites':
                    # Поиск по сайтам через связанную таблицу
                    contragents_query = contragents_query.join(Website).filter(Website.url.ilike(f'%{search_query}%'))
            
            contragents = contragents_query.order_by(Contragent.org_name).all()
            return render_template('index.html', 
                                contragents=contragents, 
                                search_query=search_query, 
                                search_field=search_field,
                                user=user)
    
    return render_template('index.html', 
                         contragents=[], 
                         search_query=search_query, 
                         search_field=search_field,
                         user=None)

# Регистрация
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
        
        # Проверяем, существует ли пользователь
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Пользователь с таким именем уже существует', 'danger')
            return redirect(url_for('register'))
        
        if email:
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
        except:
            db.session.rollback()
            flash('Произошла ошибка при регистрации', 'danger')
            return redirect(url_for('register'))
    
    return render_template('register.html')

# Авторизация
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
@app.route('/api/login', methods=['POST'])
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

# API для регистрации
@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    
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
            
            # Создаем нового контрагента
            contragent = Contragent(
                org_name=org_name,
                inn=inn if inn else None,
                contact_person=contact_person if contact_person else None,
                position=position if position else None,
                address=address if address else None
            )
            
            db.session.add(contragent)
            db.session.flush()  # Получаем ID созданного контрагента
            
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
            flash('Контрагент успешно добавлен', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении контрагента: {str(e)}', 'danger')
            return redirect(url_for('add_contragent'))
    
    return render_template('add.html')

# Редактирование контрагента - ИСПРАВЛЕНО: правильный декоратор маршрута
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_contragent(id):
    contragent = Contragent.query.get_or_404(id)
    
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
            
            # Добавляем новые телефоны
            phones = request.form.getlist('phones[]')
            for phone in phones:
                if phone and phone.strip():
                    phone_obj = Phone(contragent_id=contragent.id, number=phone.strip())
                    db.session.add(phone_obj)
            
            # Добавляем новые email
            emails = request.form.getlist('emails[]')
            for email in emails:
                if email and email.strip():
                    email_obj = Email(contragent_id=contragent.id, address=email.strip())
                    db.session.add(email_obj)
            
            # Добавляем новые сайты
            websites = request.form.getlist('websites[]')
            for website in websites:
                if website and website.strip():
                    website_obj = Website(contragent_id=contragent.id, url=website.strip())
                    db.session.add(website_obj)
            
            db.session.commit()
            flash('Контрагент успешно обновлен', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении контрагента: {str(e)}', 'danger')
            return redirect(url_for('edit_contragent', id=id))
    
    return render_template('edit.html', contragent=contragent)

# Удаление контрагента - ИСПРАВЛЕНО: правильный декоратор маршрута
@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_contragent(id):
    try:
        contragent = Contragent.query.get_or_404(id)
        db.session.delete(contragent)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Контрагент успешно удален'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Ошибка при удалении: {str(e)}'})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Создаем таблицы, если их нет
    app.run(debug=True)