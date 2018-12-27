from flask import session
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, FileField
from wtforms.fields.html5 import EmailField
from wtforms.validators import DataRequired, length


class SubmitForm(FlaskForm):
    file_upload = FileField('Upload File', validators=[DataRequired()])


class AuthForm(FlaskForm):
    email = EmailField('E-mail', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])


class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), length(max=16)])
    email = EmailField('E-mail', validators=[DataRequired(), length(max=128)])
    password = PasswordField('Password', validators=[DataRequired(), length(max=32)])
