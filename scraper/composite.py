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

# Todas as imagens entregues (compostas ou só ajustadas de tamanho) saem
# em WebP — ficheiro bastante mais pequeno que JPEG a qualidade
# comparável. quality=75 causava um artefacto visível de "banding"
# (riscas/faixas subtis) no gradiente suave e extenso da sombra sintética
# — subiu-se para 92, que elimina o banding mantendo o ficheiro pequeno.
# method=6 é mais lento a comprimir mas com melhor rácio tamanho/qualidade.
OUTPUT_FORMAT = "WEBP"
OUTPUT_QUALITY = 92
OUTPUT_METHOD = 6

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
SHADOW_WIDTH_FRAC  = 0.74   # relativa à largura sólida do carro
SHADOW_HEIGHT_FRAC = 0.14   # relativa à largura da própria sombra
SHADOW_OPACITY     = 195    # 0-255
SHADOW_COLOR       = (20, 20, 25)

# O gradiente da sombra é pré-calculado UMA VEZ numa tela pequena (onde o
# blur cobre a forma toda, sem deixar nenhuma zona interior por suavizar)
# e depois esticado para o tamanho final em cada chamada. Desenhar a
# elipse já no tamanho final e só desfocar as bordas (abordagem anterior)
# deixava um "planalto" sólido e sem gradiente no meio de sombras largas
# (carros que ocupam quase toda a largura do template), o que se via como
# uma barra escura com contornos direitos em vez de uma sombra suave.
_SHADOW_BLOB_SIZE       = 256
_SHADOW_BLOB_CIRCLE_FRAC = 0.52
_SHADOW_BLOB_BLUR_FRAC   = 0.12

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


_MIN_REFLECTION_GAP = 4     # px; lacunas mais pequenas são ruído/antialiasing, não um reflexo
_REFLECTION_ZONE_FRAC = 0.55  # só considerar lacunas que comecem na metade inferior da imagem


def _remove_floor_reflection(img: Image.Image) -> Image.Image:
    """
    Remove reflexos no piso de estúdio brilhante (comum na Renault/Dacia)
    que ficam colados por baixo da roda — o rembg trata-os com confiança
    como parte sólida do carro, porque são uma cópia nítida e detalhada
    da jante, só que invertida. `_remove_disconnected_alpha` não apanha
    isto porque o reflexo toca o corpo sólido (não está "desligado").

    Uma primeira versão assumia que a silhueta de um carro é sempre um
    único troço contínuo de alpha por coluna — falso na prática: janelas,
    reflexos de cromados e sombras na pintura criam lacunas legítimas de
    alpha=0 dentro da própria carroçaria (confirmado visualmente: cortava
    riscas verticais a meio da carroçaria/janelas). Restringe-se por isso
    a apenas lacunas que comecem na zona inferior da imagem, onde só pode
    haver rodas/chão — nunca tejadilho, vidros ou portas.
    """
    arr = np.array(img)
    alpha = arr[:, :, 3]
    h, w = alpha.shape
    zone_start = int(h * _REFLECTION_ZONE_FRAC)
    has_alpha = alpha > 0
    out_alpha = alpha.copy()
    for x in range(w):
        ys = np.where(has_alpha[:, x])[0]
        if len(ys) < 2:
            continue
        gaps = np.where(np.diff(ys) > _MIN_REFLECTION_GAP)[0]
        for g in gaps:
            gap_start_row = ys[g] + 1
            if gap_start_row >= zone_start:
                out_alpha[gap_start_row:, x] = 0
                break
    if np.array_equal(out_alpha, alpha):
        return img
    arr = arr.copy()
    arr[:, :, 3] = out_alpha
    return Image.fromarray(arr, mode="RGBA")


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
    nível do ponto de contacto do carro com o solo ou abaixo dele, coluna
    a coluna — é aí que o rembg é inconsistente entre marcas/ângulos (ex.:
    preserva uma sombra longa na traseira da VW mas corta-a por completo
    na vista de lado). Usar um único ponto de contacto global (em vez de
    um por coluna) falhava nas vistas 3/4: a roda mais próxima da câmara
    define um contacto muito mais baixo do que o resto do carro, pelo que
    resíduos de sombra/reflexo junto a outras zonas (ex.: por baixo do
    pára-choques) ficavam acima da tolerância a partir desse único ponto
    e sobreviviam, aparecendo depois como uma mancha com borda dura.
    Preserva o alpha parcial ACIMA do ponto de contacto de cada coluna
    (anti-aliasing de vidros, espelhos, antena), que não deve ser tocado.
    Substituída por uma sombra sintética consistente em composite().
    """
    arr = np.array(img)
    alpha = arr[:, :, 3]
    solid_mask = alpha >= SOLID_ALPHA_THRESHOLD
    if not solid_mask.any():
        return img
    contact_col = _contact_profile(alpha, 0, alpha.shape[1])
    soft = (alpha > 0) & (alpha < SOLID_ALPHA_THRESHOLD)
    rows = np.arange(alpha.shape[0])[:, None]
    to_strip = soft & (rows > (contact_col[np.newaxis, :] - GROUND_Y_TOLERANCE))
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


def _contact_profile(alpha: np.ndarray, x0: int, x1: int) -> np.ndarray:
    """
    Para cada coluna entre x0 e x1, devolve a linha (y) do ponto de
    contacto mais baixo do carro nessa coluna. Colunas sem nenhum pixel
    sólido (raro, só nas pontas da bbox) são preenchidas por interpolação
    a partir das vizinhas válidas.
    """
    solid = alpha[:, x0:x1] >= SOLID_ALPHA_THRESHOLD
    has_solid = solid.any(axis=0)
    h = alpha.shape[0]
    from_bottom = solid[::-1, :].argmax(axis=0)
    contact = np.where(has_solid, h - 1 - from_bottom, np.nan).astype(float)
    idx = np.arange(len(contact))
    valid = ~np.isnan(contact)
    if not valid.any():
        return np.full(len(contact), h - 1, dtype=float)
    if not valid.all():
        contact = np.interp(idx, idx[valid], contact[valid])
    return contact


_BODY_SHADOW_OPACITY_FRAC = 0.88  # sombra "de ligação" sob a carroçaria, quase tão densa como a das rodas


def _find_wheel_peaks(contact: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Identifica, no perfil de contacto, as colunas onde uma roda toca o
    chão — os pontos mais baixos e localmente proeminentes do perfil.
    Devolve (posições x, larguras estimadas em px) de cada roda
    encontrada. Sem isto, uma única "fita" de sombra a seguir o contacto
    coluna a coluna ficava tão escura sob o pára-choques (que não toca o
    chão, só passa perto de uma roda) como mesmo por baixo do pneu —
    numa vista 3/4 fechada isso criava uma mancha escura a espreitar por
    baixo do pára-choques, destacada e pouco natural.
    """
    from scipy.signal import find_peaks, peak_widths

    w = len(contact)
    global_peak = int(np.argmax(contact))
    span = contact.max() - contact.min()
    if span < 1:
        return np.array([global_peak]), np.array([w * 0.3])

    min_distance = max(5, int(w * 0.12))
    peaks, _ = find_peaks(contact, distance=min_distance, prominence=span * 0.12)
    peaks = list(peaks)
    # find_peaks exige descida dos dois lados — o ponto de contacto mais
    # baixo de todo o carro (perto da margem da janela analisada, ex.:
    # roda dianteira numa vista 3/4 fechada) pode ficar de fora por não
    # ter descida suficiente antes do limite da janela. É sempre uma roda
    # real (é o próprio ponto de referência sy1), por isso garante-se aqui.
    if not any(abs(p - global_peak) < min_distance for p in peaks):
        peaks.append(global_peak)
    peaks = np.array(sorted(peaks))
    widths = peak_widths(contact, peaks, rel_height=0.5)[0]
    widths = np.where(widths > 1, widths, w * 0.25)
    return peaks, widths


def _draw_synthetic_shadow(
    template: Image.Image, car_alpha: np.ndarray, paste_x: int, paste_y: int,
    sx0: float, sx1: float, sy1: float,
) -> Image.Image:
    """
    Desenha uma sombra em duas camadas: uma mancha bem definida e escura
    directamente sob cada roda (onde o contacto com o chão é real), e uma
    sombra mais ténue e suave a ligar essas manchas sob a carroçaria —
    como acontece numa fotografia real. Seguir o perfil de contacto
    coluna a coluna de forma uniforme (uma única "fita") ficava tão
    escuro sob zonas que não tocam o chão (pára-choques, saias) como
    mesmo por baixo do pneu, o que nas vistas 3/4 mais fechadas criava
    manchas destacadas e pouco naturais. `sy1` é o ponto de contacto mais
    baixo de todo o carro (coordenadas locais da imagem, já escalada).
    """
    from scipy.ndimage import gaussian_filter1d

    solid_w = sx1 - sx0
    shadow_w = max(1, round(solid_w * SHADOW_WIDTH_FRAC))
    ref_h = max(1, round(shadow_w * SHADOW_HEIGHT_FRAC))
    sigma_v_wheel = ref_h / 2
    sigma_v_body = ref_h * 0.85
    shadow_cx = paste_x + (sx0 + sx1) / 2

    inset = (solid_w - shadow_w) / 2
    px0 = round(sx0 + inset)
    px1 = px0 + shadow_w
    px0c, px1c = max(0, px0), min(car_alpha.shape[1], px1)
    contact = _contact_profile(car_alpha, px0c, px1c)
    pad_left, pad_right = px0c - px0, px1 - px1c
    if pad_left > 0 or pad_right > 0:
        contact = np.pad(contact, (max(0, pad_left), max(0, pad_right)), mode="edge")
    contact_light = gaussian_filter1d(contact, sigma=max(2.0, shadow_w * 0.01))
    contact_baseline = gaussian_filter1d(contact, sigma=max(2.0, shadow_w * 0.25))

    wheel_x, wheel_w = _find_wheel_peaks(contact)
    xx = np.arange(shadow_w)
    wheel_weight = np.zeros(shadow_w)
    for px, wid in zip(wheel_x, wheel_w):
        sigma_x = max(8.0, wid * 0.55)
        wheel_weight = np.maximum(wheel_weight, np.exp(-0.5 * ((xx - px) / sigma_x) ** 2))

    centers_wheel = contact_light - sy1   # <= 0
    centers_body = contact_baseline - sy1  # <= 0, perfil suavizado (sem mergulhos localizados)

    # taper horizontal (perfil do "blob" já existente, amostrado em 1D pela
    # linha central) — 1 no centro, esbate para 0 nas pontas da sombra.
    blob_arr = np.asarray(_get_shadow_blob(), dtype=np.float32)
    mid_row = blob_arr[blob_arr.shape[0] // 2, :]
    horiz = np.interp(np.linspace(0, blob_arr.shape[1] - 1, shadow_w), np.arange(blob_arr.shape[1]), mid_row) / 255.0

    # A tela cresce o suficiente para conter toda a variação de AMBOS os
    # perfis (rodas e carroçaria) mais a margem de esbatimento gaussiano —
    # garante que a sombra desvanece sempre suavemente, mesmo quando o
    # perfil de contacto varia muito (carros pequenos/arredondados em
    # ângulos 3/4 fechados).
    margin = int(np.ceil(3 * max(sigma_v_wheel, sigma_v_body)))
    top = int(np.ceil(max(0.0, -centers_wheel.min(), -centers_body.min())))
    bottom = int(np.ceil(max(0.0, centers_wheel.max(), centers_body.max())))
    out_h = top + bottom + 2 * margin
    zero_row = top + margin  # linha correspondente ao deslocamento 0 (sy1)

    yy = np.arange(out_h)[:, None] - zero_row
    vert_wheel = np.exp(-0.5 * ((yy - centers_wheel[np.newaxis, :]) / sigma_v_wheel) ** 2)
    vert_body = np.exp(-0.5 * ((yy - centers_body[np.newaxis, :]) / sigma_v_body) ** 2)
    weight = wheel_weight[np.newaxis, :]
    combined = weight * vert_wheel + (1 - weight) * _BODY_SHADOW_OPACITY_FRAC * vert_body
    alpha_arr = (combined * horiz[np.newaxis, :] * SHADOW_OPACITY).clip(0, 255).astype(np.uint8)

    color_layer = Image.new("RGBA", (shadow_w, out_h), (*SHADOW_COLOR, 0))
    color_layer.putalpha(Image.fromarray(alpha_arr, mode="L"))

    anchor_y = paste_y + sy1 - ref_h * 0.15  # mesmo ajuste visual usado antes
    top_left_y = anchor_y - zero_row
    shadow_layer = Image.new("RGBA", template.size, (0, 0, 0, 0))
    shadow_layer.paste(color_layer, (round(shadow_cx - shadow_w / 2), round(top_left_y)), color_layer)
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

    # Marcas que já entregam a foto com transparência real (sem rembg) têm
    # a sua própria sombra/reflexo de contacto, feita pela marca — mais
    # fiável do que qualquer coisa sintética. Só substituímos a sombra
    # quando ela vem do rembg, cujo recorte junto ao chão é inconsistente
    # entre marcas/ângulos (ex.: preserva uma sombra longa nalguns casos,
    # corta-a por completo noutros).
    native_alpha = _has_alpha(car)
    if not native_alpha:
        car = _remove_bg_rembg(car_bytes)
        car = _remove_floor_reflection(car)
    car = _remove_disconnected_alpha(car)
    car = _desaturate_soft_pixels(car)
    if not native_alpha:
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

    if native_alpha:
        result = template.copy()
    else:
        car_alpha = np.array(car.split()[-1])
        result = _draw_synthetic_shadow(template.copy(), car_alpha, paste_x, paste_y, sx0, sx1, sy1)
    result.paste(car, (paste_x, paste_y), car)

    buf = io.BytesIO()
    result.convert("RGB").save(buf, format=OUTPUT_FORMAT, quality=OUTPUT_QUALITY, method=OUTPUT_METHOD)
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
    canvas.save(buf, format=OUTPUT_FORMAT, quality=OUTPUT_QUALITY, method=OUTPUT_METHOD)
    return buf.getvalue()


def has_template() -> bool:
    return TEMPLATE_PATH.exists()
