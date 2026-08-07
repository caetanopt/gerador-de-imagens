import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def load(fname):
    path = DATA_DIR / fname
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def check_variants(label, variants, name_key="versionName"):
    zero = [v for v in variants if not v.get("colors")]
    if zero:
        print(f"{label}: {len(zero)} variantes SEM CORES:")
        for v in zero:
            print("   ", v.get(name_key) or v.get("name"))
    else:
        print(f"{label}: OK (nenhuma variante sem cores)")


for fname, label in [
    ("vw_catalog.json", "VW"), ("audi_catalog.json", "Audi"), ("skoda_catalog.json", "Skoda"),
    ("bmw_catalog.json", "BMW"), ("mini_catalog.json", "MINI"), ("mercedes_catalog.json", "Mercedes"),
]:
    cat = load(fname)
    if cat:
        variants = [v for g in cat["models"] for v in g["variants"]]
        check_variants(label, variants)

for fname, label in [("renault_catalog.json", "Renault"), ("dacia_catalog.json", "Dacia"), ("opel_catalog.json", "Opel")]:
    cat = load(fname)
    if cat:
        variants = [v for m in cat["models"] for v in m["variants"]]
        check_variants(label, variants)

for fname, label in [("peugeot_catalog.json", "Peugeot"), ("zeekr_catalog.json", "Zeekr"), ("byd_catalog.json", "BYD"), ("hyundai_catalog.json", "Hyundai")]:
    cat = load(fname)
    if cat:
        variants = [v for m in cat["models"] for v in m["variants"]]
        check_variants(label, variants)

cat = load("xpeng_catalog.json")
if cat:
    variants = [v for m in cat["models"] for v in m["versions"]]
    check_variants("XPENG", variants)

cat = load("geely_catalog.json")
if cat:
    zero = [m for m in cat["models"] if not m.get("colors")]
    print("Geely:", "OK" if not zero else f"{len(zero)} modelos sem cores")

cat = load("nissan_catalog.json")
if cat:
    legacy_versions = [v for m in cat["models"] if m["type"] == "legacy" for g in m["grades"] for v in g["versions"]]
    check_variants("Nissan(legado)", legacy_versions, name_key="name")
    rich_zero = [m for m in cat["models"] if m["type"] == "rich360" and not m.get("colors")]
    print("Nissan(360):", "OK" if not rich_zero else f"{len(rich_zero)} modelos sem cores")
