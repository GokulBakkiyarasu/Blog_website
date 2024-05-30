from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, ForeignKey
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
# Import your forms from the forms.py
from forms import CreateForm, RegisterForm, LoginForm, CommentForm
from smtplib import SMTP
import os


def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.id != 1:
            return abort(403)
        return f(*args, **kwargs)

    return decorated_function


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
Bootstrap5(app)
ckeditor = CKEditor(app)


# CREATE DATABASE
class Base(DeclarativeBase):
    pass


login_manager = LoginManager()
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DB_URI", "sqlite:///posts.db")
db = SQLAlchemy(model_class=Base)
db.init_app(app)
login_manager.init_app(app)


gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)


@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(UserDetail, user_id)


# TODO: Create a User table for all your registered users.
class UserDetail(UserMixin, db.Model):
    __tablename__ = "user_data"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(250), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    post = relationship("BlogPost", back_populates="author")
    comments = relationship("Comment", back_populates="author")


class BlogPost(db.Model):
    __tablename__ = "blog_post"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # author: Mapped[str] = mapped_column(String(250), nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_data.id"))
    author = relationship("UserDetail", back_populates="post")
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    comments = relationship("Comment", back_populates="parent_post")


class Comment(db.Model):
    __tablename__ = "comment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_data.id"))
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("blog_post.id"))
    text: Mapped[str] = mapped_column(String(250), nullable=False)
    author = relationship("UserDetail", back_populates="comments")
    parent_post = relationship("BlogPost", back_populates="comments")


with app.app_context():
    db.create_all()


# TODO: Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register', methods=["POST", "GET"])
def register():
    register_form = RegisterForm()
    if register_form.validate_on_submit():
        user = db.session.execute(db.select(UserDetail).where(UserDetail.email == register_form.email.data)).scalar()
        if user is None:
            hashed_and_salted_pass = generate_password_hash(password=register_form.password.data,
                                                            method="pbkdf2:sha256",
                                                            salt_length=8)
            new_user = UserDetail(email=register_form.email.data,
                                  password=hashed_and_salted_pass,
                                  name=register_form.name.data.title())
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            return redirect("/")
        else:
            flash("Email already registered, Try logging in instead.")
            return redirect("/login")
    return render_template("register.html", form=register_form)


# TODO: Retrieve a user from the database based on their email.
@app.route('/login', methods=["POST", "GET"])
def login():
    login_form = LoginForm()
    if login_form.validate_on_submit():
        user = db.session.execute(db.select(UserDetail).where(UserDetail.email == login_form.email.data)).scalar()
        if user is not None:
            if check_password_hash(password=login_form.password.data, pwhash=user.password):
                login_user(user)
                return redirect("/")
            else:
                flash("Incorrect Password, Please try again.")
        else:
            flash("The email is not registered, please register to create an account.")
    return render_template("login.html", form=login_form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    posts = db.session.execute(db.select(BlogPost)).scalars().all()
    back_img = "static/assets/img/home-bg.jpeg"
    return render_template("index.html", all_blogs=posts, background_img=back_img)


@app.route('/post/<int:post_id>', methods=["POST", "GET"])
def show_post(post_id):
    # TODO: Retrieve a BlogPost from the database based on the post_id
    comment_form = CommentForm()
    requested_post = db.session.execute(db.select(BlogPost).where(BlogPost.id == post_id)).scalar()
    comments_for_that_post = db.session.execute(db.select(Comment).where(Comment.post_id == requested_post.id)).scalars().all()
    if comment_form.validate_on_submit():
        if current_user.is_authenticated:
            new_comment = Comment(text=comment_form.comment.data, author=current_user, parent_post=requested_post)
            db.session.add(new_comment)
            db.session.commit()
        else:
            flash("You need to Login or Register to comment.")
            return redirect("/login")
    return render_template("post.html", blog=requested_post, form=comment_form, comments=comments_for_that_post)


# TODO: add_new_post() to create a new blog post
@app.route("/new-post", methods=["POST", "GET"])
@admin_only
def add_new_post():
    back_img = "static/assets/img/add-bg.jpeg"
    create_form = CreateForm()
    if create_form.validate_on_submit():
        new_post = BlogPost(title=create_form.title.data,
                            subtitle=create_form.subtitle.data,
                            date=date.today().strftime("%B %d, %Y"),
                            body=create_form.body.data,
                            author=current_user,
                            img_url=create_form.img_url.data)
        db.session.add(new_post)
        db.session.commit()
        return redirect("/")
    return render_template("make-post.html", create_form=create_form, background_img=back_img)


# TODO: edit_post() to change an existing blog post
@app.route("/edit-post", methods=["GET", "POST"])
@admin_only
def edit_post():
    back_img = "static/assets/img/edit-bg.jpeg"
    blog_id = request.args.get("blog_id")
    post = db.session.execute(db.select(BlogPost).where(BlogPost.id == blog_id)).scalar()
    edit_form = CreateForm(title=post.title,
                           subtitle=post.subtitle,
                           date=post.date,
                           body=post.body,
                           author=post.author,
                           img_url=post.img_url)
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect("/")
    return render_template("make-post.html", create_form=edit_form, is_edit=True, background_img=back_img)


# TODO: delete_post() to remove a blog post from the database
@app.route("/delete/<int:post_id>")
@admin_only
def delete(post_id):
    post = db.session.execute(db.select(BlogPost).where(BlogPost.id == post_id)).scalar()
    db.session.delete(post)
    db.session.commit()
    return redirect("/")


@app.route("/contact", methods=["POST", "GET"])
def contact_page():
    back_img = "static/assets/img/contact-bg.jpeg"
    if request.method == "POST":
        sender_email = os.environ.get("MAIL")
        passkey = os.environ.get("PASSKEY")
        receiver_email = "gokulbakkiyarasu@gmail.com"
        sent_message = f"subject:Blog's Contact Mail\n{request.form['name']}\n{request.form['email']}\n{request.form['phone']}\n{request.form['message']}"
        print(sent_message)
        with SMTP("smtp.gmail.com") as connection:
            connection.starttls()
            connection.login(user=sender_email, password=passkey)
            connection.sendmail(from_addr=sender_email,
                                to_addrs=receiver_email,
                                msg=sent_message)
    return render_template("contact.html", method=request.method, background_img=back_img)


@app.route("/about")
def about_page():
    back_img = "static/assets/img/about-bg.jpeg"
    return render_template("about.html", background_img=back_img)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
