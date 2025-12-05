# -*- coding: utf-8 -*-
"""
Service för att kommunicera med Fakturan.nu API.
"""
import json
import logging
import time
from typing import Dict, Optional, Any
from urllib.parse import urljoin  # Ny: För att hantera relativa URL:er

import requests
from requests.auth import HTTPBasicAuth
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import ConnectionError

from . import proxy_service

logger = logging.getLogger(__name__)

BASE_URL = "https://www.fakturan.nu/api/v2"


def requests_retry_session(
    retries: int = 5,
    backoff_factor: float = 1,
    status_forcelist: tuple = (500, 502, 503, 504, 408, 429),
    session: Optional[requests.Session] = None,
) -> requests.Session:
    """
    Skapar en requests.Session med retry-logik för transienta fel.
    """
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "POST", "PUT"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def _make_request(
    method: str,
    endpoint: str,
    api_key_id: str,
    api_password: str,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    timeout: int = 60,
    use_proxy: bool = True,
    full_url: Optional[str] = None  # Ny: Stöd för full URL (för paginering)
) -> Dict[str, Any]:
    """
    Centraliserad funktion för att göra alla API-anrop till Fakturan.nu.
    Stödjer full URL för pagineringslänkar.
    """
    if not api_key_id or not api_password:
        return {'error': 'API-nyckel eller lösenord saknas.'}

    url = full_url or f"{BASE_URL}/{endpoint}"
    auth = HTTPBasicAuth(api_key_id, api_password)
    headers = {'Content-Type': 'application/json'}
    proxies = proxy_service.get_proxies() if use_proxy else None
    session = requests_retry_session()

    start_time = time.time()

    logger.info(f"--- REQUEST TILL FAKTURAN.NU API (Proxy: {'Ja' if use_proxy and proxies else 'Nej'}) ---")
    logger.info(f"Metod: {method}, URL: {url}")
    if params:
        logger.info(f"Params: {json.dumps(params, indent=2, ensure_ascii=False)}")
    if data:
        logger.info(f"Data: {json.dumps(data, indent=2, ensure_ascii=False)}")
    if proxies:
        logger.info(f"Proxy: {proxies}")
    logger.info("--- SLUT PÅ REQUEST ---")

    try:
        response = session.request(
            method,
            url,
            auth=auth,
            params=params,
            data=json.dumps(data) if data else None,
            headers=headers,
            proxies=proxies,
            timeout=timeout * (2 if not use_proxy else 1),
            verify=True
        )

        duration = time.time() - start_time
        logger.info(f"--- RESPONSE FRÅN FAKTURAN.NU API (Tid: {duration:.2f}s) ---")
        logger.info(f"Statuskod: {response.status_code}")
        logger.info(f"Body: {response.text[:1000]}...")
        logger.info("--- SLUT PÅ RESPONSE ---")

        response.raise_for_status()
        if response.status_code == 204:
            return {'success': True}
        return response.json()

    except (requests.exceptions.ProxyError, ConnectionError) as e:
        if use_proxy:
            logger.warning(f"Proxy-relaterat fel: {e}. Försöker igen utan proxy.")
            return _make_request(method, endpoint, api_key_id, api_password, params, data, timeout, use_proxy=False, full_url=full_url)
        else:
            error_message = f'Nätverksfel utan proxy: {e}'
            logger.error(error_message)
            return {'error': error_message}
    except requests.exceptions.Timeout as e:
        error_message = f'Timeout-fel (väntade {timeout}s): {e}.'
        logger.error(error_message)
        return {'error': error_message}
    except requests.exceptions.RequestException as e:
        error_message = f'Nätverksfel: {e}'
        logger.error(error_message)
        return {'error': error_message}
    except Exception as e:
        error_message = f'Oväntat fel: {e}'
        logger.error(error_message, exc_info=True)
        return {'error': error_message}


def get_invoices(api_key_id: str, api_password: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Hämtar en lista över alla fakturor med paginering baserat på API-dokumentationen.
    Följer 'next'-länken för att hämta efterföljande sidor.
    Returnerar {'invoices': [list of all invoices], 'total_count': int, 'total_pages': int}.
    """
    all_invoices = []
    next_url = None
    current_page = 0
    total_pages = 0  # Uppdateras från respons
    base_timeout = 120  # Per sida

    # Initial anrop med endpoint och params (t.ex. start_date, end_date)
    result = _make_request('GET', 'invoices', api_key_id, api_password, params=params, timeout=base_timeout)
    if 'error' in result:
        return result

    # Hämta första sidans data
    page_invoices = result.get('data', [])
    all_invoices.extend(page_invoices)
    paging = result.get('paging', {})
    total_pages = paging.get('total_pages', 1)
    current_page = paging.get('current_page', 1)
    next_url = paging.get('next')

    logger.info(f"Hämtade sida {current_page} ({len(page_invoices)} fakturor).")

    # Loop för efterföljande sidor via 'next'
    while next_url:
        # Använd full_url för nästa anrop (lägg till BASE_URL om relativ)
        full_next_url = urljoin(BASE_URL, next_url) if next_url.startswith('/') else next_url

        result = _make_request('GET', '', api_key_id, api_password, timeout=base_timeout, full_url=full_next_url)
        if 'error' in result:
            return result

        page_invoices = result.get('data', [])
        all_invoices.extend(page_invoices)
        paging = result.get('paging', {})
        current_page = paging.get('current_page', current_page + 1)
        next_url = paging.get('next')

        logger.info(f"Hämtade sida {current_page} ({len(page_invoices)} fakturor).")

    logger.info(f"Hämtade totalt {len(all_invoices)} fakturor från {total_pages} sidor.")
    return {
        'invoices': all_invoices,
        'total_count': len(all_invoices),
        'total_pages': total_pages
    }


def get_invoice_details(api_key_id: str, api_password: str, fakturanu_id: int) -> Dict[str, Any]:
    """Hämtar detaljerad information för en specifik faktura."""
    return _make_request('GET', f'invoices/{fakturanu_id}', api_key_id, api_password)


def get_client_details(api_key_id: str, api_password: str, fakturanu_client_id: int) -> Dict[str, Any]:
    """Hämtar detaljerad information för en specifik kund."""
    return _make_request('GET', f'clients/{fakturanu_client_id}', api_key_id, api_password)


def add_payment(api_key_id: str, api_password: str, fakturanu_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """Registrerar en betalning för en specifik faktura."""
    return _make_request('POST', f'invoices/{fakturanu_id}/payments', api_key_id, api_password, data=data)


def update_invoice(api_key_id: str, api_password: str, fakturanu_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """Uppdaterar en befintlig faktura."""
    return _make_request('PUT', f'invoices/{fakturanu_id}', api_key_id, api_password, data=data)