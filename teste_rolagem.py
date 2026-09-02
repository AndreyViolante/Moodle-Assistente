"""Testa a rolagem simulando como o Windows entrega a roda de verdade.

No Windows o Tk manda <MouseWheel> pro widget com FOCO (normalmente o
toplevel), nao pro que esta sob o cursor. Por isso o teste dispara o evento
no widget focado - foi essa diferenca que fez a versao anterior passar nos
testes e nao rolar nada na pratica.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import moodle_core
import notificacoes

agora = int(time.time())
FAKE = {
    "agora": agora,
    "atividades": [{"materia": f"Materia {i % 3}_Eng.Soft06", "nome": f"Atividade numero {i}",
                    "duedate": agora + (i + 5) * 86400, "status": "new", "url": "https://x/y"}
                   for i in range(20)],
    "novidades": [],
}
moodle_core.coletar = lambda: FAKE
notificacoes.processar = lambda *a, **k: None

import app as app_mod

falhas = []


def checar(rotulo, ok, detalhe=""):
    print(("  OK   " if ok else "  FALHA") + f"  {rotulo}" + (f"  [{detalhe}]" if detalhe else ""))
    if not ok:
        falhas.append(rotulo)


a = app_mod.App()
prio = a.areas["Prioridades"]
canvas = prio._canvas


def roda_no_foco(cliques):
    """Como o Windows faz: entrega no widget com foco."""
    alvo = a.focus_get() or a
    for _ in range(abs(cliques)):
        alvo.event_generate("<MouseWheel>", delta=-120 if cliques < 0 else 120)
    a.update()


def etapa():
    print(f"foco: {a.focus_get()}  (e pra ca que o Windows manda a roda)")
    print("\n=== roda entregue no widget com foco ===")
    canvas.yview_moveto(0)
    a.update()
    roda_no_foco(-3)
    andou = canvas.canvasy(0)
    checar("3 cliques rolam ~180px", 150 <= andou <= 210, f"{andou:.0f}px")

    roda_no_foco(3)
    checar("volta ao topo", canvas.canvasy(0) == 0)

    print("\n=== roda entregue no toplevel (caso mais comum) ===")
    canvas.yview_moveto(0)
    a.update()
    for _ in range(3):
        a.event_generate("<MouseWheel>", delta=-120)
    a.update()
    checar("toplevel rola a lista", canvas.canvasy(0) > 0, f"{canvas.canvasy(0):.0f}px")

    print("\n=== roda entregue num widget qualquer (se ele pegar o foco) ===")
    for nome, w in [("botao Atualizar", a.botao), ("rotulo de estado", a.status),
                    ("cartao da lista", prio.interior.winfo_children()[1]),
                    ("canvas da area", canvas)]:
        canvas.yview_moveto(0)
        a.update()
        w.event_generate("<MouseWheel>", delta=-120)
        a.update()
        checar(f"rola com o evento em '{nome}'", canvas.canvasy(0) > 0, f"{canvas.canvasy(0):.0f}px")

    print("\n=== nao acumula handler a cada atualizacao ===")
    canvas.yview_moveto(0)
    a.update()
    a.event_generate("<MouseWheel>", delta=-120)
    a.update()
    um_clique = canvas.canvasy(0)
    for _ in range(3):  # simula 3 atualizacoes de 30 min
        a._mostrar(FAKE)
    a.update()
    canvas.yview_moveto(0)
    a.update()
    a.event_generate("<MouseWheel>", delta=-120)
    a.update()
    checar("1 clique continua andando o mesmo tanto", canvas.canvasy(0) == um_clique,
           f"{canvas.canvasy(0):.0f} vs {um_clique:.0f}")

    print("\n=== limite do fim ===")
    for _ in range(60):
        a.event_generate("<MouseWheel>", delta=-120)
    a.update()
    checar("para no fim sem espaco vazio", canvas.yview()[1] <= 1.0001, f"base={canvas.yview()[1]:.3f}")

    print("\n=== abas ===")
    pos_prio = canvas.canvasy(0)
    a.abas.set("Novidades")
    a.update()
    time.sleep(0.3)
    a.update()
    a.event_generate("<MouseWheel>", delta=-120)
    a.update()
    checar("aba escondida nao se mexe", canvas.canvasy(0) == pos_prio)
    checar("aba vazia: barra escondida", not a.areas["Novidades"]._barra_visivel)

    a.abas.set("Todas")
    a.update()
    time.sleep(0.3)
    a.update()
    todas = a.areas["Todas"]
    a.event_generate("<MouseWheel>", delta=-120)
    a.update()
    checar("aba Todas rola", todas._canvas.canvasy(0) > 0, f"{todas._canvas.canvasy(0):.0f}px")
    checar("aba Todas: barra visivel", todas._barra_visivel)

    print("\n=== teclado ===")
    a.abas.set("Prioridades")
    a.update()
    prio.ir_para(0)
    a.update()
    a.event_generate("<Next>")
    a.update()
    checar("Page Down desce", canvas.canvasy(0) > 100, f"{canvas.canvasy(0):.0f}px")
    a.event_generate("<Home>")
    a.update()
    checar("Home volta ao topo", canvas.canvasy(0) == 0)

    print("\n=== conteudo encolhe com a vista rolada ===")
    canvas.yview_moveto(0.9)
    a.update()
    a._mostrar(dict(FAKE, atividades=FAKE["atividades"][:2]))
    a.update()
    time.sleep(0.3)
    a.update()
    topo = canvas.yview()[0]
    checar("vista nao fica em espaco vazio", topo == 0.0, f"topo={topo:.3f}")
    checar("barra some", not prio._barra_visivel)

    a.quit()


a.after(1200, etapa)
a.mainloop()
a.destroy()
print("\nRESULTADO:", "tudo passou" if not falhas else f"{len(falhas)} falha(s): {falhas}")
sys.exit(1 if falhas else 0)
