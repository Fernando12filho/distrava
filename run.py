import threading

import webview

from app import create_app

app = create_app()


def start_flask():
    app.run(port=5000, use_reloader=False)


if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    webview.create_window("Distrava", "http://127.0.0.1:5000")
    webview.start()
