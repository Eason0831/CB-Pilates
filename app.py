from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from notify import send_notification  # 引入 WxPusher 通知功能
from sqlalchemy import func

# 翻译字典（默认中文，切换后可选择英文）
translations = {
    'zh': {
        'title': 'C&B普拉提馆',
        'available_courses': '可预约课程',
        'calendar_view': '日历视图',
        'contact_us': '联系我们',
        'admin_login': '管理登录',
        'admin_panel': '后台管理',
        'logout': '退出',
        'book': '预约',
        'waitlist': '候补',
        'full': '已满',
        'name': '姓名',
        'phone': '电话号码',
        'email': '邮箱（可选）',
        'remaining': '剩余名额',
        'submit': '提交',
        'close': '关闭',
        'welcome': '欢迎来到',
        'auto_waitlist': '若满员则自动加入候补',
        'phone_number': '手机号：',
        'wechat': '微信号：',
        'phone_hint': '请输入10位数字',
        'login_failed': '密码错误！',
        'name_phone_required': '姓名和电话为必填',
        'duplicate_booking': '您已预约过同时间段此课程',
        'course_not_found': '所选课程不存在',
        'booking_success': '预约成功！',
        'added_to_waitlist': '课程已满，已加入候补名单',
        'class_full': '该课程已满！未加入候补名单',
        'booking_error': '预约失败，请稍后重试',
        'booking_cancelled': '预约已取消',
        'waitlist_promoted': '候补转为正式预约',
        'cancel_error': '取消预约失败，请重试',
        'logged_out': '已退出后台',
        'load_error': '加载数据失败，请刷新重试',
        'all_fields_required': '请完整填写所有字段',
        'invalid_format': '时间或人数格式不正确',
        'course_added': '成功添加课程',
        'add_course_error': '添加课程失败，请重试',
        'course_deleted': '已删除课程和相关报名信息',
        'delete_course_error': '删除课程失败，请重试'
    },
    'en': {
        'title': 'C&B Pilates Studio',
        'available_courses': 'Available Courses',
        'calendar_view': 'Calendar',
        'contact_us': 'Contact Us',
        'admin_login': 'Admin Login',
        'admin_panel': 'Admin Panel',
        'logout': 'Logout',
        'book': 'Book',
        'waitlist': 'Waitlist',
        'full': 'Full',
        'name': 'Name',
        'phone': 'Phone',
        'email': 'Email (Optional)',
        'remaining': 'Spots Left',
        'submit': 'Submit',
        'close': 'Close',
        'welcome': 'Welcome to',
        'auto_waitlist': 'Add to waitlist if full',
        'phone_number': 'Phone: ',
        'wechat': 'WeChat: ',
        'phone_hint': 'Enter 10 digits',
        'login_failed': 'Wrong password!',
        'name_phone_required': 'Name and phone are required',
        'duplicate_booking': 'You have already booked this time slot',
        'course_not_found': 'Selected course not found',
        'booking_success': 'Booking successful!',
        'added_to_waitlist': 'Course is full, added to waitlist',
        'class_full': 'Class is full! Not added to waitlist',
        'booking_error': 'Booking failed, please try again',
        'booking_cancelled': 'Booking cancelled',
        'waitlist_promoted': 'Promoted from waitlist',
        'cancel_error': 'Cancel failed, please try again',
        'logged_out': 'Logged out successfully',
        'load_error': 'Failed to load data, please refresh',
        'all_fields_required': 'Please fill in all fields',
        'invalid_format': 'Invalid time or capacity format',
        'course_added': 'Course added successfully',
        'add_course_error': 'Failed to add course, please try again',
        'course_deleted': 'Course and related bookings deleted',
        'delete_course_error': 'Failed to delete course, please try again'
    }
}

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = "yoursecretkey"

# 数据库配置
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pilates.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

ADMIN_PASSWORD_HASH = generate_password_hash("abby")

# 修改：新增 teacher 字段（课程老师）
class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    teacher = db.Column(db.String(100), nullable=False)  # 课程老师字段
    start_time = db.Column(db.DateTime, nullable=False)
    max_capacity = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100))
    is_waitlist = db.Column(db.Boolean, default=False)
    waitlist_order = db.Column(db.DateTime, default=None)
    created_at = db.Column(db.DateTime, default=datetime.now)
    course = db.relationship("Course", backref="enrollments")

@app.before_first_request
def create_tables():
    db.create_all()

def check_admin_login():
    return session.get("admin_logged_in", False)

def get_locale():
    return session.get('lang', 'zh')

@app.route('/switch_language/<lang>')
def switch_language(lang):
    session['lang'] = lang
    return redirect(request.referrer or url_for('index'))

@app.route('/')
def index():
    lang = get_locale()
    return render_template("index.html", t=translations[lang])

@app.route('/available_courses')
def available_courses():
    now = datetime.now()
    courses = Course.query.order_by(Course.start_time.asc()).all()
    data = []
    for c in courses:
        enrollment_count = Enrollment.query.filter_by(course_id=c.id, is_waitlist=False).count()
        remaining = c.max_capacity - enrollment_count
        data.append({
            "id": c.id,
            "name": c.name,
            "teacher": c.teacher,
            "start_time": c.start_time,
            "enrollment_count": enrollment_count,
            "remaining": remaining,
            "max_capacity": c.max_capacity
        })
    return render_template("available_courses.html", courses=data, now=now, t=translations[get_locale()])

def check_duplicate_enrollment(course_id, phone):
    course = Course.query.get(course_id)
    if not course:
        return False
    duplicate = Enrollment.query.join(Course).filter(
        Course.start_time == course.start_time,
        Enrollment.phone == phone
    ).first()
    return duplicate is not None

@app.route('/enroll', methods=['POST'])
def enroll():
    course_id = request.form.get('course_id')
    name = request.form.get('name')
    phone = request.form.get('phone')
    if not phone.startswith('+1'):
        phone = '+1' + phone
    email = request.form.get('email')
    want_waitlist = request.form.get('want_waitlist', 'false') == 'true'
    if not name or not phone:
        flash(translations[get_locale()]['name_phone_required'], "error")
        return redirect(url_for('available_courses'))
    if check_duplicate_enrollment(course_id, phone):
        flash(translations[get_locale()]['duplicate_booking'], "error")
        return redirect(url_for('available_courses'))
    course = Course.query.get(course_id)
    if not course:
        flash(translations[get_locale()]['course_not_found'], "error")
        return redirect(url_for('available_courses'))
    enrollment_count = Enrollment.query.filter_by(course_id=course.id, is_waitlist=False).count()
    if enrollment_count < course.max_capacity:
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
        email_info = f"\n📧 邮箱：{email}" if email else ""
        message = (f"📢 预约通知：{name}（{phone}）成功预约了课程《{course.name}》\n教师：{course.teacher}{email_info}\n"
                   f"📅 时间：{course.start_time.strftime('%Y-%m-%d %H:%M')}")
        send_notification(message)
        flash(translations[get_locale()]['booking_success'], "success")
    else:
        if want_waitlist:
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
            email_info = f"\n📧 邮箱：{email}" if email else ""
            message = (f"📢 候补预约通知：{name}（{phone}）已加入候补名单\n教师：{course.teacher}{email_info}\n"
                       f"课程：《{course.name}》\n"
                       f"📅 时间：{course.start_time.strftime('%Y-%m-%d %H:%M')}")
            send_notification(message)
            flash(translations[get_locale()]['added_to_waitlist'], "info")
        else:
            flash(translations[get_locale()]['class_full'], "error")
    return redirect(url_for('available_courses'))

@app.route('/calendar_enroll', methods=['POST'])
def calendar_enroll():
    course_id = request.form.get('course_id')
    name = request.form.get('name')
    phone = request.form.get('phone')
    if not phone.startswith('+1'):
        phone = '+1' + phone
    email = request.form.get('email')
    want_waitlist = request.form.get('want_waitlist', 'false') == 'true'
    if not name or not phone:
        flash(translations[get_locale()]['name_phone_required'], "error")
        return redirect(url_for('calendar_view'))
    if check_duplicate_enrollment(course_id, phone):
        flash(translations[get_locale()]['duplicate_booking'], "error")
        return redirect(url_for('calendar_view'))
    course = Course.query.get(course_id)
    if not course:
        flash(translations[get_locale()]['course_not_found'], "error")
        return redirect(url_for('calendar_view'))
    enrollment_count = Enrollment.query.filter_by(course_id=course.id, is_waitlist=False).count()
    if enrollment_count < course.max_capacity:
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
        email_info = f"\n📧 Email: {email}" if email else ""
        message = (f"📢 Booking Notification: {name} ({phone}) successfully booked course 《{course.name}》\n教师：{course.teacher}"
                   f"{email_info}\n📅 Time: {course.start_time.strftime('%Y-%m-%d %H:%M')}")
        send_notification(message)
        flash(translations[get_locale()]['booking_success'], "success")
    else:
        if want_waitlist:
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
            email_info = f"\n📧 Email: {email}" if email else ""
            message = (f"📢 Waitlist Notification: {name} ({phone}) has joined the waitlist\n教师：{course.teacher}"
                       f"{email_info}\nCourse: 《{course.name}》\n📅 Time: {course.start_time.strftime('%Y-%m-%d %H:%M')}")
            send_notification(message)
            flash(translations[get_locale()]['added_to_waitlist'], "info")
        else:
            flash(translations[get_locale()]['class_full'], "error")
    return redirect(url_for('calendar_view'))

@app.route('/cancel/<int:enroll_id>', methods=['GET'])
def cancel(enroll_id):
    enrollment = Enrollment.query.get_or_404(enroll_id)
    course_id = enrollment.course_id
    db.session.delete(enrollment)
    db.session.commit()
    flash(translations[get_locale()]['booking_cancelled'], "info")
    waitlist_candidate = Enrollment.query.filter_by(
        course_id=course_id,
        is_waitlist=True
    ).order_by(Enrollment.waitlist_order.asc()).first()
    if waitlist_candidate:
        waitlist_candidate.is_waitlist = False
        waitlist_candidate.waitlist_order = None
        db.session.commit()
        flash(translations[get_locale()]['waitlist_promoted'], "success")
        course = waitlist_candidate.course
        email_info = f"\n📧 邮箱：{waitlist_candidate.email}" if waitlist_candidate.email else ""
        message = (f"📢 候补晋级通知：{waitlist_candidate.name}（{waitlist_candidate.phone}）已由候补转为正式预约\n教师：{course.teacher}"
                   f"{email_info}\n课程：《{course.name}》\n📅 时间：{course.start_time.strftime('%Y-%m-%d %H:%M')}")
        send_notification(message)
    return redirect(url_for('available_courses'))

@app.route('/calendar')
def calendar_view():
    return render_template("calendar.html", t=translations[get_locale()])

# 新增：显示指定日期课程的页面，路由末尾带斜杠，确保匹配
@app.route('/day/<date>/', strict_slashes=False)
def day_courses(date):
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        flash("日期格式错误", "error")
        return redirect(url_for('calendar_view'))
    courses = Course.query.filter(func.date(Course.start_time) == date_obj).order_by(Course.start_time.asc()).all()
    data = []
    for c in courses:
        enrollment_count = Enrollment.query.filter_by(course_id=c.id, is_waitlist=False).count()
        remaining = c.max_capacity - enrollment_count
        data.append({
            "id": c.id,
            "name": c.name,
            "teacher": c.teacher,
            "start_time": c.start_time,
            "enrollment_count": enrollment_count,
            "remaining": remaining,
            "max_capacity": c.max_capacity
        })
    return render_template("day_courses.html", courses=data, date=date, t=translations[get_locale()])

# 新增：显示课程详细信息的页面，允许修改课程信息和查看预约记录
@app.route('/admin/course/<int:course_id>', methods=['GET', 'POST'])
def course_detail(course_id):
    if not check_admin_login():
        return redirect(url_for('admin_login'))
    course = Course.query.get_or_404(course_id)
    if request.method == 'POST':
        course.name = request.form.get('name')
        course.teacher = request.form.get('teacher')
        start_time_str = request.form.get('start_time')
        try:
            course.start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")
        except ValueError:
            course.start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M")
        course.max_capacity = int(request.form.get('max_capacity'))
        db.session.commit()
        flash("课程信息已更新", "success")
        return redirect(url_for('course_detail', course_id=course_id))
    enrollment_list = Enrollment.query.filter_by(course_id=course.id).order_by(Enrollment.created_at.asc()).all()
    enrollment_count = sum(1 for e in enrollment_list if not e.is_waitlist)
    remaining = course.max_capacity - enrollment_count
    return render_template("course_detail.html", course=course, enrollments=enrollment_list, remaining=remaining, t=translations[get_locale()])

# 新增：编辑单个预约记录
@app.route('/admin/edit_enrollment/<int:enroll_id>', methods=['GET', 'POST'])
def edit_enrollment(enroll_id):
    if not check_admin_login():
        return redirect(url_for('admin_login'))
    enrollment = Enrollment.query.get_or_404(enroll_id)
    if request.method == 'POST':
        enrollment.name = request.form.get('name')
        enrollment.phone = request.form.get('phone')
        enrollment.email = request.form.get('email')
        enrollment.is_waitlist = (request.form.get('is_waitlist') == 'true')
        db.session.commit()
        flash("预约信息已更新", "success")
        return redirect(url_for('course_detail', course_id=enrollment.course_id))
    return render_template("edit_enrollment.html", enrollment=enrollment, t=translations[get_locale()])

# 新增：删除单个预约记录
@app.route('/admin/delete_enrollment/<int:enroll_id>')
def delete_enrollment(enroll_id):
    if not check_admin_login():
        return redirect(url_for('admin_login'))
    enrollment = Enrollment.query.get_or_404(enroll_id)
    course_id = enrollment.course_id
    db.session.delete(enrollment)
    db.session.commit()
    flash("预约信息已删除", "success")
    return redirect(url_for('course_detail', course_id=course_id))

@app.route('/contact')
def contact():
    return render_template("contact.html", t=translations[get_locale()])

# 修改 /api/events：按日期聚合课程，每天只显示课程数量，并将当天课程详情放在 extendedProps 中
@app.route('/api/events')
def api_events():
    courses = Course.query.all()
    events_dict = {}
    lang = get_locale()  # 获取当前语言
    
    for c in courses:
        date_str = c.start_time.strftime("%Y-%m-%d")
        events_dict.setdefault(date_str, []).append(c)
    
    events = []
    for date_str, course_list in events_dict.items():
        count = len(course_list)
        
        # 根据当前语言生成不同的标题
        if lang == 'zh':
            event_title = f"{count} 节课程"
        else:
            # 英文模式下：若有多节则加 s
            event_title = f"{count} Session{'s' if count > 1 else ''}"
        
        events.append({
            "id": date_str,
            "title": event_title,
            "start": date_str,
            "extendedProps": {
                "courses": [{
                    "id": c.id,
                    "name": c.name,
                    "teacher": c.teacher,
                    "start_time": c.start_time.strftime("%Y-%m-%d %H:%M"),
                    "remaining": c.max_capacity - Enrollment.query.filter_by(course_id=c.id, is_waitlist=False).count()
                } for c in course_list]
            }
        })
    
    return jsonify(events)


@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get("password")
        if check_password_hash(ADMIN_PASSWORD_HASH, password):
            session["admin_logged_in"] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash(translations[get_locale()]['login_failed'], "error")
            return redirect(url_for('admin_login'))
    return render_template("login.html", t=translations[get_locale()])

@app.route('/admin/logout')
def admin_logout():
    session.pop("admin_logged_in", None)
    flash(translations[get_locale()]['logged_out'], "info")
    return redirect(url_for('admin_login'))

@app.route('/admin')
def admin_dashboard():
    if not check_admin_login():
        return redirect(url_for('admin_login'))
    courses = Course.query.order_by(Course.start_time.asc()).all()
    enrollments = Enrollment.query.order_by(Enrollment.created_at.desc()).all()
    return render_template("admin.html", courses=courses, enrollments=enrollments, t=translations[get_locale()])

@app.route('/admin/add_course', methods=['POST'])
def add_course():
    if not check_admin_login():
        return redirect(url_for('admin_login'))
    name = request.form.get('name')
    teacher = request.form.get('teacher')
    start_time_str = request.form.get('start_time')
    max_capacity = request.form.get('max_capacity')
    if not name or not teacher or not start_time_str or not max_capacity:
        flash(translations[get_locale()]['all_fields_required'], "error")
        return redirect(url_for('admin_dashboard'))
    try:
        try:
            start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")
        except ValueError:
            start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M")
        max_capacity = int(max_capacity)
    except ValueError:
        flash(translations[get_locale()]['invalid_format'], "error")
        return redirect(url_for('admin_dashboard'))
    new_course = Course(
        name=name,
        teacher=teacher,
        start_time=start_time,
        max_capacity=max_capacity
    )
    db.session.add(new_course)
    db.session.commit()
    flash(translations[get_locale()]['course_added'], "success")
    lang = get_locale()
    if lang == 'zh':
        message = (f"📢 新课程通知：\n课程名称：{new_course.name}\n教师：{new_course.teacher}\n开始时间：{new_course.start_time.strftime('%Y-%m-%d %H:%M')}\n"
                   f"最大人数：{new_course.max_capacity}")
    else:
        message = (f"📢 New Course Added:\nCourse Name: {new_course.name}\nTeacher: {new_course.teacher}\nStart Time: {new_course.start_time.strftime('%Y-%m-%d %H:%M')}\n"
                   f"Capacity: {new_course.max_capacity}")
    send_notification(message)
    return redirect(url_for('admin_dashboard'))
    
@app.route('/admin/add_course_page')
def add_course_page():
    return render_template('add_course_page.html', t=translations[get_locale()], session=session)

@app.route('/courses')
def courses():
    lang = get_locale()
    return render_template("courses.html", t=translations[lang])

@app.route('/admin/delete_course/<int:course_id>')
def delete_course(course_id):
    if not check_admin_login():
        return redirect(url_for('admin_login'))
    course = Course.query.get_or_404(course_id)
    course_info = f"课程名称：{course.name}\n教师：{course.teacher}\n开始时间：{course.start_time.strftime('%Y-%m-%d %H:%M')}\n最大容量：{course.max_capacity}"
    Enrollment.query.filter_by(course_id=course_id).delete()
    db.session.delete(course)
    db.session.commit()
    flash(translations[get_locale()]['course_deleted'], "success")
    lang = get_locale()
    if lang == 'zh':
        message = f"📢 课程删除通知：\n{course_info}\n该课程已被删除。"
    else:
        message = f"📢 Course Deletion Notice:\n{course_info}\nThe course has been deleted."
    send_notification(message)
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=False)
