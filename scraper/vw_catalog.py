"""
Extrai o catálogo Volkswagen Portugal: modelos, cores e jantes.
Usa a API pública do configurador volkswagen.pt — a mesma plataforma
partilhada por todo o grupo VW (Audi, SEAT, Škoda, ...), só muda o
domínio, o locale no caminho e a letra da marca (brand=V para a VW).
A lógica genérica está em build_catalog_generic, reaproveitada por
audi_catalog.py.
Cache em data/vw_catalog.json.
"""
import json
import ssl
import urllib.request
from pathlib import Path

BASE = "https://configurador.volkswagen.pt/cc-pt/be/pt_PT_VW22"
CDN = "https://cdn.nwi-ms.com/media/pt/V/mc"
BRAND_CODE = "V"
DATA_FILE = Path(__file__).parent.parent / "data" / "vw_catalog.json"

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://configurador.volkswagen.pt/",
}


def _get(url: str, referer: str) -> dict | list:
    headers = dict(_HEADERS, Referer=referer)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=20) as r:
        return json.loads(r.read())


def _get_model_detail(base: str, brand_code: str, referer: str, model_code: str, color: str, upholstery: str) -> dict:
    url = f"{base}/api/v2/modeldetailFull/{brand_code}/{model_code}/{color}/{upholstery}/@/@"
    return _get(url, referer)


def _build_image_url(cdn: str, model_code: str, view: str, color: str, upholstery: str, wheel: str = "") -> str:
    return (
        f"{cdn}/{model_code}/model/{view}.webp"
        f"?F={color}&P={upholstery}&M={wheel}&size=XL"
    )


def _image_exists(url: str, referer: str) -> bool:
    try:
        req = urllib.request.Request(url, headers=dict(_HEADERS, Referer=referer, Accept="image/*"))
        with urllib.request.urlopen(req, context=_ssl_ctx, timeout=30) as r:
            return r.status == 200
    except Exception:
        return False


def name_from_pack(it: dict, equipment: str, available_equipments: list | None) -> dict:
    """
    Na Audi, os estofos opcionais vêm só com a cor ("Preto", "Preto",
    "Preto"...) — o que os distingue é o pacote de interior obrigatório
    (categoria "Estofos", ex.: "Pacote Int. S line couro, preto"), que
    também traz o preço. Estofos com nome de tecido ficam como estão.
    """
    codes = set(filter(None, equipment.split(",")))
    packs = [
        e for e in available_equipments or []
        if isinstance(e, dict) and e.get("code") in codes and "ET0" in (e.get("akatCodes") or []) and e.get("title")
    ]
    if not packs or " — " in it["name"]:
        return it
    title = packs[0]["title"].strip()
    name = title if it["name"].lower() in title.lower() else f"{title} — {it['name']}"
    price = it.get("price") or (packs[0].get("preis") or {}).get("brutto", 0) or 0
    return {**it, "name": name, "price": price}


def with_pack_swatch(it: dict) -> dict:
    """Sem o pack no M= a miniatura do estofo vem em branco."""
    url = it.get("swatchUrl") or ""
    if it.get("equipment") and url and "M=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}M={it['equipment'].replace(',', '@')}"
    return {**it, "swatchUrl": url}


_INTERIOR_PARTS =(("himl", "forro do tejadilho"), ("arma", "tablier"), ("tepp", "alcatifa"))


def disambiguate_interiors(interiors: list[dict], raw_interiors: list | None, equipments: list | None = None) -> None:
    """
    Estofos da mesma versão com o mesmo nome (ex.: dois "Preto") diferem
    no forro do tejadilho, no tablier ou na alcatifa, ou no pacote
    obrigatório — acrescenta-se ao nome o que for diferente; em último
    caso, o código do estofo.
    """
    raw = {r["code"]: r for r in raw_interiors or [] if isinstance(r, dict) and r.get("code")}
    titles = {e["code"]: e["title"].strip() for e in equipments or [] if isinstance(e, dict) and e.get("code") and e.get("title")}
    groups: dict[str, list[dict]] = {}
    for it in interiors:
        groups.setdefault(it["name"], []).append(it)
    for name, same in groups.items():
        if len(same) < 2:
            continue
        diff = [
            (field, label) for field, label in _INTERIOR_PARTS
            if len({(raw.get(it["code"]) or {}).get(field) for it in same}) > 1
        ]
        eq_sets = [set(filter(None, (it.get("equipment") or "").split(","))) for it in same]
        common = set.intersection(*eq_sets)
        for it, eqs in zip(same, eq_sets):
            r = raw.get(it["code"]) or {}
            extra = ", ".join(f"{label} {r[field]}" for field, label in diff if r.get(field))
            if not extra:
                extra = ", ".join(titles[c] for c in sorted(eqs - common) if c in titles)
            it["name"] = f"{name} ({extra})" if extra else f"{name} ({it['code']})"
        names = [it["name"] for it in same]
        for it in same:
            if names.count(it["name"]) > 1:
                it["name"] = f"{it['name'][:-1]}, {it['code']})" if it["name"].endswith(")") else f"{it['name']} ({it['code']})"


def _renderable_interiors(
    base: str, brand_code: str, referer: str, mc: str, color: str, default_upholstery: str,
    interiors: list[dict], colors: list[dict] | None = None, seat_map: dict | None = None,
) -> list[dict]:
    """
    Estofos que não o de série muitas vezes exigem equipamento associado
    (ex.: pack de interior) — a CDN de imagens só renderiza a configuração
    completa, com esse equipamento no parâmetro M= (ex.: M=PWN; com jante
    não-série, M=PWN,40Z), senão dá 404. E muitos só são compatíveis com
    algumas cores exteriores (na Audi, a maioria): validar só com a cor de
    série deitava fora ~2/3 dos estofos reais.

    Para cada estofo: pede-se o detalhe da configuração (dá o equipamento
    seleccionado e o URL-modelo das imagens) e depois testa-se na CDN a
    imagem "front" com CADA cor exterior da versão. Fica com a lista de
    cores compatíveis ("colors"); a app só mostra os estofos compatíveis
    com a cor escolhida. Estofos sem nenhuma cor compatível saem.

    Na Audi muitos estofos só renderizam com o pack de bancos a que estão
    associados (detalhe "seatToInteriorMapping", ex.: AO -> PWA/PWE) — sem
    esse código no M= a CDN dá 404. Se o equipamento devolvido pela API
    não chegar, tenta-se cada pack de bancos do estofo.
    """
    seats_for: dict[str, list[str]] = {}
    for seat, codes in (seat_map or {}).items():
        if seat and seat not in ("---", "@"):
            for code in codes:
                seats_for.setdefault(code, []).append(seat)
    import re
    from concurrent.futures import ThreadPoolExecutor

    color_codes = [c["code"] for c in (colors or [])] or [color]

    def check(it: dict) -> dict | None:
        try:
            d = _get_model_detail(base, brand_code, referer, mc, color, it["code"])
        except Exception:
            return None
        tpl = d.get("imageUrlWithPlaceholders") or ""
        if not tpl:
            return None
        eq = "" if it["code"] == default_upholstery else ",".join(
            (e.get("code") if isinstance(e, dict) else str(e)) for e in d.get("selectedEquipments") or []
        )
        # As miniaturas do estofo por pack de bancos ("imageUrlsForSeats")
        # trazem o M= completo que a CDN exige (ex.: M=5TG@PWA@QQ2)
        sel = d.get("selectedInterior") or {}
        seat_urls = sel.get("imageUrlsForSeats") if sel.get("code") == it["code"] else {}
        from_seats = [
            m.group(1).replace("@", ",")
            for m in (re.search(r"[?&]M=([^&]+)", u) for u in (seat_urls or {}).values())
            if m
        ]
        candidates = [eq] + from_seats + [",".join(x for x in (eq, seat) if x) for seat in seats_for.get(it["code"], [])]
        for cand in dict.fromkeys(candidates):
            url_tpl = re.sub(r"P=[^&]*", f"P={it['code']}", re.sub(r"M=[^&]*", f"M={cand}", tpl))
            url_tpl = url_tpl.replace("{view}", "front").replace("{size}", "L")

            def ok(cc: str, url_tpl=url_tpl) -> bool:
                return _image_exists(re.sub(r"F=[^&]*", f"F={cc}", url_tpl), referer)

            with ThreadPoolExecutor(max_workers=6) as ex:
                flags = list(ex.map(ok, color_codes))
            compatible = [cc for cc, f in zip(color_codes, flags) if f]
            if compatible:
                out = {**name_from_pack(it, cand, d.get("availableEquipments")), "equipment": cand, "colors": compatible}
                return with_pack_swatch(out)
        return None

    with ThreadPoolExecutor(max_workers=4) as ex:
        checked = list(ex.map(check, interiors))
    return [it for it in checked if it]


def disambiguate_groups(catalog: dict) -> None:
    """
    A Audi tem por vezes duas gerações do mesmo modelo à venda em
    simultâneo, com o mesmo nome (ex.: "Audi A3 Sportback" B30 e C30) — no
    selector só se via uma. Acrescenta o ano-modelo (ou o código do grupo,
    se o ano também coincidir) aos grupos com nome repetido.
    """
    from collections import Counter

    counts = Counter(g["groupName"] for g in catalog["models"])
    for g in catalog["models"]:
        if counts[g["groupName"]] <= 1:
            continue
        years = sorted({v.get("modelYear") for v in g["variants"] if v.get("modelYear")})
        g["groupName"] = f"{g['groupName']} (ano-modelo {years[-1]})" if years else f"{g['groupName']} ({g['groupCode']})"
    counts = Counter(g["groupName"] for g in catalog["models"])
    for g in catalog["models"]:
        if counts[g["groupName"]] > 1:
            g["groupName"] = f"{g['groupName']} [{g['groupCode']}]"


def build_catalog_generic(
    brand_name: str, base: str, brand_code: str, referer: str, data_file: Path, force: bool = False,
) -> dict:
    """
    Constrói e guarda o catálogo de uma marca da plataforma "Car
    Configurator" do grupo VW. Usa cache se existir. Devolve dict com
    estrutura:
    {
        "models": [
            {
                "groupCode": str,
                "groupName": str,
                "variants": [
                    {
                        "modelCode": str,
                        "variantName": str,
                        "name": str,
                        "defaultColor": str,
                        "defaultUpholstery": str,
                        "colors": [{"code", "name", "price", "swatchUrl"}],
                        "wheels": [{"code", "title", "serie", "imageUrl"}],
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

    model_groups_data = _get(f"{base}/api/v2/modelgroup?brand={brand_code}", referer)
    catalog = {"models": []}

    for mg in model_groups_data.get("modelgroups", []):
        group_code = mg["code"]
        group_name = mg["name"]
        print(f"\n  {group_name} ({group_code})")

        group_entry = {
            "groupCode": group_code,
            "groupName": group_name,
            "pictureUrl": mg.get("pictureURL", ""),
            "variants": [],
        }

        for variant in mg.get("variants", []):
            # Cada "variant" é um nível de acabamento (ex.: "Selection"), mas
            # pode ter VÁRIAS motorizações distintas em "models" (ex.: Fabia
            # Selection tem 4: 1.0 MPI 80cv, 1.0 TSI 95cv/116cv, 116cv DSG) —
            # cada uma com o seu próprio modelCode, preço e ficha técnica.
            # Ignorar isto e usar só "cheapestModelCode" (como fazia esta
            # função antes) descarta ~60% das motorizações reais (confirmado
            # na Škoda: 94 motorizações reais vs. 40 só com a mais barata).
            models = variant.get("models") or []
            if not models:
                mc = variant.get("cheapestModelCode")
                if mc:
                    models = [{"number": mc, "designation": variant["name"], "preSelection": variant.get("preSelection", {})}]

            for m in models:
                mc = m.get("number")
                if not mc:
                    continue

                ps = m.get("preSelection") or variant.get("preSelection", {})
                default_color = ps.get("standardColorCode", "")
                default_upholstery = ps.get("standardUpholsteryCode", "")
                designation = m.get("designation", variant["name"])

                print(f"    {designation} ({mc}) cor={default_color}")

                try:
                    detail = _get_model_detail(base, brand_code, referer, mc, default_color, default_upholstery)
                except Exception as e:
                    print(f"    ERRO ao buscar detalhe: {e}")
                    continue

                colors = [
                    {
                        "code": ext["code"],
                        "name": ext.get("bezf", ext["code"]),
                        "price": ext.get("preis", {}).get("brutto", 0) or 0,
                        "available": not ext.get("notAvailable", False),
                        "swatchUrl": ext.get("image", ""),
                    }
                    for ext in detail.get("availableExteriors", [])
                    if not ext.get("notAvailable", False)
                ]

                wheels = [
                    {
                        "code": w["code"],
                        "title": w.get("title", w["code"]),
                        "serie": w.get("serie", False),
                        "imageUrl": w.get("image", ""),
                    }
                    for w in detail.get("availableWheels", [])
                ]

                # estofos/cores de interior desta motorização — o código
                # entra no parâmetro P= das imagens (as vistas de interior
                # mudam com ele); a 1.ª entrada é a de série.
                interiors = [
                    {
                        "code": it["code"],
                        "name": " — ".join(x for x in (it.get("stof"), it.get("infa")) if x) or it["code"],
                        "swatchUrl": it.get("image", ""),
                    }
                    for it in detail.get("availableInteriors", [])
                    if not it.get("notAvailable", False)
                ]
                interiors.sort(key=lambda it: it["code"] != default_upholstery)
                interiors = _renderable_interiors(
                    base, brand_code, referer, mc, default_color, default_upholstery, interiors, colors,
                    detail.get("seatToInteriorMapping"),
                )
                disambiguate_interiors(interiors, detail.get("availableInteriors"), detail.get("availableEquipments"))

                variant_entry = {
                    "modelCode": mc,
                    "variantName": designation,
                    "name": detail.get("name", f"{group_name} {designation}"),
                    "price": (m.get("listPrice") or {}).get("gross", 0) or 0,
                    "defaultColor": default_color,
                    "defaultUpholstery": default_upholstery,
                    "colors": colors,
                    "wheels": wheels,
                    "interiors": interiors,
                    "modelYear": detail.get("modelYear"),
                }
                group_entry["variants"].append(variant_entry)

        catalog["models"].append(group_entry)

    disambiguate_groups(catalog)
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"\nCatálogo guardado: {data_file}")
    return catalog


def build_catalog(force: bool = False) -> dict:
    """Constrói e guarda o catálogo VW. Usa cache se existir."""
    return build_catalog_generic("VW", BASE, BRAND_CODE, "https://configurador.volkswagen.pt/", DATA_FILE, force)


def load_catalog() -> dict:
    """Devolve o catálogo do cache. Constrói se não existir."""
    return build_catalog(force=False)


def get_image_urls(model_code: str, color: str, upholstery: str, wheel: str = "") -> dict[str, str]:
    """
    Devolve dict com as 4 URLs de imagem para a configuração escolhida.
    views: exteriorfront, front, side, back
    """
    views = {
        "3/4 Frente": "exteriorfront",
        "Frente": "front",
        "Lado": "side",
        "Traseira": "back",
    }
    return {
        label: _build_image_url(CDN, model_code, view, color, upholstery, wheel)
        for label, view in views.items()
    }


if __name__ == "__main__":
    catalog = build_catalog(force=True)
    total_models = sum(len(g["variants"]) for g in catalog["models"])
    print(f"\nTotal: {len(catalog['models'])} grupos, {total_models} variantes")
