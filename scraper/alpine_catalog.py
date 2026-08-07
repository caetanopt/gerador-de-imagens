"""
Extrai o catálogo Alpine Portugal: modelos, versões, cores e jantes.

A Alpine usa exactamente a mesma plataforma de configurador "One" que a
Renault e a Dacia (o mesmo backend pt.co.rplug.renault.com) — só muda o
domínio (alpinecars.pt, não alpine.pt). Toda a lógica de extracção está
em renault_catalog.py.

Cache em data/alpine_catalog.json.
"""
import json
from pathlib import Path

from scraper.renault_catalog import build_catalog_generic

DATA_FILE = Path(__file__).parent.parent / "data" / "alpine_catalog.json"
HUB_URL = "https://www.alpinecars.pt/configurador.html"
BASE_DOMAIN = "https://www.alpinecars.pt"


def build_catalog(force: bool = False) -> dict:
    """Constrói e guarda o catálogo Alpine. Usa cache se existir."""
    catalog = build_catalog_generic("Alpine", HUB_URL, BASE_DOMAIN, DATA_FILE, force)
    # O A110 é descoberto através do hub genérico "/gama/veiculos/configurador.html"
    # (não tem página própria "/modelos-.../a110/configurador.html" como o
    # A290/A390), cujo <title> é só "Configurador oficial Alpine" — não
    # bate com o padrão "Configurador {modelo} - Alpine" das outras
    # páginas, por isso _extract_model_name cai no fallback do slug
    # ("veiculos"). O nome real é claro pelas versões (A110/GTS/R 70).
    renamed = False
    for m in catalog["models"]:
        if m["modelId"] == "veiculos" and m["modelName"] != "A110":
            m["modelName"] = "A110"
            renamed = True
    if renamed:
        DATA_FILE.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return catalog


def load_catalog() -> dict:
    """Devolve o catálogo do cache. Constrói se não existir."""
    return build_catalog(force=False)


if __name__ == "__main__":
    catalog = build_catalog(force=True)
    total_variants = sum(len(m["variants"]) for m in catalog["models"])
    print(f"\nTotal: {len(catalog['models'])} modelos, {total_variants} versões")
