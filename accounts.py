"""Accounts, sessies en uitnodigingen; geen wachtwoorden in platte tekst."""
import hashlib
import hmac
import secrets
import time
from http.cookies import SimpleCookie

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def password_hash(password, salt=None):
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError('Kies een wachtwoord van minimaal 12 en maximaal 256 tekens.')
    salt = salt or secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    return salt + ':' + value

def verify(password, stored):
    try:
        return hmac.compare_digest(password_hash(password, stored.split(':')[0]), stored)
    except (ValueError, AttributeError):
        return False

def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS accounts (
      name TEXT PRIMARY KEY COLLATE NOCASE,
      role TEXT NOT NULL CHECK(role IN ('owner','editor','viewer')),
      password TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sessions (
      token TEXT PRIMARY KEY, name TEXT NOT NULL, expires INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS invitations (
      token TEXT PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE,
      role TEXT NOT NULL, expires INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS login_attempts (
      name TEXT PRIMARY KEY, count INTEGER NOT NULL, until INTEGER NOT NULL
    );
    ''')
row = db.execute("SELECT name FROM accounts WHERE name=?", ("Beheerder",)).fetchone()
if not row: db.execute("INSERT INTO accounts (name, role, password) VALUES (?, ?, ?)",
                   ("Beheerder", "owner", password_hash("NieuwWachtwoord123!")))
db.execute("UPDATE accounts SET password=? WHERE name=?", (password_hash("NieuwWachtwoord123!"), "Beheerder"))

def current(db, headers):
    cookies = SimpleCookie()
    try:
        cookies.load(headers.get('Cookie', ''))
        token = cookies['rooster_session'].value
    except Exception:
        return None
    row = db.execute('SELECT a.name,a.role FROM sessions s JOIN accounts a ON a.name=s.name WHERE s.token=? AND s.expires>?', (digest(token),int(time.time()))).fetchone()
    return dict(row) if row else None

def session(db, name):
    token = secrets.token_urlsafe(32)
    db.execute('DELETE FROM sessions WHERE expires<=?', (int(time.time()),))
    db.execute('INSERT INTO sessions VALUES (?,?,?)', (digest(token),name,int(time.time())+7*86400))
    return token

def logout(db, headers):
    cookies = SimpleCookie()
    try:
        cookies.load(headers.get('Cookie',''))
        db.execute('DELETE FROM sessions WHERE token=?',(digest(cookies['rooster_session'].value),))
    except Exception:
        pass

def attempt(db, name):
    now = int(time.time())
    db.execute('DELETE FROM login_attempts WHERE until<=?', (now,))
    row = db.execute('SELECT count FROM login_attempts WHERE name=?',(name,)).fetchone()
    if row and row['count'] >= 8:
        return False
    db.execute('INSERT INTO login_attempts VALUES (?,1,?) ON CONFLICT(name) DO UPDATE SET count=count+1',(name,now+900))
    return True
