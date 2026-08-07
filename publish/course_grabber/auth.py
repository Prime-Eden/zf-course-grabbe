# Auth module - requests + PKCS#1 v1.5 RSA + Playwright captcha login + heartbeat
import os, json, base64, re, time, requests, threading
from urllib.parse import urljoin

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
BASE_URL = 'http://ijw.hzcu.edu.cn'
SESSION_FILE = os.path.join(os.path.dirname(__file__), 'session.json')


class JW_Session:
    def __init__(self, base_url=BASE_URL, session_file=None):
        self.base_url = base_url
        self.session_file = session_file or SESSION_FILE
        self.sess = requests.Session()
        self.sess.headers.update({'User-Agent': UA})
        self.sess.verify = False
        self.logged_in = False
        self.username = None
        self.csrf_token = None
        self.modulus = None
        self.exponent = None
        self.student_info = {}
        self._heartbeat_thread = None
        self._heartbeat_running = False

    def _req(self, path, method='GET', data=None, expect_json=False):
        url = urljoin(self.base_url, path)
        if method == 'GET':
            resp = self.sess.get(url, params=data, timeout=15)
        else:
            resp = self.sess.post(url, data=data, timeout=15)
        resp.raise_for_status()
        if expect_json:
            return resp.json()
        return resp.text

    # -- RSA encryption (PKCS#1 v1.5) --

    def _get_public_key(self):
        data = self._req('/xtgl/login_getPublicKey.html', expect_json=True)
        self.modulus = data['modulus']
        self.exponent = data['exponent']

    def _encrypt_password(self, password):
        self._get_public_key()
        modulus_bytes = base64.b64decode(self.modulus)
        exponent_bytes = base64.b64decode(self.exponent)
        if len(modulus_bytes) == 129 and modulus_bytes[0] == 0:
            modulus_bytes = modulus_bytes[1:]
        key_len = len(modulus_bytes)
        n = int.from_bytes(modulus_bytes, 'big')
        e = int.from_bytes(exponent_bytes, 'big')
        message = password.encode('utf-8')
        if len(message) > key_len - 11:
            raise ValueError('Password too long')
        pad_len = key_len - len(message) - 3
        padding = b''
        while len(padding) < pad_len:
            b = os.urandom(1)
            if b != b'\x00':
                padding += b
        block = b'\x00\x02' + padding + b'\x00' + message
        m = int.from_bytes(block, 'big')
        c = pow(m, e, n)
        enc_bytes = c.to_bytes((c.bit_length() + 7) // 8, 'big')
        return base64.b64encode(enc_bytes).decode()

    # -- Session persistence --

    def check_valid(self):
        if not os.path.exists(self.session_file):
            return False
        try:
            with open(self.session_file, 'r') as f:
                data = json.load(f)
            self._load_cookies(data['cookies'])
            resp = self._req('/xtgl/index_initMenu.html')
            return 'login_slogin' not in resp
        except:
            return False

    def load_session(self):
        if not self.check_valid():
            return False
        self.logged_in = True
        return True

    def _load_cookies(self, cookies):
        for c in cookies:
            self.sess.cookies.set(c['name'], c['value'],
                domain=c.get('domain', ''), path=c.get('path', '/'))

    def _save_session(self, cookies, username=''):
        data = {
            'base_url': self.base_url,
            'username': username,
            'cookies': cookies,
            'saved_at': time.time(),
        }
        with open(self.session_file, 'w') as f:
            json.dump(data, f, indent=2)

    # -- Heartbeat / keep-alive --

    def start_heartbeat(self, interval=120):
        if self._heartbeat_running:
            return
        self._heartbeat_running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, args=(interval,), daemon=True
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self):
        self._heartbeat_running = False

    def _heartbeat_loop(self, interval):
        while self._heartbeat_running:
            time.sleep(interval)
            if not self._heartbeat_running:
                break
            try:
                self._req('/xtgl/index_initMenu.html')
            except:
                pass

    def login_by_requests(self, username='', password=''):
        """Fast RSA login via requests; returns False when captcha is required."""
        try:
            ts = int(time.time() * 1000)
            page = self._req('/xtgl/login_slogin.html?time=%d' % ts)
            m = re.search(r'name="csrftoken"\s+value="([^"]+)"', page)
            if not m:
                return False
            self._get_public_key()
            enc = self._encrypt_password(password)
            url = '%s/xtgl/login_slogin.html?time=%d' % (self.base_url, int(time.time() * 1000))
            resp = self.sess.post(
                url,
                data={
                    'csrftoken': m.group(1),
                    'language': 'zh_CN',
                    'ydType': '',
                    'yhm': username,
                    'mm': enc,
                },
                headers={'Referer': url, 'Content-Type': 'application/x-www-form-urlencoded'},
                allow_redirects=True,
                timeout=15,
            )
            body = resp.text or ''
            if 'login_slogin' in resp.url or any(k in body.lower() for k in ('captcha', 'slider', '验证码')):
                return False
            if 'index' in resp.url or len(body) > 1000:
                self.logged_in = True
                self.username = username
                cookies = [{'name': c.name, 'value': c.value, 'domain': c.domain, 'path': c.path or '/'} for c in self.sess.cookies]
                self._save_session(cookies, username)
                self.start_heartbeat()
                return True
        except Exception:
            pass
        return False

    # -- Playwright login with Edge --

    def login_with_playwright(self, headless=False, username='', password=''):
        from playwright.sync_api import sync_playwright
        profile_dir = os.path.join(os.path.dirname(self.session_file), 'edge_profile')
        os.makedirs(profile_dir, exist_ok=True)

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                channel="msedge",
                headless=headless,
                viewport={'width': 1280, 'height': 800},
                user_agent=UA
            )
            page = context.new_page()
            login_url = f'{self.base_url}/xtgl/login_slogin.html'
            page.goto(login_url, wait_until='networkidle', timeout=30000)
            page.wait_for_timeout(1000)

            if username:
                try:
                    page.fill('#yhm', username)
                    page.fill('#mm', password)
                except:
                    pass

            if not headless:
                print('[*] Drag the slider captcha, then click Login.')

            try:
                page.wait_for_url('**/index_initMenu.html*', timeout=120000)
            except Exception as e:
                print(f'[-] Login timeout: {e}')
                context.close()
                return False

            cookies = context.cookies()
            context.close()

        self._load_cookies(cookies)
        self.logged_in = True
        self._save_session(cookies, username)
        self.start_heartbeat()
        return True


    def get_schedule(self, xnm='2026', xqm='3'):
        from playwright.sync_api import sync_playwright
        import re
        cookies_data = json.load(open(self.session_file, 'r'))

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={'width':1280,'height':800})
            context.add_cookies(cookies_data['cookies'])
            page = context.new_page()

            url = '{}/kbcx/xskbcx_cxXskbcxIndex.html?gnmkdm=N2151&layout=default'.format(self.base_url)
            page.goto(url, wait_until='networkidle', timeout=30000)
            page.wait_for_selector('#xnm_chosen', timeout=10000)
            page.wait_for_timeout(2000)
            page.select_option('#xnm', xnm, force=True)
            page.select_option('#xqm', xqm, force=True)
            page.evaluate('$("#xnm").trigger("chosen:updated");$("#xqm").trigger("chosen:updated")')
            page.wait_for_timeout(1000)
            page.evaluate('cxKbContent(paramMap(),xszd)')
            page.wait_for_timeout(4000)

            html = page.content()
            tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.S)
            browser.close()

        schedule = []
        if tables:
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tables[0], re.S)
            for row in rows:
                cells = re.findall(r'<(?:td|th)[^>]*>(.*?)</(?:td|th)>', row, re.S)
                vals = []
                for cell in cells:
                    text = re.sub(r'<[^>]+>', '', cell)
                    text = text.replace('&nbsp;', '').replace('\xa0', '')
                    vals.append(text.strip())
                if vals:
                    schedule.append(vals)

        if schedule and schedule[0]:
            title = schedule[0][0] if schedule[0] else ''
            import re as re2
            title = re2.sub(r'[一-鿿]{2,4}的课表', '***的课表', title)
            title = re2.sub(r'学号：[\d]+', '学号：****', title)
            schedule[0][0] = title

        return {'schedule': schedule, 'html_len': len(html)}

    def get_exams(self, xnm='2025', xqm='16'):
        url = urljoin(self.base_url, '/kwgl/kscx_cxXsksxxIndex.html?doType=query')
        data = {
            'xnm': xnm,
            'xqm': xqm,
            'zd_fzdm': 'N358105-xs',
            'gnmkdm': 'N358105',
            'page': '1',
            'rows': '50',
        }
        resp = self.sess.post(url, data=data, timeout=15)
        resp.raise_for_status()
        try:
            return resp.json().get('items', [])
        except Exception:
            return []

    def get_scores(self, xnm='2025', xqm='12'):
        url = urljoin(self.base_url, '/cjcx/cjcx_cxDgXscj.html?doType=query')
        data = {
            'xnm': xnm,
            'xqm': xqm,
            'gnmkdm': 'N305005',
            'page': '1',
            'rows': '100',
        }
        resp = self.sess.post(url, data=data, timeout=15)
        resp.raise_for_status()
        try:
            return resp.json().get('items', [])
        except Exception:
            return []

    def logout(self):
        self.stop_heartbeat()
        try:
            self._req('/xtgl/login_logoutAccount.html', method='POST')
        except:
            pass
        self.logged_in = False
        if os.path.exists(self.session_file):
            os.remove(self.session_file)




