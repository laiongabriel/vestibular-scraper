from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import pickle, os, time, re, base64, json, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from functools import lru_cache
from datetime import datetime

CONFIG = {
    "email": "laionp98@gmail.com",
    "senha": "00uLisses00!",
    "max_workers": 20,
    "headless": True,
    "timeout": 10,
}

# =================== CONFIGURAÇÃO DE MÚLTIPLAS PROVAS ===================
# Configure cada prova com: nome, ano, URL (sem o &page= no final) e total de páginas
PROVAS = [
    {
        "nome_prova": "UFRGS",
        "ano": 2015,
        "arquivo_saida": "ufrgs2015.json",
        "base_url": "https://app.repertorioenem.com.br/questions/list?search=1&institution%5B0%5D=21&year%5B0%5D=2015&pages=50&order_by=1",
        "total_paginas": 5
    },
    {
        "nome_prova": "UFRGS",
        "ano": 2016,
        "arquivo_saida": "ufrgs2016.json",
        "base_url": "https://app.repertorioenem.com.br/questions/list?search=1&institution%5B0%5D=21&year%5B0%5D=2016&pages=50&order_by=1",
        "total_paginas": 5
    },
    {
        "nome_prova": "FUVEST",
        "ano": 2015,
        "arquivo_saida": "fuvest2015.json",
        "base_url": "https://app.repertorioenem.com.br/questions/list?search=1&institution%5B0%5D=10&year%5B0%5D=2015&pages=50&order_by=1",
        "total_paginas": 8
    },
    # Adicione mais provas aqui
    # Basta copiar a URL do site (sem o &page= no final)
]

# Configuração de saída
OUTPUT_CONFIG = {
    "salvar_consolidado": True,  # Salva um JSON com todas as provas
    "arquivo_consolidado": "todas_provas_{timestamp}.json"
}

@lru_cache(maxsize=1000)
def limpar_html_cached(html):
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

# ================= DRIVER / LOGIN =================
def criar_driver():
    chrome_options = Options()
    if CONFIG["headless"]:
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.implicitly_wait(1)
    return driver

def fazer_login(driver, email, senha):
    print("🔐 Fazendo login...")
    driver.get("https://app.repertorioenem.com.br/login")
    try:
        driver.find_element(By.ID, "inputEmailAddress").send_keys(email)
        driver.find_element(By.ID, "inputPassword").send_keys(senha)
        driver.find_element(By.CSS_SELECTOR, ".btn.btn-lg.w-100.bg-purple").click()
        time.sleep(3)
        print("✅ Login realizado com sucesso!")
        return True
    except Exception as e:
        print(f"❌ Erro no login: {e}")
        return False

def salvar_cookies(driver):
    pickle.dump(driver.get_cookies(), open("cookies.pkl", "wb"))

def carregar_cookies():
    if os.path.exists("cookies.pkl"):
        return pickle.load(open("cookies.pkl", "rb"))
    return []

# ================= IMAGENS =================
def baixar_imagem_base64(url):
    try:
        r = requests.get(url, timeout=CONFIG["timeout"])
        if r.status_code == 200:
            mime = 'image/jpeg'
            for ext, m in {'jpeg':'image/jpeg','jpg':'image/jpeg','png':'image/png','gif':'image/gif','webp':'image/webp'}.items():
                if ext in url:
                    mime = m
            return url, f"data:{mime};base64,{base64.b64encode(r.content).decode()}"
    except:
        pass
    return url, url

def converter_imagens_para_base64_paralelo(html):
    if '<img' not in html.lower(): return html
    urls = list({m.group(1) for m in re.finditer(r'<img[^>]*src=["\']([^"\']+)["\']', html) if not m.group(1).startswith('data:')})
    if not urls: return html
    url_to_base64 = {}
    with ThreadPoolExecutor(max_workers=CONFIG["max_workers"]) as executor:
        futures = {executor.submit(baixar_imagem_base64, u): u for u in urls}
        for future in as_completed(futures):
            u, b64 = future.result()
            url_to_base64[u] = b64
    def sub(m): return m.group(0).replace(m.group(1), url_to_base64.get(m.group(1), m.group(1)))
    return re.sub(r'<img[^>]*src=["\']([^"\']+)["\']', sub, html)

# ================= EXTRAÇÃO =================
def extrair_topicos(div):
    spans = div.find_elements(By.CSS_SELECTOR, ".d-flex.flex-wrap.text-left span")
    return "; ".join([s.text.strip() for s in spans[2:] if s.text.strip()])

def extrair_dificuldade(div):
    try:
        span = div.find_element(By.CSS_SELECTOR, ".text-end span")
        return span.text.strip()
    except: return ""

def tem_link_resposta(alternativas_obj):
    proibido = "Confira a resposta através do link abaixo:"
    return any(proibido in alternativas_obj.get(f"alternativa_{l}_txt","") for l in ['a','b','c','d','e'])

def extrair_questoes(driver, mostrar_progresso=True):
    questoes = []
    enunciados = driver.find_elements(By.CSS_SELECTOR, ".mb-0.mx-2.ck-content.highlighter-context")
    
    iterator = tqdm(enunciados, desc="  📝 Extraindo", unit="Q", ncols=80) if mostrar_progresso else enunciados
    
    for e in iterator:
        try:
            enunciado_html = converter_imagens_para_base64_paralelo(e.get_attribute('innerHTML'))
            enunciado_limpo = limpar_html_cached(enunciado_html)
            pai = e.find_element(By.XPATH, "./ancestor::div[contains(@class, 'card')]")
            topicos = extrair_topicos(pai)
            dificuldade = extrair_dificuldade(pai)
            alternativas_obj = {}
            letras = ['a','b','c','d','e']
            alt_containers = pai.find_elements(By.CSS_SELECTOR, ".d-flex.flex-row.justify-content-start.align-items-center.ms-0.my-3")[:5]
            for idx, a in enumerate(alt_containers):
                try:
                    conteudo_html = converter_imagens_para_base64_paralelo(a.find_element(By.CSS_SELECTOR, ".form-check-label.ms-3").get_attribute('innerHTML'))
                    alternativas_obj[f"alternativa_{letras[idx]}_txt"] = limpar_html_cached(conteudo_html)
                except: alternativas_obj[f"alternativa_{letras[idx]}_txt"] = ""
            alternativa_correta = ""
            inputs = pai.find_elements(By.CSS_SELECTOR, ".ms-0 input")
            if inputs: alternativa_correta = f"<p>{inputs[-1].get_attribute('value').upper()}</p>"
            if not tem_link_resposta(alternativas_obj):
                questoes.append({
                    "assunto": topicos,
                    "dificuldade": dificuldade,
                    "enunciado_txt": enunciado_limpo.strip(),
                    "alternativas": alternativas_obj,
                    "alternativa_correta": alternativa_correta
                })
        except:
            continue
    return questoes

# ================= PROCESSAMENTO =================
def extrair_texto_limpo(html):
    t = re.sub(r'<[^>]+>','',html)
    return re.sub(r'\s+',' ',t).strip()

def gerar_chave_unica(q):
    inicio = extrair_texto_limpo(q['enunciado_txt'])[:30].lower()
    alt = "".join(q['alternativas'].get(f"alternativa_{l}_txt","") for l in ['a','b','c','d','e'])
    return f"{inicio}|||{alt}"

def processar_questoes(questoes):
    unicas = []
    chaves_vistas = set()
    for q in questoes:
        chave = gerar_chave_unica(q)
        if chave not in chaves_vistas:
            chaves_vistas.add(chave)
            unicas.append(q)
    return unicas

def criar_pasta_saida():
    pasta = OUTPUT_CONFIG["pasta_saida"]
    if not os.path.exists(pasta):
        os.makedirs(pasta)
    return pasta

def gerar_url_prova(url_base, pagina):
    """Gera a URL completa adicionando &page= no final"""
    return f"{url_base}&page={pagina}"

def salvar_json_individual(prova_config, questoes):
    pasta = criar_pasta_saida()
    nome_arquivo = prova_config["arquivo_saida"]
    caminho = os.path.join(pasta, nome_arquivo)
    
    dados = {
        "prova": prova_config["nome_prova"],
        "ano": prova_config["ano"],
        "total_questoes": len(questoes),
        "data_extracao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "questoes": questoes
    }
    
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    
    return caminho

def extrair_prova_completa(driver, prova_config):
    """Extrai todas as páginas de uma prova específica"""
    nome = prova_config["nome_prova"]
    ano = prova_config["ano"]
    url_base = prova_config["base_url"]
    total_paginas = prova_config["total_paginas"]
    
    print(f"\n{'='*80}")
    print(f"🎯 {nome} - {ano}")
    print(f"{'='*80}")
    
    todas_questoes = []
    
    for pagina in range(1, total_paginas + 1):
        print(f"\n📄 Página {pagina}/{total_paginas}")
        url = gerar_url_prova(url_base, pagina)
        driver.get(url)
        time.sleep(2)
        
        questoes_pagina = extrair_questoes(driver)
        print(f"   ✅ {len(questoes_pagina)} questões extraídas")
        todas_questoes.extend(questoes_pagina)
    
    if todas_questoes:
        print(f"\n🔍 Processando questões...")
        print(f"   Total inicial: {len(todas_questoes)}")
        todas_questoes = processar_questoes(todas_questoes)
        print(f"   Total final (sem duplicatas): {len(todas_questoes)}")
        
        caminho = salvar_json_individual(prova_config, todas_questoes)
        print(f"   💾 Salvo em: {caminho}")
        
        return {
            "prova": nome,
            "ano": ano,
            "questoes": todas_questoes,
            "total": len(todas_questoes)
        }
    
    return None

def salvar_consolidado(todas_provas_extraidas):
    """Salva um único JSON com todas as provas extraídas"""
    if not OUTPUT_CONFIG["salvar_consolidado"]:
        return
    
    pasta = criar_pasta_saida()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_arquivo = OUTPUT_CONFIG["arquivo_consolidado"].format(timestamp=timestamp)
    caminho = os.path.join(pasta, nome_arquivo)
    
    dados = {
        "data_extracao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_provas": len(todas_provas_extraidas),
        "total_questoes": sum(p["total"] for p in todas_provas_extraidas),
        "provas": todas_provas_extraidas
    }
    
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    
    print(f"\n📦 Arquivo consolidado salvo: {caminho}")

def gerar_relatorio_final(todas_provas_extraidas):
    """Gera um relatório resumido da extração"""
    print("\n" + "="*80)
    print("📊 RELATÓRIO FINAL")
    print("="*80)
    
    total_questoes = 0
    provas_por_vestibular = {}
    
    for prova in todas_provas_extraidas:
        nome = prova["prova"]
        total = prova["total"]
        total_questoes += total
        
        if nome not in provas_por_vestibular:
            provas_por_vestibular[nome] = {"anos": [], "questoes": 0}
        
        provas_por_vestibular[nome]["anos"].append(prova["ano"])
        provas_por_vestibular[nome]["questoes"] += total
    
    print(f"\n✅ Total de provas extraídas: {len(todas_provas_extraidas)}")
    print(f"✅ Total de questões: {total_questoes}")
    print(f"\n📋 Detalhamento por vestibular:")
    
    for nome, info in provas_por_vestibular.items():
        anos_str = ", ".join(map(str, sorted(info["anos"])))
        print(f"   • {nome}: {len(info['anos'])} anos ({anos_str}) - {info['questoes']} questões")

# ================= MAIN =================
def main():
    print("="*80)
    print("🚀 EXTRATOR AUTOMATIZADO DE MÚLTIPLAS PROVAS")
    print("="*80)
    
    # Resumo do que será extraído
    print(f"\n📋 Serão extraídas {len(PROVAS)} provas:")
    for prova in PROVAS:
        print(f"   • {prova['nome_prova']} {prova['ano']} - {prova['total_paginas']} páginas")
    
    input("\n⏸️  Pressione ENTER para iniciar a extração...")
    
    driver = criar_driver()
    todas_provas_extraidas = []
    
    try:
        # Login único
        driver.get("https://app.repertorioenem.com.br")
        time.sleep(1)
        if not fazer_login(driver, CONFIG["email"], CONFIG["senha"]):
            return
        salvar_cookies(driver)
        
        # Extrair todas as provas
        for prova_config in PROVAS:
            try:
                resultado = extrair_prova_completa(driver, prova_config)
                if resultado:
                    todas_provas_extraidas.append(resultado)
            except Exception as e:
                print(f"❌ Erro ao extrair {prova_config['nome_prova']} {prova_config['ano']}: {e}")
                continue
        
        # Salvar consolidado
        if todas_provas_extraidas:
            salvar_consolidado(todas_provas_extraidas)
            gerar_relatorio_final(todas_provas_extraidas)
            print("\n✅ EXTRAÇÃO CONCLUÍDA COM SUCESSO!")
        else:
            print("\n⚠️  Nenhuma questão foi extraída.")
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Extração interrompida pelo usuário!")
        if todas_provas_extraidas:
            print("💾 Salvando dados parciais...")
            salvar_consolidado(todas_provas_extraidas)
            gerar_relatorio_final(todas_provas_extraidas)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()