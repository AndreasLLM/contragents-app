from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ваш-секретный-ключ'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'contragents.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- МОДЕЛИ ДАННЫХ С ОГРАНИЧЕНИЯМИ ---
class Contragent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    org_name = db.Column(db.String(50), nullable=False)  # Макс 50 символов
    inn = db.Column(db.String(20))  # Макс 20 символов
    contact_person = db.Column(db.String(50))  # Макс 50 символов
    address = db.Column(db.String(50))  # Макс 50 символов
    position = db.Column(db.String(50))  # Макс 50 символов
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Для сортировки по дате
    phones = db.relationship('Phone', backref='contragent', lazy=True, cascade="all, delete-orphan")
    emails = db.relationship('Email', backref='contragent', lazy=True, cascade="all, delete-orphan")
    websites = db.relationship('Website', backref='contragent', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Contragent {self.org_name}>'

class Phone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(20))  # Макс 20 символов
    contragent_id = db.Column(db.Integer, db.ForeignKey('contragent.id'), nullable=False)

class Email(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(50))  # Макс 50 символов
    contragent_id = db.Column(db.Integer, db.ForeignKey('contragent.id'), nullable=False)

class Website(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(200))  # Макс 200 символов
    contragent_id = db.Column(db.Integer, db.ForeignKey('contragent.id'), nullable=False)

# Создаём таблицы
with app.app_context():
    db.create_all()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def save_multiple_fields(form_data, field_type, contragent):
    """Сохраняет несколько значений одного типа"""
    field_map = {
        'number': ('phones', Phone, 'number'),
        'email_address': ('emails', Email, 'address'),
        'url': ('websites', Website, 'url')
    }
    
    if field_type not in field_map:
        return
    
    rel_name, ModelClass, field_attr = field_map[field_type]
    items = form_data.getlist(field_type)
    
    for item in items:
        if item.strip():
            # Ограничение длины
            if field_type == 'url':
                max_len = 200
            else:
                max_len = 50
            
            if len(item.strip()) > max_len:
                item = item.strip()[:max_len]
            
            new_item = ModelClass()
            setattr(new_item, field_attr, item.strip()[:max_len])
            getattr(contragent, rel_name).append(new_item)

# --- МАРШРУТЫ ---
@app.route('/')
def index():
    """Главная страница с поиском"""
    search_query = request.args.get('q', '')
    search_field = request.args.get('field', 'all')

    query = Contragent.query

    if search_query:
        if search_field == 'all':
            # Ищем по всем полям (частичное совпадение)
            query = query.filter(
                or_(
                    Contragent.org_name.ilike(f'%{search_query}%'),
                    Contragent.inn.ilike(f'%{search_query}%'),
                    Contragent.contact_person.ilike(f'%{search_query}%'),
                    Contragent.address.ilike(f'%{search_query}%'),
                    Contragent.position.ilike(f'%{search_query}%')
                )
            )
        elif search_field == 'phones':
            query = query.join(Phone).filter(Phone.number.ilike(f'%{search_query}%'))
        elif search_field == 'emails':
            query = query.join(Email).filter(Email.address.ilike(f'%{search_query}%'))
        elif search_field == 'websites':
            query = query.join(Website).filter(Website.url.ilike(f'%{search_query}%'))
        else:
            if hasattr(Contragent, search_field):
                query = query.filter(getattr(Contragent, search_field).ilike(f'%{search_query}%'))

    # Сортировка по дате добавления (новые сверху)
    contragents = query.order_by(Contragent.created_at.desc()).all()
    
    return render_template('index.html', 
                         contragents=contragents,
                         search_query=search_query,
                         search_field=search_field)

@app.route('/add', methods=['GET', 'POST'])
def add_contragent():
    """Добавление нового контрагента"""
    if request.method == 'POST':
        try:
            # Ограничиваем длину полей
            org_name = request.form['org_name'][:50] if request.form['org_name'] else ''
            inn = request.form.get('inn', '')[:20]
            contact_person = request.form.get('contact_person', '')[:50]
            address = request.form.get('address', '')[:50]
            position = request.form.get('position', '')[:50]
            
            # Создаём основную запись
            new_contragent = Contragent(
                org_name=org_name,
                inn=inn,
                contact_person=contact_person,
                address=address,
                position=position
            )

            # Сохраняем множественные поля
            save_multiple_fields(request.form, 'number', new_contragent)
            save_multiple_fields(request.form, 'email_address', new_contragent)
            save_multiple_fields(request.form, 'url', new_contragent)

            db.session.add(new_contragent)
            db.session.commit()
            
            # Возвращаем JSON для всплывающего сообщения
            return jsonify({'success': True, 'message': 'Контрагент успешно добавлен!'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Ошибка при добавлении: {str(e)}'})

    return render_template('add.html')

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_contragent(id):
    """Редактирование контрагента"""
    contragent = Contragent.query.get_or_404(id)

    if request.method == 'POST':
        try:
            # Обновляем с ограничениями длины
            contragent.org_name = request.form['org_name'][:50] if request.form['org_name'] else ''
            contragent.inn = request.form.get('inn', '')[:20]
            contragent.contact_person = request.form.get('contact_person', '')[:50]
            contragent.address = request.form.get('address', '')[:50]
            contragent.position = request.form.get('position', '')[:50]

            # Удаляем старые связанные записи
            Phone.query.filter_by(contragent_id=id).delete()
            Email.query.filter_by(contragent_id=id).delete()
            Website.query.filter_by(contragent_id=id).delete()

            # Добавляем новые значения
            save_multiple_fields(request.form, 'number', contragent)
            save_multiple_fields(request.form, 'email_address', contragent)
            save_multiple_fields(request.form, 'url', contragent)

            db.session.commit()
            return jsonify({'success': True, 'message': 'Данные успешно обновлены!'})

        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Ошибка при обновлении: {str(e)}'})

    return render_template('edit.html', contragent=contragent)

@app.route('/delete/<int:id>', methods=['POST'])
def delete_contragent(id):
    """Удаление контрагента"""
    contragent = Contragent.query.get_or_404(id)
    try:
        db.session.delete(contragent)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Контрагент успешно удалён!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Ошибка при удалении: {str(e)}'})

if __name__ == '__main__':
    app.run(debug=True)