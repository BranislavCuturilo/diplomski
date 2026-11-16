"""Gunicorn za Orkestrator. Pokrece ga systemd (deploy/systemd/orkestrator.service).

Nginx salje zahteve na unix socket; spolja se gunicornu ne moze pristupiti.
"""

import os

bind = "unix:/run/orkestrator/gunicorn.sock"
# Socket je dostupan grupi orkestrator, u kojoj je i korisnik pod kojim radi nginx.
umask = 0o007

# Zahtev traje nekoliko milisekundi, pa 3 procesa podnose i vise stotina zahteva u sekundi.
# Vise procesa ne pomaze: SQLite ionako upisuje jedan po jedan.
workers = int(os.environ.get("ORKESTRATOR_PROCESA", "3"))
timeout = 30
graceful_timeout = 30
# Proces se povremeno zamenjuje novim, za slucaj da negde polako raste zauzeta memorija.
max_requests = 5000
max_requests_jitter = 500

# Pristup belezi nginx; ovde samo greske, koje idu u systemd dnevnik.
accesslog = None
errorlog = "-"
loglevel = "warning"
