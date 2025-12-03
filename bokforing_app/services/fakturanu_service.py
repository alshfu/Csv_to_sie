import os
import requests
from requests.auth import HTTPBasicAuth
import json

BASE_URL = "https://www.fakturan.nu/api/v2"

def _get_proxies():
    proxy_url = os.getenv("SOCKS5_PROXY")
    if proxy_url:
        return {"http": proxy_url, "https": proxy_url}
    return None

def _make_request(method, endpoint, api_key_id, api_password, params=None, data=None):
    """Centraliserad funktion för att göra API-anrop."""
    if not api_key_id or not api_password:
        return {'error': 'API-nyckel eller lösenord saknas.'}
    
    url = f"{BASE_URL}/{endpoint}"
    auth = HTTPBasicAuth(api_key_id, api_password)
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.request(
            method,
            url,
            auth=auth,
            params=params,
            data=json.dumps(data) if data else None,
            headers=headers,
            proxies=_get_proxies(),
            timeout=60
        )
        response.raise_for_status()
        if response.status_code == 204: # No Content
            return {'success': True}
        return response.json()
    except requests.exceptions.HTTPError as e:
        return {'error': f'HTTP-fel: {e.response.status_code} {e.response.reason}', 'details': e.response.text}
    except requests.exceptions.RequestException as e:
        return {'error': f'Nätverksfel: {e}'}
    except Exception as e:
        return {'error': f'Oväntat fel: {e}'}

def get_invoices(api_key_id, api_password, params=None):
    """Hämtar en lista över fakturor."""
    return _make_request('GET', 'invoices', api_key_id, api_password, params=params)

def get_invoice_details(api_key_id, api_password, fakturanu_id):
    """Hämtar detaljerad information för en enskild faktura."""
    return _make_request('GET', f'invoices/{fakturanu_id}', api_key_id, api_password)

def get_client_details(api_key_id, api_password, fakturanu_client_id):
    """Hämtar detaljerad information för en enskild klient."""
    return _make_request('GET', f'clients/{fakturanu_client_id}', api_key_id, api_password)

def add_payment(api_key_id, api_password, fakturanu_id, data):
    """Lägger till en betalning på en faktura."""
    return _make_request('POST', f'invoices/{fakturanu_id}/payments', api_key_id, api_password, data=data)

def update_invoice(api_key_id, api_password, fakturanu_id, data):
    """Uppdaterar en faktura, t.ex. för att markera som betald."""
    return _make_request('PUT', f'invoices/{fakturanu_id}', api_key_id, api_password, data=data)
