from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)

# Настройка базы данных SQLite
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'contragents.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Модель Контрагента (таблица в базе данных)
class Contragent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.String(200))
    note = db.Column(db.Text)

    def __repr__(self):
        return f'<Contragent {self.name}>'

# Создаём таблицу в базе данных (если её нет)
with app.app_context():
    db.create_all()

# Главная страница - список всех контрагентов
@app.route('/')
def index():
    contragents = Contragent.query.all()
    return render_template('index.html', contragents=contragents)

# Страница добавления нового контрагента
@app.route('/add', methods=['GET', 'POST'])
def add_contragent():
    if request.method == 'POST':
        # Получаем данные из формы
        name = request.form['name']
        phone = request.form['phone']
        email = request.form['email']
        address = request.form['address']
        note = request.form['note']
        
        # Создаём нового контрагента
        new_contragent = Contragent(
            name=name, 
            phone=phone, 
            email=email, 
            address=address, 
            note=note
        )
        
        # Сохраняем в базу данных
        db.session.add(new_contragent)
        db.session.commit()
        
        # Возвращаемся на главную страницу
        return redirect(url_for('index'))
    
    return render_template('add.html')

if __name__ == '__main__':
    app.run(debug=True)