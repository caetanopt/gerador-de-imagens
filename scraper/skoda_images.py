"""
Descarrega as imagens de uma configuração Škoda.
Mesma plataforma de imagens da Volkswagen — lógica genérica em
vw_images.py, só muda o domínio da CDN (letra da marca "C" — note-se que
não é "S", essa letra devolve imagens da SEAT nesta plataforma).
"""
from pathlib import Path

from scraper.vw_images import generate_images_generic, images_to_zip

CDN = "https://cdn.nwi-ms.com/media/pt/C/mc"
REFERER = "https://configurador.skoda.pt/"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

# Tal como a Audi, a CDN da Škoda não tem uma vista "exteriorfront" (frente
# recta) — "front"/"back" já são ângulos de 3/4. Ao contrário da Audi, tem
# mesmo assim uma imagem de interior disponível para todos os modelos
# testados.
VIEWS = {
    "3_4_frente": "front",
    "lado": "side",
    "traseira": "back",
    "interior": "interior",
    "lado_estudio": "overview",
}


def generate_images(
    model_code: str,
    color_code: str,
    upholstery_code: str,
    wheel_code: str = "",
    **_,
) -> dict[str, bytes]:
    """Gera as imagens Škoda para a configuração dada."""
    return generate_images_generic(
        CDN, REFERER, model_code, color_code, upholstery_code, wheel_code, views=VIEWS,
    )


if __name__ == "__main__":
    import sys
    mc = sys.argv[1] if len(sys.argv) > 1 else "PJ3DF405"
    color = sys.argv[2] if len(sys.argv) > 2 else "0B0B"
    upholstery = sys.argv[3] if len(sys.argv) > 3 else "NQ"
    wheel = sys.argv[4] if len(sys.argv) > 4 else ""

    print(f"A gerar imagens: {mc} | cor={color} | upholstery={upholstery} | jante={wheel or 'serie'}")
    images = generate_images(mc, color, upholstery, wheel)
    OUTPUT_DIR.mkdir(exist_ok=True)
    for label, data in images.items():
        path = OUTPUT_DIR / f"skoda_{mc}_{color}_{label}.webp"
        path.write_bytes(data)
        print(f"  {path.name} ({len(data):,} bytes)")
