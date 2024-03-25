from flask import Flask
from flask import request
from flask import Response
import logging
import requests

app = Flask(__name__)

@app.route("/")
def standard():
    return "Welcome to the Gateway Service!\nFrom here you can access all services!\nAppend:\n\"/apartments\" to interact with the apartment service\n\"reserve\" to interact with the reservation service\n\"search\" to interact with the searching service!"

@app.route("/apartments/")
@app.route("/apartments/add")
@app.route("/apartments/delete")
@app.route("/apartments/apartments")
def apartments():
    url = request.url.replace(request.host_url + "apartments", f"http://apartments:5000")
    logging.info(f"Requesting content from {url}...")
    response = requests.get(url)
    return Response(response.content, response.status_code, mimetype="application/json")

@app.route("/reserve/")
@app.route("/reserve/add")
@app.route("/reserve/delete")
@app.route("/reserve/reservations")
def reserve():
    url = request.url.replace(request.host_url + "reserve", f"http://reserve:5000")
    logging.info(f"Requesting content from {url}...")
    response = requests.get(url)
    return Response(response.content, response.status_code, mimetype="application/json")


@app.route("/search")
def search():
    url = request.url.replace(request.host_url, f"http://search:5000/")
    logging.info(f"Requesting content from {url}...")
    response = requests.get(url)
    return Response(response.content, response.status_code, mimetype="application/json")


if __name__ == "__main__":
    logging.basicConfig(format="%(message)s", level=1 * 10)
    logging.info("Start.")
    app.run(host="0.0.0.0", threaded=True)
