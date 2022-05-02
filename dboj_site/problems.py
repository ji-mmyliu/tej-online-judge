import os, sys, yaml
import secrets
from flask import render_template, make_response, send_from_directory, send_file, url_for, flash, redirect, request, abort
from dboj_site import app, settings, extras, bucket
from dboj_site import problem_uploading as problem_uploading
from dboj_site.forms import LoginForm, UpdateAccountForm, PostForm, SubmitForm
from dboj_site.models import User
from flask_login import login_user, current_user, logout_user, login_required
from google.cloud import storage
from functools import cmp_to_key
from flaskext.markdown import Markdown
from dboj_site.judge import *
from dboj_site.extras import *
from multiprocessing import Process, Manager
from werkzeug.utils import secure_filename
md = Markdown(app,
              safe_mode=True,
              output_format='html4',
             )

def in_contest(post):
    elapsed = contests.compare(post['start'], contests.current_time())
    contest_len = getLen(settings, post['mode'])
    return elapsed <= contest_len

def contest_problems(problems):
    if not current_user.is_authenticated or current_user.is_anonymous:
        return None
    contest = None
    for x in settings.find({"type":"access", "name":current_user.name}):
        if x['mode'] != 'admin' and x['mode'] != 'owner' and in_contest(x):
            contest = x['mode']
    if not contest:
        return None

    solved = []
    try:
        solved = settings.find_one({"type":"profile", "name":current_user.name})['solved']
    except:
        pass

    for problem in settings.find({"type":"problem", "contest":contest}):
        if not perms(problem, current_user.name):
            problems.append((problem['name'], problem['name'] in solved, problem['points'], ", ".join(problem['types']), ", ".join(problem['authors'])))
    problems.sort(key = cmp_to_key(cmpProblem))
    return contest

@app.route("/problems")
def problems():
    problems = []
    contest = contest_problems(problems)
    if not contest:
        problems = sorted([(x['name'], x['points'], ", ".join(x['types']), ", ".join(x['authors'])) for x in settings.find({"type":"tej-task", "published":True})], key = cmp_to_key(extras.cmpProblem))
    return render_template('problems.html', problems=problems, contest=contest, title="Problems")

@app.route("/problems/private")
@login_required
def private_problems():
    arr = []
    for x in settings.find({"type":"problem", "published":False}):
        if not extras.perms(x, current_user.name):
            arr.append((x['name'], x['points'], x['contest'], ", ".join(x['types']), ", ".join(x['authors'])))
    arr = sorted(arr, key = cmp_to_key(cmpProblem))
    return render_template('private_problems.html', private_problems = arr, title = "Private problems visible to " + current_user.name)

@app.route("/viewproblem/<string:problemName>")
def viewProblem(problemName):
    problem = settings.find_one({"type":"tej-task", "name":problemName})
    if problem is None:
        abort(404)
    elif (not problem['published'] and (not current_user.is_authenticated or current_user.is_anonymous or (perms(problem, current_user.name)))):
        abort(403)
        
    src = None
    try:
        bucket.blob("ProblemStatements/" + problemName + ".txt").download_to_filename("statement.md")
        src = open("statement.md", "r").read()
    except:
        src = "This problem does not yet have a problem statement."

    return render_template('view_problem.html', title="View problem " + problemName, problemName=problemName, src = ("\n" + src.replace("<", "%lft%").replace(">", "%rit%")))

@app.route("/viewproblem/<string:problemName>/submit", methods=['GET', 'POST'])
@login_required
def submit(problemName):
    problem = settings.find_one({"type":"tej-task", "name":problemName})
    if problem is None:
        abort(404)
    elif (not problem['published'] and (not current_user.is_authenticated or current_user.is_anonymous or (perms(problem, current_user.name)))):
        abort(403)

    form = SubmitForm()
    if form.validate_on_submit():
        sub_cnt = settings.find_one({"type":"sub_cnt"})['cnt']
        settings.update_one({"type":"sub_cnt"}, {"$inc":{"cnt":1}})
        
        lang = form.lang.data.lower()
        src = form.src.data
        settings.insert_one({"type":"submission", "problem":problemName, "author":current_user.name, "lang":lang, "message":src, "id":sub_cnt, "output":"", "status":"In progress"})        

        judges = settings.find_one({"type":"tej-judge", "status":0})
        
        manager = Manager()
        return_dict = manager.dict()
        rpc = Process(target = runSubmission, args = (judges, current_user.name, src, lang, problemName, False, return_dict, sub_cnt,))
        rpc.start()

        return redirect('/submission/' + str(sub_cnt))
    return render_template('submit.html', title='Submit to ' + problemName,
                        form=form, pn = problemName, user = current_user, sub_problem=problemName)
    

@app.route("/raw_submission/<int:sub_id>")
@login_required
def raw_submission(sub_id):
    sub = settings.find_one({"type":"submission", "id":sub_id})
    if not sub:
        abort(404)
    elif not current_user.is_admin and sub['author'] != current_user.name:
        abort(403)
    output = sub['output'].replace("diff", "").replace("`", "").replace("+ ", "  ").replace("- ", "  ").replace(" ", "%sp%").strip().replace("\n", "%nl%")
    response = make_response(output)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

@app.route("/submission/<int:sub_id>")
@login_required
def submission(sub_id):
    sub = settings.find_one({"type":"submission", "id":sub_id})
    if not sub:
        abort(404)
    elif not current_user.is_admin and sub['author'] != current_user.name:
        abort(403)
    return render_template('submission.html', title="Submission " + str(sub_id), sub_problem=sub['problem'], sub_id=sub_id)
    
@app.route("/viewproblem/<string:problemName>/submissions")
def submission_page(problemName):
    submissions = []
    for x in settings.find({"type":"submission", "problem":problemName}):
        if 'status' in x:
            submissions.append(x)
    submissions.reverse()
    return render_template('submission-page.html', title="Submissions for " + problemName, problemName = problemName, submissions = submissions)

@app.route("/submission/<int:sub_id>/source")
@login_required
def view_source(sub_id):
    sub = settings.find_one({"type":"submission", "id":sub_id})
    if not sub:
        abort(404)
    elif not current_user.is_admin and sub['author'] != current_user.name:
        abort(403)
    return render_template('view_source.html', title="View source from " + str(sub_id), sub_problem=sub['problem'], lang=sub['lang'], sid=sub_id, src=sub['message'].replace("\n", "%nl%").replace("\t", "%sp%%sp%%sp%%sp%").replace(" ", "%sp%"), author=sub['author'])

@app.route("/submission/<int:sub_id>/source/raw")
@login_required
def raw_source(sub_id):
    sub = settings.find_one({"type":"submission", "id":sub_id})
    if not sub:
        abort(404)
    elif not current_user.is_admin and sub['author'] != current_user.name:
        abort(403)
    with open("dboj_site/static/raw_source.txt", "w") as f:
        f.write(sub['message'].strip().replace("\n\n", "\n"))
    return send_from_directory('static', 'raw_source.txt')
    
def is_busy():
    return settings.find_one({"type":"busy"})['busy']
