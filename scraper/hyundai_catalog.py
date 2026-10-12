"""
Extrai o catálogo Hyundai Portugal: modelos, versões e cores.
Usa a API REST simples (sem autenticação) do configurador WordPress
hyundai.pt/configurador/ — endpoints wp-json/cfg/{lstModels,lstVersions,extColors}.

Cada cor de cada versão já vem com um array de 36 (ou 72) imagens de
uma volta de 360°; em vez de guardar o array inteiro (o que tornaria o
catálogo enorme), calculamos aqui os 4 ângulos que interessam por
fracção da volta completa (0%, ~22%, ~47%, ~92% — confirmados
visualmente: 3/4 frente, lado, traseira, frente) e guardamos só esses
4 URLs por cor.

Não há selector de jantes separado nesta ferramenta — a jante está
associada à versão/acabamento, tal como na BYD/Zeekr.

Cache em data/hyundai_catalog.json.
"""
import json
import re
import ssl
import urllib.request
from pathlib import Path

from scraper.cardb_interiors import interiors_by_version

BASE = "https://www.hyundai.pt/wp-json/cfg"
REFERER = "https://www.hyundai.pt/"
DATA_FILE = Path(__file__).parent.parent / "data" / "hyundai_catalog.json"

_ssl_ctx = ssl.create_default_context()

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": REFERER,
}

# fracções da volta de 360° (36 frames de referência: 1=3/4 frente,
# 9=lado, 18=traseira, 34=frente — confirmadas visualmente; "extra_N" são
# fotogramas adicionais espaçados uniformemente pelo resto da volta, sem
# nome semântico confirmado visualmente — os nomes de ângulo mudam de
# significado se a cor tiver 72 frames em vez de 36, por isso usam-se
# fracções, não índices fixos.)
_FRAME_FRACTIONS = {
    "3_4_frente": 0 / 36,
    "lado": 8 / 36,
    "traseira": 17 / 36,
    "frente": 33 / 36,
    "extra_1": 4 / 36,
    "extra_2": 13 / 36,
    "extra_3": 22 / 36,
    "extra_4": 27 / 36,
}

_MY_SUFFIX_RE = re.compile(r"\s*MY\d{2}\s*$", re.IGNORECASE)


def _get(url: str) -> dict | list:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        return json.loads(r.read())


def _url_is_valid_webp(url: str) -> bool:
    """
    Confirma com um HEAD que o URL é mesmo uma imagem webp real — a API
    da Hyundai tem uma taxa de erro relevante (arrays de 360º com
    entradas 404, ficheiros vazios ou URLs de outro tipo misturados),
    detectada só ao testar cada ficheiro individualmente.
    """
    try:
        req = urllib.request.Request(url, method="HEAD", headers=_HEADERS)
        with urllib.request.urlopen(req, context=_ssl_ctx, timeout=15) as r:
            if r.status != 200:
                return False
            if "webp" not in r.headers.get("Content-Type", "").lower():
                return False
            return int(r.headers.get("Content-Length", "0")) > 1000
    except Exception:
        return False


# abaixo disto o arredondamento das fracções pode fazer coincidir dois
# ângulos no mesmo frame (ex. "frente" e "3/4 frente" a apontar para a
# mesma imagem) — a API tem muitas cores com conjuntos de 360º
# incompletos ou vazios, por isso é preciso um mínimo de qualidade.
_MIN_FRAMES = 30


def _parse_360(raw) -> list[str]:
    if isinstance(raw, list):
        return [u for u in raw if u]
    try:
        import ast
        return [u for u in ast.literal_eval(raw or "[]") if u]
    except (ValueError, SyntaxError):
        return []


def _pick_frames(images_360: list[str]) -> dict[str, str]:
    n = len(images_360)
    if n < _MIN_FRAMES:
        return {}
    return {label: images_360[round(frac * n) % n] for label, frac in _FRAME_FRACTIONS.items()}


def _normalize_designation(designation: str) -> str:
    return _MY_SUFFIX_RE.sub("", designation).strip()


def _dedupe_versions(versions: list[dict]) -> list[dict]:
    """
    Mantém só a versão mais recente ('generation' mais alta) por
    designação normalizada — a API devolve o mesmo acabamento repetido
    por cada ano-modelo (MY26/MY27) ainda dentro da janela de vigência.
    """
    best: dict[str, dict] = {}
    for v in versions:
        key = _normalize_designation(v["designation"])
        current = best.get(key)
        if current is None or v.get("generation", 0) > current.get("generation", 0):
            best[key] = v
    return list(best.values())


def paint_swatch_color(image_url: str) -> str | None:
    """
    Para cores sem miniatura na API (colorchip vazio — o ficheiro não existe
    no servidor), deriva a cor da própria foto de lado: amostra da pintura
    na zona das portas (faixa a meia altura), ignorando reflexos extremos.
    """
    import io
    import numpy as np
    from PIL import Image

    try:
        req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0", "Referer": REFERER})
        with urllib.request.urlopen(req, timeout=25) as r:
            a = np.asarray(Image.open(io.BytesIO(r.read())).convert("RGBA"))
    except Exception:
        return None
    ys, xs = np.where(a[:, :, 3] > 250)
    if len(xs) == 0:
        return None
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    band = a[int(y0 + (y1 - y0) * 0.55):int(y0 + (y1 - y0) * 0.70), int(x0 + (x1 - x0) * 0.3):int(x0 + (x1 - x0) * 0.7)]
    px = band[band[:, :, 3] > 250][:, :3].astype(float)
    if len(px) == 0:
        return None
    lum = px.mean(axis=1)
    px = px[(lum > np.percentile(lum, 20)) & (lum < np.percentile(lum, 80))]
    r, g, b = np.percentile(px, 65, axis=0).astype(int)
    return f"rgb({r}, {g}, {b})"


def build_catalog(force: bool = False) -> dict:
    """Constrói e guarda o catálogo Hyundai. Usa cache se existir."""
    if not force and DATA_FILE.exists():
        print(f"Catálogo em cache: {DATA_FILE}")
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)

    print("A construir catálogo Hyundai...")
    DATA_FILE.parent.mkdir(exist_ok=True)

    models = _get(f"{BASE}/lstModels/")
    catalog = {"models": []}

    for m in models:
        model_id = m["id"]
        model_name = m["model"]
        print(f"\n  {model_name} ({model_id})")

        try:
            versions = _get(f"{BASE}/lstVersions/{model_id}")
        except Exception as e:
            print(f"    ERRO ao buscar versões: {e}")
            continue
        versions = _dedupe_versions(versions)

        try:
            colors_data = _get(f"{BASE}/extColors/{model_id}")
        except Exception as e:
            print(f"    ERRO ao buscar cores: {e}")
            continue
        colors_by_version: dict[int, list[dict]] = {}
        for c in colors_data.get("colors", []):
            colors_by_version.setdefault(c["version"], []).append(c)

        try:
            interiors_by_vid = interiors_by_version(_get(f"{BASE}/panomaricLI/{model_id}"), version_key="version")
        except Exception as e:
            print(f"    ERRO ao buscar cores de interior: {e}")
            interiors_by_vid = {}

        group_entry = {"groupCode": str(model_id), "groupName": model_name, "variants": []}

        for v in versions:
            vid = v["id"]
            vcolors = colors_by_version.get(vid, [])
            print(f"    {v['designation']} ({vid}) — {len(vcolors)} cores")
            if not vcolors:
                continue

            colors_out = []
            for c in vcolors:
                frames = _pick_frames(c.get("externalColorImages360", []))
                # nº de frames "válido" (>= _MIN_FRAMES) não garante frames
                # distintos — por vezes o array vem com o mesmo URL repetido
                # (dados de origem da Hyundai, ex.: IONIQ 6 Vanguard MY26).
                # Em vez de perder a versão, fica-se com as imagens distintas
                # que existirem (mesmo que seja só uma).
                if len(set(frames.values())) < 4:
                    distinct = []
                    for u in _parse_360(c.get("externalColorImages360", [])):
                        if u not in distinct:
                            distinct.append(u)
                    frames = {f"exterior_{i + 1}": u for i, u in enumerate(distinct[:8])}
                    if not frames:
                        continue
                if not all(_url_is_valid_webp(u) for u in frames.values()):
                    continue
                colors_out.append({
                    "code": str(c["id"]),
                    "name": c["designation"],
                    "price": c["price"] if c.get("isPaid") else 0,
                    "swatchUrl": c.get("colorchip") or "",
                    "swatchColor": None if c.get("colorchip") else paint_swatch_color(frames.get("lado", "")),
                    "images": frames,
                })

            if not colors_out:
                continue

            variant_entry = {
                "modelCode": str(vid),
                "variantName": _normalize_designation(v["designation"]),
                "name": f"{model_name} {_normalize_designation(v['designation'])}",
                "price": v.get("price", 0),
                "colors": colors_out,
                "interiors": interiors_by_vid.get(str(vid), []),
            }
            group_entry["variants"].append(variant_entry)

        if group_entry["variants"]:
            catalog["models"].append(group_entry)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"\nCatálogo guardado: {DATA_FILE}")
    return catalog


def load_catalog() -> dict:
    """Devolve o catálogo do cache. Constrói se não existir."""
    return build_catalog(force=False)


if __name__ == "__main__":
    catalog = build_catalog(force=True)
    total_variants = sum(len(g["variants"]) for g in catalog["models"])
    total_colors = sum(len(v["colors"]) for g in catalog["models"] for v in g["variants"])
    print(f"\nTotal: {len(catalog['models'])} modelos, {total_variants} versões, {total_colors} combinações de cor")
