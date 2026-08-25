"""Janela de chat com a IA sobre uma atividade do Moodle.

Abre ao clicar num cartao. Carrega o enunciado do professor e baixa os anexos
(PDF vai inteiro pro Gemini, que le PDF de forma nativa), e a partir dai e uma
conversa normal sobre a atividade.
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
from ui import C, FONTE, FONTE_MONO, Chip, AreaRolavel, info_prazo, materia_curta, wrap

SUGESTOES = [
    "Explica o que essa atividade esta pedindo",
    "Por onde eu começo?",
    "Faz um roteiro do que preciso entregar",
]


class BotaoCopiar(ctk.CTkButton):
    """Copia pra area de transferencia e confirma no proprio rotulo."""

    def __init__(self, master, obter_texto, rotulo="copiar"):
        super().__init__(master, text=rotulo, font=(FONTE, 10), height=20, width=1,
                         fg_color="transparent", hover_color=C["cartao_hover"],
                         text_color=C["apagado"], corner_radius=6, command=self._copiar)
        self._obter = obter_texto
        self._rotulo = rotulo

    def _copiar(self):
        self.clipboard_clear()
        self.clipboard_append(self._obter() or "")
        self.update_idletasks()  # sem isso o conteudo some quando a janela fecha
        self.configure(text="copiado!", text_color=C["verde"])
        self.after(1500, self._voltar)

    def _voltar(self):
        if self.winfo_exists():
            self.configure(text=self._rotulo, text_color=C["apagado"])


class Bolha(ctk.CTkFrame):
    """Uma mensagem do chat. Renderiza markdown simples: **negrito**, listas e
    blocos de codigo em fonte mono."""

    def __init__(self, master, texto, de_quem):
        eu = de_quem == "eu"
        super().__init__(master, fg_color=C["azul"] if eu else C["cartao"],
                         corner_radius=14, border_width=0 if eu else 1,
                         border_color=C["borda"])
        autor = "Você" if eu else "Tutor IA"
        cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        cabecalho.pack(fill="x", padx=14, pady=(8, 0))
        ctk.CTkLabel(cabecalho, text=autor, font=(FONTE, 10, "bold"),
                     text_color=C["fundo"] if eu else C["roxo"],
                     anchor="w").pack(side="left")
        if not eu:
            BotaoCopiar(cabecalho, lambda: self._texto, "copiar resposta").pack(side="right")
        self._cor_texto = C["fundo"] if eu else C["texto"]
        self._largura = 560
        self._texto = texto
        self._corpo = ctk.CTkFrame(self, fg_color="transparent")
        self._corpo.pack(fill="both", expand=True, padx=14, pady=(2, 10))
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
                caixa = ctk.CTkFrame(self._corpo, fg_color=C["fundo"], corner_radius=8)
                caixa.pack(fill="x", pady=4)
                barra = ctk.CTkFrame(caixa, fg_color="transparent")
                barra.pack(fill="x", padx=8, pady=(4, 0))
                ctk.CTkLabel(barra, text=lingua or "codigo", font=(FONTE, 9),
                             text_color=C["apagado"]).pack(side="left")
                BotaoCopiar(barra, lambda t=bloco: t).pack(side="right")
                rot = tk.Text(caixa, bg=C["fundo"], fg=C["verde"], relief="flat",
                              font=(FONTE_MONO, 10), wrap="none", borderwidth=0,
                              height=max(1, bloco.count("\n") + 1), padx=10, pady=8,
                              highlightthickness=0)
                rot.insert("1.0", bloco)
                rot.configure(state="disabled")
                rot.pack(fill="x")
                # Text desabilitado ainda deixa selecionar e copiar com Ctrl+C
                rot.bind("<Button-1>", lambda e, w=rot: w.focus_set())
            else:
                ctk.CTkLabel(self._corpo, text=bloco, font=(FONTE, 12),
                             text_color=self._cor_texto, anchor="w", justify="left",
                             wraplength=wrap(self._largura, self)).pack(fill="x", pady=1)

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
                    partes.append(("\n".join(acumulado), "codigo" if dentro else "texto", lingua if dentro else ""))
                    acumulado = []
                if not dentro:
                    lingua = linha.strip()[3:].strip()
                dentro = not dentro
                continue
            acumulado.append(linha)
        if acumulado:
            partes.append(("\n".join(acumulado), "codigo" if dentro else "texto", lingua if dentro else ""))
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

        nome = atividade["nome"]
        self.title(f"Tutor IA - {nome[:60]}")
        s = ctk.ScalingTracker.get_window_scaling(self)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(900, sw - 80), min(820, sh - 90)
        self.geometry(f"{int(w / s)}x{int(h / s)}+{int((sw - w) / 2 / s)}+{int(20 / s)}")
        self.minsize(int(520 / s), int(420 / s))
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
        self.after(100, self._checar_fila)
        self.after(150, self._preparar)

    # ---------- montagem ----------
    def _montar_cabecalho(self):
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(16, 8))

        esq = ctk.CTkFrame(topo, fg_color="transparent")
        esq.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(esq, text=self.atividade["nome"], font=(FONTE, 17, "bold"),
                     text_color=C["texto"], anchor="w", justify="left",
                     wraplength=560).pack(anchor="w")
        linha = ctk.CTkFrame(esq, fg_color="transparent")
        linha.pack(anchor="w", pady=(4, 0))
        ctk.CTkLabel(linha, text=materia_curta(self.atividade["materia"]),
                     font=(FONTE, 12), text_color=C["azul"]).pack(side="left")
        chip_txt, cor, prazo_txt = info_prazo(self.atividade, self.agora)
        ctk.CTkLabel(linha, text="  ·  " + prazo_txt, font=(FONTE, 12),
                     text_color=C["apagado"]).pack(side="left")
        Chip(linha, chip_txt, cor).pack(side="left", padx=8)

        if self.atividade.get("url"):
            ctk.CTkButton(topo, text="Abrir no AVA", width=110, height=32,
                          font=(FONTE, 12), fg_color=C["cartao"], hover_color=C["cartao_hover"],
                          text_color=C["texto"], corner_radius=8,
                          command=lambda: webbrowser.open(self.atividade["url"])).pack(side="right")

    def _montar_enunciado(self):
        self.painel = ctk.CTkFrame(self, fg_color=C["cartao"], corner_radius=12,
                                   border_width=1, border_color=C["borda"])
        self.painel.pack(fill="x", padx=20, pady=(0, 8))

        cab = ctk.CTkFrame(self.painel, fg_color="transparent")
        cab.pack(fill="x", padx=14, pady=(10, 0))
        self.bt_enunciado = ctk.CTkButton(cab, text="▼  Enunciado do professor", anchor="w",
                                          font=(FONTE, 12, "bold"), fg_color="transparent",
                                          hover_color=C["cartao_hover"], text_color=C["amarelo"],
                                          height=24, command=self._alternar_enunciado)
        self.bt_enunciado.pack(side="left")
        self.rot_anexos = ctk.CTkLabel(cab, text="", font=(FONTE, 11), text_color=C["apagado"])
        self.rot_anexos.pack(side="right")

        # os anexos aparecem sempre, mesmo sem chave da API: tem atividade que
        # nao tem enunciado escrito e o PDF e a unica fonte
        anexos = self.atividade.get("anexos") or []
        if anexos:
            faixa = ctk.CTkFrame(self.painel, fg_color="transparent")
            faixa.pack(fill="x", padx=14, pady=(6, 0))
            for anexo in anexos:
                nome = anexo.get("filename", "anexo")
                kb = (anexo.get("filesize") or 0) / 1024
                ctk.CTkButton(faixa, text=f"📎  {nome}" + (f"  ({kb:.0f} KB)" if kb else ""),
                              font=(FONTE, 11), height=26, anchor="w",
                              fg_color=C["fundo"], hover_color=C["cartao_hover"],
                              text_color=C["azul"], corner_radius=8,
                              command=lambda x=anexo: self._abrir_anexo(x)).pack(side="left", padx=(0, 6))

        self.corpo_enunciado = ctk.CTkFrame(self.painel, fg_color="transparent")
        self.corpo_enunciado.pack(fill="x", padx=14, pady=(4, 12))
        texto = self.atividade.get("enunciado") or "(o professor nao escreveu enunciado)"
        self.rot_enunciado = ctk.CTkLabel(self.corpo_enunciado, text=texto, font=(FONTE, 12),
                                          text_color=C["texto"], anchor="w", justify="left",
                                          wraplength=780)
        self.rot_enunciado.pack(fill="x")
        self._enunciado_aberto = True

    def _montar_chat(self):
        self.area = AreaRolavel(self)
        self.area.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self.bind("<Configure>", self._largura_mudou)

        self.rodape = ctk.CTkFrame(self, fg_color="transparent")
        self.rodape.pack(fill="x", padx=20, pady=(0, 16))

        self.sugestoes = ctk.CTkFrame(self.rodape, fg_color="transparent")
        self.sugestoes.pack(fill="x", pady=(0, 8))
        for s in SUGESTOES:
            ctk.CTkButton(self.sugestoes, text=s, font=(FONTE, 11), height=28,
                          fg_color=C["cartao"], hover_color=C["cartao_hover"],
                          text_color=C["apagado"], corner_radius=14,
                          command=lambda t=s: self._enviar(t)).pack(side="left", padx=(0, 6))

        caixa = ctk.CTkFrame(self.rodape, fg_color="transparent")
        caixa.pack(fill="x")
        self.entrada = ctk.CTkTextbox(caixa, height=64, font=(FONTE, 12),
                                      fg_color=C["cartao"], text_color=C["texto"],
                                      border_width=1, border_color=C["borda"], corner_radius=10)
        self.entrada.pack(side="left", fill="both", expand=True)
        self.entrada.bind("<Return>", self._tecla_enter)
        self.botao = ctk.CTkButton(caixa, text="Enviar", width=90, height=64,
                                   font=(FONTE, 13, "bold"), fg_color=C["azul"],
                                   hover_color="#5d85e6", text_color=C["fundo"],
                                   corner_radius=10, command=lambda: self._enviar())
        self.botao.pack(side="right", padx=(10, 0))

    def _abrir_anexo(self, anexo):
        """Baixa o anexo numa pasta temporaria e abre no visualizador do sistema."""
        def tarefa():
            try:
                dados = moodle_core.baixar(anexo["fileurl"])
                destino = os.path.join(tempfile.gettempdir(),
                                       "moodle-assistente",
                                       anexo.get("filename", "anexo.pdf"))
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                with open(destino, "wb") as f:
                    f.write(dados)
                os.startfile(destino)
            except Exception as e:
                self._fila.put(("erro", f"nao consegui abrir o anexo: {e}"))
        threading.Thread(target=tarefa, daemon=True).start()

    # ---------- estado ----------
    def _alternar_enunciado(self):
        self._enunciado_aberto = not self._enunciado_aberto
        if self._enunciado_aberto:
            self.corpo_enunciado.pack(fill="x", padx=14, pady=(4, 12))
            self.bt_enunciado.configure(text="▼  Enunciado do professor")
        else:
            self.corpo_enunciado.pack_forget()
            self.bt_enunciado.configure(text="▶  Enunciado do professor")

    def _aviso(self, texto, cor=None):
        rot = ctk.CTkLabel(self.area.interior, text=texto, font=(FONTE, 12),
                           text_color=cor or C["apagado"], wraplength=680, justify="left")
        rot.pack(fill="x", pady=8, padx=4)
        self.area.finalizar()
        return rot

    def _bolha(self, texto, de_quem):
        b = Bolha(self.area.interior, texto, de_quem)
        if getattr(self, "_ultima_largura", 0):
            b.ajustar_largura(self._ultima_largura)
        b.pack(fill="x", pady=(0, 10), padx=(60, 4) if de_quem == "eu" else (4, 60))
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
            self.rot_anexos.configure(text=f"baixando {len(anexos)} anexo(s)...")
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
        self._aviso(
            "Pra conversar com a IA falta a chave da API do Google.\n\n"
            "1. Abra " + ia.LINK_CHAVE + " e gere uma chave (é de graça).\n"
            "2. Abra o arquivo .env da pasta do projeto.\n"
            "3. Acrescente uma linha:  GEMINI_API_KEY=sua_chave_aqui\n"
            "4. Feche e abra o assistente de novo.\n\n"
            "O enunciado e os anexos acima continuam disponíveis mesmo sem a chave.",
            C["amarelo"])
        ctk.CTkButton(self.area.interior, text="Abrir a página da chave", font=(FONTE, 12),
                      fg_color=C["azul"], hover_color="#5d85e6", text_color=C["fundo"],
                      width=200, command=lambda: webbrowser.open(ia.LINK_CHAVE)).pack(pady=4)
        self.entrada.configure(state="disabled")
        self.botao.configure(state="disabled")
        for b in self.sugestoes.winfo_children():
            b.configure(state="disabled")
        self.area.finalizar()

    def _ocupar(self, ocupado, rotulo="pensando"):
        self.ocupado = ocupado
        self.botao.configure(state="disabled" if ocupado else "normal",
                             text="..." if ocupado else "Enviar")
        for b in self.sugestoes.winfo_children():
            b.configure(state="disabled" if ocupado else "normal")
        if ocupado:
            self._rotulo_espera = rotulo
            self._inicio_espera = time.time()
            if getattr(self, "_pensando", None) is None or not self._pensando.winfo_exists():
                self._pensando = self._aviso(f"{rotulo}...", C["roxo"])
            self._contar_espera()
        elif getattr(self, "_pensando", None) is not None and self._pensando.winfo_exists():
            self._pensando.destroy()
            self._pensando = None

    def _contar_espera(self):
        """Mostra os segundos: com PDF a resposta demora, e sem sinal de vida
        parece que travou."""
        if not self.ocupado or self._pensando is None or not self._pensando.winfo_exists():
            return
        s = int(time.time() - self._inicio_espera)
        extra = "  (modelos lentos hoje, ja ja troco de modelo)" if s > 40 else ""
        self._pensando.configure(text=f"{self._rotulo_espera}...  {s}s{extra}")
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
                    self._aviso("Erro: " + carga, C["vermelho"])
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(150, self._checar_fila)

    def _anexos_prontos(self, prontos, falhas):
        _, _, prazo_txt = info_prazo(self.atividade, self.agora)
        self.conversa = ia.Conversa(self.atividade, self.atividade.get("enunciado", ""),
                                    prazo=prazo_txt)
        enviados = [a["filename"] for a in prontos if self.conversa.anexar(a)]
        if enviados:
            self.rot_anexos.configure(text="📎 " + ", ".join(enviados), text_color=C["verde"])
        elif falhas:
            self.rot_anexos.configure(text="anexo nao baixou", text_color=C["vermelho"])
        else:
            self.rot_anexos.configure(text="sem anexos")
        self._ocupar(False)

        boas_vindas = "Li o enunciado"
        if enviados:
            boas_vindas += f" e {'o anexo' if len(enviados) == 1 else 'os anexos'} " \
                           + ", ".join(enviados)
        boas_vindas += ". Pergunta o que quiser sobre a atividade, ou usa um dos atalhos aqui embaixo."
        if falhas:
            boas_vindas += "\n\n(nao consegui baixar: " + "; ".join(falhas) + ")"
        self._bolha(boas_vindas, "ia")

    # ---------- utilidades ----------
    def _largura_mudou(self, evento):
        """Faz o texto acompanhar a largura da JANELA.

        Medir o quadro que contem o texto nao funciona: com uma linha longa o
        proprio texto estica o quadro, a largura medida so cresce e o texto
        nunca volta a caber. A janela e a unica medida que nao depende do
        conteudo. As margens abaixo somam os padding ate o texto.
        """
        if evento.widget is not self:
            return
        janela = evento.width
        largura_bolha = max(260, janela - 190)   # padx da area + da bolha + barra
        if abs(largura_bolha - getattr(self, "_ultima_largura", 0)) < 16:
            return
        self._ultima_largura = largura_bolha
        self.rot_enunciado.configure(wraplength=wrap(janela - 100, self))
        for b in self._bolhas:
            if b.winfo_exists():
                b.ajustar_largura(largura_bolha)
