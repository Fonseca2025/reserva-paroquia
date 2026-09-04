import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sao-judas-moc-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///paroquia.db'

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELOS DO BANCO DE DADOS ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)

class Sala(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)
    capacidade = db.Column(db.Integer, nullable=False)

class Reserva(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    hora_inicio = db.Column(db.String(5), nullable=False)
    hora_fim = db.Column(db.String(5), nullable=False)
    qtd_pessoas = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='Pendente')
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    sala_id = db.Column(db.Integer, db.ForeignKey('sala.id'))
    sala = db.relationship('Sala', backref='reservas')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROTAS ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Login inválido. Tente novamente.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/solicitar', methods=['GET', 'POST'])
@login_required
def solicitar():
    salas_disponiveis = None
    data_selecionada = None
    qtd_selecionada = None

    if request.method == 'POST':
        data_selecionada = request.form.get('data')
        qtd_selecionada = int(request.form.get('qtd'))
        
        # Lógica: Busca todas que comportam a quantidade
        todas_que_cabem = Sala.query.filter(Sala.capacidade >= qtd_selecionada).order_by(Sala.capacidade).all()
        
        # Filtro de "Esconder Sala Grande":
        # Se houver salas com capacidade de até 2x a quantidade pedida, mostre apenas elas.
        # Ex: Pediu 10? Mostra as de 15, 20, 25. Esconde a de 100.
        salas_ideais = [s for s in todas_que_cabem if s.capacidade <= qtd_selecionada * 2.5]
        
        if salas_ideais:
            salas_disponiveis = salas_ideais
        else:
            salas_disponiveis = todas_que_cabem # Libera o auditório se for a única opção

    return render_template('solicitar.html', salas=salas_disponiveis, data=data_selecionada, qtd=qtd_selecionada)

@app.route('/confirmar', methods=['POST'])
@login_required
def confirmar():
    sala_id = request.form.get('sala_id')
    data_str = request.form.get('data')
    qtd = request.form.get('qtd')
    h_inicio = request.form.get('h_inicio')
    h_fim = request.form.get('h_fim')
    recorrente = request.form.get('recorrente')
    
    data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
    
    def salvar(d):
        nova = Reserva(data=d, hora_inicio=h_inicio, hora_fim=h_fim, qtd_pessoas=qtd, sala_id=sala_id, usuario_id=current_user.id)
        db.session.add(nova)

    salvar(data_obj)

    if recorrente == 'sim':
        prox_data = data_obj + timedelta(days=7)
        while prox_data.year == 2024: # Altere para 2025 se necessário
            salvar(prox_data)
            prox_data += timedelta(days=7)

    db.session.commit()
    
    msg = f"Olá! Solicitei a reserva da sala no dia {data_str} para {qtd} pessoas."
    link_zap = f"https://wa.me/5538999999999?text={msg.replace(' ', '%20')}"
    
    flash(f'Pré-agendamento enviado! Clique aqui para avisar no WhatsApp: <a href="{link_zap}" target="_blank">Enviar Mensagem</a>')
    return redirect(url_for('index'))

# --- INICIALIZAÇÃO ---
def setup_db():
    db.create_all()
    if not User.query.filter_by(email='teste@gmail.com').first():
        pw = bcrypt.generate_password_hash('123456').decode('utf-8')
        db.session.add(User(username='Coordenador', email='teste@gmail.com', password=pw))
    if not Sala.query.first():
        db.session.add_all([
            Sala(nome="Sala 01 (Catequese)", capacidade=15),
            Sala(nome="Sala 02 (Reuniões)", capacidade=30),
            Sala(nome="Auditório São Judas", capacidade=100)
        ])
    db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        setup_db()
    app.run(debug=True, port=5000)