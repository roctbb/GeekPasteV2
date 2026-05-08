import eventlet

eventlet.monkey_patch()

from config import DEBUG, PORT
from paste_server import app, socketio


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', debug=DEBUG, port=PORT)
