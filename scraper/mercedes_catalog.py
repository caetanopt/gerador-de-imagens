"""
Extrai o catálogo Mercedes-Benz Portugal: modelos, versões (motorizações),
cores e jantes.

Usa a API pública "OneWeb" (api.oneweb.mercedes-benz.com) do configurador
"owcc" — a mesma plataforma "COSY" partilhada com outras marcas do grupo,
mas com um esquema de URLs de imagem diferente do da BMW.

O ponto de entrada por modelo é a resposta "entry", que devolve tudo o
que este catálogo precisa a partir de um único vehicleId inicial:
  - "motorizations.tiles": todas as motorizações/versões do modelo, já
    com vehicleId completo e pronto a usar, nome comercial (ex. "A 180
    d"), combustível e preço.
  - "selectableComponents": todas as opções válidas para essa
    configuração exacta — cores (código "LU-") e jantes (nome contém
    "Jante"), cada uma com preço e se é a escolha actual (a de série).

O vehicleId de base por modelo (para arrancar o processo) não é fácil de
obter via API pura — foi pré-extraído uma vez com Playwright a partir das
páginas de overview de cada modelo (ver scraper/explore_mercedes23.py) e
guardado em data/mercedes_model_vehicleids.json.

Cache em data/mercedes_catalog.json.
"""
import hashlib
import json
import ssl
import urllib.request
from collections import Counter
from pathlib import Path

API_BASE = "https://api.oneweb.mercedes-benz.com"
REFERER = "https://www.mercedes-benz.pt/"
DATA_FILE = Path(__file__).parent.parent / "data" / "mercedes_catalog.json"
VEHICLE_IDS_FILE = Path(__file__).parent.parent / "data" / "mercedes_model_vehicleids.json"

_ssl_ctx = ssl.create_default_context()

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": REFERER,
}

# nomes amigáveis para os ângulos-padrão (confirmados visualmente);
# os restantes ângulos de cada bloco (a API devolve a lista completa de
# perspectivas válidas por veículo em stageV2.metaData.views) ficam
# etiquetados pelo próprio código de perspectiva.
_EXTERIOR_LABELS = {
    "BE340": "3_4_frente",
    "BE000": "frente",
    "BE270": "lado",
    "BE180": "traseira",
}


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        return json.loads(r.read())


def fetch_entry(type_class: str, vehicle_id: str) -> dict | None:
    """Pede a configuração completa (versões, cores, jantes, imagem) para um vehicleId."""
    url = f"{API_BASE}/owcc-backend/api/v3/pt_PT/CCci/x/entry?typeClass={type_class}&vehicleId={vehicle_id}"
    try:
        return _get(url)
    except Exception as e:
        print(f"      ERRO entry: {e}")
        return None


def fetch_components_info(model_id: str) -> dict:
    """
    Pede as miniaturas (previewImage/mediaItems) de cada opção seleccionável
    (cores "LU-" e jantes) para um vehicleId — usa o mesmo id numérico que
    aparece a meio do vehicleId (ex. "1770101" em "pt_PT__1770101__...").
    Confirmado via tráfego real do configurador em mercedes-benz.pt: o
    endpoint devolve {"componentsInfo": {codigo: {..., "previewImage": url,
    "mediaItems": [{"url": ..., "type": "THUMBNAIL_IMAGE"}]}}}. Nem todos os
    códigos têm imagem (embalagens/códigos técnicos não têm), mas cores e
    jantes têm sempre nos modelos testados.
    """
    url = f"{API_BASE}/owcc-backend/api/v3/pt_PT/CCci/x/models/{model_id}/componentsInfo"
    try:
        data = _get(url)
        return data.get("componentsInfo", {})
    except Exception as e:
        print(f"      ERRO componentsInfo: {e}")
        return {}


def replace_in_group(vehicle_id: str, group_prefix: str, old_code: str, new_code: str) -> str:
    """
    Substitui um código dentro de um grupo do vehicleId (ex. trocar a
    jante "25R" por "RQS" dentro do grupo "SA-00U-01U-...-25R-...", ou a
    cor "696" por "922" dentro de "LU-696"). Os grupos são separados por
    "_" e os códigos dentro de cada grupo por "-".
    """
    groups = vehicle_id.split("_")
    for i, g in enumerate(groups):
        if g.startswith(group_prefix + "-"):
            tokens = g.split("-")
            if old_code in tokens:
                tokens[tokens.index(old_code)] = new_code
                groups[i] = "-".join(tokens)
            break
    return "_".join(groups)


def stage_images_from_entry(entry_data: dict) -> dict[str, str] | None:
    """
    Extrai TODOS os URLs de imagem válidos da resposta 'entry': todas as
    perspectivas exteriores (normalmente 36, passo de 10°) + interior
    estático (normalmente 4) + interior 360° (normalmente 6) — a própria
    API declara a lista exacta de perspectivas válidas por veículo em
    stageV2.metaData.views, não é preciso adivinhar códigos.
    """
    stage = entry_data.get("vehicle", {}).get("stageV2")
    if not stage:
        return None
    cosy_id = stage.get("cosyId")
    base_url = stage.get("metaData", {}).get("baseInfo", {}).get("baseUrl")
    views = stage.get("metaData", {}).get("views", {})
    ext = views.get("EXTERIOR_360")
    if not cosy_id or not base_url or not ext:
        return None
    ext_params = {p["key"]: p["value"] for p in ext.get("additionalParameters", [])}
    if "cp" not in ext_params:
        return None

    images = {}
    for persp in ext.get("perspectives", []):
        label = _EXTERIOR_LABELS.get(persp, f"exterior_{persp}")
        images[label] = (
            f"{base_url}?q={cosy_id}&IMGT=W27&POV={persp}"
            f"&BKGND={ext_params.get('BKGND', '9')}&uni={ext_params.get('uni', 'm')}"
            f"&cp={ext_params['cp']}&imwidth=1920"
        )

    interior = views.get("INTERIOR")
    if interior:
        int_params = {p["key"]: p["value"] for p in interior.get("additionalParameters", [])}
        if "cp" in int_params:
            for persp in interior.get("perspectives", []):
                images[f"interior_{persp}"] = (
                    f"{base_url}?q={cosy_id}&IMGT=W27&POV={persp}"
                    f"&BKGND={int_params.get('BKGND', '8')}&cp={int_params['cp']}&imwidth=1920"
                )

    interior360 = views.get("INTERIOR_360")
    if interior360:
        int360_params = {p["key"]: p["value"] for p in interior360.get("additionalParameters", [])}
        if "cp" in int360_params:
            for persp in interior360.get("perspectives", []):
                images[f"interior360_{persp}"] = (
                    f"{base_url}?q={cosy_id}&IMGT=W27&POV={persp}"
                    f"&BKGND={int360_params.get('BKGND', '8')}&cp={int360_params['cp']}&imwidth=1920"
                )
    return images


def _extract_versions(entry_data: dict) -> list[dict]:
    tiles = entry_data.get("motorizations", {}).get("tiles", [])
    versions = []
    for t in tiles:
        cv = {c["id"]: c["value"] for c in t.get("comparableValues", [])}
        try:
            price = float(cv.get("price", 0))
        except (TypeError, ValueError):
            price = 0.0
        versions.append({
            "modelCode": t["modelId"],
            "name": t.get("name", t["modelId"]),
            "fuel": cv.get("technicalInformation.engine.motorizationFilter", ""),
            "price": price,
            "vehicleId": t["vehicleId"],
        })

    # Duas versões podem ter o mesmo nome comercial mas motorizações
    # diferentes (ex. a mesma denominação reaproveitada para petróleo e
    # híbrido nalguns mercados) — nesse caso o combustível é acrescentado
    # ao nome para as distinguir.
    name_counts = Counter(v["name"] for v in versions)
    for v in versions:
        if name_counts[v["name"]] > 1 and v["fuel"]:
            v["displayName"] = f"{v['name']} ({v['fuel']})"
        else:
            v["displayName"] = v["name"]
    return versions


def _preview_image(components_info: dict, code: str) -> str | None:
    """Miniatura de uma opção (cor ou jante), a partir de /componentsInfo."""
    info = components_info.get(code)
    if not info:
        return None
    return info.get("previewImage")


def _extract_colors_and_wheels(
    entry_data: dict, components_info: dict | None = None,
) -> tuple[list[dict], str | None, list[dict], str | None]:
    sc = entry_data.get("selectableComponents", {})
    components_info = components_info or {}

    colors = []
    default_color_code = None
    for code, info in sc.items():
        if not code.startswith("LU-"):
            continue
        c = code.split("-", 1)[1]
        color = {
            "code": c,
            "name": info.get("name", code),
            "price": info.get("price", {}).get("price", 0),
        }
        swatch_url = _preview_image(components_info, code)
        if swatch_url:
            color["swatchUrl"] = swatch_url
        colors.append(color)
        if info.get("selected"):
            default_color_code = c

    wheels = []
    default_wheel_code = None
    for code, info in sc.items():
        if "jante" not in info.get("name", "").lower():
            continue
        c = code.split("-", 1)[1]
        wheel = {
            "code": c,
            "name": info.get("name", code),
            "price": info.get("price", {}).get("price", 0),
        }
        image_url = _preview_image(components_info, code)
        if image_url:
            wheel["imageUrl"] = image_url
        wheels.append(wheel)
        if info.get("selected"):
            default_wheel_code = c

    return colors, default_color_code, wheels, default_wheel_code


def _validate_options(
    type_class: str, vehicle_id: str, group_prefix: str, default_code: str,
    options: list[dict], seen_hashes: dict[str, str],
) -> list[dict]:
    """
    Testa cada opção (cor ou jante) trocando-a no vehicleId e verificando
    se a imagem resultante é distinta — a API por vezes não consegue
    aplicar uma opção incompatível com o resto do equipamento fixo e
    devolve silenciosamente a imagem doutra configuração, em vez de erro.
    `seen_hashes` acumula {hash: nome} ao longo de toda a validação desta
    versão (cores e jantes em conjunto), para apanhar colisões cruzadas.
    """
    valid = []
    for opt in options:
        if opt["code"] == default_code:
            vid = vehicle_id
        else:
            vid = replace_in_group(vehicle_id, group_prefix, default_code, opt["code"])
        entry = fetch_entry(type_class, vid)
        if not entry:
            continue
        images = stage_images_from_entry(entry)
        if not images or len(images) < 4:
            continue
        h = hashlib.md5(images["3_4_frente"].encode()).hexdigest()
        if h in seen_hashes:
            if opt["code"] == default_code:
                # a de série é sempre de confiar — foi ela quem "roubou"
                # a colisão a uma opção incompatível, não o contrário.
                valid.append({**opt, "serie": True})
            continue
        seen_hashes[h] = opt["name"]
        valid.append({**opt, "serie": opt["code"] == default_code})
    return valid


def build_catalog(force: bool = False) -> dict:
    """Constrói e guarda o catálogo Mercedes-Benz. Usa cache se existir."""
    if not force and DATA_FILE.exists():
        print(f"Catálogo em cache: {DATA_FILE}")
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)

    if not VEHICLE_IDS_FILE.exists():
        raise FileNotFoundError(
            f"{VEHICLE_IDS_FILE} não existe — corre primeiro "
            "scraper/explore_mercedes23.py para descobrir os vehicleId de base."
        )

    print("A construir catálogo Mercedes-Benz (modelos, versões, cores e jantes)...")
    DATA_FILE.parent.mkdir(exist_ok=True)

    model_vehicle_ids = json.loads(VEHICLE_IDS_FILE.read_text(encoding="utf-8"))
    catalog = {"models": []}

    for overview_url, info in model_vehicle_ids.items():
        type_class = info["typeClass"]
        base_vehicle_id = info["vehicleId"]

        base_entry = fetch_entry(type_class, base_vehicle_id)
        if not base_entry:
            print(f"  SEM entry inicial: {overview_url}")
            continue

        vehicle = base_entry.get("vehicle", {})
        vclass = vehicle.get("vehicleClass", "")
        vbody = vehicle.get("vehicleBody", "")
        group_name_suffix = f"{vclass} {vbody}".strip()
        if not group_name_suffix:
            slug = overview_url.rstrip("/").split("/")
            group_name_suffix = (slug[-2] if slug[-1].startswith("overview") else slug[-1].replace(".html", "")).replace("-", " ").title()
        group_code = vehicle.get("vehicleClassId", "") + "-" + vehicle.get("vehicleBodyId", "") or group_name_suffix
        print(f"\n  {group_name_suffix} ({type_class})")

        versions = _extract_versions(base_entry)
        if not versions:
            print("    SEM versões — a saltar")
            continue

        variants_out = []
        for v in versions:
            print(f"    {v['displayName']} ({v['modelCode']}, {v['fuel']})")
            v_entry = base_entry if v["vehicleId"] == base_vehicle_id else fetch_entry(type_class, v["vehicleId"])
            if not v_entry:
                print("      ERRO ao obter opções — a saltar versão")
                continue

            model_id = v["vehicleId"].split("__")[1]
            components_info = fetch_components_info(model_id)
            colors, default_color, wheels, default_wheel = _extract_colors_and_wheels(v_entry, components_info)
            if not colors:
                print("      SEM cores — a saltar versão")
                continue
            if not default_color:
                default_color = colors[0]["code"]
            if wheels and not default_wheel:
                default_wheel = wheels[0]["code"]

            seen_hashes: dict[str, str] = {}
            colors_ok = _validate_options(type_class, v["vehicleId"], "LU", default_color, colors, seen_hashes)
            wheels_ok = (
                _validate_options(type_class, v["vehicleId"], "SA", default_wheel, wheels, seen_hashes)
                if wheels else []
            )

            if not colors_ok:
                print("      SEM cores válidas (todas em colisão) — a saltar versão")
                continue

            print(f"      {len(colors_ok)}/{len(colors)} cores válidas, {len(wheels_ok)}/{len(wheels)} jantes válidas")

            variants_out.append({
                "modelCode": v["modelCode"],
                "variantName": v["displayName"],
                "name": f"{group_name_suffix} {v['displayName']}",
                "typeClass": type_class,
                "vehicleId": v["vehicleId"],
                "defaultColorCode": default_color,
                "defaultWheelCode": default_wheel,
                "price": v["price"],
                "colors": colors_ok,
                "wheels": wheels_ok,
            })

        if not variants_out:
            continue

        catalog["models"].append({
            "groupCode": group_code,
            "groupName": f"Mercedes-Benz {group_name_suffix}",
            "variants": variants_out,
        })

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"\nCatálogo guardado: {DATA_FILE}")
    return catalog


def load_catalog() -> dict:
    """Devolve o catálogo do cache. Constrói se não existir."""
    return build_catalog(force=False)


if __name__ == "__main__":
    catalog = build_catalog(force=True)
    total_variants = sum(len(g["variants"]) for g in catalog["models"])
    total_colors = sum(len(v["colors"]) for g in catalog["models"] for v in g["variants"])
    total_wheels = sum(len(v["wheels"]) for g in catalog["models"] for v in g["variants"])
    print(
        f"\nTotal: {len(catalog['models'])} modelos, {total_variants} versões, "
        f"{total_colors} combinações de cor, {total_wheels} combinações de jante"
    )
