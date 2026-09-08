import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sao-judas-moc-secret-key-final'

# Configuração do Banco de Dados Dinâmico (Postgres ou SQLite)
uri = os.getenv("DATABASE_URL")
if uri and uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri or 'sqlite:///paroquia.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELOS ---

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False) # NOVO: Campo de Admin

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
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sala_id = db.Column(db.Integer, db.ForeignKey('sala.id'), nullable=False)
    
    usuario = db.relationship('User', backref='reservas')
    sala = db.relationship('Sala', backref='reservas')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROTAS ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Este e-mail já está cadastrado.', 'danger')
            return redirect(url_for('cadastro'))

        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, email=email, password=hashed_pw, is_admin=False)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Conta criada! Faça seu login.', 'success')
        return redirect(url_for('login'))
    return render_template('cadastro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('E-mail ou senha incorretos.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/solicitar', methods=['GET', 'POST'])
@login_required
def solicitar():
    salas_disponiveis = None
    data_sel = None
    qtd_sel = None

    if request.method == 'POST':
        data_sel = request.form.get('data')
        qtd_sel = int(request.form.get('qtd'))
        
        todas = Sala.query.filter(Sala.capacidade >= qtd_sel).order_by(Sala.capacidade).all()
        # Regra de esconder Auditório para grupos pequenos
        salas_disponiveis = [s for s in todas if s.capacidade <= qtd_sel * 2.5]
        if not salas_disponiveis:
            salas_disponiveis = todas

    return render_template('solicitar.html', salas=salas_disponiveis, data=data_sel, qtd=qtd_sel)

@app.route('/confirmar', methods=['POST'])
@login_required
def confirmar():
    sala_id = request.form.get('sala_id')
    data_str = request.form.get('data')
    qtd = request.form.get('qtd')
    h_ini = request.form.get('h_inicio')
    h_fim = request.form.get('h_fim')
    recorrente = request.form.get('recorrente')
    
    data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
    
    def salvar(d):
        nova = Reserva(data=d, hora_inicio=h_ini, hora_fim=h_fim, qtd_pessoas=qtd, sala_id=sala_id, usuario_id=current_user.id)
        db.session.add(nova)

    salvar(data_obj)
    if recorrente == 'sim':
        ano = datetime.now().year
        prox = data_obj + timedelta(days=7)
        while prox.year == ano:
            salvar(prox)
            prox += timedelta(days=7)

    db.session.commit()
    num_secretaria = "5538999999999" 
    msg = f"Olá, aqui é {current_user.username}. Fiz uma reserva para o dia {data_str}."
    link = f"https://wa.me/{num_secretaria}?text={msg.replace(' ', '%20')}"
    flash(f'Enviado! <a href="{link}" target="_blank" class="btn btn-success btn-sm">Avisar no WhatsApp</a>', 'info')
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash('Acesso negado! Apenas administradores podem ver esta página.', 'danger')
        return redirect(url_for('index'))
    reservas = Reserva.query.order_by(Reserva.data.asc()).all()
    return render_template('admin.html', reservas=reservas)

@app.route('/aprovar/<int:id>', methods=['POST'])
@login_required
def aprovar_reserva(id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    reserva = Reserva.query.get_or_404(id)
    reserva.status = 'Aprovado'
    db.session.commit()
    flash(f'Reserva aprovada!', 'success')
    return redirect(url_for('admin'))

# --- INICIALIZAÇÃO ---

def setup_db():
    db.create_all()
    # Criar Admin de Teste
    if not User.query.filter_by(email='admin@paroquia.com').first():
        pw = bcrypt.generate_password_hash('saojudas2024').decode('utf-8')
        admin_user = User(username='Secretaria SJT', email='admin@paroquia.com', password=pw, is_admin=True)
        db.session.add(admin_user)
    
    if not Sala.query.first():
        db.session.add_all([
            Sala(nome="Sala Catequese 01", capacidade=15),
            Sala(nome="Sala Reuniões 02", capacidade=35),
            Sala(nome="Auditório São Judas", capacidade=100)
        ])
    db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        setup_db()
    app.run(debug=True)
