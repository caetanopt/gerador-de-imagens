"""
Descarrega as imagens de uma configuração Nissan.

Há dois "tipos" de variante no catálogo (ver nissan_catalog.py):
- "legacy" (Qashqai, Juke, Ariya): só existe UMA imagem por combinação
  versão+cor (um único ângulo, 3/4 frente) — não há frente/lado/traseira
  nem interior disponíveis nesta plataforma. As imagens combinadas com
  jantes dão sempre 404 no CDN da Nissan (confirmado em várias
  versões/jantes), por isso a escolha de jantes é apenas informativa e não
  influencia a foto.
- "rich360" (por agora só o Micra): 4 ângulos reais extraídos de uma
  sequência de ~120 fotogramas por cor (ver nissan_catalog.py). Sem
  interior disponível.
"""
import io
import ssl
import urllib.request
import zipfile

_ssl_ctx = ssl.create_default_context()
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as r:
        data = r.read()
    if not data:
        raise ValueError(f"Imagem vazia: {url}")
    return data


def generate_images(kind: str, variant: dict, color_code: str, **_) -> dict[str, bytes]:
    """Gera as imagens Nissan para a configuração dada.

    kind: "legacy" -> variant é a versão (tem imageTemplate); "rich360" ->
    variant é o modelo (tem colors com os 4 ângulos).
    """
    results = {}

    if kind == "legacy":
        url = variant["imageTemplate"].format(COLOR=color_code)
        try:
            results["3_4_frente"] = _fetch(url)
        except Exception as e:
            print(f"  ERRO imagem Nissan (legacy): {e}")
        return results

    # rich360
    color = next((c for c in variant["colors"] if c["code"] == color_code), None)
    if not color:
        return results
    for angle, url in color["images"].items():
        try:
            results[angle] = _fetch(url)
        except Exception as e:
            print(f"  ERRO imagem Nissan (360) {angle}: {e}")
    return results


def images_to_zip(images: dict[str, bytes], zip_name: str = "imagens.zip") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in images.items():
            zf.writestr(f"{label}.png", data)
    return buf.getvalue()
