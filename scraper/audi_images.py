"""
Descarrega as 4 imagens de uma configuração Audi.
Mesma plataforma de imagens da Volkswagen — lógica genérica em
vw_images.py, só muda o domínio da CDN (letra da marca "A").
"""
from pathlib import Path

from scraper.vw_images import generate_images_generic, images_to_zip

CDN = "https://cdn.nwi-ms.com/media/pt/A/mc"
REFERER = "https://configurador.audi.pt/"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

# A CDN da Audi não tem uma vista "exteriorfront" (frente recta) como a VW —
# "front"/"back" são já ângulos de 3/4. Não há vista traseira recta disponível.
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
    """Gera as imagens Audi para a configuração dada."""
    return generate_images_generic(
        CDN, REFERER, model_code, color_code, upholstery_code, wheel_code, views=VIEWS,
    )


if __name__ == "__main__":
    import sys
    mc = sys.argv[1] if len(sys.argv) > 1 else "F4BACMT0"
    color = sys.argv[2] if len(sys.argv) > 2 else "C2C2"
    upholstery = sys.argv[3] if len(sys.argv) > 3 else "AI"
    wheel = sys.argv[4] if len(sys.argv) > 4 else ""

    print(f"A gerar imagens: {mc} | cor={color} | upholstery={upholstery} | jante={wheel or 'serie'}")
    images = generate_images(mc, color, upholstery, wheel)
    OUTPUT_DIR.mkdir(exist_ok=True)
    for label, data in images.items():
        path = OUTPUT_DIR / f"audi_{mc}_{color}_{label}.webp"
        path.write_bytes(data)
        print(f"  {path.name} ({len(data):,} bytes)")
