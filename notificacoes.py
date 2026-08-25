"""Notificacoes nativas do Windows pra novidades e prazos proximos.

Prazos: avisa quando a atividade entra em 3 dias ou menos, de novo na vespera
e no dia da entrega. O que ja foi avisado fica em notificados.json pra nao
repetir o mesmo toast a cada atualizacao de 30 min.
"""
import json
import os
from datetime import datetime

from moodle_core import BASE_DIR

try:
    from windows_toasts import Toast, WindowsToaster
    _toaster = WindowsToaster("Assistente Moodle")
except Exception:
    _toaster = None

REGISTRO = os.path.join(BASE_DIR, "notificados.json")
DIAS_ALERTA = 3


def _carregar():
    if os.path.exists(REGISTRO):
        try:
            with open(REGISTRO) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def notificar(titulo, corpo):
    if _toaster is None:
        return
    try:
        t = Toast()
        t.text_fields = [titulo, corpo]
        _toaster.show_toast(t)
    except Exception:
        pass


def processar(dados, pendentes):
    """Chamado apos cada coleta: toasts de novidades e de prazos <= DIAS_ALERTA."""
    agora = dados["agora"]

    # novidades ja sao "desde a ultima checagem", entao cada uma so aparece uma vez
    for nov in dados["novidades"]:
        itens = "; ".join(f"{nome}: {desc}" for nome, desc in nov["itens"][:3])
        notificar("Novidade em " + nov["curso"].split("_")[0], itens)

    reg = _carregar()
    mudou = False
    for p in pendentes:
        if not p["duedate"] or p["duedate"] < agora:
            continue
        dias = (p["duedate"] - agora) // 86400
        if dias > DIAS_ALERTA:
            continue
        faixa = "hoje" if dias == 0 else ("1d" if dias == 1 else "3d")
        chave = f"{p['nome']}|{p['duedate']}|{faixa}"
        if chave in reg:
            continue
        prazo = datetime.fromtimestamp(p["duedate"]).strftime("%d/%m")
        if dias == 0:
            titulo = "Entrega HOJE!"
        elif dias == 1:
            titulo = "Prazo amanha"
        else:
            titulo = f"Prazo em {dias} dias"
        notificar(titulo, f"{p['nome']} - {p['materia'].split('_')[0]} (ate {prazo})")
        reg[chave] = agora
        mudou = True

    if mudou:
        with open(REGISTRO, "w") as f:
            json.dump(reg, f)
