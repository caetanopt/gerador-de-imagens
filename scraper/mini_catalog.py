"""
Extrai o catálogo MINI Portugal: modelos, cores e jantes.
A MINI (grupo BMW) usa exactamente a mesma plataforma "Connext" que a
BMW — só mudam a marca ("mini" em vez de "bmwCar"), o namespace connext
("connext-mini") e a x-api-key. Toda a lógica está em
bmw_catalog.build_catalog_generic.

Cache em data/mini_catalog.json.
"""
from pathlib import Path

from scraper.bmw_catalog import build_catalog_generic

UCP_API_KEY = "Ok9zQ1d2NE9xbFZNNzN4NWZNWnFFbGl6R3dHTFdWUGxiV1RXb29vCg=="
BRAND = "mini"
CONNEXT_NS = "connext-mini"
REFERER = "https://configure.mini.pt/"
DATA_FILE = Path(__file__).parent.parent / "data" / "mini_catalog.json"


def build_catalog(force: bool = False) -> dict:
    """Constrói e guarda o catálogo MINI. Usa cache se existir."""
    return build_catalog_generic("MINI", BRAND, CONNEXT_NS, UCP_API_KEY, REFERER, DATA_FILE, force)


def load_catalog() -> dict:
    """Devolve o catálogo do cache. Constrói se não existir."""
    return build_catalog(force=False)


if __name__ == "__main__":
    catalog = build_catalog(force=True)
    total_models = sum(len(g["variants"]) for g in catalog["models"])
    print(f"\nTotal: {len(catalog['models'])} grupos, {total_models} variantes")
