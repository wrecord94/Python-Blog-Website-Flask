from dotenv.main import load_dotenv
import os
from datetime import date
from functools import wraps

from flask import Flask, abort, render_template, redirect, url_for, flash
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
# from flask_gravatar import Gravatar

from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import Mapped, relationship
from werkzeug.security import generate_password_hash, check_password_hash
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm

app = Flask(__name__)
load_dotenv()
app.config['SECRET_KEY'] = os.environ['SUPER_SECRET_KEY']
ckeditor = CKEditor(app)
Bootstrap5(app)
# # For adding profile images to the comment section
# gravatar = Gravatar(app, default='retro')

# TODO: Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

# CONNECT TO DB
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DB_LOCATION']
db = SQLAlchemy()
db.init_app(app)


# CONFIGURE TABLES
class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(250), nullable=False)
    email = db.Column(db.String(250), unique=True, nullable=False)
    password = db.Column(db.String(250), nullable=False)
    # RELATIONAL DB WORK
    # 1. One author to many blog-posts
    posts: Mapped[list["BlogPost"]] = relationship(back_populates="author")
    # 2. One user to many Comment objects
    comments: Mapped[list["Comment"]] = relationship(back_populates="author")


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(250), unique=True, nullable=False)
    subtitle = db.Column(db.String(250), nullable=False)
    date = db.Column(db.String(250), nullable=False)
    body = db.Column(db.Text, nullable=False)
    img_url = db.Column(db.String(250), nullable=False)
    # RELATIONAL DB WORK
    # 1. One author to many blog-posts
    author_id: Mapped[int] = db.Column(db.ForeignKey("user.id"))
    author: Mapped["User"] = relationship(back_populates="posts")
    # 3. One blog_post to many comments
    comments: Mapped[list["Comment"]] = relationship(back_populates="blogpost")


class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    comment_text = db.Column(db.String(250), nullable=False)
    # RELATIONAL DB WORK
    # 2. One user to many Comment objects
    author_id: Mapped[int] = db.Column(db.Integer, db.ForeignKey('user.id'))
    author: Mapped["User"] = relationship(back_populates="comments")
    # 3. One blog_post to many comments
    blogpost_id = db.Column(db.ForeignKey('blog_posts.id'))
    blogpost = db.relationship("BlogPost", back_populates="comments")


with app.app_context():
    db.create_all()


# Create a user-loader callback
@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)


def admin_required(func):
    """Function to manage the admin access to the restricted areas of the website."""

    @wraps(func)
    def decorated_function(*args, **kwargs):
        # If id is not 1 then return abort with 403 error
        if current_user.id != 1 or not current_user.is_authenticated:
            return abort(403)
        # Otherwise continue with the route function
        return func(*args, **kwargs)

    return decorated_function


@app.route('/register', methods=["GET", "POST"])
def register():
    # If already logged in redirect to home
    if current_user.is_authenticated:
        return redirect(url_for('get_all_posts'))
    # Set our form instance
    form = RegisterForm()
    # If form is complete
    if form.validate_on_submit():
        # Check if user is already registered
        user_found = db.session.execute(db.select(User).where(User.email == form.email.data))
        user = user_found.scalar()
        if user:
            # user already exists
            flash("User already exists - please sign in.")
            return redirect(url_for('login'))
        # Hash our password from the form before we store it
        hashed_password = generate_password_hash(password=form.password.data,
                                                 method='pbkdf2:sha256',
                                                 salt_length=8)
        # Make a new User instance
        new_user = User(name=form.name.data,
                        email=form.email.data,
                        password=hashed_password)

        # Make changes to our DB
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('get_all_posts'))
    return render_template("register.html", form=form)


@app.route('/login', methods=["GET", "POST"])
def login():
    # If already logged in redirect to home
    if current_user.is_authenticated:
        return redirect(url_for('get_all_posts'))
    # Make an instance of our login form class
    form = LoginForm()
    # If form completed we want to actually log the user in
    if form.validate_on_submit():
        # Extract values for 'email' and 'password'
        form_password = form.password.data
        form_email = form.email.data
        # Check email is in system
        user_found = db.session.execute(db.select(User).where(User.email == form_email)).scalar()
        # If no user found bounce them back to login page and flash up a message
        if user_found and check_password_hash(user_found.password, form_password):
            login_user(user_found)
            return redirect(url_for('get_all_posts'))
        else:
            flash("... Can't log you in sorry babes.", category='warning')

    return render_template("login.html", form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts)


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    # Add the CommentForm to the route
    comment_form = CommentForm()
    # If form is complete we want to action the adding of a comment.
    if comment_form.validate_on_submit():
        # Check user is logged in otherwise can't post comment and redirect to login page.
        if current_user.is_authenticated:
            # If form is submitted AND user is logged in then we can comment
            # Instantiate a comment object from its class
            new_comment = Comment(
                comment_text=comment_form.comment_text.data,
                author=current_user,
                blogpost=requested_post
            )
            # Add this new comment to our db and commit changes
            db.session.add(new_comment)
            db.session.commit()
            # Redirect user to the post with the new comment appearing
            return redirect(url_for("show_post", post_id=requested_post.id))
        else:
            flash("... Please login to post a comment.", category='warning')
            return redirect(url_for('login'))

    return render_template("post.html", post=requested_post, current_user=current_user, form=comment_form)


@app.route("/new-post", methods=["GET", "POST"])
@admin_required
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author_id=current_user.id,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)


# TODO: Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_required
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author_id=post.author_id,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user.name
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


# TODO: Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
@admin_required
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


if __name__ == "__main__":
    app.run(debug=True, port=5002)
