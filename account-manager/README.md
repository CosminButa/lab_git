# Account Manager

Aplicație Flask, simplă și securizată, pentru crearea și administrarea conturilor și a apartenenței la grupuri în
**Keycloak**, **Jira Data Center** și **Nextcloud**. Rulează ca un container fără privilegii într-un cluster Kubernetes.

## Ce face

| Zonă | Funcții |
| --- | --- |
| Platforme (Keycloak / Jira / Nextcloud) | căutare utilizatori, creare utilizator cu asociere la grupuri, activare/dezactivare, resetare parolă, ștergere (cu confirmare), adăugare/scoatere din grupuri, test conexiune |
| Verificare pas cu pas | fiecare creare/asociere produce un raport: conexiune, utilizator există deja / creat și verificat, grup inexistent / deja membru / adăugat și verificat |
| Import CSV | creare în masă din fișier CSV, cu grupuri opționale per rând; fiecare rând verificat pas cu pas, rezultat în tabel, parolele afișate o singură dată |
| CLI `flask provision-user`, `flask import-users` | aceleași fluxuri din linie de comandă, cu exit code 0/1, pentru scripturi |
| Operatori (doar admin) | creare, editare rol/stare, resetare parolă, ștergere; parola temporară e afișată o singură dată |
| Audit (doar admin) | fiecare acțiune: cine, ce, pe ce platformă, țintă, rezultat |
| Cont | schimbare parolă proprie |

Fiecare platformă are propria secțiune; conturile sunt create separat, per platformă, așa cum s-a cerut.

## Pași de verificare la creare și asociere

Nicio acțiune nu este raportată ca reușită doar pentru că platforma a răspuns 200. Fluxul de creare este:

1. **Conexiune**: platforma răspunde cu credențialele configurate. Dacă nu, restul pașilor sunt marcați *sărit*.
2. **Verificare prealabilă**: utilizatorul există deja? Dacă da, este raportat *există* și **nu** se creează din nou și **nu** i se schimbă parola.
3. **Creare**, apoi **citire înapoi** a utilizatorului: doar dacă este găsit, pasul este *ok*.
4. **Pentru fiecare grup cerut**: grupul există în platformă? (altfel *eroare: grupul nu există*); utilizatorul este deja membru? (*există*); adăugare, apoi **recitirea apartenenței** (dacă platforma a zis OK dar userul nu apare în grup, este *eroare*).

La asocierea unui utilizator existent la un grup, primul pas verifică dacă utilizatorul există; dacă nu, raportul spune explicit *utilizatorul nu există, nu poate fi asociat*.

Stări posibile ale unui pas: `ok` (făcut și verificat), `exists` (starea era deja cea dorită), `skipped` (neîncercat din cauza unui pas anterior), `error`. Rezumatul ajunge și în jurnalul de audit.

Din linie de comandă (util pentru scripturi; exit code 1 dacă orice pas a eșuat):

```sh
flask --app wsgi provision-user jira ion.popescu --email ion@example.com \
  --first-name Ion --last-name Popescu --group jira-users --group dev-team
# [OK]     Conexiune: Jira răspunde.
# [OK]     Creare utilizator: Cererea de creare pentru 'ion.popescu' a fost acceptată.
# [OK]     Verificare utilizator: Utilizatorul 'ion.popescu' există și este activ.
# [OK]     Grup jira-users: 'ion.popescu' a fost adăugat și verificat în 'jira-users'.
# [EROARE] Grup dev-team: Grupul 'dev-team' nu există în Jira.
# Rezultat: EROARE
```

## Import CSV

Din pagina platformei, **Import CSV**. Fișier UTF-8, separator `,` sau `;`, cu antetul:

```csv
username,email,first_name,last_name,groups
ion.popescu,ion@example.com,Ion,Popescu,jira-users|dev-team
maria.ionescu,maria@example.com,Maria,Ionescu,
```

- Doar `username` este obligatoriu; celelalte coloane pot lipsi.
- Mai multe grupuri în aceeași celulă se separă cu `|`. Celulă goală înseamnă fără asociere.
- Utilizatorii existenți nu sunt recreați și nu li se schimbă parola; li se adaugă doar grupurile lipsă.
- Rândurile invalide (utilizator cu caractere nepermise, e-mail greșit, duplicat în fișier) sunt raportate fără a opri importul celorlalte.
- Fiecare rând trece prin aceiași pași de verificare ca la crearea individuală; rezultatul apare într-un tabel, cu parola generată afișată o singură dată. Fiecare rând este înregistrat în audit.
- Limita implicită este 500 de rânduri (`IMPORT_MAX_ROWS`); throttling-ul către platformă se aplică automat.

Din linie de comandă:

```sh
flask --app wsgi import-users jira utilizatori.csv            # exit code 1 dacă orice rând a eșuat
flask --app wsgi import-users keycloak utilizatori.csv --no-password
```

## Protecție la rate limit-ul platformelor

- **Interval minim între cereri** către aceeași platformă (`API_MIN_INTERVAL_MS`, implicit 200 ms), aplicat cu lock pe toate thread-urile unui worker.
- **Retry cu backoff** la HTTP 429/503, respectând header-ul `Retry-After` (max `API_MAX_RETRIES`, implicit 3). După epuizarea reîncercărilor, operatorul primește un mesaj clar de rate limit, nu o eroare generică.
- **Cache pentru lista de grupuri** (`GROUP_CACHE_SECONDS`, implicit 60 s), cu o reîmprospătare dacă un grup căutat nu este găsit.
- **Căutări limitate** (`SEARCH_RESULT_LIMIT`, implicit 25). La Nextcloud fiecare rezultat costă un apel suplimentar, de aceea limita este mică.
- Un singur apel per verificare: recitirea utilizatorului după creare aduce și grupurile, nu sunt apeluri separate.

## Securitate

- **Zero secrete în cod sau imagine.** Toate credențialele vin din variabile de mediu, injectate din `Secret`-ul Kubernetes. Nu sunt afișate niciodată în UI și nu ajung în log sau audit.
- **Conturi locale cu parole hash-uite** (scrypt). Politică de lungime minimă (12), blocare temporară după 5 încercări eșuate, rate limiting pe login, mesaj identic pentru user inexistent/parolă greșită.
- **Parolă temporară obligatoriu schimbată** la prima autentificare (operatori noi, resetări, admin bootstrap).
- **Sesiuni**: cookie `Secure`, `HttpOnly`, `SameSite=Lax`, expirare 8h, invalidarea tuturor sesiunilor la schimbarea parolei sau dezactivarea contului, protecție la session fixation.
- **CSRF** pe toate formularele, acțiunile distructive doar prin POST cu confirmare, ștergerea cere retastarea numelui.
- **Headere**: CSP strict (fără JS extern, fără inline), `X-Frame-Options: DENY`, `nosniff`, `no-store`, HSTS.
- **Către platforme**: TLS verificat (configurabil CA custom prin `REQUESTS_CA_BUNDLE`), timeouts, mesaje de eroare filtrate.
- **Container**: user neprivilegiat (UID 10001), root filesystem read-only, fără escaladare de privilegii.
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
| `API_MIN_INTERVAL_MS`, `API_MAX_RETRIES`, `GROUP_CACHE_SECONDS`, `SEARCH_RESULT_LIMIT` | nu | protecție la rate limit, vezi mai sus |
| `HTTP_TIMEOUT_SECONDS`, `HTTP_VERIFY_TLS`, `LOGIN_MAX_FAILURES`, `LOGIN_LOCKOUT_MINUTES`, `PASSWORD_MIN_LENGTH`, `SESSION_MINUTES`, `LOG_LEVEL`, `GUNICORN_WORKERS` | nu | ajustări fine |

O platformă fără variabile setate apare în dashboard ca „neconfigurată” și nu este apelată.

## Testare locală a imaginii

```sh
cd account-manager

# 1. rulează testele (fără rețea, API-urile sunt mock-uite)
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt && pytest

# 2. construiește imaginea
docker build -t account-manager:local .

# 3. pregătește configurarea (nu comite .env)
cp .env.example .env
# editează .env: SECRET_KEY, BOOTSTRAP_ADMIN_*, și platformele pe care vrei să le testezi
# (poți lăsa o platformă nesetată: apare ca "neconfigurată" și nu e apelată)

# 4. pornește containerul exact cum va rula în cluster (read-only, non-root)
docker run --rm -p 8000:8000 --env-file .env \
  -e SESSION_COOKIE_SECURE=false -e PROXY_COUNT=0 \
  --read-only --tmpfs /tmp -v am-data:/data account-manager:local
```

Deschide http://localhost:8000, autentifică-te cu admin-ul de bootstrap, schimbă parola. Verifică apoi:

- **Dashboard → Test conexiune** pentru fiecare platformă: trebuie să răspundă `{"ok": true}`. Dacă nu, mesajul spune dacă e problemă de rețea, TLS sau credențiale.
- **Utilizator nou** pe o platformă de test, cu un grup existent și unul inexistent: raportul trebuie să arate pașii `ok` și `eroare: grupul nu există`.
- Repetă aceeași creare: primul pas relevant trebuie să fie `există deja`, fără parolă afișată.
- **Audit**: toate acțiunile de mai sus apar cu rezultatul lor.

Alternativ, `docker compose up --build` face același lucru citind `.env`.

Dacă platformele au certificate de la o CA internă: `-v /cale/ca.crt:/etc/ssl/custom/ca.crt:ro -e REQUESTS_CA_BUNDLE=/etc/ssl/custom/ca.crt`.

## Deploy în cluster

Un singur fișier, `k8s/deploy.yaml`, în același stil cu celelalte proiecte: Namespace, PVC (Longhorn), ConfigMap, Deployment, Service, Ingress. Secretele nu trec prin git.

```sh
# 1. imaginea în Nexus, referită apoi pe digest
docker build -t nexus.domeniu.ro/account-manager:1.0.0 account-manager/
docker push nexus.domeniu.ro/account-manager:1.0.0
docker inspect --format '{{index .RepoDigests 0}}' nexus.domeniu.ro/account-manager:1.0.0   # -> pune valoarea la image: în deploy.yaml

# 2. completează în k8s/deploy.yaml: image (digest), URL-urile platformelor din ConfigMap, host-ul din Ingress

# 3. namespace, certificat wildcard, secretul aplicației
kubectl create namespace admin-accounts
kubectl get secret <wildcard> -n <ns-sursa> -o json \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps({'apiVersion':'v1','kind':'Secret','type':d['type'],'metadata':{'name':'admin-accounts-tls','namespace':'admin-accounts'},'data':d['data']}))" \
  | kubectl apply -f -
kubectl -n admin-accounts create secret generic admin-accounts-secret \
  --from-literal=SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')" \
  --from-literal=BOOTSTRAP_ADMIN_USERNAME=admin \
  --from-literal=BOOTSTRAP_ADMIN_PASSWORD='ParolaTemporara-Schimbata-La-Login' \
  --from-literal=JIRA_TOKEN='...'            # + KEYCLOAK_CLIENT_SECRET / NEXTCLOUD_APP_PASSWORD când le conectezi

# 4. deploy
kubectl apply -f account-manager/k8s/deploy.yaml
kubectl -n admin-accounts get pods -w
kubectl -n admin-accounts logs deploy/admin-accounts
```

Până ai DNS, pui `<IP ingress> accounts.domeniu.ro` în fișierul hosts; IP-ul e `EXTERNAL-IP` din `kubectl -n nginx-ingress get svc`.

Autentifică-te cu admin-ul de bootstrap, schimbă parola, creează operatorii din **Operatori**. După aceea poți scoate `BOOTSTRAP_ADMIN_*` din secret; nu se mai folosesc când există operatori.

Versiune nouă: build, push, pune noul digest la `image:` și `kubectl apply -f` din nou. Secretele și volumul rămân.

Comenzi utile:

```sh
kubectl -n admin-accounts exec -it deploy/admin-accounts -- flask --app wsgi create-admin cosmin
kubectl -n admin-accounts exec -it deploy/admin-accounts -- flask --app wsgi provision-user keycloak ion.popescu --group /dev
kubectl -n admin-accounts exec deploy/admin-accounts -- cat /data/app.db > backup-$(date +%F).db
```

Dacă pod-ul rămâne în `ImagePullBackOff`, nodurile nu ajung la Nexus sau au nevoie de un pull secret: `kubectl -n admin-accounts create secret docker-registry nexus --docker-server=nexus.domeniu.ro --docker-username=... --docker-password=...` și adaugă în Deployment `imagePullSecrets: [{name: nexus}]` la nivel de `spec.template.spec`.

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
│   │   ├── provisioning.py  # fluxuri cu pași de verificare (Report / Step) + import CSV
│   │   └── routes.py        # UI generic pentru toate platformele
│   ├── cli.py               # flask create-admin, provision-user, import-users
│   └── templates/, static/
├── tests/                   # pytest, API-uri mock-uite cu requests-mock
├── k8s/deploy.yaml          # tot deploy-ul Kubernetes într-un fișier
├── Dockerfile, gunicorn.conf.py, wsgi.py, docker-compose.yml
└── requirements*.txt
```

## Limitări cunoscute

- SQLite pe volum RWO înseamnă **un singur replica** (`strategy: Recreate`). Pentru HA, treci la PostgreSQL prin `DATABASE_URL`.
- Dezactivarea utilizatorilor în Jira prin REST necesită Jira 8.x+ și un director de utilizatori intern (nu LDAP read-only).
- În Nextcloud, listarea utilizatorilor cere câte un apel per utilizator (limitarea API-ului OCS); căutarea este limitată la 50 de rezultate.
- Nu există MFA pentru operatori; recomandat este accesul la UI doar din rețeaua internă/VPN (vezi `whitelist-source-range` în `ingress.yaml`).
