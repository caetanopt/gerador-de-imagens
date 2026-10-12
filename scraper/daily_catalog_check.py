"""
Verificação diária de todos os catálogos: reconstrói os 17 a partir da
fonte (configuradores/sites oficiais de cada marca), compara os números
com a versão anterior, e envia um resumo por email aos admins (ver
auth.ADMIN_EMAILS). Pensado para correr numa GitHub Action agendada — ver
.github/workflows/daily-catalog-check.yml.

Cada marca é isolada em try/except: uma falha numa marca (ex.: o site
mudou de estrutura) não impede a verificação das restantes, e fica
destacada no email em vez de simplesmente interromper o script.
"""
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import auth

DATA_DIR = Path(__file__).parent.parent / "data"

# (nome a mostrar, nome do módulo em scraper/, ficheiro json do cache)
BRANDS = [
    ("Volkswagen", "vw_catalog", "vw_catalog.json"),
    ("Audi", "audi_catalog", "audi_catalog.json"),
    ("Škoda", "skoda_catalog", "skoda_catalog.json"),
    ("BMW", "bmw_catalog", "bmw_catalog.json"),
    ("MINI", "mini_catalog", "mini_catalog.json"),
    ("Mercedes-Benz", "mercedes_catalog", "mercedes_catalog.json"),
    ("Renault", "renault_catalog", "renault_catalog.json"),
    ("Dacia", "dacia_catalog", "dacia_catalog.json"),
    ("Alpine", "alpine_catalog", "alpine_catalog.json"),
    ("Opel", "opel_catalog", "opel_catalog.json"),
    ("Peugeot", "peugeot_catalog", "peugeot_catalog.json"),
    ("Zeekr", "zeekr_catalog", "zeekr_catalog.json"),
    ("BYD", "byd_catalog", "byd_catalog.json"),
    ("Hyundai", "hyundai_catalog", "hyundai_catalog.json"),
    ("Geely", "geely_catalog", "geely_catalog.json"),
    ("XPENG", "xpeng_catalog", "xpeng_catalog.json"),
    ("Nissan", "nissan_catalog", "nissan_catalog.json"),
]

_NO_WHEELS = {"peugeot_catalog", "zeekr_catalog", "byd_catalog", "hyundai_catalog"}


def _stats_generic(cat: dict, wheels_applicable: bool) -> dict:
    variants = [v for g in cat["models"] for v in g.get("variants", [])]
    n_colors = sum(len(v.get("colors", [])) for v in variants)
    n_wheels = sum(len(v.get("wheels", [])) for v in variants) if wheels_applicable else 0
    return {"modelos": len(cat["models"]), "versoes": len(variants), "cores": n_colors, "jantes": n_wheels}


def _stats_geely(cat: dict) -> dict:
    return {
        "modelos": len(cat["models"]),
        "versoes": sum(len(m["versions"]) for m in cat["models"]),
        "cores": sum(len(m["colors"]) for m in cat["models"]),
        "jantes": 0,
    }


def _stats_xpeng(cat: dict) -> dict:
    versions = [v for m in cat["models"] for v in m["versions"]]
    return {"modelos": len(cat["models"]), "versoes": len(versions), "cores": sum(len(v["colors"]) for v in versions), "jantes": 0}


def _stats_nissan(cat: dict) -> dict:
    legacy = [m for m in cat["models"] if m["type"] == "legacy"]
    rich = [m for m in cat["models"] if m["type"] == "rich360"]
    versions = [v for m in legacy for g in m["grades"] for v in g["versions"]]
    n_colors = sum(len(v["colors"]) for v in versions) + sum(len(m["colors"]) for m in rich)
    return {"modelos": len(cat["models"]), "versoes": len(versions), "cores": n_colors, "jantes": 0}


_CUSTOM_STATS = {"geely_catalog": _stats_geely, "xpeng_catalog": _stats_xpeng, "nissan_catalog": _stats_nissan}


def compute_stats(module_name: str, json_name: str) -> dict | None:
    path = DATA_DIR / json_name
    if not path.exists():
        return None
    cat = json.loads(path.read_text(encoding="utf-8"))
    if module_name in _CUSTOM_STATS:
        return _CUSTOM_STATS[module_name](cat)
    return _stats_generic(cat, wheels_applicable=module_name not in _NO_WHEELS)


def _rebuild(module, module_name: str) -> None:
    """
    A maioria dos módulos expõe build_catalog(force=True); o Opel e a
    Peugeot (escritos antes desta convenção ficar padronizada) expõem
    antes load_catalog(force_refresh=True) — suporta-se os dois em vez de
    arriscar mexer nesses módulos só para uniformizar o nome.
    """
    if hasattr(module, "build_catalog"):
        module.build_catalog(force=True)
    elif hasattr(module, "load_catalog"):
        module.load_catalog(force_refresh=True)
    else:
        raise AttributeError(f"{module_name} não tem build_catalog nem load_catalog")


def check_all() -> list[dict]:
    results = []
    for label, module_name, json_name in BRANDS:
        print(f"\n=== {label} ===")
        before = compute_stats(module_name, json_name)
        error = None
        try:
            module = __import__(f"scraper.{module_name}", fromlist=["build_catalog", "load_catalog"])
            _rebuild(module, module_name)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            print(f"  ERRO: {error}")
            traceback.print_exc()
        after = compute_stats(module_name, json_name)
        results.append({"label": label, "before": before, "after": after, "error": error})
    return results


def _format_stats_line(before: dict | None, after: dict | None) -> str:
    if after is None:
        return "sem catálogo (falhou antes de gerar qualquer ficheiro)"
    if before is None:
        return f"primeira verificação — modelos={after['modelos']} versões={after['versoes']} cores={after['cores']} jantes={after['jantes']}"

    parts = []
    changed = False
    for key, nome in [("modelos", "modelos"), ("versoes", "versões"), ("cores", "cores"), ("jantes", "jantes")]:
        b, a = before[key], after[key]
        if b == a:
            parts.append(f"{nome}={a}")
        else:
            changed = True
            delta = a - b
            parts.append(f"{nome}={b}→{a} ({'+' if delta > 0 else ''}{delta})")
    prefix = "🔄 " if changed else "   "
    return prefix + " ".join(parts)


def build_report(results: list[dict]) -> tuple[str, bool]:
    """Devolve (corpo do email, houve_alteracoes_ou_erros)."""
    lines = []
    any_error = any(r["error"] for r in results)
    any_change = False

    if any_error:
        lines.append("⚠️ MARCAS COM ERRO NA VERIFICAÇÃO:")
        for r in results:
            if r["error"]:
                lines.append(f"  - {r['label']}: {r['error']}")
        lines.append("")

    lines.append("Resumo por marca:")
    for r in results:
        if r["error"]:
            continue
        line = _format_stats_line(r["before"], r["after"])
        if "🔄" in line:
            any_change = True
        lines.append(f"  {r['label']:15s} {line}")

    if not any_change and not any_error:
        lines.append("\nSem alterações desde a última verificação — tudo igual.")

    lines.append("\n—\nVerificação automática diária · Gerador de Imagens Caetano")
    return "\n".join(lines), (any_change or any_error)


def main():
    results = check_all()
    body, noteworthy = build_report(results)
    print("\n" + body)

    subject = "Verificação diária de catálogos"
    if any(r["error"] for r in results):
        subject = "⚠️ " + subject + " — falhas encontradas"
    elif noteworthy:
        subject = "🔄 " + subject + " — há alterações"

    try:
        sent = auth.send_email(sorted(auth.ADMIN_EMAILS), subject, body)
        print(f"\nEmail enviado: {sent}")
    except Exception as e:
        print(f"\nERRO ao enviar email de resumo: {e}")


if __name__ == "__main__":
    main()
