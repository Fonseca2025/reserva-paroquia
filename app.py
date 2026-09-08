import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sao-judas-moc-secret-key-final'
# Configuração do Banco de Dados Dinâmico
uri = os.getenv("DATABASE_URL")
if uri and uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = uri or 'sqlite:///paroquia.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
    # Relacionamento para ver as reservas do usuário
    reservas = db.relationship('Reserva', backref='usuario', lazy=True)

class Sala(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)
    capacidade = db.Column(db.Integer, nullable=False)
    # Relacionamento para ver as reservas da sala
    reservas = db.relationship('Reserva', backref='sala', lazy=True)

class Reserva(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    hora_inicio = db.Column(db.String(5), nullable=False)
    hora_fim = db.Column(db.String(5), nullable=False)
    qtd_pessoas = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='Pendente') # Pendente ou Aprovado
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sala_id = db.Column(db.Integer, db.ForeignKey('sala.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROTAS DE AUTENTICAÇÃO ---

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Este e-mail já está cadastrado.', 'danger')
            return redirect(url_for('cadastro'))

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Conta criada com sucesso! Faça seu login.', 'success')
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

# --- ROTAS DO SISTEMA DE RESERVAS ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/solicitar', methods=['GET', 'POST'])
@login_required
def solicitar():
    salas_disponiveis = None
    data_selecionada = None
    qtd_selecionada = None

    if request.method == 'POST':
        data_selecionada = request.form.get('data')
        qtd_selecionada = int(request.form.get('qtd'))
        
        # 1. Filtra salas que suportam a quantidade
        todas_que_cabem = Sala.query.filter(Sala.capacidade >= qtd_selecionada).order_by(Sala.capacidade).all()
        
        # 2. Lógica de Esconder Sala Grande (Auditório)
        # Se houver salas pequenas que caibam o grupo (até 2.5x o tamanho do grupo),
        # mostramos apenas as pequenas. Ex: 10 pessoas não vêem o auditório de 100.
        salas_adequadas = [s for s in todas_que_cabem if s.capacidade <= qtd_selecionada * 2.5]
        
        if salas_adequadas:
            salas_disponiveis = salas_adequadas
        else:
            salas_disponiveis = todas_que_cabem # Libera salas maiores se não houver opção pequena

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
    
    def criar_entrada(data_r):
        nova = Reserva(
            data=data_r, hora_inicio=h_inicio, hora_fim=h_fim, 
            qtd_pessoas=qtd, sala_id=sala_id, usuario_id=current_user.id
        )
        db.session.add(nova)

    # Reserva inicial
    criar_entrada(data_obj)

    # Recorrência semanal até o fim do ano vigente
    if recorrente == 'sim':
        ano_atual = datetime.now().year
        prox_data = data_obj + timedelta(days=7)
        while prox_data.year == ano_atual:
            criar_entrada(prox_data)
            prox_data += timedelta(days=7)

    db.session.commit()
    
    # Gerar link do WhatsApp para a Secretaria (Altere o número abaixo para o real)
    numero_secretaria = "5538999999999" 
    msg = f"Olá! Fiz um pré-agendamento no App para o dia {data_str} (Sala: {sala_id}). Aguardo aprovação."
    link_zap = f"https://wa.me/{numero_secretaria}?text={msg.replace(' ', '%20')}"
    
    flash(f'Solicitação enviada com sucesso! <br><br> <a href="{link_zap}" target="_blank" class="btn btn-success">Avisar Secretaria no WhatsApp</a>', 'info')
    return redirect(url_for('index'))

# --- ROTAS ADMINISTRATIVAS ---

@app.route('/admin')
@login_required
def admin():
    # Lista todas as reservas ordenadas pela data mais próxima
    reservas = Reserva.query.order_by(Reserva.data.asc()).all()
    return render_template('admin.html', reservas=reservas)

@app.route('/aprovar/<int:id>', methods=['POST'])
@login_required
def aprovar_reserva(id):
    reserva = Reserva.query.get_or_404(id)
    reserva.status = 'Aprovado'
    db.session.commit()
    flash(f'Reserva de {reserva.usuario.username} aprovada!', 'success')
    return redirect(url_for('admin'))

# --- INICIALIZAÇÃO DO BANCO ---

def setup_db():
    db.create_all()
    # Usuário de teste inicial
    if not User.query.filter_by(email='teste@gmail.com').first():
        pw = bcrypt.generate_password_hash('123456').decode('utf-8')
        db.session.add(User(username='Coordenador Teste', email='teste@gmail.com', password=pw))
    
    # Salas iniciais da paróquia
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
