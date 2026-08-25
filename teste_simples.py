import os
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = (os.getenv("MOODLE_TOKEN") or "").strip()
MOODLE_URL = "https://moodle.univassouras.edu.br"

print("Testando 1 chamada simples...")
response = requests.get(f"{MOODLE_URL}/webservice/rest/server.php", params={"wstoken": TOKEN, "wsfunction": "core_webservice_get_site_info", "moodlewsrestformat": "json"}, timeout=15)
print(response.json())
