from gql import gql, Client
from gql.transport.httpx import HTTPXTransport


class OtpClient:

    def __init__(self, otp_url: str):
        gql_transport = HTTPXTransport(url=otp_url)
        self._gql_client = Client(transport=gql_transport, fetch_schema_from_transport=False)
        self._gql_query = """
        query PatternsWithShapes($date: String!) {
            patterns {
                headsign
                directionId
                route {
                    gtfsId
                    shortName
                    longName
                    mode
                    type
                }
                tripsForDate(serviceDate: $date) {
                    gtfsId
                }
                patternGeometry {
                    points
                }
            }
        }
        """
        
    def load_active_pattern(self, date: str) -> dict:
        gql_result = self._gql_client.execute(gql(self._gql_query), variable_values={
            'date': date
        })

        result = list()
        if gql_result['patterns'] is not None:
            for pattern in gql_result['patterns']:
                if pattern['patternGeometry'] is None:
                    continue

                if len(pattern['tripsForDate']) == 0:
                    continue

                del pattern['tripsForDate']

                pattern['route']['gtfsId'] = self._strip_feed_id(pattern['route']['gtfsId'])

                result.append(pattern)

        return result
    
    def _strip_feed_id(self, obj_id: str) -> str:
        if ':' in obj_id:
            return obj_id[obj_id.find(':') + 1:]
        else:
            return obj_id
