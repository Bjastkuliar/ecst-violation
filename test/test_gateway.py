import requests
import uuid
import sqlite3
import time
import json
import pytest

data_folder = "..\\data"

def clean_up():
    r1 = requests.get(f"http://localhost:5050/apartments/apartments")
    apartments = json.loads(r1.content)["apartments"]
    for entry in apartments:
        apartment = entry["name"]
        requests.get(f"http://localhost:5050/apartments/delete?name={apartment}")

def test_apartment():
    clean_up()

    random_apartment_name = str(uuid.uuid4())

    r1 = requests.get(f"http://localhost:5050/apartments/add")
    assert r1.status_code == 400, "Test if status code 400 (Bad request) is returned if not enough data is provided"

    r2 = requests.get(f"http://localhost:5050/apartments/add?name={random_apartment_name}")
    assert r2.status_code == 400, "Test if status code 400 (Bad request) is returned if size is missing"

    r3 = requests.get(f"http://localhost:5050/apartments/add?name={random_apartment_name}&size=50")
    assert r3.status_code == 201, "Test if new apartment can be added"

    assert apartment_exists_in_db("apartments", random_apartment_name), "Test if new apartment was added to the apartment db"
    time.sleep(1)  # Give some time to services to receive update from message queue
    assert apartment_exists_in_db("search", random_apartment_name), "Test if new apartment was added to the search db"
    assert apartment_exists_in_db("reservations", random_apartment_name), "Test if new apartment was added to the reservations db"

    r4 = requests.get(f"http://localhost:5050/apartments/add?name={random_apartment_name}&size=150")
    assert r4.status_code == 400, "Test if new apartment cannot be added another time and the response is status code 400 (Bad request)"

    r5 = requests.get(f"http://localhost:5050/apartments/delete")
    assert r5.status_code == 400, "Test if status code 400 (Bad request) is returned if not enough data is provided"

    r6 = requests.get(f"http://localhost:5050/apartments/delete?name={random_apartment_name}")
    assert r6.status_code == 201, "Test if new apartment can be deleted"

    assert not apartment_exists_in_db("apartments", random_apartment_name), "Test if new apartment was deleted from the apartment db"
    time.sleep(1)  # Give some time to services to receive update from message queue
    assert not apartment_exists_in_db("search", random_apartment_name), "Test if new apartment was deleted from the search db"
    assert not apartment_exists_in_db("reservations", random_apartment_name), "Test if new apartment was deleted from the search db"


def test_reservation():
    clean_up()

    random_apartment_name = str(uuid.uuid4())
    
    requests.get(f"http://localhost:5050/apartments/add?name={random_apartment_name}&size=100")
    time.sleep(1)  # Give some time to services to receive update from message queue

    r1 = requests.get(f"http://localhost:5050/reserve/add")
    assert r1.status_code == 400, "Test if status code 400 (Bad request) is returned if not enough data is provided"

    r2 = requests.get(f"http://localhost:5050/reserve/add?name={random_apartment_name}")
    assert r2.status_code == 400, "Test if status code 400 (Bad request) is returned if size is missing"

    r3 = requests.get(f"http://localhost:5050/reserve/add?name={random_apartment_name}&start=20010101&duration=10&vip=1")
    assert r3.status_code == 201, "Test if new reservation can be added"
    id = json.loads(r3.content)["id"]

    assert reservation_exists_in_db("reservations", id), "Test if new reservation was added to the reservations db"
    time.sleep(1)  # Give some time to services to receive update from message queue
    assert reservation_exists_in_db("search", id), "Test if new reservation was added to the search db"

    r4 = requests.get(f"http://localhost:5050/reserve/add?name={random_apartment_name}&start=20010101&duration=10&vip=1")
    assert r4.status_code == 400, "Test if new reservation cannot be added another time and the response is status code 400 (Bad request)"

    r4_1 = requests.get(f"http://localhost:5050/reserve/add?name={random_apartment_name}&start=20010102&duration=8&vip=1")
    assert r4_1.status_code == 400, "Test if a conflicting reservation cannot be added and the response is status code 400 (Bad request)"

    r4_2 = requests.get(f"http://localhost:5050/reserve/add?name={random_apartment_name}&start=20010109&duration=5&vip=1")
    assert r4_2.status_code == 400, "Test if a conflicting reservation cannot be added and the response is status code 400 (Bad request)"

    r5 = requests.get(f"http://localhost:5050/reserve/delete")
    assert r5.status_code == 400, "Test if status code 400 (Bad request) is returned if not enough data is provided"

    r6 = requests.get(f"http://localhost:5050/reserve/delete?id={id}")
    assert r6.status_code == 201, "Test if new reservation can be deleted"

    assert not reservation_exists_in_db("reservations", id), "Test if new reservation was deleted from the reservations db"
    time.sleep(1)  # Give some time to services to receive update from message queue
    assert not reservation_exists_in_db("search", id), "Test if new reservation was deleted from the search db"

def test_search():
    clean_up()

    # Setup apartment to search
    random_apartment_name_1 = "Apartment1"
    random_apartment_name_2 = "Apartment2"
    requests.get(f"http://localhost:5050/apartments/add?name={random_apartment_name_1}&size=100")
    requests.get(f"http://localhost:5050/apartments/add?name={random_apartment_name_2}&size=100")
    time.sleep(1)  # Give some time to services to receive update from message queue
    requests.get(f"http://localhost:5050/reserve/add?name={random_apartment_name_1}&start=20010101&duration=10&vip=1")
    time.sleep(1)  # Give some time to services to receive update from message queue

    r1 = requests.get(f"http://localhost:5050/search")
    assert r1.status_code == 400, "Test if status code 400 (Bad request) is returned if not enough data is provided"

    r2 = requests.get(f"http://localhost:5050/search?date=20010101")
    assert r2.status_code == 400, "Test if status code 400 (Bad request) is returned if duration is missing"

    r3 = requests.get(f"http://localhost:5050/search?date=20010101&duration=10")
    assert r3.status_code == 200, "Test search"
    apartments = list(map(lambda x: x["name"], json.loads(r3.content)["apartments"]))

    assert random_apartment_name_1 not in apartments
    assert random_apartment_name_2 in apartments


def apartment_exists_in_db(db, name):
    print(f"Checking if {name} exists in apartments...")
    connection = sqlite3.connect(f"C:\\Users\\Alberto\\Desktop\\Thesis stuff\\cse-microservices4-fixed\\data\\{db}.db", isolation_level=None)
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(id) FROM apartments WHERE name = ?", (name,))
    exists = cursor.fetchone()[0]
    cursor.close()
    connection.close()
    return exists == 1


def reservation_exists_in_db(db, id):
    print(f"Checking if {id} exists in reservations...")
    connection = sqlite3.connect(f"C:\\Users\\Alberto\\Desktop\\Thesis stuff\\cse-microservices4-fixed\\data\\{db}.db", isolation_level=None)
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(id) FROM reservations WHERE id = ?", (id,))
    exists = cursor.fetchone()[0]
    cursor.close()
    connection.close()
    return exists == 1
