from flask import Flask, render_template, request, url_for, redirect, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from datetime import datetime
from zoneinfo import ZoneInfo
import uuid

app = Flask(
    __name__,
    template_folder="platform/templates",
    static_folder="platform/static"
)

app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://root:password@localhost/tnt_auth"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "password"

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

bcrypt = Bcrypt(app)


def arizona_time():
    return datetime.now(ZoneInfo("America/Phoenix"))


def generate_account_number():
    return f"TNT{str(uuid.uuid4().int)[:6]}"


class Customer(UserMixin, db.Model):
    __tablename__ = "customer"

    customerId = db.Column(db.Integer, primary_key=True)
    fullName = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    customerAccountNumber = db.Column(db.String(50), unique=True, nullable=False)
    hashedPassword = db.Column(db.String(255), nullable=False)
    availableFunds = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    createdAt = db.Column(db.DateTime, default=arizona_time, nullable=False)
    updatedAt = db.Column(db.DateTime, default=arizona_time, onupdate=arizona_time, nullable=False)

    def get_id(self):
        return f"customer-{self.customerId}"

    @property
    def is_admin(self):
        return False

    @property
    def is_customer(self):
        return True


class Company(db.Model):
    __tablename__ = "company"

    companyId = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    stockTotalQuantity = db.Column(db.Integer, nullable=False)
    ticker = db.Column(db.String(10), unique=True, nullable=False)
    currentMarketPrice = db.Column(db.Numeric(12, 2), nullable=False)
    createdBy = db.Column(db.Integer, db.ForeignKey("administrator.administratorId"), nullable=False)
    createdAt = db.Column(db.DateTime, default=arizona_time, nullable=False)
    updatedAt = db.Column(db.DateTime, default=arizona_time, onupdate=arizona_time, nullable=False)


class Administrator(UserMixin, db.Model):
    __tablename__ = "administrator"

    administratorId = db.Column(db.Integer, primary_key=True)
    fullName = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    hashedPassword = db.Column(db.String(255), nullable=False)
    createdAt = db.Column(db.DateTime, default=arizona_time, nullable=False)
    updatedAt = db.Column(db.DateTime, default=arizona_time, onupdate=arizona_time, nullable=False)

    def get_id(self):
        return f"admin-{self.administratorId}"

    @property
    def is_admin(self):
        return True

    @property
    def is_customer(self):
        return False


class StockInventory(db.Model):
    __tablename__ = "stockinventory"

    stockId = db.Column(db.Integer, primary_key=True)
    companyId = db.Column(db.Integer, db.ForeignKey("company.companyId"), nullable=False)
    administratorId = db.Column(db.Integer, db.ForeignKey("administrator.administratorId"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    ticker = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    initStockPrice = db.Column(db.Numeric(12, 2), nullable=False)
    currentMarketPrice = db.Column(db.Numeric(12, 2), nullable=False)
    createdAt = db.Column(db.DateTime, default=arizona_time, nullable=False)
    updatedAt = db.Column(db.DateTime, default=arizona_time, onupdate=arizona_time, nullable=False)


class MarketPriceConfig(db.Model):
    __tablename__ = "marketpriceconfig"

    configId = db.Column(db.Integer, primary_key=True)
    stockId = db.Column(db.Integer, db.ForeignKey("stockinventory.stockId"), nullable=False)
    minPrice = db.Column(db.Numeric(12, 2), nullable=False)
    maxPrice = db.Column(db.Numeric(12, 2), nullable=False)
    updateIntervalSeconds = db.Column(db.Integer, nullable=False)
    enabled = db.Column(db.Boolean, nullable=False)
    createdAt = db.Column(db.DateTime, default=arizona_time, nullable=False)
    updatedAt = db.Column(db.DateTime, default=arizona_time, onupdate=arizona_time, nullable=False)


class Portfolio(db.Model):
    __tablename__ = "portfolio"

    portfolioId = db.Column(db.Integer, primary_key=True)
    customerId = db.Column(db.Integer, db.ForeignKey("customer.customerId"), nullable=False)
    stockId = db.Column(db.Integer, db.ForeignKey("stockinventory.stockId"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    createdAt = db.Column(db.DateTime, default=arizona_time, nullable=False)
    updatedAt = db.Column(db.DateTime, default=arizona_time, onupdate=arizona_time, nullable=False)


class OrderHistory(db.Model):
    __tablename__ = "orderhistory"

    orderId = db.Column(db.Integer, primary_key=True)
    customerId = db.Column(db.Integer, db.ForeignKey("customer.customerId"), nullable=False)
    stockId = db.Column(db.Integer, db.ForeignKey("stockinventory.stockId"), nullable=False)
    administratorId = db.Column(db.Integer, db.ForeignKey("administrator.administratorId"), nullable=False)
    type = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    totalValue = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(10), nullable=False)
    createdAt = db.Column(db.DateTime, default=arizona_time, nullable=False)
    updatedAt = db.Column(db.DateTime, default=arizona_time, onupdate=arizona_time, nullable=False)


class FinancialTransaction(db.Model):
    __tablename__ = "financialtransaction"

    financialTransactionId = db.Column(db.Integer, primary_key=True)
    customerId = db.Column(db.Integer, db.ForeignKey("customer.customerId"), nullable=False)
    companyId = db.Column(db.Integer, db.ForeignKey("company.companyId"), nullable=False)
    orderId = db.Column(db.Integer, db.ForeignKey("orderhistory.orderId"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    type = db.Column(db.String(12), nullable=False)
    createdAt = db.Column(db.DateTime, default=arizona_time, nullable=False)


class MarketException(db.Model):
    __tablename__ = "exception"

    exceptionId = db.Column(db.Integer, primary_key=True)
    administratorId = db.Column(db.Integer, db.ForeignKey("administrator.administratorId"), nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    holidayDate = db.Column(db.Date, nullable=False)
    createdAt = db.Column(db.DateTime, default=arizona_time, nullable=False)
    updatedAt = db.Column(db.DateTime, default=arizona_time, onupdate=arizona_time, nullable=False)


class WorkingDay(db.Model):
    __tablename__ = "workingday"

    workingDayId = db.Column(db.Integer, primary_key=True)
    administratorId = db.Column(db.Integer, db.ForeignKey("administrator.administratorId"), nullable=False)
    dayOfWeek = db.Column(db.String(10), nullable=False)
    startTime = db.Column(db.Time, nullable=False)
    endTime = db.Column(db.Time, nullable=False)
    createdAt = db.Column(db.DateTime, default=arizona_time, nullable=False)
    updatedAt = db.Column(db.DateTime, default=arizona_time, onupdate=arizona_time, nullable=False)


with app.app_context():
    db.create_all()


@login_manager.user_loader
def load_user(user_id):
    if user_id.startswith("customer-"):
        customer_id = int(user_id.split("-")[1])
        return Customer.query.get(customer_id)

    if user_id.startswith("admin-"):
        admin_id = int(user_id.split("-")[1])
        return Administrator.query.get(admin_id)

    return None


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name")
        email = request.form.get("email")
        password = request.form.get("password")

        if Customer.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
            return redirect(url_for("register"))

        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

        account_number = generate_account_number()
        while Customer.query.filter_by(customerAccountNumber=account_number).first():
            account_number = generate_account_number()

        new_customer = Customer(
            fullName=full_name,
            email=email,
            customerAccountNumber=account_number,
            hashedPassword=hashed_password,
            availableFunds=0.00
        )

        try:
            db.session.add(new_customer)
            db.session.commit()
            flash("Customer account created successfully. Please log in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {str(e)}", "danger")
            return redirect(url_for("register"))

    return render_template("auth/register.html")




@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        customer = Customer.query.filter_by(email=email).first()
        if customer and bcrypt.check_password_hash(customer.hashedPassword, password):
            login_user(customer)
            flash("Customer login successful.", "success")
            return redirect(url_for("user_dashboard"))

        admin = Administrator.query.filter_by(email=email).first()
        if admin and bcrypt.check_password_hash(admin.hashedPassword, password):
            login_user(admin)
            flash("Administrator login successful.", "success")
            return redirect(url_for("admin_dashboard"))

        flash("Invalid email or password.", "danger")
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
    if not current_user.is_customer:
        flash("You do not have permission to view the user dashboard.", "danger")
        return redirect(url_for("admin_dashboard"))

    return render_template("dashboards/userdashboard.html")


@app.route("/admindashboard", methods=["GET", "POST"])
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash("You do not have permission to view the admin dashboard.", "danger")
        return redirect(url_for("user_dashboard"))
    
    if request.method == "POST":
        company_name = request.form.get("company_name")
        ticker = request.form.get("ticker").upper().strip()
        quantity = int(request.form.get("quantity"))
        initial_price = float(request.form.get("initial_price"))

        if quantity < 0 or initial_price < 0:
            flash("Quantity and price must be greater than or equal to 0.", "danger")
            return redirect(url_for("admin_dashboard"))
        
        existing_stock = StockInventory.query.filter_by(ticker=ticker).first()
        if existing_stock:
            flash("That ticker already exists.", "danger")
            return redirect(url_for("admin_dashboard"))
        
        new_company = Company(
            name=company_name,
            stockTotalQuantity=quantity,
            ticker=ticker,
            currentMarketPrice=initial_price,
            createdBy=current_user.administratorId
        )
        db.session.add(new_company)
        db.session.flush()

        new_stock = StockInventory(
            companyId=new_company.companyId,
            administratorId=current_user.administratorId,
            name=company_name,
            ticker=ticker,
            quantity=quantity,
            initStockPrice=initial_price,
            currentMarketPrice=initial_price
        )
        db.session.add(new_stock)
        db.session.commit()

        flash("Stock created successfully.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("dashboards/admindashboard.html")


@app.route("/market")
def market():
    stocks = StockInventory.query.all()
    return render_template("market.html", stocks=stocks)


@app.route("/portfolio")
@login_required
def portfolio():
    if not current_user.is_customer:
        flash("Only customers can view portfolios.", "danger")
        return redirect(url_for("admin_dashboard"))

    return render_template("portfolio.html")


@app.route("/trade", methods=["GET", "POST"])
@login_required
def trade():
    if not current_user.is_customer:
        flash("Only customers can access trading.", "danger")
        return redirect(url_for("admin_dashboard"))

    stocks = StockInventory.query.all()

    if request.method == "POST":
        stock_id = request.form.get("stock_id")
        quantity = int(request.form.get("quantity"))
        action = request.form.get("action")

        stock = StockInventory.query.get(stock_id)
        
        price = stock.currentMarketPrice 
        total_cost = price * quantity

        if action == "buy":
            if current_user.availableFunds < total_cost:
                flash("Not enough funds. Please adjust the order or deposit additional funds.")
                return redirect(url_for("trade"))
            
            if stock.quantity < quantity:
                flash(f"Not enough shares available in the market. Only {stock.quantity} left.", "danger")
                return redirect(url_for("trade"))
            
            current_user.availableFunds -= total_cost
            stock.quantity -= quantity

            portfolio = Portfolio.query.filter_by(
                customerId=current_user.customerId,
                stockId=stock.stockId,
            ).first()

            if portfolio:
                portfolio.quantity += quantity
            else:
                new_entry = Portfolio(
                    customerId=current_user.customerId,
                    stockId=stock.stockId,
                    quantity=quantity
                )
                db.session.add(new_entry)

            flash("Stock purchased successfully.", "success")

        elif action == "sell":
            portfolio = Portfolio.query.filter_by(
                customerId=current_user.customerId,
                stockId=stock.stockId
            ).first()

            if not portfolio or portfolio.quantity < quantity:
                flash("Not enough shares to sell.", "danger")
                return redirect(url_for("trade"))
            
            portfolio.quantity -= quantity

            if portfolio.quantity == 0:
                db.session.delete(portfolio)

            current_user.availableFunds += total_cost
            stock.quantity += quantity

            flash("Stock sold successfully.", "success")
            
        db.session.commit()
        return redirect(url_for("trade"))
        
    return render_template("trade.html", stocks=stocks)


if __name__ == "__main__":
    app.run(debug=True)