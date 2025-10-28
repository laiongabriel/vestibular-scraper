from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import pickle
import os
import time
import re
import base64
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from functools import lru_cache

CONFIG = {
    "email": "laionp98@gmail.com",
    "senha": "00uLisses00!",
    "max_workers": 10,
    "headless": True,
    "timeout": 10,
    "pagina_inicial": 1,
    "pagina_final": 3,
}

PROVA_CONFIG = {
    "nome_prova": "LINGUAGENS, CÓDIGOS E SUAS TECNOLOGIAS - PPL",
    "ano": 2014,
    "arquivo_saida": "enemppl2015_linguagens.json",
    "base_url": "https://app.repertorioenem.com.br/questions/list?search=1&field%5B0%5D=12&field%5B1%5D=23&field%5B2%5D=1&field%5B3%5D=3&field%5B4%5D=2&institution%5B0%5D=2&year%5B0%5D=2014&pages=50&order_by=1&page="
}

# ============ CACHE E OTIMIZAÇÕES ============
@lru_cache(maxsize=1000)
def limpar_html_cached(html):
    """Versão com cache da limpeza de HTML"""
    html = re.sub(r'\s*class="[^"]*"', '', html)
    html = re.sub(r'\s*id="[^"]*"', '', html)
    html = re.sub(r'</?span[^>]*>', '', html)
    html = html.strip()
    
    pattern = r'^<p>\s*(<p>.*</p>)\s*</p>$'
    match = re.match(pattern, html, re.DOTALL)
    if match:
        html = match.group(1)

    if not html.startswith('<p>'):
        html = f"<p>{html}</p>"
    
    return html

def criar_driver():
    """Cria driver com opções otimizadas"""
    chrome_options = Options()
    
    if CONFIG["headless"]:
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--disable-gpu')
    
    # Otimizações de performance
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-logging')
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    # Desabilita imagens para carregar mais rápido (já que vamos baixar depois)
    prefs = {
        'profile.default_content_setting_values': {
            'images': 2  # 2 = bloquear imagens
        }
    }
    chrome_options.add_experimental_option('prefs', prefs)
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    
    # Timeout implícito
    driver.implicitly_wait(5)
    
    return driver

def fazer_login(driver, email, senha):
    """Faz login no site"""
    print("🔐 Fazendo login...")
    driver.get("https://app.repertorioenem.com.br/login")
    
    wait = WebDriverWait(driver, CONFIG["timeout"])
    
    try:
        campo_email = wait.until(EC.presence_of_element_located((By.ID, "inputEmailAddress")))
        campo_email.send_keys(email)
        
        campo_senha = driver.find_element(By.ID, "inputPassword")
        campo_senha.send_keys(senha)
        
        botao_login = driver.find_element(By.CSS_SELECTOR, ".btn.btn-lg.w-100.bg-purple")
        botao_login.click()
        
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "card-body")))
        print("✅ Login realizado com sucesso!")
        return True
    except Exception as e:
        print(f"❌ ERRO: Falha no login! - {e}")
        return False

def salvar_cookies(driver, arquivo="cookies.pkl"):
    """Salva os cookies em um arquivo"""
    pickle.dump(driver.get_cookies(), open(arquivo, "wb"))

def carregar_cookies(driver, arquivo="cookies.pkl"):
    """Carrega cookies de um arquivo"""
    if os.path.exists(arquivo):
        try:
            cookies = pickle.load(open(arquivo, "rb"))
            for cookie in cookies:
                try:
                    driver.add_cookie(cookie)
                except:
                    pass
            return True
        except:
            return False
    return False

def deletar_cookies(arquivo="cookies.pkl"):
    """Deleta o arquivo de cookies"""
    if os.path.exists(arquivo):
        os.remove(arquivo)
        return True
    return False

def verificar_login(driver):
    """Verifica se ainda está logado checando a URL e elementos da página"""
    try:
        driver.get("https://app.repertorioenem.com.br/questions/list")
        time.sleep(2)
        
        if "login" in driver.current_url:
            return False
        
        driver.find_element(By.CLASS_NAME, "card-body")
        print("✅ Sessão válida!")
        return True
    except:
        return False

def baixar_imagem_base64(url_imagem):
    """Baixa UMA imagem e converte para base64 (usada pelo ThreadPool)"""
    try:
        response = requests.get(url_imagem, timeout=CONFIG["timeout"])
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            
            # Determina MIME type
            mime_map = {
                'jpeg': 'image/jpeg', 'jpg': 'image/jpeg',
                'png': 'image/png', 'gif': 'image/gif',
                'webp': 'image/webp'
            }
            
            mime_type = 'image/jpeg'  # padrão
            for ext, mime in mime_map.items():
                if ext in content_type or url_imagem.endswith(f'.{ext}'):
                    mime_type = mime
                    break
            
            img_base64 = base64.b64encode(response.content).decode('utf-8')
            return url_imagem, f"data:{mime_type};base64,{img_base64}"
        else:
            return url_imagem, url_imagem
    except:
        return url_imagem, url_imagem

def converter_imagens_para_base64_paralelo(html):
    """Converte todas as imagens do HTML usando ThreadPoolExecutor"""
    if '<img' not in html.lower():
        return html
    
    pattern = r'<img[^>]*src=["\']([^"\']+)["\'][^>]*>'
    matches = list(re.finditer(pattern, html))
    
    if not matches:
        return html
    
    # Filtra URLs que não são base64
    urls_para_baixar = [m.group(1) for m in matches if not m.group(1).startswith('data:')]
    
    if not urls_para_baixar:
        return html
    
    # Download paralelo com progress bar
    url_to_base64 = {}
    
    with ThreadPoolExecutor(max_workers=CONFIG["max_workers"]) as executor:
        futures = {executor.submit(baixar_imagem_base64, url): url for url in urls_para_baixar}
        
        with tqdm(total=len(urls_para_baixar), desc="      📥 Imagens", 
                  unit="img", leave=False, ncols=80, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}') as pbar:
            for future in as_completed(futures):
                url_original, url_base64 = future.result()
                url_to_base64[url_original] = url_base64
                pbar.update(1)
    
    # Substitui as URLs no HTML
    def substituir_img(match):
        img_tag = match.group(0)
        url_original = match.group(1)
        
        if url_original.startswith('data:'):
            return img_tag
        
        base64_url = url_to_base64.get(url_original, url_original)
        return img_tag.replace(url_original, base64_url)
    
    return re.sub(pattern, substituir_img, html)

def extrair_topicos(elemento_pai):
    """Extrai os tópicos/assuntos da questão (do 3º span em diante)"""
    try:
        div_d_flex = elemento_pai.find_element(By.CSS_SELECTOR, ".d-flex.flex-wrap.text-left")
        spans = div_d_flex.find_elements(By.TAG_NAME, "span")
        
        topicos = [s.text.strip() for s in spans[2:] if s.text.strip()]
        return "; ".join(topicos) if topicos else ""
    except:
        return ""

def extrair_dificuldade(elemento_pai):
    """Extrai a dificuldade da questão"""
    try:
        div_text_end = elemento_pai.find_element(By.CSS_SELECTOR, ".text-end")
        span = div_text_end.find_element(By.TAG_NAME, "span")
        return span.text.strip()
    except:
        return ""

def extrair_texto_limpo(html):
    """Remove tags HTML e retorna texto puro"""
    texto = re.sub(r'<[^>]+>', '', html)
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

def gerar_chave_unica(questao):
    """Gera uma chave única combinando início do enunciado + alternativas"""
    inicio = extrair_texto_limpo(questao['enunciado_txt'])[:30].lower()
    
    alternativas = ""
    for letra in ['a', 'b', 'c', 'd', 'e']:
        alternativas += questao['alternativas'].get(f"alternativa_{letra}_txt", "")
    
    return f"{inicio}|||{alternativas}"

def tem_link_resposta(alternativas_obj):
    """Verifica se alguma alternativa contém o texto de redirecionamento"""
    texto_proibido = "Confira a resposta através do link abaixo:"
    
    for letra in ['a', 'b', 'c', 'd', 'e']:
        conteudo = alternativas_obj.get(f"alternativa_{letra}_txt", "")
        if texto_proibido in conteudo:
            return True
    return False

def processar_questoes(questoes):
    """Remove questões inválidas e duplicadas"""
    print(f"\n🔍 Total inicial: {len(questoes)}")
    
    # Filtrar inválidas
    validas = []
    invalidas = 0
    for q in questoes:
        if tem_link_resposta(q['alternativas']):
            invalidas += 1
        else:
            validas.append(q)
    
    if invalidas > 0:
        print(f"🚫 Removidas {invalidas} questões inválidas")
    
    # Remover duplicadas
    unicas = []
    chaves_vistas = set()
    duplicadas = 0
    
    for q in validas:
        chave = gerar_chave_unica(q)
        if chave not in chaves_vistas:
            chaves_vistas.add(chave)
            unicas.append(q)
        else:
            duplicadas += 1
    
    if duplicadas > 0:
        print(f"⚠️  Removidas {duplicadas} questões duplicadas")
    
    print(f"✅ Total final: {len(unicas)}")
    return unicas

def extrair_questoes(driver, url):
    """Extrai enunciados e alternativas de uma página"""
    driver.get(url)
    time.sleep(2)
    
    if "login" in driver.current_url:
        print("  ❌ ERRO: Não está logado!")
        return []
    
    questoes_json = []
    
    enunciados = driver.find_elements(By.CSS_SELECTOR, ".mb-0.mx-2.ck-content.highlighter-context")
    
    if not enunciados:
        print("  ⚠️  Nenhum enunciado encontrado!")
        return []
    
    # Progress bar para extração de questões
    for enunciado in tqdm(enunciados, desc="  📝 Extraindo", unit="Q", ncols=80, 
                          bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}'):
        try:
            # Enunciado
            enunciado_html = enunciado.get_attribute('innerHTML')
            enunciado_html = converter_imagens_para_base64_paralelo(enunciado_html)
            enunciado_limpo = limpar_html_cached(enunciado_html)
            
            # Elemento pai
            elemento_pai = enunciado.find_element(By.XPATH, "./ancestor::div[contains(@class, 'card')]")
            
            # Metadados
            topicos = extrair_topicos(elemento_pai)
            dificuldade = extrair_dificuldade(elemento_pai)
            
            # Container de alternativas
            container_d_flex = elemento_pai.find_element(By.CSS_SELECTOR, ".d-flex.flex-wrap.justify-content-between")
            
            try:
                div_ms0 = container_d_flex.find_element(By.XPATH, "./following-sibling::div[contains(@class, 'ms-0')]")
            except:
                div_ms0 = container_d_flex.find_element(By.CSS_SELECTOR, ".ms-0")
            
            # Alternativas
            alternativas_container = div_ms0.find_elements(
                By.CSS_SELECTOR, 
                ".d-flex.flex-row.justify-content-start.align-items-center.ms-0.my-3"
            )
            
            alternativas_obj = {}
            letras = ['a', 'b', 'c', 'd', 'e']
            
            for idx, alt_container in enumerate(alternativas_container[:5]):
                try:
                    conteudo_label = alt_container.find_element(By.CSS_SELECTOR, ".form-check-label.ms-3")
                    conteudo = conteudo_label.get_attribute('innerHTML')
                    conteudo = converter_imagens_para_base64_paralelo(conteudo)
                    alternativas_obj[f"alternativa_{letras[idx]}_txt"] = limpar_html_cached(conteudo)
                except:
                    alternativas_obj[f"alternativa_{letras[idx]}_txt"] = ""
            
            # Alternativa correta
            alternativa_correta = ""
            try:
                inputs = div_ms0.find_elements(By.CSS_SELECTOR, "input")
                if inputs:
                    alternativa_correta = f"<p>{inputs[-1].get_attribute('value').upper()}</p>"
            except:
                pass
            
            questao_obj = {
                "assunto": topicos,
                "dificuldade": dificuldade,
                "enunciado_txt": enunciado_limpo.strip(),
                "alternativas": alternativas_obj,
                "alternativa_correta": alternativa_correta
            }
            
            questoes_json.append(questao_obj)
            
        except Exception as e:
            print(f"\n    ⚠️  Erro ao extrair questão: {e}")
    
    return questoes_json

def salvar_json(todas_questoes):
    """Salva todas as questões em um arquivo JSON"""
    dados = {
        "prova": PROVA_CONFIG["nome_prova"],
        "ano": PROVA_CONFIG["ano"],
        "questoes": todas_questoes
    }
    
    arquivo = PROVA_CONFIG["arquivo_saida"]
    
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    
    print(f"\n📁 Arquivo salvo: {arquivo}")
    print(f"📊 Total de questões: {len(todas_questoes)}")

def realizar_login_completo(driver):
    """Gerencia todo o processo de login com cookies e retry"""
    cookies_existem = carregar_cookies(driver)
    login_ok = False
    
    if cookies_existem:
        print("🔍 Verificando cookies salvos...")
        login_ok = verificar_login(driver)
        
        if not login_ok:
            print("🗑️  Cookies inválidos, deletando...")
            deletar_cookies()
    
    if not login_ok:
        # Tenta fazer login até 3 vezes
        for tentativa in range(1, 4):
            if tentativa > 1:
                print(f"\n🔄 Tentativa {tentativa}/3...")
                deletar_cookies()
                driver.delete_all_cookies()
            
            login_ok = fazer_login(driver, CONFIG["email"], CONFIG["senha"])
            
            if login_ok:
                salvar_cookies(driver)
                return True
            
            time.sleep(2)
        
        print("\n❌ ERRO CRÍTICO: Falha no login após múltiplas tentativas!")
        return False
    
    return True

# ============ CÓDIGO PRINCIPAL ============
def main():
    print("=" * 80)
    print(f"🎯 EXTRATOR DE QUESTÕES - {PROVA_CONFIG['nome_prova']} ({PROVA_CONFIG['ano']})")
    print("=" * 80)
    
    driver = criar_driver()
    
    try:
        driver.get("https://app.repertorioenem.com.br")
        time.sleep(1)
        
        # Login
        if not realizar_login_completo(driver):
            return
        
        # Extração
        todas_questoes = []
        base_url = PROVA_CONFIG["base_url"]
        
        print(f"\n📖 Extraindo páginas {CONFIG['pagina_inicial']} até {CONFIG['pagina_final']-1}...\n")
        
        for pagina in range(CONFIG["pagina_inicial"], CONFIG["pagina_final"]):
            print(f"📄 Página {pagina}")
            url = base_url + str(pagina)
            questoes_pagina = extrair_questoes(driver, url)
            todas_questoes.extend(questoes_pagina)
            print(f"   ✅ {len(questoes_pagina)} questões extraídas\n")
        
        # Processamento
        if todas_questoes:
            todas_questoes = processar_questoes(todas_questoes)
            salvar_json(todas_questoes)
            print("\n" + "=" * 80)
            print("✅ EXTRAÇÃO CONCLUÍDA COM SUCESSO!")
            print("=" * 80)
        else:
            print("\n⚠️  NENHUMA QUESTÃO EXTRAÍDA!")
        
    except Exception as e:
        print(f"\n❌ ERRO FATAL: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        driver.quit()

if __name__ == "__main__":
    main()