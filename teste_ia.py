"""Testa o enunciado, os anexos e a conversa com a IA sem chamar a API de verdade."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ia
import moodle_core

falhas = []


def checar(rotulo, ok, detalhe=""):
    print(("  OK   " if ok else "  FALHA") + f"  {rotulo}" + (f"  [{detalhe}]" if detalhe else ""))
    if not ok:
        falhas.append(rotulo)


print("=== HTML do professor vira texto legivel ===")
bruto = ('<p dir="ltr">Diagrama de Classes e c&oacute;digo;</p><p>Uma escola de '
         'm&uacute;sica&nbsp;chamada Harmonia&hellip;</p><ul><li>aluno</li>'
         '<li>professor</li></ul><br><script>x=1</script>')
texto = moodle_core.texto_do_html(bruto)
print("  ->", repr(texto))
checar("tira as tags", "<p" not in texto and "<li" not in texto)
checar("resolve entidades HTML", "código" in texto and "música" in texto)
checar("tira &nbsp;", "\xa0" not in texto)
checar("remove script", "x=1" not in texto)
checar("vira lista com tracinho", "- aluno" in texto)
checar("nao deixa linha em branco demais", "\n\n\n" not in texto)
checar("html vazio devolve vazio", moodle_core.texto_do_html("") == "")

print("\n=== conversa monta o pedido certo ===")
enviados = []


class RespostaFalsa:
    status_code = 200

    def __init__(self, texto="Resposta da IA."):
        self._texto = texto

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": self._texto}]}}]}


def post_falso(url, params=None, json=None, timeout=None):
    enviados.append({"url": url, "corpo": json})
    return RespostaFalsa()


ia.requests.post = post_falso
os.environ["GEMINI_API_KEY"] = "chave-de-teste"

atividade = {"nome": "Padroes Abstract e Factory", "materia": "Arquitetura_Eng.Soft06"}
conversa = ia.Conversa(atividade, "Implemente os padroes.", prazo="31/08/2026")
ok = conversa.anexar({"filename": "enunciado.pdf", "mimetype": "application/pdf",
                      "dados": b"%PDF-1.4 fingindo ser um pdf"})
checar("aceita o anexo", ok)

resposta = conversa.enviar("Por onde comeco?")
checar("devolve a resposta", resposta == "Resposta da IA.", resposta)

corpo = enviados[-1]["corpo"]
instrucao = corpo["system_instruction"]["parts"][0]["text"]
checar("manda o nome da atividade", "Padroes Abstract e Factory" in instrucao)
checar("manda o enunciado", "Implemente os padroes." in instrucao)
checar("manda o prazo", "31/08/2026" in instrucao)
checar("responde em portugues", "portugues" in instrucao.lower())

partes = corpo["contents"][0]["parts"]
checar("o PDF vai junto da primeira pergunta", any("inline_data" in p for p in partes))
checar("o PDF vai como application/pdf",
       any(p.get("inline_data", {}).get("mime_type") == "application/pdf" for p in partes))
checar("a pergunta vai junto", any(p.get("text") == "Por onde comeco?" for p in partes))

print("\n=== segunda mensagem ===")
conversa.enviar("E agora?")
partes2 = enviados[-1]["corpo"]["contents"][-1]["parts"]
checar("nao reenvia o PDF", not any("inline_data" in p for p in partes2))
checar("mantem o historico", len(enviados[-1]["corpo"]["contents"]) == 3,
       str(len(enviados[-1]["corpo"]["contents"])))
checar("historico guarda a resposta da IA",
       enviados[-1]["corpo"]["contents"][1]["role"] == "model")

print("\n=== anexo grande demais e recusado ===")
c2 = ia.Conversa(atividade, "x")
checar("recusa acima do limite",
       not c2.anexar({"filename": "gigante.pdf", "mimetype": "application/pdf",
                      "dados": b"0" * (ia.LIMITE_ANEXO + 1)}))

print("\n=== erros da API viram mensagem legivel ===")


class RespostaErro:
    def __init__(self, codigo, msg):
        self.status_code = codigo
        self._msg = msg
        self.text = msg

    def json(self):
        return {"error": {"message": self._msg}}


ia.requests.post = lambda *a, **k: RespostaErro(403, "API key not valid")
c3 = ia.Conversa(atividade, "x")
try:
    c3.enviar("oi")
    checar("erro 403 vira ErroIA", False, "nao levantou")
except ia.ErroIA as e:
    checar("erro 403 explica a chave", "chave" in str(e).lower(), str(e)[:60])
checar("pergunta sem resposta nao fica no historico", len(c3.historico) == 0)

ia.requests.post = lambda *a, **k: RespostaErro(429, "quota")
try:
    c3.enviar("oi")
    checar("erro 429 vira ErroIA", False)
except ia.ErroIA as e:
    checar("erro 429 fala de limite", "limite" in str(e).lower(), str(e)[:60])

print("\n=== sem chave configurada ===")
os.environ["GEMINI_API_KEY"] = ""
checar("detecta falta de chave", not ia.disponivel())

print("\nRESULTADO:", "tudo passou" if not falhas else f"{len(falhas)} falha(s): {falhas}")
sys.exit(1 if falhas else 0)
