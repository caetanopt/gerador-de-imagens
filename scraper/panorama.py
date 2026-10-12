"""
Vistas de interior a partir de panoramas 360° equirectangulares.

Várias marcas (Hyundai, XPENG — mesma plataforma "cardb ... internal360")
não têm fotos de interior normais, só um panorama esférico por versão/cor
de interior para um visualizador 360 (Pannellum). Daqui extraem-se vistas
em perspectiva como uma câmara virtual. Muitos panoramas são marcadores
("Brevemente disponível", desfocados) ou ficheiros minúsculos —
descartados por uma medida de arestas na faixa central.
"""
import io

import numpy as np
from PIL import Image

VIEWS = {
    "interior_tablier": (0, -14),            # (yaw, pitch) em graus; pitch < 0 = olhar para baixo
    "interior_bancos_traseiros": (180, -12),
}
FOV = 95
OUT_SIZE = (1920, 1200)
MIN_EDGE_PCT = 1.2


def is_real(pano: Image.Image) -> bool:
    g = np.asarray(pano.convert("L").resize((2048, 1024)), dtype=np.float32)[358:666]
    return float((np.abs(np.diff(g, axis=1)) > 25).mean() * 100) >= MIN_EDGE_PCT


def perspective(pano: Image.Image, yaw: float, pitch: float) -> Image.Image:
    w, h = OUT_SIZE
    src = np.asarray(pano.convert("RGB"))
    ph, pw = src.shape[:2]
    f = 0.5 * w / np.tan(np.radians(FOV) / 2)
    xx, yy = np.meshgrid(np.arange(w) - w / 2, np.arange(h) - h / 2)
    d = np.stack([xx, yy, np.full_like(xx, f)], -1)
    d /= np.linalg.norm(d, axis=-1, keepdims=True)
    cp, sp = np.cos(np.radians(pitch)), np.sin(np.radians(pitch))
    cy, sy = np.cos(np.radians(yaw)), np.sin(np.radians(yaw))
    rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    d = d @ rx.T @ ry.T
    lon = np.arctan2(d[..., 0], d[..., 2])
    lat = np.arcsin(np.clip(d[..., 1], -1, 1))
    u = ((lon / np.pi + 1) / 2 * pw).astype(int) % pw
    v = np.clip(((lat / (np.pi / 2) + 1) / 2 * ph).astype(int), 0, ph - 1)
    return Image.fromarray(src[v, u])


def interior_views(candidate_urls: list[str], fetch) -> dict[str, bytes]:
    """Usa o primeiro panorama real da lista (por ordem de preferência)."""
    for url in candidate_urls[:8]:
        try:
            pano = Image.open(io.BytesIO(fetch(url)))
        except Exception:
            continue
        if not is_real(pano):
            continue
        out = {}
        for label, (yaw, pitch) in VIEWS.items():
            buf = io.BytesIO()
            perspective(pano, yaw, pitch).save(buf, format="JPEG", quality=92)
            out[label] = buf.getvalue()
        return out
    return {}
