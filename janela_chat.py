"""Janela de chat com a IA sobre uma atividade do Moodle.

Abre ao clicar numa atividade. Carrega o enunciado do professor e baixa os
anexos (PDF vai inteiro pro Gemini, que le PDF de forma nativa), e a partir
dai e uma conversa normal.

Sem balao colorido dos dois lados: a pergunta fica recuada e discreta, a
resposta ocupa a largura toda como texto de leitura. O que precisa saltar aos
olhos e o conteudo, nao o enfeite da conversa.
"""
import os
import queue
import tempfile
import threading
import time
import tkinter as tk
import webbrowser

import customtkinter as ctk

import ia
import moodle_core
from ui import (C, FONTE, FONTE_MONO, T_CORPO, T_MIUDO, T_SECAO, T_TITULO,
                AreaRolavel, BotaoTexto, RotuloSecao, fio, info_prazo, materia_curta, wrap)

SUGESTOES = [
    "O que essa atividade pede?",
    "Por onde eu começo?",
    "Monta um roteiro de entrega",
]


class BotaoCopiar(ctk.CTkButton):
    """Copia pra area de transferencia e confirma no proprio rotulo."""

    def __init__(self, master, obter_texto, rotulo="copiar"):
        super().__init__(master, text=rotulo, font=(FONTE, T_SECAO), height=18, width=1,
                         fg_color="transparent", hover_color=C["superficie2"],
                         text_color=C["texto3"], corner_radius=4, command=self._copiar)
        self._obter = obter_texto
        self._rotulo = rotulo

    def _copiar(self):
        self.clipboard_clear()
        self.clipboard_append(self._obter() or "")
        self.update_idletasks()  # sem isso o conteudo some quando a janela fecha
        self.configure(text="copiado", text_color=C["ok"])
        self.after(1500, self._voltar)

    def _voltar(self):
        if self.winfo_exists():
            self.configure(text=self._rotulo, text_color=C["texto3"])


class Bolha(ctk.CTkFrame):
    """Uma mensagem. A do usuario tem fundo sutil e recuo; a da IA e texto
    corrido com um fio na lateral, que le melhor em resposta longa."""

    def __init__(self, master, texto, de_quem):
        eu = de_quem == "eu"
        super().__init__(master, fg_color=C["superficie"] if eu else "transparent",
                         corner_radius=8)
        self._eu = eu
        self._largura = 560
        self._texto = texto
        self._cor_texto = C["texto"]

        if not eu:
            cabecalho = ctk.CTkFrame(self, fg_color="transparent")
            cabecalho.pack(fill="x", pady=(0, 2))
            ctk.CTkLabel(cabecalho, text="TUTOR", font=(FONTE, T_SECAO, "bold"),
                         text_color=C["destaque"], anchor="w").pack(side="left")
            BotaoCopiar(cabecalho, lambda: self._texto, "copiar resposta").pack(side="right")

        self._corpo = ctk.CTkFrame(self, fg_color="transparent")
        self._corpo.pack(fill="both", expand=True,
                         padx=(12, 12) if eu else (0, 0), pady=(8, 9) if eu else (0, 0))
        self.definir_texto(texto)

    def ajustar_largura(self, px):
        self._largura = px
        for f in self._corpo.winfo_children():
            if isinstance(f, ctk.CTkLabel):
                f.configure(wraplength=wrap(px, self))

    def definir_texto(self, texto):
        self._texto = texto
        for f in self._corpo.winfo_children():
            f.destroy()
        for bloco, tipo, lingua in self._blocos(texto):
            if tipo == "codigo":
                caixa = ctk.CTkFrame(self._corpo, fg_color=C["fundo"], corner_radius=6,
                                     border_width=1, border_color=C["linha"])
                caixa.pack(fill="x", pady=6)
                barra = ctk.CTkFrame(caixa, fg_color="transparent")
                barra.pack(fill="x", padx=8, pady=(4, 0))
                ctk.CTkLabel(barra, text=(lingua or "codigo").lower(), font=(FONTE, T_SECAO),
                             text_color=C["texto3"]).pack(side="left")
                BotaoCopiar(barra, lambda t=bloco: t).pack(side="right")
                rot = tk.Text(caixa, bg=C["fundo"], fg=C["texto"], relief="flat",
                              font=(FONTE_MONO, 10), wrap="none", borderwidth=0,
                              height=max(1, bloco.count("\n") + 1), padx=10, pady=6,
                              highlightthickness=0, insertbackground=C["texto"])
                rot.insert("1.0", bloco)
                rot.configure(state="disabled")
                rot.pack(fill="x")
                # Text desabilitado ainda deixa selecionar e copiar com Ctrl+C
                rot.bind("<Button-1>", lambda e, w=rot: w.focus_set())
            else:
                ctk.CTkLabel(self._corpo, text=bloco, font=(FONTE, T_CORPO),
                             text_color=self._cor_texto, anchor="w", justify="left",
                             wraplength=wrap(self._largura, self)).pack(fill="x", pady=2)

    @staticmethod
    def _blocos(texto):
        """Separa blocos de codigo (```) do texto normal.

        Devolve (conteudo, tipo, linguagem): a linguagem vem do ```python e
        vira o rotulo da barrinha, ao lado do botao de copiar.
        """
        partes = []
        dentro = False
        acumulado = []
        lingua = ""
        for linha in texto.split("\n"):
            if linha.strip().startswith("```"):
                if acumulado:
                    partes.append(("\n".join(acumulado),
                                   "codigo" if dentro else "texto", lingua if dentro else ""))
                    acumulado = []
                if not dentro:
                    lingua = linha.strip()[3:].strip()
                dentro = not dentro
                continue
            acumulado.append(linha)
        if acumulado:
            partes.append(("\n".join(acumulado), "codigo" if dentro else "texto",
                           lingua if dentro else ""))
        # limpa marcacao que nao da pra renderizar em CTkLabel
        limpos = []
        for bloco, tipo, lg in partes:
            if tipo == "texto":
                bloco = bloco.replace("**", "").replace("`", "").strip("\n")
                if not bloco.strip():
                    continue
            limpos.append((bloco, tipo, lg))
        return limpos or [(texto, "texto", "")]


class JanelaChat(ctk.CTkToplevel):
    def __init__(self, dono, atividade, agora, icone=None):
        super().__init__(dono, fg_color=C["fundo"])
        self.atividade = atividade
        self.agora = agora
        self.conversa = None
        self.ocupado = False
        self._fila = queue.Queue()

        self.title(atividade["nome"][:70])
        s = ctk.ScalingTracker.get_window_scaling(self)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(820, sw - 80), min(780, sh - 90)
        self.geometry(f"{int(w / s)}x{int(h / s)}+{int((sw - w) / 2 / s)}+{int(20 / s)}")
        self.minsize(int(480 / s), int(400 / s))
        if icone:
            try:
                self.after(250, lambda: self.iconbitmap(icone))
            except Exception:
                pass

        self._pensando = None
        self._bolhas = []
        self._montar_cabecalho()
        self._montar_enunciado()
        self._montar_chat()

        # a roda do mouse e despachada pelo handler global da janela principal,
        # que descobre a janela em foco por este atributo
        self.area_rolavel = self.area
        self.bind("<Configure>", self._largura_mudou)
        self.after(100, self._checar_fila)
        self.after(150, self._preparar)

    # ---------- montagem ----------
    def _montar_cabecalho(self):
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(14, 10))

        esq = ctk.CTkFrame(topo, fg_color="transparent")
        esq.pack(side="left", fill="x", expand=True)
        self.rot_titulo = ctk.CTkLabel(esq, text=self.atividade["nome"],
                                       font=(FONTE, 15, "bold"), text_color=C["texto"],
                                       anchor="w", justify="left")
        self.rot_titulo.pack(anchor="w")

        rel, cor, data, _ = info_prazo(self.atividade, self.agora)
        pedacos = [materia_curta(self.atividade["materia"])]
        if data:
            pedacos.append(data)
        linha = ctk.CTkFrame(esq, fg_color="transparent")
        linha.pack(anchor="w", pady=(3, 0))
        ctk.CTkLabel(linha, text="   ·   ".join(pedacos), font=(FONTE, T_MIUDO),
                     text_color=C["texto2"]).pack(side="left")
        if rel:
            ctk.CTkLabel(linha, text="   ·   " + rel, font=(FONTE, T_MIUDO),
                         text_color=cor).pack(side="left")

        if self.atividade.get("url"):
            BotaoTexto(topo, "Abrir no AVA",
                       lambda: webbrowser.open(self.atividade["url"])).pack(side="right")

        fio(self).pack(fill="x", padx=20)

    def _montar_enunciado(self):
        self.painel = ctk.CTkFrame(self, fg_color="transparent")
        self.painel.pack(fill="x", padx=20, pady=(10, 0))

        cab = ctk.CTkFrame(self.painel, fg_color="transparent")
        cab.pack(fill="x")
        self.bt_enunciado = BotaoTexto(cab, "Enunciado  ▾", self._alternar_enunciado,
                                       cor=C["texto3"], font=(FONTE, T_SECAO, "bold"))
        self.bt_enunciado.pack(side="left")
        self.rot_anexos = ctk.CTkLabel(cab, text="", font=(FONTE, T_SECAO),
                                       text_color=C["texto3"])
        self.rot_anexos.pack(side="right")

        self.corpo_enunciado = ctk.CTkFrame(self.painel, fg_color="transparent")
        self.corpo_enunciado.pack(fill="x", pady=(4, 0))
        texto = self.atividade.get("enunciado") or "(o professor nao escreveu enunciado)"
        self.rot_enunciado = ctk.CTkLabel(self.corpo_enunciado, text=texto,
                                          font=(FONTE, T_MIUDO), text_color=C["texto2"],
                                          anchor="w", justify="left", wraplength=700)
        self.rot_enunciado.pack(fill="x")
        self._enunciado_aberto = True

        # os anexos aparecem sempre, mesmo sem chave da API: tem atividade que
        # nao tem enunciado escrito e o PDF e a unica fonte
        anexos = self.atividade.get("anexos") or []
        if anexos:
            faixa = ctk.CTkFrame(self.corpo_enunciado, fg_color="transparent")
            faixa.pack(fill="x", pady=(6, 0))
            for anexo in anexos:
                nome = anexo.get("filename", "anexo")
                kb = (anexo.get("filesize") or 0) / 1024
                BotaoTexto(faixa, nome + (f"  ({kb:.0f} KB)" if kb else ""),
                           lambda x=anexo: self._abrir_anexo(x), cor=C["acento"],
                           font=(FONTE, T_MIUDO)).pack(side="left", padx=(0, 10))

    def _montar_chat(self):
        self.area = AreaRolavel(self)
        self.area.pack(fill="both", expand=True, padx=20, pady=(12, 0))

        rodape = ctk.CTkFrame(self, fg_color="transparent")
        rodape.pack(fill="x", padx=20, pady=(6, 14))

        self.sugestoes = ctk.CTkFrame(rodape, fg_color="transparent")
        self.sugestoes.pack(fill="x", pady=(0, 8))
        for s in SUGESTOES:
            ctk.CTkButton(self.sugestoes, text=s, font=(FONTE, T_MIUDO), height=26,
                          fg_color="transparent", hover_color=C["superficie2"],
                          text_color=C["texto2"], border_width=1, border_color=C["linha"],
                          corner_radius=13, width=1,
                          command=lambda t=s: self._enviar(t)).pack(side="left", padx=(0, 6))

        caixa = ctk.CTkFrame(rodape, fg_color=C["superficie"], corner_radius=8)
        caixa.pack(fill="x")
        self.entrada = ctk.CTkTextbox(caixa, height=56, font=(FONTE, T_CORPO),
                                      fg_color="transparent", text_color=C["texto"],
                                      border_width=0, corner_radius=8)
        self.entrada.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        self.entrada.bind("<Return>", self._tecla_enter)
        self.botao = BotaoTexto(caixa, "Enviar", lambda: self._enviar(), cor=C["acento"],
                                font=(FONTE, T_CORPO, "bold"), height=32)
        self.botao.pack(side="right", padx=10)

    # ---------- estado ----------
    def _alternar_enunciado(self):
        self._enunciado_aberto = not self._enunciado_aberto
        if self._enunciado_aberto:
            self.corpo_enunciado.pack(fill="x", pady=(4, 0))
            self.bt_enunciado.configure(text="Enunciado  ▾")
        else:
            self.corpo_enunciado.pack_forget()
            self.bt_enunciado.configure(text="Enunciado  ▸")

    def _abrir_anexo(self, anexo):
        """Baixa o anexo numa pasta temporaria e abre no visualizador do sistema."""
        def tarefa():
            try:
                dados = moodle_core.baixar(anexo["fileurl"])
                destino = os.path.join(tempfile.gettempdir(), "moodle-assistente",
                                       anexo.get("filename", "anexo.pdf"))
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                with open(destino, "wb") as f:
                    f.write(dados)
                os.startfile(destino)
            except Exception as e:
                self._fila.put(("erro", f"nao consegui abrir o anexo: {e}"))
        threading.Thread(target=tarefa, daemon=True).start()

    def _aviso(self, texto, cor=None):
        rot = ctk.CTkLabel(self.area.interior, text=texto, font=(FONTE, T_MIUDO),
                           text_color=cor or C["texto3"], wraplength=wrap(600, self),
                           justify="left", anchor="w")
        rot.pack(fill="x", pady=8)
        self.area.finalizar()
        return rot

    def _bolha(self, texto, de_quem):
        b = Bolha(self.area.interior, texto, de_quem)
        if getattr(self, "_ultima_largura", 0):
            b.ajustar_largura(self._ultima_largura)
        b.pack(fill="x", pady=(4, 14), padx=(80, 0) if de_quem == "eu" else (0, 0))
        self._bolhas.append(b)
        self.area.finalizar()
        self.after(60, self.area.ir_para_o_fim)
        return b

    def _preparar(self):
        """Baixa os anexos e monta a conversa."""
        if not ia.disponivel():
            self._pedir_chave()
            return
        anexos = self.atividade.get("anexos") or []
        if anexos:
            self.rot_anexos.configure(text=f"lendo {len(anexos)} anexo(s)")
        self._ocupar(True, "preparando")
        threading.Thread(target=self._baixar_anexos, args=(anexos,), daemon=True).start()

    def _baixar_anexos(self, anexos):
        prontos, falhas = [], []
        for anexo in anexos:
            try:
                prontos.append({"filename": anexo.get("filename", "anexo"),
                                "mimetype": anexo.get("mimetype"),
                                "dados": moodle_core.baixar(anexo["fileurl"])})
            except Exception as e:
                falhas.append(f"{anexo.get('filename', 'anexo')}: {e}")
        self._fila.put(("anexos", (prontos, falhas)))

    def _pedir_chave(self):
        RotuloSecao(self.area.interior, "Falta configurar").pack(fill="x", pady=(4, 8))
        self._aviso(
            "O tutor precisa de uma chave da API do Google.\n\n"
            "1.  Gere uma em " + ia.LINK_CHAVE + " (é de graça)\n"
            "2.  Abra o arquivo .env desta pasta\n"
            "3.  Acrescente:  GEMINI_API_KEY=sua_chave\n"
            "4.  Feche e abra o assistente\n\n"
            "O enunciado e os anexos acima funcionam do mesmo jeito sem a chave.",
            C["texto2"])
        BotaoTexto(self.area.interior, "Abrir a página da chave",
                   lambda: webbrowser.open(ia.LINK_CHAVE), cor=C["acento"]).pack(anchor="w")
        self.entrada.configure(state="disabled")
        self.botao.configure(state="disabled")
        for b in self.sugestoes.winfo_children():
            b.configure(state="disabled")
        self.area.finalizar()

    def _ocupar(self, ocupado, rotulo="pensando"):
        self.ocupado = ocupado
        self.botao.configure(state="disabled" if ocupado else "normal")
        for b in self.sugestoes.winfo_children():
            b.configure(state="disabled" if ocupado else "normal")
        if ocupado:
            self._rotulo_espera = rotulo
            self._inicio_espera = time.time()
            if self._pensando is None or not self._pensando.winfo_exists():
                self._pensando = self._aviso(rotulo, C["destaque"])
            self._contar_espera()
        elif self._pensando is not None and self._pensando.winfo_exists():
            self._pensando.destroy()
            self._pensando = None

    def _contar_espera(self):
        """Mostra os segundos: com PDF a resposta demora, e sem sinal de vida
        parece que travou."""
        if not self.ocupado or self._pensando is None or not self._pensando.winfo_exists():
            return
        s = int(time.time() - self._inicio_espera)
        extra = "   ·   modelo lento, ja troco por outro" if s > 40 else ""
        self._pensando.configure(text=f"{self._rotulo_espera}   {s}s{extra}")
        self.after(1000, self._contar_espera)

    # ---------- envio ----------
    def _tecla_enter(self, evento):
        if evento.state & 0x0001:  # Shift+Enter quebra linha
            return
        self._enviar()
        return "break"

    def _enviar(self, texto=None):
        if self.ocupado or self.conversa is None:
            return
        texto = (texto or self.entrada.get("1.0", "end")).strip()
        if not texto:
            return
        self.entrada.delete("1.0", "end")
        self._bolha(texto, "eu")
        self._ocupar(True)
        threading.Thread(target=self._perguntar, args=(texto,), daemon=True).start()

    def _perguntar(self, texto):
        try:
            self._fila.put(("resposta", self.conversa.enviar(texto)))
        except Exception as e:
            self._fila.put(("erro", str(e)))

    def _checar_fila(self):
        try:
            while True:
                tipo, carga = self._fila.get_nowait()
                if tipo == "anexos":
                    self._anexos_prontos(*carga)
                elif tipo == "resposta":
                    self._ocupar(False)
                    self._bolha(carga, "ia")
                elif tipo == "erro":
                    self._ocupar(False)
                    self._aviso(carga, C["vencido"])
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(150, self._checar_fila)

    def _anexos_prontos(self, prontos, falhas):
        _, _, _, _ = info_prazo(self.atividade, self.agora)
        rel, _, data, _ = info_prazo(self.atividade, self.agora)
        self.conversa = ia.Conversa(self.atividade, self.atividade.get("enunciado", ""),
                                    prazo=data or "sem prazo")
        enviados = [a["filename"] for a in prontos if self.conversa.anexar(a)]
        if enviados:
            self.rot_anexos.configure(text="leu " + ", ".join(enviados), text_color=C["ok"])
        elif falhas:
            self.rot_anexos.configure(text="anexo nao baixou", text_color=C["vencido"])
        else:
            self.rot_anexos.configure(text="")
        self._ocupar(False)

        texto = "Li o enunciado"
        if enviados:
            texto += " e " + ("o anexo " if len(enviados) == 1 else "os anexos ") + ", ".join(enviados)
        texto += ". Pergunta o que quiser, ou usa um dos atalhos abaixo."
        if falhas:
            texto += "\n\n(nao consegui baixar: " + "; ".join(falhas) + ")"
        self._bolha(texto, "ia")

    # ---------- utilidades ----------
    def _largura_mudou(self, evento):
        """Faz o texto acompanhar a largura da JANELA.

        Medir o quadro que contem o texto nao funciona: com uma linha longa o
        proprio texto estica o quadro, a largura medida so cresce e o texto
        nunca volta a caber. A janela e a unica medida que nao depende do
        conteudo.
        """
        if evento.widget is not self:
            return
        janela = evento.width
        largura_bolha = max(260, janela - 150)
        if abs(largura_bolha - getattr(self, "_ultima_largura", 0)) < 16:
            return
        self._ultima_largura = largura_bolha
        self.rot_titulo.configure(wraplength=wrap(janela - 180, self))
        self.rot_enunciado.configure(wraplength=wrap(janela - 60, self))
        for b in self._bolhas:
            if b.winfo_exists():
                b.ajustar_largura(largura_bolha)
