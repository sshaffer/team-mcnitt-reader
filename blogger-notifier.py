import os
import sqlite3
import time
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import feedparser
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler

# Load variables from a local .env file (if running outside Docker)
load_dotenv()

# --- LOGGING CONFIGURATION ---
DATA_DIR = "/app/data"
os.makedirs(DATA_DIR, exist_ok=True)
LOG_FILE = os.path.join(DATA_DIR, "blogger_bot.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),  # Outputs to console / Docker logs
        RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
    ]
)

# --- CONFIGURATION FROM ENV ---
BLOG_RSS_URL = "https://mcnittsminions.blogspot.com/feeds/posts/default"
DATA_DIR = "/app/data"

os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "blogger_posts.db")

SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

receivers_env = os.getenv("RECEIVER_EMAILS", "")
RECEIVER_EMAILS = [email.strip() for email in receivers_env.split(",") if email.strip()]

start_date_str = os.getenv("START_DATE", "2026-01-01")
START_DATE = datetime.strptime(start_date_str, "%Y-%m-%d")
# ---------------------

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

def log_startup_config():
    """Logs all loaded environment variables and database status at startup."""
    logging.info("--- Configuration Loaded ---")
    logging.info(f"BLOG_RSS_URL: {BLOG_RSS_URL}")
    logging.info(f"SENDER_EMAIL: {SENDER_EMAIL}")
    logging.info(f"SENDER_PASSWORD: {'***' if SENDER_PASSWORD else 'Not Set'}")
    logging.info(f"RECEIVER_EMAILS: {RECEIVER_EMAILS}")
    logging.info(f"START_DATE: {START_DATE}")

    if os.path.exists(DB_FILE):
        logging.info(f"Found existing SQLite database at: {DB_FILE}")
    else:
        logging.info(f"SQLite database not found at {DB_FILE}. A new one will be created.")

def init_db():
    """Initialize the SQLite database and create the posts table if it doesn't exist."""
    logging.info("Initializing SQLite database connection...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            post_id TEXT PRIMARY KEY,
            title TEXT,
            published_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def is_post_seen(post_id):
    """Check if a post ID already exists in the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM posts WHERE post_id = ?", (post_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def save_post(post_id, title, published_at):
    """Record a processed post into the database so it won't trigger an alert again."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO posts (post_id, title, published_at) VALUES (?, ?, ?)", 
        (post_id, title, published_at)
    )
    conn.commit()
    conn.close()

def send_email_notification(post_title, post_link, post_summary):
    """Sends an email notification to multiple recipients about the new blog post."""
    logging.info(f"Preparing email notification for: '{post_title}'")
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"New Blog Post: {post_title}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(RECEIVER_EMAILS)

    text = f"A new post has been published on McNitt's Minions!\n\nTitle: {post_title}\nLink: {post_link}\n\nSummary:\n{post_summary}"
    html = f"""
    <html>
      <body>
        <h2>New Post on McNitt's Minions!</h2>
        <h3><a href="{post_link}">{post_title}</a></h3>
        <p>{post_summary}</p>
        <hr>
        <p><a href="{post_link}">Click here to read the full post.</a></p>
      </body>
    </html>
    """

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAILS, msg.as_string())
        logging.info("Emails sent successfully!")
    except Exception as e:
        logging.error(f"Failed to send emails: {e}")

def check_for_new_posts():
    """Checks the Blogger RSS feed against the SQLite database and date threshold."""
    logging.info("Checking Blogger RSS feed for new posts...")
    feed = feedparser.parse(BLOG_RSS_URL)
    
    if feed.bozo:
        logging.warning("Feed might be malformed or unreachable.")
        return

    new_posts_found = False

    for entry in feed.entries:
        post_id = entry.id
        post_title = entry.title
        post_link = entry.link
        post_summary = entry.get("summary", "No summary available.")

        if hasattr(entry, "published_parsed") and entry.published_parsed:
            post_date = datetime(*entry.published_parsed[:6])
        else:
            continue

        if post_date < START_DATE:
            continue

        if not is_post_seen(post_id):
            logging.info(f"New post detected: '{post_title}' (Published: {post_date})")
            send_email_notification(post_title, post_link, post_summary)
            save_post(post_id, post_title, post_date.isoformat())
            new_posts_found = True

    if not new_posts_found:
        logging.info("No new posts found.")

if __name__ == "__main__":
    log_startup_config()
    init_db()
    logging.info("Blogger notification bot started. Entering poll loop...")
    
    while True:
        try:
            check_for_new_posts()
        except Exception as e:
            logging.error(f"Unexpected error during check loop: {e}")
            
        logging.info("Waiting 4 hours for the next check...\n")
        time.sleep(14400)