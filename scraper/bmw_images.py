"""
Descarrega as imagens de uma configuração BMW a partir da API de imagens
do configurador (prod.cosy.bmw.cloud). A API recebe a lista COMPLETA de
códigos de opção activos (baseOptions do catálogo + cor + jante) e devolve
URLs (encriptadas, não editáveis) por colecção.

Exterior: colecção "stage-fullscreen-views-legacy" — mesmos ângulos da
"-newnames" usada antes, mas com o carro a ocupar ~2x mais área do frame
(muito mais resolução útil). Ângulos WALKAROUND: 0 = frente, 40 = 3/4
frente esq., 90 = lado esq., 150 = 3/4 traseira esq., 180 = traseira,
270 = lado dir., 340 = 3/4 frente dir.; 271 = grande plano da jante.
Todas em estúdio "sand" (sem fundo transparente; a única colecção com
BKGND=transparent, "line-selection-modal", só tem 2 ângulos a 1300px) —
recortadas por rembg + sombra sintética em composite.py.
Interior: DASHBOARD e DRIVERDOOR (legacy) + FRONTSEATS, REARSEATS e
INTERIOR da "stage-fullscreen-views"; repetidos descartados por hash.
"""
import hashlib
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

_EXTERIOR_COLLECTION = "stage-fullscreen-views-legacy"
_INTERIOR_COLLECTION = "stage-fullscreen-views"

# label -> (colecção, POV, ANGLE)
VIEWS = {
    "3_4_frente": (_EXTERIOR_COLLECTION, "WALKAROUND", "40"),
    "frente": (_EXTERIOR_COLLECTION, "WALKAROUND", "0"),
    "3_4_frente_direita": (_EXTERIOR_COLLECTION, "WALKAROUND", "340"),
    "lado_esquerdo": (_EXTERIOR_COLLECTION, "WALKAROUND", "90"),
    "lado_direito": (_EXTERIOR_COLLECTION, "WALKAROUND", "270"),
    "3_4_traseira_esquerda": (_EXTERIOR_COLLECTION, "WALKAROUND", "150"),
    "traseira": (_EXTERIOR_COLLECTION, "WALKAROUND", "180"),
    "jante_detalhe": (_EXTERIOR_COLLECTION, "WALKAROUND", "271"),
    "interior_tablier": (_EXTERIOR_COLLECTION, "DASHBOARD", None),
    "interior_lateral": (_EXTERIOR_COLLECTION, "DRIVERDOOR", None),
    "interior": (_INTERIOR_COLLECTION, "INTERIOR", None),
    "interior_bancos": (_INTERIOR_COLLECTION, "FRONTSEATS", None),
    "interior_bancos_traseiros": (_INTERIOR_COLLECTION, "REARSEATS", None),
}


def _fetch_collection(collection: str, model_code: str, options: list[str], effect_date: str) -> dict:
    effectdate = effect_date.replace("-", "")
    options_csv = ",".join(sorted(options))
    url = (
        f"{COSY_BASE}/image-urls/dynamic-named-images/mandators/connext-bmw/"
        f"collections/{collection}/brands/bmwCar/models/{model_code}"
        f"?effectdate={effectdate}&hub=CLOUD_PROD_INTERNET&imagetype=webp&options={options_csv}&accessories="
    )
    req = urllib.request.Request(url, headers=_JSON_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        return json.loads(r.read())


def _first_url_by_pov(data: dict, collection: str) -> dict[tuple, str]:
    """(POV, ANGLE) -> primeira URL da colecção (as seguintes do mesmo
    POV/ângulo são variantes de enquadramento/fundo nocturno)."""
    block = data.get(collection, {})
    device = block.get("desktop") or next(iter(block.values()), {})
    out = {}
    for named in device.get("namedImages", []):
        for im in named.get("images", []):
            p = im.get("distinctionParameters", {})
            if p.get("BKGND") and "night" in p["BKGND"]:
                continue
            out.setdefault((p.get("POV"), p.get("ANGLE")), im["viewImage"])
    return out


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

    urls_by_collection = {}
    for collection in {c for c, _, _ in VIEWS.values()}:
        try:
            urls_by_collection[collection] = _first_url_by_pov(
                _fetch_collection(collection, model_code, options, effect_date), collection,
            )
        except Exception as e:
            print(f"  ERRO ao obter URLs ({collection}): {e}")

    to_fetch = {}
    for label, (collection, pov, angle) in VIEWS.items():
        url = urls_by_collection.get(collection, {}).get((pov, angle))
        if url:
            to_fetch[label] = url
        else:
            print(f"  AVISO: sem imagem para {pov} {angle or ''}")

    fetched = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {label: pool.submit(_fetch_image_bytes, url) for label, url in to_fetch.items()}
        for label, future in futures.items():
            try:
                fetched[label] = future.result()
            except Exception as e:
                print(f"  ERRO {label}: {e}")

    results, seen = {}, set()
    for label, data in fetched.items():
        h = hashlib.md5(data).hexdigest()
        if h not in seen:
            seen.add(h)
            results[label] = data
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
