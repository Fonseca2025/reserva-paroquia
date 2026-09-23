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
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user
)
from flask_bcrypt import Bcrypt
from sqlalchemy import inspect, text


# ============================================================
# CONFIGURAÇÃO
# ============================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "chave-temporaria-sao-judas"
)

database_url = os.environ.get(
    "DATABASE_URL",
    "sqlite:///paroquia.db"
)

# Compatibilidade com URLs antigas do Render
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
    id = db.Column(db.Integer, primary_key=True)

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
            return redirect(url_for("index"))

        return f(*args, **kwargs)

    return decorated_function


# ============================================================
# VERIFICAÇÃO DE CONFLITO DE HORÁRIO
# ============================================================

def existe_conflito(
    sala_id,
    data_obj,
    h_inicio,
    h_fim,
    reserva_id=None
):
    reservas = Reserva.query.filter_by(
        sala_id=sala_id,
        data=data_obj
    ).filter(
        Reserva.status.in_(["Pendente", "Aprovado"])
    )

    if reserva_id is not None:
        reservas = reservas.filter(
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

    for reserva in reservas.all():

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
# BANCO DE DADOS
# ============================================================

def atualizar_estrutura_banco():

    inspector = inspect(db.engine)

    tabelas = inspector.get_table_names()

    if "reserva" in tabelas:

        colunas = [
            coluna["name"]
            for coluna in inspector.get_columns("reserva")
        ]

        if "observacao" not in colunas:

            with db.engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE reserva "
                        "ADD COLUMN observacao TEXT"
                    )
                )

            print(
                "Coluna observacao adicionada à tabela reserva."
            )


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

        admin.is_admin = True

        db.session.commit()

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
        "Tabelas verificadas/criadas com sucesso."
    )

    print(
        "Configuração do banco concluída."
    )


# ============================================================
# PÁGINA INICIAL
# ============================================================

@app.route("/")
def index():

    return render_template("index.html")


# ============================================================
# CADASTRO
# ============================================================

@app.route("/cadastro", methods=["GET", "POST"])
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

        usuario = User(
            username=username,
            email=email,
            password=senha_hash,
            is_admin=False
        )

        db.session.add(usuario)
        db.session.commit()

        flash(
            "Cadastro realizado com sucesso.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    return render_template("cadastro.html")


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(
            url_for("index")
        )

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        user = User.query.filter_by(
            email=email
        ).first()

        if user and bcrypt.check_password_hash(
            user.password,
            password
        ):

            login_user(user)

            flash(
                "Login realizado com sucesso.",
                "success"
            )

            return redirect(
                url_for("index")
            )

        flash(
            "E-mail ou senha incorretos.",
            "danger"
        )

    return render_template("login.html")


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
# SOLICITAÇÃO DE RESERVA
# ============================================================

@app.route("/solicitar", methods=["GET"])
@login_required
def solicitar():

    data_str = request.args.get(
        "data",
        ""
    )

    qtd_str = request.args.get(
        "qtd_pessoas",
        ""
    )

    salas = []

    if data_str and qtd_str:

        try:

            data_obj = datetime.strptime(
                data_str,
                "%Y-%m-%d"
            ).date()

            qtd_pessoas = int(qtd_str)

            if data_obj < date.today():

                flash(
                    "Não é possível reservar uma data passada.",
                    "danger"
                )

                return redirect(
                    url_for("solicitar")
                )

            salas_todas = Sala.query.filter(
                Sala.capacidade >= qtd_pessoas
            ).order_by(
                Sala.capacidade.asc()
            ).all()

            salas_adequadas = [
                sala
                for sala in salas_todas
                if sala.capacidade <= qtd_pessoas * 2.5
            ]

            if salas_adequadas:
                salas = salas_adequadas
            else:
                salas = salas_todas

        except ValueError:

            flash(
                "Data ou quantidade de pessoas inválida.",
                "danger"
            )

            return redirect(
                url_for("solicitar")
            )

    return render_template(
        "solicitar.html",
        salas=salas,
        data=data_str,
        qtd_pessoas=qtd_str
    )


# ============================================================
# CONFIRMAÇÃO DA RESERVA
# ============================================================

@app.route("/confirmar", methods=["POST"])
@login_required
def confirmar():

    data_str = request.form.get(
        "data",
        ""
    )

    sala_id_str = request.form.get(
        "sala_id",
        ""
    )

    qtd_str = request.form.get(
        "qtd_pessoas",
        ""
    )

    hora_inicio = request.form.get(
        "hora_inicio",
        ""
    )

    hora_fim = request.form.get(
        "hora_fim",
        ""
    )

    observacao = request.form.get(
        "observacao",
        ""
    ).strip()

    recorrente = request.form.get(
        "recorrente"
    )

    # --------------------------------------------------------
    # VALIDAÇÃO DOS CAMPOS
    # --------------------------------------------------------

    if not all([
        data_str,
        sala_id_str,
        qtd_str,
        hora_inicio,
        hora_fim
    ]):

        flash(
            "Preencha todos os campos obrigatórios.",
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

        sala_id = int(sala_id_str)

        qtd_pessoas = int(qtd_str)

    except ValueError:

        flash(
            "Dados inválidos.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    if data_obj < date.today():

        flash(
            "Não é possível reservar uma data passada.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    # --------------------------------------------------------
    # HORÁRIOS
    # --------------------------------------------------------

    try:

        inicio = datetime.strptime(
            hora_inicio,
            "%H:%M"
        ).time()

        fim = datetime.strptime(
            hora_fim,
            "%H:%M"
        ).time()

        limite_22h = datetime.strptime(
            "22:00",
            "%H:%M"
        ).time()

    except ValueError:

        flash(
            "Horário inválido.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    if inicio >= fim:

        flash(
            "O horário final deve ser posterior ao horário inicial.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    if inicio >= limite_22h:

        flash(
            "As reservas devem começar antes das 22h.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    if fim > limite_22h:

        flash(
            "O funcionamento das salas termina às 22h.",
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
            "A quantidade de pessoas excede a capacidade da sala.",
            "danger"
        )

        return redirect(
            url_for("solicitar")
        )

    # --------------------------------------------------------
    # DATAS DA RESERVA
    # --------------------------------------------------------

    datas_reserva = [data_obj]

    if recorrente:

        data_atual = data_obj

        ultimo_dia = date(
            data_obj.year,
            12,
            31
        )

        while True:

            proxima_data = (
                data_atual
                + timedelta(days=7)
            )

            if proxima_data > ultimo_dia:
                break

            datas_reserva.append(
                proxima_data
            )

            data_atual = proxima_data

    # --------------------------------------------------------
    # VERIFICAÇÃO DE CONFLITOS
    # --------------------------------------------------------

    for data_reserva in datas_reserva:

        if existe_conflito(
            sala_id,
            data_reserva,
            hora_inicio,
            hora_fim
        ):

            flash(
                f"Já existe uma reserva para "
                f"{sala.nome} em "
                f"{data_reserva.strftime('%d/%m/%Y')} "
                f"nesse horário.",
                "danger"
            )

            return redirect(
                url_for(
                    "solicitar",
                    data=data_str,
                    qtd_pessoas=qtd_str
                )
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
            observacao=observacao or None,
            status="Pendente",
            usuario_id=current_user.id,
            sala_id=sala_id
        )

        db.session.add(nova_reserva)

    db.session.commit()

    # --------------------------------------------------------
    # LINK PARA WHATSAPP DA SECRETARIA
    # --------------------------------------------------------

    numero_whatsapp = os.environ.get(
        "WHATSAPP_SECRETARIA",
        "5538999999999"
    )

    mensagem = (
        "Nova solicitação de reserva de sala.\n\n"
        f"Solicitante: {current_user.username}\n"
        f"Data: {data_obj.strftime('%d/%m/%Y')}\n"
        f"Horário: {hora_inicio} às {hora_fim}\n"
        f"Sala: {sala.nome}\n"
        f"Pessoas: {qtd_pessoas}\n"
    )

    if observacao:
        mensagem += (
            f"Observação: {observacao}\n"
        )

    if recorrente:
        mensagem += (
            "Reserva semanal até o final do ano."
        )

    link_whatsapp = (
        "https://wa.me/"
        + numero_whatsapp
        + "?text="
        + quote(mensagem)
    )

    return render_template(
        "confirmacao.html",
        reserva=sala,
        data=data_obj,
        hora_inicio=hora_inicio,
        hora_fim=hora_fim,
        qtd_pessoas=qtd_pessoas,
        observacao=observacao,
        link_whatsapp=link_whatsapp
    )


# ============================================================
# AGENDA DE RESERVAS
# ============================================================

@app.route("/agenda")
@admin_required
def agenda():

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

    consulta = Reserva.query

    if data_filtro:

        consulta = consulta.filter(
            Reserva.data == data_filtro
        )

    reservas = consulta.order_by(
        Reserva.data.asc(),
        Reserva.hora_inicio.asc()
    ).all()

    return render_template(
        "agenda.html",
        reservas=reservas,
        data_filtro=data_str
    )


# ============================================================
# PAINEL ADMINISTRATIVO
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

@app.route("/aprovar/<int:id>")
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

    if reserva.status == "Aprovado":

        flash(
            "Esta reserva já está aprovada.",
            "warning"
        )

        return redirect(
            url_for("admin")
        )

    # Verifica novamente se surgiu conflito
    # antes da aprovação.
    if existe_conflito(
        reserva.sala_id,
        reserva.data,
        reserva.hora_inicio,
        reserva.hora_fim,
        reserva.id
    ):

        flash(
            "Não é possível aprovar esta reserva "
            "porque existe conflito de horário.",
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
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        )
    )
