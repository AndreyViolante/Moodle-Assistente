"""Interface grafica do assistente Moodle.

Abre uma janela, busca os dados assim que inicia e re-atualiza sozinha a cada 30 min.
Feita pra rodar na inicializacao do Windows via atalho na pasta Startup (com pythonw).
"""
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk

import moodle_core

ATUALIZA_CADA_MS = 30 * 60 * 1000  # 30 minutos

CORES = {
    "fundo": "#1e1e2e",
    "painel": "#27273a",
    "texto": "#e6e6f0",
    "apagado": "#8f8fa8",
    "titulo": "#89b4fa",
    "vencido": "#f38ba8",
    "urgente": "#fab387",
    "ok": "#a6e3a1",
    "novidade": "#f9e2af",
}


def materia_curta(nome_completo):
    # "Arquitetura e Projeto de Software_Eng.Soft06_A_N_M_991193_20262" -> so a parte antes do "_"
    return nome_completo.split("_")[0]


class App:
    def __init__(self, root):
        self.root = root
        root.title("Assistente Moodle - Univassouras")
        root.geometry("760x680")
        root.configure(bg=CORES["fundo"])
        root.minsize(560, 400)

        topo = tk.Frame(root, bg=CORES["fundo"])
        topo.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(topo, text="Assistente Moodle", font=("Segoe UI", 16, "bold"),
                 bg=CORES["fundo"], fg=CORES["texto"]).pack(side="left")
        self.botao = tk.Button(topo, text="Atualizar agora", command=self.atualizar,
                               font=("Segoe UI", 10), bg=CORES["painel"], fg=CORES["texto"],
                               activebackground=CORES["titulo"], activeforeground=CORES["fundo"],
                               relief="flat", padx=12, pady=4, cursor="hand2")
        self.botao.pack(side="right")
        self.status = tk.Label(topo, text="", font=("Segoe UI", 9),
                               bg=CORES["fundo"], fg=CORES["apagado"])
        self.status.pack(side="right", padx=10)

        corpo = tk.Frame(root, bg=CORES["fundo"])
        corpo.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.texto = tk.Text(corpo, wrap="word", bg=CORES["painel"], fg=CORES["texto"],
                             font=("Segoe UI", 10), relief="flat", padx=14, pady=12,
                             cursor="arrow", state="disabled",
                             selectbackground=CORES["titulo"], insertbackground=CORES["texto"])
        barra = ttk.Scrollbar(corpo, orient="vertical", command=self.texto.yview)
        self.texto.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        self.texto.pack(side="left", fill="both", expand=True)

        t = self.texto
        t.tag_configure("secao", font=("Segoe UI", 12, "bold"), foreground=CORES["titulo"],
                        spacing1=14, spacing3=4)
        t.tag_configure("vencido", foreground=CORES["vencido"], font=("Segoe UI", 10, "bold"))
        t.tag_configure("urgente", foreground=CORES["urgente"], font=("Segoe UI", 10, "bold"))
        t.tag_configure("ok", foreground=CORES["ok"])
        t.tag_configure("nome", font=("Segoe UI", 10, "bold"))
        t.tag_configure("apagado", foreground=CORES["apagado"])
        t.tag_configure("novidade", foreground=CORES["novidade"])
        t.tag_configure("erro", foreground=CORES["vencido"], font=("Segoe UI", 10, "bold"))

        self.buscando = False
        self.atualizar()
        self.root.after(ATUALIZA_CADA_MS, self._atualizacao_periodica)

    # ---- busca em thread pra nao travar a janela ----
    def atualizar(self):
        if self.buscando:
            return
        self.buscando = True
        self.botao.configure(state="disabled")
        self.status.configure(text="Atualizando...")
        threading.Thread(target=self._buscar, daemon=True).start()

    def _buscar(self):
        try:
            dados = moodle_core.coletar()
            self.root.after(0, self._mostrar, dados)
        except Exception as e:
            self.root.after(0, self._mostrar_erro, str(e))

    def _atualizacao_periodica(self):
        self.atualizar()
        self.root.after(ATUALIZA_CADA_MS, self._atualizacao_periodica)

    # ---- renderizacao ----
    def _fim_busca(self):
        self.buscando = False
        self.botao.configure(state="normal")
        self.status.configure(text="Atualizado as " + datetime.now().strftime("%H:%M"))

    def _mostrar_erro(self, msg):
        self.buscando = False
        self.botao.configure(state="normal")
        self.status.configure(text="Falha ao atualizar")
        t = self.texto
        t.configure(state="normal")
        t.insert("1.0", "ERRO: " + msg + "\n\n", "erro")
        t.configure(state="disabled")

    def _mostrar(self, dados):
        self._fim_busca()
        agora = dados["agora"]
        t = self.texto
        t.configure(state="normal")
        t.delete("1.0", "end")

        t.insert("end", "Prioridades de estudo\n", "secao")
        pendentes = moodle_core.pendentes_ordenadas(dados["atividades"])
        if not pendentes:
            t.insert("end", "Nenhuma atividade pendente. \n", "ok")
        for p in pendentes:
            if p["duedate"]:
                dias = (p["duedate"] - agora) // 86400
                prazo = datetime.fromtimestamp(p["duedate"]).strftime("%d/%m/%Y")
                if p["duedate"] < agora:
                    t.insert("end", "  [VENCIDO] ", "vencido")
                elif dias <= 7:
                    t.insert("end", f"  [faltam {dias} dia{'s' if dias != 1 else ''}] ", "urgente")
                else:
                    t.insert("end", f"  [{prazo}] ", "ok")
            else:
                prazo = "sem prazo"
                t.insert("end", "  [sem prazo] ", "apagado")
            t.insert("end", p["nome"], "nome")
            t.insert("end", f"\n      {materia_curta(p['materia'])}  -  prazo: {prazo}\n", "apagado")

        t.insert("end", "Novidades\n", "secao")
        if not dados["novidades"]:
            t.insert("end", "  Nada novo desde a ultima checagem.\n", "apagado")
        for nov in dados["novidades"]:
            t.insert("end", "  " + materia_curta(nov["curso"]) + "\n", "nome")
            for nome_mod, descricao in nov["itens"]:
                t.insert("end", f"      - {nome_mod}: ", "novidade")
                t.insert("end", descricao + "\n")

        t.insert("end", "Todas as atividades\n", "secao")
        for a in dados["atividades"]:
            prazo = datetime.fromtimestamp(a["duedate"]).strftime("%d/%m/%Y") if a["duedate"] else "sem prazo"
            status = moodle_core.STATUS_MAP.get(a["status"], a["status"])
            tag_status = "ok" if a["status"] == "submitted" else "vencido"
            t.insert("end", "  " + a["nome"], "nome")
            t.insert("end", f"  ({materia_curta(a['materia'])})\n", "apagado")
            t.insert("end", "      " + status, tag_status)
            t.insert("end", f"  -  prazo: {prazo}\n", "apagado")

        t.configure(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
