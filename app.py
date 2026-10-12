"""
Gerador de Imagens — Veículos Novos — Caetano
Interface para gerar 4 imagens de carros em diferentes ângulos.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import streamlit as st
from scraper.vw_catalog import load_catalog as vw_load_catalog, get_image_urls
from scraper.vw_images import generate_images as vw_generate_images, images_to_zip as vw_images_to_zip
from scraper.peugeot_catalog import load_catalog as peugeot_load_catalog
from scraper.peugeot_images import generate_images as peugeot_generate_images, images_to_zip as peugeot_images_to_zip
from scraper.renault_catalog import load_catalog as renault_load_catalog, get_wheels_for_color, get_upholsteries_for
from scraper.renault_images import generate_images as renault_generate_images, images_to_zip as renault_images_to_zip
from scraper.dacia_catalog import load_catalog as dacia_load_catalog
from scraper.dacia_images import generate_images as dacia_generate_images, images_to_zip as dacia_images_to_zip
from scraper.opel_catalog import load_catalog as opel_load_catalog
from scraper.opel_images import generate_images as opel_generate_images, images_to_zip as opel_images_to_zip
from scraper.zeekr_catalog import load_catalog as zeekr_load_catalog
from scraper.zeekr_images import generate_images as zeekr_generate_images, images_to_zip as zeekr_images_to_zip
from scraper.byd_catalog import load_catalog as byd_load_catalog
from scraper.byd_images import generate_images as byd_generate_images, images_to_zip as byd_images_to_zip
from scraper.audi_catalog import load_catalog as audi_load_catalog
from scraper.audi_images import generate_images as audi_generate_images, images_to_zip as audi_images_to_zip
from scraper.bmw_catalog import load_catalog as bmw_load_catalog
from scraper.bmw_images import generate_images as bmw_generate_images, images_to_zip as bmw_images_to_zip
from scraper.hyundai_catalog import load_catalog as hyundai_load_catalog
from scraper.hyundai_images import generate_images as hyundai_generate_images, images_to_zip as hyundai_images_to_zip
from scraper.mercedes_catalog import load_catalog as mercedes_load_catalog
from scraper.mercedes_images import generate_images as mercedes_generate_images, images_to_zip as mercedes_images_to_zip
from scraper.mini_catalog import load_catalog as mini_load_catalog
from scraper.mini_images import generate_images as mini_generate_images, images_to_zip as mini_images_to_zip
from scraper.nissan_catalog import load_catalog as nissan_load_catalog
from scraper.nissan_images import generate_images as nissan_generate_images, images_to_zip as nissan_images_to_zip
from scraper.skoda_catalog import load_catalog as skoda_load_catalog
from scraper.skoda_images import generate_images as skoda_generate_images, images_to_zip as skoda_images_to_zip
from scraper.geely_catalog import load_catalog as geely_load_catalog
from scraper.geely_images import generate_images as geely_generate_images, images_to_zip as geely_images_to_zip
from scraper.alpine_catalog import load_catalog as alpine_load_catalog
from scraper.alpine_images import generate_images as alpine_generate_images, images_to_zip as alpine_images_to_zip
from scraper.xpeng_catalog import load_catalog as xpeng_load_catalog
from scraper.xpeng_images import generate_images as xpeng_generate_images, images_to_zip as xpeng_images_to_zip
from scraper.composite import composite, has_template, standardize_only
from scraper.cardb_interiors import for_exterior as cardb_for_exterior
import auth
from brands_config import BRANDS as ALL_BRANDS

st.set_page_config(
    page_title="Gerador de Imagens Caetano - Viaturas Novas",
    page_icon="🚗",
    layout="wide",
)

# ── Logos (pasta logos-caetano) ───────────────────────────────────────────────
_LOGOS_DIR = Path(__file__).parent / "logos-caetano"

# chave interna da marca -> nome do ficheiro em logos-caetano/svg
_BRAND_LOGO_FILES = {"vw": "volkswagen", "mercedes": "mercedes-benz"}


@st.cache_resource
def _caetano_logo_b64() -> str | None:
    """Wordmark Caetano (versão branca, com alfa) reduzida — usada como
    máscara CSS, por isso a cor final é definida no CSS."""
    import io
    from PIL import Image
    path = _LOGOS_DIR / "png" / "caetano-branco.png"
    if not path.exists():
        return None
    im = Image.open(path)
    im.thumbnail((900, 160))
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


@st.cache_resource
def _brand_logo_b64(brand_key: str) -> str | None:
    path = _LOGOS_DIR / "svg" / f"{_BRAND_LOGO_FILES.get(brand_key, brand_key)}.svg"
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode()


_logo_b64 = _caetano_logo_b64()

# ── CSS global (string normal — sem f-string para não precisar escapar { }) ───
st.markdown("""
<style>
/* ── Wordmark Caetano — PNG branco usado como máscara, pintado a azul ── */
.caetano-wordmark {
    display: inline-block;
    aspect-ratio: 2883 / 512;
    background-color: #0c304d;
    -webkit-mask: var(--logo) no-repeat center / contain;
    mask: var(--logo) no-repeat center / contain;
}

.caetano-logo-sidebar {
    padding: 0 0 12px 0;
    line-height: 0;
}
.caetano-logo-sidebar .caetano-wordmark { width: 170px; }

/* ── Cabeçalho da página ── */
.app-header { margin: 0 0 1.75rem 0; }
.app-header-title {
    color: #0c304d;
    font-size: 2.1rem;
    font-weight: 700;
    line-height: 1.2;
}
.app-header-title .caetano-wordmark {
    height: .78em;
    margin-left: .3em;
    vertical-align: baseline;
}
.app-header-sub {
    color: #5b6878;
    font-size: 1.05rem;
    font-weight: 500;
    margin-top: .2rem;
}

/* ════════════════════════════════════════════════════════
   CONTROL PANEL — scoped ao container com key="control_panel"
   (não pode usar :first-child / nth-child, porque isso também
   apanhava a primeira coluna de cada linha de imagens geradas).
   Cartão azul com texto branco. Só se pintam a branco os elementos
   de texto do próprio painel (títulos, labels, legendas) — nunca o
   conteúdo dos widgets, senão as caixas de selecção ficavam com
   texto branco sobre fundo claro.
════════════════════════════════════════════════════════ */
.st-key-control_panel {
    background: #0c304d !important;
    border-radius: 14px !important;
    padding: 24px 22px 26px !important;
    box-shadow: 0 6px 24px rgba(12, 48, 77, .18) !important;
}

.st-key-control_panel h3 {
    color: #ffffff !important;
    font-weight: 700 !important;
    padding-bottom: 10px !important;
    border-bottom: 1px solid rgba(255, 255, 255, .18) !important;
    margin-bottom: 14px !important;
}

.st-key-control_panel [data-testid="stWidgetLabel"] p {
    color: #ffffff !important;
    font-weight: 600 !important;
    font-size: .88rem !important;
}

.st-key-control_panel [data-testid="stCaptionContainer"],
.st-key-control_panel [data-testid="stSpinner"] {
    color: rgba(255, 255, 255, .75) !important;
}

.st-key-control_panel [data-baseweb="select"] > div {
    border-color: #cfd7e0 !important;
    border-radius: 8px !important;
}

.st-key-control_panel [data-testid="stImage"] img {
    border-radius: 8px !important;
    border: 1px solid rgba(255, 255, 255, .25) !important;
}

.st-key-control_panel [data-testid="stImageCaption"],
.st-key-control_panel figcaption {
    color: rgba(255, 255, 255, .75) !important;
    font-size: .8rem !important;
}

.st-key-control_panel hr {
    border-color: rgba(255, 255, 255, .18) !important;
    margin: 16px 0 !important;
}

.st-key-control_panel [data-testid="stButton"] > button {
    font-weight: 700 !important;
    border-radius: 10px !important;
    padding: .6rem 1rem !important;
}

.st-key-control_panel [data-testid="stBaseButton-primary"] {
    background: #ffffff !important;
    border-color: #ffffff !important;
    color: #0c304d !important;
}

.st-key-control_panel [data-testid="stBaseButton-primary"]:hover {
    background: #e3ebf3 !important;
    border-color: #e3ebf3 !important;
}

/* ── Botão de download do ZIP — azul Caetano, texto branco, destacado ── */
.st-key-zip_download button {
    background: #0c304d !important;
    border: 2px solid #0c304d !important;
    color: #ffffff !important;
    border-radius: 12px !important;
    padding: 1rem 1.5rem !important;
    min-height: 3.6rem !important;
    box-shadow: 0 6px 20px rgba(12, 48, 77, .28) !important;
    transition: background .15s ease, transform .15s ease, box-shadow .15s ease !important;
}
.st-key-zip_download button p,
.st-key-zip_download button span {
    color: #ffffff !important;
    font-size: 1.15rem !important;
    font-weight: 700 !important;
}
.st-key-zip_download button:hover:not(:disabled) {
    background: #164a73 !important;
    border-color: #164a73 !important;
    transform: translateY(-1px);
    box-shadow: 0 10px 26px rgba(12, 48, 77, .35) !important;
}
.st-key-zip_download button:disabled {
    opacity: .45 !important;
    box-shadow: none !important;
}

/* ── Logo da marca seleccionada (ao lado do selectbox) ── */
.brand-logo {
    height: 40px;
    margin-bottom: 16px;  /* compensa o margin-bottom: -16px do stMarkdownContainer */
    display: flex;
    align-items: center;
    justify-content: center;
}
.brand-logo img {
    max-height: 40px;
    max-width: 100%;
    filter: brightness(0) invert(1);
}
</style>
""", unsafe_allow_html=True)

_wordmark_html = (
    f'<span class="caetano-wordmark" role="img" aria-label="Caetano" '
    f'style="--logo: url(data:image/png;base64,{_logo_b64})"></span>'
    if _logo_b64 else "Caetano"
)

# ── Autenticação ─────────────────────────────────────────────────────────────
if "auth_email" not in st.session_state:
    st.session_state.auth_email = None

auth.restore_session()

if not st.session_state.auth_email:
    auth.render_login_screen()
    st.stop()

current_email = st.session_state.auth_email
is_admin_user = auth.is_admin(current_email)

with st.sidebar:
    if _logo_b64:
        st.markdown(f'<div class="caetano-logo-sidebar">{_wordmark_html}</div>', unsafe_allow_html=True)
    st.caption(f"Sessão: {current_email}")
    if is_admin_user:
        label = "← Voltar à ferramenta" if st.session_state.get("view") == "backoffice" else "Backoffice"
        if st.button(label, use_container_width=True):
            st.session_state.view = "tool" if st.session_state.get("view") == "backoffice" else "backoffice"
            st.rerun()
    if st.button("Sair", use_container_width=True):
        auth.logout()
        st.session_state.pop("view", None)
        st.rerun()

if is_admin_user and st.session_state.get("view") == "backoffice":
    import backoffice
    backoffice.render()
    st.stop()

st.markdown(
    f'<div class="app-header">'
    f'<div class="app-header-title">Gerador de Imagens{_wordmark_html}</div>'
    f'<div class="app-header-sub">Viaturas Novas</div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── Catálogos com cache ────────────────────────────────────────────────────────
@st.cache_data(show_spinner="A carregar catálogo VW...")
def get_vw_catalog():
    return vw_load_catalog()

@st.cache_data(show_spinner="A carregar catálogo Peugeot...")
def get_peugeot_catalog():
    return peugeot_load_catalog()

@st.cache_data(show_spinner="A carregar catálogo Renault...")
def get_renault_catalog():
    return renault_load_catalog()

@st.cache_data(show_spinner="A verificar jantes disponíveis para esta cor...")
def get_platform_wheels_for_color(configurator_url, conf_uri, color_code):
    """Partilhado por Renault/Dacia/Alpine — mesma plataforma "One"."""
    return get_wheels_for_color(configurator_url, conf_uri, color_code)

@st.cache_data(show_spinner="A verificar estofos disponíveis...")
def get_platform_upholsteries(configurator_url, conf_uri, color_code, wheel_code):
    """Partilhado por Renault/Dacia/Alpine — depende de versão+cor+jante."""
    return get_upholsteries_for(configurator_url, conf_uri, color_code, wheel_code)

@st.cache_data(show_spinner="A carregar catálogo Dacia...")
def get_dacia_catalog():
    return dacia_load_catalog()

@st.cache_data(show_spinner="A carregar catálogo Opel...")
def get_opel_catalog():
    return opel_load_catalog()

@st.cache_data(show_spinner="A carregar catálogo Zeekr...")
def get_zeekr_catalog():
    return zeekr_load_catalog()

@st.cache_data(show_spinner="A carregar catálogo BYD...")
def get_byd_catalog():
    return byd_load_catalog()

@st.cache_data(show_spinner="A carregar catálogo Audi...")
def get_audi_catalog():
    return audi_load_catalog()

@st.cache_data(show_spinner="A carregar catálogo BMW...")
def get_bmw_catalog():
    return bmw_load_catalog()

@st.cache_data(show_spinner="A carregar catálogo Hyundai...")
def get_hyundai_catalog():
    return hyundai_load_catalog()

@st.cache_data(show_spinner="A carregar catálogo Mercedes-Benz...")
def get_mercedes_catalog():
    return mercedes_load_catalog()

@st.cache_data(show_spinner="A carregar catálogo MINI...")
def get_mini_catalog():
    return mini_load_catalog()

@st.cache_data(show_spinner="A carregar catálogo Nissan...")
def get_nissan_catalog():
    return nissan_load_catalog()

@st.cache_data(show_spinner="A carregar catálogo Škoda...")
def get_skoda_catalog():
    return skoda_load_catalog()

@st.cache_data(show_spinner="A carregar catálogo Geely...")
def get_geely_catalog():
    return geely_load_catalog()

@st.cache_data(show_spinner="A carregar catálogo Alpine...")
def get_alpine_catalog():
    return alpine_load_catalog()

@st.cache_data(show_spinner="A carregar catálogo XPENG...")
def get_xpeng_catalog():
    return xpeng_load_catalog()

LABELS_PT = {
    "3_4_frente": "3/4 Frente",
    "frente": "Frente",
    "lado": "Lado",
    "traseira": "Traseira",
    "interior": "Interior",
    "lado_estudio": "Lado (estúdio)",
    "lado_oposto": "Lado (oposto)",
    "jante_detalhe": "Jante (detalhe)",
    "interior_bancos": "Interior (bancos)",
    "interior_tablier": "Interior (tablier)",
    "interior_lateral": "Interior (lateral)",
    "3_4_frente_direita": "3/4 Frente Direita",
    "lado_direito": "Lado Direito",
    "3_4_traseira_esquerda": "3/4 Traseira Esquerda",
    "3_4_frente_esquerda": "3/4 Frente Esquerda",
    "3_4_frente_esquerda_proxima": "3/4 Frente Esquerda (próxima)",
    "3_4_frente_direita_lateral": "3/4 Frente Direita (lateral)",
    "3_4_traseira_esquerda_lateral": "3/4 Traseira Esquerda (lateral)",
    "3_4_traseira_direita": "3/4 Traseira Direita",
    "3_4_traseira_direita_lateral": "3/4 Traseira Direita (lateral)",
    "interior_bancos_traseiros": "Interior (bancos traseiros)",
    "bagageira_detalhe": "Bagageira",
    "pintura_detalhe": "Pintura (detalhe)",
    "traseira_recta": "Traseira (recta)",
    "farol_detalhe": "Farol (detalhe)",
    "lado_esquerdo": "Lado Esquerdo",
    "interior_estofos": "Interior (estofos)",
}

# marcadores que identificam imagens que NÃO são uma foto de produto
# isolada (interior, detalhe de jante) — a estas não se aplica a lógica
# de fundo branco + logo + sombra sintética, ficam como vêm da fonte.
_NO_COMPOSITE_MARKERS = ("interior", "detalhe")

# marcas cujas fotos já vêm em fundo branco liso com sombra natural —
# não se recortam (ver composite._composite_keep_background).
_KEEP_BACKGROUND_BRANDS = {"renault", "dacia", "alpine", "opel", "peugeot", "geely"}


def _pretty_label(key: str) -> str:
    """Nome amigável para uma label de imagem; cai para uma versão
    formatada da própria key quando não há tradução conhecida (as labels
    "extra_N"/"frame_N"/"ext_NNN"/"vista_NNN" não têm nome semântico
    confirmado visualmente — ver comentários nos respectivos *_images.py)."""
    if key in LABELS_PT:
        return LABELS_PT[key]
    if key.startswith("rotacao_") and key[8:].isdigit():
        return f"Rotação {int(key[8:])}°"
    return key.replace("_", " ").strip().capitalize()

def _show_color_swatch(color: dict) -> None:
    """Amostra de cor: imagem (swatchUrl) ou, quando o site só a desenha
    com CSS (ex.: Geely), um círculo com a cor (swatchColor)."""
    # sem legenda: o nome já está no selector e, numa coluna de 60px, a
    # legenda partia-se letra a letra
    if color.get("swatchUrl"):
        st.image(color["swatchUrl"], width=60)
    elif color.get("swatchColor"):
        st.markdown(
            f'<div style="display:flex;flex-direction:column;align-items:flex-start;gap:4px;margin:4px 0 8px">'
            f'<div style="width:56px;height:56px;border-radius:50%;background:{color["swatchColor"]};'
            f'border:1px solid #cfd7e0"></div></div>',
            unsafe_allow_html=True,
        )


def _interiors_for_color(interiors: list[dict] | None, color_code: str) -> list[dict]:
    """Só os estofos compatíveis com a cor exterior escolhida (campo
    "colors" do catálogo — VW/Audi/Škoda); sem esse campo, todos."""
    return [i for i in (interiors or []) if not i.get("colors") or color_code in i["colors"]]


def _pick_interior(interiors: list[dict] | None, key: str) -> dict | None:
    """Selector "Cor interior" + pré-visualização, comum a todas as marcas.
    `interiors`: [{"code", "name", "swatchUrl"?}], 1.ª = de série. Sem
    lista (marca/versão sem opções de interior) não mostra nada."""
    if not interiors:
        return None
    labels = []
    for it in interiors:
        lbl = it["name"]
        if it.get("price"):
            lbl += f" (+{it['price']:.0f}€)"
        while lbl in labels:
            lbl += " "
        labels.append(lbl)
    sel = interiors[labels.index(st.selectbox("Cor interior", labels, key=key))]
    _show_color_swatch(sel)
    return sel


# ── Layout ─────────────────────────────────────────────────────────────────────
col_sel, col_imgs = st.columns([1, 2], gap="large")

# ── Painel de selecção ─────────────────────────────────────────────────────────
panel = col_sel.container(key="control_panel")
with panel:
    st.subheader("Configuração")

    user_brand_keys = auth.get_user_brands(current_email) or []
    BRANDS = {name: key for name, key in ALL_BRANDS.items() if key in user_brand_keys}
    if not BRANDS:
        st.warning("A tua conta ainda não tem marcas atribuídas. Contacta um administrador.")
        st.stop()
    brand_col, logo_col = st.columns([5, 1], vertical_alignment="bottom")
    selected_brand = BRANDS[brand_col.selectbox("Marca", list(BRANDS.keys()))]
    _brand_logo = _brand_logo_b64(selected_brand)
    if _brand_logo:
        logo_col.markdown(
            f'<div class="brand-logo"><img src="data:image/svg+xml;base64,{_brand_logo}" alt="" /></div>',
            unsafe_allow_html=True,
        )

    # Limpar imagens ao mudar de marca
    if st.session_state.get("last_brand") != selected_brand:
        st.session_state.generated_images = None
        st.session_state.generated_config = None
        st.session_state.last_brand = selected_brand

    gerar_btn = False  # default

    # ── VW ────────────────────────────────────────────────────────────────────
    if selected_brand == "vw":
        catalog = get_vw_catalog()
        all_variants = [
            {"label": f"{g['groupName']} — {v['variantName']}", **v}
            for g in catalog.get("models", [])
            for v in g.get("variants", [])
        ]
        variant_labels = [v["label"] for v in all_variants]
        sel_variant_label = st.selectbox("Modelo", variant_labels, key="vw_model")
        selected_variant = next(v for v in all_variants if v["label"] == sel_variant_label)
        model_code = selected_variant["modelCode"]
        default_upholstery = selected_variant["defaultUpholstery"]
        colors = selected_variant["colors"]
        wheels = selected_variant["wheels"]

        color_labels = [
            f"{c['name']} (+{c['price']:.0f}€)" if c["price"] > 0 else c["name"]
            for c in colors
        ]
        color_map = {lbl: c for lbl, c in zip(color_labels, colors)}
        sel_color = color_map[st.selectbox("Cor", color_labels, key="vw_color")]
        _show_color_swatch(sel_color)

        wheel_labels = [f"{w['title']} {'(série)' if w['serie'] else ''}" for w in wheels]
        wheel_map = {lbl: w for lbl, w in zip(wheel_labels, wheels)}
        sel_wheel = wheel_map[st.selectbox("Jantes", wheel_labels, key="vw_wheels")]
        if sel_wheel.get("imageUrl"):
            st.image(sel_wheel["imageUrl"], width=120, caption=sel_wheel["title"])

        sel_vint = _pick_interior(_interiors_for_color(selected_variant.get("interiors"), sel_color["code"]), "vw_interior")
        if sel_vint:
            default_upholstery = sel_vint["code"]
        vw_equipment = (sel_vint or {}).get("equipment", "")

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── Peugeot ───────────────────────────────────────────────────────────────
    elif selected_brand == "peugeot":
        pcat = get_peugeot_catalog()
        pmodels = pcat.get("models", [])
        model_names = [m["modelName"] for m in pmodels]
        model_map = {name: m for name, m in zip(model_names, pmodels)}
        sel_model = model_map[st.selectbox("Modelo", model_names, key="peugeot_model")]

        # Seletor de versão (trim)
        variants = sel_model["variants"]
        variant_names = [v["variantName"] for v in variants]
        variant_map = {n: v for n, v in zip(variant_names, variants)}
        sel_variant = variant_map[st.selectbox("Versão", variant_names, key="peugeot_version")]

        # Seletor de cor
        pcolors = sel_variant["colors"]
        pcolor_labels = [c["name"] for c in pcolors]
        pcolor_map = {n: c for n, c in zip(pcolor_labels, pcolors)}
        sel_pcolor = pcolor_map[st.selectbox("Cor", pcolor_labels, key="peugeot_color")]

        _show_color_swatch(sel_pcolor)
        # o interior é o código "trim" do V3D; os GT têm 2 à escolha
        sel_pint = _pick_interior(sel_variant.get("interiors"), "peugeot_interior")
        if not sel_pint and sel_variant.get("trimCode"):
            st.image(f"https://visuel3d-secure.peugeot.com/v3dcentral/Trims/ndp/th_{sel_variant['trimCode']}.png",
                     width=60)
            st.caption("Interior incluído na versão")
        peugeot_trim = (sel_pint or {}).get("code") or sel_variant["trimCode"]

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── Renault ───────────────────────────────────────────────────────────────
    elif selected_brand == "renault":
        rcat = get_renault_catalog()
        rmodels = rcat.get("models", [])
        rmodel_names = [m["modelName"] for m in rmodels]
        rmodel_map = {name: m for name, m in zip(rmodel_names, rmodels)}
        sel_rmodel = rmodel_map[st.selectbox("Modelo", rmodel_names, key="renault_model")]

        # Seletor de versão
        rvariants = sel_rmodel["variants"]
        rvariant_labels = [f"{v['versionName']} (desde {v['startingPrice']:.0f}€)" for v in rvariants]
        rvariant_map = {lbl: v for lbl, v in zip(rvariant_labels, rvariants)}
        sel_rvariant = rvariant_map[st.selectbox("Versão", rvariant_labels, key="renault_version")]

        # Seletor de cor
        rcolors = sel_rvariant["colors"]
        rcolor_labels = [
            f"{c['name']} (+{c['price']:.0f}€)" if c["price"] > 0 else c["name"]
            for c in rcolors
        ]
        rcolor_map = {lbl: c for lbl, c in zip(rcolor_labels, rcolors)}
        sel_rcolor = rcolor_map[st.selectbox("Cor", rcolor_labels, key="renault_color")]

        _show_color_swatch(sel_rcolor)

        # Seletor de jantes — buscadas em tempo real para a cor escolhida
        # (nesta plataforma a validade de uma jante depende da cor; a
        # lista completa da versão inclui jantes que não servem para
        # todas as cores).
        rwheels = get_platform_wheels_for_color(sel_rmodel["configuratorUrl"], sel_rvariant["confURI"], sel_rcolor["code"])
        if rwheels:
            rwheel_labels = [
                f"{w['name']} (+{w['price']:.0f}€)" if w["price"] > 0 else f"{w['name']} (série)"
                for w in rwheels
            ]
            rwheel_map = {lbl: w for lbl, w in zip(rwheel_labels, rwheels)}
            sel_rwheel = rwheel_map[st.selectbox("Jantes", rwheel_labels, key="renault_wheels")]
        else:
            sel_rwheel = {"code": "", "name": "série"}

        if sel_rwheel.get("imageUrl"):
            st.image(sel_rwheel["imageUrl"], width=120, caption=sel_rwheel["name"])

        sel_renault_int = _pick_interior(
            get_platform_upholsteries(sel_rmodel["configuratorUrl"], sel_rvariant["confURI"], sel_rcolor["code"], sel_rwheel["code"]),
            "renault_interior",
        )

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── Dacia ─────────────────────────────────────────────────────────────────
    elif selected_brand == "dacia":
        dcat = get_dacia_catalog()
        dmodels = dcat.get("models", [])
        dmodel_names = [m["modelName"] for m in dmodels]
        dmodel_map = {name: m for name, m in zip(dmodel_names, dmodels)}
        sel_dmodel = dmodel_map[st.selectbox("Modelo", dmodel_names, key="dacia_model")]

        # Seletor de versão
        dvariants = sel_dmodel["variants"]
        dvariant_labels = [f"{v['versionName']} (desde {v['startingPrice']:.0f}€)" for v in dvariants]
        dvariant_map = {lbl: v for lbl, v in zip(dvariant_labels, dvariants)}
        sel_dvariant = dvariant_map[st.selectbox("Versão", dvariant_labels, key="dacia_version")]

        # Seletor de cor
        dcolors = sel_dvariant["colors"]
        dcolor_labels = [
            f"{c['name']} (+{c['price']:.0f}€)" if c["price"] > 0 else c["name"]
            for c in dcolors
        ]
        dcolor_map = {lbl: c for lbl, c in zip(dcolor_labels, dcolors)}
        sel_dcolor = dcolor_map[st.selectbox("Cor", dcolor_labels, key="dacia_color")]

        _show_color_swatch(sel_dcolor)

        # Seletor de jantes — buscadas em tempo real para a cor escolhida
        # (ver nota equivalente na Renault, mesma plataforma).
        dwheels = get_platform_wheels_for_color(sel_dmodel["configuratorUrl"], sel_dvariant["confURI"], sel_dcolor["code"])
        if dwheels:
            dwheel_labels = [
                f"{w['name']} (+{w['price']:.0f}€)" if w["price"] > 0 else f"{w['name']} (série)"
                for w in dwheels
            ]
            dwheel_map = {lbl: w for lbl, w in zip(dwheel_labels, dwheels)}
            sel_dwheel = dwheel_map[st.selectbox("Jantes", dwheel_labels, key="dacia_wheels")]
        else:
            sel_dwheel = {"code": "", "name": "série"}

        if sel_dwheel.get("imageUrl"):
            st.image(sel_dwheel["imageUrl"], width=120, caption=sel_dwheel["name"])

        sel_dacia_int = _pick_interior(
            get_platform_upholsteries(sel_dmodel["configuratorUrl"], sel_dvariant["confURI"], sel_dcolor["code"], sel_dwheel["code"]),
            "dacia_interior",
        )

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── Opel ──────────────────────────────────────────────────────────────────
    elif selected_brand == "opel":
        ocat = get_opel_catalog()
        omodels = ocat.get("models", [])
        omodel_names = [m["modelName"] for m in omodels]
        omodel_map = {name: m for name, m in zip(omodel_names, omodels)}
        sel_omodel = omodel_map[st.selectbox("Modelo", omodel_names, key="opel_model")]

        # Seletor de versão (acabamento + motor)
        ovariants = sel_omodel["variants"]
        ovariant_labels = [v["versionName"] for v in ovariants]
        ovariant_map = {lbl: v for lbl, v in zip(ovariant_labels, ovariants)}
        sel_ovariant = ovariant_map[st.selectbox("Versão", ovariant_labels, key="opel_version")]

        # Seletor de cor
        ocolors = sel_ovariant["colors"]
        ocolor_labels = [
            f"{c['name']} (+{c['price']:.0f}€)" if c.get("price", 0) > 0 else c["name"]
            for c in ocolors
        ]
        ocolor_map = {lbl: c for lbl, c in zip(ocolor_labels, ocolors)}
        sel_ocolor = ocolor_map[st.selectbox("Cor", ocolor_labels, key="opel_color")]
        _show_color_swatch(sel_ocolor)
        # interior = código "trim" do V3D; a maioria das versões só tem 1
        # (fica fixo, com pré-visualização), algumas têm 2 (ex.: Frontera)
        sel_oint = _pick_interior(sel_ovariant.get("interiors"), "opel_interior")
        if not sel_oint and sel_ovariant.get("trimCode") and len(sel_ovariant.get("lcdv16", "")) >= 6:
            _l = sel_ovariant["lcdv16"]
            st.image(f"https://visual3d-secure.opel-vauxhall.com/V3DCentral/{_l[:4]}/{_l[4:6]}/Trims/{sel_ovariant['trimCode']}.jpg",
                     width=60)
            st.caption("Interior incluído na versão")

        # Seletor de jantes (nem todas as versões têm alternativa de jante)
        owheels = sel_ovariant["wheels"]
        if owheels:
            owheel_labels = [
                f"{w['name']} (+{w['price']:.0f}€)" if w["price"] > 0 else f"{w['name']} (série)"
                for w in owheels
            ]
            owheel_map = {lbl: w for lbl, w in zip(owheel_labels, owheels)}
            sel_owheel = owheel_map[st.selectbox("Jantes", owheel_labels, key="opel_wheels")]
            if sel_owheel.get("imageUrl"):
                st.image(sel_owheel["imageUrl"], width=120, caption=sel_owheel["name"])
        else:
            sel_owheel = {"code": "", "name": "série"}

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── Zeekr ─────────────────────────────────────────────────────────────────
    elif selected_brand == "zeekr":
        zcat = get_zeekr_catalog()
        zmodels = zcat.get("models", [])
        zmodel_names = [m["modelName"] for m in zmodels]
        zmodel_map = {name: m for name, m in zip(zmodel_names, zmodels)}
        sel_zmodel = zmodel_map[st.selectbox("Modelo", zmodel_names, key="zeekr_model")]

        # Seletor de versão
        zvariants = sel_zmodel["variants"]
        zvariant_labels = [f"{v['versionName']} (desde {v['price']:.0f}€)" for v in zvariants]
        zvariant_map = {lbl: v for lbl, v in zip(zvariant_labels, zvariants)}
        sel_zvariant = zvariant_map[st.selectbox("Versão", zvariant_labels, key="zeekr_version")]

        # Seletor de cor (sem jantes seleccionáveis nem cor de interior — a
        # Zeekr não expõe nenhuma das duas como opção separada)
        zcolors = sel_zvariant["colors"]
        zcolor_labels = [
            f"{c['name']} (+{c['price']:.0f}€)" if c["price"] > 0 else c["name"]
            for c in zcolors
        ]
        zcolor_map = {lbl: c for lbl, c in zip(zcolor_labels, zcolors)}
        sel_zcolor = zcolor_map[st.selectbox("Cor", zcolor_labels, key="zeekr_color")]
        _show_color_swatch(sel_zcolor)

        sel_zint = _pick_interior(sel_zvariant.get("interiors"), "zeekr_interior")

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── BYD ───────────────────────────────────────────────────────────────────
    elif selected_brand == "byd":
        bcat = get_byd_catalog()
        bmodels = bcat.get("models", [])
        bmodel_names = [m["modelName"] for m in bmodels]
        bmodel_map = {name: m for name, m in zip(bmodel_names, bmodels)}
        sel_bmodel = bmodel_map[st.selectbox("Modelo", bmodel_names, key="byd_model")]

        # Seletor de versão
        bvariants = sel_bmodel["variants"]
        bvariant_labels = [f"{v['versionName']} (desde {v['price']:.0f}€)" for v in bvariants]
        bvariant_map = {lbl: v for lbl, v in zip(bvariant_labels, bvariants)}
        sel_bvariant = bvariant_map[st.selectbox("Versão", bvariant_labels, key="byd_version")]

        # Seletor de cor (sem jantes seleccionáveis — o tamanho de jante é uma
        # especificação da versão, não uma opção)
        bcolors = sel_bvariant["colors"]
        bcolor_labels = [
            f"{c['name']} (+{c['price']:.0f}€)" if c["price"] > 0 else c["name"]
            for c in bcolors
        ]
        bcolor_map = {lbl: c for lbl, c in zip(bcolor_labels, bcolors)}
        sel_bcolor = bcolor_map[st.selectbox("Cor", bcolor_labels, key="byd_color")]
        _show_color_swatch(sel_bcolor)

        sel_bint = _pick_interior(
            cardb_for_exterior(sel_bvariant.get("interiors", []), sel_bcolor.get("extId")), "byd_interior",
        )

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── Audi ──────────────────────────────────────────────────────────────────
    elif selected_brand == "audi":
        acat = get_audi_catalog()
        all_avariants = [
            {"label": f"{g['groupName']} — {v['variantName']}", **v}
            for g in acat.get("models", [])
            for v in g.get("variants", [])
        ]
        avariant_labels = [v["label"] for v in all_avariants]
        sel_avariant_label = st.selectbox("Modelo", avariant_labels, key="audi_model")
        selected_avariant = next(v for v in all_avariants if v["label"] == sel_avariant_label)
        amodel_code = selected_avariant["modelCode"]
        adefault_upholstery = selected_avariant["defaultUpholstery"]
        acolors = selected_avariant["colors"]
        awheels = selected_avariant["wheels"]

        acolor_labels = [
            f"{c['name']} (+{c['price']:.0f}€)" if c["price"] > 0 else c["name"]
            for c in acolors
        ]
        acolor_map = {lbl: c for lbl, c in zip(acolor_labels, acolors)}
        sel_acolor = acolor_map[st.selectbox("Cor", acolor_labels, key="audi_color")]
        _show_color_swatch(sel_acolor)

        awheel_labels = [f"{w['title']} {'(série)' if w['serie'] else ''}" for w in awheels]
        awheel_map = {lbl: w for lbl, w in zip(awheel_labels, awheels)}
        sel_awheel = awheel_map[st.selectbox("Jantes", awheel_labels, key="audi_wheels")]
        if sel_awheel.get("imageUrl"):
            st.image(sel_awheel["imageUrl"], width=120, caption=sel_awheel["title"])

        sel_aint = _pick_interior(_interiors_for_color(selected_avariant.get("interiors"), sel_acolor["code"]), "audi_interior")
        if sel_aint:
            adefault_upholstery = sel_aint["code"]
        audi_equipment = (sel_aint or {}).get("equipment", "")

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── BMW ───────────────────────────────────────────────────────────────────
    elif selected_brand == "bmw":
        bmwcat = get_bmw_catalog()
        all_bmwvariants = [
            {"label": f"{g['groupName']} — {v['variantName']}", **v}
            for g in bmwcat.get("models", [])
            for v in g.get("variants", [])
        ]
        bmwvariant_labels = [v["label"] for v in all_bmwvariants]
        sel_bmwvariant_label = st.selectbox("Modelo", bmwvariant_labels, key="bmw_model")
        selected_bmwvariant = next(v for v in all_bmwvariants if v["label"] == sel_bmwvariant_label)
        bmw_model_code = selected_bmwvariant["modelCode"]
        bmw_base_options = selected_bmwvariant["baseOptions"]
        bmw_effect_date = selected_bmwvariant["effectDate"]
        bmwcolors = selected_bmwvariant["colors"]
        bmwwheels = selected_bmwvariant["wheels"]

        bmwcolor_labels = [c["name"] for c in bmwcolors]
        bmwcolor_map = {lbl: c for lbl, c in zip(bmwcolor_labels, bmwcolors)}
        sel_bmwcolor = bmwcolor_map[st.selectbox("Cor", bmwcolor_labels, key="bmw_color")]
        _show_color_swatch(sel_bmwcolor)

        bmwwheel_labels = [f"{w['name']} {'(série)' if w['std'] else ''}" for w in bmwwheels]
        bmwwheel_map = {lbl: w for lbl, w in zip(bmwwheel_labels, bmwwheels)}
        sel_bmwwheel = bmwwheel_map[st.selectbox("Jantes", bmwwheel_labels, key="bmw_wheels")]
        if sel_bmwwheel.get("imageUrl"):
            st.image(sel_bmwwheel["imageUrl"], width=120, caption=sel_bmwwheel["name"])

        # estofo: troca o código de estofo de série das opções base pelo escolhido
        sel_bmwint = _pick_interior(selected_bmwvariant.get("interiors"), "bmw_interior")
        if sel_bmwint:
            _uph_codes = {i["code"] for i in selected_bmwvariant["interiors"]}
            bmw_base_options = [o for o in bmw_base_options if o not in _uph_codes] + [sel_bmwint["code"]]

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── Hyundai ───────────────────────────────────────────────────────────────
    elif selected_brand == "hyundai":
        hcat = get_hyundai_catalog()
        hmodels = hcat.get("models", [])
        hmodel_names = [m["groupName"] for m in hmodels]
        hmodel_map = {name: m for name, m in zip(hmodel_names, hmodels)}
        sel_hmodel = hmodel_map[st.selectbox("Modelo", hmodel_names, key="hyundai_model")]

        # Seletor de versão
        hvariants = sel_hmodel["variants"]
        hvariant_labels = [v["variantName"] for v in hvariants]
        hvariant_map = {lbl: v for lbl, v in zip(hvariant_labels, hvariants)}
        sel_hvariant = hvariant_map[st.selectbox("Versão", hvariant_labels, key="hyundai_version")]

        # Seletor de cor (sem jantes seleccionáveis — tal como na BYD/Zeekr,
        # a jante é uma especificação da versão, não uma opção)
        hcolors = sel_hvariant["colors"]
        hcolor_labels = [
            f"{c['name']} (+{c['price']:.0f}€)" if c["price"] > 0 else c["name"]
            for c in hcolors
        ]
        hcolor_map = {lbl: c for lbl, c in zip(hcolor_labels, hcolors)}
        sel_hcolor = hcolor_map[st.selectbox("Cor", hcolor_labels, key="hyundai_color")]
        _show_color_swatch(sel_hcolor)

        sel_hint = _pick_interior(
            cardb_for_exterior(sel_hvariant.get("interiors", []), sel_hcolor["code"]), "hyundai_interior",
        )

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── Mercedes-Benz ─────────────────────────────────────────────────────────
    elif selected_brand == "mercedes":
        mcat = get_mercedes_catalog()
        mmodels = mcat.get("models", [])
        mmodel_names = [m["groupName"] for m in mmodels]
        mmodel_map = {name: m for name, m in zip(mmodel_names, mmodels)}
        sel_mmodel = mmodel_map[st.selectbox("Modelo", mmodel_names, key="mercedes_model")]

        # Seletor de versão (motorização)
        mvariants = sel_mmodel["variants"]
        mvariant_labels = [f"{v['variantName']} (desde {v['price']:.0f}€)" for v in mvariants]
        mvariant_map = {lbl: v for lbl, v in zip(mvariant_labels, mvariants)}
        mvariant = mvariant_map[st.selectbox("Versão", mvariant_labels, key="mercedes_version")]

        # Seletor de cor
        mcolors = mvariant["colors"]
        mcolor_labels = [
            f"{c['name']} (+{c['price']:.0f}€)" if c["price"] > 0 else c["name"]
            for c in mcolors
        ]
        mcolor_map = {lbl: c for lbl, c in zip(mcolor_labels, mcolors)}
        sel_mcolor = mcolor_map[st.selectbox("Cor", mcolor_labels, key="mercedes_color")]
        _show_color_swatch(sel_mcolor)

        # Seletor de jantes (algumas versões só têm a jante de série válida)
        mwheels = mvariant["wheels"]
        if mwheels:
            mwheel_labels = [
                f"{w['name']} (+{w['price']:.0f}€)" if w["price"] > 0 else f"{w['name']} (série)"
                for w in mwheels
            ]
            mwheel_map = {lbl: w for lbl, w in zip(mwheel_labels, mwheels)}
            sel_mwheel = mwheel_map[st.selectbox("Jantes", mwheel_labels, key="mercedes_wheels")]
            if sel_mwheel.get("imageUrl"):
                st.image(sel_mwheel["imageUrl"], width=120, caption=sel_mwheel["name"])
        else:
            sel_mwheel = {"code": "", "name": "série"}

        sel_mint = _pick_interior(mvariant.get("interiors"), "mercedes_interior")

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── MINI ──────────────────────────────────────────────────────────────────
    elif selected_brand == "mini":
        minicat = get_mini_catalog()
        all_minivariants = [
            {"label": f"{g['groupName']} — {v['variantName']}", **v}
            for g in minicat.get("models", [])
            for v in g.get("variants", [])
        ]
        minivariant_labels = [v["label"] for v in all_minivariants]
        sel_minivariant_label = st.selectbox("Modelo", minivariant_labels, key="mini_model")
        selected_minivariant = next(v for v in all_minivariants if v["label"] == sel_minivariant_label)
        mini_model_code = selected_minivariant["modelCode"]
        mini_base_options = selected_minivariant["baseOptions"]
        mini_effect_date = selected_minivariant["effectDate"]
        minicolors = selected_minivariant["colors"]
        miniwheels = selected_minivariant["wheels"]

        minicolor_labels = [c["name"] for c in minicolors]
        minicolor_map = {lbl: c for lbl, c in zip(minicolor_labels, minicolors)}
        sel_minicolor = minicolor_map[st.selectbox("Cor", minicolor_labels, key="mini_color")]
        _show_color_swatch(sel_minicolor)

        miniwheel_labels = [f"{w['name']} {'(série)' if w['std'] else ''}" for w in miniwheels]
        miniwheel_map = {lbl: w for lbl, w in zip(miniwheel_labels, miniwheels)}
        sel_miniwheel = miniwheel_map[st.selectbox("Jantes", miniwheel_labels, key="mini_wheels")]
        if sel_miniwheel.get("imageUrl"):
            st.image(sel_miniwheel["imageUrl"], width=120, caption=sel_miniwheel["name"])

        # estofo: troca o código de estofo de série das opções base pelo escolhido
        sel_miniint = _pick_interior(selected_minivariant.get("interiors"), "mini_interior")
        if sel_miniint:
            _uph_codes = {i["code"] for i in selected_minivariant["interiors"]}
            mini_base_options = [o for o in mini_base_options if o not in _uph_codes] + [sel_miniint["code"]]

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── Nissan ────────────────────────────────────────────────────────────────
    # configurador.nissan.pt (plataforma "cardb", como a BYD): modelo ->
    # versão -> cor -> cor de interior. Micra bicolor com volta de 360°.
    elif selected_brand == "nissan":
        ncat = get_nissan_catalog()
        nmodels = ncat.get("models", [])
        nmodel_names = [m["modelName"] for m in nmodels]
        nmodel_map = {name: m for name, m in zip(nmodel_names, nmodels)}
        sel_nmodel = nmodel_map[st.selectbox("Modelo", nmodel_names, key="nissan_model")]

        nversions = sel_nmodel["variants"]
        nversion_labels = [
            f"{v['versionName']} (desde {v['price']:.0f}€)" if v.get("price") else v["versionName"]
            for v in nversions
        ]
        nversion_map = {lbl: v for lbl, v in zip(nversion_labels, nversions)}
        sel_nversion = nversion_map[st.selectbox("Versão", nversion_labels, key="nissan_version")]

        ncolors = sel_nversion["colors"]
        ncolor_labels = [
            f"{c['name']} (+{c['price']:.0f}€)" if c["price"] > 0 else c["name"]
            for c in ncolors
        ]
        ncolor_map = {lbl: c for lbl, c in zip(ncolor_labels, ncolors)}
        sel_ncolor = ncolor_map[st.selectbox("Cor", ncolor_labels, key="nissan_color")]
        _show_color_swatch(sel_ncolor)

        sel_nint = _pick_interior(
            cardb_for_exterior(sel_nversion.get("interiors", []), sel_ncolor.get("extId")), "nissan_interior",
        )

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── Škoda ─────────────────────────────────────────────────────────────────
    elif selected_brand == "skoda":
        scat = get_skoda_catalog()
        all_svariants = [
            {"label": f"{g['groupName']} — {v['variantName']}", **v}
            for g in scat.get("models", [])
            for v in g.get("variants", [])
        ]
        svariant_labels = [v["label"] for v in all_svariants]
        sel_svariant_label = st.selectbox("Modelo", svariant_labels, key="skoda_model")
        selected_svariant = next(v for v in all_svariants if v["label"] == sel_svariant_label)
        skoda_model_code = selected_svariant["modelCode"]
        skoda_default_upholstery = selected_svariant["defaultUpholstery"]
        scolors = selected_svariant["colors"]
        swheels = selected_svariant["wheels"]

        scolor_labels = [
            f"{c['name']} (+{c['price']:.0f}€)" if c["price"] > 0 else c["name"]
            for c in scolors
        ]
        scolor_map = {lbl: c for lbl, c in zip(scolor_labels, scolors)}
        sel_scolor = scolor_map[st.selectbox("Cor", scolor_labels, key="skoda_color")]
        _show_color_swatch(sel_scolor)

        swheel_labels = [f"{w['title']} {'(série)' if w['serie'] else ''}" for w in swheels]
        swheel_map = {lbl: w for lbl, w in zip(swheel_labels, swheels)}
        sel_swheel = swheel_map[st.selectbox("Jantes", swheel_labels, key="skoda_wheels")]
        if sel_swheel.get("imageUrl"):
            st.image(sel_swheel["imageUrl"], width=120, caption=sel_swheel["title"])

        sel_sint = _pick_interior(_interiors_for_color(selected_svariant.get("interiors"), sel_scolor["code"]), "skoda_interior")
        if sel_sint:
            skoda_default_upholstery = sel_sint["code"]
        skoda_equipment = (sel_sint or {}).get("equipment", "")

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── Geely ─────────────────────────────────────────────────────────────────
    # Site SPA simples: versões (PRO/MAX/...) só têm preço próprio, não
    # afectam a foto — o "Vista 360°" é só por cor (24 fotogramas fixos por
    # combinação modelo+cor, sem depender de versão/jantes).
    elif selected_brand == "geely":
        gcat = get_geely_catalog()
        gmodels = gcat.get("models", [])
        gmodel_names = [m["modelName"] for m in gmodels]
        gmodel_map = {name: m for name, m in zip(gmodel_names, gmodels)}
        sel_gmodel = gmodel_map[st.selectbox("Modelo", gmodel_names, key="geely_model")]

        gversions = sel_gmodel["versions"]
        gversion_labels = [f"{v['name']} ({v['spec']}) — {v['price']:.0f}€" for v in gversions]
        gversion_map = {lbl: v for lbl, v in zip(gversion_labels, gversions)}
        sel_gversion = gversion_map[st.selectbox("Versão", gversion_labels, key="geely_version")]

        gcolors = sel_gmodel["colors"]
        gcolor_labels = [
            f"{c['name']} (+{c['price']:.0f}€)" if c["price"] > 0 else c["name"]
            for c in gcolors
        ]
        gcolor_map = {lbl: c for lbl, c in zip(gcolor_labels, gcolors)}
        sel_gcolor = gcolor_map[st.selectbox("Cor", gcolor_labels, key="geely_color")]
        _show_color_swatch(sel_gcolor)
        st.caption("A versão não influencia a foto — o \"Vista 360°\" do site oficial é só por cor.")

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── Alpine ────────────────────────────────────────────────────────────────
    elif selected_brand == "alpine":
        alcat = get_alpine_catalog()
        almodels = alcat.get("models", [])
        almodel_names = [m["modelName"] for m in almodels]
        almodel_map = {name: m for name, m in zip(almodel_names, almodels)}
        sel_almodel = almodel_map[st.selectbox("Modelo", almodel_names, key="alpine_model")]

        alvariants = sel_almodel["variants"]
        alvariant_labels = [f"{v['versionName']} (desde {v['startingPrice']:.0f}€)" for v in alvariants]
        alvariant_map = {lbl: v for lbl, v in zip(alvariant_labels, alvariants)}
        sel_alvariant = alvariant_map[st.selectbox("Versão", alvariant_labels, key="alpine_version")]

        alcolors = sel_alvariant["colors"]
        if alcolors:
            alcolor_labels = [
                f"{c['name']} (+{c['price']:.0f}€)" if c["price"] > 0 else c["name"]
                for c in alcolors
            ]
            alcolor_map = {lbl: c for lbl, c in zip(alcolor_labels, alcolors)}
            sel_alcolor = alcolor_map[st.selectbox("Cor", alcolor_labels, key="alpine_color")]
            _show_color_swatch(sel_alcolor)
        else:
            # Edições especiais (ex.: A110 R 70 Rouge) têm uma única cor fixa
            # de fábrica, sem alternativa seleccionável no configurador.
            sel_alcolor = {"code": "", "name": "cor única de série"}
            st.caption("Esta versão tem cor única de fábrica, sem alternativa seleccionável.")

        # Jantes buscadas em tempo real para a cor escolhida (ver nota
        # equivalente na Renault, mesma plataforma) — para as edições sem
        # cor seleccionável, sel_alcolor["code"] é "" e devolve as jantes
        # da versão base.
        alwheels = get_platform_wheels_for_color(sel_almodel["configuratorUrl"], sel_alvariant["confURI"], sel_alcolor["code"])
        if alwheels:
            alwheel_labels = [
                f"{w['name']} (+{w['price']:.0f}€)" if w["price"] > 0 else f"{w['name']} (série)"
                for w in alwheels
            ]
            alwheel_map = {lbl: w for lbl, w in zip(alwheel_labels, alwheels)}
            sel_alwheel = alwheel_map[st.selectbox("Jantes", alwheel_labels, key="alpine_wheels")]
        else:
            sel_alwheel = {"code": "", "name": "série"}

        if sel_alwheel.get("imageUrl"):
            st.image(sel_alwheel["imageUrl"], width=120, caption=sel_alwheel["name"])

        sel_alpine_int = _pick_interior(
            get_platform_upholsteries(sel_almodel["configuratorUrl"], sel_alvariant["confURI"], sel_alcolor["code"], sel_alwheel["code"]),
            "alpine_interior",
        )

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

    # ── XPENG ─────────────────────────────────────────────────────────────────
    # 5 ângulos por cor; interior a partir do panorama 360° da cor de
    # interior escolhida (scraper/panorama.py).
    else:
        xcat = get_xpeng_catalog()
        xmodels = xcat.get("models", [])
        xmodel_names = [m["modelName"] for m in xmodels]
        xmodel_map = {name: m for name, m in zip(xmodel_names, xmodels)}
        sel_xmodel = xmodel_map[st.selectbox("Modelo", xmodel_names, key="xpeng_model")]

        xversions = sel_xmodel["versions"]
        xversion_labels = [f"{v['versionName']} (desde {v['price']:.0f}€)" for v in xversions]
        xversion_map = {lbl: v for lbl, v in zip(xversion_labels, xversions)}
        sel_xversion = xversion_map[st.selectbox("Versão", xversion_labels, key="xpeng_version")]

        xcolors = sel_xversion["colors"]
        xcolor_labels = [
            f"{c['name']} (+{c['price']:.0f}€)" if c["price"] > 0 else c["name"]
            for c in xcolors
        ]
        xcolor_map = {lbl: c for lbl, c in zip(xcolor_labels, xcolors)}
        sel_xcolor = xcolor_map[st.selectbox("Cor", xcolor_labels, key="xpeng_color")]
        _show_color_swatch(sel_xcolor)

        sel_xint = _pick_interior(
            cardb_for_exterior(sel_xversion.get("interiors", []), str(sel_xcolor["code"])), "xpeng_interior",
        )

        st.divider()
        gerar_btn = st.button("Gerar Imagens", type="primary", use_container_width=True)

# ── Coluna de imagens ──────────────────────────────────────────────────────────
with col_imgs:
    st.subheader("Imagens Geradas")

    if "generated_images" not in st.session_state:
        st.session_state.generated_images = None
        st.session_state.generated_config = None

    if gerar_btn:
        try:
            with st.spinner("A gerar imagens..."):
                if selected_brand == "vw":
                    color_code = sel_color["code"]
                    wheel_code = ",".join(x for x in (vw_equipment, sel_wheel["code"] if not sel_wheel.get("serie") else "") if x)
                    images = vw_generate_images(
                        model_code=model_code,
                        color_code=color_code,
                        upholstery_code=default_upholstery,
                        wheel_code=wheel_code,
                    )
                    cfg = {
                        "brand": "VW",
                        "model": selected_variant.get("name"),
                        "color": sel_color.get("name"),
                        "detail": sel_wheel.get("title"),
                        "zip_prefix": f"VW_{model_code}_{color_code}",
                    }
                elif selected_brand == "peugeot":
                    images = peugeot_generate_images(
                        version=sel_variant["lcdv16"],
                        color_id=sel_pcolor["id"],
                        trim_id=peugeot_trim,
                    )
                    cfg = {
                        "brand": "Peugeot",
                        "model": sel_model["modelName"],
                        "color": sel_pcolor["name"],
                        "detail": sel_variant["variantName"],
                        "zip_prefix": f"Peugeot_{sel_variant['lcdv16']}_{sel_pcolor['id']}",
                    }
                elif selected_brand == "renault":
                    images = renault_generate_images(
                        configurator_url=sel_rmodel["configuratorUrl"],
                        conf_uri=sel_rvariant["confURI"],
                        color_code=sel_rcolor["code"],
                        wheel_code=sel_rwheel["code"],
                        upholstery_code=(sel_renault_int or {}).get("code", ""),
                    )
                    cfg = {
                        "brand": "Renault",
                        "model": sel_rmodel["modelName"],
                        "color": sel_rcolor["name"],
                        "detail": sel_rvariant["versionName"],
                        "zip_prefix": f"Renault_{sel_rmodel['modelId']}_{sel_rcolor['code']}",
                    }
                elif selected_brand == "dacia":
                    images = dacia_generate_images(
                        configurator_url=sel_dmodel["configuratorUrl"],
                        conf_uri=sel_dvariant["confURI"],
                        color_code=sel_dcolor["code"],
                        wheel_code=sel_dwheel["code"],
                        upholstery_code=(sel_dacia_int or {}).get("code", ""),
                    )
                    cfg = {
                        "brand": "Dacia",
                        "model": sel_dmodel["modelName"],
                        "color": sel_dcolor["name"],
                        "detail": sel_dvariant["versionName"],
                        "zip_prefix": f"Dacia_{sel_dmodel['modelId']}_{sel_dcolor['code']}",
                    }
                elif selected_brand == "opel":
                    images = opel_generate_images(
                        version=sel_ovariant["lcdv16"],
                        color_id=sel_ocolor["code"],
                        trim_id=(sel_oint or {}).get("code") or sel_ovariant["trimCode"],
                        wheel_code=sel_owheel["code"],
                    )
                    cfg = {
                        "brand": "Opel",
                        "model": sel_omodel["modelName"],
                        "color": sel_ocolor["name"],
                        "detail": sel_ovariant["versionName"],
                        "zip_prefix": f"Opel_{sel_omodel['modelId']}_{sel_ocolor['code']}",
                    }
                elif selected_brand == "zeekr":
                    images = zeekr_generate_images(
                        color=sel_zcolor,
                        interior_image_url=(sel_zint or {}).get("image") or sel_zvariant["interiorImage"],
                        interior_image_2=(sel_zint or {}).get("image2", ""),
                    )
                    cfg = {
                        "brand": "Zeekr",
                        "model": sel_zmodel["modelName"],
                        "color": sel_zcolor["name"],
                        "detail": sel_zvariant["versionName"],
                        "zip_prefix": f"Zeekr_{sel_zmodel['modelId']}_{sel_zcolor['code']}",
                    }
                elif selected_brand == "byd":
                    images = byd_generate_images(color=sel_bcolor, interior_images=(sel_bint or {}).get("images", []))
                    cfg = {
                        "brand": "BYD",
                        "model": sel_bmodel["modelName"],
                        "color": sel_bcolor["name"],
                        "detail": sel_bvariant["versionName"],
                        "zip_prefix": f"BYD_{sel_bmodel['modelId']}_{sel_bcolor['code']}",
                    }
                elif selected_brand == "audi":
                    acolor_code = sel_acolor["code"]
                    awheel_code = ",".join(x for x in (audi_equipment, sel_awheel["code"] if not sel_awheel.get("serie") else "") if x)
                    images = audi_generate_images(
                        model_code=amodel_code,
                        color_code=acolor_code,
                        upholstery_code=adefault_upholstery,
                        wheel_code=awheel_code,
                    )
                    cfg = {
                        "brand": "Audi",
                        "model": selected_avariant.get("name"),
                        "color": sel_acolor.get("name"),
                        "detail": sel_awheel.get("title"),
                        "zip_prefix": f"Audi_{amodel_code}_{acolor_code}",
                    }
                elif selected_brand == "bmw":
                    bmwcolor_code = sel_bmwcolor["code"]
                    bmwwheel_code = sel_bmwwheel["code"]
                    images = bmw_generate_images(
                        model_code=bmw_model_code,
                        base_options=bmw_base_options,
                        color_code=bmwcolor_code,
                        wheel_code=bmwwheel_code,
                        effect_date=bmw_effect_date,
                    )
                    cfg = {
                        "brand": "BMW",
                        "model": selected_bmwvariant.get("name"),
                        "color": sel_bmwcolor.get("name"),
                        "detail": sel_bmwwheel.get("name"),
                        "zip_prefix": f"BMW_{bmw_model_code}_{bmwcolor_code}",
                    }
                elif selected_brand == "hyundai":
                    images = hyundai_generate_images(color=sel_hcolor, model_id=sel_hmodel["groupCode"], version_id=sel_hvariant["modelCode"], interior_code=(sel_hint or {}).get("code", ""))
                    cfg = {
                        "brand": "Hyundai",
                        "model": sel_hmodel["groupName"],
                        "color": sel_hcolor["name"],
                        "detail": sel_hvariant["variantName"],
                        "zip_prefix": f"Hyundai_{sel_hvariant['modelCode']}_{sel_hcolor['code']}",
                    }
                elif selected_brand == "mercedes":
                    images = mercedes_generate_images(
                        variant=mvariant,
                        color_code=sel_mcolor["code"],
                        wheel_code=sel_mwheel["code"],
                        interior_code=(sel_mint or {}).get("code", ""),
                    )
                    cfg = {
                        "brand": "Mercedes-Benz",
                        "model": sel_mmodel["groupName"],
                        "color": sel_mcolor["name"],
                        "detail": f"{mvariant['variantName']} · {sel_mwheel['name']}",
                        "zip_prefix": f"Mercedes_{mvariant['modelCode']}_{sel_mcolor['code']}",
                    }
                elif selected_brand == "mini":
                    minicolor_code = sel_minicolor["code"]
                    miniwheel_code = sel_miniwheel["code"]
                    images = mini_generate_images(
                        model_code=mini_model_code,
                        base_options=mini_base_options,
                        color_code=minicolor_code,
                        wheel_code=miniwheel_code,
                        effect_date=mini_effect_date,
                    )
                    cfg = {
                        "brand": "MINI",
                        "model": selected_minivariant.get("name"),
                        "color": sel_minicolor.get("name"),
                        "detail": sel_miniwheel.get("name"),
                        "zip_prefix": f"MINI_{mini_model_code}_{minicolor_code}",
                    }
                elif selected_brand == "nissan":
                    images = nissan_generate_images(
                        model_name=sel_nmodel["modelName"],
                        color=sel_ncolor,
                        interior_images=(sel_nint or {}).get("images", []),
                    )
                    cfg = {
                        "brand": "Nissan",
                        "model": sel_nmodel["modelName"],
                        "color": sel_ncolor["name"],
                        "detail": sel_nversion["versionName"],
                        "zip_prefix": f"Nissan_{sel_nmodel['modelName'].replace(' ', '-')}_{sel_ncolor['code']}",
                    }
                elif selected_brand == "skoda":
                    scolor_code = sel_scolor["code"]
                    swheel_code = ",".join(x for x in (skoda_equipment, sel_swheel["code"] if not sel_swheel.get("serie") else "") if x)
                    images = skoda_generate_images(
                        model_code=skoda_model_code,
                        color_code=scolor_code,
                        upholstery_code=skoda_default_upholstery,
                        wheel_code=swheel_code,
                    )
                    cfg = {
                        "brand": "Škoda",
                        "model": selected_svariant.get("name"),
                        "color": sel_scolor.get("name"),
                        "detail": sel_swheel.get("title"),
                        "zip_prefix": f"Skoda_{skoda_model_code}_{scolor_code}",
                    }
                elif selected_brand == "geely":
                    images = geely_generate_images(sel_gmodel, sel_gcolor["slug"])
                    cfg = {
                        "brand": "Geely",
                        "model": sel_gmodel["modelName"],
                        "color": sel_gcolor["name"],
                        "detail": f"{sel_gversion['name']} ({sel_gversion['spec']})",
                        "zip_prefix": f"Geely_{sel_gmodel['modelSlug']}_{sel_gcolor['slug']}",
                    }
                elif selected_brand == "alpine":
                    images = alpine_generate_images(
                        configurator_url=sel_almodel["configuratorUrl"],
                        conf_uri=sel_alvariant["confURI"],
                        color_code=sel_alcolor["code"],
                        wheel_code=sel_alwheel["code"],
                        upholstery_code=(sel_alpine_int or {}).get("code", ""),
                    )
                    cfg = {
                        "brand": "Alpine",
                        "model": sel_almodel["modelName"],
                        "color": sel_alcolor["name"],
                        "detail": sel_alvariant["versionName"],
                        "zip_prefix": f"Alpine_{sel_almodel['modelId']}_{sel_alcolor['code']}",
                    }
                else:
                    images = xpeng_generate_images(
                        sel_xcolor,
                        panoramas=[i["panorama"] for i in ([sel_xint] if sel_xint else sel_xversion.get("interiors", [])) if i.get("panorama")],
                    )
                    cfg = {
                        "brand": "XPENG",
                        "model": sel_xmodel["modelName"],
                        "color": sel_xcolor["name"],
                        "detail": sel_xversion["versionName"],
                        "zip_prefix": f"XPENG_{sel_xmodel['modelCode']}_{sel_xcolor['code']}",
                    }

                if images and has_template():
                    # imagens de interior/detalhe de jante não são uma foto de
                    # produto isolada (não têm pneus/chão a recortar) — a
                    # lógica de fundo branco + logo + sombra não se aplica,
                    # mas ainda assim são ajustadas ao mesmo tamanho de
                    # ficheiro das exteriores (letterbox, sem tocar no
                    # conteúdo), para que o ZIP saia todo com o mesmo formato.
                    keep_bg = selected_brand in _KEEP_BACKGROUND_BRANDS

                    def _process(item):
                        k, v = item
                        if any(m in k for m in _NO_COMPOSITE_MARKERS):
                            return k, standardize_only(v)
                        return k, composite(v, keep_background=keep_bg)

                    with ThreadPoolExecutor(max_workers=4) as ex:
                        images = dict(ex.map(_process, images.items()))
        except Exception as e:
            st.error(f"Não foi possível gerar as imagens: {e}")
            images = None

        if images:
            st.session_state.generated_images = images
            st.session_state.generated_config = cfg
            st.session_state.gen_id = st.session_state.get("gen_id", 0) + 1
        else:
            st.error("Não foi possível gerar as imagens. Verifica a ligação.")

    if st.session_state.generated_images:
        images = st.session_state.generated_images
        cfg    = st.session_state.generated_config
        st.caption(f"**{cfg['model']}** · Cor: {cfg['color']} · {cfg['detail']}")
        st.caption(f"{len(images)} imagens geradas — desmarca as que não queres antes de descarregar.")

        gen_id = st.session_state.gen_id
        view_keys = list(images.keys())
        selection: dict[str, bool] = {}
        COLS_PER_ROW = 4
        for row_start in range(0, len(view_keys), COLS_PER_ROW):
            row_keys = view_keys[row_start:row_start + COLS_PER_ROW]
            cols = st.columns(COLS_PER_ROW)
            for col, key in zip(cols, row_keys):
                with col:
                    st.image(images[key], caption=_pretty_label(key), width="stretch")
                    selection[key] = st.checkbox("Incluir", value=True, key=f"imgchk_{gen_id}_{key}")

        selected_images = {k: v for k, v in images.items() if selection.get(k, True)}

        st.divider()
        zip_name  = f"{cfg['zip_prefix']}.zip"
        if cfg["brand"] == "VW":
            zip_bytes = vw_images_to_zip(selected_images, zip_name)
        elif cfg["brand"] == "Peugeot":
            zip_bytes = peugeot_images_to_zip(selected_images, zip_name)
        elif cfg["brand"] == "Renault":
            zip_bytes = renault_images_to_zip(selected_images, zip_name)
        elif cfg["brand"] == "Dacia":
            zip_bytes = dacia_images_to_zip(selected_images, zip_name)
        elif cfg["brand"] == "Opel":
            zip_bytes = opel_images_to_zip(selected_images, zip_name)
        elif cfg["brand"] == "Zeekr":
            zip_bytes = zeekr_images_to_zip(selected_images, zip_name)
        elif cfg["brand"] == "BYD":
            zip_bytes = byd_images_to_zip(selected_images, zip_name)
        elif cfg["brand"] == "Audi":
            zip_bytes = audi_images_to_zip(selected_images, zip_name)
        elif cfg["brand"] == "BMW":
            zip_bytes = bmw_images_to_zip(selected_images, zip_name)
        elif cfg["brand"] == "Hyundai":
            zip_bytes = hyundai_images_to_zip(selected_images, zip_name)
        elif cfg["brand"] == "Mercedes-Benz":
            zip_bytes = mercedes_images_to_zip(selected_images, zip_name)
        elif cfg["brand"] == "MINI":
            zip_bytes = mini_images_to_zip(selected_images, zip_name)
        elif cfg["brand"] == "Nissan":
            zip_bytes = nissan_images_to_zip(selected_images, zip_name)
        elif cfg["brand"] == "Škoda":
            zip_bytes = skoda_images_to_zip(selected_images, zip_name)
        elif cfg["brand"] == "Geely":
            zip_bytes = geely_images_to_zip(selected_images, zip_name)
        elif cfg["brand"] == "Alpine":
            zip_bytes = alpine_images_to_zip(selected_images, zip_name)
        else:
            zip_bytes = xpeng_images_to_zip(selected_images, zip_name)
        if not selected_images:
            st.warning("Nenhuma imagem seleccionada — marca pelo menos uma para poderes descarregar.")
        st.download_button(
            label=f"**Download ZIP ({len(selected_images)} imagens)**",
            data=zip_bytes,
            file_name=zip_name,
            mime="application/zip",
            icon="📥",
            use_container_width=True,
            disabled=not selected_images,
            key="zip_download",
        )

    else:
        st.info("Selecciona um modelo e clica em **Gerar Imagens**.")
        if selected_brand == "vw":
            color_code = sel_color["code"]
            wheel_code = ",".join(x for x in (vw_equipment, sel_wheel["code"] if not sel_wheel.get("serie") else "") if x)
            st.image(
                f"https://cdn.nwi-ms.com/media/pt/V/mc/{model_code}/model/exteriorfront.webp"
                f"?F={color_code}&P={default_upholstery}&M={wheel_code}&size=L",
                caption=f"Preview — {selected_variant.get('name')}",
                width="stretch",
            )
        elif selected_brand == "peugeot":
            v = sel_variant["lcdv16"]; c = sel_pcolor["id"]; t = peugeot_trim
            st.image(
                f"https://visuel3d-secure.peugeot.com/V3DImage.ashx"
                f"?client=SOLVCG&ratio=1&format=jpg&quality=90&width=900&height=500"
                f"&back=0&view=006&version={v}&color={c}&trim={t}&mkt=PT",
                caption=f"Preview — {sel_model['modelName']}",
                width="stretch",
            )
        elif selected_brand == "renault":
            st.caption(f"{sel_rmodel['modelName']} · {sel_rvariant['versionName']} · {sel_rcolor['name']}")
        elif selected_brand == "dacia":
            st.caption(f"{sel_dmodel['modelName']} · {sel_dvariant['versionName']} · {sel_dcolor['name']}")
        elif selected_brand == "opel":
            st.caption(f"{sel_omodel['modelName']} · {sel_ovariant['versionName']} · {sel_ocolor['name']}")
        elif selected_brand == "zeekr":
            st.caption(f"{sel_zmodel['modelName']} · {sel_zvariant['versionName']} · {sel_zcolor['name']}")
        elif selected_brand == "byd":
            st.caption(f"{sel_bmodel['modelName']} · {sel_bvariant['versionName']} · {sel_bcolor['name']}")
        elif selected_brand == "audi":
            acolor_code = sel_acolor["code"]
            awheel_code = ",".join(x for x in (audi_equipment, sel_awheel["code"] if not sel_awheel.get("serie") else "") if x)
            st.image(
                f"https://cdn.nwi-ms.com/media/pt/A/mc/{amodel_code}/model/front.webp"
                f"?F={acolor_code}&P={adefault_upholstery}&M={awheel_code}&size=L",
                caption=f"Preview — {selected_avariant.get('name')}",
                width="stretch",
            )
        elif selected_brand == "bmw":
            st.caption(f"{selected_bmwvariant.get('name')} · {sel_bmwcolor['name']} · {sel_bmwwheel['name']}")
        elif selected_brand == "hyundai":
            st.caption(f"{sel_hmodel['groupName']} · {sel_hvariant['variantName']} · {sel_hcolor['name']}")
        elif selected_brand == "mercedes":
            st.caption(f"{mvariant['variantName']} · {sel_mcolor['name']} · {sel_mwheel['name']}")
        elif selected_brand == "mini":
            st.caption(f"{selected_minivariant.get('name')} · {sel_minicolor['name']} · {sel_miniwheel['name']}")
        elif selected_brand == "nissan":
            st.caption(f"{sel_nmodel['modelName']} · {sel_nversion['versionName']} · {sel_ncolor['name']}")
        elif selected_brand == "skoda":
            scolor_code = sel_scolor["code"]
            swheel_code = ",".join(x for x in (skoda_equipment, sel_swheel["code"] if not sel_swheel.get("serie") else "") if x)
            st.image(
                f"https://cdn.nwi-ms.com/media/pt/C/mc/{skoda_model_code}/model/front.webp"
                f"?F={scolor_code}&P={skoda_default_upholstery}&M={swheel_code}&size=L",
                caption=f"Preview — {selected_svariant.get('name')}",
                width="stretch",
            )
        elif selected_brand == "geely":
            st.caption(f"{sel_gmodel['modelName']} · {sel_gversion['name']} · {sel_gcolor['name']}")
        elif selected_brand == "alpine":
            st.caption(f"{sel_almodel['modelName']} · {sel_alvariant['versionName']} · {sel_alcolor['name']} · {sel_alwheel['name']}")
        else:
            st.caption(f"{sel_xmodel['modelName']} · {sel_xversion['versionName']} · {sel_xcolor['name']}")
