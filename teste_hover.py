"""Testa o hover dos cartoes.

O <Leave> do Tk dispara tambem quando o mouse passa do cartao pra um filho
dele. Ligando Enter/Leave em todos os filhos (que e preciso, pois sao eles
que recebem o evento), despintar direto no Leave faz o cartao piscar a cada
movimento do mouse. Este teste conta quantas vezes o cartao e realmente
redesenhado ao varrer o mouse por cima dele.
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
    "novidades": [],
    "atividades": [{"materia": f"Materia {i}_Eng.Soft06", "nome": f"Atividade numero {i}",
                    "duedate": agora + (i + 5) * 86400, "status": "new", "url": "https://x/y"}
                   for i in range(6)],
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
area = a.areas["Prioridades"]


def descendentes(w):
    yield w
    for f in w.winfo_children():
        yield from descendentes(f)


def etapa():
    cartao = area.interior.winfo_children()[0]
    outro = area.interior.winfo_children()[1]

    # finge que o cursor esta no meio do cartao
    def cursor_em(widget):
        alvo = [widget.winfo_rootx() + widget.winfo_width() // 2,
                widget.winfo_rooty() + widget.winfo_height() // 2]
        for c in descendentes(area.interior):
            c.winfo_pointerxy = lambda alvo=alvo: tuple(alvo)

    # conta redesenhos de verdade
    redesenhos = []
    orig = type(cartao).configure
    def espiao(self, **kw):
        if "fg_color" in kw:
            redesenhos.append(kw["fg_color"])
        return orig(self, **kw)
    type(cartao).configure = espiao

    print("=== varrendo o mouse por dentro do cartao ===")
    cursor_em(cartao)
    filhos = list(descendentes(cartao))
    redesenhos.clear()
    filhos[0].event_generate("<Enter>")
    a.update()
    # o mouse anda por 12 widgets internos: cada passo gera Leave no anterior
    # e Enter no seguinte
    for w in filhos[1:13]:
        w.event_generate("<Leave>")
        w.event_generate("<Enter>")
        a.update()
    a.update_idletasks()
    print(f"  redesenhos ao atravessar {len(filhos[1:13])} widgets internos: {len(redesenhos)}")
    checar("nao pisca ao andar dentro do cartao", len(redesenhos) <= 1, f"{len(redesenhos)} redesenhos")
    checar("fica no estado hover", cartao._cor == app_mod.C["cartao_hover"], cartao._cor)

    print("\n=== saindo do cartao de verdade ===")
    cursor_em(outro)  # cursor agora esta sobre outro cartao
    redesenhos.clear()
    filhos[5].event_generate("<Leave>")
    a.update()
    a.update_idletasks()
    checar("despinta ao sair", cartao._cor == app_mod.C["cartao"], cartao._cor)
    checar("um unico redesenho", len(redesenhos) == 1, f"{len(redesenhos)}")

    print("\n=== voltando pro cartao ===")
    cursor_em(cartao)
    cartao.event_generate("<Enter>")
    a.update()
    checar("pinta de novo", cartao._cor == app_mod.C["cartao_hover"], cartao._cor)

    print("\n=== cursor fora da janela (Leave sem Enter) ===")
    for c in descendentes(area.interior):
        c.winfo_pointerxy = lambda: (5000, 5000)
    cartao.event_generate("<Leave>")
    a.update()
    a.update_idletasks()
    checar("nao fica preso no hover", cartao._cor == app_mod.C["cartao"], cartao._cor)

    print("\n=== cursor (mao) e clique ===")
    cursores = {str(w): w.cget("cursor") for w in descendentes(cartao)}
    todos_mao = all(v == "hand2" for v in cursores.values())
    checar("cursor de mao em todo o cartao", todos_mao,
           f"{sum(1 for v in cursores.values() if v == 'hand2')}/{len(cursores)}")

    abertos = []
    app_mod.webbrowser.open = lambda u: abertos.append(u)
    for w in list(descendentes(cartao))[:8]:
        w.event_generate("<Button-1>")
    a.update()
    checar("clique abre o link em qualquer parte do cartao", len(abertos) == 8, f"{len(abertos)}/8")

    type(cartao).configure = orig
    a.quit()


a.after(1200, etapa)
a.mainloop()
a.destroy()
print("\nRESULTADO:", "tudo passou" if not falhas else f"{len(falhas)} falha(s): {falhas}")
sys.exit(1 if falhas else 0)
