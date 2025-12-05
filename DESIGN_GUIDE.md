# Designguide för Bokföringsappen

Detta dokument beskriver de designprinciper, komponenter och riktlinjer som ska följas vid utveckling av denna applikation. Målet är att skapa ett enhetligt, professionellt och användarvänligt gränssnitt.

## 1. Grundläggande Designprinciper

### 1.1. Färgschema

Vi använder ett begränsat och konsekvent färgschema som definieras med CSS-variabler i `static/css/custom.css`. Använd alltid dessa variabler istället för hårdkodade färgvärden.

| Variabel              | Värde       | Användning                               |
| --------------------- | ----------- | ---------------------------------------- |
| `--primary-color`     | `#0d6efd`   | Primära knappar, aktiva länkar, accenter. |
| `--secondary-color`   | `#6c757d`   | Sekundära knappar, mindre viktig text.   |
| `--success-color`     | `#198754`   | Positiva statusar, framgångsmeddelanden. |
| `--danger-color`      | `#dc3545`   | Felmeddelanden, raderaknappar, varningar. |
| `--background-color`  | `#f8f9fa`   | Global bakgrundsfärg för `<body>`.      |
| `--text-color`        | `#212529`   | Brödtext och generell text.              |

### 1.2. Typografi

Applikationen använder typsnittet **Roboto** för ett rent och professionellt utseende.

- **Typsnitt:** `Roboto`, `sans-serif` (laddas från Google Fonts).
- **Grundstorlek:** `1rem` (16px).
- **Brödtext:** `font-weight: 400`.
- **Rubriker:** Använd `font-weight: 500` eller `700` för visuell hierarki.

### 1.3. Spacing (Utrymme)

Allt utrymme (marginaler och padding) baseras på en grundenhet för att skapa en visuell rytm.

- **Spacing-enhet:** `var(--spacing-unit)` är `1rem`. Använd multiplar av denna enhet (t.ex. `margin-bottom: var(--spacing-unit);`, `padding: calc(var(--spacing-unit) / 2);`).

## 2. Layout

### 2.1. Sidstruktur

Varje sida ska ha en konsekvent grundstruktur.

- **Huvudcontainer:** Allt innehåll i `{% block content %}` ska omslutas av en container. Huvudvyn använder `px-md-4 py-4` för enhetlig padding.
- **Sidhuvud:** Varje sida ska definiera en sidtitel med `{% block page_title %}` som renderas i ett standardiserat sidhuvud.

```html
{% extends 'base.html' %}
{% block page_title %}Sidans Titel{% endblock %}

{% block content %}
    <!-- Innehållet placeras här -->
{% endblock %}
```

## 3. Komponenter

### 3.1. Kort (Cards)

Kort är den primära containern för grupperat innehåll. De har en enhetlig stil som definieras globalt.

- **Klass:** Använd `.card`. Undvik extra klasser som `shadow-sm` eller `border-0` då detta hanteras i `custom.css`.
- **Header:** `.card-header` har en ljus bakgrund och en subtil border.

**Exempel:**
```html
<div class="card">
    <div class="card-header">
        <h5 class="card-title mb-0">Kortets Titel</h5>
    </div>
    <div class="card-body">
        ...
    </div>
</div>
```

### 3.2. Knappar (Buttons)

Knappar ska vara konsekventa i stil och storlek.

- **Primär handling:** Använd `.btn-primary` (t.ex. "Spara", "Ladda upp").
- **Sekundär handling:** Använd `.btn-secondary` (t.ex. "Avbryt").
- **Farlig handling:** Använd `.btn-danger` (t.ex. "Radera").
- **Ikoner:** Inkludera ikoner från Bootstrap Icons för tydlighet. Placera ikonen före texten med klassen `me-1` eller `me-2` för avstånd.

**Exempel:**
```html
<!-- Primär knapp -->
<button class="btn btn-primary">
    <i class="bi bi-check-circle me-1"></i> Spara
</button>

<!-- Farlig knapp -->
<button class="btn btn-danger">
    <i class="bi bi-trash me-1"></i> Radera
</button>
```

### 3.3. Tabeller (Tables)

Tabeller används för att visa data och ska vara sorterbara med DataTables.

- **Klasser:** Använd `.table`, `.table-hover`, `.table-striped` och `.datatable`.
- **Header:** Använd `<thead>` med `class="table-dark"` för tydlig kontrast.

### 3.4. Modalfönster (Modals)

Modalfönster används för fokuserade uppgifter som redigering och skapande av poster.

- **Storlek och position:** Använd `.modal-xl` och `.modal-dialog-centered` för ett brett och centrerat fönster.
- **Knapp-layout:**
    - **Farlig handling (Radera):** Vänsterjusterad (`me-auto`).
    - **Neutral handling (Avbryt):** Högerjusterad.
    - **Primär handling (Spara):** Längst till höger, med `.btn-primary`.
- **Laddningsindikator:** "Spara"-knappen ska innehålla en spinner som visas vid submit för att ge användaren feedback.

**Exempel (modal-footer):**
```html
<div class="modal-footer">
    <button type="button" class="btn btn-danger me-auto" id="delete-entry-btn-modal">
        <i class="bi bi-trash me-1"></i>Radera
    </button>
    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Avbryt</button>
    <button type="submit" class="btn btn-primary" id="save-entry-btn">
        <span class="spinner-border spinner-border-sm d-none" role="status"></span>
        <i class="bi bi-check-circle me-1"></i>
        Spara
    </button>
</div>
```

### 3.5. Meddelanden (Notifications)

Använd **inte** webbläsarens inbyggda `alert()`. Använd istället den globala `showToast()`-funktionen.

- **Funktion:** `showToast(message, category)`
- **Användning:** Anropas från JavaScript för att visa ett icke-blockerande meddelande.
- **Kategorier:** `'success'`, `'danger'`, `'warning'`, `'info'`.

**Exempel:**
```javascript
showToast('Verifikationen har sparats!', 'success');
showToast('Fel: Fältet får inte vara tomt.', 'danger');
```

## 4. JavaScript

### 4.1. `utils.js`

Återanvändbar logik ska placeras i `static/js/utils.js`. Detta inkluderar funktioner som:
- `showToast()`
- `createEntryRow()`
- `updateTotals()`

Importera alltid `utils.js` i `base.html` så att funktionerna är globalt tillgängliga.

---
*Detta dokument ska uppdateras löpande när nya komponenter utvecklas eller befintliga designprinciper ändras.*
