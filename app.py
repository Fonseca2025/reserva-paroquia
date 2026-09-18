import os
from functools import wraps
from datetime import datetime, timedelta
from urllib.parse import quote

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user
)
from flask_bcrypt import Bcrypt


# ============================================================
# CONFIGURAÇÃO
# ============================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "chave-temporaria-sao-judas"
)

# Utiliza a DATABASE_URL existente no Render.
# Se ela não existir, utiliza SQLite apenas para desenvolvimento local.
database_url = os.environ.get(
    "DATABASE_URL",
    "sqlite:///paroquia.db"
)

# Alguns ambientes fornecem postgres://.
# O SQLAlchemy atual utiliza postgresql://.
if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://",
        "postgresql://",
        1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Faça login para acessar esta página."
login_manager.login_message_category = "warning"


# ============================================================
# MODELOS
# ============================================================

class User(db.Model, UserMixin):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    username = db.Column(
        db.String(100),
        nullable=False
    )

    email = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(200),
        nullable=False
    )

    is_admin = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    reservas = db.relationship(
        "Reserva",
        backref="usuario",
        lazy=True
    )


class Sala(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    nome = db.Column(
        db.String(100),
        nullable=False
    )

    capacidade = db.Column(
        db.Integer,
        nullable=False
    )

    reservas = db.relationship(
        "Reserva",
        backref="sala",
        lazy=True
    )


class Reserva(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    data = db.Column(
        db.Date,
        nullable=False
    )

    hora_inicio = db.Column(
        db.String(5),
        nullable=False
    )

    hora_fim = db.Column(
        db.String(5),
        nullable=False
    )

    qtd_pessoas = db.Column(
        db.Integer,
        nullable=False
    )

    status = db.Column(
        db.String(20),
        default="Pendente",
        nullable=False
    )

    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    sala_id = db.Column(
        db.Integer,
        db.ForeignKey("sala.id"),
        nullable=False
    )


# ============================================================
# LOGIN
# ============================================================

@login_manager.user_loader
def load_user(user_id):

    return db.session.get(
        User,
        int(user_id)
    )


# ============================================================
# PROTEÇÃO ADMINISTRATIVA
# ============================================================

def admin_required(f):

    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):

        if not current_user.is_admin:

            flash(
                "Acesso restrito à administração da paróquia.",
                "danger"
            )

            return redirect(
                url_for("index")
            )

        return f(*args, **kwargs)

    return decorated_function


# ============================================================
# CADASTRO
# ============================================================

@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():

    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        if not username or not email or not password:

            flash(
                "Preencha todos os campos.",
                "danger"
            )

            return redirect(
                url_for("cadastro")
            )

        usuario_existente = User.query.filter_by(
            email=email
        ).first()

        if usuario_existente:

            flash(
                "Este e-mail já está cadastrado.",
                "danger"
            )

            return redirect(
                url_for("cadastro")
            )

        senha_hash = bcrypt.generate_password_hash(
            password
        ).decode("utf-8")

        novo_usuario = User(
            username=username,
            email=email,
            password=senha_hash,
            is_admin=False
        )

        db.session.add(novo_usuario)
        db.session.commit()

        flash(
            "Conta criada com sucesso! Faça seu login.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "cadastro.html"
    )


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        usuario = User.query.filter_by(
            email=email
        ).first()

        if usuario and bcrypt.check_password_hash(
            usuario.password,
            password
        ):

            login_user(usuario)

            return redirect(
                url_for("index")
            )

        flash(
            "E-mail ou senha incorretos.",
            "danger"
        )

    return render_template(
        "login.html"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
@login_required
def logout():

    logout_user()

    flash(
        "Você saiu do sistema.",
        "info"
    )

    return redirect(
        url_for("index")
    )


# ============================================================
# PÁGINA INICIAL
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ============================================================
# SOLICITAR RESERVA
# ============================================================

@app.route("/solicitar", methods=["GET", "POST"])
@login_required
def solicitar():

    salas_disponiveis = None
    data_selecionada = None
    qtd_selecionada = None

    if request.method == "POST":

        data_selecionada = request.form.get(
            "data"
        )

        qtd_str = request.form.get(
            "qtd"
        )

        try:

            qtd_selecionada = int(
                qtd_str
            )

        except (TypeError, ValueError):

            flash(
                "Informe uma quantidade válida de pessoas.",
                "danger"
            )

            return redirect(
                url_for("solicitar")
            )

        if qtd_selecionada <= 0:

            flash(
                "A quantidade de pessoas deve ser maior que zero.",
                "danger"
            )

            return redirect(
                url_for("solicitar")
            )

        try:

            datetime.strptime(
                data_selecionada,
                "%Y-%m-%d"
            )

        except (TypeError, ValueError):

            flash(
                "Informe uma data válida.",
                "danger"
            )

            return redirect(
                url_for("solicitar")
            )

        todas_que_cabem = (
            Sala.query
            .filter(
                Sala.capacidade >= qtd_selecionada
            )
            .order_by(
                Sala.capacidade
            )
            .all()
        )

        salas_adequadas = [
            sala
            for sala in todas_que_cabem
            if sala.capacidade <= qtd_selecionada * 2.5
        ]

        if salas_adequadas:

            salas_disponiveis = salas_adequadas

        else:

            salas_disponiveis = todas_que_cabem

    return render_template(
        "solicitar.html",
        salas=salas_disponiveis,
        data=data_selecionada,
        qtd=qtd_selecionada
    )


# ============================================================
# CONFIRMAR RESERVA
# ============================================================

@app.route("/confirmar", methods=["POST"])
@login_required
def confirmar():

    sala_id = request.form.get(
        "sala_id"
    )

    data_str = request.form.get(
        "data"
    )

    qtd_str = request.form.get(
        "qtd"
    )

    h_inicio = request.form.get(
        "h_inicio"
    )

    h_fim = request.form.get(
        "h_fim"
    )

    recorrente = request.form.get(
        "recorrente"
    )

    sala = db.session.get(
        Sala,
        sala_id
    )

    if not sala:

        flash(
            "A sala selecionada não foi encontrada.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    try:

        data_obj = datetime.strptime(
            data_str,
            "%Y-%m-%d"
        ).date()

    except (TypeError, ValueError):

        flash(
            "A data informada é inválida.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    try:

        qtd = int(
            qtd_str
        )

    except (TypeError, ValueError):

        flash(
            "A quantidade de pessoas é inválida.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    if qtd <= 0:

        flash(
            "A quantidade de pessoas deve ser maior que zero.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    if qtd > sala.capacidade:

        flash(
            "A quantidade de pessoas excede a capacidade da sala.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    if not h_inicio or not h_fim:

        flash(
            "Informe o horário de início e término.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    try:

        inicio = datetime.strptime(
            h_inicio,
            "%H:%M"
        )

        fim = datetime.strptime(
            h_fim,
            "%H:%M"
        )

    except ValueError:

        flash(
            "Informe horários válidos.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    if fim <= inicio:

        flash(
            "O horário de término deve ser posterior ao horário de início.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    def criar_entrada(data_r):

        nova_reserva = Reserva(
            data=data_r,
            hora_inicio=h_inicio,
            hora_fim=h_fim,
            qtd_pessoas=qtd,
            sala_id=sala.id,
            usuario_id=current_user.id,
            status="Pendente"
        )

        db.session.add(
            nova_reserva
        )

    criar_entrada(
        data_obj
    )

    if recorrente == "sim":

        ano_atual = datetime.now().year

        prox_data = data_obj + timedelta(
            days=7
        )

        while prox_data.year == ano_atual:

            criar_entrada(
                prox_data
            )

            prox_data += timedelta(
                days=7
            )

    db.session.commit()

    numero_secretaria = os.environ.get(
        "WHATSAPP_SECRETARIA",
        "5538999999999"
    )

    mensagem = (
        "Olá! Fiz um pré-agendamento no "
        "Sistema de Reservas da Paróquia São Judas Tadeu.\n\n"
        f"Solicitante: {current_user.username}\n"
        f"Data: {data_obj.strftime('%d/%m/%Y')}\n"
        f"Horário: {h_inicio} às {h_fim}\n"
        f"Sala: {sala.nome}\n"
        f"Quantidade de pessoas: {qtd}\n\n"
        "Aguardo a aprovação da Secretaria."
    )

    link_zap = (
        f"https://wa.me/{numero_secretaria}"
        f"?text={quote(mensagem)}"
    )

    flash(
        "Solicitação enviada com sucesso! "
        f"<br><br>"
        f'<a href="{link_zap}" target="_blank" '
        f'class="btn btn-success">'
        "Avisar Secretaria no WhatsApp"
        "</a>",
        "info"
    )

    return redirect(
        url_for("index")
    )


# ============================================================
# PAINEL ADMINISTRATIVO
# ============================================================

@app.route("/admin")
@admin_required
def admin():

    reservas = (
        Reserva.query
        .order_by(
            Reserva.data.asc(),
            Reserva.hora_inicio.asc()
        )
        .all()
    )

    return render_template(
        "admin.html",
        reservas=reservas
    )


# ============================================================
# APROVAR RESERVA
# ============================================================

@app.route(
    "/aprovar/<int:id>",
    methods=["POST"]
)
@admin_required
def aprovar_reserva(id):

    reserva = db.session.get(
        Reserva,
        id
    )

    if not reserva:

        flash(
            "Reserva não encontrada.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    reserva.status = "Aprovado"

    db.session.commit()

    flash(
        f"Reserva de {reserva.usuario.username} aprovada!",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# ============================================================
# PREPARAÇÃO DO BANCO
# ============================================================

def setup_db():

    print("Iniciando configuração do banco de dados...")

    # Cria todas as tabelas que ainda não existem.
    db.create_all()

    print("Tabelas verificadas/criadas com sucesso.")

    # --------------------------------------------------------
    # Administrador inicial
    # --------------------------------------------------------

    admin_email = os.environ.get(
        "ADMIN_EMAIL",
        "teste@gmail.com"
    ).strip().lower()

    admin_password = os.environ.get(
        "ADMIN_PASSWORD",
        "123456"
    )

    admin_user = User.query.filter_by(
        email=admin_email
    ).first()

    if admin_user:

        admin_user.is_admin = True

        print(
            f"Usuário administrador encontrado: {admin_email}"
        )

    else:

        senha_hash = bcrypt.generate_password_hash(
            admin_password
        ).decode("utf-8")

        admin_user = User(
            username="Administrador",
            email=admin_email,
            password=senha_hash,
            is_admin=True
        )

        db.session.add(
            admin_user
        )

        print(
            f"Administrador criado: {admin_email}"
        )

    # --------------------------------------------------------
    # Salas iniciais
    # --------------------------------------------------------

    if not Sala.query.first():

        db.session.add_all([
            Sala(
                nome="Sala Catequese 01",
                capacidade=15
            ),
            Sala(
                nome="Sala Reuniões 02",
                capacidade=35
            ),
            Sala(
                nome="Auditório São Judas",
                capacidade=100
            )
        ])

        print(
            "Salas iniciais cadastradas."
        )

    db.session.commit()

    print(
        "Configuração do banco concluída."
    )


# ============================================================
# INICIALIZAÇÃO
# ============================================================

with app.app_context():

    setup_db()


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )
