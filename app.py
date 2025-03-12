# Main Flask application for One Stop Shop with MongoDB integration
from flask import Flask, render_template, request, redirect, url_for, flash, session
from pymongo import MongoClient
from bson import ObjectId
import certifi
from flask_pymongo import PyMongo
import datetime

app = Flask(__name__)
app.secret_key = 'no-one-knows-this'  # Required for session and flash messages

# MongoDB Setup
uri = "mongodb+srv://theochen16:1234@cluster0.n8qic.mongodb.net"

try:
    # Create client with detailed logging
    client = MongoClient(uri,
                        serverSelectionTimeoutMS=5000,  # 5 second timeout
                        connectTimeoutMS=5000,
                        tls=True,
                        tlsCAFile=certifi.where()
)
   
    # Test the connection with more detailed error reporting
    print("Attempting to connect to MongoDB...")
    db = client.get_database("shop")
    db.command("ping")
    print("MongoDB connection successful!")
   
except Exception as e:
    print(f"Detailed connection error: {str(e)}")
    print(f"Error type: {type(e)}")





# Configure Flask-PyMongo with the same URI
app.config["MONGO_URI"] = f"{uri}/notes?tls=true"
mongo = PyMongo(app, tlsCAFile=certifi.where())

@app.route('/')
def index():
    # Display all stores and products on home page
    try:
        stores = db.stores.find({}).limit(50)  # Limit to 50 stores
        products = db.products.find({}).limit(100)  # Limit to 100 products
        return render_template("home.html", stores=stores, products=products)
    except Exception as e:
        print(f"Database query error: {str(e)}")
        return "Error loading data", 500

@app.route('/register_store', methods=['POST'])
def register_store():
    # Register new store with empty products array to store ObjectIds
    store_data = {
        'shop_name': request.form['shop_name'],
        'owner_name': request.form['owner_name'],
        'email': request.form['email'],
        'contact': request.form['contact'],
        'password': request.form['password'],
        'products': []  # Array to store product ObjectIds
    }
    
    try:
        db.stores.insert_one(store_data)
        flash('Store registered successfully!')
    except Exception as e:
        flash('Registration failed')
    return redirect('/')

@app.route('/login', methods=['POST'])
def login():
    # Store owner login
    email = request.form['email']
    password = request.form['password']
    store = db.stores.find_one({'email': email, 'password': password})
    
    if store:
        session['store_email'] = email
        return redirect(url_for('shop_home'))
    flash('Invalid login credentials')
    return redirect('/')

@app.route('/logout')
def logout():
    # Clear store owner session
    session.pop('store_email', None)
    return redirect('/')

@app.route('/shop_home')
def shop_home():
    # Shop owner's home page with products looked up by ObjectId
    if 'store_email' not in session:
        return redirect('/')
    
    store = db.stores.find_one({'email': session['store_email']})
    # Get all products using the ObjectIds stored in store.products
    products = list(db.products.find({'_id': {'$in': store['products']}}))
    return render_template('shophome.html', store=store, products=products)

@app.route('/add_product', methods=['POST'])
def add_product():
    # Add new product and store its ObjectId in the store's products array
    if 'store_email' not in session:
        return redirect('/')
    
    product = {
        'name': request.form['name'],
        'description': request.form['description'],
        'price': float(request.form['price']),
        'quantity': int(request.form['quantity']),
        'img_link': request.form['img_link']
    }
    
    # Insert product and get its ObjectId
    result = db.products.insert_one(product)
    
    # Add the product's ObjectId to the store's products array
    db.stores.update_one(
        {'email': session['store_email']},
        {'$push': {'products': result.inserted_id}}
    )
    
    flash('Product added successfully!')
    return redirect('/shop_home')

@app.route('/update_stock', methods=['POST'])
def update_stock():
    # Update product stock
    if 'store_email' not in session:
        return redirect('/')
    
    product_id = ObjectId(request.form['product_id'])
    new_quantity = int(request.form['quantity'])
    db.products.update_one(
        {'_id': product_id},
        {'$set': {'quantity': new_quantity}}
    )
    flash('Stock updated successfully!')
    return redirect('/shop_home')

@app.route('/shop_view/<email>')  # Changed from /shop/<email> to /shop_view/<email>
def shop_view(email):  # Changed function name from shop to shop_view
    # Find store and its products using ObjectId references
    store = db.stores.find_one({'email': email})
    if not store:
        flash('Store not found')
        return redirect('/')
    
    # Get products using ObjectIds from store.products array
    products = list(db.products.find({'_id': {'$in': store['products']}}))
    return render_template('shop_view.html', store=store, products=products)

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    # Add product to cart
    if 'cart' not in session:
        session['cart'] = []
    
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])
    
    product = db.products.find_one({'_id': ObjectId(product_id)})
    if product and product['quantity'] >= quantity:
        cart_item = {
            'product_id': product_id,
            'name': product['name'],
            'price': product['price'],
            'quantity': quantity
        }
        session['cart'].append(cart_item)
        
        # Update product quantity
        db.products.update_one(
            {'_id': ObjectId(product_id)},
            {'$inc': {'quantity': -quantity}}
        )
        flash('Added to cart!')
    else:
        flash('Not enough stock available!')
    return redirect(request.referrer)

@app.route('/view_cart')
def view_cart():
    # View shopping cart with full product details
    cart = session.get('cart', [])
    cart_items = []
    total = 0
    
    for item in cart:
        product = db.products.find_one({'_id': ObjectId(item['product_id'])})
        if product:
            cart_items.append({
                'product': product,
                'quantity': item['quantity']
            })
            total += product['price'] * item['quantity']
    
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/checkout', methods=['POST'])
def checkout():
    # Process checkout
    session.pop('cart', None)
    flash('Checkout successful! Thank you for shopping!')
    return redirect('/')

@app.route('/update_cart', methods=['POST'])
def update_cart():
    # Update quantity of item in cart
    product_id = request.form['product_id']
    new_quantity = int(request.form['quantity'])
    
    cart = session.get('cart', [])
    for item in cart:
        if item['product_id'] == product_id:
            # Check if new quantity is available in stock
            product = db.products.find_one({'_id': ObjectId(product_id)})
            if product and product['quantity'] >= new_quantity:
                # Calculate quantity difference
                quantity_diff = new_quantity - item['quantity']
                # Update product stock
                db.products.update_one(
                    {'_id': ObjectId(product_id)},
                    {'$inc': {'quantity': -quantity_diff}}
                )
                item['quantity'] = new_quantity
                flash('Cart updated successfully!')
            else:
                flash('Not enough stock available!')
            break
    
    session['cart'] = cart
    return redirect(url_for('view_cart'))

@app.route('/remove_from_cart', methods=['POST'])
def remove_from_cart():
    # Remove item from cart and return quantity to stock
    product_id = request.form['product_id']
    cart = session.get('cart', [])
    
    for item in cart:
        if item['product_id'] == product_id:
            # Return quantity to stock
            db.products.update_one(
                {'_id': ObjectId(product_id)},
                {'$inc': {'quantity': item['quantity']}}
            )
            cart.remove(item)
            break
    
    session['cart'] = cart
    flash('Item removed from cart!')
    return redirect(url_for('view_cart'))

@app.route('/clear_cart', methods=['POST'])
def clear_cart():
    # Clear cart and return all quantities to stock
    cart = session.get('cart', [])
    
    for item in cart:
        # Return quantity to stock for each item
        db.products.update_one(
            {'_id': ObjectId(item['product_id'])},
            {'$inc': {'quantity': item['quantity']}}
        )
    
    session.pop('cart', None)
    flash('Cart cleared!')
    return redirect(url_for('view_cart'))

@app.route('/checkout_page')
def checkout_page():
    # Display checkout page with cart items
    cart = session.get('cart', [])
    if not cart:
        flash('Your cart is empty!')
        return redirect(url_for('index'))
    
    cart_items = []
    total = 0
    
    for item in cart:
        product = db.products.find_one({'_id': ObjectId(item['product_id'])})
        if product:
            cart_items.append({
                'product': product,
                'quantity': item['quantity']
            })
            total += product['price'] * item['quantity']
    
    return render_template('checkout.html', cart_items=cart_items, total=total)

@app.route('/process_order', methods=['POST'])
def process_order():
    # Process the order and save to database
    if 'cart' not in session or not session['cart']:
        flash('Your cart is empty!')
        return redirect(url_for('index'))
    
    order_data = {
        'customer_name': request.form['name'],
        'email': request.form['email'],
        'phone': request.form['phone'],
        'address': request.form['address'],
        'items': session['cart'],
        'total': sum(item['price'] * item['quantity'] for item in session['cart']),
        'status': 'pending',
        'date': datetime.datetime.now()
    }
    
    try:
        # Save order to database
        db.orders.insert_one(order_data)
        # Clear the cart
        session.pop('cart', None)
        flash('Order placed successfully!')
        return redirect(url_for('index'))
    except Exception as e:
        flash('Error processing order. Please try again.')
        return redirect(url_for('checkout_page'))

if __name__ == '__main__':
    app.run()
