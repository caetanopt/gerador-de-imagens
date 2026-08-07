"""Testa o botão 'Gerar 4 Imagens' na app Streamlit."""
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    print("1. A abrir app...")
    page.goto("http://localhost:8501", wait_until="load", timeout=30000)
    time.sleep(6)

    # Mudar para Golf LIFE (procurar na dropdown de modelo)
    print("2. A seleccionar GOLF LIFE...")
    # Streamlit selectboxes têm classe específica
    try:
        # Clicar na dropdown de Modelo
        model_sel = page.locator("[data-testid='stSelectbox']").first
        model_sel.click()
        time.sleep(1)
        page.screenshot(path="data/test_dropdown_open.png")

        # Procurar opção Golf LIFE
        option = page.locator(f"li:has-text('GOLF — LIFE')").first
        if option.is_visible(timeout=3000):
            option.click()
            print("  Golf LIFE seleccionado")
        else:
            print("  Opção não encontrada, a continuar com modelo actual")
        time.sleep(2)
    except Exception as e:
        print(f"  Erro ao mudar modelo: {e}")

    # Clicar no botão "Gerar 4 Imagens"
    print("3. A clicar 'Gerar 4 Imagens'...")
    try:
        btn = page.locator("button:has-text('Gerar 4 Imagens')").first
        if btn.is_visible(timeout=5000):
            btn.click()
            print("  Botão clicado")
        else:
            print("  Botão não encontrado")
    except Exception as e:
        print(f"  Erro: {e}")

    # Aguardar geração das imagens (pode demorar alguns segundos)
    print("4. A aguardar imagens...")
    time.sleep(15)

    page.screenshot(path="data/test_generated.png", full_page=True)
    print("  Screenshot: data/test_generated.png")

    browser.close()
print("Teste concluído.")
