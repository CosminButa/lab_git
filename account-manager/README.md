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

## Deploy simplu în cluster (fără CI/CD)

Ai nevoie doar de `docker`, `kubectl` și un registry la care ajunge clusterul (sau, pentru un cluster de test cu un singur nod, încărcarea imaginii direct pe nod).

```sh
# 1. imaginea
docker build -t registry.example.com/account-manager:1.0.0 account-manager/
docker push registry.example.com/account-manager:1.0.0
#    fără registry, pe k3s:  docker save account-manager:local | sudo k3s ctr images import -
#    pe kind:                kind load docker-image account-manager:local
#    pe minikube:            minikube image load account-manager:local
#    și pune imaginea respectivă în k8s/kustomization.yaml (newName/newTag)

# 2. adaptează manifestele (o singură dată)
#    k8s/kustomization.yaml  -> images.newName / newTag
#    k8s/configmap.yaml      -> KEYCLOAK_URL, KEYCLOAK_REALM, KEYCLOAK_CLIENT_ID, JIRA_URL, NEXTCLOUD_URL, NEXTCLOUD_USER
#    k8s/ingress.yaml        -> host, ingressClassName, anotarea cert-manager.io/cluster-issuer (sau secret TLS propriu)
#    k8s/networkpolicy.yaml  -> namespace-ul ingress controller-ului tău
#    k8s/pvc.yaml            -> storageClassName dacă nu ai una implicită

# 3. namespace + secrete (secretele nu trec niciodată prin git)
kubectl create namespace account-manager
#    registry privat (Nexus, Harbor...): pull secret, numele e referit în deployment.yaml
kubectl -n account-manager create secret docker-registry nexus-registry \
  --docker-server=nexus.example.com --docker-username='<user>' --docker-password='<parola sau token>'
kubectl -n account-manager create secret generic account-manager-secrets \
  --from-literal=SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')" \
  --from-literal=BOOTSTRAP_ADMIN_USERNAME=admin \
  --from-literal=BOOTSTRAP_ADMIN_PASSWORD='ParolaTemporara-Schimbata-La-Login' \
  --from-literal=KEYCLOAK_CLIENT_SECRET='...' \
  --from-literal=JIRA_TOKEN='...' \
  --from-literal=NEXTCLOUD_APP_PASSWORD='...'

# 4. deploy
kubectl apply -k account-manager/k8s/
kubectl -n account-manager rollout status deploy/account-manager
kubectl -n account-manager logs deploy/account-manager --tail=50

# 5. dacă nu ai încă ingress/DNS, testează prin port-forward
kubectl -n account-manager port-forward svc/account-manager 8000:80
#    -> http://localhost:8000 (cookie-ul e marcat Secure; pentru test pe http pune
#       SESSION_COOKIE_SECURE=false în ConfigMap temporar, apoi revino la true)
```

Autentifică-te cu admin-ul de bootstrap, schimbă parola, creează operatorii din **Operatori**. După aceea poți scoate `BOOTSTRAP_ADMIN_*` din Secret; nu se mai folosesc oricum când există operatori.

Actualizare la o versiune nouă, fără CI/CD:

```sh
docker build -t registry.example.com/account-manager:1.0.1 account-manager/ && docker push registry.example.com/account-manager:1.0.1
kubectl -n account-manager set image deploy/account-manager app=registry.example.com/account-manager:1.0.1
kubectl -n account-manager rollout status deploy/account-manager
```

Comenzi utile:

```sh
# creare/promovare admin din pod (parola e cerută interactiv)
kubectl -n account-manager exec -it deploy/account-manager -- flask --app wsgi create-admin cosmin
# provisionare din pod, cu raport pas cu pas
kubectl -n account-manager exec -it deploy/account-manager -- \
  flask --app wsgi provision-user keycloak ion.popescu --email ion@example.com --group /dev
# backup bază de date (SQLite)
kubectl -n account-manager exec deploy/account-manager -- cat /data/app.db > backup-$(date +%F).db
```

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
