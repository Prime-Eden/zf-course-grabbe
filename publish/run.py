# Course grabber entry point
import sys, os, json, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'course_grabber'))
from auth import JW_Session

def main():
    print('=== Course Grabber ===')

    # Find existing sessions
    session_dir = os.path.join(os.path.dirname(__file__), 'course_grabber')
    sessions = glob.glob(os.path.join(session_dir, 'session*.json'))

    if sessions:
        print('Saved sessions:')
        for i, s in enumerate(sessions):
            try:
                d = json.load(open(s, 'r'))
                uname = d.get('username', os.path.basename(s))
                age = (__import__('time').time() - d.get('saved_at', 0)) / 60
                print(f'  [{i+1}] {uname} (saved {age:.0f}m ago)')
            except:
                print(f'  [{i+1}] {os.path.basename(s)} (invalid)')
        print(f'  [N] New login')
        print(f'  [Q] Quit')

        choice = input('Choice: ').strip()
        if choice.upper() == 'Q':
            return
        if choice.upper() == 'N':
            do_login(session_dir, None)
            return
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(sessions):
                sf = sessions[idx]
                jw = JW_Session(session_file=sf)
                if jw.check_valid():
                    jw.logged_in = True
                    d = json.load(open(sf, 'r'))
                    jw.username = d.get('username', '')
                    print(f'[+] Session valid: {jw.username}')
                    start_web(jw)
                else:
                    print('[-] Session expired. Need new login.')
                    uname = os.path.basename(sf).replace('session_','').replace('.json','').replace('session','default')
                    do_login(session_dir, uname if uname != 'default' else None)
        except (ValueError, IndexError):
            print('Invalid choice')
            return
    else:
        print('No saved sessions found.')
        do_login(session_dir, None)

def do_login(session_dir, username=None):
    if not username:
        username = input('Student ID: ').strip()
        if not username:
            print('Username required')
            return

    sf = os.path.join(session_dir, f'session_{username}.json')
    jw = JW_Session(session_file=sf)

    if jw.check_valid():
        print(f'[i] Found valid session for {username}')
        use = input('Use saved session? [Y/n]: ').strip().lower()
        if use != 'n':
            jw.logged_in = True
            jw.username = username
            start_web(jw)
            return

    print(f'Opening Edge browser for {username}...')
    input('Press Enter...')

    pwd = input('Password: ').strip()  # sent via HTTPS, not stored
    if jw.login_with_playwright(headless=False, username=username, password=pwd):
        jw.username = username
        sf2 = os.path.join(session_dir, f'session_{username}.json')
        if sf2 != sf:
            import shutil
            shutil.copy(sf, sf2)
        print(f'[+] Login OK!')
        start_web(jw)
    else:
        print('[-] Login failed')

def start_web(jw):
    print(f'Starting web server at http://127.0.0.1:5000')
    from app import app
    app.run(host='127.0.0.1', port=5000, debug=False)

if __name__ == '__main__':
    main()

