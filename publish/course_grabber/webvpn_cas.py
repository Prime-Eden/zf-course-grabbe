"""Pure-requests login through Sangfor webvpn + CAS (no slider captcha)."""
import json
import os
import re
import sys
import time
from urllib.parse import urljoin, urlsplit, urlparse, parse_qs

import requests

WEBVPN_BASE = 'https://webvpn1.hzcu.edu.cn'
CAS_ORIGIN = 'http://ca-hzcu-edu-cn.webvpn1.hzcu.edu.cn:8118'
IJW_BASE = 'http://ijw-hzcu-edu-cn.webvpn1.hzcu.edu.cn:8118'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0')


def new_session():
    requests.packages.urllib3.disable_warnings()
    s = requests.Session()
    s.verify = False
    s.headers.update({'User-Agent': UA})
    return s


def get_auth_config(s):
    url = WEBVPN_BASE + '/passport/v1/public/authConfig'
    params = {
        'clientType': 'SDPBrowserClient',
        'platform': 'Windows',
        'lang': 'zh-CN',
        'needTicket': '1',
    }
    r = s.get(url, params=params, timeout=20,
              headers={'Referer': WEBVPN_BASE + '/portal/#!/login'})
    r.raise_for_status()
    data = r.json()
    if data.get('code') != 0:
        raise RuntimeError('authConfig failed: %s' % data.get('message'))
    return data


def _cas_login_page(s):
    url = WEBVPN_BASE + '/passport/v1/public/casLogin'
    r = s.get(url, timeout=20, allow_redirects=True)
    r.raise_for_status()
    html = r.text
    form = re.search(r'<form[^>]+action="([^"]+)"', html)
    if not form:
        raise RuntimeError('CAS login form not found')
    lt = re.search(r'name="lt"\s+value="([^"]*)"', html)
    execution = re.search(r'name="execution"\s+value="([^"]*)"', html)
    return {
        'action': form.group(1),
        'lt': lt.group(1) if lt else '',
        'execution': execution.group(1) if execution else 'e1s1',
    }


def _extract_shortcut_ticket(url):
    params = parse_qs(urlsplit(url).query)
    data = params.get('data', [''])[0]
    if not data:
        return None
    try:
        return json.loads(data).get('ticket')
    except Exception:
        return None


def _complete_webvpn_handshake(s, ticket):
    q = '?clientType=SDPBrowserClient&platform=Windows&lang=zh-CN'
    device_id = os.urandom(32).hex()
    body = {
        'ticket': ticket,
        'deviceId': device_id,
        'env': {
            'endpoint': {
                'device_id': device_id,
                'device': {'type': 'browser'},
            }
        },
    }
    s.post(WEBVPN_BASE + '/controller/v1/public/reportEnv' + q,
           json=body, timeout=20)
    s.get(WEBVPN_BASE + '/passport/v1/auth/authCheck' + q, timeout=20)
    s.post(WEBVPN_BASE + '/passport/v1/public/ticketExchange' + q,
           timeout=20)


def login_cas(s, username, password):
    get_auth_config(s)
    form = _cas_login_page(s)
    login_url = urljoin(CAS_ORIGIN, form['action'])
    data = {
        'username': username,
        'password': password,
        'authType': '0',
        'lt': form['lt'],
        'execution': form['execution'],
        '_eventId': 'submit',
        'validTime': '5',
    }
    r = s.post(login_url, data=data, timeout=20, allow_redirects=False,
               headers={'Referer': login_url})
    if r.status_code not in (301, 302, 303, 307, 308):
        raise RuntimeError('CAS login rejected, status=%s' % r.status_code)
    location = r.headers.get('Location', '')
    if not location or 'ticket=' not in location:
        raise RuntimeError('CAS login rejected, no ticket redirect')
    service_url = urljoin(WEBVPN_BASE, location)
    r2 = s.get(service_url, timeout=20, allow_redirects=False)
    r2.raise_for_status()
    shortcut_url = r2.headers.get('Location', '')
    if not shortcut_url:
        raise RuntimeError('CAS ticket exchange missing shortcut redirect')
    shortcut_url = urljoin(WEBVPN_BASE, shortcut_url)
    ticket = _extract_shortcut_ticket(shortcut_url)
    if not ticket:
        raise RuntimeError('CAS ticket exchange missing data ticket')
    s.get(shortcut_url, timeout=20, allow_redirects=True).raise_for_status()
    _complete_webvpn_handshake(s, ticket)
    return True


def login_ijw(s):
    url = IJW_BASE + '/sso/ddlogin'
    r = s.get(url, timeout=20, allow_redirects=False)
    location = r.headers.get('Location', '')
    if location:
        verify_url = urljoin(WEBVPN_BASE, location)
        r2 = s.get(verify_url, timeout=20, allow_redirects=False)
        r2.raise_for_status()
        if r2.status_code in (301, 302, 303, 307, 308):
            app_url = urljoin(verify_url, r2.headers.get('Location', ''))
            r3 = s.get(app_url, timeout=20, allow_redirects=True)
            r3.raise_for_status()
            return r3.url
        return r2.url
    r3 = s.get(url, timeout=20, allow_redirects=True)
    r3.raise_for_status()
    return r3.url


def verify_ijw(s):
    url = IJW_BASE + '/xtgl/index_initMenu.html'
    r = s.get(url, timeout=20, allow_redirects=True)
    parts = urlsplit(r.url or '')
    return (parts.hostname == 'ijw-hzcu-edu-cn.webvpn1.hzcu.edu.cn'
            and parts.path.startswith('/xtgl/index_initMenu'))


def cookies_to_dicts(s):
    out = []
    for c in s.cookies:
        out.append({
            'name': c.name,
            'value': c.value,
            'domain': c.domain,
            'path': c.path or '/',
            'expires': c.expires,
            'httpOnly': None,
            'secure': c.secure,
            'sameSite': None,
        })
    return out


def login_and_save(username, password, session_file=None):
    session_file = session_file or os.path.join(
        os.path.dirname(__file__), 'session_webvpn.json')
    s = new_session()
    login_cas(s, username, password)
    final_url = login_ijw(s)
    if not verify_ijw(s):
        raise RuntimeError('ijw session invalid after SSO')
    data = {
        'base_url': IJW_BASE,
        'username': username,
        'cookies': cookies_to_dicts(s),
        'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    with open(session_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return session_file, final_url


if __name__ == '__main__':
    username = os.environ.get('WEBVPN_USERNAME') or input('学号: ').strip()
    password = os.environ.get('WEBVPN_PASSWORD') or input('密码: ')
    try:
        path, final_url = login_and_save(username, password)
    except Exception as e:
        print('Login failed:', e)
        sys.exit(1)
    print('Saved session:', path)
    print('Final URL:', final_url)
