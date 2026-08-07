"""
Descarrega as imagens de uma configuração XPENG.

Só existem 2 ângulos reais por cor (confirmado na própria API, em todos
os modelos): 3/4 frente e lado — sem frente recta, sem traseira, sem
interior fotográfico (ver scraper/xpeng_catalog.py para o porquê). Os
URLs já vêm resolvidos no catálogo, na ordem confirmada visualmente
[3/4 frente, lado].
"""
import io
import ssl
import urllib.request
import zipfile

_ssl_ctx = ssl.create_default_context()
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_ANGLE_LABELS = ["3_4_frente", "lado"]


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        data = r.read()
    if not data:
        raise ValueError(f"Imagem vazia: {url}")
    return data


def generate_images(color: dict, **_) -> dict[str, bytes]:
    """Gera as imagens XPENG para a cor escolhida."""
    results = {}
    for label, url in zip(_ANGLE_LABELS, color.get("images", [])):
        try:
            results[label] = _fetch(url)
        except Exception as e:
            print(f"  ERRO imagem XPENG {label}: {e}")
    return results


def images_to_zip(images: dict[str, bytes], zip_name: str = "imagens.zip") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in images.items():
            zf.writestr(f"{label}.webp", data)
    return buf.getvalue()
