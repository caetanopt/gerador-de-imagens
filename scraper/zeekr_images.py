"""
Descarrega as imagens de uma configuração Zeekr.

Ao contrário das outras marcas, as imagens são ficheiros estáticos com
URLs já conhecidas (guardadas no catálogo em data/zeekr_catalog.json) —
não há nenhuma API a chamar, só descarregar os PNGs directamente.
"""
import io
import ssl
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image

OUTPUT_DIR = Path(__file__).parent.parent / "output"

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/*,*/*",
    "Referer": "https://configurador.zeekr.pt/",
}


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=30) as r:
        return r.read()


def generate_images(color: dict, interior_image_url: str, interior_image_2: str = "", **_) -> dict[str, bytes]:
    """
    Gera as imagens para a configuração dada. `color` é a entrada da
    lista `colors` do catálogo (já tem as 3 URLs exteriores em `images`).
    """
    results = {}
    for label, url in color.get("images", {}).items():
        try:
            results[label] = _http_get(url)
        except Exception as e:
            print(f"  ERRO {label}: {e}")

    # 2 fotos de interior por cor de interior (frente e lateral); a 2.ª tem
    # o mesmo nome com "-interior-2-" (e pode ter outra extensão — vem do
    # catálogo quando conhecida)
    if interior_image_url:
        second = interior_image_2 or interior_image_url.replace("-interior-1-", "-interior-2-")
        for label, url in (("interior", interior_image_url), ("interior_lateral", second)):
            try:
                data = _http_get(url)
                Image.open(io.BytesIO(data))
                results[label] = data
            except Exception as e:
                print(f"  ERRO {label}: {e}")

    return results


def images_to_zip(images: dict[str, bytes], zip_name: str = "imagens_zeekr.zip") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in images.items():
            ext = "jpg" if data[:3] == b"\xff\xd8\xff" else "png"
            zf.writestr(f"{label}.{ext}", data)
    return buf.getvalue()


if __name__ == "__main__":
    import json
    import sys

    cat = json.load(open(Path(__file__).parent.parent / "data" / "zeekr_catalog.json", encoding="utf-8"))
    model_id = sys.argv[1] if len(sys.argv) > 1 else "001"
    model = next(m for m in cat["models"] if m["modelId"] == model_id)
    variant = model["variants"][0]
    color = variant["colors"][0]

    print(f"A gerar: {model['modelName']} | {variant['versionName']} | cor={color['name']}")
    images = generate_images(color, variant["interiorImage"])
    OUTPUT_DIR.mkdir(exist_ok=True)
    for label, data in images.items():
        path = OUTPUT_DIR / f"zeekr_{model_id}_{color['code']}_{label}.png"
        path.write_bytes(data)
        print(f"  {path.name} ({len(data):,} bytes)")
