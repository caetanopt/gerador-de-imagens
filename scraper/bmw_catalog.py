"""
Extrai o catálogo BMW Portugal: modelos, cores e jantes.
Usa a API interna do configurador "Connext" (configure.bmw.pt), que corre
sobre prod.ucp.bmw.cloud (catálogo/regras) e prod.cosy.bmw.cloud (imagens).
As chaves x-api-key abaixo são chaves públicas do frontend (visíveis em
qualquer pedido do browser), não credenciais de utilizador.

Esta mesma plataforma "Connext" é partilhada por outras marcas do grupo
BMW (ex. MINI) — a lógica de catálogo (vehicle-tree, opções, sales-group-
-tree) é genérica em build_catalog_generic, parametrizada pela marca
("bmwCar"/"mini"), o namespace connext ("connext-bmw"/"connext-mini") e a
respectiva x-api-key. Reaproveitada por mini_catalog.py.

Ao contrário da VW/Audi (um parâmetro de cor/jante na URL da imagem), a
BMW exige a lista COMPLETA de códigos de opção válidos para essa
configuração. Por isso o catálogo guarda, por variante, uma lista
"baseOptions" (todas as opções de série menos pintura/jantes) à qual
basta acrescentar o código de cor e de jante escolhidos.

Cache em data/bmw_catalog.json.
"""
import datetime
import json
import ssl
import urllib.request
from pathlib import Path

UCP_BASE = "https://prod.ucp.bmw.cloud"
UCP_API_KEY = "OmFpaEFpV0VUaUlrWTJ2Tnp0ZGdiUTd1NDhxR3JOcHRacXg1UWQK"
# prod.cosy.bmw.cloud serve as imagens (render completo do carro e também
# miniaturas por opção). Exige uma x-api-key PRÓPRIA, diferente da UCP_API_KEY
# acima — confirmado via os pedidos reais do browser em configure.bmw.pt
# (também uma chave pública do frontend, não uma credencial de utilizador).
COSY_BASE = "https://prod.cosy.bmw.cloud"
COSY_API_KEY = "KLexy26ApAFmYH3aViwuLxf02wN1wqBATdFPONSig"
BRAND = "bmwCar"
CONNEXT_NS = "connext-bmw"
REFERER = "https://configure.bmw.pt/"
DATA_FILE = Path(__file__).parent.parent / "data" / "bmw_catalog.json"

_ssl_ctx = ssl.create_default_context()


def _headers(referer: str, api_key: str) -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": referer,
        "x-api-key": api_key,
    }


def _get(url: str, referer: str, api_key: str) -> dict | list:
    req = urllib.request.Request(url, headers=_headers(referer, api_key))
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=30) as r:
        return json.loads(r.read())


def _today() -> str:
    return datetime.date.today().isoformat()


def _fetch_vehicle_tree(connext_ns: str, brand: str, referer: str, api_key: str) -> dict:
    today = _today()
    url = (
        f"{UCP_BASE}/model-matrices/vehicle-trees/{connext_ns}/sources/sprint-cus/"
        f"brands/{brand}/countries/pt/effect-dates/{today}/order-dates/{today}"
        f"?gfs-policy=none&cluster=default&future-models=true&closest-fallback=true"
    )
    return _get(url, referer, api_key)


def _fetch_options_meta(model_code: str, brand: str, referer: str, api_key: str) -> dict:
    today = _today()
    url = (
        f"{UCP_BASE}/localisations/overridden-vehicle-data/sources/sprint-cus/"
        f"brands/{brand}/countries/pt/effect-dates/2026-09-08/order-dates/{today}/"
        f"applications/connext-sprint/models/{model_code}/options/languages/pt?trim=BASIC_LINE"
    )
    return _get(url, referer, api_key)


def _fetch_sales_group_tree(model_code: str, brand: str, referer: str, api_key: str) -> list:
    today = _today()
    url = (
        f"{UCP_BASE}/localisations/overridden-vehicle-data/sources/sprint-cus/"
        f"brands/{brand}/countries/pt/effect-dates/2026-09-08/order-dates/{today}/"
        f"applications/connext-sprint/sales-group-tree/models/{model_code}/languages/pt?trim=BASIC_LINE"
    )
    return _get(url, referer, api_key)


def _fetch_option_images(
    connext_ns: str, brand: str, model_code: str, effect_date: str,
    codes: list, referer: str, cosy_api_key: str,
) -> dict:
    """
    Busca, num único pedido, a miniatura ("tile_square") de cada código de
    opção indicado (cores e/ou jantes), via o mesmo endpoint de imagens
    ("option-selector-grid") que o configurador oficial usa para desenhar a
    grelha de selecção de cor/jante. Confirmado com pedidos de rede reais
    de configure.bmw.pt e configure.mini.pt (Playwright).
    Devolve {codigo: url_imagem}; omite silenciosamente códigos sem imagem
    disponível ou se o pedido falhar (a app deve continuar a funcionar sem
    miniaturas nesse caso).
    Nota: a API exige os códigos ORDENADOS alfabeticamente — de outra forma
    devolve 400 "options is not sorted".
    """
    if not codes:
        return {}
    effect_date_compact = effect_date.replace("-", "")
    options_param = ",".join(sorted(set(codes)))
    url = (
        f"{COSY_BASE}/image-urls/static-images/mandators/{connext_ns}/"
        f"collections/option-selector-grid/brands/{brand}/models/{model_code}/options"
        f"?effectdate={effect_date_compact}&hub=CLOUD_PROD_INTERNET&imagetype=webp"
        f"&options={options_param}&params.market=pt"
    )
    try:
        data = _get(url, referer, cosy_api_key)
    except Exception as e:
        print(f"      AVISO: falha a obter miniaturas de cor/jante: {e}")
        return {}
    mobile = data.get("collections", {}).get("option-selector-grid", {}).get("mobile", {})
    images = {}
    for code, entry in mobile.items():
        try:
            images[code] = entry["imageGroups"][0]["images"][0]["viewImage"]
        except (KeyError, IndexError, TypeError):
            continue
    return images


def _option_name(options_meta: dict, code: str) -> str:
    meta = options_meta.get(code, {})
    phrases = meta.get("phrases", {})
    return phrases.get("longDescription") or phrases.get("description") or code


def _find_node(nodes: list, node_code: str) -> dict | None:
    for n in nodes:
        if n.get("nodeCode") == node_code:
            return n
    return None


def _extract_colors_and_wheels(sgt: list, options_meta: dict) -> tuple[list, list]:
    """
    Percorre a sales-group-tree do modelo e devolve (colors, wheels).
    Cores: só as gamas "curadas" (BMW Individual, Metalizada, Sólida) —
    ignora "Pinturas Individual" (centenas de cores por encomenda especial,
    fora do catálogo padrão de concessionário).
    """
    colors, wheels = [], []
    exterior = _find_node(sgt, "EXTERIOR")
    if not exterior:
        return colors, wheels

    # nome do nó varia por marca: "COLOUR" na BMW, "BODY_COLOURS" na MINI.
    colour_node = _find_node(exterior.get("nodes", []), "COLOUR") or _find_node(
        exterior.get("nodes", []), "BODY_COLOURS"
    )
    if colour_node:
        for sub in colour_node.get("nodes", []):
            for code in sub.get("options", []):
                meta = options_meta.get(code, {})
                # Códigos de sobretaxa/companheiro automático (ex. "Pintura
                # BMW Individual") não são cores seleccionáveis por si só —
                # têm familyCode vazio, ao contrário de cores reais
                # (MET/UNI/SPPNT).
                if not meta.get("familyCode"):
                    continue
                colors.append({
                    "code": code,
                    "name": _option_name(options_meta, code),
                    "std": bool(meta.get("std", False)),
                    "group": sub.get("name", ""),
                })

    rims_node = _find_node(exterior.get("nodes", []), "RIMS")
    if rims_node:
        for code in rims_node.get("options", []):
            meta = options_meta.get(code, {})
            wheels.append({
                "code": code,
                "name": _option_name(options_meta, code),
                "std": bool(meta.get("std", False)),
            })

    return colors, wheels


def _extract_default_upholstery(sgt: list) -> str | None:
    """
    Devolve um código de estofo válido para completar a configuração (a
    API de imagens exige um, mas esta ferramenta não expõe a escolha de
    estofo ao utilizador — tal como acontece com defaultUpholstery na
    VW/Audi).
    """
    interior = _find_node(sgt, "INTERIOR")
    if not interior:
        return None
    upholstery_node = _find_node(interior.get("nodes", []), "UPHOLSTERY")
    if not upholstery_node:
        return None
    if upholstery_node.get("options"):
        return upholstery_node["options"][0]
    # Algumas marcas (ex. MINI) não listam os códigos directamente em
    # "UPHOLSTERY" — estão um nível abaixo, agrupados por material
    # (ex. "CLOTH_FABRICS"/"LEATHER").
    for sub in upholstery_node.get("nodes", []):
        if sub.get("options"):
            return sub["options"][0]
    return None


def _best_transmission_variant(model_val: dict) -> dict | None:
    variants = model_val.get("transmissionVariants", [])
    for v in variants:
        if v.get("constructible", True):
            return v
    return variants[0] if variants else None


def build_catalog_generic(
    brand_label: str,
    brand: str,
    connext_ns: str,
    ucp_api_key: str,
    cosy_api_key: str,
    referer: str,
    data_file: Path,
    force: bool = False,
) -> dict:
    """
    Constrói e guarda o catálogo de uma marca da plataforma "Connext" do
    grupo BMW. Usa cache se existir.
    """
    if not force and data_file.exists():
        print(f"Catálogo em cache: {data_file}")
        with open(data_file, encoding="utf-8") as f:
            return json.load(f)

    print(f"A construir catálogo {brand_label}...")
    data_file.parent.mkdir(exist_ok=True)

    tree = _fetch_vehicle_tree(connext_ns, brand, referer, ucp_api_key)

    # As mesmas gamas (ex. U11E da BMW) podem aparecer repetidas sob mais
    # do que uma série (ex. "X" e "i" partilham a iX1) — deduplicar por
    # rangeCode.
    ranges_by_code: dict[str, dict] = {}
    for series_val in tree.values():
        for range_code, range_val in series_val.get("modelRanges", {}).items():
            if range_code not in ranges_by_code:
                ranges_by_code[range_code] = range_val

    catalog = {"models": []}

    for range_code, range_val in ranges_by_code.items():
        desc = range_val.get("additionalData", {}).get("description", {}).get("pt", {})
        group_name = desc.get("longDescription") or desc.get("mediumDescription") or f"{brand_label} {range_code}"
        print(f"\n  {group_name} ({range_code})")

        group_entry = {"groupCode": range_code, "groupName": group_name, "variants": []}

        for model_code, model_val in range_val.get("models", {}).items():
            if not model_val.get("dealerOffer", False):
                continue

            tv = _best_transmission_variant(model_val)
            if not tv:
                continue
            baseline = list(tv.get("includedOptions", []))

            phrases = model_val.get("phrases", {}).get("pt", {})
            name = phrases.get("mediumDescription") or model_val.get("derivative") or model_code
            effect_date = model_val.get("effectDate", "2026-09-08")

            print(f"    {name} ({model_code})")

            try:
                options_meta = _fetch_options_meta(model_code, brand, referer, ucp_api_key)
                sgt = _fetch_sales_group_tree(model_code, brand, referer, ucp_api_key)
            except Exception as e:
                print(f"      ERRO ao buscar opções: {e}")
                continue

            if not baseline:
                # Para a janela de encomenda de hoje pode não haver nenhuma
                # variante de transmissão "constructible" com includedOptions
                # (ex. MINI com só a opção manual, não encomendável, listada)
                # — nesse caso aproxima-se o equipamento de série a partir
                # das opções marcadas "std" na informação de opções do
                # modelo, para a configuração continuar a ser válida.
                baseline = [code for code, meta in options_meta.items() if meta.get("std")]

            colors, wheels = _extract_colors_and_wheels(sgt, options_meta)
            if not colors or not wheels:
                print(f"      SEM cores/jantes suficientes (colors={len(colors)}, wheels={len(wheels)}) — a saltar")
                continue

            # Miniaturas de cor/jante (ver _fetch_option_images) — best-effort,
            # não bloqueia a construção do catálogo se falhar.
            image_codes = [c["code"] for c in colors] + [w["code"] for w in wheels]
            option_images = _fetch_option_images(
                connext_ns, brand, model_code, effect_date, image_codes, referer, cosy_api_key
            )
            for c in colors:
                c["swatchUrl"] = option_images.get(c["code"], "")
            for w in wheels:
                w["imageUrl"] = option_images.get(w["code"], "")

            # baseOptions = opções de série sem a pintura/jante actualmente
            # incluída (para depois se acrescentar a cor/jante escolhida).
            color_codes = {c["code"] for c in colors}
            wheel_codes = {w["code"] for w in wheels}
            base_options = [o for o in baseline if o not in color_codes and o not in wheel_codes]

            default_upholstery = _extract_default_upholstery(sgt)
            if default_upholstery and default_upholstery not in base_options:
                base_options.append(default_upholstery)

            baseline_set = set(baseline)
            default_color = next(
                (c["code"] for c in colors if c["code"] in baseline_set),
                next(
                    (c["code"] for c in colors if c["std"]),
                    next(
                        (c["code"] for c in colors if c["group"] == "Sólida"),
                        colors[0]["code"],
                    ),
                ),
            )
            default_wheel = next(
                (w["code"] for w in wheels if w["code"] in baseline_set),
                next((w["code"] for w in wheels if w["std"]), wheels[0]["code"]),
            )

            variant_entry = {
                "modelCode": model_code,
                "variantName": model_val.get("derivative", name),
                "name": f"{group_name} {name}",
                "effectDate": effect_date,
                "baseOptions": base_options,
                "defaultColor": default_color,
                "defaultWheel": default_wheel,
                "colors": colors,
                "wheels": wheels,
            }
            group_entry["variants"].append(variant_entry)

        if group_entry["variants"]:
            catalog["models"].append(group_entry)

    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"\nCatálogo guardado: {data_file}")
    return catalog


def build_catalog(force: bool = False) -> dict:
    """Constrói e guarda o catálogo BMW. Usa cache se existir."""
    return build_catalog_generic(
        "BMW", BRAND, CONNEXT_NS, UCP_API_KEY, COSY_API_KEY, REFERER, DATA_FILE, force
    )


def load_catalog() -> dict:
    """Devolve o catálogo do cache. Constrói se não existir."""
    return build_catalog(force=False)


if __name__ == "__main__":
    catalog = build_catalog(force=True)
    total_models = sum(len(g["variants"]) for g in catalog["models"])
    print(f"\nTotal: {len(catalog['models'])} grupos, {total_models} variantes")
