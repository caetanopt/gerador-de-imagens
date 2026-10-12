"""
Descarrega imagens de uma configuração Peugeot.
Usa o visualizador 3D: visuel3d-secure.peugeot.com — mesma tecnologia V3D
da Opel, mas sem volta 360. Varrimento 000-099 deduplicado por hash:
códigos inexistentes devolvem a vista 000 (o antigo "006" era isso mesmo).
- 000-005: seis cenas exteriores distintas;
- 010-013: interior (tablier, bancos dianteiros, bancos traseiros, lateral);
- 020-025: faces de um panorama cúbico do interior (tecto, chão, encostos)
  — não servem como foto, ficam de fora.
Fundo branco liso com sombra nativa (keep_background=True em app.py).
O servidor respeita width/height — pede-se 2400x1110 (antes 1450x670).
"""
import hashlib, io, ssl, urllib.request, zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CDN = "https://visuel3d-secure.peugeot.com/V3DImage.ashx"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/webp,image/*,*/*",
    "Referer": "https://store.peugeot.pt/",
}

# As cenas são escolhidas modelo a modelo (ex.: no 208 o 005 é a 3/4
# traseira, no 3008 é uma 3/4 frente) — por isso os nomes são neutros.
VIEWS = {
    **{f"exterior_{i + 1}": f"{i:03d}" for i in range(6)},
    **{f"interior_{i + 1}": f"{10 + i:03d}" for i in range(4)},
}


def _image_url(version: str, color_id: str, trim_id: str, view_code: str) -> str:
    return (
        f"{CDN}?client=SOLVCG&ratio=1&format=jpg&quality=90"
        f"&width=2400&height=1110&back=0"
        f"&view={view_code}&version={version}&color={color_id}&trim={trim_id}&mkt=PT"
    )


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
    **_,
) -> dict[str, bytes]:
    def fetch(item):
        label, view_code = item
        try:
            return label, fetch_image_bytes(_image_url(version, color_id, trim_id, view_code))
        except Exception as e:
            print(f"  ERRO {label} (view {view_code}): {e}")
            return label, None

    with ThreadPoolExecutor(max_workers=8) as ex:
        fetched = list(ex.map(fetch, VIEWS.items()))

    # vista inexistente = cópia da 000 -> descarta repetidos
    results, seen = {}, set()
    for label, data in fetched:
        if not data:
            continue
        h = hashlib.md5(data).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        results[label] = data
    return results


def images_to_zip(images: dict[str, bytes], zip_name: str = "imagens_peugeot.zip") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in images.items():
            ext = "jpg" if data[:3] == b"\xff\xd8\xff" else "webp"
            zf.writestr(f"{label}.{ext}", data)
    return buf.getvalue()


if __name__ == "__main__":
    import sys
    version  = sys.argv[1] if len(sys.argv) > 1 else "1PP2A5HJLKB02PH2"
    color_id = sys.argv[2] if len(sys.argv) > 2 else "0MM00NEQ"
    trim_id  = sys.argv[3] if len(sys.argv) > 3 else "0PG90RFX"

    print(f"A gerar: version={version}  cor={color_id}  trim={trim_id}")
    images = generate_images(version, color_id, trim_id)
    OUTPUT_DIR.mkdir(exist_ok=True)
    for label, data in images.items():
        path = OUTPUT_DIR / f"peugeot_{version}_{label}.jpg"
        path.write_bytes(data)
        print(f"  {path.name} ({len(data):,} bytes)")
