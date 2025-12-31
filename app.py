from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from flask_login import UserMixin, LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

app = Flask(__name__)
app.config["SECRET_KEY"] = "testing234"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# ----------------- MODELS -----------------
# --- Classroom Model ---
# --- Many-to-many table for teachers and classrooms ---
teacher_class = db.Table(
    "teacher_class",
    db.Column("teacher_id", db.Integer, db.ForeignKey("user.id")),
    db.Column("classroom_id", db.Integer, db.ForeignKey("classroom.id"))
)
def get_teacher_classes():
    teacher = Teacher.query.get(session["teacher_id"])
    return teacher.classes.split(",")

# --- User Model ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(10), nullable=False)  # "student" or "teacher"
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True)  # only for teachers
    student_id = db.Column(db.String(20), unique=True)  # only for students
    password = db.Column(db.String(200), nullable=False)
    points = db.Column(db.Integer, default=0)

    # Optional: track parts submitted or completed for progress
    submitted_parts = db.relationship("Part", secondary="part_submissions", backref="submitted_users")
    # For students: one classroom
    classroom_id = db.Column(db.Integer, db.ForeignKey("classroom.id"), nullable=True)
    
        
    # For teachers: one course
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=True)

    # Many-to-many relationship with classrooms (for teachers)
    classrooms = db.relationship(
        "Classroom",
        secondary=teacher_class,
        back_populates="teachers"
    )
classroom_course = db.Table(
    "classroom_course",
    db.Column("classroom_id", db.Integer, db.ForeignKey("classroom.id")),
    db.Column("course_id", db.Integer, db.ForeignKey("course.id"))
)
# --- Classroom Model ---
class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)

    # Many teachers in this classroom
    teachers = db.relationship(
        "User",
        secondary=teacher_class,
        back_populates="classrooms"
    )

    # Course relationship
    courses = db.relationship(
        "Course",
        secondary=classroom_course,
        backref=db.backref("classrooms", lazy="dynamic")
    )
    # Students in this classroom
    students = db.relationship(
        "User",
        backref="classroom",
        lazy=True,
        primaryjoin="and_(User.classroom_id==Classroom.id, User.role=='student')"
    )

    events = db.relationship("CalendarEvent", backref="classroom", lazy=True)
class PartCompletion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.Integer, db.ForeignKey('part.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    completed_on = db.Column(db.DateTime, default=datetime.utcnow)

# --- Course Model ---
class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)

    # One teacher can create a course

    



class LessonNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.Integer, db.ForeignKey("part.id"), nullable=False)
    pdf_url = db.Column(db.String(300), nullable=False)

    part = db.relationship("Part", backref="lesson_notes")

class Part(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey("chapter.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    lesson_video = db.Column(db.String(300))
    answer_video = db.Column(db.String(300))

    chapter = db.relationship("Chapter", backref="parts")
class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.Integer, db.ForeignKey("part.id"), nullable=False)

    question_text = db.Column(db.Text, nullable=False)

    option_a = db.Column(db.String(200), nullable=False)
    option_b = db.Column(db.String(200), nullable=False)
    option_c = db.Column(db.String(200), nullable=False)
    option_d = db.Column(db.String(200), nullable=False)

    correct_answer = db.Column(db.String(1), nullable=False)  # A, B, C, D

    part = db.relationship("Part", backref="questions")


class PartSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey("part.id"), nullable=False)

    correct = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)

    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("User")
    part = db.relationship("Part")

    __table_args__ = (
        db.UniqueConstraint("student_id", "part_id"),
    )
class StudentPartProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey('part.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('student_id', 'part_id'),
    )

@app.route("/submit_part/<int:part_id>", methods=["POST"])
@login_required
def submit_part(part_id):
    part = Part.query.get_or_404(part_id)

    # Count correct answers
    correct = 0
    total = len(part.questions)

    for q in part.questions:
        student_ans = request.form.get(f"q_{q.id}")
        if student_ans == q.correct_answer:
            correct += 1

    # Add points to student
    current_user.points += correct * 10

    # Record submission
    submission = PartSubmission(
        student_id=current_user.id,
        part_id=part.id,
        correct=correct,
        total=total
    )

    # Add part to student's submitted_parts (for progress tracking)
    if part not in current_user.submitted_parts:
        current_user.submitted_parts.append(part)

    db.session.add(submission)
    db.session.commit()

    flash(f"Submitted! Score: {correct}/{total} (+{correct*10} points)", "success")
    return redirect(url_for("chapter_page", chapter_id=part.chapter_id))



part_submissions = db.Table('part_submissions',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('part_id', db.Integer, db.ForeignKey('part.id'))
)


# --- Calendar Events ---
class CalendarEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.String(10))
    classroom_id = db.Column(db.Integer, db.ForeignKey("classroom.id"))
    


# --- Chapter Model ---
class Chapter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"))
    title = db.Column(db.String(100), nullable=False)
    video_url = db.Column(db.String(300))
    content = db.Column(db.Text)
    order = db.Column(db.Integer, nullable=False)  # order of chapters
    course = db.relationship("Course", backref="chapters")
class SubmittedPart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    part_id = db.Column(db.Integer, db.ForeignKey("part.id"))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Forum Post
class ForumPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)

    # link to classroom
    classroom_id = db.Column(db.Integer, db.ForeignKey("classroom.id"), nullable=False)

    # link to user (teacher or student)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    author = db.relationship("User", backref="forum_posts")

    # relationship to answers
    answers = db.relationship("ForumAnswer", backref="post", cascade="all, delete")



# Forum Reply
class ForumAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)

    post_id = db.Column(db.Integer, db.ForeignKey("forum_post.id"), nullable=False)

    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    author = db.relationship("User", backref="forum_answers")


# --- Chapter Completion ---
class ChapterCompletion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    chapter_id = db.Column(db.Integer, db.ForeignKey("chapter.id"))
    completed = db.Column(db.Boolean, default=False)
    practice_score = db.Column(db.Float, nullable=True)
    student = db.relationship("User", backref="chapter_completions")
    chapter = db.relationship("Chapter", backref="completions")

# ----------------- LOGIN -----------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ----------------- ROUTES -----------------
@app.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.role == "teacher":
            return redirect(url_for("teacher_dashboard"))
        else:
            return redirect(url_for("student_dashboard"))
    return render_template("index.html")

# ---------- SIGNUP ----------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    classrooms = Classroom.query.all()  # for student dropdown

    if request.method == "POST":
        role = request.form.get("role")
        name = request.form.get("name")
        password_raw = request.form.get("password")
        if not all([role, name, password_raw]):
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("signup"))

        password = generate_password_hash(password_raw, method="pbkdf2:sha256")

        try:
            if role == "teacher":
                email = request.form.get("email_or_id")
                verification = request.form.get("teacher_verif")
                class_names_raw = request.form.get("class_name")

                if not email or not class_names_raw:
                    flash("Please fill in email and class names.", "danger")
                    return redirect(url_for("signup"))

                # Check teacher verification
                if verification != "teacher":
                    flash("Invalid teacher verification password", "danger")
                    return redirect(url_for("signup"))

                # Check if email already exists
                if User.query.filter_by(email=email).first():
                    flash("A user with this email already exists.", "danger")
                    return redirect(url_for("signup"))

                # Create teacher
                new_teacher = User(name=name, email=email, password=password, role="teacher")
                db.session.add(new_teacher)
                db.session.commit()  # commit to get ID

                # Process class names
                class_names = [c.strip() for c in class_names_raw.split(",") if c.strip()]
                for cname in class_names:
                    classroom = Classroom.query.filter_by(name=cname).first()
                    if not classroom:
                        classroom = Classroom(name=cname)
                        db.session.add(classroom)
                        db.session.commit()

                    # Add teacher to classroom
                    if classroom not in new_teacher.classrooms:
                        new_teacher.classrooms.append(classroom)

                db.session.commit()
                flash("Teacher account created and joined/created classes!", "success")
                return redirect(url_for("login"))

            elif role == "student":
                student_id = request.form.get("email_or_id")
                classroom_id = request.form.get("classroom_id")

                if not student_id or not classroom_id:
                    flash("Please provide student ID and select a classroom.", "danger")
                    return redirect(url_for("signup"))

                # Check if student ID already exists
                if User.query.filter_by(student_id=student_id).first():
                    flash("A student with this ID already exists.", "danger")
                    return redirect(url_for("signup"))

                classroom = Classroom.query.get(classroom_id)
                if not classroom:
                    flash("Selected classroom does not exist.", "danger")
                    return redirect(url_for("signup"))

                new_student = User(
                    name=name,
                    student_id=student_id,
                    password=password,
                    role="student",
                    classroom_id=classroom.id
                )
                db.session.add(new_student)
                db.session.commit()
                flash("Student account created!", "success")
                return redirect(url_for("login"))

            else:
                flash("Invalid role selected.", "danger")
                return redirect(url_for("signup"))

        except Exception as e:
            db.session.rollback()
            flash("An unexpected error occurred: " + str(e), "danger")
            return redirect(url_for("signup"))

    return render_template("signup.html", classrooms=classrooms)


@app.route('/leaderboard')
@login_required
def leaderboard():
    students = User.query.filter_by(role="student").all()

    students = sorted(students, key=lambda s: s.points, reverse=True)
    return render_template('leaderboard.html', students=students)


@app.route("/profile")
@login_required
def profile():
 
    return render_template("profile.html")

# Forum main page for classroom
# Forum main page for classroom
@app.route("/forum", methods=["GET", "POST"])
@login_required
def forum():
    if current_user.role == "teacher":
        # Get all classes for this teacher
        teacher_classes = current_user.classrooms
        classroom_id = request.args.get("classroom_id", type=int)

        # Default to first classroom if none selected
        if classroom_id:
            classroom = Classroom.query.get_or_404(classroom_id)
            if classroom not in teacher_classes:
                flash("You do not belong to this classroom.", "danger")
                return redirect(url_for("forum"))
        elif teacher_classes:
            classroom = teacher_classes[0]
        else:
            classroom = None

    else:
        # Students only have one classroom
        classroom = current_user.classroom
        teacher_classes = []

    # Handle new post
    if request.method == "POST" and classroom:
        content = request.form.get("content")
        if content:
            post = ForumPost(content=content, classroom_id=classroom.id, author_id=current_user.id)
            db.session.add(post)
            db.session.commit()
            flash("Post added!", "success")
        return redirect(url_for("forum", classroom_id=classroom.id if classroom else None))

    # Fetch posts for selected classroom
    posts = ForumPost.query.filter_by(classroom_id=classroom.id).order_by(ForumPost.id.desc()).all() if classroom else []

    return render_template(
        "forum.html",
        teacher_classes=teacher_classes,
        current_class=classroom,
        posts=posts
    )



# Reply to post
@app.route("/forum/answer/<int:post_id>", methods=["POST"])
@login_required
def answer_post(post_id):
    post = ForumPost.query.get_or_404(post_id)
    classroom_id = post.classroom_id

    content = request.form.get("content")
    if content:
        answer = ForumAnswer(
            content=content,
            post_id=post.id,
            author_id=current_user.id
        )
        db.session.add(answer)
        db.session.commit()

    return redirect(url_for("forum", classroom_id=classroom_id))




# Delete post (teachers only)
@app.route("/forum/delete/<int:post_id>")
@login_required
def delete_post(post_id):
    post = ForumPost.query.get_or_404(post_id)

    if current_user.role != "teacher":
        flash("Only teachers can delete posts.", "danger")
        return redirect(url_for("forum"))

    db.session.delete(post)
    db.session.commit()
    flash("Post deleted!", "success")
    return redirect(url_for("forum"))


# Delete reply (teachers only)
@app.route("/forum/delete_reply/<int:reply_id>", methods=["POST"])
@login_required
def delete_reply(reply_id):
    reply = ForumReply.query.get_or_404(reply_id)
    if current_user.role != "teacher":
        flash("Unauthorized", "danger")
        return redirect(url_for("forum"))

    db.session.delete(reply)
    db.session.commit()
    flash("Reply deleted!", "success")
    return redirect(url_for("forum"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form["role"]
        email_or_id = request.form["email_or_id"]
        password = request.form["password"]

        if role == "teacher":
            user = User.query.filter_by(email=email_or_id, role="teacher").first()
        else:
            user = User.query.filter_by(student_id=email_or_id, role="student").first()

        if not user or not check_password_hash(user.password, password):
            flash("Invalid login", "danger")
            return redirect(url_for("login"))

        login_user(user)
        return redirect(url_for("index"))

    return render_template("login.html")


# ---------- LOGOUT ----------
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

@app.route("/student_dashboard")
@login_required
def student_dashboard():

    # 🔒 Role check
    if current_user.role != "student":
        flash("Unauthorized", "danger")
        return redirect(url_for("index"))

    # 🏫 Classroom check
    classroom = current_user.classroom
    if not classroom:
        return render_template(
            "student_dashboard.html",
            classroom=None,
            student_course_data=[]
        )

    # 📚 Courses assigned to classroom
    courses = classroom.courses

    # ✅ Parts completed by this student
    completed_part_ids = {
        sp.part_id
        for sp in SubmittedPart.query.filter_by(
            student_id=current_user.id
        ).all()
    }

    student_course_data = []

    for course in courses:

        # 📖 Chapters for this course
        chapters = Chapter.query.filter_by(
            course_id=course.id
        ).order_by(Chapter.order).all()

        chapter_data = []

        for chapter in chapters:

            # 🧩 Parts inside this chapter
            parts = Part.query.filter_by(
                chapter_id=chapter.id
            ).all()

            total_parts = len(parts)
            completed_parts = sum(
                1 for p in parts if p.id in completed_part_ids
            )

            chapter_completed = (
                total_parts > 0 and completed_parts == total_parts
            )

            chapter_data.append({
                "id": chapter.id,
                "title": chapter.title,
                "completed": chapter_completed
            })

        student_course_data.append({
            "course": course,
            "chapters": chapter_data
        })

    return render_template(
        "student_dashboard.html",
        classroom=classroom,
        student_course_data=student_course_data
    )



#from openai import OpenAI

#@app.route('/chatgpt_chapter/<int:chapter_id>', methods=['GET', 'POST'])
#@login_required
#def chatgpt_chapter(chapter_id):
    #chapter = Chapter.query.get_or_404(chapter_id)
    #answer = None

    #if request.method == "POST":
        #question = request.form.get("question")

        #if question:
            #response = client.chat.completions.create(
                #model="gpt-4.1-mini",
                #messages=[
                    #{
                        #"role": "system",
                        #"content": (
                            #"You are a tutor. Do NOT give any answers "
                            #"before the student asks a question."
                        #)
                    #},
                    #{"role": "user", "content": question}
                #]
            #)

        #answer = response.choices[0].message.content

    #return render_template(
        #"chatgpt_chapter.html",
        #chapter=chapter,
        #answer=answer
    #)



# ---------- MARK CHAPTER COMPLETE ----------
@app.route("/mark_part_complete/<int:part_id>", methods=["POST"])
@login_required
def mark_part_complete(part_id):
    part = Part.query.get_or_404(part_id)

    # Check if completion already exists
    existing = PartCompletion.query.filter_by(
        user_id=current_user.id,
        part_id=part.id
    ).first()

    if not existing:
        completion = PartCompletion(
            user_id=current_user.id,
            part_id=part.id
        )
        db.session.add(completion)

        # Also add to submitted_parts for progress bar
        if part not in current_user.submitted_parts:
            current_user.submitted_parts.append(part)

        db.session.commit()
        flash(f"Part '{part.title}' marked complete!", "success")
    else:
        flash("Part already marked complete.", "warning")

    return redirect(request.referrer)

# ---------- TEACHER DASHBOARD ----------
@app.route("/teacher_dashboard", methods=["GET", "POST"])
@login_required
def teacher_dashboard():
    # Only teachers allowed
    if current_user.role != "teacher":
        flash("Unauthorized access", "danger")
        return redirect(url_for("index"))

    # Classrooms owned by this teacher
    classrooms = current_user.classrooms  

    # List of available courses to publish
    courses = Course.query.all()

    if request.method == "POST":
        classroom_id = request.form.get("classroom_id")
        course_id = request.form.get("course_id")

        classroom = Classroom.query.get(classroom_id)
        course = Course.query.get(course_id)

        # Validate
        if not classroom or classroom.teacher_id != current_user.id:
            flash("Invalid classroom selection", "danger")
            return redirect(url_for("teacher_dashboard"))

        if not course:
            flash("Invalid course selection", "danger")
            return redirect(url_for("teacher_dashboard"))

        # Publish the course to that classroom
        classroom.course_id = course.id
        db.session.commit()

        flash(f"Course '{course.name}' published to {classroom.name}!", "success")
        return redirect(url_for("teacher_dashboard"))

    return render_template(
        "teacher_dashboard.html",
        classrooms=classrooms,
        courses=courses
    )

@app.route("/chapter/<int:chapter_id>")
@login_required
def chapter_page(chapter_id):
    if current_user.role != "student":
        flash("Unauthorized", "danger")
        return redirect(url_for("index"))

    chapter = Chapter.query.get_or_404(chapter_id)
    
    student = current_user

    # All parts in this chapter
    parts = chapter.parts

    # Parts already completed by this student
    completed_part_ids = [p.id for p in student.submitted_parts if p.chapter_id == chapter_id]

    
    submissions = {
        s.part_id: s
        for s in PartSubmission.query.filter_by(student_id=current_user.id).all()
    }

    # Inject runtime flags into parts
    for part in chapter.parts:
        submission = submissions.get(part.id)

        part.submitted = submission is not None
        part.correct = submission.correct if submission else 0
        part.total = submission.total if submission else 0
        part.completed = part.submitted  # teaching parts can also mark completion

    return render_template(
        "chapter_page.html",
        chapter=chapter,parts=parts,
        completed_part_ids=completed_part_ids
    )

# ---------- CREATE CLASSROOM ----------
@app.route("/create_classroom", methods=["GET", "POST"])
@login_required
def create_classroom():
    if current_user.role != "teacher":
        flash("Unauthorized", "danger")
        return redirect(url_for("index"))
    if request.method == "POST":
        name = request.form["name"]
        course_id = int(request.form["course_id"])
        classroom = Classroom(name=name, teacher_id=current_user.id, course_id=course_id)
        db.session.add(classroom)
        db.session.commit()
        flash("Classroom created!", "success")
        return redirect(url_for("teacher_dashboard"))
    courses = Course.query.all()
    return render_template("create_classroom.html", courses=courses)


@app.route("/assign_course/<int:classroom_id>", methods=["GET", "POST"])
@login_required
def assign_course(classroom_id):
    classroom = Classroom.query.get_or_404(classroom_id)

    # Security check: only teachers assigned to this classroom
    if current_user.role != "teacher" or classroom not in current_user.classrooms:
        flash("Unauthorized", "danger")
        return redirect(url_for("teacher_dashboard"))

    # Only show courses created by this teacher
    courses = Course.query.all()

    
    if request.method == "POST":
        # Get multiple selected course IDs from form
        selected_course_ids = request.form.getlist("course_ids")

        # Clear previous course assignments
        classroom.courses = []

        # Assign selected courses to the classroom
        for cid in selected_course_ids:
            course = Course.query.get(int(cid))
            if course:
                classroom.courses.append(course)

        db.session.commit()
        flash(f"Courses updated for {classroom.name}!", "success")
        return redirect(url_for("teacher_dashboard"))

    return render_template(
        "assign_course.html",
        classroom=classroom,
        courses=courses
    )


# ---------- CALENDAR ----------





from calendar import monthrange
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

@app.route("/calendar", methods=["GET", "POST"])
@login_required
def calendar():
    is_teacher = current_user.role == "teacher"

    # ------------------------------
    # Classroom selection
    # ------------------------------
    if is_teacher:
        classrooms = current_user.classrooms
        classroom_id = request.args.get("classroom_id", type=int)

        if classroom_id:
            classroom = Classroom.query.get_or_404(classroom_id)
            if classroom not in classrooms:
                flash("You do not belong to this classroom.", "danger")
                return redirect(url_for("calendar"))
        else:
            classroom = classrooms[0] if classrooms else None
    else:
        classroom = current_user.classroom
        classrooms = [classroom]

    if classroom is None:
        flash("No classroom found.", "danger")
        return redirect(url_for("teacher_dashboard"))

    # ------------------------------
    # Add event (teacher only)
    # ------------------------------
    if is_teacher and request.method == "POST":
        try:
            title = request.form["title"]
            day = int(request.form["day"])
            time = request.form["time"]

            month = request.args.get("month", datetime.today().month, type=int)
            year = request.args.get("year", datetime.today().year, type=int)
            date = datetime(year, month, day).date()

            event = CalendarEvent(
                title=title,
                date=date,
                time=time,
                classroom_id=classroom.id
            )
            db.session.add(event)
            db.session.commit()

            return redirect(url_for("calendar", classroom_id=classroom.id, month=month, year=year))
        except Exception as e:
            flash("Error adding event: " + str(e), "danger")

    # ------------------------------
    # Calendar display
    # ------------------------------
    today = datetime.today()
    month = request.args.get("month", today.month, type=int)
    year = request.args.get("year", today.year, type=int)

    # Fetch all events for this classroom
    all_events = CalendarEvent.query.filter_by(classroom_id=classroom.id).all()

    events = {}
    for ev in all_events:
        if ev.date.month == month and ev.date.year == year:
            events.setdefault(ev.date.day, []).append(ev)

    # First day of the month (Sunday=0)
    first_day = datetime(year, month, 1)
    start_day_offset = (first_day.weekday() + 1) % 7  # Mon=0 → Sun=0

    # Total days in month
    total_days = monthrange(year, month)[1]

    # Previous / next month
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return render_template(
        "calendar.html",
        events=events,
        month=month,
        year=year,
        classrooms=classrooms,
        current_classroom=classroom,
        is_teacher=is_teacher,
        start_day_offset=start_day_offset,
        total_days=total_days,
        prev_month=prev_month,
        prev_year=prev_year,
        next_month=next_month,
        next_year=next_year
    )




@app.route("/delete_event/<int:event_id>/<int:year>/<int:month>", methods=["POST"])
@login_required
def delete_event(event_id, year, month):

    if current_user.role != "teacher":
        flash("Unauthorized", "danger")
        return redirect(url_for("calendar", year=year, month=month))

    event = CalendarEvent.query.get_or_404(event_id)

    # 🔒 Security + correctness
    if event.classroom not in current_user.classrooms:
        flash("Unauthorized", "danger")
        return redirect(url_for("calendar"))

    db.session.delete(event)
    db.session.commit()

    flash("Event deleted!", "success")

    return redirect(url_for(
        "calendar",
        classroom_id=event.classroom_id,
        year=year,
        month=month
    ))


@app.route("/part/<int:part_id>", methods=["GET", "POST"])
@login_required
def part_page(part_id):
    part = Part.query.get_or_404(part_id)

    # Has student already submitted?
    submission = PartSubmission.query.filter_by(
        student_id=current_user.id,
        part_id=part.id
    ).first()

    if request.method == "POST":
        if submission:
            flash("You have already submitted this part.", "warning")
            return redirect(url_for("part_answers", part_id=part.id))

        questions = part.questions
        correct = 0

        for q in questions:
            ans = request.form.get(f"q_{q.id}", "").strip().lower()
            if ans == q.correct_answer.lower():
                correct += 1

        submission = PartSubmission(
            student_id=current_user.id,
            part_id=part.id,
            correct=correct,
            total=len(questions)
        )

        db.session.add(submission)
        db.session.commit()

        flash("Answers submitted successfully!", "success")
        return redirect(url_for("part_answers", part_id=part.id))

    return render_template(
        "part.html",
        part=part,
        submission=submission
    )



@app.route("/part/<int:part_id>/answers")
@login_required
def part_answers(part_id):
    part = Part.query.get_or_404(part_id)

    submission = PartSubmission.query.filter_by(
        student_id=current_user.id,
        part_id=part.id
    ).first()

    # 🚫 HARD BLOCK
    if not submission:
        flash("You must submit the questions before viewing answers.", "danger")
        return redirect(url_for("part_page", part_id=part.id))

    return render_template(
        "part_answers.html",
        part=part,
        submission=submission
    )





# ---------- INITIALIZE DB ----------
with app.app_context():
    #db.drop_all()
    db.create_all()
    # Add default courses if not exist
    
    course1 = Course(name="Integration Course")
    course2 = Course(name="Course 2(no content)")
    db.session.add_all([course1, course2])
    db.session.commit()

    chapter1 = Chapter(
        title="Basic Antiderivatives",
        order=1,
        course_id=course1.id
    )
    db.session.add(chapter1)
    db.session.commit()

    # ---------- PART 1 (TEACHING) ----------
    part1 = Part(
        chapter_id=chapter1.id,
        title="Basic Properties of Integration",
        type="teaching",
        lesson_video="zcL4G3SN_hU"
    )
    db.session.add(part1)
    db.session.commit()

    # Lesson notes (PDF)
    note1 = LessonNote(
        part_id=part1.id,
        pdf_url="notes/Lesson 1 Notes.pdf"
    )
    db.session.add(note1)

    
    part2 = Part(
        chapter_id=chapter1.id,
        title="Integrals of Simple Functions",
        type="teaching",
        lesson_video="c5No6tp_UL4"
    )
    db.session.add(part2)
    db.session.commit()


    # Lesson notes for answers
    note2 = LessonNote(
        part_id=part2.id,
        pdf_url="notes/Lesson 2 Notes.pdf"
    )
    db.session.add(note2)

    part3 = Part(
        chapter_id=chapter1.id,
        title="Integrating Common Functions",
        type="teaching",
        lesson_video="vwhcLpfkeu4"
    )
    db.session.add(part3)
    db.session.commit()

    note3 = LessonNote(
        part_id=part3.id,
        pdf_url="notes/Lesson 3 Notes.pdf"
    )
    db.session.add(note3)
    
    part4 = Part(
        chapter_id=chapter1.id,
        title="Practice Exercises I",
        type="exercise",
        lesson_video="MNwCsN79mcQ"
    )
    db.session.add(part4)
    db.session.commit()

    note4 = LessonNote(
        part_id=part4.id,
        pdf_url="notes/Lesson 4 Notes.pdf"
    )
    db.session.add(note4)
    part5 = Part(
        chapter_id=chapter1.id,
        title="Practice Exercises II",
        type="exercise",
        lesson_video="oYsvq5Q_SYY"
    )
    db.session.add(part5)
    db.session.commit()

    note5 = LessonNote(
        part_id=part5.id,
        pdf_url="notes/Lesson 5 Notes.pdf"
    )
    db.session.add(note5)
    
    part6 = Part(
        chapter_id=chapter1.id,
        title="Practice Exercises III",
        type="exercise",
        lesson_video="1M6nXAbVgn8"
    )
    db.session.add(part6)
    db.session.commit()

    note6 = LessonNote(
        part_id=part6.id,
        pdf_url="notes/Lesson 6 Notes.pdf"
    )
    db.session.add(note6)
    chapter2 = Chapter(
        title="Integration By Substitutions",
        order=2,
        course_id=course1.id
    )
    db.session.add(chapter2)
    db.session.commit()
    part7 = Part(
        chapter_id=chapter2.id,
        title="Introduction to U-Substitution",
        type="teaching",
        lesson_video="cSCaF8cgE9A"
    )
    db.session.add(part7)
    db.session.commit()

    note7 = LessonNote(
        part_id=part7.id,
        pdf_url="notes/Lesson 7 Notes.pdf"
    )
    db.session.add(note7)
    part8 = Part(
        chapter_id=chapter2.id,
        title="Practice Exercises IV",
        type="exercise",
        lesson_video="W6k9WXdTzOE"
    )
    db.session.add(part8)
    db.session.commit()

    note8 = LessonNote(
        part_id=part8.id,
        pdf_url="notes/Lesson 8 Notes.pdf"
    )
    db.session.add(note8)
    part9 = Part(
        chapter_id=chapter2.id,
        title="Practice Exercises V",
        type="exercise",
        lesson_video="B9jJnbU00i4"
    )
    db.session.add(part9)
    db.session.commit()

    note9 = LessonNote(
        part_id=part9.id,
        pdf_url="notes/Lesson 9 Notes.pdf"
    )
    db.session.add(note9)
    part10 = Part(
        chapter_id=chapter2.id,
        title="Practice Exercises VI",
        type="exercise",
        lesson_video="BaHFyceu9Eo"
    )
    db.session.add(part10)
    db.session.commit()

    note10 = LessonNote(
        part_id=part10.id,
        pdf_url="notes/Lesson 10 Notes.pdf"
    )
    db.session.add(note10)
    chapter3 = Chapter(
        title="Special Substitution",
        order=3,
        course_id=course1.id
    )
    db.session.add(chapter3)
    db.session.commit()
    part11 = Part(
        chapter_id=chapter3.id,
        title="Introduction to Trigonometric Substitutions",
        type="teaching",
        lesson_video="UNMoskoJq8"
    )
    db.session.add(part11)
    db.session.commit()

    note11 = LessonNote(
        part_id=part11.id,
        pdf_url="notes/Lesson 11 Notes.pdf"
    )
    db.session.add(note11)
    part12 = Part(
        chapter_id=chapter3.id,
        title="Domain of Trigonometric Substitutions",
        type="teaching",
        lesson_video="4F7pv-05aI"
    )
    db.session.add(part12)
    db.session.commit()

    note12 = LessonNote(
        part_id=part12.id,
        pdf_url="notes/Lesson 12 Notes.pdf"
    )
    db.session.add(note12)
    part13 = Part(
        chapter_id=chapter3.id,
        title="Introduction to t-substitutions",
        type="teaching",
        lesson_video="gXoAY_a-dWM"
    )
    db.session.add(part13)
    db.session.commit()

    note13 = LessonNote(
        part_id=part13.id,
        pdf_url="notes/Lesson 13 Notes.pdf"
    )
    db.session.add(note13)
    part14 = Part(
        chapter_id=chapter3.id,
        title="Applications of t-substitutions",
        type="teaching",
        lesson_video="tDFmXA4OIrI"
    )
    db.session.add(part14)
    db.session.commit()

    note14 = LessonNote(
        part_id=part14.id,
        pdf_url="notes/Lesson 14 Notes.pdf"
    )
    db.session.add(note14)
    part15 = Part(
        chapter_id=chapter3.id,
        title="Practice Exercises VII",
        type="exercise",
        lesson_video="5Uj_LOZ7V3I"
    )
    db.session.add(part15)
    db.session.commit()

    note15 = LessonNote(
        part_id=part15.id,
        pdf_url="notes/Lesson 15 Notes.pdf"
    )
    db.session.add(note15)
    part16 = Part(
        chapter_id=chapter3.id,
        title="Practice Exercises VIII",
        type="exercise",
        lesson_video="-vOZ10AJTvI"
    )
    db.session.add(part16)
    db.session.commit()

    note16 = LessonNote(
        part_id=part16.id,
        pdf_url="notes/Lesson 16 Notes.pdf"
    )
    db.session.add(note16)
    part17 = Part(
        chapter_id=chapter3.id,
        title="Practice Exercises IX",
        type="exercise",
        lesson_video="Jd8FGbZEX10"
    )
    db.session.add(part17)
    db.session.commit()

    note17 = LessonNote(
        part_id=part17.id,
        pdf_url="notes/Lesson 17 Notes.pdf"
    )
    db.session.add(note17)
    chapter4 = Chapter(
        title="Integration By Parts",
        order=4,
        course_id=course1.id
    )
    db.session.add(chapter4)
    db.session.commit()
    part18 = Part(
        chapter_id=chapter4.id,
        title="Introduction to Integration by Parts",
        type="teaching",
        lesson_video="oeR1wcSe4vc"
    )
    db.session.add(part18)
    db.session.commit()

    note18 = LessonNote(
        part_id=part18.id,
        pdf_url="notes/Lesson 18 Notes.pdf"
    )
    db.session.add(note18)
    part19 = Part(
        chapter_id=chapter4.id,
        title="Practice Exercises X",
        type="exercise",
        lesson_video="FNULURSvhJo"
    )
    db.session.add(part19)
    db.session.commit()

    note19 = LessonNote(
        part_id=part19.id,
        pdf_url="notes/Lesson 6 Notes.pdf"
    )
    db.session.add(note19)
    part20 = Part(
        chapter_id=chapter4.id,
        title="Practice Exercises XI",
        type="exercise",
        lesson_video="-etd88Nmu1k"
    )
    db.session.add(part20)
    db.session.commit()

    note20 = LessonNote(
        part_id=part20.id,
        pdf_url="notes/Lesson 20 Notes.pdf"
    )
    db.session.add(note20)
    part21 = Part(
        chapter_id=chapter4.id,
        title="Reduction Formulae",
        type="teaching",
        lesson_video="8E9x53dbOhM"
    )
    db.session.add(part21)
    db.session.commit()

    note21 = LessonNote(
        part_id=part21.id,
        pdf_url="notes/Lesson 21 Notes.pdf"
    )
    db.session.add(note21)
    part22 = Part(
        chapter_id=chapter4.id,
        title="Unusual Application of Integration by Parts",
        type="teaching",
        lesson_video="49f6GU_Qxc0")
    db.session.add(part22)
    db.session.commit()

    note22 = LessonNote(
        part_id=part22.id,
        pdf_url="notes/Lesson 22 Notes.pdf"
    )
    db.session.add(note22)
    chapter5 = Chapter(
        title="Final Practice",
        order=5,
        course_id=course1.id
    )
    db.session.add(chapter5)
    db.session.commit()
    part23 = Part(
        chapter_id=chapter5.id,
        title="Final Review",
        type="exercise",
        lesson_video=None
    )
    db.session.add(part23)
    db.session.commit()
    

    q1 = Question(part_id=part4.id, question_text="What is ∫ (x + 2) dx?", option_a="x^2 + 2x + C", option_b="0.5x^2 + 2x + C", option_c="x^2 + C", option_d="0.5x^2 + C", correct_answer="B")
    q2 = Question(part_id=part4.id, question_text="What is ∫ (3x^2 + 4x) dx?", option_a="x^3 + 2x^2 + C", option_b="x^3 + 4x + C", option_c="3x^3 + 2x^2 + C", option_d="x^2 + 4x + C", correct_answer="A")
    q3 = Question(part_id=part4.id, question_text="What is ∫ (x + 1)^6 dx?", option_a="(x + 1)^6 + C", option_b="(x + 1)^7 + C", option_c="(1/7)(x + 1)^7 + C", option_d="6(x + 1)^5 + C", correct_answer="C")
    q4 = Question(part_id=part4.id, question_text="What is ∫ [(x - 1)^3 - (2x - 1)^3] dx?", option_a="(1/4)(x - 1)^4 - (1/4)(2x - 1)^4 + C", option_b="(1/4)(x - 1)^4 - (1/8)(2x - 1)^4 + C", option_c="(x - 1)^4 - (2x - 1)^4 + C", option_d="(1/4)(x - 1)^4 - (2x - 1)^4 + C", correct_answer="B")
    q5 = Question(part_id=part4.id, question_text="What is ∫ e^(4x + 3) dx?", option_a="e^(4x + 3) + C", option_b="4e^(4x + 3) + C", option_c="(1/4)e^(4x + 3) + C", option_d="e^(x + 3) + C", correct_answer="C")
    q6 = Question(part_id=part4.id, question_text="What is ∫ (4 + e^(-x/2 + 1)) dx?", option_a="4x - 2e^(-x/2 + 1) + C", option_b="4x + 2e^(-x/2 + 1) + C", option_c="4 + e^(-x/2 + 1) + C", option_d="4x - e^(-x/2 + 1) + C", correct_answer="A")
    q7 = Question(part_id=part4.id, question_text="What is ∫ 1 / (3x + 2) dx?", option_a="ln|3x + 2| + C", option_b="(1/3)ln|3x + 2| + C", option_c="3ln|3x + 2| + C", option_d="ln|x + 2| + C", correct_answer="B")
    q8 = Question(part_id=part4.id, question_text="What is ∫ (x^3 - 1)/(x - 1)^2 dx, given x > 1?", option_a="x + 1 + C", option_b="x^2 + C", option_c="0.5x^2 + 2x + 3ln|x - 1| + C", option_d="x - 1 + C", correct_answer="C")
    q9 = Question(part_id=part4.id, question_text="What is ∫ (x^2 + 3x + 2)/(x + 1) dx, given x > 0?", option_a="0.5x^2 + 2x + C", option_b="x^2 + x + C", option_c="x + ln|x + 1| + C", option_d="x^2 + 2 + C", correct_answer="A")
    q10 = Question(part_id=part4.id, question_text="What is ∫ 1 / (x^2 - 5x + 6) dx, given x < 0?", option_a="ln|x - 2| - ln|x - 3| + C", option_b="ln|x - 3| - ln|x - 2| + C", option_c="1/(x - 2) + C", option_d="1/(x - 3) + C", correct_answer="B")


    q11 = Question(part_id=part5.id, question_text="Evaluate ∫ (sin(3x + 6) - 4cos x) dx", option_a="(1/3)cos(3x+6) - 4sin x + C", option_b="-(1/3)cos(3x+6) - 4sin x + C", option_c="(1/3)sin(3x+6) - 4cos x + C", option_d="-(1/3)sin(3x+6) + 4cos x + C", correct_answer="B")
    q12 = Question(part_id=part5.id, question_text="Evaluate ∫ cos²x dx", option_a="sin x + C", option_b="tan x + C", option_c="(x/2) + (sin 2x)/4 + C", option_d="cos x + C", correct_answer="C")
    q13 = Question(part_id=part5.id, question_text="Evaluate ∫ sin x sin 3x dx", option_a="(1/4)cos 2x - (1/8)cos 4x + C", option_b="(1/2)sin 2x + C", option_c="(1/4)sin 2x - (1/8)sin 4x + C", option_d="-(1/4)sin 2x + (1/8)sin 4x + C", correct_answer="C")
    q14 = Question(part_id=part5.id, question_text="Evaluate ∫ sin³x dx", option_a="(1/3)cos³x - cos x + C", option_b="-(3/4)cos x + (1/12)cos 3x + C", option_c="(3/4)sin x + (1/12)sin 3x + C", option_d="-(3/4)sin x + (1/12)sin 3x + C", correct_answer="A")
    q15 = Question(part_id=part5.id, question_text="Evaluate ∫ (1 + tan²x) dx", option_a="sec x + C", option_b="-tan x + C", option_c="cot x + C", option_d="tan x + C", correct_answer="D")
    q16 = Question(part_id=part5.id, question_text="Evaluate ∫ tan²(-x + 2) dx", option_a="tan(-x+2) + x + C", option_b="-tan(-x+2) - x + C", option_c="tan(x-2) - x + C", option_d="tan(x-2) + C", correct_answer="C")


    q17 = Question(part_id=part6.id, question_text="Evaluate ∫ 1/√(3-x²) dx", option_a="arccos(x/√3)+C", option_b="ln|x|+C", option_c="√(3-x²)+C", option_d="arcsin(x/√3)+C", correct_answer="D")
    q18 = Question(part_id=part6.id, question_text="Evaluate ∫ 1/√(3-(x+2)²) dx", option_a="arcsin((x+2)/√3) + C", option_b="sec⁻¹x + C", option_c="2arcsin(√(x+2)/√3) + C", option_d="arcsin x + C", correct_answer="A")
    q19 = Question(part_id=part6.id, question_text="Evaluate ∫ 1/(x²+9x+13) dx", option_a="arctan x + C", option_b="(1/√29) ln|(2x+9-√29)/(2x+9+√29)|+C", option_c="ln|x²+9x+13|+C", option_d="x/(x²+9x+13)+C", correct_answer="B")
    q20 = Question(part_id=part6.id, question_text="Evaluate ∫ (x^3+x^2-5x+15)/(x^2+4x+7) dx", option_a="x^2 + C", option_b="0.5x^2 - 3x + (3/4)ln|x^2+4x+7| + (2/√3)arctan((x+2)/√3) + C", option_c="ln|x| + C", option_d="arctan x + C", correct_answer="B")


    q21 = Question(part_id=part8.id, question_text="Evaluate ∫ 1/(x ln x) dx, x>0", option_a="1/ln x + C", option_b="ln x + C", option_c="x ln x + C", option_d="ln|ln x| + C", correct_answer="D")
    q22 = Question(part_id=part8.id, question_text="Evaluate ∫ 2x/√(x²+1) dx", option_a="√(x²+1) + C", option_b="arcsin x + C", option_c="2√(x²+1) + C", option_d="ln|x²+1| + C", correct_answer="C")
    q23 = Question(part_id=part8.id, question_text="Evaluate ∫ 3x²/((x³+3)√(x³+3)) dx", option_a="ln|x³+3| + C", option_b="1/(x³+3) + C", option_c="√(x³+3) + C", option_d="-2/√(x³+3) + C", correct_answer="D")
    q24 = Question(part_id=part8.id, question_text="Evaluate ∫ (x+3)²/(x²+4) dx", option_a="tan⁻¹(x/2) + C", option_b="x + C", option_c="x + 3ln|x²+4| + (5/2)arctan(x/2) + C", option_d="ln|x²+4| + C", correct_answer="C")
    q25 = Question(part_id=part8.id, question_text="Evaluate ∫ x√(x-2) dx", option_a="ln|x-2| + C", option_b="(x-2)^(3/2) + C", option_c="x²/√(x-2) + C", option_d="2√(x-2)*(x²/5 - 2x/15 - 8/15) + C", correct_answer="D")


    q26 = Question(part_id=part9.id, question_text="∫ tan x dx", option_a="ln|sin x| + C", option_b="-ln|cos x| + C", option_c="ln|cos x| + C", option_d="ln|sec x| + C", correct_answer="B")
    q27 = Question(part_id=part9.id, question_text="∫ 2cot x dx", option_a="2 ln|sin x| + C", option_b="2 tan x + C", option_c="-2 cot x + C", option_d="-2 tan x + C", correct_answer="A")
    q28 = Question(part_id=part9.id, question_text="∫ (sec^2 x + sec x tan x) dx", option_a="tan x + sec x + C", option_b="x + cot x + C", option_c="tan x - x + C", option_d="x - tan x + C", correct_answer="A")
    q29 = Question(part_id=part10.id, question_text="∫ (cos^4 x sin x) dx", option_a="-1/5 cos^5 x + C", option_b="sin x - (2/3)sin³x - (1/5)sin⁵x + C", option_c="sin x + (2/3)sin³x + (1/5)sin⁵x + C", option_d="1/5 sin^5 x + C", correct_answer="A")
    q30 = Question(part_id=part10.id, question_text="∫ sec x dx", option_a="ln|sec x + tan x| + C", option_b="ln|sec x - tan x| + C", option_c="ln|cos x| + C", option_d="ln|sin x| + C", correct_answer="A")


    q31 = Question(part_id=part15.id, question_text="∫ 1 / (x^2√(x² - 4)) dx", option_a="√(x² - 4) / (4x) + C", option_b="√(x² - 4) / x + C", option_c="x / √(x² - 4) + C", option_d="1 / (2√(x² - 4)) + C", correct_answer="A")
    q32 = Question(part_id=part15.id, question_text="∫ √(4x - x²) dx", option_a="2 arcsin((x-2)/2) + (x-2)√(4x-x²)/2 + C", option_b="2 arcsin((x-2)/2) + √(4x-x²) + C", option_c="arcsin(x-2) + (x-2)√(4x-x²) + C", option_d="2 arcsin((x-2)/2) + (x-2)√(4x-x²) + C", correct_answer="A")
    q33 = Question(part_id=part16.id, question_text="∫ (x - 2) / (x² - 2x + 2)^2 dx", option_a="(x-3)/(2(x²-2x+2)) + 1.5arctan(x-1) + C", option_b="arctan(x-1) + C", option_c="(1/2)arctan(x-1) + C", option_d="(x-1)/(x²-2x+2) + C", correct_answer="A")
    q34 = Question(part_id=part17.id, question_text="∫ 1 / (2 + cos x) dx", option_a="(2/√3) arctan(tan(x/2)/√3) + C", option_b="(2/√3) arctan(√3 tan(x/2) + 1) + C", option_c="(1/√3) arctan(√3 tan(x/2)) + C", option_d="arctan(tan(x/2)) + C", correct_answer="A")
    q35 = Question(part_id=part17.id, question_text="∫ 1 / (2 sin x - cos x + 5) dx", option_a="1/5 ln|(3 tan(x/2) - 1)/(tan(x/2) + 3)| + C", option_b="0.2ln|(2tan(x/2)+1)| - 0.2ln|(tan(x/2)-2)| + C", option_c="ln |3 sin x + 4 cos x| + C", option_d="arctan(tan(x/2)) + C", correct_answer="B")

    q36 = Question(part_id=part19.id, question_text="∫ x sin x dx", option_a="-x cos x + sin x + C", option_b="x cos x - sin x + C", option_c="-x cos x - sin x + C", option_d="x cos x + sin x + C", correct_answer="A")
    q37 = Question(part_id=part19.id, question_text="∫ e^x sin(2x) dx", option_a="e^x (sin 2x - 2 cos 2x)/5 + C", option_b="e^x (sin 2x - cos 2x)/2 + C", option_c="e^x (sin 2x + 2 cos 2x)/5 + C", option_d="e^x (sin 2x - 2 cos 2x)/4 + C", correct_answer="A")
    q38 = Question(part_id=part19.id, question_text="∫ x (ln x)² dx", option_a="(x²/2)(ln x)² - (x²/2)ln x + x²/4 + C", option_b="(x²/2)(ln x)² - x² ln x + x²/2 + C", option_c="(x²/2)(ln x)² - (x²/4)ln x + x²/8 + C", option_d="(x²/2)(ln x)² - (x²/2)ln x + x²/2 + C", correct_answer="A")
    q39 = Question(part_id=part19.id, question_text="∫ arctan x dx", option_a="x arctan x - (1/2) ln|1 + x²| + C", option_b="x arctan x + (1/2) ln|1 + x²| + C", option_c="x arctan x - ln|1 + x²| + C", option_d="arctan x + x/(1 + x²) + C", correct_answer="A")
    q40 = Question(part_id=part20.id, question_text="∫ x¹⁰ e^x dx", option_a="e^x (x¹⁰ - 10x⁹ + 90x⁸ - 720x⁷ + 5040x⁶ - 30240x⁵ + 151200x⁴ - 604800x³ + 1814400x² - 3628800x + 3628800) + C", option_b="e^x (x¹⁰ + ... + 3628800) + C", option_c="Polynomial * e^x", option_d="None of the above", correct_answer="A")

    q41 = Question(part_id=part23.id, question_text="∫ (x^3 + 1)^3 * x^2 dx", option_a="(1/12)(x^3 + 1)^4 + C", option_b="(1/3)(x^3 + 1)^4 + C", option_c="(x^3 + 1)^4 / 4 + C", option_d="None", correct_answer="A")
    q42 = Question(part_id=part23.id, question_text="∫ sin x / (sin x + cos x) dx", option_a="0.5(x - ln|sin x + cos x|) + C", option_b="0.5(x + ln|sin x + cos x|) + C", option_c="x - ln|sin x + cos x| + C", option_d="0.5 ln|sin x + cos x| + C", correct_answer="A")
    q43 = Question(part_id=part23.id, question_text="∫ 1 / (1 + x^(1/3)) dx", option_a="1.5x^(2/3) - 3x^(1/3) + 3ln|1+x^(1/3)| + C", option_b="3x^(1/3) - 3ln|1+x^(1/3)| + C", option_c="3x^(2/3)/2 - 3x^(1/3) + 3ln|1+x^(1/3)| + C", option_d="None", correct_answer="C")
    q44 = Question(part_id=part23.id, question_text="∫ 1 / (x(x⁶ + 1)) dx", option_a="ln|x| - (1/6) ln|x⁶ + 1| + C", option_b="ln|x| + (1/6) ln|x⁶ + 1| + C", option_c="(1/6) ln|x⁶ / (x⁶ + 1)| + C", option_d="None", correct_answer="A")
    q45 = Question(part_id=part23.id, question_text="∫ (3e^{3x} + 2x) / (e^{3x} + x^2) dx", option_a="ln|e^{3x} + x^2| + C", option_b="ln|e^{3x} + x^2| - 3x + C", option_c="ln|e^{3x} + x^2| + C", option_d="None", correct_answer="A")
    q46 = Question(part_id=part23.id, question_text="∫ (tan x)^(1/3) dx", option_a="Complex result involving ln and arctan", option_b="No simple form", option_c="Standard power rule", option_d="D", correct_answer="A")
    q47 = Question(part_id=part23.id, question_text="∫ (arcsin x)² dx", option_a="x(arcsin x)² + 2√(1-x²) arcsin x - 2x + C", option_b="x(arcsin x)² - 2√(1-x²) arcsin x + 2x + C", option_c="x(arcsin x)² + 2√(1-x²) arcsin x + 2x + C", option_d="None", correct_answer="A")
    q48 = Question(part_id=part23.id, question_text="∫ x csc x cot x dx", option_a="-x csc x - ln|csc x + cot x| + C", option_b="-x csc x + ln|csc x + cot x| + C", option_c="x csc x - ln|csc x + cot x| + C", option_d="None", correct_answer="A")
    q49 = Question(part_id=part23.id, question_text="∫ x⁸ sin x dx", option_a="(-x⁸ + 56x⁶ - 1680x⁴ + 20160x² - 40320) cos x + (8x⁷ - 336x⁵ + 6720x³ - 40320x) sin x + C", option_b="Correct Expansion result", option_c="None", option_d="A", correct_answer="A")
    q50 = Question(part_id=part23.id, question_text="∫ f'(x)/f(x) form questions", option_a="ln|f(x)| + C", option_b="0.5ln|e^{-2x} + cos 2x| + ln|x| + C", option_c="ln|e^{-2x} + cos 2x| + C", option_d="B", correct_answer="B")

    db.session.add_all([q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, q11, q12, q13, q14, q15, q16, q17, q18, q19, q20, q21, q22, q23, q24, q25, q26, q27, q28, q29, q30, q31, q32, q33, q34, q35, q36, q37, q38, q39, q40, q41, q42, q43, q44, q45, q46, q47, q48, q49, q50])
    db.session.commit()
    

# ---------- RUN APP ----------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
