import os
import sqlite3
import time
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import feedparser
from dotenv import load_dotenv

# --- CONFIGURATION ---
BLOG_RSS_URL = "https://mcnittsminions.blogspot.com/feeds/posts/default"

DATA_DIR = "/app/data"
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "blogger_posts.db")

# Email Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


# Pull parameters from environment variables
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

# Split comma-separated emails into a clean list
receivers_env = os.getenv("RECEIVER_EMAILS", "")
RECEIVER_EMAILS = [email.strip() for email in receivers_env.split(",") if email.strip()]

start_date_str = os.getenv("START_DATE", "2026-01-01")
START_DATE = datetime.strptime(start_date_str, "%Y-%m-%d")

# ---------------------

def init_db():
    """Initialize the SQLite database and create the posts table if it doesn't exist."""
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

#def save_post(post_id, title, published_at):
#    """Record a processed post into the database so it won't trigger an alert again."""
#    conn = sqlite3.connect(DB_FILE)
#    cursor = conn.cursor()
#    cursor.execute("OR IGNORE INTO posts (post_id, title, published_at) VALUES (?, ?, ?)" if "OR" in "INSERT OR IGNORE" else 
#                   "INSERT OR IGNORE INTO posts (post_id, title, published_at) VALUES (?, ?, ?)", 
#                   (post_id, title, published_at))
#    conn.commit()
#    conn.close()

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
    print(f"Sending email notifications for: '{post_title}'")
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"New Blog Post: {post_title}"
    msg["From"] = SENDER_EMAIL
    # Join the list with commas for the email header
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
            # Pass the Python list directly to sendmail to deliver to all recipients securely in one go
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAILS, msg.as_string())
        print("Emails sent successfully!")
    except Exception as e:
        print(f"Failed to send emails: {e}")

def check_for_new_posts():
    """Checks the Blogger RSS feed against the SQLite database and date threshold."""
    print("Checking for new blog posts...")
    feed = feedparser.parse(BLOG_RSS_URL)
    
    if feed.bozo:
        print("Warning: Feed might be malformed or unreachable.")
        return

    new_posts_found = False

    for entry in feed.entries:
        post_id = entry.id
        post_title = entry.title
        post_link = entry.link
        post_summary = entry.get("summary", "No summary available.")

        # Parse publication date from feed struct_time
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            post_date = datetime(*entry.published_parsed[:6])
        else:
            continue

        # Skip posts older than the configured start date
        if post_date < START_DATE:
            continue

        # Check if the post is already tracked in SQLite
        if not is_post_seen(post_id):
            send_email_notification(post_title, post_link, post_summary)
            save_post(post_id, post_title, post_date.isoformat())
            new_posts_found = True

    if not new_posts_found:
        print("No new posts found.")

if __name__ == "__main__":
    init_db()
    
    while True:
        try:
            check_for_new_posts()
        except Exception as e:
            print(f"Error during check: {e}")
            
        print("Waiting 4 hours for the next check...\n")
        time.sleep(14400)  # 4 hours in seconds