from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import pickle
import os
import time
import re
import base64
import requests
import json

def fazer_login(driver, email, senha):
    """Faz login no site"""
    print("Fazendo login...")
    driver.get("https://app.repertorioenem.com.br/login")
    
    wait = WebDriverWait(driver, 10)
    
    try:
        campo_email = wait.until(EC.presence_of_element_located((By.ID, "inputEmailAddress")))
        campo_email.clear()
        campo_email.send_keys(email)
        
        campo_senha = driver.find_element(By.ID, "inputPassword")
        campo_senha.clear()
        campo_senha.send_keys(senha)
        
        botao_login = driver.find_element(By.CSS_SELECTOR, ".btn.btn-lg.w-100.bg-purple")
        botao_login.click()
        
        time.sleep(5)
        
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "card-body")))
        print("Login realizado com sucesso!")
        return True
    except Exception as e:
        print(f"ERRO: Falha no login! - {e}")
        return False

def salvar_cookies(driver, arquivo="cookies.pkl"):
    """Salva os cookies em um arquivo"""
    pickle.dump(driver.get_cookies(), open(arquivo, "wb"))
    print(f"Cookies salvos em {arquivo}")

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
            print("Cookies carregados!")
            return True
        except Exception as e:
            print(f"ERRO ao carregar cookies: {e}")
            return False
    return False

def deletar_cookies(arquivo="cookies.pkl"):
    """Deleta o arquivo de cookies"""
    if os.path.exists(arquivo):
        os.remove(arquivo)
        print(f"Cookies deletados: {arquivo}")
        return True
    return False

def verificar_login(driver):
    """Verifica se ainda está logado checando a URL e elementos da página"""
    try:
        driver.get("https://app.repertorioenem.com.br/questions/list")
        time.sleep(3)
        
        if "login" in driver.current_url:
            print("Redirecionado para login - sessão inválida")
            return False
        
        driver.find_element(By.CLASS_NAME, "card-body")
        print("Sessão válida!")
        return True
    except:
        print("Sessão inválida")
        return False

def imagem_para_base64(url_imagem):
    """Baixa a imagem e converte para base64"""
    try:
        response = requests.get(url_imagem, timeout=10)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            
            if 'jpeg' in content_type or url_imagem.endswith(('.jpg', '.jpeg')):
                mime_type = 'image/jpeg'
            elif 'png' in content_type or url_imagem.endswith('.png'):
                mime_type = 'image/png'
            elif 'gif' in content_type or url_imagem.endswith('.gif'):
                mime_type = 'image/gif'
            elif 'webp' in content_type or url_imagem.endswith('.webp'):
                mime_type = 'image/webp'
            else:
                mime_type = 'image/jpeg'
            
            img_base64 = base64.b64encode(response.content).decode('utf-8')
            data_uri = f"data:{mime_type};base64,{img_base64}"
            return data_uri
        else:
            print(f"      ERRO ao baixar imagem: Status {response.status_code}")
            return url_imagem
    except Exception as e:
        print(f"      ERRO ao converter imagem: {e}")
        return url_imagem

def converter_imagens_para_base64(html):
    """Encontra todas as tags img e converte src para base64"""
    if '<img' not in html.lower():
        return html
    
    pattern = r'<img[^>]*src=["\']([^"\']+)["\'][^>]*>'
    
    def substituir_img(match):
        img_tag = match.group(0)
        url_original = match.group(1)
        
        if url_original.startswith('data:'):
            return img_tag
        
        base64_url = imagem_para_base64(url_original)
        nova_img_tag = img_tag.replace(url_original, base64_url)
        return nova_img_tag
    
    html_convertido = re.sub(pattern, substituir_img, html)
    return html_convertido

def limpar_html(html):
    """Remove spans e formata o HTML, mantendo apenas <p> interno"""
    # Remove classes e IDs
    html = re.sub(r'\s*class="[^"]*"', '', html)
    html = re.sub(r'\s*id="[^"]*"', '', html)
    
    # Remove todas as tags <span>
    html = re.sub(r'</?span[^>]*>', '', html)
    
    # Remove <p> vazio ou extra no início/fim
    html = html.strip()
    
    # Se houver <p> externo envolvendo outro <p>, remove o externo
    pattern = r'^<p>\s*(<p>.*</p>)\s*</p>$'
    match = re.match(pattern, html, re.DOTALL)
    if match:
        html = match.group(1)

    if not html.startswith('<p>'):
        html = f"<p>{html}</p>"
    
    return html

def extrair_topicos(elemento_pai):
    """Extrai os tópicos/assuntos da questão (do 3º span em diante)"""
    try:
        div_d_flex = elemento_pai.find_element(By.CSS_SELECTOR, ".d-flex.flex-wrap.text-left")
        spans = div_d_flex.find_elements(By.TAG_NAME, "span")
        
        # Pegar do 3º span em diante (índice 2+)
        topicos = []
        for i in range(2, len(spans)):
            texto = spans[i].text.strip()
            if texto:
                topicos.append(texto)
        
        # Juntar com ponto e vírgula
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

def extrair_questoes(driver, url):
    """Extrai enunciados e alternativas de uma página"""
    print(f"Acessando: {url}")
    driver.get(url)
    time.sleep(3)
    
    if "login" in driver.current_url:
        print("  ERRO: Não está logado! Redirecionado para página de login.")
        return []
    
    questoes_json = []
    
    enunciados = driver.find_elements(By.CSS_SELECTOR, ".mb-0.mx-2.ck-content.highlighter-context")
    print(f"  - {len(enunciados)} enunciados encontrados")
    
    for i, enunciado in enumerate(enunciados, 1):
        try:
            enunciado_html = enunciado.get_attribute('innerHTML')
            if '<img' in enunciado_html.lower():
                print(f"    Questão {i}: Convertendo imagens do enunciado...")
            enunciado_html = converter_imagens_para_base64(enunciado_html)
            enunciado_limpo = limpar_html(enunciado_html)
            
            # Localiza container principal da questão
            elemento_pai = enunciado.find_element(By.XPATH, "./ancestor::div[contains(@class, 'card')]")
            
            # Extrair tópicos e dificuldade
            topicos = extrair_topicos(elemento_pai)
            dificuldade = extrair_dificuldade(elemento_pai)
            
            container_d_flex = elemento_pai.find_element(By.CSS_SELECTOR, ".d-flex.flex-wrap.justify-content-between")
            
            # Tenta pegar a div .ms-0 correta
            try:
                div_ms0 = container_d_flex.find_element(By.XPATH, "./following-sibling::div[contains(@class, 'ms-0')]")
            except:
                div_ms0 = container_d_flex.find_element(By.CSS_SELECTOR, ".ms-0")
            
            # Alternativas
            alternativas_container = div_ms0.find_elements(
                By.CSS_SELECTOR, 
                ".d-flex.flex-row.justify-content-start.align-items-center.ms-0.my-3"
            )
            
            alternativas_obj = {f"alternativa_{l}_txt": "" for l in ['a','b','c','d','e']}
            
            for idx, alt_container in enumerate(alternativas_container):
                if idx >= 5:
                    break
                try:
                    conteudo_label = alt_container.find_element(By.CSS_SELECTOR, ".form-check-label.ms-3")
                    conteudo = conteudo_label.get_attribute('innerHTML')
                    if '<img' in conteudo.lower():
                        print(f"    Questão {i}: Convertendo imagens da alternativa {['a','b','c','d','e'][idx]}...")
                    conteudo = converter_imagens_para_base64(conteudo)
                    alternativas_obj[f"alternativa_{['a','b','c','d','e'][idx]}_txt"] = limpar_html(conteudo)
                except:
                    pass
            
            # Último input = alternativa correta (em maiúsculo e dentro de <p>)
            alternativa_correta = ""
            try:
                inputs = div_ms0.find_elements(By.CSS_SELECTOR, "input")
                if inputs:
                    alternativa_correta = inputs[-1].get_attribute('value').upper()
                    alternativa_correta = f"<p>{alternativa_correta}</p>"
            except:
                pass
            
            questao_obj = {
                "assunto": topicos,
                "dificuldade": dificuldade,
                "enunciado_txt": enunciado_limpo,
                "alternativas": alternativas_obj,
                "alternativa_correta": alternativa_correta
            }

            # Remove \n e espaços estranhos do início/fim
            questao_obj["enunciado_txt"] = re.sub(r'^\s*\\n\s*', '', questao_obj["enunciado_txt"])
            questao_obj["enunciado_txt"] = re.sub(r'\\n\s*$', '', questao_obj["enunciado_txt"])
            
            questoes_json.append(questao_obj)
            print(f"    Questão {i}: Extraída com sucesso (Assunto: {topicos[:50]}..., Dificuldade: {dificuldade})")
            
        except Exception as e:
            print(f"    Questão {i}: Erro - {e}")
    
    return questoes_json

def salvar_json(todas_questoes, arquivo="enem2020_natureza.json"):
    """Salva todas as questões em um arquivo JSON"""
    dados = {
        "prova": "CIÊNCIAS DA NATUREZA E SUAS TECNOLOGIAS",
        "ano": 2020,
        "questoes": todas_questoes
    }
    
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    
    print(f"\nArquivo salvo: {arquivo}")
    print(f"Total de questões extraídas: {len(todas_questoes)}")

def realizar_login_com_retry(driver, email, senha, max_tentativas=3):
    """Tenta fazer login com múltiplas tentativas"""
    for tentativa in range(1, max_tentativas + 1):
        print(f"\n--- Tentativa de login {tentativa}/{max_tentativas} ---")
        
        # Deletar cookies antes de tentar novamente
        if tentativa > 1:
            print("Deletando cookies corrompidos...")
            deletar_cookies()
            driver.delete_all_cookies()
        
        # Tentar fazer login
        login_ok = fazer_login(driver, email, senha)
        
        if login_ok:
            salvar_cookies(driver)
            return True
        
        print(f"Tentativa {tentativa} falhou.")
        time.sleep(2)
    
    return False

# ============ CÓDIGO PRINCIPAL ============

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

try:
    driver.get("https://app.repertorioenem.com.br")
    time.sleep(2)
    
    cookies_existem = carregar_cookies(driver)
    login_ok = False
    
    if cookies_existem:
        print("Verificando se cookies ainda são válidos...")
        login_ok = verificar_login(driver)
        
        # Se cookies existem mas são inválidos, deletar
        if not login_ok:
            print("Cookies inválidos detectados. Deletando...")
            deletar_cookies()
    
    if not login_ok:
        print("Realizando login...")
        login_ok = realizar_login_com_retry(driver, "laionp98@gmail.com", "00uLisses00!", max_tentativas=3)
        
        if not login_ok:
            print("\n❌ ERRO CRÍTICO: Não foi possível fazer login após múltiplas tentativas!")
            print("Verifique suas credenciais ou tente novamente mais tarde.")
            driver.quit()
            exit(1)
    
    base_url = "https://app.repertorioenem.com.br/questions/list?search=1&field%5B%5D=8&field%5B%5D=10&field%5B%5D=9&institution%5B%5D=1&year%5B%5D=2020&text=&pages=50&order_by=1"
    
    todas_questoes = []
    
    print("\n=== INICIANDO EXTRAÇÃO ===\n")
    for pagina in range(1, 2):
        url = base_url + str(pagina)
        questoes_pagina = extrair_questoes(driver, url)
        todas_questoes.extend(questoes_pagina)
        print(f"Página {pagina}: {len(questoes_pagina)} questões extraídas\n")
    
    if len(todas_questoes) > 0:
        salvar_json(todas_questoes)
        print("\n✅ === EXTRAÇÃO CONCLUÍDA ===")
    else:
        print("\n⚠️ === NENHUMA QUESTÃO EXTRAÍDA - VERIFIQUE O LOGIN ===")
    
finally:
    driver.quit()