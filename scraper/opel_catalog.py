"""
Catálogo Opel via GraphQL (store.opel.pt/graphql).

Mesma plataforma Stellantis (GraphQL + visualizador V3D) que a Peugeot,
só muda o domínio de imagens (visual3d-secure.opel-vauxhall.com) e o
facto de a Opel expor jantes como uma opção normal (categoria "Jantes"
na query GetOptions), em vez de nem ter esse conceito como a Peugeot.

Cada combinação acabamento × motor sellable (ex: "Edition" a gasolina e
"Edition" eléctrico do Mokka) é tratada como uma versão própria, chaveada
por lcdv16 — ao contrário da Peugeot, onde motor não é um eixo relevante.

Cache em data/opel_catalog.json.
"""
import json
import ssl
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_PATH = DATA_DIR / "opel_catalog.json"
GQL = "https://store.opel.pt/graphql"

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_GQL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Referer": "https://store.opel.pt/configurable?channel=b2c",
    "Origin": "https://store.opel.pt",
}

_OPTIONS_QUERY = """
query GetOptions($input: OptionsInput!) {
  options(input: $input) {
    error
    options(sort: ["order:asc"]) {
      id
      title
      category
      images { url }
      prices { cash { baseAmount } }
    }
  }
}
"""


def load_catalog(force_refresh=False):
    if not force_refresh and CACHE_PATH.exists():
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return _build_catalog()


# ─────────────────────────────────────────────────────────────────────────────

def _gql(query, variables=None):
    payload = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    body = json.dumps(payload).encode()
    req = urllib.request.Request(GQL, data=body, headers=_GQL_HEADERS, method="POST")
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=20) as r:
        return json.load(r)


def _fetch_offers(query_name):
    res = _gql(f"""
    {{
        {query_name} {{
            offers {{
                externalId
                lcdv16
                nameplateBodyStyleSlug
                model {{ title }}
                bodyStyle {{ title }}
                trim {{ id title }}
                engine {{ title }}
                exteriorColour {{ id title }}
                custom
            }}
        }}
    }}
    """)
    return res.get("data", {}).get(query_name, {}).get("offers", []) or []


def _wheels_for(external_id):
    """
    Jantes para uma configuração: a query GetOptions só devolve upgrades
    pagos (categoria "Jantes") — a jante de série incluída no acabamento
    nunca aparece aí, porque não é uma opção "adicionável". Sem a
    acrescentarmos à mão, o utilizador ficava sem forma de escolher a
    jante de série e era obrigado a pagar por um upgrade.
    """
    res = _gql(_OPTIONS_QUERY, {"input": {"configuration": external_id, "options": []}})
    options = (res.get("data", {}).get("options", {}) or {}).get("options", []) or []
    upgrades = [
        {
            "code": o["id"],
            "name": o["title"],
            "price": ((o.get("prices") or {}).get("cash") or {}).get("baseAmount", 0) or 0,
            "imageUrl": ((o.get("images") or [{}])[0] or {}).get("url", ""),
        }
        for o in options
        if o.get("category") == "Jantes"
    ]
    if not upgrades:
        return []
    base = {"code": "", "name": "Jantes", "price": 0}
    return [base] + upgrades


_STORE_BASE = "https://store.opel.pt"

_FULL_COLORS_QUERY = """
query getProductOfferColors($input: DimensionsInput!) {
  getProductOffer(input: $input) {
    configurationOptions {
      exteriorColours(sort: ["prices.cash.baseAmount:asc"]) {
        id
        title
        image
        prices { cash { baseAmount } }
      }
      interiorColours {
        id
        title
        image
        prices { cash { baseAmount } }
      }
    }
  }
}
"""


def _discover_seed_urls(model_slugs):
    """
    A lista de cores por oferta (getHotOffers/getMtoOffers) é uma amostra,
    não a paleta toda de cada modelo. Para a paleta completa é preciso
    chamar getProductOffer, que exige "slugs" (model/trim/engineGearbox/
    exteriorColour/interiorColour) em vez dos códigos que já temos.
    Navegar para /selector/configurable/{slug} sem mais nada faz o site
    preencher esses slugs por defeito — um pedido leve por modelo.
    """
    seeds = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
        page = ctx.new_page()
        for slug in model_slugs:
            try:
                page.goto(f"{_STORE_BASE}/selector/configurable/{slug}?channel=b2c",
                           wait_until="networkidle", timeout=30000)
                time.sleep(1)
                path = page.url.split("?")[0].split("/selector/configurable/")[-1]
                segments = [s for s in path.strip("/").split("/") if s]
                if len(segments) >= 5:
                    seeds[slug] = {
                        "model": segments[0],
                        "trim": segments[1],
                        "engineGearbox": segments[2],
                        "exteriorColour": segments[3],
                        "interiorColour": segments[4],
                    }
                else:
                    print(f"    seed incompleto para {slug}: {path}")
            except Exception as e:
                print(f"    seed falhou para {slug}: {e}")
        browser.close()
    return seeds


def _full_colors_for(seed_input):
    """(cores exteriores completas do modelo, cores de interior do acabamento
    do seed). O interior na Stellantis é o código "trim" do V3D; a maioria
    dos acabamentos só tem 1, mas alguns têm 2 (ex.: Frontera e Zafira
    Edition) — a imagem muda com o código."""
    variables = {"input": {**seed_input, "options": [], "accessories": []}, "page": "config"}
    res = _gql(_FULL_COLORS_QUERY, variables)
    if "errors" in res:
        raise RuntimeError(res["errors"])
    co = (res.get("data", {}).get("getProductOffer") or {}).get("configurationOptions") or {}
    colours = co.get("exteriorColours", []) or []
    exterior = {
        c["id"]: {
            "code": c["id"],
            "name": c["title"],
            "price": ((c.get("prices") or {}).get("cash") or {}).get("baseAmount", 0) or 0,
            "swatchUrl": c.get("image") or "",
        }
        for c in colours
        if c.get("id")
    }
    interiors = [
        {
            "code": i["id"],
            "name": i["title"].strip(),
            "price": ((i.get("prices") or {}).get("cash") or {}).get("baseAmount", 0) or 0,
            "swatchUrl": i.get("image") or "",
        }
        for i in co.get("interiorColours", []) or []
        if i.get("id")
    ]
    return exterior, interiors


_TRIM_INTERIORS_QUERY = """
query getTrimInteriors($input: DimensionsInput!) {
  getProductOffer(input: $input) {
    configurationOptions {
      trims { id slug title }
      interiorColours {
        id
        title
        image
        prices { cash { baseAmount } }
      }
    }
  }
}
"""


def trim_interiors(gql, model_slug: str) -> list[dict]:
    """
    Interiores por acabamento (loja Stellantis — Opel e Peugeot). Basta
    {model} para obter os acabamentos e {model, trim} para os interiores
    desse acabamento; motor e cores são opcionais. `gql(query, variables)`
    é o cliente GraphQL da marca. Devolve [{id, title, interiors}].
    """
    def options(**dims):
        res = gql(_TRIM_INTERIORS_QUERY, {"input": {**dims, "options": [], "accessories": []}})
        return ((res.get("data") or {}).get("getProductOffer") or {}).get("configurationOptions") or {}

    out = []
    for t in options(model=model_slug).get("trims") or []:
        try:
            co = options(model=model_slug, trim=t["slug"])
        except Exception as e:
            print(f"    ERRO interiores {model_slug}/{t.get('slug')}: {e}")
            continue
        out.append({
            "id": t["id"],
            "title": (t.get("title") or "").strip(),
            "interiors": [
                {
                    "code": i["id"],
                    "name": i["title"].strip(),
                    "price": ((i.get("prices") or {}).get("cash") or {}).get("baseAmount", 0) or 0,
                    "swatchUrl": i.get("image") or "",
                }
                for i in co.get("interiorColours") or []
                if i.get("id")
            ],
        })
    return out


def interiors_for_variant(trims: list[dict], trim_code: str, trim_id: str = "", version_name: str = "") -> list[dict]:
    """
    Escolhe o acabamento da versão: pelo id (Peugeot guarda-o), senão pela
    1.ª palavra do nome da versão (Opel: "GS Hybrid ..." -> "GS"), senão
    pelo acabamento cuja lista inclui o interior de série. O interior de
    série da versão vem primeiro.
    """
    first_word = (version_name.split() or [""])[0].lower()
    match = (
        next((t for t in trims if trim_id and t["id"] == trim_id), None)
        or next((t for t in trims if first_word and t["title"].lower() == first_word), None)
        or next((t for t in trims if any(i["code"] == trim_code for i in t["interiors"])), None)
    )
    if not match or not any(i["code"] == trim_code for i in match["interiors"]):
        return []
    return sorted(match["interiors"], key=lambda i: i["code"] != trim_code)


def _swatch_url(lcdv16: str, color_id: str) -> str:
    """
    O thumbnail da cor vive num caminho com prefixo específico do modelo
    (ex: V3DCentral/1GJO/A5/Colors/...), derivado dos primeiros 6
    caracteres do lcdv16 da própria oferta que introduziu esta cor.
    """
    if len(lcdv16) < 6 or not color_id:
        return ""
    return f"https://visual3d-secure.opel-vauxhall.com/V3DCentral/{lcdv16[:4]}/{lcdv16[4:6]}/Colors/{color_id}.jpg"


def _build_catalog():
    print("A construir catálogo Opel...")
    models = {}

    for query_name in ["getHotOffers", "getMtoOffers"]:
        try:
            offers = _fetch_offers(query_name)
        except Exception as e:
            print(f"{query_name} falhou: {e}")
            continue
        for o in offers:
            _process_offer(models, o)

    print("A obter a paleta de cores completa por modelo...")
    seeds = _discover_seed_urls(list(models.keys()))
    for slug, seed in seeds.items():
        try:
            full_colors, interiors = _full_colors_for(seed)
        except Exception as e:
            print(f"    ERRO cores completas de {slug}: {e}")
            continue
        if full_colors:
            models[slug]["colors"] = full_colors
        models[slug]["seedInteriors"] = interiors

    print("A obter os interiores por acabamento...")
    for slug in models:
        try:
            models[slug]["trims"] = trim_interiors(_gql, slug)
        except Exception as e:
            print(f"    ERRO acabamentos de {slug}: {e}")

    return _save_catalog(models)


def _process_offer(models, o):
    slug = o.get("nameplateBodyStyleSlug", "")
    if not slug:
        return

    lcdv16 = o.get("lcdv16", "")
    ext_id = o.get("externalId", "")
    parts = ext_id.split("+") if ext_id else []
    color_id = parts[1] if len(parts) > 1 else (o.get("exteriorColour") or {}).get("id", "")
    trim_code = parts[2] if len(parts) > 2 else ""
    if not lcdv16 or not color_id or not trim_code:
        return

    model_data = o.get("model") or {}
    body_data = o.get("bodyStyle") or {}
    ext_data = o.get("exteriorColour") or {}
    trim_data = o.get("trim") or {}
    engine_data = o.get("engine") or {}
    custom = o.get("custom") or {}

    model_title = model_data.get("title", "")
    body_title = body_data.get("title", "")
    show_body = custom.get("showExtendedBodyStyleLabel", False) if isinstance(custom, dict) else False
    model_label = f"{model_title} {body_title}".strip() if show_body else model_title

    trim_title = trim_data.get("title", "") or trim_data.get("id", "")
    engine_title = engine_data.get("title", "")
    color_name = ext_data.get("title", color_id)

    if slug not in models:
        models[slug] = {"modelName": model_label or slug, "bodyTitle": body_title, "variants": {}, "colors": {}}

    if lcdv16 not in models[slug]["variants"]:
        version_name = f"{trim_title} {engine_title}".strip()
        models[slug]["variants"][lcdv16] = {
            "versionName": version_name,
            "lcdv16": lcdv16,
            "trimCode": trim_code,
            "externalId": ext_id,
        }

    if color_id and color_id not in models[slug]["colors"]:
        models[slug]["colors"][color_id] = {
            "code": color_id,
            "name": color_name,
            "price": 0,  # substituído pelo preço real quando a paleta completa é obtida
            "swatchUrl": _swatch_url(lcdv16, color_id),
        }


def _save_catalog(models):
    name_counts = {}
    for data in models.values():
        n = data["modelName"]
        name_counts[n] = name_counts.get(n, 0) + 1

    result_models = []
    for slug, data in models.items():
        colors_list = [c for c in data["colors"].values() if c["code"]]
        if not colors_list:
            continue

        variants_out = []
        for v in data["variants"].values():
            print(f"    a carregar jantes: {v['versionName']} ({v['lcdv16']})")
            try:
                wheels = _wheels_for(v["externalId"])
            except Exception as e:
                print(f"      ERRO jantes: {e}")
                wheels = []
            seed_ints = data.get("seedInteriors") or []
            trim_ints = interiors_for_variant(data.get("trims") or [], v["trimCode"], version_name=v["versionName"])
            variants_out.append({
                "versionName": v["versionName"],
                "lcdv16": v["lcdv16"],
                "trimCode": v["trimCode"],
                "colors": colors_list,
                "wheels": wheels,
                # interiores do acabamento; se a consulta falhar, os do seed
                # (só válidos quando o acabamento é o do seed)
                "interiors": trim_ints or (
                    sorted(seed_ints, key=lambda i: i["code"] != v["trimCode"])
                    if any(i["code"] == v["trimCode"] for i in seed_ints) else []
                ),
            })

        if not variants_out:
            continue

        display_name = data["modelName"]
        if name_counts.get(display_name, 0) > 1 and data.get("bodyTitle"):
            display_name = f"{display_name} {data['bodyTitle']}"

        result_models.append({
            "modelId": slug,
            "modelName": display_name,
            "variants": variants_out,
        })

    catalog = {"models": result_models}
    DATA_DIR.mkdir(exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"Catálogo guardado: {CACHE_PATH}")
    return catalog


if __name__ == "__main__":
    cat = load_catalog(force_refresh=True)
    total_variants = sum(len(m["variants"]) for m in cat["models"])
    print(f"\nTotal: {len(cat['models'])} modelos, {total_variants} versões")
    for m in cat["models"]:
        print(f"\n{m['modelName']} ({m['modelId']}) — {len(m['variants'])} versão(ões), {len(m['variants'][0]['colors'])} cor(es)")
        for v in m["variants"]:
            print(f"  [{v['versionName']}] lcdv16={v['lcdv16']} jantes={len(v['wheels'])}")
