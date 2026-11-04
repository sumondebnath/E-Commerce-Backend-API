# E-Commerce Backend API

A Django REST Framework backend for an e-commerce store. It provides JWT authentication, a product catalog, reviews and a watchlist, a persistent cart, transactional checkout, order and payment handling, and a staff-only admin API.

The API is JSON-first and is intended to be consumed by a separate frontend (SPA or mobile app). Django's built-in admin site is also available for day-to-day data management.

## Features

- Email-based user accounts with JWT access and refresh tokens
- Profile management, password changes, and saved addresses
- Categories and products with search, filtering, ordering, and image uploads
- Product reviews (one per user per product) and a saved-products watchlist
- Persistent cart with stock-aware add/update operations and a summary endpoint
- Atomic checkout that validates stock, resolves shipping, creates the order, records payment, and empties the cart
- Order history, order details, and cancellation with automatic restocking and payment refund state
- Signed payment webhooks with status-transition validation and idempotent retries
- Staff-only admin API for dashboard metrics, orders, products, stock, and categories
- CORS support, request throttling, and production security settings
- Health-check endpoint for uptime monitoring

## Tech Stack

- Python 3.12+ (required by Django 6)
- Django 6.x
- Django REST Framework 3.18
- Simple JWT
- django-filter
- django-cors-headers
- Cloudinary for media storage
- WhiteNoise for static file serving
- SQLite for local development, PostgreSQL in production
- Gunicorn and `vercel.json` for deployment

## Project Structure

```text
accounts/            # users, authentication, profiles, addresses
products/            # categories, products, reviews, watchlist
cart/                # cart items and cart operations
orders/              # checkout, order lifecycle, payments, shipping pricing
custom_admin/        # staff-only admin REST API (active implementation)
E_Commerce_backend/  # project settings, root URLs, WSGI/ASGI entry points
staticfiles/         # collected static assets served by WhiteNoise
manage.py            # Django management entry point
vercel.json          # Vercel deployment configuration
```

Application modules follow the same pattern:

- `models.py` — database schema
- `serializers.py` — request validation and response shaping
- `views.py` — API behavior and business rules
- `urls.py` — route registration
- `tests.py` — API and business-logic tests

### Admin implementation

The admin REST API is served by `custom_admin/` and mounted at `/api/admin/`. It uses serializers and shared order services to validate transitions and restock inventory safely.

Repository notes:

- `admin_config.py` — **used**. It is imported by `E_Commerce_backend/urls.py` to set the Django admin site branding.
- `admin_urls.py` — **not used**. Its only include in the root URLconf is commented out in favor of `custom_admin.urls`.
- `admin_views.py` — **not used**. It is an older admin implementation superseded by `custom_admin/views.py`, which adds serializer validation, order-status transition rules, automatic restocking, and payment settlement.
- `custom_admin/config.py` — **not used** and duplicates the branding already provided by `admin_config.py`.

Keeping both implementations around creates a maintenance and security risk because the old views bypass checks that the active admin API enforces.

## Getting Started

### Prerequisites

- Python 3.12 or newer
- pip and venv
- A Cloudinary account (for image uploads)
- PostgreSQL (production only; SQLite is used locally by default)

### 1. Clone the repository

```bash
git clone <repository-url>
cd E-Commerce-Backend-API
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` intentionally leaves packages unpinned. Pin versions for reproducible production builds.

### 4. Configure environment variables

```bash
cp .env.example .env
```

Then edit `.env` and provide at least `SECRET_KEY` and the Cloudinary credentials.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `SECRET_KEY` | Yes | — | Django secret key and JWT signing key |
| `DEBUG` | No | `True` | Enables debug mode and local CORS origins |
| `DATABASE_URL` | When `DEBUG=False` | SQLite in debug | PostgreSQL connection URL |
| `CLOUDINARY_CLOUD_NAME` | For media uploads | — | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | For media uploads | — | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | For media uploads | — | Cloudinary API secret |
| `CORS_ALLOWED_ORIGINS` | Production | `[]` | Comma-separated frontend origins |
| `PAYMENT_WEBHOOK_SECRET` | Production | `""` | HMAC secret used to verify webhooks |
| `FREE_SHIPPING_THRESHOLD` | No | `100.00` | Subtotal at which shipping becomes free |
| `FLAT_SHIPPING_COST` | No | `5.00` | Flat shipping fee below the threshold |

Example `.env` for local development:

```env
SECRET_KEY=change-me
DEBUG=True

CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret

CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
PAYMENT_WEBHOOK_SECRET=local-dev-secret
FREE_SHIPPING_THRESHOLD=100.00
FLAT_SHIPPING_COST=5.00
```

When `DEBUG=False`, `DATABASE_URL` is mandatory and the project refuses to start without it.

### 5. Apply migrations

```bash
python manage.py migrate
```

### 6. Create a superuser

A superuser is required to access `/admin/`. Staff rights (`is_staff`) are required for the `/api/admin/` endpoints.

```bash
python manage.py createsuperuser
```

### 7. Run the development server

```bash
python manage.py runserver
```

The API will be available at:

```text
http://127.0.0.1:8000/
```

Verify it is running:

```bash
curl http://127.0.0.1:8000/api/health/
```

```json
{"status": "ok", "message": "E-Commerce Backend Service is running successfully."}
```

## API Reference

All endpoints are prefixed with `/api/`. Unless stated otherwise, requests must include:

```http
Authorization: Bearer <access-token>
Content-Type: application/json
```

List endpoints are paginated with a default page size of 20.

### Authentication and Accounts

Base path: `/api/accounts/`

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/register/` | Public | Create an account; returns the user and a token pair |
| `POST` | `/login/` | Public | Log in with `email` and `password`; returns tokens and user |
| `POST` | `/login/refresh/` | Public | Exchange a refresh token for a new access token |
| `POST` | `/logout/` | User | Blacklist the supplied refresh token |
| `GET` `PATCH` | `/profile/` | User | Retrieve or update the current user's profile |
| `POST` | `/change-password/` | User | Change password using `old_password`, `new_password`, `new_password2` |
| `GET` `POST` | `/addresses/` | User | List or create the current user's addresses |
| `GET` `PUT` `PATCH` `DELETE` | `/addresses/{id}/` | User | Retrieve, replace, update, or delete an address |

Notes:

- Users authenticate with **email**, not username.
- Registration, login, and password changes are throttled at 10 requests per minute per client.
- Addresses with `is_default=True` automatically clear the previous default of the same address type.

### Products

Base path: `/api/products/`

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| `GET` `POST` | `/categories/` | Public read; staff write | List or create categories |
| `GET` `PUT` `PATCH` `DELETE` | `/categories/{slug}/` | Public read; staff write | Category detail, update, or delete (lookup by slug) |
| `GET` `POST` | `/` | Public read; staff write | List or create products |
| `GET` `PUT` `PATCH` `DELETE` | `/{id}/` | Public read; staff write | Product detail, update, or delete |
| `POST` | `/{id}/save_to_watchlist/` | User | Add a product to the current user's watchlist |
| `GET` `POST` | `/reviews/` | User | List reviews or create a review |
| `GET` `PUT` `PATCH` `DELETE` | `/reviews/{id}/` | User | Retrieve, update, or delete a review (own reviews only) |
| `GET` `POST` | `/watchlist/` | User | List or add saved products |
| `DELETE` | `/watchlist/{id}/` | User | Remove a saved product |

Product list query parameters:

| Parameter | Example | Description |
| --- | --- | --- |
| `search` | `?search=shirt` | Search name and description |
| `category` | `?category=3` | Filter by category ID |
| `is_active` | `?is_active=true` | Filter by active status |
| `ordering` | `?ordering=-price` | Order by `price`, `stock_count`, `created_at`, or `updated_at` |
| `page` | `?page=2` | Pagination |

Inactive products are hidden from non-staff users. Product creation and updates accept JSON or multipart form data for image uploads.

### Cart

Base path: `/api/cart/`

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| `GET` `POST` | `/` | User | List cart items or add a product |
| `GET` `PUT` `PATCH` `DELETE` | `/{id}/` | User | Retrieve, update quantity, or remove a cart item |
| `POST` | `/clear/` | User | Remove all items from the cart |
| `GET` | `/summary/` | User | Return item count, total quantity, and subtotal |

`POST /api/cart/` is additive. Send `product_id` and an optional `quantity` (default `1`); adding an existing product increases its quantity. Quantities are validated against current stock inside a database transaction.

### Orders and Payments

Base path: `/api/orders/`

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/checkout/` | User | Convert the cart into an order |
| `GET` | `/` | User | List the current user's orders |
| `GET` | `/{id}/` | User | Order detail with items and payment (UUID) |
| `POST` | `/{id}/cancel/` | User | Cancel a `PENDING` or `PROCESSING` order |
| `POST` | `/payment-webhook/` | Signed webhook | Update payment status from a payment gateway |

#### Checkout

Send either a saved `address_id` or all shipping fields, plus a `payment_method`:

```json
{
  "address_id": 4,
  "payment_method": "stripe"
}
```

Or:

```json
{
  "shipping_full_name": "Jane Doe",
  "shipping_street_address": "123 Main St",
  "shipping_city": "Dhaka",
  "shipping_state": "Dhaka",
  "shipping_postal_code": "1207",
  "shipping_country": "Bangladesh",
  "payment_method": "stripe"
}
```

Checkout is atomic:

1. Locks the user's cart rows and the affected product rows.
2. Rejects unavailable or insufficient stock before writing anything.
3. Resolves the shipping address snapshot.
4. Calculates shipping server-side (free at or above `FREE_SHIPPING_THRESHOLD`, otherwise `FLAT_SHIPPING_COST`).
5. Creates the order and order items, deducts stock, creates a pending payment, and clears the cart.

On success it returns `201 Created` with the full order representation. A client-supplied shipping cost is never trusted.

#### Payment webhook

The gateway sends the raw JSON body and an HMAC-SHA256 signature header:

```http
X-Webhook-Signature: sha256=<hex-digest>
```

```json
{
  "order_id": "0f2b4c1e-8a4d-4f7e-9c1a-2d3e4f5a6b7c",
  "transaction_id": "txn_123456",
  "status": "Completed",
  "amount": "105.00"
}
```

The signature is computed over the raw request body using `PAYMENT_WEBHOOK_SECRET`. In production, a missing secret or invalid signature is rejected. If `amount` is supplied, it must match the payment amount.

Payment status transitions:

```text
Pending    -> Completed | Failed
Completed  -> Refunded
Failed     -> (terminal)
Refunded   -> (terminal)
```

A `Completed` payment moves the order to `PROCESSING`. A `Failed` or `Refunded` payment cancels and restocks the order only if it has not shipped. Repeated callbacks with the same status are idempotent.

### Admin API

Base path: `/api/admin/`

All admin endpoints require an authenticated user with `is_staff=True`.

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/dashboard/` | Total orders, non-staff users, and completed revenue |
| `GET` | `/orders/` | Paginated orders with user, status, total, and item count |
| `PATCH` | `/orders/{uuid}/status/` | Change order status using the allowed transitions |
| `GET` `POST` | `/products/` | List products (optional `?search=`) or create one |
| `PATCH` `DELETE` | `/products/{id}/` | Update or delete a product |
| `PATCH` | `/products/{id}/stock/` | Set a non-negative stock count |
| `GET` `POST` | `/categories/` | List or create categories |
| `GET` `PATCH` `DELETE` | `/categories/{id}/` | Retrieve, update, or delete a category |

Allowed order status transitions:

```text
PENDING    -> PROCESSING | CANCELLED
PROCESSING -> SHIPPED | CANCELLED
SHIPPED    -> DELIVERED
DELIVERED  -> (terminal)
CANCELLED  -> (terminal)
```

Cancelling an order through the admin API restocks inventory (once, tracked by `Order.inventory_released`) and refunds a completed payment.

### Health Check

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/api/health/` | Public | Returns `{"status": "ok", ...}` |

### Django Admin

Django's built-in admin site is available at `/admin/` for superusers. Site branding is configured in `admin_config.py`.

## Authentication Flow

The project uses `rest_framework_simplejwt`.

1. Register or log in to receive an access token and a refresh token.
2. Send the access token with protected requests:

   ```http
   Authorization: Bearer <access-token>
   ```

3. When the access token expires, call `/api/accounts/login/refresh/` with the refresh token.
4. On logout, send the refresh token to `/api/accounts/logout/` so it is blacklisted.

Token settings:

| Setting | Value |
| --- | --- |
| Access token lifetime | 1 day |
| Refresh token lifetime | 7 days |
| Refresh rotation | Enabled |
| Blacklist after rotation | Enabled |
| Header type | `Bearer` |
| Algorithm | `HS256` |

All endpoints require authentication by default except where a view explicitly allows public access (product/category reads, registration, login, token refresh, health check, and the signed payment webhook).

## Data Model

| Model | Key fields | Relationships |
| --- | --- | --- |
| `User` | UUID `id`, unique `email`, names, `is_staff`, `created_at` | Has many addresses, orders, reviews, cart items, saved products |
| `Address` | `address_type`, street, city, state, postal code, country, `is_default` | Belongs to a user |
| `Category` | unique `name`, unique `slug`, `description` | Has many products |
| `Product` | name, description, price, stock, image, `is_active` | Belongs to a category; has reviews, cart items, order items |
| `Review` | rating (1–5), comment, `created_at` | One per user per product |
| `SaveProduct` | `saved_at` | One per user per product (watchlist) |
| `CartItem` | quantity, timestamps | One per user per product |
| `Order` | UUID `id`, status, subtotal, shipping, total, shipping snapshot, `inventory_released` | Belongs to a user; has many items and one payment |
| `OrderItem` | product name snapshot, quantity, purchase price | Belongs to an order |
| `Payment` | method, status, unique transaction ID, amount, `paid_at` | One-to-one with an order |

## Business Rules

- Product and category writes require `is_staff`; reads are public.
- Reviews and watchlist entries are unique per user and product.
- Cart additions and checkout use row locks to prevent overselling under concurrent requests.
- Shipping is always calculated server-side from the subtotal.
- Orders are created only through checkout, never through a direct model write.
- Cancellation and failed payments restock inventory at most once.
- Payment and order status changes follow explicit transition maps.
- A cancelled order cannot be completed by a late payment callback.
- Pagination defaults to 20 items per page.
- Throttling defaults: 60 requests/minute for anonymous clients, 1,000/day for authenticated users, and 10/minute for auth actions.

## Running Tests

Each app includes tests for authentication, cart, orders, products, and the admin API.

```bash
python manage.py test
```

Run a single app's tests:

```bash
python manage.py test custom_admin
python manage.py test orders
```

Run Django's system checks:

```bash
python manage.py check
```

## Deployment

The repository includes a `vercel.json` that routes all requests to `E_Commerce_backend/wsgi.py` using the Vercel Python runtime.

Production checklist:

1. Set `DEBUG=False`.
2. Provide a strong `SECRET_KEY`.
3. Provide `DATABASE_URL` for PostgreSQL; startup fails without it in production.
4. Set Cloudinary credentials for media storage.
5. Set `CORS_ALLOWED_ORIGINS` to the deployed frontend origin(s).
6. Set a strong `PAYMENT_WEBHOOK_SECRET` and register the webhook URL with your payment provider.
7. Run migrations as part of the deploy pipeline:

   ```bash
   python manage.py migrate
   ```

8. Collect static files for WhiteNoise:

   ```bash
   python manage.py collectstatic --noinput
   ```

9. Serve through Gunicorn (`gunicorn E_Commerce_backend.wsgi:application`) or the Vercel WSGI entry point.

When `DEBUG=False`, the project automatically enables SSL redirects, secure cookies, HSTS, and the proxy SSL header.

## Notes and Limitations

- SQLite is used automatically for local development when `DATABASE_URL` is absent.
- Media files are stored on Cloudinary; local `MEDIA_ROOT` is only used for development URLs.
- The built-in Django admin and the custom admin REST API are separate interfaces to the same models.
- The project does not include a built-in frontend, email delivery, or a real payment-gateway client; the gateway integration is represented by the signed webhook contract.
- Pin dependency versions before deploying to production.

## Learning Path

To understand the codebase, read it in this order:

1. `E_Commerce_backend/settings.py`
2. `E_Commerce_backend/urls.py`
3. `accounts/`
4. `products/`
5. `cart/`
6. `orders/models.py` and `orders/services.py`
7. `orders/views.py` (checkout and webhook logic)
8. `custom_admin/`

## License

Released under the MIT License. See [LICENSE](LICENSE).
