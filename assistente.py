from datetime import datetime

import requests

from moodle_core import STATUS_MAP, coletar, pendentes_ordenadas

try:
    dados = coletar()
    agora = dados["agora"]
    atividades = dados["atividades"]

    print("=== ATIVIDADES ===")
    for a in atividades:
        prazo = datetime.fromtimestamp(a["duedate"]).strftime("%d/%m/%Y") if a["duedate"] else "sem prazo"
        print(a["materia"], "-", a["nome"])
        print("   prazo:", prazo, "| status:", STATUS_MAP.get(a["status"], a["status"]))

    print("")
    print("=== NOVIDADES ===")
    if not dados["novidades"]:
        print("Nada novo desde a ultima checagem.")
    for nov in dados["novidades"]:
        print(nov["curso"])
        for nome_mod, descricao in nov["itens"]:
            print("  -", nome_mod, ":", descricao)

    print("")
    print("=== PRIORIDADES DE ESTUDO ===")
    for p in pendentes_ordenadas(atividades):
        if p["duedate"]:
            prazo = datetime.fromtimestamp(p["duedate"]).strftime("%d/%m/%Y")
            tag = "VENCIDO" if p["duedate"] < agora else "a vencer"
        else:
            prazo = "sem prazo"
            tag = "sem urgencia definida"
        print("[" + tag + "]", p["materia"])
        print("   ", p["nome"], "- prazo:", prazo)

except requests.exceptions.Timeout:
    print("ERRO: demorou demais e foi cancelado.")
except requests.exceptions.ConnectionError as e:
    print(f"ERRO de conexao: {e}")
except Exception as e:
    print(f"ERRO: {e}")
