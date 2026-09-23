import os
from functools import wraps
from datetime import datetime, date, timedelta
from urllib.parse import quote

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash
)

from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
    LoginManager
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

# Compatibilidade com URLs antigas do PostgreSQL
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

login_manager.login_message = (
    "Faça login para acessar esta página."
)


# ============================================================
# MODELOS
# ============================================================

class User(UserMixin, db.Model):

    __tablename__ = "user"

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

    __tablename__ = "sala"

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

    __tablename__ = "reserva"

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

    observacao = db.Column(
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

    return db.session.get(
        User,
        int(user_id)
    )


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
        Reserva.status.in_(
            ["Pendente", "Aprovado"]
        ),
        Reserva.hora_inicio < h_fim,
        Reserva.hora_fim > h_inicio
    )

    if reserva_id is not None:

        consulta = consulta.filter(
            Reserva.id != reserva_id
        )

    return consulta.first() is not None


# ============================================================
# ATUALIZAÇÃO DA ESTRUTURA DO BANCO
# ============================================================

def atualizar_estrutura_banco():

    inspector = inspect(
        db.engine
    )

    tabelas = inspector.get_table_names()

    if "reserva" in tabelas:

        colunas = [
            coluna["name"]
            for coluna in inspector.get_columns(
                "reserva"
            )
        ]

        if "observacao" not in colunas:

            with db.engine.begin() as connection:

                connection.execute(
                    text(
                        "ALTER TABLE reserva "
                        "ADD COLUMN observacao TEXT"
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

    else:

        senha_hash = (
            bcrypt
            .generate_password_hash(
                admin_password
            )
            .decode("utf-8")
        )

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

        salas = [

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

        db.session.add_all(salas)

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

        senha_hash = (
            bcrypt
            .generate_password_hash(
                password
            )
            .decode("utf-8")
        )

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
            "Cadastro realizado com sucesso. Faça login.",
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

        if usuario and bcrypt.check_password_hash(
            usuario.password,
            password
        ):

            login_user(
                usuario
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
        "Você saiu do sistema.",
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

    if request.method == "POST":

        data_str = request.form.get(
            "data",
            ""
        ).strip()

        qtd_str = request.form.get(
            "qtd_pessoas",
            ""
        ).strip()

        try:

            data_obj = datetime.strptime(
                data_str,
                "%Y-%m-%d"
            ).date()

            qtd_pessoas = int(
                qtd_str
            )

        except (ValueError, TypeError):

            flash(
                "Informe uma data e quantidade de pessoas válidas.",
                "danger"
            )

            return redirect(
                url_for("solicitar")
            )

        if data_obj < date.today():

            flash(
                "Não é possível solicitar uma reserva para uma data passada.",
                "danger"
            )

            return redirect(
                url_for("solicitar")
            )

        if qtd_pessoas <= 0:

            flash(
                "A quantidade de pessoas deve ser maior que zero.",
                "danger"
            )

            return redirect(
                url_for("solicitar")
            )

        salas = Sala.query.filter(
            Sala.capacidade >= qtd_pessoas
        ).order_by(
            Sala.capacidade.asc()
        ).all()

        return render_template(
            "solicitar.html",
            salas=salas,
            data=data_str,
            qtd_pessoas=qtd_pessoas
        )

    return render_template(
        "solicitar.html",
        salas=[],
        data="",
        qtd_pessoas=""
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
        "hora_inicio",
        ""
    ).strip()

    hora_fim = request.form.get(
        "hora_fim",
        ""
    ).strip()

    qtd_str = request.form.get(
        "qtd_pessoas",
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

    recorrencia = request.form.get(
        "recorrencia",
        ""
    ).strip()

    # --------------------------------------------------------
    # VALIDAÇÕES
    # --------------------------------------------------------

    try:

        data_obj = datetime.strptime(
            data_str,
            "%Y-%m-%d"
        ).date()

        qtd_pessoas = int(
            qtd_str
        )

        sala_id = int(
            sala_id_str
        )

    except (ValueError, TypeError):

        flash(
            "Dados inválidos para a reserva.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    if data_obj < date.today():

        flash(
            "Não é possível reservar uma data passada.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    if qtd_pessoas <= 0:

        flash(
            "A quantidade de pessoas deve ser maior que zero.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

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
            "A quantidade de pessoas excede a capacidade da sala.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    # --------------------------------------------------------
    # VALIDAÇÃO DOS HORÁRIOS
    # --------------------------------------------------------

    try:

        inicio = datetime.strptime(
            hora_inicio,
            "%H:%M"
        )

        fim = datetime.strptime(
            hora_fim,
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

    limite = datetime.strptime(
        "22:00",
        "%H:%M"
    )

    if fim > limite:

        flash(
            "As reservas devem terminar até às 22h.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    # --------------------------------------------------------
    # DATAS DA RESERVA
    # --------------------------------------------------------

    datas_reserva = [
        data_obj
    ]

    if recorrencia == "semanal":

        proxima_data = data_obj + timedelta(
            days=7
        )

        ultimo_dia_ano = date(
            data_obj.year,
            12,
            31
        )

        while proxima_data <= ultimo_dia_ano:

            datas_reserva.append(
                proxima_data
            )

            proxima_data += timedelta(
                days=7
            )

    # --------------------------------------------------------
    # VERIFICA CONFLITOS
    # --------------------------------------------------------

    for data_reserva in datas_reserva:

        if existe_conflito(
            sala.id,
            data_reserva,
            hora_inicio,
            hora_fim
        ):

            data_formatada = (
                data_reserva.strftime(
                    "%d/%m/%Y"
                )
            )

            flash(
                f"Já existe uma reserva para a sala "
                f"{sala.nome} em {data_formatada} "
                f"nesse horário.",
                "danger"
            )

            return redirect(
                url_for("solicitar")
            )

    # --------------------------------------------------------
    # CRIA RESERVAS
    # --------------------------------------------------------

    reservas_criadas = []

    for data_reserva in datas_reserva:

        reserva = Reserva(
            data=data_reserva,
            hora_inicio=hora_inicio,
            hora_fim=hora_fim,
            qtd_pessoas=qtd_pessoas,
            observacao=observacao,
            status="Pendente",
            usuario_id=current_user.id,
            sala_id=sala.id
        )

        db.session.add(
            reserva
        )

        reservas_criadas.append(
            reserva
        )

    db.session.commit()

    # --------------------------------------------------------
    # WHATSAPP
    # --------------------------------------------------------

    whatsapp_numero = os.environ.get(
        "WHATSAPP_SECRETARIA",
        "5538999999999"
    )

    if len(datas_reserva) == 1:

        data_mensagem = (
            datas_reserva[0]
            .strftime("%d/%m/%Y")
        )

    else:

        data_mensagem = (
            f"{datas_reserva[0].strftime('%d/%m/%Y')} "
            f"(e demais datas semanais)"
        )

    mensagem = (
        "Nova solicitação de reserva de sala\n\n"
        f"Solicitante: {current_user.username}\n"
        f"Data: {data_mensagem}\n"
        f"Horário: {hora_inicio} às {hora_fim}\n"
        f"Sala: {sala.nome}\n"
        f"Pessoas: {qtd_pessoas}\n"
    )

    if observacao:

        mensagem += (
            f"Observação: {observacao}\n"
        )

    whatsapp_link = (
        "https://wa.me/"
        + whatsapp_numero
        + "?text="
        + quote(mensagem)
    )

    flash(
        "Solicitação registrada com sucesso.",
        "success"
    )

    return render_template(
        "confirmacao.html",
        reservas=reservas_criadas,
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

            flash(
                "Data inválida.",
                "danger"
            )

            return redirect(
                url_for("agenda")
            )

    # --------------------------------------------------------
    # MÊS DO CALENDÁRIO
    # --------------------------------------------------------

    mes_str = request.args.get(
        "mes",
        ""
    ).strip()

    if mes_str:

        try:

            mes_data = datetime.strptime(
                mes_str,
                "%Y-%m"
            ).date()

        except ValueError:

            mes_data = date.today()

    else:

        mes_data = (
            data_filtro
            if data_filtro
            else date.today()
        )

    # --------------------------------------------------------
    # PRIMEIRO DIA DO MÊS
    # --------------------------------------------------------

    primeiro_dia_mes = date(
        mes_data.year,
        mes_data.month,
        1
    )

    # --------------------------------------------------------
    # MÊS ANTERIOR
    # --------------------------------------------------------

    if mes_data.month == 1:

        mes_anterior = date(
            mes_data.year - 1,
            12,
            1
        )

    else:

        mes_anterior = date(
            mes_data.year,
            mes_data.month - 1,
            1
        )

    # --------------------------------------------------------
    # PRÓXIMO MÊS
    # --------------------------------------------------------

    if mes_data.month == 12:

        proximo_mes = date(
            mes_data.year + 1,
            1,
            1
        )

    else:

        proximo_mes = date(
            mes_data.year,
            mes_data.month + 1,
            1
        )

    # --------------------------------------------------------
    # PRIMEIRO DIA DO PRÓXIMO MÊS
    # --------------------------------------------------------

    if mes_data.month == 12:

        inicio_proximo_mes = date(
            mes_data.year + 1,
            1,
            1
        )

    else:

        inicio_proximo_mes = date(
            mes_data.year,
            mes_data.month + 1,
            1
        )

    # --------------------------------------------------------
    # RESERVAS DO MÊS
    # --------------------------------------------------------

    reservas_mes = Reserva.query.filter(
        Reserva.data >= primeiro_dia_mes,
        Reserva.data < inicio_proximo_mes
    ).order_by(
        Reserva.data.asc(),
        Reserva.hora_inicio.asc()
    ).all()

    # --------------------------------------------------------
    # DIAS COM RESERVA
    # --------------------------------------------------------

    dias_com_reserva = sorted(
        {
            reserva.data.day
            for reserva in reservas_mes
        }
    )

    # --------------------------------------------------------
    # RESERVAS DA LISTA
    # --------------------------------------------------------

    consulta = Reserva.query

    if data_filtro:

        consulta = consulta.filter(
            Reserva.data == data_filtro
        )

    reservas = consulta.order_by(
        Reserva.data.asc(),
        Reserva.hora_inicio.asc()
    ).all()

    # --------------------------------------------------------
    # NOME DO MÊS
    # --------------------------------------------------------

    meses = [
        "",
        "Janeiro",
        "Fevereiro",
        "Março",
        "Abril",
        "Maio",
        "Junho",
        "Julho",
        "Agosto",
        "Setembro",
        "Outubro",
        "Novembro",
        "Dezembro"
    ]

    nome_mes = (
        f"{meses[mes_data.month]} "
        f"{mes_data.year}"
    )

    # --------------------------------------------------------
    # ENVIA OS DADOS PARA O TEMPLATE
    # --------------------------------------------------------

    return render_template(
        "agenda.html",
        reservas=reservas,
        data_filtro=data_str,

        mes_atual=mes_data.strftime(
            "%Y-%m"
        ),

        nome_mes=nome_mes,

        mes_anterior=mes_anterior.strftime(
            "%Y-%m"
        ),

        proximo_mes=proximo_mes.strftime(
            "%Y-%m"
        ),

        dias_com_reserva=dias_com_reserva,

        mes_numero=mes_data.month,

        ano=mes_data.year,

        primeiro_dia_mes=primeiro_dia_mes
    )


# ============================================================
# PAINEL ADMINISTRATIVO
# ============================================================

@app.route("/admin")
@admin_required
def admin():

    reservas_pendentes = Reserva.query.filter_by(
        status="Pendente"
    ).order_by(
        Reserva.data.asc(),
        Reserva.hora_inicio.asc()
    ).all()

    return render_template(
        "admin.html",
        reservas=reservas_pendentes
    )


# ============================================================
# APROVAR RESERVA
# ============================================================

@app.route(
    "/aprovar/<int:id>",
    methods=["POST", "GET"]
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
            "Esta reserva não está pendente.",
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
            "Não foi possível aprovar: "
            "existe outra reserva conflitante para esta sala e horário.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    reserva.status = "Aprovado"

    db.session.commit()

    flash(
        "Reserva aprovada com sucesso.",
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
        debug=True
    )
