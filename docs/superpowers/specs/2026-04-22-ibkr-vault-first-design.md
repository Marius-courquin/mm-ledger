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

    # 2. Spawn ib-gateway
    self._container = self._docker.containers.run(
        "ghcr.io/gnzsnz/ib-gateway:latest",
        name=self._container_name,
        environment={
            "TWS_USERID": credentials["username"],
            "TWS_PASSWORD": credentials["password"],
            "TRADING_MODE": credentials["trading_mode"],
            "READ_ONLY_API": "yes",
            "TWOFA_TIMEOUT_ACTION": "restart",
        },
        ports={"4001/tcp": ("127.0.0.1", 4001)},  # bind localhost only
        detach=True,
        auto_remove=True,
        labels={"mm-ledger": "ibkr-gateway"},
    )

    # 3. Poll :4001 jusqu'à ready
    self.event_queue.put({"type": "status", "state": "starting_gateway"})
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 4001), timeout=2):
                break
        except OSError:
            time.sleep(2)
    else:
        self._stop_container()
        raise TimeoutError("ib-gateway n'a pas démarré dans les 90s. Vérifier les logs.")

    # 4. Connect ib_async
    from ib_async import IB
    self._ib = IB()
    self._ib.connect("127.0.0.1", 4001, clientId=1)
    self.event_queue.put({"type": "status", "state": "connected"})
```

`disconnect()` stoppe ib_async puis `self._container.stop(timeout=10)` (auto_remove nettoie).

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

### 5. Docker compose — suppression du service `ib-gateway`

- Retirer entièrement le bloc `ib-gateway` de `docker-compose.yml`. Retirer le volume `ib-gateway-data`.
- Service `app` (en prod) : ajouter le mount `/var/run/docker.sock:/var/run/docker.sock` (déjà le pattern de `watchtower`).
- Pas d'impact sur les autres services (`app`, `watchtower`, `wg-easy`, `duckdns`).

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

### Risques résiduels

1. `docker inspect` sur un container actif expose l'env (= creds) à quiconque a accès au docker socket. Mais cet accès implique déjà root hôte → peut dump la mémoire Python → pas une nouvelle vulnérabilité.
2. `/var/run/docker.sock` monté dans le container `app` = trust boundary équivalente à root hôte. Déjà présent via watchtower, accepté dans le threat model du projet. À redocumenter dans `README.md`.
3. Logs : vérifier qu'aucun message d'erreur ou log ne concatène les credentials. Règle dans le spec : les exceptions de `connect()` utilisent `str(e)` sans injecter les creds. Audit rapide dans l'implémentation.
4. Port exposure : bind explicite `127.0.0.1:4001` via le paramètre `ports=` plutôt que `network_mode=host`. Empêche un voisin sur le LAN de parler au gateway.
5. Image tierce : `ghcr.io/gnzsnz/ib-gateway` est communautaire. Risque de supply chain en théorie, même qu'avant. `READ_ONLY_API=yes` limite l'impact (pas de trades possibles via l'API).

### Hardening intégré au design

- `READ_ONLY_API=yes` maintenu.
- `ports={"4001/tcp": ("127.0.0.1", 4001)}` au lieu de `network_mode=host`.
- `auto_remove=True` + `try/finally` sur le stop → pas de containers orphelins avec creds en env qui traînent.
- Nommage container unique par user (pas de collision accidentelle).
- Pas de log des credentials (discipline du code + revue).

## Tests

- `tests/test_manager.py::test_error_event_transitions_state` — un `{type: "error", message: "x"}` sur `event_queue` → `get_status()` renvoie `{state: "error", detail: "x"}`.
- `tests/test_manager.py::test_worker_config_contains_key` — le worker reçoit `config["worker_key"] == connector_id`.
- `tests/test_api_connectors.py::test_ibkr_connector_types` — les `credential_fields` contiennent bien `username`, `password`, `trading_mode`.
- `tests/test_connector_ibkr.py` (nouveau) — avec `docker.from_env` mocké :
  - `connect()` happy path : container créé avec bons env, socket ready, `IB().connect()` appelé, status `connected` émis.
  - `connect()` timeout gateway : container stoppé, event `error` avec message sur timeout.
  - `connect()` conflit de nom → nettoyage du container précédent.
  - `disconnect()` : ib_async disconnect + container stop.

## Migration / compatibilité

- Les connecteurs IBKR existants en DB (s'il y en a) ont des credentials vides dans le vault. Au prochain `connect` → erreur claire `"username manquant"`. User re-saisit les 3 champs via le formulaire (route PUT existante).
- Pas de migration SQL nécessaire (le vault est schemaless, stocke un dict arbitraire).
- Les volumes docker `ib-gateway-data` existants (persistent state IBC) sont orphelins. Optionnel : les supprimer manuellement (`docker volume rm mm-ledger_ib-gateway-data`).

## Risques et questions ouvertes

- **Démarrage lent d'ib-gateway** : 60-90s typiquement. L'UI doit refléter un état intermédiaire `starting_gateway` (ajouté au design) pour que le user ne croie pas que c'est bloqué.
- **2FA mobile IBKR** : à la première connexion, IBKR demande parfois une approbation sur l'app mobile. Si le user n'approuve pas, `ib-gateway` boucle. `TWOFA_TIMEOUT_ACTION=restart` rejoue. À documenter dans le CLAUDE.md / README.
- **Platform ARM (Raspberry Pi)** : vérifier que `ghcr.io/gnzsnz/ib-gateway:latest` existe en `arm64`. Si non → pin sur un tag ARM-compatible ou fallback.
- **Test local dev** : quand Charles dev sur macOS, `docker.from_env()` parle au Docker Desktop local. Pas de mount `/var/run/docker.sock` nécessaire puisque l'app tourne hors container. OK.
- **Docker socket sur macOS** : `DOCKER_HOST=unix:///var/run/docker.sock` peut ne pas marcher par défaut sur macOS récent. Fallback sur `~/.docker/run/docker.sock`. Le SDK Python gère généralement ça avec `docker.from_env()`.
