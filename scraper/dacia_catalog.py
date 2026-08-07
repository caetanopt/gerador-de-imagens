"""
Extrai o catálogo Dacia Portugal: modelos, versões, cores e jantes.

A Dacia usa exactamente a mesma plataforma de configurador "One" que a
Renault (o mesmo backend pt.co.rplug.renault.com e o mesmo visualizador
3D 3dv.renault.com) — só muda o domínio (dacia.pt) e o nome do nó do
configurador no APP_STATE ("configurator_copy" em vez de "configurator").
Toda a lógica de extracção está em renault_catalog.py.

Cache em data/dacia_catalog.json.
"""
from pathlib import Path

from scraper.renault_catalog import build_catalog_generic

DATA_FILE = Path(__file__).parent.parent / "data" / "dacia_catalog.json"
HUB_URL = "https://www.dacia.pt/configuradores.html"
BASE_DOMAIN = "https://www.dacia.pt"


def build_catalog(force: bool = False) -> dict:
    """Constrói e guarda o catálogo Dacia. Usa cache se existir."""
    return build_catalog_generic("Dacia", HUB_URL, BASE_DOMAIN, DATA_FILE, force)


def load_catalog() -> dict:
    """Devolve o catálogo do cache. Constrói se não existir."""
    return build_catalog(force=False)


if __name__ == "__main__":
    catalog = build_catalog(force=True)
    total_variants = sum(len(m["variants"]) for m in catalog["models"])
    print(f"\nTotal: {len(catalog['models'])} modelos, {total_variants} versões")
