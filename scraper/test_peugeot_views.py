"""Testa os view codes do visualizador 3D Peugeot e descobre o catálogo completo."""
import json, ssl, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

DATA_DIR = Path(__file__).parent.parent / "data"
SAMPLES_DIR = DATA_DIR / "peugeot_samples"
SAMPLES_DIR.mkdir(exist_ok=True)

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://store.peugeot.pt/",
}


def img_url(version, color, trim, view, width=900, height=500):
    return (
        f"https://visuel3d-secure.peugeot.com/V3DImage.ashx"
        f"?client=SOLVCG&ratio=1&format=jpg&quality=90"
        f"&width={width}&height={height}&back=0"
        f"&view={view}&version={version}&color={color}&trim={trim}&mkt=PT"
    )


def download(url):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=20) as r:
        return r.read()


def main():
    # Dados do primeiro offer do JSON guardado
    with open(DATA_DIR / "peugeot_next_data.json", encoding="utf-8") as f:
        d = json.load(f)
    state = d.get("configurable", {}).get("props", {}).get("initialState", {})
    offers = state.get("OfferList", {}).get("configurable", {}).get("offers", [])
    obj = offers[0].get("_properties", {}).get("object", {})

    version = offers[0]["_id"].split("+")[0]
    color = obj["exteriorColour"]["id"]
    trim = obj["interiorColour"]["id"]
    print(f"version={version}  color={color}  trim={trim}")

    # Testar views 001-006 (exteriores)
    print("\n=== A descarregar views 001-006 ===")
    for v in ["001", "002", "003", "004", "005", "006"]:
        url = img_url(version, color, trim, v)
        try:
            data = download(url)
            path = SAMPLES_DIR / f"view_{v}.jpg"
            path.write_bytes(data)
            print(f"  view {v}: {len(data):,} bytes -> {path.name}")
        except Exception as e:
            print(f"  view {v}: ERRO {e}")

    # --- Catálogo completo via spc-api ---
    print("\n=== A pesquisar catálogo completo via configurador ===")
    api_calls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})

        def on_response(r):
            url = r.url
            ct = r.headers.get("content-type", "")
            if "spc-api" in url and "json" in ct:
                try:
                    body = r.body()
                    api_calls.append({"url": url, "status": r.status, "body": json.loads(body)})
                except Exception:
                    api_calls.append({"url": url, "status": r.status, "body": None})

        ctx.on("response", on_response)
        page = ctx.new_page()

        # Navegar ao configurador para cada modelo
        for offer in offers:
            slug = offer.get("_properties", {}).get("object", {}).get("nameplateBodyStyleSlug", "")
            if not slug:
                continue
            # URL do configurador
            for url_try in [
                f"https://store.peugeot.pt/pt/configurator/{slug}?channel=b2c",
                f"https://store.peugeot.pt/configurator/{slug}?channel=b2c",
            ]:
                try:
                    page.goto(url_try, wait_until="domcontentloaded", timeout=20000)
                    time.sleep(2)
                    final = page.url
                    if "404" not in final:
                        print(f"  OK: {url_try} -> {final}")
                        break
                    else:
                        print(f"  404: {url_try}")
                except Exception as e:
                    print(f"  ERR: {url_try}: {e}")

        browser.close()

    # Guardar chamadas API
    out = DATA_DIR / "peugeot_spc_api.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(api_calls, f, ensure_ascii=False, indent=2)
    print(f"\n{len(api_calls)} chamadas spc-api guardadas: {out}")

    for c in api_calls[:20]:
        body_preview = str(c.get("body", ""))[:200] if c["body"] else "null"
        print(f"  [{c['status']}] {c['url'][:120]}")
        print(f"    {body_preview}")


if __name__ == "__main__":
    main()
