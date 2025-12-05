# Bokföringsapplikation

Detta är en Flask-baserad webbapplikation designad för att förenkla bokföring genom att automatisera hanteringen av banktransaktioner, fakturor och underlag. Applikationen använder Google Gemini för att ge intelligenta bokföringsförslag och har ett flexibelt system för att matcha delbetalningar mot fakturor och bilagor.

## Huvudfunktioner

- **Företagshantering**: Skapa och hantera flera företagsprofiler.
- **CSV-import**: Ladda upp banktransaktioner från CSV-filer.
- **AI-drivna Förslag**: Få automatiska bokföringsförslag för transaktioner och fakturor med hjälp av Google Gemini.
- **Fakturasynkronisering**: Synkronisera kundfakturor från externa system (för närvarande Fakturan.nu).
- **Avancerad Matchning**: Ett dedikerat gränssnitt för att matcha en eller flera transaktioner mot en eller flera fakturor/bilagor, med stöd för delbetalningar.
- **Manuell Bokföring**: En flexibel modal för att skapa och redigera verifikationer manuellt.
- **SIE-export**: Generera SIE-filer för import till andra redovisningssystem.

## Installation och Konfiguration

### Förutsättningar
- Python 3.10+
- En SOCKS5-proxy (för anrop till externa API:er)

### Steg
1.  **Klona projektet:**
    ```bash
    git clone <repository-url>
    cd <repository-folder>
    ```

2.  **Skapa och aktivera en virtuell miljö:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Installera beroenden:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Konfigurera Miljövariabler:**
    Skapa en `.env`-fil i projektets rotkatalog och lägg till följande variabler:

    ```
    # Flask-inställningar
    FLASK_APP=run.py
    FLASK_ENV=development
    SECRET_KEY='en_mycket_hemlig_nyckel'

    # API-nyckel för Google Gemini
    GEMINI_API_KEY='din_gemini_api_nyckel'

    # SOCKS5 Proxy för externa anrop
    SOCKS5_PROXY='socks5h://användare:lösenord@din_proxy_host:port'
    ```

5.  **Initialisera Databasen:**
    Kör följande kommandon för att skapa och applicera databasmigreringar:
    ```bash
    flask db init  # Körs bara första gången
    flask db migrate -m "Initial migration"
    flask db upgrade
    ```

6.  **Kör applikationen:**
    ```bash
    flask run
    ```
    Applikationen är nu tillgänglig på `http://127.0.0.1:5000`.

## Databasmodeller

Applikationen använder SQLAlchemy och följande huvudmodeller (se `bokforing_app/models.py` för detaljer):

- **Company**: Huvudmodellen för ett företag.
- **BankTransaction**: Representerar en verifikation.
- **BookkeepingEntry**: En rad i en verifikation.
- **Invoice**: En kundfaktura.
- **Bilaga**: Ett uppladdat underlag (kvitto/faktura).
- **Matchning**: Kärnan i matchningssystemet. En instans av denna modell representerar en specifik summa som kopplar en `BankTransaction` till en `Invoice` eller en `Bilaga`. Detta möjliggör många-till-många-relationer med delbetalningar.
- **Association**: En regel för AI:n som kopplar ett nyckelord till ett konto.
- **Setting**: För generella inställningar, som anpassade AI-prompts.

## Projektstruktur

- `run.py`: Applikationens startpunkt.
- `bokforing_app/`: Huvudpaketet för applikationen.
  - `__init__.py`: Skapar och konfigurerar Flask-appen.
  - `models.py`: Definierar alla databasmodeller.
  - `main/`: Innehåller routes som renderar HTML-sidor.
  - `api/`: Innehåller alla API-slutpunkter som anropas av JavaScript.
  - `services/`: Innehåller affärslogik och kommunikation med externa tjänster (Gemini, Fakturan.nu).
  - `templates/`: Innehåller alla HTML/Jinja2-mallar.
  - `static/`: Innehåller statiska filer som CSS och JavaScript.
