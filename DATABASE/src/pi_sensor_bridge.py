from flask import Flask, jsonify
from sensor_interface import get_sensor

app = Flask(__name__)

MQ_SENSOR_IDS = [2, 3, 4, 5, 8, 9, 135]

@app.get("/health")
def health():
    return jsonify({"ok": True})

@app.get("/api/sensor")
def sensor_data():
    sensor = get_sensor()
    connected = sensor.has_environment_data()

    mq_readings = {}
    for sid in MQ_SENSOR_IDS:
        val = sensor.get_mq_reading(sid)
        if val is not None:
            mq_readings[sid] = int(val)

    return jsonify({
        "temperature": sensor.get_temperature(),
        "humidity": sensor.get_humidity(),
        "connected": connected,
        "mq_readings": mq_readings
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
