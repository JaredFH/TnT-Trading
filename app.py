from flask import Flask, render_template, request, url_for, redirect, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal, ROUND_HALF_UP
import uuid
import random

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

def refresh_stock_price(stock):
    config = MarketPriceConfig.query.filter_by(
        stockId=stock.stockId,
        enabled=True
    ).first()

    if not config:
        return
    
    now = arizona_time()
    last_update = stock.updatedAt or stock.createdAt
    
    if last_update.tzinfo is None:
        last_update = last_update.replace(tzinfo=ZoneInfo("America/Phoenix"))
    
    seconds_since_update = (now - last_update).total_seconds()

    if seconds_since_update < config.updateIntervalSeconds:
        return
    
    current_price = Decimal(str(stock.currentMarketPrice))
    min_price = Decimal(str(config.minPrice))
    max_price = Decimal(str(config.maxPrice))

    percent_change = Decimal(str(random.uniform(-0.03, 0.03)))
    new_price = current_price * (Decimal("1.00") + percent_change)

    if new_price < min_price:
        new_price = min_price
    elif new_price > max_price:
        new_price = max_price

    new_price = new_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    stock.currentMarketPrice = new_price

    company = Company.query.get(stock.companyId)
    if company:
        company.currentMarketPrice = new_price
        company.updatedAt = now

    stock.updatedAt = now

def refresh_all_stock_prices(stocks):
    for stock in stocks:
        refresh_stock_price(stock)
    db.session.commit()



VALID_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def is_market_open():
    now = arizona_time()
    today_name = now.strftime("%A")
    today_date = now.date()
    current_time = now.time()

    if today_name not in VALID_WEEKDAYS:
        return False, "Market is closed on weekends."

    holiday = MarketException.query.filter_by(holidayDate=today_date).first()
    if holiday:
        return False, f"Market is closed today: {holiday.reason}"

    working_day = WorkingDay.query.filter_by(dayOfWeek=today_name).first()
    if not working_day:
        return False, f"No market hours have been set for {today_name}."

    if current_time < working_day.startTime or current_time > working_day.endTime:
        return False, (
            f"Market is closed right now. Hours for {today_name} are "
            f"{working_day.startTime.strftime('%H:%M')} to {working_day.endTime.strftime('%H:%M')}."
        )

    return True, "Market is open."


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

    @property
    def percent_change(self):
        if float(self.initStockPrice) > 0:
            return ((float(self.currentMarketPrice) - float(self.initStockPrice)) / float(self.initStockPrice)) * 100.0
        return 0.0


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

@app.before_request
def auto_execute_orders():
    try:
        pending_orders = OrderHistory.query.filter_by(status="pending").all()
        now = arizona_time()
        updated = False
        for order in pending_orders:
            order_time = order.createdAt if order.createdAt.tzinfo else order.createdAt.replace(tzinfo=ZoneInfo("America/Phoenix"))
            if (now - order_time).total_seconds() >= 30:
                order.status = "completed"
                updated = True
        if updated:
            db.session.commit()
    except Exception:
        pass


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


@app.route("/userdashboard", methods=["GET", "POST"])
@login_required
def user_dashboard():
    if not current_user.is_customer:
        flash("You do not have permission to view the user dashboard.", "danger")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        amount = float(request.form.get("amount"))
        action = request.form.get("action")

        if amount <= 0:
            flash("Amount must be greater than 0.", "danger")
            return redirect(url_for("user_dashboard"))

        if action == "deposit":
            current_user.availableFunds = float(current_user.availableFunds) + amount
            db.session.commit()
            flash("Deposited successfully!")

        elif action == "withdraw":
            if float(current_user.availableFunds) < amount:
                flash("Insufficient funds, you cannot withdraw more than is available.")
                return redirect(url_for("user_dashboard"))

            current_user.availableFunds = float(current_user.availableFunds) - amount
            db.session.commit()
            flash("Funds withdrawn successfully.")

        return redirect(url_for("user_dashboard"))
    
    portfolio_items = (
        db.session.query(Portfolio, StockInventory)
        .join(StockInventory, Portfolio.stockId == StockInventory.stockId)
        .filter(Portfolio.customerId == current_user.customerId)
        .all()
        )
    
    stocks = [stock for _, stock in portfolio_items]
    refresh_all_stock_prices(stocks)

    total_stock_value = sum(
        portfolio.quantity * stock.currentMarketPrice
        for portfolio, stock in portfolio_items
    )

    orders = OrderHistory.query.filter_by(customerId=current_user.customerId).all()
    total_buys = sum(float(order.totalValue) for order in orders if order.type == "buy")
    total_sells = sum(float(order.totalValue) for order in orders if order.type == "sell")

    net_worth = float(current_user.availableFunds) + float(total_stock_value)
    net_worth_change = float(total_stock_value) + total_sells - total_buys

    return render_template(
        "dashboards/userdashboard.html",
        total_stock_value=total_stock_value,
        net_worth=net_worth,
        net_worth_change=net_worth_change
        )


@app.route("/admindashboard", methods=["GET", "POST"])
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash("You do not have permission to view the admin dashboard.", "danger")
        return redirect(url_for("user_dashboard"))

    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "create_stock":
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
            db.session.flush()

            new_market_config = MarketPriceConfig(
                stockId=new_stock.stockId,
                minPrice=initial_price * 0.50,
                maxPrice=initial_price * 1.50,
                updateIntervalSeconds=30,
                enabled=True
            )
            db.session.add(new_market_config)
            db.session.commit()

            flash("Stock created successfully.", "success")
            return redirect(url_for("admin_dashboard"))

        elif form_type == "save_schedule":
            day_of_week = request.form.get("day_of_week")
            start_time = datetime.strptime(request.form.get("start_time"), "%H:%M").time()
            end_time = datetime.strptime(request.form.get("end_time"), "%H:%M").time()

            if day_of_week not in VALID_WEEKDAYS:
                flash("Only Monday through Friday can be scheduled as market days.", "danger")
                return redirect(url_for("admin_dashboard"))

            if start_time >= end_time:
                flash("Start time must be earlier than end time.", "danger")
                return redirect(url_for("admin_dashboard"))

            existing_day = WorkingDay.query.filter_by(dayOfWeek=day_of_week).first()

            if existing_day:
                existing_day.startTime = start_time
                existing_day.endTime = end_time
                existing_day.administratorId = current_user.administratorId
                flash(f"{day_of_week} market hours updated successfully.", "success")
            else:
                new_day = WorkingDay(
                    administratorId=current_user.administratorId,
                    dayOfWeek=day_of_week,
                    startTime=start_time,
                    endTime=end_time
                )
                db.session.add(new_day)
                flash(f"{day_of_week} market hours added successfully.", "success")

            db.session.commit()
            return redirect(url_for("admin_dashboard"))

        elif form_type == "add_holiday":
            reason = request.form.get("reason").strip()
            holiday_date = datetime.strptime(request.form.get("holiday_date"), "%Y-%m-%d").date()

            existing_exception = MarketException.query.filter_by(holidayDate=holiday_date).first()
            if existing_exception:
                flash("A market exception already exists for that date.", "danger")
                return redirect(url_for("admin_dashboard"))

            new_exception = MarketException(
                administratorId=current_user.administratorId,
                reason=reason,
                holidayDate=holiday_date
            )
            db.session.add(new_exception)
            db.session.commit()

            flash("Market closure added successfully.", "success")
            return redirect(url_for("admin_dashboard"))

    schedules = WorkingDay.query.order_by(WorkingDay.dayOfWeek.asc()).all()
    holidays = MarketException.query.order_by(MarketException.holidayDate.asc()).all()

    return render_template(
        "dashboards/admindashboard.html",
        schedules=schedules,
        holidays=holidays,
        valid_weekdays=VALID_WEEKDAYS
    )


@app.route("/market")
def market():
    stocks = StockInventory.query.all()
    refresh_all_stock_prices(stocks)
    schedules = WorkingDay.query.order_by(WorkingDay.dayOfWeek.asc()).all()

    return render_template("market.html", stocks=stocks, schedules=schedules)


@app.route("/portfolio")
@login_required
def portfolio():
    if not current_user.is_customer:
        flash("Only customers can view portfolios.", "danger")
        return redirect(url_for("admin_dashboard"))

    user_portfolio = db.session.query(Portfolio, StockInventory)\
        .join(StockInventory, Portfolio.stockId == StockInventory.stockId)\
        .filter(Portfolio.customerId == current_user.customerId)\
        .all()
    
    owned_stocks = [stock for portfolio, stock in user_portfolio]
    refresh_all_stock_prices(owned_stocks)

    return render_template("portfolio.html", portfolio_items=user_portfolio)


@app.route("/trade", methods=["GET", "POST"])
@login_required
def trade():
    if not current_user.is_customer:
        flash("Only customers can access trading.", "danger")
        return redirect(url_for("admin_dashboard"))

    stocks = StockInventory.query.all()
    refresh_all_stock_prices(stocks)

    market_open, market_message = is_market_open()

    if request.method == "POST":
        market_open, market_message = is_market_open()
        stock_id = request.form.get("stock_id")
        quantity = int(request.form.get("quantity"))
        action = request.form.get("action")

        stock = StockInventory.query.get(stock_id)

        refresh_stock_price(stock)
        db.session.commit()

        price = stock.currentMarketPrice
        total_cost = price * quantity

        if not market_open:
            admin = Administrator.query.first()

            new_order = OrderHistory(
                customerId=current_user.customerId,
                stockId=stock.stockId,
                administratorId=admin.administratorId if admin else 1,
                type=action,
                quantity=quantity,
                price=price,
                totalValue=total_cost,
                status="pending"
            )
            db.session.add(new_order)
            db.session.commit()

            flash("Market is currently closed. Your order has been placed in queue.")
            return redirect(url_for("order_history"))

        if action == "buy":
            if float(current_user.availableFunds) < total_cost:
                flash("Not enough funds. Please adjust the order or deposit additional funds.", "warning")
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

            admin = Administrator.query.first()
            new_order = OrderHistory(
                customerId=current_user.customerId,
                stockId=stock.stockId,
                administratorId=admin.administratorId if admin else 1,
                type="buy",
                quantity=quantity,
                price=price,
                totalValue=total_cost,
                status="pending"
            )
            db.session.add(new_order)

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

            admin = Administrator.query.first()
            new_order = OrderHistory(
                customerId=current_user.customerId,
                stockId=stock.stockId,
                administratorId=admin.administratorId if admin else 1,
                type="sell",
                quantity=quantity,
                price=price,
                totalValue=total_cost,
                status="pending"
            )
            db.session.add(new_order)

            flash("Stock sold successfully.", "success")

        db.session.commit()
        return redirect(url_for("trade"))

    return render_template(
        "trade.html", 
        stocks=stocks, 
        market_open=market_open, 
        market_message=market_message
        )



@app.route("/cancel_order/<int:order_id>", methods=["POST"])
@login_required
def cancel_order(order_id):
    order = OrderHistory.query.get_or_404(order_id)
    stock = StockInventory.query.get(order.stockId)

    if order.type == "buy":
        current_user.availableFunds += order.totalValue
        stock.quantity += order.quantity
        portfolio = Portfolio.query.filter_by(customerId=current_user.customerId, stockId=stock.stockId).first()
        if portfolio:
            portfolio.quantity -= order.quantity
            if portfolio.quantity <= 0:
                db.session.delete(portfolio)
    elif order.type == "sell":
        current_user.availableFunds -= order.totalValue
        stock.quantity -= order.quantity
        portfolio = Portfolio.query.filter_by(customerId=current_user.customerId, stockId=stock.stockId).first()
        if portfolio:
            portfolio.quantity += order.quantity
        else:
            new_entry = Portfolio(customerId=current_user.customerId, stockId=stock.stockId, quantity=order.quantity)
            db.session.add(new_entry)

    order.status = "canceled"
    db.session.commit()
    flash("Order canceled successfully.", "success")
    return redirect(url_for("order_history"))


@app.route("/orderhistory")
@login_required
def order_history():
    query = db.session.query(OrderHistory, StockInventory, Customer)\
        .join(StockInventory, StockInventory.stockId == OrderHistory.stockId)\
        .join(Customer, Customer.customerId == OrderHistory.customerId)

    if current_user.is_customer:
        query = query.filter(OrderHistory.customerId == current_user.customerId)

    orders = query.order_by(OrderHistory.createdAt.desc()).all()

    return render_template("orderhistory.html", orders=orders)


if __name__ == "__main__":
    app.run(debug=True)