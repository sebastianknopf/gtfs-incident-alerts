# gtfs-incident-alerts
Python utility for matching incident data agains GTFS shapes and generating GTFS-RT service alerts.

## How it works
The main worker of this package requests incident data from a given source, in this the [TomTom Traffic API](https://www.tomtom.com/products/traffic-apis/) and matches them with GTFS shapes fetched from an [OpenTripPlanner](https://www.opentripplanner.org/). If there's a match between an incident and a GTFS shape of a certain line, the worker checks for an appropriate template and generates a GTFS-RT service alert for the affected line. The results can be exported as file or published to an MQTT broker as differential GTFS-RT feed.

What you need is ...
- ... a bounding box which should be monitored for incidents
- ... an API key for accessing the traffic incident data
- ... an OpenTripPlanner instance loaded with your GTFS data

The application was initially developed for Verkehrsverbund Pforzheim-Enzkreis GmbH and is further developed. Ideas, issues and other contributions are highly welcome.

## Installation
Simple clone this repository and install it with its dependencies:
```
git clone https://github.com/sebastianknopf/gtfs-incident-alerts.git
cd gtfs-incident-alerts

pip install .
```
Then run the main worker with following command:
```
python -m gtfs-incident-alerts run -b [BBOX] -k [ApiKey] -u [OtpUrl] -t templates.yaml -o gtfs-service-alerts.pbf -i 300
```
Replace the `[BBOX]` with a comma-separated coordinates for a bounding box (e.g. `8.445740,48.773388,8.986816,49.045070` for region Pforzheim), the `[ApiKey]` with your API key for accessing the incident data and `[OtpUrl]` with the endpoint to the GTFS-GraphQL-API of your OpenTripPlanner instance loaded with your GTFS data.

The option `-t` enables you to use a custom templates file, the option `-o` is the path to the destination file. Use `-i` to set a fetch interval in seconds.

### MQTT Publishing
If you want the alerts to be published to a MQTT broker, you need to specify a connection string to an MQTT broker by using option `-m` instead of `-o` for an output file. The URL needs to be in following format:
```
mqtt://[username]:[password]@[domain]/here/is/your/topic/for/alert/[alertId]
```
where `[username]` and `[password]` are optional if your broker works with authentication. The path after your domain represents the topic, the messages should be published to. 

Please note the `[alertId]` at the end: This is a placeholder which *must remain the connection string as it is*, since the messages are published as retained messages in order to make alerts available to clients connected to the broker after publishing an alert too. The `[alertId]` will be replaced by a generated UUID for each alert. The default expiration time for the retained messages is 600s. You can specify another expiration time by using option `-e` with a value in seconds.

## Templating
The incident texts are generated using a YAML template definition file. See [templates.yaml](templates.yaml) for reference. [Mako](https://www.makotemplates.org/) is used as template engine which enables you to use arbitrary python code in the templates wihtout any extra effort. Each template consists of at least following information:

- `name`: A technical name for development and debugging purposes
- `conditions`: A set of conditions with must be fulfilled that this template is considered as matching template for an incident. See section `conditions` for more information.
- `cause`: The GTFS-RT compatible cause mapped for this incident
- `effect`: The GTFS-RT compatible effect mapped for this incident
- `url`: An URL pointing to more information about this alert
- `header`: A header with basic information
- `description`: A full description of the alert

Each of the elements `url`, `header` and `description` can be specified in multiple languages by using the according language ISO code as child of the corresponding element.

Following variables are available in the templates:
- `startLocationName`: Descriptive location name of the start of the incident
- `endLocationName`: Descriptive location name of the end of the incident
- `affectedLines`: Array containing a list of objects describing a certain line. Each objects contains the keys `gtfsId`, `shortName`, `longName`, `mode` and `type`.

### Conditions
The conditions of a template are based on [TMC Event Codes](https://wiki.openstreetmap.org/wiki/TMC/Event_Code_List). Each condition needs at least one code, which is used to determine whether the template is valid for an incident or not. See the following example:
```yaml
templates:
  - name: 'sample-template'
    conditions:
      - code: 201
#...
```
This template would match to an incident containing code `201`.


Multiple conditions are handeled as logical AND; that means a template with multiple conditions may only match, if an incident has both codes:
```yaml
templates:
  - name: 'sample-template'
    conditions:
      - code: 101
      - code: 858
#...
```
This template would match to an incident containing code `101` AND `858`.

If you need to define a template for classes of incidents, you can use the `or` key to accept multiple different TMC codes handled as logical OR:
```yaml
templates:
  - name: 'sample-template'
    conditions:
      - code: 101
        or: 
            - 102
            - 103
#...
```

You can also specify a minimum delay for a template by using the key `delay` in the condition:
```yaml
templates:
  - name: 'sample-template'
    conditions:
      - code: 101
        delay: 450
#...
```
Thus, the template matches only, if the incident contains a `delay` attribute greater or equal the value in seconds in the template definition.

## License
This project is licensed under the Apache License. See [LICENSE.md](LICENSE.md) for more information.