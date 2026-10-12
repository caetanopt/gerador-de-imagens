"""
Descarrega as imagens de uma configuração Hyundai. Os URLs das 4 vistas
já vêm resolvidos no catálogo (ver hyundai_catalog.py — cada cor guarda
os 4 frames da volta de 360° correspondentes aos ângulos-padrão), por
isso aqui só é preciso fazer o download.
"""
import io
import json
import ssl
import urllib.request
import zipfile
from pathlib import Path

from scraper import panorama

REFERER = "https://www.hyundai.pt/"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

_ssl_ctx = ssl.create_default_context()

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/webp,image/*,*/*",
    "Referer": REFERER,
}


def _fetch_image_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        data = r.read()
    if not data:
        raise ValueError(f"Imagem vazia: {url}")
    return data


# Interior: o configurador não tem fotos de interior, só um panorama 360°
# por versão/cor de interior (endpoint "panomaricLI", assim mesmo) — ver
# scraper/panorama.py.
_CFG_BASE = "https://www.hyundai.pt/wp-json/cfg"


def _panorama_candidates(model_id: str, version_id: str, interior_code: str = "") -> list[str]:
    """Panoramas por ordem de preferência: o da cor de interior escolhida
    nesta versão e, a seguir, o da MESMA cor de interior noutras versões do
    modelo (muitas versões só têm o marcador "Brevemente disponível").
    Sem cor escolhida, usa a(s) cor(es) desta versão."""
    req = urllib.request.Request(f"{_CFG_BASE}/panomaricLI/{model_id}", headers={**_HEADERS, "Accept": "application/json"})
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        data = json.loads(r.read())
    colors = [c for entry in data for c in entry.get("colors", []) if c.get("panoramImg")]
    own = [c for c in colors if str(c.get("version")) == str(version_id)]
    wanted = {str(interior_code)} if interior_code else {str(c.get("idColor")) for c in own}
    own = [c for c in own if str(c.get("idColor")) in wanted]
    others = [c for c in colors if str(c.get("version")) != str(version_id) and str(c.get("idColor")) in wanted]
    out = []
    for c in own + others:
        if c["panoramImg"] not in out:
            out.append(c["panoramImg"])
    return out


def _interior_views(model_id: str, version_id: str, interior_code: str = "") -> dict[str, bytes]:
    return panorama.interior_views(_panorama_candidates(model_id, version_id, interior_code), _fetch_image_bytes)


def generate_images(color: dict, model_id: str = "", version_id: str = "", interior_code: str = "", **_) -> dict[str, bytes]:
    """Imagens Hyundai para a cor escolhida (URLs já no catálogo) + vistas
    de interior extraídas do panorama 360°, quando existe um real."""
    results = {}
    for label, url in color.get("images", {}).items():
        try:
            results[label] = _fetch_image_bytes(url)
        except Exception as e:
            print(f"  ERRO {label}: {e}")
    if model_id and version_id:
        try:
            results.update(_interior_views(model_id, version_id, interior_code))
        except Exception as e:
            print(f"  ERRO interior (panorama): {e}")
    return results


def images_to_zip(images: dict[str, bytes], zip_name: str = "imagens.zip") -> bytes:
    """Empacota as imagens num ZIP e devolve os bytes do ZIP."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in images.items():
            ext = "jpg" if data[:3] == b"\xff\xd8\xff" else "webp"
            zf.writestr(f"{label}.{ext}", data)
    return buf.getvalue()


if __name__ == "__main__":
    from scraper.hyundai_catalog import load_catalog

    catalog = load_catalog()
    variant = catalog["models"][0]["variants"][0]
    color = variant["colors"][0]
    print(f"A gerar imagens de teste: {variant['name']} — {color['name']}")
    images = generate_images(color=color)
    OUTPUT_DIR.mkdir(exist_ok=True)
    for label, data in images.items():
        path = OUTPUT_DIR / f"hyundai_{variant['modelCode']}_{color['code']}_{label}.webp"
        path.write_bytes(data)
        print(f"  {path.name} ({len(data):,} bytes)")
