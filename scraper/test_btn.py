"""Testa o botão 'Gerar 4 Imagens' com o modelo por defeito."""
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    print("1. A abrir app...")
    page.goto("http://localhost:8501", wait_until="load", timeout=30000)
    time.sleep(8)

    page.screenshot(path="data/test_before.png", full_page=True)
    print("   Screenshot antes: data/test_before.png")

    print("2. A clicar 'Gerar 4 Imagens'...")
    btn = page.locator("button", has_text="Gerar 4 Imagens").first
    print(f"   Botão visível: {btn.is_visible(timeout=5000)}")
    btn.click()
    print("   Botão clicado")

    print("3. A aguardar imagens (20s)...")
    time.sleep(20)

    page.screenshot(path="data/test_after.png", full_page=True)
    print("   Screenshot depois: data/test_after.png")

    # Verificar se há imagens geradas
    imgs = page.locator("img").all()
    print(f"   Total de imagens na página: {len(imgs)}")

    browser.close()

print("Teste concluído.")
