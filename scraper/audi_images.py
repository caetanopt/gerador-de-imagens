"""
Descarrega as imagens de uma configuração Audi.
Mesma plataforma de imagens da Volkswagen — lógica genérica em
vw_images.py, só muda o domínio da CDN (letra da marca "A").
"""
from pathlib import Path

from scraper.vw_images import generate_images_generic, images_to_zip

CDN = "https://cdn.nwi-ms.com/media/pt/A/mc"
REFERER = "https://configurador.audi.pt/"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

# Vistas usadas pelo próprio configurador (capturadas ao vivo) — nomes
# diferentes da VW e sem spin 360. Pedidas com background=transparent, as
# exteriores vêm com alpha real e sombra nativa. "overview" (= "side") e
# "interiorfront" (= "interior") são idênticas byte a byte e ficam de
# fora. Nem todas existem para todos os modelos — as que faltam são
# ignoradas.
VIEWS = {
    "3_4_frente": "front",
    "frente": "directfront",
    "lado": "side",
    "traseira": "back",
    "traseira_recta": "directback",
    "farol_detalhe": "headlight",
    "jante_detalhe": "wheel",
    "interior": "interior",
    "interior_lateral": "interiorside",
    "interior_bancos_traseiros": "back_seats",
    "bagageira_detalhe": "trunk",
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
        transparent=True,
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
