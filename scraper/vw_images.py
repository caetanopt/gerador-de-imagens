"""
Descarrega as 4 imagens de uma configuração VW para a pasta output/.
Lógica genérica (reaproveitada por audi_images.py) parametrizada pelo
domínio da CDN — a plataforma de imagens é partilhada por todo o grupo VW.
"""
import io
import ssl
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CDN = "https://cdn.nwi-ms.com/media/pt/V/mc"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/webp,image/*,*/*",
    "Referer": "https://configurador.volkswagen.pt/",
}

# "front"/"side" foram retiradas: vêm num estúdio com chão cinzento e,
# depois do recorte, repetiam outros ângulos com uma sombra errada. O
# spin 360 do configurador ("01"-"12", de 30 em 30 graus a partir da
# frente-esquerda) pedido com background=transparent vem com alpha real e
# sombra nativa. Ficam de fora o "03" (= overview) e o "06" (= back).
# Nem todos os frames existem para todos os modelos — os que faltam são
# simplesmente ignorados.
VIEWS = {
    "3_4_frente": "exteriorfront",
    "3_4_frente_esquerda_proxima": "01",
    "3_4_frente_esquerda": "02",
    "lado_estudio": "overview",
    "3_4_traseira_esquerda_lateral": "04",
    "3_4_traseira_esquerda": "05",
    "traseira": "back",
    "3_4_traseira_direita": "07",
    "3_4_traseira_direita_lateral": "08",
    "lado_direito": "09",
    "3_4_frente_direita_lateral": "10",
    "3_4_frente_direita": "11",
    "frente": "12",
    "interior_tablier": "interior_center",
    "interior_bancos": "interior",
    "interior_lateral": "interior_side",
    "interior_bancos_traseiros": "interior_back",
    "bagageira_detalhe": "trunk",
}

# vistas que são fotografias de cena (interior, bagageira, detalhes) —
# não se pede fundo transparente. Inclui os nomes da Audi/Škoda.
_SCENE_VIEWS = {
    "interior", "interior_center", "interior_side", "interior_back", "trunk",
    "interiorside", "interiorfront", "back_seats", "headlight", "wheel", "boot",
}


def _image_url(cdn: str, model_code: str, view: str, color: str, upholstery: str, wheel: str = "", transparent: bool = False) -> str:
    url = (
        f"{cdn}/{model_code}/model/{view}.webp"
        f"?F={color}&P={upholstery}&M={wheel}&size=XL"
    )
    if transparent and view not in _SCENE_VIEWS:
        url += "&background=transparent"
    return url


def fetch_image_bytes(url: str, referer: str = "https://configurador.volkswagen.pt/") -> bytes:
    """Descarrega imagem e devolve bytes. Lança exceção se falhar."""
    headers = dict(_HEADERS, Referer=referer)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=20) as r:
        data = r.read()
    if not data:
        raise ValueError(f"Imagem vazia: {url}")
    return data


def generate_images_generic(
    cdn: str,
    referer: str,
    model_code: str,
    color_code: str,
    upholstery_code: str,
    wheel_code: str = "",
    views: dict[str, str] | None = None,
    transparent: bool = False,
) -> dict[str, bytes]:
    """
    Gera as imagens para a configuração dada.
    Devolve dict: {label: bytes_da_imagem}, pela ordem de `views`.
    """
    views = views or VIEWS

    def fetch(item):
        label, view = item
        url = _image_url(cdn, model_code, view, color_code, upholstery_code, wheel_code, transparent)
        try:
            return label, fetch_image_bytes(url, referer)
        except Exception as e:
            print(f"  ERRO {view}: {e}")
            return label, None

    with ThreadPoolExecutor(max_workers=8) as ex:
        fetched = list(ex.map(fetch, views.items()))
    return {label: data for label, data in fetched if data}


def generate_images(
    model_code: str,
    color_code: str,
    upholstery_code: str,
    wheel_code: str = "",
    model_name: str = "",
    color_name: str = "",
) -> dict[str, bytes]:
    """Gera as imagens VW (exterior + interior) para a configuração dada."""
    return generate_images_generic(
        CDN, "https://configurador.volkswagen.pt/", model_code, color_code, upholstery_code, wheel_code,
        transparent=True,
    )


def save_images(
    images: dict[str, bytes],
    model_code: str,
    color_code: str,
    wheel_code: str = "",
) -> list[Path]:
    """Guarda imagens em output/ e devolve lista de paths."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    prefix = f"{model_code}_{color_code}"
    if wheel_code:
        prefix += f"_{wheel_code}"

    saved = []
    for label, data in images.items():
        path = OUTPUT_DIR / f"{prefix}_{label}.webp"
        with open(path, "wb") as f:
            f.write(data)
        saved.append(path)
    return saved


def images_to_zip(images: dict[str, bytes], zip_name: str = "imagens.zip") -> bytes:
    """Empacota as imagens num ZIP e devolve os bytes do ZIP."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in images.items():
            ext = "jpg" if data[:3] == b"\xff\xd8\xff" else "webp"
            zf.writestr(f"{label}.{ext}", data)
    return buf.getvalue()


if __name__ == "__main__":
    import sys
    mc = sys.argv[1] if len(sys.argv) > 1 else "DA13HYA2"
    color = sys.argv[2] if len(sys.argv) > 2 else "5K5K"
    upholstery = sys.argv[3] if len(sys.argv) > 3 else "BD"
    wheel = sys.argv[4] if len(sys.argv) > 4 else ""

    print(f"A gerar imagens: {mc} | cor={color} | upholstery={upholstery} | jante={wheel or 'serie'}")
    images = generate_images(mc, color, upholstery, wheel)
    paths = save_images(images, mc, color, wheel)
    print(f"Guardadas {len(paths)} imagens:")
    for p in paths:
        size = p.stat().st_size
        print(f"  {p.name} ({size:,} bytes)")
