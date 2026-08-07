"""
Descarrega imagens de uma configuração Peugeot.
Usa o visualizador 3D: visuel3d-secure.peugeot.com — mesma tecnologia V3D
do Opel, mas sem rotação contínua (sem sequência de graus válida); cada
código de view é uma cena curada fixa. Além das 4 vistas já confirmadas
como estáveis, tentam-se mais códigos: 000/001/004 são exterior, e
011/012/013/020/021/023/024/025 são todas cenas de INTERIOR (confirmado
visualmente) — como nem todos os códigos existem para todos os
modelos/versões, cada um é pedido individualmente e ignorado em silêncio
se falhar (não bloqueia as restantes).
"""
import io, ssl, urllib.request, zipfile
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

# Mapeamento view code → label PT (cenas já confirmadas como estáveis)
VIEWS = {
    "3_4_frente": "006",  # 3/4 frente (selector/default)
    "frente":     "002",  # 3/4 frente esquerda
    "lado":       "003",  # perfil
    "traseira":   "005",  # traseira 3/4
}

# outras cenas exteriores confirmadas como distintas mas sem nome fiável
# (variam conforme o modelo) — extraídas com o código de view como label.
_EXTRA_EXTERIOR_VIEWS = ["000", "001", "004"]

# 011-025 são todas cenas de INTERIOR (confirmado visualmente: tablier,
# bancos, apoios de cabeça, consola) — label com o prefixo "interior_"
# para que fiquem automaticamente isentas do recorte/fundo branco/logo em
# app.py (ver _NO_COMPOSITE_MARKERS), tal como qualquer outra imagem de
# interior do projecto.
_EXTRA_INTERIOR_VIEWS = ["011", "012", "013", "020", "021", "023", "024", "025"]


def _image_url(version: str, color_id: str, trim_id: str, view_code: str) -> str:
    return (
        f"{CDN}?client=SOLVCG&ratio=1&format=jpg&quality=90"
        f"&width=1450&height=670&back=0"
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
    results = {}
    for label, view_code in VIEWS.items():
        url = _image_url(version, color_id, trim_id, view_code)
        try:
            data = fetch_image_bytes(url)
            results[label] = data
        except Exception as e:
            print(f"  ERRO {label} (view {view_code}): {e}")

    for view_code in _EXTRA_EXTERIOR_VIEWS:
        url = _image_url(version, color_id, trim_id, view_code)
        try:
            results[f"vista_{view_code}"] = fetch_image_bytes(url)
        except Exception as e:
            print(f"  ERRO vista_{view_code} (view {view_code}): {e}")

    for view_code in _EXTRA_INTERIOR_VIEWS:
        url = _image_url(version, color_id, trim_id, view_code)
        try:
            results[f"interior_{view_code}"] = fetch_image_bytes(url)
        except Exception as e:
            print(f"  ERRO interior_{view_code} (view {view_code}): {e}")
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
