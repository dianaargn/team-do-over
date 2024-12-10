from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workouts.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

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

# Template Model
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

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def root():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user = User(
            username=request.form['username'],
            email=request.form['email']
        )
        user.set_password(request.form['password'])
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    folders = Folder.query.filter_by(user_id=current_user.id).all()
    recent_workouts = Workout.query.filter_by(user_id=current_user.id).order_by(Workout.date.desc()).limit(5).all()
    return render_template('dashboard.html', folders=folders, recent_workouts=recent_workouts)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/folder/<int:folder_id>')
@login_required
def view_folder(folder_id):
    folder = Folder.query.get_or_404(folder_id)
    if folder.user_id != current_user.id:
        return redirect(url_for('dashboard'))
    return render_template('folder.html', folder=folder)

@app.route('/folder/create', methods=['POST'])
@login_required
def create_folder():
    folder = Folder(
        name=request.form['name'],
        user_id=current_user.id
    )
    db.session.add(folder)
    db.session.commit()
    flash('Folder created successfully', 'success')
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

@app.route('/template/<int:template_id>/start', methods=['POST', 'GET'])
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

@app.route('/workout/<int:workout_id>')
@login_required
def view_workout(workout_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        flash("You don't have access to this workout.", 'error')
        return redirect(url_for('dashboard'))

    return render_template('view_workout.html', workout=workout)

@app.route('/workout/<int:workout_id>/set/<int:set_id>/update', methods=['POST'])
@login_required
def update_set(workout_id, set_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        flash("You don't have access to this workout.", 'error')
        return redirect(url_for('dashboard'))

    w_set = WorkoutSet.query.get_or_404(set_id)
    if w_set.workout_id != workout_id:
        flash("Invalid set for this workout.", 'error')
        return redirect(url_for('view_workout', workout_id=workout_id))

    weight = request.form.get('weight')
    reps = request.form.get('reps')
    rpe = request.form.get('rpe')
    rir = request.form.get('rir')

    if weight == '':
        weight = None
    else:
        weight = float(weight) if weight else None

    if reps == '' or reps is None:
        reps = 0
    else:
        reps = int(reps)

    if rpe == '':
        rpe = None
    else:
        rpe = float(rpe) if rpe else None

    if rir == '':
        rir = None
    else:
        rir = int(rir) if rir else None

    # Automatically mark completed as True since set is updated
    w_set.weight = weight
    w_set.reps = reps
    w_set.rpe = rpe
    w_set.rir = rir
    w_set.completed = True

    db.session.commit()
    flash("Set updated and marked as completed!", "success")
    return redirect(url_for('view_workout', workout_id=workout_id))

@app.route('/workout/<int:workout_id>/finish', methods=['POST'])
@login_required
def finish_workout(workout_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        flash("You don't have access to this workout.", 'error')
        return redirect(url_for('dashboard'))

    # Mark workout as completed
    workout.completed = True
    db.session.commit()
    flash("Workout logged successfully!", "success")
    return redirect(url_for('dashboard'))

@app.route('/search_exercises')
def search_exercises():
    query = request.args.get('q', '').lower()
    exercises = Exercise.query.filter(Exercise.name.ilike(f'%{query}%')).all()
    return jsonify([exercise.to_dict() for exercise in exercises])

def init_db():
    with app.app_context():
        db.create_all()
        if Exercise.query.count() == 0:
            exercises_data = [
                ('Bench Press', 'Chest', 'Barbell'),
                ('Incline Bench Press', 'Chest', 'Barbell'),
                ('Decline Bench Press', 'Chest', 'Barbell'),
                ('Dumbbell Chest Press', 'Chest', 'Dumbbell'),
                ('Push-Up', 'Chest', 'Bodyweight'),
                ('Bent Over Row', 'Back', 'Barbell'),
                ('Pull-Up', 'Back', 'Bodyweight'),
                ('Lat Pulldown', 'Back', 'Cable'),
                ('Deadlift', 'Back', 'Barbell'),
                ('Overhead Press', 'Shoulders', 'Barbell'),
                ('Lateral Raise', 'Shoulders', 'Dumbbell'),
                ('Front Raise', 'Shoulders', 'Barbell'),
                ('Bicep Curl', 'Arms', 'Dumbbell'),
                ('Tricep Extension', 'Arms', 'Cable'),
                ('Hammer Curl', 'Arms', 'Dumbbell'),
                ('Squat', 'Legs', 'Barbell'),
                ('Romanian Deadlift', 'Legs', 'Barbell'),
                ('Leg Press', 'Legs', 'Machine'),
                ('Plank', 'Core', 'Bodyweight'),
                ('Crunch', 'Core', 'Bodyweight'),
                ('Russian Twist', 'Core', 'Bodyweight'),
            ]

            for name, category, equipment in exercises_data:
                exercise = Exercise(name=name, category=category, equipment=equipment)
                db.session.add(exercise)

            db.session.commit()

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
