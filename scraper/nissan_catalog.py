"""
Catálogo Nissan — configurador configurador.nissan.pt (desde 2026-10).

A Nissan Portugal mudou para a mesma plataforma "cardb" da BYD/XPENG/
Hyundai (API /api/wcc/{models,versions,colors}, imagens em
cardb.nissanportugal.pt). O método antigo (bloco `carConfJson` no HTML das
páginas de modelo) deixou de existir. Ganha-se: 8 modelos (Juke, Micra,
Qashqai, LEAF, X-Trail e-Power, Primastar Van/Combi, Ariya), versões
reais, cores com miniatura e cores de interior com foto (filtradas pela
cor exterior — ver cardb_interiors.py).

Exterior: a galeria só tem 1 foto por cor (2-3 no X-Trail/LEAF), PNG com
alpha. Excepção: no Micra, as cores bicolor têm também a volta de 360°
do componente "vehicle360" da página do modelo (código "COL" + código de
fábrica da cor, ex.: COLXUF) — usada para 24 ângulos (nissan_images.py).

Cache em data/nissan_catalog.json.
"""
import json
import ssl
import urllib.request
from collections import defaultdict
from pathlib import Path

from scraper.cardb_interiors import interiors_by_version

DATA_FILE = Path(__file__).parent.parent / "data" / "nissan_catalog.json"
API_BASE = "https://configurador.nissan.pt/api/wcc"

# Volta de 360° do Micra (componente AEM da página do modelo — o caminho
# tem um id gerado, teria de ser redescoberto noutro modelo).
RICH_MODEL_360_JSON = {
    "Micra": (
        "https://www.nissan.pt/content/nissan_prod/pt_PT/index/vehicles/new/"
        "new-nissan-micra/jcr:content/freeEditorial/columns12_e474/col1-par/"
        "vehicle360_e5d2.vehicle360_images.json"
    ),
}

_ssl_ctx = ssl.create_default_context()
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://configurador.nissan.pt/",
}


def _get_json(url: str):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=30) as r:
        return json.loads(r.read())


def _float(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _display_name(api_name: str) -> str:
    """"Nissan JUKE" -> "Juke", "Nissan X-TRAIL E-POWER" -> "X-Trail e-Power"."""
    name = api_name.replace("Nissan ", "").strip()
    fixed = {"LEAF": "LEAF", "E-POWER": "e-Power", "X-TRAIL": "X-Trail"}
    return " ".join(fixed.get(w, w.capitalize()) for w in name.split())


def _rotation_keys(model_name: str) -> set[str]:
    url = RICH_MODEL_360_JSON.get(model_name)
    if not url:
        return set()
    try:
        return {c["key"] for c in _get_json(url).get("colours", []) if c.get("key")}
    except Exception as e:
        print(f"    aviso: sem volta 360 ({e})")
        return set()


def _legacy_fallback(previous: dict, present: set[str]) -> list[dict]:
    """
    Modelos que o configurador novo lista sem nenhuma foto (ex.: Ariya)
    mas que existiam no catálogo antigo (packshot por versão+cor no CDN
    www-europe.nissan-cdn.net, que continua a responder) — convertidos
    para a estrutura nova em vez de desaparecerem.
    """
    out = []
    for m in previous.get("models", []):
        if m.get("type") != "legacy" or m["modelName"] in present:
            continue
        variants = []
        for g in m.get("grades", []):
            for v in g.get("versions", []):
                colors = [
                    {**c, "extId": c["code"], "images": [v["imageTemplate"].format(COLOR=c["code"])], "rotationKey": ""}
                    for c in v.get("colors", [])
                ]
                if colors:
                    variants.append({"idvc": "", "versionName": v["name"], "price": _float(v.get("startingPrice")),
                                     "colors": colors, "interiors": []})
        if variants:
            print(f"  mantido do catálogo antigo: {m['modelName']} ({len(variants)} versões)")
            out.append({"modelId": m.get("modelCode", m["modelName"]), "modelName": m["modelName"], "variants": variants})
    return out


def _build_catalog() -> dict:
    print("A construir catálogo Nissan (configurador.nissan.pt)...")
    models_out = []
    for m in _get_json(f"{API_BASE}/models"):
        model_id, model_code = m["modelID"], m["localCode"]
        name = _display_name(m["modelName"])
        print(f"\n  {name} ({model_id}/{model_code})")
        try:
            versions = _get_json(f"{API_BASE}/versions?modelID={model_id}&modelCode={model_code}")
            colors_data = _get_json(f"{API_BASE}/colors?modelID={model_id}&modelCode={model_code}")
        except Exception as e:
            print(f"    ERRO: {e}")
            continue

        ext = (colors_data.get("exteriorColors") or [{}])[0]
        colors_by_idvc = defaultdict(list)
        for c in ext.get("colors", []):
            colors_by_idvc[str(c["idvc"])].append(c)
        gallery = defaultdict(list)
        for g in ext.get("gallery", []):
            for item in g.get("lst", []):
                key = (str(g["idvc"]), str(item["idColor"]))
                if item["image"] not in gallery[key]:
                    gallery[key].append(item["image"])
        interiors = interiors_by_version(colors_data.get("interiorColors") or [])
        rotation_keys = _rotation_keys(name)

        variants_out = []
        for v in versions:
            idvc = str(v["idvc"])
            colors_out = []
            for c in colors_by_idvc.get(idvc, []):
                imgs = gallery.get((idvc, str(c["id"])), [])
                if not imgs:
                    continue
                rot = f"COL{c.get('factoryCode', '')}"
                colors_out.append({
                    "extId": str(c["id"]),
                    "code": c.get("factoryCode") or str(c["id"]),
                    "name": c["designation"].strip(),
                    "price": _float(c.get("price")),
                    "swatchUrl": c.get("colorchip") or "",
                    "images": imgs,
                    "rotationKey": rot if rot in rotation_keys else "",
                })
            if not colors_out:
                print(f"    versão sem cores com imagem: {v.get('versionName')} — a ignorar")
                continue
            variants_out.append({
                "idvc": idvc,
                "versionName": (v.get("versionName") or "").strip(),
                "price": _float(v.get("price")),
                "colors": colors_out,
                "interiors": interiors.get(idvc, []),
            })
            print(f"    {variants_out[-1]['versionName']}: {len(colors_out)} cores, {len(variants_out[-1]['interiors'])} interiores")

        if variants_out:
            models_out.append({"modelId": model_code, "modelName": name, "variants": variants_out})

    if DATA_FILE.exists():
        with open(DATA_FILE, encoding="utf-8") as f:
            models_out += _legacy_fallback(json.load(f), {m["modelName"] for m in models_out})

    catalog = {"models": models_out}
    DATA_FILE.parent.mkdir(exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"\nCatálogo guardado: {DATA_FILE}")
    return catalog


def build_catalog(force: bool = False) -> dict:
    if not force and DATA_FILE.exists():
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return _build_catalog()


def load_catalog() -> dict:
    return build_catalog(force=False)


if __name__ == "__main__":
    cat = build_catalog(force=True)
    print(f"\nTotal: {len(cat['models'])} modelos, {sum(len(m['variants']) for m in cat['models'])} versões")
