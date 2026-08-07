"""
Gera o template.png: fundo branco liso com o logo Caetano no canto superior esquerdo.
Corre uma vez sempre que for preciso regenerar o template.
"""
from pathlib import Path
from PIL import Image

DATA_DIR = Path(__file__).parent.parent / "data"
TEMPLATE_SIZE = (1195, 896)
LOGO_TARGET_WIDTH = 453
LOGO_MARGIN_LEFT = 44
LOGO_MARGIN_TOP = 58


def main():
    logo = Image.open(DATA_DIR / "logo_caetano.png").convert("RGBA")
    logo = logo.crop(logo.getbbox())

    scale = LOGO_TARGET_WIDTH / logo.width
    logo = logo.resize((LOGO_TARGET_WIDTH, round(logo.height * scale)), Image.LANCZOS)

    template = Image.new("RGBA", TEMPLATE_SIZE, (255, 255, 255, 255))
    template.paste(logo, (LOGO_MARGIN_LEFT, LOGO_MARGIN_TOP), logo)
    template.save(DATA_DIR / "template.png")


if __name__ == "__main__":
    main()
