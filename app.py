import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

# ----------------------
# 配置部分
# ----------------------
app = Flask(__name__)
app.secret_key = "yoursecretkey"  # Flask Session 需要

# 这里使用 SQLite 数据库，实际生产中可以换为 RDS 或其他数据库
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pilates.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 定义初始管理密码（实际可放在环境变量或配置文件）
ADMIN_PASSWORD_HASH = generate_password_hash("abby")

# ----------------------
# 数据库模型
# ----------------------

class Course(db.Model):
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)            # 课程名称
    start_time = db.Column(db.DateTime, nullable=False)         # 课程开始时间
    max_capacity = db.Column(db.Integer, nullable=False)        # 最大容量
    created_at = db.Column(db.DateTime, default=datetime.now)   # 课程添加时间

    # 为了简化演示，这里不动态储存 current_capacity,
    # 直接由 Enrollment.count() 判断已预约数

class Enrollment(db.Model):
    __tablename__ = 'enrollments'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100))
    is_waitlist = db.Column(db.Boolean, default=False)          # 是否在候补名单
    waitlist_order = db.Column(db.DateTime, default=None)       # 加入候补的时间戳
    created_at = db.Column(db.DateTime, default=datetime.now)

    course = db.relationship("Course", backref="enrollments")

# ----------------------
# 初始化数据库
# ----------------------
@app.before_first_request
def create_tables():
    db.create_all()

# ----------------------
# 工具函数
# ----------------------
def check_admin_login():
    """检查当前 session 是否已经验证管理员密码"""
    return session.get("admin_logged_in", False)

# ----------------------
# 路由：主页（显示可预约的课程列表 + 日历入口）
# ----------------------
@app.route('/')
def index():
    """
    前台首页，显示所有可用课程的列表，并判断是否满员。
    """
    now = datetime.now()
    courses = Course.query.order_by(Course.start_time.asc()).all()

    data = []
    for c in courses:
        enrollment_count = Enrollment.query.filter_by(course_id=c.id, is_waitlist=False).count()
        remaining = c.max_capacity - enrollment_count
        # 如果已满，remaining <= 0
        data.append({
            "id": c.id,
            "name": c.name,
            "start_time": c.start_time,
            "enrollment_count": enrollment_count,
            "remaining": remaining,
            "max_capacity": c.max_capacity
        })

    return render_template("index.html", courses=data, now=now)

# ----------------------
# 路由：提交预约
# ----------------------
@app.route('/enroll', methods=['POST'])
def enroll():
    """处理用户的预约/候补请求"""
    course_id = request.form.get('course_id')
    name = request.form.get('name')
    phone = request.form.get('phone')
    email = request.form.get('email')
    want_waitlist = request.form.get('want_waitlist', 'false') == 'true'

    # 表单简单验证
    if not name or not phone:
        flash("姓名和电话为必填", "error")
        return redirect(url_for('index'))

    if not phone.startswith("+1"):
        flash("电话必须以 +1 开头", "error")
        return redirect(url_for('index'))

    # 验证 email 格式(如果填写)
    if email:
        if "@" not in email or "." not in email:
            flash("邮箱格式不正确", "error")
            return redirect(url_for('index'))

    course = Course.query.get(course_id)
    if not course:
        flash("所选课程不存在", "error")
        return redirect(url_for('index'))

    # 先检查当前预约人数
    enrollment_count = Enrollment.query.filter_by(course_id=course.id, is_waitlist=False).count()
    if enrollment_count < course.max_capacity:
        # 还有余位，直接加入正式预约
        try:
            new_enrollment = Enrollment(
                course_id=course.id,
                name=name,
                phone=phone,
                email=email,
                is_waitlist=False,
                created_at=datetime.now()
            )
            db.session.add(new_enrollment)
            db.session.commit()
            flash("预约成功！", "success")
        except IntegrityError:
            db.session.rollback()
            flash("发生并发冲突，请稍后再试", "error")
    else:
        # 课程已满
        if want_waitlist:
            # 如果用户选择加入候补名单
            new_enrollment = Enrollment(
                course_id=course.id,
                name=name,
                phone=phone,
                email=email,
                is_waitlist=True,
                waitlist_order=datetime.now(),
                created_at=datetime.now()
            )
            db.session.add(new_enrollment)
            db.session.commit()
            flash("课程已满，您已加入候补名单", "info")
        else:
            flash("该课程已满！未加入候补名单", "error")

    return redirect(url_for('index'))

# ----------------------
# 路由：取消预约
# ----------------------
@app.route('/cancel/<int:enroll_id>', methods=['GET'])
def cancel(enroll_id):
    """取消预约，如果有候补则转为正式预约"""
    enrollment = Enrollment.query.get_or_404(enroll_id)
    course_id = enrollment.course_id

    db.session.delete(enrollment)
    db.session.commit()
    flash("预约已取消", "info")

    # 检查候补名单中是否有人可以顶上
    waitlist_candidate = Enrollment.query.filter_by(
        course_id=course_id, 
        is_waitlist=True
    ).order_by(Enrollment.waitlist_order.asc()).first()

    if waitlist_candidate:
        # 将最早排队的候补转为正式预约
        waitlist_candidate.is_waitlist = False
        waitlist_candidate.waitlist_order = None
        db.session.commit()
        flash(f"候补名单中的 {waitlist_candidate.name} 已成功转为正式预约", "success")

    return redirect(url_for('index'))

# ----------------------
# 路由：日历视图 (FullCalendar 演示)
# ----------------------
@app.route('/calendar')
def calendar_view():
    return render_template("calendar.html")

@app.route('/api/events')
def api_events():
    """
    返回 JSON 数据给前端的 FullCalendar，用于显示课程日历
    FullCalendar 默认要求字段：
    - id
    - title
    - start (ISO8601格式的日期时间字符串)
    """
    courses = Course.query.all()
    events = []
    for c in courses:
        enrollment_count = Enrollment.query.filter_by(course_id=c.id, is_waitlist=False).count()
        remaining = c.max_capacity - enrollment_count
        events.append({
            "id": c.id,
            "title": f"{c.name} (剩余: {remaining})",
            "start": c.start_time.isoformat()  # 转为ISO字符串
        })
    return jsonify(events)

# ----------------------
# 后台管理：登录
# ----------------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get("password")
        if check_password_hash(ADMIN_PASSWORD_HASH, password):
            session["admin_logged_in"] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash("密码错误！", "error")
            return redirect(url_for('admin_login'))
    return render_template("login.html")

# ----------------------
# 后台管理：登出
# ----------------------
@app.route('/admin/logout')
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("已退出后台", "info")
    return redirect(url_for('admin_login'))

# ----------------------
# 后台管理：首页 (查看课程/预约记录)
# ----------------------
@app.route('/admin')
def admin_dashboard():
    if not check_admin_login():
        return redirect(url_for('admin_login'))

    # 显示所有课程和所有预约（包括候补）
    courses = Course.query.order_by(Course.start_time.asc()).all()
    enrollments = Enrollment.query.order_by(Enrollment.created_at.desc()).all()

    return render_template("admin.html", courses=courses, enrollments=enrollments)

# ----------------------
# 后台管理：添加课程
# ----------------------
@app.route('/admin/add_course', methods=['POST'])
def add_course():
    if not check_admin_login():
        return redirect(url_for('admin_login'))

    name = request.form.get('name')
    start_time_str = request.form.get('start_time')
    max_capacity = request.form.get('max_capacity')

    if not name or not start_time_str or not max_capacity:
        flash("请完整填写课程信息", "error")
        return redirect(url_for('admin_dashboard'))

    try:
        # 解析时间，比如前端传的格式 "2025-01-01 10:00"
        start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M")
        max_capacity = int(max_capacity)
    except ValueError:
        flash("日期时间格式或人数上限格式错误", "error")
        return redirect(url_for('admin_dashboard'))

    new_course = Course(
        name=name,
        start_time=start_time,
        max_capacity=max_capacity
    )
    db.session.add(new_course)
    db.session.commit()
    flash("成功添加课程", "success")

    return redirect(url_for('admin_dashboard'))

# ----------------------
# 后台管理：删除课程
# ----------------------
@app.route('/admin/delete_course/<int:course_id>', methods=['GET'])
def delete_course(course_id):
    if not check_admin_login():
        return redirect(url_for('admin_login'))

    course = Course.query.get_or_404(course_id)
    # 同时删掉对应的预约记录
    Enrollment.query.filter_by(course_id=course_id).delete()
    db.session.delete(course)
    db.session.commit()
    flash("成功删除课程及其预约记录", "success")

    return redirect(url_for('admin_dashboard'))

# ----------------------
# 主函数启动
# ----------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
