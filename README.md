# Teknisk dokumentation för projektet "Csv_to_sie"

## 1. Översikt över projektet

**Csv_to_sie** är ett webbapplikation utvecklat i Flask för bokföring. Huvudsyftet med applikationen är att förenkla processen för bearbetning och redovisning av finansiella dokument (kvitton, fakturor) och bankutdrag (CSV), deras laddning, analys och efterföljande bokföring i enlighet med kontoplanen.

Viktiga funktioner:
- Hantering av flera företag.
- Ladda upp och lagra finansiella dokument (PDF, JPG, PNG).
- **Bearbetning av CSV-filer med banktransaktioner.**
- Interaktivt gränssnitt för visning, redigering av metadata och bokföring av dokument.
- Inbyggd PDF-visare med navigations- och zoomfunktioner baserat på **PDF.js**.
- Automatiska förslag på konton baserat på associationsregler.
- Konvertering av data till SIE-format (standardformat för import/export av bokföringsdata i Sverige).

## 2. Teknisk stack

- **Backend:**
  - **Språk:** Python 3
  - **Ramverk:** Flask
  - **Databas:** Flask-SQLAlchemy (baserat på projektets struktur)
  - **Databehandling:** Pandas

- **Frontend:**
  - **HTML/CSS:** Mallningsverktyget Jinja2, ramverket Bootstrap 5.
  - **JavaScript:**
    - Inbyggd JavaScript (ES6 Modules).
    - **PDF.js** (lokal version `5.4.394-dist`) för rendering av PDF.
    - **Tom-select** för autouppfyllning i fält för konto-val.

- **Miljö:**
  - **Virtuell miljö:** `venv`
  - **Versionshanteringssystem:** Git

## 3. Projektstruktur

```
/
├── bokforing_app/            # Huvudpaketet för applikationen
│   ├── api/                  # Moduler för API-endpunkter
│   ├── services/             # Affärslogik (hantering av PDF, CSV, bokföring)
│   ├── static/               # Statiska filer
│   │   ├── css/
│   │   ├── js/
│   │   │   ├── bilagaPage.js         # Logik för sidan "Bilagor"
│   │   │   ├── kontoAutocomplete.js  # Logik för autouppfyllning av konton
│   │   │   └── pdfjs-5.4.394-dist/ # Lokal bibliotek för PDF.js
│   │   └── uploads/            # Uppladdade filer från användaren
│   ├── templates/            # HTML-mallar (Jinja2)
│   │   ├── bilagor.html        # Sida för arbete med dokument
│   │   └── base.html           # Bas-mall
│   ├── __init__.py           # Initiering av Flask-applikationen
│   └── models.py             # Databasmodeller (SQLAlchemy)
│
├── instance/                 # Instansfiler (t.ex. SQLite-databas)
├── venv/                     # Virtuell miljö
└── README.md                 # Denna dokumentation
```

## 4. Installation och körning

1.  **Klona repositoryn:**
    ```bash
    git clone <repository_url>
    cd Csv_to_sie
    ```

2.  **Skapa och aktivera virtuell miljö:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # För macOS/Linux
    # eller
    venv\Scripts\activate     # För Windows
    ```

3.  **Installera beroenden:**
    (Antas att filen `requirements.txt` finns)
    ```bash
    pip install -r requirements.txt
    ```
    *Om filen saknas, huvudberoenden: `Flask`, `Flask-SQLAlchemy`, `Flask-Migrate`, `pandas`.*

4.  **Initiera och tillämpa databas-migreringar:**
    ```bash
    flask db init
    flask db migrate -m "Initial migration."
    flask db upgrade
    ```

5.  **Kör applikationen:**
    ```bash
    flask run
    ```
    Applikationen kommer att vara tillgänglig på adressen `http://127.0.0.1:5000`.

## 5. Bearbetning av CSV-filer

Systemet tillåter uppladdning av CSV-filer med banktransaktioner för automatisk bearbetning och skapande av bokförings poster.

- **Endpunkt:** `POST /api/company/<int:company_id>/upload_csv`
- **Tjänst:** `booking_service.process_csv_upload`

### Krav på CSV-format:
- **Kodning:** `latin-1`
- **Fältskilltecken:** semikolon (`;`)
- **Decimaltecken:** komma (`,`)
- **Rubriker:** Data förväntas börja från andra raden (`header=1`).
- **Viktiga kolumner:** `Bokföringsdag`, `Insättning/Uttag`, `Referens`.

### Bearbetningslogik:
1.  Filen läses med biblioteket **Pandas**.
2.  För varje rad i filen skapas en post `BankTransaction`.
3.  Baserat på belopp (`Insättning/Uttag`) och referenstext (`Referens`) bestäms motkonto med hjälp av funktionen `get_contra_account`.
4.  Automatiskt skapas två bokföringsposter (`BookkeepingEntry`): en för bankkontot (`1930`), en för motkontot, vilket säkerställer dubbel bokföring.

## 6. Viktiga API-endpunkter

Alla endpunkter finns i paketet `bokforing_app/api/`.

- `POST /api/company/<int:company_id>/multi_upload_bilagor`
  - **Syfte:** Massuppladdning av filer (dokument).
  - **Request-kropp:** `FormData` med filer i fältet `files`.
  - **Svar:** JSON-array med information om uppladdade filer.

- `POST /api/bilaga/<int:bilaga_id>/metadata`
  - **Syfte:** Spara uppdaterade metadata för dokumentet.
  - **Request-kropp:** JSON med dokumentfält (t.ex. `fakturadatum`, `saljare_namn` osv.).
  - **Svar:** JSON med meddelande om framgång eller fel.

- `POST /api/bilaga/<int:bilaga_id>/bokfor`
  - **Syfte:** Bokför dokument med angivna bokföringsposter.
  - **Request-kropp:** JSON med array `entries`, där varje objekt innehåller `konto`, `debet`, `kredit`.
  - **Svar:** JSON med meddelande om framgång eller fel.

- `DELETE /api/bilaga/<int:bilaga_id>`
  - **Syfte:** Ta bort dokument.
  - **Svar:** JSON med meddelande om framgång.