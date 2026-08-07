"""
Extrai o catálogo Nissan a partir de duas fontes distintas, ambas embutidas
directamente no HTML/JSON servido pelo AEM (sem necessidade de API dinâmica):

1. "Legado" (Qashqai, Juke, Ariya) — o bloco `var carConfJson = {...}` no
   HTML de cada página de modelo contém toda a árvore gama -> versão -> cor
   -> jantes, com uma única imagem "packshot" (ângulo 3/4 frente fixo) por
   combinação versão+cor. Jantes usam um template com um placeholder
   `^COLOR_KEY^` a substituir pelo código da cor escolhida. Não há imagem de
   interior disponível (o campo existe no JSON mas o ficheiro real dá 404 em
   todos os modelos testados — falha de conteúdo do lado da Nissan).

2. "Rico" (por agora só o Micra) — um componente "vehicle360" separado
   (JSON `vehicle360_images.json`) fornece uma sequência de ~120 fotogramas
   por cor, cobrindo os 360° do carro. Escolhemos 4 fotogramas por fracção
   da sequência (0%=lado, 12.5%=3/4 frente, 25%=frente, 75%=traseira),
   confirmado visualmente. Não depende de grade/versão/jantes (o spinner é
   só por cor) e não tem interior disponível para o Micra.

O X-Trail não tem `carConfJson` nem `vehicle360` — não expõe configurador
nesta plataforma, por isso fica fora do catálogo.
"""
import json
import ssl
import urllib.request
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent / "data" / "nissan_catalog.json"

CDN_BASE = "https://www-europe.nissan-cdn.net"

LEGACY_MODEL_PAGES = {
    "Qashqai": "https://www.nissan.pt/veiculos/novos-veiculos/qashqai.html",
    "Juke": "https://www.nissan.pt/veiculos/novos-veiculos/juke.html",
    "Ariya": "https://www.nissan.pt/veiculos/novos-veiculos/ariya.html",
}

# O widget "vehicle360" só existe (até agora) na página do Micra. O caminho
# do componente AEM (columns12_e474/col1-par/vehicle360_e5d2) é gerado por
# página — teria de ser redescoberto se um dia aparecer noutro modelo.
RICH_MODEL_360_JSON = {
    "Micra": (
        "https://www.nissan.pt/content/nissan_prod/pt_PT/index/vehicles/new/"
        "new-nissan-micra/jcr:content/freeEditorial/columns12_e474/col1-par/"
        "vehicle360_e5d2.vehicle360_images.json"
    ),
}

# fracção da sequencia de 360 -> angulo, confirmado visualmente com o Micra
# ("extra_N" são fotogramas adicionais sem nome semântico confirmado,
# espaçados uniformemente pelo resto da volta)
_ANGLE_FRACTIONS = {
    "lado": 0.0,
    "3_4_frente": 0.125,
    "frente": 0.25,
    "extra_1": 44 / 117,
    "extra_2": 59 / 117,
    "extra_3": 73 / 117,
    "traseira": 0.75,
    "extra_4": 102 / 117,
}

_ssl_ctx = ssl.create_default_context()
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        return r.read()


def _get_json(url: str) -> dict:
    return json.loads(_get(url))


def _extract_car_conf_json(html: str) -> dict | None:
    marker = "var carConfJson = "
    idx = html.find(marker)
    if idx == -1:
        return None
    start = idx + len(marker)
    obj, _ = json.JSONDecoder().raw_decode(html, start)
    return obj


def _abs_url(path: str) -> str:
    if path.startswith("http"):
        return path
    if path.startswith("//"):
        return "https:" + path
    return CDN_BASE + path


def _float(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _build_legacy_model(model_name: str, page_url: str) -> dict | None:
    html = _get(page_url).decode("utf-8", errors="replace")
    conf = _extract_car_conf_json(html)
    if not conf:
        print(f"  {model_name}: sem carConfJson, a saltar")
        return None

    model_code = conf["basicModelInformation"].get("modelCode", "")
    grades_out = []
    for grade in conf["steps"]["grade"]["choices"]:
        versions_out = []
        for ver in grade["powertrain"]["choices"]:
            if not ver.get("available", True):
                continue
            image_template = _abs_url(ver["exteriorImage"]).replace(".png", "_col{COLOR}.png")
            wheel_choices = ver.get("wheels", {}).get("choices", [])
            wheel_template = None
            if wheel_choices:
                wheel_template = _abs_url(wheel_choices[0]["exteriorImage"]).replace("^COLOR_KEY^", "{COLOR}")
            versions_out.append({
                "name": ver["name"],
                "startingPrice": _float(ver.get("startingPrice")),
                "fuelType": ver.get("fuelType", ""),
                "transmission": ver.get("transmission", ""),
                "imageTemplate": image_template,
                "wheelImageTemplate": wheel_template,
                "wheelName": wheel_choices[0]["name"] if wheel_choices else None,
                "wheelImageUrl": _abs_url(wheel_choices[0]["thumbnailPath"]) if wheel_choices and wheel_choices[0].get("thumbnailPath") else None,
                "colors": [
                    {
                        "code": c["key"],
                        "name": c["name"],
                        "price": _float(c.get("price")),
                        "swatchUrl": _abs_url(c["thumbnailPath"]) if c.get("thumbnailPath") else None,
                    }
                    for c in ver.get("colour", {}).get("choices", [])
                ],
            })
        if versions_out:
            grades_out.append({
                "key": grade["key"],
                "name": grade["name"],
                "startingPrice": _float(grade.get("startingPrice")),
                "versions": versions_out,
            })

    return {
        "type": "legacy",
        "modelName": model_name,
        "modelCode": model_code,
        "grades": grades_out,
    }


def _build_rich_model(model_name: str, json_url: str) -> dict | None:
    data = _get_json(json_url)
    colours = data.get("colours", [])
    colors_out = []
    for c in colours:
        if "key" not in c:
            continue
        frames = c.get("imagePaths", {}).get("standard", {}).get("large", [])
        if len(frames) < 10:
            continue
        n = len(frames)
        images = {
            angle: _abs_url(frames[min(n - 1, round(frac * n))])
            for angle, frac in _ANGLE_FRACTIONS.items()
        }
        colors_out.append({
            "code": c["key"],
            "name": c.get("disclaimer") or frames[0].split("/")[-2].replace("_", " "),
            "images": images,
        })
    if not colors_out:
        return None
    return {
        "type": "rich360",
        "modelName": model_name,
        "colors": colors_out,
    }


def build_catalog(force: bool = False) -> dict:
    if DATA_FILE.exists() and not force:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))

    models = []
    for name, url in LEGACY_MODEL_PAGES.items():
        print(f"A processar {name} (legado)...")
        m = _build_legacy_model(name, url)
        if m:
            models.append(m)
            n_versions = sum(len(g["versions"]) for g in m["grades"])
            n_colors = sum(len(v["colors"]) for g in m["grades"] for v in g["versions"])
            print(f"  {name}: {len(m['grades'])} gamas, {n_versions} versões, {n_colors} combinações de cor")

    for name, url in RICH_MODEL_360_JSON.items():
        print(f"A processar {name} (360)...")
        m = _build_rich_model(name, url)
        if m:
            models.append(m)
            print(f"  {name}: {len(m['colors'])} cores (360°)")

    catalog = {"models": models}
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    return catalog


def load_catalog() -> dict:
    return build_catalog(force=False)


if __name__ == "__main__":
    cat = build_catalog(force=True)
    print("\nTotal modelos no catálogo:", len(cat["models"]))
