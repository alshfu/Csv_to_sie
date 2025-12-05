# -*- coding: utf-8 -*-
"""
Fristående skript för att diagnostisera SOCKS5-proxyanslutningen.

Detta skript är helt oberoende av Flask-applikationen och testar endast
den grundläggande nätverksanslutningen till en extern webbplats via
den proxy som är specificerad i miljövariabeln SOCKS5_PROXY.

Syfte:
Att isolera och bekräfta om anslutningsproblem (som 'Broken pipe')
beror på den lokala miljön (proxy-inställningar, proxy-serverns status)
eller på applikationens kod.

Hur man kör skriptet:
1. Se till att du har 'requests[socks]' installerat (`pip install "requests[socks]"`).
2. Se till att din SOCKS5_PROXY miljövariabel är satt.
3. Kör skriptet från terminalen: `python proxy_test.py`

Förväntat resultat:
- Om det lyckas: Skriptet skriver ut "SUCCESS" och HTML-innehållet från Google.
- Om det misslyckas: Skriptet skriver ut "FAILURE" och ett detaljerat felmeddelande,
  vilket bör vara samma 'Broken pipe'-fel som ses i applikationen.
"""
import os
import requests
import logging

# Konfigurera grundläggande loggning för att se detaljerad output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_proxy_settings():
    """
    Läser proxy-inställningar från miljövariabler.
    Detta är en förenklad version av logiken i appen för att testa anslutningen.
    """
    proxy_url = os.getenv("SOCKS5_PROXY")
    if proxy_url:
        # För att vara säker, testa med 'socks5h' som är mer robust
        if not proxy_url.startswith("socks5"):
            logging.warning("Proxy-URL bör starta med 'socks5://' eller 'socks5h://'. Försöker ändå.")
        
        # Om autentisering behövs, kan de läggas till här, men vi testar den enklaste formen först.
        # Exempel: "socks5h://user:pass@host:port"
        
        return {"http": proxy_url, "https": proxy_url}
    return None

def run_test():
    """
    Kör anslutningstestet.
    """
    target_url = "https://www.google.com"
    proxies = get_proxy_settings()

    if not proxies:
        logging.error("FAILURE: Miljövariabeln SOCKS5_PROXY är inte satt. Kan inte testa proxyn.")
        return

    logging.info(f"Försöker ansluta till {target_url} via proxy: {proxies.get('https')}")

    try:
        response = requests.get(target_url, proxies=proxies, timeout=30)
        response.raise_for_status()  # Kasta ett fel om statuskoden är 4xx eller 5xx

        logging.info(f"SUCCESS! Fick svar från {target_url}.")
        logging.info("Anslutningen via proxyn fungerar.")
        # print("\n--- Sidans början ---")
        # print(response.text[:500])
        # print("--- Sidans slut ---\n")

    except requests.exceptions.ProxyError as e:
        logging.error(f"FAILURE: Ett proxy-fel inträffade. Detta är grundorsaken till problemet.")
        logging.error(f"Felmeddelande: {e}")
        logging.error("Kontrollera att din proxy-server är igång och att URL:en i SOCKS5_PROXY är korrekt.")
    except requests.exceptions.RequestException as e:
        logging.error(f"FAILURE: Ett generellt nätverksfel inträffade.")
        logging.error(f"Felmeddelande: {e}")
    except Exception as e:
        logging.error(f"FAILURE: Ett oväntat fel inträffade.")
        logging.error(f"Felmeddelande: {e}")

if __name__ == "__main__":
    run_test()
