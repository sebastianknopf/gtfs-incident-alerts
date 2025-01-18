
call venv/Scripts/activate.bat

set %1
set %2
set %3

python -m gtfs-incident-alerts fetch -b %bbox% -k %key% -o incidents.geojson
python -m gtfs-incident-alerts match -u %otpurl% -i incidents.geojson -o service-alerts.pbf

deactivate

