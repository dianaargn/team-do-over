from flask import (
    Flask, 
    render_template, 
    request, jsonify, 
    redirect, url_for, 
    flash,  
    get_flashed_messages, 
    session
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from waitress import serve

import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workouts.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Replace with a secure secret key
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ----------------------- Models -----------------------

# User Model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    folders = db.relationship('Folder', backref='user', lazy=True)
    workouts = db.relationship('Workout', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Folder Model
class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    templates = db.relationship('WorkoutTemplate', backref='folder', lazy=True)

# Workout Template Model
class WorkoutTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey('folder.id'), nullable=False)
    exercises = db.relationship('TemplateExercise', backref='template', lazy=True)

# Template Exercise Model
class TemplateExercise(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('workout_template.id'), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey('exercise.id'), nullable=False)
    sets = db.Column(db.Integer, nullable=False)
    reps = db.Column(db.String(50), nullable=True)
    weight = db.Column(db.Float, nullable=True)
    rpe = db.Column(db.Float, nullable=True)
    rir = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.String(200), nullable=True)
    exercise = db.relationship('Exercise')

# Workout Model
class Workout(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('workout_template.id'))
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    name = db.Column(db.String(100))
    notes = db.Column(db.String(500))
    completed = db.Column(db.Boolean, default=False)
    sets = db.relationship('WorkoutSet', backref='workout', lazy=True)

# Workout Set Model
class WorkoutSet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workout_id = db.Column(db.Integer, db.ForeignKey('workout.id'), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey('exercise.id'), nullable=False)
    weight = db.Column(db.Float)
    reps = db.Column(db.Integer)   
    rpe = db.Column(db.Float)      
    rir = db.Column(db.Integer)    
    notes = db.Column(db.String(200))
    completed = db.Column(db.Boolean, default=False)
    exercise = db.relationship('Exercise', backref='sets')

# Exercise Model
class Exercise(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    equipment = db.Column(db.String(50))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'equipment': self.equipment
        }

# ----------------------- Login Manager -----------------------

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ----------------------- Flash -----------------------
def clear_flashes():
    session.pop('_flashes', None)


# ----------------------- Routes -----------------------

@app.route('/')
def root():
    if current_user.is_authenticated:
        return redirect(url_for('profile'))
    return redirect(url_for('login'))

# ----------------------- Authentication Routes -----------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST': 
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('profile'))
        flash('Invalid username or password.', 'error')
    else:
        # Clear flashes when accessing the login page via GET
        clear_flashes()
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Existing registration logic...
        existing_user = User.query.filter(
            (User.username == request.form['username']) | 
            (User.email == request.form['email'])
        ).first()
        if existing_user:
            flash('Username or email already exists.', 'error')
            return redirect(url_for('register'))

        user = User(
            username=request.form['username'],
            email=request.form['email']
        )
        user.set_password(request.form['password'])
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    else:
        # Clear flashes when accessing the register page via GET
        clear_flashes()
    return render_template('register.html')

# ----------------------- Dashboard Routes -----------------------

@app.route('/template/<int:template_id>/start', methods=['POST'])
@login_required
def start_workout(template_id):
    template = WorkoutTemplate.query.get_or_404(template_id)
    if template.folder.user_id != current_user.id:
        flash("You don't have access to this template.", 'error')
        return redirect(url_for('dashboard'))

    # Create a new workout from the template
    new_workout = Workout(
        user_id=current_user.id,
        template_id=template_id,
        date=datetime.utcnow(),
        name=template.name,
        notes=None
    )
    db.session.add(new_workout)
    db.session.commit()

    # Create WorkoutSet entries from the template exercises
    for ex in template.exercises:
        for i in range(ex.sets):
            new_set = WorkoutSet(
                workout_id=new_workout.id,
                exercise_id=ex.exercise_id,
                weight=ex.weight,
                rpe=ex.rpe,
                rir=ex.rir,
                notes=f"Suggested: {ex.reps}" if ex.reps else None,
                completed=False
            )
            db.session.add(new_set)

    db.session.commit()
    flash('Workout started from template!', 'success')
    return redirect(url_for('view_workout', workout_id=new_workout.id))

@app.route('/dashboard')
@login_required
def dashboard():
    folders = Folder.query.filter_by(user_id=current_user.id).all()
    current_workout = Workout.query.filter_by(
        user_id=current_user.id, 
        completed=False
    ).order_by(Workout.date.desc()).first()
    recent_workouts = Workout.query.filter_by(
        user_id=current_user.id,
        completed=True
    ).order_by(Workout.date.desc()).limit(5).all()
    return render_template('dashboard.html', 
                         folders=folders, 
                         recent_workouts=recent_workouts, 
                         current_workout=current_workout)

@app.route('/start')
@login_required
def start_workout_page():
    return redirect(url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

# ----------------------- Folder Routes -----------------------

@app.route('/folder/<int:folder_id>/delete', methods=['POST'])
@login_required
def delete_folder(folder_id):
    folder = Folder.query.get_or_404(folder_id)
    if folder.user_id != current_user.id:
        flash("You don't have permission to delete this folder.", 'error')
        return redirect(url_for('dashboard'))
    
    # Delete all associated templates and their exercises
    for template in folder.templates:
        TemplateExercise.query.filter_by(template_id=template.id).delete()
    WorkoutTemplate.query.filter_by(folder_id=folder_id).delete()
    
    db.session.delete(folder)
    db.session.commit()
    flash('Folder and all its templates deleted successfully.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/folder/<int:folder_id>')
@login_required
def view_folder(folder_id):
    folder = Folder.query.get_or_404(folder_id)
    if folder.user_id != current_user.id:
        flash("You don't have access to this folder.", 'error')
        return redirect(url_for('dashboard'))
    return render_template('folder.html', folder=folder)

@app.route('/folder/create', methods=['POST'])
@login_required
def create_folder():
    folder_name = request.form.get('name')
    if not folder_name:
        flash('Folder name cannot be empty.', 'error')
        return redirect(url_for('dashboard'))
    folder = Folder(
        name=folder_name,
        user_id=current_user.id
    )
    db.session.add(folder)
    db.session.commit()
    flash('Folder created successfully.', 'success')
    return redirect(url_for('dashboard'))

# ----------------------- Workout Template Routes -----------------------

@app.route('/template/exercise/<int:template_id>/<int:exercise_id>/update', methods=['POST'])
@login_required
def update_template_exercise(template_id, exercise_id):
    template = WorkoutTemplate.query.get_or_404(template_id)
    exercise = TemplateExercise.query.get_or_404(exercise_id)
    
    if template.folder.user_id != current_user.id:
        flash("You don't have permission to edit this template.", 'error')
        return redirect(url_for('dashboard'))
    
    exercise.sets = int(request.form.get('sets'))
    exercise.reps = request.form.get('reps') or None
    
    weight = request.form.get('weight')
    exercise.weight = float(weight) if weight else None
    
    rpe = request.form.get('rpe')
    exercise.rpe = float(rpe) if rpe else None
    
    rir = request.form.get('rir')
    exercise.rir = int(rir) if rir else None
    
    exercise.notes = request.form.get('notes') or None
    
    db.session.commit()
    flash('Exercise updated successfully.', 'success')
    return redirect(url_for('edit_template', template_id=template_id))

@app.route('/template/<int:template_id>/delete', methods=['POST'])
@login_required
def delete_template(template_id):
    template = WorkoutTemplate.query.get_or_404(template_id)
    if template.folder.user_id != current_user.id:
        flash("You don't have permission to delete this template.", 'error')
        return redirect(url_for('dashboard'))
    
    # Delete all associated template exercises first
    TemplateExercise.query.filter_by(template_id=template_id).delete()
    
    db.session.delete(template)
    db.session.commit()
    flash('Template deleted successfully.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/template/create/<int:folder_id>', methods=['GET', 'POST'])
@login_required
def create_template(folder_id):
    folder = Folder.query.get_or_404(folder_id)
    if folder.user_id != current_user.id:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        try:
            template_name = request.form.get('name')
            if not template_name:
                flash('Template name is required', 'error')
                return redirect(url_for('view_folder', folder_id=folder_id))

            template = WorkoutTemplate(
                name=template_name,
                folder_id=folder_id
            )
            db.session.add(template)
            db.session.commit()
            flash('Template created successfully', 'success')
            return redirect(url_for('view_folder', folder_id=folder_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating template: {str(e)}', 'error')
            return redirect(url_for('view_folder', folder_id=folder_id))
    else:
        return redirect(url_for('view_folder', folder_id=folder_id))

@app.route('/template/<int:template_id>/edit')
@login_required
def edit_template(template_id):
    template = WorkoutTemplate.query.get_or_404(template_id)
    if template.folder.user_id != current_user.id:
        return redirect(url_for('dashboard'))
    exercises = Exercise.query.order_by(Exercise.category, Exercise.name).all()
    return render_template('edit_template.html', template=template, exercises=exercises)

@app.route('/template/exercise/add/<int:template_id>', methods=['POST'])
@login_required
def add_template_exercise(template_id):
    template = WorkoutTemplate.query.get_or_404(template_id)
    if template.folder.user_id != current_user.id:
        return redirect(url_for('dashboard'))

    exercise_id = request.form.get('exercise_id')
    sets = request.form.get('sets')
    reps = request.form.get('reps')
    weight = request.form.get('weight')
    rpe = request.form.get('rpe')
    rir = request.form.get('rir')
    notes = request.form.get('notes')

    if reps == '':
        reps = None

    if weight == '':
        weight = None
    else:
        weight = float(weight) if weight else None

    if rpe == '':
        rpe = None
    else:
        rpe = float(rpe) if rpe else None

    if rir == '':
        rir = None
    else:
        rir = int(rir) if rir else None

    sets = int(sets)

    exercise = TemplateExercise(
        template_id=template_id,
        exercise_id=int(exercise_id),
        sets=sets,
        reps=reps,
        weight=weight,
        rpe=rpe,
        rir=rir,
        notes=notes
    )

    db.session.add(exercise)
    db.session.commit()
    flash('Exercise added to template', 'success')
    return redirect(url_for('edit_template', template_id=template_id))

@app.route('/template/exercise/delete/<int:template_id>/<int:exercise_id>', methods=['POST'])
@login_required
def delete_template_exercise(template_id, exercise_id):
    template = WorkoutTemplate.query.get_or_404(template_id)
    if template.folder.user_id != current_user.id:
        return redirect(url_for('dashboard'))

    exercise = TemplateExercise.query.get_or_404(exercise_id)
    db.session.delete(exercise)
    db.session.commit()
    flash('Exercise removed from template', 'success')
    return redirect(url_for('edit_template', template_id=template_id))


# ----------------------- Workout Routes -----------------------

@app.route('/workout/<int:workout_id>/add_exercise', methods=['POST'])
@login_required
def add_exercise_to_workout(workout_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        flash("You don't have access to this workout.", 'error')
        return redirect(url_for('dashboard'))
    
    exercise_id = request.form.get('exercise_id')
    sets = request.form.get('sets', 1)

    if not exercise_id or not sets:
        flash('Exercise and number of sets are required.', 'error')
        return redirect(url_for('view_workout', workout_id=workout_id))

    try:
        exercise_id = int(exercise_id)
        sets = int(sets)
    except ValueError:
        flash('Invalid input for exercise or sets.', 'error')
        return redirect(url_for('view_workout', workout_id=workout_id))

    for _ in range(sets):
        new_set = WorkoutSet(
            workout_id=workout_id,
            exercise_id=exercise_id,
            completed=False
        )
        db.session.add(new_set)
    
    db.session.commit()
    flash('Exercise added to workout.', 'success')
    return redirect(url_for('view_workout', workout_id=workout_id))

@app.route('/workout/<int:workout_id>/exercise/<int:exercise_id>/add_set', methods=['POST'])
@login_required
def add_set_to_exercise(workout_id, exercise_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        flash("You don't have access to this workout.", 'error')
        return redirect(url_for('dashboard'))
    
    new_set = WorkoutSet(
        workout_id=workout_id,
        exercise_id=exercise_id,
        completed=False
    )
    db.session.add(new_set)
    db.session.commit()
    
    flash('Set added.', 'success')
    return redirect(url_for('view_workout', workout_id=workout_id))

@app.route('/workout/<int:workout_id>/finish', methods=['POST'])
@login_required
def finish_workout(workout_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        flash("You don't have access to this workout.", 'error')
        return redirect(url_for('dashboard'))

    if workout.completed:
        flash("Workout is already completed.", 'info')
        return redirect(url_for('dashboard'))

    # Retrieve all sets data from the form
    sets_dict = {}
    for key in request.form:
        if key.startswith('sets['):
            # Extract set_id and field name
            parts = key.split('[')
            if len(parts) < 3:
                continue  # Skip invalid keys
            set_id = parts[1].rstrip(']')
            field = parts[2].rstrip(']')
            if set_id not in sets_dict:
                sets_dict[set_id] = {}
            sets_dict[set_id][field] = request.form.get(key)

    # Iterate over each set and update the corresponding WorkoutSet
    for set_id, fields in sets_dict.items():
        workout_set = WorkoutSet.query.get(set_id)
        if not workout_set or workout_set.workout_id != workout.id:
            continue  # Skip invalid sets

        # Update fields if they exist in the form
        if 'weight' in fields and fields['weight']:
            try:
                workout_set.weight = float(fields['weight'])
            except ValueError:
                flash(f"Invalid weight for set {set_id}. Please enter a valid number.", 'error')
                return redirect(url_for('view_workout', workout_id=workout_id))

        if 'reps' in fields and fields['reps']:
            try:
                workout_set.reps = int(fields['reps'])
            except ValueError:
                flash(f"Invalid reps for set {set_id}. Please enter a valid integer.", 'error')
                return redirect(url_for('view_workout', workout_id=workout_id))

        if 'rpe' in fields and fields['rpe']:
            try:
                rpe_value = float(fields['rpe'])
                if not (1 <= rpe_value <= 10):
                    raise ValueError
                workout_set.rpe = rpe_value
            except ValueError:
                flash(f"Invalid RPE for set {set_id}. Please enter a number between 1 and 10.", 'error')
                return redirect(url_for('view_workout', workout_id=workout_id))

        if 'rir' in fields and fields['rir']:
            try:
                rir_value = int(fields['rir'])
                if not (0 <= rir_value <= 9):
                    raise ValueError
                workout_set.rir = rir_value
            except ValueError:
                flash(f"Invalid RIR for set {set_id}. Please enter an integer between 0 and 9.", 'error')
                return redirect(url_for('view_workout', workout_id=workout_id))

    # Optionally, verify that all sets have been filled out
    incomplete_sets = WorkoutSet.query.filter_by(workout_id=workout_id, completed=False).all()
    for s in incomplete_sets:
        if s.weight is None or s.reps is None:
            flash("Please fill out all weight and reps before finishing the workout.", 'error')
            return redirect(url_for('view_workout', workout_id=workout_id))

    # Mark the workout as completed
    workout.completed = True
    db.session.commit()
    flash("Workout logged successfully!", "success")
    return redirect(url_for('dashboard'))

@app.route('/workout/<int:workout_id>')
@login_required
def view_workout(workout_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        flash("You don't have access to this workout.", 'error')
        return redirect(url_for('dashboard'))

    available_exercises = Exercise.query.order_by(Exercise.category, Exercise.name).all()

    # Get previous performance data for each exercise
    last_performances = {}
    for s in workout.sets:
        if s.exercise_id not in last_performances:
            # Get the last workout that included this exercise
            previous_set = WorkoutSet.query.join(Workout).filter(
                Workout.user_id == current_user.id,
                Workout.id != workout.id,
                WorkoutSet.exercise_id == s.exercise_id,
                WorkoutSet.completed == True,
                WorkoutSet.weight.isnot(None),
                WorkoutSet.reps.isnot(None)
            ).order_by(Workout.date.desc()).first()

            if previous_set:
                last_performances[s.exercise_id] = {
                    'weight': previous_set.weight,
                    'reps': previous_set.reps,
                    'rpe': previous_set.rpe,
                    'date': previous_set.workout.date
                }

    return render_template('view_workout.html', 
                           workout=workout, 
                           last_performances=last_performances,
                           available_exercises=available_exercises)

# ----------------------- API Routes -----------------------

@app.route('/api/set/<int:set_id>/update', methods=['POST'])
@login_required
def update_set_api(set_id):
    w_set = WorkoutSet.query.get_or_404(set_id)
    if w_set.workout.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json

    if 'weight' in data:
        w_set.weight = data['weight']
    if 'reps' in data:
        w_set.reps = data['reps']
    if 'rpe' in data:
        w_set.rpe = data['rpe']
    if 'rir' in data:
        w_set.rir = data['rir']
    if 'notes' in data:
        w_set.notes = data['notes']

    w_set.completed = True
    db.session.commit()

    return jsonify({"success": True})

# ----------------------- Profile Routes -----------------------

@app.route('/profile')
@login_required
def profile():
    # Total workouts
    total_workouts = Workout.query.filter_by(user_id=current_user.id, completed=True).count()
    
    # Workouts in the last 7 days
    one_week_ago = datetime.utcnow() - timedelta(days=7)
    workouts_last_week = Workout.query.filter(
        Workout.user_id == current_user.id,
        Workout.completed == True,
        Workout.date >= one_week_ago
    ).count()

    return render_template('profile.html', 
                         total_workouts=total_workouts,
                         workouts_per_week=workouts_last_week)

# ----------------------- History Routes -----------------------

@app.route('/history')
@login_required
def history():
    past_workouts = Workout.query.filter_by(user_id=current_user.id, completed=True).order_by(Workout.date.desc()).all()
    return render_template('history.html', workouts=past_workouts)

# ----------------------- Stats Routes -----------------------

@app.route('/stats')
@login_required
def stats():
    # Get all unique exercises the user has performed
    exercises_performed = db.session.query(Exercise)\
        .join(WorkoutSet)\
        .join(Workout)\
        .filter(
            Workout.user_id == current_user.id,
            WorkoutSet.completed == True,
            WorkoutSet.weight.isnot(None),
            WorkoutSet.reps.isnot(None)
        )\
        .distinct()\
        .all()
    
    exercise_stats = {}
    for exercise in exercises_performed:
        # Get all workouts with this exercise
        workouts = db.session.query(Workout)\
            .join(WorkoutSet)\
            .filter(
                Workout.user_id == current_user.id,
                WorkoutSet.exercise_id == exercise.id,
                WorkoutSet.completed == True,
                WorkoutSet.weight.isnot(None),
                WorkoutSet.reps.isnot(None)
            )\
            .distinct()\
            .order_by(Workout.date)\
            .all()
        
        data_points = []
        for workout in workouts:
            # Get all sets for this exercise in this workout
            sets = WorkoutSet.query.filter(
                WorkoutSet.workout_id == workout.id,
                WorkoutSet.exercise_id == exercise.id,
                WorkoutSet.completed == True,
                WorkoutSet.weight.isnot(None),
                WorkoutSet.reps.isnot(None)
            ).all()
            
            # Find the set with highest calculated 1RM
            max_e1rm = 0
            best_set = None
            
            for set in sets:
                # Calculate e1RM based on RPE when available
                if set.rpe is not None:
                    e1rm = set.weight * (1 + set.reps/30) * (set.rpe/10)
                else:
                    e1rm = set.weight * (1 + set.reps/30)
                
                if e1rm > max_e1rm:
                    max_e1rm = e1rm
                    best_set = set
            
            if best_set:  # Only add if we found a valid set
                data_points.append({
                    'date': workout.date.strftime('%Y-%m-%d'),
                    'one_rm': round(max_e1rm, 2),
                    'weight': best_set.weight,
                    'reps': best_set.reps,
                    'rpe': best_set.rpe
                })
        
        if data_points:  # Only add exercises with actual data
            exercise_stats[exercise.name] = data_points
    
    return render_template('stats.html', exercise_stats=exercise_stats)

# ----------------------- Delete Routes -----------------------

@app.route('/workout/<int:workout_id>/exercise/<int:exercise_id>/delete', methods=['POST'])
@login_required
def delete_exercise_from_workout(workout_id, exercise_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        flash("You don't have access to this workout.", 'error')
        return redirect(url_for('dashboard'))

    # Delete all sets for this exercise
    WorkoutSet.query.filter_by(
        workout_id=workout_id,
        exercise_id=exercise_id
    ).delete()

    db.session.commit()
    flash('Exercise removed from workout.', 'success')
    return redirect(url_for('view_workout', workout_id=workout_id))

@app.route('/workout/set/<int:set_id>/delete', methods=['POST'])
@login_required
def delete_set(set_id):
    w_set = WorkoutSet.query.get_or_404(set_id)
    if w_set.workout.user_id != current_user.id:
        flash("You don't have access to this set.", 'error')
        return redirect(url_for('dashboard'))

    workout_id = w_set.workout_id
    db.session.delete(w_set)
    db.session.commit()
    flash('Set deleted.', 'success')
    return redirect(url_for('view_workout', workout_id=workout_id))

# ----------------------- Start Workout Page Route -----------------------



# ----------------------- Database Initialization -----------------------

def init_db():
    with app.app_context():
        db.create_all()
        if Exercise.query.count() == 0:
            exercises_data = [
                # Chest
                ('Assisted Dip', 'Chest', 'Assisted'),
                ('Band-Assisted Bench Press', 'Chest', 'Band'),
                ('Bar Dip', 'Chest', 'Bodyweight'),
                ('Bench Press', 'Chest', 'Barbell'),
                ('Cable Crossover', 'Chest', 'Cable'),
                ('Chest Fly (Machine)', 'Chest', 'Machine'),
                ('Dumbbell Bench Press', 'Chest', 'Dumbbell'),
                ('Incline Bench Press', 'Chest', 'Barbell'),
                ('Incline Dumbbell Press', 'Chest', 'Dumbbell'),
                ('Push-Up', 'Chest', 'Bodyweight'),
                ('Single-Arm Dumbbell Press', 'Chest', 'Dumbbell'),
                ('Wide-Grip Push-Up', 'Chest', 'Bodyweight'),

                # Back
                ('Barbell Row', 'Back', 'Barbell'),
                ('Bent Over Row', 'Back', 'Barbell'),
                ('Chin-Up', 'Back', 'Bodyweight'),
                ('Clean', 'Back', 'Barbell'),
                ('Clean and Jerk', 'Back', 'Barbell'),
                ('Deadlift', 'Back', 'Barbell'),
                ('Deficit Deadlift', 'Back', 'Barbell'),
                ('Dumbbell Deadlift', 'Back', 'Dumbbell'),
                ('Dumbbell Row', 'Back', 'Dumbbell'),
                ('Dumbbell Shrug', 'Back', 'Dumbbell'),
                ('Floor Back Extension', 'Back', 'Bodyweight'),
                ('Good Morning', 'Back', 'Barbell'),
                ('Gorilla Row', 'Back', 'Dumbbell/Kettlebell'),
                ('Hang Clean', 'Back', 'Barbell'),
                ('Hang Power Clean', 'Back', 'Barbell'),
                ('Hang Power Snatch', 'Back', 'Barbell'),
                ('Hang Snatch', 'Back', 'Barbell'),
                ('Inverted Row', 'Back', 'Bodyweight'),
                ('Inverted Row with Underhand Grip', 'Back', 'Bodyweight'),
                ('Jefferson Curl', 'Back', 'Barbell'),
                ('Jumping Muscle-Up', 'Back', 'Bodyweight'),
                ('Kettlebell Swing', 'Back', 'Kettlebell'),
                ('Lat Pulldown With Pronated Grip', 'Back', 'Cable'),
                ('Lat Pulldown With Supinated Grip', 'Back', 'Cable'),
                ('Muscle-Up (Bar)', 'Back', 'Bar'),
                ('Muscle-Up (Rings)', 'Back', 'Rings'),
                ('One-Handed Cable Row', 'Back', 'Cable'),
                ('One-Handed Lat Pulldown', 'Back', 'Cable'),
                ('Pause Deadlift', 'Back', 'Barbell'),
                ('Pendlay Row', 'Back', 'Barbell'),
                ('Power Clean', 'Back', 'Barbell'),
                ('Power Snatch', 'Back', 'Barbell'),
                ('Pull-Up', 'Back', 'Bodyweight'),
                ('Pull-Up With a Neutral Grip', 'Back', 'Bodyweight'),
                ('Rack Pull', 'Back', 'Barbell'),
                ('Ring Pull-Up', 'Back', 'Rings'),
                ('Ring Row', 'Back', 'Rings'),
                ('Scap Pull-Up', 'Back', 'Bodyweight'),
                ('Seal Row', 'Back', 'Bench/Barbell'),
                ('Seated Machine Row', 'Back', 'Machine'),
                ('Single Leg Deadlift with Kettlebell', 'Back', 'Kettlebell'),
                ('Smith Machine One-Handed Row', 'Back', 'Smith Machine'),
                ('Snatch', 'Back', 'Barbell'),
                ('Snatch Grip Deadlift', 'Back', 'Barbell'),
                ('Stiff-Legged Deadlift', 'Back', 'Barbell'),
                ('Straight Arm Lat Pulldown', 'Back', 'Cable'),
                ('Sumo Deadlift', 'Back', 'Barbell'),
                ('T-Bar Row', 'Back', 'T-Bar'),
                ('Trap Bar Deadlift With High Handles', 'Back', 'Trap Bar'),
                ('Trap Bar Deadlift With Low Handles', 'Back', 'Trap Bar'),

                # Glutes
                ('Banded Side Kicks', 'Glutes', 'Band'),
                ('Cable Pull Through', 'Glutes', 'Cable'),
                ('Clamshells', 'Glutes', 'Bodyweight/Band'),
                ('Cossack Squat', 'Glutes', 'Bodyweight/Kettlebell'),
                ('Death March with Dumbbells', 'Glutes', 'Dumbbell'),
                ('Donkey Kicks', 'Glutes', 'Bodyweight'),
                ('Dumbbell Romanian Deadlift', 'Glutes', 'Dumbbell'),
                ('Dumbbell Frog Pumps', 'Glutes', 'Dumbbell'),
                ('Fire Hydrants', 'Glutes', 'Bodyweight'),
                ('Frog Pumps', 'Glutes', 'Bodyweight'),
                ('Glute Bridge', 'Glutes', 'Bodyweight/Barbell'),
                ('Hip Abduction Against Band', 'Glutes', 'Band'),
                ('Hip Abduction Machine', 'Glutes', 'Machine'),
                ('Hip Thrust', 'Glutes', 'Barbell'),
                ('Hip Thrust Machine', 'Glutes', 'Machine'),
                ('Hip Thrust With Band Around Knees', 'Glutes', 'Band/Barbell'),
                ('Lateral Walk With Band', 'Glutes', 'Band'),
                ('Machine Glute Kickbacks', 'Glutes', 'Machine'),
                ('One-Legged Glute Bridge', 'Glutes', 'Bodyweight'),
                ('One-Legged Hip Thrust', 'Glutes', 'Bodyweight'),
                ('Reverse Hyperextension', 'Glutes', 'Machine'),
                ('Romanian Deadlift', 'Glutes', 'Barbell'),
                ('Single Leg Romanian Deadlift', 'Glutes', 'Dumbbell/Kettlebell'),
                ('Standing Glute Kickback in Machine', 'Glutes', 'Machine'),
                ('Step Up', 'Glutes', 'Bodyweight/Dumbbell'),

                # Abs
                ('Ball Slams', 'Core', 'Medicine Ball'),
                ('Cable Crunch', 'Core', 'Cable'),
                ('Crunch', 'Core', 'Bodyweight'),
                ('Dead Bug', 'Core', 'Bodyweight'),
                ('Dragon Flag', 'Core', 'Bodyweight'),
                ('Hanging Knee Raise', 'Core', 'Bodyweight'),
                ('Hanging Leg Raise', 'Core', 'Bodyweight'),
                ('Hanging Sit-Up', 'Core', 'Bodyweight'),
                ('Hanging Windshield Wiper', 'Core', 'Bodyweight'),
                ('High to Low Wood Chop with Band', 'Core', 'Band'),
                ('Horizontal Wood Chop with Band', 'Core', 'Band'),
                ('Jackknife Sit-Up', 'Core', 'Bodyweight'),
                ('Kneeling Ab Wheel Roll-Out', 'Core', 'Ab Wheel'),
                ('Kneeling Plank', 'Core', 'Bodyweight'),
                ('Kneeling Side Plank', 'Core', 'Bodyweight'),
                ('Lying Leg Raise', 'Core', 'Bodyweight'),
                ('Lying Windshield Wiper', 'Core', 'Bodyweight'),
                ('Lying Windshield Wiper with Bent Knees', 'Core', 'Bodyweight'),
                ('Machine Crunch', 'Core', 'Machine'),
                ('Mountain Climbers', 'Core', 'Bodyweight'),
                ('Oblique Crunch', 'Core', 'Bodyweight'),
                ('Oblique Sit-Up', 'Core', 'Bodyweight'),
                ('Plank', 'Core', 'Bodyweight'),
                ('Plank with Leg Lifts', 'Core', 'Bodyweight'),
                ('Russian Twist', 'Core', 'Bodyweight'),
                ('Side Plank', 'Core', 'Bodyweight'),
                ('Sit-Up', 'Core', 'Bodyweight'),

                # Calves
                ('Barbell Standing Calf Raise', 'Calves', 'Barbell'),
                ('Donkey Calf Raise', 'Calves', 'Bodyweight/Machine'),
                ('Eccentric Heel Drop', 'Calves', 'Bodyweight'),
                ('Heel Raise', 'Calves', 'Bodyweight'),
                ('Seated Calf Raise', 'Calves', 'Machine'),
                ('Standing Calf Raise', 'Calves', 'Bodyweight/Machine'),

                # Forearm Flexors & Grip
                ('Barbell Wrist Curl', 'Forearms', 'Barbell'),
                ('Barbell Wrist Curl Behind the Back', 'Forearms', 'Barbell'),
                ('Bar Hang', 'Forearms', 'Bodyweight'),
                ('Dumbbell Wrist Curl', 'Forearms', 'Dumbbell'),
                ('Farmers Walk', 'Forearms', 'Dumbbell/Kettlebell'),
                ('Fat Bar Deadlift', 'Forearms', 'Fat Bar'),
                ('Gripper', 'Forearms', 'Hand Gripper'),
                ('One-Handed Bar Hang', 'Forearms', 'Bodyweight'),
                ('Plate Pinch', 'Forearms', 'Plates'),
                ('Plate Wrist Curl', 'Forearms', 'Plates'),
                ('Towel Pull-Up', 'Forearms', 'Bodyweight/Towel'),
                ('Wrist Roller', 'Forearms', 'Wrist Roller'),

                # Forearm Extensors
                ('Barbell Wrist Extension', 'Forearms', 'Barbell'),
                ('Dumbbell Wrist Extension', 'Forearms', 'Dumbbell')
            ]
            default_user = User.query.filter_by(username='default_user').first()
            if not default_user:
                default_user = User(username='default_user', email='default@example.com')
                default_user.set_password('defaultpassword')
                db.session.add(default_user)
                db.session.commit()

            for name, category, equipment in exercises_data:
                exercise = Exercise(name=name, category=category, equipment=equipment)
                db.session.add(exercise)

            db.session.commit()

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
