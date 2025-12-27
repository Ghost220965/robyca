import os, threading, time, requests
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# --- CONFIGURARE BAZĂ DE DATE (NEON.TECH) ---
# Am înlocuit link-ul de MySQL cu cel de PostgreSQL de la Neon
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_boMmapeV25cy@ep-sparkling-hill-a4mf9956-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- CREARE AUTOMATĂ TABELE ---
# Această secțiune verifică și creează tabelele pe Neon la prima pornire
with app.app_context():
    db.create_all()

# Stocare în RAM pentru sesiuni și control procese
active_sessions = {}  
running_processes = {} 

# --- MODELE (Rămân neschimbate) ---
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_text = db.Column(db.String(255), nullable=False)

class UserToken(db.Model):
    __tablename__ = 'user_tokens'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100))
    val = db.Column(db.Text, nullable=False)

class AutotyperState(db.Model):
    __tablename__ = 'autotyper_state'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    payload = db.Column(db.Text)
    payload_shift = db.Column(db.Text)
    channel_id = db.Column(db.String(255))
    target_id = db.Column(db.String(255))
    delay_ms = db.Column(db.Integer, default=1500)
    is_loop = db.Column(db.Boolean, default=False)
    is_typing = db.Column(db.Boolean, default=False)
    start_time = db.Column(db.Float)

# --- HELPERS (MODIFICAT PENTRU RENDER) ---
def get_client_ip():
    # Pe Render, IP-ul real se ia din X-Forwarded-For
    x_forwarded = request.headers.get('X-Forwarded-For')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.remote_addr

def get_current_user_id():
    return active_sessions.get(get_client_ip())

def cloud_worker(user_id, token, channel_id, delay, messages, is_loop, target_id, is_typing_enabled):
    with app.app_context():
        while True:
            if user_id not in running_processes or not running_processes[user_id]:
                break
            for m in messages:
                if user_id not in running_processes or not running_processes[user_id]: return
                
                if is_typing_enabled:
                    try: requests.post(f"https://discord.com/api/v9/channels/{channel_id}/typing", 
                                       headers={'Authorization': token}, timeout=2)
                    except: pass
                
                content = f"<@{target_id}> {m}" if target_id else m
                try:
                    requests.post(f"https://discord.com/api/v9/channels/{channel_id}/messages", 
                                  headers={'Authorization': token}, json={'content': content}, timeout=5)
                except: pass
                
                time.sleep(int(delay) / 1000)
            
            if not is_loop:
                running_processes[user_id] = False
                break

# --- RUTE PAGINI (Rămân la fel) ---
@app.route('/')
def login_page():
    if get_current_user_id(): return redirect(url_for('autotyper'))
    return render_template('login.html')

@app.route('/register_page')
def register_page():
    if get_current_user_id(): return redirect(url_for('autotyper'))
    return render_template('register.html')

@app.route('/autotyper')
def autotyper():
    if not get_current_user_id(): return redirect(url_for('login_page'))
    return render_template('autotyper.html')

@app.route('/config')
def config():
    if not get_current_user_id(): return redirect(url_for('login_page'))
    return render_template('index.html')

@app.route('/console')
def console():
    if not get_current_user_id(): return redirect(url_for('login_page'))
    return render_template('console.html')

@app.route('/settings')
def settings():
    if not get_current_user_id(): return redirect(url_for('login_page'))
    return render_template('settings.html')

# --- API (Rămân la fel) ---
@app.route('/login_api', methods=['POST'])
def login_api():
    data = request.json
    user = User.query.filter_by(username=data['username'], password_text=data['password']).first()
    if user:
        active_sessions[get_client_ip()] = user.id
        return jsonify({'success': True})
    return jsonify({'error': 'INVALID_CREDENTIALS'}), 401

@app.route('/register', methods=['POST'])
def register():
    if get_current_user_id(): return jsonify({'error': 'ALREADY_LOGGED_IN'}), 403
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'USERNAME_TAKEN'}), 400
    new_user = User(username=data['username'], password_text=data['password'])
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/logout_api', methods=['POST'])
def logout_api():
    ip = get_client_ip()
    if ip in active_sessions: del active_sessions[ip]
    return jsonify({'success': True})

@app.route('/validate_token', methods=['POST'])
def validate_token():
    tk = request.json.get('token')
    try:
        res = requests.get("https://discord.com/api/v9/users/@me", headers={'Authorization': tk}, timeout=5)
        if res.status_code == 200: return jsonify({'valid': True, 'user': res.json()['username']})
    except: pass
    return jsonify({'valid': False})

@app.route('/save_token', methods=['POST'])
def save_token():
    u_id = get_current_user_id()
    if not u_id: return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    new_tk = UserToken(user_id=u_id, name=data['name'], val=data['val'])
    db.session.add(new_tk)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/get_tokens')
def get_tokens():
    u_id = get_current_user_id()
    if not u_id: return jsonify([])
    tokens = UserToken.query.filter_by(user_id=u_id).all()
    return jsonify([{'name': t.name, 'val': t.val} for t in tokens])

@app.route('/delete_token', methods=['POST'])
def delete_token():
    u_id = get_current_user_id()
    if not u_id: return jsonify({'error': 'Unauthorized'}), 401
    tk = UserToken.query.filter_by(user_id=u_id, name=request.json['name']).first()
    if tk:
        db.session.delete(tk)
        db.session.commit()
    return jsonify({'success': True})

@app.route('/get_autotyper')
def get_autotyper():
    u_id = get_current_user_id()
    if not u_id: return jsonify({}), 401
    s = AutotyperState.query.filter_by(user_id=u_id).first()
    return jsonify({
        'payload': s.payload if s else "",
        'payload_shift': s.payload_shift if s else "",
        'channel_id': s.channel_id if s else "",
        'target_id': s.target_id if s else "",
        'delay_ms': s.delay_ms if s else 1500,
        'is_loop': s.is_loop if s else False,
        'is_typing': s.is_typing if s else False,
        'is_running': running_processes.get(u_id, False),
        'start_time': s.start_time if s else 0
    })

@app.route('/save_autotyper', methods=['POST'])
def save_autotyper():
    u_id = get_current_user_id()
    if not u_id: return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    s = AutotyperState.query.filter_by(user_id=u_id).first()
    if not s:
        s = AutotyperState(user_id=u_id)
        db.session.add(s)
    
    if 'payload' in data: s.payload = data['payload']
    if 'payload_shift' in data: s.payload_shift = data['payload_shift']
    if 'channel_id' in data: s.channel_id = data['channel_id']
    if 'target_id' in data: s.target_id = data['target_id']
    if 'delay' in data: s.delay_ms = int(data['delay'])
    if 'loop' in data: s.is_loop = data['loop']
    if 'typing' in data: s.is_typing = data['typing']
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/start_cloud', methods=['POST'])
def start_cloud():
    u_id = get_current_user_id()
    if not u_id: return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    running_processes[u_id] = True
    s = AutotyperState.query.filter_by(user_id=u_id).first()
    if s:
        s.start_time = time.time()
        db.session.commit()
    
    threading.Thread(target=cloud_worker, args=(
        u_id, data['token'], data['channel_id'], data['delay'], 
        data['messages'], data['loop'], data['target_id'], data['typing']
    )).start()
    return jsonify({'success': True})

@app.route('/stop_cloud', methods=['POST'])
def stop_cloud():
    u_id = get_current_user_id()
    if u_id:
        running_processes[u_id] = False
    return jsonify({'success': True})

@app.route('/send', methods=['POST'])
def send_message():
    if not get_current_user_id(): return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    try:
        res = requests.post(f"https://discord.com/api/v9/channels/{data['channel_id']}/messages", 
                           headers={'Authorization': data['token']}, 
                           json={'content': data['content']}, timeout=5)
        return jsonify({'success': res.ok})
    except:
        return jsonify({'error': 'Failed'}), 500

@app.route('/get_status')
def get_status():
    u_id = get_current_user_id()
    return jsonify({'is_running': running_processes.get(u_id, False)})

@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()

if __name__ == '__main__':
    app.run(debug=True)
