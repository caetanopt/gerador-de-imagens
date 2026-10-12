"""
Descarrega as imagens de uma configuração Geely.

Ficheiros estáticos, sem API — a sequência de 360° tem sempre exactamente
24 fotogramas por cor (1-24; o 0 e o 25 não existem), em
`/assets/360/{asset_slug}-{color_slug}/{n}.webp`, a 15° cada: 1 = frente,
4 = 3/4 frente esq., 7 = lado esq., 13 = traseira, 19 = lado dir.
Fotos de 4431px em fundo branco liso com sombra nativa — compostas sem
recorte (keep_background=True em app.py). Usam-se os 24 fotogramas. A
imagem de interior é uma foto estática única por modelo (não varia por
cor nem versão — ver geely_catalog.py).
"""
import io
import ssl
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

BASE_URL = "https://www.geely-auto.pt"

_ROTATION_NAMES = {
    0: "frente",
    45: "3_4_frente_esquerda",
    90: "lado_esquerdo",
    135: "3_4_traseira_esquerda",
    180: "traseira",
    225: "3_4_traseira_direita",
    270: "lado_direito",
    315: "3_4_frente_direita",
}

# label -> nº do fotograma, a começar no 3/4 frente esquerda (45°)
_ANGLES = {}
for _step in range(24):
    _deg = (45 + _step * 15) % 360
    _ANGLES[_ROTATION_NAMES.get(_deg, f"rotacao_{_deg:03d}")] = _deg // 15 + 1

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
    jobs = [
        (label, f"{BASE_URL}/assets/360/{variant['assetSlug']}-{color_slug}/{n}.webp")
        for label, n in _ANGLES.items()
    ]
    if variant.get("interiorImage"):
        jobs.append(("interior", variant["interiorImage"]))

    def fetch(job):
        label, url = job
        try:
            return label, _fetch(url)
        except Exception as e:
            print(f"  ERRO imagem Geely {label}: {e}")
            return label, None

    with ThreadPoolExecutor(max_workers=8) as ex:
        fetched = list(ex.map(fetch, jobs))
    return {label: data for label, data in fetched if data}


def images_to_zip(images: dict[str, bytes], zip_name: str = "imagens.zip") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in images.items():
            zf.writestr(f"{label}.webp", data)
    return buf.getvalue()
