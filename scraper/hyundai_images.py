"""
Descarrega as imagens de uma configuração Hyundai. Os URLs das 4 vistas
já vêm resolvidos no catálogo (ver hyundai_catalog.py — cada cor guarda
os 4 frames da volta de 360° correspondentes aos ângulos-padrão), por
isso aqui só é preciso fazer o download.
"""
import io
import ssl
import urllib.request
import zipfile
from pathlib import Path

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


def generate_images(color: dict, **_) -> dict[str, bytes]:
    """Gera as 4 imagens Hyundai para a cor escolhida (já inclui os URLs)."""
    results = {}
    for label, url in color.get("images", {}).items():
        try:
            results[label] = _fetch_image_bytes(url)
        except Exception as e:
            print(f"  ERRO {label}: {e}")
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
