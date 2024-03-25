# Detecting Event Carried State Transfer Violations in an Event Driven Architecture
In order to reduce the verbosity of the [README](README.md) some abbreviations have been adopted.
- **ECST** for *Event Carried State Transfer*
- **EDA** for *Event Driven Architecture*

This repo is meant as a companion of the bachelor thesis (link TBA) of mine.
## Repo Structure
The repo is composed of three branches:
- [basic-system]() where a basic version of the application system is stored (without the telemetry capture)
-  [main](https://github.com/Bjastkuliar/ecst-violation/tree/main) which holds a copy of the EDA with the instrumentation in place
- [faulty-system](https://github.com/Bjastkuliar/ecst-violation/tree/faulty-system) which holds the same system with a violation of the ECST principles (dependecy anti-pattern) purposely implemented
## How to run
To get the system running follow the steps listed below, beware that the application is built with [DockerComposeV2](https://docs.docker.com/compose/migrate/) (pytest may fail otherwise).
### 1. Gather the necessary software
The system requires 3 programmes to be installed locally:
- [Python](https://www.python.org/downloads/): the application uses [Flask](https://flask.palletsprojects.com/en/3.0.x/) for simulating the behaviour of a server on which each service is hosted.
- [Docker Compose](https://docs.docker.com/compose/install/): the application makes use of the container technology for simulating the system. Additionally by utilising compose it is possible to start each service with the ports already configured.
### 2.Get the application running
By executing the command `docker compose up --build` the application system will deploy automatically in its entirety (along with jaeger as telemetry capture service). 
### 3.Produce telemetry
Either interact with the system (by either querying the `gateway` service or the single services themselves) or run `pytest` for some interactions to be simulated and recorded.
### 4.Visualise interaction data
Access the frontend of the collection service by opening the web browser at the frontend port of [Jaeger](https://www.jaegertracing.io/docs/1.55/frontend-ui/).