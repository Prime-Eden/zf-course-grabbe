"""Parse schedule table rows into structured course events."""
import re


_SURNAMES = set(
    '王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦傅方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤'
)

_COURSE_KEYWORDS = (
    '基础', '原理', '设计', '技术', '工程', '英语', '数学', '物理', '化学', '体育',
    '思政', '实践', '实验', '导论', '概论', '分析', '应用', '系统', '电路', '电子',
    '材料', '管理', '经济', '法律', '文化', '专业', '训练', '方法', '科学', '研究',
    '创新', '创业', '心理', '健康', '职业', '规划', '艺术', '音乐', '美术', '写作',
    '阅读', '听力', '口语', '翻译', '测试', '建模', '算法', '编程', '数据库', '网络',
    '软件', '硬件', '自动', '信号', '通信', '机械', '土木', '建筑', '生物', '医学',
    '护理', '药学', '法学', '新闻', '传播', '制造', '哲学', '逻辑', '历史', '地理',
    '综合', '拓展', '选修', '必修', '限选', '通识', '专项', '竞赛', '实训', '实习',
    '课程', '教学', '原理', '理论', '社会学', '经济学', '心理学', '概论', '教育',
)

_LOCATION_KEYWORDS = ('楼', '室', '馆', '场', '区', '教', '实', '图', '体')


def _is_person_name(token):
    if not token or not 2 <= len(token) <= 4:
        return False
    if not all('\u4e00' <= ch <= '\u9fff' for ch in token):
        return False
    return token[0] in _SURNAMES


def _looks_like_course(token):
    if not token or len(token) < 2:
        return False
    if any(keyword in token for keyword in _COURSE_KEYWORDS):
        return True
    if any(ch.isdigit() or ('a' <= ch.lower() <= 'z') for ch in token):
        return len(token) >= 2
    if len(token) >= 4:
        return not _is_person_name(token)
    return False


def _is_location(token):
    if not token:
        return False
    if any(ch in token for ch in _LOCATION_KEYWORDS) and any(
        ch.isdigit() or ch in '一二三四五六七八九十' for ch in token
    ):
        return True
    return token.endswith(('楼', '馆', '场', '室'))


def _expand_weeks(weeks_str):
    weeks = []
    if not weeks_str:
        return weeks
    for part in re.split(r'[,，、]', weeks_str):
        part = part.strip()
        m = re.match(r'(\d+)-(\d+)周?', part)
        if m:
            weeks.extend(range(int(m.group(1)), int(m.group(2)) + 1))
        else:
            m2 = re.match(r'(\d+)周?', part)
            if m2:
                weeks.append(int(m2.group(1)))
    return sorted(set(weeks))


def _extract_period(text):
    m = re.search(r'[（(]?\s*(\d+)\s*[-—–]\s*(\d+)\s*节\s*[）)]?', text)
    if m:
        return m.group(1) + '-' + m.group(2)
    return ''


def _parse_cell(cell, day_name, default_period=''):
    """Parse one schedule cell into structured course events.

    Course name detection prefers course-like tokens over person names, so a
    teacher name can never become the displayed course name.
    """
    cell = str(cell or '').replace('浙大城市学院', '')
    if not cell.strip() or cell.strip() == '无':
        return []

    events = []
    segments = []
    matches = list(re.finditer(r'[（(]?\s*(\d+)\s*[-—–]\s*(\d+)\s*节\s*[）)]?', cell))
    if matches:
        prefix = cell[:matches[0].start()]
        for idx, m in enumerate(matches):
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(cell)
            seg_text = cell[m.start():end]
            if idx == 0:
                seg_text = prefix + seg_text
            segments.append((seg_text, m.group(0)))
    else:
        segments.append((cell, default_period))

    for segment, period_marker in segments:
        period = _extract_period(period_marker) or _extract_period(segment)
        if not period:
            period = _extract_period(default_period)
        tokens = re.split(r'\s+', segment)
        tokens = [t.strip() for t in tokens if t.strip() and not re.fullmatch(r'[（(]?\d+[-—–]\d+节[）)]?', t.strip())]

        name = ''
        teachers = []
        locations = []
        weeks_str = ''
        nature = ''

        for token in tokens:
            wk = re.search(r'(\d+-\d+周(?:[,，、]\d+-\d+周)*)', token)
            if wk:
                weeks_str = wk.group(1)
                continue
            if _is_location(token):
                if token not in locations:
                    locations.append(token)
                continue
            if re.fullmatch(r'(必修|选修|限选|考查|考试|实践|实验|面授|线上|混合|授课)', token):
                nature = token
                continue
            if _looks_like_course(token) and not name:
                name = token
                continue
            if _is_person_name(token) and token not in teachers:
                teachers.append(token)
                continue
            if not name and not _is_person_name(token):
                name = token

        if not name and teachers:
            name = ''

        if not name and not weeks_str:
            continue
        if not name:
            continue

        event = {
            'name': name,
            'day': day_name,
            'period': period + '节' if period else '',
            'weeks': _expand_weeks(weeks_str),
            'weeks_str': weeks_str,
            'location': ' · '.join(locations),
            'teacher': '、'.join(teachers),
            'nature': nature,
        }
        if period:
            start, _, end = period.partition('-')
            event['period_start'] = int(start)
            event['period_end'] = int(end)
        else:
            event['period_start'] = 0
            event['period_end'] = 0
        events.append(event)

    return events


def schedule_to_events(schedule):
    """Convert schedule table rows into structured course events."""
    if len(schedule) < 2:
        return []

    header = schedule[1]
    day_start = None
    for idx, h in enumerate(header):
        if '星期' in str(h) or str(h).strip() in ('一', '二', '三', '四', '五', '六', '日'):
            day_start = idx
            break
    if day_start is None:
        day_start = 2
    day_headers = [h for h in header[day_start:] if h]
    events = []

    for row in schedule[2:]:
        if not row:
            continue
        first = str(row[0]).strip() if row else ''
        # Rows that begin a period block carry a "上午/下午/晚上" label; those
        # rows are one column wider. Align course columns against the weekday
        # header instead of assuming a fixed column offset.
        course_start = day_start if first in ('上午', '下午', '晚上') else day_start - 1
        default_period = ''
        m = re.search(r'(\d+)-(\d+)节', str(row[0]) + ' ' + str(row[1]) if len(row) > 1 else str(row[0]))
        if m:
            default_period = m.group(0)
        for col in range(course_start, min(len(row), course_start + len(day_headers))):
            cell = row[col]
            if not cell or str(cell).strip() in ('', '无'):
                continue
            day_idx = col - course_start
            day_name = day_headers[day_idx] if day_idx < len(day_headers) else ''
            events.extend(_parse_cell(cell, day_name, default_period))

    return events
