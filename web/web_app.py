import os
import json
import configparser
from flask import Flask, render_template, request, redirect, url_for, session
from database import Database
from service_manager import create_schemas, servicenow, splunk, backup_db, stop_servicenow, stop_splunk, generate_yaml
from logger import Logger
import service_manager
from services.servicenow_api import ServiceNowAPI

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
            elif service == 'create_schemas':
                service_manager.create_schemas()
            elif service == 'backup':
                service_manager.backup_db()
            # Add other services here...
        elif action == 'stop':
            if service == 'servicenow':
                service_manager.stop_servicenow()
            elif service == 'splunk':
                service_manager.stop_splunk()

    # Check the status of each service
    servicenow_status = 'Running' if 'servicenow' in service_manager.scheduled_services else 'Stopped'
    splunk_status = 'Running' if 'splunk' in service_manager.scheduled_services else 'Stopped'

    return render_template('manage.html', servicenow_status=servicenow_status, splunk_status=splunk_status)
    
@app.route('/yaml')
def manage_yaml():
    forms_data = service_manager.generate_yaml()
    # Use forms_data to pass information to your template
    return render_template('yaml.html', forms=forms_data)

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
            session['username'] = user[1]  # user[1] is the username
            session['group_id'] = user[4]  # user[4] is the group ID, adjust index as needed
            logger.info(f"User {username} logged in successfully.")
            return redirect(url_for('home'))
        else:
            error = 'Invalid Credentials. Please try again.'
            logger.error(f"Failed login attempt for {username}")

    return render_template('login.html', error=error)

@app.route('/deployment', methods=['GET', 'POST'])
def deployment():
    if request.method == 'POST':
        # Extract ticket description from the form data
        ticket_description = request.form['description']

        # Call a function to handle the ServiceNow ticket creation
        # This function should be implemented in your logic (not shown here)
        #create_servicenow_ticket(ticket_description)

        # Redirect to a confirmation page or back to the ticket creation page
        # with a success message
        return redirect(url_for('ticket_created'))
    else:
        return render_template('deployment.html')

@app.route('/ticket_created')
def ticket_created():
    return render_template('ticket_created.html')

@app.route('/tasks')
def show_tasks():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    db = Database(config, logger)
    username = session['username']

    # Read snow_states from config
    snow_states = config.get('Web', 'snow_states').split(', ')

    # Fetch the user's name using view_data
    user_fields = ['name']
    user_conditions = {'username': username}

    user_data = db.view_data('users', user_fields, user_conditions)
    if not user_data:
        return "User not found", 404

    print(user_data)
    user_name = user_data[0]['name']  # Assuming the first column is 'name'

    # Define the JOIN clause and the fields you want to retrieve
    join_clause = "LEFT JOIN snow_options ON snow_tasks.sys_id = snow_options.sys_id"
    task_fields = ['snow_tasks.sys_id', 'snow_tasks.description', 'snow_tasks.state', 'snow_tasks.work_notes', 'snow_options.name']

    # Fetch tasks using the existing view_data method
    tasks = db.view_data('snow_tasks', task_fields, {'assigned_to': user_name}, join=join_clause)
    print(tasks)
    
    return render_template('tasks.html', tasks=tasks, username=user_name, snow_states=snow_states)

@app.route('/update_task', methods=['POST'])
def update_task():
    sys_id = request.form['sys_id']
    new_state = request.form['state']
    new_work_notes = request.form['work_notes']

    # Update the task in the PostgreSQL database
    db = Database(config, logger)
    db.update_task(sys_id, new_state, new_work_notes)

    # Update the task in ServiceNow
    servicenow_api = ServiceNowAPI(config, logger)
    servicenow_api.update_service_now_task(sys_id, new_state, new_work_notes)

    return redirect(url_for('show_tasks'))


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        config = configparser.ConfigParser()
        config.read('settings.cfg')

        # Iterate over form data and update config
        for key in request.form:
            section, option = key.split('.')
            config.set(section, option, request.form[key])

        # Write changes back to the file
        with open('settings.cfg', 'w') as configfile:
            config.write(configfile)

        return redirect(url_for('config'))
    else:
        config = load_config()
        return render_template('settings.html', config=config)

@app.route('/group_tasks')
def group_tasks():
    # Use the group_id from the session
    group_id = session.get('group_id')
    
    if not group_id:
        return "Group information not found in session", 403

    db = Database(config, logger)
    task_fields = ['snow_tasks.sys_id', 'snow_tasks.description', 'snow_tasks.state', 'snow_tasks.work_notes', 'snow_options.name']
    join_clause = "LEFT JOIN snow_options ON snow_tasks.sys_id = snow_options.sys_id"
    tasks = db.view_data('snow_tasks', task_fields, {'assignment_group': group_id}, join=join_clause)

    return render_template('group_tasks.html', tasks=tasks, group_id=group_id)



@app.route('/notes')
def notes():
    if 'username' not in session:
        return redirect(url_for('login'))

    db = Database(config, logger)
    session_username = session['username']  # Logged-in user's username

    # Fetch notes belonging to the logged-in user
    notes_conditions = {'username': session_username}
    user_notes = db.view_data('notes', ['uc_id', 'description', 'username'], notes_conditions)

    return render_template('notes.html', notes=user_notes)



@app.route('/submit_note', methods=['POST'])
def submit_note():
    uc_id = request.form['uc_id']
    description = request.form['description']
    username = session['username']  # Assuming the username is stored in the session

    db = Database(config, logger)
    db.upsert_data('notes', ['uc_id', 'description', 'username'], {'uc_id': uc_id, 'description': description, 'username': username}, ['id'])

    return redirect(url_for('notes'))


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
