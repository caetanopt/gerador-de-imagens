"""
Descarrega as 4 imagens de uma configuração VW para a pasta output/.
Lógica genérica (reaproveitada por audi_images.py) parametrizada pelo
domínio da CDN — a plataforma de imagens é partilhada por todo o grupo VW.
"""
import io
import ssl
import urllib.request
import zipfile
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

VIEWS = {
    "3_4_frente": "exteriorfront",
    "frente": "front",
    "lado": "side",
    "traseira": "back",
    "lado_estudio": "overview",
}


def _image_url(cdn: str, model_code: str, view: str, color: str, upholstery: str, wheel: str = "") -> str:
    return (
        f"{cdn}/{model_code}/model/{view}.webp"
        f"?F={color}&P={upholstery}&M={wheel}&size=XL"
    )


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
) -> dict[str, bytes]:
    """
    Gera as imagens para a configuração dada.
    Devolve dict: {label: bytes_da_imagem}
    """
    results = {}
    for label, view in (views or VIEWS).items():
        url = _image_url(cdn, model_code, view, color_code, upholstery_code, wheel_code)
        try:
            data = fetch_image_bytes(url, referer)
            results[label] = data
        except Exception as e:
            print(f"  ERRO {view}: {e}")
    return results


def generate_images(
    model_code: str,
    color_code: str,
    upholstery_code: str,
    wheel_code: str = "",
    model_name: str = "",
    color_name: str = "",
) -> dict[str, bytes]:
    """Gera as 4 imagens VW para a configuração dada."""
    return generate_images_generic(
        CDN, "https://configurador.volkswagen.pt/", model_code, color_code, upholstery_code, wheel_code,
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
