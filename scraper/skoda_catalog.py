"""
Extrai o catálogo Škoda Portugal: modelos, cores e jantes.

A Škoda usa exactamente a mesma plataforma "Car Configurator" da
Volkswagen (mesmo formato de API e de CDN de imagens) — só muda o
domínio (configurador.skoda.pt), o locale no caminho (pt_PT_SKODA23) e a
letra da marca. Note-se que a letra da Škoda é "C" — "S" neste endpoint
devolve os modelos da SEAT (Ibiza/Arona/Leon), não da Škoda; confirmado
pelos nomes reais devolvidos (Fabia, Octavia, Superb, Kodiaq, Enyaq...).
Toda a lógica de extracção está em vw_catalog.py.

Cache em data/skoda_catalog.json.
"""
from pathlib import Path

from scraper.vw_catalog import build_catalog_generic

BASE = "https://configurador.skoda.pt/cc-pt/be/pt_PT_SKODA23"
BRAND_CODE = "C"
REFERER = "https://configurador.skoda.pt/"
DATA_FILE = Path(__file__).parent.parent / "data" / "skoda_catalog.json"


def build_catalog(force: bool = False) -> dict:
    """Constrói e guarda o catálogo Škoda. Usa cache se existir."""
    return build_catalog_generic("Skoda", BASE, BRAND_CODE, REFERER, DATA_FILE, force)


def load_catalog() -> dict:
    """Devolve o catálogo do cache. Constrói se não existir."""
    return build_catalog(force=False)


if __name__ == "__main__":
    catalog = build_catalog(force=True)
    total_models = sum(len(g["variants"]) for g in catalog["models"])
    print(f"\nTotal: {len(catalog['models'])} grupos, {total_models} variantes")
