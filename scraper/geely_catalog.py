"""
Extrai o catálogo Geely Portugal (geely-auto.pt): modelos, versões e cores.

A Geely usa um site SPA (sem conteúdo em SSR — o HTML estático não tem
nada útil, é preciso Playwright) com um configurador simples: versões
(trims) com preço próprio, e um "Vista 360°" por cor que é uma sequência
de 24 fotogramas estáticos em `/assets/360/{asset_slug}-{color_slug}/{n}.webp`
(sem depender de versão/jantes — o spinner é só por cor, à semelhança do
Nissan Micra). Mapeei os ângulos por número de fotograma, confirmado
visualmente: frente=1, 3/4 frente=4, lado=7, traseira=13 (24 fotogramas,
15° cada). A imagem de interior é uma foto estática única por modelo em
`/assets/interior/{nome-arbitrario}.webp` (não varia por cor nem versão).

Cache em data/geely_catalog.json.
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

DATA_FILE = Path(__file__).parent.parent / "data" / "geely_catalog.json"
BASE_URL = "https://www.geely-auto.pt"

# não há forma automática de derivar o "asset slug" (pasta de imagens 360)
# a partir do slug do modelo na URL — foi confirmado manualmente por marca.
MODELS = [
    {"modelSlug": "geely-e5", "modelName": "Geely E5", "assetSlug": "e5"},
    {"modelSlug": "geely-starray-em-i", "modelName": "Geely Starray EM-i", "assetSlug": "starray"},
]


def _extract_model(page, model: dict) -> dict:
    page.goto(f"{BASE_URL}/modelos/{model['modelSlug']}", timeout=45000)
    page.wait_for_load_state("networkidle", timeout=20000)
    try:
        page.click("text=Aceitar", timeout=4000)
    except Exception:
        pass
    page.evaluate("document.querySelector('a[href*=configurador]').click()")
    page.wait_for_timeout(2000)

    versions_out = []
    version_btns = page.locator("button:has-text('kWh')")
    for i in range(version_btns.count()):
        version_btns.nth(i).click(timeout=5000)
        page.wait_for_timeout(1000)
        name, spec = version_btns.nth(i).inner_text().split("\n", 1)
        price_matches = page.evaluate("document.body.innerText.match(/[\\d\\s]+€/g)") or []
        price = 0.0
        if price_matches:
            price = float(price_matches[0].replace("\xa0", "").replace(" ", "").replace("€", ""))
        versions_out.append({"name": name.strip(), "spec": spec.strip(), "price": price})

    colors_out = []
    seen_slugs = set()
    swatches = page.locator(".color-swatch")
    for i in range(swatches.count()):
        swatch = swatches.nth(i)
        title = swatch.get_attribute("title") or ""
        swatch.click(timeout=5000)
        page.wait_for_timeout(500)
        slug = page.evaluate("document.querySelector('.viewer360') ? document.querySelector('.viewer360').getAttribute('data-cor') : null")
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        price = 0.0
        if "(+" in title:
            price_str = title.split("(+")[1].split("€")[0].strip()
            price = float(price_str)
        name = title.split(" (")[0]
        colors_out.append({"slug": slug, "name": name, "price": price})

    interior_imgs = page.evaluate(
        "() => Array.from(document.querySelectorAll('img')).map(i => i.src).filter(s => s.includes('/interior/'))"
    )

    return {
        "modelSlug": model["modelSlug"],
        "modelName": model["modelName"],
        "assetSlug": model["assetSlug"],
        "versions": versions_out,
        "colors": colors_out,
        "interiorImage": interior_imgs[0] if interior_imgs else None,
    }


def build_catalog(force: bool = False) -> dict:
    if DATA_FILE.exists() and not force:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))

    catalog = {"models": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1400})
        for model in MODELS:
            print(f"A processar {model['modelName']}...")
            entry = _extract_model(page, model)
            catalog["models"].append(entry)
            print(f"  {len(entry['versions'])} versões, {len(entry['colors'])} cores, interior={'sim' if entry['interiorImage'] else 'não'}")
        browser.close()

    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    return catalog


def load_catalog() -> dict:
    return build_catalog(force=False)


if __name__ == "__main__":
    cat = build_catalog(force=True)
    print("\nTotal modelos:", len(cat["models"]))
