"""Gunicorn za Orkestrator (plan 15.2 i ugovor 15.12).

Port 8000 se ne objavljuje: dostupan je samo Nginx-u u compose mrezi.
"""

bind = "0.0.0.0:8000"

# 50 z/s x ~20 ms = 1 zahtev istovremeno u proseku; 4 radnika ostavljaju mesto za PBKDF2 prijavu
# (Nginx pusta 2 prijave u sekundi na celom sajtu, visak odlaze). Spore klijente baferuje Nginx, pa sync radnik
# ne ceka mrezu.
workers = 4
worker_class = "sync"
timeout = 30
graceful_timeout = 30

# Povremena zamena radnika; brojac prijave je u bazi, pa zamena ne brise blokade.
max_requests = 2000
max_requests_jitter = 200

# Otkucaj radnika u memoriji, ne na disku kontejnera (koren je samo za citanje).
worker_tmp_dir = "/dev/shm"

# Od gunicorn 25.1 kontrolni socket je podrazumevano u $HOME/.gunicorn/; korisnik app nema HOME, a koren je
# samo za citanje. Upravljanje ide kroz docker compose, pa socket ne treba.
control_socket_disable = True

# Pristupni log vodi Nginx, sa maskiranim tokenom (plan 15.4); ovde samo greske, na stderr.
accesslog = None
errorlog = "-"
loglevel = "info"

# Log gresaka gunicorn-a ("Error handling request /r/<token>/", trag izuzetka) prolazi isti filter kao log
# Django-a (settings_prod.LOGGING): bez tokena linka, semena i kljuca sesije. Zamenjuje gunicorn-ov rukovalac za
# errorlog; pristupnog loga nema. Filter se uvozi u master procesu pre aplikacije (/app je vec na sys.path).
logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"bez_tajni": {"()": "orkestrator.greske.FilterLoga"}},
    "formatters": {
        "generic": {
            "format": "%(asctime)s [%(process)d] [%(levelname)s] %(message)s",
            "datefmt": "[%Y-%m-%d %H:%M:%S %z]",
        },
    },
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "generic",
            "filters": ["bez_tajni"],
        },
    },
    "root": {"level": "WARNING", "handlers": ["stderr"]},
    "loggers": {
        "gunicorn.error": {"level": "INFO", "handlers": ["stderr"], "propagate": False},
        "gunicorn.access": {"level": "INFO", "handlers": [], "propagate": False},
    },
}

# Do gunicorn-a stize samo Nginx, koji X-Forwarded-Proto uvek prepisuje. Gunicorn veruje samo tom zaglavlju:
# podrazumevani skup ukljucuje i X-Forwarded-Ssl i X-Forwarded-Protocol, koje Nginx prosledjuje od klijenta,
# pa bi klijent mogao da izazove 400 zbog protivrecnih zaglavlja.
forwarded_allow_ips = "*"
secure_scheme_headers = {"X-FORWARDED-PROTO": "https"}
# Gunicorn 27 uz forwarded_allow_ips="*" inace prima SCRIPT_NAME i PATH_INFO iz zaglavlja zahteva (podrazumevano
# "SCRIPT_NAME,PATH_INFO"); prazno: nijedno zaglavlje ne menja WSGI okruzenje.
forwarder_headers = ""

proc_name = "orkestrator"
