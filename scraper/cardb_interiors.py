"""
Cores de interior na plataforma "cardb" (mesmo fornecedor por trás dos
configuradores BYD, XPENG e Hyundai em Portugal — imagens em
cardb.<marca>.pt/files/bdproduto_*/...).

Cada cor de interior vem por versão com nome, preço, miniatura
(colorchip/colorChip), um panorama 360° opcional (panoramImg), a lista
de cores exteriores com que é compatível (parentsColors, string JSON) e,
nalgumas marcas, uma galeria de fotos por cor de interior.
"""
import json


def _parents(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        return [str(x) for x in json.loads(raw or "[]")]
    except (TypeError, ValueError):
        return []


def interiors_by_version(interior_entries: list[dict], version_key: str = "idvc") -> dict[str, list[dict]]:
    """
    -> {id da versão: [{"code", "name", "price", "swatchUrl", "panorama",
    "images", "parents"}]}, pela ordem da API (a 1.ª é a de série).
    """
    gallery: dict[tuple[str, str], list[str]] = {}
    for entry in interior_entries or []:
        for g in entry.get("gallery", []):
            for item in g.get("lst", []):
                key = (str(g.get("idvc")), str(item.get("idColor")))
                if item.get("image") and item["image"] not in gallery.setdefault(key, []):
                    gallery[key].append(item["image"])

    out: dict[str, list[dict]] = {}
    for entry in interior_entries or []:
        for c in entry.get("colors", []):
            vid = str(c.get(version_key) or c.get("idvc") or c.get("version"))
            code = str(c.get("idColor"))
            lst = out.setdefault(vid, [])
            if any(i["code"] == code for i in lst):
                continue
            try:
                price = float(c.get("price") or 0)
            except (TypeError, ValueError):
                price = 0
            lst.append({
                "code": code,
                "name": c.get("designation") or code,
                "price": price,
                "swatchUrl": c.get("colorchip") or c.get("colorChip") or "",
                "panorama": c.get("panoramImg") or "",
                "images": gallery.get((vid, code), []),
                "parents": _parents(c.get("parentsColors")),
            })
    return out


def for_exterior(interiors: list[dict], exterior_id: str | None) -> list[dict]:
    """Só as cores de interior compatíveis com a cor exterior escolhida
    (se a API não indicar compatibilidades, devolve todas)."""
    if not exterior_id:
        return interiors
    ok = [i for i in interiors if not i.get("parents") or str(exterior_id) in i["parents"]]
    return ok or interiors
