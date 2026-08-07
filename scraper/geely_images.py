"""
Descarrega as imagens de uma configuração Geely.

Ficheiros estáticos, sem API — a sequência de 360° tem sempre exactamente
24 fotogramas por cor (confirmado — o fotograma 25 já não existe), em
`/assets/360/{asset_slug}-{color_slug}/{n}.webp`. Ângulos-âncora
escolhidos por número de fotograma (confirmado visualmente, consistente
entre o E5 e o Starray EM-i): frente=1, 3/4 frente=4, lado=7, traseira=13.
Os restantes 4 fotogramas (10, 16, 19, 22) completam um conjunto de 8
espaçados uniformemente pela volta completa, sem nome semântico
confirmado. A imagem de interior é uma foto estática única por modelo
(não varia por cor nem versão — ver geely_catalog.py).
"""
import io
import ssl
import urllib.request
import zipfile

BASE_URL = "https://www.geely-auto.pt"

_ANGLES = {
    "frente": 1,
    "3_4_frente": 4,
    "lado": 7,
    "frame_10": 10,
    "traseira": 13,
    "frame_16": 16,
    "frame_19": 19,
    "frame_22": 22,
}

_ssl_ctx = ssl.create_default_context()
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        data = r.read()
    if not data:
        raise ValueError(f"Imagem vazia: {url}")
    return data


def generate_images(variant: dict, color_slug: str, **_) -> dict[str, bytes]:
    """Gera as imagens Geely para a configuração dada."""
    results = {}
    for label, n in _ANGLES.items():
        url = f"{BASE_URL}/assets/360/{variant['assetSlug']}-{color_slug}/{n}.webp"
        try:
            results[label] = _fetch(url)
        except Exception as e:
            print(f"  ERRO imagem Geely {label}: {e}")

    interior_url = variant.get("interiorImage")
    if interior_url:
        try:
            results["interior"] = _fetch(interior_url)
        except Exception as e:
            print(f"  ERRO interior Geely: {e}")

    return results


def images_to_zip(images: dict[str, bytes], zip_name: str = "imagens.zip") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in images.items():
            zf.writestr(f"{label}.webp", data)
    return buf.getvalue()
