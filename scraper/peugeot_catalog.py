"""
Catálogo Peugeot via GraphQL (store.peugeot.pt/api/graphql).
Estrutura: modelo → variantes (trims: Style/Allure/GT) → cores disponíveis.
Combina getMtoOffers + getHotOffers + getDealerStockOffers.
Cache em data/peugeot_catalog.json.
"""
import json, ssl, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

from scraper.opel_catalog import interiors_for_variant, trim_interiors

DATA_DIR   = Path(__file__).parent.parent / "data"
CACHE_PATH = DATA_DIR / "peugeot_catalog.json"
GQL        = "https://store.peugeot.pt/api/graphql"

_V3D_COLORS = "https://visuel3d-secure.peugeot.com/v3dcentral/Colors/NDP/th_{}.png"
_V3D_TRIMS  = "https://visuel3d-secure.peugeot.com/v3dcentral/Trims/ndp/th_{}.png"

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode    = ssl.CERT_NONE

_GQL_HEADERS = {
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "Referer":      "https://store.peugeot.pt/stock?channel=b2c",
    "Origin":       "https://store.peugeot.pt",
}

# Slugs que diferem entre mtoOffers e stockOffers
_SLUG_ALIASES = {
    "novo-308-berlina": "novo-308-5-portas",
    "novo-408-berlina": "novo-408-5-portas",
}

# Nomes dos modelos eléctricos (slug base → nome display)
_EV_MODEL_NAMES = {
    "208-5-portas":      "e-208",
    "2008-suv":          "e-2008",
    "novo-308-5-portas": "e-308",
    "novo-308-sw":       "e-308 SW",
    "novo-408-5-portas": "e-408",
    "3008-suv":          "e-3008",
    "5008-suv":          "e-5008",
}

# Cache de nomes de cores (id → nome PT) populado a partir das respostas GraphQL
_color_names: dict = {}

# Ordem de apresentação dos trims
_TRIM_ORDER = ["STYLE___", "EDITION0", "ALLURE__", "GT______", "GT_EXCLU"]
_TRIM_NAMES = {
    "STYLE___": "Style",
    "EDITION0": "Edition",
    "ALLURE__": "Allure",
    "GT______": "GT",
    "GT_EXCLU": "GT Exclusive",
}


def load_catalog(force_refresh=False):
    if not force_refresh and CACHE_PATH.exists():
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return _build_catalog()


# ─────────────────────────────────────────────────────────────────────────────

def _gql(query, variables=None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    body = json.dumps(payload).encode()
    req  = urllib.request.Request(GQL, data=body, headers=_GQL_HEADERS, method="POST")
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=20) as r:
        return json.load(r)


def _build_catalog():
    """Constrói catálogo com variantes (trims) e cores por modelo."""
    # model_slug → { modelName, variants: {trimId → {...}}, colors: {colorId → {...}} }
    models = {}

    # ── getHotOffers — fonte principal para variantes ─────────────────────────
    try:
        res = _gql("""
        {
            getHotOffers {
                offers {
                    externalId
                    lcdv16
                    nameplateBodyStyleSlug
                    model { id title }
                    bodyStyle { title }
                    trim { id title }
                    engine { title }
                    exteriorColour { id title }
                    custom
                }
            }
        }
        """)
        for o in res["data"]["getHotOffers"]["offers"]:
            _process_offer(models, o)
    except Exception as e:
        print(f"getHotOffers falhou: {e}")
        return _scrape_catalog_playwright()

    # ── getMtoOffers — garante os modelos principais ──────────────────────────
    try:
        res = _gql("""
        {
            getMtoOffers {
                offers {
                    externalId
                    lcdv16
                    nameplateBodyStyleSlug
                    model { id title }
                    bodyStyle { title }
                    trim { id title }
                    engine { title }
                    exteriorColour { id title }
                    custom
                }
            }
        }
        """)
        for o in res["data"]["getMtoOffers"]["offers"]:
            _process_offer(models, o)
    except Exception as e:
        print(f"getMtoOffers falhou (ignorado): {e}")

    # ── getDealerStockOffers — cores adicionais ───────────────────────────────
    try:
        res = _gql("""
        {
            getDealerStockOffers {
                offers {
                    lcdv16
                    nameplateBodyStyleSlug
                    model { id title }
                    bodyStyle { title }
                    engine { title }
                    exteriorColour { id title }
                }
            }
        }
        """)
        for o in res["data"]["getDealerStockOffers"]["offers"]:
            _add_stock_color(models, o)
    except Exception as e:
        print(f"getDealerStockOffers falhou (ignorado): {e}")

    _merge_validated_colors(models)

    # Interiores por acabamento (os GT têm 2) — a loja só conhece o slug
    # base do modelo; as versões eléctricas ("-ev") partilham-no
    print("A obter os interiores por acabamento...")
    trims_by_base = {}
    for slug in models:
        base = slug.removesuffix("-ev")
        if base not in trims_by_base:
            try:
                trims_by_base[base] = trim_interiors(_gql, base)
            except Exception as e:
                print(f"    ERRO acabamentos de {base}: {e}")
                trims_by_base[base] = []
        models[slug]["trims"] = trims_by_base[base]

    return _save_catalog(models)


def _merge_validated_colors(models):
    """Adiciona cores validadas por V3D pixel (de peugeot_colors_per_model.json) se disponível."""
    colors_file = DATA_DIR / "peugeot_colors_per_model.json"
    if not colors_file.exists():
        return
    with open(colors_file, encoding="utf-8") as f:
        per_model = json.load(f)
    for slug, validated in per_model.items():
        norm = _normalise_slug(slug)
        # Aplica cores validadas ao modelo base e ao modelo EV correspondente
        for target_slug in [norm, f"{norm}-ev"]:
            target = models.get(target_slug)
            if not target:
                continue
            for cid, cname in validated.items():
                if cid not in target["colors"]:
                    official = _color_names.get(cid, cname)
                    target["colors"][cid] = {
                        "id":       cid,
                        "name":     official,
                        "swatchUrl": _V3D_COLORS.format(cid),
                    }


def _normalise_slug(slug):
    return _SLUG_ALIASES.get(slug, slug)


def _is_ev(o):
    engine = (o.get("engine") or {}).get("title", "")
    return "létrico" in engine or "léctrico" in engine or "Electric" in engine


def _process_offer(models, o):
    """Adiciona um offer ao dicionário models, criando variante e cor se necessário."""
    base_slug = _normalise_slug(o.get("nameplateBodyStyleSlug", ""))
    if not base_slug:
        return

    ev   = _is_ev(o)
    slug = f"{base_slug}-ev" if ev else base_slug

    ext_id   = o.get("externalId") or ""
    parts    = ext_id.split("+") if ext_id else []
    version  = parts[0] if parts and parts[0] else o.get("lcdv16", "")
    color_id = parts[1] if len(parts) > 1 else (o.get("exteriorColour") or {}).get("id", "")
    trim_code= parts[2] if len(parts) > 2 else ""

    model_data  = o.get("model") or {}
    body_data   = o.get("bodyStyle") or {}
    ext_data    = o.get("exteriorColour") or {}
    trim_data   = o.get("trim") or {}
    custom      = o.get("custom") or {}

    model_title = model_data.get("title", "")
    body_title  = body_data.get("title", "")
    show_body   = custom.get("showExtendedBodyStyleLabel", False) if isinstance(custom, dict) else False

    if ev:
        model_label = _EV_MODEL_NAMES.get(base_slug, f"e-{model_title}".strip())
    else:
        model_label = f"{model_title} {body_title}".strip() if show_body else model_title

    trim_gql_id = trim_data.get("id", "")  # ex: "STYLE___"
    trim_name   = _TRIM_NAMES.get(trim_gql_id, trim_data.get("title", trim_gql_id).strip("_"))
    color_name  = ext_data.get("title", color_id)
    if color_id and color_name and color_name != color_id:
        _color_names[color_id] = color_name

    if not slug or not version:
        return

    if slug not in models:
        models[slug] = {"modelName": model_label or slug, "bodyTitle": body_title, "variants": {}, "colors": {}}

    # Adicionar variante (trim) se nova
    if trim_gql_id and trim_gql_id not in models[slug]["variants"]:
        models[slug]["variants"][trim_gql_id] = {
            "variantId":   trim_gql_id,
            "variantName": trim_name,
            "lcdv16":      version,
            "trimCode":    trim_code,
        }

    # Adicionar cor ao modelo (se ainda não existe)
    if color_id and color_id not in models[slug]["colors"]:
        models[slug]["colors"][color_id] = {
            "id":       color_id,
            "name":     color_name,
            "swatchUrl": _V3D_COLORS.format(color_id) if color_id else "",
        }


def _add_stock_color(models, o):
    """Adiciona apenas a cor de um stock offer (sem variante — sem trim info)."""
    base_slug = _normalise_slug(o.get("nameplateBodyStyleSlug", ""))
    if not base_slug:
        return
    slug = f"{base_slug}-ev" if _is_ev(o) else base_slug
    if slug not in models:
        return
    ext_data = o.get("exteriorColour") or {}
    color_id = ext_data.get("id", "")
    color_name = ext_data.get("title", color_id)
    if color_id and color_id not in models[slug]["colors"]:
        models[slug]["colors"][color_id] = {
            "id":       color_id,
            "name":     color_name,
            "swatchUrl": _V3D_COLORS.format(color_id) if color_id else "",
        }


def _save_catalog(models):
    # Detectar nomes duplicados para disambiguação
    name_counts = {}
    for data in models.values():
        n = data["modelName"]
        name_counts[n] = name_counts.get(n, 0) + 1

    result_models = []
    for slug, data in models.items():
        colors_list = [c for c in data["colors"].values() if c["id"]]
        if not colors_list:
            continue

        # Ordenar variantes pelo _TRIM_ORDER
        raw_variants = data["variants"]
        sorted_variants = sorted(
            raw_variants.values(),
            key=lambda v: _TRIM_ORDER.index(v["variantId"])
            if v["variantId"] in _TRIM_ORDER else 99,
        )

        if not sorted_variants:
            continue

        # Cada variante inclui todas as cores do modelo
        variants_out = [
            {
                "variantId":   v["variantId"],
                "variantName": v["variantName"],
                "lcdv16":      v["lcdv16"],
                "trimCode":    v["trimCode"],
                "colors":      colors_list,
                "interiors":   interiors_for_variant(data.get("trims") or [], v["trimCode"], v["variantId"]),
            }
            for v in sorted_variants
            if v["lcdv16"] and v["trimCode"]
        ]

        if not variants_out:
            continue

        display_name = data["modelName"]
        if name_counts.get(display_name, 0) > 1 and data.get("bodyTitle"):
            display_name = f"{display_name} {data['bodyTitle']}"

        result_models.append({
            "modelId":   slug,
            "modelName": display_name,
            "variants":  variants_out,
        })

    catalog = {"models": result_models}
    DATA_DIR.mkdir(exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    return catalog


# ── Fallback Playwright ───────────────────────────────────────────────────────

def _scrape_catalog_playwright():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.goto(
            "https://store.peugeot.pt/configurable?channel=b2c",
            wait_until="networkidle",
            timeout=40000,
        )
        time.sleep(3)
        nd = page.evaluate("() => window.__NEXT_DATA__ || null")
        browser.close()

    if not nd:
        raise RuntimeError("Não foi possível carregar o catálogo Peugeot")
    props  = nd.get("props", {})
    pp     = props.get("pageProps") or props.get("initialProps", {})
    mto    = pp.get("mtoOffers") or {}
    offers_raw = mto.get("offers", [])
    if not offers_raw:
        raise RuntimeError("Nenhum offer encontrado.")
    models = {}
    for o in offers_raw:
        _process_offer(models, o)
    return _save_catalog(models)


if __name__ == "__main__":
    cat = load_catalog(force_refresh=True)
    for m in cat["models"]:
        print(f"\n{m['modelName']} ({m['modelId']}) — {len(m['variants'])} variante(s), {len(m['variants'][0]['colors'])} cor(es)")
        for v in m["variants"]:
            print(f"  [{v['variantName']}] lcdv16={v['lcdv16']} trimCode={v['trimCode']}")
        for c in m["variants"][0]["colors"]:
            print(f"    cor: {c['name']} ({c['id']})")
