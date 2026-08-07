"""
Descarrega imagens de uma configuração Opel.
Usa o visualizador 3D: visual3d-secure.opel-vauxhall.com (mesma
tecnologia V3D da Peugeot, domínio diferente).

Não há vista de frente/traseira a direito neste visualizador — só 3/4
frente, 3/4 traseira e perfil. Ao contrário da Peugeot (mesma tecnologia
V3D, mas sem rotação contínua), o Opel tem uma volta 360° real: os
códigos de view 030-053 (24 valores, confirmados por hash distinto)
formam uma sequência de rotação suave em incrementos de 15°. Extrai-se
um subconjunto de 8 fotogramas espaçados uniformemente por essa volta,
além das 4 vistas fixas (3/4 frente, lado, traseira, interior).
"""
import io
import ssl
import urllib.request
import zipfile
from pathlib import Path

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

# Mapeamento view code → label PT
VIEWS = {
    "3_4_frente": "001",
    "lado":       "002",
    "traseira":   "003",  # 3/4 traseira (não há traseira a direito)
    "interior":   "010",
}

# 8 fotogramas espaçados uniformemente pela volta de rotação real
# (view=030 a view=053, 24 valores no total, ~15°/fotograma).
_ROTATION_VIEWS = [f"{30 + round(i * 23 / 7):03d}" for i in range(8)]


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
    results = {}
    for label, view_code in VIEWS.items():
        url = _image_url(version, color_id, trim_id, view_code, wheel_code)
        try:
            data = fetch_image_bytes(url)
            results[label] = data
        except Exception as e:
            print(f"  ERRO {label} (view {view_code}): {e}")

    for i, view_code in enumerate(_ROTATION_VIEWS, 1):
        url = _image_url(version, color_id, trim_id, view_code, wheel_code)
        try:
            results[f"rotacao_{i}"] = fetch_image_bytes(url)
        except Exception as e:
            print(f"  ERRO rotacao_{i} (view {view_code}): {e}")
    return results


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
