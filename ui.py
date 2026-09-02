"""Pecas de interface usadas pela janela principal e pela janela de chat.

A paleta e proposital: cinzas neutros e cores dessaturadas. Cor aqui e
informacao (o quao perto esta o prazo), nao enfeite - por isso nada de fundo
colorido, badge chapado ou numero gigante.
"""
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime

import customtkinter as ctk

C = {
    "fundo": "#1b1b1e",        # fundo da janela
    "superficie": "#212126",   # blocos e linha sob o cursor
    "superficie2": "#26262c",  # hover mais forte
    "linha": "#2d2d33",        # fio de separacao
    "texto": "#e6e6e8",
    "texto2": "#a0a0a8",       # secundario (materia, data)
    "texto3": "#6c6c75",       # terciario (rotulos de secao)
    "acento": "#5e8fd0",
    "vencido": "#cf6a5c",
    "urgente": "#c8914e",
    "ok": "#6d9a63",
    "destaque": "#a98ac2",
}

FONTE = "Segoe UI"
FONTE_MONO = "Cascadia Mono"

# tamanhos em um lugar so, pra hierarquia ficar coerente entre as janelas
T_TITULO = 13
T_CORPO = 12
T_MIUDO = 11
T_SECAO = 10


def materia_curta(nome_completo):
    return nome_completo.split("_")[0]


def wrap(pixels, widget):
    """Converte pixels de tela no valor de wraplength do CustomTkinter.

    O CTkLabel multiplica o wraplength pela escala de DPI do Windows, entao
    passar o valor em pixels direto faz o texto quebrar mais largo que o
    espaco disponivel e sair cortado pela direita.
    """
    escala = ctk.ScalingTracker.get_widget_scaling(widget) or 1.0
    return int(max(120, pixels) / escala)


_fontes = {}


def fonte_medida(tamanho, peso="normal"):
    """Font do Tk (com cache) so pra medir texto em pixels."""
    chave = (tamanho, peso)
    if chave not in _fontes:
        _fontes[chave] = tkfont.Font(family=FONTE, size=tamanho, weight=peso)
    return _fontes[chave]


def encurtar(texto, fonte, limite_px):
    """Corta com reticencias no fim, medindo a fonte de verdade.

    O Tk nao encurta sozinho: sem isso o texto so seria cortado no meio de uma
    letra quando faltasse espaco.
    """
    if limite_px <= 0 or fonte.measure(texto) <= limite_px:
        return texto
    reticencias = fonte.measure("…")
    baixo, alto = 0, len(texto)
    while baixo < alto:
        meio = (baixo + alto + 1) // 2
        if fonte.measure(texto[:meio]) + reticencias <= limite_px:
            baixo = meio
        else:
            alto = meio - 1
    return texto[:baixo].rstrip() + "…" if baixo else "…"


def info_prazo(a, agora):
    """Devolve (relativo, cor, data, urgencia) pra uma atividade.

    O relativo ("em 3 dias", "ontem") e o que a pessoa quer saber; a data
    exata fica ao lado, discreta. Prazo longe nao ganha cor: so o que exige
    acao chama atencao.
    """
    if not a.get("duedate"):
        return "sem prazo", C["texto3"], "", "sem"

    data = datetime.fromtimestamp(a["duedate"]).strftime("%d/%m")
    dias = (a["duedate"] - agora) // 86400
    if a["duedate"] < agora:
        atraso = max(1, (agora - a["duedate"]) // 86400)
        rel = "ontem" if atraso == 1 else f"ha {atraso} dias"
        return rel, C["vencido"], data, "vencido"
    if dias == 0:
        return "hoje", C["vencido"], data, "hoje"
    if dias == 1:
        return "amanha", C["urgente"], data, "urgente"
    if dias <= 7:
        return f"em {dias} dias", C["urgente"], data, "urgente"
    if dias <= 30:
        return f"em {dias} dias", C["texto2"], data, "longe"
    return "", C["texto2"], datetime.fromtimestamp(a["duedate"]).strftime("%d/%m/%y"), "longe"


def fio(master, cor=None):
    """Linha de 1px pra separar conteudo sem precisar de caixa em volta.

    tk.Frame, e nao CTkFrame: o CTkFrame desenha o fundo como retangulo no
    canvas interno e com 1px de altura nao sai nada na tela. Alem disso ele
    nasce com 200px de largura e empurraria o quadro que o contem.
    """
    return tk.Frame(master, height=1, width=1, bg=cor or C["linha"])


class RotuloSecao(ctk.CTkFrame):
    """Cabecalho de grupo: 'ATRASADAS   2'."""

    def __init__(self, master, texto, quantidade=None):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(self, text=texto.upper(), font=(FONTE, T_SECAO, "bold"), height=14,
                     text_color=C["texto3"], anchor="w").pack(side="left")
        if quantidade is not None:
            ctk.CTkLabel(self, text=str(quantidade), font=(FONTE, T_SECAO), height=14,
                         text_color=C["texto3"], anchor="e").pack(side="right")


class BotaoTexto(ctk.CTkButton):
    """Botao sem caixa: so o texto, que acende ao passar o mouse."""

    def __init__(self, master, texto, comando, cor=None, **kw):
        super().__init__(master, text=texto, command=comando,
                         font=kw.pop("font", (FONTE, T_CORPO)),
                         fg_color="transparent", hover_color=C["superficie2"],
                         text_color=cor or C["texto2"], corner_radius=6,
                         height=kw.pop("height", 26), width=kw.pop("width", 1), **kw)


class Abas(ctk.CTkFrame):
    """Abas de texto com sublinhado, no lugar do botao segmentado.

    Expoe get()/set() como o CTkTabview, que e o que o resto do codigo usa.
    """

    def __init__(self, master, nomes, ao_trocar=None):
        super().__init__(master, fg_color="transparent")
        self._ao_trocar = ao_trocar
        self._atual = nomes[0]
        self._itens = {}
        for nome in nomes:
            quadro = ctk.CTkFrame(self, fg_color="transparent")
            quadro.pack(side="left", padx=(0, 18))
            rot = ctk.CTkLabel(quadro, text=nome, font=(FONTE, T_CORPO), height=18,
                               text_color=C["texto2"], cursor="hand2")
            rot.pack()
            # tk.Frame: CTkFrame de 2px nao aparece, e os 200px padrao dele
            # ainda espalhariam as abas pela largura toda
            risco = tk.Frame(quadro, height=2, width=1, bg=C["fundo"])
            risco.pack(fill="x", pady=(5, 0))
            self._itens[nome] = (rot, risco)
            for w in (quadro, rot):
                tk.Misc.bind(w, "<Button-1>", lambda e, n=nome: self.set(n))
        self._pintar()

    def _pintar(self):
        for nome, (rot, risco) in self._itens.items():
            ativa = nome == self._atual
            rot.configure(text_color=C["texto"] if ativa else C["texto2"])
            risco.configure(bg=C["acento"] if ativa else C["fundo"])

    def get(self):
        return self._atual

    def set(self, nome):
        if nome not in self._itens or nome == self._atual:
            return
        self._atual = nome
        self._pintar()
        if self._ao_trocar:
            self._ao_trocar(nome)


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

        # a barra fica sempre no layout, so muda de cor quando nao e necessaria:
        # esconder com grid_forget deixava um risco de 1px na direita (o widget
        # continuava mapeado) e ainda fazia o conteudo pular de largura
        self._cor_fundo = cor_fundo or C["fundo"]
        self._barra = ctk.CTkScrollbar(self, orientation="vertical", width=10,
                                       command=self._canvas.yview, fg_color="transparent",
                                       button_color=self._cor_fundo,
                                       button_hover_color=self._cor_fundo)
        self._barra.grid(row=0, column=1, sticky="ns", padx=(6, 0))
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
        if precisa != self._barra_visivel:
            self._barra_visivel = precisa
            self._barra.configure(
                button_color=C["linha"] if precisa else self._cor_fundo,
                button_hover_color=C["texto3"] if precisa else self._cor_fundo)

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
        """Page Up/Down. Se a aba acabou de aparecer o canvas ainda pode estar
        sem altura; nesse caso rola um tanto fixo em vez de nao rolar nada."""
        if not self._barra_visivel:
            return
        altura = self._canvas.winfo_height()
        if altura <= 1:
            altura = 400
        self._canvas.yview_scroll(int(quantas * altura * 0.9), "units")

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
