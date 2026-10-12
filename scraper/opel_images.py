"""
Descarrega imagens de uma configuração Opel.
Usa o visualizador 3D: visual3d-secure.opel-vauxhall.com (mesma
tecnologia V3D da Peugeot, domínio diferente).

Códigos de view válidos (varrimento 000-199, deduplicado por hash e por
semelhança visual):
- 030-053: volta 360° real, 24 fotogramas a 15° (048 = frente recta,
  036 = traseira recta). Usam-se todos — são os únicos exteriores.
- 000/001/002/003: vistas "fixas" que repetem fotogramas da volta
  (000 = 001 = 046, 002 = 052, 003 ~ 034) — ficam de fora.
- 004: vista de cima com as rodas em falta (render partido) — fora.
- 010/011/012: interior (tablier, bancos dianteiros, bancos traseiros).
- 020-025: faces de um panorama cúbico do interior (tecto, pilar, chão)
  — não servem como foto, ficam de fora.
Views inexistentes devolvem um placeholder de 100x100, que se descarta.
Tudo vem em fundo branco liso com sombra nativa (composite com
keep_background=True em app.py).
"""
import io
import ssl
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

CDN = "https://visual3d-secure.opel-vauxhall.com/V3DImage.ashx"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/webp,image/*,*/*",
    "Referer": "https://store.opel.pt/",
}

# volta 360: código 048 = frente (0°), cada código seguinte roda 15° no
# sentido frente -> lado esquerdo -> traseira -> lado direito.
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


def _rotation_views() -> dict[str, str]:
    """label -> código, a começar no 3/4 frente esquerda (45°)."""
    views = {}
    for step in range(24):
        deg = (45 + step * 15) % 360
        code = 30 + (18 + deg // 15) % 24
        views[_ROTATION_NAMES.get(deg, f"rotacao_{deg:03d}")] = f"{code:03d}"
    return views


VIEWS = {
    **_rotation_views(),
    "interior": "010",
    "interior_bancos": "011",
    "interior_bancos_traseiros": "012",
}

_PLACEHOLDER_MAX_WIDTH = 200


def _image_url(version: str, color_id: str, trim_id: str, view_code: str, wheel_code: str = "") -> str:
    url = (
        f"{CDN}?client=SOLVCG&ratio=1&format=jpg&quality=90"
        f"&width=1450&height=670&back=0"
        f"&view={view_code}&version={version}&color={color_id}&trim={trim_id}&mkt=PT"
    )
    if wheel_code:
        url += f"&opt1={wheel_code}"
    return url


def fetch_image_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=20) as r:
        data = r.read()
    if not data:
        raise ValueError(f"Imagem vazia: {url}")
    return data


def generate_images(
    version: str,
    color_id: str,
    trim_id: str,
    wheel_code: str = "",
    **_,
) -> dict[str, bytes]:
    def fetch(item):
        label, view_code = item
        url = _image_url(version, color_id, trim_id, view_code, wheel_code)
        try:
            data = fetch_image_bytes(url)
            if Image.open(io.BytesIO(data)).width <= _PLACEHOLDER_MAX_WIDTH:
                return label, None
            return label, data
        except Exception as e:
            print(f"  ERRO {label} (view {view_code}): {e}")
            return label, None

    with ThreadPoolExecutor(max_workers=8) as ex:
        fetched = list(ex.map(fetch, VIEWS.items()))
    return {label: data for label, data in fetched if data}


def images_to_zip(images: dict[str, bytes], zip_name: str = "imagens_opel.zip") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in images.items():
            ext = "jpg" if data[:3] == b"\xff\xd8\xff" else "webp"
            zf.writestr(f"{label}.{ext}", data)
    return buf.getvalue()


if __name__ == "__main__":
    import sys
    version    = sys.argv[1] if len(sys.argv) > 1 else "1GJOA5HJLKB0A0J2"
    color_id   = sys.argv[2] if len(sys.argv) > 2 else "0MM00NAV"
    trim_id    = sys.argv[3] if len(sys.argv) > 3 else "0PBP0RFX"
    wheel_code = sys.argv[4] if len(sys.argv) > 4 else ""

    print(f"A gerar: version={version}  cor={color_id}  trim={trim_id}  jante={wheel_code or '(série)'}")
    images = generate_images(version, color_id, trim_id, wheel_code)
    OUTPUT_DIR.mkdir(exist_ok=True)
    for label, data in images.items():
        path = OUTPUT_DIR / f"opel_{version}_{label}.jpg"
        path.write_bytes(data)
        print(f"  {path.name} ({len(data):,} bytes)")
