"""Testa getNscStockOffers para obter todas as cores disponíveis."""
import ssl, urllib.request, json, collections

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

FIELDS = "lcdv16 nameplateBodyStyleSlug exteriorColour { id title } model { title }"

# Testar getNscStockOffers sem e com argumentos
for args in ["", "(limit: 500)", "(first: 200)", "(count: 500)"]:
    q = f"{{ getNscStockOffers{args} {{ count offers {{ {FIELDS} }} }} }}"
    res = gql(q)
    if "error" in res:
        body = res.get("body", "")
        if "Unknown argument" in body:
            print(f"getNscStockOffers{args}: argumento inválido")
        else:
            print(f"getNscStockOffers{args}: ERRO {body[:150]}")
    else:
        data = (res.get("data") or {}).get("getNscStockOffers") or {}
        offers = data.get("offers", [])
        print(f"getNscStockOffers{args}: count={data.get('count')} loaded={len(offers)}")
        if offers:
            by_model = collections.defaultdict(dict)
            for o in offers:
                slug = o.get("nameplateBodyStyleSlug", "")
                ext = o.get("exteriorColour") or {}
                cid = ext.get("id", "")
                cname = ext.get("title", "")
                lcdv = o.get("lcdv16", "")
                if slug and cid and cid not in by_model[slug]:
                    by_model[slug][cid] = {"name": cname, "lcdv16": lcdv}
            for slug, cols in sorted(by_model.items()):
                names = [f"{v['name']} ({k})" for k, v in cols.items()]
                print(f"  {slug}: {names}")
        break
