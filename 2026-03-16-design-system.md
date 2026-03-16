# MM Ledger — Design System

Dashboard de visualisation de portefeuille Trade Republic. Dark mode, esprit luxueux "Private Bank".

**Stack** : React, Recharts, Inter (Google Fonts)

---

## Palette

### Core (UI principale)

| Role | Nom | Hex | Usage |
|------|-----|-----|-------|
| Background | Deep Space Blue | `#102b3f` | Fond global |
| Surface | Evergreen | `#062726` | Cards, panneaux, modales |
| Surface Elevated | — | `#143a42` | Cards hover, elements sureleves |
| Accent primaire | Gold | `#C9A84C` | CTA, gains, valeurs cles, bordures d'emphase |
| Accent secondaire | Lavender Purple | `#a06cd5` | Hover states, liens, elements interactifs |
| Accent tertiaire | Deep Lilac | `#6247aa` | Tags, badges, accents secondaires |
| Text Primary | — | `#f0ece4` | Texte principal (blanc casse chaud) |
| Text Secondary | Thistle | `#e2cfea` | Labels, texte secondaire |
| Text Muted | — | `#e2cfea80` | Thistle 50%, placeholders, texte desactive |
| Gain | Gold | `#C9A84C` | Variations positives |
| Loss | Thistle Muted | `#e2cfea70` | Variations negatives |
| Border | — | `#1a3d4d` | Separateurs, bordures subtiles |

### Data Viz (charts & graphiques uniquement)

| Ordre | Nom | Hex |
|-------|-----|-----|
| 1 | Azure Blue | `#2c7ce5` |
| 2 | Saffron | `#f8c421` |
| 3 | Malachite | `#49cc5c` |
| 4 | Electric Indigo | `#6434e9` |
| 5 | Tomato | `#fb6640` |
| 6 | Hot Fuchsia | `#f82553` |

Ces couleurs ne sont utilisees que dans les charts, jamais dans l'UI generale.

---

## Typographie

**Font** : Inter (sans-serif), Google Fonts.

| Role | Taille | Weight | Couleur | Usage |
|------|--------|--------|---------|-------|
| H1 | 32px | 600 | Text Primary | Valeur totale du portefeuille |
| H2 | 24px | 600 | Text Primary | Titres de sections |
| H3 | 18px | 500 | Text Primary | Titres de cards |
| Body | 14px | 400 | Text Primary | Texte courant |
| Body Small | 12px | 400 | Text Secondary | Labels, legendes |
| Caption | 11px | 400 | Text Muted | Timestamps, disclaimers |
| Montant Large | 40px | 700 | Gold | Valeur totale hero |
| Montant | 18px | 600 | Text Primary / Gold | Valeurs dans les cards |
| Variation | 14px | 500 | Gold / Thistle Muted | +2.34%, -1.12% |

Tous les montants et pourcentages : `font-variant-numeric: tabular-nums`.

---

## Spacing (base 4px)

| Token | Valeur | Usage |
|-------|--------|-------|
| `space-xs` | 4px | Espacement interne minimal |
| `space-sm` | 8px | Gap entre elements proches |
| `space-md` | 16px | Padding interne des cards |
| `space-lg` | 24px | Gap entre cards |
| `space-xl` | 32px | Marges de sections |
| `space-2xl` | 48px | Separation entre grandes sections |

## Border Radius

| Token | Valeur | Usage |
|-------|--------|-------|
| `radius-sm` | 4px | Badges, tags |
| `radius-md` | 8px | Boutons, inputs |
| `radius-lg` | 12px | Cards |
| `radius-xl` | 16px | Modales, panneaux |

## Ombres

Pas de box-shadow (inadapte au dark mode). A la place :
- Bordures subtiles (`Border`) pour delimiter les cards
- Fond eleve (`Surface Elevated`) pour la hierarchie visuelle
- Glow dore optionnel : `0 0 20px #C9A84C15` sur les elements d'emphase
