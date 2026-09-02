"""Interface grafica do assistente Moodle.

Abre uma janela, busca os dados assim que inicia e re-atualiza sozinha a cada
30 min. Feita pra rodar na inicializacao do Windows via atalho na pasta
Startup (com pythonw).

A tela e uma lista, nao um painel: o que importa e ler rapido o que falta
entregar e em quanto tempo. Por isso linha fina agrupada por urgencia, cor so
no prazo, e nada de numero grande em caixa.
"""
import ctypes
import os
import queue
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime

import customtkinter as ctk

import moodle_core
import notificacoes
from janela_chat import JanelaChat
from ui import (C, FONTE, T_CORPO, T_MIUDO, T_TITULO, Abas, AreaRolavel, BotaoTexto,
                RotuloSecao, fio, info_prazo, materia_curta, wrap)

ATUALIZA_CADA_MS = 30 * 60 * 1000  # 30 minutos
ICONE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icone.ico")

# sem isso a barra de tarefas mostra o icone generico do Python, e nao o nosso
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AndreyViolante.AssistenteMoodle")
except Exception:
    pass

ctk.set_appearance_mode("dark")

# grupos da aba Prioridades, na ordem em que aparecem
GRUPOS = [("vencido", "Atrasadas"), ("hoje", "Hoje"), ("urgente", "Esta semana"),
          ("longe", "Mais pra frente"), ("sem", "Sem prazo")]


class LinhaAtividade(ctk.CTkFrame):
    """Uma atividade na lista: nome, materia e prazo, em duas linhas.

    Sem caixa nem borda - o que separa uma da outra e um fio de 1px e o
    espacamento. Cabe mais coisa na tela e nada disputa atencao com o prazo.
    """

    ALTURA = 26  # marcador lateral; a linha cresce com o texto

    def __init__(self, master, atividade, agora, ocultar_sem_prazo=False):
        super().__init__(master, fg_color="transparent", corner_radius=4)
        self.atividade = atividade
        self.url = atividade.get("url")
        self._conferindo = False
        self._cor = "transparent"

        rel, cor, data, urgencia = info_prazo(atividade, agora)
        entregue = atividade.get("status") == "submitted"

        # marcador fino, so quando ha o que fazer: atrasada ou vencendo.
        # tk.Frame porque CTkFrame com 2px de largura nao desenha nada.
        self._cor_marcador = (cor if urgencia in ("vencido", "hoje", "urgente")
                              and not entregue else None)
        self._marcador = tk.Frame(self, width=2, height=self.ALTURA,
                                  bg=self._cor_marcador or C["fundo"])
        self._marcador.pack(side="left", fill="y", padx=(0, 12), pady=7)

        if urgencia == "sem" and ocultar_sem_prazo:
            rel = ""  # na aba Prioridades a secao ja se chama "Sem prazo"
        # so cria a coluna do prazo se houver o que mostrar: CTkFrame vazio
        # assume os 200x200 padrao e transforma a linha num bloco enorme
        if rel or data:
            prazo = ctk.CTkFrame(self, fg_color="transparent", width=1, height=1)
            prazo.pack(side="right", padx=(12, 12), pady=7)
            if rel:
                ctk.CTkLabel(prazo, text=rel, font=(FONTE, T_MIUDO), height=15,
                             text_color=C["texto3"] if entregue else cor,
                             anchor="e").pack(anchor="e")
            if data:
                ctk.CTkLabel(prazo, text=data, font=(FONTE, T_MIUDO), height=15,
                             text_color=C["texto3"], anchor="e").pack(anchor="e")

        corpo = ctk.CTkFrame(self, fg_color="transparent")
        corpo.pack(side="left", fill="x", expand=True, pady=(7, 8))
        linha1 = ctk.CTkFrame(corpo, fg_color="transparent")
        linha1.pack(fill="x")
        if entregue:
            ctk.CTkLabel(linha1, text="✓", font=(FONTE, T_CORPO), height=18,
                         text_color=C["ok"], width=14).pack(side="left", padx=(0, 4))
        self.rot_nome = ctk.CTkLabel(
            linha1, text=atividade["nome"], font=(FONTE, T_TITULO), height=18,
            text_color=C["texto3"] if entregue else C["texto"], anchor="w", justify="left")
        self.rot_nome.pack(side="left", fill="x", expand=True)

        rodape = materia_curta(atividade["materia"])
        if atividade.get("anexos"):
            n = len(atividade["anexos"])
            rodape += f"   ·   {n} anexo" + ("s" if n > 1 else "")
        ctk.CTkLabel(corpo, text=rodape, font=(FONTE, T_MIUDO), height=15,
                     text_color=C["texto2"], anchor="w").pack(fill="x", pady=(1, 0))

        self._ligar(self)

    def ajustar_largura(self, px):
        self.rot_nome.configure(wraplength=wrap(px, self))

    # ---- clique e hover ----
    def _ligar(self, widget):
        # tk.Misc.bind porque o bind() do CustomTkinter desvia pros widgets
        # internos e deixa buracos: parte da linha ficaria sem responder
        tk.Misc.bind(widget, "<Button-1>", self._abrir)
        tk.Misc.bind(widget, "<Button-3>", self._abrir_no_ava)
        tk.Misc.bind(widget, "<Enter>", self._entrou)
        tk.Misc.bind(widget, "<Leave>", self._saiu)
        tk.Misc.configure(widget, cursor="hand2")  # uma vez so, nao a cada hover
        for filho in widget.winfo_children():
            self._ligar(filho)

    def _entrou(self, _e=None):
        self._pintar(C["superficie"])

    def _saiu(self, _e=None):
        # Leave dispara ao passar pra um filho; so apaga se o mouse saiu mesmo
        if not self._conferindo:
            self._conferindo = True
            self.after(30, self._conferir_saida)

    def _conferir_saida(self):
        self._conferindo = False
        if not self.winfo_exists():
            return
        x, y = self.winfo_pointerxy()
        dentro = (self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width()
                  and self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height())
        self._pintar(C["superficie"] if dentro else "transparent")

    def _pintar(self, cor):
        if cor != self._cor and self.winfo_exists():
            self._cor = cor
            self.configure(fg_color=cor)
            # o marcador e tk.Frame e nao herda fundo transparente: sem isso
            # sobra um risco da cor errada na linha sob o cursor
            if self._cor_marcador is None:
                self._marcador.configure(
                    bg=C["superficie"] if cor != "transparent" else C["fundo"])

    def _abrir(self, _e=None):
        self.winfo_toplevel().abrir_chat(self.atividade)

    def _abrir_no_ava(self, _e=None):
        if self.url:
            webbrowser.open(self.url)
        return "break"


class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=C["fundo"])
        self.title("Assistente Moodle")
        self._aplicar_icone()
        s = ctk.ScalingTracker.get_window_scaling(self)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(880, sw - 60), min(760, sh - 90)
        x, y = (sw - w) // 2, max(10, (sh - h) // 2 - 10)
        self.geometry(f"{int(w / s)}x{int(h / s)}+{int(x / s)}+{int(y / s)}")
        self.minsize(int(520 / s), int(400 / s))

        # ---- barra unica no topo: abas a esquerda, estado a direita ----
        topo = ctk.CTkFrame(self, fg_color="transparent", height=38)
        topo.pack(fill="x", padx=18, pady=(12, 0))
        self.abas = Abas(topo, ["Prioridades", "Novidades", "Todas"], self._trocar_aba)
        self.abas.pack(side="left")
        self.botao = BotaoTexto(topo, "Atualizar", self.atualizar)
        self.botao.pack(side="right")
        self.status = ctk.CTkLabel(topo, text="", font=(FONTE, T_MIUDO), text_color=C["texto3"])
        self.status.pack(side="right", padx=(0, 12))

        fio(self).pack(fill="x", padx=18, pady=(0, 0))

        self.progresso = ctk.CTkProgressBar(self, mode="indeterminate", height=2,
                                            progress_color=C["acento"], fg_color=C["fundo"],
                                            corner_radius=0)

        # ---- conteudo: uma area de rolagem por aba, empilhadas ----
        self.corpo = ctk.CTkFrame(self, fg_color="transparent")
        self.corpo.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self.areas = {}
        for nome in ("Prioridades", "Novidades", "Todas"):
            self.areas[nome] = AreaRolavel(self.corpo)
            setattr(self, "aba_" + nome.lower(), self.areas[nome])
        self.areas["Prioridades"].pack(fill="both", expand=True)

        # No Windows o Tk entrega a roda pro widget com FOCO, nao pro que esta
        # sob o cursor - e o foco fica no toplevel. Por isso a ligacao tem que
        # ser global (bind_all) e despachar pra janela/aba certa.
        tk.Misc.bind_all(self, "<MouseWheel>", self._roda_global)
        for tecla, acao in (("<Prior>", lambda a: a.rolar_paginas(-1)),
                            ("<Next>", lambda a: a.rolar_paginas(1)),
                            ("<Home>", lambda a: a.ir_para(0)),
                            ("<End>", lambda a: a.ir_para(1))):
            self.bind(tecla, lambda e, f=acao: f(self._area_visivel()))
        self.bind("<F5>", lambda e: self.atualizar())
        self.bind("<Configure>", self._largura_mudou)

        self.erro_label = None
        self.buscando = False
        self._chats = {}
        self._agora = int(time.time())
        self._dados = None
        self._linhas = []
        self._fila = queue.Queue()
        self._checar_fila()
        self.atualizar()
        self.after(ATUALIZA_CADA_MS, self._atualizacao_periodica)

    def _aplicar_icone(self):
        if not os.path.exists(ICONE):
            return
        try:
            self.iconbitmap(ICONE)
            # o CustomTkinter repoe o icone dele depois que a janela abre
            self.after(300, lambda: self.iconbitmap(ICONE))
        except Exception:
            pass

    # ---- navegacao ----
    def _area_visivel(self):
        return self.areas[self.abas.get()]

    def _trocar_aba(self, nome):
        for chave, area in self.areas.items():
            if chave == nome:
                area.pack(fill="both", expand=True)
            else:
                area.pack_forget()

    def _roda_global(self, evento):
        # bind_all vale pra aplicacao toda, entao aqui decidimos qual janela
        # rola: as de chat expoem area_rolavel; a principal usa a aba visivel
        try:
            topo = evento.widget.winfo_toplevel()
        except Exception:
            topo = self
        area = getattr(topo, "area_rolavel", None) or self._area_visivel()
        area.rolar(evento.delta)
        return "break"

    def _largura_mudou(self, evento):
        if evento.widget is not self:
            return
        largura = max(240, evento.width - 260)
        if abs(largura - getattr(self, "_ultima_largura", 0)) < 16:
            return
        self._ultima_largura = largura
        for linha in self._linhas:
            if linha.winfo_exists():
                linha.ajustar_largura(largura)

    def abrir_chat(self, atividade):
        """Abre (ou traz pra frente) a janela de chat da atividade."""
        chave = atividade["nome"] + "|" + atividade["materia"]
        janela = self._chats.get(chave)
        if janela is not None and janela.winfo_exists():
            janela.deiconify()
            janela.lift()
            janela.focus_force()
            return janela
        janela = JanelaChat(self, atividade, self._agora,
                            icone=ICONE if os.path.exists(ICONE) else None)
        self._chats[chave] = janela
        return janela

    # ---- busca em thread pra nao travar a janela ----
    def atualizar(self):
        if self.buscando:
            return
        self.buscando = True
        self.botao.configure(state="disabled", text="Atualizando")
        self.status.configure(text="")
        self.progresso.pack(fill="x", before=self.corpo)
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

    # ---- montagem da lista ----
    def _vazio(self, area, texto):
        ctk.CTkLabel(area.interior, text=texto, font=(FONTE, T_CORPO),
                     text_color=C["texto3"]).pack(pady=40)

    def _linha(self, area, atividade, ocultar_sem_prazo=False):
        linha = LinhaAtividade(area.interior, atividade, self._agora, ocultar_sem_prazo)
        if getattr(self, "_ultima_largura", 0):
            linha.ajustar_largura(self._ultima_largura)
        linha.pack(fill="x")
        self._linhas.append(linha)
        return linha

    def _mostrar_erro(self, msg):
        self._fim_busca()
        self.status.configure(text="falhou", text_color=C["vencido"])
        if self.erro_label is None or not self.erro_label.winfo_exists():
            self.erro_label = ctk.CTkLabel(self, text="", font=(FONTE, T_MIUDO),
                                           text_color=C["vencido"], wraplength=800)
            self.erro_label.pack(before=self.corpo, padx=18, pady=(6, 0))
        self.erro_label.configure(text=msg)

    def _mostrar(self, dados):
        self._fim_busca()
        self._dados = dados
        self._agora = dados["agora"]
        self._linhas = []
        if self.erro_label is not None and self.erro_label.winfo_exists():
            self.erro_label.destroy()
        self.status.configure(text=datetime.now().strftime("%H:%M"), text_color=C["texto3"])

        atividades = dados["atividades"]
        pendentes = moodle_core.pendentes_ordenadas(atividades)
        notificacoes.processar(dados, pendentes)

        # ---- Prioridades: agrupadas por urgencia ----
        area = self.areas["Prioridades"]
        area.limpar()
        if not pendentes:
            self._vazio(area, "Nada pendente. Tudo entregue.")
        else:
            por_grupo = {}
            for p in pendentes:
                por_grupo.setdefault(info_prazo(p, self._agora)[3], []).append(p)
            primeiro = True
            for chave, titulo in GRUPOS:
                itens = por_grupo.get(chave)
                if not itens:
                    continue
                cab = RotuloSecao(area.interior, titulo, len(itens))
                cab.pack(fill="x", pady=(0 if primeiro else 20, 6), padx=2)
                primeiro = False
                for i, p in enumerate(itens):
                    if i:
                        fio(area.interior).pack(fill="x", padx=14)
                    self._linha(area, p, ocultar_sem_prazo=True)
        area.finalizar()

        # ---- Novidades ----
        area = self.areas["Novidades"]
        area.limpar()
        if not dados["novidades"]:
            self._vazio(area, "Nada novo desde a ultima checagem.")
        for i, nov in enumerate(dados["novidades"]):
            RotuloSecao(area.interior, materia_curta(nov["curso"])).pack(
                fill="x", pady=(0 if not i else 20, 6), padx=2)
            for nome_mod, descricao in nov["itens"]:
                item = ctk.CTkFrame(area.interior, fg_color="transparent")
                item.pack(fill="x", pady=1)
                ctk.CTkLabel(item, text=nome_mod, font=(FONTE, T_CORPO),
                             text_color=C["texto"], anchor="w").pack(side="left", padx=(14, 0))
                ctk.CTkLabel(item, text=descricao, font=(FONTE, T_MIUDO),
                             text_color=C["destaque"], anchor="e").pack(side="right", padx=(0, 12))
        area.finalizar()

        # ---- Todas: pendentes e entregues separadas ----
        area = self.areas["Todas"]
        area.limpar()
        entregues = [a for a in atividades if a["status"] == "submitted"]
        outras = sorted((a for a in atividades if a["status"] != "submitted"),
                        key=lambda x: x["duedate"] or float("inf"))
        for titulo, grupo, primeiro in (("A entregar", outras, True),
                                        ("Entregues", entregues, False)):
            if not grupo:
                continue
            RotuloSecao(area.interior, titulo, len(grupo)).pack(
                fill="x", pady=(0 if primeiro else 20, 6), padx=2)
            for i, a in enumerate(grupo):
                if i:
                    fio(area.interior).pack(fill="x", padx=14)
                self._linha(area, a)
        if not atividades:
            self._vazio(area, "Nenhuma atividade encontrada.")
        area.finalizar()


if __name__ == "__main__":
    App().mainloop()
