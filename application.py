import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

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
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    names = []
    symbols = []
    shares = []
    price = []
    value = []

    stock_shares_price = db.execute("SELECT name, stock_symbol, shares, price FROM portfolio WHERE user_id = :id", id=session["user_id"])
    for element in range(len(stock_shares_price)):
        companyName = stock_shares_price[element]['name']
        stock = stock_shares_price[element]['stock_symbol']
        share = stock_shares_price[element]['shares']
        current_price = stock_shares_price[element]['price']
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

    cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
    # TODO round()
    cash = round(cash[0]['cash'])

    # TODO round()
    total = cash + sum(value)

    print(cash, total)

    return render_template("index.html", stocks=portfolio, cash=cash, total=total)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        bought = "Bought"
        # Ensure symbol and number of shares was submitted
        symbol = request.form.get("symbol")
        amount = int(request.form.get("amount"))
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
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
        # Price to buy the number of stocks requested
        price = stock['price'] * amount

        if cash[0]['cash'] < price:
            return apology("Sorry. Insufficient Funds")

        #add stock to portfolio
        existant = db.execute("SELECT stock_symbol FROM portfolio WHERE stock_symbol = :stock \
                        AND user_id = :id", stock=symbol, id=session["user_id"])
        existing_amount = db.execute("SELECT shares FROM portfolio WHERE stock_symbol = :stock \
                        AND user_id = :id", stock=symbol, id=session["user_id"])


        if not existant:
            db.execute("INSERT INTO portfolio (name, stock_symbol, shares, price, user_id) \
                        VALUES(:name, :stock_symbol, :shares, :price, :user_id)", name=stock['name'], stock_symbol=stock['symbol'], \
                        shares=amount, price=stock['price'], user_id=session["user_id"])
        else:

            db.execute("UPDATE portfolio SET shares = :amount WHERE stock_symbol = :stock \
                        AND user_id = :id", amount=amount+existing_amount[0]['shares'], stock=symbol, id=session["user_id"])


        #Subtract cash from user database
        db.execute("UPDATE users SET cash = cash - :price WHERE id = :id", price=price, id=session["user_id"])

        # ADD transaction to history table
        db.execute("INSERT INTO history (transaction_type, symbol, shares, price, user_id) \
                        VALUES (:transaction, :symbol, :shares, :price, :user_id)", transaction=bought, symbol=stock['symbol'], \
                        shares=amount, price=stock['price'], user_id=session["user_id"])


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

    stock_shares_price = db.execute("SELECT transaction_type, symbol, shares, price FROM history WHERE user_id = :id", id=session["user_id"])
    for element in range(len(stock_shares_price)):
        symbols.append(stock_shares_price[element]['symbol'])
        shares.append(stock_shares_price[element]['shares'])
        transaction_type.append(stock_shares_price[element]['transaction_type'])
        price.append(stock_shares_price[element]['price'])

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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

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
        result = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))
        if result:
            return apology("Username already exists", 403)

        # Insert the new user into the database
        new_user = db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", username=request.form.get("username"), hash=hash)

        # Log the user in automatically
        row = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))
        session["user_id"] = row[0]["id"]

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
        amount = int(request.form.get("amount"))
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
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
        # Price to sell the number of stocks requested
        price = (stock['price']) * amount

        #Subtrack stock to portfolio
        existant = db.execute("SELECT stock_symbol FROM portfolio WHERE stock_symbol = :stock \
                        AND user_id = :id", stock=symbol, id=session["user_id"])

        existing_amount = db.execute("SELECT shares FROM portfolio WHERE stock_symbol = :stock \
                        AND user_id = :id", stock=symbol, id=session["user_id"])

        # Unlikely because of drop down menu
        if not existant:
            return apology("You do not own any " + symbol + " stocks")
        # If user tries to sell more shares than you own
        elif existing_amount[0]['shares'] < amount:
            return apology("You only have " + str(existing_amount[0]['shares']) + " stocks to sell")
        else:
            db.execute("UPDATE portfolio SET shares = :amount WHERE stock_symbol = :stock \
                        AND user_id = :id", amount=existing_amount[0]['shares'] - amount, stock=symbol, id=session["user_id"])

        # Delete row if existing amount is 0


        #Subtract cash from user database
        db.execute("UPDATE users SET cash = cash + :price WHERE id = :id", price=price, id=session["user_id"])

        # ADD stock to history table
        db.execute("INSERT INTO history (transaction_type, symbol, shares, price, user_id) \
                        VALUES (:transaction, :symbol, :shares, :price, :user_id)", transaction=sold, symbol=stock['symbol'], \
                        shares=amount, price=stock['price'], user_id=session["user_id"])

        print(existing_amount[0]['shares'] - amount)
        if existing_amount[0]['shares'] - amount == 0:

            db.execute("DELETE FROM portfolio WHERE stock_symbol=:stock_symbol AND user_id=:user_id" \
                        , stock_symbol=stock['symbol'], user_id=session["user_id"])

        return redirect("/")
    else:
        # List of stocks owned to include in select menu
        stock = []
        stocks = db.execute("SELECT stock_symbol FROM portfolio WHERE user_id = :id", id=session["user_id"])
        for element in range(len(stocks)):
            share = stocks[element]['stock_symbol']
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