"""
Backoffice — gestão de utilizadores autorizados e das marcas a que cada
um tem acesso. Só acessível a emails admin (ver auth.ADMIN_EMAILS).
"""
import streamlit as st

import auth
from brands_config import BRANDS

_BRAND_NAMES = list(BRANDS.keys())
_BRAND_KEY_TO_NAME = {v: k for k, v in BRANDS.items()}


def _brand_keys_to_names(keys: list[str]) -> list[str]:
    return [_BRAND_KEY_TO_NAME[k] for k in keys if k in _BRAND_KEY_TO_NAME]


def _inject_backoffice_css():
    st.markdown("""
    <style>
    /* ════════════════════════════════════════════════════════
       PAINEL DO BACKOFFICE — mesma identidade visual do ecrã de
       login (gradiente azul Caetano).
    ════════════════════════════════════════════════════════ */
    .st-key-bo_panel {
        background: linear-gradient(165deg, #00408f 0%, #002c59 45%, #001830 100%) !important;
        border-radius: 20px !important;
        padding: 36px 40px 30px !important;
        margin-bottom: 24px !important;
        box-shadow:
            0 24px 60px rgba(0,20,60,.35),
            inset 0 1px 0 rgba(255,255,255,.22),
            inset 0 -3px 10px rgba(0,0,0,.4) !important;
        border: 1px solid rgba(255,255,255,.14) !important;
    }

    .st-key-bo_panel h1, .st-key-bo_panel h2, .st-key-bo_panel h3, .st-key-bo_panel h4,
    .st-key-bo_panel p, .st-key-bo_panel label,
    .st-key-bo_panel [data-testid="stCaptionContainer"],
    .st-key-bo_panel [data-testid="stMarkdownContainer"] {
        color: white !important;
    }

    .st-key-bo_panel h2 {
        font-weight: 700 !important;
        letter-spacing: .3px !important;
        text-shadow: 0 2px 6px rgba(0,0,0,.4) !important;
        margin-bottom: 2px !important;
    }

    .st-key-bo_panel [data-testid="stCaptionContainer"] {
        color: rgba(255,255,255,.75) !important;
        margin-bottom: 8px !important;
    }

    .st-key-bo_panel hr {
        border-color: rgba(255,255,255,.2) !important;
        margin: 18px 0 !important;
    }

    .st-key-bo_panel [data-baseweb="input"] > div {
        background-color: rgba(255,255,255,.92) !important;
        border-color: rgba(255,255,255,.32) !important;
        border-radius: 8px !important;
    }

    .st-key-bo_panel input {
        color: #1a1a1a !important;
    }

    .st-key-bo_panel input::placeholder {
        color: rgba(0,0,0,.45) !important;
    }

    .st-key-bo_panel [data-baseweb="select"] > div {
        background-color: rgba(255,255,255,.12) !important;
        border-color: rgba(255,255,255,.32) !important;
        border-radius: 8px !important;
    }

    .st-key-bo_panel [data-baseweb="select"] span {
        color: white !important;
    }

    .st-key-bo_panel [data-baseweb="tag"] {
        background-color: rgba(255,255,255,.18) !important;
    }

    .st-key-bo_panel [data-testid="stFormSubmitButton"] > button {
        background: linear-gradient(135deg, #1a6fcf 0%, #0d4fa8 100%) !important;
        color: white !important;
        border: 1px solid rgba(255,255,255,.3) !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        letter-spacing: .4px !important;
        box-shadow: 0 4px 14px rgba(0,0,0,.4), inset 0 1px 0 rgba(255,255,255,.25) !important;
    }

    .st-key-bo_panel [data-testid="stFormSubmitButton"] > button:hover {
        background: linear-gradient(135deg, #2179db 0%, #1460c0 100%) !important;
        transform: translateY(-1px) !important;
    }

    /* Popup do multiselect — texto escuro sobre fundo branco. */
    [data-baseweb="popover"] *, [data-baseweb="menu"] *,
    [role="option"], [role="option"] *,
    ul[data-baseweb] li, ul[data-baseweb] li * {
        color: #1a1a1a !important;
        background-color: white !important;
    }
    </style>
    """, unsafe_allow_html=True)


def render():
    _inject_backoffice_css()

    editing_email = st.session_state.get("bo_editing_email")
    editing_user = None
    if editing_email:
        brands = auth.get_user_brands(editing_email)
        if brands is not None:
            editing_user = {"email": editing_email, "brands": brands}

    with st.container(key="bo_panel"):
        st.markdown("## 🔧 Backoffice — Acessos")
        st.caption("Gestão de utilizadores autorizados e marcas visíveis para cada um.")
        st.divider()
        st.markdown(f"#### {'Adicionar / editar utilizador' if not editing_user else f'A editar: {editing_email}'}")
        with st.form("bo_user_form", clear_on_submit=not editing_user):
            email = st.text_input(
                "Email Caetano",
                value=editing_user["email"] if editing_user else "",
                placeholder="nome.apelido@caetano.pt",
                disabled=bool(editing_user),
            )
            default_names = _brand_keys_to_names(editing_user["brands"]) if editing_user else []
            selected_names = st.multiselect("Marcas com acesso", _BRAND_NAMES, default=default_names)
            col1, col2 = st.columns(2)
            submitted = col1.form_submit_button("Guardar", type="primary", use_container_width=True)
            cancel_edit = col2.form_submit_button("Cancelar edição", use_container_width=True) if editing_user else False

    if cancel_edit:
        st.session_state.pop("bo_editing_email", None)
        st.rerun()

    if submitted:
        email_clean = email.strip().lower()
        if not auth.is_caetano_email(email_clean):
            st.error("Introduz um email válido do domínio @caetano.pt.")
        elif not selected_names:
            st.error("Selecciona pelo menos uma marca.")
        else:
            brand_keys = [BRANDS[n] for n in selected_names]
            auth.upsert_user(email_clean, brand_keys)
            st.session_state.pop("bo_editing_email", None)
            st.success(f"Utilizador {email_clean} guardado.")
            st.rerun()

    st.divider()
    st.subheader("Utilizadores autorizados")
    users = auth.load_users()
    if not users:
        st.info("Ainda não há nenhum utilizador autorizado.")
        return

    confirm_email = st.session_state.get("bo_confirm_delete")

    for u in sorted(users, key=lambda x: x["email"]):
        email = u["email"]
        brand_names = ", ".join(_brand_keys_to_names(u.get("brands", []))) or "—"
        col_info, col_edit, col_del = st.columns([6, 1, 1])
        col_info.markdown(f"**{email}**  \n{brand_names}")
        if col_edit.button("Editar", key=f"edit_{email}", use_container_width=True):
            st.session_state.bo_editing_email = email
            st.rerun()
        if col_del.button("Apagar", key=f"del_{email}", use_container_width=True):
            st.session_state.bo_confirm_delete = email
            st.rerun()

        if confirm_email == email:
            st.warning(f"Confirmas apagar o acesso de **{email}**?")
            c1, c2 = st.columns(2)
            if c1.button("Sim, apagar", key=f"confirm_del_{email}", type="primary", use_container_width=True):
                auth.delete_user(email)
                st.session_state.pop("bo_confirm_delete", None)
                st.rerun()
            if c2.button("Cancelar", key=f"cancel_del_{email}", use_container_width=True):
                st.session_state.pop("bo_confirm_delete", None)
                st.rerun()
