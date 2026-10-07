"""Werkrooster: lokale webapp met duurzame SQLite-opslag."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import sqlite3, json, uuid, datetime, os
import psycopg
import accounts, secrets, time, socket
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parent
DATABASE_URL = os.environ.get('DATABASE_URL')
PORT = int(os.environ.get('PORT', '8765'))
EMPLOYEES = ['Mirek', 'Chris', 'Adam', 'Lee', 'Rene', 'Micheal']



def connect():
    return psycopg.connect(DATABASE_URL)

def initialize():
    with connect() as db:
         with db.cursor() as cur:
            cur.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, employee TEXT NOT NULL, date TEXT NOT NULL,
                title TEXT NOT NULL, location TEXT NOT NULL, start TEXT NOT NULL,
                "end" TEXT NOT NULL, notes TEXT NOT NULL)''')
            cur.execute('CREATE INDEX IF NOT EXISTS jobs_date ON jobs(date)')
            accounts.initialize(db)
        
        

def validate(data):
    if not isinstance(data, dict):
        raise ValueError('Ongeldige invoer.')
    result = {}
    for key, limit in [('employee',40), ('date',10), ('title',160), ('location',200), ('start',5), ('end',5), ('notes',2000)]:
        value = data.get(key, '')
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError('Controleer de ingevulde velden.')
        result[key] = value.strip()
    if result['employee'] not in EMPLOYEES:
        raise ValueError('Kies een werknemer.')
    try:
        date = datetime.date.fromisoformat(result['date'])
        if date.isoformat() != result['date']: raise ValueError()
    except ValueError:
        raise ValueError('Kies een geldige datum.')
    if not result['title']:
        raise ValueError('Vul de werkzaamheden in.')
    if bool(result['start']) != bool(result['end']):
        raise ValueError('Vul beide tijden in of laat beide leeg.')
    if result['start']:
        for field in ['start', 'end']:
            try:
                t = datetime.time.fromisoformat(result[field])
                if t.strftime('%H:%M') != result[field]: raise ValueError()
            except ValueError:
                raise ValueError('Vul een geldige tijd in.')
        if result['end'] <= result['start']:
            raise ValueError('De eindtijd moet later zijn dan de begintijd.')
    return result

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, fmt, *args):
        pass

    def send(self, status, data, content_type='application/json; charset=utf-8', cookie=None):
        body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, (dict,list)) else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        if cookie is not None:
            self.send_header('Set-Cookie', 'rooster_session='+cookie+'; HttpOnly; SameSite=Strict; Path=/; Max-Age='+('604800' if cookie else '0'))
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        hosts = {f'127.0.0.1:{PORT}', f'localhost:{PORT}', 'werkplanning-app.onrender.com'}
        if self.headers.get('Host') not in hosts:
            self.send(403, {'error':'Geen toegang.'}); return False
        origin = self.headers.get('Origin')
        if origin and origin not in {f'https://{h}' for h in hosts}:
            self.send(403, {'error':'Geen toegang.'}); return False
        return True

    def user(self):
        with connect() as db:
            return accounts.current(db, self.headers)

    def json_body(self):
        if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
            raise ValueError('Ongeldig formaat.')
        length = int(self.headers.get('Content-Length','0'))
        if not 0 < length <= 16000:
            raise ValueError('De invoer is te groot of leeg.')
        data = json.loads(self.request_body)
        if not isinstance(data,dict):
            raise ValueError('Ongeldige invoer.')
        return data

    def auth_request(self, path):
        try:
            data = self.json_body()
            token = None
            with connect() as db:
                user = accounts.current(db,self.headers)
                name = data.get('name','')
                if not isinstance(name,str) or len(name)>60:
                    raise ValueError('Ongeldige accountnaam.')
                name = name.strip()
                if path == '/api/setup':
                    # Local-only bootstrap. A deployed version must provision the owner separately.
                   with db.cursor() as cur:
                    cur.execute('SELECT 1 FROM accounts LIMIT 1')
                    account_exists = cur.fetchone()
                if account_exists:
                        self.send(409,{'error':'Het beheerdersaccount bestaat al.'}); return
                        hashed = accounts.password_hash(data.get('password'))
                    
                    
                        
                        db.execute('INSERT INTO accounts VALUES (%s,%s,%s)',('Beheerder','owner',hashed))
                        token = accounts.session(db,'Beheerder')
                        result = {'name':'Beheerder','role':'owner'}
                        self.send(200,result,{'Set-Cookie':accounts.cookie_header(token)})
                        return
                elif path == '/api/login':
                  
                    if not accounts.attempt(db,name.casefold()):
                        self.send(429,{'error':'Te veel pogingen. Probeer het over 15 minuten opnieuw.'}); return
                    with db.cursor() as cur:
                        cur.execute('SELECT * FROM accounts WHERE name=%s', (name,))
                        row = cur.fetchone()
                    if not row or not accounts.verify(data.get('password'),row['password']):
                        db.commit()
                        self.send(401,{'error':'Accountnaam of wachtwoord klopt niet.'}); return
                        db.execute('DELETE FROM login_attempts WHERE name=%s',(name.casefold(),))
                    token = accounts.session(db,row['name'])
                    result = {'name':row['name'],'role':row['role']}
                elif path == '/api/logout':
                    accounts.logout(db,self.headers); token=''; result={'ok':True}
                elif path == '/api/invite':
                    if not user or user['role']!='owner':
                        self.send(403,{'error':'Alleen de beheerder kan toegang regelen.'}); return
                    if name not in EMPLOYEES:
                        raise ValueError('Kies een werknemer.')
                if db.execute('SELECT 1 FROM accounts WHERE name=?',(name,)).fetchone():
                    self.send(409,{'error':'Deze medewerker heeft al een account.'}); return
                invitation = secrets.token_urlsafe(32)
                role = 'editor' if name=='Lee' else 'viewer'
                db.execute('INSERT INTO invitations VALUES (?,?,?,?) ON CONFLICT(name) DO UPDATE SET token=excluded.token,expires=excluded.expires,role=excluded.role',(accounts.digest(invitation),name,role,int(time.time())+48*3600))
                result={'token':invitation,'name':name,'role':role}
                elif path == '/api/join':
                    invitation=data.get('token','')
                if not isinstance(invitation,str) or len(invitation)>200:
                        raise ValueError('Ongeldige uitnodiging.')
                    hashed=accounts.password_hash(data.get('password'))
                    db.execute('BEGIN IMMEDIATE')
                    row=db.execute('SELECT * FROM invitations WHERE token=? AND expires>?',(accounts.digest(invitation),int(time.time()))).fetchone()
                    if not row:
                        raise ValueError('De uitnodiging is verlopen of al gebruikt. Vraag een nieuwe aan de beheerder.')
                    db.execute('INSERT INTO accounts VALUES (?,?,?)',(row['name'],row['role'],hashed))
                    db.execute('DELETE FROM invitations WHERE token=?',(row['token'],))
                    token=accounts.session(db,row['name'])
                    result={'name':row['name'],'role':row['role']}
                elif path == '/api/revoke':
                    if not user or user['role']!='owner':
                        self.send(403,{'error':'Alleen de beheerder kan toegang regelen.'}); return
                    if name not in EMPLOYEES:
                        raise ValueError('Kies een werknemer.')
                    db.execute('DELETE FROM sessions WHERE name=?',(name,))
                    db.execute('DELETE FROM accounts WHERE name=?',(name,))
                    db.execute('DELETE FROM invitations WHERE name=?',(name,))
                    result={'ok':True}
                else:
                    self.send(404,{'error':'Niet gevonden.'}); return
            self.send(200,result,cookie=token)
        except (ValueError,UnicodeDecodeError) as error:
            self.send(400,{'error':str(error) or 'Ongeldige invoer.'})
        except psycopg.Error:
            self.send(503,{'error':'Dit is niet gelukt. Probeer het opnieuw.'})

    def do_GET(self):
        if not self.allowed(): return
        path = self.path.split('?')[0]
        if path == '/':
            self.send(200, (ROOT/'index.html').read_bytes(), 'text/html; charset=utf-8')
        elif path in ['/manifest.webmanifest','/sw.js','/app.js','/icon-192.png','/icon-512.png','/offline.html']:
            types={'/manifest.webmanifest':'application/manifest+json','/sw.js':'text/javascript','/app.js':'text/javascript','/offline.html':'text/html; charset=utf-8'}
            self.send(200,(ROOT/path[1:]).read_bytes(),types.get(path,'image/png'))
        elif path == '/api/me':
            with connect() as db:
                setup=not bool(db.execute('SELECT 1 FROM accounts LIMIT 1').fetchone())
                self.send(200,{'user':accounts.current(db,self.headers),'setup':setup,'local':True})
        elif path == '/api/accounts':
            user=self.user()
            if not user or user['role']!='owner':
                self.send(403,{'error':'Geen toegang.'}); return
            with connect() as db:
                registered=[r['name'] for r in db.execute('SELECT name FROM accounts')]
                self.send(200,{'registered':registered})
        elif path == '/api/invitation':
            invitation=parse_qs(urlsplit(self.path).query).get('token',[''])[0]
            with connect() as db:
                row=db.execute('SELECT name,role FROM invitations WHERE token=? AND expires>?',(accounts.digest(invitation),int(time.time()))).fetchone()
            self.send(200,dict(row)) if row else self.send(400,{'error':'Deze uitnodiging is verlopen of al gebruikt.'})
        elif path == '/api/jobs':
            if not self.user():
                self.send(401,{'error':'Log in om het rooster te bekijken.'}); return
            try:
                with connect() as db:
                    rows = [dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY date,start,title')]
                self.send(200, rows)
            except Exception as e:
                self.send(503, {'error':'Het rooster kan niet worden geladen. Probeer het opnieuw.'})
        else:
            self.send(404, {'error':'Niet gevonden.'})

    def mutate(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<=length<=16000:
                self.send(413,{'error':'De invoer is te groot.'}); return
            self.request_body=self.rfile.read(length)
        except (ValueError,TimeoutError):
            self.send(400,{'error':'Ongeldig verzoek.'}); return
        if not self.allowed(): return
        if self.headers.get('X-Rooster-Request')!='1':
            self.send(403,{'error':'Ongeldig verzoek. Open het rooster opnieuw.'}); return
        path = self.path.split('?')[0]
        if self.command=='POST' and path in ['/api/setup','/api/login','/api/logout','/api/invite','/api/join','/api/revoke']:
            return self.auth_request(path)
        user=self.user()
        if not user:
            self.send(401,{'error':'Log in om het rooster te bekijken.'}); return
        if user['role'] not in ['owner','editor']:
            self.send(403,{'error':'Je mag het rooster alleen bekijken.'}); return
        key = path.removeprefix('/api/jobs/')
        if path != '/api/jobs' and not path.startswith('/api/jobs/'):
            self.send(404, {'error':'Niet gevonden.'}); return
        try:
            if self.command == 'POST' and path != '/api/jobs':
                self.send(404, {'error':'Niet gevonden.'}); return
            if self.command in ['PUT','DELETE']:
                try: uuid.UUID(key)
                except ValueError:
                    self.send(404, {'error':'Werk niet gevonden.'}); return
            if self.command != 'DELETE':
                if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                    self.send(415, {'error':'Ongeldig formaat.'}); return
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 16000:
                    raise ValueError('De invoer is te groot of leeg.')
                data = validate(json.loads(self.request_body))
            with connect() as db:
                with db.cursor()as cur:
                    if self.command == 'DELETE':
                       cursor = cur.execute('DELETE FROM jobs WHERE id=%s', (key,))
                    elif self.command == 'PUT':
                    cursor = cur.execute('UPDATE jobs SET employee=%s,date=%s,title=%s,location=%s,start=%s,end=%s,notes=%s WHERE id=%s', (*data.values(),key))
                    else:
                    key = str(uuid.uuid4())
                    cursor = cur.execute('INSERT INTO jobs VALUES (%s,%s,%s,%s,%s,%s,%s,%s)', (key,*data.values()))
                        db.commit()
                    if self.command != 'POST' and not cursor.rowcount:
                    self.send(404, {'error':'Dit werk bestaat niet meer. Ververs het rooster.'}); return
            self.send(200, {'id':key} if self.command == 'DELETE' else {'id':key, **data})
        except (ValueError, UnicodeDecodeError) as error:
            self.send(400, {'error': str(error) or 'Ongeldige invoer.'})
        except psycopg.Error:
            self.send(503, {'error':'Opslaan is niet gelukt. Je invoer blijft staan; probeer opnieuw.'})

    do_POST = mutate
    do_PUT = mutate
    do_DELETE = mutate

class RoosterServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

if __name__ == '__main__':
    initialize()
    server = RoosterServer(('0.0.0.0',PORT), Handler)
    print(f'Werkrooster gestart: http://127.0.0.1:{PORT}', flush=True)
    server.serve_forever()
