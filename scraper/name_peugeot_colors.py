"""
Valida cores Peugeot e obtém nomes.
Testa V3DImage: se tamanho > 20KB = cor válida para esse modelo.
"""
import ssl, urllib.request, json, concurrent.futures
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# SSL context igual ao peugeot_images.py
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/webp,image/*,*/*",
    "Referer": "https://store.peugeot.pt/",
}

with open(DATA_DIR / "peugeot_colors.json", encoding="utf-8") as f:
    colors = json.load(f)

# Versões representativas por modelo para testar
MODEL_VERSIONS = {
    "208":  ("1PP2A5HJLKB02PH2", "0PG90RFX"),
    "2008": ("1PP1SYHJLKB02PH2", "0PG90RFX"),
    "408":  ("1PP6CBPJHWB0A0G0", "0PZ70RFX"),
    "3008": ("1PPDSYRJH7L0A0D2", "0PW60RFX"),
}

CDN = "https://visuel3d-secure.peugeot.com/V3DImage.ashx"


def fetch_image_size(color_id, version, trim_id):
    url = (
        f"{CDN}?client=SOLVCG&ratio=1&format=jpg&quality=90"
        f"&width=400&height=220&back=0&view=006"
        f"&version={version}&color={color_id}&trim={trim_id}&mkt=PT"
    )
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, context=_ssl_ctx, timeout=15) as r:
            data = r.read()
            return len(data)
    except Exception as e:
        return 0


def test_color_on_208(color_id):
    version, trim = MODEL_VERSIONS["208"]
    size = fetch_image_size(color_id, version, trim)
    return color_id, size


print("=== Validando cores com V3DImage (modelo 208) ===")
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    futures = {ex.submit(test_color_on_208, cid): cid for cid in colors}
    results = {}
    for f in concurrent.futures.as_completed(futures):
        cid = futures[f]
        cid2, size = f.result()
        results[cid] = size

# Tamanho de referência de uma cor conhecida
ref_size = results.get("0MM00NEQ", 0)
print(f"Referencia (Amarelo Agueda): {ref_size:,}B")
print()

valid_colors = {}
invalid_colors = {}
for cid, size in sorted(results.items()):
    name = colors.get(cid, cid)
    # Cor válida se tamanho for parecido com a referência (>= 60% do tamanho ref)
    # Ou pelo menos > 20KB
    is_valid = size > 20000
    if is_valid:
        valid_colors[cid] = name
        print(f"  OK  {cid}: {name:25} {size:,}B")
    else:
        invalid_colors[cid] = name
        if name != cid:  # só mostrar se tinha nome (estava nos conhecidos)
            print(f"  --  {cid}: {name:25} {size:,}B")

print(f"\nCores validas para 208: {len(valid_colors)}")
print(f"Cores invalidas/nao-existentes: {len(invalid_colors)}")

# Guardar cores válidas actualizadas
out = DATA_DIR / "peugeot_colors_valid.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(valid_colors, f, ensure_ascii=False, indent=2)
print(f"Guardado em {out}")
