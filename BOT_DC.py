import discord
from discord.ext import commands, tasks
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Caminho para o driver do Chrome
driver_path = r"CAMINHO CHROME DRIVER(DADO SENSÍVEL)"

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True  # Permite acessar o conteúdo das mensagens
bot = commands.Bot(command_prefix="!", intents=intents)

jogadores_por_servidor = {}
eventos_queue = asyncio.Queue()  # Fila para comunicação entre backend e bot

# Carregar jogadores de um arquivo JSON
def carregar_jogadores():
    global jogadores_por_servidor
    try:
        with open("jogadores.json", "r") as f:
            jogadores_por_servidor = json.load(f)
    except FileNotFoundError:
        jogadores_por_servidor = {}

# Salvar jogadores em um arquivo JSON
def salvar_jogadores():
    with open("jogadores.json", "w") as f:
        json.dump(jogadores_por_servidor, f)

# Função de backend para buscar o valor do jogador
def buscar_valor_selenium(nome):
    service = Service(driver_path)
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Executa em modo invisível
    driver = webdriver.Chrome(service=service, options=options)

    try:
        pesquisa = f"{nome} futwiz ea fc 25"
        driver.get("https://www.google.com")
        search_box = driver.find_element(By.NAME, "q")
        search_box.send_keys(pesquisa)
        search_box.send_keys(Keys.RETURN)

        WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.PARTIAL_LINK_TEXT, "futwiz.com")))
        links = driver.find_elements(By.PARTIAL_LINK_TEXT, "futwiz.com")
        for link in links:
            if "futwiz.com" in link.get_attribute("href"):
                link.click()
                break

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//*[@id='panel']/div[2]/div/div[1]/div[2]/div[2]/div[1]/div[2]/div[1]")))
        element = driver.find_element(By.XPATH, "//*[@id='panel']/div[2]/div/div[1]/div[2]/div[2]/div[1]/div[2]/div[1]")
        valor = element.text.replace(",", "").replace("$", "").strip()
        return float(valor)
    except Exception as e:
        print(f"Erro ao buscar valor para {nome}: {e}")
        return None
    finally:
        driver.quit()

async def buscar_valor(nome):
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, buscar_valor_selenium, nome)

# Comando para adicionar jogador
@bot.command()
async def adicionar(ctx, nome: str, valor_alvo: str):
    nome = nome.lower()
    servidor_id = str(ctx.guild.id)
    try:
        valor_alvo = float(valor_alvo.replace(",", ""))
        if servidor_id not in jogadores_por_servidor:
            jogadores_por_servidor[servidor_id] = {}
        jogadores_por_servidor[servidor_id][nome] = valor_alvo
        salvar_jogadores()
        await ctx.send(f"Jogador `{nome}` adicionado com valor-alvo de {valor_alvo} no servidor `{ctx.guild.name}`!")
    except ValueError:
        await ctx.send("Erro: Por favor, insira um valor numérico válido para o valor-alvo.")

# Comando para consultar o valor atual de um jogador
@bot.command()
async def valor(ctx, nome: str):
    nome = nome.lower()
    await ctx.send(f"🔍 Buscando o valor atual do jogador `{nome}`...")

    # Buscar o valor usando a função assíncrona
    valor_atual = await buscar_valor(nome)
    if valor_atual is not None:
        await ctx.send(f"⚽ O valor atual do jogador `{nome}` é `{valor_atual}`!")
    else:
        await ctx.send(f"❌ Não foi possível encontrar o valor do jogador `{nome}`.")

# Comando para remover jogador
@bot.command()
async def remover(ctx, nome: str):
    nome = nome.lower()
    servidor_id = str(ctx.guild.id)
    if servidor_id in jogadores_por_servidor and nome in jogadores_por_servidor[servidor_id]:
        del jogadores_por_servidor[servidor_id][nome]
        salvar_jogadores()
        # Após remoção, recarregar os jogadores para garantir que dados atualizados sejam usados
        carregar_jogadores()
        await ctx.send(f"Jogador `{nome}` removido da lista no servidor `{ctx.guild.name}`.")
    else:
        await ctx.send(f"Jogador `{nome}` não encontrado no servidor `{ctx.guild.name}`.")

# Tarefa para verificar valores
@tasks.loop(minutes=1)
async def verificar_valores():
    carregar_jogadores()
    
    # Iterando sobre uma cópia da lista de itens para evitar o erro de modificação durante a iteração
    for servidor_id, jogadores in list(jogadores_por_servidor.items()):  # Usando list()
        for nome, valor_alvo in list(jogadores.items()):  # Usando list() também
            valor_atual = await buscar_valor(nome)
            if valor_atual is not None and valor_atual <= valor_alvo:
                # Remover o jogador do JSON imediatamente após atingir o valor
                del jogadores_por_servidor[servidor_id][nome]
                salvar_jogadores()  # Salvar o estado atualizado no arquivo JSON
                
                # Enviar notificação
                servidor = discord.utils.get(bot.guilds, id=int(servidor_id))
                if servidor:
                    canal = servidor.text_channels[0]  # Alterar para canal correto
                    await canal.send(f"🎉 O jogador `{nome}` atingiu o valor-alvo! Valor atual: {valor_atual}.")

# Consumir a fila e enviar notificações
@tasks.loop(seconds=5)
async def processar_eventos():
    while not eventos_queue.empty():
        servidor_id, nome, valor_atual = await eventos_queue.get()
        servidor = discord.utils.get(bot.guilds, id=int(servidor_id))
        if servidor:
            canal = servidor.text_channels[0]  # Alterar para canal correto
            await canal.send(f"🎉 O jogador `{nome}` atingiu o valor-alvo! Valor atual: {valor_atual}.")

# Evento ao inicializar
@bot.event
async def on_ready():
    print(f"Bot {bot.user.name} está online!")
    verificar_valores.start()
    processar_eventos.start()

# Rodar o bot
if __name__ == "__main__":
    bot.run('TOKEN BOT(DADO SENSÍVEL)')