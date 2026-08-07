"""
Extrai o catálogo XPENG Portugal (xpeng-auto.pt): modelos, versões e cores.

API própria e simples, sem necessidade de Playwright — dois pedidos GET
por modelo (`/api/services/colors` e `/api/services/engines`, ambos com
`modelID=-1` para devolver TODAS as motorizações de uma vez, não só a
seleccionada). Junta-se pelo campo `idvc` (id da versão comercial),
comum aos dois. As imagens já vêm resolvidas no campo `gallery` de
`colors` — não é preciso adivinhar nomes de ficheiro.

Limitação confirmada na própria API (testado em G6, G9 e P7+): há sempre
exactamente 2 fotografias reais por cor (3/4 frente + lado) — sem frente
recta, sem traseira, sem interior fotográfico. O campo "colorchip" das
cores de INTERIOR é só um ícone pequeno da textura (não uma foto do
habitáculo); o "panoramImg" é uma panorâmica equirectangular 360°, não
uma foto normal — nenhum dos dois serve como imagem de "interior" no
mesmo formato das outras marcas. O "colorchip" das cores EXTERIORES já é
um swatch de tinta real e utilizável (guardado como "swatchUrl"). O
modelo L03 não tem configurador nesta plataforma (404) — fica fora do
catálogo.

Cache em data/xpeng_catalog.json.
"""
import json
import ssl
import urllib.request
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent / "data" / "xpeng_catalog.json"
API_BASE = "https://www.xpeng-auto.pt/api/services"

# Não há forma de derivar o modelCode a partir do slug da página — foi
# confirmado por captura de rede em cada configurador (não está no HTML
# estático, só é usado via chamadas de API feitas em JS).
MODELS = [
    {"modelName": "XPENG G6", "modelCode": "FFBB123"},
    {"modelName": "XPENG G9", "modelCode": "EECY020"},
    {"modelName": "XPENG P7+", "modelCode": "FJBB000"},
]

_ssl_ctx = ssl.create_default_context()
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "application/json"}


def _get_json(url: str) -> dict | list:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        return json.loads(r.read())


def _build_model(model_name: str, model_code: str) -> dict | None:
    colors_data = _get_json(f"{API_BASE}/colors?modelID=-1&modelCode={model_code}")
    engines = _get_json(f"{API_BASE}/engines?modelID=-1&modelCode={model_code}")

    engines_by_idvc = {e["idvc"]: e for e in engines}

    # gallery[] e colors[] de cada grupo exteriorColors partilham o mesmo
    # "idvc" — juntar num dict idvc -> {colorId: [urls]}
    gallery_by_idvc: dict[int, dict[int, list[str]]] = {}
    for group in colors_data.get("exteriorColors", []):
        for g in group.get("gallery", []):
            by_color: dict[int, list[str]] = {}
            for item in g.get("lst", []):
                by_color.setdefault(item["idColor"], []).append(item["image"])
            gallery_by_idvc[g["idvc"]] = by_color

    colors_by_idvc: dict[int, list[dict]] = {}
    for group in colors_data.get("exteriorColors", []):
        for c in group.get("colors", []):
            colors_by_idvc.setdefault(c["idvc"], []).append(c)

    versions_out = []
    for idvc, eng in engines_by_idvc.items():
        colors_list = colors_by_idvc.get(idvc, [])
        gallery = gallery_by_idvc.get(idvc, {})
        colors_out = [
            {
                "code": c["id"],
                "name": c["designation"],
                "price": c.get("price", 0) or 0,
                "images": gallery.get(c["id"], []),
                "swatchUrl": c.get("colorchip", ""),
            }
            for c in colors_list
            if gallery.get(c["id"])
        ]
        if not colors_out:
            continue
        versions_out.append({
            "idvc": idvc,
            "versionName": eng.get("versionName", ""),
            "price": eng.get("price", 0) or 0,
            "colors": colors_out,
        })

    if not versions_out:
        return None
    return {"modelName": model_name, "modelCode": model_code, "versions": versions_out}


def build_catalog(force: bool = False) -> dict:
    if DATA_FILE.exists() and not force:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))

    catalog = {"models": []}
    for m in MODELS:
        print(f"A processar {m['modelName']}...")
        entry = _build_model(m["modelName"], m["modelCode"])
        if entry:
            catalog["models"].append(entry)
            n_colors = sum(len(v["colors"]) for v in entry["versions"])
            print(f"  {len(entry['versions'])} versões, {n_colors} combinações de cor")

    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    return catalog


def load_catalog() -> dict:
    return build_catalog(force=False)


if __name__ == "__main__":
    cat = build_catalog(force=True)
    print("\nTotal modelos:", len(cat["models"]))
