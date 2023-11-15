import os
import json
import configparser
from flask import Flask, render_template, request, redirect, url_for, session
from database import Database
from service_manager import create_schemas, servicenow, splunk, backup_db, stop_servicenow, stop_splunk, generate_yaml
from logger import Logger
import service_manager

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'your_secret_key'  # Set a secret key for session management


def load_config():
    config = configparser.ConfigParser()
    config.read('settings.cfg')
    return config

# Initialize Logger
config = load_config()
logger = Logger()

def start_web_app():
    config = load_config()
    web_host = config.get('Web', 'host')
    web_port = int(config.get('Web', 'port'))
    web_debug = config.get('Web', 'debug').lower() in ['true', '1', 'yes']
    run_web_app(host=web_host, port=web_port, debug=web_debug)

@app.route('/')
def home():
    if 'username' in session:
        return render_template('index.html', username=session['username'])
    return redirect(url_for('login'))


@app.route('/manage_service', methods=['GET', 'POST'])
def manage_service():
    if request.method == 'POST':
        service = request.form['service']
        action = request.form.get('action', 'start')
        interval = int(request.form.get('interval', 60))  # New: Get interval from the form

        if action == 'start':
            if service == 'servicenow':
                service_manager.schedule_service(service_manager.servicenow, 'servicenow', interval)
            elif service == 'splunk':
                service_manager.schedule_service(service_manager.splunk, 'splunk', interval)
            # Add other services here...
        elif action == 'stop':
            if service == 'servicenow':
                service_manager.stop_servicenow()
            elif service == 'splunk':
                service_manager.stop_splunk()
            # Add stop logic for other services here...

    # Check the status of each service
    servicenow_status = 'Running' if 'servicenow' in service_manager.scheduled_services else 'Stopped'
    splunk_status = 'Running' if 'splunk' in service_manager.scheduled_services else 'Stopped'

    return render_template('manage.html', servicenow_status=servicenow_status, splunk_status=splunk_status)
    

@app.route('/generate_files')
def generate_files():
    try:
        service_manager.generate_yaml()
        return "YAML and HTML files generated successfully."
    except Exception as e:
        logger.error(f"Error generating files: {str(e)}")
        print(f"Error generating files: {str(e)}")
        return "Error generating files."

@app.route('/view_logs', methods=['GET'])
def view_logs():
    log_file = request.args.get('log_file')
    
    if log_file is None:
        return render_template('logs.html', logs="No log file selected.")
    else:
        log_path = os.path.join('logs', log_file)

        try:
            with open(log_path, 'r') as file:
                logs = [json.loads(line) for line in file if line.strip()]
        except FileNotFoundError:
            logs = "Log file not found."
        except json.JSONDecodeError:
            logs = "Error decoding log file."

        return render_template('logs.html', logs=json.dumps(logs, indent=4))


@app.route('/list_log_files', methods=['GET'])
def list_log_files():
    log_directory = 'logs'
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)  # Create the logs directory if it doesn't exist
    log_files = [f for f in os.listdir(log_directory) if f.endswith('.json')]
    return json.dumps(log_files)

@app.route('/get_logs', methods=['GET'])
def get_logs():
    log_file = request.args.get('log_file')
    log_path = os.path.join('logs', log_file)

    try:
        with open(log_path, 'r') as file:
            log_content = [json.loads(line) for line in file if line.strip()]
        return json.dumps(log_content)
    except FileNotFoundError:
        return json.dumps({"error": "Log file not found."}), 404
    except json.JSONDecodeError:
        return json.dumps({"error": "Error decoding log file."}), 500


@app.route('/execute_query', methods=['GET', 'POST'])
def execute_query():
    default_queries = get_default_queries()
    selected_query = None

    if request.method == 'POST':
        query = request.form['query']
        selected_query = query
        db = Database(config, logger)
        try:
            results, columns = db.execute_query(query)
            # Make sure to pass default_queries to the template
            return render_template('results.html', data=results, columns=columns, query=query, default_queries=default_queries, selected_query=selected_query)
        except Exception as e:
            # Pass default_queries here as well
            return render_template('results.html', error=str(e), query=query, default_queries=default_queries, selected_query=selected_query)
    else:
        query = None

    # This return is for handling GET requests
    return render_template('results.html', default_queries=default_queries, query=query, selected_query=selected_query)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = Database(load_config(), logger)
        user = db.validate_login(username, password)
        
        if user:
            session['username'] = user[0]  # Assuming user[0] is the username
            logger.info(f"User {username} logged in successfully.")
            return redirect(url_for('home'))
        else:
            error = 'Invalid Credentials. Please try again.'
            logger.error(f"Failed login attempt for {username}")

    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

def run_web_app(host='127.0.0.1', port=5000, debug=True):
    app.run(host=host, port=port, debug=debug)

def get_default_queries():
    db = Database(load_config(), logger)
    return db.get_default_select_queries(load_config())

if __name__ == "__main__":
    start_web_app()
