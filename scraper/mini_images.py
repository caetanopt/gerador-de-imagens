"""
Descarrega as imagens de uma configuração MINI a partir das coleções
"walkaround-360" (exterior, 36 fotogramas a 10° cada, todos devolvidos
num único pedido — 0°=frente, 90°=lado, 180°=traseira, 40°=3/4 frente,
confirmados visualmente; os restantes são etiquetados pelo grau) e
"interior-mixed" (interior — 6 fotogramas estáticos de alta resolução,
todos usados) da API de imagens do configurador "Connext"
(prod.cosy.bmw.cloud). Tal como na BMW, a MINI exige a lista COMPLETA de
códigos de opção activos (baseOptions do catálogo + cor + jante
escolhidas), não um único parâmetro de cor/jante.
"""
import io
import json
import ssl
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_MAX_WORKERS = 8

COSY_BASE = "https://prod.cosy.bmw.cloud"
COSY_API_KEY = "IUuxS945sM6HB4cdGU9u59G4sIHqImwi8Apu6BgK"
REFERER = "https://configure.mini.pt/"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

_ssl_ctx = ssl.create_default_context()

_JSON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": REFERER,
    "x-api-key": COSY_API_KEY,
}
_IMG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/webp,image/*,*/*",
    "Referer": REFERER,
}

# label interno -> angulo do walkaround-360 (0°=frente, 40°=3/4 frente
# esquerda, 90°=lado com a frente virada para a esquerda, 180°=traseira);
# os restantes 32 ângulos (passo de 10°, 0-350°) são etiquetados pelo grau.
_ANGLE_LABELS = {
    0: "frente",
    40: "3_4_frente",
    90: "lado",
    180: "traseira",
}
_ALL_ANGLES = list(range(0, 360, 10))


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=_JSON_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        return json.loads(r.read())


def _fetch_walkaround(model_code: str, options: list[str], effect_date: str) -> dict[int, str]:
    effectdate = effect_date.replace("-", "")
    options_csv = ",".join(sorted(options))
    url = (
        f"{COSY_BASE}/image-urls/dynamic-images/mandators/connext-mini/"
        f"collections/walkaround-360/brands/mini/models/{model_code}"
        f"?effectdate={effectdate}&options={options_csv}&background=day&imagetype=WEBP"
        f"&hub=CLOUD_PROD_INTERNET&lightson=false"
    )
    data = _get(url)
    images = data.get("walkaround-360", {}).get("desktop_xl", {}).get("images", [])
    return {im["angle"]: im["viewImage"] for im in images}


def _fetch_interior(model_code: str, options: list[str], effect_date: str) -> list[str]:
    effectdate = effect_date.replace("-", "")
    options_csv = ",".join(sorted(options))
    url = (
        f"{COSY_BASE}/image-urls/dynamic-images/mandators/connext-mini/"
        f"collections/interior-mixed/brands/mini/models/{model_code}"
        f"?effectdate={effectdate}&options={options_csv}&hub=CLOUD_PROD_INTERNET&imagetype=WEBP"
    )
    data = _get(url)
    images = data.get("interior-mixed", {}).get("res_2000x2000", {}).get("images", [])
    return [im["viewImage"] for im in images]


def _fetch_image_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_IMG_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        data = r.read()
    if not data:
        raise ValueError(f"Imagem vazia: {url}")
    return data


def generate_images(
    model_code: str,
    base_options: list[str],
    color_code: str,
    wheel_code: str,
    effect_date: str = "2026-09-08",
    **_,
) -> dict[str, bytes]:
    """Gera as imagens MINI para a configuração dada."""
    options = list(base_options) + [color_code, wheel_code]

    try:
        by_angle = _fetch_walkaround(model_code, options, effect_date)
    except Exception as e:
        print(f"  ERRO ao obter walkaround-360: {e}")
        by_angle = {}
    try:
        interior_urls = _fetch_interior(model_code, options, effect_date)
    except Exception as e:
        print(f"  ERRO interior: {e}")
        interior_urls = []

    to_fetch = {}
    for angle in _ALL_ANGLES:
        url = by_angle.get(angle)
        if url:
            to_fetch[_ANGLE_LABELS.get(angle, f"ext_{angle:03d}")] = url
        else:
            print(f"  AVISO: sem imagem para angulo={angle}")
    for i, url in enumerate(interior_urls, 1):
        to_fetch[f"interior_{i}"] = url

    results = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {label: pool.submit(_fetch_image_bytes, url) for label, url in to_fetch.items()}
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
    from scraper.mini_catalog import load_catalog

    catalog = load_catalog()
    variant = catalog["models"][0]["variants"][0]
    print(f"A gerar imagens de teste: {variant['name']}")
    images = generate_images(
        model_code=variant["modelCode"],
        base_options=variant["baseOptions"],
        color_code=variant["defaultColor"],
        wheel_code=variant["defaultWheel"],
    )
    OUTPUT_DIR.mkdir(exist_ok=True)
    for label, data in images.items():
        path = OUTPUT_DIR / f"mini_{variant['modelCode']}_{label}.webp"
        path.write_bytes(data)
        print(f"  {path.name} ({len(data):,} bytes)")
