from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import hashlib
import jwt
import datetime
from functools import wraps
import os

app = Flask(__name__)
CORS(app)

# Secret key untuk JWT
app.config['SECRET_KEY'] = 'hackathon_voting_secret_2024'

# Database initialization
def init_db():
    conn = sqlite3.connect('voting_system.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'voter',
            has_voted INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Candidates table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            team_members TEXT,
            project_title TEXT,
            votes_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Votes table for tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            candidate_id INTEGER,
            voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (candidate_id) REFERENCES candidates (id)
        )
    ''')
    
    # Insert default admin if not exists
    cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        admin_password = hashlib.sha256('admin123'.encode()).hexdigest()
        cursor.execute('''
            INSERT INTO users (username, password, role) 
            VALUES (?, ?, ?)
        ''', ('admin', admin_password, 'admin'))
    
    # Insert sample candidates if not exists
    cursor.execute('SELECT COUNT(*) FROM candidates')
    if cursor.fetchone()[0] == 0:
        sample_candidates = [
            ('Team Alpha', 'AI-powered learning platform', 'John, Jane, Bob', 'EduAI Assistant'),
            ('Team Beta', 'Blockchain voting system', 'Alice, Charlie, David', 'SecureVote'),
            ('Team Gamma', 'Environmental monitoring app', 'Eve, Frank, Grace', 'EcoWatch'),
            ('Team Delta', 'Healthcare chatbot', 'Henry, Iris, Jack', 'MediBot'),
        ]
        
        for candidate in sample_candidates:
            cursor.execute('''
                INSERT INTO candidates (name, description, team_members, project_title) 
                VALUES (?, ?, ?, ?)
            ''', candidate)
    
    conn.commit()
    conn.close()

# JWT token verification decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = data
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Token is invalid'}), 401
        
        return f(current_user, *args, **kwargs)
    return decorated

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if current_user.get('role') != 'admin':
            return jsonify({'message': 'Admin access required'}), 403
        return f(current_user, *args, **kwargs)
    return decorated

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

@app.route('/voting')
def voting_page():
    return render_template('voting.html')

@app.route('/results')
def results_page():
    return render_template('results.html')

# Authentication endpoints
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'message': 'Username and password required'}), 400
    
    conn = sqlite3.connect('voting_system.db')
    cursor = conn.cursor()
    
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    cursor.execute('SELECT id, username, role, has_voted FROM users WHERE username = ? AND password = ?', 
                   (username, hashed_password))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        token = jwt.encode({
            'user_id': user[0],
            'username': user[1],
            'role': user[2],
            'has_voted': user[3],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'token': token,
            'user': {
                'id': user[0],
                'username': user[1],
                'role': user[2],
                'has_voted': bool(user[3])
            }
        })
    else:
        return jsonify({'message': 'Invalid credentials'}), 401

# Voting endpoints
@app.route('/api/candidates', methods=['GET'])
@token_required
def get_candidates(current_user):
    conn = sqlite3.connect('voting_system.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, description, team_members, project_title, votes_count FROM candidates ORDER BY name')
    candidates = cursor.fetchall()
    conn.close()
    
    candidate_list = []
    for candidate in candidates:
        candidate_list.append({
            'id': candidate[0],
            'name': candidate[1],
            'description': candidate[2],
            'team_members': candidate[3],
            'project_title': candidate[4],
            'votes_count': candidate[5]
        })
    
    return jsonify(candidate_list)

@app.route('/api/vote', methods=['POST'])
@token_required
def vote(current_user):
    if current_user.get('has_voted'):
        return jsonify({'message': 'You have already voted'}), 400
    
    data = request.get_json()
    candidate_id = data.get('candidate_id')
    
    if not candidate_id:
        return jsonify({'message': 'Candidate ID required'}), 400
    
    conn = sqlite3.connect('voting_system.db')
    cursor = conn.cursor()
    
    try:
        # Check if candidate exists
        cursor.execute('SELECT id FROM candidates WHERE id = ?', (candidate_id,))
        if not cursor.fetchone():
            return jsonify({'message': 'Candidate not found'}), 404
        
        # Record vote
        cursor.execute('INSERT INTO votes (user_id, candidate_id) VALUES (?, ?)', 
                       (current_user['user_id'], candidate_id))
        
        # Update candidate vote count
        cursor.execute('UPDATE candidates SET votes_count = votes_count + 1 WHERE id = ?', 
                       (candidate_id,))
        
        # Mark user as voted
        cursor.execute('UPDATE users SET has_voted = 1 WHERE id = ?', 
                       (current_user['user_id'],))
        
        conn.commit()
        return jsonify({'message': 'Vote recorded successfully'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'message': 'Error recording vote'}), 500
    finally:
        conn.close()

@app.route('/api/results', methods=['GET'])
@token_required
def get_results(current_user):
    conn = sqlite3.connect('voting_system.db')
    cursor = conn.cursor()
    
    # Get vote counts
    cursor.execute('''
        SELECT c.id, c.name, c.project_title, c.votes_count,
               ROUND(c.votes_count * 100.0 / NULLIF((SELECT SUM(votes_count) FROM candidates), 0), 2) as percentage
        FROM candidates c 
        ORDER BY c.votes_count DESC, c.name
    ''')
    results = cursor.fetchall()
    
    # Get total votes
    cursor.execute('SELECT COUNT(*) FROM votes')
    total_votes = cursor.fetchone()[0]
    
    conn.close()
    
    result_list = []
    for result in results:
        result_list.append({
            'id': result[0],
            'name': result[1],
            'project_title': result[2],
            'votes_count': result[3],
            'percentage': result[4] if result[4] else 0
        })
    
    return jsonify({
        'results': result_list,
        'total_votes': total_votes
    })

# Admin endpoints
@app.route('/api/admin/users', methods=['GET'])
@token_required
@admin_required
def get_users(current_user):
    conn = sqlite3.connect('voting_system.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, role, has_voted, created_at FROM users ORDER BY created_at DESC')
    users = cursor.fetchall()
    conn.close()
    
    user_list = []
    for user in users:
        user_list.append({
            'id': user[0],
            'username': user[1],
            'role': user[2],
            'has_voted': bool(user[3]),
            'created_at': user[4]
        })
    
    return jsonify(user_list)

@app.route('/api/admin/add_user', methods=['POST'])
@token_required
@admin_required
def add_user(current_user):
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'voter')
    
    if not username or not password:
        return jsonify({'message': 'Username and password required'}), 400
    
    if role not in ['admin', 'voter']:
        return jsonify({'message': 'Invalid role'}), 400
    
    conn = sqlite3.connect('voting_system.db')
    cursor = conn.cursor()
    
    try:
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', 
                       (username, hashed_password, role))
        conn.commit()
        return jsonify({'message': 'User added successfully'})
    except sqlite3.IntegrityError:
        return jsonify({'message': 'Username already exists'}), 400
    except Exception as e:
        return jsonify({'message': 'Error adding user'}), 500
    finally:
        conn.close()

@app.route('/api/admin/reset_votes', methods=['POST'])
@token_required
@admin_required
def reset_votes(current_user):
    conn = sqlite3.connect('voting_system.db')
    cursor = conn.cursor()
    
    try:
        # Reset all vote counts
        cursor.execute('UPDATE candidates SET votes_count = 0')
        cursor.execute('DELETE FROM votes')
        cursor.execute('UPDATE users SET has_voted = 0 WHERE role = "voter"')
        
        conn.commit()
        return jsonify({'message': 'All votes reset successfully'})
    except Exception as e:
        conn.rollback()
        return jsonify({'message': 'Error resetting votes'}), 500
    finally:
        conn.close()

@app.route('/api/admin/add_candidate', methods=['POST'])
@token_required
@admin_required
def add_candidate(current_user):
    data = request.get_json()
    name = data.get('name')
    description = data.get('description', '')
    team_members = data.get('team_members', '')
    project_title = data.get('project_title', '')
    
    if not name:
        return jsonify({'message': 'Candidate name required'}), 400
    
    conn = sqlite3.connect('voting_system.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO candidates (name, description, team_members, project_title) 
            VALUES (?, ?, ?, ?)
        ''', (name, description, team_members, project_title))
        conn.commit()
        return jsonify({'message': 'Candidate added successfully'})
    except Exception as e:
        return jsonify({'message': 'Error adding candidate'}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='127.0.0.1', port=5000)