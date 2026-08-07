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

                variant_entry = {
                    "modelCode": mc,
                    "variantName": designation,
                    "name": detail.get("name", f"{group_name} {designation}"),
                    "price": (m.get("listPrice") or {}).get("gross", 0) or 0,
                    "defaultColor": default_color,
                    "defaultUpholstery": default_upholstery,
                    "colors": colors,
                    "wheels": wheels,
                }
                group_entry["variants"].append(variant_entry)

        catalog["models"].append(group_entry)

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
