"""Conversa com o Gemini (Google) sobre uma atividade do Moodle.

Usa a API REST direto com requests, que ja e dependencia do projeto. O Gemini
le PDF de forma nativa (inline_data), entao o anexo do professor vai inteiro -
com diagramas e imagens - sem precisar extrair texto.

Precisa de GEMINI_API_KEY no .env (pega em https://aistudio.google.com/apikey).
Opcional: GEMINI_MODEL pra fixar um modelo.
"""
import base64
import os
import re

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

API = "https://generativelanguage.googleapis.com/v1beta"
MODELO_PADRAO = (os.getenv("GEMINI_MODEL") or "gemini-3.5-flash").strip()
MAX_TENTATIVAS = 4        # nao sai varrendo a lista inteira de modelos
_ultimo_que_funcionou = None   # evita re-testar modelo morto a cada pergunta
# geram texto mas nao servem de tutor, ou tem cota simbolica
DESCARTADOS = ("tts", "image", "audio", "video", "lyria", "veo", "imagen",
               "embedding", "gemma", "computer-use", "customtools", "learnlm")
LIMITE_ANEXO = 15 * 1024 * 1024  # a requisicao inteira tem que caber em ~20MB
LINK_CHAVE = "https://aistudio.google.com/apikey"

INSTRUCAO = """Voce e um tutor particular de um aluno de Engenharia de Software \
da Universidade de Vassouras. Ele esta fazendo a atividade descrita abaixo e vai \
te pedir ajuda.

Como agir:
- Responda sempre em portugues do Brasil, direto e sem enrolacao.
- Ensine o aluno a fazer: explique o raciocinio, mostre o caminho, de exemplos \
de codigo completos quando ajudar a entender.
- Se o enunciado for ambiguo, diga qual interpretacao voce assumiu em vez de \
travar a conversa com perguntas.
- Use o enunciado e os anexos como fonte principal; se algo nao estiver la, \
diga que esta supondo.
- Formate com markdown simples (titulos curtos, listas, blocos de codigo).

ATIVIDADE: {nome}
MATERIA: {materia}
PRAZO: {prazo}

ENUNCIADO DO PROFESSOR:
{enunciado}"""


def chave():
    return (os.getenv("GEMINI_API_KEY") or "").strip()


def disponivel():
    return bool(chave())


class ErroIA(Exception):
    def __init__(self, mensagem, recuperavel=False):
        """recuperavel: o problema e daquele modelo, entao vale tentar outro."""
        super().__init__(mensagem)
        self.recuperavel = recuperavel


def _pedir(caminho, corpo=None, metodo="post"):
    if not disponivel():
        raise ErroIA("Falta a chave da API do Google. Coloque GEMINI_API_KEY no .env "
                     f"(pegue em {LINK_CHAVE}).")
    url = f"{API}/{caminho}"
    try:
        if metodo == "get":
            r = requests.get(url, params={"key": chave()}, timeout=60)
        else:
            # 75s e folgado pra uma resposta com PDF, e curto o bastante pra
            # nao deixar o aluno esperando quando o modelo esta travado
            r = requests.post(url, params={"key": chave()}, json=corpo, timeout=75)
    except requests.exceptions.Timeout:
        raise ErroIA("Esse modelo demorou demais pra responder.", recuperavel=True)
    except requests.exceptions.ConnectionError as e:
        raise ErroIA(f"Sem conexao com a API do Google: {e}")

    if r.status_code == 200:
        return r.json()

    try:
        erro = r.json().get("error", {})
        msg = erro.get("message", r.text[:300])
        espera = ""
        for det in erro.get("details", []):
            if "retryDelay" in det:
                espera = f" Tenta de novo em {det['retryDelay']}."
    except Exception:
        msg, espera = r.text[:300], ""

    if r.status_code in (401, 403):
        raise ErroIA(f"A chave da API foi recusada: {msg}")
    if r.status_code == 404:
        # modelo aposentado: a propria mensagem do Google sugere o substituto
        raise ErroIA(f"O modelo saiu do ar: {msg}", recuperavel=True)
    if r.status_code == 429:
        raise ErroIA("Esse modelo esta sem cota agora." + espera, recuperavel=True)
    if r.status_code in (500, 502, 503, 504):
        raise ErroIA("O modelo esta sobrecarregado no momento.", recuperavel=True)
    raise ErroIA(f"A API respondeu {r.status_code}: {msg}")


def _nota(nome):
    """Ordena os modelos: primeiro os mais novos, e dentro da mesma geracao
    prefere flash (rapido e com cota folgada) a pro, e versao estavel a preview."""
    versao = 0.0
    m = re.match(r"gemini-(\d+(?:\.\d+)?)", nome)
    if m:
        versao = float(m.group(1))
    if "flash-lite" in nome:
        familia = 2
    elif "flash" in nome:
        familia = 3
    elif "pro" in nome:
        familia = 1
    else:
        familia = 0
    estavel = 0 if "preview" in nome or "exp" in nome else 1
    return (versao, estavel, familia)


def modelos():
    """Modelos que servem de tutor, do melhor pro pior."""
    dados = _pedir("models", metodo="get")
    nomes = [m["name"].split("/")[-1] for m in dados.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    uteis = [n for n in nomes
             if n.startswith("gemini") and not any(x in n for x in DESCARTADOS)]
    return sorted(uteis, key=_nota, reverse=True)


def candidatos(preferido=None):
    """Ordem de tentativa: o preferido, o que ja funcionou, e so entao a lista da API.

    Modelo do Gemini e aposentado de tempos em tempos (o gemini-2.5-flash saiu
    do ar com 404), entao nao da pra depender de um nome fixo no codigo.

    E um gerador de proposito: consultar a lista de modelos e uma chamada a
    mais na API, e ela so acontece se os nomes que ja conhecemos falharem.
    """
    vistos = []
    for m in (preferido, _ultimo_que_funcionou, MODELO_PADRAO):
        if m and m not in vistos:
            vistos.append(m)
            yield m
    try:
        for m in modelos():
            if len(vistos) >= MAX_TENTATIVAS:
                return
            if m not in vistos:
                vistos.append(m)
                yield m
    except ErroIA:
        return  # sem a lista, resta o que ja tentamos


class Conversa:
    """Histórico de uma conversa sobre uma atividade."""

    def __init__(self, atividade, enunciado, anexos=(), prazo="sem prazo"):
        self.atividade = atividade
        # comeca pelo modelo que ja respondeu nesta sessao: sem isso toda conversa
        # nova gasta uma ida a API redescobrindo que o padrao foi aposentado
        self.modelo = _ultimo_que_funcionou or MODELO_PADRAO
        self.historico = []      # [{"role": "user"/"model", "parts": [...]}]
        self.anexos_pendentes = []
        self.instrucao = INSTRUCAO.format(
            nome=atividade.get("nome", "?"),
            materia=atividade.get("materia", "?"),
            prazo=prazo,
            enunciado=enunciado.strip() or "(o professor nao escreveu enunciado; "
                                           "veja os anexos)")
        for anexo in anexos:
            self.anexar(anexo)

    def anexar(self, anexo):
        """anexo: {'filename', 'mimetype', 'dados' (bytes)}"""
        dados = anexo.get("dados")
        if not dados or len(dados) > LIMITE_ANEXO:
            return False
        self.anexos_pendentes.append({
            "inline_data": {
                "mime_type": anexo.get("mimetype") or "application/pdf",
                "data": base64.b64encode(dados).decode("ascii"),
            }
        })
        return True

    def enviar(self, texto):
        """Manda a mensagem e devolve a resposta da IA."""
        partes = list(self.anexos_pendentes) + [{"text": texto}]
        self.anexos_pendentes = []  # anexo vai uma vez so; depois fica no historico
        self.historico.append({"role": "user", "parts": partes})

        corpo = {
            # copia: o corpo enviado nao pode mudar quando o historico crescer
            "contents": list(self.historico),
            "system_instruction": {"parts": [{"text": self.instrucao}]},
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 8192},
        }

        global _ultimo_que_funcionou
        dados, ultimo_erro = None, None
        for modelo in candidatos(self.modelo):
            try:
                dados = _pedir(f"models/{modelo}:generateContent", corpo)
            except ErroIA as e:
                # aposentado, sem cota ou sobrecarregado: o proximo da fila pode ir
                if e.recuperavel:
                    ultimo_erro = e
                    continue
                self.historico.pop()  # nao guarda pergunta que nao foi respondida
                raise
            self.modelo = _ultimo_que_funcionou = modelo
            break

        if dados is None:
            self.historico.pop()
            raise ultimo_erro or ErroIA("Nenhum modelo do Gemini esta disponivel agora.")

        # nome diferente da funcao candidatos(): variavel local sombreia o modulo
        # inteiro e quebra a escolha de modelo la em cima
        saidas = dados.get("candidates") or []
        if not saidas:
            motivo = dados.get("promptFeedback", {}).get("blockReason", "")
            self.historico.pop()
            raise ErroIA("A IA nao respondeu" + (f" (bloqueado: {motivo})" if motivo else "."))

        partes_resp = saidas[0].get("content", {}).get("parts", [])
        resposta = "".join(p.get("text", "") for p in partes_resp).strip()
        if not resposta:
            fim = saidas[0].get("finishReason", "")
            self.historico.pop()
            raise ErroIA(f"A IA devolveu uma resposta vazia ({fim or 'sem motivo'}).")

        self.historico.append({"role": "model", "parts": [{"text": resposta}]})
        return resposta
