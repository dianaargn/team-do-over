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
from pytz import timezone
from waitress import serve

import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workouts.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Replace with a secure secret key
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
cstnow = lambda: datetime.now(timezone('America/Chicago'))

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
    date = db.Column(db.DateTime, nullable=False, default=cstnow())
    name = db.Column(db.String(100))
    notes = db.Column(db.String(500))
    completed = db.Column(db.Boolean, default=False)
    end_time = db.Column(db.DateTime)  # Add this line
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

@app.route('/template/<int:template_id>/start', methods=['POST', 'GET'])
@login_required
def start_workout(template_id):
    template = WorkoutTemplate.query.get_or_404(template_id)
    if template.folder.user_id != current_user.id:
        flash("You don't have access to this template.", 'error')
        return redirect(url_for('dashboard'))

    try:
        # Create the workout
        new_workout = Workout(
            user_id=current_user.id,
            template_id=template_id,
            date=cstnow(),  # Changed from datetime.utcnow()
            name=template.name,
            notes=None
        )
        db.session.add(new_workout)
        db.session.commit()

        # Create sets from template exercises
        for template_exercise in template.exercises:
            # Create the specified number of sets for each exercise
            for _ in range(template_exercise.sets):
                # Handle reps conversion properly
                reps_value = None
                if template_exercise.reps:
                    # If reps contains a range (e.g., "8-12"), take the first number
                    try:
                        reps_value = int(template_exercise.reps.split('-')[0]) if '-' in template_exercise.reps else int(template_exercise.reps)
                    except (ValueError, AttributeError):
                        reps_value = None

                new_set = WorkoutSet(
                    workout_id=new_workout.id,
                    exercise_id=template_exercise.exercise_id,
                    weight=template_exercise.weight,  # This will already be float or None
                    reps=reps_value,
                    rpe=template_exercise.rpe,    # This will already be float or None
                    rir=template_exercise.rir,    # This will already be int or None
                    notes=template_exercise.notes,
                    completed=False
                )
                db.session.add(new_set)
        
        db.session.commit()
        flash('Workout started from template!', 'success')
        return redirect(url_for('view_workout', workout_id=new_workout.id))

    except Exception as e:
        db.session.rollback()
        flash(f'Error starting workout: {str(e)}', 'error')
        return redirect(url_for('dashboard'))
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
    return 

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
                return redirect(url_for('dashboard'))

            template = WorkoutTemplate(
                name=template_name,
                folder_id=folder_id
            )
            db.session.add(template)
            db.session.commit()
            flash('Template created successfully', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating template: {str(e)}', 'error')
            return redirect(url_for('dashboard'))
    else:
        return redirect(url_for('dashboard'))

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

    # Convert empty strings to None
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

# In app.py, update the update_set_api function:
@app.route('/workout/set/<int:set_id>/update', methods=['POST'])
@login_required
def update_set_api(set_id):
    w_set = WorkoutSet.query.get_or_404(set_id)
    if w_set.workout.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    try:
        # Update to handle null/empty values correctly
        if 'weight' in data:
            w_set.weight = float(data['weight']) if data['weight'] not in [None, ''] else None
        if 'reps' in data:
            w_set.reps = int(data['reps']) if data['reps'] not in [None, ''] else None
        if 'rpe' in data:
            w_set.rpe = float(data['rpe']) if data['rpe'] not in [None, ''] else None
        if 'rir' in data:
            w_set.rir = int(data['rir']) if data['rir'] not in [None, ''] else None
        if 'notes' in data:
            w_set.notes = data['notes']
        
        w_set.completed = True
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400

# Update the finish_workout function to properly handle all set data:
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

    action = request.form.get('action','cancel')
    
    print("hi")
    print(action)
    
    
    if action == 'cancel':
        try:
            WorkoutSet.query.filter_by(workout_id=workout_id).delete()
            db.session.delete(workout)
            db.session.commit()
            flash("Workout cancelled.", "info")
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error cancelling workout: {str(e)}", "error")
            return redirect(url_for('view_workout', workout_id=workout_id))

    try:
        # Process each set's data
        for key, value in request.form.items():
            if not key.startswith('sets['):
                continue
                
            try:
                # Extract the set ID and field name using string operations
                key_parts = key.replace('sets[', '').replace(']', ' ').strip()
                set_id, field = key_parts.split('[')
                field = field.strip('[]')
                set_id = int(set_id)
                
                # Get the workout set
                w_set = WorkoutSet.query.get(set_id)
                if not w_set or w_set.workout_id != workout_id:
                    continue
                
                # Update the appropriate field with proper type conversion
                if value.strip():  # Only process non-empty values
                    if field == 'weight':
                        w_set.weight = float(value)
                    elif field == 'reps':
                        w_set.reps = int(value)
                    elif field == 'rpe':
                        w_set.rpe = float(value)
                    elif field == 'rir':
                        w_set.rir = int(value)
                else:
                    # Handle empty values by setting to None
                    setattr(w_set, field, None)
                
                w_set.completed = True
                
            except (ValueError, IndexError) as e:
                flash(f"Error processing set data: {str(e)}", "error")
                return redirect(url_for('view_workout', workout_id=workout_id))

        workout.completed = True
        workout.end_time = cstnow()  # Add this line to record end time
        db.session.commit()
        flash("Workout completed successfully!", "success")
        return redirect(url_for('dashboard'))

    except Exception as e:
        db.session.rollback()
        flash(f"Error saving workout: {str(e)}", "error")
        return redirect(url_for('view_workout', workout_id=workout_id))

@app.route('/workout/<int:workout_id>/exercise/<int:exercise_id>/add_set', methods=['POST'])
@login_required
def add_set_to_exercise(workout_id, exercise_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        flash("You don't have access to this workout.", 'error')
        return redirect(url_for('dashboard'))
    
    # Collect form data
    form_data = {k: v for k, v in request.form.items() if k.startswith('sets[')}
    
    new_set = WorkoutSet(
        workout_id=workout_id,
        exercise_id=exercise_id,
        completed=False
    )
    db.session.add(new_set)
    db.session.commit()
    
    flash('Set added.', 'success')
    # Redirect with preserved form data
    return redirect(url_for('view_workout', workout_id=workout_id, **form_data))

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
            previous_workout = Workout.query.join(WorkoutSet).filter(
                Workout.user_id == current_user.id,
                Workout.id != workout.id,
                WorkoutSet.exercise_id == s.exercise_id,
                WorkoutSet.completed == True,
                WorkoutSet.weight.isnot(None),
                WorkoutSet.reps.isnot(None)
            ).order_by(Workout.date.desc()).first()

            if previous_workout:
                # Get all sets from that workout for this exercise
                previous_sets = WorkoutSet.query.filter(
                    WorkoutSet.workout_id == previous_workout.id,
                    WorkoutSet.exercise_id == s.exercise_id,
                    WorkoutSet.completed == True,
                    WorkoutSet.weight.isnot(None),
                    WorkoutSet.reps.isnot(None)
                ).order_by(WorkoutSet.id).all()

                # Store each set's data in a dictionary
                last_performances[s.exercise_id] = {}
                for idx, prev_set in enumerate(previous_sets):
                    last_performances[s.exercise_id][idx] = {
                        'weight': prev_set.weight,
                        'reps': prev_set.reps,
                        'rpe': prev_set.rpe,
                        'date': previous_workout.date
                    }

    return render_template('view_workout.html', 
                           workout=workout, 
                           last_performances=last_performances,
                           available_exercises=available_exercises)

@app.route('/workout/<int:workout_id>/add_exercise', methods=['POST'])
@login_required
def add_exercise_to_workout(workout_id):  # Leave the function name as is
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        flash("You don't have access to this workout.", 'error')
        return redirect(url_for('dashboard'))
    
    exercise_id = request.form.get('exercise_id')
    sets = int(request.form.get('sets', 1))
    
    # Get default values if they exist in the form
    weight = request.form.get('weight')
    reps = request.form.get('reps')
    rpe = request.form.get('rpe')
    rir = request.form.get('rir')
    notes = request.form.get('notes')
    
    # Convert to appropriate types
    weight = float(weight) if weight and weight != '' else None
    reps = int(reps) if reps and reps != '' else None
    rpe = float(rpe) if rpe and rpe != '' else None
    rir = int(rir) if rir and rir != '' else None
    
    for _ in range(sets):
        new_set = WorkoutSet(
            workout_id=workout_id,
            exercise_id=exercise_id,
            weight=weight,
            reps=reps,
            rpe=rpe,
            rir=rir,
            notes=notes,
            completed=False
        )
        db.session.add(new_set)
    
    db.session.commit()
    flash('Exercise added to workout', 'success')
    return redirect(url_for('view_workout', workout_id=workout_id))

# ----------------------- Profile Routes -----------------------

@app.route('/profile')
@login_required
def profile():
    # Total workouts
    total_workouts = Workout.query.filter_by(user_id=current_user.id, completed=True).count()
    
    # Workouts in the last 7 days
    one_week_ago = cstnow() - timedelta(days=7)
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

    # Collect form data
    form_data = {k: v for k, v in request.form.items() if k.startswith('sets[')}

    # Delete the exercise sets
    WorkoutSet.query.filter_by(
        workout_id=workout_id,
        exercise_id=exercise_id
    ).delete()

    db.session.commit()
    flash('Exercise removed from workout.', 'success')
    return redirect(url_for('view_workout', workout_id=workout_id, **form_data))

@app.route('/workout/set/<int:set_id>/delete', methods=['POST'])
@login_required
def delete_set(set_id):
    w_set = WorkoutSet.query.get_or_404(set_id)
    if w_set.workout.user_id != current_user.id:
        flash("You don't have access to this set.", 'error')
        return redirect(url_for('dashboard'))

    # Collect form data
    form_data = {k: v for k, v in request.form.items() if k.startswith('sets[')}

    workout_id = w_set.workout_id
    db.session.delete(w_set)
    db.session.commit()
    flash('Set deleted.', 'success')
    return redirect(url_for('view_workout', workout_id=workout_id, **form_data))

# ----------------------- History Edit Routes -----------------------

@app.route('/history/edit/<int:workout_id>')
@login_required
def edit_history(workout_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        flash("You don't have access to edit this workout.", 'error')
        return redirect(url_for('history'))
    
    available_exercises = Exercise.query.order_by(Exercise.category, Exercise.name).all()

    # Get previous performance data for each exercise
    last_performances = {}
    for s in workout.sets:
        if s.exercise_id not in last_performances:
            # Get the last workout that included this exercise
            previous_workout = Workout.query.join(WorkoutSet).filter(
                Workout.user_id == current_user.id,
                Workout.id != workout.id,
                WorkoutSet.exercise_id == s.exercise_id,
                WorkoutSet.completed == True,
                WorkoutSet.weight.isnot(None),
                WorkoutSet.reps.isnot(None)
            ).order_by(Workout.date.desc()).first()

            if previous_workout:
                # Get all sets from that workout for this exercise
                previous_sets = WorkoutSet.query.filter(
                    WorkoutSet.workout_id == previous_workout.id,
                    WorkoutSet.exercise_id == s.exercise_id,
                    WorkoutSet.completed == True,
                    WorkoutSet.weight.isnot(None),
                    WorkoutSet.reps.isnot(None)
                ).order_by(WorkoutSet.id).all()

                # Store each set's data in a dictionary
                last_performances[s.exercise_id] = {}
                for idx, prev_set in enumerate(previous_sets):
                    last_performances[s.exercise_id][idx] = {
                        'weight': prev_set.weight,
                        'reps': prev_set.reps,
                        'rpe': prev_set.rpe,
                        'date': previous_workout.date
                    }

    return render_template('edit_history.html', 
                         workout=workout,
                         last_performances=last_performances,
                         available_exercises=available_exercises,
                         is_editing=True)

@app.route('/history/edit/<int:workout_id>/save', methods=['POST'])
@login_required
def save_history_edit(workout_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403

    try:
        # Process each set's data
        for key, value in request.form.items():
            if not key.startswith('sets['):
                continue

            try:
                # Extract set ID and field using regex
                import re
                pattern = r'sets\[(\d+)\]\[(\w+)\]'
                match = re.match(pattern, key)
                if not match:
                    continue
                
                set_id = int(match.group(1))
                field = match.group(2)
                
                # Get the workout set
                workout_set = WorkoutSet.query.get(set_id)
                if not workout_set or workout_set.workout_id != workout_id:
                    continue

                # Update the appropriate field with proper type conversion
                value = value.strip()
                if value:  # Only process non-empty values
                    try:
                        if field == 'weight':
                            workout_set.weight = float(value)
                        elif field == 'reps':
                            workout_set.reps = int(value)
                        elif field == 'rpe':
                            rpe_value = float(value)
                            if not (1 <= rpe_value <= 10):
                                return jsonify({"error": f"Invalid RPE value: {rpe_value}. Must be between 1 and 10."}), 400
                            workout_set.rpe = rpe_value
                        elif field == 'rir':
                            rir_value = int(value)
                            if not (0 <= rir_value <= 9):
                                return jsonify({"error": f"Invalid RIR value: {rir_value}. Must be between 0 and 9."}), 400
                            workout_set.rir = rir_value
                    except (ValueError, TypeError) as e:
                        return jsonify({"error": f"Invalid value for {field}: {value}"}), 400
                else:
                    # Handle empty values by setting to None
                    setattr(workout_set, field, None)

            except (ValueError, IndexError) as e:
                return jsonify({"error": f"Error processing set data: {str(e)}"}), 400

        # Mark all sets as completed
        for workout_set in workout.sets:
            workout_set.completed = True

        db.session.commit()
        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400

@app.route('/history/edit/<int:workout_id>/exercise/add', methods=['POST'])
@login_required
def add_exercise_to_history(workout_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        flash("You don't have access to edit this workout.", 'error')
        return redirect(url_for('history'))
    
    exercise_id = request.form.get('exercise_id')
    sets = request.form.get('sets', 1)

    if not exercise_id or not sets:
        flash('Exercise and number of sets are required.', 'error')
        return redirect(url_for('edit_history', workout_id=workout_id))

    try:
        exercise_id = int(exercise_id)
        sets = int(sets)
    except ValueError:
        flash('Invalid input for exercise or sets.', 'error')
        return redirect(url_for('edit_history', workout_id=workout_id))

    for _ in range(sets):
        new_set = WorkoutSet(
            workout_id=workout_id,
            exercise_id=exercise_id,
            completed=True
        )
        db.session.add(new_set)
    
    db.session.commit()
    flash('Exercise added to workout.', 'success')
    return redirect(url_for('edit_history', workout_id=workout_id))

@app.route('/history/edit/<int:workout_id>/exercise/<int:exercise_id>/delete', methods=['POST'])
@login_required
def delete_exercise_from_history(workout_id, exercise_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        flash("You don't have access to edit this workout.", 'error')
        return redirect(url_for('history'))

    # Delete all sets for this exercise
    WorkoutSet.query.filter_by(
        workout_id=workout_id,
        exercise_id=exercise_id
    ).delete()

    db.session.commit()
    flash('Exercise removed from workout.', 'success')
    return redirect(url_for('edit_history', workout_id=workout_id))

@app.route('/history/edit/<int:workout_id>/set/<int:set_id>/delete', methods=['POST'])
@login_required
def delete_set_from_history(set_id, workout_id):
    workout_set = WorkoutSet.query.get_or_404(set_id)
    if workout_set.workout.user_id != current_user.id:
        flash("You don't have access to edit this workout.", 'error')
        return redirect(url_for('history'))

    db.session.delete(workout_set)
    db.session.commit()
    flash('Set deleted.', 'success')
    return redirect(url_for('edit_history', workout_id=workout_id))

@app.route('/history/edit/<int:workout_id>/exercise/<int:exercise_id>/add_set', methods=['POST'])
@login_required
def add_set_to_history_exercise(workout_id, exercise_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        flash("You don't have access to edit this workout.", 'error')
        return redirect(url_for('history'))
    
    new_set = WorkoutSet(
        workout_id=workout_id,
        exercise_id=exercise_id,
        completed=True
    )
    db.session.add(new_set)
    db.session.commit()
    
    flash('Set added.', 'success')
    return redirect(url_for('edit_history', workout_id=workout_id))

# ----------------------- Database Initialization -----------------------

def init_db():
    with app.app_context():
        db.create_all()
        if Exercise.query.count() == 0:
            exercises_data = [
                # Chest
                ('Bench Press', 'Chest', 'Barbell'),
                ('Incline Dumbbell Press', 'Chest', 'Dumbbell'),
                ('Dips', 'Chest', 'Bodyweight'),
                ('Standing Cable Chest Fly', 'Chest', 'Cable'),
                ('Assisted Dip', 'Chest', 'Assisted'),
                ('Band-Assisted Bench Press', 'Chest', 'Band'),
                ('Cable Crossover', 'Chest', 'Cable'),
                ('Close-Grip Bench Press', 'Chest', 'Barbell'),
                ('Decline Bench Press', 'Chest', 'Barbell'),
                ('Dumbbell Chest Fly', 'Chest', 'Dumbbell'),
                ('Push-Up', 'Chest', 'Bodyweight'),
                ('Ring Dip', 'Chest', 'Rings'),
                ('Smith Machine Bench Press', 'Chest', 'Smith Machine'),
                ('Incline Push-Up', 'Chest', 'Bodyweight'),
                ('Dumbbell Pullover', 'Chest', 'Dumbbell'),

                # Shoulders
                ('Overhead Press', 'Shoulders', 'Barbell'),
                ('Seated Dumbbell Shoulder Press', 'Shoulders', 'Dumbbell'),
                ('Dumbbell Lateral Raise', 'Shoulders', 'Dumbbell'),
                ('Reverse Dumbbell Fly', 'Shoulders', 'Dumbbell'),
                ('Reverse Machine Fly', 'Shoulders', 'Machine'),
                ('Arnold Press', 'Shoulders', 'Dumbbell'),
                ('Band Pull-Apart', 'Shoulders', 'Band'),
                ('Cable Lateral Raise', 'Shoulders', 'Cable'),
                ('Face Pull', 'Shoulders', 'Cable'),
                ('Landmine Press', 'Shoulders', 'Landmine'),
                ('Machine Shoulder Press', 'Shoulders', 'Machine'),

                # Back
                ('Deadlift', 'Back', 'Barbell'),
                ('Lat Pulldown', 'Back', 'Cable'),
                ('Pull-Up', 'Back', 'Bodyweight'),
                ('Barbell Row', 'Back', 'Barbell'),
                ('Dumbbell Row', 'Back', 'Dumbbell'),
                ('Seal Row', 'Back', 'Barbell'),
                ('T-Bar Row', 'Back', 'T-Bar'),
                ('Meadows row', 'Back', 'T-Bar'),
                ('Back Extensions', 'Back', 'Barbell/Dumbbell/Plate'),
                ('Inverted Row', 'Back', 'Bodyweight'),
                ('Trap Bar Deadlift', 'Back', 'Trap Bar'),
                ('Cable Seated Row', 'Back', 'Cable'),
                ('Straight Arm Lat Pulldown', 'Back', 'Cable'),
                ('Machine Row', 'Back', 'Machine'),

                # Biceps
                ('Barbell Curl', 'Biceps', 'Barbell'),
                ('Dumbbell Curl', 'Biceps', 'Dumbbell'),
                ('Hammer Curl', 'Biceps', 'Dumbbell'),
                ('Incline Dumbbell Curl', 'Biceps', 'Dumbbell'),
                ('Concentration Curl', 'Biceps', 'Dumbbell'),
                ('Cable Curl', 'Biceps', 'Cable'),
                ('Spider Curl', 'Biceps', 'Dumbbell'),
                ('Preacher Curl', 'Biceps', 'Barbell/Dumbbell'),

                # Triceps
                ('Barbell Lying Triceps Extension', 'Triceps', 'Barbell'),
                ('Overhead Cable Triceps Extension', 'Triceps', 'Cable'),
                ('Tricep Pushdown', 'Triceps', 'Cable'),
                ('Dips', 'Triceps', 'Bodyweight'),
                ('Close-Grip Bench Press', 'Triceps', 'Barbell'),
                ('Dumbbell Skull Crusher', 'Triceps', 'Dumbbell'),
                ('Barbell Skull Crusher', 'Triceps', 'Barbell'),
                ('Tricep Kickback', 'Triceps', 'Dumbbell'),
                ('Bench Dip', 'Triceps', 'Bodyweight'),

                # Quadriceps
                ('Squat', 'Quadriceps', 'Barbell'),
                ('Hack Squats', 'Quadriceps', 'Machine'),
                ('Leg Extension', 'Quadriceps', 'Machine'),
                ('Bulgarian Split Squat', 'Quadriceps', 'Dumbbell'),
                ('Front Squat', 'Quadriceps', 'Barbell'),
                ('Goblet Squat', 'Quadriceps', 'Dumbbell'),
                ('Smith Machine Squat', 'Quadriceps', 'Smith Machine'),

                # Hamstrings
                ('Seated Leg Curl', 'Hamstrings', 'Machine'),
                ('Lying Leg Curl', 'Hamstrings', 'Machine'),
                ('Romanian Deadlift', 'Hamstrings', 'Barbell'),
                ('Nordic Hamstring Curl', 'Hamstrings', 'Bodyweight'),
                ('Good Morning', 'Hamstrings', 'Barbell'),
                ('Stiff Leg Deadlift', 'Hamstrings', 'Barbell'),

                # Glutes
                ('Squat', 'Glutes', 'Barbell'),
                ('Lunges', 'Glutes', 'Barbell/Dumbbell'),
                ('Hip Thrust', 'Glutes', 'Barbell'),
                ('Romanian Deadlift', 'Glutes', 'Barbell'),
                ('Bulgarian Split Squat', 'Glutes', 'Dumbbell'),
                ('Glute Bridge', 'Glutes', 'Bodyweight'),
                ('Cable Pull Through', 'Glutes', 'Cable'),
                ('Reverse Hyperextension', 'Glutes', 'Machine'),

                # Abs
                ('Cable Crunch', 'Abs', 'Cable'),
                ('Machine Crunch', 'Abs', 'Machine'),
                ('Decline Sit Ups', 'Abs', 'Bodyweight'),
                ('Hanging Leg Raise', 'Abs', 'Bodyweight'),
                ('High to Low Wood Chop', 'Abs', 'Cable'),
                ('Crunch', 'Abs', 'Bodyweight'),
                ('Sit Ups', 'Abs', 'Bodyweight'),
                ('Leg Raise', 'Abs', 'Bodyweight'),
                ('Plank', 'Abs', 'Bodyweight'),
                ('Side Plank', 'Abs', 'Bodyweight'),
                ('Russian Twist', 'Abs', 'Bodyweight'),
                ('Mountain Climbers', 'Abs', 'Bodyweight'),

                # Calves
                ('Standing Calf Raise', 'Calves', 'Machine'),
                ('Seated Calf Raise', 'Calves', 'Machine'),
                ('Donkey Calf Raise', 'Calves', 'Machine'),
                ('Barbell Calf Raise', 'Calves', 'Barbell'),

                # Forearm Flexors & Grip
                ('Farmers Walk', 'Forearms', 'Dumbbell/Kettlebell'),
                ('Bar Hang', 'Forearms', 'Bodyweight'),
                ('Gripper', 'Forearms', 'Hand Gripper'),
                ('Plate Pinch', 'Forearms', 'Plate'),
                ('Wrist Roller', 'Forearms', 'Wrist Roller'),
                ('Wrist Curls', 'Forearms', 'Barbell/Dumbbell'),

                # Forearm Extensors
                ('Barbell Wrist Extension', 'Forearms', 'Barbell'),
                ('Dumbbell Wrist Extension', 'Forearms', 'Dumbbell'),
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
