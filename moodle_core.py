"""Logica compartilhada de acesso ao Moodle (usada pelo assistente.py e pelo app.py)."""
import json
import os
import time

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

MOODLE_URL = "https://moodle.univassouras.edu.br"
TOKEN = (os.getenv("MOODLE_TOKEN") or "").strip()
USER_ID = 1730027
COURSE_IDS = [48598, 48573, 48464, 48458, 48374, 48215, 44078]
STATE_FILE = os.path.join(BASE_DIR, "last_check.json")
TIPO_LEGIVEL = {"configuration": "configuracoes/prazo alterado", "contentfiles": "novo arquivo/material"}
STATUS_MAP = {"submitted": "ENTREGUE", "new": "NAO ENTREGUE", "draft": "RASCUNHO"}


def _chamar(sessao, wsfunction, extra_params):
    params = {"wstoken": TOKEN, "wsfunction": wsfunction, "moodlewsrestformat": "json"}
    params.update(extra_params)
    resultado = sessao.get(f"{MOODLE_URL}/webservice/rest/server.php", params=params, timeout=15).json()
    if isinstance(resultado, dict) and "exception" in resultado:
        erro_msg = resultado.get("message", "erro sem mensagem")
        raise Exception("Moodle recusou " + wsfunction + ": " + erro_msg)
    return resultado


def coletar():
    """Consulta o Moodle e devolve {"agora", "atividades", "novidades"}.

    atividades: [{"materia", "nome", "duedate", "status"}]
    novidades:  [{"curso": nome, "itens": [(nome_modulo, descricao)]}]
    Atualiza o STATE_FILE apenas se toda a coleta der certo.
    """
    if not TOKEN:
        raise RuntimeError("token nao encontrado. Confere se o .env existe e tem MOODLE_TOKEN=...")

    sessao = requests.Session()
    agora = int(time.time())

    courses_info = _chamar(sessao, "core_enrol_get_users_courses", {"userid": USER_ID})
    nomes_curso = {c["id"]: c["fullname"] for c in courses_info}

    assign_data = _chamar(sessao, "mod_assign_get_assignments", {"courseids[]": COURSE_IDS})
    atividades = []
    for course in assign_data["courses"]:
        for a in course["assignments"]:
            status = _chamar(sessao, "mod_assign_get_submission_status", {"assignid": a["id"]})
            try:
                submission_status = status["lastattempt"]["submission"]["status"]
            except KeyError:
                submission_status = "desconhecido"
            atividades.append({"materia": course["fullname"], "nome": a["name"],
                               "duedate": a["duedate"], "status": submission_status,
                               "url": f"{MOODLE_URL}/mod/assign/view.php?id={a['cmid']}" if a.get("cmid") else None})

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            since = json.load(f)["since"]
    else:
        since = agora - 7 * 24 * 60 * 60

    novidades = []
    for cid in COURSE_IDS:
        updates = _chamar(sessao, "core_course_get_updates_since", {"courseid": cid, "since": since})
        relevantes = []
        for inst in updates.get("instances", []):
            tipos = [u["name"] for u in inst["updates"] if u["name"] != "submissions"]
            if tipos:
                relevantes.append((inst["id"], tipos))
        if not relevantes:
            continue
        contents = _chamar(sessao, "core_course_get_contents", {"courseid": cid})
        nomes_modulo = {}
        for secao in contents:
            for mod in secao.get("modules", []):
                nomes_modulo[mod["id"]] = mod["name"]
        itens = []
        for cmid, tipos in relevantes:
            nome_mod = nomes_modulo.get(cmid, f"modulo {cmid}")
            descricao = ", ".join(TIPO_LEGIVEL.get(t, t) for t in tipos)
            itens.append((nome_mod, descricao))
        novidades.append({"curso": nomes_curso.get(cid, str(cid)), "itens": itens})

    with open(STATE_FILE, "w") as f:
        json.dump({"since": agora}, f)

    return {"agora": agora, "atividades": atividades, "novidades": novidades}


def pendentes_ordenadas(atividades):
    pendentes = [a for a in atividades if a["status"] in ("new", "draft")]
    pendentes.sort(key=lambda x: x["duedate"] if x["duedate"] else float("inf"))
    return pendentes
