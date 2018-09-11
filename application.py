import os
import sqlite3

from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

import pickle
from datetime import timedelta
from uuid import uuid4
from redis import Redis
from werkzeug.datastructures import CallbackDict
from flask.sessions import SessionInterface, SessionMixin

# For Heroku Deployment purposes see: http://flask.pocoo.org/snippets/75/
class RedisSession(CallbackDict, SessionMixin):

    def __init__(self, initial=None, sid=None, new=False):
        def on_update(self):
            self.modified = True
        CallbackDict.__init__(self, initial, on_update)
        self.sid = sid
        self.new = new
        self.modified = False

class RedisSessionInterface(SessionInterface):
    serializer = pickle
    session_class = RedisSession

    def __init__(self, redis=None, prefix='session:'):
        if redis is None:
            redis = Redis()
        self.redis = redis
        self.prefix = prefix

    def generate_sid(self):
        return str(uuid4())

    def get_redis_expiration_time(self, app, session):
        if session.permanent:
            return app.permanent_session_lifetime
        return timedelta(days=1)

    def open_session(self, app, request):
        sid = request.cookies.get(app.session_cookie_name)
        if not sid:
            sid = self.generate_sid()
            return self.session_class(sid=sid, new=True)
        val = self.redis.get(self.prefix + sid)
        if val is not None:
            data = self.serializer.loads(val)
            return self.session_class(data, sid=sid)
        return self.session_class(sid=sid, new=True)

    def save_session(self, app, session, response):
        domain = self.get_cookie_domain(app)
        if not session:
            self.redis.delete(self.prefix + session.sid)
            if session.modified:
                response.delete_cookie(app.session_cookie_name,
                                       domain=domain)
            return
        redis_exp = self.get_redis_expiration_time(app, session)
        cookie_exp = self.get_expiration_time(app, session)
        val = self.serializer.dumps(dict(session))
        self.redis.setex(self.prefix + session.sid, val,
                         int(redis_exp.total_seconds()))
        response.set_cookie(app.session_cookie_name, session.sid,
                            expires=cookie_exp, httponly=True,
                            domain=domain)

# Configure application
app = Flask(__name__)
app.session_interface = RedisSessionInterface()

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
# sqlite:///finance.db
# postgres://czzvikmcykodyo:e98334d004b1a42bda26225961bb6e77e8ba098097704f1857158e4dcd91ffe6@ec2-54-225-92-1.compute-1.amazonaws.com:5432/ddi73ral6701au


connection = sqlite3.connect("finance.db")
crsr = connection.cursor()

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    names = []
    symbols = []
    shares = []
    price = []
    value = []

    stock_shares_price = crsr.execute("SELECT name, stock_symbol, shares, price FROM portfolio WHERE user_id=?", (session["user_id"],))
    stockList = stock_shares_price.fetchall()

    for element in range(len(stockList)):
        companyName = stockList[element][0]
        stock = stockList[element][1]
        share = stockList[element][2]
        current_price = stockList[element][3]
        if stock in symbols:
            # Add the number of shares to the existing shares at the index corresponding to the stock
            index_a = symbols.index(stock)
            updated_shares = shares[index_a] + share
            shares[index_a] = updated_shares
        else:
            # Insert the stock to the symbols list and insert the corresponding number of shares
            names.append(companyName)
            symbols.append(stock)
            index = symbols.index(stock)
            shares.insert(index, share)
            # Insert the current price to the price list at the index corresponding to the symbol
            price.append(current_price)
    # Value of each stock held is price * number of shares
    for i in range(len(symbols)):
        value.append(price[i] * shares[i])

    # Create a list of dictionaries whose values are lists to be passed to index.html including symbol, shares, price, and values
    portfolio = [{'names': names, 'symbol': symbols, 'shares': shares, 'price': price, 'value': value}]

    # Get cash and round it
    cash = crsr.execute("SELECT cash FROM users WHERE id=?", (session["user_id"],))
    cashList = cash.fetchone()
    cash = round(cashList[0])

    total = cash + sum(value)

    return render_template("index.html", stocks=portfolio, cash=cash, total=total)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        bought = "Bought"
        # Ensure symbol and number of shares was submitted
        symbol = request.form.get("symbol")
        amount = request.form.get("amount")
        if not amount:
            return apology("Please enter an amount")
        try:
            amount = int(amount)
        except ValueError:
            return apology("Please enter a number")
        if amount <= 0:
            return apology("Please enter a number above 0")

        if not symbol:
            return apology("Please enter a Symbol")
        while True:
            if not amount and not amount > 0:
                return apology("Please enter a number of Shares")
            else:
                break

        # Look up price
        stock = lookup(symbol)
        if stock is None:
            return apology('Please enter a valid symbol')

        # Look up cash available
        cash = crsr.execute("SELECT cash FROM users WHERE id=?", (session["user_id"],))
        cashList = cash.fetchone()
        # Price to buy the number of stocks requested
        price = stock['price'] * amount

        if cashList[0] < price:
            return apology("Sorry. Insufficient Funds")

        #add stock to portfolio
        existant = crsr.execute("SELECT stock_symbol FROM portfolio WHERE stock_symbol=:stock \
                        AND user_id=:id", {"stock": symbol, "id": session["user_id"]})
        existing_amount = crsr.execute("SELECT shares FROM portfolio WHERE stock_symbol=:stock \
                        AND user_id=:id", {"stock": symbol, "id": session["user_id"]})
        fetch_existing_amount = existing_amount.fetchone()

        if fetch_existing_amount is None:
            crsr.execute("INSERT INTO portfolio (name, stock_symbol, shares, price, user_id) \
                        VALUES(:name, :stock_symbol, :shares, :price, :user_id)", {"name": stock['name'], "stock_symbol": stock['symbol'], \
                        "shares": amount, "price": stock['price'], "user_id": session["user_id"]})
        else:

            crsr.execute("UPDATE portfolio SET shares = :amount WHERE stock_symbol=:stock \
                        AND user_id=:id", {"amount": amount + fetch_existing_amount[0], "stock": symbol, "id": session["user_id"]})


        #Subtract cash from user database
        crsr.execute("UPDATE users SET cash = cash - :price WHERE id = :id", {"price": price, "id": session["user_id"]})

        # ADD transaction to history table
        crsr.execute("INSERT INTO history (transaction_type, symbol, shares, price, user_id) \
                        VALUES (:transaction, :symbol, :shares, :price, :user_id)", {"transaction": bought, "symbol": stock['symbol'], \
                        "shares": amount, "price": stock['price'], "user_id": session["user_id"]})

        connection.commit()
        return redirect("/")
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
     # Create a list of dictionaries whose values are lists to be passed to index.html including symbol, shares, price, and transaction type
    symbols = []
    shares = []
    price = []
    transaction_type = []

    stock_shares_price = crsr.execute("SELECT transaction_type, symbol, shares, price FROM history WHERE user_id = ?", (session["user_id"],))
    stockList = stock_shares_price.fetchall()
    print(stockList)
    for element in range(len(stockList)):
        transaction_type.append(stockList[element][0])
        symbols.append(stockList[element][1])
        shares.append(stockList[element][2])

        price.append(stockList[element][3])

    portfolio = [{'symbol': symbols, 'shares': shares, 'price': price, 'transaction_type': transaction_type}]

    return render_template("history.html", stocks=portfolio)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        username = request.form.get("username")
        rows = crsr.execute("SELECT * FROM users WHERE username=?", (username,))
        row = rows.fetchone()

        if row is None:
            return apology('username does not exist')
        # Ensure username exists and password is correct
        if row[1] != username or not check_password_hash(row[2], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = row[0]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        # Ensure symbol was submitted
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Please enter a Symbol")

        # returns dict with name, price, and symbol of the stock
        quote = lookup(symbol)
        print(quote)
        # Ensure the symbol entered was valid
        if not quote:
            return apology("Please enter a valid Symbol")

        return render_template("quoted.html", price=quote['price'], symbol=quote['symbol'])

    return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)
        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)
        # Ensure password was confirm
        elif not request.form.get("passwordConfirm"):
            return apology("must confirm password", 403)
        # Ensure passwords match
        elif not request.form.get("password") == request.form.get("passwordConfirm"):
            return apology("Passwords must match", 403)

        # Hash the password
        hash = generate_password_hash(request.form.get("password"))

        # Check whether the username already exists
        result = crsr.execute("SELECT * FROM users WHERE username = :username",
                          {"username": request.form.get("username")})
        fetch_result = result.fetchone()
        if fetch_result is not None:
            return apology("Username already exists", 403)

        # Insert the new user into the database
        new_user = crsr.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", {"username": request.form.get("username"), "hash": hash})

        # Log the user in automatically
        row = crsr.execute("SELECT * FROM users WHERE username = ?",
                          (request.form.get("username"),))
        fetch_row = row.fetchone()

        session["user_id"] = fetch_row[0]

        connection.commit()
        # Redirects User to the homepage
        return redirect("/")

    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        sold = "Sold"
        # Ensure symbol and number of shares was submitted
        symbol = request.form.get("symbol")

        amount = request.form.get("amount")
        if not amount:
            return apology("Please enter an amount")
        amount = int(amount)

        if not symbol:
            return apology("Please enter a Symbol")
        while True:
            if not amount and not amount > 0:
                return apology("Please enter a number of Shares")
            else:
                break
        # Look up price
        stock = lookup(symbol)
        # Look up cash available
        cash = crsr.execute("SELECT cash FROM users WHERE id = ?", (session["user_id"],))
        # Price to sell the number of stocks requested
        price = (stock['price']) * amount

        #Subtrack stock to portfolio
        existant = crsr.execute("SELECT stock_symbol FROM portfolio WHERE stock_symbol = :stock \
                        AND user_id = :id", {"stock": symbol, "id": session["user_id"]})

        existing_amount = crsr.execute("SELECT shares FROM portfolio WHERE stock_symbol = :stock \
                        AND user_id = :id", {"stock": symbol, "id": session["user_id"]})
        fetch_existing_amount = existing_amount.fetchone()

        # Unlikely because of drop down menu
        if fetch_existing_amount is None:
            return apology("You do not own any " + symbol + " stocks")
        # If user tries to sell more shares than you own
        elif fetch_existing_amount[0] < amount:
            return apology("You only have " + str(existing_amount[0]['shares']) + " stocks to sell")
        else:
            crsr.execute("UPDATE portfolio SET shares = :amount WHERE stock_symbol = :stock \
                        AND user_id = :id", {"amount": fetch_existing_amount[0] - amount, "stock":symbol, "id": session["user_id"]})


        #Subtract cash from user database
        crsr.execute("UPDATE users SET cash = cash + :price WHERE id = :id", {"price": price, "id": session["user_id"]})

        # ADD stock to history table
        crsr.execute("INSERT INTO history (transaction_type, symbol, shares, price, user_id) \
                        VALUES (:transaction, :symbol, :shares, :price, :user_id)", {"transaction": sold, "symbol": stock['symbol'], \
                        "shares": amount, "price": stock['price'], "user_id": session["user_id"]})

        if fetch_existing_amount[0] - amount == 0:

            crsr.execute("DELETE FROM portfolio WHERE stock_symbol=:stock_symbol AND user_id=:user_id" \
                        , {"stock_symbol": stock['symbol'], "user_id": session["user_id"]})

        connection.commit()
        return redirect("/")
    else:
        # List of stocks owned to include in select menu
        stock = []
        stocks = crsr.execute("SELECT stock_symbol FROM portfolio WHERE user_id = ?", (session["user_id"],))
        fetch_stocks = stocks.fetchall()
        print(fetch_stocks)
        for element in range(len(fetch_stocks)):
            share = fetch_stocks[element][0]
            if share in stock:
                continue
            else:
                # Insert the stock to the symbols list and insert the corresponding number of shares
                stock.append(share)

        return render_template("sell.html", stocks=stock)

def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)

# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

