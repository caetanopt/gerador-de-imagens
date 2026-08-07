"""
Composta imagens de carro sobre o template Caetano.
Imagens com alpha usam-no directamente; imagens sem alpha têm o fundo
removido por rembg (U2Net).
"""
import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

TEMPLATE_PATH = Path(__file__).parent.parent / "data" / "template.png"

# Posição do carro no template (frações das dimensões do template)
CAR_MAX_WIDTH_FRAC  = 0.90
CAR_BOTTOM_Y_FRAC   = 0.83
CAR_CENTER_X_FRAC   = 0.50
MIN_TOP_MARGIN_FRAC = 0.17   # margem mínima no topo para não cobrir o logo

# Pixels com alpha >= a este valor contam como carro "sólido" (carroçaria,
# pneus). Abaixo disso é sombra/reflexo suave no chão, que tem comprimento
# variável consoante o render e não deve influenciar o enquadramento.
SOLID_ALPHA_THRESHOLD = 250

# Margem (em pixels da imagem de origem) acima do ponto de contacto mais
# baixo do carro que ainda se considera "borda do carro" (anti-aliasing
# de vidros/antena/espelhos) em vez de "sombra no chão".
GROUND_Y_TOLERANCE = 3

# Sombra sintética desenhada por baixo do carro (fracções da largura
# "sólida" final, já escalada): garante uma sombra consistente e realista
# em todas as marcas, em vez de depender da sombra natural de cada render
# — o rembg corta-a de forma inconsistente (bem em algumas vistas/marcas,
# completamente em outras, ex.: a vista de lado da VW).
SHADOW_WIDTH_FRAC  = 0.92   # relativa à largura sólida do carro
SHADOW_HEIGHT_FRAC = 0.10   # relativa à largura da própria sombra
SHADOW_OPACITY     = 110    # 0-255
SHADOW_COLOR       = (20, 20, 25)

# O gradiente da sombra é pré-calculado UMA VEZ numa tela pequena (onde o
# blur cobre a forma toda, sem deixar nenhuma zona interior por suavizar)
# e depois esticado para o tamanho final em cada chamada. Desenhar a
# elipse já no tamanho final e só desfocar as bordas (abordagem anterior)
# deixava um "planalto" sólido e sem gradiente no meio de sombras largas
# (carros que ocupam quase toda a largura do template), o que se via como
# uma barra escura com contornos direitos em vez de uma sombra suave.
_SHADOW_BLOB_SIZE       = 256
_SHADOW_BLOB_CIRCLE_FRAC = 0.42
_SHADOW_BLOB_BLUR_FRAC   = 0.16

# Salvaguarda contra imagens onde não há uma silhueta de carro fiável a
# detectar (ex.: uma cena de interior/lifestyle sem carroçaria visível,
# onde o rembg deixa só um resíduo minúsculo de alpha "sólido") — sem
# isto, `scale` explode e o resize seguinte tenta alocar uma imagem
# gigantesca (MemoryError). Nesses casos devolve-se a imagem original,
# tal como já acontece para labels "interior"/"detalhe" em app.py.
MIN_SOLID_FRAC = 0.05
MAX_SCALE = 6.0


def _has_alpha(img: Image.Image) -> bool:
    """True se a imagem já tem transparência real no canal alpha."""
    if img.mode != "RGBA":
        return False
    arr = np.array(img)
    return bool((arr[:, :, 3] < 255).any())


_rembg_session = None


def _get_rembg_session():
    global _rembg_session
    if _rembg_session is None:
        from rembg import new_session
        _rembg_session = new_session("u2net")
    return _rembg_session


def _remove_bg_rembg(img_bytes: bytes) -> Image.Image:
    from rembg import remove
    result = remove(img_bytes, session=_get_rembg_session())
    return Image.open(io.BytesIO(result)).convert("RGBA")


def _desaturate_soft_pixels(img: Image.Image) -> Image.Image:
    """
    Remove o matiz de pixels com alpha parcial (a sombra/reflexo suave no
    chão): deviam ser neutros, mas quando o fundo original tem uma cor forte
    (ex.: o piso azul dos renders de estúdio da MINI), o rembg deixa esse
    matiz infiltrar-se na sombra composta. Em fundos já neutros isto não
    muda visivelmente nada.
    """
    arr = np.array(img).astype(np.float64)
    alpha = arr[:, :, 3]
    soft = (alpha > 0) & (alpha < SOLID_ALPHA_THRESHOLD)
    if soft.any():
        gray = arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114
        for c in range(3):
            arr[:, :, c] = np.where(soft, gray, arr[:, :, c])
    return Image.fromarray(arr.astype(np.uint8), mode="RGBA")


def _remove_disconnected_alpha(img: Image.Image) -> Image.Image:
    """
    Remove ilhas de alpha desligadas do corpo sólido do carro — falhas de
    segmentação do rembg que deixam uma silhueta residual "fantasma" (ex.:
    um resíduo semi-transparente do tejadilho flutuando por cima do carro,
    sem qualquer ligação física ao resto da carroçaria). Mantém só a(s)
    componente(s) ligada(s) que tocam o alpha "sólido" (>= SOLID_ALPHA_THRESHOLD);
    zera tudo o resto.
    """
    from scipy import ndimage

    arr = np.array(img)
    alpha = arr[:, :, 3]
    solid_mask = alpha >= SOLID_ALPHA_THRESHOLD
    if not solid_mask.any():
        return img
    full_mask = alpha > 0
    labeled, _ = ndimage.label(full_mask, structure=np.ones((3, 3), dtype=int))
    solid_labels = set(np.unique(labeled[solid_mask])) - {0}
    keep_mask = np.isin(labeled, list(solid_labels))
    alpha2 = np.where(keep_mask, alpha, 0)
    arr = arr.copy()
    arr[:, :, 3] = alpha2
    return Image.fromarray(arr, mode="RGBA")


def _strip_ground_shadow(img: Image.Image) -> Image.Image:
    """
    Remove o alpha parcial (sombra/reflexo natural do render) que fica ao
    nível do ponto de contacto do carro com o solo ou abaixo dele — é aí
    que o rembg é inconsistente entre marcas/ângulos (ex.: preserva uma
    sombra longa na traseira da VW mas corta-a por completo na vista de
    lado). Preserva o alpha parcial ACIMA do ponto de contacto (anti-
    aliasing de vidros, espelhos, antena), que não deve ser tocado.
    Substituída por uma sombra sintética consistente em composite().
    """
    arr = np.array(img)
    alpha = arr[:, :, 3]
    solid_mask = alpha >= SOLID_ALPHA_THRESHOLD
    ys, _ = np.where(solid_mask)
    if len(ys) == 0:
        return img
    contact_y = ys.max()
    soft = (alpha > 0) & (alpha < SOLID_ALPHA_THRESHOLD)
    rows = np.arange(alpha.shape[0])[:, None]
    to_strip = soft & (rows > (contact_y - GROUND_Y_TOLERANCE))
    alpha2 = np.where(to_strip, 0, alpha)
    arr = arr.copy()
    arr[:, :, 3] = alpha2
    return Image.fromarray(arr, mode="RGBA")


_shadow_blob = None


def _get_shadow_blob() -> Image.Image:
    """
    Gradiente radial suave (0-255) pré-calculado uma única vez, numa tela
    pequena e fixa — o blur é aplicado aqui, onde cobre a forma inteira, e
    não depois de esticar para o tamanho final (ver nota em SHADOW_WIDTH_FRAC).
    """
    global _shadow_blob
    if _shadow_blob is None:
        size = _SHADOW_BLOB_SIZE
        blob = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(blob)
        r = size * _SHADOW_BLOB_CIRCLE_FRAC
        c = size / 2
        draw.ellipse([c - r, c - r, c + r, c + r], fill=255)
        _shadow_blob = blob.filter(ImageFilter.GaussianBlur(size * _SHADOW_BLOB_BLUR_FRAC))
    return _shadow_blob


def _draw_synthetic_shadow(template: Image.Image, sx0: float, sx1: float, base_y: float) -> Image.Image:
    """
    Desenha uma sombra elíptica suave, centrada no eixo do carro, com a
    base à altura `base_y`. Devolve o template com a sombra já composta.
    """
    shadow_w = max(1, round((sx1 - sx0) * SHADOW_WIDTH_FRAC))
    shadow_h = max(1, round(shadow_w * SHADOW_HEIGHT_FRAC))
    shadow_cx = (sx0 + sx1) / 2
    shadow_cy = base_y - shadow_h * 0.15

    mask = _get_shadow_blob().resize((shadow_w, shadow_h), Image.BILINEAR)
    color_layer = Image.new("RGBA", mask.size, (*SHADOW_COLOR, 0))
    color_layer.putalpha(mask.point(lambda v: v * SHADOW_OPACITY // 255))

    shadow_layer = Image.new("RGBA", template.size, (0, 0, 0, 0))
    shadow_layer.paste(color_layer, (round(shadow_cx - shadow_w / 2), round(shadow_cy - shadow_h / 2)), color_layer)
    return Image.alpha_composite(template, shadow_layer)


def _solid_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    """
    Bounding box do carro "sólido" (carroçaria/pneus), ignorando a sombra ou
    reflexo suave no chão. É esta bbox que serve de referência para escalar
    e alinhar o carro, para que o ponto de contacto mais baixo dos pneus
    fique sempre à mesma altura, independentemente do comprimento da sombra.
    """
    alpha = np.array(img.split()[-1])
    mask = alpha >= SOLID_ALPHA_THRESHOLD
    ys, xs = np.where(mask)
    if len(xs) == 0:
        bbox = img.getbbox()
        return bbox if bbox else (0, 0, img.width, img.height)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def composite(car_bytes: bytes) -> bytes:
    """
    Sobrepõe a imagem do carro sobre o template Caetano.
    Se o template não existir devolve a imagem original sem alteração.
    """
    if not TEMPLATE_PATH.exists():
        return car_bytes

    template = Image.open(TEMPLATE_PATH).convert("RGBA")
    tw, th = template.size

    car = Image.open(io.BytesIO(car_bytes)).convert("RGBA")

    if not _has_alpha(car):
        car = _remove_bg_rembg(car_bytes)
    car = _remove_disconnected_alpha(car)
    car = _desaturate_soft_pixels(car)
    car = _strip_ground_shadow(car)

    sx0, sy0, sx1, sy1 = _solid_bbox(car)
    solid_w, solid_h = sx1 - sx0, sy1 - sy0

    if solid_w < car.width * MIN_SOLID_FRAC and solid_h < car.height * MIN_SOLID_FRAC:
        # não há silhueta de carro fiável nesta imagem — devolve-a sem
        # recorte/logo, mas ainda assim com o mesmo tamanho de ficheiro
        # das restantes.
        return standardize_only(car_bytes)

    # Escalar para o carro "sólido" caber em max_width × max_height
    # (mantendo proporção); a sombra escala junto mas não conta para o limite.
    max_w = int(tw * CAR_MAX_WIDTH_FRAC)
    max_h = int(th * CAR_BOTTOM_Y_FRAC) - int(th * MIN_TOP_MARGIN_FRAC)
    scale = min(max_w / solid_w, max_h / solid_h, MAX_SCALE)
    if scale != 1.0:
        car = car.resize((round(car.width * scale), round(car.height * scale)), Image.LANCZOS)
        sx0, sy0, sx1, sy1 = sx0 * scale, sy0 * scale, sx1 * scale, sy1 * scale

    # Posicionar: bbox sólida centrada horizontalmente e com a base sempre
    # à mesma altura.
    paste_x = round(tw * CAR_CENTER_X_FRAC - (sx0 + (sx1 - sx0) / 2))
    paste_y = round(th * CAR_BOTTOM_Y_FRAC - sy1)

    result = _draw_synthetic_shadow(template.copy(), paste_x + sx0, paste_x + sx1, th * CAR_BOTTOM_Y_FRAC)
    result.paste(car, (paste_x, paste_y), car)

    buf = io.BytesIO()
    result.convert("RGB").save(buf, format="JPEG", quality=93)
    return buf.getvalue()


def standardize_only(image_bytes: bytes) -> bytes:
    """
    Ajusta uma imagem (interior, detalhe de jante) ao mesmo tamanho de
    ficheiro do template Caetano, SEM aplicar nenhuma das transformações de
    composite() (sem recorte de carro, sem remoção de fundo, sem logo nem
    sombra) — o conteúdo fica intacto, só a tela é ajustada por letterbox
    (fundo branco a preencher a diferença de proporção) para que todas as
    imagens do mesmo ZIP saiam com a mesma resolução.
    """
    if not TEMPLATE_PATH.exists():
        return image_bytes
    tw, th = Image.open(TEMPLATE_PATH).size
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    scale = min(tw / img.width, th / img.height)
    new_w, new_h = round(img.width * scale), round(img.height * scale)
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (tw, th), (255, 255, 255))
    canvas.paste(resized, ((tw - new_w) // 2, (th - new_h) // 2))

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=93)
    return buf.getvalue()


def has_template() -> bool:
    return TEMPLATE_PATH.exists()
