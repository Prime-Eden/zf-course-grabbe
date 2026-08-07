# Course module - domain model for course monitoring and sniping
import json, re, time, threading, random
from dataclasses import dataclass, field
from enum import Enum

GNMKDM = "N253512"
XK_INDEX   = "/xsxk/zzxkyzb_cxZzxkYzbIndex.html"
XK_DISPLAY = "/xsxk/zzxkyzb_cxZzxkYzbPartDisplay.html"
XK_CLASSES = "/xsxk/zzxkyzbjk_cxJxbWithKchZzxkYzb.html"
XK_SELECT  = "/xsxk/zzxkyzb_xkBcZyZzxkYzb.html"
XK_DROP    = "/xsxk/zzxkyzb_tuikBcZzxkYzb.html"

CLASS_LIST_DEFAULTS = {
    "rwlx": "2", "xkly": "0", "bklx_id": "0", "sfkkjyxdxnxq": "0",
    "kzkcgs": "0", "xqh_id": "1", "jg_id": "28",
    "zyfx_id": "wfx", "txbsfrl": "0",
    "xbm": "1", "xslbdm": "421", "mzm": "01", "xz": "4", "ccdm": "3",
    "xsbj": "1", "sfkknj": "0", "gnjkxdnj": "0", "sfkkzy": "0", "kzybkxy": "0",
    "sfznkx": "0", "zdkxms": "0", "sfkxq": "1", "sfkcfx": "0",
    "bbhzxjxb": "0", "kkbk": "0", "kkbkdj": "0", "bklbkcj": "0",
    "xkxskcgskg": "1",
    "rlkz": "0", "cdrlkz": "0", "rlzlkz": "1",
    "jxbzcxskg": "0", "xklc": "1", "cxbj": "0", "fxbj": "0",
}

SELECT_DEFAULTS = {
    "rwlx": "2",
    "rlkz": "0",
    "cdrlkz": "0",
    "rlzlkz": "1",
    "sxbj": "1",
    "xxkbj": "0",
    "qz": "0",
    "cxbj": "0",
    "xklc": "1",
    "jcxx_id": "",
}

DROP_DEFAULTS = {
    "txbsfrl": "0",
}


class TaskStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    STOPPED = "stopped"


class ClassInfo:
    def __init__(self, jxb_id, teacher="", time="", location="", weeks="", capacity="", selected="", extra=None):
        self.jxb_id = jxb_id
        self.teacher = teacher
        self.time = time
        self.location = location
        self.weeks = weeks
        self.capacity = capacity
        self.selected = selected
        self.extra = extra or {}

    @property
    def remaining(self):
        try:
            cap = int(re.sub(r"[^\d]", "", str(self.capacity or "0")) or "0")
            sel = int(re.sub(r"[^\d]", "", str(self.selected or "0")) or "0")
            return max(0, cap - sel)
        except ValueError:
            return 0

    @property
    def is_full(self):
        return self.remaining <= 0

    def to_dict(self):
        return {
            "jxb_id": self.jxb_id,
            "teacher": self.teacher,
            "time": self.time,
            "location": self.location,
            "weeks": self.weeks,
            "capacity": self.capacity,
            "selected": self.selected,
            "remaining": self.remaining,
            "is_full": self.is_full,
            "extra": self.extra,
        }


class CourseInfo:
    def __init__(self, course_id, name="", teacher="", time="", location="", weeks="", credit="", category="", classes=None):
        self.course_id = course_id
        self.name = name
        self.teacher = teacher
        self.time = time
        self.location = location
        self.weeks = weeks
        self.credit = credit
        self.category = category
        self.classes = classes or []

    def to_dict(self):
        return {
            "id": self.course_id,
            "name": self.name,
            "teacher": self.teacher,
            "time": self.time,
            "location": self.location,
            "weeks": self.weeks,
            "credit": self.credit,
            "category": self.category,
            "classes": [c.to_dict() for c in self.classes],
        }


@dataclass
class GrabTask:
    task_id: str
    course: CourseInfo
    target_jxb_id: str = ""
    interval: float = 2.0
    status: TaskStatus = TaskStatus.IDLE
    attempt_count: int = 0
    last_message: str = ""
    last_result: str = ""
    last_checked_at: float = field(default_factory=time.time)
    added_at: float = field(default_factory=time.time)
    log: list = field(default_factory=list)

    def add_log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")
        if len(self.log) > 200:
            self.log = self.log[-200:]

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "course_id": self.course.course_id,
            "course_name": self.course.name,
            "target_jxb_id": self.target_jxb_id,
            "interval": self.interval,
            "status": self.status.value,
            "attempts": self.attempt_count,
            "last_msg": self.last_message,
            "last_result": self.last_result,
            "last_checked_at": self.last_checked_at,
            "log": self.log,
        }


class CourseManager:
    def __init__(self, session):
        self.session = session
        self.tasks: dict[str, GrabTask] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._stop_events: dict[str, threading.Event] = {}
        self.status = "idle"
        self.last_global_result = None
        self.max_tasks = 10
        self._initialized = False
        self._categories = []
        self._filters = {}
        self.xnm = '2025'
        self.xqm = '12'

    def _now(self):
        return time.time()

    # -- Init / page context --

    def _init_selection(self):
        if self._initialized:
            return True, self._categories
        try:
            resp = self.session._req(f"{XK_INDEX}?gnmkdm={GNMKDM}&layout=default")
            inputs = re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', resp)
            for name, value in inputs:
                if name not in self.session.student_info:
                    self.session.student_info[name] = value

            for key in ['firstXkkzId', 'firstNjdmId', 'firstZyhId', 'firstKklxdm']:
                m = re.search(rf'id="{re.escape(key)}"\s+value="([^"]*)"', resp)
                if m:
                    self.session.student_info[key] = m.group(1)
                    canonical = key.replace('first', '').replace('Id', '_id')
                    if not self.session.student_info.get(canonical):
                        self.session.student_info[canonical] = m.group(1)

            tabs = re.findall(
                r"queryCourse\(this,'([^']+?)','([^']+?)','([^']+?)','[^']+?'\)[^>]*>([^<]+?)</a>",
                resp
            )
            self._categories = []
            for t in tabs:
                self._categories.append({
                    'kklxdm': t[0],
                    'name': t[3].strip(),
                    'xkkz_id': t[1],
                    'rwlx': t[2],
                })

            filter_inputs = re.findall(r'name="(filter_list\[\d+\])"', resp)
            for fi in filter_inputs:
                m = re.search(rf'name="{re.escape(fi)}"\s+value="([^"]*)"', resp)
                if m:
                    self._filters[fi] = m.group(1)

            self._initialized = True
            return True, self._categories
        except Exception as e:
            return False, []

    def get_categories(self):
        ok, cats = self._init_selection()
        return cats if ok else []

    # -- Course search / class detail --

    def search_courses(self, keyword="", category_kklxdm="", page=1, **extra_filters):
        self._init_selection()
        page = max(page, 1)
        kspage = (page - 1) * 10 + 1
        jspage = page * 10
        data = dict(self.session.student_info)
        data.update({
            "gnmkdm": GNMKDM,
            "kspage": str(kspage),
            "jspage": str(jspage),
            "tykczgxdcs": "10",
        })
        if keyword:
            data["kcm"] = keyword
            data["kch"] = keyword
        if category_kklxdm:
            data["kklxdm"] = category_kklxdm
            data["filter_list[0]"] = category_kklxdm
        for k, v in extra_filters.items():
            data[k] = str(v)

        try:
            payload = self.session._req(XK_DISPLAY, method="POST", data=data, expect_json=True)
            return self._parse_list(payload)
        except Exception as e:
            return {"error": str(e), "courses": []}

    def _parse_list(self, payload):
        courses = []
        if isinstance(payload, dict):
            raw = payload.get('tmpList', [])
            if not isinstance(raw, list):
                raw = []
            for item in raw:
                courses.append({
                    "id": item.get('kch_id') or item.get('kch') or "",
                    "name": item.get('kcmc') or "",
                    "credit": item.get('xf') or "",
                    "category": item.get('kclbmc') or "",
                    "teacher": item.get('jsxx') or "",
                    "weeks": item.get('zcm') or item.get('kssjd') or "",
                    "time": item.get('sksj') or "",
                    "location": item.get('jxdd') or "",
                    "capacity": item.get('jxbrl') or item.get('kxsl') or "",
                    "selected": item.get('yxzrs') or item.get('yxzrs') or "",
                })
            return {"courses": courses, "total": len(courses)}

        html = payload if isinstance(payload, str) else ""
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
        for row in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            if len(cells) >= 10:
                courses.append({
                    "id": self._s(cells[0]),
                    "name": self._s(cells[2]),
                    "credit": self._s(cells[3]) if len(cells) > 3 else "",
                    "category": self._s(cells[4]) if len(cells) > 4 else "",
                    "teacher": self._s(cells[5]) if len(cells) > 5 else "",
                    "weeks": self._s(cells[6]) if len(cells) > 6 else "",
                    "time": self._s(cells[7]) if len(cells) > 7 else "",
                    "location": self._s(cells[8]) if len(cells) > 8 else "",
                    "capacity": self._s(cells[11]) if len(cells) > 11 else "",
                    "selected": self._s(cells[12]) if len(cells) > 12 else "",
                })
            elif len(cells) >= 6:
                courses.append({
                    "id": self._s(cells[0]),
                    "name": self._s(cells[1]),
                    "credit": self._s(cells[2]) if len(cells) > 2 else "",
                    "category": self._s(cells[3]) if len(cells) > 3 else "",
                    "teacher": self._s(cells[4]) if len(cells) > 4 else "",
                    "capacity": self._s(cells[5]) if len(cells) > 5 else "",
                    "selected": self._s(cells[6]) if len(cells) > 6 else "",
                })
        return {"courses": courses, "total": len(courses)}

    def _s(self, html):
        return re.sub(r"<[^>]+>", "", html).strip()

    def get_course_detail(self, course_id):
        self._init_selection()
        try:
            payload = self.session._req(
                f"{XK_CLASSES}?gnmkdm={GNMKDM}&kch_id={course_id}",
                method="POST",
                expect_json=True,
                data={**CLASS_LIST_DEFAULTS, "kch_id": course_id, **self._context_fields()},
            )
            return self._parse_classes(payload)
        except Exception as e:
            return {"error": str(e), "classes": []}

    def _parse_classes(self, payload):
        if isinstance(payload, list):
            classes = []
            for item in payload:
                classes.append({
                    "jxb_id": item.get("do_jxb_id", ""),
                    "teacher": item.get("jsxx") or "",
                    "time": item.get("sksj") or "",
                    "location": item.get("jxdd") or "",
                    "weeks": item.get("kcxqz") or item.get("zcm") or "",
                    "capacity": item.get("jxbrl") or "",
                    "selected": item.get("yxzrs") or "",
                    "remaining": max(0, int(re.sub(r"[^\d]", "", str(item.get("jxbrl") or "0")) or "0") - int(re.sub(r"[^\d]", "", str(item.get("yxzrs") or "0")) or "0")),
                    "is_full": False,
                    "extra": {
                        "jxb_mc": item.get("jxbmc") or item.get("kzmc", "未分组"),
                        "kclbmc": item.get("kclbmc") or "",
                        "xf": item.get("xf") or "",
                        "xkbz": item.get("xkbz") or "",
                        "sxbj": item.get("sxbj") or "",
                    }
                })
                classes[-1]["is_full"] = classes[-1]["remaining"] <= 0
            return {"classes": classes, "total": len(classes)}

        html = payload if isinstance(payload, str) else ""
        classes = []
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
        for row in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            if len(cells) >= 8:
                classes.append({
                    "jxb_id": self._s(cells[0]),
                    "teacher": self._s(cells[3]) if len(cells) > 3 else "",
                    "time": self._s(cells[4]) if len(cells) > 4 else "",
                    "location": self._s(cells[5]) if len(cells) > 5 else "",
                    "weeks": self._s(cells[6]) if len(cells) > 6 else "",
                    "capacity": self._s(cells[7]) if len(cells) > 7 else "",
                    "selected": self._s(cells[8]) if len(cells) > 8 else "",
                })
        return {"classes": classes, "total": len(classes)}

    def _context_fields(self):
        return {
            "xkkz_id": self.session.student_info.get('xkkz_id', ''),
            "njdm_id": self.session.student_info.get('njdm_id', ''),
        "zyh_id": self.session.student_info.get('zyh_id', ''),
        "kklxdm": self.session.student_info.get('kklxdm', '10'),
        "xkxnm": self.xnm,
        "xkxqm": self.xqm,
    }

    # -- Task management --

    def add_course(self, course_id, course_name="", target_jxb_id="", interval=2.0, xnm=None, xqm=None):
        if len(self.tasks) >= self.max_tasks:
            return False, f"最多添加 {self.max_tasks} 个监控任务"
        if not course_id:
            return False, "课程编号为空"
        if course_id in self.tasks:
            return False, "该课程已在监控中"
        if xnm:
            self.xnm = str(xnm)
        if xqm:
            self.xqm = '3' if str(xqm) == '1' else ('12' if str(xqm) == '2' else str(xqm))
        course = CourseInfo(course_id=course_id, name=course_name or course_id)
        task = GrabTask(
            task_id=self._new_task_id(course_id),
            course=course,
            target_jxb_id=target_jxb_id,
            interval=interval,
        )
        self.tasks[course_id] = task
        task.add_log("已加入监控队列")
        return True, "已加入"

    def remove_course(self, course_id):
        self.stop_task(course_id)
        task = self.tasks.pop(course_id, None)
        if task:
            task.add_log("已移出监控队列")
        self._stop_events.pop(course_id, None)

    def start_monitoring(self):
        if not self.tasks:
            return False, "没有可监控的任务"
        self._init_selection()
        for cid in self.tasks:
            self.start_task(cid)
        self.status = "running"
        return True, f"已启动 {len(self.tasks)} 个任务"

    def stop_monitoring(self):
        for cid in list(self.tasks.keys()):
            self.stop_task(cid)
        self.status = "idle"
        return True, "已停止"

    def start_task(self, course_id):
        task = self.tasks.get(course_id)
        if not task or task.status == TaskStatus.RUNNING:
            return
        ev = threading.Event()
        self._stop_events[course_id] = ev
        task.status = TaskStatus.RUNNING
        task.add_log("开始监控")
        t = threading.Thread(target=self._watch_loop, args=(course_id, ev), daemon=True)
        self._threads[course_id] = t
        t.start()

    def stop_task(self, course_id):
        ev = self._stop_events.get(course_id)
        if ev:
            ev.set()
        task = self.tasks.get(course_id)
        if task:
            task.status = TaskStatus.STOPPED
            task.add_log("停止监控")

    def _new_task_id(self, course_id):
        return f"task_{course_id}_{int(time.time()*1000)}"

    # -- Core monitor / sniping logic --

    def _watch_loop(self, course_id, stop_event):
        task = self.tasks[course_id]
        while not stop_event.is_set():
            try:
                result = self._check_course(course_id)
                task.attempt_count += 1
                task.last_checked_at = self._now()
                task.last_result = result.get("summary", "")
                if result.get("grabbed"):
                    task.status = TaskStatus.SUCCESS
                    task.last_message = "抢课成功"
                    task.add_log("抢课成功")
                    self.last_global_result = result
                    self.status = "grabbed"
                    for cid in self.tasks:
                        if cid != course_id:
                            self.stop_task(cid)
                    return
                else:
                    task.last_message = result.get("summary", "暂无结果")
                    if result.get("log"):
                        task.add_log(result.get("log"))
                    elif task.attempt_count % 5 == 0:
                        task.add_log(f"尝试 #{task.attempt_count}：{task.last_message}")
            except Exception as e:
                task.last_message = str(e)[:120]
                task.add_log(f"异常：{task.last_message}")
            stop_event.wait(timeout=task.interval)

    def _check_course(self, course_id):
        class_payload = self._fetch_class_list(course_id)
        classes = class_payload.get("classes", [])
        if not classes:
            err = class_payload.get('error', '')
            if 'login' in err.lower() or 'slogin' in err.lower():
                return {"grabbed": False, "summary": "会话可能过期", "log": err[:100]}
            return {"grabbed": False, "summary": "未获取到班级信息", "log": "班级列表为空"}

        selected_class = self._select_target_class(classes, course_id)
        if not selected_class:
            return {"grabbed": False, "summary": "未找到可用班级", "log": "无符合条件班级"}

        remaining = selected_class.get("remaining", 0)
        task = self.tasks.get(course_id)
        if remaining <= 0:
            if task and task.attempt_count in (1, 5, 15, 30):
                return {
                    "grabbed": False,
                    "summary": f"仍无余量，当前剩余 {remaining}",
                    "log": f"班级 {selected_class.get('jxb_id')} 剩余 {remaining}",
                }
            return {"grabbed": False, "summary": f"当前剩余 {remaining}", "log": ""}

        select_payload = self._submit_select(course_id, selected_class, self.xnm, self.xqm)
        flag = select_payload.get("flag")
        msg = select_payload.get("msg", str(select_payload))
        if flag == "1" or flag == 1:
            return {
                "grabbed": True,
                "summary": "已抢到课程",
                "log": f"选课成功：{msg}",
                "raw": str(select_payload),
            }
        if "冲突" in str(msg) or "conflict" in str(msg).lower():
            return {
                "grabbed": False,
                "summary": "时间冲突",
                "log": f"选课失败：{msg}",
                "raw": str(select_payload),
            }
        if "过期" in str(msg) or "login" in str(msg).lower() or "slogin" in str(msg).lower():
            return {
                "grabbed": False,
                "summary": "会话可能过期",
                "log": f"选课失败：{msg}",
                "raw": str(select_payload),
            }
        return {
            "grabbed": False,
            "summary": msg or "未成功",
            "log": f"选课未成功：{msg}",
            "raw": str(select_payload),
        }

    def _fetch_class_list(self, course_id):
        try:
            payload = self.session._req(
                f"{XK_CLASSES}?gnmkdm={GNMKDM}&kch_id={course_id}",
                method="POST",
                expect_json=True,
                data={**CLASS_LIST_DEFAULTS, "kch_id": course_id, **self._context_fields()},
            )
            if isinstance(payload, list):
                classes = []
                for item in payload:
                    cap = item.get("jxbrl") or ""
                    sel = item.get("yxzrs") or ""
                    try:
                        remaining = max(0, int(re.sub(r"[^\d]", "", str(cap)) or "0") - int(re.sub(r"[^\d]", "", str(sel)) or "0"))
                    except ValueError:
                        remaining = 0
                    classes.append({
                        "jxb_id": item.get("do_jxb_id", ""),
                        "teacher": item.get("jsxx") or "",
                        "time": item.get("sksj") or "",
                        "location": item.get("jxdd") or "",
                        "weeks": item.get("kcxqz") or item.get("zcm") or "",
                        "capacity": cap,
                        "selected": sel,
                        "remaining": remaining,
                        "is_full": remaining <= 0,
                        "extra": {
                            "jxb_mc": item.get("jxbmc") or item.get("kzmc", "未分组"),
                            "kclbmc": item.get("kclbmc") or "",
                            "xf": item.get("xf") or "",
                            "xkbz": item.get("xkbz") or "",
                            "sxbj": item.get("sxbj") or "",
                        }
                    })
                return {"classes": classes}
            html = payload if isinstance(payload, str) else ""
            classes = []
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
            for row in rows:
                cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
                if len(cells) >= 8:
                    classes.append({
                        "jxb_id": self._s(cells[0]),
                        "teacher": self._s(cells[3]) if len(cells) > 3 else "",
                        "time": self._s(cells[4]) if len(cells) > 4 else "",
                        "location": self._s(cells[5]) if len(cells) > 5 else "",
                        "weeks": self._s(cells[6]) if len(cells) > 6 else "",
                        "capacity": self._s(cells[7]) if len(cells) > 7 else "",
                        "selected": self._s(cells[8]) if len(cells) > 8 else "",
                    })
            return {"classes": classes}
        except Exception as e:
            return {"classes": [], "error": str(e)}

    def _select_target_class(self, classes, course_id):
        task = self.tasks.get(course_id)
        if task and task.target_jxb_id:
            for cls in classes:
                if cls.get("jxb_id") == task.target_jxb_id:
                    return cls
        for cls in classes:
            if not cls.get("is_full", True):
                return cls
        return classes[0] if classes else None

    def _submit_select(self, course_id, cls, xnm='2025', xqm='12'):
        data = {
            "jxb_ids": cls.get("jxb_id", ""),
            "kch_id": course_id,
            "qz": "0",
            "xkxnm": str(xnm),
            "xkxqm": str(xqm),
            "njdm_id": self.session.student_info.get('njdm_id', ''),
            "zyh_id": self.session.student_info.get('zyh_id', ''),
            "kklxdm": self.session.student_info.get('kklxdm', '10'),
        }
        text = self.session._req(XK_SELECT, method="POST", data=data)
        try:
            return json.loads(text)
        except Exception:
            return {"flag": "-1", "msg": text[:500]}

    def drop_course(self, jxb_ids, kch_id):
        data = {
            "kch_id": kch_id,
            "jxb_ids": jxb_ids,
            "xkxnm": self.session.student_info.get('xkxnm', '2025'),
            "xkxqm": self.session.student_info.get('xkxqm', '12'),
            **DROP_DEFAULTS,
        }
        text = self.session._req(XK_DROP, method="POST", data=data)
        try:
            result = json.loads(text)
        except Exception:
            result = {"flag": "-1", "msg": text[:500]}
        flag = result.get("flag") if isinstance(result, dict) else result
        if flag == "1" or flag == 1:
            return {"ok": True, "msg": "退课成功", "raw": result}
        return {"ok": False, "msg": result.get("msg") if isinstance(result, dict) else str(result), "raw": result}

    def get_status(self):
        return {
            "status": self.status,
            "tasks": [t.to_dict() for t in self.tasks.values()],
            "categories": self._categories,
            "initialized": self._initialized,
        }
