# Account Manager

Aplicație Flask, simplă și securizată, pentru crearea și administrarea conturilor și a apartenenței la grupuri în
**Keycloak**, **Jira Data Center** și **Nextcloud**. Rulează ca un container fără privilegii într-un cluster Kubernetes.

## Ce face

| Zonă | Funcții |
| --- | --- |
| Platforme (Keycloak / Jira / Nextcloud) | căutare utilizatori, creare utilizator, activare/dezactivare, resetare parolă, ștergere (cu confirmare), adăugare/scoatere din grupuri, test conexiune |
| Operatori (doar admin) | creare, editare rol/stare, resetare parolă, ștergere; parola temporară e afișată o singură dată |
| Audit (doar admin) | fiecare acțiune: cine, ce, pe ce platformă, țintă, rezultat |
| Cont | schimbare parolă proprie |

Fiecare platformă are propria secțiune; conturile sunt create separat, per platformă, așa cum s-a cerut.

## Securitate

- **Zero secrete în cod sau imagine.** Toate credențialele vin din variabile de mediu, injectate din `Secret`-ul Kubernetes. Nu sunt afișate niciodată în UI și nu ajung în log sau audit.
- **Conturi locale cu parole hash-uite** (scrypt). Politică de lungime minimă (12), blocare temporară după 5 încercări eșuate, rate limiting pe login, mesaj identic pentru user inexistent/parolă greșită.
- **Parolă temporară obligatoriu schimbată** la prima autentificare (operatori noi, resetări, admin bootstrap).
- **Sesiuni**: cookie `Secure`, `HttpOnly`, `SameSite=Lax`, expirare 8h, invalidarea tuturor sesiunilor la schimbarea parolei sau dezactivarea contului, protecție la session fixation.
- **CSRF** pe toate formularele, acțiunile distructive doar prin POST cu confirmare, ștergerea cere retastarea numelui.
- **Headere**: CSP strict (fără JS extern, fără inline), `X-Frame-Options: DENY`, `nosniff`, `no-store`, HSTS.
- **Către platforme**: TLS verificat (configurabil CA custom prin `REQUESTS_CA_BUNDLE`), timeouts, mesaje de eroare filtrate.
- **Container**: user neprivilegiat (UID 10001), root filesystem read-only, fără capabilities, `seccomp RuntimeDefault`, `NetworkPolicy` care permite intrare doar de la ingress și ieșire doar pe DNS/443, namespace cu Pod Security `restricted`.
- **Parolele generate** pentru utilizatorii noi/resetări sunt afișate o singură dată și nu sunt persistate.

## Configurare

Toate setările sunt variabile de mediu (vezi `.env.example`).

| Variabilă | Obligatoriu | Descriere |
| --- | --- | --- |
| `SECRET_KEY` | da | cheia de semnare a sesiunilor; `python3 -c 'import secrets;print(secrets.token_hex(32))'` |
| `DATABASE_URL` | nu | implicit `sqlite:////data/app.db`; acceptă și PostgreSQL (`postgresql+psycopg://...`, adaugă driverul în `requirements.txt`) |
| `BOOTSTRAP_ADMIN_USERNAME` / `_PASSWORD` | prima pornire | creează primul administrator **doar** dacă tabela de operatori e goală; parola trebuie schimbată la login |
| `SESSION_COOKIE_SECURE` | nu | `true` implicit; pune `false` doar pentru http pe localhost |
| `PROXY_COUNT` | nu | câte proxy-uri (ingress) stau în față; implicit 1 |
| `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` | pentru Keycloak | client confidențial cu *Service accounts roles* activat și rolurile `realm-management`: `view-users`, `manage-users`, `query-groups`. `KEYCLOAK_AUTH_REALM` opțional dacă clientul e în alt realm |
| `JIRA_URL`, `JIRA_TOKEN` | pentru Jira DC | Personal Access Token al unui utilizator cu *Jira System Administrators* |
| `NEXTCLOUD_URL`, `NEXTCLOUD_USER`, `NEXTCLOUD_APP_PASSWORD` | pentru Nextcloud | admin + app password (Settings → Security → Devices & sessions) |
| `HTTP_TIMEOUT_SECONDS`, `HTTP_VERIFY_TLS`, `LOGIN_MAX_FAILURES`, `LOGIN_LOCKOUT_MINUTES`, `PASSWORD_MIN_LENGTH`, `SESSION_MINUTES`, `LOG_LEVEL` | nu | ajustări fine |

O platformă fără variabile setate apare în dashboard ca „neconfigurată” și nu este apelată.

## Rulare locală

```sh
cd account-manager
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest                                   # 40 de teste, fără rețea (API-urile sunt mock-uite)

cp .env.example .env                     # completează valorile
set -a; . ./.env; set +a
export DATABASE_URL=sqlite:///$PWD/app.db SESSION_COOKIE_SECURE=false PROXY_COUNT=0
flask --app wsgi run                     # http://127.0.0.1:5000
```

Sau cu Docker: `docker compose up --build` și deschide http://localhost:8000.

Creare/promovare administrator din linie de comandă (parola este cerută interactiv):

```sh
flask --app wsgi create-admin cosmin
# în Kubernetes:
kubectl -n account-manager exec -it deploy/account-manager -- flask --app wsgi create-admin cosmin
```

## Deploy în Kubernetes

1. Construiește și publică imaginea:
   ```sh
   docker build -t registry.example.com/account-manager:1.0.0 account-manager/
   docker push registry.example.com/account-manager:1.0.0
   ```
2. Ajustează în `k8s/`: imaginea (`kustomization.yaml`), URL-urile platformelor (`configmap.yaml`), hostname-ul și clasa de ingress (`ingress.yaml`), namespace-ul ingress-ului (`networkpolicy.yaml`), `storageClassName` dacă e nevoie (`pvc.yaml`).
3. Creează secretul, în afara git-ului:
   ```sh
   kubectl create namespace account-manager
   kubectl -n account-manager create secret generic account-manager-secrets \
     --from-literal=SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')" \
     --from-literal=BOOTSTRAP_ADMIN_USERNAME=admin \
     --from-literal=BOOTSTRAP_ADMIN_PASSWORD='ParolaTemporara-Schimbata-La-Login' \
     --from-literal=KEYCLOAK_CLIENT_SECRET='...' \
     --from-literal=JIRA_TOKEN='...' \
     --from-literal=NEXTCLOUD_APP_PASSWORD='...'
   ```
   (sau SealedSecret / External Secrets Operator; `secret.example.yaml` arată structura.)
4. Aplică:
   ```sh
   kubectl apply -k account-manager/k8s/
   kubectl -n account-manager rollout status deploy/account-manager
   ```
5. Intră pe `https://accounts.example.com`, autentifică-te cu admin-ul de bootstrap, schimbă parola, apoi creează operatorii din meniul **Operatori**. După aceea poți scoate `BOOTSTRAP_ADMIN_*` din Secret.

Dacă platformele folosesc certificate emise de o CA internă, montează bundle-ul într-un volum și setează `REQUESTS_CA_BUNDLE=/etc/ssl/custom/ca.crt`.

## Structura

```
account-manager/
├── app/
│   ├── __init__.py          # app factory, bootstrap admin, handlers globale
│   ├── config.py            # toate setările, din env
│   ├── models.py            # Operator, AuditLog
│   ├── security.py          # headere, rate limiter, generare parole
│   ├── auth/                # login, logout, schimbare parolă
│   ├── admin/               # operatori, audit
│   ├── platforms/
│   │   ├── base.py          # interfața comună + gestionare erori HTTP
│   │   ├── keycloak.py      # Admin REST API
│   │   ├── jira.py          # REST API v2 (Data Center)
│   │   ├── nextcloud.py     # OCS Provisioning API
│   │   └── routes.py        # UI generic pentru toate platformele
│   └── templates/, static/
├── tests/                   # pytest, API-uri mock-uite cu requests-mock
├── k8s/                     # manifeste kustomize
├── Dockerfile, gunicorn.conf.py, wsgi.py, docker-compose.yml
└── requirements*.txt
```

## Limitări cunoscute

- SQLite pe volum RWO înseamnă **un singur replica** (`strategy: Recreate`). Pentru HA, treci la PostgreSQL prin `DATABASE_URL`.
- Dezactivarea utilizatorilor în Jira prin REST necesită Jira 8.x+ și un director de utilizatori intern (nu LDAP read-only).
- În Nextcloud, listarea utilizatorilor cere câte un apel per utilizator (limitarea API-ului OCS); căutarea este limitată la 50 de rezultate.
- `NetworkPolicy` permite ieșire doar pe 443; dacă o platformă ascultă pe alt port (ex. Jira pe 8080), adaugă-l în `networkpolicy.yaml`.
- Nu există MFA pentru operatori; recomandat este accesul la UI doar din rețeaua internă/VPN (vezi `whitelist-source-range` în `ingress.yaml`).
