"""
Descarrega as imagens de uma configuração Nissan (configurador.nissan.pt,
plataforma "cardb" — ver nissan_catalog.py).

- Micra, cores bicolor: volta de 360° do componente "vehicle360" (~120
  fotogramas por cor, lido ao vivo). Usam-se 24 (um a cada 15°) e o PNG
  ORIGINAL de cada fotograma (2560x1440, alpha real) em vez da versão
  redimensionada ".ximg.c1h.360.png" (1160x652) que vem no JSON. Nº do
  fotograma -> ângulo: 1 = lado dir., 31 = frente, 61 = lado esq.,
  91 = traseira (3° por fotograma).
- Restantes: fotos da galeria da cor (1-3 por cor).
- Interior: fotos da cor de interior escolhida (galeria "internal360",
  que na Nissan são fotos normais e não panoramas).
"""
import hashlib
import io
import json
import re
import ssl
from concurrent.futures import ThreadPoolExecutor
import urllib.request
import zipfile

_ssl_ctx = ssl.create_default_context()
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


_NISSAN_HOST = "https://www.nissan.pt"
_FRONT_FRAME = 31
_ROTATION_NAMES = {
    0: "frente",
    45: "3_4_frente_esquerda",
    90: "lado_esquerdo",
    135: "3_4_traseira_esquerda",
    180: "traseira",
    225: "3_4_traseira_direita",
    270: "lado_direito",
    315: "3_4_frente_direita",
}


def _original(url: str) -> str:
    """Tira o sufixo de rendição AEM (".ximg.c1h.360.png") -> PNG original."""
    return url.split(".ximg.")[0] if ".ximg." in url else url


def _rotation_urls(model_name: str, color_code: str) -> dict[str, str]:
    from scraper.nissan_catalog import RICH_MODEL_360_JSON

    json_url = RICH_MODEL_360_JSON.get(model_name)
    if not json_url:
        return {}
    data = json.loads(_fetch(json_url))
    colour = next((c for c in data.get("colours", []) if c.get("key") == color_code), None)
    if not colour:
        return {}
    paths = colour["imagePaths"]
    frames = (paths.get("highRes") or {}).get("large") or paths["standard"]["large"]
    # a posição na lista NÃO serve: há cores com 117 fotogramas (0001-0117)
    # e outras com 120 (0000-0119). O nº no nome do ficheiro é que é fiel:
    # 120 fotogramas a 3°, frente = nº 31 (confirmado pela silhueta mais
    # estreita em várias cores).
    by_number = {}
    for f in frames:
        m = re.search(r"\.(\d{4})\.png", f)
        if m:
            by_number[int(m.group(1))] = f
    if not by_number:
        return {}
    out = {}
    for step in range(24):
        deg = (45 + step * 15) % 360
        target = (_FRONT_FRAME + round(deg / 3)) % 120
        nearest = min(by_number, key=lambda k: min(abs(k - target), 120 - abs(k - target)))
        out[_ROTATION_NAMES.get(deg, f"rotacao_{deg:03d}")] = _original(_NISSAN_HOST + by_number[nearest])
    return out


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        data = r.read()
    if not data:
        raise ValueError(f"Imagem vazia: {url}")
    return data


def generate_images(model_name: str, color: dict, interior_images: list[str] | None = None, **_) -> dict[str, bytes]:
    """
    Imagens Nissan (configurador.nissan.pt) para a cor escolhida:
    - volta de 360° com 24 ângulos quando a cor a tem (Micra bicolor —
      color["rotationKey"]);
    - senão, as fotos da galeria da cor (1-3; repetidas descartadas);
    - mais as fotos da cor de interior escolhida.
    """
    urls: dict[str, str] = {}
    if color.get("rotationKey"):
        try:
            urls = _rotation_urls(model_name, color["rotationKey"])
        except Exception as e:
            print(f"  ERRO a ler a sequência 360 Nissan: {e}")
    if not urls:
        for i, u in enumerate(color.get("images", [])):
            urls["3_4_frente" if i == 0 else f"exterior_{i + 1}"] = u
    for i, u in enumerate(interior_images or []):
        urls["interior" if i == 0 else f"interior_{i + 1}"] = u

    def fetch(item):
        label, url = item
        try:
            return label, _fetch(url)
        except Exception as e:
            print(f"  ERRO imagem Nissan {label}: {e}")
            return label, None

    with ThreadPoolExecutor(max_workers=8) as ex:
        fetched = list(ex.map(fetch, urls.items()))
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


def images_to_zip(images: dict[str, bytes], zip_name: str = "imagens.zip") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in images.items():
            ext = "jpg" if data[:3] == b"\xff\xd8\xff" else "webp"
            zf.writestr(f"{label}.{ext}", data)
    return buf.getvalue()
