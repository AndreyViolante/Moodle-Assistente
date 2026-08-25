"""Pecas de interface usadas pela janela principal e pela janela de chat."""
import tkinter as tk
from datetime import datetime

import customtkinter as ctk

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
    "roxo": "#bb9af7",
}

FONTE = "Segoe UI"
FONTE_MONO = "Cascadia Mono"


def materia_curta(nome_completo):
    return nome_completo.split("_")[0]


def wrap(pixels, widget):
    """Converte pixels de tela no valor de wraplength do CustomTkinter.

    O CTkLabel multiplica o wraplength pela escala de DPI do Windows, entao
    passar o valor em pixels direto faz o texto quebrar mais largo do que o
    espaco disponivel e sair cortado pela direita.
    """
    escala = ctk.ScalingTracker.get_widget_scaling(widget) or 1.0
    return int(max(120, pixels) / escala)


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


class AreaRolavel(ctk.CTkFrame):
    """Area com rolagem propria.

    Feita no lugar do CTkScrollableFrame, que usa bind_all: com uma aba por
    area, toda rolagem disparava o handler das tres abas e andava so ~20px por
    clique da roda. A barra some quando o conteudo cabe na tela e a posicao e
    presa dentro do conteudo quando ele encolhe (senao a vista fica parada num
    espaco vazio).

    Quem liga a roda do mouse e a janela dona da area: no Windows o Tk entrega
    <MouseWheel> pro widget com FOCO, nao pro que esta sob o cursor, entao a
    ligacao precisa ser global (bind_all) e despachar pra area visivel.
    """

    PASSO = 60  # pixels por clique da roda

    def __init__(self, master, cor_fundo=None):
        super().__init__(master, fg_color="transparent")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(self, bg=cor_fundo or C["fundo"], highlightthickness=0,
                                 bd=0, yscrollincrement=1)
        self._canvas.grid(row=0, column=0, sticky="nsew")

        self._barra = ctk.CTkScrollbar(self, orientation="vertical", width=12,
                                       command=self._canvas.yview, fg_color=C["fundo"],
                                       button_color=C["borda"], button_hover_color=C["azul"])
        self._canvas.configure(yscrollcommand=self._barra.set)
        self._barra_visivel = False

        self.interior = ctk.CTkFrame(self._canvas, fg_color="transparent")
        self._janela = self._canvas.create_window((0, 0), window=self.interior, anchor="nw")

        self._ajuste_pendente = False
        self.interior.bind("<Configure>", self._agendar_ajuste)
        self._canvas.bind("<Configure>", self._canvas_redimensionou)
        self._canvas.bind("<Map>", self._agendar_ajuste)

    # ---- geometria ----
    def _canvas_redimensionou(self, evento):
        self._canvas.itemconfigure(self._janela, width=evento.width)
        self._agendar_ajuste()

    def _agendar_ajuste(self, _evento=None):
        # debounce: mostrar/esconder a barra muda a largura e dispara Configure de novo
        if not self._ajuste_pendente:
            self._ajuste_pendente = True
            self.after_idle(self._ajustar)

    def _ajustar(self):
        self._ajuste_pendente = False
        if not self._canvas.winfo_exists():
            return
        altura = self.interior.winfo_reqheight()
        visivel = self._canvas.winfo_height()
        self._canvas.configure(scrollregion=(0, 0, self._canvas.winfo_width(), altura))
        if visivel <= 1:
            return  # aba ainda sem layout: o <Map> refaz a conta quando ela aparecer

        precisa = altura > visivel + 1
        if precisa and not self._barra_visivel:
            self._barra.grid(row=0, column=1, sticky="ns", padx=(8, 0))
            self._barra_visivel = True
        elif not precisa and self._barra_visivel:
            self._barra.grid_forget()
            self._barra_visivel = False

        if not precisa:
            self._canvas.yview_moveto(0)
        elif self._canvas.canvasy(0) > altura - visivel:
            self._canvas.yview_moveto((altura - visivel) / altura)

    # ---- rolagem ----
    def rolar(self, delta):
        """Um clique da roda = PASSO pixels. Quem chama e o handler global da janela."""
        if self._barra_visivel:
            self._canvas.yview_scroll(int(-delta / 120 * self.PASSO), "units")

    def rolar_paginas(self, quantas):
        if self._barra_visivel:
            self._canvas.yview_scroll(int(quantas * self._canvas.winfo_height() * 0.9), "units")

    def ir_para(self, fracao):
        self._canvas.yview_moveto(fracao)

    def ir_para_o_fim(self):
        self._ajustar()
        self._canvas.yview_moveto(1.0)

    def limpar(self):
        for filho in self.interior.winfo_children():
            filho.destroy()

    def finalizar(self):
        """Chamado depois de montar o conteudo."""
        self._agendar_ajuste()
