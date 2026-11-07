# 🚀 راهنمای جامع استقرار و دیپلوی NEXUS روی سرور مجازی (VPS)

این راهنما برای راه‌اندازی، اتصال دامنه، گواهی SSL، و نحوه آپدیت ۱-دستوری بدون پاک شدن اطلاعات روی سرور لینوکس (اوبونتو / دبیان) آماده شده است.

---

## 📋 مشخصات حداقلی سرور (VPS)
* **سیستم‌عامل پیشنهادی:** Ubuntu 22.04 LTS یا Ubuntu 24.04 LTS
* **سخت‌افزار:** حداقل ۱ هسته پردازنده (CPU) و ۱ یا ۲ گیگابایت رم (RAM)
* **دسترسی:** دسترسی روت (`root` یا دسترسی `sudo`)

---

## 🛠 روش اول: استقرار با Docker Compose (پیشنهادی و بسیار ساده)

### ۱. نصب پیش‌نیازها روی سرور
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl docker.io docker-compose-v2
sudo systemctl enable --now docker
```

### ۲. کلون کردن پروژه
```bash
git clone https://github.com/parhamje/nexus-freelance-agent.git /opt/freelance-agent
cd /opt/freelance-agent
```

### ۳. ایجاد فایل تنظیمات محیطی (.env)
```bash
cp .env.example .env
# ساخت کلید رمزنگاری امن برای توکن‌ها:
SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
sed -i "s|FREELANCE_SECRET_KEY=.*|FREELANCE_SECRET_KEY=$SECRET|" .env
```

### ۴. اجرای برنامه با داکر
```bash
docker compose up -d --build
```
> **تضمین ماندگاری دیتا:** اطلاعات دیتابیس در ولوم دائمی `pgdata` داکر ذخیره می‌شود. بنابراین در هر بار ریست یا آپدیت، هیچ داده‌ای پاک نخواهد شد.

---

## ⚙️ روش دوم: استقرار مستقیم (Native Systemd)

اگر نمی‌خواهید از داکر استفاده کنید و ترجیح می‌دهید برنامه مستقیماً با پایتون و Systemd اجرا شود:

```bash
git clone https://github.com/parhamje/nexus-freelance-agent.git /opt/freelance-agent
cd /opt/freelance-agent
chmod +x scripts/*.sh update.sh

# اجرای اسکریپت راه‌اندازی خودکار لینوکس (نصب پایتون، venv و وابستگی‌ها):
sudo ./scripts/setup_linux.sh

# کپی سرویس Systemd برای اجرای مداوم پس‌زمینه و اجرای خودکار پس از ریبوت:
sudo cp systemd/freelance-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now freelance-agent
sudo systemctl status freelance-agent
```

---

## 🌐 اتصال به دامنه، Nginx و SSL رایگان (HTTPS)

برای اینکه وب‌سایت با آدرس دامنه شما باز شود و سوکت تلگرام و وب بدون مشکل کار کنند:

### ۱. نصب Nginx و Certbot
```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

### ۲. تنظیم کانفیگ Nginx
فایل آماده کانفیگ را فعال کنید:
```bash
sudo cp /opt/freelance-agent/systemd/nginx-nexus.conf /etc/nginx/sites-available/nexus.conf
# دامنه خود را در این فایل جایگزین کنید:
sudo nano /etc/nginx/sites-available/nexus.conf
# فعال‌سازی سایت:
sudo ln -s /etc/nginx/sites-available/nexus.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### ۳. دریافت SSL رایگان با یک دستور
```bash
sudo certbot --nginx -d your-domain.com
```

---

## 🔄 نحوه آپدیت سرور فقط با ۱ دستور (Zero Data Loss)

هر زمان که ویژگی جدیدی به گیت‌هاب اضافه کردید، کافیست وارد پوشه پروژه در سرور شوید و دستور زیر را بزنید:

```bash
./update.sh
```

### عملکرد اسکریپت `update.sh`:
1. **بکاپ خودکار دیتابیس:** قبل از هر کاری، یک نسخه کامل از دیتابیس در پوشه `backups/` ذخیره می‌کند.
2. **دریافت آخرین کدها:** دستور `git pull origin main` را به صورت خودکار اجرا می‌کند.
3. **مایگریشن ایمن:** تغییرات جداول جدید دیتابیس را بدون دست زدن به اطلاعات قبلی ثبت می‌کند (`alembic upgrade head`).
4. **ریستارت سرویس:** سرویس را مجدداً بارگذاری کرده و وضعیت سلامت را چک می‌کند.

**نتیجه:** تمام حساب‌های کاربری، تنظیمات ثبت‌شده، توکن تلگرام و چت‌های متصل کاملاً حفظ می‌شوند و هیچ‌چیز از صفر شروع نخواهد شد!

---

## 👤 اولین ورود و فرم اطلاعات اولیه (Onboarding)
* به آدرس سرور یا دامنه خود بروید.
* اکانت‌های تست قبلی همگی حذف شده‌اند؛ با زدن تب **«ثبت‌نام جدید»**، نام کاربری و رمز عبور اختصاصی خود را بسازید.
* بلافاصله پس از ثبت‌نام، **فرم راه‌اندازی اولیه و مهارت‌ها** برای شما باز می‌شود تا تخصص‌ها، مهارت‌های کلیدی و پلتفرم‌های مدنظرتان را تعیین کنید.
