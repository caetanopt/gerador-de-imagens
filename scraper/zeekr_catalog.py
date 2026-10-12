"""
Catálogo Zeekr — configurador próprio da Caetano (configurador.zeekr.pt).

Ao contrário das outras marcas, não há GraphQL nem visualizador 3D:
todo o catálogo vive num único JSON estático e cada foto é um PNG
pré-gerado com um caminho previsível. Não há jantes seleccionáveis
(aparecem só como texto no equipamento) nem selector de cor de
interior (tal como nas outras marcas, usa-se sempre a cor de série).

Ângulos exterior confirmados visualmente: 1=3/4 frente, 2=lado, 3=traseira.
Há também uma imagem "chips" por cor (esfera de pré-visualização usada no
próprio picker de cor do configurador, classe `colour-picker__sphere`) —
mesmo padrão de nome, mas com sufixo "-chips-" em vez do número de ângulo.
Confirmado (GET directo) que é um ficheiro distinto das 3 fotos grandes
(bastante mais pequeno), usado como `swatchUrl`.
A cor exterior desliza de forma simples e fiável (minúsculas + hífen).
A cor de interior NÃO — o nome do ficheiro tem um sufixo de material
(ex: "-leather") que não está no nome apresentado — por isso a imagem
de interior é sempre obtida por navegação real (Playwright), nunca
adivinhada.

Cache em data/zeekr_catalog.json.
"""
import json
import re
import ssl
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_PATH = DATA_DIR / "zeekr_catalog.json"
CATALOG_JSON_URL = "https://configurador.zeekr.pt/data/zeekr_configurador.json"
IMAGE_BASE = "https://configurador.zeekr.pt/images/configurator"

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _slugify(name: str) -> str:
    s = name.lower().replace("&", "").strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _fetch_raw_catalog() -> dict:
    req = urllib.request.Request(CATALOG_JSON_URL, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=20) as r:
        return json.load(r)


def _exterior_image_urls(image_folder: str, filename_slug: str, version_name: str, color_name: str) -> dict:
    version_enc = version_name.replace(" ", "%20")
    color_slug = _slugify(color_name)
    base = f"{IMAGE_BASE}/{image_folder}/{version_enc}/Exterior/zeekr-{filename_slug}-exterior"
    return {
        "3_4_frente": f"{base}-1-{color_slug}.png",
        "lado": f"{base}-2-{color_slug}.png",
        "traseira": f"{base}-3-{color_slug}.png",
    }


def _exterior_swatch_url(image_folder: str, filename_slug: str, version_name: str, color_name: str) -> str:
    """URL da esfera de pré-visualização de cor (imagem "chips" do colour-picker)."""
    version_enc = version_name.replace(" ", "%20")
    color_slug = _slugify(color_name)
    return f"{IMAGE_BASE}/{image_folder}/{version_enc}/Exterior/zeekr-{filename_slug}-exterior-chips-{color_slug}.png"


def _default_exterior_filename_slug(page) -> str:
    """
    O nome do modelo dentro do ficheiro (ex: "7GT" ou "x") não segue uma
    regra fixa de maiúsculas/minúsculas — varia por modelo (confirmado:
    "zeekr-7GT-exterior-..." mas "zeekr-x-cover..."). Em vez de adivinhar,
    extrai-se o valor real do URL da imagem exterior actualmente mostrada.
    """
    imgs = page.eval_on_selector_all("img", "els => els.map(e => e.src)")
    for src in imgs:
        if "/Exterior/" in src and "-chips-" not in src:
            m = re.search(r"zeekr-(.+?)-exterior-\d", src)
            if m:
                return m.group(1)
    return ""


def _try_click(page, selectors, timeout=3000, force=False):
    for sel in selectors:
        try:
            page.click(sel, timeout=timeout, force=force)
            return sel
        except Exception:
            continue
    return None


def _default_interior_image(page) -> str:
    """Lê o src da 1ª imagem de interior actualmente mostrada (a cor de série já vem seleccionada por defeito)."""
    imgs = page.eval_on_selector_all("img", "els => els.map(e => e.src)")
    for src in imgs:
        if "/Interior/" in src and "-chips-" not in src:
            return src
    return ""


_INTERIOR_EXTS = [".png", ".jpg", ".jpeg"]


def _image_exists(url: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={**_HEADERS, "Referer": "https://configurador.zeekr.pt/"})
        with urllib.request.urlopen(req, context=_ssl_ctx, timeout=20) as r:
            head = r.read(4)
        return head[:2] == bytes.fromhex("ffd8") or head in (bytes.fromhex("89504e47"), b"RIFF")
    except Exception:
        return False


def _interior_chip_slugs(page) -> list[str]:
    """Slugs exactos das cores de interior da versão, lidos das miniaturas
    ("-interior-chips-<slug>.png") que o configurador mostra — o slug não
    se deduz do nome apresentado (ex.: "Charcoal black & White" ->
    "charcoal-black-polar-white-leather")."""
    srcs = page.eval_on_selector_all("img", "els => els.map(e => e.src)")
    out = []
    for src in srcs:
        if "/Interior/" in src and "-interior-chips-" in src:
            slug = src.split("-interior-chips-")[1].rsplit(".", 1)[0]
            if slug not in out:
                out.append(slug)
    return out


def interior_options(default_image: str, interior_colors: list[dict], chip_slugs: list[str]) -> list[dict]:
    """
    Cores de interior da versão (JSON do configurador) com as fotos de cada
    uma. A foto de interior pode ser .png ou .jpg consoante a cor (ex.:
    001 Sport "Charcoal Grey & Orange" é .jpg) — testam-se as extensões.
    A ordem das miniaturas coincide com a de interior_colors.
    """
    if not default_image or not interior_colors:
        return []
    base = default_image.split("-interior-1-")[0]
    default_slug = default_image.split("-interior-1-")[1].rsplit(".", 1)[0]
    slugs = chip_slugs or [default_slug]
    out = []
    for i, ic in enumerate(interior_colors):
        slug = slugs[i] if i < len(slugs) else None
        if not slug:
            continue
        img1 = default_image if slug == default_slug else next(
            (base + "-interior-1-" + slug + ext for ext in _INTERIOR_EXTS if _image_exists(base + "-interior-1-" + slug + ext)), None)
        if not img1:
            continue
        img2 = next((base + "-interior-2-" + slug + ext for ext in _INTERIOR_EXTS if _image_exists(base + "-interior-2-" + slug + ext)), "")
        chip = base + "-interior-chips-" + slug + ".png"
        out.append({"code": slug, "name": ic["name"], "price": ic.get("price", 0) or 0,
                    "image": img1, "image2": img2, "swatchUrl": chip})
    return out


def _build_catalog() -> dict:
    print("A construir catálogo Zeekr...")
    raw = _fetch_raw_catalog()
    models_out = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
        page = ctx.new_page()

        for model_full_name, model_data in raw.items():
            suffix = model_full_name.replace("ZEEKR ", "").strip()
            nav_slug = suffix.lower()
            image_folder = suffix
            print(f"\n  {model_full_name} ({nav_slug})")

            page.goto(f"https://configurador.zeekr.pt/{nav_slug}", wait_until="networkidle", timeout=40000)
            time.sleep(1.5)
            _try_click(page, ["#onetrust-accept-btn-handler", "button:has-text('Aceitar')"], timeout=3000)
            time.sleep(1)

            versions_out = []
            for i, v in enumerate(model_data.get("versions", [])):
                version_name = v["version"]
                print(f"    versão: {version_name}")
                if i > 0:
                    clicked = _try_click(page, [f"text={version_name}"], timeout=5000, force=True)
                    if not clicked:
                        print(f"      ERRO: não consegui seleccionar a versão, a saltar")
                        continue
                    time.sleep(1.5)

                interior_image = _default_interior_image(page)
                if not interior_image:
                    print("      aviso: sem imagem de interior encontrada")

                filename_slug = _default_exterior_filename_slug(page) or nav_slug
                colors_out = []
                for c in v.get("exterior_colors", []):
                    colors_out.append({
                        "code": _slugify(c["name"]),
                        "name": c["name"],
                        "price": c.get("price", 0) or 0,
                        "images": _exterior_image_urls(image_folder, filename_slug, version_name, c["name"]),
                        "swatchUrl": _exterior_swatch_url(image_folder, filename_slug, version_name, c["name"]),
                    })

                versions_out.append({
                    "versionName": version_name,
                    "price": v.get("pvp", 0),
                    "colors": colors_out,
                    "interiorImage": interior_image,
                    "interiors": interior_options(interior_image, v.get("interior_colors", []), _interior_chip_slugs(page)),
                })

            models_out.append({
                "modelId": nav_slug,
                "modelName": model_full_name,
                "variants": versions_out,
            })

        browser.close()

    catalog = {"models": models_out}
    DATA_DIR.mkdir(exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"\nCatálogo guardado: {CACHE_PATH}")
    return catalog


def build_catalog(force: bool = False) -> dict:
    if not force and CACHE_PATH.exists():
        print(f"Catálogo em cache: {CACHE_PATH}")
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return _build_catalog()


def load_catalog() -> dict:
    return build_catalog(force=False)


if __name__ == "__main__":
    cat = build_catalog(force=True)
    total_variants = sum(len(m["variants"]) for m in cat["models"])
    print(f"\nTotal: {len(cat['models'])} modelos, {total_variants} versões")
    for m in cat["models"]:
        print(f"\n{m['modelName']} ({m['modelId']})")
        for v in m["variants"]:
            print(f"  [{v['versionName']}] {len(v['colors'])} cor(es), interior={'ok' if v['interiorImage'] else 'FALTA'}")
