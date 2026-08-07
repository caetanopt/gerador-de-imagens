"""
Descarrega as imagens de uma configuração BMW a partir da colecao
"stage-fullscreen-views-legacy-newnames" da API de imagens do
configurador (prod.cosy.bmw.cloud). Ao contrário da VW/Audi, a imagem
não depende de um único parâmetro de cor/jante — a API recebe a lista
COMPLETA de códigos de opção activos (baseOptions do catálogo + cor +
jante escolhidas) e devolve, para essa configuração exacta, um conjunto
de vistas nomeadas por ângulo ("POV"): HEROFRONT (frente recta),
FRONTLEFT (3/4 frente), SIDELEFT (lado), HEROREAR (traseira recta) e
FRONTSEATS (interior).
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
COSY_API_KEY = "KLexy26ApAFmYH3aViwuLxf02wN1wqBATdFPONSig"
REFERER = "https://configure.bmw.pt/"
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

# label interno -> POV da colecao stage-fullscreen-views-legacy-newnames
# (11 POVs confirmados nesta colecao — nao existe REARRIGHT nem TOP).
# NOTA: "WHEEL" fica de fora de propósito — confirmado por comparação de
# bytes e inspecção visual que devolve a MESMA foto de corpo inteiro que
# SIDELEFT (a API espera que o recorte de zoom, indicado nos parâmetros
# X/Y/W/H da resposta, seja aplicado no frontend — não há um ficheiro de
# detalhe de jante real a descarregar aqui).
VIEWS = {
    "3_4_frente": "FRONTLEFT",
    "frente": "HEROFRONT",
    "lado": "SIDELEFT",
    "traseira": "HEROREAR",
    "interior": "FRONTSEATS",
    "3_4_frente_direita": "FRONTRIGHT",
    "lado_direito": "SIDERIGHT",
    "3_4_traseira_esquerda": "REARLEFT",
    "interior_tablier": "DASH",
    "interior_lateral": "INTERIORSIDE",
}


def _fetch_stage_images(model_code: str, options: list[str], effect_date: str) -> dict:
    effectdate = effect_date.replace("-", "")
    options_csv = ",".join(sorted(options))
    url = (
        f"{COSY_BASE}/image-urls/dynamic-named-images/mandators/connext-bmw/"
        f"collections/stage-fullscreen-views-legacy-newnames/brands/bmwCar/models/{model_code}"
        f"?effectdate={effectdate}&hub=CLOUD_PROD_INTERNET&imagetype=webp&options={options_csv}&accessories="
    )
    req = urllib.request.Request(url, headers=_JSON_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        return json.loads(r.read())


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
    """Gera as imagens BMW para a configuração dada."""
    options = list(base_options) + [color_code, wheel_code]

    try:
        data = _fetch_stage_images(model_code, options, effect_date)
    except Exception as e:
        print(f"  ERRO ao obter URLs de imagem: {e}")
        return {}

    desktop = (
        data.get("stage-fullscreen-views-legacy-newnames", {})
        .get("desktop", {})
        .get("namedImages", [{}])[0]
        .get("images", [])
    )
    by_pov: dict[str, str] = {}
    for im in desktop:
        pov = im.get("distinctionParameters", {}).get("POV")
        if pov and pov not in by_pov:
            by_pov[pov] = im["viewImage"]

    to_fetch = {}
    for label, pov in VIEWS.items():
        url = by_pov.get(pov)
        if url:
            to_fetch[label] = url
        else:
            print(f"  AVISO: sem imagem para POV={pov}")

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
    from scraper.bmw_catalog import load_catalog

    catalog = load_catalog()
    variant = catalog["models"][0]["variants"][0]
    print(f"A gerar imagens de teste: {variant['name']}")
    images = generate_images(
        model_code=variant["modelCode"],
        base_options=variant["baseOptions"],
        color_code=variant["defaultColor"],
        wheel_code=variant["defaultWheel"],
        effect_date=variant["effectDate"],
    )
    OUTPUT_DIR.mkdir(exist_ok=True)
    for label, data in images.items():
        path = OUTPUT_DIR / f"bmw_{variant['modelCode']}_{label}.webp"
        path.write_bytes(data)
        print(f"  {path.name} ({len(data):,} bytes)")
