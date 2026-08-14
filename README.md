# 🎓 zf-course-grabber （仅验证hzcu）

> 基于正方教务系统（zftal-ui-v5）的本地选课辅助工具  
> 使用 Playwright 处理滑块验证码登录，requests 维持会话，Flask 提供本地 Web 界面

**仅供学习研究使用，请遵守所在学校教务管理规定。使用本工具产生的任何后果由使用者自行承担。**

---

## ✨ 功能亮点

- 🔐 **半自动登录** – Playwright 调用本机 Edge/Chromium，自动填写账号密码，您只需手动拖拽一次滑块验证码
- 💾 **会话持久化** – 登录成功后自动保存 session cookie，并定时心跳保活，无需频繁重新登录
- 👥 **多账号支持** – 每个账号独立保存登录态，可随时在 Web 界面切换
- 🔍 **课程检索** – 按课程名称、课程编号、分类等多维度筛选
- ⚡ **并发抢课** – 最多同时监控 5 门课程，检测到余量自动提交选课请求
- 🖱️ **手动操作** – 支持对任意课程一键选课或退选
- 📅 **课表查看** – headless 模式抓取周课表，姓名学号自动脱敏，保护隐私
- 📊 **考试 & 成绩查询** – 本地 Web 界面直接展示
- 📆 **ICS 导出** – 一键导出课表为 `.ics` 文件，可导入 Google Calendar、Outlook 等日历应用

---

## 🚀 快速开始

### 安装

```bash
git clone https://github.com/Prime-Eden/zf-course-grabber.git
cd zf-course-grabber
pip install -r requirements.txt
playwright install chromium   # 若使用 Edge 可跳过
