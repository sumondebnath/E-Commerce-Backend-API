# E-Commerce Backend API

A Django REST API backend for an e-commerce platform with authentication, product catalog management, cart workflows, order processing, and admin endpoints.

## Overview

This project provides the server-side foundation for an online store. It is built with Django and Django REST Framework and exposes JSON APIs for:

- user registration, login, logout, and profile management
- product and category browsing
- product reviews and saved products
- shopping cart operations
- checkout and order history
- payment status updates through webhooks
- admin dashboard-style endpoints for store management

## Tech Stack

- Python 3.10+
- Django 6.0.6
- Django REST Framework
- Simple JWT
- Django Filters
- Cloudinary for media storage
- SQLite for local development

## Project Structure

```text
accounts/           # users, auth, profile, addresses
products/           # categories, products, reviews, wishlist
cart/               # cart items and cart operations
orders/             # orders, order items, payments, checkout
E_Commerce_backend/ # project settings and global URLs
```

## Main Features

### Authentication

- register a new user
- log in and receive JWT access/refresh tokens
- refresh access tokens
- log out by blacklisting refresh tokens
- change password
- manage addresses

### Product Catalog

- create and retrieve categories
- list products with search, filtering, and ordering
- view product details
- add product reviews
- save products to a watchlist

### Cart

- add products to the cart
- update quantities
- view cart summary and subtotal
- clear the cart

### Orders

- checkout the cart into an order
- view order history and details
- cancel eligible orders
- update payment status through webhook endpoints

### Admin APIs

- dashboard statistics for admins
- update order status
- update product stock

## Installation

1. Clone the repository.
2. Create and activate a virtual environment.
3. Install dependencies.
4. Configure environment variables.
5. Apply migrations.
6. Run the development server.

### 1) Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Configure environment variables

Create a `.env` file in the project root with values such as:

```env
SECRET_KEY=your-secret-key
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
```

### 4) Apply migrations

```bash
python manage.py migrate
```

### 5) Create a superuser (optional but recommended)

```bash
python manage.py createsuperuser
```

### 6) Start the development server

```bash
python manage.py runserver
```

The API will be available at:

```text
http://127.0.0.1:8000/
```

## API Endpoints

### Authentication

- `POST /api/accounts/register/`
- `POST /api/accounts/login/`
- `POST /api/accounts/login/refresh/`
- `POST /api/accounts/logout/`
- `POST /api/accounts/change-password/`
- `GET/PATCH /api/accounts/profile/`
- `GET/POST/PATCH/DELETE /api/accounts/addresses/`

### Products

- `GET/POST /api/products/categories/`
- `GET/POST /api/products/`
- `GET/PATCH/DELETE /api/products/<id>/`
- `POST /api/products/<id>/save_to_watchlist/`
- `GET/POST /api/products/reviews/`
- `GET/POST /api/products/watchlist/`

### Cart

- `GET/POST /api/cart/`
- `POST /api/cart/clear/`
- `GET /api/cart/summary/`

### Orders

- `POST /api/orders/checkout/`
- `GET /api/orders/`
- `GET /api/orders/<id>/`
- `POST /api/orders/<id>/cancel/`
- `POST /api/orders/payment-webhook/`

### Admin

- `/admin/`
- `/api/admin/dashboard/`

## Application Design

The project follows a modular Django app structure:

- `accounts`: user identity and profile-related logic
- `products`: catalog and review logic
- `cart`: cart state and cart-specific business rules
- `orders`: checkout, order lifecycle, and payment handling

Each app generally contains:

- `models.py` for the database schema
- `serializers.py` for request/response validation
- `views.py` for business logic
- `urls.py` for endpoint registration

## Core Models

- `User`: custom user model using email as the username field
- `Address`: user addresses for shipping or billing
- `Category`: product categories
- `Product`: product item with price, stock, image, and activity status
- `Review`: user review for a product
- `SaveProduct`: saved/watchlisted products
- `CartItem`: product quantity in a user’s cart
- `Order`: purchase record
- `OrderItem`: products inside an order
- `Payment`: payment status and transaction data

## Authentication Flow

The project uses JWT authentication via `rest_framework_simplejwt`.

Typical flow:

1. the client sends credentials to `/api/accounts/login/`
2. the API returns access and refresh tokens
3. the client includes the access token in the `Authorization` header
4. protected endpoints authorize the request using the token

## Learning Path

If you want to understand this codebase thoroughly, read it in this order:

1. `E_Commerce_backend/settings.py`
2. `E_Commerce_backend/urls.py`
3. `accounts/`
4. `products/`
5. `cart/`
6. `orders/`
7. `admin_views.py`

This order helps you understand the system from configuration to business logic.

## Notes

- The project uses SQLite by default for local development.
- Media files are configured to use Cloudinary.
- The project is currently configured for development use with `DEBUG = True`.
- For production, you should strengthen security settings, database configuration, and deployment practices.

## License

This project is intended for learning and development purposes.
