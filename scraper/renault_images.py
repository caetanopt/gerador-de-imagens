"""
Descarrega imagens de uma configuração Renault (modelo + versão + cor + jantes).

O visualizador 3D da Renault (3dv.renault.com) só devolve imagens para uma
configuração completa (string "visualVCD" + databaseId), que só se obtém
navegando o configurador passo a passo: versão -> cor -> jantes. Cada passo
é um pedido HTTP normal (ver renault_catalog.py) que devolve a próxima
"nextURI" a seguir.

Ângulos disponíveis no conjunto CONFIG_MULTISTATIC (fixo, 6 imagens —
confirmado que não há mais nenhum além destes): 0 = 3/4 frente,
1 = 3/4 traseira, 2 = lado, 3 = jante (detalhe), 4 = interior (tablier),
5 = interior (bancos). Usam-se todos os 6.
Não existe frente/traseira a direito neste visualizador — usam-se os
ângulos 3/4 para "3_4_frente" e "traseira", tal como nas outras marcas.
"""
import io
import re
import ssl
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from scraper.renault_catalog import conf_url, get_configurator

OUTPUT_DIR = Path(__file__).parent.parent / "output"

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*",
    "Referer": "https://www.renault.pt/",
}

# índice do frame devolvido por ImagesFromBookmarkSet -> label da imagem
_FRAME_LABELS = {
    0: "3_4_frente",
    1: "traseira",
    2: "lado",
    3: "jante_detalhe",
    4: "interior",
    5: "interior_bancos",
}


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=30) as r:
        return r.read()


def _find_option(possibles: list[dict], code: str) -> dict | None:
    return next((o for o in possibles if o.get("code") == code), None)


def _navigate(base_configurator_url: str, conf_uri: str, color_code: str, wheel_code: str) -> dict:
    """
    Percorre versão -> cor -> jantes e devolve o dict `scene` final
    (com visualVCD + modelDatabaseId) para a configuração pedida.
    """
    vcfg = get_configurator(conf_url(base_configurator_url, conf_uri))

    if color_code:
        design = vcfg.get("dynamicData", {}).get("design", [])
        colors = next((d for d in design if d.get("code") == "CATCOLORS1"), {})
        color_opt = _find_option(colors.get("possibles", []), color_code)
        if not color_opt or not color_opt.get("nextURI"):
            raise ValueError(f"Cor '{color_code}' não encontrada nas opções desta versão")
        vcfg = get_configurator(conf_url(base_configurator_url, color_opt["nextURI"]))

    if wheel_code:
        design = vcfg.get("dynamicData", {}).get("design", [])
        wheels = next((d for d in design if d.get("code") == "CATWHEELS1"), {})
        wheel_opt = _find_option(wheels.get("possibles", []), wheel_code)
        if not wheel_opt or not wheel_opt.get("nextURI"):
            raise ValueError(f"Jante '{wheel_code}' não encontrada nas opções desta cor")
        vcfg = get_configurator(conf_url(base_configurator_url, wheel_opt["nextURI"]))

    return vcfg["dynamicData"]["scene"]


def _fetch_frame_urls(visual_vcd: str, database_id: str) -> list[str]:
    conf_enc = urllib.parse.quote(visual_vcd, safe="")
    url = (
        "https://3dv.renault.com/ImagesFromBookmarkSet"
        f"?configuration={conf_enc}&profile=1704x960_169_jpg"
        f"&bookmarkSet=CONFIG_MULTISTATIC&decorDeltaAltitude=0.00&databaseId={database_id}"
    )
    body = _http_get(url).decode("utf-8")
    return [u.replace("&amp;", "&") for u in re.findall(r'directUrl="([^"]+)"', body)]


def generate_images(
    configurator_url: str,
    conf_uri: str,
    color_code: str,
    wheel_code: str = "",
    **_,
) -> dict[str, bytes]:
    """
    Gera as imagens para a configuração dada.
    Devolve dict: {label: bytes_da_imagem}
    """
    scene = _navigate(configurator_url, conf_uri, color_code, wheel_code)
    frame_urls = _fetch_frame_urls(scene["visualVCD"], scene["modelDatabaseId"])

    results = {}
    for idx, label in _FRAME_LABELS.items():
        if idx >= len(frame_urls):
            continue
        try:
            results[label] = _http_get(frame_urls[idx])
        except Exception as e:
            print(f"  ERRO {label}: {e}")
    return results


def images_to_zip(images: dict[str, bytes], zip_name: str = "imagens_renault.zip") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in images.items():
            ext = "jpg" if data[:3] == b"\xff\xd8\xff" else "webp"
            zf.writestr(f"{label}.{ext}", data)
    return buf.getvalue()


if __name__ == "__main__":
    import sys
    configurator_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.renault.pt/veiculos-hibridos/captur/configurador.html"
    conf_uri = sys.argv[2] if len(sys.argv) > 2 else "https://pt.co.rplug.renault.com/c/BAEHx/ApcyM"
    color = sys.argv[3] if len(sys.argv) > 3 else "TENNP"
    wheel = sys.argv[4] if len(sys.argv) > 4 else ""

    print(f"A gerar imagens: {configurator_url} | cor={color} | jante={wheel or '(série)'}")
    images = generate_images(configurator_url, conf_uri, color, wheel)
    OUTPUT_DIR.mkdir(exist_ok=True)
    for label, data in images.items():
        path = OUTPUT_DIR / f"renault_{color}_{label}.jpg"
        path.write_bytes(data)
        print(f"  {path.name} ({len(data):,} bytes)")
