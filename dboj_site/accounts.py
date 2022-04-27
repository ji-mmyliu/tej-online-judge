import os
import secrets, bcrypt
from flask import render_template, url_for, flash, redirect, request, abort
from dboj_site import app, settings, extras
from dboj_site.forms import LoginForm, UpdateAccountForm, PostForm, SubmitForm, RegisterForm
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

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = settings.find_one({"type":"user", "username":form.username.data})
        if not user is None:
            if not bcrypt.checkpw(form.password.data.encode(), user['password']):
                flash('Sorry, the password you entered is incorrect', 'danger')
                return redirect('/login')
            login_user(User(user['username']), remember=form.remember.data)
            next_page = request.args.get('next')
            flash('Login Success!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('No account exists under this username.', 'danger')
    return render_template('login.html', title='Log In', form=form)


@app.route("/logout")
def logout():
    logout_user()
    flash('Successfully logged out. See you later!', 'success')
    return redirect(url_for('home'))

@app.route("/register", methods = ["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        user = settings.find_one({"type":"user", "username":form.username.data})
        if not user is None:
            flash('A user with this name already exists', 'danger')
            return redirect('/register')
        if form.password.data != form.confirm.data:
            flash('Password confirmation does not match', 'danger')
            return redirect('/register')
        hashed_pw = bcrypt.hashpw(form.password.data.encode(), bcrypt.gensalt())
        settings.insert_one({"type":"user", "username":form.username.data, "password":hashed_pw, "id":settings.find_one({"type":"id_cnt"})['cnt'], "admin":False})
        settings.update_one({"type":"id_cnt"}, {"$inc":{"cnt":1}})
        flash('Account successfully created!', 'success')
        return redirect('/home')
    return render_template("register.html", title="Register", form = form)
