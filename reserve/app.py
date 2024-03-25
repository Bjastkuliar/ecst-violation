import sqlite3
import uuid
from flask import request
from flask import Flask
from flask import Response
import logging
import pika
import json
import time
import os
from datetime import datetime
import threading
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

@app.route("/add")
def add():
    id = uuid.uuid4()
    apartment = request.args.get("name")
    start = request.args.get("start")
    duration = request.args.get("duration")
    vip = request.args.get("vip")

    if apartment == None or start == None or duration == None or vip == None:
        return Response('{"result": false, "error": 1, "description": "Cannot proceed because you did not provide name, start, duration and vip status for the reservation."}', status=400, mimetype="application/json")

    vip_as_integer = 1 if vip == "1" else 0

    # Connect and setup the database
    db_connection = sqlite3.connect("/home/data/reservations.db", isolation_level=None)
    cursor = db_connection.cursor()

    cursor.execute("SELECT id FROM apartments WHERE name = ?", (apartment,))
    appartment_id = cursor.fetchone()
    if appartment_id == None:
        return Response('{"result": false, "error": 2, "description": "Cannot proceed because this apartment does not exist"}', status=400, mimetype="application/json")

    appartment_id = appartment_id[0]

    start_as_datetime = datetime.strptime(start, "%Y%m%d")
    from_as_timestamp = start_as_datetime.timestamp()
    to_as_timestamp = from_as_timestamp + int(duration) * 24 * 60 * 60

    # Check if appartement is already reserved during the indicated period
    logging.info(f"Trying to insert a reservation for apartment {appartment_id} from {from_as_timestamp} ({datetime.fromtimestamp(from_as_timestamp).isoformat()}) to {to_as_timestamp} ({datetime.fromtimestamp(to_as_timestamp).isoformat()})")
    
    cursor.execute("SELECT COUNT(id) FROM reservations WHERE apartment = ? AND ((period_from < ? AND period_to > ?) OR (period_from < ? AND period_to > ?) OR (period_from <= ? AND period_to >= ?))", (appartment_id, from_as_timestamp, from_as_timestamp, to_as_timestamp, to_as_timestamp, from_as_timestamp, to_as_timestamp))
    already_exists = cursor.fetchone()[0]
    if already_exists > 0:
        logging.info("Rejecting reservation, since apartment is already taken during the requested period.")
        return Response('{"result": false, "error": 2, "description": "Cannot proceed because this apartment is already reserved"}', status=400, mimetype="application/json")

    # Add appartement
    logging.info("Accepting reservation, since apartment is free during the requested period.")
    cursor.execute("INSERT INTO reservations (id, apartment, period_from, period_to, vip) VALUES (?, ?, ?, ?, ?)", (str(id), appartment_id, from_as_timestamp, to_as_timestamp, vip_as_integer))
    cursor.close()
    db_connection.close()

    # Notify everybody that the apartment was added
    mq_connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
    channel = mq_connection.channel()
    channel.exchange_declare(exchange="reservations", exchange_type="direct")

    data_to_send = {"id": str(id), "apartment": appartment_id, "from": from_as_timestamp, "to": to_as_timestamp}
    channel.basic_publish(exchange="reservations", routing_key="added", body=json.dumps(data_to_send))
    mq_connection.close()

    return Response('{"result": true, "description": "Reservation was added successfully.", "id": "' + str(id) + '"}', status=201, mimetype="application/json")


@app.route("/delete")
def delete():
    id = request.args.get("id")

    if id == None:
        return Response('{"result": false, "error": 1, "description": "Cannot proceed because you did not provide the id of the reservation."}', status=400, mimetype="application/json")

    # Connect and setup the database
    db_connection = sqlite3.connect("/home/data/reservations.db", isolation_level=None)
    cursor = db_connection.cursor()

    # Check if reservation exists
    cursor.execute("SELECT COUNT(id) FROM reservations WHERE id = ?", (id,))
    already_exists = cursor.fetchone()[0]
    if already_exists == 0:
        return Response('{"result": false, "error": 2, "description": "Cannot proceed because this reservation does not exist"}', status=400, mimetype="application/json")

    # Add appartement
    cursor.execute("DELETE FROM reservations WHERE id = ?", (id,))
    cursor.close()
    db_connection.close()

    # Notify everybody that the apartment was added
    mq_connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
    channel = mq_connection.channel()
    channel.exchange_declare(exchange="reservations", exchange_type="direct")

    data_to_send = {"id": id}
    channel.basic_publish(exchange="reservations", routing_key="deleted", body=json.dumps(data_to_send))
    mq_connection.close()

    return Response('{"result": true, "description": "Reservation was deleted successfully."}', status=201, mimetype="application/json")


@app.route("/")
def hello():
    return "Valid reservation links are:\n/reservations to list reservations\n/add?name=<apartment_name>?date=<startYmd>?duration=<duration>?vip=<1 or 0> to add a new reservation\n/delete?id=<reservationID> to delete a reservation"


@app.route("/reservations")
def reservations():
    if os.path.exists("/home/data/reservations.db"):
        db_connection = sqlite3.connect("/home/data/reservations.db", isolation_level=None)
        cursor = db_connection.cursor()
        cursor.execute("SELECT id, apartment, period_from, period_to, vip FROM reservations")
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return Response(json.dumps({"reservations": rows}), status=200, mimetype="application/json")

    return Response(json.dumps({"reservations": []}), status=200, mimetype="application/json")


def connect_to_mq():
    while True:
        time.sleep(10)

        try:
            return pika.BlockingConnection(pika.ConnectionParameters(host="rabbitmq"))
        except Exception as e:
            logging.warning(f"Could not start listening to the message queue, retrying...")


def apartment_added(ch, method, properties, body):
    data = json.loads(body)
    id = data["id"]
    name = data["name"]

    logging.info(f"Adding apartment {name}...")

    db_connection = sqlite3.connect("/home/data/reservations.db", isolation_level=None)
    cursor = db_connection.cursor()
    cursor.execute("INSERT INTO apartments VALUES (?, ?)", (id, name))
    cursor.close()
    db_connection.close()

def apartment_deleted(ch, method, properties, body):
    data = json.loads(body)
    name = data["name"]

    logging.info(f"Deleting apartment {name}...")

    db_connection = sqlite3.connect("/home/data/reservations.db", isolation_level=None)
    cursor = db_connection.cursor()
    cursor.execute("DELETE FROM apartments WHERE name = ?", (name, ))
    cursor.execute("DELETE FROM reservations WHERE apartment = ?", (name, ))
    cursor.close()
    db_connection.close()

def listen_to_events(channel):
    channel.start_consuming()

def apartment_changed(ch, method, properties, body):
    data = json.loads(body)

    if method.exchange == "apartments":
        if method.routing_key == "added":
            id = data["id"]
            name = data["name"]

            logging.info(f"Adding apartment {name}...")

            # correct
            # db_connection = sqlite3.connect("/home/data/reservations.db", isolation_level=None)
            # cursor = db_connection.cursor()
            # cursor.execute("INSERT INTO apartments VALUES (?, ?)", (id, name))
            # cursor.close()
            # db_connection.close()

            # lazy
            db_connection = sqlite3.connect("/home/data/reservations.db", isolation_level=None)
            cursor = db_connection.cursor()
            cursor.execute("DELETE FROM apartments")
            cursor.close()
            db_connection.close()
            reload_all_apartments_from_db()


        if method.routing_key == "deleted":
            name = data["name"]

            logging.info(f"Deleting apartment {name}...")

            db_connection = sqlite3.connect("/home/data/reservations.db", isolation_level=None)
            cursor = db_connection.cursor()
            cursor.execute("DELETE FROM apartments WHERE name = ?", (name,))
            cursor.close()
            db_connection.close()

def reload_all_apartments_from_db():
    db_connection = sqlite3.connect("/home/data/reservations.db", isolation_level=None)
    cursor = db_connection.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS reservations (id text, apartment text, period_from integer, period_to integer, vip integer)")
    cursor.execute("CREATE TABLE IF NOT EXISTS apartments (id text, name text)")
    
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
            
    cursor.close()
    db_connection.close()

if __name__ == "__main__":
    logging.basicConfig(format="%(message)s", level=1 * 10)
    logging.getLogger("pika").setLevel(logging.WARNING)
    logging.getLogger("sqlite3").setLevel(logging.WARNING)

    mq_connection = connect_to_mq()

    channel = mq_connection.channel()
    channel.exchange_declare(exchange="apartments", exchange_type="direct")
    result = channel.queue_declare(queue="", exclusive=True)
    queue_name = result.method.queue
    channel.queue_bind(exchange="apartments", queue=queue_name, routing_key="added")
    channel.queue_bind(exchange="apartments", queue=queue_name, routing_key="deleted")
    channel.basic_consume(queue=queue_name, on_message_callback=apartment_changed, auto_ack=True)
    
    logging.info("Waiting for messages.")
    
    thread = threading.Thread(target=listen_to_events, args=(channel,), daemon=True)
    thread.start()

    database_is_initialized = False
    if os.path.exists("/home/data/reservations.db"):
        database_is_initialized = True
    else:
        reload_all_apartments_from_db()
        database_is_initialized = True

    if not database_is_initialized:
        logging.error("Cannot initialize database.")
    else:
        try:
            logging.info("Start.")
            app.run(host="0.0.0.0", threaded=True)
        finally:
            mq_connection.close()
