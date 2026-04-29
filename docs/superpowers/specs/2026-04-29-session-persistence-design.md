# Design — Persistance de session par connecteur

**Date** : 2026-04-29
**Statut** : proposé
**Auteur** : Charles (+ Claude)

## Contexte

À chaque restart de l'app, les workers perdent leur session :
- TR : token WS perdu → re-login + bypass WAF Cloudflare + SMS 2FA → 30-60s pour reconnecter.
- IBKR : connexion TWS perdue → reconnexion + risque de redémarrer le container ib-gateway (60-90s).
- woob_bank : session Woob perdue → re-2FA Banque Populaire à chaque fois.
- banking (Enable Banking PSD2) : tokens OAuth perdus → re-flow consentement utilisateur.

C'est insupportable côté UX. Les credentials sont déjà dans le vault SQLCipher chiffré ; rien n'empêche d'y stocker aussi la **session active** (tokens, cookies, IDs) pour la restaurer au démarrage.

## Goal

Persistance + restauration des sessions actives par connecteur, dans le vault. Au connect, le worker tente d'abord de **restaurer** la session précédente (ping un endpoint léger pour valider) ; si la session est encore valide → skip le 2FA et passe `connected` directement. Sinon → fallback transparent sur le login normal.

## Architecture

**Storage** : ajout d'une colonne `session` (TEXT NULL, JSON sérialisé) à la table `credentials` du vault SQLCipher. Pas de nouvelle table — la session vit avec les credentials, partage le chiffrement, et est wipée à la suppression d'un connecteur.

**Interface `ConnectorWorker` (méthodes optionnelles, défaut no-op)** :

```python
def serialize_session(self) -> dict | None:
    """Sérialise l'état d'auth courant. None = ne rien persister."""
    return None

def restore_session(self, blob: dict) -> bool:
    """Réinjecte un blob de session. Doit pinger un endpoint léger pour valider.
    Renvoie True si restoration réussie + connecté ; False sinon (fallback login)."""
    return False
```

**Vault** : 3 nouvelles méthodes :
- `store_session(connector_id, session: dict)`
- `retrieve_session(connector_id) -> dict | None`
- `clear_session(connector_id)` (utilisé à la suppression d'un connecteur ou au logout)

**Manager** :
- À `spawn(connector_id, connector_type, credentials)` : récupère aussi `vault.retrieve_session(connector_id)` et le passe au worker.
- Le worker reçoit `{credentials, session_blob}` à la commande `connect`.
- Run loop du worker :
  ```
  if session_blob and self.restore_session(session_blob):
      → connected, skip login
  else:
      self.connect(credentials)  # 2FA si nécessaire
  ```
- Après un connect réussi (qu'il soit via restore ou login complet), envoyer un event `session_save` au manager → `vault.store_session(connector_id, blob)`.
- À `disconnect()` ou `delete_connector()` : `vault.clear_session(connector_id)`.

## Implémentations par connecteur

| Connecteur | `serialize_session` | `restore_session` | Ping de validation |
|---|---|---|---|
| **TR** | `{session_token, refresh_token, device_id, waf_cookies}` | setter ces attributs | `accountInfo` WS sub |
| **IBKR** | `{client_id, account_id, gateway_port}` | reconnect `IB.connect()` direct, skip container restart si déjà up | `accountValues()` quick |
| **woob_bank** | storage Woob sérialisé (`backend.storage.dumps()`) | `backend.storage.loads(blob)` | `iter_accounts()` 1 itération |
| **banking** | `{access_token, refresh_token, expires_at, asid}` | setter + check expiration | `GET /sessions/<asid>` |

## Sécurité

- Tokens stockés dans le vault SQLCipher chiffré par password user → même garanties que les credentials.
- Si vault locked → pas de restore possible (comportement attendu).
- À la suppression d'un connecteur : `clear_session` appelée (cohérent avec `delete` credentials).
- Au change_password vault : tokens transparents (rekey global SQLCipher).

## Non-objectifs

- **Refresh automatique** des tokens expirants : c'est au connecteur de gérer son cycle de vie. Si TR refresh son token toutes les heures, le worker doit re-serialize et envoyer `session_save` à intervalles.
- **UI "session restaurée vs login complet"** : nice-to-have v2.
- **Inter-process partage de session** : un seul process worker par connecteur, donc pas de besoin.
- **Migrations vault** complexes : on ajoute simplement `ALTER TABLE credentials ADD COLUMN session TEXT` au unlock si la colonne n'existe pas (idempotent).

## Impact mesuré

Connecteur déjà connecté précédemment :
- Restart app → unlock vault → connect : **<3s** au lieu de 30-90s.
- Pas de 2FA SMS à valider à chaque restart.
- Pas de container ib-gateway redémarré inutilement.
