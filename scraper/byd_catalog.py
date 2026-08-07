"""
Catálogo BYD via API REST (www.byd-auto.pt/api/...) — site oficial da BYD
em Portugal (distribuído pela Salvador Caetano Auto, LHD, à esquerda —
não confundir com o site global byd.com/pt, que não tem loja/configurador
em PT, nem com o configurador do Reino Unido, que é RHD).

Estrutura: modelo → versões (acabamento) → cores exteriores, cada uma já
com uma galeria de fotos fixas (sem jantes seleccionáveis — o tamanho de
jante é uma especificação da versão, não uma opção; sem cor de interior
seleccionável tal como nas outras marcas já integradas).

Ângulos confirmados visualmente (consistentes em 6 modelos testados,
sempre exactamente 5 imagens): índice 0 = 3/4 frente, 1 = frente,
2 = lado, 3 = traseira, 4 = lado (direção oposta, imagem real e
distinta, confirmada por hash). As fotos já vêm em fundo branco.

Cache em data/byd_catalog.json.
"""
import json
import ssl
import urllib.request
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_PATH = DATA_DIR / "byd_catalog.json"
API_BASE = "https://www.byd-auto.pt/api"

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.byd-auto.pt/",
}

_VIEW_ORDER = ["3_4_frente", "frente", "lado", "traseira", "lado_oposto"]


def _get_json(url: str):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=30) as r:
        return json.load(r)


def _fetch_models() -> list[dict]:
    return _get_json(f"{API_BASE}/models")


def _fetch_versions(model_id: int, model_code: str) -> list[dict]:
    url = f"{API_BASE}/services/versions?modelID={model_id}&modelCode={model_code}"
    return _get_json(url)


def _fetch_colors(model_id: int, model_code: str) -> dict:
    url = f"{API_BASE}/services/colors?modelID={model_id}&modelCode={model_code}"
    data = _get_json(url)
    entries = data.get("exteriorColors") or []
    return entries[0] if entries else {}


def _build_catalog() -> dict:
    print("A construir catálogo BYD...")
    models_raw = _fetch_models()

    models_out = []
    for m in models_raw:
        model_id = m["modelID"]
        model_code = m["localCode"]
        model_name = m["modelName"]
        print(f"\n  {model_name} ({model_id}/{model_code})")

        try:
            versions = _fetch_versions(model_id, model_code)
        except Exception as e:
            print(f"    ERRO a obter versões: {e}")
            continue
        try:
            color_entry = _fetch_colors(model_id, model_code)
        except Exception as e:
            print(f"    ERRO a obter cores: {e}")
            continue

        colors_by_idvc = defaultdict(list)
        for c in color_entry.get("colors", []):
            colors_by_idvc[c["idvc"]].append(c)

        gallery_by_idvc = {}
        for g in color_entry.get("gallery", []):
            images_by_color = defaultdict(list)
            for item in g["lst"]:
                images_by_color[item["idColor"]].append(item["image"])
            gallery_by_idvc[g["idvc"]] = images_by_color

        variants_out = []
        for v in versions:
            idvc = v["idvc"]
            version_name = v["versionName"]
            cols = colors_by_idvc.get(idvc, [])
            images_by_color = gallery_by_idvc.get(idvc, {})

            colors_out = []
            for c in cols:
                imgs = images_by_color.get(c["id"], [])
                if len(imgs) < len(_VIEW_ORDER):
                    print(f"    aviso: {version_name} / {c['designation']} sem fotos suficientes "
                          f"({len(imgs)}/{len(_VIEW_ORDER)}) — a ignorar cor")
                    continue
                colors_out.append({
                    "code": c.get("factoryCode") or str(c["id"]),
                    "name": c["designation"],
                    "price": c.get("price", 0) or 0,
                    "swatchUrl": c.get("colorchip", ""),
                    "images": dict(zip(_VIEW_ORDER, imgs)),
                })

            if not colors_out:
                print(f"    versão sem cores válidas: {version_name} — a ignorar")
                continue

            variants_out.append({
                "versionName": version_name,
                "price": v.get("price", 0) or 0,
                "colors": colors_out,
            })

        if not variants_out:
            print("    sem versões válidas — a ignorar modelo")
            continue

        models_out.append({
            "modelId": model_code,
            "modelName": model_name,
            "variants": variants_out,
        })

    catalog = {"models": models_out}
    DATA_DIR.mkdir(exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"\nCatálogo guardado: {CACHE_PATH}")
    return catalog


def build_catalog(force: bool = False) -> dict:
    if not force and CACHE_PATH.exists():
        print(f"Catálogo em cache: {CACHE_PATH}")
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return _build_catalog()


def load_catalog() -> dict:
    return build_catalog(force=False)


if __name__ == "__main__":
    cat = build_catalog(force=True)
    total_variants = sum(len(m["variants"]) for m in cat["models"])
    print(f"\nTotal: {len(cat['models'])} modelos, {total_variants} versões")
    for m in cat["models"]:
        print(f"\n{m['modelName']} ({m['modelId']})")
        for v in m["variants"]:
            print(f"  [{v['versionName']}] {len(v['colors'])} cor(es)")
