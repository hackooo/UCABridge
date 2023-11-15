import argparse
import time
import threading
from service_manager import create_schemas, servicenow, splunk, run_web, backup_db, schedule_service

services = {
    'create_schemas': create_schemas,
    'servicenow': servicenow,
    'splunk': splunk,
    'web': run_web,
    'backup_db': backup_db
}

def main():
    parser = argparse.ArgumentParser(description="Command line tool for various operations.")
    parser.add_argument("command", help="The command to execute")
    parser.add_argument("--interval", help="Interval in minutes for scheduling a service", type=int, default=60)
    args = parser.parse_args()

    if args.command in services:
        if args.command == 'web':  # Web service should run immediately without scheduling
            services[args.command]()
        else:
            schedule_service(services[args.command], args.interval)

if __name__ == "__main__":
    main()
