"""Auto solve zfdun slider captcha: template gap detection + human-like trajectory."""
import random, time

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


def _detect_gap(bg_bytes, piece_bytes):
    """Return gap center x. Alpha-masked template match, ddddocr fallback."""
    try:
        import cv2, numpy as np
        bgr = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
        pcr = cv2.imdecode(np.frombuffer(piece_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
        if bgr is None or pcr is None:
            raise ValueError('decode failed')
        ys, xs = np.where(pcr[:, :, 3] > 100)
        if len(xs) == 0:
            raise ValueError('no opaque piece')
        y0, y1 = ys.min(), ys.max()
        pc = pcr[y0:y1+1, 0:xs.max()+1]
        r = cv2.matchTemplate(bgr[:, :, :3], pc[:, :, :3], cv2.TM_CCORR_NORMED, mask=pc[:, :, 3])
        _, mv, _, ml = cv2.minMaxLoc(r)
        if mv > 0.85:
            return ml[0] + pc.shape[1] // 2, mv
    except Exception:
        pass
    try:
        import ddddocr
        ocr = ddddocr.DdddOcr(show_ad=False)
        res = ocr.slide_match(bg_bytes, piece_bytes, simple_target=True)
        return int(res['target'][0]), float(res.get('confidence', 0))
    except Exception:
        return 0, 0


def _drag(page, distance, sx, sy):
    """Human-like drag: slow start, fast middle, overshoot, settle-back, y-press."""
    n = 77
    t0 = time.time()
    page.mouse.move(sx, sy)
    page.mouse.down()
    for i in range(1, n + 1):
        p = i / n
        eased = 0.5 - 0.5 * __import__('math').cos(3.14159 * p)
        x = sx + distance * eased * 1.04
        if p > 0.9:
            x -= (p - 0.9) * distance * 0.35
        y = sy + random.uniform(-1, 1) + (14 if p > 0.93 else 0)
        page.mouse.move(x, y, steps=2)
        elapsed = time.time() - t0
        target = p * 1.6
        if elapsed < target:
            time.sleep(min(0.05, target - elapsed))
    page.mouse.up()


def _is_slider_verified(page):
    return page.evaluate("""() => {
        const tips = document.querySelector('.zfdun_verify_tips');
        const succ = document.querySelector('.zfdun_verify_tips_succsss');
        const fail = document.querySelector('.zfdun_verify_tips_fail');
        const tipsText = tips ? tips.innerText : '';
        const succVisible = succ ? (getComputedStyle(succ).display !== 'none' && getComputedStyle(succ).visibility !== 'hidden') : false;
        const failVisible = fail ? (getComputedStyle(fail).display !== 'none' && getComputedStyle(fail).visibility !== 'hidden') : false;
        return /verified/.test(tipsText) && !/验证失败/.test(tipsText);
    }""")


def solve_slider(page, base_url=''):
    """Detect gap and drag with retry around the detected position."""
    import requests
    try:
        page.wait_for_selector('.zfdun_slider_bar_btn', timeout=10000)
        page.wait_for_timeout(800)
        info = page.evaluate("""() => {
            const bg = document.querySelector('.zfdun_bgimg_img');
            const piece = document.querySelector('.zfdun_bgimg_jigsaw');
            const btn = document.querySelector('.zfdun_slider_bar_btn');
            const bar = document.querySelector('.zfdun_slider_bar') || document.querySelector('.zfdun_container');
            if (!bg || !piece || !btn || !bar) return null;
            return { bgSrc: bg.src, pieceSrc: piece.src, btn: btn.getBoundingClientRect(), bar: bar.getBoundingClientRect() };
        }""")
        if not info:
            return False
        s = requests.Session(); s.verify = False
        for c in page.context.cookies():
            s.cookies.set(c['name'], c['value'], domain=c.get('domain',''), path=c.get('path','/'))
        hdrs = {'User-Agent': UA, 'Referer': base_url + '/xtgl/login_slogin.html'}
        bg = s.get(info['bgSrc'], headers=hdrs, timeout=10).content
        piece = s.get(info['pieceSrc'], headers=hdrs, timeout=10).content
        gap, conf = _detect_gap(bg, piece)
        if gap <= 0:
            return False
        bar = info['bar']; btn = info['btn']
        sx = btn['x'] + btn['width'] / 2
        sy = btn['y'] + btn['height'] / 2
        image_left = bar['x']
        base_d = gap + (image_left - sx)
        for off in (0, -36, 36, -18, 18):
            d = base_d + off
            if d < 10 or d > bar['width']:
                continue
            _drag(page, d, sx, sy)
            page.wait_for_timeout(1200)
            verified = _is_slider_verified(page)
            if verified:
                return True
            try:
                page.evaluate('$(".zfdun_refresh_btn").click()')
                page.wait_for_timeout(1500)
            except Exception:
                pass
        return False
    except Exception:
        return False
