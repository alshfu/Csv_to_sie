# -*- coding: utf-8 -*-
"""
Centraliserad service för hantering av proxy-inställningar.

Denna modul ansvarar för att hämta, validera och tillhandahålla
proxy-konfigurationer för hela applikationen. Den läser från
miljövariabeln SOCKS5_PROXY och inkluderar en proaktiv kontroll
för att säkerställa att proxyn är nåbar innan den används.
"""
import os
import socket
import logging
from typing import Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def is_proxy_alive(proxy_url: str) -> bool:
    """
    Kontrollerar om en proxy-server är nåbar på en grundläggande TCP-nivå.
    Returnerar True om en anslutning kan etableras, annars False.
    """
    try:
        parsed_url = urlparse(proxy_url)
        proxy_host = parsed_url.hostname
        proxy_port = parsed_url.port

        if not proxy_host or not proxy_port:
            logger.warning(f"Ogiltig proxy-URL för anslutningstest: {proxy_url}")
            return False

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect((proxy_host, proxy_port))

        logger.info(f"Proxy-anslutningstest till {proxy_host}:{proxy_port} lyckades.")
        return True
    except (socket.timeout, ConnectionRefusedError, OSError, TypeError) as e:
        logger.warning(f"Kunde inte ansluta till proxyn på {proxy_url}. Fel: {e}. Proxyn kommer att kringgås.")
        return False


def get_proxies() -> Optional[Dict[str, str]]:
    """
    Hämtar och validerar proxy-inställningar från miljövariabeln SOCKS5_PROXY.

    Om proxyn är konfigurerad men inte nåbar, loggas en varning och funktionen
    returnerar None, vilket effektivt inaktiverar proxy-användning för det anropet.

    Returns:
        En dictionary med proxy-inställningar (t.ex. {"http": ..., "https": ...})
        om en giltig och nåbar proxy hittas, annars None.
    """
    proxy_url = os.getenv("SOCKS5_PROXY", "").strip()

    if proxy_url:
        if not is_proxy_alive(proxy_url):
            logger.info("Proxy otillgänglig – kringgår proxy.")
            return None

        logger.info(f"Använder nåbar proxy från SOCKS5_PROXY: {proxy_url}")
        return {"http": proxy_url, "https": proxy_url}

    # Ingen loggning behövs här eftersom det är normalt att ingen proxy är satt.
    return None
