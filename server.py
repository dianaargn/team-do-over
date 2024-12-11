from flask import Flask, render_template, request
from history_page import*
from stats_page import*
from search_page import*
from new_workout_page import*
from profile_page import*

from waitress import serve

app = Flask(__name__)

#home page, has buttons to get to other pages, runs through 'templates/home.html'
@app.route('/')
@app.route('/index')
@app.route('/home')
def index():
    return render_template('base.html')

#past workouts page route, currently returns placeholder text
@app.route('/history')
def testAction():
    return test_page()

#search bar route, currently returns placeholder text
@app.route('/search')
def searchBar():
    return search()

#NEW WORKOUT PAGE STUFF
#new workout page route, currently returns placeholder text
@app.route('/new_workout')
def newWorkout():
    return render_template(
        "new_workout.html",
        template_list='get_list_function()',
        workout='current workout'
    )

@app.route('/start_workout')
def startWorkout():
    current_workout='get_current_workout_function()'
    #start_workout(current_workout)
    return render_template(
        "working_out.html"
    )




#stats page route, currently returns placeholder text
@app.route('/stats')
def showStats():
    return stats()

#profile page route, currently returns placeholder text
@app.route('/profile')
def showProfile():
    return profile()


if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8000)