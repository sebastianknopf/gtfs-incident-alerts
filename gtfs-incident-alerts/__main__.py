import click
import logging

from .adapter import tomtom
from .matcher import OtpGtfsMatcher

logging.basicConfig(
    level=logging.INFO, 
    format= '[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)

@click.group()
def cli():
    pass

@cli.command()
@click.option('--source', '-s', default='tomtom', help='Datasource type for generating GeoJSON file')
@click.option('--bbox', '-b', help='Bounding box as list of two tuples to load incident data for')
@click.option('--key', '-k', help='An optional API key')
@click.option('--output', '-o', default='incidents.geojson', help='Output filename for GeoJSON file')
def fetch(output, source, bbox, key):

    if source == 'tomtom':
        adapter = tomtom.Adapter(key)
        adapter.fetch(bbox, output)
    else:
        logging.error(f"unknown source type {source}")

@cli.command()
@click.option('--url', '-u', default='', help='OpenTripPlanner GraphQL GTFS endpoint for requesting GTFS data')
@click.option('--input', '-i', help='Input GeoJSON file with incident data')
@click.option('--templates', '-t', default='templates.yaml', help='YAML file containing text templates and their rules')
@click.option('--output', '-o', default=None, help='Output protobuf or JSON file for generated service alerts')
@click.option('--mqtt', '-m', default=None, help='MQTT connection and topic URI')
@click.option('--expiration', '-e', default=600, help='MQTT message expiration time. Only used in MQTT publishing')
def match(url, input, templates, output, mqtt, expiration):
    
    if output is None and mqtt is None:
        logging.error('either --output/-o or --mqtt/-m must be specified')
        return

    matcher = OtpGtfsMatcher(url, templates)
    matcher.match(input, output, mqtt, expiration)

if __name__ == '__main__':
    cli()