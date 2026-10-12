"""
Extrai o catálogo Renault Portugal: modelos, versões, cores e jantes.

O configurador da Renault (pt.co.rplug.renault.com) é uma SPA em React
cujo HTML vem server-rendered com o estado completo embebido em
`window.APP_STATE = JSON.parse("...")`. Não é preciso browser/Playwright —
um pedido HTTP normal já devolve esse HTML.

Cache em data/renault_catalog.json.
"""
import json
import re
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent / "data" / "renault_catalog.json"
HUB_URL = "https://www.renault.pt/configuradores.html"

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html",
}


def _fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _extract_app_state(html: str) -> dict:
    m = re.search(r'window\.APP_STATE\s*=\s*JSON\.parse\(', html)
    if not m:
        raise ValueError("APP_STATE não encontrado na página")
    start = m.end()
    if html[start] != '"':
        raise ValueError("Formato inesperado de APP_STATE")
    # o literal de string JSON é lido pelo próprio decoder (respeita os
    # escapes) — procurar o primeiro ");" cortava-o quando o texto da
    # página continha ");" (aconteceu com o Mégane)
    inner_json_text, _ = json.JSONDecoder().raw_decode(html, start)
    return json.loads(inner_json_text)


def conf_url(base_configurator_url: str, conf_uri: str) -> str:
    """
    Combina o configurador base de um modelo com uma URI de configuração
    (pt.co.rplug.renault.com/c/...). Pedir a URI da rplug directamente é
    inconsistente (às vezes não devolve o contentZone completo); pedir
    através do wrapper www.renault.pt com `?conf=` é sempre fiável.
    """
    return base_configurator_url + "?conf=" + urllib.parse.quote(conf_uri, safe="")


def _configurator_node(content_zone: dict) -> dict:
    """
    O nó do configurador dentro de contentZone chama-se "configurator" na
    Renault mas "configurator_copy" na Dacia (mesma plataforma "One",
    marcas diferentes) — aceita qualquer um dos dois.
    """
    for key in ("configurator", "configurator_copy"):
        if key in content_zone:
            return content_zone[key]
    raise KeyError("Nó do configurador não encontrado em contentZone")


def get_configurator(url: str) -> dict:
    """Devolve o nó do configurador do APP_STATE para a página indicada."""
    html = _fetch_html(url)
    state = _extract_app_state(html)
    return _configurator_node(state["page"]["data"]["content"]["contentZone"])


def _discover_model_urls(hub_url: str, base_domain: str) -> list[dict]:
    """Lista os configuradores de modelos de passageiros (exclui comerciais/profissionais)."""
    html = _fetch_html(hub_url)
    links = re.findall(r'href="(/[^"]*configurador[^"]*\.html)"', html)

    seen_slugs = {}
    for link in sorted(set(links)):
        if link == "/configuradores.html":
            continue
        slug = link.rstrip("/").split("/")[-2]
        is_pre = "pre-configurador" in link
        if slug in seen_slugs and is_pre:
            continue
        seen_slugs[slug] = link

    results = []
    for slug, link in seen_slugs.items():
        url = base_domain + link
        if "pre-configurador" in url:
            # Alguns modelos só estão ligados via pre-configurador no hub,
            # mas têm sempre um configurador.html completo com o mesmo slug.
            candidate = url.replace("pre-configurador.html", "configurador.html")
            try:
                req = urllib.request.Request(candidate, headers=_HEADERS, method="HEAD")
                with urllib.request.urlopen(req, context=_ssl_ctx, timeout=15) as r:
                    if r.status == 200:
                        url = candidate
            except Exception:
                pass
        results.append({"slug": slug, "url": url})
    return results


def _extract_model_name(html: str, fallback: str, brand: str = "Renault") -> str:
    m = re.search(rf"<title[^>]*>Configurador (.*?) - {brand}", html)
    if m:
        return m.group(1).strip()
    # Alguns modelos (ex: Trafic) usam "Configurador - Renault <Nome>"
    m = re.search(rf"<title[^>]*>Configurador\s*-\s*{brand} (.*?)</title>", html)
    if m:
        return m.group(1).strip()
    return fallback.replace("-", " ").title()


def _picture_map(vcfg: dict, node_code: str) -> dict:
    """
    Mapeia code -> URL de imagem a partir de `staticData.designPictures`
    do configurador. Esse nó tem entradas por categoria (CATCOLORS1,
    CATWHEELS1, CATUPHOLSTERIES1, ...), cada uma com uma lista `pictures`
    de `{"url": ..., "specCode": ...}` — `specCode` corresponde exactamente
    ao `code` das opções em `dynamicData.design` (confirmado por inspecção
    directa da API real: pt.co.rplug.renault.com). Renault, Dacia e Alpine
    (mesma plataforma "One") expõem este nó da mesma forma.
    """
    design_pictures = vcfg.get("staticData", {}).get("designPictures", [])
    node = next((d for d in design_pictures if d.get("code") == node_code), {})
    return {
        p["specCode"]: p["url"]
        for p in node.get("pictures", [])
        if p.get("specCode") and p.get("url")
    }


def _colors_from_design(design_colors: dict, picture_map: dict | None = None) -> list[dict]:
    picture_map = picture_map or {}
    result = []
    for c in design_colors.get("possibles", []):
        entry = {
            "code": c["code"],
            "name": c.get("label", c["code"]),
            "price": c.get("optionPrice", 0) or 0,
            "nextURI": c.get("nextURI", ""),
        }
        swatch_url = picture_map.get(c["code"])
        if swatch_url:
            entry["swatchUrl"] = swatch_url
        result.append(entry)
    return result


def _wheels_from_design(design_wheels: dict, picture_map: dict | None = None) -> list[dict]:
    picture_map = picture_map or {}
    result = []
    for w in design_wheels.get("possibles", []):
        entry = {
            "code": w["code"],
            "name": w.get("label", w["code"]),
            "price": w.get("optionPrice", 0) or 0,
            "nextURI": w.get("nextURI", ""),
        }
        image_url = picture_map.get(w["code"])
        if image_url:
            entry["imageUrl"] = image_url
        result.append(entry)
    return result


def get_wheels_for_color(configurator_url: str, conf_uri: str, color_code: str) -> list[dict]:
    """
    Devolve as jantes REALMENTE válidas para uma cor específica de uma
    versão. A lista "wheels" guardada no catálogo por versão agrega todas
    as jantes alguma vez vistas nessa versão (capturadas a partir de UMA
    única cor de referência ao construir o catálogo) — mas nesta
    plataforma a validade de uma jante depende também da cor escolhida, e
    combinações fora desta lista falham ao gerar a imagem (ver
    renault_images._navigate). Usar isto para popular o selector de
    jantes DEPOIS de a cor estar escolhida, em vez da lista estática do
    catálogo.
    """
    vcfg = get_configurator(conf_url(configurator_url, conf_uri))
    if color_code:
        design = vcfg.get("dynamicData", {}).get("design", [])
        colors_design = next((d for d in design if d.get("code") == "CATCOLORS1"), {})
        color_opt = next((c for c in colors_design.get("possibles", []) if c.get("code") == color_code), None)
        if color_opt and color_opt.get("nextURI"):
            vcfg = get_configurator(conf_url(configurator_url, color_opt["nextURI"]))
    design = vcfg.get("dynamicData", {}).get("design", [])
    wheels_design = next((d for d in design if d.get("code") == "CATWHEELS1"), {})
    return _wheels_from_design(wheels_design, _picture_map(vcfg, "CATWHEELS1"))


def get_upholsteries_for(configurator_url: str, conf_uri: str, color_code: str, wheel_code: str = "") -> list[dict]:
    """
    Estofos válidos para a combinação versão + cor + jante (como as
    jantes, a lista depende das escolhas anteriores — navega-se passo a
    passo pelas "nextURI"). Cada um com nome, preço e miniatura.
    """
    vcfg = get_configurator(conf_url(configurator_url, conf_uri))
    for cat, code in (("CATCOLORS1", color_code), ("CATWHEELS1", wheel_code)):
        if not code:
            continue
        design = vcfg.get("dynamicData", {}).get("design", [])
        node = next((d for d in design if d.get("code") == cat), {})
        opt = next((o for o in node.get("possibles", []) if o.get("code") == code), None)
        if opt and opt.get("nextURI"):
            vcfg = get_configurator(conf_url(configurator_url, opt["nextURI"]))
    design = vcfg.get("dynamicData", {}).get("design", [])
    node = next((d for d in design if d.get("code") == "CATUPHOLSTERIES1"), {})
    pictures = _picture_map(vcfg, "CATUPHOLSTERIES1")
    return [
        {
            "code": u["code"],
            "name": u.get("label", u["code"]),
            "price": u.get("optionPrice", 0) or 0,
            "swatchUrl": pictures.get(u["code"], ""),
        }
        for u in node.get("possibles", [])
    ]


def _disambiguate_model_names(catalog: dict) -> None:
    """
    A Renault usa o mesmo <title> para modelos com nomes iguais mas
    motorizações diferentes (ex: "Kangoo" ICE vs "Kangoo" E-Tech eléctrico).
    Acrescenta um sufixo com base no slug para não ficarem indistinguíveis
    no selector da interface.
    """
    from collections import Counter

    counts = Counter(m["modelName"] for m in catalog["models"])
    for m in catalog["models"]:
        if counts[m["modelName"]] <= 1:
            continue
        slug = m["modelId"]
        if "e-tech" in slug or "eletrico" in slug:
            suffix = "E-Tech Eléctrico"
        elif slug.endswith("-ice") or "-ice-" in slug:
            suffix = "ICE"
        else:
            suffix = slug.replace("-", " ").title()
        m["modelName"] = f"{m['modelName']} ({suffix})"


def build_catalog_generic(
    brand_name: str, hub_url: str, base_domain: str, data_file: Path, force: bool = False,
) -> dict:
    """
    Constrói e guarda o catálogo de uma marca da plataforma "One"
    (Renault/Dacia partilham a mesma pt.co.rplug.renault.com). Usa cache
    se existir. Devolve dict com estrutura:
    {
        "models": [
            {
                "modelId": str (slug),
                "modelName": str,
                "configuratorUrl": str,
                "variants": [
                    {
                        "versionCode": str,
                        "versionName": str,
                        "confURI": str,
                        "startingPrice": number,
                        "colors": [{"code","name","price","nextURI","swatchUrl"?}],
                        "wheels": [{"code","name","price","nextURI","imageUrl"?}],
                    }
                ]
            }
        ]
    }
    """
    if not force and data_file.exists():
        print(f"Catálogo em cache: {data_file}")
        with open(data_file, encoding="utf-8") as f:
            return json.load(f)

    print(f"A construir catálogo {brand_name}...")
    data_file.parent.mkdir(exist_ok=True)

    model_urls = _discover_model_urls(hub_url, base_domain)
    catalog = {"models": []}

    for m in model_urls:
        print(f"\n  {m['slug']} ({m['url']})")
        try:
            html = _fetch_html(m["url"])
            state = _extract_app_state(html)
            cfg = _configurator_node(state["page"]["data"]["content"]["contentZone"])
        except Exception as e:
            print(f"    ERRO ao carregar modelo: {e}")
            continue

        model_name = _extract_model_name(html, m["slug"], brand=brand_name)
        grades = cfg.get("staticData", {}).get("grades", [])
        if not grades:
            print("    sem versões (grades) — a ignorar modelo")
            continue

        # Deduplicar versões por nextURI (grades pode ter entradas repetidas)
        seen_uris = set()
        variants = []
        for g in grades:
            # A Renault/Dacia usam "nextURI" nos grades; a Alpine (mesma
            # plataforma, mesmo formato) usa "uri" em vez disso.
            next_uri = g.get("nextURI") or g.get("uri") or ""
            if not next_uri or next_uri in seen_uris:
                continue
            seen_uris.add(next_uri)

            print(f"    a carregar versão: {g.get('label')} ({next_uri})")
            try:
                vcfg = get_configurator(conf_url(m["url"], next_uri))
            except Exception as e:
                print(f"      ERRO: {e}")
                continue

            details = vcfg.get("dynamicData", {}).get("details", {})
            version_info = details.get("version", {})
            design = vcfg.get("dynamicData", {}).get("design", [])
            colors_design = next((d for d in design if d.get("code") == "CATCOLORS1"), {})
            wheels_design = next((d for d in design if d.get("code") == "CATWHEELS1"), {})

            variants.append({
                "versionCode": version_info.get("code", g.get("code", "")),
                "versionName": version_info.get("label", g.get("label", "")),
                "confURI": next_uri,
                "startingPrice": details.get("price", g.get("startingPrice", 0)),
                "colors": _colors_from_design(colors_design, _picture_map(vcfg, "CATCOLORS1")),
                "wheels": _wheels_from_design(wheels_design, _picture_map(vcfg, "CATWHEELS1")),
            })

        if not variants:
            print("    nenhuma versão válida — a ignorar modelo")
            continue

        catalog["models"].append({
            "modelId": m["slug"],
            "modelName": model_name,
            "configuratorUrl": m["url"],
            "variants": variants,
        })

    _disambiguate_model_names(catalog)

    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"\nCatálogo guardado: {data_file}")
    return catalog


def build_catalog(force: bool = False) -> dict:
    """Constrói e guarda o catálogo Renault. Usa cache se existir."""
    return build_catalog_generic("Renault", HUB_URL, "https://www.renault.pt", DATA_FILE, force)


def load_catalog() -> dict:
    """Devolve o catálogo do cache. Constrói se não existir."""
    return build_catalog(force=False)


if __name__ == "__main__":
    catalog = build_catalog(force=True)
    total_variants = sum(len(m["variants"]) for m in catalog["models"])
    print(f"\nTotal: {len(catalog['models'])} modelos, {total_variants} versões")
