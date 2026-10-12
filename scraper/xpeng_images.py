"""
Descarrega as imagens de uma configuração XPENG.

Desde 2026-09 a galeria da API tem 5 fotos por cor (antes 2), sempre na
mesma ordem (confirmado visualmente em G6, G9 e P7+): 3/4 frente, frente,
lado direito, traseira, lado esquerdo — PNG com alpha e sombra nativa.
Cores antigas ainda só com 2 fotos seguem a ordem antiga [3/4 frente, lado].
Interior: vistas extraídas do panorama 360° da versão (scraper/panorama.py).
"""
import io
import ssl
import urllib.request
import zipfile

from scraper import panorama

_ssl_ctx = ssl.create_default_context()
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_ANGLE_LABELS = ["3_4_frente", "frente", "lado_direito", "traseira", "lado_esquerdo"]
_ANGLE_LABELS_OLD = ["3_4_frente", "lado"]


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        data = r.read()
    if not data:
        raise ValueError(f"Imagem vazia: {url}")
    return data


def generate_images(color: dict, panoramas: list[str] | None = None, **_) -> dict[str, bytes]:
    """Gera as imagens XPENG para a cor escolhida (+ interior do panorama da versão)."""
    urls = color.get("images", [])
    labels = _ANGLE_LABELS if len(urls) > 2 else _ANGLE_LABELS_OLD
    results = {}
    for label, url in zip(labels, urls):
        try:
            results[label] = _fetch(url)
        except Exception as e:
            print(f"  ERRO imagem XPENG {label}: {e}")
    if panoramas:
        try:
            results.update(panorama.interior_views(panoramas, _fetch))
        except Exception as e:
            print(f"  ERRO interior XPENG: {e}")
    return results


def images_to_zip(images: dict[str, bytes], zip_name: str = "imagens.zip") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in images.items():
            zf.writestr(f"{label}.webp", data)
    return buf.getvalue()
