from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import requests
import uuid
from sqlalchemy import or_, func, text
from dotenv import load_dotenv
from sqlalchemy.pool import NullPool
from urllib.parse import urlparse

# Загружаем переменные окружения
load_dotenv()

# Создаем приложение Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ваш-очень-длинный-секретный-ключ-измените-это')

# Настройки сессии
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

# ========== НАСТРОЙКА БАЗЫ ДАННЫХ (ТОЛЬКО POSTGRESQL) ==========
database_url = os.environ.get('DATABASE_URL')

if not database_url:
    # Критическая ошибка - нет DATABASE_URL
    print("❌ ОШИБКА: DATABASE_URL не установлен!")
    print("✅ Для локальной разработки добавьте DATABASE_URL в .env файл")
    print("✅ На Render DATABASE_URL добавляется автоматически при создании PostgreSQL")
    exit(1)

# Преобразование URL для PostgreSQL (если требуется)
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
elif database_url.startswith('postgresql://'):
    database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)

print(f"📦 Подключаемся к базе данных PostgreSQL...")

# Определяем, на Render ли мы
is_render = 'onrender.com' in database_url or 'RENDER' in os.environ
is_local_dev = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

# Настройки движка для PostgreSQL
engine_options = {
    'pool_recycle': 300,
    'pool_pre_ping': True,
    'poolclass': NullPool,
}

if is_render and not is_local_dev:
    # На Render с PostgreSQL - требуется SSL
    engine_options['connect_args'] = {"sslmode": "require"}
    print(f"✅ Настроено SSL подключение для Render")
else:
    # Локально - без SSL
    print(f"✅ Локальная разработка - SSL не требуется")

# Настраиваем приложение
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = engine_options
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализируем db
db = SQLAlchemy(app)

# ========== ФУНКЦИЯ ОТПРАВКИ ПИСЬМА ЧЕРЕЗ UNISENDER API ==========
def send_reset_email_via_unisender(email, reset_url):
    api_key = os.environ.get('UNISENDER_API_KEY')
    sender_email = os.environ.get('MAIL_DEFAULT_SENDER')
    
    if not api_key or not sender_email:
        print("❌ ОШИБКА: Не установлены переменные UNISENDER_API_KEY или MAIL_DEFAULT_SENDER")
        return {'success': False, 'error': 'Не настроены почтовые переменные'}
    
    api_url = "https://api.unisender.com/ru/api/sendEmail"
    
    payload = {
        'api_key': api_key,
        'email': email,
        'sender_name': 'Восстановление пароля',
        'sender_email': sender_email,
        'subject': 'Восстановление пароля в системе "Контрагенты"',
        'body': f'''<p>Здравствуйте!</p>
                   <p>Для восстановления пароля перейдите по ссылке:</p>
                   <p><a href="{reset_url}" style="background-color: #5dade2; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Восстановить пароль</a></p>
                   <p>Или скопируйте эту ссылку в браузер:<br>{reset_url}</p>
                   <p><strong>Ссылка действительна в течение 1 часа.</strong></p>
                   <hr>
                   <p style="color: #666; font-size: 12px;">Если вы не запрашивали восстановление пароля, проигнорируйте это письмо.</p>''',
        'list_id': '0'
    }
    
    try:
        response = requests.post(api_url, data=payload, timeout=30)
        result = response.json()
        
        print(f"📧 Ответ от Unisender API: {result}")
        
        if 'result' in result:
            print(f"✅ Письмо отправлено. ID: {result['result'].get('message_id', 'неизвестно')}")
            return {'success': True, 'message': 'Письмо отправлено'}
        else:
            error_msg = result.get('error', 'Неизвестная ошибка API')
            print(f"❌ Ошибка Unisender API: {error_msg}")
            return {'success': False, 'error': f'Ошибка Unisender: {error_msg}'}
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка сети при отправке письма: {str(e)}")
        return {'success': False, 'error': f'Ошибка сети: {str(e)}'}
    except ValueError as e:
        print(f"❌ Ошибка разбора JSON от Unisender: {str(e)}")
        return {'success': False, 'error': 'Неверный ответ от сервера'}
# ========== КОНЕЦ ФУНКЦИИ ОТПРАВКИ ==========

# ========== ФУНКЦИИ ДЛЯ МНОГОЯЗЫЧНОСТИ ==========
def get_translations(lang='ru'):
    """
    Возвращает словарь переводов для указанного языка
    """
    translations = {
        'ru': {
            'title': 'Контрагенты',
            'welcome': 'Добро пожаловать!',
            'add_contragent': 'Добавить нового контрагента',
            'search': 'Поиск',
            'search_placeholder': 'Введите текст...',
            'search_by': 'Искать по:',
            'search_all': 'Всем параметрам',
            'search_org_name': 'Наименование',
            'search_inn': 'ИНН',
            'search_contact_person': 'Контактное лицо',
            'search_address': 'Адрес',
            'search_position': 'Должность',
            'search_phones': 'Телефоны',
            'search_emails': 'Email',
            'search_websites': 'Сайты',
            'login': 'Войти',
            'logout': 'Выйти',
            'register': 'Регистрация',
            'personal_cabinet': 'Личный кабинет',
            'go_to_cabinet': 'Перейти в личный кабинет',
            'organization': 'Организация, ИНН',
            'contact_person': 'Контактное лицо',
            'position': 'Должность',
            'address': 'Адрес',
            'phones': 'Телефоны',
            'emails': 'Email',
            'websites': 'Сайты',
            'actions': 'Действия',
            'edit': 'Редактировать',
            'copy': 'Копировать контрагента',
            'copy_verb': 'Копировать',
            'create_copy': 'Создать копию',
            'delete': 'Удалить',
            'no_contragents': 'Контрагентов не найдено',
            'change_search': 'Измените параметры поиска или добавьте контрагента',
            'welcome_to_system': 'Добро пожаловать в систему "Контрагенты"!',
            'need_auth': 'Для работы с контрагентами необходимо',
            'need_auth_login': 'войти',
            'need_auth_or': 'или',
            'need_auth_register': 'зарегистрироваться',
            'forgot_password': 'Забыли пароль?',
            'restore_access': 'Восстановить доступ',
            'login_title': 'Вход в систему',
            'username': 'Имя пользователя',
            'password': 'Пароль',
            'to_main': 'На главную',
            'forgot_password_q': 'Забыли пароль? Восстановить доступ',
            'no_account': 'Нет аккаунта?',
            'register_here': 'Зарегистрируйтесь',
            'registration': 'Регистрация',
            'email_optional': 'Email (необязательно)',
            'confirm_password': 'Подтвердите пароль',
            'already_have_account': 'Уже есть аккаунт?',
            'login_here': 'Войти',
            'password_recovery': 'Восстановление пароля',
            'enter_email': 'Введите ваш email:',
            'send_recovery_link': 'Отправить ссылку для восстановления',
            'change_email': 'Изменить email',
            'new_email': 'Новый email:',
            'save_email': 'Сохранить email',
            'change_password': 'Изменить пароль',
            'current_password': 'Текущий пароль',
            'new_password': 'Новый пароль',
            'confirm_new_password': 'Подтвердите пароль',
            'change_password_btn': 'Сменить пароль',
            'back': 'Назад',
            'registration_date': 'Дата регистрации',
            'contragents_count': 'Контрагентов',
            'not_specified': 'Не указан',
            'unknown': 'Неизвестно',
            'clear_search': 'Очистить',
            'search_button': 'Поиск',
            'language_ru': 'Русский',
            'language_en': 'English',
            'change_language': 'Сменить язык',
            'org_name': 'Организация',
            'inn': 'ИНН',
            'user': 'Пользователь',
            'welcome_back': 'добро пожаловать!',
            'enter_login': 'Логин',
            'enter_password': 'Пароль',
            'reset_password_request': 'Отправить ссылку для восстановления',
            'reset_password_sent': 'Письмо отправлено. Проверьте почту.',
            'email_updated': 'Email успешно обновлен',
            'password_updated': 'Пароль успешно изменен',
            'add_success': 'Контрагент успешно добавлен',
            'edit_success': 'Контрагент успешно обновлен',
            'save_changes': 'Сохранить изменения',
            'add': 'Добавить',
            'delete_success': 'Контрагент успешно удален',
            'login_success': 'Авторизация успешна',
            'logout_success': 'Вы вышли из системы',
            'register_success': 'Регистрация успешна! Теперь вы можете войти.',
            'auth_required': 'Для доступа к этой странице необходимо авторизоваться',
            'user_exists': 'Пользователь с таким именем уже существует',
            'email_exists': 'Пользователь с таким email уже существует',
            'wrong_password': 'Неверный текущий пароль',
            'password_length': 'Пароль должен быть не менее 6 символов',
            'passwords_not_match': 'Пароли не совпадают',
            'edit_contragent': 'Редактировать контрагента',
            'copy_contragent': 'Копировать контрагента',
            'save_changes': 'Сохранить изменения',
            'create_copy': 'Создать копию',
            'organization_name': 'Наименование организации',
            'add_phone': 'Добавить телефон',
            'add_email': 'Добавить email',
            'add_site': 'Добавить сайт',
            'max_20_chars': 'Максимум 20 символов для каждого телефона',
            'max_50_chars': 'Максимум 50 символов для каждого email',
            'max_200_chars': 'Максимум 200 символов',
            'any_text_or_no_site': '(можно вводить "нет сайте" или любой текст)',
            'phone': 'телефона',
            'email': 'email',
            'website': 'сайта',
            'max_3_items': 'Максимум можно добавить 3 {item}',
            'connection_error': 'Ошибка соединения с сервером',
            'password_recovery': 'Восстановление пароля',
            'new_password': 'Новый пароль',
            'confirm_password': 'Подтвердите пароль',
            'change_password': 'Изменить пароль',
            'link_invalid': 'Ссылка для восстановления пароля недействительна или истекла.',
            'password_changed': 'Пароль успешно изменен! Теперь вы можете войти с новым паролем.',
            'error_editing': 'Ошибка при обновлении контрагента',
            'copy_not_found': 'Контрагент для копирования не найден',
            'invalid_copy_id': 'Некорректный ID для копирования',
            'org_name_required': 'Название организации обязательно для заполнения',
            'error_adding': 'Ошибка при добавлении контрагента'
        },
        'en': {
            'title': 'Counterparties',
            'welcome': 'Welcome!',
            'add_contragent': 'Add new counterparty',
            'search': 'Search',
            'search_placeholder': 'Enter text...',
            'search_by': 'Search by:',
            'search_all': 'All parameters',
            'search_org_name': 'Organization name',
            'search_inn': 'Tax ID',
            'search_contact_person': 'Contact person',
            'search_address': 'Address',
            'search_position': 'Position',
            'search_phones': 'Phones',
            'search_emails': 'Email',
            'search_websites': 'Websites',
            'login': 'Login',
            'logout': 'Logout',
            'register': 'Register',
            'personal_cabinet': 'Personal cabinet',
            'go_to_cabinet': 'Go to personal cabinet',
            'organization': 'Organization, Tax ID',
            'contact_person': 'Contact person',
            'position': 'Position',
            'address': 'Address',
            'phones': 'Phones',
            'emails': 'Email',
            'websites': 'Websites',
            'actions': 'Actions',
            'edit': 'Edit',
            'copy': 'Copy counterparty',
            'copy_verb': 'Copy',
            'create_copy': 'Create copy',
            'delete': 'Delete',
            'no_contragents': 'No counterparties found',
            'change_search': 'Change search parameters or add counterparty',
            'welcome_to_system': 'Welcome to "Counterparties" system!',
            'need_auth': 'To work with counterparties you need to',
            'need_auth_login': 'login',
            'need_auth_or': 'or',
            'need_auth_register': 'register',
            'forgot_password': 'Forgot password?',
            'restore_access': 'Restore access',
            'login_title': 'Login',
            'username': 'Username',
            'password': 'Password',
            'to_main': 'To main',
            'forgot_password_q': 'Forgot password? Restore access',
            'no_account': 'No account?',
            'register_here': 'Register',
            'registration': 'Registration',
            'email_optional': 'Email (optional)',
            'confirm_password': 'Confirm password',
            'already_have_account': 'Already have an account?',
            'login_here': 'Login',
            'password_recovery': 'Password recovery',
            'enter_email': 'Enter your email:',
            'send_recovery_link': 'Send recovery link',
            'change_email': 'Change email',
            'new_email': 'New email:',
            'save_email': 'Save email',
            'change_password': 'Change password',
            'current_password': 'Current password',
            'new_password': 'New password',
            'confirm_new_password': 'Confirm password',
            'change_password_btn': 'Change password',
            'back': 'Back',
            'registration_date': 'Registration date',
            'contragents_count': 'Counterparties',
            'not_specified': 'Not specified',
            'unknown': 'Unknown',
            'clear_search': 'Clear',
            'search_button': 'Search',
            'language_ru': 'Russian',
            'language_en': 'English',
            'change_language': 'Change language',
            'org_name': 'Organization',
            'inn': 'Tax ID',
            'user': 'User',
            'welcome_back': 'welcome!',
            'enter_login': 'Login',
            'enter_password': 'Password',
            'reset_password_request': 'Send recovery link',
            'reset_password_sent': 'Email sent. Check your inbox.',
            'email_updated': 'Email successfully updated',
            'password_updated': 'Password successfully changed',
            'add_success': 'Counterparty successfully added',
            'edit_success': 'Counterparty successfully updated',
            'save_changes': 'Save changes',
            'add': 'Add',
            'delete_success': 'Counterparty successfully deleted',
            'login_success': 'Authorization successful',
            'logout_success': 'You have logged out',
            'register_success': 'Registration successful! Now you can login.',
            'auth_required': 'You need to log in to access this page',
            'user_exists': 'User with this name already exists',
            'email_exists': 'User with this email already exists',
            'wrong_password': 'Wrong current password',
            'password_length': 'Password must be at least 6 characters',
            'passwords_not_match': 'Passwords do not match',
            'edit_contragent': 'Edit Counterparty',
            'copy_contragent': 'Copy Counterparty',
            'save_changes': 'Save changes',
            'create_copy': 'Create copy',
            'organization_name': 'Organization name',
            'add_phone': 'Add phone',
            'add_email': 'Add email',
            'add_site': 'Add website',
            'max_20_chars': 'Maximum 20 characters for each phone',
            'max_50_chars': 'Maximum 50 characters for each email',
            'max_200_chars': 'Maximum 200 characters',
            'any_text_or_no_site': '(you can enter "no site" or any text)',
            'phone': 'phone',
            'email': 'email',
            'website': 'website',
            'max_3_items': 'You can add up to 3 {item}',
            'connection_error': 'Server connection error',
            'password_recovery': 'Password Recovery',
            'new_password': 'New password',
            'confirm_password': 'Confirm password',
            'change_password': 'Change password',
            'link_invalid': 'The password reset link is invalid or has expired.',
            'password_changed': 'Password successfully changed! You can now log in with your new password.',
            'error_editing': 'Error updating counterparty',
            'copy_not_found': 'Counterparty for copying not found',
            'invalid_copy_id': 'Invalid copy ID',
            'org_name_required': 'Organization name is required',
            'error_adding': 'Error adding counterparty'
        }
    }
    return translations.get(lang, translations['ru'])

# ========== МОДЕЛИ БАЗЫ ДАННЫХ ==========

# Модель пользователя
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    
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
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    phones = db.relationship('Phone', backref='contragent', lazy=True, cascade="all, delete-orphan")
    emails = db.relationship('Email', backref='contragent', lazy=True, cascade="all, delete-orphan")
    websites = db.relationship('Website', backref='contragent', lazy=True, cascade="all, delete-orphan")

# ========== ДЕКОРАТОРЫ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

# Декоратор для проверки авторизации
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            lang = session.get('language', 'ru')
            t = get_translations(lang)
            flash(t['auth_required'], 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Флаг для отслеживания инициализации БД
database_initialized = False

# Создаем таблицы при первом запросе
@app.before_request
def initialize_database():
    global database_initialized
    if not database_initialized:
        try:
            print("🔄 Создание таблиц в базе данных PostgreSQL...")
            with app.app_context():
                db.create_all()
                print("✅ Таблицы PostgreSQL созданы")
                
                # Создаем тестового пользователя, если нет пользователей
                if User.query.count() == 0:
                    test_user = User(username='admin', email='admin@example.com')
                    test_user.set_password('admin123')
                    db.session.add(test_user)
                    db.session.commit()
                    print("✅ Создан тестовый пользователь PostgreSQL:")
                    print("   Логин: admin")
                    print("   Пароль: admin123")
                else:
                    print(f"ℹ️  В базе PostgreSQL уже есть {User.query.count()} пользователей")
            
            database_initialized = True
        except Exception as e:
            print(f"⚠️  Ошибка при создании таблиц PostgreSQL: {e}")
            print("⚠️  Пробуем продолжить...")
            # Не устанавливаем флаг в True, чтобы попробовать снова при следующем запросе

# ========== МАРШРУТЫ ==========

# Маршрут для смены языка
@app.route('/set_language/<lang>')
def set_language(lang):
    if lang in ['ru', 'en']:
        session['language'] = lang
    return redirect(request.referrer or url_for('index'))

# Главная страница
@app.route('/')
def index():
    lang = session.get('language', 'ru')
    t = get_translations(lang)
    
    search_query_input = request.args.get('q', '').strip()
    search_query_lower = search_query_input.lower()
    search_field = request.args.get('field', 'all')
    
    if 'user_id' in session:
        user = db.session.get(User, session['user_id'])
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
                                        user=user,
                                        t=t,
                                        lang=lang)
                
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
                                    user=user,
                                    t=t,
                                    lang=lang)
            
            else:
                contragents = query.order_by(Contragent.id.desc()).all()
                return render_template('index.html', 
                                    contragents=contragents, 
                                    search_query=search_query_input, 
                                    search_field=search_field,
                                    user=user,
                                    t=t,
                                    lang=lang)
    
    return render_template('index.html', 
                         contragents=[], 
                         search_query=search_query_input, 
                         search_field=search_field,
                         user=None,
                         t=t,
                         lang=lang)

# Старые маршруты для совместимости
@app.route('/login', methods=['GET'])
def login_redirect():
    return redirect(url_for('index'))

@app.route('/register', methods=['GET'])
def register_redirect():
    return redirect(url_for('index'))

# API для авторизации
@app.route('/api/login', methods=['POST'], endpoint='api_login')
def api_login():
    lang = session.get('language', 'ru')
    t = get_translations(lang)
    
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    user = User.query.filter_by(username=username).first()
    
    if user and user.check_password(password):
        session['user_id'] = user.id
        session.permanent = True
        return jsonify({'success': True, 'message': t['login_success']})
    else:
        return jsonify({'success': False, 'message': 'Неверное имя пользователя или пароль'})

# API для регистрации
@app.route('/api/register', methods=['POST'], endpoint='api_register')
def api_register():
    lang = session.get('language', 'ru')
    t = get_translations(lang)
    
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    
    if email == '':
        email = None
    
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({'success': False, 'message': t['user_exists']})
    
    if email:
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            return jsonify({'success': False, 'message': t['email_exists']})
    
    if len(password) < 6:
        return jsonify({'success': False, 'message': t['password_length']})
    
    new_user = User(username=username, email=email)
    new_user.set_password(password)
    
    try:
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'success': True, 'message': t['register_success']})
    except:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Произошла ошибка при регистрации'})

# API для изменения email
@app.route('/api/change-email', methods=['POST'])
@login_required
def change_email():
    lang = session.get('language', 'ru')
    t = get_translations(lang)
    
    data = request.get_json()
    new_email = data.get('email', '').strip()
    
    user = User.query.get(session['user_id'])
    
    if not new_email:
        user.email = None
        db.session.commit()
        return jsonify({'success': True, 'message': 'Email удален'})
    
    existing_user = User.query.filter(User.email == new_email, User.id != user.id).first()
    if existing_user:
        return jsonify({'success': False, 'message': t['email_exists']})
    
    user.email = new_email
    db.session.commit()
    
    return jsonify({'success': True, 'message': t['email_updated']})

# API для изменения пароля
@app.route('/api/change-password', methods=['POST'])
@login_required
def change_password():
    lang = session.get('language', 'ru')
    t = get_translations(lang)
    
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    user = User.query.get(session['user_id'])
    
    if not user.check_password(current_password):
        return jsonify({'success': False, 'message': t['wrong_password']})
    
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': t['password_length']})
    
    user.set_password(new_password)
    db.session.commit()
    
    return jsonify({'success': True, 'message': t['password_updated']})

# API для восстановления пароля
@app.route('/reset_password_request', methods=['POST'])
def reset_password_request_ajax():
    lang = session.get('language', 'ru')
    t = get_translations(lang)
    
    data = request.get_json()
    email = data.get('email', '').strip()
    
    if not email:
        return jsonify({'success': False, 'message': 'Пожалуйста, введите email'})
    
    user = User.query.filter_by(email=email).first()
    success_message = t['reset_password_sent']
    
    if user:
        reset_token = str(uuid.uuid4())
        user.reset_token = reset_token
        user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        
        try:
            db.session.commit()
            reset_url = url_for('reset_password_confirm', token=reset_token, _external=True)
            result = send_reset_email_via_unisender(email, reset_url)
            
            if not result['success']:
                print(f"⚠️ Ошибка отправки письма для {email}: {result.get('error')}")
        
        except Exception as e:
            db.session.rollback()
            print(f"❌ Ошибка при сохранении токена: {str(e)}")
            return jsonify({'success': False, 'message': 'Ошибка сервера при обработки запроса'})
    
    return jsonify({'success': True, 'message': success_message})

# Подтверждение сброса пароля
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password_confirm(token):
    lang = session.get('language', 'ru')
    t = get_translations(lang)
    
    user = User.query.filter_by(reset_token=token).first()
    
    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.utcnow():
        flash(t['reset_password_sent'], 'danger')
        return render_template('reset_confirm.html', token=None, valid=False, t=t, lang=lang)
    
    if request.method == 'POST':
        new_password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if not new_password or not confirm_password:
            flash(t['passwords_not_match'], 'danger')
            return render_template('reset_confirm.html', token=token, valid=True, t=t, lang=lang)
        
        if new_password != confirm_password:
            flash(t['passwords_not_match'], 'danger')
            return render_template('reset_confirm.html', token=token, valid=True, t=t, lang=lang)
        
        if len(new_password) < 6:
            flash(t['password_length'], 'danger')
            return render_template('reset_confirm.html', token=token, valid=True, t=t, lang=lang)
        
        try:
            user.set_password(new_password)
            user.reset_token = None
            user.reset_token_expires = None
            db.session.commit()
            
            flash(t['password_updated'], 'success')
            return render_template('reset_confirm.html', token=None, valid=False, success=True, t=t, lang=lang)
            
        except Exception as e:
            db.session.rollback()
            flash('Ошибка при изменении пароля. Пожалуйста, попробуйте еще раз.', 'danger')
            return render_template('reset_confirm.html', token=token, valid=True, t=t, lang=lang)
    
    return render_template('reset_confirm.html', token=token, valid=True, t=t, lang=lang)

# Выход
@app.route('/logout')
def logout():
    lang = session.get('language', 'ru')
    t = get_translations(lang)
    
    session.pop('user_id', None)
    flash(t['logout_success'], 'success')
    return redirect(url_for('index'))

# Добавление контрагента
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_contragent():
    # Определяем текущий язык
    lang = session.get('language', 'ru')
    t = get_translations(lang)
    
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
                flash(t['copy_not_found'], 'danger')
                return redirect(url_for('index'))
        except (ValueError, TypeError):
            flash(t['invalid_copy_id'], 'danger')
            return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            org_name = request.form.get('org_name', '').strip()
            inn = request.form.get('inn', '').strip()
            contact_person = request.form.get('contact_person', '').strip()
            position = request.form.get('position', '').strip()
            address = request.form.get('address', '').strip()
            
            if not org_name:
                flash(t['org_name_required'], 'danger')
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
            
            flash(t['add_success'], 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f"{t['error_adding']}: {str(e)}", 'danger')
            return redirect(url_for('add_contragent'))
    
    # GET запрос - показываем форму добавления
    return render_template('add.html', 
                         contragent=contragent_to_copy, 
                         is_copy=bool(copy_id_str),
                         t=t,
                         lang=lang)

# Редактирование контрагента
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_contragent(id):
    # Определяем текущий язык
    lang = session.get('language', 'ru')
    t = get_translations(lang)
    
    contragent = Contragent.query.filter_by(id=id, user_id=session['user_id']).first_or_404()
    
    if request.method == 'POST':
        try:
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
                return jsonify({'success': True, 'message': t['edit_success']})
            else:
                flash(t['edit_success'], 'success')
                return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            error_message = t['error_editing']
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': error_message})
            else:
                flash(error_message, 'danger')
                return redirect(url_for('edit_contragent', id=id))
    
    # GET запрос - показываем форму редактирования
    return render_template('edit.html', 
                         contragent=contragent, 
                         is_copy=False,
                         t=t,
                         lang=lang)

# Удаление контрагента
@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_contragent(id):
    lang = session.get('language', 'ru')
    t = get_translations(lang)
    
    try:
        contragent = Contragent.query.filter_by(id=id, user_id=session['user_id']).first()
        
        if not contragent:
            return jsonify({'success': False, 'message': 'Контрагент не найден'})
        
        db.session.delete(contragent)
        db.session.commit()
        return jsonify({'success': True, 'message': t['delete_success']})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Ошибка при удалении: {str(e)}'})

# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
    print(f"🚀 Приложение запущено на порту {port}")