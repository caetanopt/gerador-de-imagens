import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def load(fname):
    path = DATA_DIR / fname
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def report(name, n_models, n_versions, n_colors, n_wheels, empty_colors, empty_wheels, wheels_applicable=True):
    wheels_str = f"jantes={n_wheels} (sem jantes em {empty_wheels})" if wheels_applicable else "jantes=N/A (marca sem jantes seleccionaveis)"
    print(f"{name:14s} modelos={n_models:3d} versoes={n_versions:4d} cores={n_colors:5d} (sem cores em {empty_colors:3d})  {wheels_str}")


# ── VW-group: vw, audi, skoda (models -> variants[colors,wheels]) ──────────
for fname, label in [("vw_catalog.json", "VW"), ("audi_catalog.json", "Audi"), ("skoda_catalog.json", "Skoda")]:
    cat = load(fname)
    if not cat:
        print(f"{label}: SEM FICHEIRO"); continue
    variants = [v for g in cat["models"] for v in g["variants"]]
    n_colors = sum(len(v["colors"]) for v in variants)
    n_wheels = sum(len(v["wheels"]) for v in variants)
    empty_c = sum(1 for v in variants if not v["colors"])
    empty_w = sum(1 for v in variants if not v["wheels"])
    report(label, len(cat["models"]), len(variants), n_colors, n_wheels, empty_c, empty_w)

# ── BMW-group: bmw, mini (models -> variants[colors,wheels]) ───────────────
for fname, label in [("bmw_catalog.json", "BMW"), ("mini_catalog.json", "MINI")]:
    cat = load(fname)
    if not cat:
        print(f"{label}: SEM FICHEIRO"); continue
    variants = [v for g in cat["models"] for v in g["variants"]]
    n_colors = sum(len(v["colors"]) for v in variants)
    n_wheels = sum(len(v["wheels"]) for v in variants)
    empty_c = sum(1 for v in variants if not v["colors"])
    empty_w = sum(1 for v in variants if not v["wheels"])
    report(label, len(cat["models"]), len(variants), n_colors, n_wheels, empty_c, empty_w)

# ── Mercedes (models -> variants[colors,wheels]) ────────────────────────────
cat = load("mercedes_catalog.json")
if cat:
    variants = [v for g in cat["models"] for v in g["variants"]]
    n_colors = sum(len(v["colors"]) for v in variants)
    n_wheels = sum(len(v["wheels"]) for v in variants)
    empty_c = sum(1 for v in variants if not v["colors"])
    empty_w = sum(1 for v in variants if not v["wheels"])
    report("Mercedes", len(cat["models"]), len(variants), n_colors, n_wheels, empty_c, empty_w)

# ── Renault-group: renault, dacia, alpine (models -> variants[colors,wheels]) ─
for fname, label in [("renault_catalog.json", "Renault"), ("dacia_catalog.json", "Dacia"), ("alpine_catalog.json", "Alpine")]:
    cat = load(fname)
    if not cat:
        print(f"{label}: SEM FICHEIRO"); continue
    variants = [v for m in cat["models"] for v in m["variants"]]
    n_colors = sum(len(v["colors"]) for v in variants)
    n_wheels = sum(len(v["wheels"]) for v in variants)
    empty_c = sum(1 for v in variants if not v["colors"])
    empty_w = sum(1 for v in variants if not v["wheels"])
    report(label, len(cat["models"]), len(variants), n_colors, n_wheels, empty_c, empty_w)

# ── Opel (models -> variants[colors,wheels]) ────────────────────────────────
cat = load("opel_catalog.json")
if cat:
    variants = [v for m in cat["models"] for v in m["variants"]]
    n_colors = sum(len(v["colors"]) for v in variants)
    n_wheels = sum(len(v.get("wheels", [])) for v in variants)
    empty_c = sum(1 for v in variants if not v["colors"])
    empty_w = sum(1 for v in variants if not v.get("wheels"))
    report("Opel", len(cat["models"]), len(variants), n_colors, n_wheels, empty_c, empty_w)

# ── Peugeot (models -> variants[colors], sem jantes) ────────────────────────
cat = load("peugeot_catalog.json")
if cat:
    variants = [v for m in cat["models"] for v in m["variants"]]
    n_colors = sum(len(v["colors"]) for v in variants)
    empty_c = sum(1 for v in variants if not v["colors"])
    report("Peugeot", len(cat["models"]), len(variants), n_colors, 0, empty_c, 0, wheels_applicable=False)

# ── Zeekr (models -> variants[colors], sem jantes) ──────────────────────────
cat = load("zeekr_catalog.json")
if cat:
    variants = [v for m in cat["models"] for v in m["variants"]]
    n_colors = sum(len(v["colors"]) for v in variants)
    empty_c = sum(1 for v in variants if not v["colors"])
    report("Zeekr", len(cat["models"]), len(variants), n_colors, 0, empty_c, 0, wheels_applicable=False)

# ── BYD (models -> variants[colors], sem jantes) ────────────────────────────
cat = load("byd_catalog.json")
if cat:
    variants = [v for m in cat["models"] for v in m["variants"]]
    n_colors = sum(len(v["colors"]) for v in variants)
    empty_c = sum(1 for v in variants if not v["colors"])
    report("BYD", len(cat["models"]), len(variants), n_colors, 0, empty_c, 0, wheels_applicable=False)

# ── Hyundai (models -> variants[colors], sem jantes) ────────────────────────
cat = load("hyundai_catalog.json")
if cat:
    variants = [v for m in cat["models"] for v in m["variants"]]
    n_colors = sum(len(v["colors"]) for v in variants)
    empty_c = sum(1 for v in variants if not v["colors"])
    report("Hyundai", len(cat["models"]), len(variants), n_colors, 0, empty_c, 0, wheels_applicable=False)

# ── Geely (models -> versions[] + colors[] a nivel de modelo) ──────────────
cat = load("geely_catalog.json")
if cat:
    n_versions = sum(len(m["versions"]) for m in cat["models"])
    n_colors = sum(len(m["colors"]) for m in cat["models"])
    report("Geely", len(cat["models"]), n_versions, n_colors, 0, 0, 0, wheels_applicable=False)

# ── XPENG (models -> versions[colors]) ──────────────────────────────────────
cat = load("xpeng_catalog.json")
if cat:
    versions = [v for m in cat["models"] for v in m["versions"]]
    n_colors = sum(len(v["colors"]) for v in versions)
    empty_c = sum(1 for v in versions if not v["colors"])
    report("XPENG", len(cat["models"]), len(versions), n_colors, 0, empty_c, 0, wheels_applicable=False)

# ── Nissan (misto: legacy grades->versions[colors] / rich360 colors) ───────
cat = load("nissan_catalog.json")
if cat:
    legacy = [m for m in cat["models"] if m["type"] == "legacy"]
    rich = [m for m in cat["models"] if m["type"] == "rich360"]
    versions = [v for m in legacy for g in m["grades"] for v in g["versions"]]
    n_colors = sum(len(v["colors"]) for v in versions)
    empty_c = sum(1 for v in versions if not v["colors"])
    print(f"{'Nissan(legado)':14s} modelos={len(legacy):3d} versoes={len(versions):4d} cores={n_colors:5d} (sem cores em {empty_c:3d})  jantes=N/A (informativas, sem imagem)")
    rich_colors = sum(len(m["colors"]) for m in rich)
    print(f"{'Nissan(360)':14s} modelos={len(rich):3d} versoes=N/A cores={rich_colors:5d}  jantes=N/A (spinner so por cor)")
