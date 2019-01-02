from . import app
from flask import render_template


@app.errorhandler(404)
def not_found(error):
    """404 page"""
    return render_template('errors/404_notfound.html', error=error), 404


@app.errorhandler(405)
def bad_method(error):
    """405 page"""
    return render_template('errors/405_bad_method.html', error=error), 405


@app.errorhandler(500)
def server_error(error):
    """ server error """
    return render_template('errors/500_server_error.html', error=error), 500
