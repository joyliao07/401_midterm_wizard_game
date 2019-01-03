import pytz
import os
import boto3, botocore
from uuid import uuid4
from datetime import datetime, timedelta
from os.path import splitext
from os.path import join as path_join
from os import remove as remove_file

from flask import Flask, request, render_template, redirect, url_for, session, abort, flash, session, g
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from werkzeug.utils import secure_filename

from .auth import login_required, logout_required
from .forms import SubmitForm
from .models import db, Submission, Prompt, Account
from .gvision import ProcessedImage
from .submissions import evaluate_submission
from .prompt import random_generator

from . import app


@app.route('/')
def home():
    """
    get: user visits homepage
    """
    return render_template('pages/home.html')


@app.route('/play', methods=['GET', 'POST'])
@login_required
def play():
    """
    get: visiting page to submit photo
    post: receiving submission form from user
    """

    if session.get('recent_image_path'):
        del session['recent_image_path']
        del session['recent_submission_id']

    form = SubmitForm()

    prompt = Prompt.query.order_by(Prompt.id.desc()).first()

    if prompt is None:
        random_generator()
        prompt = Prompt.query.order_by(Prompt.id.desc()).first()

    if form.validate_on_submit():
        allowed_filetypes = set(['.png', '.jpg', '.jpeg'])

        f = form.file_upload.data
        ext = splitext(f.filename)[1]

        if ext not in allowed_filetypes:
            flash('File must be a .png or a .jpg/.jpeg')
            return redirect(url_for('.play'))

        filename = secure_filename(str(uuid4()) + ext)
        file_path = path_join(app.root_path, app.config['UPLOAD_FOLDER'], filename)
        f.save(file_path)

        # TRY TO UPLOAD PICTURE TO S3 HERE:
        # If passing in "f", error: expecting string or bytes-like object
        # If passing in "file_path", error: Fileobj must implement read

        upload_file_to_s3(f, "wizardphoto", acl="public-read")

        try:
            time_pacific = datetime.now() + timedelta(hours=-8)

            submission = Submission(
                image_path=filename,
                prompt_id=prompt.id,
                submitted_by=session.get('account_id'),
                passes_prompt=False,
                submission_time=time_pacific
            )

            db.session.add(submission)
            db.session.commit()

            session['recent_image_path'] = filename
            session['recent_submission_id'] = submission.id
            return redirect(url_for('.submission'))

        except IntegrityError:
            remove_file(file_path)
            flash('There was an error uploading your submission')
            return redirect(url_for('.submission'))

    return render_template('pages/play.html', form=form, prompt=prompt)


s3 = boto3.client(
   "s3",
   aws_access_key_id=os.environ.get('S3_KEY'),
   aws_secret_access_key=os.environ.get('S3_SECRET_ACCESS_KEY'),
)


def upload_file_to_s3(file, bucket_name, acl="public-read"):
    """
    Docs: http://zabana.me/notes/upload-files-amazon-s3-flask.html
    """
    try:
        print('trying file upload')
        s3.upload_fileobj(
            file,
            bucket_name,
            file.filename,
            ExtraArgs={
                "ACL": acl,
                "ContentType": file.content_type
            }
        )
        new_path="{}{}".format('https://s3-us-west-1.amazonaws.com/wizardphoto/', file.filename)

    except Exception as e:
        print('error msg from upload')
        print("Something Happened: ", e)
        return e

    return "{}{}".format(app.config["S3_LOCATION"], file.filename)


@app.route('/submission', methods=['GET', 'POST'])
@login_required
def submission():
    """
    get: viewing submission and confirming
    post: user confirms submission for evaluation
    """
    if session.get('recent_image_path'):
        prompt = Prompt.query.order_by(Prompt.id.desc()).first()

        image_path = session.get('recent_image_path')

        return render_template('pages/submission.html', image_path=image_path, prompt=prompt)

    abort(404)


@app.route('/feedback')
@login_required
def feedback():
    """
    get: user sees whether submission passed/failed
    """

    if session.get('recent_image_path'):
        submission_id = session.get('recent_submission_id')
        prompt = Prompt.query.order_by(Prompt.id.desc()).first()
        image_path = session.get('recent_image_path')

        image = ProcessedImage(path_join(app.root_path, app.config['UPLOAD_FOLDER'], image_path))
        status = evaluate_submission(image, (prompt.adjective, prompt.noun))

        if status[0] is True and status[1] is True:
            submission = Submission.query.filter(Submission.id == submission_id).first()
            submission.passes_prompt = True
            db.session.commit()

            random_generator()

        del session['recent_image_path']
        del session['recent_submission_id']

        return render_template('pages/feedback.html', adjective=status[0], noun=status[1], prompt=prompt)

    abort(404)


@app.route('/history')
@login_required
def history():
    """
    get: user views their own history
    """
    user = g.user.id
    all = Submission.query.filter(Submission.submitted_by == user).order_by(Submission.submission_time.desc()).all()

    # To get the number of submission all time:
    all_time_count = Submission.query.filter(Submission.submitted_by == user).filter(Submission.passes_prompt == True).count()

    # To get the number of submission today:

    date = datetime.now().date()

    today_count = Submission.query.filter(Submission.submitted_by == user).filter(Submission.passes_prompt == True).filter(func.date(Submission.submission_time) == date).count()

    # To get the number of submission of the past week:

    now = datetime.now()
    week_ago = now - timedelta(days=7)

    week_count = Submission.query.filter(Submission.submitted_by == user).filter(Submission.passes_prompt == True).filter(Submission.submission_time > week_ago).count()

    # To Pass all submission history:

    history = []

    for what in all:
        user = Account.query.filter(Account.id == what.submitted_by).first()
        prompt = Prompt.query.filter(Prompt.id == what.prompt_id).first()

        history.append({
            'time': str(what.submission_time)[:16] + ' PST',
            'image': what.image_path,
            'adjective': prompt.adjective,
            'noun': prompt.noun,
            'result': 'Pass' if what.passes_prompt is True else 'Fail'
        })

    return render_template('pages/history.html', history=history, all_time_count=all_time_count, today_count=today_count, week_count=week_count)


@app.route('/players')
@login_required
def players():
    """
    get: user views others' history
    """

    top_5 = Submission.query.filter(Submission.passes_prompt == 't').order_by(Submission.submission_time.desc()).limit(15)

    compiled = []

    for what in top_5:
        user = Account.query.filter(Account.id == what.submitted_by).first()
        prompt = Prompt.query.filter(Prompt.id == what.prompt_id).first()

        score = Submission.query.filter(Submission.submitted_by == what.submitted_by).filter(Submission.passes_prompt == True).count()

        compiled.append({
            'time': str(what.submission_time)[:16] + ' PST',
            'user': user.username,
            'score': score,
            'image': what.image_path,
            'adjective': prompt.adjective,
            'noun': prompt.noun
            })

    return render_template('pages/players.html', compiled=compiled)
