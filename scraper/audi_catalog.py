"""
Extrai o catálogo Audi Portugal: modelos, cores e jantes.

A Audi usa exactamente a mesma plataforma "Car Configurator" da
Volkswagen (mesmo formato de API e de CDN de imagens) — só muda o
domínio (configurador.audi.pt), o locale no caminho (pt_PT_AUDI23) e a
letra da marca (A em vez de V). Toda a lógica de extracção está em
vw_catalog.py.

Cache em data/audi_catalog.json.
"""
from pathlib import Path

from scraper.vw_catalog import build_catalog_generic

BASE = "https://configurador.audi.pt/cc-pt/be/pt_PT_AUDI23"
BRAND_CODE = "A"
REFERER = "https://configurador.audi.pt/"
DATA_FILE = Path(__file__).parent.parent / "data" / "audi_catalog.json"


def build_catalog(force: bool = False) -> dict:
    """Constrói e guarda o catálogo Audi. Usa cache se existir."""
    return build_catalog_generic("Audi", BASE, BRAND_CODE, REFERER, DATA_FILE, force)


def load_catalog() -> dict:
    """Devolve o catálogo do cache. Constrói se não existir."""
    return build_catalog(force=False)


if __name__ == "__main__":
    catalog = build_catalog(force=True)
    total_models = sum(len(g["variants"]) for g in catalog["models"])
    print(f"\nTotal: {len(catalog['models'])} grupos, {total_models} variantes")
