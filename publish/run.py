# Course grabber entry point
import sys, os, glob
import webbrowser
import threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'course_grabber'))
from auth import JW_Session

def main():
    print('=== Course Grabber ===')

    session_dir = os.path.join(os.path.dirname(__file__), 'course_grabber')
    sessions = glob.glob(os.path.join(session_dir, 'session*.json'))

    # Direct start: pick the newest session file if any (does not require it to be valid here),
    # then launch the web UI and open the browser. Login/expiry is handled in the browser.
    newest = None
    for s in sessions:
        try:
            if newest is None or os.path.getmtime(s) > os.path.getmtime(newest):
                newest = s
        except OSError:
            newest = s if newest is None else newest

    jw = JW_Session(session_file=newest) if newest else JW_Session()
    start_web(jw)

def start_web(jw):
    print(f'Starting web server at http://127.0.0.1:5000')
    from app import app
    app._forced_session_file = jw.session_file
    threading.Timer(1.0, lambda: webbrowser.open('http://127.0.0.1:5000')).start()
    app.run(host='127.0.0.1', port=5000, debug=False)

if __name__ == '__main__':
    main()

