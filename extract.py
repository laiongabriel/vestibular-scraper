from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pickle
import time
import re
import base64
import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from functools import lru_cache

# =================== CONFIGURAÇÃO ===================
CONFIG = {
    "email": "laionp98@gmail.com",
    "senha": "00uLisses00!",
    "max_workers": 40,
    "headless": True,
    "timeout": 2,
    "page_load_timeout": 10, 
}

PROVAS = [
    {
        "nome_prova": "UFRGS",
        "ano": 2024,
        "arquivo_saida": "ufrgs2024.json",
        "base_url": "https://app.repertorioenem.com.br/questions/list?search=1&institution%5B%5D=152&year%5B%5D=2024&text=&pages=50&order_by=1",
        "total_paginas": 2
    },
    {
        "nome_prova": "UFRGS",
        "ano": 2024,
        "arquivo_saida": "ufrgs2024.json",
        "base_url": "https://app.repertorioenem.com.br/questions/list?search=1&institution%5B%5D=152&year%5B%5D=2024&text=&pages=50&order_by=1",
        "total_paginas": 2
    },
    {
        "nome_prova": "UFRGS",
        "ano": 2024,
        "arquivo_saida": "ufrgs2024.json",
        "base_url": "https://app.repertorioenem.com.br/questions/list?search=1&institution%5B%5D=152&year%5B%5D=2024&text=&pages=50&order_by=1",
        "total_paginas": 2
    },
]

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})

# =================== DRIVER ===================
def criar_driver():
    options = Options()
    if CONFIG["headless"]:
        options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
    
    # Otimizações de performance
    options.add_argument('--disable-images')  # Não carrega imagens via browser
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')
    options.add_argument('--disable-web-security')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disk-cache-size=0')  # Sem cache de disco
    options.add_argument('--disable-application-cache')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Preferências para performance
    prefs = {
        "profile.managed_default_content_settings.images": 2,  # Bloqueia imagens
        "profile.default_content_setting_values.notifications": 2,
        "profile.managed_default_content_settings.stylesheets": 2,  # Sem CSS externo
    }
    options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    # Timeouts otimizados
    driver.set_page_load_timeout(CONFIG["page_load_timeout"])
    driver.implicitly_wait(0.5)  # Reduzido de 1 para 0.5
    
    return driver

def fazer_login(driver, email, senha):
    print("🔐 Fazendo login...")
    driver.get("https://app.repertorioenem.com.br/login")
    
    try:
        wait = WebDriverWait(driver, 10)
        
        email_field = wait.until(EC.presence_of_element_located((By.ID, "inputEmailAddress")))
        email_field.send_keys(email)
        
        driver.find_element(By.ID, "inputPassword").send_keys(senha)
        driver.find_element(By.CSS_SELECTOR, ".btn.btn-lg.w-100.bg-purple").click()
        
        time.sleep(2)  # Reduzido de 3 para 2
        print("✅ Login realizado com sucesso!")
        return True
    except Exception as e:
        print(f"❌ Erro no login: {e}")
        return False

# =================== HTML ===================
@lru_cache(maxsize=2000)  # Aumentado de 1000 para 2000
def limpar_html(html):
    # Regex compilados para performance
    html = re.sub(r'\s*class="[^"]*"', '', html)
    html = re.sub(r'\s*id="[^"]*"', '', html)
    html = re.sub(r'</?span[^>]*>', '', html)
    html = html.strip()
    
    # Remove <p> duplicado
    match = re.match(r'^<p>\s*(<p>.*</p>)\s*</p>$', html, re.DOTALL)
    if match:
        html = match.group(1)
    
    if not html.startswith('<p>'):
        html = f"<p>{html}</p>"
    
    return html

# Regex compilados globalmente para performance
IMG_REGEX = re.compile(r'<img[^>]*src=["\']([^"\']+)["\']')

# =================== IMAGENS ===================
def baixar_imagem_base64(url):
    try:
        r = session.get(url, timeout=CONFIG["timeout"], stream=True)  # stream para eficiência
        if r.status_code == 200:
            mime = 'image/jpeg'
            for ext, m in [('png', 'image/png'), ('gif', 'image/gif'), ('webp', 'image/webp')]:
                if ext in url:
                    mime = m
                    break
            
            content = r.content
            return url, f"data:{mime};base64,{base64.b64encode(content).decode()}"
    except:
        pass
    return url, url

def converter_imagens_para_base64(html):
    if '<img' not in html.lower():
        return html
    
    # Usando regex compilado
    urls = list({m.group(1) for m in IMG_REGEX.finditer(html) 
                 if not m.group(1).startswith('data:')})
    
    if not urls:
        return html
    
    url_to_base64 = {}
    with ThreadPoolExecutor(max_workers=CONFIG["max_workers"]) as executor:
        futures = {executor.submit(baixar_imagem_base64, u): u for u in urls}
        for future in as_completed(futures):
            u, b64 = future.result()
            url_to_base64[u] = b64
    
    def substituir(match):
        url = match.group(1)
        return match.group(0).replace(url, url_to_base64.get(url, url))
    
    return IMG_REGEX.sub(substituir, html)

# =================== EXTRAÇÃO ===================
def extrair_topicos(div):
    spans = div.find_elements(By.CSS_SELECTOR, ".d-flex.flex-wrap.text-left span")
    return "; ".join([s.text.strip() for s in spans[2:] if s.text.strip()])

def extrair_dificuldade(div):
    try:
        span = div.find_element(By.CSS_SELECTOR, ".text-end span")
        return span.text.strip()
    except:
        return ""

def tem_link_resposta(alternativas):
    texto_proibido = "Confira a resposta através do link abaixo:"
    return any(texto_proibido in alternativas.get(f"alternativa_{letra}_txt", "") 
               for letra in ['a', 'b', 'c', 'd', 'e'])

def extrair_questoes(driver, mostrar_progresso=True):
    questoes = []
    
    # Espera otimizada pelo primeiro elemento
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".mb-0.mx-2.ck-content.highlighter-context"))
        )
    except:
        return questoes
    
    enunciados = driver.find_elements(By.CSS_SELECTOR, ".mb-0.mx-2.ck-content.highlighter-context")
    
    iterator = tqdm(enunciados, desc="  📝 Extraindo", unit="Q", ncols=80) if mostrar_progresso else enunciados
    
    for enunciado_elem in iterator:
        try:
            # Enunciado
            enunciado_html = enunciado_elem.get_attribute('innerHTML')
            enunciado_com_imgs = converter_imagens_para_base64(enunciado_html)
            enunciado_limpo = limpar_html(enunciado_com_imgs)
            
            # Card pai
            pai = enunciado_elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'card')]")
            topicos = extrair_topicos(pai)
            dificuldade = extrair_dificuldade(pai)
            
            # Alternativas
            alternativas = {}
            letras = ['a', 'b', 'c', 'd', 'e']
            alt_containers = pai.find_elements(By.CSS_SELECTOR, 
                ".d-flex.flex-row.justify-content-start.align-items-center.ms-0.my-3")[:5]
            
            for idx, container in enumerate(alt_containers):
                try:
                    label = container.find_element(By.CSS_SELECTOR, ".form-check-label.ms-3")
                    html = label.get_attribute('innerHTML')
                    html_com_imgs = converter_imagens_para_base64(html)
                    alternativas[f"alternativa_{letras[idx]}_txt"] = limpar_html(html_com_imgs)
                except:
                    alternativas[f"alternativa_{letras[idx]}_txt"] = ""
            
            # Resposta correta
            alternativa_correta = ""
            inputs = pai.find_elements(By.CSS_SELECTOR, ".ms-0 input")
            if inputs:
                alternativa_correta = f"<p>{inputs[-1].get_attribute('value').upper()}</p>"
            
            # Adiciona se válida
            if not tem_link_resposta(alternativas):
                questoes.append({
                    "assunto": topicos,
                    "dificuldade": dificuldade,
                    "enunciado_txt": enunciado_limpo.strip(),
                    "alternativas": alternativas,
                    "alternativa_correta": alternativa_correta
                })
        except:
            continue
    
    return questoes

# =================== PROCESSAMENTO ===================
# Regex compilados
HTML_TAG_REGEX = re.compile(r'<[^>]+>')
WHITESPACE_REGEX = re.compile(r'\s+')

def extrair_texto_limpo(html):
    texto = HTML_TAG_REGEX.sub('', html)
    return WHITESPACE_REGEX.sub(' ', texto).strip()

def gerar_chave_unica(questao):
    inicio = extrair_texto_limpo(questao['enunciado_txt'])[:30].lower()
    alternativas = "".join(questao['alternativas'].get(f"alternativa_{l}_txt", "") 
                          for l in ['a', 'b', 'c', 'd', 'e'])
    return f"{inicio}|||{alternativas}"

def remover_duplicatas(questoes):
    unicas = []
    chaves_vistas = set()
    
    for questao in questoes:
        chave = gerar_chave_unica(questao)
        if chave not in chaves_vistas:
            chaves_vistas.add(chave)
            unicas.append(questao)
    
    return unicas

# =================== SALVAMENTO ===================
def salvar_json(prova_config, questoes):
    dados = {
        "prova": prova_config["nome_prova"],
        "ano": prova_config["ano"],
        "total_questoes": len(questoes),
        "questoes": questoes
    }
    
    with open(prova_config["arquivo_saida"], "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    
    return prova_config["arquivo_saida"]

# =================== EXTRAÇÃO COMPLETA ===================
def extrair_prova(driver, prova_config):
    nome = prova_config["nome_prova"]
    ano = prova_config["ano"]
    total_paginas = prova_config["total_paginas"]
    
    print(f"\n{'='*80}")
    print(f"🎯 {nome} - {ano}")
    print(f"{'='*80}")
    
    todas_questoes = []
    
    for pagina in range(1, total_paginas + 1):
        print(f"\n📄 Página {pagina}/{total_paginas}")
        url = f"{prova_config['base_url']}&page={pagina}"
        driver.get(url)
        time.sleep(1)  # Reduzido de 2 para 1
        
        questoes_pagina = extrair_questoes(driver)
        print(f"   ✅ {len(questoes_pagina)} questões extraídas")
        todas_questoes.extend(questoes_pagina)
    
    if todas_questoes:
        print(f"\n🔍 Processando questões...")
        print(f"   Total inicial: {len(todas_questoes)}")
        
        todas_questoes = remover_duplicatas(todas_questoes)
        print(f"   Total final (sem duplicatas): {len(todas_questoes)}")
        
        arquivo = salvar_json(prova_config, todas_questoes)
        print(f"   💾 Salvo em: {arquivo}")
        
        return {
            "prova": nome,
            "ano": ano,
            "total": len(todas_questoes)
        }
    
    return None

# =================== RELATÓRIO ===================
def gerar_relatorio(provas_extraidas):
    print("\n" + "="*80)
    print("📊 RELATÓRIO FINAL")
    print("="*80)
    
    total_questoes = 0
    provas_por_vestibular = {}
    
    for prova in provas_extraidas:
        nome = prova["prova"]
        total = prova["total"]
        total_questoes += total
        
        if nome not in provas_por_vestibular:
            provas_por_vestibular[nome] = {"anos": [], "questoes": 0}
        
        provas_por_vestibular[nome]["anos"].append(prova["ano"])
        provas_por_vestibular[nome]["questoes"] += total
    
    print(f"\n✅ Total de provas extraídas: {len(provas_extraidas)}")
    print(f"✅ Total de questões: {total_questoes}")
    print(f"\n📋 Detalhamento por vestibular:")
    
    for nome, info in provas_por_vestibular.items():
        anos_str = ", ".join(map(str, sorted(info["anos"])))
        print(f"   • {nome}: {len(info['anos'])} anos ({anos_str}) - {info['questoes']} questões")

# =================== MAIN ===================
def main():
    print("="*80)
    print("🚀 EXTRATOR AUTOMATIZADO DE MÚLTIPLAS PROVAS")
    print("="*80)
    
    print(f"\n📋 Serão extraídas {len(PROVAS)} provas:")
    for prova in PROVAS:
        print(f"   • {prova['nome_prova']} {prova['ano']} - {prova['total_paginas']} páginas")
    
    print("\n")
    driver = criar_driver()
    provas_extraidas = []
    
    try:
        # Login
        driver.get("https://app.repertorioenem.com.br")
        time.sleep(0.5)  # Reduzido de 1 para 0.5
        if not fazer_login(driver, CONFIG["email"], CONFIG["senha"]):
            return
        pickle.dump(driver.get_cookies(), open("cookies.pkl", "wb"))
        
        # Extração
        for prova_config in PROVAS:
            try:
                resultado = extrair_prova(driver, prova_config)
                if resultado:
                    provas_extraidas.append(resultado)
            except Exception as e:
                print(f"❌ Erro ao extrair {prova_config['nome_prova']} {prova_config['ano']}: {e}")
                continue
        
        # Resultado
        if provas_extraidas:
            gerar_relatorio(provas_extraidas)
            print("\n✅ EXTRAÇÃO CONCLUÍDA COM SUCESSO!")
        else:
            print("\n⚠️  Nenhuma questão foi extraída.")
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Extração interrompida pelo usuário!")
        if provas_extraidas:
            gerar_relatorio(provas_extraidas)
    finally:
        driver.quit()
        session.close()  # Fecha a sessão de requests

if __name__ == "__main__":
    main()