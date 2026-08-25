"""Interface grafica do assistente Moodle (CustomTkinter).

Abre uma janela, busca os dados assim que inicia e re-atualiza sozinha a cada 30 min.
Clicar num cartao de atividade abre ela direto no Moodle.
Feita pra rodar na inicializacao do Windows via atalho na pasta Startup (com pythonw).
"""
import threading
import webbrowser
from datetime import datetime

import customtkinter as ctk

import moodle_core

ATUALIZA_CADA_MS = 30 * 60 * 1000  # 30 minutos

ctk.set_appearance_mode("dark")

C = {
    "fundo": "#12121c",
    "cartao": "#1d1d2b",
    "cartao_hover": "#262638",
    "borda": "#2e2e42",
    "texto": "#eceff4",
    "apagado": "#8b8ba3",
    "azul": "#7aa2f7",
    "vermelho": "#f7768e",
    "laranja": "#ff9e64",
    "verde": "#9ece6a",
    "amarelo": "#e0af68",
}

FONTE = "Segoe UI"


def materia_curta(nome_completo):
    return nome_completo.split("_")[0]


def info_prazo(a, agora):
    """Devolve (texto_do_chip, cor, texto_prazo) pra uma atividade."""
    if not a["duedate"]:
        return "SEM PRAZO", C["apagado"], "sem prazo definido"
    prazo = datetime.fromtimestamp(a["duedate"]).strftime("%d/%m/%Y")
    if a["duedate"] < agora:
        return "VENCIDO", C["vermelho"], prazo
    dias = (a["duedate"] - agora) // 86400
    if dias == 0:
        return "HOJE", C["vermelho"], prazo
    if dias <= 7:
        return f"{dias} DIA{'S' if dias != 1 else ''}", C["laranja"], prazo
    return f"{dias} DIAS", C["verde"], prazo


class Chip(ctk.CTkLabel):
    def __init__(self, master, texto, cor, **kw):
        super().__init__(master, text=texto, font=(FONTE, 11, "bold"),
                         text_color=C["fundo"], fg_color=cor,
                         corner_radius=20, padx=10, pady=2, **kw)


class CartaoAtividade(ctk.CTkFrame):
    def __init__(self, master, atividade, agora):
        super().__init__(master, fg_color=C["cartao"], corner_radius=12,
                         border_width=1, border_color=C["borda"])
        self.url = atividade.get("url")

        chip_txt, cor, prazo_txt = info_prazo(atividade, agora)

        faixa = ctk.CTkFrame(self, fg_color=cor, corner_radius=6, width=5, height=10)
        faixa.pack(side="left", fill="y", padx=(10, 0), pady=10)

        corpo = ctk.CTkFrame(self, fg_color="transparent")
        corpo.pack(side="left", fill="both", expand=True, padx=14, pady=12)

        linha1 = ctk.CTkFrame(corpo, fg_color="transparent")
        linha1.pack(fill="x")
        ctk.CTkLabel(linha1, text=atividade["nome"], font=(FONTE, 14, "bold"),
                     text_color=C["texto"], anchor="w", justify="left").pack(side="left", fill="x", expand=True)
        Chip(linha1, chip_txt, cor).pack(side="right", padx=(10, 0))

        linha2 = ctk.CTkFrame(corpo, fg_color="transparent")
        linha2.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(linha2, text=materia_curta(atividade["materia"]), font=(FONTE, 12),
                     text_color=C["azul"], anchor="w").pack(side="left")
        ctk.CTkLabel(linha2, text="  ·  " + prazo_txt, font=(FONTE, 12),
                     text_color=C["apagado"], anchor="w").pack(side="left")
        status = moodle_core.STATUS_MAP.get(atividade["status"], atividade["status"])
        cor_status = C["verde"] if atividade["status"] == "submitted" else C["apagado"]
        ctk.CTkLabel(linha2, text="  ·  " + status.lower(), font=(FONTE, 12),
                     text_color=cor_status, anchor="w").pack(side="left")

        if self.url:
            self._bind_clique(self)

    def _bind_clique(self, widget):
        widget.bind("<Button-1>", self._abrir)
        widget.bind("<Enter>", lambda e: self.configure(fg_color=C["cartao_hover"], cursor="hand2"))
        widget.bind("<Leave>", lambda e: self.configure(fg_color=C["cartao"], cursor="arrow"))
        for filho in widget.winfo_children():
            self._bind_clique(filho)

    def _abrir(self, _evento=None):
        webbrowser.open(self.url)


class CartaoResumo(ctk.CTkFrame):
    def __init__(self, master, titulo, cor):
        super().__init__(master, fg_color=C["cartao"], corner_radius=12,
                         border_width=1, border_color=C["borda"])
        self.valor = ctk.CTkLabel(self, text="—", font=(FONTE, 26, "bold"), text_color=cor)
        self.valor.pack(pady=(12, 0))
        ctk.CTkLabel(self, text=titulo, font=(FONTE, 12), text_color=C["apagado"]).pack(pady=(0, 12))

    def set(self, texto):
        self.valor.configure(text=str(texto))


class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=C["fundo"])
        self.title("Assistente Moodle - Univassouras")
        # o CTk multiplica a geometria pela escala do Windows; divide antes pra janela caber na tela
        s = ctk.ScalingTracker.get_window_scaling(self)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(1150, sw - 60), min(830, sh - 90)
        x, y = (sw - w) // 2, max(10, (sh - h) // 2 - 10)
        self.geometry(f"{int(w / s)}x{int(h / s)}+{int(x / s)}+{int(y / s)}")
        self.minsize(int(640 / s), int(440 / s))

        # ---- cabecalho ----
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=24, pady=(20, 12))
        titulos = ctk.CTkFrame(topo, fg_color="transparent")
        titulos.pack(side="left")
        ctk.CTkLabel(titulos, text="Assistente Moodle", font=(FONTE, 24, "bold"),
                     text_color=C["texto"], anchor="w").pack(anchor="w")
        ctk.CTkLabel(titulos, text="Univassouras · Engenharia de Software", font=(FONTE, 13),
                     text_color=C["apagado"], anchor="w").pack(anchor="w")

        self.botao = ctk.CTkButton(topo, text="Atualizar", font=(FONTE, 13, "bold"),
                                   fg_color=C["azul"], hover_color="#5d85e6",
                                   text_color=C["fundo"], corner_radius=10,
                                   width=120, height=36, command=self.atualizar)
        self.botao.pack(side="right")
        self.status = ctk.CTkLabel(topo, text="", font=(FONTE, 12), text_color=C["apagado"])
        self.status.pack(side="right", padx=14)

        # ---- cartoes de resumo ----
        resumo = ctk.CTkFrame(self, fg_color="transparent")
        resumo.pack(fill="x", padx=24, pady=(0, 12))
        resumo.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="resumo")
        self.r_pendentes = CartaoResumo(resumo, "pendentes", C["azul"])
        self.r_vencidas = CartaoResumo(resumo, "vencidas", C["vermelho"])
        self.r_proximo = CartaoResumo(resumo, "proximo prazo", C["laranja"])
        self.r_entregues = CartaoResumo(resumo, "entregues", C["verde"])
        for i, cartao in enumerate([self.r_pendentes, self.r_vencidas, self.r_proximo, self.r_entregues]):
            cartao.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))

        # ---- barra de progresso da busca ----
        self.progresso = ctk.CTkProgressBar(self, mode="indeterminate", height=4,
                                            progress_color=C["azul"], fg_color=C["fundo"])

        # ---- abas ----
        self.abas = ctk.CTkTabview(self, fg_color=C["fundo"],
                                   segmented_button_fg_color=C["cartao"],
                                   segmented_button_selected_color=C["azul"],
                                   segmented_button_selected_hover_color="#5d85e6",
                                   segmented_button_unselected_color=C["cartao"],
                                   segmented_button_unselected_hover_color=C["cartao_hover"],
                                   text_color=C["texto"], corner_radius=12)
        self.abas.pack(fill="both", expand=True, padx=16, pady=(4, 16))
        self.abas._segmented_button.configure(font=(FONTE, 13, "bold"))
        for nome in ("Prioridades", "Novidades", "Todas"):
            aba = self.abas.add(nome)
            rolagem = ctk.CTkScrollableFrame(aba, fg_color="transparent")
            rolagem.pack(fill="both", expand=True)
            setattr(self, "aba_" + nome.lower(), rolagem)

        self.erro_label = None
        self.buscando = False
        self.atualizar()
        self.after(ATUALIZA_CADA_MS, self._atualizacao_periodica)

    # ---- busca em thread pra nao travar a janela ----
    def atualizar(self):
        if self.buscando:
            return
        self.buscando = True
        self.botao.configure(state="disabled", text="Atualizando...")
        self.status.configure(text="")
        self.progresso.pack(fill="x", padx=24, before=self.abas)
        self.progresso.start()
        threading.Thread(target=self._buscar, daemon=True).start()

    def _buscar(self):
        try:
            dados = moodle_core.coletar()
            self.after(0, self._mostrar, dados)
        except Exception as e:
            self.after(0, self._mostrar_erro, str(e))

    def _atualizacao_periodica(self):
        self.atualizar()
        self.after(ATUALIZA_CADA_MS, self._atualizacao_periodica)

    def _fim_busca(self):
        self.buscando = False
        self.progresso.stop()
        self.progresso.pack_forget()
        self.botao.configure(state="normal", text="Atualizar")

    def _limpar(self, quadro):
        for filho in quadro.winfo_children():
            filho.destroy()

    def _aviso(self, quadro, texto, cor=None):
        ctk.CTkLabel(quadro, text=texto, font=(FONTE, 13),
                     text_color=cor or C["apagado"]).pack(pady=24)

    # ---- renderizacao ----
    def _mostrar_erro(self, msg):
        self._fim_busca()
        self.status.configure(text="Falha ao atualizar", text_color=C["vermelho"])
        if self.erro_label is None or not self.erro_label.winfo_exists():
            self.erro_label = ctk.CTkLabel(self, text="", font=(FONTE, 12),
                                           text_color=C["vermelho"], wraplength=800)
            self.erro_label.pack(before=self.abas, padx=24, pady=(0, 4))
        self.erro_label.configure(text="ERRO: " + msg)

    def _mostrar(self, dados):
        self._fim_busca()
        if self.erro_label is not None and self.erro_label.winfo_exists():
            self.erro_label.destroy()
        self.status.configure(text="Atualizado as " + datetime.now().strftime("%H:%M"),
                              text_color=C["apagado"])
        agora = dados["agora"]
        atividades = dados["atividades"]
        pendentes = moodle_core.pendentes_ordenadas(atividades)
        vencidas = [p for p in pendentes if p["duedate"] and p["duedate"] < agora]
        entregues = [a for a in atividades if a["status"] == "submitted"]
        com_prazo_futuro = [p for p in pendentes if p["duedate"] and p["duedate"] >= agora]

        self.r_pendentes.set(len(pendentes))
        self.r_vencidas.set(len(vencidas))
        self.r_entregues.set(len(entregues))
        if com_prazo_futuro:
            dias = (com_prazo_futuro[0]["duedate"] - agora) // 86400
            self.r_proximo.set("hoje" if dias == 0 else f"{dias}d")
        else:
            self.r_proximo.set("—")

        self._limpar(self.aba_prioridades)
        if not pendentes:
            self._aviso(self.aba_prioridades, "Nenhuma atividade pendente. Tudo em dia!", C["verde"])
        for p in pendentes:
            CartaoAtividade(self.aba_prioridades, p, agora).pack(fill="x", pady=(0, 8))

        self._limpar(self.aba_novidades)
        if not dados["novidades"]:
            self._aviso(self.aba_novidades, "Nada novo desde a ultima checagem.")
        for nov in dados["novidades"]:
            bloco = ctk.CTkFrame(self.aba_novidades, fg_color=C["cartao"], corner_radius=12,
                                 border_width=1, border_color=C["borda"])
            bloco.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(bloco, text=materia_curta(nov["curso"]), font=(FONTE, 14, "bold"),
                         text_color=C["amarelo"], anchor="w").pack(fill="x", padx=14, pady=(10, 2))
            for nome_mod, descricao in nov["itens"]:
                ctk.CTkLabel(bloco, text=f"•  {nome_mod}  —  {descricao}", font=(FONTE, 12),
                             text_color=C["texto"], anchor="w", justify="left",
                             wraplength=760).pack(fill="x", padx=22, pady=(0, 4))
            ctk.CTkFrame(bloco, fg_color="transparent", height=6).pack()

        self._limpar(self.aba_todas)
        for a in sorted(atividades, key=lambda x: x["duedate"] or float("inf")):
            CartaoAtividade(self.aba_todas, a, agora).pack(fill="x", pady=(0, 8))


if __name__ == "__main__":
    App().mainloop()
