# Patches appliqués au module woob `banquepopulaire`

Le module woob `banquepopulaire` (v3.7) est cassé upstream. Deux patches sont nécessaires pour que la connexion fonctionne. Les fichiers patchés se trouvent dans `~/.local/share/woob/modules/3.7/woob_modules/banquepopulaire/`.

## Contexte

Le site Banque Populaire (icgauth.banquepopulaire.fr) a subi deux changements récents qui cassent le module woob :

1. Les OAuth client IDs ne sont plus hardcodés dans les chunks JavaScript
2. Le clavier virtuel génère des images différentes à chaque session (les MD5 ne sont plus stables)

## Patch 1 : OAuth client IDs (`browser.py` + `pages.py`)

### Problème

Le login OAuth nécessite deux client IDs :
- `oauth_token_client_id` : pour obtenir un token anonyme (POST vers `as-ano-bad-ib.banquepopulaire.fr/api/oauth/v2/token`)
- `oauth_autorize_client_id` : pour l'authorize flow (GET vers `as-ext-bad-ib.banquepopulaire.fr/api/oauth/v2/authorize`)

Avant, ces IDs étaient hardcodés dans les fichiers JS chunks (`chunk-XXXXXXXX.js`) du front se-connecter, et woob les extrayait via regex. Maintenant, le JS utilise des placeholders (`#ANO_CLIENT_ID#`, `#RIA_CLIENT_ID#`) remplacés au runtime par les valeurs de `xld-keys.json`.

### Comment on a trouvé les bons IDs

1. On a téléchargé le main JS depuis la page de login
2. On a listé les 92 chunks référencés
3. On a trouvé le chunk config (`chunk-HN6EVBPP.js`) contenant `gatewayAccess`
4. On a extrait les déclarations de variables avec `sed 's/,/,\n/g'` et `grep`
5. On a trouvé le mapping :
   - Variable `u` = `#ANO_CLIENT_ID#` → client ID anonyme (pour le token)
   - Variable `Oe` = `#RIA_CLIENT_ID#` → client ID authorize
6. Les vraies valeurs sont dans `https://www.icgauth.banquepopulaire.fr/se-connecter/assets/xld-keys.json`

### Modification dans `pages.py`

Ajout d'une nouvelle classe `SeConnecterKeysPage` qui parse le JSON `xld-keys.json` :

```python
class SeConnecterKeysPage(JsonPage):
    def get_ano_client_id(self):
        return Dict("#ANO_CLIENT_ID#")(self.doc)

    def get_ria_client_id(self):
        return Dict("#RIA_CLIENT_ID#")(self.doc)
```

### Modification dans `browser.py`

1. Import de `SeConnecterKeysPage`
2. Ajout d'une URL :
   ```python
   se_connecter_keys = URL(r"/se-connecter/assets/xld-keys.json", SeConnecterKeysPage, base="URL_ICG")
   ```
3. Fallback dans `do_new_login()` — après la boucle qui scan les chunks, si les IDs ne sont pas trouvés :
   ```python
   if oauth_token_client_id == "" or oauth_autorize_client_id == "":
       self.logger.debug("Client IDs not found in chunks, trying se-connecter xld-keys.json")
       self.se_connecter_keys.go()
       if oauth_token_client_id == "":
           oauth_token_client_id = self.page.get_ano_client_id()
       if oauth_autorize_client_id == "":
           oauth_autorize_client_id = self.page.get_ria_client_id()
   ```

## Patch 2 : Clavier virtuel (`pages.py`)

### Problème

La classe `BPOVirtKeyboard` héritait de `SplitKeyboard` et utilisait un dictionnaire `char_to_hash` qui mappait chaque chiffre (0-9) à des MD5 d'images connues. Le site génère maintenant des rendus légèrement différents à chaque session (anti-scraping), donc les hashes ne matchent plus.

### Solution

Remplacement complet de `BPOVirtKeyboard` : au lieu du hash matching, on utilise `pytesseract` (OCR) pour identifier chaque chiffre.

```python
class BPOVirtKeyboard:
    codesep = " "

    def __init__(self, browser, images):
        import pytesseract
        from PIL import ImageOps

        self.char_to_code = {}
        whitelist = "-c tessedit_char_whitelist=0123456789"

        for img_item in images:
            # ... download et preprocess image (inchangé) ...

            # Compute pixel density for disambiguation
            pixels = list(img.getdata())
            black_ratio = sum(1 for p in pixels if p == 0) / len(pixels)

            # Try multiple OCR strategies
            digit = None
            for prep in [img, scaled_3x, padded]:
                result = pytesseract.image_to_string(prep, config=f"--psm 10 {whitelist}").strip()
                if result and len(result) == 1 and result in "0123456789":
                    digit = result
                    break

            # Disambiguation : tesseract confond parfois "1" et "4"
            # Le "1" est le chiffre le plus fin (ratio pixels noirs < 10%)
            if digit == "4" and black_ratio < 0.10:
                digit = "1"

            self.char_to_code[digit] = img_item["value"]

    def get_string_code(self, password):
        return self.codesep.join(self.char_to_code[c] for c in password)
```

### Dépendance ajoutée

`pytesseract` (pip) + `tesseract` (brew) sont nécessaires :
```bash
pip install pytesseract
brew install tesseract
```

## Résumé des fichiers modifiés

| Fichier | Changement |
|---------|-----------|
| `pages.py` | + classe `SeConnecterKeysPage`, remplacement de `BPOVirtKeyboard` (hash → OCR) |
| `browser.py` | + import `SeConnecterKeysPage`, + URL `se_connecter_keys`, + fallback xld-keys.json dans `do_new_login` |

## Note

Ces patches sont un workaround local. Le bug upstream est connu (voir issue woob GitLab). Quand woob sortira un fix, ces patches ne seront plus nécessaires et `woob update` les écrasera.
