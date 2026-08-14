# zf-course-grabber

基于正方教务系统（zftal-ui-v5）的本地选课辅助工具。使用 Playwright 处理滑块验证码登录，requests 维持会话，Flask 提供本地 Web 界面。

> 仅供学习研究使用，请遵守所在学校教务管理规定。使用本工具产生的任何后果由使用者自行承担。

## ✨ 功能亮点

- 👥 **多账号支持** – 每个账号独立保存登录态，可在 Web 界面切换
- 🔍 **课程检索** – 按课程名称、课程编号、分类等多维度筛选
- ⚡ **并发抢课** – 同时监控多门课程，检测到余量自动提交选课请求
- 🖱️ **手动操作** – 支持对任意课程一键选课或退选
- 📅 **课表查看** – headless 模式抓取周课表，姓名学号自动脱敏，保护隐私
- 📊 **考试 & 成绩查询** – 本地 Web 界面直接展示

##🧩 技术栈
- Python 3.8+
- Playwright（Edge / Chromium）
- Flask
- requests

## 安装

```bash
git clone https://github.com/<你的用户名>/zf-course-grabber.git
cd zf-course-grabber
pip install -r requirements.txt
playwright install chromium
```

Windows 上若使用 Edge 通道（默认），无需额外安装浏览器。

## 使用

```bash
python run.py
```

启动后：

1. 按提示输入学号和密码
2. Edge 自动打开教务登录页，拖动滑块验证码完成登录
3. 浏览器自动关闭，session 保存到本地
4. 打开 `http://127.0.0.1:5000` 使用 Web 界面

### 课表查询

首次加载课表约需 10 秒（headless Edge 启动），之后可缓存优化。

## 项目结构

```
.
├── run.py                  # 入口：登录 + 启动 Flask
├── requirements.txt        # 依赖
└── course_grabber/
    ├── app.py              # Flask API
    ├── auth.py             # 登录 / 会话 / RSA 加密 / 心跳
    ├── courses.py          # 课程搜索 / 监控 / 选课
    └── templates/
        └── index.html      # Web 界面
```

## 隐私说明

- session cookie 仅保存在本地 `course_grabber/session_<学号>.json`，已加入 `.gitignore`
- 密码不落盘，仅通过 Playwright 填入浏览器
- 课表返回时自动脱敏姓名和学号
- 项目不包含任何遥测 / 统计 / 外部上报逻辑

## 致谢

- 参考 [vancehuds/VanceCoursePro](https://github.com/vancehuds/VanceCoursePro)
  和 [zfn_api](https://github.com/openschoolcn/zfn_api) 的 API 交互思路
## License

[MIT](LICENSE)
