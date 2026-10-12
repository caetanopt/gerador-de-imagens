"""
Descobre todos os códigos de cor Peugeot válidos testando a API de thumbnails V3D.
Padrão observado: 0MM00N + 3 chars alfanuméricos maiúsculos.
Guarda resultado em data/peugeot_colors.json.
"""
import ssl, urllib.request, json, itertools, concurrent.futures, time
from pathlib import Path

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

DATA_DIR = Path(__file__).parent.parent / "data"
SWATCH_URL = "https://visuel3d-secure.peugeot.com/v3dcentral/Colors/NDP/th_{}.png"
KNOWN_COLORS = {
    "0MM00NEQ": "Amarelo Águeda",
    "0MM00NSU": "Branco Okénite",
    "0MM00NKH": "Azul Lagoa",
    "0MM00N7K": "Azul Ingaro",
    "0MM00NF9": "Verde Flare",
    "0MM00NDP": "Azul Obsession",
    "0MM00NF4": "Cinzento Artense",
    "0MM00NLD": "Cinzento Selenium",
    "0MM00N9V": "Preto Perla Nera",
}

# Chars a testar no sufixo (uppercase letters + digits)
CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def check_color(code):
    url = SWATCH_URL.format(code)
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=5) as r:
            if r.status == 200:
                return code
    except Exception:
        pass
    return None


def discover_colors():
    # Gerar candidatos: 0MM00N + 3 chars
    # Para limitar: primeiro char = letra A-Z ou dígito (36)
    # Segundo char = letra ou dígito (36)
    # Terceiro char = letra ou dígito (36)
    # Total: 36^3 = 46656 — demasiado. Filtrar pelo padrão observado.
    # Observado: segundo char é letra maiúscula ou dígito 7/9
    # Simplificação: testar apenas sufixos de 3 chars com CHARS[:20] para começar

    # Padrão observado: primeiro=N, segundo=letra/dígito, terceiro=letra/dígito
    # Vamos testar N + 2 chars alfanuméricos = 36^2 = 1296 combinações
    candidates = [f"0MM00N{c1}{c2}" for c1 in CHARS for c2 in CHARS]

    print(f"A testar {len(candidates)} candidatos...")
    found = dict(KNOWN_COLORS)  # começa com os conhecidos

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(check_color, code): code for code in candidates}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            done += 1
            result = future.result()
            if result and result not in found:
                found[result] = result  # nome temporário = código
                print(f"  Nova cor: {result}")
            if done % 200 == 0:
                print(f"  Progresso: {done}/{len(candidates)} ({len(found)} cores)")

    return found


if __name__ == "__main__":
    start = time.time()
    colors = discover_colors()
    elapsed = time.time() - start
    print(f"\nCores encontradas: {len(colors)} em {elapsed:.1f}s")
    for code, name in sorted(colors.items()):
        print(f"  {code}: {name}")

    out = DATA_DIR / "peugeot_colors.json"
    DATA_DIR.mkdir(exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(colors, f, ensure_ascii=False, indent=2)
    print(f"\nGuardado em: {out}")
