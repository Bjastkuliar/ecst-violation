import sqlite3
import logging
import pika
import time
import threading
import json
from flask import Flask
from flask import request
from flask import Response
import os
from datetime import datetime
import requests
from opentelemetry import trace
from opentelemetry . sdk . trace import TracerProvider
from opentelemetry . sdk . trace . export import BatchSpanProcessor
from opentelemetry . exporter . otlp . proto . http . trace_exporter import OTLPSpanExporter
from opentelemetry . instrumentation . requests import RequestsInstrumentor
from opentelemetry . instrumentation . flask import FlaskInstrumentor

app = Flask(__name__)

trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(OTLPSpanExporter())) 
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()

@app.route("/")
def hello():
    return "Hello World from the search service!"

@app.route("/search")
def search():
    start = request.args.get("date")
    duration = request.args.get("duration")

    if start == None or duration == None:
        return Response('{"result": false, "error": 1, "description": "Cannot proceed because you did not provide start and duration for the search."}', status=400, mimetype="application/json")

    start_as_datetime = datetime.strptime(start, "%Y%m%d")
    from_as_timestamp = start_as_datetime.timestamp()
    to_as_timestamp = from_as_timestamp + int(duration) * 24 * 60

    logging.info(f"Searching for appartments not reserved from {from_as_timestamp} to {to_as_timestamp}...")

    db_connection = sqlite3.connect("/home/data/search.db", isolation_level=None)
    cursor = db_connection.cursor()
    cursor.execute("SELECT name FROM apartments WHERE id NOT IN (SELECT apartment FROM reservations WHERE ((period_from < ? AND period_to > ?) OR (period_from < ? AND period_to > ?) OR (period_from <= ? AND period_to >= ?)))", (from_as_timestamp, from_as_timestamp, to_as_timestamp, to_as_timestamp, from_as_timestamp, to_as_timestamp))
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    cursor.close()
    db_connection.close()
    return Response(json.dumps({"apartments": rows}), status=200, mimetype="application/json")


def apartment_or_reservations_changed(ch, method, properties, body):
    data = json.loads(body)

    if method.exchange == "apartments":
        if method.routing_key == "added":
            id = data["id"]
            name = data["name"]

            logging.info(f"Adding apartment {name}...")

            db_connection = sqlite3.connect("/home/data/search.db", isolation_level=None)
            cursor = db_connection.cursor()
            cursor.execute("INSERT INTO apartments VALUES (?, ?)", (id, name))
            cursor.close()
            db_connection.close()

        if method.routing_key == "deleted":
            name = data["name"]

            logging.info(f"Deleting apartment {name}...")

            db_connection = sqlite3.connect("/home/data/search.db", isolation_level=None)
            cursor = db_connection.cursor()
            cursor.execute("DELETE FROM apartments WHERE name = ?", (name,))
            cursor.close()
            db_connection.close()

    if method.exchange == "reservations":
        if method.routing_key == "added":
            id = data["id"]
            apartment = data["apartment"]
            period_from = int(data["from"])
            period_to = int(data["to"])

            logging.info(f"Adding reservation {id}...")

            db_connection = sqlite3.connect("/home/data/search.db", isolation_level=None)
            cursor = db_connection.cursor()
            cursor.execute("INSERT INTO reservations (id, apartment, period_from, period_to) VALUES (?, ?, ?, ?)", (id, apartment, period_from, period_to))
            cursor.close()
            db_connection.close()

        if method.routing_key == "deleted":
            id = data["id"]

            logging.info(f"Deleting reservation {id}...")

            db_connection = sqlite3.connect("/home/data/search.db", isolation_level=None)
            cursor = db_connection.cursor()
            cursor.execute("DELETE FROM reservations WHERE id = ?", (id,))
            cursor.close()
            db_connection.close()


def connect_to_mq():
    while True:
        time.sleep(10)

        try:
            return pika.BlockingConnection(pika.ConnectionParameters(host="rabbitmq"))
        except Exception as e:
            logging.warning(f"Could not start listening to the message queue, retrying...")


def listen_to_events(channel):
    channel.start_consuming()



if __name__ == "__main__":
    logging.basicConfig(format="%(message)s", level=1 * 10)
    logging.getLogger("pika").setLevel(logging.WARNING)
    logging.getLogger("sqlite3").setLevel(logging.WARNING)

    mq_connection = connect_to_mq()

    channel = mq_connection.channel()
    channel.exchange_declare(exchange="apartments", exchange_type="direct")
    channel.exchange_declare(exchange="reservations", exchange_type="direct")
    result = channel.queue_declare(queue="", exclusive=True)
    queue_name = result.method.queue
    channel.queue_bind(exchange="apartments", queue=queue_name, routing_key="added")
    channel.queue_bind(exchange="apartments", queue=queue_name, routing_key="deleted")
    channel.queue_bind(exchange="reservations", queue=queue_name, routing_key="added")
    channel.queue_bind(exchange="reservations", queue=queue_name, routing_key="deleted")
    channel.basic_consume(queue=queue_name, on_message_callback=apartment_or_reservations_changed, auto_ack=True)

    logging.info("Waiting for messages.")

    thread = threading.Thread(target=listen_to_events, args=(channel,), daemon=True)
    thread.start()

    # Verify if database has to be initialized
    database_is_initialized = False
    if os.path.exists("/home/data/search.db"):
        database_is_initialized = True
    else:
        db_connection = sqlite3.connect("/home/data/search.db", isolation_level=None)
        cursor = db_connection.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS apartments (id text, name text)")
        cursor.execute("CREATE TABLE IF NOT EXISTS reservations (id text, apartment text, period_from integer, period_to integer)")

        while True:
            try:
                data = requests.get(f"http://apartments:5000/apartments").json()
                for entry in data["apartments"]:
                    cursor.execute("INSERT INTO apartments VALUES (?, ?)", (entry["id"], entry["name"]))
                break
            except Exception as e:
                print(e)
                logging.warning("Apartments is down, reconnecting...")
                time.sleep(5)
            
        while True:
            try:
                data = requests.get(f"http://reserve:5000/reservations").json()
                for entry in data["reservations"]:
                    cursor.execute("INSERT INTO reservations (id, apartment, period_from, period_to) VALUES (?, ?, ?, ?)", (entry["id"], entry["apartment"], entry["period_from"], entry["period_to"]))
                break
            except:
                logging.warning("Reservations are down, reconnecting...")
                time.sleep(5)

        cursor.close()
        db_connection.close()
        database_is_initialized = True

    if not database_is_initialized:
        logging.error("Cannot initialize database.")
    else:
        try:
            logging.info("Start.")
            app.run(host="0.0.0.0", threaded=True)
        finally:
            mq_connection.close()
