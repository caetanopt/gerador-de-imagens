"""
Descarrega imagens de uma configuração Alpine (modelo + versão + cor + jantes).

Mesma plataforma "One" da Renault/Dacia (3dv.renault.com) — toda a lógica de
navegação e geração de imagens está em renault_images.py, reaproveitada
aqui tal como está.
"""
from pathlib import Path

from scraper.renault_images import generate_images

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def images_to_zip(images: dict[str, bytes], zip_name: str = "imagens_alpine.zip") -> bytes:
    from scraper.renault_images import images_to_zip as _images_to_zip
    return _images_to_zip(images, zip_name)


if __name__ == "__main__":
    import sys
    configurator_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.alpinecars.pt/modelos-eletricos/a290/configurador.html"
    conf_uri = sys.argv[2] if len(sys.argv) > 2 else "https://pt.co.rplug.renault.com/c/BAEIj/Ao0"
    color = sys.argv[3] if len(sys.argv) > 3 else ""
    wheel = sys.argv[4] if len(sys.argv) > 4 else ""

    print(f"A gerar imagens: {configurator_url} | cor={color} | jante={wheel or '(série)'}")
    images = generate_images(configurator_url, conf_uri, color, wheel)
    OUTPUT_DIR.mkdir(exist_ok=True)
    for label, data in images.items():
        path = OUTPUT_DIR / f"alpine_{color}_{label}.jpg"
        path.write_bytes(data)
        print(f"  {path.name} ({len(data):,} bytes)")
