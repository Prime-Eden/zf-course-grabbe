from flask import Flask, render_template, request, jsonify, session as fs
from auth import JW_Session, SESSION_FILE
from courses import CourseManager
import os, secrets, threading, json, time
import re
from datetime import datetime

def parse_ics(path):
    with open(path, encoding='utf-8') as f:
        text = f.read()
    events = re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', text, re.S)
    out = []
    weekdays = ['一', '二', '三', '四', '五', '六', '日']
    for e in events:
        sm = re.search(r'SUMMARY:([^\r\n]+)', e)
        dt = re.search(r'DTSTART;TZID=Asia/Shanghai:(\d{8})T(\d{6})', e)
        un = re.search(r'UNTIL=(\d{8})T\d{6}Z', e)
        if not sm or not dt:
            continue
        start = datetime.strptime(dt.group(1) + dt.group(2), '%Y%m%d%H%M%S')
        end = datetime.strptime(un.group(1), '%Y%m%d') if un else start
        weeks = round((end - start).days / 7) + 1 if un else 1
        loc = re.search(r'LOCATION:([^\r\n]+)', e)
        locs = loc.group(1).strip().split() if loc else []
        place = locs[0] if locs else ''
        teacher = ' '.join(locs[1:]) if len(locs) > 1 else ''
        desc = re.search(r'DESCRIPTION:([^\r\n]+)', e)
        period = ''
        if desc:
            m = re.search(r'第\s*(\d+)\s*[-–]\s*(\d+)\s*节', desc.group(1))
            if m:
                period = m.group(1) + '-' + m.group(2) + '节'
        out.append({
            'name': sm.group(1).strip(),
            'day': weekdays[start.weekday()],
            'period': period,
            'weeks': str(weeks) + '周',
            'start': start.strftime('%m-%d'),
            'end': end.strftime('%m-%d'),
            'location': place,
            'teacher': teacher,
        })
    return out

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

sessions = {}
_login_lock = threading.Lock()
_login_in_progress = False

def _uid():
    sid = fs.get('uid')
    if not sid:
        sid = secrets.token_hex(16)
        fs['uid'] = sid
    return sid

def _cm():
    sid = _uid()
    if sid in sessions:
        return sessions[sid]
    return None, None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    global _login_in_progress
    d = request.json
    if not d.get('username') or not d.get('password'):
        return jsonify({'ok': False, 'error': 'Missing credentials'})
    with _login_lock:
        if _login_in_progress:
            return jsonify({'ok': False, 'error': 'Login in progress'})
        _login_in_progress = True
    try:
        jw = JW_Session()
        ok = jw.login_by_requests(d['username'], d['password'])
        if not ok:
            ok = jw.login_with_playwright(
                headless=False, username=d['username'], password=d['password']
            )
        if ok:
            sessions[_uid()] = (jw, CourseManager(jw))
            return jsonify({'ok': True})
        return jsonify({'ok': False, 'error': 'Login timeout'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
    finally:
        with _login_lock:
            _login_in_progress = False

@app.route('/api/logout', methods=['POST'])
def api_logout():
    jw, cm = _cm()
    if jw:
        jw.logout()
        sessions.pop(_uid(), None)
    return jsonify({'ok': True})

@app.route('/api/categories', methods=['GET'])
def api_categories():
    _, cm = _cm()
    if not cm:
        return jsonify({'ok': False, 'error': 'Not logged in'})
    return jsonify({'ok': True, 'categories': cm.get_categories()})

@app.route('/api/search', methods=['POST'])
def api_search():
    _, cm = _cm()
    if not cm:
        return jsonify({'ok': False, 'error': 'Not logged in'})
    d = request.json or {}
    return jsonify({'ok': True, **cm.search_courses(
        keyword=d.get('keyword', ''),
        category_kklxdm=d.get('kklxdm', ''),
        page=d.get('page', 1),
    )})

@app.route('/api/course/<cid>', methods=['GET'])
def api_course_detail(cid):
    _, cm = _cm()
    if not cm:
        return jsonify({'ok': False, 'error': 'Not logged in'})
    return jsonify({'ok': True, **cm.get_course_detail(cid)})

@app.route('/api/tasks', methods=['GET'])
def api_tasks():
    _, cm = _cm()
    if not cm:
        return jsonify({'ok': False, 'tasks': []})
    return jsonify({'ok': True, 'tasks': [t.to_dict() for t in cm.tasks.values()]})

@app.route('/api/tasks/add', methods=['POST'])
def api_task_add():
    _, cm = _cm()
    if not cm:
        return jsonify({'ok': False, 'error': 'Not logged in'})
    d = request.json
    ok, msg = cm.add_course(
        d['course_id'],
        course_name=d.get('course_name', ''),
        target_jxb_id=d.get('target_jxb_id', ''),
        interval=float(d.get('interval', 2.0)),
        xnm=d.get('xnm'),
        xqm=d.get('xqm'),
    )
    return jsonify({'ok': ok, 'message': msg})

@app.route('/api/tasks/remove', methods=['POST'])
def api_task_remove():
    _, cm = _cm()
    if not cm:
        return jsonify({'ok': False, 'error': 'Not logged in'})
    cm.remove_course(request.json['course_id'])
    return jsonify({'ok': True})

@app.route('/api/course/select', methods=['POST'])
def api_course_select():
    _, cm = _cm()
    if not cm:
        return jsonify({'ok': False, 'error': 'Not logged in'})
    d = request.json or {}
    course_id = d.get('course_id')
    jxb_id = d.get('jxb_id')
    if not course_id or not jxb_id:
        return jsonify({'ok': False, 'error': 'Missing course_id or jxb_id'})
    cm._init_selection()
    classes = cm.get_course_detail(course_id).get('classes', [])
    target = next((c for c in classes if c.get('jxb_id') == jxb_id), None)
    if not target:
        return jsonify({'ok': False, 'error': 'Class not found'})
    result = cm._submit_select(course_id, target)
    flag = result.get('flag') if isinstance(result, dict) else result
    if flag == '1' or flag == 1:
        return jsonify({'ok': True, 'result': result})
    return jsonify({'ok': False, 'result': result, 'message': result.get('msg') if isinstance(result, dict) else str(result)})

@app.route('/api/course/drop', methods=['POST'])
def api_course_drop():
    _, cm = _cm()
    if not cm:
        return jsonify({'ok': False, 'error': 'Not logged in'})
    d = request.json or {}
    result = cm.drop_course(d.get('jxb_ids'), d.get('course_id'))
    return jsonify({'ok': result.get('ok'), 'message': result.get('msg'), 'result': result.get('raw')})

@app.route('/api/monitor/start', methods=['POST'])
def api_monitor_start():
    jw, cm = _cm()
    if not cm:
        return jsonify({'ok': False, 'error': 'Not logged in'})
    jw.start_heartbeat(120)
    ok, msg = cm.start_monitoring()
    return jsonify({'ok': ok, 'message': msg})

@app.route('/api/monitor/stop', methods=['POST'])
def api_monitor_stop():
    jw, cm = _cm()
    if not cm:
        return jsonify({'ok': False, 'error': 'Not logged in'})
    cm.stop_monitoring()
    jw.stop_heartbeat()
    return jsonify({'ok': True})

@app.route('/api/status', methods=['GET'])
def api_status():
    jw, cm = _cm()
    if not jw:
        return jsonify({'logged_in': False})
    return jsonify({
        'logged_in': True,
        'username': jw.username,
        'monitoring': cm.status == 'running',
        'status': cm.status,
        'tasks': [t.to_dict() for t in cm.tasks.values()],
        'categories': cm._categories,
        'heartbeat': jw._heartbeat_running,
    })

@app.route('/api/session/check', methods=['GET'])
def api_session_check():
    if os.path.exists(SESSION_FILE):
        try:
            d = json.load(open(SESSION_FILE, 'r'))
            age = time.time() - d.get('saved_at', 0)
            return jsonify({'has_session': True, 'age_minutes': round(age/60,1)})
        except:
            pass
    return jsonify({'has_session': False})

@app.route('/api/session/load', methods=['POST'])
def api_session_load():
    jw = JW_Session()
    if jw.load_session():
        sessions[_uid()] = (jw, CourseManager(jw))
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'Session expired'})

@app.route('/api/schedule', methods=['POST'])
def api_schedule():
    jw, cm = _cm()
    if not jw:
        return jsonify({'ok': False, 'error': 'Not logged in'})
    d = request.json or {}
    try:
        r = jw.get_schedule(d.get('xnm','2026'), d.get('xqm','3'))
        return jsonify({'ok': True, 'schedule': r.get('schedule',[])})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/exams', methods=['POST'])
def api_exams():
    jw, cm = _cm()
    if not jw:
        return jsonify({'ok': False, 'error': 'Not logged in'})
    d = request.json or {}
    try:
        items = jw.get_exams(d.get('xnm', '2025'), d.get('xqm', '16'))
        return jsonify({'ok': True, 'exams': items})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/schedule-ics', methods=['GET'])
def api_schedule_ics():
    path = r'G:\桌面\大二上.ics'
    if not os.path.exists(path):
        return jsonify({'ok': False, 'error': 'ics not found'})
    try:
        return jsonify({'ok': True, 'courses': parse_ics(path)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/scores', methods=['POST'])
def api_scores():
    jw, cm = _cm()
    if not jw:
        return jsonify({'ok': False, 'error': 'Not logged in'})
    d = request.json or {}
    try:
        items = jw.get_scores(d.get('xnm', '2025'), d.get('xqm', '12'))
        return jsonify({'ok': True, 'scores': items})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
