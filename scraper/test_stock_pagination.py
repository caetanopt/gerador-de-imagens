"""Testa paginação em getDealerStockOffers para obter todas as cores."""
import ssl, urllib.request, json

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
H = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Referer": "https://store.peugeot.pt/stock?channel=b2c",
    "Origin": "https://store.peugeot.pt",
}
GQL = "https://store.peugeot.pt/api/graphql"

def gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(GQL, data=body, headers=H, method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode()[:500]}

OFFER_FIELDS = """
    lcdv16
    nameplateBodyStyleSlug
    exteriorColour { id title }
    model { id title }
"""

args_to_try = [
    "(limit: 500)",
    "(first: 500)",
    "(limit: 500, offset: 0)",
    "(page: 1, limit: 500)",
    "(skip: 0, take: 500)",
    '(filters: {}, limit: 500)',
]

for args in args_to_try:
    q = f"{{ getDealerStockOffers{args} {{ count offers {{ {OFFER_FIELDS} }} }} }}"
    res = gql(q)
    if "error" in res:
        print(f"{args}: ERR {res.get('body', '')[:120]}")
    else:
        data = (res.get("data") or {}).get("getDealerStockOffers") or {}
        count = data.get("count")
        offers = data.get("offers", [])
        print(f"{args}: count={count} loaded={len(offers)}")
        if len(offers) > 8:
            # Agregar cores únicas
            colors = {}
            for o in offers:
                slug = o.get("nameplateBodyStyleSlug", "")
                ext = o.get("exteriorColour") or {}
                cid = ext.get("id", "")
                cname = ext.get("title", "")
                if slug and cid:
                    colors.setdefault(slug, set()).add(f"{cname} ({cid})")
            for slug, cs in sorted(colors.items()):
                print(f"  {slug}: {sorted(cs)}")
