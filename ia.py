"""Conversa com o Gemini (Google) sobre uma atividade do Moodle.

Usa a API REST direto com requests, que ja e dependencia do projeto. O Gemini
le PDF de forma nativa (inline_data), entao o anexo do professor vai inteiro -
com diagramas e imagens - sem precisar extrair texto.

Precisa de GEMINI_API_KEY no .env (pega em https://aistudio.google.com/apikey).
Opcional: GEMINI_MODEL pra fixar um modelo.
"""
import base64
import os

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

API = "https://generativelanguage.googleapis.com/v1beta"
MODELO_PADRAO = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
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
    pass


def _pedir(caminho, corpo=None, metodo="post"):
    if not disponivel():
        raise ErroIA("Falta a chave da API do Google. Coloque GEMINI_API_KEY no .env "
                     f"(pegue em {LINK_CHAVE}).")
    url = f"{API}/{caminho}"
    try:
        if metodo == "get":
            r = requests.get(url, params={"key": chave()}, timeout=60)
        else:
            r = requests.post(url, params={"key": chave()}, json=corpo, timeout=120)
    except requests.exceptions.Timeout:
        raise ErroIA("A IA demorou demais pra responder. Tenta de novo.")
    except requests.exceptions.ConnectionError as e:
        raise ErroIA(f"Sem conexao com a API do Google: {e}")

    if r.status_code == 200:
        return r.json()

    try:
        msg = r.json().get("error", {}).get("message", r.text[:300])
    except Exception:
        msg = r.text[:300]
    if r.status_code in (401, 403):
        raise ErroIA(f"A chave da API foi recusada: {msg}")
    if r.status_code == 429:
        raise ErroIA("Passou do limite de uso da API por agora. Espera um pouco.")
    raise ErroIA(f"A API respondeu {r.status_code}: {msg}")


def modelos():
    """Modelos que a chave pode usar, dos melhores pros mais simples."""
    dados = _pedir("models", metodo="get")
    nomes = [m["name"].split("/")[-1] for m in dados.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    def nota(n):
        return (("pro" in n) * 2 + ("flash" in n), n)
    return sorted(nomes, key=nota, reverse=True)


class Conversa:
    """Histórico de uma conversa sobre uma atividade."""

    def __init__(self, atividade, enunciado, anexos=(), prazo="sem prazo"):
        self.atividade = atividade
        self.modelo = MODELO_PADRAO
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

        try:
            dados = _pedir(f"models/{self.modelo}:generateContent", corpo)
        except ErroIA as e:
            # modelo aposentado ou indisponivel pra essa chave: tenta outro
            if "404" in str(e) or "not found" in str(e).lower():
                alternativos = [m for m in modelos() if m != self.modelo]
                if not alternativos:
                    self.historico.pop()
                    raise
                self.modelo = alternativos[0]
                dados = _pedir(f"models/{self.modelo}:generateContent", corpo)
            else:
                self.historico.pop()  # nao guarda pergunta que nao foi respondida
                raise

        candidatos = dados.get("candidates") or []
        if not candidatos:
            motivo = dados.get("promptFeedback", {}).get("blockReason", "")
            self.historico.pop()
            raise ErroIA("A IA nao respondeu" + (f" (bloqueado: {motivo})" if motivo else "."))

        partes_resp = candidatos[0].get("content", {}).get("parts", [])
        resposta = "".join(p.get("text", "") for p in partes_resp).strip()
        if not resposta:
            fim = candidatos[0].get("finishReason", "")
            self.historico.pop()
            raise ErroIA(f"A IA devolveu uma resposta vazia ({fim or 'sem motivo'}).")

        self.historico.append({"role": "model", "parts": [{"text": resposta}]})
        return resposta
