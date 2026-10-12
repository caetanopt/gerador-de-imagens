"""
Autenticação por email + código de verificação de 6 dígitos, e gestão de
permissões por marca. Only emails geridos no backoffice (ver
backoffice.py) podem entrar na ferramenta; os emails admin (fixos, abaixo)
podem sempre entrar, mesmo antes de terem uma entrada em
data/authorized_users.json, para poderem aceder ao backoffice e criar o
primeiro utilizador.

Envio do código: pela API do Amazon SES (região eu-west-1), sempre a
partir de "Caetano <info@caetano.pt>" (este remetente tem de estar
verificado no SES). Credenciais lidas de variáveis de ambiente (também de
um ficheiro .env na raiz do projecto, se existir — ver .env.example):
AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY. Enquanto isto não estiver
configurado, o código é mostrado directamente no ecrã de login (com
aviso bem visível), para a ferramenta ficar testável de imediato.
"""
import json
import os
import random
import re
import secrets
import time
from pathlib import Path

import boto3
import streamlit as st
from botocore.exceptions import NoCredentialsError, PartialCredentialsError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SES_REGION = "eu-west-1"
SES_SENDER = "Caetano <info@caetano.pt>"

DATA_DIR = Path(__file__).parent / "data"
USERS_FILE = DATA_DIR / "authorized_users.json"
TOKENS_FILE = DATA_DIR / "login_tokens.json"

REMEMBER_SECONDS = 7 * 24 * 60 * 60  # 1 semana
REMEMBER_QUERY_PARAM = "t"

CAETANO_DOMAIN = "@caetano.pt"
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@caetano\.pt$", re.IGNORECASE)

# Emails admin fixos — só estes veem/gerem o backoffice. Não são editáveis
# pela própria ferramenta (por decisão explícita do utilizador).
ADMIN_EMAILS = {
    "manuel.alves@caetano.pt",
    "diogo.martins@caetano.pt",
    "daniel.gil@caetano.pt",
    "miguel.msantos@caetano.pt",
    "diogo.machado@caetano.pt",
}

CODE_TTL_SECONDS = 600  # 10 minutos


def is_caetano_email(email: str) -> bool:
    return bool(EMAIL_RE.match((email or "").strip()))


def is_admin(email: str) -> bool:
    return (email or "").strip().lower() in ADMIN_EMAILS


# ── Armazenamento de utilizadores autorizados ──────────────────────────────

def load_users() -> list[dict]:
    if not USERS_FILE.exists():
        return []
    with open(USERS_FILE, encoding="utf-8") as f:
        return json.load(f).get("users", [])


def save_users(users: list[dict]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump({"users": users}, f, ensure_ascii=False, indent=2)


def get_user_brands(email: str) -> list[str] | None:
    """Devolve a lista de marcas do utilizador, ou None se não estiver autorizado."""
    email = (email or "").strip().lower()
    for u in load_users():
        if u["email"].strip().lower() == email:
            return u.get("brands", [])
    return None


def upsert_user(email: str, brands: list[str]) -> None:
    email = email.strip().lower()
    users = load_users()
    for u in users:
        if u["email"].strip().lower() == email:
            u["brands"] = brands
            save_users(users)
            return
    users.append({"email": email, "brands": brands})
    save_users(users)


# ── Sessão persistente ("lembrar-me" por 1 semana) ──────────────────────────
# O token vive num parâmetro da URL (?t=...) — sobrevive a um refresh da
# página (a URL mantém-se) sem precisar de cookies nem de bibliotecas
# extra. O token em si não revela nada; só é útil comparado com o registo
# guardado aqui no servidor, que também controla a validade de 1 semana.

def _load_tokens() -> dict:
    if not TOKENS_FILE.exists():
        return {}
    with open(TOKENS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_tokens(tokens: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)


def create_remember_token(email: str) -> str:
    """Cria um token de sessão válido por 1 semana e devolve-o."""
    tokens = _load_tokens()
    now = time.time()
    # aproveita para limpar tokens expirados
    tokens = {t: v for t, v in tokens.items() if v.get("expires_at", 0) > now}
    token = secrets.token_urlsafe(32)
    tokens[token] = {"email": email.strip().lower(), "expires_at": now + REMEMBER_SECONDS}
    _save_tokens(tokens)
    return token


def validate_remember_token(token: str) -> str | None:
    """Devolve o email associado ao token, se ainda for válido."""
    if not token:
        return None
    entry = _load_tokens().get(token)
    if not entry or entry.get("expires_at", 0) < time.time():
        return None
    return entry["email"]


def revoke_remember_token(token: str) -> None:
    tokens = _load_tokens()
    if token in tokens:
        del tokens[token]
        _save_tokens(tokens)


def restore_session():
    """
    Chamado no arranque do script, antes de mostrar o ecrã de login: se a
    URL já tiver um token de sessão válido (?t=...), autentica logo sem
    pedir novo código — é isto que faz a sessão sobreviver a um refresh da
    página durante 1 semana.
    """
    if st.session_state.get("auth_email"):
        return
    token = st.query_params.get(REMEMBER_QUERY_PARAM)
    email = validate_remember_token(token) if token else None
    if email:
        st.session_state.auth_email = email


def logout():
    """Termina a sessão e revoga o token de "lembrar-me" (login seguinte
    volta a pedir código de verificação)."""
    token = st.query_params.get(REMEMBER_QUERY_PARAM)
    if token:
        revoke_remember_token(token)
        del st.query_params[REMEMBER_QUERY_PARAM]
    st.session_state.auth_email = None


def delete_user(email: str) -> None:
    email = email.strip().lower()
    users = [u for u in load_users() if u["email"].strip().lower() != email]
    save_users(users)


def can_login(email: str) -> bool:
    """Admins entram sempre (para poderem gerir o backoffice); os
    restantes só se já estiverem na lista de utilizadores autorizados."""
    if is_admin(email):
        return True
    return get_user_brands(email) is not None


# ── Código de verificação ──────────────────────────────────────────────────

def generate_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def send_email(to_emails: list[str], subject: str, body: str) -> bool:
    """
    Envia um email pela API do Amazon SES (eu-west-1), sempre a partir de
    SES_SENDER. Devolve True se enviado, ou False se não houver
    credenciais AWS configuradas. Lança excepção se as credenciais
    existirem mas o envio falhar (erro real a reportar/tratar pelo
    chamador — ex.: remetente não verificado, conta ainda em sandbox).
    """
    try:
        client = boto3.client("ses", region_name=SES_REGION)
        client.send_email(
            Source=SES_SENDER,
            Destination={"ToAddresses": to_emails},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )
    except (NoCredentialsError, PartialCredentialsError):
        return False
    return True


def send_verification_code(email: str, code: str) -> bool:
    """
    Tenta enviar o código de acesso por email. Devolve True se enviado, ou
    False se não houver credenciais AWS configuradas (o chamador deve
    então mostrar o código no ecrã).
    """
    body = (
        f"O teu código de acesso ao Gerador de Imagens Caetano é: {code}\n\n"
        f"Válido por {CODE_TTL_SECONDS // 60} minutos."
    )
    return send_email([email], "Código de acesso — Gerador de Imagens Caetano", body)


# ── Ecrã de login (Streamlit) ───────────────────────────────────────────────

def _reset_login_state():
    for key in ("pending_email", "pending_code", "pending_expiry"):
        st.session_state.pop(key, None)


def _inject_login_css():
    # Nota: não se força a cor de fundo da página (.stApp) — isso lutava
    # contra o tema claro/escuro/sistema do Streamlit e deixava o texto
    # dos avisos (fora do cartão) ilegível em modo escuro. O cartão em si
    # já é auto-contido (fundo escuro + texto branco definidos
    # explicitamente), por isso fica legível em qualquer tema à mesma.
    st.markdown("""
    <style>
    /* ════════════════════════════════════════════════════════
       CARTÃO DE LOGIN — mesma identidade visual do painel de
       configuração da ferramenta (gradiente azul Caetano).
    ════════════════════════════════════════════════════════ */
    .st-key-login_card {
        background: linear-gradient(165deg, #00408f 0%, #002c59 45%, #001830 100%) !important;
        border-radius: 20px !important;
        padding: 40px 40px 34px !important;
        margin-top: 18px !important;
        box-shadow:
            0 24px 60px rgba(0,20,60,.35),
            inset 0 1px 0 rgba(255,255,255,.22),
            inset 0 -3px 10px rgba(0,0,0,.4) !important;
        border: 1px solid rgba(255,255,255,.14) !important;
    }

    .st-key-login_card h1, .st-key-login_card h2, .st-key-login_card h3,
    .st-key-login_card p, .st-key-login_card label,
    .st-key-login_card [data-testid="stCaptionContainer"],
    .st-key-login_card [data-testid="stMarkdownContainer"] {
        color: white !important;
    }

    .st-key-login_card h2 {
        font-weight: 700 !important;
        letter-spacing: .3px !important;
        text-shadow: 0 2px 6px rgba(0,0,0,.4) !important;
        margin-bottom: 2px !important;
    }

    .st-key-login_card [data-testid="stCaptionContainer"] {
        color: rgba(255,255,255,.75) !important;
        margin-bottom: 18px !important;
    }

    .st-key-login_card hr {
        border-color: rgba(255,255,255,.2) !important;
        margin: 18px 0 !important;
    }

    .st-key-login_card [data-baseweb="input"] > div {
        background-color: rgba(255,255,255,.92) !important;
        border-color: rgba(255,255,255,.32) !important;
        border-radius: 8px !important;
    }

    .st-key-login_card input {
        color: #1a1a1a !important;
    }

    .st-key-login_card input::placeholder {
        color: rgba(0,0,0,.45) !important;
    }

    .st-key-login_card [data-testid="stFormSubmitButton"] > button,
    .st-key-login_card [data-testid="stBaseButton-secondaryFormSubmit"] {
        background: linear-gradient(135deg, #1a6fcf 0%, #0d4fa8 100%) !important;
        color: white !important;
        border: 1px solid rgba(255,255,255,.3) !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        letter-spacing: .4px !important;
        box-shadow: 0 4px 14px rgba(0,0,0,.4), inset 0 1px 0 rgba(255,255,255,.25) !important;
    }

    .st-key-login_card [data-testid="stFormSubmitButton"] > button:hover {
        background: linear-gradient(135deg, #2179db 0%, #1460c0 100%) !important;
        transform: translateY(-1px) !important;
    }
    </style>
    """, unsafe_allow_html=True)


def render_login_screen():
    _inject_login_css()

    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        card = st.container(key="login_card")
        with card:
            st.markdown("## 🔒 Acesso à ferramenta")
            st.caption("Gerador de Imagens Caetano · Viaturas Novas")

            pending_email = st.session_state.get("pending_email")

            if not pending_email:
                with st.form("login_email_form"):
                    email = st.text_input("Email Caetano", placeholder="nome.apelido@caetano.pt")
                    submitted = st.form_submit_button("Enviar código", type="primary", use_container_width=True)
            else:
                st.write(f"Código enviado para **{pending_email}**.")
                with st.form("login_code_form"):
                    code_input = st.text_input("Código de verificação (6 dígitos)", max_chars=6)
                    col1, col2 = st.columns(2)
                    verify = col1.form_submit_button("Verificar", type="primary", use_container_width=True)
                    cancel = col2.form_submit_button("Usar outro email", use_container_width=True)

        # Mensagens de estado ficam fora do cartão escuro (legibilidade
        # das cores próprias de cada tipo de alerta), mas continuam
        # centradas na mesma coluna.
        if not pending_email:
            if submitted:
                email = (email or "").strip().lower()
                if not is_caetano_email(email):
                    st.error("Introduz um email válido do domínio @caetano.pt.")
                elif not can_login(email):
                    st.error("Este email não tem acesso autorizado a esta ferramenta.")
                else:
                    code = generate_code()
                    try:
                        sent = send_verification_code(email, code)
                    except Exception as e:
                        st.error(f"Não foi possível enviar o email: {e}")
                        sent = None
                    if sent is not None:
                        st.session_state.pending_email = email
                        st.session_state.pending_code = code
                        st.session_state.pending_expiry = time.time() + CODE_TTL_SECONDS
                        if sent:
                            st.success(f"Código enviado para {email}.")
                        else:
                            st.warning(
                                "Envio de email não configurado. "
                                f"Código de acesso (modo de teste): **{code}**"
                            )
                        st.rerun()
        else:
            if cancel:
                _reset_login_state()
                st.rerun()
            if verify:
                if time.time() > st.session_state.get("pending_expiry", 0):
                    st.error("O código expirou. Pede um novo código.")
                    _reset_login_state()
                elif (code_input or "").strip() != st.session_state.get("pending_code"):
                    st.error("Código incorrecto.")
                else:
                    st.session_state.auth_email = pending_email
                    st.query_params[REMEMBER_QUERY_PARAM] = create_remember_token(pending_email)
                    _reset_login_state()
                    st.rerun()
