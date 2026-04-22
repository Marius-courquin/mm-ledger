# Design — IBKR vault-first, app-managed ib-gateway

**Date** : 2026-04-22
**Statut** : proposé
**Auteur** : Charles (+ Claude)

## Contexte

Le connecteur IBKR est inopérant. Deux causes combinées :

1. Le container `ib-gateway` est éteint et `.env` est vide. Pour le relancer en l'état actuel il faudrait remplir `IBKR_USERNAME` / `IBKR_PASSWORD` dans `.env`, ce qui viole la règle vault-first du projet (aucun credential sur disque hors vault).
2. `src/manager.py::collect_events` ne transitionne l'état du worker que sur les events `{type: "status"}`. Un event `{type: "error"}` — émis par `IB().connect()` quand la connexion échoue — n'update pas `handle.state`. Conséquence : le worker reste en `"connecting"` pour toujours côté UI. Bug transverse (pas spécifique IBKR).

## Objectifs

- Rétablir un IBKR fonctionnel, utilisable pour consulter capital / positions / cash.
- **Zéro credential sur disque hors du vault SQLCipher.** `ib-gateway` reçoit ses creds en env à la volée depuis le vault, au moment du `connect`.
- Corriger le bug cross-cutting du manager (état `"error"`).
- Expérience UI claire : quand ça échoue, on sait pourquoi et quoi faire.

## Non-objectifs

- Auto-retry / self-healing d'`ib-gateway` en cas de crash.
- Support multi-account IBKR sur une même instance mm-ledger.
- Support IBKR multi-user concurrent (contrainte physique : un seul ib-gateway sur :4001).
- Refactor des autres connecteurs (TR, Woob, Banking).

## État actuel (ce qu'on remplace)

- `docker-compose.yml` déclare un service `ib-gateway` avec profile `ibkr`. `TWS_USERID` / `TWS_PASSWORD` lus depuis `.env` via interpolation.
- `src/connectors/ibkr.py::connect` lit `host`, `port` depuis `credentials` (défauts `127.0.0.1`, `4001`). Les `config_fields` (host/port) existent mais ne sont jamais lus (bug mineur : les valeurs viennent toujours des défauts).
- `src/api/connectors.py` : IBKR a `credential_fields = []` et `config_fields = [host, port]`. Le `spawn(...)` ne passe que `credentials` (dict vide), donc host/port ne remontent pas jusqu'au worker.
- Flux : user démarre `ib-gateway` manuellement (compose profile), crée un connecteur IBKR dans l'UI, clique connect → l'app connecte ib_async à un gateway déjà debout.

## Design proposé

### 1. Vault — schéma des credentials IBKR

Les credentials migrent du container (env) vers le vault (par user).

`src/api/connectors.py::CONNECTOR_TYPES` pour `ibkr` :

```python
{
    "type": "ibkr", "label": "Interactive Brokers",
    "credential_fields": [
        {"name": "username", "type": "text", "required": True},
        {"name": "password", "type": "password", "required": True},
        {"name": "trading_mode", "type": "select", "required": True,
         "options": [{"value": "live", "label": "Live"},
                     {"value": "paper", "label": "Paper"}],
         "default": "live"},
    ],
    "config_fields": [],   # plus de host/port, c'est géré en interne
    "supports_2fa": False, "supports_streaming": True,
}
```

Le formulaire `ConnectorForm` gère déjà les `credential_fields` dynamiquement — UI automatique.

### 2. Worker IBKR — orchestration du container

`src/connectors/ibkr.py` passe de "client qui se connecte à un gateway existant" à "client qui démarre son propre gateway puis s'y connecte".

```python
# Pseudo-code de connect()
def connect(self, credentials: dict) -> None:
    import docker, socket, time

    self._container_name = f"mm-ledger-ibkr-{self._safe_key()}"
    self._docker = docker.from_env()

    # 1. Nettoyage d'un éventuel container orphelin (crash précédent)
    self._remove_existing_container()

    # 2. Spawn ib-gateway (hardened)
    run_kwargs = dict(
        image=IBKR_GATEWAY_IMAGE,        # pinné par digest, voir constants
        name=self._container_name,
        environment={
            "TWS_USERID": credentials["username"],
            "TWS_PASSWORD": credentials["password"],
            "TRADING_MODE": credentials["trading_mode"],
            "READ_ONLY_API": "yes",
            "TWOFA_TIMEOUT_ACTION": "restart",
        },
        detach=True,
        auto_remove=True,
        labels={"mm-ledger": "ibkr-gateway"},
        # — Hardening —
        security_opt=["no-new-privileges:true"],
        mem_limit="2g",
        nano_cpus=2_000_000_000,         # 2 CPU cores max
        network=IBKR_NETWORK_NAME,       # network docker dédié, pas host
    )
    if self._dev_mode():
        # En dev, l'app tourne sur l'hôte → publier le port sur 127.0.0.1
        run_kwargs["ports"] = {"4001/tcp": ("127.0.0.1", 4001)}
    # En prod, app ∈ même network → pas de publication, DNS via nom container
    self._container = self._docker.containers.run(**run_kwargs)

    # 3. Détermine l'endpoint selon mode (dev vs prod-in-docker)
    gateway_host, gateway_port = self._gateway_endpoint()
    # dev → ("127.0.0.1", 4001) ; prod → (self._container_name, 4001)

    # 4. Poll jusqu'à ready
    self.event_queue.put({"type": "status", "state": "starting_gateway"})
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            with socket.create_connection((gateway_host, gateway_port), timeout=2):
                break
        except OSError:
            time.sleep(2)
    else:
        self._stop_container()
        raise TimeoutError("ib-gateway n'a pas démarré dans les 90s. Vérifier 'docker logs <container>'.")

    # 5. Connect ib_async
    from ib_async import IB
    self._ib = IB()
    self._ib.connect(gateway_host, gateway_port, clientId=1)
    self.event_queue.put({"type": "status", "state": "connected"})
```

`disconnect()` stoppe ib_async puis `self._container.stop(timeout=10)` (auto_remove nettoie).

**Constantes** (`src/connectors/ibkr.py`, top-level) :

```python
# Pinné par digest pour prévenir une substitution silencieuse de l'image (supply chain).
# Le digest doit être mis à jour manuellement lors d'un upgrade, après audit du changelog.
IBKR_GATEWAY_IMAGE = "ghcr.io/gnzsnz/ib-gateway@sha256:<DIGEST_A_FIXER>"
IBKR_NETWORK_NAME = "mm-ledger-net"
```

Le `<DIGEST_A_FIXER>` se résout en phase d'implémentation via `docker pull ghcr.io/gnzsnz/ib-gateway:latest-stable && docker inspect --format '{{index .RepoDigests 0}}'`. Tag `:latest` proscrit.

**Mode dev vs prod** :

```python
def _dev_mode(self) -> bool:
    # L'app tourne dans un container si /.dockerenv existe.
    return not os.path.exists("/.dockerenv")

def _gateway_endpoint(self) -> tuple[str, int]:
    if self._dev_mode():
        return ("127.0.0.1", 4001)         # port publié sur loopback hôte
    return (self._container_name, 4001)    # DNS docker intra-network

Le worker a besoin d'une **clé propre et bornée** pour nommer son container. On passe le `worker_key` (= `f"{user_id}:{connector_id}"`) dans le `config` du worker au moment du `spawn()`. Sanitisation du nom de container :

```python
def _safe_key(self) -> str:
    # docker container names: [a-zA-Z0-9][a-zA-Z0-9_.-]*, max 63 chars
    raw = self.config["worker_key"].lower()
    return re.sub(r"[^a-z0-9_.-]", "-", raw)[:50]
```

Nettoyage d'un container orphelin (crash précédent, stop imparfait) :

```python
def _remove_existing_container(self):
    try:
        old = self._docker.containers.get(self._container_name)
        old.stop(timeout=5)
        old.remove(force=True)
    except docker.errors.NotFound:
        pass
```

Gestion d'erreur :
- `docker.errors.APIError` ou `ConnectionError` sur le socket → `event_queue.put({"type": "error", "message": "..."})` avec un message actionnable. Le worker ne crash pas, il revient au `run()` loop, prêt à accepter une commande `shutdown` ou un nouveau `connect`.
- Si un ib-gateway tourne déjà pour un autre user sur :4001 → `APIError` sur conflict → message clair "port 4001 occupé par un autre user IBKR".

### 3. Manager — fix cross-cutting de l'état erreur

`src/manager.py::collect_events` actuellement (ligne 75-82) :

```python
if evt_type == "status":
    handle.state = event.get("state", handle.state)
    handle.detail = event.get("detail")
elif evt_type in ("accounts", "balances", "positions", "transactions"):
    ...
```

Ajouter :

```python
elif evt_type == "error":
    handle.state = "error"
    handle.detail = event.get("message")
```

Impact : quand un worker émet une erreur (fatale ou non), son état devient `"error"` avec le message, et l'UI le voit. Touche tous les connecteurs, pas que IBKR.

Contrat mis à jour pour `ConnectorWorker` (doc dans `base.py`) : un event `error` signifie "opération en échec, consulter `detail`". Il ne signifie pas "worker mort" — le worker continue à tourner et peut recevoir d'autres commandes.

### 4. Manager — passage du `worker_key` au worker

`spawn()` actuel crée le worker avec `config = {}`. On change :

```python
def spawn(self, connector_id: str, connector_type: str, credentials: dict):
    ...
    proc = Process(target=_run_worker, args=(cls, cmd_q, event_q, {"worker_key": connector_id}), daemon=True)
```

`_run_worker` devient :

```python
def _run_worker(cls, cmd_q, event_q, config):
    worker = cls(cmd_q, event_q, config)
    worker.run()
```

Le worker IBKR lit `self.config["worker_key"]` pour nommer son container.

### 5. Docker compose — suppression du service `ib-gateway` + network dédié

- Retirer entièrement le bloc `ib-gateway` de `docker-compose.yml`. Retirer le volume `ib-gateway-data`.
- Déclarer un network `mm-ledger-net` :

  ```yaml
  networks:
    mm-ledger-net:
      name: mm-ledger-net
      driver: bridge
  ```

- Service `app` :
  - Rejoindre `mm-ledger-net` (`networks: [mm-ledger-net]`) pour pouvoir résoudre le nom du container ib-gateway spawné dynamiquement.
  - Ajouter le mount `/var/run/docker.sock:/var/run/docker.sock` (pattern déjà utilisé par `watchtower`).
- Pas d'impact sur `watchtower`, `wg-easy`, `duckdns`.
- En prod : aucun port IBKR n'est exposé sur l'hôte → `ib-gateway` n'est joignable que depuis le network interne, ce qui réduit la surface d'attaque (un process hors du container app ne peut pas parler à :4001).

### 6. Dependencies

- `pyproject.toml` : ajouter `docker>=7` aux deps.
- Pas de nouvelle dep côté frontend.

### 7. Frontend

- `ConnectorForm` : rien à faire, les `credential_fields` sont rendus dynamiquement.
- Carte connecteur (Accounts / Dashboard) : ajouter l'affichage du badge `"error"` avec `worker.detail` en tooltip ou sous-titre rouge. Déjà partiellement là si le composant rend les états arbitraires — sinon petite extension.
- Toast d'erreur réseau (fetch 503/409 lors de `/connect`) : message serveur relayé tel quel.

### 8. `.env` / `.env.example`

- `.env.example` : pas de changement (déjà sans IBKR_*).
- Vérifier qu'on ne documente nulle part dans `README.md` ou docs l'usage de `IBKR_USERNAME` / `IBKR_PASSWORD` en env. Retirer toute mention résiduelle.

## Sécurité

Threat model : Raspberry Pi self-hosted, single-tenant, accès réseau via VPN WireGuard. Attaquant = code malveillant dans l'app ou accès physique/SSH.

### Amélioration vs état actuel

| Surface | `.env` (actuel théorique) | Design |
|---|---|---|
| Plaintext sur disque | oui, durable | **non** (vault SQLCipher) |
| Leak git | possible | non |
| Backup / rsync | exposé | exposé mais chiffré |
| Env container en runtime | oui | oui (temporaire) |

### Risques résiduels (après hardening)

1. `docker inspect` sur le container actif expose l'env (= creds) à quiconque a accès au docker socket. Mais cet accès implique déjà root hôte → peut dump la mémoire Python → pas une nouvelle vulnérabilité.
2. `/var/run/docker.sock` monté dans le container `app` = trust boundary équivalente à root hôte. Déjà présent via watchtower, accepté dans le threat model. Redocumenté dans `README.md`.
3. Image tierce `ghcr.io/gnzsnz/ib-gateway` : pinnée par digest → supply chain compromise détectable au moment d'un upgrade manuel. `READ_ONLY_API=yes` limite l'impact (lecture seule).
4. Compromission du process Python de l'app → accès aux creds en mémoire (vault unlock) + docker socket → game over. Inévitable pour toute app gérant des secrets. Surface réduite par les tests, revue de code, pas de CI exposant l'app.

### Hardening intégré au design

- **`READ_ONLY_API=yes`** maintenu — l'API IBKR ne peut que lire, pas trader.
- **Image pinnée par SHA256 digest** (`@sha256:...`), pas `:latest`. Empêche un swap silencieux de l'image amont. Upgrade = action manuelle après audit.
- **Network isolation** : en prod, aucun port exposé sur l'hôte. ib-gateway joignable uniquement via le network interne `mm-ledger-net`. En dev, fallback `127.0.0.1:4001` (app hors docker).
- **`security_opt=["no-new-privileges:true"]`** — bloque l'escalade via binaires setuid dans le container.
- **Resource limits** : `mem_limit="2g"`, `nano_cpus=2e9` (2 cores). Contient un éventuel runaway du process Java d'IBC / Xvfb.
- **`auto_remove=True`** + pré-cleanup des orphelins → aucun container avec creds en env ne traîne après un crash.
- **Nommage unique par user** — évite les collisions.
- **No-log-creds** : règle de code — les messages d'erreur n'injectent jamais `credentials`. Exceptions: `str(e)` uniquement sur exceptions issues de `docker.errors.*` ou `ib_async` (qui n'incluent pas les creds par construction). Test explicite dans la suite.
- **Audit log** : `src/connectors/ibkr.py` logue à chaque `connect`/`disconnect` via `logging.info` un message de type `"IBKR: user=%s connector=%s action=connect result=ok"`. Pas de password, pas de username. But : forensique si compromission soupçonnée.

## Tests

- `tests/test_manager.py::test_error_event_transitions_state` — un `{type: "error", message: "x"}` sur `event_queue` → `get_status()` renvoie `{state: "error", detail: "x"}`.
- `tests/test_manager.py::test_worker_config_contains_key` — le worker reçoit `config["worker_key"] == connector_id`.
- `tests/test_api_connectors.py::test_ibkr_connector_types` — les `credential_fields` contiennent bien `username`, `password`, `trading_mode`.
- `tests/test_connector_ibkr.py` (nouveau) — avec `docker.from_env` mocké :
  - `connect()` happy path : container créé avec bons env + hardening flags (`security_opt`, `mem_limit`, `nano_cpus`, digest pinné), socket ready, `IB().connect()` appelé, status `connected` émis.
  - `connect()` timeout gateway : container stoppé, event `error` avec message sur timeout, **aucun credential dans le message** (assertion explicite).
  - `connect()` conflit de nom → nettoyage du container précédent.
  - `connect()` avec credentials invalides : `IB().connect()` raise → event `error`, **le message ne contient ni username ni password** (assertion explicite).
  - `disconnect()` : ib_async disconnect + container stop.
  - Audit log : `connect`/`disconnect` produisent la ligne log attendue **sans creds**.

## Migration / compatibilité

- Les connecteurs IBKR existants en DB (s'il y en a) ont des credentials vides dans le vault. Au prochain `connect` → erreur claire `"username manquant"`. User re-saisit les 3 champs via le formulaire (route PUT existante).
- Pas de migration SQL nécessaire (le vault est schemaless, stocke un dict arbitraire).
- Les volumes docker `ib-gateway-data` existants (persistent state IBC) sont orphelins. Optionnel : les supprimer manuellement (`docker volume rm mm-ledger_ib-gateway-data`).

## Risques et questions ouvertes

- **Démarrage lent d'ib-gateway** : 60-90s typiquement. L'UI doit refléter un état intermédiaire `starting_gateway` (ajouté au design) pour que le user ne croie pas que c'est bloqué.
- **2FA mobile IBKR** : à la première connexion, IBKR demande parfois une approbation sur l'app mobile. Si le user n'approuve pas, `ib-gateway` boucle. `TWOFA_TIMEOUT_ACTION=restart` rejoue. À documenter dans le CLAUDE.md / README.
- **Platform ARM (Raspberry Pi)** : vérifier que `ghcr.io/gnzsnz/ib-gateway` existe en `arm64`. Le digest doit pointer sur une **manifest list** multi-arch (Docker sélectionne l'image locale), sinon le digest sera platform-specific. À vérifier au moment de résoudre `<DIGEST_A_FIXER>` : `docker buildx imagetools inspect ghcr.io/gnzsnz/ib-gateway:latest-stable` doit lister `linux/arm64` ET `linux/amd64`.
- **Test local dev** : quand Charles dev sur macOS, `docker.from_env()` parle au Docker Desktop local. Pas de mount `/var/run/docker.sock` nécessaire puisque l'app tourne hors container. OK.
- **Docker socket sur macOS** : `DOCKER_HOST=unix:///var/run/docker.sock` peut ne pas marcher par défaut sur macOS récent. Fallback sur `~/.docker/run/docker.sock`. Le SDK Python gère généralement ça avec `docker.from_env()`.
