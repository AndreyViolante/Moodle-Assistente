"""Testa a janela de chat de ponta a ponta, com a API do Google simulada.

Nao gasta cota nem precisa de chave: o download do anexo e feito de verdade
so se houver token do Moodle, senao usa um PDF de mentira.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ia
import moodle_core
import notificacoes

notificacoes.processar = lambda *a, **k: None
os.environ["GEMINI_API_KEY"] = "chave-de-teste"

RESPOSTA = ("Claro! Vamos por partes.\n\n"
            "**Passo 1:** entenda o padrao.\n\n"
            "```python\nclass Fabrica:\n    def criar(self):\n        pass\n```\n\n"
            "Depois disso e so implementar.")
pedidos = []


class RespostaFalsa:
    status_code = 200

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": RESPOSTA}]}}]}


def post_falso(url, params=None, json=None, timeout=None):
    pedidos.append(json)
    time.sleep(0.4)  # latencia de mentira, pra dar pra testar o estado "pensando"
    return RespostaFalsa()


ia.requests.post = post_falso
# sem isso o fallback de modelo faria uma chamada de rede real na listagem
ia.requests.get = lambda *a, **k: (_ for _ in ()).throw(
    ia.requests.exceptions.ConnectionError("sem rede no teste"))

# o anexo e baixado de mentira, pra o teste nao depender da rede
moodle_core.baixar = lambda url, timeout=60: b"%PDF-1.4 conteudo de teste"

import app as app_mod
from janela_chat import Bolha

falhas = []


def imprimivel(texto):
    """O console do Windows e cp1252 e engasga com emoji (o anexo usa um)."""
    codec = sys.stdout.encoding or "utf-8"
    return str(texto).encode(codec, "replace").decode(codec, "replace")


def checar(rotulo, ok, detalhe=""):
    linha = ("  OK   " if ok else "  FALHA") + f"  {rotulo}"
    if detalhe:
        linha += f"  [{imprimivel(detalhe)}]"
    print(linha, flush=True)
    if not ok:
        falhas.append(rotulo)


def passo(func):
    """Sem isso um erro dentro de callback do Tk deixa o teste rodando pra sempre."""
    def envolvido(*args):
        try:
            func(*args)
        except Exception as e:
            import traceback
            traceback.print_exc()
            falhas.append(f"{func.__name__}: {e}")
            a.quit()
    return envolvido


agora = int(time.time())
ATIVIDADE = {
    "nome": "Implementacao dos Padroes Abstract e Factory",
    "materia": "Arquitetura e Projeto de Software_Eng.Soft06",
    "duedate": agora + 6 * 86400,
    "status": "new",
    "url": "https://moodle.univassouras.edu.br/mod/assign/view.php?id=1",
    "enunciado": "Implemente os padroes Abstract Factory e Factory Method.",
    "anexos": [{"filename": "Atividade Factory e Abstract.pdf", "filesize": 442653,
                "mimetype": "application/pdf", "fileurl": "https://exemplo/arquivo.pdf"}],
}

moodle_core.coletar = lambda: {"agora": agora, "novidades": [], "atividades": [ATIVIDADE]}

a = app_mod.App()


def bolhas(janela):
    return [w for w in janela.area.interior.winfo_children() if isinstance(w, Bolha)]


def textos(janela):
    out = []
    for b in bolhas(janela):
        for f in b._corpo.winfo_children():
            for x in ([f] + list(f.winfo_children())):
                if hasattr(x, "cget"):
                    try:
                        t = x.cget("text")
                        if t:
                            out.append(t)
                    except Exception:
                        pass
    return out


@passo
def etapa1():
    print("=== abrir pelo cartao ===", flush=True)
    cartao = a.areas["Prioridades"].interior.winfo_children()[0]
    cartao.event_generate("<Button-1>")
    a.update()
    janela = a._chats.get(ATIVIDADE["nome"] + "|" + ATIVIDADE["materia"])
    checar("o clique no cartao abre a janela de chat", janela is not None)
    if janela is None:
        a.quit()
        return
    checar("titulo tem o nome da atividade", "Abstract" in janela.title())
    checar("mostra o enunciado", "Abstract Factory" in janela.rot_enunciado.cget("text"))

    print("\n=== a mesma atividade nao abre duas janelas ===")
    de_novo = a.abrir_chat(ATIVIDADE)
    checar("reaproveita a janela aberta", de_novo is janela)

    a.after(1500, lambda: etapa2(janela))


@passo
def etapa2(janela):
    print("\n=== anexo baixado e mandado pra IA ===")
    checar("a conversa foi montada", janela.conversa is not None)
    if janela.conversa is None:
        a.quit()
        return
    checar("o anexo entrou na conversa", len(janela.conversa.anexos_pendentes) == 1,
           str(len(janela.conversa.anexos_pendentes)))
    checar("o rodape mostra o anexo", "Atividade Factory" in janela.rot_anexos.cget("text"),
           janela.rot_anexos.cget("text"))
    checar("tem mensagem de boas-vindas", len(bolhas(janela)) == 1, str(len(bolhas(janela))))

    print("\n=== mandar uma pergunta (tecla Enter) ===")
    janela.entrada.insert("1.0", "Por onde eu comeco?")
    # o Enter e tratado no widget interno do CTkTextbox, e evento de teclado so
    # dispara o binding se o widget estiver com o foco - que e o caso quando o
    # usuario digita de verdade
    caixa = getattr(janela.entrada, "_textbox", janela.entrada)
    caixa.focus_force()
    a.update()
    caixa.event_generate("<Return>")
    a.update()
    checar("a pergunta virou bolha", len(bolhas(janela)) == 2, str(len(bolhas(janela))))
    checar("a caixa de texto esvaziou", not janela.entrada.get("1.0", "end").strip())
    checar("trava o envio enquanto pensa", janela.ocupado)
    a.after(1200, lambda: etapa3(janela))


@passo
def etapa3(janela):
    checar("destravou depois da resposta", not janela.ocupado)
    checar("a resposta virou bolha", len(bolhas(janela)) == 3, str(len(bolhas(janela))))
    conteudo = " ".join(textos(janela))
    checar("mostra o texto da resposta", "Vamos por partes" in conteudo)
    checar("nao mostra os asteriscos do markdown", "**" not in conteudo)

    codigo = [w for b in bolhas(janela) for f in b._corpo.winfo_children()
              for w in f.winfo_children() if w.winfo_class() == "Text"]
    checar("bloco de codigo vira caixa mono", len(codigo) == 1, str(len(codigo)))
    if codigo:
        checar("o codigo esta certo", "class Fabrica" in codigo[0].get("1.0", "end"))

    print("\n=== o pedido que foi pra API ===")
    checar("mandou o PDF", any("inline_data" in p for p in pedidos[-1]["contents"][0]["parts"]))
    checar("mandou o enunciado no system_instruction",
           "Abstract Factory" in pedidos[-1]["system_instruction"]["parts"][0]["text"])

    print("\n=== rolagem: chat e janela principal nao se misturam ===")
    for i in range(12):
        janela._bolha(f"mensagem de enchimento {i}", "ia")
    a.update()
    time.sleep(0.3)
    a.update()
    pos_principal = a.areas["Prioridades"]._canvas.canvasy(0)
    janela.event_generate("<MouseWheel>", delta=-120)
    a.update()
    checar("a roda rola o chat", janela.area._canvas.canvasy(0) > 0,
           f"{janela.area._canvas.canvasy(0):.0f}px")
    checar("a janela principal nao se mexe",
           a.areas["Prioridades"]._canvas.canvasy(0) == pos_principal)

    print("\n=== erro da API aparece pro usuario ===")
    ia.requests.post = lambda *ar, **kw: (_ for _ in ()).throw(
        ia.requests.exceptions.ConnectionError("sem rede"))
    janela._enviar("teste de erro")
    a.after(1200, lambda: etapa4(janela))


@passo
def etapa4(janela):
    conteudo = " ".join(w.cget("text") for w in janela.area.interior.winfo_children()
                        if hasattr(w, "cget") and not isinstance(w, Bolha))
    checar("mostra o erro na conversa", "Erro" in conteudo or "conexao" in conteudo.lower(),
           conteudo[:70])
    checar("destravou depois do erro", not janela.ocupado)
    janela.destroy()
    a.update()
    checar("fechar o chat nao quebra a janela principal", a.winfo_exists())
    a.quit()


a.after(1500, etapa1)
a.mainloop()
a.destroy()
print("\nRESULTADO:", "tudo passou" if not falhas else f"{len(falhas)} falha(s): {falhas}")
sys.exit(1 if falhas else 0)
