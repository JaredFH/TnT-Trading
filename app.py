from flask import Flask, render_template, request, url_for, redirect, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from datetime import datetime
from zoneinfo import ZoneInfo

app = Flask(
    __name__,
    template_folder="platform/templates",
    static_folder="platform/static"
)

app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://root:password@localhost/tnt_auth"
app.config["SECRET_KEY"] = "password"

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

bcrypt = Bcrypt(app)

def eastern_time():
    return datetime.now(ZoneInfo("America/New_York"))

class Users(UserMixin, db.Model):
    __tablename__ = "users"
    id                    = db.Column(db.Integer, primary_key=True)
    fullname              = db.Column(db.String(255), nullable=False)
    username              = db.Column(db.String(250), unique=True, nullable=False)
    email                 = db.Column(db.String(255), unique=True, nullable=False)
    password              = db.Column(db.String(255), nullable=False)
    role                  = db.Column(db.String(50), default="user", nullable=False)  
    customerAccountNumber = db.Column(db.String(50), unique=True, nullable=True)      
    availableFunds        = db.Column(db.Numeric(12, 2), default=0.00, nullable=True) 
    createdAt             = db.Column(db.DateTime(timezone=True), default=eastern_time, nullable=False)
    updatedAt             = db.Column(db.DateTime(timezone=True), default=eastern_time, onupdate=eastern_time, nullable=False)

class Company(db.Model):
    __tablename__ = "company"
    companyId          = db.Column(db.Integer, primary_key=True)
    createdBy          = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name               = db.Column(db.String(255), nullable=False)
    description        = db.Column(db.Text, nullable=True)
    stockTotalQuantity = db.Column(db.Integer, nullable=False)
    ticker             = db.Column(db.String(10), nullable=False, unique=True)
    currentMarketPrice = db.Column(db.Numeric(12, 2), nullable=False)
    createdAt             = db.Column(db.DateTime(timezone=True), default=eastern_time, nullable=False)
    updatedAt             = db.Column(db.DateTime(timezone=True), default=eastern_time, onupdate=eastern_time, nullable=False)


with app.app_context():
    db.create_all()


@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name")
        username = request.form.get("username")
        email     = request.form.get("email")
        password = request.form.get("password")

        existing_user = Users.query.filter_by(username=username).first()
        if existing_user:
            flash("Username already exists. Please choose another one.", "danger")
            return redirect(url_for("register"))
        
        if Users.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
            return redirect(url_for("register"))

        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

        import uuid
        account_number = str(uuid.uuid4())[:8].upper()

        user = Users(
            fullname=full_name,
            username=username,
            email=email,
            password=hashed_password,
            role="user",
            customerAccountNumber=account_number,
            availableFunds=0.00
        )

        db.session.add(user)
        db.session.commit()

        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("auth/register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = Users.query.filter_by(username=username).first()

        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            flash("Login successful.", "success")

            if user.role == "admin":
                return redirect(url_for("admin_dashboard"))
            else:
                return redirect(url_for("user_dashboard"))

        flash("Invalid username or password.", "danger")
        return redirect(url_for("login"))

    return render_template("auth/login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


@app.route("/userdashboard")
@login_required
def user_dashboard():
    return render_template("dashboards/userdashboard.html")


@app.route("/admindashboard")
@login_required
def admin_dashboard():
    if current_user.role != "admin":
        flash("You do not have permission to view that page.", "danger")
        return redirect(url_for("user_dashboard"))

    return render_template("dashboards/admindashboard.html")


@app.route("/market")
def market():
    return render_template("market.html")


@app.route("/portfolio")
@login_required
def portfolio():
    return render_template("portfolio.html")


@app.route("/trade")
@login_required
def trade():
    return render_template("trade.html")


if __name__ == "__main__":
    app.run(debug=True)