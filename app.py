import os
from functools import wraps
from datetime import datetime, date, timedelta
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
from sqlalchemy import inspect, text


app = Flask(__name__)

# ============================================================
# CONFIGURAÇÕES
# ============================================================

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "chave-temporaria-sao-judas"
)

database_url = os.environ.get(
    "DATABASE_URL",
    "sqlite:///paroquia.db"
)

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


# ============================================================
# MODELOS
# ============================================================

class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    reservas = db.relationship(
        "Reserva",
        backref="usuario",
        lazy=True
    )


class Sala(db.Model):
    __tablename__ = "sala"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    capacidade = db.Column(db.Integer, nullable=False)

    reservas = db.relationship(
        "Reserva",
        backref="sala",
        lazy=True
    )


class Reserva(db.Model):
    __tablename__ = "reserva"

    id = db.Column(db.Integer, primary_key=True)

    data = db.Column(db.Date, nullable=False)

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

    observacao = db.Column(
        db.Text,
        nullable=True
    )

    motivo_reprovacao = db.Column(
        db.Text,
        nullable=True
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
    return db.session.get(User, int(user_id))


# ============================================================
# PROTEÇÃO DE ADMINISTRADOR
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
# VERIFICAÇÃO DE CONFLITOS
# ============================================================

def existe_conflito(
    sala_id,
    data_obj,
    h_inicio,
    h_fim,
    reserva_id=None
):

    consulta = Reserva.query.filter(
        Reserva.sala_id == sala_id,
        Reserva.data == data_obj,
        Reserva.status.in_(["Pendente", "Aprovado"])
    )

    if reserva_id is not None:

        consulta = consulta.filter(
            Reserva.id != reserva_id
        )

    inicio_novo = datetime.strptime(
        h_inicio,
        "%H:%M"
    ).time()

    fim_novo = datetime.strptime(
        h_fim,
        "%H:%M"
    ).time()

    for reserva in consulta.all():

        inicio_existente = datetime.strptime(
            reserva.hora_inicio,
            "%H:%M"
        ).time()

        fim_existente = datetime.strptime(
            reserva.hora_fim,
            "%H:%M"
        ).time()

        if (
            inicio_existente < fim_novo
            and fim_existente > inicio_novo
        ):

            return True

    return False


# ============================================================
# ATUALIZAÇÃO DA ESTRUTURA DO BANCO
# ============================================================

def atualizar_estrutura_banco():

    inspector = inspect(db.engine)

    tabelas = inspector.get_table_names()

    if "reserva" not in tabelas:
        return

    colunas_reserva = [
        coluna["name"]
        for coluna in inspector.get_columns("reserva")
    ]

    # --------------------------------------------------------
    # OBSERVAÇÃO
    # --------------------------------------------------------

    if "observacao" not in colunas_reserva:

        print(
            "Adicionando coluna 'observacao' à tabela reserva..."
        )

        with db.engine.begin() as conexao:

            conexao.execute(
                text(
                    "ALTER TABLE reserva "
                    "ADD COLUMN observacao TEXT"
                )
            )

    # --------------------------------------------------------
    # MOTIVO DA REPROVAÇÃO
    # --------------------------------------------------------

    inspector = inspect(db.engine)

    colunas_reserva = [
        coluna["name"]
        for coluna in inspector.get_columns("reserva")
    ]

    if "motivo_reprovacao" not in colunas_reserva:

        print(
            "Adicionando coluna "
            "'motivo_reprovacao' à tabela reserva..."
        )

        with db.engine.begin() as conexao:

            conexao.execute(
                text(
                    "ALTER TABLE reserva "
                    "ADD COLUMN motivo_reprovacao TEXT"
                )
            )


# ============================================================
# CONFIGURAÇÃO INICIAL DO BANCO
# ============================================================

def setup_db():

    print(
        "Iniciando configuração do banco de dados..."
    )

    db.create_all()

    atualizar_estrutura_banco()

    # --------------------------------------------------------
    # ADMINISTRADOR
    # --------------------------------------------------------

    admin_email = os.environ.get(
        "ADMIN_EMAIL",
        "teste@gmail.com"
    )

    admin_password = os.environ.get(
        "ADMIN_PASSWORD",
        "123456"
    )

    admin = User.query.filter_by(
        email=admin_email
    ).first()

    if admin:

        if not admin.is_admin:

            admin.is_admin = True

            db.session.commit()

            print(
                f"Administrador atualizado: {admin_email}"
            )

    else:

        senha_hash = bcrypt.generate_password_hash(
            admin_password
        ).decode("utf-8")

        admin = User(
            username="Administrador",
            email=admin_email,
            password=senha_hash,
            is_admin=True
        )

        db.session.add(admin)

        db.session.commit()

        print(
            f"Administrador criado: {admin_email}"
        )

    # --------------------------------------------------------
    # SALAS
    # --------------------------------------------------------

    if Sala.query.count() == 0:

        salas_iniciais = [

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

        ]

        db.session.add_all(
            salas_iniciais
        )

        db.session.commit()

        print(
            "Salas iniciais cadastradas."
        )

    print(
        "Configuração do banco concluída."
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
# CADASTRO
# ============================================================

@app.route(
    "/cadastro",
    methods=["GET", "POST"]
)
def cadastro():

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

        db.session.add(
            novo_usuario
        )

        db.session.commit()

        flash(
            "Cadastro realizado com sucesso.",
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

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

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

        if (
            usuario
            and bcrypt.check_password_hash(
                usuario.password,
                password
            )
        ):

            login_user(usuario)

            flash(
                "Login realizado com sucesso.",
                "success"
            )

            if usuario.is_admin:

                return redirect(
                    url_for("admin")
                )

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
        "Você saiu da sua conta.",
        "success"
    )

    return redirect(
        url_for("index")
    )


# ============================================================
# SOLICITAR RESERVA
# ============================================================

@app.route(
    "/solicitar",
    methods=["GET", "POST"]
)
@login_required
def solicitar():

    salas = []

    data = ""
    qtd = ""

    # --------------------------------------------------------
    # PRIMEIRA ABERTURA DA PÁGINA
    # --------------------------------------------------------

    if request.method == "GET":

        return render_template(
            "solicitar.html",
            salas=salas,
            data=data,
            qtd=qtd
        )

    # --------------------------------------------------------
    # CONSULTA DE SALAS
    # --------------------------------------------------------

    data = request.form.get(
        "data",
        ""
    ).strip()

    qtd_str = request.form.get(
        "qtd",
        ""
    ).strip()

    if not data or not qtd_str:

        flash(
            "Informe a data e a quantidade de pessoas.",
            "danger"
        )

        return render_template(
            "solicitar.html",
            salas=[],
            data=data,
            qtd=qtd_str
        )

    try:

        qtd = int(qtd_str)

    except ValueError:

        flash(
            "Informe uma quantidade de pessoas válida.",
            "danger"
        )

        return render_template(
            "solicitar.html",
            salas=[],
            data=data,
            qtd=qtd_str
        )

    if qtd <= 0:

        flash(
            "A quantidade de pessoas deve ser maior que zero.",
            "danger"
        )

        return render_template(
            "solicitar.html",
            salas=[],
            data=data,
            qtd=qtd
        )

    # --------------------------------------------------------
    # VALIDAÇÃO DA DATA
    # --------------------------------------------------------

    try:

        data_obj = datetime.strptime(
            data,
            "%Y-%m-%d"
        ).date()

    except ValueError:

        flash(
            "Informe uma data válida.",
            "danger"
        )

        return render_template(
            "solicitar.html",
            salas=[],
            data=data,
            qtd=qtd
        )

    if data_obj < date.today():

        flash(
            "Não é possível solicitar uma reserva para uma data passada.",
            "danger"
        )

        return render_template(
            "solicitar.html",
            salas=[],
            data=data,
            qtd=qtd
        )

    # --------------------------------------------------------
    # SALAS COMPATÍVEIS COM A QUANTIDADE
    # --------------------------------------------------------

    salas = Sala.query.filter(
        Sala.capacidade >= qtd
    ).order_by(
        Sala.capacidade.asc(),
        Sala.nome.asc()
    ).all()

    if not salas:

        flash(
            "Não existe uma sala com capacidade suficiente "
            "para a quantidade de pessoas informada.",
            "warning"
        )

    return render_template(
        "solicitar.html",
        salas=salas,
        data=data,
        qtd=qtd
    )


# ============================================================
# CONFIRMAR RESERVA
# ============================================================

@app.route(
    "/confirmar",
    methods=["POST"]
)
@login_required
def confirmar():

    data_str = request.form.get(
        "data",
        ""
    ).strip()

    hora_inicio = request.form.get(
        "h_inicio",
        ""
    ).strip()

    hora_fim = request.form.get(
        "h_fim",
        ""
    ).strip()

    qtd_pessoas_str = request.form.get(
        "qtd",
        ""
    ).strip()

    sala_id_str = request.form.get(
        "sala_id",
        ""
    ).strip()

    observacao = request.form.get(
        "observacao",
        ""
    ).strip()

    recorrente = request.form.get(
        "recorrente"
    )

    # --------------------------------------------------------
    # CAMPOS OBRIGATÓRIOS
    # --------------------------------------------------------

    if not all([
        data_str,
        hora_inicio,
        hora_fim,
        qtd_pessoas_str,
        sala_id_str
    ]):

        flash(
            "Preencha todos os campos obrigatórios.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    # --------------------------------------------------------
    # CONVERSÃO DOS DADOS
    # --------------------------------------------------------

    try:

        data_inicial = datetime.strptime(
            data_str,
            "%Y-%m-%d"
        ).date()

        qtd_pessoas = int(
            qtd_pessoas_str
        )

        sala_id = int(
            sala_id_str
        )

        inicio = datetime.strptime(
            hora_inicio,
            "%H:%M"
        ).time()

        fim = datetime.strptime(
            hora_fim,
            "%H:%M"
        ).time()

    except ValueError:

        flash(
            "Informe os dados em formato válido.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    if data_inicial < date.today():

        flash(
            "Não é possível solicitar uma reserva para uma data passada.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    # --------------------------------------------------------
    # QUANTIDADE
    # --------------------------------------------------------

    if qtd_pessoas <= 0:

        flash(
            "A quantidade de pessoas deve ser maior que zero.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    # --------------------------------------------------------
    # HORÁRIO
    # --------------------------------------------------------

    if fim <= inicio:

        flash(
            "O horário de término deve ser posterior ao horário de início.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    # --------------------------------------------------------
    # LIMITE DE 22H
    # --------------------------------------------------------

    limite_22h = datetime.strptime(
        "22:00",
        "%H:%M"
    ).time()

    if fim > limite_22h:

        flash(
            "As reservas devem terminar até as 22h.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    # --------------------------------------------------------
    # SALA
    # --------------------------------------------------------

    sala = db.session.get(
        Sala,
        sala_id
    )

    if not sala:

        flash(
            "Sala não encontrada.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    if qtd_pessoas > sala.capacidade:

        flash(
            f"A sala selecionada comporta no máximo "
            f"{sala.capacidade} pessoas.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    # --------------------------------------------------------
    # DATAS
    # --------------------------------------------------------

    datas_reserva = [
        data_inicial
    ]

    if recorrente:

        data_atual = data_inicial + timedelta(
            days=7
        )

        while data_atual.year == data_inicial.year:

            datas_reserva.append(
                data_atual
            )

            data_atual += timedelta(
                days=7
            )

    # --------------------------------------------------------
    # VERIFICAÇÃO DE CONFLITOS
    # --------------------------------------------------------

    for data_reserva in datas_reserva:

        if existe_conflito(
            sala.id,
            data_reserva,
            hora_inicio,
            hora_fim
        ):

            data_formatada = data_reserva.strftime(
                "%d/%m/%Y"
            )

            flash(
                f"Já existe uma reserva para "
                f"{sala.nome} em {data_formatada} "
                f"nesse horário.",
                "danger"
            )

            return redirect(
                url_for("solicitar")
            )

    # --------------------------------------------------------
    # CRIAÇÃO DAS RESERVAS
    # --------------------------------------------------------

    for data_reserva in datas_reserva:

        nova_reserva = Reserva(
            data=data_reserva,
            hora_inicio=hora_inicio,
            hora_fim=hora_fim,
            qtd_pessoas=qtd_pessoas,
            observacao=observacao,
            motivo_reprovacao=None,
            status="Pendente",
            usuario_id=current_user.id,
            sala_id=sala.id
        )

        db.session.add(
            nova_reserva
        )

    db.session.commit()

    # --------------------------------------------------------
    # WHATSAPP
    # --------------------------------------------------------

    numero_whatsapp = os.environ.get(
        "WHATSAPP_SECRETARIA",
        "5538999999999"
    )

    mensagem = (
        "Nova solicitação de reserva de sala.\n\n"
        f"Solicitante: {current_user.username}\n"
        f"Sala: {sala.nome}\n"
        f"Data inicial: {data_inicial.strftime('%d/%m/%Y')}\n"
        f"Horário: {hora_inicio} às {hora_fim}\n"
        f"Pessoas: {qtd_pessoas}\n"
    )

    if recorrente:

        mensagem += (
            "Reserva recorrente: semanal\n"
        )

    if observacao:

        mensagem += (
            f"Observação: {observacao}\n"
        )

    mensagem += (
        "\nA solicitação aguarda análise da administração."
    )

    whatsapp_link = (
        "https://wa.me/"
        + numero_whatsapp
        + "?text="
        + quote(mensagem)
    )

    flash(
        "Solicitação enviada com sucesso.",
        "success"
    )

    return render_template(
        "confirmar.html",
        whatsapp_link=whatsapp_link
    )


# ============================================================
# AGENDA
# ============================================================

@app.route("/agenda")
@admin_required
def agenda():

    # --------------------------------------------------------
    # FILTRO POR DATA
    # --------------------------------------------------------

    data_str = request.args.get(
        "data",
        ""
    ).strip()

    data_filtro = None

    if data_str:

        try:

            data_filtro = datetime.strptime(
                data_str,
                "%Y-%m-%d"
            ).date()

        except ValueError:

            data_filtro = None

    # --------------------------------------------------------
    # FILTRO POR SALA
    # --------------------------------------------------------

    sala_id_str = request.args.get(
        "sala_id",
        ""
    ).strip()

    sala_filtro = None
    sala_id_filtro = None

    if sala_id_str:

        try:

            sala_id_filtro = int(
                sala_id_str
            )

            sala_filtro = db.session.get(
                Sala,
                sala_id_filtro
            )

        except ValueError:

            sala_id_filtro = None
            sala_filtro = None

    # --------------------------------------------------------
    # SALAS
    # --------------------------------------------------------

    salas = Sala.query.order_by(
        Sala.nome.asc()
    ).all()

    # --------------------------------------------------------
    # MÊS
    # --------------------------------------------------------

    hoje = date.today()

    mes_str = request.args.get(
        "mes",
        ""
    ).strip()

    try:

        if mes_str:

            primeiro_dia_mes = datetime.strptime(
                mes_str + "-01",
                "%Y-%m-%d"
            ).date()

        else:

            primeiro_dia_mes = hoje.replace(
                day=1
            )

    except ValueError:

        primeiro_dia_mes = hoje.replace(
            day=1
        )

    # --------------------------------------------------------
    # MÊS ANTERIOR
    # --------------------------------------------------------

    if primeiro_dia_mes.month == 1:

        mes_anterior = primeiro_dia_mes.replace(
            year=primeiro_dia_mes.year - 1,
            month=12,
            day=1
        )

    else:

        mes_anterior = primeiro_dia_mes.replace(
            month=primeiro_dia_mes.month - 1,
            day=1
        )

    # --------------------------------------------------------
    # PRÓXIMO MÊS
    # --------------------------------------------------------

    if primeiro_dia_mes.month == 12:

        proximo_mes = primeiro_dia_mes.replace(
            year=primeiro_dia_mes.year + 1,
            month=1,
            day=1
        )

    else:

        proximo_mes = primeiro_dia_mes.replace(
            month=primeiro_dia_mes.month + 1,
            day=1
        )

    # --------------------------------------------------------
    # RESERVAS DO MÊS
    # --------------------------------------------------------

    consulta_mes = Reserva.query.filter(
        Reserva.data >= primeiro_dia_mes,
        Reserva.data < proximo_mes
    )

    if sala_filtro:

        consulta_mes = consulta_mes.filter(
            Reserva.sala_id == sala_filtro.id
        )

    reservas_mes = consulta_mes.order_by(
        Reserva.data.asc(),
        Reserva.hora_inicio.asc()
    ).all()

    dias_com_reserva = {
        reserva.data.day
        for reserva in reservas_mes
    }

    # --------------------------------------------------------
    # RESERVAS DA TABELA
    # --------------------------------------------------------

    consulta = Reserva.query

    if data_filtro:

        consulta = consulta.filter(
            Reserva.data == data_filtro
        )

    else:

        consulta = consulta.filter(
            Reserva.data >= primeiro_dia_mes,
            Reserva.data < proximo_mes
        )

    if sala_filtro:

        consulta = consulta.filter(
            Reserva.sala_id == sala_filtro.id
        )

    reservas = consulta.order_by(
        Reserva.data.asc(),
        Reserva.hora_inicio.asc()
    ).all()

    return render_template(
        "agenda.html",
        reservas=reservas,
        salas=salas,
        sala_filtro=sala_filtro,
        sala_id_filtro=sala_id_filtro,
        data_filtro=data_filtro,
        primeiro_dia_mes=primeiro_dia_mes,
        mes_anterior=mes_anterior,
        proximo_mes=proximo_mes,
        dias_com_reserva=dias_com_reserva
    )


# ============================================================
# ADMINISTRAÇÃO
# ============================================================

@app.route("/admin")
@admin_required
def admin():

    reservas = Reserva.query.order_by(
        Reserva.data.asc(),
        Reserva.hora_inicio.asc()
    ).all()

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
def aprovar(id):

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

    if reserva.status != "Pendente":

        flash(
            "Somente reservas pendentes podem ser aprovadas.",
            "warning"
        )

        return redirect(
            url_for("admin")
        )

    if existe_conflito(
        reserva.sala_id,
        reserva.data,
        reserva.hora_inicio,
        reserva.hora_fim,
        reserva.id
    ):

        flash(
            "Não foi possível aprovar esta reserva porque "
            "existe conflito de horário com outra reserva "
            "pendente ou aprovada.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    reserva.status = "Aprovado"

    reserva.motivo_reprovacao = None

    db.session.commit()

    flash(
        "Reserva aprovada com sucesso.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# ============================================================
# REPROVAR RESERVA
# ============================================================

@app.route(
    "/reprovar/<int:id>",
    methods=["POST"]
)
@admin_required
def reprovar(id):

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

    if reserva.status != "Pendente":

        flash(
            "Somente reservas pendentes podem ser reprovadas.",
            "warning"
        )

        return redirect(
            url_for("admin")
        )

    motivo = request.form.get(
        "motivo_reprovacao",
        ""
    ).strip()

    if not motivo:

        flash(
            "Informe o motivo da reprovação.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    reserva.status = "Reprovado"

    reserva.motivo_reprovacao = motivo

    db.session.commit()

    flash(
        "Reserva reprovada com sucesso.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# ============================================================
# INICIALIZAÇÃO DO BANCO
# ============================================================

with app.app_context():

    setup_db()


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=False
    )
