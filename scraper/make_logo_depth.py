"""
Adiciona profundidade (sombra suave projectada) ao logo "caetano" já
gravado em data/template.png, sem tocar no resto da imagem (fundo branco).
Gera uma pré-visualização antes de substituir o ficheiro real.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

TEMPLATE_PATH = Path(__file__).parent.parent / "data" / "template.png"
PREVIEW_PATH = Path(__file__).parent.parent / "data" / "template_logo_depth_preview.png"

# parametros da sombra
SHADOW_OFFSET_X = 4
SHADOW_OFFSET_Y = 6
SHADOW_BLUR = 6
SHADOW_OPACITY = 0.45  # 0-1
SHADOW_COLOR = (10, 20, 35)  # quase preto, tom frio a condizer com o logo


def main():
    template = Image.open(TEMPLATE_PATH).convert("RGBA")
    arr = np.array(template).astype(np.float64)

    # mascara do logo: quanto o pixel difere do branco (255,255,255)
    rgb = arr[:, :, :3]
    whiteness = rgb.min(axis=2)  # 255 = branco puro, menor = mais "tinta"
    logo_alpha = np.clip(255 - whiteness, 0, 255)

    # limitar a mascara a uma zona um pouco maior que o bbox do logo,
    # para nao arrastar ruido de compressao do resto da imagem branca
    ys, xs = np.where(logo_alpha > 8)
    pad = 40
    y0, y1 = max(0, ys.min() - pad), min(template.height, ys.max() + pad)
    x0, x1 = max(0, xs.min() - pad), min(template.width, xs.max() + pad)
    region_mask = np.zeros_like(logo_alpha)
    region_mask[y0:y1, x0:x1] = logo_alpha[y0:y1, x0:x1]
    logo_alpha = region_mask

    logo_mask_img = Image.fromarray(logo_alpha.astype(np.uint8), mode="L")

    # camada de sombra: mascara deslocada, desfocada, colorida e com opacidade reduzida
    shadow_mask = Image.new("L", template.size, 0)
    shadow_mask.paste(logo_mask_img, (SHADOW_OFFSET_X, SHADOW_OFFSET_Y))
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(SHADOW_BLUR))
    shadow_arr = (np.array(shadow_mask).astype(np.float64) * SHADOW_OPACITY).astype(np.uint8)

    shadow_layer = Image.new("RGBA", template.size, (*SHADOW_COLOR, 0))
    shadow_rgba = np.array(shadow_layer)
    shadow_rgba[:, :, 3] = shadow_arr
    shadow_layer = Image.fromarray(shadow_rgba, mode="RGBA")

    # resultado: fundo branco original -> sombra -> logo original por cima
    result = template.copy()
    # remover o logo original temporariamente (repor branco) para nao duplicar,
    # so na zona onde a sombra vai ficar por baixo do proprio logo original
    result = Image.alpha_composite(result, shadow_layer)
    original_logo_rgba = np.array(template.convert("RGBA")).copy()
    original_logo_rgba[:, :, 3] = logo_alpha.astype(np.uint8)
    original_logo_layer = Image.fromarray(original_logo_rgba, mode="RGBA")
    result = Image.alpha_composite(result, original_logo_layer)

    result.convert("RGB").save(PREVIEW_PATH)
    print(f"Pré-visualização guardada em {PREVIEW_PATH}")


if __name__ == "__main__":
    main()
