from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workouts.db'
db = SQLAlchemy(app)

def upgrade_db():
    with app.app_context():
        # Add start_time column with default value
        db.engine.execute('ALTER TABLE workout ADD COLUMN start_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP')
        # Add duration column
        db.engine.execute('ALTER TABLE workout ADD COLUMN duration INTEGER')
        
        # Update existing workouts to use their date as start_time
        db.engine.execute('UPDATE workout SET start_time = date WHERE start_time IS NULL')

if __name__ == '__main__':
    upgrade_db()
    print("Database upgrade completed successfully!")