from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from models import db, User, Task
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import atexit
import os

app = Flask(__name__)
# Use environment variable in production; fallback for local dev only
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Decorator for admin routes
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def check_active_user():
    # Skip static file requests to avoid unnecessary DB queries
    if request.endpoint == 'static':
        return
    if current_user.is_authenticated and not current_user.is_active_user:
        logout_user()
        flash('Your account has been disabled by an administrator.', 'danger')
        return redirect(url_for('login'))

def _do_reset(category):
    """Core reset logic — must be called with an active app context."""
    tasks = Task.query.filter_by(category=category, is_completed=True).all()
    for task in tasks:
        task.is_completed = False
        task.completed_at = None
    db.session.commit()
    print(f"Reset {len(tasks)} {category} tasks.")

def reset_tasks(category):
    """Wrapper used by APScheduler — pushes its own app context since the
    scheduler runs outside of any Flask request context."""
    with app.app_context():
        _do_reset(category)


scheduler = BackgroundScheduler()
# Reset daily tasks at midnight
scheduler.add_job(func=reset_tasks, args=['daily'], trigger="cron", hour=0, minute=0)
# Reset weekly tasks on Monday at midnight
scheduler.add_job(func=reset_tasks, args=['weekly'], trigger="cron", day_of_week='mon', hour=0, minute=0)
# Reset monthly tasks on the 1st of every month at midnight
scheduler.add_job(func=reset_tasks, args=['monthly'], trigger="cron", day=1, hour=0, minute=0)

scheduler.start()
atexit.register(lambda: scheduler.shutdown())

with app.app_context():
    db.create_all()
    # Create an initial admin user if none exists
    if not User.query.filter_by(role='admin').first():
        admin = User(username='admin', email='admin@example.com', password_hash=generate_password_hash('admin123'), role='admin')
        db.session.add(admin)
        db.session.commit()

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active_user:
                flash('Your account has been disabled.', 'danger')
                return redirect(url_for('login'))
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('Username already taken', 'danger')
        else:
            new_user = User(
                username=username, 
                email=email, 
                password_hash=generate_password_hash(password)
            )
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful. Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.created_at.desc()).all()
    
    def calc_progress(cat):
        cat_tasks = [t for t in tasks if t.category == cat]
        if not cat_tasks: return 0
        completed = len([t for t in cat_tasks if t.is_completed])
        return int((completed / len(cat_tasks)) * 100)
    
    progress = {
        'daily': calc_progress('daily'),
        'weekly': calc_progress('weekly'),
        'monthly': calc_progress('monthly'),
        'overall': int((len([t for t in tasks if t.is_completed]) / len(tasks)) * 100) if tasks else 0
    }
    
    daily_tasks = [t for t in tasks if t.category == 'daily']
    weekly_tasks = [t for t in tasks if t.category == 'weekly']
    monthly_tasks = [t for t in tasks if t.category == 'monthly']
    
    return render_template('dashboard.html', 
                           daily_tasks=daily_tasks, 
                           weekly_tasks=weekly_tasks, 
                           monthly_tasks=monthly_tasks, 
                           progress=progress)

@app.route('/add-task', methods=['POST'])
@login_required
def add_task():
    title = request.form.get('title')
    description = request.form.get('description')
    category = request.form.get('category')
    if title and category in ['daily', 'weekly', 'monthly']:
        new_task = Task(title=title, description=description, category=category, user_id=current_user.id)
        db.session.add(new_task)
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/update-task/<int:task_id>', methods=['POST'])
@login_required
def update_task(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id == current_user.id:
        task.title = request.form.get('title', task.title)
        task.description = request.form.get('description', task.description)
        task.category = request.form.get('category', task.category)
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete-task/<int:task_id>', methods=['POST', 'DELETE'])
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    if current_user.role == 'admin' or task.user_id == current_user.id:
        db.session.delete(task)
        db.session.commit()
        if request.method == 'DELETE' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True})
        return redirect(url_for('dashboard'))
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    return redirect(url_for('dashboard'))

@app.route('/toggle-task/<int:task_id>', methods=['POST'])
@login_required
def toggle_task(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id == current_user.id:
        data = request.get_json()
        task.is_completed = data.get('completed', False)
        task.completed_at = datetime.utcnow() if task.is_completed else None
        db.session.commit()
        
        # Calculate new progress for AJAX response
        tasks = Task.query.filter_by(user_id=current_user.id).all()
        cat_tasks = [t for t in tasks if t.category == task.category]
        cat_progress = int((len([t for t in cat_tasks if t.is_completed]) / len(cat_tasks)) * 100) if cat_tasks else 0
        overall_progress = int((len([t for t in tasks if t.is_completed]) / len(tasks)) * 100) if tasks else 0
        
        return jsonify({
            'success': True, 
            'category_progress': cat_progress,
            'overall_progress': overall_progress
        })
    return jsonify({'success': False, 'error': 'Unauthorized'}), 403

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    users = User.query.all()
    tasks = Task.query.order_by(Task.created_at.desc()).all()
    
    # Stats
    total_users = len(users)
    total_tasks = len(tasks)
    
    # Tasks completed today
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    completed_today = Task.query.filter(Task.is_completed == True, Task.completed_at >= today_start).count()
    
    # Most active users (by total tasks)
    user_task_counts = db.session.query(Task.user_id, db.func.count(Task.id)).group_by(Task.user_id).all()
    user_task_counts.sort(key=lambda x: x[1], reverse=True)
    
    top_users = []
    for user_id, count in user_task_counts[:5]:
        user = db.session.get(User, user_id)
        if user:
            top_users.append({'username': user.username, 'task_count': count})
            
    return render_template('admin.html', 
                           users=users, 
                           tasks=tasks, 
                           total_users=total_users, 
                           total_tasks=total_tasks, 
                           completed_today=completed_today,
                           top_users=top_users)

@app.route('/admin/toggle-user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if user.role != 'admin':  # Prevent disabling other admins
        user.is_active_user = not user.is_active_user
        db.session.commit()
        status = "enabled" if user.is_active_user else "disabled"
        flash(f'User {user.username} {status}.', 'success')
    else:
        flash('Cannot disable an admin user.', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if user.role != 'admin': # Prevent deleting other admins
        db.session.delete(user)
        db.session.commit()
        flash(f'User {user.username} deleted.', 'success')
    else:
        flash('Cannot delete an admin user.', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reset-tasks/<category>', methods=['POST'])
@login_required
@admin_required
def manual_reset_tasks(category):
    if category in ['daily', 'weekly', 'monthly']:
        _do_reset(category)  # Already inside a request context — no need to push a new one
        flash(f'Successfully reset {category} tasks.', 'success')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    # debug=False in production; set DEBUG=1 env var for local dev
    app.run(debug=os.environ.get('DEBUG', '0') == '1')
