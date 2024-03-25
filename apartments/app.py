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

app = Flask(__name__)


@app.route("/add")
def add():
    id = uuid.uuid4()
    name = request.args.get("name")
    size = request.args.get("size")

    if name == None or size == None:
        return Response('{"result": false, "error": 1, "description": "Cannot proceed because you did not provide a name and a size for the apartment."}', status=400, mimetype="application/json")

    if not size.isdigit():
        return Response('{"result": false, "error": 2, "description": "Size is not a number."}', status=400, mimetype="application/json")

    # Connect and setup the database
    db_connection = sqlite3.connect("/home/data/apartments.db", isolation_level=None)
    cursor = db_connection.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS apartments (id text, name text, size integer)")

    # Check if appartement already exists
    cursor.execute("SELECT COUNT(id) FROM apartments WHERE name = ?", (name,))
    already_exists = cursor.fetchone()[0]
    if already_exists > 0:
        return Response('{"result": false, "error": 2, "description": "Cannot proceed because this apartment already exists"}', status=400, mimetype="application/json")

    # Add appartement
    cursor.execute("INSERT INTO apartments (id, name, size) VALUES (?, ?, ?)", (str(id), name, int(size)))
    cursor.close()
    db_connection.close()

    # Notify everybody that the apartment was added
    mq_connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
    channel = mq_connection.channel()
    channel.exchange_declare(exchange="apartments", exchange_type="direct")
    data_to_send = {"id": str(id), "name": name}
    channel.basic_publish(exchange="apartments", routing_key="added", body=json.dumps(data_to_send))
    mq_connection.close()

    return Response('{"result": true, "description": "Apartment was added successfully."}', status=201, mimetype="application/json")

@app.route("/delete")
def delete():
    name = request.args.get("name")

    if name == None:
        return Response('{"result": false, "error": 1, "description": "Cannot proceed because you did not provide a name for the apartment."}', status=400, mimetype="application/json")

    # Connect and setup the database
    db_connection = sqlite3.connect("/home/data/apartments.db", isolation_level=None)
    cursor = db_connection.cursor()

    # Check if appartement exists
    cursor.execute("SELECT COUNT(id) FROM apartments WHERE name = ?", (name,))
    already_exists = cursor.fetchone()[0]
    if already_exists == 0:
        return Response('{"result": false, "error": 2, "description": "Cannot proceed because this apartment does not exist"}', status=400, mimetype="application/json")

    # Add appartement
    cursor.execute("DELETE FROM apartments WHERE name = ?", (name, ))
    cursor.close()
    db_connection.close()

    # Notify everybody that the apartment was added
    mq_connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
    channel = mq_connection.channel()
    channel.exchange_declare(exchange="apartments", exchange_type="direct")
    
    data_to_send = {"name": name}
    channel.basic_publish(exchange="apartments", routing_key="deleted", body=json.dumps(data_to_send))
    mq_connection.close()

    return Response('{"result": true, "description": "Apartment was deleted successfully."}', status=201, mimetype="application/json")

@app.route("/")
def hello():
    return "Hello World from appartements!"


@app.route("/apartments")
def apartments():
    if os.path.exists("/home/data/apartments.db"):
        db_connection = sqlite3.connect("/home/data/apartments.db", isolation_level=None)
        cursor = db_connection.cursor()
        cursor.execute("SELECT id, name FROM apartments")
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return Response(json.dumps({"apartments": rows}), status=200, mimetype="application/json")

    return Response(json.dumps({"apartments": []}), status=200, mimetype="application/json")


if __name__ == "__main__":
    logging.basicConfig(format="%(message)s", level=1 * 10)
    logging.getLogger("pika").setLevel(logging.WARNING)
    logging.getLogger("sqlite3").setLevel(logging.WARNING)

    # Setup db
    db_connection = sqlite3.connect("/home/data/apartments.db", isolation_level=None)
    cursor = db_connection.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS apartments (id text, name text, size integer)")
    cursor.close()
    db_connection.close()

    logging.info("Start.")
    app.run(host="0.0.0.0", threaded=True)
