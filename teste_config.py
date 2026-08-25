"""Testa que a configuracao vem do .env e que o resto o Moodle descobre sozinho.

Sem isso o projeto so serviria pro dono do repositorio: usuario, cursos e a
URL do Moodle estavam fixos no codigo.
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

falhas = []


def checar(rotulo, ok, detalhe=""):
    print(("  OK   " if ok else "  FALHA") + f"  {rotulo}" + (f"  [{detalhe}]" if detalhe else ""))
    if not ok:
        falhas.append(rotulo)


def recarregar(**variaveis):
    """Recarrega o moodle_core com outras variaveis de ambiente."""
    for k, v in variaveis.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import moodle_core
    return importlib.reload(moodle_core)


print("=== o arquivo de exemplo ===")
exemplo = open(".env.exemplo", encoding="utf-8").read()
for chave in ["MOODLE_TOKEN", "MOODLE_URL", "MOODLE_USER_ID", "MOODLE_COURSE_IDS",
              "GEMINI_API_KEY", "GEMINI_MODEL"]:
    checar(f"documenta {chave}", chave in exemplo)
checar("explica onde pegar o token", "Chaves de seguranca" in exemplo)
checar("explica onde pegar a chave do Gemini", "aistudio.google.com" in exemplo)
checar("avisa pra nao compartilhar o token", "senha" in exemplo.lower())
checar("nao tem dado pessoal de ninguem",
       not any(x in exemplo for x in ["1730027", "48215", "48374", "48598"]))
checar("nao tem valor preenchido em campo secreto",
       all(l.split("=", 1)[1].strip() == ""
           for l in exemplo.splitlines()
           if l.startswith(("MOODLE_TOKEN=", "GEMINI_API_KEY="))))

print("\n=== .env ignorado pelo git, exemplo versionado ===")
ignorados = open(".gitignore", encoding="utf-8").read()
checar(".env esta no .gitignore", "\n.env\n" in "\n" + ignorados)
checar(".env.exemplo nao esta ignorado", ".env.exemplo" not in ignorados)

print("\n=== variaveis mandam na configuracao ===")
mc = recarregar(MOODLE_URL="https://moodle.outra.edu.br/",
                MOODLE_USER_ID="999", MOODLE_COURSE_IDS="11, 22,33")
checar("usa a URL do .env", mc.MOODLE_URL == "https://moodle.outra.edu.br", mc.MOODLE_URL)
checar("tira a barra do fim da URL", not mc.MOODLE_URL.endswith("/"))
checar("usa o usuario do .env", mc.USER_ID == 999, str(mc.USER_ID))
checar("aceita lista de cursos com espacos", mc.COURSE_IDS == [11, 22, 33], str(mc.COURSE_IDS))

print("\n=== em branco, descobre sozinho ===")
mc = recarregar(MOODLE_URL=None, MOODLE_USER_ID="", MOODLE_COURSE_IDS="")
checar("sem MOODLE_URL cai no padrao", "univassouras" in mc.MOODLE_URL, mc.MOODLE_URL)
checar("sem usuario fica None (pergunta pro Moodle)", mc.USER_ID is None)
checar("sem cursos fica None (usa os matriculados)", mc.COURSE_IDS is None)

chamadas = []


def falso(sessao, wsfunction, params):
    chamadas.append((wsfunction, params))
    if wsfunction == "core_webservice_get_site_info":
        return {"userid": 4242}
    if wsfunction == "core_enrol_get_users_courses":
        return [{"id": 7, "fullname": "Curso Sete_X"}, {"id": 8, "fullname": "Curso Oito_X"}]
    if wsfunction == "mod_assign_get_assignments":
        return {"courses": []}
    if wsfunction == "core_course_get_updates_since":
        return {"instances": []}
    return {}


mc.TOKEN = "token-de-teste"
mc._chamar = falso
mc.STATE_FILE = os.path.join(os.environ.get("TEMP", "."), "teste_config_state.json")
mc.coletar()
funcoes = [c[0] for c in chamadas]
checar("pergunta quem e o usuario", "core_webservice_get_site_info" in funcoes)
checar("usa o userid que o Moodle respondeu",
       any(f == "core_enrol_get_users_courses" and p["userid"] == 4242 for f, p in chamadas))
checar("acompanha os cursos matriculados",
       any(f == "mod_assign_get_assignments" and p["courseids[]"] == [7, 8] for f, p in chamadas))
checar("busca novidades dos mesmos cursos",
       sorted(p["courseid"] for f, p in chamadas if f == "core_course_get_updates_since") == [7, 8])

print("\n=== com cursos no .env, respeita a escolha ===")
mc = recarregar(MOODLE_COURSE_IDS="8")
mc.TOKEN = "token-de-teste"
chamadas.clear()
mc._chamar = falso
mc.STATE_FILE = os.path.join(os.environ.get("TEMP", "."), "teste_config_state.json")
mc.coletar()
checar("usa so o curso escolhido",
       any(f == "mod_assign_get_assignments" and p["courseids[]"] == [8] for f, p in chamadas))

if os.path.exists(mc.STATE_FILE):
    os.remove(mc.STATE_FILE)
print("\nRESULTADO:", "tudo passou" if not falhas else f"{len(falhas)} falha(s): {falhas}")
sys.exit(1 if falhas else 0)
