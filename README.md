# 🚚 SwiftCourier – Courier Aggregator Platform
**SwiftCourier** is a powerful courier aggregation platform that enables businesses to seamlessly manage, optimize, and automate their shipping operations across multiple courier partners from a single interface.

---

## ✨ Features
* 📦 Multi-courier integration
* 🚀 Automated order processing
* 📍 Real-time tracking
* 📊 Shipment analytics & reporting
* 🔄 Task handling using Celery
* 🧾 PDF generation for invoices, labels (WeasyPrint)
* ⚡ High-performance backend with modern tooling

---

## 🛠️ Tech Stack

* **Backend:** Django (Python)
* **Task Queue:** Celery
* **Package Manager:** uv (fast Python package manager)
* **PDF Engine:** WeasyPrint
* **Environment Support:** MSYS2 (for Windows compatibility)

---

## 📦 Requirements

Make sure the following are installed:

* Python (>= 3.10 recommended)
* uv (Python package manager)
* Redis / RabbitMQ (for Celery broker)
* MSYS2 (required for WeasyPrint dependencies on Windows)
* WeasyPrint system dependencies

---

## ⚙️ Installation

### 1. Clone the Repository

```bash
git clone https://github.com/shipnick/swiftcourier.git
cd swiftcourier
```

---

### 2. Install Dependencies using uv
```bash
pip install uv
uv sync
```

---

### 3. Setup Environment Variables
Create a `.env` file:

```env
DEBUG=True
SECRET_KEY=your-secret-key

CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
CELERY_RESULT_BACKEND=rpc://
```

---

### 4. Setup MSYS2 (Windows Only)

WeasyPrint requires native libraries.

* Install MSYS2 from: [https://www.msys2.org/](https://www.msys2.org/) & follow their instructions
* Add MSYS2 `mingw64/bin` to your system PATH

---

### 5. Run Migrations
```bash
uv run manage.py makemigrations
uv run manage.py migrate
```

---

### 6. Start Development Server
```bash
uv run manage.py runserver
```

## 🔄 Start Tailwind
Start Celery worker:
```bash
uv run manage.py tailwind start
```

## 🔄 Running Celery
Start Celery worker:
```bash
uv run celery -A swiftcourier worker -l info -P solo
```

---

## 📄 PDF Generation (WeasyPrint)

SwiftCourier uses **WeasyPrint** for generating:

* Shipping labels
* Invoices
* Reports

If you face issues:
* Ensure GTK libraries are installed (via MSYS2)

---

## 🚀 Deployment Notes
* Use **Gunicorn + Nginx** for production
* Configure Celery with **Redis**
* Use environment variables for secrets
* Ensure system dependencies for WeasyPrint are installed on server
* Full AWS (EC2 + RDS) runbook, including domain + TLS setup: see [DEPLOYMENT.md](DEPLOYMENT.md)

---

## 🧪 Development Tips
* Use logging extensively for async tasks
* Monitor Celery queues for failures
* Cache heavy computations where needed

---

## 💡 About SwiftCourier
SwiftCourier simplifies logistics by bridging businesses with multiple courier providers, enabling faster, smarter, and more reliable deliveries.
