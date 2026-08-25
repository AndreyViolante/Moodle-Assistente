"""Interface grafica do assistente Moodle (CustomTkinter).

Abre uma janela, busca os dados assim que inicia e re-atualiza sozinha a cada 30 min.
Clicar num cartao de atividade abre ela direto no Moodle.
Feita pra rodar na inicializacao do Windows via atalho na pasta Startup (com pythonw).
"""
import queue
import threading
import tkinter as tk
import webbrowser
from datetime import datetime

import customtkinter as ctk

import moodle_core
import notificacoes

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


class AreaRolavel(ctk.CTkFrame):
    """Area com rolagem propria.

    Feita no lugar do CTkScrollableFrame, que usa bind_all: com uma aba por
    area, toda rolagem disparava o handler das tres abas e andava so ~20px por
    clique da roda. Aqui a roda e ligada so nos widgets desta area, a barra
    some quando o conteudo cabe na tela e a posicao e presa dentro do conteudo
    quando ele encolhe (senao a vista fica parada num espaco vazio).
    """

    PASSO = 60  # pixels por clique da roda

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(self, bg=C["fundo"], highlightthickness=0, bd=0,
                                 yscrollincrement=1)
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

    # ---- roda do mouse ----
    def rolar(self, delta):
        """Um clique da roda = PASSO pixels. Quem chama e o handler global do App."""
        if self._barra_visivel:
            self._canvas.yview_scroll(int(-delta / 120 * self.PASSO), "units")

    def rolar_paginas(self, quantas):
        if self._barra_visivel:
            self._canvas.yview_scroll(int(quantas * self._canvas.winfo_height() * 0.9), "units")

    def ir_para(self, fracao):
        self._canvas.yview_moveto(fracao)

    def limpar(self):
        for filho in self.interior.winfo_children():
            filho.destroy()

    def finalizar(self):
        """Chamado depois de montar o conteudo."""
        self._agendar_ajuste()


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
        self.areas = {}
        for nome in ("Prioridades", "Novidades", "Todas"):
            area = AreaRolavel(self.abas.add(nome))
            area.pack(fill="both", expand=True)
            self.areas[nome] = area
            setattr(self, "aba_" + nome.lower(), area)

        # No Windows o Tk entrega a roda pro widget com FOCO, nao pro que esta
        # sob o cursor - e o foco fica no toplevel. Por isso a ligacao tem que
        # ser global (bind_all) e despachar pra aba visivel; ligar nos widgets
        # do conteudo simplesmente nao recebe nada.
        tk.Misc.bind_all(self, "<MouseWheel>", self._roda_global)
        for tecla, acao in (("<Prior>", lambda a: a.rolar_paginas(-1)),
                            ("<Next>", lambda a: a.rolar_paginas(1)),
                            ("<Home>", lambda a: a.ir_para(0)),
                            ("<End>", lambda a: a.ir_para(1))):
            self.bind(tecla, lambda e, f=acao: f(self._area_visivel()))

        self.erro_label = None
        self.buscando = False
        self._fila = queue.Queue()
        self._checar_fila()
        self.atualizar()
        self.after(ATUALIZA_CADA_MS, self._atualizacao_periodica)

    def _area_visivel(self):
        return self.areas[self.abas.get()]

    def _roda_global(self, evento):
        self._area_visivel().rolar(evento.delta)
        return "break"

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
        # so entrega o resultado pela fila: mexer no Tk fora da thread principal
        # (inclusive com after) pode quebrar o interpretador num app que fica dias ligado
        try:
            self._fila.put(("ok", moodle_core.coletar()))
        except Exception as e:
            self._fila.put(("erro", str(e)))

    def _checar_fila(self):
        try:
            while True:
                tipo, carga = self._fila.get_nowait()
                self._mostrar(carga) if tipo == "ok" else self._mostrar_erro(carga)
        except queue.Empty:
            pass
        self.after(150, self._checar_fila)

    def _atualizacao_periodica(self):
        self.atualizar()
        self.after(ATUALIZA_CADA_MS, self._atualizacao_periodica)

    def _fim_busca(self):
        self.buscando = False
        self.progresso.stop()
        self.progresso.pack_forget()
        self.botao.configure(state="normal", text="Atualizar")

    def _aviso(self, area, texto, cor=None):
        ctk.CTkLabel(area.interior, text=texto, font=(FONTE, 13),
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
        notificacoes.processar(dados, pendentes)

        self.r_pendentes.set(len(pendentes))
        self.r_vencidas.set(len(vencidas))
        self.r_entregues.set(len(entregues))
        if com_prazo_futuro:
            dias = (com_prazo_futuro[0]["duedate"] - agora) // 86400
            self.r_proximo.set("hoje" if dias == 0 else f"{dias}d")
        else:
            self.r_proximo.set("—")

        self.aba_prioridades.limpar()
        if not pendentes:
            self._aviso(self.aba_prioridades, "Nenhuma atividade pendente. Tudo em dia!", C["verde"])
        for p in pendentes:
            CartaoAtividade(self.aba_prioridades.interior, p, agora).pack(fill="x", pady=(0, 8))
        self.aba_prioridades.finalizar()

        self.aba_novidades.limpar()
        if not dados["novidades"]:
            self._aviso(self.aba_novidades, "Nada novo desde a ultima checagem.")
        for nov in dados["novidades"]:
            bloco = ctk.CTkFrame(self.aba_novidades.interior, fg_color=C["cartao"], corner_radius=12,
                                 border_width=1, border_color=C["borda"])
            bloco.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(bloco, text=materia_curta(nov["curso"]), font=(FONTE, 14, "bold"),
                         text_color=C["amarelo"], anchor="w").pack(fill="x", padx=14, pady=(10, 2))
            for nome_mod, descricao in nov["itens"]:
                ctk.CTkLabel(bloco, text=f"•  {nome_mod}  —  {descricao}", font=(FONTE, 12),
                             text_color=C["texto"], anchor="w", justify="left",
                             wraplength=760).pack(fill="x", padx=22, pady=(0, 4))
            ctk.CTkFrame(bloco, fg_color="transparent", height=6).pack()
        self.aba_novidades.finalizar()

        self.aba_todas.limpar()
        for a in sorted(atividades, key=lambda x: x["duedate"] or float("inf")):
            CartaoAtividade(self.aba_todas.interior, a, agora).pack(fill="x", pady=(0, 8))
        self.aba_todas.finalizar()


if __name__ == "__main__":
    App().mainloop()
