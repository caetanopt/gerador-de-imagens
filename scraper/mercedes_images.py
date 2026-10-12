"""
Gera as imagens de uma configuração Mercedes-Benz. Ao contrário da
maioria das outras marcas, o catálogo não guarda URLs de imagem
pré-calculados por cor — guarda antes o vehicleId base de cada versão e
os códigos de cor/jante de série. Aqui troca-se a cor e a jante
escolhidas nesse vehicleId (ver scraper.mercedes_catalog.replace_in_group)
e pede-se a imagem resultante à API "entry" em tempo real.
"""
import io
import ssl
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scraper.mercedes_catalog import fetch_entry, replace_in_group, stage_images_from_entry

_MAX_WORKERS = 8

REFERER = "https://www.mercedes-benz.pt/"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

_ssl_ctx = ssl.create_default_context()

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/webp,image/*,*/*",
    "Referer": REFERER,
}


def _fetch_image_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        data = r.read()
    if not data:
        raise ValueError(f"Imagem vazia: {url}")
    return data


def generate_images(
    variant: dict,
    color_code: str,
    wheel_code: str = "",
    interior_code: str = "",
    **_,
) -> dict[str, bytes]:
    """Gera as imagens Mercedes-Benz para a versão + cor + jante escolhidas."""
    # o estofo pode exigir um pack (ver mercedes_catalog.extract_interiors) —
    # nesse caso parte-se da configuração guardada com o estofo
    interior = next((i for i in variant.get("interiors") or [] if i["code"] == interior_code), None)
    start_vid = (interior or {}).get("vehicleId") or variant["vehicleId"]
    vehicle_id = replace_in_group(start_vid, "LU", variant["defaultColorCode"], color_code)
    if wheel_code and variant.get("defaultWheelCode"):
        vehicle_id = replace_in_group(vehicle_id, "SA", variant["defaultWheelCode"], wheel_code)
    if interior_code and variant.get("defaultInteriorCode") and not (interior or {}).get("vehicleId"):
        vehicle_id = replace_in_group(vehicle_id, "AU", variant["defaultInteriorCode"], interior_code)

    entry = fetch_entry(variant["typeClass"], vehicle_id)
    if not entry:
        return {}
    image_urls = stage_images_from_entry(entry)
    if not image_urls:
        return {}

    results = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {label: pool.submit(_fetch_image_bytes, url) for label, url in image_urls.items()}
        for label, future in futures.items():
            try:
                results[label] = future.result()
            except Exception as e:
                print(f"  ERRO {label}: {e}")
    return results


def images_to_zip(images: dict[str, bytes], zip_name: str = "imagens.zip") -> bytes:
    """Empacota as imagens num ZIP e devolve os bytes do ZIP."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in images.items():
            ext = "jpg" if data[:3] == b"\xff\xd8\xff" else "webp"
            zf.writestr(f"{label}.{ext}", data)
    return buf.getvalue()


if __name__ == "__main__":
    from scraper.mercedes_catalog import load_catalog

    catalog = load_catalog()
    variant = catalog["models"][0]["variants"][0]
    color = variant["colors"][0]
    wheel = variant["wheels"][0] if variant["wheels"] else None
    print(f"A gerar imagens de teste: {variant['name']} — {color['name']} — {wheel['name'] if wheel else 'jante de série'}")
    images = generate_images(
        variant=variant,
        color_code=color["code"],
        wheel_code=wheel["code"] if wheel else "",
    )
    OUTPUT_DIR.mkdir(exist_ok=True)
    for label, data in images.items():
        path = OUTPUT_DIR / f"mercedes_{variant['modelCode']}_{color['code']}_{label}.webp"
        path.write_bytes(data)
        print(f"  {path.name} ({len(data):,} bytes)")
