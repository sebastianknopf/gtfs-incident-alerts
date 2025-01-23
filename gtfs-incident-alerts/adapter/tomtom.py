import json
import logging
import requests


class Adapter:

    def __init__(self, key):
        self._api_version = 5
        self._api_lang = 'en-US'
        self._api_categories = '0,1,2,5,6,10,11'
        self._api_query = """
        {
            incidents {
                type,
                geometry {
                    type,
                    coordinates
                },
                properties {
                    id,
                    events {
                        description,
                        code
                    },
                    startTime,
                    endTime,
                    from,
                    to,
                    length,
                    delay,
                    timeValidity,
                    probabilityOfOccurrence
                }
            }
        }
        """

        self._api_key = key

    def fetch(self, bbox, output_filename=None) -> dict | None:

        request_fields = self._api_query.replace('\n', ' ').replace('\r', '').replace('\t', '').replace(' ', '')
        request_url = f"https://api.tomtom.com/traffic/services/{self._api_version}/incidentDetails?key={self._api_key}&bbox={bbox}&language={self._api_lang}&fields={request_fields}&categoryFilter={self._api_categories}"

        logging.info(f"HTTP Request: GET {request_url}")

        response = requests.get(request_url)
        if response.status_code == 200:
            json_response = json.loads(response.text)

            json_response['type'] = 'FeatureCollection'
            json_response['features'] = json_response['incidents']
            del json_response['incidents']

            if output_filename is not None:
                with open(output_filename, 'w', encoding='utf-8') as output_file:
                    output_file.write(json.dumps(json_response))
            else:
                return json_response
        
        else:
            logging.error(f"TomTom API response status code {response.status_code}")
            logging.info(response.text)

            if output_filename is None:
                return None
